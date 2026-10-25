from datetime import timedelta

from defuse.graph import build_exposure_graph
from defuse.model.facts import (
    CollectedFacts,
    DependencySource,
    JobFact,
    ResolvedDependency,
    VariableFact,
)
from defuse.model.graph import (
    EdgeKind,
    ExposureGraph,
    JobNode,
    NodeKind,
    PackageVersionNode,
    SecretNode,
)
from defuse.scenario import APP_A, APP_B, T0, scenario_facts, scenario_ioc


def _graph(facts: CollectedFacts | None = None) -> ExposureGraph:
    return build_exposure_graph(scenario_ioc(), facts or scenario_facts())


def test_scenario_reproduces_the_full_infection() -> None:
    graph = _graph()
    versions = {n.id: n for n in graph.by_kind(NodeKind.PACKAGE_VERSION)}
    seed = versions["pkg:@defuse-sandbox/loader@1.0.3"]
    rogue = versions["pkg:@defuse-sandbox/strings@2.4.1"]
    assert isinstance(seed, PackageVersionNode)
    assert isinstance(rogue, PackageVersionNode)
    assert (seed.generation, seed.rogue) == (0, False)
    assert (rogue.generation, rogue.rogue, rogue.registry_project_id) == (1, True, 103)
    assert {n.id for n in graph.by_kind(NodeKind.JOB)} == {"job:101:90001", "job:102:90011"}
    assert graph.has("hook:102:.claude/settings.json")
    assert graph.has("watcher:defuse-runner-1:defuse-watcher.service")
    assert [g.depth for g in graph.generations] == [0, 1]


def test_clean_and_out_of_window_jobs_are_excluded() -> None:
    graph = _graph()
    assert not graph.has("job:101:89950")
    assert not graph.has("job:101:90002")


def test_protected_and_environment_scoped_variables_are_not_readable() -> None:
    graph = _graph()
    readable = {e.dst for e in graph.out("job:101:90001", EdgeKind.CAN_READ)}
    assert "secret:ci_variable:project/101:DEPLOY_SSH_KEY" not in readable
    assert "secret:deploy_token:project/103:31" in readable
    assert "secret:ci_variable:group/defuse-sandbox:SENTRY_AUTH_TOKEN" in readable


def test_variables_holding_tokens_become_token_nodes_with_carriers() -> None:
    node = _graph().node("secret:deploy_token:project/103:31")
    assert isinstance(node, SecretNode)
    assert node.carriers == ("project/101:NPM_PUBLISH_TOKEN",)
    assert node.publish_capable
    assert not node.source_capable


def test_provenance_mismatch_records_the_publisher() -> None:
    graph = _graph()
    published = graph.into("pkg:@defuse-sandbox/strings@2.4.1", EdgeKind.PUBLISHED)
    assert [e.src for e in published] == ["secret:deploy_token:project/103:31"]
    assert "no publishing pipeline" in published[0].evidence


def test_hook_planter_is_matched_by_bot_user() -> None:
    planted = _graph().into("hook:102:.claude/settings.json", EdgeKind.PLANTED)
    assert [e.src for e in planted] == ["secret:project_access_token:project/102:41"]


def test_watcher_conservatively_watches_every_secret_on_its_host() -> None:
    watched = {
        e.dst
        for e in _graph().out("watcher:defuse-runner-1:defuse-watcher.service", EdgeKind.WATCHES)
    }
    assert watched == {
        "secret:ci_variable:group/defuse-sandbox:SENTRY_AUTH_TOKEN",
        "secret:deploy_token:project/103:31",
        "secret:project_access_token:project/102:41",
    }


def test_canonical_json_is_byte_identical_and_order_independent() -> None:
    facts = scenario_facts()
    shuffled = facts.model_copy(
        update={
            "jobs": tuple(reversed(facts.jobs)),
            "variables": tuple(reversed(facts.variables)),
            "published_packages": tuple(reversed(facts.published_packages)),
        }
    )
    assert _graph(facts).canonical_json() == _graph(shuffled).canonical_json()


def test_infection_through_job_published_package_recurses() -> None:
    facts = scenario_facts()
    third = JobFact(
        project_id=APP_A,
        id=90100,
        pipeline_id=5100,
        name="install",
        ref="feature",
        protected_ref=False,
        started_at=T0 + timedelta(minutes=20),
        resolved=(
            ResolvedDependency(
                name="@defuse-sandbox/strings",
                version="2.4.1",
                source=DependencySource.LOCKFILE,
                evidence="package-lock.json",
            ),
        ),
    )
    graph = _graph(facts.model_copy(update={"jobs": (*facts.jobs, third)}))
    job = graph.node("job:101:90100")
    assert isinstance(job, JobNode)
    readable = {e.dst for e in graph.out(job.id, EdgeKind.CAN_READ)}
    assert "secret:ci_variable:group/defuse-sandbox:SENTRY_AUTH_TOKEN" in readable


def test_environment_wildcard_scope() -> None:
    facts = scenario_facts()
    var = VariableFact(
        owner=f"project/{APP_B}",
        visible_to_projects=(APP_B,),
        key="REVIEW_TOKEN",
        environment_scope="review/*",
    )
    job = facts.jobs[3].model_copy(update={"environment": "review/feature-1"})
    graph = _graph(
        facts.model_copy(
            update={"variables": (*facts.variables, var), "jobs": (*facts.jobs[:3], job)}
        )
    )
    readable = {e.dst for e in graph.out("job:102:90011", EdgeKind.CAN_READ)}
    assert "secret:ci_variable:project/102:REVIEW_TOKEN" in readable


def test_no_affected_versions_gives_an_empty_graph() -> None:
    facts = scenario_facts()
    clean = facts.model_copy(update={"jobs": (facts.jobs[2],), "published_packages": ()})
    graph = _graph(clean)
    assert graph.by_kind(NodeKind.JOB) == []
    assert graph.generations == ()
