"""Run a plan layer by layer, writing an append-only ledger and re-layering on partial failure."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, nullcontext

import structlog

from defuse.execute.executors import ExecutionContext, execute
from defuse.graph.build import build_exposure_graph
from defuse.model.facts import CollectedFacts
from defuse.model.graph import AgentSessionNode, NodeKind, PackageVersionNode
from defuse.model.incident import ActionRecord, RecordStatus
from defuse.model.ioc import IOCSet
from defuse.model.plan import Action, ActionKind, Plan

log = structlog.get_logger(__name__)

SUCCESS = frozenset({RecordStatus.APPLIED, RecordStatus.ALREADY_SATISFIED})

RecordSink = Callable[[ActionRecord], Awaitable[None]]


def enrich(plan: Plan, ioc: IOCSet, facts: CollectedFacts) -> Plan:
    """Attach registry coordinates to quarantine actions so the executor can act."""

    graph = build_exposure_graph(ioc, facts)
    versions = {
        n.label: n
        for n in graph.by_kind(NodeKind.PACKAGE_VERSION)
        if isinstance(n, PackageVersionNode)
    }
    by_name_version = {(p.name, p.version): p for p in facts.published_packages}
    actions: list[Action] = []
    for action in plan.actions:
        enriched = action
        if action.kind in {ActionKind.BLOCK_AGENT_IDENTITY, ActionKind.RESTORE_AGENT_IDENTITY}:
            agent = graph.node(action.target)
            if isinstance(agent, AgentSessionNode) and agent.user_id is not None:
                enriched = action.model_copy(
                    update={
                        "params": (
                            *action.params,
                            ("project_id", str(agent.project_id)),
                            ("user_id", str(agent.user_id)),
                        )
                    }
                )
        if action.kind == ActionKind.QUARANTINE_VERSION:
            node = versions.get(action.target.split("pkg:", 1)[1])
            pkg = by_name_version.get((node.name, node.version)) if node else None
            if pkg is not None:
                enriched = action.model_copy(
                    update={
                        "params": (
                            ("project_id", str(pkg.project_id)),
                            ("package_id", str(pkg.package_id)),
                        )
                    }
                )
        actions.append(enriched)
    return plan.model_copy(update={"actions": tuple(actions)})


async def run_plan(
    ctx: ExecutionContext,
    plan: Plan,
    sink: RecordSink,
    *,
    claim: Callable[[str], AbstractAsyncContextManager[None]] | None = None,
    completed: Callable[[], Awaitable[set[str]]] | None = None,
) -> list[ActionRecord]:
    actions = {a.id: a for a in plan.actions}
    records: list[ActionRecord] = []
    satisfied = set(plan.completed)
    for layer in plan.layers:
        for action_id in layer:
            async with claim(action_id) if claim else nullcontext():
                if completed is not None and not ctx.dry_run:
                    satisfied.update(await completed())
                await _run_one(ctx, plan, actions, action_id, satisfied, records=records, sink=sink)
    return records


async def _run_one(
    ctx: ExecutionContext,
    plan: Plan,
    actions: dict[str, Action],
    action_id: str,
    satisfied: set[str],
    *,
    records: list[ActionRecord],
    sink: RecordSink,
) -> None:
    blocked = sorted(
        e.before for e in plan.edges if e.after == action_id and e.before not in satisfied
    )
    if action_id in satisfied and not ctx.dry_run:
        action = actions[action_id]
        now = ctx.clock()
        record = ActionRecord(
            incident_id=ctx.incident_id,
            action_id=action.id,
            kind=action.kind,
            target=action.target,
            actor=ctx.actor,
            status=RecordStatus.ALREADY_SATISFIED,
            dry_run=False,
            detail="completed by another worker; ledger rechecked inside the lease",
            started_at=now,
            finished_at=now,
        )
    elif blocked and not ctx.dry_run:
        action = actions[action_id]
        now = ctx.clock()
        record = ActionRecord(
            incident_id=ctx.incident_id,
            action_id=action.id,
            kind=action.kind,
            target=action.target,
            actor=ctx.actor,
            status=RecordStatus.NEEDS_OPERATOR,
            dry_run=False,
            detail=f"blocked by unfinished prerequisites: {', '.join(blocked)}",
            started_at=now,
            finished_at=now,
        )
    else:
        record = await execute(ctx, actions[action_id])
    records.append(record)
    await sink(record)
    if record.status in SUCCESS:
        satisfied.add(action_id)
    if record.status == RecordStatus.FAILED and not ctx.dry_run:
        log.error("run.layer_failed", action=action_id, detail=record.detail)
