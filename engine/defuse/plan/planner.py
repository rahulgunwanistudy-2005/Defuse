"""The planner: build the action DAG, layer it, and explain it.

Deterministic. Given a graph it returns the same plan every time. If the ordering rules cannot
all hold it raises `UnsatisfiablePlan` carrying a minimal conflicting set in plain language.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise

from defuse.model.graph import ExposureGraph
from defuse.model.plan import (
    Action,
    ActionKind,
    Conflict,
    ConstraintSpec,
    EdgeReason,
    Explanation,
    OrderingEdge,
    Plan,
    ShapingEdge,
)
from defuse.plan.catalog import actions_for, index
from defuse.plan.constraints import CONSTRAINTS, OperatorPin, Requirement, requirements


class UnsatisfiablePlan(Exception):
    def __init__(self, conflict: Conflict) -> None:
        super().__init__(conflict.explanation)
        self.conflict = conflict


def _resolve_edges(actions: list[Action], reqs: list[Requirement]) -> list[OrderingEdge]:
    """Turn each requirement into a single ordering edge.

    A requirement offers one or more predecessors; we keep the edge from the predecessor the
    planner would schedule earliest (highest priority, then id), so a disjunctive safety rule
    does not over-serialise the plan.
    """

    rank = {a.id: (-a.priority, a.id) for a in actions}
    edges: dict[tuple[str, str], OrderingEdge] = {}
    for req in reqs:
        options = [b for b in req.before_any if b in rank and b != req.after]
        if not options:
            continue
        chosen = min(options, key=lambda b: rank[b])
        key = (chosen, req.after)
        candidate = OrderingEdge(
            before=chosen,
            after=req.after,
            reason=req.reason,
            constraint_id=req.constraint_id,
            note=req.note,
        )
        current = edges.get(key)
        if current is None or (
            current.reason != EdgeReason.CONSTRAINT and candidate.reason == EdgeReason.CONSTRAINT
        ):
            edges[key] = candidate
    return sorted(edges.values(), key=lambda e: (e.before, e.after))


def _layer(actions: list[Action], edges: list[OrderingEdge]) -> list[list[str]]:
    preds: dict[str, set[str]] = {a.id: set() for a in actions}
    succs: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        preds[edge.after].add(edge.before)
        succs[edge.before].add(edge.after)
    remaining = dict(preds)
    priority = {a.id: a.priority for a in actions}
    layers: list[list[str]] = []
    placed: set[str] = set()
    while remaining:
        ready = [a for a, p in remaining.items() if not (p - placed)]
        if not ready:
            raise UnsatisfiablePlan(_cycle(remaining, edges))
        ready.sort(key=lambda a: (-priority[a], a))
        layers.append(ready)
        placed.update(ready)
        for a in ready:
            del remaining[a]
    return layers


def _cycle(remaining: dict[str, set[str]], edges: list[OrderingEdge]) -> Conflict:
    """Find the shortest cycle among the unschedulable actions and describe it."""

    # Every stuck action has a stuck predecessor, so walking predecessors must revisit a node.
    node = min(remaining)
    seen: list[str] = []
    while node not in seen:
        seen.append(node)
        node = min(remaining[node] & remaining.keys())
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.before in remaining and edge.after in remaining:
            successors[edge.before].append(edge.after)
    ring = _shortest_cycle_through(node, successors)
    edge_by_pair = {(e.before, e.after): e for e in edges}
    rules: list[str] = []
    for before, after in pairwise(ring):
        edge = edge_by_pair[(before, after)]
        tag = f"[{edge.constraint_id or edge.reason.value}] "
        rules.append(f"{tag}{before} must finish before {after}: {edge.note}")
    explanation = (
        "These ordering rules cannot all hold; together they require an action to finish "
        "before itself. Drop or change one of them:\n  " + "\n  ".join(rules)
    )
    return Conflict(rules=tuple(rules), cycle=tuple(ring), explanation=explanation)


def _shortest_cycle_through(start: str, successors: dict[str, list[str]]) -> list[str]:
    parent: dict[str, str] = {}
    frontier = [start]
    while frontier:
        nxt: list[str] = []
        for node in frontier:
            for succ in sorted(successors.get(node, [])):
                if succ == start:
                    path = [node]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    return [*reversed(path), start]
                if succ not in parent:
                    parent[succ] = node
                    nxt.append(succ)
        frontier = nxt
    raise AssertionError(f"{start} is not on a cycle")


def _missing_guard(reqs: list[Requirement], present: set[str]) -> Conflict | None:
    for req in reqs:
        if req.required and not [b for b in req.before_any if b in present]:
            spec = CONSTRAINTS[req.constraint_id] if req.constraint_id else None
            head = f"[{spec.id}] {spec.title}: " if spec else ""
            text = f"{head}{req.after} cannot be ordered safely. {req.note}"
            return Conflict(rules=(text,), cycle=(req.after,), explanation=text)
    return None


def plan_incident(graph: ExposureGraph, pins: tuple[OperatorPin, ...] = ()) -> Plan:
    exposure = index(graph)
    actions = actions_for(exposure)
    reqs = requirements(exposure, actions)
    reqs.extend(
        Requirement(
            after=pin.after,
            before_any=(pin.before,),
            reason=EdgeReason.OPERATOR,
            constraint_id=None,
            note=pin.note,
        )
        for pin in pins
    )
    conflict = _missing_guard(reqs, {a.id for a in actions})
    if conflict is not None:
        raise UnsatisfiablePlan(conflict)
    edges = _resolve_edges(actions, reqs)
    layers = _layer(actions, edges)
    return Plan(
        ioc_id=graph.ioc_id,
        strategy="defuse",
        actions=tuple(actions),
        edges=tuple(edges),
        layers=tuple(tuple(layer) for layer in layers),
    )


def plan_naive(graph: ExposureGraph) -> Plan:
    """The detonator baseline: revoke and remove everything at once, no ordering.

    Kept explicitly labelled. The demo runs it to show the worm fire its handlers.
    """

    exposure = index(graph)
    actions = [
        a
        for a in actions_for(exposure)
        if a.kind
        in {
            ActionKind.REVOKE_SECRET,
            ActionKind.ROTATE_SECRET,
            ActionKind.QUARANTINE_VERSION,
            ActionKind.REMOVE_HOOK_FILES,
        }
    ]
    return Plan(
        ioc_id=graph.ioc_id,
        strategy="naive",
        actions=tuple(actions),
        edges=(),
        layers=(tuple(sorted(a.id for a in actions)),) if actions else (),
    )


def replan(plan: Plan, completed: set[str]) -> Plan:
    """Re-layer, treating completed actions as already satisfied. Never re-runs a completed one."""

    pending = [a for a in plan.actions if a.id not in completed]
    pending_ids = {a.id for a in pending}
    edges = [e for e in plan.edges if e.after in pending_ids]
    kept_edges = [e for e in edges if e.before in pending_ids]
    layers = _layer(pending, kept_edges)
    return plan.model_copy(
        update={
            "actions": tuple(pending),
            "edges": tuple(
                e for e in plan.edges if e.after in pending_ids or e.before in pending_ids
            ),
            "layers": tuple(tuple(layer) for layer in layers),
            "completed": tuple(sorted(completed)),
        }
    )


def explain(plan: Plan, action_id: str) -> Explanation:
    action = plan.action(action_id)
    shaping = sorted(
        (e for e in plan.edges if e.after == action_id),
        key=lambda e: (e.constraint_id or "~", e.before),
    )
    shaped_by = tuple(
        ShapingEdge(before=e.before, reason=e.reason, constraint_id=e.constraint_id, note=e.note)
        for e in shaping
    )
    specs: tuple[ConstraintSpec, ...] = tuple(
        CONSTRAINTS[c] for c in sorted({e.constraint_id for e in shaping if e.constraint_id})
    )
    critical = _critical_path(plan, action_id)
    layer = plan.layer_of(action_id)
    if not shaped_by:
        summary = f"{action.label} has no predecessors; it can run in the first layer."
    else:
        constraint_bits = [
            f"{CONSTRAINTS[e.constraint_id].id} ({CONSTRAINTS[e.constraint_id].title})"
            for e in shaped_by
            if e.constraint_id
        ]
        dep_count = sum(1 for e in shaped_by if e.constraint_id is None)
        parts = []
        if constraint_bits:
            parts.append("safety " + ", ".join(dict.fromkeys(constraint_bits)))
        if dep_count:
            parts.append(f"{dep_count} dependency edge{'s' if dep_count != 1 else ''}")
        summary = f"{action.label} is in layer {layer}, placed by " + " and ".join(parts) + "."
    return Explanation(
        action_id=action_id,
        label=action.label,
        layer=layer,
        phase=action.phase,
        shaped_by=shaped_by,
        constraints=specs,
        critical_path=critical,
        summary=summary,
    )


def _critical_path(plan: Plan, action_id: str) -> tuple[str, ...]:
    """The chain of latest-finishing predecessors: why the action cannot start earlier."""

    preds: dict[str, list[OrderingEdge]] = defaultdict(list)
    for edge in plan.edges:
        if edge.before not in plan.completed:
            preds[edge.after].append(edge)
    path: list[str] = [action_id]
    node = action_id
    while preds.get(node):
        chosen = max(
            preds[node],
            key=lambda e: (plan.layer_of(e.before), 1 if e.constraint_id else 0, e.before),
        )
        node = chosen.before
        path.append(node)
    return tuple(reversed(path))
