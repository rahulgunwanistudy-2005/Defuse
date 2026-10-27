from __future__ import annotations

import runpy
from pathlib import Path

import httpx


async def test_sinkhole_rejects_extra_fields_without_reflecting_them() -> None:
    module = runpy.run_path(str(Path(__file__).parents[3] / "sinkhole" / "app.py"))
    transport = httpx.ASGITransport(app=module["create_app"]())
    async with httpx.AsyncClient(transport=transport, base_url="http://sinkhole") as client:
        rejected = await client.post("/beacon", json={"canary": "test", "value": "dummy-input"})
        assert rejected.status_code == 422
        assert "dummy-input" not in rejected.text
        assert (await client.get("/beacons")).json()["count"] == 0
        accepted = await client.post("/beacon", json={"canary": "test", "variable_names": ["KEY"]})
        assert accepted.status_code == 200
        recent = (await client.get("/beacons")).json()
        assert recent["count"] == 1
        assert recent["observed_seconds"] < 120
        assert recent["complete"] is True
        assert (await client.get("/beacons?window=-1")).status_code == 422


async def test_sinkhole_keeps_beacons_after_restart(tmp_path: Path) -> None:
    module = runpy.run_path(str(Path(__file__).parents[3] / "sinkhole" / "app.py"))
    db = str(tmp_path / "durable.db")
    first = module["create_app"](db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=first), base_url="http://s"
    ) as client:
        assert (await client.post("/beacon", json={"canary": "persisted"})).status_code == 200
    second = module["create_app"](db)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=second), base_url="http://s"
    ) as client:
        data = (await client.get("/beacons")).json()
    assert data["count"] == 1
    assert data["canaries"] == ["persisted"]
    assert data["observed_seconds"] < 120
