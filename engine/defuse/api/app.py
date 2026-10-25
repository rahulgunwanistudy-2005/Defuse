"""FastAPI app: REST for incidents, graph, plan, explain, metrics; SSE per incident."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from defuse.config import Settings, get_settings
from defuse.model.graph import ExposureGraph
from defuse.model.plan import Plan
from defuse.plan.planner import explain
from defuse.store.models import IncidentRow
from defuse.store.repository import Store

log = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = Store(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await store.create_all()
        if settings.seed_scenario:
            from defuse.api.seed import seed_scenario

            await seed_scenario(store, settings)
        yield
        await store.dispose()

    app = FastAPI(
        title="Defuse",
        version="0.1.0",
        summary="Worm containment for GitLab CI",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.store = store

    def get_store() -> Store:
        return store

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/incidents")
    async def list_incidents(store: Store = Depends(get_store)) -> list[dict[str, Any]]:
        return await store.list_incidents()

    async def _row(store: Store, incident_id: str) -> IncidentRow:
        row = await store.get_incident_row(incident_id)
        if row is None:
            raise HTTPException(404, f"no incident {incident_id}")
        return row

    @app.get("/api/incidents/{incident_id}")
    async def get_incident(incident_id: str, store: Store = Depends(get_store)) -> dict[str, Any]:
        row = await _row(store, incident_id)
        return {
            **row.data,
            "status": row.status,
            "ioc": row.ioc_set,
            "metrics": row.metrics,
            "verification": row.verification,
        }

    @app.get("/api/incidents/{incident_id}/graph")
    async def get_graph(incident_id: str, store: Store = Depends(get_store)) -> dict[str, Any]:
        row = await _row(store, incident_id)
        if row.graph is None:
            raise HTTPException(409, "incident not scoped yet")
        return row.graph

    @app.get("/api/incidents/{incident_id}/plan")
    async def get_plan(
        incident_id: str, strategy: str = "defuse", store: Store = Depends(get_store)
    ) -> dict[str, Any]:
        row = await _row(store, incident_id)
        plan = row.naive_plan if strategy == "naive" else row.plan
        if plan is None:
            raise HTTPException(409, "incident not planned yet")
        return plan

    @app.get("/api/incidents/{incident_id}/plan/explain/{action_id:path}")
    async def explain_action(
        incident_id: str, action_id: str, store: Store = Depends(get_store)
    ) -> dict[str, Any]:
        row = await _row(store, incident_id)
        if row.plan is None:
            raise HTTPException(409, "incident not planned yet")
        plan = Plan.model_validate(row.plan)
        try:
            return explain(plan, action_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(404, f"no action {action_id}") from exc

    @app.get("/api/incidents/{incident_id}/replay")
    async def get_replay(incident_id: str, store: Store = Depends(get_store)) -> dict[str, Any]:
        from defuse.model.ioc import IOCSet
        from defuse.plan.adversary import replay as run_replay

        row = await _row(store, incident_id)
        if not (row.graph and row.plan and row.naive_plan and row.ioc_set):
            raise HTTPException(409, "incident not planned yet")
        graph = ExposureGraph.model_validate(row.graph)
        IOCSet.model_validate(row.ioc_set)

        def _dump(plan_json: dict[str, Any]) -> dict[str, Any]:
            result = run_replay(graph, Plan.model_validate(plan_json))
            return {**result.model_dump(mode="json"), "safe": result.safe}

        return {"defuse": _dump(row.plan), "naive": _dump(row.naive_plan)}

    @app.get("/api/incidents/{incident_id}/actions")
    async def get_actions(
        incident_id: str, store: Store = Depends(get_store)
    ) -> list[dict[str, Any]]:
        await _row(store, incident_id)
        return await store.get_actions(incident_id)

    @app.get("/api/incidents/{incident_id}/metrics")
    async def get_metrics(incident_id: str, store: Store = Depends(get_store)) -> dict[str, Any]:
        row = await _row(store, incident_id)
        return row.metrics or {}

    @app.get("/api/incidents/{incident_id}/events")
    async def stream_events(
        incident_id: str,
        request: Request,
        store: Store = Depends(get_store),
        once: bool = False,
        last_event_id: int = 0,
    ) -> StreamingResponse:
        await _row(store, incident_id)

        async def gen() -> AsyncIterator[bytes]:
            async with store.events.subscribe(incident_id) as queue:
                for event in await store.get_events(incident_id, after_seq=last_event_id):
                    yield _sse(event)
                if once:
                    # Deliver the backlog and close. Clients that want live updates omit
                    # `once` and the stream stays open, pushing each new event.
                    return
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield b": keep-alive\n\n"
                        continue
                    yield _sse(event)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _sse(event: dict[str, Any]) -> bytes:
    return f"id: {event['seq']}\nevent: {event['kind']}\ndata: {json.dumps(event)}\n\n".encode()
