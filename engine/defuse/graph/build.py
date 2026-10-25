"""Build the exposure graph from an IOC set and collected facts.

Pure and deterministic: the same inputs give a byte-identical `canonical_json()`.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from defuse.model.facts import (
    AccessTokenFact,
    CollectedFacts,
    DeployTokenFact,
    JobFact,
    PublishedPackageFact,
    VariableFact,
)
from defuse.model.graph import (
    AgentSessionNode,
    Edge,
    EdgeKind,
    ExposureGraph,
    Generation,
    HookFileNode,
    HostNode,
    JobNode,
    Node,
    PackageVersionNode,
    PipelineNode,
    ProjectNode,
    RegistryPackageNode,
    RunnerNode,
    SecretKind,
    SecretNode,
    WatcherNode,
    agent_id,
    hook_id,
    host_id,
    job_id,
    package_id,
    pipeline_id,
    project_id,
    registry_id,
    runner_id,
    secret_id,
    watcher_id,
)
from defuse.model.ioc import IOCSet

AUTO_DEPLOY_TOKEN = "gitlab-deploy-token"
PUBLISH_SCOPES = frozenset({"api", "write_package_registry"})
SOURCE_SCOPES = frozenset({"api", "write_repository"})
_PUBLISH_NAME = re.compile(r"(NPM|NODE_AUTH|PYPI|TWINE|REGISTRY|PUBLISH)", re.IGNORECASE)
_SOURCE_NAME = re.compile(r"(GITHUB|GH_|GITLAB|GL_|GIT_|REPO|PUSH)", re.IGNORECASE)


@dataclass
class _Builder:
    ioc: IOCSet
    facts: CollectedFacts
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)
    version_gen: dict[tuple[str, str], int] = field(default_factory=dict)
    job_gen: dict[str, int] = field(default_factory=dict)
    exposed: set[str] = field(default_factory=set)

    def add(self, node: Node) -> None:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return
        if isinstance(existing, PackageVersionNode) and isinstance(node, PackageVersionNode):
            self.nodes[node.id] = existing.model_copy(
                update={
                    "generation": min(existing.generation, node.generation),
                    "rogue": existing.rogue or node.rogue,
                    "registry_project_id": existing.registry_project_id or node.registry_project_id,
                    "published_at": existing.published_at or node.published_at,
                }
            )
        elif isinstance(existing, SecretNode) and isinstance(node, SecretNode):
            carriers = tuple(sorted(set(existing.carriers) | set(node.carriers)))
            self.nodes[node.id] = existing.model_copy(update={"carriers": carriers})

    def link(self, src: str, dst: str, kind: EdgeKind, evidence: str) -> None:
        key = (src, dst, kind.value)
        if key not in self.edges:
            self.edges[key] = Edge(src=src, dst=dst, kind=kind, evidence=evidence)

    # --- facts lookups -------------------------------------------------------------------

    def project_node(self, pid: int) -> str:
        project = next((p for p in self.facts.projects if p.id == pid), None)
        path = project.path if project else f"project-{pid}"
        node_id = project_id(pid)
        self.add(ProjectNode(id=node_id, label=path, project_id=pid, path=path))
        return node_id

    # --- rules ---------------------------------------------------------------------------

    def run(self) -> ExposureGraph:
        self._seed_versions()
        while True:
            before = len(self.version_gen)
            self._infect_jobs()
            self._find_rogue_versions()
            if len(self.version_gen) == before:
                break
        self._hooks_and_agents()
        self._watchers()
        return ExposureGraph(
            ioc_id=self.ioc.id,
            nodes=tuple(sorted(self.nodes.values(), key=lambda n: n.id)),
            edges=tuple(sorted(self.edges.values(), key=lambda e: e.key)),
            generations=self._generations(),
        )

    def _seed_versions(self) -> None:
        observed: set[tuple[str, str]] = set()
        for job in self.facts.jobs:
            observed.update((d.name, d.version) for d in job.resolved)
        observed.update((p.name, p.version) for p in self.facts.published_packages)
        for name, version in sorted(observed):
            if self.ioc.affected(name, version):
                self._add_version(name, version, generation=0, rogue=False)
        for pkg in self.facts.published_packages:
            if (pkg.name, pkg.version) in self.version_gen:
                self._place_in_registry(pkg)

    def _add_version(self, name: str, version: str, *, generation: int, rogue: bool) -> None:
        key = (name, version)
        current = self.version_gen.get(key)
        if current is None or generation < current:
            self.version_gen[key] = generation
        self.add(
            PackageVersionNode(
                id=package_id(name, version),
                label=f"{name}@{version}",
                name=name,
                version=version,
                generation=self.version_gen[key],
                rogue=rogue,
            )
        )

    def _place_in_registry(self, pkg: PublishedPackageFact) -> None:
        version_node = package_id(pkg.name, pkg.version)
        current = _as(self.nodes[version_node], PackageVersionNode)
        self.nodes[version_node] = current.model_copy(
            update={"registry_project_id": pkg.project_id, "published_at": pkg.created_at}
        )
        reg = registry_id(pkg.project_id, pkg.name)
        self.add(
            RegistryPackageNode(id=reg, label=pkg.name, project_id=pkg.project_id, name=pkg.name)
        )
        self.link(version_node, reg, EdgeKind.HOSTED_IN, f"package {pkg.package_id}")
        self.link(reg, self.project_node(pkg.project_id), EdgeKind.HOSTED_IN, "package registry")

    def _in_window(self, job: JobFact) -> bool:
        return job.started_at is not None and self.ioc.in_window(job.started_at)

    def _infect_jobs(self) -> None:
        for job in sorted(self.facts.jobs, key=lambda j: (j.project_id, j.id)):
            if not self._in_window(job):
                continue
            hits = [d for d in job.resolved if (d.name, d.version) in self.version_gen]
            if not hits:
                continue
            jid = job_id(job.project_id, job.id)
            generation = min(self.version_gen[(d.name, d.version)] for d in hits)
            self.job_gen[jid] = min(generation, self.job_gen.get(jid, generation))
            self._add_job(job)
            for dep in sorted(hits, key=lambda d: (d.name, d.version, d.source.value)):
                self.link(
                    package_id(dep.name, dep.version),
                    jid,
                    EdgeKind.RESOLVED_IN,
                    f"{dep.source.value}: {dep.evidence}",
                )
            for secret, evidence in self._readable_secrets(job):
                self.exposed.add(secret)
                self.link(jid, secret, EdgeKind.CAN_READ, evidence)

    def _add_job(self, job: JobFact) -> None:
        jid = job_id(job.project_id, job.id)
        self.add(
            JobNode(
                id=jid,
                label=f"{job.name} #{job.id}",
                project_id=job.project_id,
                job_id=job.id,
                pipeline_id=job.pipeline_id,
                name=job.name,
                ref=job.ref,
                protected_ref=job.protected_ref,
                environment=job.environment,
                started_at=job.started_at,
                web_url=job.web_url,
            )
        )
        pipeline = next(
            (
                p
                for p in self.facts.pipelines
                if p.project_id == job.project_id and p.id == job.pipeline_id
            ),
            None,
        )
        pid = pipeline_id(job.project_id, job.pipeline_id)
        self.add(
            PipelineNode(
                id=pid,
                label=f"pipeline #{job.pipeline_id}",
                project_id=job.project_id,
                pipeline_id=job.pipeline_id,
                ref=pipeline.ref if pipeline else job.ref,
                sha=pipeline.sha if pipeline else "",
                web_url=pipeline.web_url if pipeline else None,
            )
        )
        self.link(jid, pid, EdgeKind.PART_OF, "job belongs to pipeline")
        self.link(pid, self.project_node(job.project_id), EdgeKind.PART_OF, "pipeline project")
        if job.runner_id is None:
            return
        runner = next((r for r in self.facts.runners if r.id == job.runner_id), None)
        if runner is None:
            return
        rid = runner_id(runner.id)
        self.add(
            RunnerNode(
                id=rid,
                label=runner.description or f"runner {runner.id}",
                runner_id=runner.id,
                description=runner.description,
                shared=runner.shared,
                persistent=runner.persistent,
                tags=tuple(sorted(runner.tags)),
            )
        )
        self.link(jid, rid, EdgeKind.RAN_ON, f"job {job.id} runner_id={runner.id}")
        if runner.host is None:
            return
        host = next((h for h in self.facts.hosts if h.name == runner.host), None)
        hid = host_id(runner.host)
        self.add(
            HostNode(
                id=hid,
                label=runner.host,
                name=runner.host,
                managed=host.managed if host else False,
                zone=host.zone if host else None,
                network_tags=tuple(sorted(host.network_tags)) if host else (),
            )
        )
        self.link(rid, hid, EdgeKind.RUNS_ON_HOST, "runner host mapping")

    def _readable_secrets(self, job: JobFact) -> Iterable[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for var in self.facts.variables:
            if not _variable_readable(var, job):
                continue
            carrier = f"{var.owner}:{var.key}"
            token = self._token_for(var.holds_token) if var.holds_token else None
            if token is not None:
                found.append((token, f"CI variable {var.key} ({var.owner}) holds this token"))
                self._attach_carrier(token, carrier)
                continue
            sid = secret_id(SecretKind.CI_VARIABLE, var.owner, var.key)
            self.add(
                SecretNode(
                    id=sid,
                    label=var.key,
                    secret_kind=SecretKind.CI_VARIABLE,
                    owner=var.owner,
                    name=var.key,
                    publish_capable=bool(_PUBLISH_NAME.search(var.key)),
                    source_capable=bool(_SOURCE_NAME.search(var.key)),
                    rotatable=False,
                    protected=var.protected,
                    environment_scope=var.environment_scope,
                    carriers=(carrier,),
                )
            )
            scope = "all environments" if var.environment_scope == "*" else var.environment_scope
            found.append((sid, f"CI variable {var.key} ({var.owner}) visible in {scope}"))
        for deploy in self.facts.deploy_tokens:
            if (
                deploy.project_id == job.project_id
                and deploy.name == AUTO_DEPLOY_TOKEN
                and not deploy.revoked
                and not deploy.expired
            ):
                sid = self._deploy_token_node(deploy)
                found.append((sid, "gitlab-deploy-token is injected as CI_DEPLOY_PASSWORD"))
        return sorted(found)

    def _token_for(self, ref: str) -> str | None:
        kind, _, raw = ref.partition(":")
        if not raw.isdigit():
            return None
        token_num = int(raw)
        if kind == "project_access_token":
            pat = next((t for t in self.facts.access_tokens if t.id == token_num), None)
            return self._access_token_node(pat) if pat and pat.active else None
        if kind == "deploy_token":
            dt = next((t for t in self.facts.deploy_tokens if t.id == token_num), None)
            return self._deploy_token_node(dt) if dt and not dt.revoked else None
        return None

    def _attach_carrier(self, sid: str, carrier: str) -> None:
        node = _as(self.nodes[sid], SecretNode)
        self.nodes[sid] = node.model_copy(
            update={"carriers": tuple(sorted({*node.carriers, carrier}))}
        )

    def _access_token_node(self, token: AccessTokenFact) -> str:
        owner = f"project/{token.project_id}"
        sid = secret_id(SecretKind.PROJECT_ACCESS_TOKEN, owner, str(token.id))
        scopes = tuple(sorted(token.scopes))
        self.add(
            SecretNode(
                id=sid,
                label=token.name,
                secret_kind=SecretKind.PROJECT_ACCESS_TOKEN,
                owner=owner,
                name=token.name,
                publish_capable=bool(PUBLISH_SCOPES & set(scopes)),
                source_capable=bool(SOURCE_SCOPES & set(scopes)),
                rotatable=True,
                scopes=scopes,
                project_id=token.project_id,
                token_id=token.id,
                user_id=token.user_id,
            )
        )
        self._token_reach(sid, token.project_id, scopes)
        return sid

    def _deploy_token_node(self, token: DeployTokenFact) -> str:
        owner = f"project/{token.project_id}"
        sid = secret_id(SecretKind.DEPLOY_TOKEN, owner, str(token.id))
        scopes = tuple(sorted(token.scopes))
        self.add(
            SecretNode(
                id=sid,
                label=token.name,
                secret_kind=SecretKind.DEPLOY_TOKEN,
                owner=owner,
                name=token.name,
                publish_capable=bool(PUBLISH_SCOPES & set(scopes)),
                source_capable=bool(SOURCE_SCOPES & set(scopes)),
                rotatable=True,
                scopes=scopes,
                project_id=token.project_id,
                token_id=token.id,
            )
        )
        self._token_reach(sid, token.project_id, scopes)
        return sid

    def _token_reach(self, sid: str, pid: int, scopes: tuple[str, ...]) -> None:
        target = self.project_node(pid)
        if PUBLISH_SCOPES & set(scopes):
            self.link(sid, target, EdgeKind.CAN_PUBLISH, f"scopes {','.join(scopes)}")
        if SOURCE_SCOPES & set(scopes):
            self.link(sid, target, EdgeKind.CAN_PUSH, f"scopes {','.join(scopes)}")

    def _publish_reach(self) -> dict[int, list[str]]:
        reach: dict[int, list[str]] = {}
        for sid in sorted(self.exposed):
            for edge in self.edges.values():
                if edge.src == sid and edge.kind == EdgeKind.CAN_PUBLISH:
                    pid = int(edge.dst.split(":", 1)[1])
                    reach.setdefault(pid, []).append(sid)
        for jid in sorted(self.job_gen):
            job = _as(self.nodes[jid], JobNode)
            reach.setdefault(job.project_id, []).append(jid)
        return reach

    def _find_rogue_versions(self) -> None:
        reach = self._publish_reach()
        for pkg in sorted(
            self.facts.published_packages, key=lambda p: (p.project_id, p.package_id)
        ):
            if not self.ioc.in_window(pkg.created_at) or pkg.project_id not in reach:
                continue
            publisher, reason = self._rogue_publisher(pkg, reach[pkg.project_id])
            if publisher is None:
                continue
            parent_gen = self._generation_of(publisher)
            self._add_version(pkg.name, pkg.version, generation=parent_gen + 1, rogue=True)
            self._place_in_registry(pkg)
            self.link(publisher, package_id(pkg.name, pkg.version), EdgeKind.PUBLISHED, reason)

    def _rogue_publisher(
        self, pkg: PublishedPackageFact, reachable: list[str]
    ) -> tuple[str | None, str]:
        if pkg.published_by and pkg.published_by in self.exposed:
            return pkg.published_by, "audit event: published by an exposed credential"
        infected_pipelines = {
            (n.project_id, n.pipeline_id)
            for jid in self.job_gen
            if isinstance(n := self.nodes[jid], JobNode)
        }
        for pipe in pkg.pipeline_ids:
            if (pkg.project_id, pipe) in infected_pipelines:
                job = next(
                    jid
                    for jid in sorted(self.job_gen)
                    if isinstance(n := self.nodes[jid], JobNode)
                    and (n.project_id, n.pipeline_id) == (pkg.project_id, pipe)
                )
                return job, f"published by pipeline {pipe}, which ran an infected job"
        mismatch = None
        if not pkg.pipeline_ids:
            mismatch = "provenance mismatch: no publishing pipeline"
        elif pkg.commit_exists is False:
            mismatch = f"provenance mismatch: commit {pkg.pipeline_sha} not in repository"
        if mismatch is None:
            return None, ""
        return sorted(reachable)[0], mismatch

    def _generation_of(self, node_id: str) -> int:
        if node_id in self.job_gen:
            return self.job_gen[node_id]
        readers = [
            e.src for e in self.edges.values() if e.dst == node_id and e.kind == EdgeKind.CAN_READ
        ]
        return min((self.job_gen[r] for r in readers if r in self.job_gen), default=0)

    def _hooks_and_agents(self) -> None:
        hooked_projects: set[int] = set()
        for finding in sorted(self.facts.hook_findings, key=lambda h: (h.project_id, h.path)):
            hid = hook_id(finding.project_id, finding.path)
            self.add(
                HookFileNode(
                    id=hid,
                    label=finding.path,
                    project_id=finding.project_id,
                    path=finding.path,
                    hook_kind=finding.hook_kind,
                    commit_sha=finding.commit_sha,
                )
            )
            hooked_projects.add(finding.project_id)
            self.link(hid, self.project_node(finding.project_id), EdgeKind.HOSTED_IN, "repository")
            planters = [
                sid
                for sid in sorted(self.exposed)
                if isinstance(n := self.nodes[sid], SecretNode)
                and n.user_id is not None
                and n.user_id == finding.author_user_id
            ]
            evidence = f"commit {finding.commit_sha} authored by the token's bot user"
            if not planters:
                planters = [
                    e.src
                    for e in self.edges.values()
                    if e.kind == EdgeKind.CAN_PUSH
                    and e.src in self.exposed
                    and e.dst == project_id(finding.project_id)
                ]
                evidence = "exposed credential can push to this repository"
            for planter in sorted(planters):
                self.link(planter, hid, EdgeKind.PLANTED, evidence)
        for session in sorted(self.facts.agent_sessions, key=lambda a: (a.identity, a.project_id)):
            if session.project_id not in hooked_projects:
                continue
            aid = agent_id(session.identity, session.project_id)
            self.add(
                AgentSessionNode(
                    id=aid,
                    label=session.identity,
                    identity=session.identity,
                    user_id=session.user_id,
                    project_id=session.project_id,
                )
            )
            self.link(
                aid, project_id(session.project_id), EdgeKind.OPENED, "agent opened repository"
            )

    def _watchers(self) -> None:
        for finding in sorted(self.facts.watcher_findings, key=lambda w: (w.host, w.unit)):
            hid = host_id(finding.host)
            if hid not in self.nodes:
                continue
            wid = watcher_id(finding.host, finding.unit)
            self.add(
                WatcherNode(
                    id=wid,
                    label=finding.unit,
                    host=finding.host,
                    unit=finding.unit,
                    indicator_path=finding.indicator_path,
                )
            )
            self.link(
                wid, hid, EdgeKind.HOSTED_IN, f"persistence indicator {finding.indicator_path}"
            )
            for secret in sorted(self._secrets_seen_on_host(hid)):
                self.link(
                    wid,
                    secret,
                    EdgeKind.WATCHES,
                    "assumed: a watcher can hold any secret exposed to jobs on its host",
                )

    def _secrets_seen_on_host(self, hid: str) -> set[str]:
        runners = {
            e.src for e in self.edges.values() if e.kind == EdgeKind.RUNS_ON_HOST and e.dst == hid
        }
        jobs = {
            e.src for e in self.edges.values() if e.kind == EdgeKind.RAN_ON and e.dst in runners
        }
        return {e.dst for e in self.edges.values() if e.kind == EdgeKind.CAN_READ and e.src in jobs}

    def _generations(self) -> tuple[Generation, ...]:
        depths = sorted(set(self.version_gen.values()))
        result: list[Generation] = []
        for depth in depths:
            versions = sorted(f"{n}@{v}" for (n, v), g in self.version_gen.items() if g == depth)
            jobs = [j for j, g in self.job_gen.items() if g == depth]
            projects = {n.project_id for j in jobs if isinstance(n := self.nodes[j], JobNode)}
            result.append(
                Generation(
                    depth=depth,
                    versions=tuple(versions),
                    jobs=len(jobs),
                    projects=len(projects),
                )
            )
        return tuple(result)


def _as[T](node: Node, cls: type[T]) -> T:
    if not isinstance(node, cls):
        raise TypeError(f"{node.id} is {node.kind}, expected {cls.__name__}")
    return node


def _variable_readable(var: VariableFact, job: JobFact) -> bool:
    if job.project_id not in var.visible_to_projects:
        return False
    if var.protected and not job.protected_ref:
        return False
    if var.environment_scope == "*":
        return True
    return job.environment is not None and fnmatch.fnmatchcase(
        job.environment, var.environment_scope
    )


def build_exposure_graph(ioc: IOCSet, facts: CollectedFacts) -> ExposureGraph:
    return _Builder(ioc=ioc, facts=facts).run()
