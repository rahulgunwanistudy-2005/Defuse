"""Deterministic event qualification and validated flow-application boundaries."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from defuse.automate.flows import DuoRunner, FlowRequest
from defuse.automate.models import FileEdit, FlowDraft
from defuse.automate.repository import PendingChange, RepositoryChanges
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings


def detector_failure(
    event: dict[str, Any], jobs: list[dict[str, Any]], trace: str
) -> tuple[int, int, datetime] | None:
    attributes = event.get("object_attributes", {})
    if attributes.get("status") != "failed":
        return None
    job = next((j for j in jobs if j.get("name") == "detect" and j.get("status") == "failed"), None)
    if job is None:
        return None
    matched = re.search(r"DETECTOR: (\d+) IOC match\(es\), (\d+) provenance mismatch\(es\)", trace)
    if matched is None or int(matched[1]) + int(matched[2]) == 0:
        return None
    timestamp = attributes.get("finished_at") or attributes.get("created_at")
    if not isinstance(timestamp, str):
        raise ValueError("detector event is missing its recorded timestamp")
    detected = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if detected.tzinfo is None:
        raise ValueError("detector timestamp must carry a timezone")
    return int(job["id"]), int(attributes["id"]), detected


async def apply_draft(
    gl: GitLabClient,
    settings: Settings,
    request: FlowRequest,
    draft: FlowDraft,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    # Revalidate at the mutation boundary, including drafts constructed by another caller.
    request.validate_output(draft.model_dump_json())
    paths = {e.file_path for e in draft.edits}
    await gl.assert_mutable(request.project_id)
    if dry_run:
        return {"status": "dry_run", "paths": sorted(paths), "mr_url": None}
    try:
        changed, url = await RepositoryChanges(
            gl, auto_merge=settings.auto_merge_remediation, timeout=settings.action_timeout
        ).apply(
            request.project_id,
            request.incident_id,
            request.flow,
            draft.title,
            description=draft.description,
            edits=draft.edits,
            allowed=set(request.allowed_paths),
        )
        return {
            "status": "applied" if changed else "already_satisfied",
            "paths": sorted(paths),
            "mr_url": url,
        }
    except PendingChange as pending:
        return {
            "status": "pending",
            "paths": sorted(paths),
            "mr_url": pending.url,
            "detail": str(pending),
        }


async def intake_pipeline(
    gl: GitLabClient,
    settings: Settings,
    event: dict[str, Any],
    ioc_path: str,
    namespace: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    from defuse.workflow import IncidentRequest

    FileEdit(action="delete", file_path=ioc_path)
    project = int(event["project"]["id"])
    await gl.assert_mutable(project)
    pipeline = int(event["object_attributes"]["id"])
    jobs = [j async for j in gl.paginate(f"/api/v4/projects/{project}/pipelines/{pipeline}/jobs")]
    job = next((j for j in jobs if j.get("name") == "detect" and j.get("status") == "failed"), None)
    if job is None:
        return {"status": "ignored", "reason": "no failed Defuse detector job"}
    trace = await gl.get_text(
        f"/api/v4/projects/{project}/jobs/{int(job['id'])}/trace", max_bytes=2 * 1024 * 1024
    )
    qualified = detector_failure(event, jobs, trace)
    if qualified is None:
        return {"status": "ignored", "reason": "no authenticated detector findings"}
    _, pipeline, detected = qualified
    incident = f"gitlab-{project}-{pipeline}"
    request = IncidentRequest(
        incident_id=incident,
        ioc_path=ioc_path,
        namespace=namespace,
        detected_at=detected,
        pipeline_url=event["object_attributes"].get("url"),
    )
    edit = FileEdit(
        action="create",
        file_path=f"incidents/{incident}/request.json",
        content=request.model_dump_json(indent=2) + "\n",
    )
    goal = {
        "pipeline_id": pipeline,
        "detector_job_id": int(job["id"]),
        "detected_at": detected.isoformat(),
    }
    flow = FlowRequest(
        flow="incident-commander",
        incident_id=incident,
        project_id=project,
        goal=goal,
        allowed_paths=(edit.file_path,),
        expected_edits=(edit,),
    )
    draft = (
        await DuoRunner(settings.duo_timeout).draft(flow)
        if settings.duo_enabled
        else FlowDraft(
            flow="incident-commander",
            incident_id=incident,
            project_id=project,
            title=f"Contain detector incident {incident}",
            description=json.dumps(goal, indent=2),
            edits=(edit,),
        )
    )
    result = await apply_draft(gl, settings, flow, draft, dry_run=dry_run)
    if dry_run:
        return {**result, "incident_id": incident}
    title = f"Defuse incident {incident}"
    existing = [
        i
        async for i in gl.paginate(
            f"/api/v4/projects/{project}/issues", {"search": title, "in": "title"}
        )
        if i.get("title") == title
    ]
    issue = (
        existing[0]
        if existing
        else await gl.mutate(
            "POST",
            f"/api/v4/projects/{project}/issues",
            project=project,
            json_body={
                "title": title,
                "description": draft.description,
                "labels": "defuse,incident",
            },
        )
    )
    return {**result, "incident_id": incident, "issue_url": issue.get("web_url")}


def audit_record(
    settings: Settings, operation: str, project: int, dry_run: bool, result: dict[str, Any]
) -> Path:
    from datetime import UTC

    root = settings.records_dir / "flows"
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "operation": operation,
        "project_id": project,
        "actor": settings.actor,
        "dry_run": dry_run,
        "at": datetime.now(UTC).isoformat(),
        "result": result,
    }
    path = root / (uuid4().hex + ".json")
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path
