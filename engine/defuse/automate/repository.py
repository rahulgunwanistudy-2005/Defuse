"""Idempotent repository changes through sandbox-scoped, diff-checked merge requests."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from defuse.automate.models import FileEdit
from defuse.collect.gitlab import GitLabClient, NotFound, encode


class PendingChange(Exception):
    def __init__(self, detail: str, url: str | None = None) -> None:
        super().__init__(detail)
        self.url = url


def guard_paths(changed: set[str], allowed: set[str]) -> None:
    if not changed <= allowed:
        raise ValueError("protected diff guard: change outside the deterministic file allowlist")


class RepositoryChanges:
    def __init__(
        self,
        gl: GitLabClient,
        *,
        auto_merge: bool = False,
        timeout: float = 300,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.gl, self.auto_merge, self.timeout, self.sleep = gl, auto_merge, timeout, sleep

    async def read(self, project: int, path: str, ref: str) -> str | None:
        FileEdit(action="delete", file_path=path)
        try:
            return str(
                await self.gl.get_text(
                    f"/api/v4/projects/{project}/repository/files/{encode(path)}/raw",
                    max_bytes=2_000_000,
                    params={"ref": ref},
                )
            )
        except NotFound:
            return None

    async def apply(
        self,
        project: int,
        incident: str,
        kind: str,
        title: str,
        *,
        description: str,
        edits: tuple[FileEdit, ...],
        allowed: set[str],
    ) -> tuple[bool, str | None]:
        guard_paths({e.file_path for e in edits}, allowed)
        await self.gl.assert_mutable(project)
        if not edits:
            return False, None
        metadata = await self.gl.get(f"/api/v4/projects/{project}")
        default = str(metadata.get("default_branch") or "main")
        digest = hashlib.sha256(f"{incident}:{kind}:{project}".encode()).hexdigest()[:20]
        branch = f"defuse/{kind}/{digest}"
        existing = [
            mr
            async for mr in self.gl.paginate(
                f"/api/v4/projects/{project}/merge_requests",
                {"source_branch": branch, "scope": "all", "state": "all"},
            )
        ]
        if existing:
            mr = existing[0]
            if mr["state"] == "closed":
                raise PendingChange("remediation MR was closed without merging", mr.get("web_url"))
        else:
            actions = [edit.model_dump(exclude_none=True) for edit in edits]
            # start_sha pins the proposal to the default branch revision observed here.
            head = await self.gl.get(
                f"/api/v4/projects/{project}/repository/branches/{encode(default)}"
            )
            try:
                recovered = await self.gl.get(
                    f"/api/v4/projects/{project}/repository/branches/{encode(branch)}"
                )
            except NotFound:
                recovered = None
            if recovered is not None:
                for edit in edits:
                    if (
                        await self.read(project, edit.file_path, recovered["commit"]["id"])
                        != edit.content
                    ):
                        raise ValueError("recovered remediation branch differs from the proposal")
            else:
                await self.gl.mutate(
                    "POST",
                    f"/api/v4/projects/{project}/repository/commits",
                    project=project,
                    json_body={
                        "branch": branch,
                        "start_sha": head["commit"]["id"],
                        "commit_message": title,
                        "actions": actions,
                    },
                )
            mr = await self.gl.mutate(
                "POST",
                f"/api/v4/projects/{project}/merge_requests",
                project=project,
                json_body={
                    "source_branch": branch,
                    "target_branch": default,
                    "title": title,
                    "description": description,
                    "remove_source_branch": True,
                },
            )
        iid = int(mr["iid"])
        url = mr.get("web_url")
        diffs = [
            d
            async for d in self.gl.paginate(
                f"/api/v4/projects/{project}/merge_requests/{iid}/diffs"
            )
        ]
        changed = {str(d[k]) for d in diffs for k in ("old_path", "new_path")}
        guard_paths(changed, allowed)
        if changed != {e.file_path for e in edits}:
            raise ValueError("protected diff guard: MR includes edits absent from the proposal")
        if not diffs or any(d.get("too_large") or d.get("collapsed") for d in diffs):
            raise ValueError("protected diff guard: incomplete MR diff")
        # Comparing every generated diff to the intended commit prevents a reused branch from
        # smuggling edits to an allow-listed file. Content is checked at the branch tip as well.
        source = str(
            mr.get("sha")
            or (
                await self.gl.get(
                    f"/api/v4/projects/{project}/repository/branches/{encode(branch)}"
                )
            )["commit"]["id"]
        )
        for edit in edits:
            actual = await self.read(project, edit.file_path, source)
            if actual != edit.content:
                raise ValueError("protected diff guard: MR contents differ from validated proposal")
        if mr["state"] == "merged":
            await self._assert_applied(project, default, edits)
            return False, url
        if not self.auto_merge:
            raise PendingChange("remediation MR awaits merge under project policy", url)
        await self.gl.mutate(
            "PUT",
            f"/api/v4/projects/{project}/merge_requests/{iid}/merge",
            project=project,
            json_body={"sha": source, "auto_merge": True},
        )
        deadline = monotonic() + self.timeout
        while True:
            current: dict[str, Any] = await self.gl.get(
                f"/api/v4/projects/{project}/merge_requests/{iid}"
            )
            if current["state"] == "merged":
                await self._assert_applied(project, default, edits)
                return True, url
            if current["state"] == "closed":
                raise PendingChange("remediation MR was closed without merging", url)
            if monotonic() >= deadline:
                raise PendingChange(
                    "remediation MR is waiting for required checks or approval", url
                )
            await self.sleep(2)

    async def _assert_applied(self, project: int, ref: str, edits: tuple[FileEdit, ...]) -> None:
        for edit in edits:
            if await self.read(project, edit.file_path, ref) != edit.content:
                raise ValueError("merged remediation is not present on the target branch")
