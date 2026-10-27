"""Typed async GitLab client.

- bounded concurrency (semaphore), per-request timeouts, HTTP/2
- retry with jittered exponential backoff on 429 and 5xx, honouring Retry-After
- conditional GETs with ETag
- pagination by following the `Link: rel="next"` header (keyset or offset)
- every mutating call is checked against the sandbox namespace allowlist, and refused
  outright in dry-run mode
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit

import httpx
import structlog
from pydantic import SecretStr

log = structlog.get_logger(__name__)

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
JSON = Any


class GitLabError(Exception):
    def __init__(self, method: str, path: str, status: int, message: str) -> None:
        super().__init__(f"{method} {path} returned {status}: {message}")
        self.method = method
        self.path = path
        self.status = status
        self.message = message


class NotFound(GitLabError):
    pass


class Forbidden(GitLabError):
    pass


class NamespaceViolation(Exception):
    """A mutating call targeted a project outside the configured sandbox namespaces."""


class DryRunViolation(Exception):
    """A mutating call was attempted by a client running in dry-run mode."""


def _error(method: str, path: str, response: httpx.Response) -> GitLabError:
    try:
        body = response.json()
        message = str(body.get("message") or body.get("error") or body)
    except (ValueError, AttributeError):
        message = response.text[:200]
    cls = {404: NotFound, 401: Forbidden, 403: Forbidden}.get(response.status_code, GitLabError)
    return cls(method, path, response.status_code, message)


def encode(path_or_id: int | str) -> str:
    return str(path_or_id) if isinstance(path_or_id, int) else quote(path_or_id, safe="")


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        token: SecretStr | None,
        namespaces: tuple[str, ...],
        *,
        concurrency: int = 8,
        timeout: float = 20.0,
        max_retries: int = 5,
        dry_run: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        headers = {"User-Agent": "defuse/0.1"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token.get_secret_value()}"
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            http2=transport is None,
            transport=transport,
        )
        self._namespaces = namespaces
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_retries = max_retries
        self._sleep = sleep
        self._etags: dict[str, tuple[str, JSON]] = {}
        self._paths: dict[int, str] = {}
        self.dry_run = dry_run
        self.requests = 0

    async def __aenter__(self) -> GitLabClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- transport -----------------------------------------------------------------------

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        if re.match(r"^/api/v4/(projects|groups)/[^/]+/variables(?:/|$)", path):
            raise GitLabError(method, path, 0, "use GraphQL metadata selection for variables")
        attempt = 0
        while True:
            async with self._semaphore:
                self.requests += 1
                try:
                    response = await self._http.request(
                        method, path, params=params, json=json_body, headers=headers
                    )
                except httpx.TransportError as exc:
                    if attempt >= self._max_retries:
                        raise GitLabError(method, path, 0, f"transport error: {exc}") from exc
                    response = None
            if response is not None and response.status_code not in RETRY_STATUS:
                return response
            if attempt >= self._max_retries:
                assert response is not None  # noqa: S101 - transport branch raised above
                raise _error(method, path, response)
            delay = self._backoff(attempt, response)
            log.warning(
                "gitlab.retry",
                method=method,
                path=path,
                status=response.status_code if response is not None else None,
                attempt=attempt + 1,
                delay=round(delay, 2),
            )
            await self._sleep(delay)
            attempt += 1

    @staticmethod
    def _backoff(attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                return float(int(retry_after))
        base: float = min(30.0, 0.5 * (2**attempt))
        jitter: float = random.uniform(0, base)  # noqa: S311 - jitter, not crypto
        return base + jitter

    # --- reads ---------------------------------------------------------------------------

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> JSON:
        key = path + "?" + json.dumps(dict(params or {}), sort_keys=True, default=str)
        cached = self._etags.get(key)
        headers = {"If-None-Match": cached[0]} if cached else None
        response = await self._send("GET", path, params=params, headers=headers)
        if response.status_code == 304 and cached:
            return cached[1]
        if response.status_code >= 400:
            raise _error("GET", path, response)
        body = response.json()
        etag = response.headers.get("ETag")
        if etag:
            self._etags[key] = (etag, body)
        return body

    async def get_text(
        self, path: str, *, max_bytes: int, params: Mapping[str, Any] | None = None
    ) -> str:
        async with self._semaphore:
            self.requests += 1
            async with self._http.stream("GET", path, params=params) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise _error("GET", path, response)
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk[: max_bytes - size])
                    size += len(chunks[-1])
                    if size >= max_bytes:
                        break
        return b"".join(chunks).decode("utf-8", errors="replace")

    async def paginate(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        keyset: bool = False,
        limit: int | None = None,
    ) -> AsyncIterator[JSON]:
        first: dict[str, Any] = {"per_page": 100, **dict(params or {})}
        if keyset:
            first.update({"pagination": "keyset", "order_by": "id", "sort": "asc"})
        query: dict[str, Any] | None = first
        url: str | None = path
        seen = 0
        while url is not None:
            # After the first page `url` is the absolute `rel="next"` link, which already
            # carries the cursor/offset; passing params again would drop that query string.
            response = await self._send("GET", url, params=query)
            if response.status_code >= 400:
                raise _error("GET", path, response)
            for item in response.json():
                yield item
                seen += 1
                if limit is not None and seen >= limit:
                    return
            next_link = response.links.get("next", {}).get("url")
            url = next_link if next_link else None
            query = None

    async def graphql(self, query: str, variables: Mapping[str, Any]) -> JSON:
        if re.search(r"\bmutation\b", query):
            raise NamespaceViolation("GraphQL mutations must use the scoped REST client")
        if "ciVariables" in query and re.search(r"\bvalue\b", query):
            raise ValueError("variable queries must request metadata only")
        response = await self._send(
            "POST", "/api/graphql", json_body={"query": query, "variables": dict(variables)}
        )
        if response.status_code >= 400:
            raise _error("POST", "/api/graphql", response)
        body = cast(dict[str, Any], response.json())
        if body.get("errors"):
            raise GitLabError("POST", "/api/graphql", 200, json.dumps(body["errors"])[:300])
        return body["data"]

    # --- writes --------------------------------------------------------------------------

    async def project_path(self, project: int | str) -> str:
        if isinstance(project, str):
            return project
        if project not in self._paths:
            body = await self.get(f"/api/v4/projects/{project}")
            self._paths[project] = str(body["path_with_namespace"])
        return self._paths[project]

    def remember_project(self, project_id: int, path: str) -> None:
        self._paths[project_id] = path

    async def assert_mutable(self, project: int | str) -> str:
        path = await self.project_path(project)
        if not any(path == ns or path.startswith(ns + "/") for ns in self._namespaces):
            raise NamespaceViolation(
                f"refusing to change {path}: it is outside the sandbox namespaces "
                f"{', '.join(self._namespaces)}"
            )
        return path

    async def mutate_runner(self, runner_id: int, *, json_body: Any) -> JSON:
        """Pause/unpause a runner only when all its projects belong to the sandbox.

        Runners are instance-scoped, so the project allowlist cannot gate them directly; we
        read the runner's projects and refuse if it also serves an outside project.
        """

        detail = await self.get(f"/api/v4/runners/{runner_id}")
        projects = detail.get("projects") or []
        paths = [p.get("path_with_namespace", "") for p in projects]
        if not paths or not all(
            any(path == ns or path.startswith(ns + "/") for ns in self._namespaces)
            for path in paths
        ):
            raise NamespaceViolation(
                f"refusing to change runner {runner_id}: all projects must be inside the sandbox"
            )
        if self.dry_run:
            raise DryRunViolation(f"dry run: PUT /api/v4/runners/{runner_id} was not sent")
        response = await self._send("PUT", f"/api/v4/runners/{runner_id}", json_body=json_body)
        if response.status_code >= 400:
            raise _error("PUT", f"/api/v4/runners/{runner_id}", response)
        return response.json()

    async def mutate(
        self,
        method: str,
        path: str,
        *,
        project: int | str,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
    ) -> JSON:
        decoded = unquote(urlsplit(path).path)
        if any(part in {".", ".."} for part in decoded.split("/")):
            raise NamespaceViolation("mutation path must not contain traversal segments")
        if not path.startswith(f"/api/v4/projects/{encode(project)}/"):
            raise NamespaceViolation("mutation path does not match the checked sandbox project")
        await self.assert_mutable(project)
        if self.dry_run:
            raise DryRunViolation(f"dry run: {method} {path} was not sent")
        response = await self._send(method, path, params=params, json_body=json_body)
        if response.status_code >= 400:
            raise _error(method, path, response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
