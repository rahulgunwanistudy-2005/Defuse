from __future__ import annotations

import httpx
import pytest

from defuse.collect.gitlab import GitLabClient
from defuse.execute.executors import ExecutionContext, execute
from defuse.execute.gcp import RecordingGcpOps
from defuse.execute.runner import enrich, run_plan
from defuse.graph import build_exposure_graph
from defuse.model.incident import ActionRecord, RecordStatus
from defuse.model.plan import ActionKind
from defuse.plan.planner import plan_incident
from defuse.scenario import scenario_facts, scenario_ioc


def _client(dry_run: bool = False) -> GitLabClient:
    state = {"token": 41, "deploy_present": True, "package_present": True, "paused": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if (
            path.startswith("/api/v4/projects/")
            and path.count("/") == 4
            and request.method == "GET"
        ):
            pid = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"path_with_namespace": f"defuse-sandbox/p{pid}"})
        if path == "/api/v4/runners/7" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "paused": state["paused"],
                    "active": not state["paused"],
                    "projects": [{"path_with_namespace": "defuse-sandbox/app-a"}],
                },
            )
        if path == "/api/v4/runners/7" and request.method == "PUT":
            state["paused"] = True
            return httpx.Response(200, json={"paused": True})
        if path.endswith("/rotate"):
            state["token"] = 999
            return httpx.Response(200, json={"id": 999, "token": "new"})
        if "access_tokens" in path and request.method == "DELETE":
            return httpx.Response(204)
        if "deploy_tokens" in path and request.method == "DELETE":
            state["deploy_present"] = False
            return httpx.Response(204)
        if "packages" in path and request.method == "DELETE":
            state["package_present"] = False
            return httpx.Response(204)
        if path.endswith("/pipeline") and request.method == "POST":
            return httpx.Response(
                201, json={"id": 6001, "web_url": "https://gitlab.com/p/-/pipelines/6001"}
            )
        return httpx.Response(404, json={"message": "unexpected"})

    async def no_sleep(_: float) -> None:
        return None

    return GitLabClient(
        "https://gitlab.test",
        None,
        ("defuse-sandbox",),
        transport=httpx.MockTransport(handler),
        sleep=no_sleep,
        dry_run=dry_run,
    )


def _ctx(client: GitLabClient, gcp: RecordingGcpOps, dry_run: bool = False) -> ExecutionContext:
    return ExecutionContext(
        "inc-1",
        client,
        gcp,
        actor="test",
        dry_run=dry_run,
        isolation_tag="quarantined",
        live_tag="runner-live",
    )


@pytest.fixture
def plan_and_facts():  # type: ignore[no-untyped-def]
    ioc, facts = scenario_ioc(), scenario_facts()
    plan = enrich(plan_incident(build_exposure_graph(ioc, facts)), ioc, facts)
    return plan, facts


async def test_isolate_host_swaps_tags_and_is_idempotent(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    gcp = RecordingGcpOps({"defuse-runner-1": ["runner-live", "web"]})
    ctx = _ctx(_client(), gcp)
    action = plan.action("isolate_host@host:defuse-runner-1")
    first = await execute(ctx, action)
    assert first.status == RecordStatus.APPLIED
    assert await gcp.host_network_tags("defuse-runner-1") == ["quarantined", "web"]
    second = await execute(ctx, action)
    assert second.status == RecordStatus.ALREADY_SATISFIED


async def test_rotate_project_token(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    record = await execute(
        _ctx(_client(), RecordingGcpOps()),
        plan.action("rotate_secret@secret:project_access_token:project/102:41"),
    )
    assert record.status == RecordStatus.APPLIED
    assert record.after["token_id"] == 999


async def test_rotate_ci_variable_needs_operator(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    record = await execute(
        _ctx(_client(), RecordingGcpOps()),
        plan.action("rotate_secret@secret:ci_variable:group/defuse-sandbox:SENTRY_AUTH_TOKEN"),
    )
    assert record.status == RecordStatus.NEEDS_OPERATOR


async def test_quarantine_deletes_located_package(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    action = plan.action("quarantine_version@pkg:@defuse-sandbox/strings@2.4.1")
    assert action.param("package_id") == "3002"
    record = await execute(_ctx(_client(), RecordingGcpOps()), action)
    assert record.status == RecordStatus.APPLIED
    assert record.after["present"] is False


async def test_dry_run_sends_nothing_and_records_intent(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    ctx = _ctx(_client(dry_run=True), RecordingGcpOps(), dry_run=True)
    record = await execute(ctx, plan.action("revoke_secret@secret:deploy_token:project/103:31"))
    assert record.status == RecordStatus.DRY_RUN
    assert record.dry_run


async def test_run_plan_writes_a_record_per_action(plan_and_facts) -> None:  # type: ignore[no-untyped-def]
    plan, _ = plan_and_facts
    gcp = RecordingGcpOps({"defuse-runner-1": ["runner-live"]})
    ctx = _ctx(_client(), gcp)
    written: list[ActionRecord] = []

    async def sink(record: ActionRecord) -> None:
        written.append(record)

    records = await run_plan(ctx, plan, sink)
    assert len(records) == len(plan.actions)
    assert {r.action_id for r in records} == {a.id for a in plan.actions}
    assert written == records
    assert all(r.status != RecordStatus.FAILED for r in records)
    kinds = {r.kind for r in records if r.status == RecordStatus.APPLIED}
    assert ActionKind.ISOLATE_HOST in kinds
