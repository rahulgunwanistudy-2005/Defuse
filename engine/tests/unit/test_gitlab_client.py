from __future__ import annotations

import httpx
import pytest

from defuse.collect.gitlab import (
    DryRunViolation,
    Forbidden,
    GitLabClient,
    NamespaceViolation,
    NotFound,
)

NS = ("defuse-sandbox",)


def _client(handler: httpx.MockTransport, **kw: object) -> GitLabClient:
    async def no_sleep(_: float) -> None:
        return None

    return GitLabClient(
        "https://gitlab.test",
        None,
        NS,
        transport=handler,
        sleep=no_sleep,
        **kw,  # type: ignore[arg-type]
    )


async def test_retries_on_429_and_honours_retry_after() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    async with _client(httpx.MockTransport(handler)) as gl:
        assert await gl.get("/api/v4/x") == {"ok": True}
    assert calls["n"] == 3


async def test_gives_up_after_max_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with _client(httpx.MockTransport(handler), max_retries=2) as gl:
        with pytest.raises(Exception, match="503"):
            await gl.get("/api/v4/x")


async def test_conditional_get_uses_etag() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("If-None-Match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, json=[{"id": 1}], headers={"ETag": '"v1"'})

    async with _client(httpx.MockTransport(handler)) as gl:
        first = await gl.get("/api/v4/x")
        second = await gl.get("/api/v4/x")
    assert first == second == [{"id": 1}]
    assert calls["n"] == 2


async def test_pagination_follows_link_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "page2" in str(request.url) or request.url.params.get("cursor") == "c2":
            return httpx.Response(200, json=[{"id": 2}])
        link = '<https://gitlab.test/api/v4/x?cursor=c2>; rel="next"'
        return httpx.Response(200, json=[{"id": 1}], headers={"Link": link})

    async with _client(httpx.MockTransport(handler)) as gl:
        items = [i async for i in gl.paginate("/api/v4/x")]
    assert [i["id"] for i in items] == [1, 2]


async def test_get_text_is_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"a" * 5000)

    async with _client(httpx.MockTransport(handler)) as gl:
        text = await gl.get_text("/api/v4/x/trace", max_bytes=1000)
    assert len(text) == 1000


async def test_mutation_outside_namespace_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"path_with_namespace": "other-group/app"})
        return httpx.Response(200, json={})

    async with _client(httpx.MockTransport(handler)) as gl:
        with pytest.raises(NamespaceViolation, match="outside the sandbox"):
            await gl.mutate("DELETE", "/api/v4/projects/9/x", project=9)


async def test_mutation_in_namespace_is_allowed() -> None:
    seen = {"deleted": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"path_with_namespace": "defuse-sandbox/app-a"})
        seen["deleted"] = True
        return httpx.Response(204)

    async with _client(httpx.MockTransport(handler)) as gl:
        await gl.mutate("DELETE", "/api/v4/projects/9/x", project=9)
    assert seen["deleted"]


async def test_dry_run_refuses_to_send_mutations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path_with_namespace": "defuse-sandbox/app-a"})

    async with _client(httpx.MockTransport(handler), dry_run=True) as gl:
        with pytest.raises(DryRunViolation):
            await gl.mutate("DELETE", "/api/v4/projects/9/x", project=9)


async def test_not_found_and_forbidden_are_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        code = 404 if "missing" in str(request.url) else 403
        return httpx.Response(code, json={"message": "no"})

    async with _client(httpx.MockTransport(handler)) as gl:
        with pytest.raises(NotFound):
            await gl.get("/api/v4/missing")
        with pytest.raises(Forbidden):
            await gl.get("/api/v4/secret")


async def test_checked_project_cannot_authorize_a_different_mutation_path() -> None:
    async with _client(httpx.MockTransport(lambda request: httpx.Response(204))) as gl:
        with pytest.raises(NamespaceViolation, match="does not match"):
            await gl.mutate("DELETE", "/api/v4/projects/99/packages/1", project=9)
        assert gl.requests == 0


async def test_runner_serving_outside_projects_cannot_be_paused() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(
            200,
            json={
                "projects": [
                    {"path_with_namespace": "defuse-sandbox/app-a"},
                    {"path_with_namespace": "production/app"},
                ]
            },
        )

    async with _client(httpx.MockTransport(handler)) as gl:
        with pytest.raises(NamespaceViolation, match="all projects"):
            await gl.mutate_runner(7, json_body={"paused": True})
    assert seen == ["GET"]


async def test_rest_variable_reads_are_refused_before_the_request() -> None:
    from defuse.collect.gitlab import GitLabError

    async with _client(httpx.MockTransport(lambda request: httpx.Response(200, json=[]))) as gl:
        with pytest.raises(GitLabError, match="GraphQL metadata"):
            await gl.get("/api/v4/projects/9/variables")
        assert gl.requests == 0


async def test_graphql_secret_selection_is_refused_before_the_request() -> None:
    async with _client(httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as gl:
        with pytest.raises(ValueError, match="metadata only"):
            await gl.graphql("query { project { ciVariables { nodes { key value } } } }", {})
        assert gl.requests == 0
