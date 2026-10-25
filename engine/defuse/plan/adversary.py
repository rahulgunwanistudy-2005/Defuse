"""Replay a plan against the worm's published trigger rules.

The model is deliberately small and matches the sources the constraints cite:

- revocation watcher (SANS ISC, Aug 2026): if a watched secret stops working while its host
  still has network access and the watcher is running, the attacker's handler fires.
- dead-man's switch (GitLab VR, Nov 2025): if a live host loses registry-publish access and
  source-host access in the same step, the payload wipes the host.

Actions in one layer happen simultaneously, so a layer that isolates a host and revokes its
watched secret together is a race and counts as unsafe.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from defuse.model.graph import ExposureGraph, host_id
from defuse.model.plan import ActionKind, Plan
from defuse.plan.catalog import index


class TriggerKind(StrEnum):
    REVOCATION_HANDLER = "revocation_handler"
    DEAD_MANS_SWITCH = "dead_mans_switch"


class Trigger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TriggerKind
    layer: int
    host: str
    cause: tuple[str, ...]
    detail: str


class StepState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    layer: int
    actions: tuple[str, ...]
    isolated_hosts: tuple[str, ...]
    running_watchers: tuple[str, ...]
    revoked_secrets: tuple[str, ...]
    triggers: tuple[Trigger, ...]


class Replay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: str
    steps: tuple[StepState, ...]
    triggers: tuple[Trigger, ...]
    hosts_intact: tuple[str, ...]
    hosts_lost: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return not self.triggers


def _invalidates(kind: ActionKind, mode: str | None) -> bool:
    if kind == ActionKind.REVOKE_SECRET:
        return True
    return kind == ActionKind.ROTATE_SECRET and mode == "operator_handoff"


def replay(graph: ExposureGraph, plan: Plan) -> Replay:
    exposure = index(graph)
    actions = {a.id: a for a in plan.actions}
    watcher_host = {w.id: host_id(w.host) for w in exposure.watchers}
    watched = {w.id: set(exposure.watched(w)) for w in exposure.watchers}
    host_secrets = {h.id: exposure.secrets_on_host(h) for h in exposure.hosts}

    isolated: set[str] = set()
    running: set[str] = set(watcher_host)
    revoked: set[str] = set()
    lost: set[str] = set()
    steps: list[StepState] = []
    all_triggers: list[Trigger] = []

    for number, layer in enumerate(plan.layers):
        newly_revoked: set[str] = set()
        next_isolated = set(isolated)
        next_running = set(running)
        for aid in layer:
            action = actions[aid]
            if action.kind == ActionKind.ISOLATE_HOST:
                next_isolated.add(action.target)
            elif action.kind == ActionKind.STOP_WATCHER:
                next_running.discard(action.target)
            elif _invalidates(action.kind, action.param("mode")):
                newly_revoked.add(action.target)

        triggers: list[Trigger] = []
        for wid in sorted(running):
            hid = watcher_host[wid]
            hit = sorted(watched[wid] & newly_revoked)
            if hit and hid not in isolated and hid not in lost:
                triggers.append(
                    Trigger(
                        kind=TriggerKind.REVOCATION_HANDLER,
                        layer=number,
                        host=hid,
                        cause=tuple(hit),
                        detail=f"{wid} saw {len(hit)} watched secret(s) fail while {hid} was up",
                    )
                )
        for hid, secrets in sorted(host_secrets.items()):
            if hid in isolated or hid in lost:
                continue
            publish = {s.id for s in secrets if s.publish_capable} & newly_revoked
            source = {s.id for s in secrets if s.source_capable} & newly_revoked
            if publish and source:
                triggers.append(
                    Trigger(
                        kind=TriggerKind.DEAD_MANS_SWITCH,
                        layer=number,
                        host=hid,
                        cause=tuple(sorted(publish | source)),
                        detail=f"{hid} lost publish and source access in the same step",
                    )
                )
        lost.update(t.host for t in triggers)
        all_triggers.extend(triggers)
        isolated = next_isolated
        running = next_running
        revoked |= newly_revoked
        steps.append(
            StepState(
                layer=number,
                actions=tuple(layer),
                isolated_hosts=tuple(sorted(isolated)),
                running_watchers=tuple(sorted(running)),
                revoked_secrets=tuple(sorted(revoked)),
                triggers=tuple(triggers),
            )
        )

    hosts = sorted(h.id for h in exposure.hosts)
    return Replay(
        strategy=plan.strategy,
        steps=tuple(steps),
        triggers=tuple(all_triggers),
        hosts_intact=tuple(h for h in hosts if h not in lost),
        hosts_lost=tuple(h for h in hosts if h in lost),
    )
