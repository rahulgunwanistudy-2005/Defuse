"""Async repository over the store, plus an in-process event bus for SSE."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from defuse.model.graph import ExposureGraph
from defuse.model.incident import ActionRecord, Incident, Metrics, Verification
from defuse.model.ioc import IOCSet
from defuse.model.plan import Plan
from defuse.store.models import ActionRow, Base, EventRow, IncidentRow


class EventBus:
    """Fan-out of (incident_id -> queues) so a live SSE client wakes the moment a row lands."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def publish(self, incident_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(incident_id, ())):
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, incident_id: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[incident_id].add(queue)
        try:
            yield queue
        finally:
            self._subscribers[incident_id].discard(queue)


class Store:
    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url, future=True)
        self._session = async_sessionmaker(self._engine, expire_on_commit=False)
        self.events = EventBus()

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session() as session:
            yield session

    # --- writes --------------------------------------------------------------------------

    async def upsert_incident(self, incident: Incident) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(IncidentRow, incident.id)
            payload = incident.model_dump(mode="json")
            if row is None:
                session.add(_incident_row(incident, payload))
            else:
                row.status = incident.status.value
                row.title = incident.title
                row.data = payload

    async def save_scope(
        self, incident_id: str, ioc: IOCSet, graph: ExposureGraph, plan: Plan, naive: Plan
    ) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(IncidentRow, incident_id)
            if row is None:
                raise KeyError(incident_id)
            row.ioc_set = ioc.model_dump(mode="json")
            row.graph = graph.model_dump(mode="json")
            row.plan = plan.model_dump(mode="json")
            row.naive_plan = naive.model_dump(mode="json")

    async def append_action(self, record: ActionRecord) -> None:
        async with self._session() as session, session.begin():
            session.add(
                ActionRow(
                    incident_id=record.incident_id,
                    action_id=record.action_id,
                    data=record.model_dump(mode="json"),
                )
            )

    async def save_results(
        self, incident_id: str, metrics: Metrics, verification: Verification | None
    ) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(IncidentRow, incident_id)
            if row is None:
                raise KeyError(incident_id)
            row.metrics = metrics.model_dump(mode="json")
            row.verification = verification.model_dump(mode="json") if verification else None

    async def emit(
        self, incident_id: str, kind: str, payload: dict[str, Any], message: str = ""
    ) -> dict[str, Any]:
        at = datetime.now(UTC)
        async with self._session() as session, session.begin():
            row = EventRow(
                incident_id=incident_id, kind=kind, at=at, payload=payload, message=message
            )
            session.add(row)
            await session.flush()
            event = {
                "seq": row.seq,
                "kind": kind,
                "at": at.isoformat(),
                "payload": payload,
                "message": message,
            }
        self.events.publish(incident_id, event)
        return event

    # --- reads ---------------------------------------------------------------------------

    async def list_incidents(self) -> list[dict[str, Any]]:
        async with self._session() as session:
            rows = (
                await session.execute(select(IncidentRow).order_by(IncidentRow.created_at.desc()))
            ).scalars()
            return [
                {**row.data, "status": row.status, "has_plan": row.plan is not None} for row in rows
            ]

    async def get_incident_row(self, incident_id: str) -> IncidentRow | None:
        async with self._session() as session:
            return await session.get(IncidentRow, incident_id)

    async def get_actions(self, incident_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(ActionRow)
                    .where(ActionRow.incident_id == incident_id)
                    .order_by(ActionRow.seq)
                )
            ).scalars()
            return [row.data for row in rows]

    async def get_events(self, incident_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        async with self._session() as session:
            rows = (
                await session.execute(
                    select(EventRow)
                    .where(EventRow.incident_id == incident_id, EventRow.seq > after_seq)
                    .order_by(EventRow.seq)
                )
            ).scalars()
            return [
                {
                    "seq": r.seq,
                    "kind": r.kind,
                    "at": r.at.isoformat(),
                    "payload": r.payload,
                    "message": r.message,
                }
                for r in rows
            ]


def _incident_row(incident: Incident, payload: dict[str, Any]) -> IncidentRow:
    return IncidentRow(
        id=incident.id,
        title=incident.title,
        ioc_id=incident.ioc_id,
        origin=incident.origin.value,
        status=incident.status.value,
        namespace=incident.namespace,
        created_at=incident.created_at,
        detected_at=incident.detected_at,
        data=payload,
    )
