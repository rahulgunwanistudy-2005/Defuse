"""Seed a browsable scenario incident so the live console works without a GitLab sandbox.

Everything it stores is derived from the deterministic scenario and the dry-run executors,
so the metrics are real timings of the dry run, clearly labelled as a scenario in the UI.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import structlog

from defuse.config import Settings
from defuse.model.incident import Incident, IncidentOrigin, IncidentStatus
from defuse.scenario import NAMESPACE, T0, scenario_cleaned_facts, scenario_facts, scenario_ioc
from defuse.service import IncidentService
from defuse.store.repository import Store

log = structlog.get_logger(__name__)

SCENARIO_ID = "scenario-sandbox"


def _advancing(start: datetime, step: float = 3.5) -> Callable[[], datetime]:
    state = {"t": start}

    def clock() -> datetime:
        state["t"] = state["t"] + timedelta(seconds=step)
        return state["t"]

    return clock


async def seed_scenario(store: Store, settings: Settings) -> None:
    if await store.get_incident_row(SCENARIO_ID) is not None:
        return
    from defuse.collect.memory_backend import MemoryGitLab

    ioc = scenario_ioc()
    facts = scenario_facts()
    backend = MemoryGitLab()
    detected = T0 + timedelta(minutes=6)
    incident = Incident(
        id=SCENARIO_ID,
        title="Scenario: self-replicating loader in @defuse-sandbox",
        ioc_id=ioc.id,
        origin=IncidentOrigin.SCENARIO,
        status=IncidentStatus.OPEN,
        namespace=NAMESPACE,
        created_at=detected + timedelta(seconds=40),
        detected_at=detected,
        first_exposure_at=T0,
        work_item_url="https://gitlab.com/defuse-sandbox/incidents/-/issues/1",
    )
    seed_settings = settings.model_copy(
        update={
            "seed_scenario": True,
            "sandbox_namespaces": NAMESPACE,
            "runner_hosts": {"7": "defuse-runner-1"},
        }
    )
    service = IncidentService(store, seed_settings, transport=backend.transport())
    await service.scope(incident, ioc, facts)
    clock = _advancing(detected + timedelta(seconds=40))
    records = await service.contain(incident, ioc, facts, dry_run=False, clock=clock)
    await service.verify(
        incident,
        ioc.model_copy(update={"window_end": clock()}),
        facts,
        scenario_cleaned_facts(),
        records,
        sentinel_intact=True,
        llm_credits=3.0,
        checked_at=clock(),
    )
    log.info("seed.scenario_ready", incident=SCENARIO_ID, actions=len(records))
