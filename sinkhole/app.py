"""Sinkhole: records simulator beacons so verification can confirm the worm went quiet.

A beacon carries a random canary id and the NAMES of readable CI variables — never values.
The service refuses any beacon that carries a field that looks like a secret value.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from threading import RLock
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class Beacon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canary: Annotated[str, Field(min_length=1, max_length=128)]
    variable_names: tuple[str, ...] = ()
    note: str = ""


class Record(BaseModel):
    at: float
    canary: str
    variable_names: tuple[str, ...]


def create_app(database_path: str = ":memory:") -> FastAPI:
    app = FastAPI(title="Defuse sinkhole", version="0.1.0")
    db = sqlite3.connect(database_path, check_same_thread=False)
    lock = RLock()
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS beacons (at REAL, canary TEXT, names TEXT)")
        db.execute("CREATE INDEX IF NOT EXISTS beacons_at ON beacons(at)")
        db.execute("CREATE TABLE IF NOT EXISTS observation (id INTEGER PRIMARY KEY, started REAL)")
        # Restarting any worker conservatively restarts the shared observation window.
        db.execute("INSERT OR REPLACE INTO observation VALUES (1, ?)", (time.time(),))

    @app.exception_handler(RequestValidationError)
    async def invalid_beacon(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Validation errors normally echo the submitted input. Never reflect beacon values.
        return JSONResponse(status_code=422, content={"detail": "invalid beacon or query fields"})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/beacon")
    def beacon(body: Beacon) -> dict[str, str]:
        with lock, db:
            db.execute(
                "INSERT INTO beacons VALUES (?, ?, ?)",
                (time.time(), body.canary, json.dumps(body.variable_names)),
            )
            db.execute("DELETE FROM beacons WHERE at < ?", (time.time() - 86400,))
        return {"status": "recorded"}

    @app.get("/beacons")
    def list_beacons(window: Annotated[float, Query(gt=0, le=3600)] = 120.0) -> dict[str, object]:
        cutoff = time.time() - window
        with lock:
            recent = db.execute("SELECT canary FROM beacons WHERE at >= ?", (cutoff,)).fetchall()
            started_at = db.execute("SELECT started FROM observation WHERE id = 1").fetchone()[0]
        return {
            "count": len(recent),
            "observed_seconds": time.time() - started_at,
            "complete": True,
            "window": window,
            "canaries": sorted({b[0] for b in recent}),
        }

    return app


app = create_app(os.environ.get("DEFUSE_SINKHOLE_DATABASE", "sinkhole.db"))
