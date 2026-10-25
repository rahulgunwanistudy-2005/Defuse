"""Hypothesis strategies that generate random but well-formed collected facts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import strategies as st

from defuse.model.facts import (
    AccessTokenFact,
    AgentSessionFact,
    CollectedFacts,
    DependencySource,
    DeployTokenFact,
    HookFinding,
    HostFact,
    JobFact,
    ProjectFact,
    PublishedPackageFact,
    ResolvedDependency,
    RunnerFact,
    VariableFact,
    WatcherFinding,
)
from defuse.model.ioc import AffectedPackage, HookKind, IOCSet

T0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
SEED_PKG = "worm-seed"
LIB_PKGS = ("lib-a", "lib-b", "lib-c")

IOC = IOCSet(
    id="property-ioc",
    title="generated",
    packages=(AffectedPackage(name=SEED_PKG, versions=("1.0.1",)),),
    window_start=T0,
)

PAT_SCOPES = st.sampled_from(
    [("api",), ("write_repository",), ("read_api",), ("read_repository", "write_repository")]
)
DEPLOY_SCOPES = st.sampled_from(
    [("write_package_registry",), ("read_package_registry",), ("write_repository",)]
)


@st.composite
def collected_facts(
    draw: st.DrawFn, *, allow_unmanaged: bool = True, force_watched: bool = False
) -> CollectedFacts:
    n_projects = draw(st.integers(1, 5))
    projects = tuple(ProjectFact(id=100 + i, path=f"sbx/p{i}") for i in range(n_projects))
    pids = [p.id for p in projects]

    n_hosts = draw(st.integers(0, 3))
    hosts = tuple(
        HostFact(name=f"h{i}", managed=draw(st.booleans()) if allow_unmanaged else True)
        for i in range(n_hosts)
    )
    runners: list[RunnerFact] = [
        RunnerFact(id=1, description="shared", shared=True, persistent=False)
    ]
    for i in range(draw(st.integers(0, 3))):
        host = draw(st.sampled_from([h.name for h in hosts])) if hosts else None
        runners.append(
            RunnerFact(id=10 + i, description=f"r{i}", shared=False, persistent=True, host=host)
        )

    pats = tuple(
        AccessTokenFact(
            project_id=draw(st.sampled_from(pids)),
            id=40 + i,
            name=f"pat{i}",
            scopes=draw(PAT_SCOPES),
            user_id=9000 + i,
        )
        for i in range(draw(st.integers(0, 3)))
    )
    deploys = tuple(
        DeployTokenFact(
            project_id=draw(st.sampled_from(pids)),
            id=30 + i,
            name=draw(st.sampled_from(["gitlab-deploy-token", f"dt{i}"])),
            username=f"dt{i}",
            scopes=draw(DEPLOY_SCOPES),
        )
        for i in range(draw(st.integers(0, 2)))
    )
    token_refs = [f"project_access_token:{t.id}" for t in pats]
    token_refs += [f"deploy_token:{t.id}" for t in deploys]

    variables = tuple(
        VariableFact(
            owner=f"project/{pid}",
            visible_to_projects=(pid,),
            key=draw(st.sampled_from(["NPM_TOKEN", "GH_TOKEN", "SENTRY", "DB_URL", "PUSH_KEY"]))
            + f"_{i}",
            environment_scope=draw(st.sampled_from(["*", "*", "production"])),
            protected=draw(st.booleans()),
            holds_token=draw(st.sampled_from([None, *token_refs])),
        )
        for i, pid in enumerate(draw(st.lists(st.sampled_from(pids), max_size=6)))
    )

    versions = [(SEED_PKG, "1.0.1"), (SEED_PKG, "1.0.0")] + [(p, "2.0.1") for p in LIB_PKGS]
    jobs: list[JobFact] = []
    for i in range(draw(st.integers(1, 12))):
        deps = draw(st.lists(st.sampled_from(versions), max_size=2, unique=True))
        jobs.append(
            JobFact(
                project_id=draw(st.sampled_from(pids)),
                id=1000 + i,
                pipeline_id=500 + draw(st.integers(0, 5)),
                name="install",
                ref="main",
                protected_ref=draw(st.booleans()),
                environment=draw(st.sampled_from([None, "production"])),
                started_at=T0 + timedelta(minutes=draw(st.integers(-30, 120))),
                runner_id=draw(st.sampled_from([r.id for r in runners])),
                resolved=tuple(
                    ResolvedDependency(
                        name=n, version=v, source=DependencySource.LOCKFILE, evidence="lockfile"
                    )
                    for n, v in deps
                ),
            )
        )

    packages = tuple(
        PublishedPackageFact(
            project_id=draw(st.sampled_from(pids)),
            package_id=3000 + i,
            name=name,
            version="2.0.1",
            created_at=T0 + timedelta(minutes=draw(st.integers(-10, 60))),
            pipeline_ids=draw(st.sampled_from([(), (500,), (501,), (999,)])),
            commit_exists=draw(st.sampled_from([None, True, False])),
        )
        for i, name in enumerate(LIB_PKGS)
        if draw(st.booleans())
    )

    hooks = tuple(
        HookFinding(
            project_id=pid,
            path=".claude/settings.json",
            hook_kind=HookKind.CLAUDE_SESSION_START,
            signature="sig",
            author_user_id=draw(st.sampled_from([None, *[t.user_id for t in pats]])),
        )
        for pid in draw(st.lists(st.sampled_from(pids), max_size=2, unique=True))
    )
    agents = tuple(
        AgentSessionFact(identity=f"agent{i}", project_id=pid)
        for i, pid in enumerate(draw(st.lists(st.sampled_from(pids), max_size=2, unique=True)))
    )
    watchers = tuple(
        WatcherFinding(host=h.name, unit="w.service", indicator_path="~/.config/w.service")
        for h in hosts
        if draw(st.booleans())
    )
    if force_watched:
        pid = pids[0]
        hosts = (
            *hosts,
            HostFact(name="hw", managed=draw(st.booleans()) if allow_unmanaged else True),
        )
        runners.append(
            RunnerFact(id=99, description="rw", shared=False, persistent=True, host="hw")
        )
        pats = (*pats, AccessTokenFact(project_id=pid, id=99, name="patw", scopes=draw(PAT_SCOPES)))
        variables = (
            *variables,
            VariableFact(
                owner=f"project/{pid}",
                visible_to_projects=(pid,),
                key="WATCHED",
                holds_token="project_access_token:99",
            ),
        )
        jobs.append(
            JobFact(
                project_id=pid,
                id=1999,
                pipeline_id=599,
                name="install",
                ref="main",
                protected_ref=False,
                started_at=T0 + timedelta(minutes=1),
                runner_id=99,
                resolved=(
                    ResolvedDependency(
                        name=SEED_PKG, version="1.0.1", source=DependencySource.TRACE, evidence="t"
                    ),
                ),
            )
        )
        watchers = (*watchers, WatcherFinding(host="hw", unit="w.service", indicator_path="~/w"))
    return CollectedFacts(
        collected_at=T0 + timedelta(hours=3),
        namespace="sbx",
        projects=projects,
        jobs=tuple(jobs),
        runners=tuple(runners),
        hosts=hosts,
        variables=variables,
        access_tokens=pats,
        deploy_tokens=deploys,
        published_packages=packages,
        hook_findings=hooks,
        agent_sessions=agents,
        watcher_findings=watchers,
    )
