from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from defuse.automate.models import CredentialConsumer, CredentialRequest
from defuse.broker.app import create_app
from defuse.broker.authority import AuthorityError, GitLabAuthority
from defuse.config import Settings


def request() -> CredentialRequest:
    return CredentialRequest(
        incident_id="broker-test",
        action_id="rotate@token",
        target="secret:project_access_token:project/101:41",
        namespace="defuse-sandbox",
        projects=("defuse-sandbox/app-a",),
        scopes=("write_repository",),
        consumers=(
            CredentialConsumer(
                owner="project/101", key="GITLAB_PUSH_TOKEN", environment_scope="*", protected=True
            ),
        ),
    )


async def test_native_broker_installs_new_credential_and_returns_metadata_only(
    tmp_path: Path,
) -> None:
    calls = []

    def transport(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.url.path == "/api/v4/projects/101":
            return httpx.Response(200, json={"path_with_namespace": "defuse-sandbox/app-a"})
        if req.url.path.endswith("/access_tokens"):
            if req.method == "GET":
                return httpx.Response(
                    200, json=[{"id": 41, "access_level": 30, "scopes": ["write_repository"]}]
                )
            return httpx.Response(201, json={"id": 99, "token": "inert-new-test-credential"})
        if "/variables/" in req.url.path:
            assert req.method == "PUT"
            body = json.loads(req.content)
            assert body["masked"] is True
            assert body["protected"] is True
            assert body["value"] == "inert-new-test-credential"
            return httpx.Response(200, json={"key": "GITLAB_PUSH_TOKEN"})
        raise AssertionError("unexpected broker request")

    settings = Settings(
        broker_journal=tmp_path / "broker.db", broker_gitlab_token=SecretStr("inert-auth-fixture")
    )
    authority = GitLabAuthority(settings, httpx.MockTransport(transport))
    first = await authority.replace(request())
    total = len(calls)
    second = await authority.replace(request())
    assert first == second
    assert len(calls) == total
    assert first.replacement_id == "99"
    assert "inert-new-test-credential" not in first.model_dump_json()
    assert b"inert-new-test-credential" not in (tmp_path / "broker.db").read_bytes()
    authority.db.close()


async def test_broker_refuses_scope_escalation(tmp_path: Path) -> None:
    def transport(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/101"):
            return httpx.Response(200, json={"path_with_namespace": "defuse-sandbox/app-a"})
        assert req.method == "GET"
        return httpx.Response(
            200, json=[{"id": 41, "access_level": 30, "scopes": ["read_repository"]}]
        )

    authority = GitLabAuthority(
        Settings(
            broker_journal=tmp_path / "b.db", broker_gitlab_token=SecretStr("inert-auth-fixture")
        ),
        httpx.MockTransport(transport),
    )
    try:
        with pytest.raises(AuthorityError, match="scopes exceed"):
            await authority.replace(request())
    finally:
        authority.db.close()


async def test_broker_api_requires_its_own_authentication(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            broker_journal=tmp_path / "api.db",
            credential_broker_token=SecretStr("inert-auth-fixture"),
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://broker"
    ) as client:
        response = await client.post("/replace", json=request().model_dump(mode="json"))
    assert response.status_code == 401
    assert "inert-auth-fixture" not in response.text
    app.state.authority.db.close()


async def test_broker_rejects_outside_consumers_without_issuing_tokens(tmp_path: Path) -> None:
    authority = GitLabAuthority(
        Settings(
            broker_journal=tmp_path / "outside.db",
            broker_gitlab_token=SecretStr("inert-auth-fixture"),
        ),
        httpx.MockTransport(
            lambda req: httpx.Response(200, json={"path_with_namespace": "production/app"})
        ),
    )
    try:
        with pytest.raises(AuthorityError, match="outside sandbox"):
            await authority.replace(request())
    finally:
        authority.db.close()
