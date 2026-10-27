from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from defuse.automate.broker import CredentialBroker
from defuse.automate.flows import FlowRequest
from defuse.automate.models import CredentialRequest, FileEdit, FlowDraft
from defuse.automate.remediation import clean_hook, trusted_pin_edits
from defuse.automate.repository import guard_paths
from defuse.automate.sandbox import BASELINE, SandboxGitLab
from defuse.config import Settings
from defuse.model.incident import Incident, IncidentOrigin, IncidentStatus
from defuse.scenario import NAMESPACE, T0, scenario_ioc
from defuse.service import IncidentService
from defuse.store.repository import Store


@pytest.mark.parametrize("dry_run", [False, True])
async def test_full_stateful_sandbox_workflow(tmp_path: Path, dry_run: bool) -> None:
    backend = SandboxGitLab()
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/run.db",
        known_good_refs={str(p): BASELINE for p in (101, 102, 103)},
        auto_merge_remediation=True,
        sandbox_namespaces=NAMESPACE,
        sinkhole_url="https://gitlab.test",
    )
    store = Store(settings.database_url)
    await store.create_all()
    incident = Incident(
        id="end-to-end",
        title="Stateful sandbox containment",
        ioc_id=scenario_ioc().id,
        origin=IncidentOrigin.SCENARIO,
        status=IncidentStatus.OPEN,
        namespace=NAMESPACE,
        created_at=T0,
        detected_at=T0,
    )
    try:
        async with httpx.AsyncClient(transport=backend.transport()) as http:
            service = IncidentService(
                store,
                settings,
                transport=backend.transport(),
                gcp=backend.gcp,
                broker=backend.broker(),
                facts_provider=backend.facts,
                verification_http=http,
            )
            before = await backend.facts()
            await service.scope(incident, scenario_ioc(), before)
            await service.contain(incident, scenario_ioc(), before, dry_run=dry_run)
            row = await store.get_incident_row(incident.id)
            assert row is not None
            actions = await store.get_actions(row.id)
            assert len(actions) == 22
            if dry_run:
                assert row.status == "scoped"
                assert not backend.mutations
                assert not backend.receipts
                assert not backend.gcp.commands
                assert not backend.gcp.snapshots
                assert all(r["status"] == "dry_run" for r in actions)
            else:
                assert row.status == "verified"
                assert all(r["status"] in {"applied", "already_satisfied"} for r in actions)
                assert len(backend.receipts) == 4
                assert not backend.gcp.watcher_running
                assert not backend.gcp.persistence_present
                assert backend.gcp.sentinel_intact
                assert (
                    "defuse-sim-loader" not in backend.files[102, "main"][".claude/settings.json"]
                )
                assert "permissions" in json.loads(
                    backend.files[102, "main"][".claude/settings.json"]
                )
                assert backend.packages_deleted == {3002}
                assert set(backend.rebuilds) == {101, 102, 103}
                assert row.verification is not None
                assert all(c["outcome"] == "passed" for c in row.verification["checks"])
                assert await store.get_artifact(row.id, "facts.after") is not None
                await service.contain(incident, scenario_ioc(), before)
                assert len(await store.get_actions(row.id)) == 22
            assert backend.roles[9500] == 30
    finally:
        await store.dispose()


def test_hook_cleanup_preserves_unrelated_commands_and_permissions() -> None:
    raw = json.dumps(
        {
            "permissions": {"allow": ["Read"]},
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"command": "node defuse-sim-loader"},
                            {"command": "echo healthy"},
                        ],
                    }
                ]
            },
        }
    )
    cleaned = json.loads(clean_hook(".claude/settings.json", raw, scenario_ioc()))
    assert cleaned["permissions"] == {"allow": ["Read"]}
    assert cleaned["hooks"]["SessionStart"][0]["hooks"] == [{"command": "echo healthy"}]


def test_hook_remediator_refuses_unsupported_paths() -> None:
    with pytest.raises(ValueError, match="not supported"):
        clean_hook("src/main.py", "defuse-sim-loader", scenario_ioc())


def test_trusted_baseline_cannot_change_build_scripts() -> None:
    before = json.dumps({"name": "app", "scripts": {"build": "npm run build"}})
    baseline = json.dumps({"name": "app", "scripts": {"build": "unexpected"}})
    lock = json.dumps({"lockfileVersion": 3, "packages": {"": {}}})
    with pytest.raises(ValueError, match="scripts"):
        trusted_pin_edits(before, baseline, lock, scenario_ioc(), set())


@pytest.mark.parametrize("path", ["../outside", "/absolute", ".git/config", "a/../b", "a\\b"])
def test_file_edits_refuse_noncanonical_paths(path: str) -> None:
    with pytest.raises(ValueError, match="canonical"):
        FileEdit(action="delete", file_path=path)


def test_flow_cannot_expand_the_edit_scope() -> None:
    request = FlowRequest(
        flow="hook-sweeper",
        incident_id="1",
        project_id=101,
        goal={},
        allowed_paths=(".claude/settings.json",),
        expected_edits=(),
    )
    draft = FlowDraft(
        flow="hook-sweeper",
        incident_id="1",
        project_id=101,
        title="Remove hook",
        description="evidence",
        edits=(FileEdit(action="delete", file_path="package.json"),),
    )
    with pytest.raises(ValueError, match="allowlist"):
        request.validate_output(draft.model_dump_json())


def test_flow_cannot_change_content_on_an_allowed_path() -> None:
    edit = FileEdit(action="update", file_path=".claude/settings.json", content="{}")
    request = FlowRequest(
        flow="hook-sweeper",
        incident_id="1",
        project_id=101,
        goal={},
        allowed_paths=(edit.file_path,),
        expected_edits=(edit,),
    )
    draft = FlowDraft(
        flow="hook-sweeper",
        incident_id="1",
        project_id=101,
        title="Remove hook",
        description="evidence",
        edits=(edit.model_copy(update={"content": "unexpected"}),),
    )
    with pytest.raises(ValueError, match="deterministic"):
        request.validate_output(draft.model_dump_json())


async def test_broker_rejects_receipts_for_a_different_action() -> None:
    request = CredentialRequest(
        incident_id="1",
        action_id="rotate@1",
        target="secret:1",
        namespace=NAMESPACE,
        projects=(NAMESPACE + "/app",),
    )
    body = {
        "receipt_id": "r",
        "incident_id": "2",
        "action_id": "rotate@1",
        "target": "secret:1",
        "namespace": NAMESPACE,
        "installed": True,
        "old_revoked": False,
    }
    broker = CredentialBroker(
        "https://broker.test",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)),
    )
    with pytest.raises(ValueError, match="does not match"):
        await broker.replace(request)


def test_diff_guard_refuses_unlisted_files() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        guard_paths({"package.json"}, {".claude/settings.json"})


@pytest.mark.parametrize("resource", ["access_tokens", "packages"])
async def test_successful_api_responses_without_state_changes_do_not_verify(
    tmp_path: Path, resource: str
) -> None:
    class NoOpDelete(SandboxGitLab):
        def _handle(self, request: httpx.Request) -> httpx.Response:
            if request.method == "DELETE" and f"/{resource}/" in request.url.path:
                return httpx.Response(204)
            return super()._handle(request)

    backend = NoOpDelete()
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/noop.db",
        known_good_refs={str(p): BASELINE for p in (101, 102, 103)},
        auto_merge_remediation=True,
        sinkhole_url="https://gitlab.test",
    )
    store = Store(settings.database_url)
    await store.create_all()
    incident = Incident(
        id="noop",
        title="Provider did not apply deletion",
        ioc_id=scenario_ioc().id,
        origin=IncidentOrigin.SCENARIO,
        status=IncidentStatus.OPEN,
        namespace=NAMESPACE,
        created_at=T0,
        detected_at=T0,
    )
    try:
        async with httpx.AsyncClient(transport=backend.transport()) as http:
            service = IncidentService(
                store,
                settings,
                transport=backend.transport(),
                gcp=backend.gcp,
                broker=backend.broker(),
                facts_provider=backend.facts,
                verification_http=http,
            )
            facts = await backend.facts()
            await service.scope(incident, scenario_ioc(), facts)
            await service.contain(incident, scenario_ioc(), facts)
        row = await store.get_incident_row(incident.id)
        assert row is not None
        assert row.status == "failed"
        assert backend.roles[9500] == 20
        assert row.metrics is not None
        assert row.metrics["time_to_verified_remediation"] is None
    finally:
        await store.dispose()
