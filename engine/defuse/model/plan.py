"""Actions, ordering edges and plans."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Phase(StrEnum):
    ISOLATE = "isolate"
    PRESERVE = "preserve"
    ERADICATE = "eradicate"
    ROTATE = "rotate"
    QUARANTINE = "quarantine"
    REBUILD = "rebuild"
    VERIFY = "verify"

    @property
    def rank(self) -> int:
        return list(Phase).index(self)


class ActionKind(StrEnum):
    ISOLATE_HOST = "isolate_host"
    SNAPSHOT_EVIDENCE = "snapshot_evidence"
    STOP_WATCHER = "stop_watcher"
    REMOVE_PERSISTENCE = "remove_persistence"
    REMOVE_HOOK_FILES = "remove_hook_files"
    PAUSE_RUNNER = "pause_runner"
    ROTATE_SECRET = "rotate_secret"
    REVOKE_SECRET = "revoke_secret"
    QUARANTINE_VERSION = "quarantine_version"
    PIN_KNOWN_GOOD = "pin_known_good"
    REBUILD_ARTIFACTS = "rebuild_artifacts"
    BLOCK_AGENT_IDENTITY = "block_agent_identity"
    RESTORE_AGENT_IDENTITY = "restore_agent_identity"
    VERIFY_CLEAN = "verify_clean"


ACTION_PHASE: dict[ActionKind, Phase] = {
    ActionKind.ISOLATE_HOST: Phase.ISOLATE,
    ActionKind.PAUSE_RUNNER: Phase.ISOLATE,
    ActionKind.BLOCK_AGENT_IDENTITY: Phase.ISOLATE,
    ActionKind.SNAPSHOT_EVIDENCE: Phase.PRESERVE,
    ActionKind.STOP_WATCHER: Phase.ERADICATE,
    ActionKind.REMOVE_PERSISTENCE: Phase.ERADICATE,
    ActionKind.REMOVE_HOOK_FILES: Phase.ERADICATE,
    ActionKind.ROTATE_SECRET: Phase.ROTATE,
    ActionKind.REVOKE_SECRET: Phase.ROTATE,
    ActionKind.QUARANTINE_VERSION: Phase.QUARANTINE,
    ActionKind.PIN_KNOWN_GOOD: Phase.REBUILD,
    ActionKind.REBUILD_ARTIFACTS: Phase.REBUILD,
    ActionKind.RESTORE_AGENT_IDENTITY: Phase.VERIFY,
    ActionKind.VERIFY_CLEAN: Phase.VERIFY,
}

GCP_ACTIONS = frozenset(
    {
        ActionKind.ISOLATE_HOST,
        ActionKind.SNAPSHOT_EVIDENCE,
        ActionKind.STOP_WATCHER,
        ActionKind.REMOVE_PERSISTENCE,
    }
)


def action_id(kind: ActionKind, target: str) -> str:
    return f"{kind.value}@{target}"


class Action(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ActionKind
    target: str
    phase: Phase
    priority: int
    label: str
    params: tuple[tuple[str, str], ...] = ()

    def param(self, key: str) -> str | None:
        for k, v in self.params:
            if k == key:
                return v
        return None


class EdgeReason(StrEnum):
    CONSTRAINT = "constraint"
    DEPENDENCY = "dependency"
    OPERATOR = "operator"


class OrderingEdge(BaseModel):
    """`before` must finish before `after` starts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    before: str
    after: str
    reason: EdgeReason
    constraint_id: str | None = None
    note: str


class ConstraintSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    rationale: str
    source: str
    source_url: str


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ioc_id: str
    strategy: Literal["defuse", "naive"]
    actions: tuple[Action, ...]
    edges: tuple[OrderingEdge, ...]
    layers: tuple[tuple[str, ...], ...]
    completed: tuple[str, ...] = ()

    def action(self, action_id: str) -> Action:
        for action in self.actions:
            if action.id == action_id:
                return action
        raise KeyError(action_id)

    def layer_of(self, action_id: str) -> int:
        for index, layer in enumerate(self.layers):
            if action_id in layer:
                return index
        raise KeyError(action_id)


class ShapingEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    before: str
    reason: EdgeReason
    constraint_id: str | None
    note: str


class Explanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str
    label: str
    layer: int
    phase: Phase
    shaped_by: tuple[ShapingEdge, ...]
    constraints: tuple[ConstraintSpec, ...]
    critical_path: tuple[str, ...]
    summary: str


class Conflict(BaseModel):
    """A minimal set of ordering rules that cannot all hold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[str, ...]
    cycle: tuple[str, ...]
    explanation: str
