"""The incident service: scope, plan, contain and verify, emitting events as it goes.

The hands-off path. A scoped IOC set goes in; a contained, verified incident comes out, with
an event per containment phase and per action so the console timeline is live.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx
import structlog

from defuse.automate.actions import ActionAutomation
from defuse.automate.broker import CredentialBroker
from defuse.collect.collector import Collector
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings
from defuse.execute.executors import ExecutionContext, GcpOps
from defuse.execute.gcp import GcloudOps, RecordingGcpOps
from defuse.execute.runner import SUCCESS, enrich, run_plan
from defuse.graph.build import build_exposure_graph
from defuse.model.facts import CollectedFacts, Degradation
from defuse.model.graph import (
    HostNode,
    NodeKind,
    PackageVersionNode,
    SecretKind,
    SecretNode,
    WatcherNode,
)
from defuse.model.incident import (
    ActionRecord,
    CheckOutcome,
    Incident,
    IncidentOrigin,
    IncidentStatus,
    RecordStatus,
    StateValue,
    Verification,
    VerificationCheck,
)
from defuse.model.ioc import IOCSet
from defuse.model.plan import ActionKind, action_id
from defuse.plan.adversary import replay
from defuse.plan.planner import plan_incident, plan_naive, replan
from defuse.store.repository import Store
from defuse.verify.verify import compute_metrics, next_status, verify_containment

log = structlog.get_logger(__name__)

GROWTH_ORDER = (
    NodeKind.PACKAGE_VERSION,
    NodeKind.JOB,
    NodeKind.RUNNER,
    NodeKind.HOST,
    NodeKind.SECRET,
    NodeKind.REGISTRY_PACKAGE,
    NodeKind.HOOK_FILE,
    NodeKind.AGENT_SESSION,
    NodeKind.WATCHER,
)


def make_gcp_ops(settings: Settings) -> GcpOps:
    if not settings.seed_scenario:
        if not settings.gcp_project:
            raise ValueError("live containment requires DEFUSE_GCP_PROJECT")
        return GcloudOps(settings.gcp_project, settings.gcp_zone)
    return RecordingGcpOps({h: [settings.live_tag] for h in set(settings.runner_hosts.values())})


class IncidentService:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        gcp: GcpOps | None = None,
        broker: CredentialBroker | None = None,
        facts_provider: Callable[[], Awaitable[CollectedFacts]] | None = None,
        verification_http: httpx.AsyncClient | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._transport = transport
        self._gcp = gcp
        self._broker = broker
        self._facts_provider = facts_provider
        self._verification_http = verification_http

    def gitlab(self, *, dry_run: bool = False) -> GitLabClient:
        return GitLabClient(
            self._settings.gitlab_url,
            self._settings.gitlab_token,
            self._settings.namespaces,
            concurrency=self._settings.concurrency,
            timeout=self._settings.request_timeout,
            dry_run=dry_run,
            transport=self._transport,
        )

    async def collect(self, incident: Incident, ioc: IOCSet) -> CollectedFacts:
        if self._facts_provider is not None:
            return await self._facts_provider()
        async with self.gitlab() as client:
            return await Collector(client, self._settings, ioc).collect(incident.namespace)

    async def scope(self, incident: Incident, ioc: IOCSet, facts: CollectedFacts) -> None:
        await self._store.upsert_incident(incident)
        await self._store.emit(incident.id, "incident.opened", {"status": incident.status.value})
        graph = build_exposure_graph(ioc, facts)
        for kind in GROWTH_ORDER:
            nodes = graph.by_kind(kind)
            if nodes:
                await self._store.emit(
                    incident.id,
                    "graph.grow",
                    {"kind": kind.value, "ids": [n.id for n in nodes]},
                    f"found {len(nodes)} {kind.value.replace('_', ' ')}(s)",
                )
        plan = enrich(plan_incident(graph), ioc, facts)
        naive = plan_naive(graph)
        await self._store.save_scope(incident.id, ioc, graph, plan, naive)
        await self._store.put_artifact(incident.id, "facts.before", facts.model_dump(mode="json"))
        scoped = incident.model_copy(update={"status": IncidentStatus.SCOPED})
        await self._store.upsert_incident(scoped)
        for degradation in facts.degradations:
            await self._store.emit(
                incident.id, "degradation", degradation.model_dump(mode="json"), degradation.effect
            )
        safe = replay(graph, plan).safe
        await self._store.emit(
            incident.id,
            "plan.ready",
            {"layers": [list(layer) for layer in plan.layers], "safe": safe},
            f"{len(plan.actions)} actions in {len(plan.layers)} layers; replay safe={safe}",
        )

    async def contain(
        self,
        incident: Incident,
        ioc: IOCSet,
        facts: CollectedFacts,
        *,
        dry_run: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> list[ActionRecord]:
        graph = build_exposure_graph(ioc, facts)
        plan = enrich(plan_incident(graph), ioc, facts)
        prior = [ActionRecord.model_validate(r) for r in await self._store.get_actions(incident.id)]
        completed = {r.action_id for r in prior if r.status in SUCCESS and not r.dry_run}
        if not dry_run:
            plan = replan(plan, completed)
        if not dry_run:
            await self._store.upsert_incident(
                incident.model_copy(update={"status": IncidentStatus.CONTAINING})
            )
        await self._store.emit(incident.id, "containment.started", {"dry_run": dry_run})
        simulation = incident.origin == IncidentOrigin.SCENARIO
        if simulation and self._transport is None:
            raise ValueError("scenario containment requires an in-memory GitLab transport")
        gcp = (
            RecordingGcpOps()
            if dry_run
            else self._gcp
            or make_gcp_ops(self._settings.model_copy(update={"seed_scenario": simulation}))
        )
        async with self.gitlab(dry_run=dry_run) as client:
            ctx = ExecutionContext(
                incident.id,
                client,
                gcp,
                actor=self._settings.actor,
                dry_run=dry_run,
                isolation_tag=self._settings.isolation_tag,
                live_tag=self._settings.live_tag,
                clock=clock,
                simulation=simulation,
            )
            await self.configure_context(ctx, incident, ioc, facts, prior)

            async def sink(record: ActionRecord) -> None:
                await self._store.append_action(record)
                await self._store.emit(
                    incident.id,
                    "action",
                    record.model_dump(mode="json"),
                    f"{record.kind.value} {record.target}: {record.status.value}",
                )

            async def completed_now() -> set[str]:
                return {
                    r["action_id"]
                    for r in await self._store.get_actions(incident.id)
                    if r["status"] in {s.value for s in SUCCESS} and not r["dry_run"]
                }

            records = await run_plan(
                ctx,
                plan,
                sink,
                claim=lambda aid: self._store.action_lock(incident.id, aid),
                completed=completed_now,
            )
        if not dry_run:
            checked = await self._store.get_artifact(incident.id, "verification.latest")
            after = await self._store.get_artifact(incident.id, "facts.after")
            if checked is not None and after is not None:
                await self.verify(
                    incident,
                    ioc,
                    facts,
                    CollectedFacts.model_validate(after),
                    records,
                    checked_verification=Verification.model_validate(checked),
                )
        if not dry_run and any(r.status == RecordStatus.FAILED for r in records):
            await self._store.upsert_incident(
                incident.model_copy(update={"status": IncidentStatus.FAILED})
            )
        return records

    async def configure_context(
        self,
        ctx: ExecutionContext,
        incident: Incident,
        ioc: IOCSet,
        facts: CollectedFacts,
        prior: list[ActionRecord],
    ) -> None:
        artifacts = await self._store.artifacts(incident.id)
        state = {
            k.removeprefix("state."): v for k, v in artifacts.items() if k.startswith("state.")
        }

        async def checkpoint(key: str, payload: dict[str, StateValue]) -> None:
            await self._store.put_artifact(incident.id, "state." + key, payload)

        async def evaluate() -> Verification:
            after = await self.collect(incident, ioc)
            rebuilds = {
                r.after.get("pipeline")
                for r in automation.prior
                if r.kind == ActionKind.REBUILD_ARTIFACTS and r.status in SUCCESS
            }
            infected = {
                j.project_id
                for j in facts.jobs
                if any(ioc.affected(d.name, d.version) for d in j.resolved)
            }
            # Historic infected jobs remain evidence; verify newly rebuilt pipelines instead.
            jobs = tuple(j for j in after.jobs if j.pipeline_id in rebuilds)
            missing = infected - {j.project_id for j in jobs}
            limitations = (
                *after.degradations,
                *(
                    Degradation(
                        source="rebuild",
                        reason="missing",
                        effect=f"no successful post-containment job observed for project {pid}",
                    )
                    for pid in sorted(missing)
                ),
            )
            after = after.model_copy(update={"jobs": jobs, "degradations": limitations})
            intact: bool | None = None
            graph = build_exposure_graph(ioc, facts)
            hosts = [n for n in graph.nodes if isinstance(n, HostNode) and n.managed]
            if hosts:
                from shlex import quote

                outcomes = [
                    await ctx.gcp.run_command(
                        h.name,
                        f"if test -d {quote(self._settings.sentinel_path)}; "
                        "then printf intact; else printf missing; fi",
                    )
                    for h in hosts
                ]
                intact = all(o.strip() == "intact" for o in outcomes)
            base = await verify_containment(
                ioc,
                facts,
                after,
                sinkhole_url=self._settings.sinkhole_url,
                sentinel_intact=intact,
                sinkhole_window=self._settings.verification_window,
                http=self._verification_http,
                checked_at=ctx.clock(),
            )
            from shlex import quote

            watchers = [n for n in graph.nodes if isinstance(n, WatcherNode)]
            running = [
                await ctx.gcp.run_command(
                    w.host, f"systemctl --user is-active -- {quote(w.unit)} || true"
                )
                for w in watchers
            ]
            versions = {
                (n.name, n.version)
                for n in graph.nodes
                if isinstance(n, PackageVersionNode) and n.registry_project_id is not None
            }
            remaining = [p for p in after.published_packages if (p.name, p.version) in versions]
            tokens = [n for n in graph.nodes if isinstance(n, SecretNode) and n.rotatable]
            active = [
                n
                for n in tokens
                if (
                    (
                        n.secret_kind == SecretKind.PROJECT_ACCESS_TOKEN
                        and any(
                            t.id == n.token_id and t.project_id == n.project_id and t.active
                            for t in after.access_tokens
                        )
                    )
                    or (
                        n.secret_kind == SecretKind.DEPLOY_TOKEN
                        and any(
                            t.id == n.token_id
                            and t.project_id == n.project_id
                            and not t.revoked
                            and not t.expired
                            for t in after.deploy_tokens
                        )
                    )
                )
            ]
            isolated = [await ctx.gcp.host_network_tags(h.name) for h in hosts]
            from defuse.automate.repository import RepositoryChanges
            from defuse.collect.lockfile import parse_npm_lockfile

            repo = RepositoryChanges(ctx.gl)
            dirty_locks = []
            for project in sorted({j.project_id for j in facts.jobs if j.resolved}):
                metadata = await ctx.gl.get(f"/api/v4/projects/{project}")
                lock = await repo.read(
                    project, "package-lock.json", str(metadata.get("default_branch") or "main")
                )
                if lock is None or any(
                    ioc.affected(n, v) or (n, v) in versions for n, v, _ in parse_npm_lockfile(lock)
                ):
                    dirty_locks.append(project)
            required = {
                a.id
                for a in plan_incident(graph).actions
                if a.kind not in {ActionKind.VERIFY_CLEAN, ActionKind.RESTORE_AGENT_IDENTITY}
            }
            done = {r.action_id for r in automation.prior if r.status in SUCCESS and not r.dry_run}
            checks = (
                *base.checks,
                VerificationCheck(
                    id="quarantined_versions_absent",
                    outcome=CheckOutcome.FAILED if remaining else CheckOutcome.PASSED,
                    detail=f"{len(remaining)} quarantined version(s) still published",
                ),
                VerificationCheck(
                    id="old_credentials_revoked",
                    outcome=CheckOutcome.FAILED if active else CheckOutcome.PASSED,
                    detail=f"{len(active)} old exposed identities remain active",
                ),
                VerificationCheck(
                    id="hosts_isolated",
                    outcome=CheckOutcome.PASSED
                    if all(
                        self._settings.isolation_tag in tags and self._settings.live_tag not in tags
                        for tags in isolated
                    )
                    else CheckOutcome.FAILED,
                    detail="host isolation re-read from provider",
                ),
                VerificationCheck(
                    id="source_locks_clean",
                    outcome=CheckOutcome.FAILED if dirty_locks else CheckOutcome.PASSED,
                    detail=f"{len(dirty_locks)} affected or missing source lockfile(s)",
                ),
                VerificationCheck(
                    id="hooks_removed",
                    outcome=CheckOutcome.FAILED if after.hook_findings else CheckOutcome.PASSED,
                    detail=f"{len(after.hook_findings)} planted hook(s) remain",
                ),
                VerificationCheck(
                    id="secrets_rotated",
                    outcome=CheckOutcome.PASSED if required <= done else CheckOutcome.UNVERIFIED,
                    detail=f"{len(required - done)} unfinished containment actions",
                ),
                VerificationCheck(
                    id="watchers_stopped",
                    outcome=CheckOutcome.PASSED
                    if all(o.strip() == "inactive" for o in running)
                    else CheckOutcome.FAILED,
                    detail="watcher service state checked on every affected host",
                ),
            )
            result = base.model_copy(update={"checks": checks})
            await self._store.put_artifact(
                incident.id, "facts.after", after.model_dump(mode="json")
            )
            await self._store.put_artifact(
                incident.id, "verification.latest", result.model_dump(mode="json")
            )
            return result

        broker = self._broker
        if broker is None and self._settings.credential_broker_url:
            broker = CredentialBroker(
                self._settings.credential_broker_url, self._settings.credential_broker_token
            )
        automation = ActionAutomation(
            ctx,
            self._settings,
            ioc,
            build_exposure_graph(ioc, facts),
            prior,
            broker=broker,
            verify=evaluate,
            checkpoint=checkpoint,
            state=state,
            namespace=incident.namespace,
            facts=facts,
        )
        ctx.automation = automation

    async def verify(
        self,
        incident: Incident,
        ioc: IOCSet,
        before: CollectedFacts,
        after: CollectedFacts,
        records: list[ActionRecord],
        *,
        sentinel_intact: bool | None = None,
        llm_credits: float | None = None,
        checked_at: datetime | None = None,
        checked_verification: Verification | None = None,
    ) -> None:
        verification = checked_verification or await verify_containment(
            ioc,
            before,
            after,
            sinkhole_url=self._settings.sinkhole_url,
            sentinel_intact=sentinel_intact,
            checked_at=checked_at,
        )
        expected = {
            a.id
            for a in plan_incident(build_exposure_graph(ioc, before)).actions
            if a.kind != ActionKind.VERIFY_CLEAN
        }
        ledger = [
            ActionRecord.model_validate(r) for r in await self._store.get_actions(incident.id)
        ]
        latest: dict[str, ActionRecord] = {}
        for record in (*ledger, *records):
            if record.dry_run:
                continue
            previous = latest.get(record.action_id)
            if previous is None or previous.status not in SUCCESS:
                latest[record.action_id] = record
        effective = list(latest.values())
        succeeded = {r.action_id for r in effective if r.status in SUCCESS and not r.dry_run}
        unfinished = sorted(expected - succeeded)
        checks = (
            *(c for c in verification.checks if c.id not in {"hooks_removed", "secrets_rotated"}),
            VerificationCheck(
                id="hooks_removed",
                outcome=CheckOutcome.FAILED if after.hook_findings else CheckOutcome.PASSED,
                detail=f"{len(after.hook_findings)} planted hook(s) remain",
            ),
            VerificationCheck(
                id="secrets_rotated",
                outcome=CheckOutcome.UNVERIFIED if unfinished else CheckOutcome.PASSED,
                detail=(
                    f"unfinished actions: {', '.join(unfinished)}"
                    if unfinished
                    else "all containment actions completed"
                ),
            ),
        )
        verification = verification.model_copy(update={"checks": checks})
        if verification.passed and not any(
            r.kind == ActionKind.VERIFY_CLEAN and r.status in SUCCESS for r in effective
        ):
            verified = ActionRecord(
                incident_id=incident.id,
                action_id=action_id(ActionKind.VERIFY_CLEAN, "incident"),
                kind=ActionKind.VERIFY_CLEAN,
                target="incident",
                actor=self._settings.actor,
                status=RecordStatus.APPLIED,
                dry_run=False,
                detail="all post-containment checks passed",
                started_at=verification.checked_at,
                finished_at=verification.checked_at,
            )
            await self._store.append_action(verified)
            effective = [r for r in effective if r.kind != ActionKind.VERIFY_CLEAN]
            effective.append(verified)
        metrics = compute_metrics(incident, effective, verification, llm_credits=llm_credits)
        await self._store.save_results(incident.id, metrics, verification)
        status = next_status(verification)
        if any(r.status == RecordStatus.FAILED for r in effective):
            status = IncidentStatus.FAILED
        elif unfinished and status != IncidentStatus.FAILED:
            status = IncidentStatus.CONTAINING
        final = incident.model_copy(update={"status": status})
        await self._store.upsert_incident(final)
        await self._store.emit(
            incident.id,
            "verification.completed",
            {
                "passed": verification.passed,
                "checks": [c.model_dump(mode="json") for c in verification.checks],
                "metrics": metrics.model_dump(mode="json"),
            },
            f"verification {'passed' if verification.passed else 'did not pass'}",
        )
