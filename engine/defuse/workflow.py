"""Complete incident CLI workflow and schema-validated flow boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from pydantic import Field, field_validator

from defuse.automate.flows import DuoRunner, FlowRequest
from defuse.automate.models import StrictModel
from defuse.config import Settings, get_settings
from defuse.model.incident import Incident, IncidentOrigin, IncidentStatus
from defuse.model.ioc import IOCSet
from defuse.service import IncidentService
from defuse.store.repository import Store

app = typer.Typer(help="Incident workflows, flow validation and evidence export.")


class IncidentRequest(StrictModel):
    incident_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    ioc_path: str
    namespace: str
    detected_at: datetime
    first_exposure_at: datetime | None = None
    work_item_url: str | None = None
    pipeline_url: str | None = None

    @field_validator("detected_at", "first_exposure_at")
    @classmethod
    def timezone_required(cls, timestamp: datetime | None) -> datetime | None:
        if timestamp is not None and timestamp.tzinfo is None:
            raise ValueError("incident timestamps must carry a timezone")
        return timestamp

    @field_validator("ioc_path")
    @classmethod
    def safe_ioc_path(cls, path: str) -> str:
        from defuse.automate.models import FileEdit

        FileEdit(action="delete", file_path=path)
        if not path.startswith("incidents/") or not path.endswith("/ioc.json"):
            raise ValueError("IOC path must be incidents/<id>/ioc.json")
        return path


async def run_incident(
    settings: Settings,
    ioc: IOCSet,
    incident_id: str,
    namespace: str,
    *,
    scenario: bool = False,
    dry_run: bool = False,
    detected_at: datetime | None = None,
) -> dict[str, Any]:
    from defuse.automate.sandbox import BASELINE, SandboxGitLab

    backend = SandboxGitLab() if scenario else None
    if backend is not None:
        settings = settings.model_copy(
            update={
                "known_good_refs": {str(p): BASELINE for p in (101, 102, 103)},
                "sandbox_namespaces": "defuse-sandbox",
                "auto_merge_remediation": True,
                "sinkhole_url": "https://gitlab.test",
                "runner_hosts": {"7": "defuse-runner-1"},
            }
        )
    store = Store(settings.database_url)
    await store.create_all()
    async with httpx.AsyncClient(transport=backend.transport() if backend else None) as http:
        service = IncidentService(
            store,
            settings,
            transport=backend.transport() if backend else None,
            gcp=backend.gcp if backend else None,
            broker=backend.broker() if backend else None,
            facts_provider=backend.facts if backend else None,
            verification_http=http,
        )
        now = datetime.now(UTC)
        incident = Incident(
            id=incident_id,
            title=ioc.title,
            ioc_id=ioc.id,
            origin=IncidentOrigin.SCENARIO if scenario else IncidentOrigin.ADVISORY,
            status=IncidentStatus.OPEN,
            namespace=namespace,
            created_at=now,
            detected_at=detected_at or now,
        )
        try:
            existing = await store.get_incident_row(incident_id)
            if existing is not None:
                if scenario:
                    raise ValueError(
                        "use a fresh scenario incident ID; modeled state is isolated per run"
                    )
                before = await store.get_artifact(incident_id, "facts.before")
                if before is None:
                    raise ValueError("existing incident has no durable collection context")
                from defuse.model.facts import CollectedFacts

                facts = CollectedFacts.model_validate(before)
                incident = Incident.model_validate(existing.data)
            else:
                facts = await service.collect(incident, ioc)
                incident = incident.model_copy(update={"created_at": datetime.now(UTC)})
                await service.scope(incident, ioc, facts)
            await service.contain(incident, ioc, facts, dry_run=dry_run)
            row = await store.get_incident_row(incident_id)
            assert row is not None  # noqa: S101
            return {
                "incident_id": incident_id,
                "mode": "sandbox-model" if scenario else "gitlab",
                "status": row.status,
                "metrics": row.metrics,
                "verification": row.verification,
                "actions": await store.get_actions(incident_id),
            }
        finally:
            await store.dispose()


@app.command("run")
def run_cmd(
    ioc: Annotated[Path | None, typer.Argument()] = None,
    *,
    namespace: str = "defuse-sandbox",
    incident: str = "local-run",
    scenario: bool = False,
    dry_run: bool = False,
    out: Path | None = None,
) -> None:
    """Collect, plan, execute, verify and restore agents; resume from the durable ledger."""
    from defuse.scenario import scenario_ioc

    try:
        if ioc is None and not scenario:
            raise ValueError("provide an IOC file, or explicitly use --scenario")
        loaded = IOCSet.model_validate_json(ioc.read_text()) if ioc else scenario_ioc()
        result = asyncio.run(
            run_incident(
                get_settings(), loaded, incident, namespace, scenario=scenario, dry_run=dry_run
            )
        )
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    if out:
        out.write_text(json.dumps(result, indent=2) + "\n")
    typer.echo(json.dumps({k: v for k, v in result.items() if k != "actions"}, indent=2))
    if not dry_run and result["status"] != "verified":
        raise typer.Exit(1)


@app.command("flow")
def flow_cmd(request: Path, *, output: Path | None = None, run: bool = False) -> None:
    """Validate a stored flow output, or invoke Duo headlessly and validate its result."""
    try:
        job = FlowRequest.model_validate_json(request.read_text())
        if run:
            if not get_settings().duo_enabled:
                raise ValueError("set DEFUSE_DUO_ENABLED=true to invoke the authenticated Duo CLI")
            draft = asyncio.run(DuoRunner(get_settings().duo_timeout).draft(job))
            if output is None:
                raise ValueError("--output is required when running a flow")
            output.write_text(draft.model_dump_json(indent=2) + "\n")
        else:
            if output is None:
                raise ValueError("--output is required for flow validation")
            draft = job.validate_output(output.read_text())
        typer.echo(f"validated {draft.flow}: {len(draft.edits)} deterministic edits")
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


@app.command("export")
def export_cmd(incident: str, out: Path) -> None:
    """Export the complete incident record without credential contents."""

    async def export() -> dict[str, Any]:
        store = Store(get_settings().database_url)
        try:
            row = await store.get_incident_row(incident)
            if row is None:
                raise ValueError("unknown incident")
            return {
                "incident": row.data,
                "status": row.status,
                "metrics": row.metrics,
                "verification": row.verification,
                "graph": row.graph,
                "plan": row.plan,
                "actions": await store.get_actions(incident),
                "events": await store.get_events(incident),
            }
        finally:
            await store.dispose()

    out.write_text(json.dumps(asyncio.run(export()), indent=2) + "\n")
    typer.echo(f"wrote {out}")


@app.command("prepare")
def prepare_cmd(request: Path, out: Path, repo_root: Path | None = None) -> None:
    """Validate a committed request and compile its real dynamic child pipeline."""
    job = IncidentRequest.model_validate_json(request.read_text())
    root = repo_root or next(
        (p.parent for p in request.resolve().parents if p.name == "incidents"), None
    )
    if root is None:
        raise ValueError("provide --repo-root or keep the request under incidents/")
    root = root.resolve()

    async def prepare() -> None:
        from defuse.automate.models import FileEdit
        from defuse.cli import _plan
        from defuse.execute.compiler import CompileOptions, compile_child_pipeline
        from defuse.model.plan import Plan

        FileEdit(action="delete", file_path=job.ioc_path)
        ioc_path = (root / job.ioc_path).resolve()
        if not ioc_path.is_relative_to(root) or not ioc_path.is_file():
            raise ValueError("IOC path must identify a file inside the repository")
        settings = get_settings()
        store = Store(settings.database_url)
        await store.create_all()
        try:
            existing = await store.get_incident_row(job.incident_id)
            if existing is None:
                plan = await _plan(ioc_path, False, job.namespace, job.incident_id, False)
                existing = await store.get_incident_row(job.incident_id)
                assert existing is not None  # noqa: S101
                incident = Incident.model_validate(existing.data).model_copy(
                    update={
                        "detected_at": job.detected_at,
                        "first_exposure_at": job.first_exposure_at,
                        "work_item_url": job.work_item_url,
                        "pipeline_url": job.pipeline_url,
                    }
                )
                await store.upsert_incident(incident)
            else:
                if existing.plan is None:
                    raise ValueError("existing incident has no saved plan")
                loaded = IOCSet.model_validate_json(ioc_path.read_text())
                if existing.ioc_id != loaded.id or existing.namespace != job.namespace:
                    raise ValueError("request conflicts with the existing incident")
                plan = Plan.model_validate(existing.plan)
            options = CompileOptions(
                incident_id=job.incident_id,
                image=settings.executor_image,
                wif_audience=settings.wif_audience,
                wif_provider=settings.wif_provider,
                gcp_service_account=settings.gcp_service_account,
                record_project_id=settings.record_project_id,
            )
            await asyncio.to_thread(out.write_text, compile_child_pipeline(plan, options))
        finally:
            await store.dispose()

    try:
        asyncio.run(prepare())
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"wrote {out}")


@app.command("postmortem")
def postmortem_cmd(incident: str, project: int, dry_run: bool = False) -> None:
    async def publish_record() -> dict[str, Any]:
        from defuse.automate.postmortem import publish
        from defuse.collect.gitlab import GitLabClient

        settings = get_settings()
        store = Store(settings.database_url)
        try:
            async with GitLabClient(
                settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=dry_run
            ) as gl:
                return await publish(store, gl, settings, incident, project, dry_run=dry_run)
        finally:
            await store.dispose()

    typer.echo(json.dumps(asyncio.run(publish_record()), indent=2))


@app.command("apply-flow")
def apply_flow_cmd(request: Path, output: Path, dry_run: bool = False) -> None:
    """Apply a schema-validated flow draft through a checked, idempotent MR."""
    from defuse.automate.intake import apply_draft, audit_record
    from defuse.collect.gitlab import GitLabClient

    job = FlowRequest.model_validate_json(request.read_text())
    draft = job.validate_output(output.read_text())
    settings = get_settings()
    result: dict[str, Any] = {"status": "failed"}

    async def apply() -> dict[str, Any]:
        async with GitLabClient(
            settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=dry_run
        ) as gl:
            return await apply_draft(gl, settings, job, draft, dry_run=dry_run)

    try:
        result = asyncio.run(apply())
        typer.echo(json.dumps(result, indent=2))
    finally:
        audit_record(settings, job.flow, job.project_id, dry_run, result)


@app.command("intake-pipeline")
def intake_pipeline_cmd(event: Path, ioc_path: str, namespace: str, dry_run: bool = False) -> None:
    """Ignore unrelated failures; turn a qualified detector failure into an incident request."""
    from defuse.automate.intake import audit_record, intake_pipeline
    from defuse.collect.gitlab import GitLabClient

    payload = json.loads(event.read_text())
    settings = get_settings()
    result: dict[str, Any] = {"status": "failed"}

    async def consume() -> dict[str, Any]:
        async with GitLabClient(
            settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=dry_run
        ) as gl:
            return await intake_pipeline(
                gl, settings, payload, ioc_path, namespace, dry_run=dry_run
            )

    try:
        result = asyncio.run(consume())
        typer.echo(json.dumps(result, indent=2))
    finally:
        audit_record(settings, "incident-commander", int(payload["project"]["id"]), dry_run, result)


@app.command("collect")
def collect_cmd(ioc: Path, namespace: str, out: Path) -> None:
    """Record typed, metadata-only facts for replay/contract fixtures (never raw responses)."""
    loaded = IOCSet.model_validate_json(ioc.read_text())

    async def collect() -> str:
        from defuse.collect.collector import Collector
        from defuse.collect.gitlab import GitLabClient

        settings = get_settings()
        async with GitLabClient(
            settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=True
        ) as gl:
            await gl.assert_mutable(namespace)
            facts = await Collector(gl, settings, loaded).collect(namespace)
            return facts.model_dump_json(indent=2)

    out.write_text(asyncio.run(collect()) + "\n")
    typer.echo(f"wrote metadata-only facts to {out}")


@app.command("policy-check")
def policy_check_cmd(root: Path = Path("."), registry: str = "https://registry.npmjs.org") -> None:
    """Enforce committed minimum-release-age and lockfile policies before installing packages."""
    from defuse.automate.policy import DependencyPolicy, check_dependencies

    failures = []
    for path in sorted((root / ".defuse/policies").glob("*.json")):
        policy = DependencyPolicy.model_validate_json(path.read_text())
        failures.extend(asyncio.run(check_dependencies(root, policy, registry=registry)))
    if failures:
        for failure in sorted(set(failures)):
            typer.echo(failure, err=True)
        raise typer.Exit(1)
    typer.echo("dependency policies passed")
