"""Action executors. Each one is idempotent, honours dry-run, and returns an action record.

GitLab-facing executors call through GitLabClient, so the namespace allowlist and the dry-run
guard apply. GCP-facing executors (host isolation, watcher stop, snapshot, persistence removal)
go through GcpOps, which the CLI wires to real gcloud calls or to a recording stub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

import structlog

from defuse.collect.gitlab import DryRunViolation, GitLabClient, NamespaceViolation
from defuse.model.graph import SecretKind
from defuse.model.incident import ActionRecord, RecordStatus, StateValue
from defuse.model.plan import Action, ActionKind

log = structlog.get_logger(__name__)


class GcpOps(Protocol):
    async def host_network_tags(self, host: str) -> list[str]: ...
    async def set_network_tags(self, host: str, tags: list[str]) -> None: ...
    async def snapshot_disk(self, host: str) -> str: ...
    async def run_command(self, host: str, command: str) -> str: ...


class ExecutionContext:
    def __init__(
        self,
        incident_id: str,
        client: GitLabClient,
        gcp: GcpOps,
        *,
        actor: str,
        dry_run: bool,
        isolation_tag: str,
        live_tag: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.incident_id = incident_id
        self.gl = client
        self.gcp = gcp
        self.actor = actor
        self.dry_run = dry_run
        self.isolation_tag = isolation_tag
        self.live_tag = live_tag
        self.clock = clock or (lambda: datetime.now(UTC))


Handler = Callable[
    ["ExecutionContext", Action],
    Awaitable[tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]],
]
_HANDLERS: dict[ActionKind, Handler] = {}


def handler(kind: ActionKind) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return register


def _target_id(target: str, prefix: str) -> str:
    return target.split(prefix, 1)[1]


async def execute(ctx: ExecutionContext, action: Action) -> ActionRecord:
    started = ctx.clock()
    handler_fn = _HANDLERS.get(action.kind)
    if handler_fn is None:
        raise KeyError(f"no executor for {action.kind}")
    try:
        if ctx.dry_run:
            status, detail, before, after, url = await _describe(ctx, action)
        else:
            status, detail, before, after, url = await handler_fn(ctx, action)
    except DryRunViolation as exc:
        status, detail, before, after, url = RecordStatus.DRY_RUN, str(exc), {}, {}, None
    except NamespaceViolation as exc:
        status, detail, before, after, url = RecordStatus.FAILED, str(exc), {}, {}, None
    except Exception as exc:
        log.error("execute.failed", action=action.id, error=str(exc))
        status, detail, before, after, url = (
            RecordStatus.FAILED,
            f"{type(exc).__name__}: {exc}",
            {},
            {},
            None,
        )
    return ActionRecord(
        incident_id=ctx.incident_id,
        action_id=action.id,
        kind=action.kind,
        target=action.target,
        actor=ctx.actor,
        status=status,
        dry_run=ctx.dry_run,
        before=before,
        after=after,
        detail=detail,
        evidence_url=url,
        started_at=started,
        finished_at=ctx.clock(),
    )


async def _describe(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    return RecordStatus.DRY_RUN, f"would {action.label.lower()}", {}, {}, None


# --- GCP host actions ----------------------------------------------------------------------


def _host_name(target: str) -> str:
    return _target_id(target, "host:")


@handler(ActionKind.ISOLATE_HOST)
async def _isolate_host(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    host = _host_name(action.target)
    before = await ctx.gcp.host_network_tags(host)
    if ctx.isolation_tag in before and ctx.live_tag not in before:
        return (
            RecordStatus.ALREADY_SATISFIED,
            f"{host} already isolated",
            {"tags": before},
            {"tags": before},
            None,
        )
    after = [t for t in before if t != ctx.live_tag]
    if ctx.isolation_tag not in after:
        after.append(ctx.isolation_tag)
    await ctx.gcp.set_network_tags(host, after)
    return (
        RecordStatus.APPLIED,
        f"swapped network tags on {host}",
        {"tags": before},
        {"tags": sorted(after)},
        None,
    )


@handler(ActionKind.SNAPSHOT_EVIDENCE)
async def _snapshot(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    host = _host_name(action.target)
    snapshot = await ctx.gcp.snapshot_disk(host)
    return RecordStatus.APPLIED, f"snapshotted {host}", {}, {"snapshot": snapshot}, None


@handler(ActionKind.STOP_WATCHER)
async def _stop_watcher(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    host = action.param("host") or ""
    unit = action.param("unit") or ""
    out = await ctx.gcp.run_command(
        host, f"systemctl --user stop {unit} && systemctl --user mask {unit}"
    )
    return RecordStatus.APPLIED, f"stopped {unit} on {host}", {}, {"result": out}, None


@handler(ActionKind.REMOVE_PERSISTENCE)
async def _remove_persistence(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    host = _host_name(action.target)
    out = await ctx.gcp.run_command(
        host,
        "rm -f ~/.config/systemd/user/defuse-watcher.service && systemctl --user daemon-reload",
    )
    return RecordStatus.APPLIED, f"removed persistence on {host}", {}, {"result": out}, None


# --- GitLab actions ------------------------------------------------------------------------


@handler(ActionKind.PAUSE_RUNNER)
async def _pause_runner(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    runner_id = int(_target_id(action.target, "runner:"))
    current = await ctx.gl.get(f"/api/v4/runners/{runner_id}")
    if current.get("paused", not current.get("active", True)):
        return (
            RecordStatus.ALREADY_SATISFIED,
            "runner already paused",
            {"paused": True},
            {"paused": True},
            None,
        )
    await ctx.gl.mutate_runner(runner_id, json_body={"paused": True})
    return (
        RecordStatus.APPLIED,
        f"paused runner {runner_id}",
        {"paused": False},
        {"paused": True},
        None,
    )


def _secret_parts(target: str) -> tuple[SecretKind, int, int]:
    _, kind, owner, token = target.split(":", 3)
    return SecretKind(kind), int(owner.split("/", 1)[1]), int(token)


@handler(ActionKind.ROTATE_SECRET)
async def _rotate_secret(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    if action.param("mode") == "operator_handoff":
        return (
            RecordStatus.NEEDS_OPERATOR,
            "CI variable has no API-rotatable credential; operator must replace its value",
            {},
            {},
            None,
        )
    kind, project_id, token_id = _secret_parts(action.target)
    if kind == SecretKind.PROJECT_ACCESS_TOKEN:
        result = await ctx.gl.mutate(
            "POST",
            f"/api/v4/projects/{project_id}/access_tokens/{token_id}/rotate",
            project=project_id,
        )
        new_id = result.get("id") if isinstance(result, dict) else None
        return (
            RecordStatus.APPLIED,
            "rotated project access token",
            {"token_id": token_id},
            {"token_id": new_id},
            None,
        )
    return (
        RecordStatus.NEEDS_OPERATOR,
        "deploy tokens cannot be rotated via API; revoke and recreate",
        {},
        {},
        None,
    )


@handler(ActionKind.REVOKE_SECRET)
async def _revoke_secret(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    kind, project_id, token_id = _secret_parts(action.target)
    if kind == SecretKind.DEPLOY_TOKEN:
        await ctx.gl.mutate(
            "DELETE", f"/api/v4/projects/{project_id}/deploy_tokens/{token_id}", project=project_id
        )
        return (
            RecordStatus.APPLIED,
            "revoked deploy token",
            {"revoked": False},
            {"revoked": True},
            None,
        )
    await ctx.gl.mutate(
        "DELETE", f"/api/v4/projects/{project_id}/access_tokens/{token_id}", project=project_id
    )
    return (
        RecordStatus.APPLIED,
        "revoked project access token",
        {"active": True},
        {"active": False},
        None,
    )


@handler(ActionKind.QUARANTINE_VERSION)
async def _quarantine(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    # target: pkg:<name>@<version>; the registry project is carried in params by the executor driver
    project_id = int(action.param("project_id") or 0)
    package_id = int(action.param("package_id") or 0)
    if not project_id or not package_id:
        return (
            RecordStatus.NEEDS_OPERATOR,
            "rogue version not located in a managed registry",
            {},
            {},
            None,
        )
    await ctx.gl.mutate(
        "DELETE", f"/api/v4/projects/{project_id}/packages/{package_id}", project=project_id
    )
    return (
        RecordStatus.APPLIED,
        f"deleted rogue package {package_id}",
        {"present": True},
        {"present": False},
        None,
    )


@handler(ActionKind.PIN_KNOWN_GOOD)
async def _pin(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    return (
        RecordStatus.NEEDS_OPERATOR,
        "known-good pin is proposed by the postmortem-policy MR",
        {},
        {},
        None,
    )


@handler(ActionKind.REBUILD_ARTIFACTS)
async def _rebuild(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    project_id = int(_target_id(action.target, "project:"))
    ref = action.param("ref") or "main"
    result = await ctx.gl.mutate(
        "POST",
        f"/api/v4/projects/{project_id}/pipeline",
        project=project_id,
        json_body={"ref": ref},
    )
    url = result.get("web_url") if isinstance(result, dict) else None
    return (
        RecordStatus.APPLIED,
        f"triggered clean rebuild of {project_id}",
        {},
        {"pipeline": result.get("id") if isinstance(result, dict) else None},
        url,
    )


@handler(ActionKind.REMOVE_HOOK_FILES)
async def _remove_hooks(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    paths = [v for k, v in action.params if k == "path"]
    return (
        RecordStatus.NEEDS_OPERATOR,
        f"hook removal is performed by the hook-sweeper flow MR for {len(paths)} file(s)",
        {},
        {"paths": paths},
        None,
    )


@handler(ActionKind.BLOCK_AGENT_IDENTITY)
async def _block_agent(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    return (
        RecordStatus.NEEDS_OPERATOR,
        "agent write tools set to Deny via tool governance (see docs/governance.md)",
        {},
        {},
        None,
    )


@handler(ActionKind.RESTORE_AGENT_IDENTITY)
async def _restore_agent(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    return (
        RecordStatus.NEEDS_OPERATOR,
        "agent write tools restored after verification",
        {},
        {},
        None,
    )


@handler(ActionKind.VERIFY_CLEAN)
async def _verify(
    ctx: ExecutionContext, action: Action
) -> tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]:
    return RecordStatus.APPLIED, "verification runs in the verify stage", {}, {}, None
