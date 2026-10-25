"""Properties every Defuse plan must hold, over randomly generated exposure scenarios.

Run with HYPOTHESIS_PROFILE=ci for 500 examples per property.
"""

from __future__ import annotations

from hypothesis import event, given
from hypothesis import strategies as st

from defuse.graph import build_exposure_graph
from defuse.model.facts import CollectedFacts
from defuse.model.graph import EdgeKind, ExposureGraph, NodeKind, PackageVersionNode
from defuse.model.plan import ActionKind, Plan
from defuse.plan.adversary import replay
from defuse.plan.catalog import index
from defuse.plan.check import check_plan
from defuse.plan.planner import UnsatisfiablePlan, plan_incident, plan_naive, replan
from tests.property.strategies import IOC, collected_facts


def _plan(facts: CollectedFacts) -> tuple[ExposureGraph, Plan]:
    graph = build_exposure_graph(IOC, facts)
    return graph, plan_incident(graph)


@given(
    st.one_of(
        collected_facts(allow_unmanaged=False),
        collected_facts(allow_unmanaged=False, force_watched=True),
    )
)
def test_no_safety_constraint_is_ever_violated(facts: CollectedFacts) -> None:
    graph, plan = _plan(facts)
    assert check_plan(graph, plan) == []


@given(
    st.one_of(
        collected_facts(allow_unmanaged=False),
        collected_facts(allow_unmanaged=False, force_watched=True),
    )
)
def test_the_adversary_never_fires_against_a_defuse_plan(facts: CollectedFacts) -> None:
    graph, plan = _plan(facts)
    exposure = index(graph)
    event(f"watched secrets: {min(3, sum(len(exposure.watched(w)) for w in exposure.watchers))}")
    event(f"layers: {min(6, len(plan.layers))}")
    assert replay(graph, plan).safe


@given(collected_facts(allow_unmanaged=False))
def test_every_exposed_secret_is_rotated_exactly_once(facts: CollectedFacts) -> None:
    graph, plan = _plan(facts)
    exposed = {e.dst for e in graph.edges if e.kind == EdgeKind.CAN_READ}
    rotations = [a.target for a in plan.actions if a.kind == ActionKind.ROTATE_SECRET]
    assert sorted(rotations) == sorted(exposed)


@given(collected_facts(allow_unmanaged=False))
def test_every_rogue_version_is_quarantined(facts: CollectedFacts) -> None:
    graph, plan = _plan(facts)
    rogue = {
        n.id
        for n in graph.by_kind(NodeKind.PACKAGE_VERSION)
        if isinstance(n, PackageVersionNode) and n.rogue
    }
    quarantined = {a.target for a in plan.actions if a.kind == ActionKind.QUARANTINE_VERSION}
    assert rogue <= quarantined


@given(collected_facts(allow_unmanaged=False))
def test_plan_is_acyclic_and_every_action_is_scheduled_once(facts: CollectedFacts) -> None:
    _, plan = _plan(facts)
    scheduled = [a for layer in plan.layers for a in layer]
    assert sorted(scheduled) == sorted(a.id for a in plan.actions)
    for edge in plan.edges:
        assert plan.layer_of(edge.before) < plan.layer_of(edge.after)


@given(collected_facts(allow_unmanaged=False), st.data())
def test_replanning_never_reruns_a_completed_action(
    facts: CollectedFacts, data: st.DataObject
) -> None:
    graph, plan = _plan(facts)
    cut = data.draw(st.integers(0, len(plan.layers)))
    done = {a for layer in plan.layers[:cut] for a in layer}
    if cut < len(plan.layers):
        done |= set(data.draw(st.lists(st.sampled_from(plan.layers[cut]), unique=True)))
    again = replan(plan, done)
    remaining = [a for layer in again.layers for a in layer]
    assert not set(remaining) & done
    assert sorted(remaining) == sorted({a.id for a in plan.actions} - done)
    assert check_plan(graph, again) == []


@given(collected_facts(allow_unmanaged=False))
def test_the_graph_is_deterministic(facts: CollectedFacts) -> None:
    shuffled = facts.model_copy(
        update={
            "jobs": tuple(reversed(facts.jobs)),
            "variables": tuple(reversed(facts.variables)),
            "published_packages": tuple(reversed(facts.published_packages)),
            "hook_findings": tuple(reversed(facts.hook_findings)),
        }
    )
    first = build_exposure_graph(IOC, facts).canonical_json()
    assert first == build_exposure_graph(IOC, shuffled).canonical_json()


@given(collected_facts(allow_unmanaged=False, force_watched=True))
def test_naive_baseline_fires_whenever_a_watched_secret_exists(facts: CollectedFacts) -> None:
    graph = build_exposure_graph(IOC, facts)
    exposure = index(graph)
    assert any(exposure.watched(w) for w in exposure.watchers)
    assert not replay(graph, plan_naive(graph)).safe
    assert replay(graph, plan_incident(graph)).safe


@given(
    st.one_of(
        collected_facts(allow_unmanaged=True),
        collected_facts(allow_unmanaged=True, force_watched=True),
    )
)
def test_unsat_plans_explain_themselves(facts: CollectedFacts) -> None:
    graph = build_exposure_graph(IOC, facts)
    try:
        plan = plan_incident(graph)
    except UnsatisfiablePlan as refused:
        conflict = refused.conflict
    else:
        assert check_plan(graph, plan) == []
        assert replay(graph, plan).safe
        return
    event("refused as unsatisfiable")
    assert conflict.rules
    assert any(rule.startswith(("[C1]", "[C3]")) for rule in conflict.rules)
