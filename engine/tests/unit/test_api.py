from __future__ import annotations

import asyncio

import httpx
import pytest
from asgi_lifespan import LifespanManager

from defuse.api.app import create_app
from defuse.api.seed import SCENARIO_ID
from defuse.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db", seed_scenario=True)


@pytest.fixture
async def client(settings):  # type: ignore[no-untyped-def]
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c


async def test_healthz(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/healthz")).json() == {"status": "ok"}


async def test_scenario_incident_is_browsable(client) -> None:  # type: ignore[no-untyped-def]
    listing = (await client.get("/api/incidents")).json()
    assert any(i["id"] == SCENARIO_ID for i in listing)
    incident = (await client.get(f"/api/incidents/{SCENARIO_ID}")).json()
    assert incident["status"] == "verified"
    assert incident["metrics"]["time_to_containment"] > 0
    assert incident["ioc"]["id"] == "sandbox-loader-worm"


async def test_graph_plan_and_explain(client) -> None:  # type: ignore[no-untyped-def]
    graph = (await client.get(f"/api/incidents/{SCENARIO_ID}/graph")).json()
    assert graph["ioc_id"] == "sandbox-loader-worm"
    plan = (await client.get(f"/api/incidents/{SCENARIO_ID}/plan")).json()
    assert plan["strategy"] == "defuse"
    naive = (await client.get(f"/api/incidents/{SCENARIO_ID}/plan?strategy=naive")).json()
    assert naive["strategy"] == "naive"
    action = "revoke_secret@secret:deploy_token:project/103:31"
    explained = (await client.get(f"/api/incidents/{SCENARIO_ID}/plan/explain/{action}")).json()
    assert "C1" in {c["id"] for c in explained["constraints"]}


async def test_replay_shows_the_divergence(client) -> None:  # type: ignore[no-untyped-def]
    replay = (await client.get(f"/api/incidents/{SCENARIO_ID}/replay")).json()
    assert replay["defuse"]["safe"] is True
    assert replay["naive"]["safe"] is False
    assert replay["naive"]["hosts_lost"]


async def test_actions_and_metrics(client) -> None:  # type: ignore[no-untyped-def]
    actions = (await client.get(f"/api/incidents/{SCENARIO_ID}/actions")).json()
    assert len(actions) >= 20
    metrics = (await client.get(f"/api/incidents/{SCENARIO_ID}/metrics")).json()
    assert metrics["actions_executed"] >= 1


async def test_sse_once_streams_the_backlog_then_closes(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get(f"/api/incidents/{SCENARIO_ID}/events?once=true")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        line.split(":", 1)[1].strip()
        for line in response.text.splitlines()
        if line.startswith("event:")
    ]
    assert events[0] == "incident.opened"
    assert "graph.grow" in events
    assert "verified" in events


async def test_event_bus_fans_out_live_events() -> None:
    from defuse.store.repository import EventBus

    bus = EventBus()
    async with bus.subscribe("inc") as queue:
        bus.publish("inc", {"seq": 1, "kind": "note"})
        bus.publish("other", {"seq": 2, "kind": "ignored"})
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["kind"] == "note"
    assert queue.empty()


async def test_missing_incident_is_404(client) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/incidents/nope")).status_code == 404
    assert (await client.get("/api/incidents/nope/graph")).status_code == 404
