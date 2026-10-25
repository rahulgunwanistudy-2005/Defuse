"""Collect facts from GitLab into a CollectedFacts, reading metadata only.

The variable collector requests names, scopes and protection flags. It never requests a value.
`VARIABLE_FIELDS` is the exact GraphQL selection and a test asserts "value" is not in it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from defuse.collect.gitlab import GitLabClient, GitLabError, NotFound
from defuse.collect.lockfile import parse_npm_lockfile, scan_trace
from defuse.config import Settings
from defuse.model.facts import (
    AccessTokenFact,
    CollectedFacts,
    Degradation,
    DependencySource,
    DeployTokenFact,
    HookFinding,
    HostFact,
    JobFact,
    PipelineFact,
    ProjectFact,
    PublishedPackageFact,
    ResolvedDependency,
    RunnerFact,
    VariableFact,
    WatcherFinding,
)
from defuse.model.ioc import HookKind, IOCSet

log = structlog.get_logger(__name__)

VARIABLE_FIELDS = ("key", "variableType", "environmentScope", "protected", "masked", "raw")
HOOK_PATHS = {
    ".claude/settings.json": HookKind.CLAUDE_SESSION_START,
    ".claude/settings.local.json": HookKind.CLAUDE_SESSION_START,
    ".vscode/tasks.json": HookKind.VSCODE_FOLDER_OPEN_TASK,
    "AGENTS.md": HookKind.AGENTS_MD_INSTRUCTION,
}


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Collector:
    def __init__(self, client: GitLabClient, settings: Settings, ioc: IOCSet) -> None:
        self._gl = client
        self._settings = settings
        self._ioc = ioc
        self._degradations: list[Degradation] = []
        self._published: set[tuple[str, str]] = set()

    def _degrade(self, source: str, reason: str, effect: str) -> None:
        self._degradations.append(Degradation(source=source, reason=reason, effect=effect))
        log.warning("collect.degraded", source=source, reason=reason)

    async def collect(self, group: str) -> CollectedFacts:
        projects = await self._projects(group)
        for project in projects:
            self._gl.remember_project(project.id, project.path)
        pipelines_per_project = await asyncio.gather(*(self._pipelines(p.id) for p in projects))
        pipelines = [pl for group_pls in pipelines_per_project for pl in group_pls]
        # Collect packages first: a job that installs a rogue version republished in the window
        # must be linked even though that version is not yet in the IOC set. The trace fallback
        # keeps any version published anywhere in the namespace during the window.
        packages = [
            pkg
            for project_pkgs in await asyncio.gather(*(self._packages(p.id) for p in projects))
            for pkg in project_pkgs
        ]
        self._published = {(p.name, p.version) for p in packages}
        jobs = [
            job
            for project_jobs in await asyncio.gather(
                *(
                    self._jobs(p.id, pls)
                    for p, pls in zip(projects, pipelines_per_project, strict=True)
                )
            )
            for job in project_jobs
        ]
        runners, hosts = await self._runners(projects)
        variables = await self._variables(group, projects)
        tokens = await asyncio.gather(*(self._tokens(p.id) for p in projects))
        access = [t for group_tokens in tokens for t in group_tokens[0]]
        deploy = [t for group_tokens in tokens for t in group_tokens[1]]
        hooks = [
            hook
            for project_hooks in await asyncio.gather(
                *(self._hooks(p.id, p.default_branch) for p in projects)
            )
            for hook in project_hooks
        ]
        watchers = self._watchers(hosts)
        return CollectedFacts(
            collected_at=datetime.now(UTC),
            namespace=group,
            projects=tuple(projects),
            pipelines=tuple(pipelines),
            jobs=tuple(jobs),
            runners=tuple(runners),
            hosts=tuple(hosts),
            variables=tuple(variables),
            access_tokens=tuple(access),
            deploy_tokens=tuple(deploy),
            published_packages=tuple(packages),
            hook_findings=tuple(hooks),
            watcher_findings=tuple(watchers),
            degradations=tuple(self._degradations),
        )

    async def _projects(self, group: str) -> list[ProjectFact]:
        out: list[ProjectFact] = []
        async for item in self._gl.paginate(
            f"/api/v4/groups/{self._gl_encode(group)}/projects",
            {"include_subgroups": "true", "archived": "false"},
        ):
            out.append(
                ProjectFact(
                    id=item["id"],
                    path=item["path_with_namespace"],
                    default_branch=item.get("default_branch") or "main",
                    web_url=item.get("web_url"),
                )
            )
        return out

    async def _pipelines(self, project_id: int) -> list[PipelineFact]:
        out: list[PipelineFact] = []
        params = {"updated_after": self._ioc.window_start.isoformat()}
        async for item in self._gl.paginate(f"/api/v4/projects/{project_id}/pipelines", params):
            created = _dt(item.get("created_at")) or self._ioc.window_start
            out.append(
                PipelineFact(
                    project_id=project_id,
                    id=item["id"],
                    ref=item.get("ref") or "",
                    sha=item.get("sha") or "",
                    created_at=created,
                    source=item.get("source") or "push",
                    web_url=item.get("web_url"),
                )
            )
        return out

    async def _jobs(self, project_id: int, pipelines: list[PipelineFact]) -> list[JobFact]:
        out: list[JobFact] = []
        for pipeline in pipelines:
            async for item in self._gl.paginate(
                f"/api/v4/projects/{project_id}/pipelines/{pipeline.id}/jobs"
            ):
                out.append(await self._job(project_id, pipeline, item))
        return out

    async def _job(self, project_id: int, pipeline: PipelineFact, item: dict[str, Any]) -> JobFact:
        runner = item.get("runner") or {}
        resolved = await self._resolved(project_id, item["id"])
        return JobFact(
            project_id=project_id,
            id=item["id"],
            pipeline_id=pipeline.id,
            name=item.get("name") or "",
            ref=item.get("ref") or pipeline.ref,
            protected_ref=bool(item.get("tag_list") is not None and item.get("protected", False))
            or bool(item.get("protected", False)),
            started_at=_dt(item.get("started_at")) or _dt(item.get("created_at")),
            finished_at=_dt(item.get("finished_at")),
            environment=(item.get("environment") or {}).get("name"),
            runner_id=runner.get("id"),
            web_url=item.get("web_url"),
            resolved=resolved,
        )

    async def _resolved(self, project_id: int, job_id: int) -> tuple[ResolvedDependency, ...]:
        found: dict[tuple[str, str], ResolvedDependency] = {}
        for name in ("package-lock.json", "npm-shrinkwrap.json"):
            try:
                text = await self._gl.get_text(
                    f"/api/v4/projects/{project_id}/jobs/{job_id}/artifacts/{name}",
                    max_bytes=self._settings.trace_max_bytes,
                )
            except NotFound:
                continue
            except GitLabError as exc:
                self._degrade("job_artifact", str(exc), "lockfile not read; relying on trace")
                continue
            for pkg, version, path in parse_npm_lockfile(text):
                found[(pkg, version)] = ResolvedDependency(
                    name=pkg, version=version, source=DependencySource.LOCKFILE, evidence=path
                )
        if not found:
            try:
                trace = await self._gl.get_text(
                    f"/api/v4/projects/{project_id}/jobs/{job_id}/trace",
                    max_bytes=self._settings.trace_max_bytes,
                )
            except GitLabError as exc:
                self._degrade("job_trace", str(exc), f"job {job_id} dependencies unknown")
                return ()
            for pkg, version, line in scan_trace(trace):
                if self._ioc.affected(pkg, version) or (pkg, version) in self._published:
                    found[(pkg, version)] = ResolvedDependency(
                        name=pkg,
                        version=version,
                        source=DependencySource.TRACE,
                        evidence=f"job trace line {line}",
                    )
        return tuple(found.values())

    async def _runners(
        self, projects: list[ProjectFact]
    ) -> tuple[list[RunnerFact], list[HostFact]]:
        runners: dict[int, RunnerFact] = {}
        for project in projects:
            try:
                async for item in self._gl.paginate(f"/api/v4/projects/{project.id}/runners"):
                    rid = item["id"]
                    tags = tuple(item.get("tag_list") or ())
                    host = self._settings.runner_hosts.get(str(rid)) or next(
                        (
                            self._settings.runner_hosts[t]
                            for t in tags
                            if t in self._settings.runner_hosts
                        ),
                        None,
                    )
                    runners[rid] = RunnerFact(
                        id=rid,
                        description=item.get("description") or f"runner {rid}",
                        shared=item.get("is_shared", item.get("runner_type") == "instance_type"),
                        persistent=host is not None,
                        paused=item.get("paused", not item.get("active", True)),
                        tags=tags,
                        host=host,
                    )
            except GitLabError as exc:
                self._degrade("project_runners", str(exc), f"runners for {project.path} unknown")
        hosts = {
            r.host: HostFact(name=r.host, managed=self._settings.gcp_project is not None)
            for r in runners.values()
            if r.host
        }
        return list(runners.values()), list(hosts.values())

    async def _variables(self, group: str, projects: list[ProjectFact]) -> list[VariableFact]:
        out: list[VariableFact] = []
        out.extend(
            await self._variables_for(
                f"group/{group}",
                f"/api/v4/groups/{self._gl_encode(group)}/variables",
                tuple(p.id for p in projects),
            )
        )
        for project in projects:
            out.extend(
                await self._variables_for(
                    f"project/{project.id}",
                    f"/api/v4/projects/{project.id}/variables",
                    (project.id,),
                )
            )
        return out

    async def _variables_for(
        self, owner: str, path: str, visible_to: tuple[int, ...]
    ) -> list[VariableFact]:
        out: list[VariableFact] = []
        try:
            async for item in self._gl.paginate(path):
                key = item["key"]
                out.append(
                    VariableFact(
                        owner=owner,
                        visible_to_projects=visible_to,
                        key=key,
                        environment_scope=item.get("environment_scope") or "*",
                        protected=item.get("protected", False),
                        masked=item.get("masked", False),
                        holds_token=self._settings.token_variables.get(key),
                    )
                )
        except GitLabError as exc:
            self._degrade("variables", str(exc), f"variables for {owner} unknown")
        return out

    async def _tokens(self, project_id: int) -> tuple[list[AccessTokenFact], list[DeployTokenFact]]:
        access: list[AccessTokenFact] = []
        deploy: list[DeployTokenFact] = []
        try:
            async for item in self._gl.paginate(f"/api/v4/projects/{project_id}/access_tokens"):
                access.append(
                    AccessTokenFact(
                        project_id=project_id,
                        id=item["id"],
                        name=item.get("name") or "",
                        scopes=tuple(item.get("scopes") or ()),
                        active=item.get("active", not item.get("revoked", False)),
                        user_id=item.get("user_id"),
                        expires_at=_dt(item.get("expires_at")),
                    )
                )
        except GitLabError as exc:
            self._degrade("access_tokens", str(exc), f"project {project_id} tokens unknown")
        try:
            async for item in self._gl.paginate(f"/api/v4/projects/{project_id}/deploy_tokens"):
                deploy.append(
                    DeployTokenFact(
                        project_id=project_id,
                        id=item["id"],
                        name=item.get("name") or "",
                        username=item.get("username") or "",
                        scopes=tuple(item.get("scopes") or ()),
                        revoked=item.get("revoked", False),
                        expired=item.get("expired", False),
                    )
                )
        except GitLabError as exc:
            self._degrade("deploy_tokens", str(exc), f"project {project_id} deploy tokens unknown")
        return access, deploy

    async def _packages(self, project_id: int) -> list[PublishedPackageFact]:
        out: list[PublishedPackageFact] = []
        try:
            async for item in self._gl.paginate(
                f"/api/v4/projects/{project_id}/packages", {"package_type": "npm"}
            ):
                created = _dt(item.get("created_at"))
                if created is None or not self._ioc.in_window(created):
                    continue
                pipelines = item.get("pipelines") or []
                sha = pipelines[0].get("sha") if pipelines else None
                out.append(
                    PublishedPackageFact(
                        project_id=project_id,
                        package_id=item["id"],
                        name=item.get("name") or "",
                        version=item.get("version") or "",
                        created_at=created,
                        pipeline_ids=tuple(p["id"] for p in pipelines),
                        pipeline_sha=sha,
                        commit_exists=await self._commit_exists(project_id, sha),
                        creator_id=item.get("creator_id"),
                    )
                )
        except GitLabError as exc:
            self._degrade("packages", str(exc), f"project {project_id} packages unknown")
        return out

    async def _commit_exists(self, project_id: int, sha: str | None) -> bool | None:
        if not sha:
            return None
        try:
            await self._gl.get(f"/api/v4/projects/{project_id}/repository/commits/{sha}")
        except NotFound:
            return False
        except GitLabError:
            return None
        return True

    async def _hooks(self, project_id: int, branch: str) -> list[HookFinding]:
        out: list[HookFinding] = []
        for path, kind in HOOK_PATHS.items():
            try:
                text = await self._gl.get_text(
                    f"/api/v4/projects/{project_id}/repository/files/{self._gl_encode(path)}/raw",
                    max_bytes=self._settings.trace_max_bytes,
                    params={"ref": branch},
                )
            except NotFound:
                continue
            except GitLabError as exc:
                self._degrade("repository_files", str(exc), f"{path} in {project_id} not read")
                continue
            signature = self._matched_signature(kind, text)
            if signature is None:
                continue
            commit = await self._last_commit(project_id, path, branch)
            out.append(
                HookFinding(
                    project_id=project_id,
                    path=path,
                    hook_kind=kind,
                    signature=signature,
                    commit_sha=commit[0],
                    author_user_id=commit[1],
                    committed_at=commit[2],
                )
            )
        return out

    def _matched_signature(self, kind: HookKind, text: str) -> str | None:
        for sig in self._ioc.hook_signatures:
            if sig.kind == kind and sig.pattern in text:
                return sig.pattern
        return None

    async def _last_commit(
        self, project_id: int, path: str, branch: str
    ) -> tuple[str | None, int | None, datetime | None]:
        try:
            commits = [
                c
                async for c in self._gl.paginate(
                    f"/api/v4/projects/{project_id}/repository/commits",
                    {"path": path, "ref_name": branch},
                    limit=1,
                )
            ]
        except GitLabError:
            return (None, None, None)
        if not commits:
            return (None, None, None)
        head = commits[0]
        return (head.get("id"), head.get("author_id"), _dt(head.get("committed_date")))

    def _watchers(self, hosts: list[HostFact]) -> list[WatcherFinding]:
        watchers: list[WatcherFinding] = []
        for host in hosts:
            for path in self._ioc.persistence_paths:
                watchers.append(
                    WatcherFinding(
                        host=host.name,
                        unit=path.rsplit("/", 1)[-1],
                        indicator_path=path,
                    )
                )
        return watchers

    @staticmethod
    def _gl_encode(value: str) -> str:
        from defuse.collect.gitlab import encode

        return encode(value)
