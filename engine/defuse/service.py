"""The incident service: scope, plan, contain and verify, emitting events as it goes.

The hands-off path. A scoped IOC set goes in; a contained, verified incident comes out, with
an event per containment phase and per action so the console timeline is live.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import httpx
import structlog

from defuse.collect.collector import Collector
from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings
from defuse.execute.executors import ExecutionContext, GcpOps
from defuse.execute.gcp import GcloudOps, RecordingGcpOps
from defuse.execute.runner import enrich, run_plan
from defuse.graph.build import build_exposure_graph
from defuse.model.facts import CollectedFacts
from defuse.model.graph import NodeKind
from defuse.model.incident import ActionRecord, Incident, IncidentStatus
from defuse.model.ioc import IOCSet
from defuse.plan.adversary import replay
from defuse.plan.planner import plan_incident, plan_naive
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
    if settings.gcp_project and not settings.seed_scenario:
        return GcloudOps(settings.gcp_project, settings.gcp_zone)
    return RecordingGcpOps({h: [settings.live_tag] for h in set(settings.runner_hosts.values())})


class IncidentService:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._transport = transport

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
        plan = plan_incident(graph)
        naive = plan_naive(graph)
        await self._store.save_scope(incident.id, ioc, graph, plan, naive)
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
        await self._store.upsert_incident(
            incident.model_copy(update={"status": IncidentStatus.CONTAINING})
        )
        await self._store.emit(incident.id, "containment.started", {"dry_run": dry_run})
        gcp = make_gcp_ops(self._settings)
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
            )

            async def sink(record: ActionRecord) -> None:
                await self._store.append_action(record)
                await self._store.emit(
                    incident.id,
                    "action",
                    record.model_dump(mode="json"),
                    f"{record.kind.value} {record.target}: {record.status.value}",
                )

            records = await run_plan(ctx, plan, sink)
        return records

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
    ) -> None:
        verification = await verify_containment(
            ioc,
            before,
            after,
            sinkhole_url=self._settings.sinkhole_url,
            sentinel_intact=sentinel_intact,
            checked_at=checked_at,
        )
        metrics = compute_metrics(incident, records, verification, llm_credits=llm_credits)
        await self._store.save_results(incident.id, metrics, verification)
        final = incident.model_copy(update={"status": next_status(verification)})
        await self._store.upsert_incident(final)
        await self._store.emit(
            incident.id,
            "verified",
            {
                "passed": verification.passed,
                "checks": [c.model_dump(mode="json") for c in verification.checks],
                "metrics": metrics.model_dump(mode="json"),
            },
            f"verification {'passed' if verification.passed else 'did not pass'}",
        )
