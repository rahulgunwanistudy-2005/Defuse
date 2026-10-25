"""Safety constraints C1-C6 as data, plus the ordinary action dependencies.

Each rule turns graph facts into requirements of the form "one of these actions must finish
before that action starts". A requirement with a single option is a plain ordering edge.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from defuse.model.graph import EdgeKind, project_id
from defuse.model.plan import Action, ActionKind, ConstraintSpec, EdgeReason
from defuse.plan.catalog import VERIFY_TARGET, Exposure

SANS = "https://isc.sans.edu/diary/33218"
GITLAB_VR = "https://about.gitlab.com/blog/gitlab-discovers-widespread-npm-supply-chain-attack/"
MICROSOFT = (
    "https://www.microsoft.com/en-us/security/blog/2026/08/04/"
    "chaindrop-supply-chain-compromise-anatomy-self-propagating-worm/"
)
THN = "https://thehackernews.com/2026/08/keyv-linked-npm-worm-poisons-hundreds.html"

CONSTRAINTS: dict[str, ConstraintSpec] = {
    spec.id: spec
    for spec in (
        ConstraintSpec(
            id="C1",
            title="Isolate before rotating a watched secret",
            rationale=(
                "A secret watched from a host may be rotated or revoked only after that host is "
                "isolated or its watcher is stopped, so the attacker's revocation handler cannot "
                "fire."
            ),
            source="SANS ISC, Don't revoke that token yet (Aug 5, 2026)",
            source_url=SANS,
        ),
        ConstraintSpec(
            id="C2",
            title="Preserve before eradicate",
            rationale=(
                "Snapshot a host for evidence before any eradication step runs on that same host, "
                "so the forensic record survives."
            ),
            source="SANS ISC, isolate-preserve-eradicate order (Aug 5, 2026)",
            source_url=SANS,
        ),
        ConstraintSpec(
            id="C3",
            title="Keep one lifeline on a live host",
            rationale=(
                "On a host not yet isolated, do not remove both registry-publish access and "
                "source-host access in the same layer; losing both at once is the dead-man's "
                "switch that makes the worm wipe the home directory."
            ),
            source="GitLab Vulnerability Research, Shai-Hulud variant (Nov 24, 2025)",
            source_url=GITLAB_VR,
        ),
        ConstraintSpec(
            id="C4",
            title="Stop propagation first",
            rationale=(
                "Rotate publish-capable secrets before any other secret, so the worm loses its "
                "ability to republish while the rest of the plan runs."
            ),
            source="Microsoft, ChainDrop worm anatomy (Aug 4, 2026)",
            source_url=MICROSOFT,
        ),
        ConstraintSpec(
            id="C5",
            title="Remove hooks before restoring agents",
            rationale=(
                "Planted agent hooks are removed before any agent identity that opened the repo is "
                "re-enabled, so re-infection through a SessionStart hook cannot recur."
            ),
            source="The Hacker News, keyv-linked npm worm (Aug 2026)",
            source_url=THN,
        ),
        ConstraintSpec(
            id="C6",
            title="Rebuild only on a clean runner",
            rationale=(
                "Rebuild artifacts only after the exposed runner is paused, so the rebuild cannot "
                "run on a compromised host."
            ),
            source="GitLab Vulnerability Research, CI runner compromise (Nov 24, 2025)",
            source_url=GITLAB_VR,
        ),
    )
}


@dataclass(frozen=True)
class Requirement:
    """`after` may start only once at least one option in `before_any` has finished."""

    after: str
    before_any: tuple[str, ...]
    reason: EdgeReason
    constraint_id: str | None
    note: str
    required: bool = False


@dataclass(frozen=True)
class OperatorPin:
    """An ordering the incident commander insists on, e.g. a token under active abuse."""

    before: str
    after: str
    note: str


Rule = Callable[[Exposure, dict[ActionKind, dict[str, Action]]], Iterator[Requirement]]
_RULES: list[Rule] = []


def _rule(fn: Rule) -> Rule:
    _RULES.append(fn)
    return fn


def _by_kind(actions: list[Action]) -> dict[ActionKind, dict[str, Action]]:
    index: dict[ActionKind, dict[str, Action]] = {}
    for action in actions:
        index.setdefault(action.kind, {})[action.target] = action
    return index


def _present(
    index: dict[ActionKind, dict[str, Action]], kind: ActionKind, target: str
) -> str | None:
    action = index.get(kind, {}).get(target)
    return action.id if action else None


# --- ordinary dependencies -----------------------------------------------------------------


@_rule
def _rotate_before_revoke(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for target, revoke in index.get(ActionKind.REVOKE_SECRET, {}).items():
        rotate = _present(index, ActionKind.ROTATE_SECRET, target)
        if rotate:
            yield Requirement(
                after=revoke.id,
                before_any=(rotate,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="issue the replacement before revoking the old credential",
            )


@_rule
def _quarantine_before_pin(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    quarantines = tuple(sorted(a.id for a in index.get(ActionKind.QUARANTINE_VERSION, {}).values()))
    for pin in index.get(ActionKind.PIN_KNOWN_GOOD, {}).values():
        for q in quarantines:
            yield Requirement(
                after=pin.id,
                before_any=(q,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="rogue versions are quarantined before pinning the known-good set",
            )


@_rule
def _pin_before_rebuild(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for target, rebuild in index.get(ActionKind.REBUILD_ARTIFACTS, {}).items():
        pin = _present(index, ActionKind.PIN_KNOWN_GOOD, target)
        if pin:
            yield Requirement(
                after=rebuild.id,
                before_any=(pin,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="pin the known-good versions before rebuilding against them",
            )


@_rule
def _host_sequence(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for host in exposure.hosts:
        isolate = _present(index, ActionKind.ISOLATE_HOST, host.id)
        snapshot = _present(index, ActionKind.SNAPSHOT_EVIDENCE, host.id)
        if isolate and snapshot:
            yield Requirement(
                after=snapshot,
                before_any=(isolate,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="isolate first so the snapshot captures a host the attacker cannot reach",
            )
        persistence = _present(index, ActionKind.REMOVE_PERSISTENCE, host.id)
        if persistence is None:
            continue
        for watcher in exposure.watchers:
            stop = _present(index, ActionKind.STOP_WATCHER, watcher.id)
            if stop and watcher.host == host.name:
                yield Requirement(
                    after=persistence,
                    before_any=(stop,),
                    reason=EdgeReason.DEPENDENCY,
                    constraint_id=None,
                    note="stop the running watcher before deleting its unit files",
                )


@_rule
def _cut_planters_before_hook_removal(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for hook in exposure.hooks:
        remove = _present(index, ActionKind.REMOVE_HOOK_FILES, project_id(hook.project_id))
        if remove is None:
            continue
        for edge in exposure.graph.into(hook.id, EdgeKind.PLANTED):
            cut = invalidator(index, edge.src)
            if cut:
                yield Requirement(
                    after=remove,
                    before_any=(cut,),
                    reason=EdgeReason.DEPENDENCY,
                    constraint_id=None,
                    note="cut the credential that planted the hook so it cannot be re-planted",
                )


@_rule
def _cut_publishers_before_rebuild(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for target, rebuild in index.get(ActionKind.REBUILD_ARTIFACTS, {}).items():
        for edge in exposure.graph.into(target, EdgeKind.CAN_PUBLISH):
            cut = invalidator(index, edge.src)
            if cut and edge.src in {s.id for s in exposure.secrets}:
                yield Requirement(
                    after=rebuild.id,
                    before_any=(cut,),
                    reason=EdgeReason.DEPENDENCY,
                    constraint_id=None,
                    note="cut the exposed publish credential before republishing clean builds",
                )


@_rule
def _verify_last(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    verify = _present(index, ActionKind.VERIFY_CLEAN, VERIFY_TARGET)
    if verify is None:
        return
    for kind, targets in index.items():
        if kind == ActionKind.VERIFY_CLEAN:
            continue
        for action in targets.values():
            if kind == ActionKind.RESTORE_AGENT_IDENTITY:
                yield Requirement(
                    after=action.id,
                    before_any=(verify,),
                    reason=EdgeReason.DEPENDENCY,
                    constraint_id=None,
                    note="agents are re-enabled only after verification passes",
                )
                continue
            yield Requirement(
                after=verify,
                before_any=(action.id,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="verification runs after every containment action",
            )


# --- safety constraints --------------------------------------------------------------------


@_rule
def _c1_isolate_before_rotate(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for watcher in exposure.watchers:
        guards: list[str] = []
        stop = _present(index, ActionKind.STOP_WATCHER, watcher.id)
        if stop:
            guards.append(stop)
        isolate = _present(index, ActionKind.ISOLATE_HOST, exposure.watcher_host(watcher))
        if isolate:
            guards.append(isolate)
        for secret in exposure.watched(watcher):
            for kind in (ActionKind.ROTATE_SECRET, ActionKind.REVOKE_SECRET):
                act = _present(index, kind, secret)
                if not act:
                    continue
                if guards:
                    note = (
                        f"{watcher.unit} on {watcher.host} watches this secret; neutralise it first"
                    )
                else:
                    note = (
                        f"{watcher.unit} on {watcher.host} watches this secret, and Defuse can "
                        f"neither isolate {watcher.host} nor stop the watcher because the host "
                        "is not under management. Bring the host under management or isolate "
                        "it by hand, then replan."
                    )
                yield Requirement(
                    after=act,
                    before_any=tuple(sorted(guards)),
                    reason=EdgeReason.CONSTRAINT,
                    constraint_id="C1",
                    note=note,
                    required=True,
                )


@_rule
def _c2_preserve_before_eradicate(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for host in exposure.hosts:
        snapshot = _present(index, ActionKind.SNAPSHOT_EVIDENCE, host.id)
        if snapshot is None:
            continue
        for kind in (ActionKind.STOP_WATCHER, ActionKind.REMOVE_PERSISTENCE):
            for target, action in index.get(kind, {}).items():
                on_host = kind == ActionKind.REMOVE_PERSISTENCE and target == host.id
                on_host = on_host or any(
                    w.id == target and w.host == host.name for w in exposure.watchers
                )
                if on_host:
                    yield Requirement(
                        after=action.id,
                        before_any=(snapshot,),
                        reason=EdgeReason.CONSTRAINT,
                        constraint_id="C2",
                        note=f"snapshot {host.name} before eradicating on it",
                    )


def invalidator(index: dict[ActionKind, dict[str, Action]], secret: str) -> str | None:
    """The action that makes a secret stop working: revoke, or a hand-off rotation."""

    revoke = _present(index, ActionKind.REVOKE_SECRET, secret)
    if revoke:
        return revoke
    rotate = index.get(ActionKind.ROTATE_SECRET, {}).get(secret)
    if rotate and rotate.param("mode") == "operator_handoff":
        return rotate.id
    return None


@_rule
def _c3_keep_one_lifeline(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for host in exposure.hosts:
        on_host = exposure.secrets_on_host(host)
        publish = [s for s in on_host if s.publish_capable]
        source = [s for s in on_host if s.source_capable]
        if not publish or not source:
            continue
        isolate = _present(index, ActionKind.ISOLATE_HOST, host.id)
        if isolate is not None:
            for secret in sorted({*publish, *source}, key=lambda s: s.id):
                act = invalidator(index, secret.id)
                if act:
                    yield Requirement(
                        after=act,
                        before_any=(isolate,),
                        reason=EdgeReason.CONSTRAINT,
                        constraint_id="C3",
                        note=(
                            f"{host.name} holds both publish and source access; isolate it "
                            "before either is cut"
                        ),
                    )
            continue
        for secret in publish:
            if secret.source_capable and invalidator(index, secret.id):
                yield Requirement(
                    after=invalidator(index, secret.id) or secret.id,
                    before_any=(),
                    reason=EdgeReason.CONSTRAINT,
                    constraint_id="C3",
                    note=(
                        f"{secret.label} carries both publish and source access on {host.name}, "
                        "which cannot be isolated, so cutting it removes both in one step"
                    ),
                    required=True,
                )
        for p in publish:
            for q in source:
                first, second = invalidator(index, p.id), invalidator(index, q.id)
                if first and second and first != second:
                    yield Requirement(
                        after=second,
                        before_any=(first,),
                        reason=EdgeReason.CONSTRAINT,
                        constraint_id="C3",
                        note=f"{host.name} cannot be isolated; cut publish access a step earlier",
                    )


@_rule
def _c4_propagation_first(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    publish_rotations = tuple(
        sorted(
            a.id
            for s in exposure.secrets
            if s.publish_capable
            for a in [index.get(ActionKind.ROTATE_SECRET, {}).get(s.id)]
            if a is not None
        )
    )
    if not publish_rotations:
        return
    publish_ids = {s.id for s in exposure.secrets if s.publish_capable}
    for secret in exposure.secrets:
        if secret.id in publish_ids:
            continue
        rotate = _present(index, ActionKind.ROTATE_SECRET, secret.id)
        if rotate:
            yield Requirement(
                after=rotate,
                before_any=publish_rotations,
                reason=EdgeReason.CONSTRAINT,
                constraint_id="C4",
                note="rotate publish-capable secrets before other secrets",
            )


@_rule
def _c5_hooks_before_restore(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    for agent in exposure.agents:
        restore = _present(index, ActionKind.RESTORE_AGENT_IDENTITY, agent.id)
        remove = _present(index, ActionKind.REMOVE_HOOK_FILES, project_id(agent.project_id))
        if restore and remove:
            yield Requirement(
                after=restore,
                before_any=(remove,),
                reason=EdgeReason.CONSTRAINT,
                constraint_id="C5",
                note="remove planted hooks before re-enabling the agent that opened the repo",
            )
        block = _present(index, ActionKind.BLOCK_AGENT_IDENTITY, agent.id)
        if restore and block:
            yield Requirement(
                after=restore,
                before_any=(block,),
                reason=EdgeReason.DEPENDENCY,
                constraint_id=None,
                note="block the agent before restoring it",
            )


@_rule
def _c6_rebuild_on_clean_runner(
    exposure: Exposure, index: dict[ActionKind, dict[str, Action]]
) -> Iterator[Requirement]:
    pauses = tuple(sorted(a.id for a in index.get(ActionKind.PAUSE_RUNNER, {}).values()))
    if not pauses:
        return
    for rebuild in index.get(ActionKind.REBUILD_ARTIFACTS, {}).values():
        yield Requirement(
            after=rebuild.id,
            before_any=pauses,
            reason=EdgeReason.CONSTRAINT,
            constraint_id="C6",
            note="pause the exposed runner before rebuilding",
        )


def requirements(exposure: Exposure, actions: list[Action]) -> list[Requirement]:
    index = _by_kind(actions)
    out: list[Requirement] = []
    for rule in _RULES:
        out.extend(rule(exposure, index))
    return out
