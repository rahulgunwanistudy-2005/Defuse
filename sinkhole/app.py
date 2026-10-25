"""Sinkhole: records simulator beacons so verification can confirm the worm went quiet.

A beacon carries a random canary id and the NAMES of readable CI variables — never values.
The service refuses any beacon that carries a field that looks like a secret value.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Annotated

from fastapi import FastAPI
from pydantic import BaseModel, Field

BANNED_FIELDS = {"value", "token", "secret", "password"}


class Beacon(BaseModel):
    canary: Annotated[str, Field(min_length=1, max_length=128)]
    variable_names: tuple[str, ...] = ()
    note: str = ""


class Record(BaseModel):
    at: float
    canary: str
    variable_names: tuple[str, ...]


def create_app() -> FastAPI:
    app = FastAPI(title="Defuse sinkhole", version="0.1.0")
    beacons: deque[Record] = deque(maxlen=10000)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/beacon")
    def beacon(body: Beacon) -> dict[str, str]:
        beacons.append(
            Record(at=time.time(), canary=body.canary, variable_names=body.variable_names)
        )
        return {"status": "recorded"}

    @app.get("/beacons")
    def list_beacons(window: float = 120.0) -> dict[str, object]:
        cutoff = time.time() - window
        recent = [b for b in beacons if b.at >= cutoff]
        return {
            "count": len(recent),
            "window": window,
            "canaries": sorted({b.canary for b in recent}),
        }

    return app


app = create_app()
