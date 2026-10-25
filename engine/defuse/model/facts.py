"""Collected facts: what the collectors read from GitLab and GCP, before any inference.

Nothing in this module can hold a secret value. Variables and tokens are described by name,
scope and metadata only.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from defuse.model.ioc import HookKind


class _Fact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProjectFact(_Fact):
    id: int
    path: str
    default_branch: str = "main"
    web_url: str | None = None


class PipelineFact(_Fact):
    project_id: int
    id: int
    ref: str
    sha: str
    created_at: datetime
    source: str = "push"
    web_url: str | None = None


class DependencySource(StrEnum):
    LOCKFILE = "lockfile"
    TRACE = "trace"


class ResolvedDependency(_Fact):
    name: str
    version: str
    source: DependencySource
    evidence: str


class JobFact(_Fact):
    project_id: int
    id: int
    pipeline_id: int
    name: str
    ref: str
    protected_ref: bool
    started_at: datetime | None
    finished_at: datetime | None = None
    environment: str | None = None
    runner_id: int | None = None
    web_url: str | None = None
    resolved: tuple[ResolvedDependency, ...] = ()


class RunnerFact(_Fact):
    id: int
    description: str
    shared: bool
    persistent: bool
    paused: bool = False
    tags: tuple[str, ...] = ()
    host: str | None = None


class HostFact(_Fact):
    name: str
    managed: bool
    zone: str | None = None
    network_tags: tuple[str, ...] = ()


class VariableFact(_Fact):
    owner: str
    visible_to_projects: tuple[int, ...]
    key: str
    environment_scope: str = "*"
    protected: bool = False
    masked: bool = False
    holds_token: str | None = None


class AccessTokenFact(_Fact):
    project_id: int
    id: int
    name: str
    scopes: tuple[str, ...]
    active: bool = True
    user_id: int | None = None
    expires_at: datetime | None = None


class DeployTokenFact(_Fact):
    project_id: int
    id: int
    name: str
    username: str
    scopes: tuple[str, ...]
    revoked: bool = False
    expired: bool = False


class PublishedPackageFact(_Fact):
    project_id: int
    package_id: int
    name: str
    version: str
    created_at: datetime
    pipeline_ids: tuple[int, ...] = ()
    pipeline_sha: str | None = None
    commit_exists: bool | None = None
    published_by: str | None = None
    creator_id: int | None = None
    file_sha256s: tuple[str, ...] = ()


class HookFinding(_Fact):
    project_id: int
    path: str
    hook_kind: HookKind
    signature: str
    commit_sha: str | None = None
    author_user_id: int | None = None
    committed_at: datetime | None = None


class AgentSessionFact(_Fact):
    identity: str
    project_id: int
    user_id: int | None = None
    opened_at: datetime | None = None


class WatcherFinding(_Fact):
    host: str
    unit: str
    indicator_path: str


class Degradation(_Fact):
    """Something the engine could not see, and what that means for the result."""

    source: str
    reason: str
    effect: str


class CollectedFacts(_Fact):
    collected_at: datetime
    namespace: str
    projects: tuple[ProjectFact, ...] = ()
    pipelines: tuple[PipelineFact, ...] = ()
    jobs: tuple[JobFact, ...] = ()
    runners: tuple[RunnerFact, ...] = ()
    hosts: tuple[HostFact, ...] = ()
    variables: tuple[VariableFact, ...] = ()
    access_tokens: tuple[AccessTokenFact, ...] = ()
    deploy_tokens: tuple[DeployTokenFact, ...] = ()
    published_packages: tuple[PublishedPackageFact, ...] = ()
    hook_findings: tuple[HookFinding, ...] = ()
    agent_sessions: tuple[AgentSessionFact, ...] = ()
    watcher_findings: tuple[WatcherFinding, ...] = ()
    degradations: tuple[Degradation, ...] = ()
