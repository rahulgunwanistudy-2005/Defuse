"""Executable action integrations. Targets, file lists and order always come from code."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import TYPE_CHECKING

from defuse.automate.broker import CredentialBroker
from defuse.automate.models import CredentialConsumer, CredentialRequest, FileEdit
from defuse.automate.remediation import clean_hook, trusted_pin_edits
from defuse.automate.repository import PendingChange, RepositoryChanges
from defuse.collect.gitlab import NotFound
from defuse.model.graph import PackageVersionNode, SecretNode
from defuse.model.incident import ActionRecord, RecordStatus, StateValue, Verification
from defuse.model.plan import Action, ActionKind

if TYPE_CHECKING:
    from defuse.config import Settings
    from defuse.execute.executors import ExecutionContext
    from defuse.model.facts import CollectedFacts
    from defuse.model.graph import ExposureGraph
    from defuse.model.ioc import IOCSet

Result = tuple[RecordStatus, str, dict[str, StateValue], dict[str, StateValue], str | None]
AUTOMATED = frozenset(
    {
        ActionKind.ROTATE_SECRET,
        ActionKind.REMOVE_HOOK_FILES,
        ActionKind.PIN_KNOWN_GOOD,
        ActionKind.BLOCK_AGENT_IDENTITY,
        ActionKind.RESTORE_AGENT_IDENTITY,
        ActionKind.REBUILD_ARTIFACTS,
        ActionKind.VERIFY_CLEAN,
    }
)


class ActionAutomation:
    def __init__(
        self,
        ctx: ExecutionContext,
        settings: Settings,
        ioc: IOCSet,
        graph: ExposureGraph,
        prior: list[ActionRecord],
        *,
        broker: CredentialBroker | None = None,
        verify: Callable[[], Awaitable[Verification]] | None = None,
        checkpoint: Callable[[str, dict[str, StateValue]], Awaitable[None]] | None = None,
        state: dict[str, dict[str, StateValue]] | None = None,
        namespace: str | None = None,
        facts: CollectedFacts | None = None,
    ) -> None:
        self.ctx, self.settings, self.ioc, self.graph = ctx, settings, ioc, graph
        self.prior, self.broker, self.verifier = prior, broker, verify
        self.checkpoint = checkpoint
        self.state = state or {}
        self.namespace = namespace or settings.sandbox_namespaces
        self.facts = facts
        self.repo = RepositoryChanges(
            ctx.gl, auto_merge=settings.auto_merge_remediation, timeout=settings.action_timeout
        )

    def note(self, record: ActionRecord) -> None:
        self.prior.append(record)

    async def perform(self, action: Action) -> Result:
        try:
            match action.kind:
                case ActionKind.ROTATE_SECRET:
                    return await self._rotate(action)
                case ActionKind.REMOVE_HOOK_FILES:
                    return await self._hooks(action)
                case ActionKind.PIN_KNOWN_GOOD:
                    return await self._pin(action)
                case ActionKind.BLOCK_AGENT_IDENTITY | ActionKind.RESTORE_AGENT_IDENTITY:
                    return await self._agent(action)
                case ActionKind.REBUILD_ARTIFACTS:
                    return await self._rebuild(action)
                case ActionKind.VERIFY_CLEAN:
                    if self.verifier is None:
                        raise PendingChange("verification context is not configured")
                    result = await self.verifier()
                    if not result.passed:
                        raise PendingChange("verification has failed or incomplete checks")
                    return RecordStatus.APPLIED, "all post-containment checks passed", {}, {}, None
                case _:
                    raise ValueError("unsupported automated action")
        except PendingChange as exc:
            return RecordStatus.NEEDS_OPERATOR, str(exc), {}, {}, exc.url

    async def _rotate(self, action: Action) -> Result:
        if self.broker is None:
            raise PendingChange("configure a credential broker for metadata-only replacement")
        node = self.graph.node(action.target)
        if not isinstance(node, SecretNode):
            raise ValueError("credential action has no secret metadata")
        projects = tuple(
            sorted({await self.ctx.gl.assert_mutable(p) for p in self._credential_projects(node)})
        )
        receipt = await self.broker.replace(
            CredentialRequest(
                incident_id=self.ctx.incident_id,
                action_id=action.id,
                target=action.target,
                namespace=self.namespace,
                projects=projects,
                carriers=node.carriers,
                scopes=node.scopes,
                retire_old=not node.rotatable,
                consumers=tuple(
                    CredentialConsumer(
                        owner=v.owner,
                        key=v.key,
                        environment_scope=v.environment_scope,
                        protected=v.protected,
                    )
                    for v in (self.facts.variables if self.facts else ())
                    if f"{v.owner}:{v.key}" in node.carriers
                ),
            )
        )
        return (
            RecordStatus.APPLIED,
            "replacement installed in every credential consumer",
            {"credential": node.name},
            {
                "receipt_id": receipt.receipt_id,
                "replacement_id": receipt.replacement_id,
                "old_revoked": receipt.old_revoked,
            },
            receipt.evidence_url,
        )

    def _credential_projects(self, node: SecretNode) -> set[int]:
        from defuse.model.graph import EdgeKind, JobNode

        projects = {node.project_id} if node.project_id is not None else set()
        for edge in self.graph.into(node.id, EdgeKind.CAN_READ):
            job = self.graph.node(edge.src)
            if isinstance(job, JobNode):
                projects.add(job.project_id)
        if not projects:
            raise ValueError("credential has no sandbox project scope")
        return projects

    async def _hooks(self, action: Action) -> Result:
        project = int(action.target.split(":", 1)[1])
        metadata = await self.ctx.gl.get(f"/api/v4/projects/{project}")
        ref = str(metadata.get("default_branch") or "main")
        paths = {v for k, v in action.params if k == "path"}
        edits = []
        for path in sorted(paths):
            current = await self.repo.read(project, path, ref)
            if current is None:
                continue
            cleaned = clean_hook(path, current, self.ioc)
            if cleaned != current:
                edits.append(FileEdit(action="update", file_path=path, content=cleaned))
        title = "Remove planted hooks"
        description = f"Incident {self.ctx.incident_id}: remove only matched IOC hooks."
        if self.settings.duo_enabled and edits:
            from defuse.automate.flows import DuoRunner, FlowRequest

            cached = self.state.get(action.id + ".draft")
            if cached is None:
                draft = await DuoRunner(self.settings.duo_timeout).draft(
                    FlowRequest(
                        flow="hook-sweeper",
                        incident_id=self.ctx.incident_id,
                        project_id=project,
                        goal={
                            "paths": sorted(paths),
                            "hook_signatures": [
                                s.model_dump(mode="json") for s in self.ioc.hook_signatures
                            ],
                        },
                        allowed_paths=(),
                        expected_edits=(),
                    )
                )
                cached = {"title": draft.title, "description": draft.description}
                await self._checkpoint(action.id + ".draft", cached)
            title, description = str(cached["title"]), str(cached["description"])
        changed, url = await self.repo.apply(
            project,
            self.ctx.incident_id,
            "hooks",
            title,
            description=description,
            edits=tuple(edits),
            allowed=paths,
        )
        return (
            RecordStatus.APPLIED if changed else RecordStatus.ALREADY_SATISFIED,
            "matched hooks removed and target branch checked",
            {},
            {"paths": sorted(paths)},
            url,
        )

    async def _pin(self, action: Action) -> Result:
        project = int(action.target.split(":", 1)[1])
        baseline = self.settings.known_good_refs.get(str(project))
        if baseline is None:
            raise PendingChange("configure a trusted known-good commit for this project")
        import re

        if not re.fullmatch(r"[0-9a-f]{40}", baseline):
            raise ValueError("known-good baseline must be an immutable 40-character commit SHA")
        metadata = await self.ctx.gl.get(f"/api/v4/projects/{project}")
        ref = str(metadata.get("default_branch") or "main")
        current = await self.repo.read(project, "package.json", ref)
        manifest = await self.repo.read(project, "package.json", baseline)
        lock = await self.repo.read(project, "package-lock.json", baseline)
        if current is None or manifest is None or lock is None:
            raise PendingChange("trusted baseline must contain package.json and package-lock.json")
        rogue = {(n.name, n.version) for n in self.graph.nodes if isinstance(n, PackageVersionNode)}
        edits = trusted_pin_edits(current, manifest, lock, self.ioc, rogue)
        # Exact comparison keeps retries from creating another MR after a successful merge.
        needed = tuple(
            [e for e in edits if await self.repo.read(project, e.file_path, ref) != e.content]
        )
        changed, url = await self.repo.apply(
            project,
            self.ctx.incident_id,
            "pins",
            "Pin trusted dependency baseline",
            description=f"Incident {self.ctx.incident_id}; baseline {baseline}.",
            edits=needed,
            allowed={"package.json", "package-lock.json"},
        )
        return (
            RecordStatus.APPLIED if changed else RecordStatus.ALREADY_SATISFIED,
            "trusted manifest and lockfile applied",
            {},
            {"baseline": baseline},
            url,
        )

    async def _agent(self, action: Action) -> Result:
        project, user = action.param("project_id"), action.param("user_id")
        if project is None or user is None:
            raise PendingChange("agent isolation requires project and user metadata")
        pid, uid = int(project), int(user)
        direct = f"/api/v4/projects/{pid}/members/{uid}"
        effective = f"/api/v4/projects/{pid}/members/all/{uid}"
        if action.kind == ActionKind.BLOCK_AGENT_IDENTITY:
            try:
                member = await self.ctx.gl.get(direct)
            except NotFound as exc:
                raise PendingChange(
                    "inherited agent membership cannot be reduced at project scope"
                ) from exc
            original = self.state.get(action.id, {}).get("original_access_level")
            if not isinstance(original, int):
                original = int(member["access_level"])
            if original >= 40:
                raise PendingChange("refusing automatic role changes to a Maintainer or Owner")
            await self._checkpoint(action.id, {"original_access_level": original})
            if original > 20:
                await self.ctx.gl.mutate("PUT", direct, project=pid, json_body={"access_level": 20})
            actual = await self.ctx.gl.get(effective)
            if int(actual["access_level"]) > 20:
                raise PendingChange(
                    "inherited permissions still allow agent writes; isolation incomplete"
                )
            return (
                RecordStatus.APPLIED,
                "agent project writes disabled",
                {"access_level": original},
                {"access_level": 20},
                None,
            )
        block_id = action.id.replace("restore_agent_identity@", "block_agent_identity@", 1)
        before = self.state.get(block_id, {}).get("original_access_level")
        if before is None:
            record = next(
                (
                    r
                    for r in reversed(self.prior)
                    if r.action_id == block_id
                    and r.status in {RecordStatus.APPLIED, RecordStatus.ALREADY_SATISFIED}
                ),
                None,
            )
            before = record.before.get("access_level") if record else None
        if not isinstance(before, int) or not 0 <= before <= 30:
            raise PendingChange("original agent permissions are not recorded")
        await self.ctx.gl.mutate("PUT", direct, project=pid, json_body={"access_level": before})
        actual = await self.ctx.gl.get(effective)
        if int(actual["access_level"]) != before:
            raise PendingChange("agent permissions did not return to the recorded role")
        return (
            RecordStatus.APPLIED,
            "original agent role restored after verification",
            {"access_level": 20},
            {"access_level": before},
            None,
        )

    async def _checkpoint(self, key: str, payload: dict[str, StateValue]) -> None:
        self.state[key] = payload
        if self.checkpoint is not None:
            await self.checkpoint(key, payload)

    async def _rebuild(self, action: Action) -> Result:
        pid = int(action.target.split(":", 1)[1])
        saved = self.state.get(action.id, {})
        pipeline = saved.get("pipeline")
        if not isinstance(pipeline, int):
            result = await self.ctx.gl.mutate(
                "POST",
                f"/api/v4/projects/{pid}/pipeline",
                project=pid,
                json_body={
                    "ref": action.param("ref") or "main",
                    "variables": [
                        {"key": "DEFUSE_CLEAN_REBUILD", "value": "1"},
                        {"key": "DEFUSE_INCIDENT_ID", "value": self.ctx.incident_id},
                    ],
                },
            )
            pipeline = int(result["id"])
            await self._checkpoint(action.id, {"pipeline": pipeline})
        deadline = monotonic() + self.settings.action_timeout
        while True:
            current = await self.ctx.gl.get(f"/api/v4/projects/{pid}/pipelines/{pipeline}")
            if current.get("status") == "success":
                jobs = [
                    j
                    async for j in self.ctx.gl.paginate(
                        f"/api/v4/projects/{pid}/pipelines/{pipeline}/jobs"
                    )
                ]
                paused = {
                    int(r.target.split(":", 1)[1])
                    for r in self.prior
                    if r.kind == ActionKind.PAUSE_RUNNER
                    and r.status in {RecordStatus.APPLIED, RecordStatus.ALREADY_SATISFIED}
                }
                if any(j.get("runner", {}).get("id") in paused for j in jobs if j.get("runner")):
                    raise ValueError("rebuild used an exposed runner")
                if not jobs:
                    raise PendingChange(
                        "rebuild pipeline has no job evidence", current.get("web_url")
                    )
                return (
                    RecordStatus.APPLIED,
                    "clean rebuild pipeline succeeded",
                    {},
                    {"pipeline": pipeline},
                    current.get("web_url"),
                )
            if current.get("status") in {"failed", "canceled", "skipped"}:
                raise ValueError("clean rebuild pipeline did not succeed")
            if monotonic() >= deadline:
                raise PendingChange("clean rebuild is still running", current.get("web_url"))
            await asyncio.sleep(2)
