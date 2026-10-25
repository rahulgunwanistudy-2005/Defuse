"""Independent safety check of a finished plan.

This restates C1-C6 directly over layer indices, without reusing the rules that built the
plan, so a bug in plan construction cannot also hide itself from the check.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from defuse.model.graph import ExposureGraph, host_id, project_id
from defuse.model.plan import ActionKind, Plan, action_id
from defuse.plan.catalog import index


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    constraint_id: str
    detail: str


def _invalidating(plan: Plan) -> dict[str, int]:
    """Secret id -> layer in which it stops working."""

    out: dict[str, int] = {}
    for number, layer in enumerate(plan.layers):
        for aid in layer:
            action = plan.action(aid)
            if action.kind == ActionKind.REVOKE_SECRET or (
                action.kind == ActionKind.ROTATE_SECRET
                and action.param("mode") == "operator_handoff"
            ):
                out[action.target] = min(number, out.get(action.target, number))
    return out


def check_plan(graph: ExposureGraph, plan: Plan) -> list[Violation]:
    exposure = index(graph)
    layer: dict[str, int] = {aid: n for n, ids in enumerate(plan.layers) for aid in ids}
    done = set(plan.completed)

    def at(kind: ActionKind, target: str) -> int | None:
        aid = action_id(kind, target)
        if aid in done:
            return -1
        return layer.get(aid)

    found: list[Violation] = []
    cut = _invalidating(plan)

    for watcher in exposure.watchers:
        hid = host_id(watcher.host)
        guard_layers = [
            x
            for x in (at(ActionKind.ISOLATE_HOST, hid), at(ActionKind.STOP_WATCHER, watcher.id))
            if x is not None
        ]
        guard = min(guard_layers) if guard_layers else None
        for secret in exposure.watched(watcher):
            for kind in (ActionKind.ROTATE_SECRET, ActionKind.REVOKE_SECRET):
                when = at(kind, secret)
                if when is None or when < 0:
                    continue
                if guard is None or guard >= when:
                    found.append(
                        Violation(
                            constraint_id="C1",
                            detail=f"{kind.value} {secret} at layer {when} before {hid} is safe",
                        )
                    )

    for host in exposure.hosts:
        snap = at(ActionKind.SNAPSHOT_EVIDENCE, host.id)
        erad = [at(ActionKind.REMOVE_PERSISTENCE, host.id)]
        erad += [
            at(ActionKind.STOP_WATCHER, w.id) for w in exposure.watchers if w.host == host.name
        ]
        for when in erad:
            if when is not None and when >= 0 and (snap is None or snap >= when):
                found.append(
                    Violation(
                        constraint_id="C2", detail=f"eradication on {host.name} before snapshot"
                    )
                )

        isolated_at = at(ActionKind.ISOLATE_HOST, host.id)
        secrets = exposure.secrets_on_host(host)
        publish = {s.id for s in secrets if s.publish_capable}
        source = {s.id for s in secrets if s.source_capable}
        for number in range(len(plan.layers)):
            if isolated_at is not None and isolated_at < number:
                continue
            cut_here = {s for s, n in cut.items() if n == number}
            if cut_here & publish and cut_here & source:
                found.append(
                    Violation(
                        constraint_id="C3",
                        detail=f"{host.name} live, lost publish+source access in layer {number}",
                    )
                )

    publish_rot = [
        at(ActionKind.ROTATE_SECRET, s.id) for s in exposure.secrets if s.publish_capable
    ]
    other_rot = [
        at(ActionKind.ROTATE_SECRET, s.id) for s in exposure.secrets if not s.publish_capable
    ]
    p_max = max((x for x in publish_rot if x is not None), default=None)
    o_min = min((x for x in other_rot if x is not None and x >= 0), default=None)
    if p_max is not None and o_min is not None and p_max >= o_min:
        found.append(
            Violation(
                constraint_id="C4",
                detail="a non-publish secret rotates no later than a publish one",
            )
        )

    for agent in exposure.agents:
        restore = at(ActionKind.RESTORE_AGENT_IDENTITY, agent.id)
        removal = at(ActionKind.REMOVE_HOOK_FILES, project_id(agent.project_id))
        if restore is not None and restore >= 0 and (removal is None or removal >= restore):
            found.append(
                Violation(
                    constraint_id="C5", detail=f"{agent.identity} restored before hooks removed"
                )
            )

    pauses = [at(ActionKind.PAUSE_RUNNER, r.id) for r in exposure.runners if not r.shared]
    for rebuild_id in [a.id for a in plan.actions if a.kind == ActionKind.REBUILD_ARTIFACTS]:
        when = layer.get(rebuild_id)
        if when is None:
            continue
        if any(p is None or p >= when for p in pauses):
            found.append(
                Violation(constraint_id="C6", detail=f"{rebuild_id} before runners paused")
            )

    return found
