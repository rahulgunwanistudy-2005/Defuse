from __future__ import annotations

import inspect

import pytest

from defuse.collect.collector import VARIABLE_FIELDS, Collector
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings
from defuse.graph import build_exposure_graph
from defuse.model.graph import EdgeKind, NodeKind, PackageVersionNode
from defuse.scenario import scenario_ioc
from tests.contract.server import make_transport


@pytest.fixture
def settings() -> Settings:
    return Settings(
        sandbox_namespaces="defuse-sandbox",
        gcp_project="defuse-demo",
        runner_hosts={"7": "defuse-runner-1"},
        token_variables={
            "NPM_PUBLISH_TOKEN": "deploy_token:31",
            "GITLAB_PUSH_TOKEN": "project_access_token:41",
            "RELEASE_TOKEN": "project_access_token:42",
        },
    )


async def _collect(settings: Settings):  # type: ignore[no-untyped-def]
    async def no_sleep(_: float) -> None:
        return None

    client = GitLabClient(
        "https://gitlab.test", None, settings.namespaces, transport=make_transport(), sleep=no_sleep
    )
    async with client:
        return await Collector(client, settings, scenario_ioc()).collect("defuse-sandbox")


async def test_collector_reproduces_the_infection_from_api_alone(settings: Settings) -> None:
    facts = await _collect(settings)
    graph = build_exposure_graph(scenario_ioc(), facts)

    assert {n.id for n in graph.by_kind(NodeKind.JOB)} == {"job:101:90001", "job:102:90011"}
    rogue = [
        n
        for n in graph.by_kind(NodeKind.PACKAGE_VERSION)
        if isinstance(n, PackageVersionNode) and n.rogue
    ]
    assert [n.label for n in rogue] == ["@defuse-sandbox/strings@2.4.1"]
    assert graph.has("hook:102:.claude/settings.json")
    assert graph.has("watcher:defuse-runner-1:defuse-watcher.service")
    assert [g.depth for g in graph.generations] == [0, 1]

    published = graph.into("pkg:@defuse-sandbox/strings@2.4.1", EdgeKind.PUBLISHED)
    assert "no publishing pipeline" in published[0].evidence


async def test_collector_reads_lockfiles_then_falls_back_to_trace(settings: Settings) -> None:
    facts = await _collect(settings)
    app_a = next(j for j in facts.jobs if j.id == 90001)
    app_b = next(j for j in facts.jobs if j.id == 90011)
    assert app_a.resolved[0].source.value == "lockfile"
    assert app_b.resolved[0].source.value == "trace"
    assert app_b.resolved[0].version == "2.4.1"


async def test_collector_never_requests_a_secret_value(settings: Settings) -> None:
    facts = await _collect(settings)
    for variable in facts.variables:
        dumped = variable.model_dump()
        assert "value" not in dumped
    assert "value" not in VARIABLE_FIELDS
    source = inspect.getsource(Collector._variables_for)
    assert "value" not in source.lower().replace("values", "").replace("visible", "")


async def test_no_fixture_response_contains_a_secret_value() -> None:
    from pathlib import Path

    text = (Path(__file__).parent / "fixtures" / "routes.json").read_text()
    assert '"value"' not in text
