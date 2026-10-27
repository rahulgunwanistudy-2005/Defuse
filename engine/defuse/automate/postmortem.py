"""Idempotent incident publication and deterministic prevention-policy proposals."""

from __future__ import annotations

import json
from typing import Any

import yaml

from defuse.automate.flows import DuoRunner, FlowRequest
from defuse.automate.models import FileEdit
from defuse.automate.repository import RepositoryChanges
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings
from defuse.store.repository import Store


def render_record(record: dict[str, Any]) -> str:
    incident = record["incident"]
    metrics = record.get("metrics") or {}
    checks = (record.get("verification") or {}).get("checks", [])
    lines = [
        f"# Defuse incident {incident['id']}",
        "",
        incident["title"],
        "",
        f"Status: {record['status']}",
        "",
        "## Measured timings",
    ]
    for name in (
        "time_to_detect",
        "time_to_scope",
        "time_to_containment",
        "time_to_verified_remediation",
    ):
        timing = metrics.get(name)
        lines.append(
            f"- {name.replace('_', ' ')}: {timing if timing is not None else 'unmeasured'}"
        )
    lines += ["", "## Verification"]
    lines += [f"- {c['id']}: {c['outcome']} — {c['detail']}" for c in checks]
    lines += ["", "## Could not verify"]
    unknown = [c for c in checks if c["outcome"] != "passed"]
    lines += [f"- {c['id']}: {c['detail']}" for c in unknown] or ["All recorded checks passed."]
    lines += ["", "## Actions"]
    lines += [f"- {a['kind']} {a['target']}: {a['status']}" for a in record["actions"]]
    lines += ["", "## Timeline"]
    lines += [f"- {e['at']}: {e['message'] or e['kind']}" for e in record.get("events", [])]
    return "\n".join(lines) + "\n"


async def publish(
    store: Store,
    gl: GitLabClient,
    settings: Settings,
    incident_id: str,
    project_id: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    row = await store.get_incident_row(incident_id)
    if row is None:
        raise ValueError("unknown incident")
    record = {
        "incident": row.data,
        "status": row.status,
        "metrics": row.metrics,
        "verification": row.verification,
        "actions": await store.get_actions(incident_id),
        "events": await store.get_events(incident_id),
    }
    text = render_record(record)
    policy = {
        "incident_id": incident_id,
        "lockfile_required": True,
        "minimum_release_age_hours": 24,
        "variable_scope_review": [
            {
                "name": n["name"],
                "owner": n["owner"],
                "current_scope": n.get("environment_scope", "*"),
            }
            for n in (row.graph or {}).get("nodes", [])
            if n["kind"] == "secret" and n.get("environment_scope", "*") == "*"
        ],
        "install_scripts": "require_explicit_review",
    }
    edit = FileEdit(
        action="create",
        file_path=f".defuse/policies/{incident_id}.json",
        content=json.dumps(policy, indent=2) + "\n",
    )
    repo = RepositoryChanges(gl, auto_merge=False)
    metadata = await gl.get(f"/api/v4/projects/{project_id}")
    ref = str(metadata.get("default_branch") or "main")
    ci = await repo.read(project_id, ".gitlab-ci.yml", ref)
    ci_doc = yaml.safe_load(ci) if ci else {}
    if not isinstance(ci_doc, dict):
        raise ValueError("project CI configuration must be a YAML mapping")
    includes = ci_doc.get("include", [])
    if not isinstance(includes, list):
        includes = [includes]
    include = {"local": ".gitlab/defuse-policy.yml"}
    if include not in includes:
        includes.append(include)
    ci_doc["include"] = includes
    policy_ci = {
        "defuse:dependency-policy": {
            "stage": ".pre",
            "image": "$DEFUSE_EXECUTOR_IMAGE",
            "script": ["defuse workflow policy-check ."],
            "allow_failure": False,
        }
    }
    candidates = (
        edit,
        FileEdit(
            action="update" if ci is not None else "create",
            file_path=".gitlab-ci.yml",
            content=yaml.safe_dump(ci_doc, sort_keys=False),
        ),
        FileEdit(
            action="create",
            file_path=".gitlab/defuse-policy.yml",
            content=yaml.safe_dump(policy_ci, sort_keys=False),
        ),
    )
    edits = []
    for candidate in candidates:
        current = await repo.read(project_id, candidate.file_path, ref)
        if current != candidate.content:
            edits.append(
                candidate.model_copy(
                    update={"action": "update" if current is not None else "create"}
                )
            )
    title = f"Defuse incident {incident_id}"
    proposal_title = "Prevent recurrence after " + incident_id
    proposal_description = text
    if settings.duo_enabled and not dry_run:
        draft = await DuoRunner(settings.duo_timeout).draft(
            FlowRequest(
                flow="postmortem-policy",
                incident_id=incident_id,
                project_id=project_id,
                goal={"record": record},
                allowed_paths=(),
                expected_edits=(),
            )
        )
        proposal_title, proposal_description = draft.title, draft.description
    if dry_run:
        result = {
            "dry_run": True,
            "issue_title": title,
            "policy_paths": [e.file_path for e in edits],
        }
        await store.emit(incident_id, "postmortem.dry_run", result)
        return result
    await gl.assert_mutable(project_id)
    known = await store.get_artifact(incident_id, "postmortem.issue")
    if known is None:
        existing = [
            i
            async for i in gl.paginate(
                f"/api/v4/projects/{project_id}/issues", {"search": title, "in": "title"}
            )
            if i.get("title") == title
        ]
        known = (
            existing[0]
            if existing
            else await gl.mutate(
                "POST",
                f"/api/v4/projects/{project_id}/issues",
                project=project_id,
                json_body={"title": title, "description": text, "labels": "defuse,incident"},
            )
        )
        await store.put_artifact(
            incident_id, "postmortem.issue", {"iid": known["iid"], "web_url": known.get("web_url")}
        )
    # Prevention is proposed as an MR; merging policy is a separate governance decision.
    from defuse.automate.repository import PendingChange

    try:
        _, url = await RepositoryChanges(gl, auto_merge=False).apply(
            project_id,
            incident_id,
            "policy",
            proposal_title,
            description=proposal_description,
            edits=tuple(edits),
            allowed={e.file_path for e in edits},
        )
    except PendingChange as pending:
        url = pending.url
    result = {"issue_url": known.get("web_url"), "policy_mr_url": url, "dry_run": False}
    await store.put_artifact(incident_id, "postmortem.result", result)
    await store.emit(incident_id, "postmortem.published", result)
    return result
