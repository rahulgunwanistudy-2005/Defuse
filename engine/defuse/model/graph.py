"""Exposure graph: typed nodes and evidence-carrying edges."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from defuse.model.ioc import HookKind


class NodeKind(StrEnum):
    PACKAGE_VERSION = "package_version"
    PIPELINE = "pipeline"
    JOB = "job"
    RUNNER = "runner"
    HOST = "host"
    SECRET = "secret"
    PROJECT = "project"
    REGISTRY_PACKAGE = "registry_package"
    HOOK_FILE = "hook_file"
    AGENT_SESSION = "agent_session"
    WATCHER = "watcher"


class EdgeKind(StrEnum):
    RESOLVED_IN = "RESOLVED_IN"
    PART_OF = "PART_OF"
    RAN_ON = "RAN_ON"
    RUNS_ON_HOST = "RUNS_ON_HOST"
    CAN_READ = "CAN_READ"
    CAN_PUBLISH = "CAN_PUBLISH"
    CAN_PUSH = "CAN_PUSH"
    PUBLISHED = "PUBLISHED"
    PLANTED = "PLANTED"
    WATCHES = "WATCHES"
    OPENED = "OPENED"
    HOSTED_IN = "HOSTED_IN"


class SecretKind(StrEnum):
    CI_VARIABLE = "ci_variable"
    PROJECT_ACCESS_TOKEN = "project_access_token"
    DEPLOY_TOKEN = "deploy_token"
    OIDC_AUDIENCE = "oidc_audience"


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    label: str


class PackageVersionNode(_Node):
    kind: Literal[NodeKind.PACKAGE_VERSION] = NodeKind.PACKAGE_VERSION
    name: str
    version: str
    generation: int
    rogue: bool = False
    registry_project_id: int | None = None
    published_at: datetime | None = None


class PipelineNode(_Node):
    kind: Literal[NodeKind.PIPELINE] = NodeKind.PIPELINE
    project_id: int
    pipeline_id: int
    ref: str
    sha: str
    web_url: str | None = None


class JobNode(_Node):
    kind: Literal[NodeKind.JOB] = NodeKind.JOB
    project_id: int
    job_id: int
    pipeline_id: int
    name: str
    ref: str
    protected_ref: bool
    environment: str | None = None
    started_at: datetime | None = None
    web_url: str | None = None


class RunnerNode(_Node):
    kind: Literal[NodeKind.RUNNER] = NodeKind.RUNNER
    runner_id: int
    description: str
    shared: bool
    persistent: bool
    tags: tuple[str, ...] = ()


class HostNode(_Node):
    kind: Literal[NodeKind.HOST] = NodeKind.HOST
    name: str
    managed: bool
    zone: str | None = None
    network_tags: tuple[str, ...] = ()


class SecretNode(_Node):
    kind: Literal[NodeKind.SECRET] = NodeKind.SECRET
    secret_kind: SecretKind
    owner: str
    name: str
    publish_capable: bool
    source_capable: bool
    rotatable: bool
    protected: bool = False
    environment_scope: str = "*"
    scopes: tuple[str, ...] = ()
    project_id: int | None = None
    token_id: int | None = None
    user_id: int | None = None
    carriers: tuple[str, ...] = ()


class ProjectNode(_Node):
    kind: Literal[NodeKind.PROJECT] = NodeKind.PROJECT
    project_id: int
    path: str


class RegistryPackageNode(_Node):
    kind: Literal[NodeKind.REGISTRY_PACKAGE] = NodeKind.REGISTRY_PACKAGE
    project_id: int
    name: str


class HookFileNode(_Node):
    kind: Literal[NodeKind.HOOK_FILE] = NodeKind.HOOK_FILE
    project_id: int
    path: str
    hook_kind: HookKind
    commit_sha: str | None = None


class AgentSessionNode(_Node):
    kind: Literal[NodeKind.AGENT_SESSION] = NodeKind.AGENT_SESSION
    identity: str
    user_id: int | None = None
    project_id: int


class WatcherNode(_Node):
    kind: Literal[NodeKind.WATCHER] = NodeKind.WATCHER
    host: str
    unit: str
    indicator_path: str


Node = Annotated[
    PackageVersionNode
    | PipelineNode
    | JobNode
    | RunnerNode
    | HostNode
    | SecretNode
    | ProjectNode
    | RegistryPackageNode
    | HookFileNode
    | AgentSessionNode
    | WatcherNode,
    Field(discriminator="kind"),
]


class Edge(BaseModel):
    """A fact linking two nodes, with the evidence it was derived from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    src: str
    dst: str
    kind: EdgeKind
    evidence: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.src, self.dst, self.kind.value)


class Generation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    depth: int
    versions: tuple[str, ...]
    jobs: int
    projects: int


class ExposureGraph(BaseModel):
    """The complete exposure picture for one incident. Serialises byte-identically."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ioc_id: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    generations: tuple[Generation, ...] = ()

    _by_id: dict[str, Node] = PrivateAttr(default_factory=dict)
    _out: dict[str, list[Edge]] = PrivateAttr(default_factory=dict)
    _into: dict[str, list[Edge]] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        self._by_id = {n.id: n for n in self.nodes}
        for edge in self.edges:
            self._out.setdefault(edge.src, []).append(edge)
            self._into.setdefault(edge.dst, []).append(edge)

    def has(self, node_id: str) -> bool:
        return node_id in self._by_id

    def node(self, node_id: str) -> Node:
        return self._by_id[node_id]

    def by_kind(self, kind: NodeKind) -> list[Node]:
        return [n for n in self.nodes if n.kind == kind]

    def out(self, node_id: str, kind: EdgeKind | None = None) -> list[Edge]:
        return [e for e in self._out.get(node_id, []) if kind is None or e.kind == kind]

    def into(self, node_id: str, kind: EdgeKind | None = None) -> list[Edge]:
        return [e for e in self._into.get(node_id, []) if kind is None or e.kind == kind]

    def canonical_json(self) -> str:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def package_id(name: str, version: str) -> str:
    return f"pkg:{name}@{version}"


def pipeline_id(project_id: int, pipeline: int) -> str:
    return f"pipeline:{project_id}:{pipeline}"


def job_id(project_id: int, job: int) -> str:
    return f"job:{project_id}:{job}"


def runner_id(runner: int) -> str:
    return f"runner:{runner}"


def host_id(name: str) -> str:
    return f"host:{name}"


def secret_id(kind: SecretKind, owner: str, name: str) -> str:
    return f"secret:{kind.value}:{owner}:{name}"


def project_id(project: int) -> str:
    return f"project:{project}"


def registry_id(project: int, name: str) -> str:
    return f"registry:{project}:{name}"


def hook_id(project: int, path: str) -> str:
    return f"hook:{project}:{path}"


def agent_id(identity: str, project: int) -> str:
    return f"agent:{identity}:{project}"


def watcher_id(host: str, unit: str) -> str:
    return f"watcher:{host}:{unit}"
