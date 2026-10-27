from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from defuse.automate.intake import detector_failure
from defuse.automate.policy import DependencyPolicy, check_dependencies
from defuse.automate.postmortem import publish
from defuse.automate.sandbox import SandboxGitLab
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings
from defuse.execute.gcp import GcloudOps
from defuse.model.incident import Incident, IncidentOrigin, IncidentStatus
from defuse.scenario import NAMESPACE, T0
from defuse.store.repository import Store


def test_only_a_failed_detector_with_recorded_findings_opens_an_incident() -> None:
    event = {
        "object_attributes": {"id": 10, "status": "failed", "finished_at": "2026-10-27T10:00:00Z"}
    }
    jobs = [{"id": 20, "name": "test", "status": "failed"}]
    trace = "DETECTOR: 1 IOC match(es), 0 provenance mismatch(es)"
    assert detector_failure(event, jobs, trace) is None
    jobs[0]["name"] = "detect"
    assert detector_failure(event, jobs, "DETECTOR: clean") is None
    result = detector_failure(event, jobs, trace)
    assert result is not None
    assert result[:2] == (20, 10)
    assert result[2].tzinfo is not None


async def test_release_age_policy_uses_registry_timestamps(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"app"}')
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {"lockfileVersion": 3, "packages": {"node_modules/example": {"version": "1.0.0"}}}
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"time": {"1.0.0": "2026-10-27T10:00:00Z"}})
        )
    ) as client:
        failures = await check_dependencies(
            tmp_path,
            DependencyPolicy(incident_id="1"),
            http=client,
            now=datetime(2026, 10, 27, 11, tzinfo=UTC),
        )
    assert failures == ["example@1.0.0: younger than 24 hours"]


async def test_missing_release_metadata_does_not_silently_pass(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"app"}')
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {"lockfileVersion": 3, "packages": {"node_modules/example": {"version": "1.0.0"}}}
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        failures = await check_dependencies(
            tmp_path, DependencyPolicy(incident_id="1"), http=client
        )
    assert failures


async def make_store(path: Path) -> Store:
    store = Store(f"sqlite+aiosqlite:///{path}")
    await store.create_all()
    await store.upsert_incident(
        Incident(
            id="boundary",
            title="Boundary incident",
            ioc_id="test-ioc",
            origin=IncidentOrigin.SCENARIO,
            status=IncidentStatus.OPEN,
            namespace=NAMESPACE,
            created_at=T0,
            detected_at=T0,
        )
    )
    return store


async def test_action_lease_excludes_another_process_and_releases(tmp_path: Path) -> None:
    first = await make_store(tmp_path / "leases.db")
    second = Store(f"sqlite+aiosqlite:///{tmp_path}/leases.db")
    try:
        async with first.action_lock("boundary", "action"):
            with pytest.raises(RuntimeError, match="another worker"):
                async with second.action_lock("boundary", "action"):
                    pytest.fail("second worker acquired a held action")
        async with second.action_lock("boundary", "action"):
            pass
    finally:
        await first.dispose()
        await second.dispose()


async def test_postmortem_is_idempotent_and_policy_mr_adds_enforcement(tmp_path: Path) -> None:
    store = await make_store(tmp_path / "postmortem.db")
    backend = SandboxGitLab()
    try:
        async with GitLabClient(
            "https://gitlab.test", None, (NAMESPACE,), transport=backend.transport()
        ) as gl:
            settings = Settings()
            first = await publish(store, gl, settings, "boundary", 101)
            second = await publish(store, gl, settings, "boundary", 101)
            assert first == second
            assert len(backend.issues) == 1
            assert len(backend.mrs) == 1
            mr = next(iter(backend.mrs.values()))
            proposed = backend.commits[mr["sha"]]
            assert ".gitlab/defuse-policy.yml" in proposed
            assert ".defuse/policies/boundary.json" in proposed
            assert "policy-check" in proposed[".gitlab/defuse-policy.yml"]
            before = len(backend.mutations)
            await publish(store, gl, settings, "boundary", 101, dry_run=True)
            assert len(backend.mutations) == before
    finally:
        await store.dispose()


async def test_snapshot_uses_the_attached_boot_disk_and_stable_name() -> None:
    class FakeGcloud(GcloudOps):
        def __init__(self) -> None:
            super().__init__("project", "zone")
            self.calls: list[tuple[str, ...]] = []

        async def _gcloud(self, *args: str) -> str:
            self.calls.append(args)
            if args[1:3] == ("snapshots", "list"):
                return "[]"
            if args[1:3] == ("instances", "describe"):
                return json.dumps(
                    {"disks": [{"boot": True, "source": "projects/p/disks/actual-boot-disk"}]}
                )
            return ""

    gcp = FakeGcloud()
    assert await gcp.snapshot_disk("runner-host", name="stable-snapshot") == "stable-snapshot"
    assert gcp.calls[-1][3] == "actual-boot-disk"
    assert "--snapshot-names=stable-snapshot" in gcp.calls[-1]
