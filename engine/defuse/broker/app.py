"""Loopback credential-authority API; credentials never appear in responses or validation errors."""

from __future__ import annotations

import hmac
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from defuse.automate.models import CredentialReceipt, CredentialRequest
from defuse.broker.authority import AuthorityError, GitLabAuthority
from defuse.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    authority = GitLabAuthority(configured)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        authority.db.close()

    app = FastAPI(title="Defuse local credential authority", lifespan=lifespan)
    app.state.authority = authority

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "invalid metadata request"})

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/replace", response_model=CredentialReceipt)
    async def replace(request: Request, body: CredentialRequest) -> CredentialReceipt:
        if (
            configured.credential_broker_token is None
            or not configured.credential_broker_token.get_secret_value()
        ):
            raise HTTPException(503, "credential authority authentication is not configured")
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(
            supplied, "Bearer " + configured.credential_broker_token.get_secret_value()
        ):
            raise HTTPException(401, "credential authority authentication failed")
        owner = uuid4().hex
        with authority.db:
            authority.db.execute("BEGIN IMMEDIATE")
            held = authority.db.execute(
                "SELECT expires FROM leases WHERE target=?", (body.target,)
            ).fetchone()
            if held and float(held[0]) > time.time():
                raise HTTPException(409, "credential replacement is already in progress")
            authority.db.execute(
                "INSERT OR REPLACE INTO leases VALUES (?,?,?)",
                (body.target, owner, time.time() + 3600),
            )
        try:
            return await authority.replace(body)
        except AuthorityError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            # Never reflect third-party responses, subprocess output or exception inputs.
            raise HTTPException(502, "credential authority could not finish replacement") from None
        finally:
            with authority.db:
                authority.db.execute(
                    "DELETE FROM leases WHERE target=? AND owner=?", (body.target, owner)
                )

    return app
