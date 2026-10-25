"""A MockTransport that serves the recorded fixture responses to the collector."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def _load_routes() -> dict[str, object]:
    data = json.loads((FIXTURES / "routes.json").read_text())
    assert isinstance(data, dict)
    return data


def make_transport() -> httpx.MockTransport:
    routes = _load_routes()

    def handler(request: httpx.Request) -> httpx.Response:
        parts = urlsplit(str(request.url))
        path = parts.path
        query = parse_qs(parts.query)
        for key in (f"{path}?{parts.query}", path):
            if key in routes:
                return _respond(routes[key], query)
        raise AssertionError(f"no fixture for {request.method} {path}?{parts.query}")

    return httpx.MockTransport(handler)


def _respond(entry: object, query: dict[str, list[str]]) -> httpx.Response:
    if isinstance(entry, dict) and "status" in entry:
        return httpx.Response(int(entry["status"]), json=entry.get("json"))
    if isinstance(entry, dict) and entry.get("kind") == "text":
        return httpx.Response(200, content=str(entry["text"]).encode())
    if isinstance(entry, dict) and entry.get("kind") == "paged":
        pages = entry["pages"]
        assert isinstance(pages, list)
        cursor = int(query.get("cursor", ["0"])[0])
        body = pages[cursor] if cursor < len(pages) else []
        headers = {}
        if cursor + 1 < len(pages):
            headers["Link"] = f'<https://gitlab.test/next?cursor={cursor + 1}>; rel="next"'
        return httpx.Response(200, json=body, headers=headers)
    return httpx.Response(200, json=entry)
