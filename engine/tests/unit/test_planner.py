import pytest

from defuse.graph import build_exposure_graph
from defuse.model.graph import ExposureGraph, HostNode
from defuse.model.plan import ActionKind, EdgeReason
from defuse.plan.adversary import TriggerKind, replay
from defuse.plan.check import check_plan
from defuse.plan.constraints import CONSTRAINTS, OperatorPin
from defuse.plan.planner import (
    UnsatisfiablePlan,
    explain,
    plan_incident,
    plan_naive,
    replan,
)
from defuse.scenario import scenario_facts, scenario_ioc

ISOLATE = "isolate_host@host:defuse-runner-1"
REVOKE_PUBLISH = "revoke_secret@secret:deploy_token:project/103:31"


@pytest.fixture
def graph() -> ExposureGraph:
    return build_exposure_graph(scenario_ioc(), scenario_facts())


def test_plan_is_deterministic(graph: ExposureGraph) -> None:
    assert plan_incident(graph).model_dump_json() == plan_incident(graph).model_dump_json()


def test_isolate_comes_before_revoking_a_watched_secret(graph: ExposureGraph) -> None:
    plan = plan_incident(graph)
    assert plan.layer_of(ISOLATE) < plan.layer_of(REVOKE_PUBLISH)
    assert check_plan(graph, plan) == []
    assert replay(graph, plan).safe


def test_every_action_has_an_explanation(graph: ExposureGraph) -> None:
    plan = plan_incident(graph)
    for action in plan.actions:
        explanation = explain(plan, action.id)
        assert explanation.layer == plan.layer_of(action.id)
        assert explanation.critical_path[-1] == action.id
        assert explanation.summary


def test_explain_names_the_constraint_that_placed_the_action(graph: ExposureGraph) -> None:
    explanation = explain(plan_incident(graph), REVOKE_PUBLISH)
    assert "C1" in {c.id for c in explanation.constraints}
    assert explanation.critical_path[0] == ISOLATE
    assert "C1" in explanation.summary


def test_first_layer_explanation(graph: ExposureGraph) -> None:
    assert "first layer" in explain(plan_incident(graph), ISOLATE).summary


def test_naive_baseline_fires_both_triggers(graph: ExposureGraph) -> None:
    result = replay(graph, plan_naive(graph))
    assert not result.safe
    assert {t.kind for t in result.triggers} == {
        TriggerKind.REVOCATION_HANDLER,
        TriggerKind.DEAD_MANS_SWITCH,
    }
    assert result.hosts_lost == ("host:defuse-runner-1",)


def test_unmanaged_watcher_host_is_refused_with_a_readable_reason() -> None:
    facts = scenario_facts()
    unmanaged = tuple(h.model_copy(update={"managed": False}) for h in facts.hosts)
    graph = build_exposure_graph(scenario_ioc(), facts.model_copy(update={"hosts": unmanaged}))
    host = graph.node("host:defuse-runner-1")
    assert isinstance(host, HostNode)
    assert not host.managed
    with pytest.raises(UnsatisfiablePlan) as caught:
        plan_incident(graph)
    assert "[C1]" in caught.value.conflict.explanation
    assert "not under management" in caught.value.conflict.explanation


def test_operator_pin_that_contradicts_c1_returns_a_minimal_cycle(graph: ExposureGraph) -> None:
    pin = OperatorPin(
        before=REVOKE_PUBLISH, after=ISOLATE, note="commander: revoke the npm token right now"
    )
    with pytest.raises(UnsatisfiablePlan) as caught:
        plan_incident(graph, pins=(pin,))
    conflict = caught.value.conflict
    assert conflict.cycle[0] == conflict.cycle[-1]
    assert any("commander" in rule for rule in conflict.rules)
    assert any(rule.startswith(("[C1]", "[C3]")) for rule in conflict.rules)
    assert len(conflict.rules) <= 4


def test_compatible_operator_pin_is_respected(graph: ExposureGraph) -> None:
    pin = OperatorPin(
        before="quarantine_version@pkg:@defuse-sandbox/strings@2.4.1",
        after=ISOLATE,
        note="registry first",
    )
    plan = plan_incident(graph, pins=(pin,))
    assert plan.layer_of(pin.before) < plan.layer_of(ISOLATE)
    assert any(e.reason == EdgeReason.OPERATOR for e in plan.edges)


def test_replan_skips_completed_actions(graph: ExposureGraph) -> None:
    plan = plan_incident(graph)
    done = set(plan.layers[0]) | set(plan.layers[1])
    again = replan(plan, done)
    remaining = {a for layer in again.layers for a in layer}
    assert not remaining & done
    assert remaining == {a.id for a in plan.actions} - done
    assert check_plan(graph, again) == []


def test_every_exposed_secret_is_rotated_once(graph: ExposureGraph) -> None:
    plan = plan_incident(graph)
    rotations = [a.target for a in plan.actions if a.kind == ActionKind.ROTATE_SECRET]
    assert sorted(rotations) == sorted(set(rotations))
    assert len(rotations) == 4


def test_constraint_specs_cite_sources() -> None:
    assert sorted(CONSTRAINTS) == ["C1", "C2", "C3", "C4", "C5", "C6"]
    for spec in CONSTRAINTS.values():
        assert spec.source_url.startswith("https://")
        assert spec.rationale.endswith(".")
