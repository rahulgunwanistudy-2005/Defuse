"""An in-memory GitLab backend for the seeded scenario and integration tests.

It serves the packaged scenario fixtures for reads and applies mutations in memory (pause a
runner, rotate/revoke a token, delete a package, trigger a pipeline), so a real, non-dry-run
containment can run end to end without a live GitLab. Shapes follow the GitLab REST reference.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

_ROUTES = json.loads((files("defuse.data") / "sandbox_routes.json").read_text(encoding="utf-8"))


class MemoryGitLab:
    def __init__(self) -> None:
        self._routes: dict[str, Any] = json.loads(json.dumps(_ROUTES))
        self.mutations: list[tuple[str, str]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        parts = urlsplit(str(request.url))
        path, query = parts.path, parse_qs(parts.query)
        if path == "/api/graphql":
            return graphql_fixture(self._routes[path], json.loads(request.content))
        if request.method in ("POST", "PUT", "DELETE"):
            return self._mutate(request.method, path)
        for key in (f"{path}?{parts.query}", path):
            if key in self._routes:
                return _read(self._routes[key], query)
        raise AssertionError(f"no fixture for {request.method} {path}")

    def _mutate(self, method: str, path: str) -> httpx.Response:
        self.mutations.append((method, path))
        if path.endswith("/rotate"):
            return httpx.Response(200, json={"id": 9001, "active": True})
        if path == "/api/v4/runners/7" and method == "PUT":
            self._routes[path] = {**self._routes[path], "paused": True, "active": False}
            return httpx.Response(200, json={"paused": True})
        if "/packages/" in path and method == "DELETE":
            return httpx.Response(204)
        if "/access_tokens/" in path and method == "DELETE":
            return httpx.Response(204)
        if "/deploy_tokens/" in path and method == "DELETE":
            return httpx.Response(204)
        if path.endswith("/pipeline") and method == "POST":
            return httpx.Response(
                201,
                json={
                    "id": 6100,
                    "web_url": "https://gitlab.com/defuse-sandbox/x/-/pipelines/6100",
                },
            )
        return httpx.Response(204)


def _read(entry: Any, query: dict[str, list[str]]) -> httpx.Response:
    if isinstance(entry, dict) and "status" in entry:
        return httpx.Response(int(entry["status"]), json=entry.get("json"))
    if isinstance(entry, dict) and entry.get("kind") == "text":
        return httpx.Response(200, content=str(entry["text"]).encode())
    if isinstance(entry, dict) and entry.get("kind") == "paged":
        pages = entry["pages"]
        cursor = int(query.get("cursor", ["0"])[0])
        body = pages[cursor] if cursor < len(pages) else []
        headers = {}
        if cursor + 1 < len(pages):
            headers["Link"] = f'<https://gitlab.test/next?cursor={cursor + 1}>; rel="next"'
        return httpx.Response(200, json=body, headers=headers)
    return httpx.Response(200, json=entry)


def graphql_fixture(entry: Any, body: dict[str, Any]) -> httpx.Response:
    """Serve metadata-only fixtures; reject accidental secret selection at the transport."""
    import re

    if re.search(r"\bvalue\b", body["query"]):
        raise AssertionError("variable query must never select secret contents")
    kind = "group" if "group(fullPath" in body["query"] else "project"
    node = entry["entries"].get(f"{kind}:{body['variables']['path']}")
    if node is not None and "pages" in node:
        node = node["pages"][int(body["variables"].get("after") or 0)]
    return httpx.Response(200, json={"data": {kind: {"ciVariables": node} if node else None}})
