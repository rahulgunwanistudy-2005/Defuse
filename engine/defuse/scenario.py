"""The sandbox scenario: the facts the collectors return after one simulator run.

Shapes mirror the sandbox described in `simulator/README.md`: a human push infects app-a, the
simulator republishes the shared library with no matching commit, app-b installs it, a
SessionStart hook is planted in app-b, and a watcher is installed on the persistent runner.

This is fixture data, not a recorded incident. The console labels anything built from it as a
scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from defuse.model.facts import (
    AccessTokenFact,
    AgentSessionFact,
    CollectedFacts,
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
from defuse.model.ioc import AffectedPackage, HookKind, HookSignature, IOCSet

NAMESPACE = "defuse-sandbox"
T0 = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
APP_A, APP_B, LIB = 101, 102, 103
WEB = "https://gitlab.com/defuse-sandbox"


def scenario_ioc() -> IOCSet:
    return IOCSet(
        id="sandbox-loader-worm",
        title="Self-replicating loader in @defuse-sandbox packages",
        source_urls=("https://isc.sans.edu/diary/33218",),
        packages=(AffectedPackage(name="@defuse-sandbox/loader", versions=("1.0.3",)),),
        persistence_paths=("~/.config/systemd/user/defuse-watcher.service",),
        hook_signatures=(
            HookSignature(kind=HookKind.CLAUDE_SESSION_START, pattern="defuse-sim-loader"),
        ),
        exfil_indicators=("sinkhole.defuse.dev",),
        window_start=T0 - timedelta(hours=1),
    )


def _at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def scenario_facts() -> CollectedFacts:
    return CollectedFacts(
        collected_at=_at(9),
        namespace=NAMESPACE,
        projects=(
            ProjectFact(id=APP_A, path=f"{NAMESPACE}/app-a", web_url=f"{WEB}/app-a"),
            ProjectFact(id=APP_B, path=f"{NAMESPACE}/app-b", web_url=f"{WEB}/app-b"),
            ProjectFact(id=LIB, path=f"{NAMESPACE}/strings", web_url=f"{WEB}/strings"),
        ),
        pipelines=(
            PipelineFact(
                project_id=APP_A,
                id=5001,
                ref="main",
                sha="a1f0c3e",
                created_at=_at(0),
                web_url=f"{WEB}/app-a/-/pipelines/5001",
            ),
            PipelineFact(
                project_id=APP_A,
                id=4990,
                ref="main",
                sha="9be771d",
                created_at=_at(-300),
                web_url=f"{WEB}/app-a/-/pipelines/4990",
            ),
            PipelineFact(
                project_id=APP_B,
                id=5002,
                ref="main",
                sha="77c2a90",
                created_at=_at(5),
                web_url=f"{WEB}/app-b/-/pipelines/5002",
            ),
        ),
        jobs=(
            JobFact(
                project_id=APP_A,
                id=90001,
                pipeline_id=5001,
                name="install",
                ref="main",
                protected_ref=True,
                started_at=_at(0.2),
                finished_at=_at(1.4),
                runner_id=7,
                web_url=f"{WEB}/app-a/-/jobs/90001",
                resolved=(
                    ResolvedDependency(
                        name="@defuse-sandbox/loader",
                        version="1.0.3",
                        source=DependencySource.LOCKFILE,
                        evidence="package-lock.json node_modules/@defuse-sandbox/loader",
                    ),
                ),
            ),
            JobFact(
                project_id=APP_A,
                id=90002,
                pipeline_id=5001,
                name="deploy",
                ref="main",
                protected_ref=True,
                started_at=_at(1.6),
                environment="production",
                runner_id=7,
                web_url=f"{WEB}/app-a/-/jobs/90002",
            ),
            JobFact(
                project_id=APP_A,
                id=89950,
                pipeline_id=4990,
                name="install",
                ref="main",
                protected_ref=True,
                started_at=_at(-300),
                runner_id=7,
                resolved=(
                    ResolvedDependency(
                        name="@defuse-sandbox/loader",
                        version="1.0.2",
                        source=DependencySource.LOCKFILE,
                        evidence="package-lock.json node_modules/@defuse-sandbox/loader",
                    ),
                ),
            ),
            JobFact(
                project_id=APP_B,
                id=90011,
                pipeline_id=5002,
                name="install",
                ref="main",
                protected_ref=True,
                started_at=_at(5.1),
                runner_id=1,
                web_url=f"{WEB}/app-b/-/jobs/90011",
                resolved=(
                    ResolvedDependency(
                        name="@defuse-sandbox/strings",
                        version="2.4.1",
                        source=DependencySource.TRACE,
                        evidence="job trace line 212: + @defuse-sandbox/strings@2.4.1",
                    ),
                ),
            ),
        ),
        runners=(
            RunnerFact(
                id=7,
                description="sandbox-persistent",
                shared=False,
                persistent=True,
                tags=("sandbox-persistent",),
                host="defuse-runner-1",
            ),
            RunnerFact(id=1, description="gitlab-saas-small", shared=True, persistent=False),
        ),
        hosts=(
            HostFact(
                name="defuse-runner-1",
                managed=True,
                zone="us-central1-a",
                network_tags=("runner-live",),
            ),
        ),
        variables=(
            VariableFact(
                owner=f"project/{APP_A}",
                visible_to_projects=(APP_A,),
                key="NPM_PUBLISH_TOKEN",
                holds_token="deploy_token:31",
                masked=True,
            ),
            VariableFact(
                owner=f"project/{APP_A}",
                visible_to_projects=(APP_A,),
                key="GITLAB_PUSH_TOKEN",
                holds_token="project_access_token:41",
                masked=True,
            ),
            VariableFact(
                owner=f"project/{APP_A}",
                visible_to_projects=(APP_A,),
                key="DEPLOY_SSH_KEY",
                environment_scope="production",
                protected=True,
                masked=True,
            ),
            VariableFact(
                owner="group/defuse-sandbox",
                visible_to_projects=(APP_A, APP_B, LIB),
                key="SENTRY_AUTH_TOKEN",
                masked=True,
            ),
            VariableFact(
                owner=f"project/{APP_B}",
                visible_to_projects=(APP_B,),
                key="RELEASE_TOKEN",
                holds_token="project_access_token:42",
                masked=True,
            ),
        ),
        access_tokens=(
            AccessTokenFact(
                project_id=APP_B,
                id=41,
                name="hook-bot",
                scopes=("write_repository",),
                user_id=9041,
            ),
            AccessTokenFact(
                project_id=APP_B,
                id=42,
                name="release-bot",
                scopes=("api",),
                user_id=9042,
            ),
        ),
        deploy_tokens=(
            DeployTokenFact(
                project_id=LIB,
                id=31,
                name="strings-publish",
                username="strings-publish",
                scopes=("read_package_registry", "write_package_registry"),
            ),
        ),
        published_packages=(
            PublishedPackageFact(
                project_id=LIB,
                package_id=3001,
                name="@defuse-sandbox/strings",
                version="2.4.0",
                created_at=_at(-2000),
                pipeline_ids=(4100,),
                pipeline_sha="5e1d0aa",
                commit_exists=True,
            ),
            PublishedPackageFact(
                project_id=LIB,
                package_id=3002,
                name="@defuse-sandbox/strings",
                version="2.4.1",
                created_at=_at(2.1),
                pipeline_ids=(),
                commit_exists=None,
            ),
        ),
        hook_findings=(
            HookFinding(
                project_id=APP_B,
                path=".claude/settings.json",
                hook_kind=HookKind.CLAUDE_SESSION_START,
                signature="defuse-sim-loader",
                commit_sha="c0ffee1",
                author_user_id=9041,
                committed_at=_at(3),
            ),
        ),
        agent_sessions=(
            AgentSessionFact(identity="duo-developer-flow", user_id=9500, project_id=APP_B),
        ),
        watcher_findings=(
            WatcherFinding(
                host="defuse-runner-1",
                unit="defuse-watcher.service",
                indicator_path="~/.config/systemd/user/defuse-watcher.service",
            ),
        ),
    )
