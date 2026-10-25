"""Action catalog: which containment actions an exposure graph calls for."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from defuse.model.graph import (
    AgentSessionNode,
    EdgeKind,
    ExposureGraph,
    HookFileNode,
    HostNode,
    JobNode,
    NodeKind,
    PackageVersionNode,
    ProjectNode,
    RunnerNode,
    SecretNode,
    WatcherNode,
    host_id,
    project_id,
)
from defuse.model.plan import ACTION_PHASE, Action, ActionKind, action_id

PRIORITY: dict[ActionKind, int] = {
    ActionKind.ISOLATE_HOST: 100,
    ActionKind.PAUSE_RUNNER: 95,
    ActionKind.BLOCK_AGENT_IDENTITY: 90,
    ActionKind.QUARANTINE_VERSION: 85,
    ActionKind.SNAPSHOT_EVIDENCE: 80,
    ActionKind.STOP_WATCHER: 75,
    ActionKind.REMOVE_PERSISTENCE: 70,
    ActionKind.REMOVE_HOOK_FILES: 65,
    ActionKind.ROTATE_SECRET: 50,
    ActionKind.REVOKE_SECRET: 45,
    ActionKind.PIN_KNOWN_GOOD: 40,
    ActionKind.REBUILD_ARTIFACTS: 30,
    ActionKind.RESTORE_AGENT_IDENTITY: 20,
    ActionKind.VERIFY_CLEAN: 0,
}
PUBLISH_BONUS = 10

VERIFY_TARGET = "incident"


@dataclass(frozen=True)
class Exposure:
    """Graph facts the planner reasons about, pre-indexed."""

    graph: ExposureGraph
    infected_jobs: tuple[JobNode, ...]
    secrets: tuple[SecretNode, ...]
    hosts: tuple[HostNode, ...]
    runners: tuple[RunnerNode, ...]
    watchers: tuple[WatcherNode, ...]
    hooks: tuple[HookFileNode, ...]
    agents: tuple[AgentSessionNode, ...]
    versions: tuple[PackageVersionNode, ...]

    def watched(self, watcher: WatcherNode) -> list[str]:
        return sorted(e.dst for e in self.graph.out(watcher.id, EdgeKind.WATCHES))

    def watcher_host(self, watcher: WatcherNode) -> str:
        return host_id(watcher.host)

    def secrets_on_host(self, host: HostNode) -> list[SecretNode]:
        runners = {e.src for e in self.graph.into(host.id, EdgeKind.RUNS_ON_HOST)}
        jobs = {e.src for r in runners for e in self.graph.into(r, EdgeKind.RAN_ON)}
        ids = {e.dst for j in jobs for e in self.graph.out(j, EdgeKind.CAN_READ)}
        return [s for s in self.secrets if s.id in ids]

    def infected_projects(self) -> list[int]:
        return sorted({j.project_id for j in self.infected_jobs})


def index(graph: ExposureGraph) -> Exposure:
    read_targets = {e.dst for e in graph.edges if e.kind == EdgeKind.CAN_READ}
    infected = {e.dst for e in graph.edges if e.kind == EdgeKind.RESOLVED_IN}

    def typed[T](kind: NodeKind, cls: type[T]) -> tuple[T, ...]:
        return tuple(n for n in graph.by_kind(kind) if isinstance(n, cls))

    return Exposure(
        graph=graph,
        infected_jobs=tuple(j for j in typed(NodeKind.JOB, JobNode) if j.id in infected),
        secrets=tuple(s for s in typed(NodeKind.SECRET, SecretNode) if s.id in read_targets),
        hosts=typed(NodeKind.HOST, HostNode),
        runners=typed(NodeKind.RUNNER, RunnerNode),
        watchers=typed(NodeKind.WATCHER, WatcherNode),
        hooks=typed(NodeKind.HOOK_FILE, HookFileNode),
        agents=typed(NodeKind.AGENT_SESSION, AgentSessionNode),
        versions=typed(NodeKind.PACKAGE_VERSION, PackageVersionNode),
    )


def _action(
    kind: ActionKind,
    target: str,
    label: str,
    *,
    bonus: int = 0,
    params: tuple[tuple[str, str], ...] = (),
) -> Action:
    return Action(
        id=action_id(kind, target),
        kind=kind,
        target=target,
        phase=ACTION_PHASE[kind],
        priority=PRIORITY[kind] + bonus,
        label=label,
        params=params,
    )


def _project_label(exposure: Exposure, pid: int) -> str:
    node_id = project_id(pid)
    if exposure.graph.has(node_id):
        node = exposure.graph.node(node_id)
        if isinstance(node, ProjectNode):
            return node.path
    return f"project {pid}"


def actions_for(exposure: Exposure) -> list[Action]:
    return sorted(_generate(exposure), key=lambda a: a.id)


def _generate(exposure: Exposure) -> Iterator[Action]:
    for host in exposure.hosts:
        if not host.managed:
            continue
        yield _action(ActionKind.ISOLATE_HOST, host.id, f"Isolate host {host.name}")
        yield _action(ActionKind.SNAPSHOT_EVIDENCE, host.id, f"Snapshot disk of {host.name}")
        if any(w.host == host.name for w in exposure.watchers):
            yield _action(
                ActionKind.REMOVE_PERSISTENCE, host.id, f"Remove persistence on {host.name}"
            )
    managed = {h.name for h in exposure.hosts if h.managed}
    for watcher in exposure.watchers:
        if watcher.host in managed:
            yield _action(
                ActionKind.STOP_WATCHER,
                watcher.id,
                f"Stop watcher {watcher.unit} on {watcher.host}",
                params=(("unit", watcher.unit), ("host", watcher.host)),
            )
    for runner in exposure.runners:
        if not runner.shared:
            yield _action(ActionKind.PAUSE_RUNNER, runner.id, f"Pause runner {runner.description}")
    for secret in exposure.secrets:
        bonus = PUBLISH_BONUS if secret.publish_capable else 0
        mode = "issue_and_swap" if secret.rotatable else "operator_handoff"
        yield _action(
            ActionKind.ROTATE_SECRET,
            secret.id,
            f"Rotate {secret.label}",
            bonus=bonus,
            params=(("mode", mode),),
        )
        if secret.rotatable:
            yield _action(
                ActionKind.REVOKE_SECRET, secret.id, f"Revoke old {secret.label}", bonus=bonus
            )
    for version in exposure.versions:
        if version.registry_project_id is not None:
            yield _action(
                ActionKind.QUARANTINE_VERSION,
                version.id,
                f"Quarantine {version.label}",
                bonus=PUBLISH_BONUS if version.rogue else 0,
            )
    for pid in exposure.infected_projects():
        target = project_id(pid)
        name = _project_label(exposure, pid)
        yield _action(ActionKind.PIN_KNOWN_GOOD, target, f"Pin known-good versions in {name}")
        yield _action(ActionKind.REBUILD_ARTIFACTS, target, f"Rebuild {name} on clean runners")
    rebuilt = set(exposure.infected_projects())
    for version in exposure.versions:
        registry = version.registry_project_id
        if registry is not None and registry not in rebuilt:
            rebuilt.add(registry)
            yield _action(
                ActionKind.REBUILD_ARTIFACTS,
                project_id(registry),
                f"Rebuild {_project_label(exposure, registry)} on clean runners",
            )
    hooked: dict[int, list[str]] = {}
    for hook in exposure.hooks:
        hooked.setdefault(hook.project_id, []).append(hook.path)
    for pid, paths in sorted(hooked.items()):
        yield _action(
            ActionKind.REMOVE_HOOK_FILES,
            project_id(pid),
            f"Remove planted hooks from {_project_label(exposure, pid)}",
            params=tuple(("path", p) for p in sorted(paths)),
        )
    for agent in exposure.agents:
        yield _action(
            ActionKind.BLOCK_AGENT_IDENTITY, agent.id, f"Block writes by agent {agent.identity}"
        )
        yield _action(
            ActionKind.RESTORE_AGENT_IDENTITY, agent.id, f"Restore agent {agent.identity}"
        )
    yield _action(ActionKind.VERIFY_CLEAN, VERIFY_TARGET, "Verify the incident is contained")
