"""Incidents, the action ledger, verification results and timing metrics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from defuse.model.facts import Degradation
from defuse.model.plan import ActionKind


class IncidentStatus(StrEnum):
    OPEN = "open"
    SCOPED = "scoped"
    CONTAINING = "containing"
    CONTAINED = "contained"
    VERIFIED = "verified"
    FAILED = "failed"


class IncidentOrigin(StrEnum):
    ADVISORY = "advisory"
    DETECTOR = "detector"
    SCENARIO = "scenario"


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    ioc_id: str
    origin: IncidentOrigin
    status: IncidentStatus
    namespace: str
    created_at: datetime
    detected_at: datetime
    first_exposure_at: datetime | None = None
    work_item_url: str | None = None
    pipeline_url: str | None = None


class RecordStatus(StrEnum):
    APPLIED = "applied"
    ALREADY_SATISFIED = "already_satisfied"
    DRY_RUN = "dry_run"
    NEEDS_OPERATOR = "needs_operator"
    FAILED = "failed"


StateValue = str | int | bool | None | list[str]


class ActionRecord(BaseModel):
    """One append-only ledger line: who did what, the state before and after, and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: str
    action_id: str
    kind: ActionKind
    target: str
    actor: str
    status: RecordStatus
    dry_run: bool
    before: dict[str, StateValue] = Field(default_factory=dict)
    after: dict[str, StateValue] = Field(default_factory=dict)
    detail: str = ""
    evidence_url: str | None = None
    started_at: datetime
    finished_at: datetime


class CheckOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"


class VerificationCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal[
        "no_affected_resolution",
        "no_new_publishes",
        "sinkhole_quiet",
        "sentinel_intact",
        "hooks_removed",
        "secrets_rotated",
        "collection_complete",
        "watchers_stopped",
        "quarantined_versions_absent",
        "old_credentials_revoked",
        "hosts_isolated",
        "source_locks_clean",
    ]
    outcome: CheckOutcome
    detail: str


class Verification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checked_at: datetime
    checks: tuple[VerificationCheck, ...]

    @property
    def passed(self) -> bool:
        """Verification needs positive evidence for every check."""

        return bool(self.checks) and all(c.outcome == CheckOutcome.PASSED for c in self.checks)

    @property
    def fully_verified(self) -> bool:
        return self.passed

    @property
    def unverified(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.checks if c.outcome == CheckOutcome.UNVERIFIED)


class Metrics(BaseModel):
    """GitLab Security Standard timings, in seconds, from stored timestamps only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    time_to_detect: float | None
    time_to_scope: float | None
    time_to_containment: float | None
    time_to_verified_remediation: float | None
    actions_executed: int
    llm_credits: float | None = None


class IncidentRecord(BaseModel):
    """The postmortem-ready record: timeline, actions, metrics, and what could not be verified."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident: Incident
    actions: tuple[ActionRecord, ...]
    verification: Verification | None
    metrics: Metrics
    degradations: tuple[Degradation, ...]
    unverified: tuple[str, ...]
