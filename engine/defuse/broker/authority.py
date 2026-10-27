"""GitLab-native credential issuance and consumer installation.

Only NEWLY ISSUED replacements are handled here, in this separate authority process. Existing
CI secret contents are never requested. No credential contents enter the journal or receipts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from defuse.automate.models import CredentialReceipt, CredentialRequest
from defuse.config import Settings


class AuthorityError(Exception):
    """A sanitized failure that contains no API response or subprocess output."""


class GitLabAuthority:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings, self.transport = settings, transport
        self.lock = asyncio.Lock()
        settings.broker_journal.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(settings.broker_journal, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS operations "
            "(key TEXT PRIMARY KEY, attempts INTEGER, receipt TEXT, fingerprint TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS leases (target TEXT PRIMARY KEY, owner TEXT, expires REAL)"
        )
        self.db.commit()

    async def _request(
        self, http: httpx.AsyncClient, method: str, path: str, body: dict[str, Any] | None = None
    ) -> httpx.Response:
        response = await http.request(method, path, json=body)
        if response.status_code >= 400:
            raise AuthorityError(
                f"GitLab credential operation returned HTTP {response.status_code}"
            )
        return response

    async def _project(self, http: httpx.AsyncClient, project: int) -> str:
        response = await self._request(http, "GET", f"/api/v4/projects/{project}")
        path = str(response.json().get("path_with_namespace") or "")
        if not any(path.startswith(ns + "/") for ns in self.settings.namespaces):
            raise AuthorityError("credential operation is outside sandbox namespaces")
        return path

    async def replace(self, request: CredentialRequest) -> CredentialReceipt:
        if (
            self.settings.broker_gitlab_token is None
            or not self.settings.broker_gitlab_token.get_secret_value()
        ):
            raise AuthorityError("broker GitLab authentication is not configured")
        if request.namespace not in self.settings.namespaces:
            raise AuthorityError("credential namespace is not allow-listed")
        key = hashlib.sha256(f"{request.incident_id}:{request.action_id}".encode()).hexdigest()
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        async with self.lock:
            stored = self.db.execute(
                "SELECT attempts,receipt,fingerprint FROM operations WHERE key=?", (key,)
            ).fetchone()
            if stored and stored[2] != fingerprint:
                raise AuthorityError("idempotency key belongs to a different request")
            if stored and stored[1]:
                receipt = CredentialReceipt.model_validate_json(stored[1])
                if (receipt.target, receipt.namespace) != (request.target, request.namespace):
                    raise AuthorityError("idempotency key belongs to another credential")
                return receipt
            attempt = (int(stored[0]) + 1) if stored else 1
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO operations VALUES (?,?,NULL,?)",
                    (key, attempt, fingerprint),
                )
            headers = {
                "Authorization": f"Bearer {self.settings.broker_gitlab_token.get_secret_value()}"
            }
            async with httpx.AsyncClient(
                base_url=self.settings.gitlab_url,
                headers=headers,
                transport=self.transport,
                timeout=30,
                follow_redirects=False,
            ) as http:
                for path in request.projects:
                    if not path.startswith(request.namespace + "/"):
                        raise AuthorityError("credential consumer is outside incident namespace")
                for consumer in request.consumers:
                    if not re.fullmatch(r"[A-Z_a-z][A-Za-z0-9_]{0,254}", consumer.key):
                        raise AuthorityError("invalid consumer variable name")
                    kind, _, owner = consumer.owner.partition("/")
                    if kind == "project" and owner.isdigit():
                        path = await self._project(http, int(owner))
                        if path not in request.projects:
                            raise AuthorityError("consumer project was not in the scoped request")
                    elif kind == "group":
                        if owner != request.namespace:
                            raise AuthorityError("group consumer is outside incident namespace")
                    else:
                        raise AuthorityError("unsupported consumer owner")
                parts = request.target.split(":", 3)
                if len(parts) != 4 or parts[0] != "secret":
                    raise AuthorityError("invalid credential target")
                if not request.consumers:
                    raise AuthorityError(
                        "automatic replacement requires explicit consumer bindings"
                    )
                kind, owner, old = parts[1:]
                name = f"defuse-{key[:20]}-a{attempt}"
                if kind in {"project_access_token", "deploy_token"}:
                    if not owner.startswith("project/") or not old.isdigit():
                        raise AuthorityError("invalid GitLab credential coordinates")
                    pid = int(owner.split("/", 1)[1])
                    if await self._project(http, pid) not in request.projects:
                        raise AuthorityError("credential owner is outside the incident scope")
                    endpoint = (
                        "access_tokens" if kind == "project_access_token" else "deploy_tokens"
                    )
                    listed = (
                        await self._request(http, "GET", f"/api/v4/projects/{pid}/{endpoint}")
                    ).json()
                    metadata = next((item for item in listed if int(item["id"]) == int(old)), None)
                    if metadata is None:
                        raise AuthorityError("original credential metadata is unavailable")
                    if not set(request.scopes) <= set(metadata.get("scopes", [])):
                        raise AuthorityError("replacement scopes exceed the original credential")
                    body: dict[str, Any] = {
                        "name": name,
                        "scopes": list(request.scopes),
                        "expires_at": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
                    }
                    if kind == "project_access_token":
                        level = int(metadata.get("access_level", 30))
                        if level > 30:
                            raise AuthorityError(
                                "automatic replacement will not grant privileged project roles"
                            )
                        body["access_level"] = level
                    elif metadata.get("username"):
                        body["username"] = str(metadata["username"])
                    created = (
                        await self._request(
                            http, "POST", f"/api/v4/projects/{pid}/{endpoint}", body
                        )
                    ).json()
                    replacement_id = str(created["id"])
                    # Only the authority sees this newly minted credential. It is never returned,
                    # logged or persisted; the containment engine receives the metadata below.
                    replacement = SecretStr(str(created["token"]))
                    orphan_ids = [
                        int(item["id"])
                        for item in listed
                        if str(item.get("name", "")).startswith(f"defuse-{key[:20]}-a")
                    ]
                else:
                    replacement, replacement_id = await self._provider(request)
                    orphan_ids = []
                    pid = 0
                    endpoint = ""
                if not request.consumers:
                    raise AuthorityError(
                        "automatic replacement requires explicit consumer bindings"
                    )
                for consumer in request.consumers:
                    owner_kind, _, owner_id = consumer.owner.partition("/")
                    collection = "projects" if owner_kind == "project" else "groups"
                    path = (
                        f"/api/v4/{collection}/{quote(owner_id, safe='')}/variables/"
                        f"{quote(consumer.key, safe='')}?filter[environment_scope]="
                        f"{quote(consumer.environment_scope, safe='')}"
                    )
                    # Update in place without retrieving the existing variable or its contents.
                    response = await self._request(
                        http,
                        "PUT",
                        path,
                        {
                            "value": replacement.get_secret_value(),
                            "masked": True,
                            "protected": consumer.protected,
                            "environment_scope": consumer.environment_scope,
                        },
                    )
                    if response.status_code not in (200, 201):
                        raise AuthorityError("consumer installation was not acknowledged")
                for orphan in orphan_ids:
                    await self._request(
                        http, "DELETE", f"/api/v4/projects/{pid}/{endpoint}/{orphan}"
                    )
                if request.retire_old and kind in {"project_access_token", "deploy_token"}:
                    await self._request(http, "DELETE", f"/api/v4/projects/{pid}/{endpoint}/{old}")
                receipt = CredentialReceipt(
                    receipt_id=key,
                    incident_id=request.incident_id,
                    action_id=request.action_id,
                    target=request.target,
                    namespace=request.namespace,
                    installed=True,
                    old_revoked=request.retire_old,
                    replacement_id=replacement_id,
                    consumer_refs=tuple(c.ref for c in request.consumers),
                )
                with self.db:
                    self.db.execute(
                        "UPDATE operations SET receipt=? WHERE key=?",
                        (receipt.model_dump_json(), key),
                    )
                return receipt

    async def _provider(self, request: CredentialRequest) -> tuple[SecretStr, str]:
        command = self.settings.broker_provider_commands.get(request.target)
        if not command:
            raise AuthorityError("non-GitLab credential requires an explicitly configured provider")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(request.model_dump_json().encode()), timeout=60
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise AuthorityError("credential provider timed out") from None
        if process.returncode != 0 or len(output) > 65536:
            raise AuthorityError(
                "credential provider did not produce a bounded successful response"
            )
        try:
            data = json.loads(output)
            if data.get("old_revoked") is not True or not isinstance(data.get("replacement"), str):
                raise AuthorityError("provider did not attest upstream credential retirement")
            return SecretStr(data["replacement"]), str(data["replacement_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthorityError("credential provider returned an invalid response") from exc
