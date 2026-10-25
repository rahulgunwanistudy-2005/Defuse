from __future__ import annotations

from typing import Any

import yaml
from hypothesis import given

from defuse.execute.compiler import (
    MAX_NEEDS,
    CompileOptions,
    compile_child_pipeline,
    resource_group,
    transitive_reduction,
)
from defuse.graph import build_exposure_graph
from defuse.model.plan import Action, ActionKind, EdgeReason, OrderingEdge, Phase, Plan
from defuse.plan.planner import plan_incident
from defuse.scenario import scenario_facts, scenario_ioc
from tests.property.strategies import IOC, collected_facts

RESERVED = {"stages", "default", "variables"}


def _closure(edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    closure = set(edges)
    changed = True
    while changed:
        changed = False
        for a, b in list(closure):
            for c, d in list(closure):
                if b == c and (a, d) not in closure:
                    closure.add((a, d))
                    changed = True
    return closure


def _jobs(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in doc.items() if k not in RESERVED}


def _needs_closure(doc: dict[str, Any]) -> set[tuple[str, str]]:
    edges = {(n["job"], name) for name, job in _jobs(doc).items() for n in job["needs"]}
    closure = _closure(edges)
    return {(a, b) for a, b in closure if not a.startswith("gate ") and not b.startswith("gate ")}


def _scenario_plan() -> Plan:
    return plan_incident(build_exposure_graph(scenario_ioc(), scenario_facts()))


def test_scenario_compiles_to_a_readable_child_pipeline() -> None:
    plan = _scenario_plan()
    doc = yaml.safe_load(compile_child_pipeline(plan, CompileOptions(incident_id="inc-1")))
    assert doc["stages"][0] == "isolate"
    assert doc["stages"][-1] == "verify"
    assert set(_jobs(doc)) == {a.id for a in plan.actions}
    isolate = doc["isolate_host@host:defuse-runner-1"]
    assert isolate["needs"] == []
    assert isolate["environment"] == {"name": "containment", "action": "access"}
    assert isolate["resource_group"] == "containment-host-defuse-runner-1"
    assert "defuse act" in isolate["script"][0]


def test_needs_preserve_plan_order_exactly() -> None:
    plan = _scenario_plan()
    doc = yaml.safe_load(compile_child_pipeline(plan, CompileOptions(incident_id="inc-1")))
    assert _needs_closure(doc) == _closure({(e.before, e.after) for e in plan.edges})


def test_stages_never_go_backwards() -> None:
    plan = _scenario_plan()
    doc = yaml.safe_load(compile_child_pipeline(plan, CompileOptions(incident_id="inc-1")))
    rank = {s: i for i, s in enumerate(doc["stages"])}
    for job in _jobs(doc).values():
        for need in job["needs"]:
            assert rank[doc[need["job"]]["stage"]] <= rank[job["stage"]]


def test_gcp_actions_authenticate_with_id_tokens_only() -> None:
    options = CompileOptions(
        incident_id="inc-1",
        wif_audience="//iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/providers/gl",
        wif_provider="projects/1/locations/global/workloadIdentityPools/p/providers/gl",
        gcp_service_account="defuse-containment@proj.iam.gserviceaccount.com",
    )
    text = compile_child_pipeline(_scenario_plan(), options)
    doc = yaml.safe_load(text)
    assert "GCP_ID_TOKEN" in doc["isolate_host@host:defuse-runner-1"]["id_tokens"]
    assert "id_tokens" not in doc["pause_runner@runner:7"]
    assert "private_key" not in text


def test_dry_run_flag_reaches_every_job() -> None:
    doc = yaml.safe_load(
        compile_child_pipeline(_scenario_plan(), CompileOptions(incident_id="i", dry_run=True))
    )
    assert doc["variables"]["DEFUSE_DRY_RUN"] == "1"
    assert all(job["script"][0].endswith("--dry-run") for job in _jobs(doc).values())


def test_wide_fan_in_is_split_into_gates() -> None:
    sources = [
        Action(
            id=f"rotate_secret@s{i:03}",
            kind=ActionKind.ROTATE_SECRET,
            target=f"s{i:03}",
            phase=Phase.ROTATE,
            priority=50,
            label=f"Rotate s{i}",
        )
        for i in range(MAX_NEEDS + 10)
    ]
    sink = Action(
        id="verify_clean@incident",
        kind=ActionKind.VERIFY_CLEAN,
        target="incident",
        phase=Phase.VERIFY,
        priority=0,
        label="Verify",
    )
    plan = Plan(
        ioc_id="x",
        strategy="defuse",
        actions=(*sources, sink),
        edges=tuple(
            OrderingEdge(before=s.id, after=sink.id, reason=EdgeReason.DEPENDENCY, note="n")
            for s in sources
        ),
        layers=(tuple(s.id for s in sources), (sink.id,)),
    )
    doc = yaml.safe_load(compile_child_pipeline(plan, CompileOptions(incident_id="i")))
    assert all(len(job["needs"]) <= MAX_NEEDS for job in _jobs(doc).values())
    assert len(doc[sink.id]["needs"]) == 2
    assert _needs_closure(doc) == {(s.id, sink.id) for s in sources}


def test_transitive_reduction_drops_implied_edges() -> None:
    kept = transitive_reduction(["a", "b", "c"], [("a", "b"), ("b", "c"), ("a", "c")])
    assert kept == {("a", "b"), ("b", "c")}


def test_resource_group_is_safe() -> None:
    assert resource_group("secret:deploy_token:project/103:31") == (
        "containment-secret-deploy_token-project-103-31"
    )


@given(collected_facts(allow_unmanaged=False))
def test_compiled_pipeline_preserves_order_for_any_plan(facts: Any) -> None:
    plan = plan_incident(build_exposure_graph(IOC, facts))
    doc = yaml.safe_load(compile_child_pipeline(plan, CompileOptions(incident_id="p")))
    assert _needs_closure(doc) == _closure({(e.before, e.after) for e in plan.edges})
