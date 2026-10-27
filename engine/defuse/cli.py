"""The `defuse` CLI. Thin: it parses, wires dependencies and calls into the engine."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import structlog
import typer

from defuse.collect.gitlab import GitLabClient
from defuse.config import get_settings
from defuse.logging import configure_logging
from defuse.model.facts import CollectedFacts
from defuse.model.incident import (
    ActionRecord,
    Incident,
    IncidentOrigin,
    IncidentStatus,
    RecordStatus,
)
from defuse.model.ioc import IOCSet
from defuse.model.plan import Plan
from defuse.workflow import app as workflow_app

app = typer.Typer(add_completion=False, help="Worm containment for GitLab CI.")
log = structlog.get_logger(__name__)


app.add_typer(workflow_app, name="workflow")


def _load_ioc(path: Path) -> IOCSet:
    return IOCSet.model_validate_json(path.read_text())


@app.command()
def schema(action: Annotated[str, typer.Argument()] = "write") -> None:
    """Write or print the IOC JSON Schema."""

    from defuse.model.schema import ioc_schema_json, write_schema

    if action == "write":
        typer.echo(f"wrote {write_schema()}")
    else:
        typer.echo(ioc_schema_json())


@app.command()
def validate(ioc: Annotated[Path, typer.Argument(help="path to an ioc.json")]) -> None:
    """Validate an IOC file against the schema. Exit 1 and say which field on failure."""

    from pydantic import ValidationError

    try:
        loaded = _load_ioc(ioc)
    except OSError as exc:
        typer.echo(f"cannot read IOC file: {exc}", err=True)
        raise typer.Exit(1) from exc
    except ValidationError as exc:
        for error in exc.errors():
            loc = ".".join(str(p) for p in error["loc"])
            typer.echo(f"{loc}: {error['msg']}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"ok: {loaded.id} ({len(loaded.packages)} package(s))")


@app.command()
def graph(
    ioc: Annotated[Path, typer.Argument()] = Path("-"),
    *,
    scenario: Annotated[bool, typer.Option(help="use the built-in sandbox facts")] = False,
    namespace: str | None = None,
) -> None:
    """Collect sandbox metadata and print the deterministic exposure graph."""
    from defuse.collect.collector import Collector
    from defuse.graph import build_exposure_graph
    from defuse.scenario import scenario_facts

    settings = get_settings()
    try:
        if str(ioc) == "-":
            if not scenario:
                raise ValueError("provide an IOC file and --namespace, or use --scenario")
            loaded = _scenario_ioc()
        else:
            loaded = _load_ioc(ioc)

        async def collect() -> CollectedFacts:
            if not namespace or settings.gitlab_token is None:
                raise ValueError(
                    "live graph collection requires --namespace and DEFUSE_GITLAB_TOKEN"
                )
            async with GitLabClient(
                settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=True
            ) as client:
                await client.assert_mutable(namespace)
                return await Collector(client, settings, loaded).collect(namespace)

        facts = scenario_facts() if scenario else asyncio.run(collect())
        typer.echo(build_exposure_graph(loaded, facts).canonical_json())
    except (OSError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


@app.command("plan")
def plan_cmd(
    ioc: Annotated[Path, typer.Argument()] = Path("-"),
    *,
    naive: Annotated[bool, typer.Option(help="produce the revoke-everything baseline")] = False,
    scenario: Annotated[
        bool, typer.Option(help="use fixture data, without live mutations")
    ] = False,
    out: Annotated[Path | None, typer.Option(help="write plan.gitlab-ci.yml here")] = None,
    namespace: Annotated[str | None, typer.Option(help="sandbox namespace to collect")] = None,
    incident: Annotated[str, typer.Option(help="incident ID saved with the plan")] = "cli",
    dry_run: Annotated[bool, typer.Option()] = False,
) -> None:
    """Plan containment. Prints the layered plan; --naive prints the detonator baseline."""

    from defuse.execute.compiler import CompileOptions, compile_child_pipeline

    if naive and out is not None:
        typer.echo(
            "the naive baseline is replay-only and cannot be compiled for execution", err=True
        )
        raise typer.Exit(2)
    plan = asyncio.run(_plan(ioc, scenario, namespace, incident, naive))
    for index, layer in enumerate(plan.layers):
        typer.echo(f"layer {index}:")
        for action_id in layer:
            typer.echo(f"  {plan.action(action_id).label}  [{action_id}]")
    if out is not None:
        settings = get_settings()
        out.write_text(
            compile_child_pipeline(
                plan,
                CompileOptions(
                    incident_id=incident,
                    dry_run=dry_run,
                    image=settings.executor_image,
                    wif_audience=settings.wif_audience,
                    wif_provider=settings.wif_provider,
                    gcp_service_account=settings.gcp_service_account,
                    record_project_id=settings.record_project_id,
                ),
            )
        )
        typer.echo(f"wrote {out}")


async def _plan(
    path: Path, scenario: bool, namespace: str | None, incident_id: str, naive: bool
) -> Plan:
    from defuse.collect.collector import Collector
    from defuse.execute.runner import enrich
    from defuse.graph import build_exposure_graph
    from defuse.plan.planner import plan_incident, plan_naive
    from defuse.scenario import scenario_facts
    from defuse.store.repository import Store

    settings = get_settings()
    if str(path) == "-":
        if not scenario:
            typer.echo(
                "provide an IOC file and --namespace, or use --scenario for the demo", err=True
            )
            raise typer.Exit(2)
        ioc = _scenario_ioc()
    else:
        try:
            ioc = _load_ioc(path)
        except (OSError, ValueError) as exc:
            typer.echo(f"invalid IOC file: {exc}", err=True)
            raise typer.Exit(2) from exc
    facts: CollectedFacts
    if scenario:
        facts = scenario_facts()
    else:
        if not namespace or settings.gitlab_token is None:
            typer.echo("live planning requires --namespace and DEFUSE_GITLAB_TOKEN", err=True)
            raise typer.Exit(2)
        async with GitLabClient(
            settings.gitlab_url, settings.gitlab_token, settings.namespaces, dry_run=True
        ) as client:
            await client.assert_mutable(namespace)
            facts = await Collector(client, settings, ioc).collect(namespace)
    built = build_exposure_graph(ioc, facts)
    safe = enrich(plan_incident(built), ioc, facts)
    baseline = plan_naive(built)
    if naive:
        return baseline
    now = datetime.now(UTC)
    record = Incident(
        id=incident_id,
        title=ioc.title,
        ioc_id=ioc.id,
        origin=IncidentOrigin.SCENARIO if scenario else IncidentOrigin.ADVISORY,
        status=IncidentStatus.SCOPED,
        namespace=facts.namespace,
        created_at=now,
        detected_at=now,
    )
    store = Store(settings.database_url)
    try:
        await store.create_all()
        existing = await store.get_incident_row(incident_id)
        if existing is not None and await store.get_actions(incident_id):
            typer.echo("incident already has action records; use a new incident ID", err=True)
            raise typer.Exit(2)
        await store.upsert_incident(record)
        await store.save_scope(incident_id, ioc, built, safe, baseline)
        await store.put_artifact(incident_id, "facts.before", facts.model_dump(mode="json"))
    finally:
        await store.dispose()
    return safe


@app.command()
def explain(action_id: Annotated[str, typer.Argument()]) -> None:
    """Explain why an action sits where it does in the scenario plan."""

    from defuse.graph import build_exposure_graph
    from defuse.plan.planner import explain as explain_action
    from defuse.plan.planner import plan_incident
    from defuse.scenario import scenario_facts

    plan = plan_incident(build_exposure_graph(_scenario_ioc(), scenario_facts()))
    typer.echo(json.dumps(explain_action(plan, action_id).model_dump(mode="json"), indent=2))


@app.command()
def act(
    action_id: Annotated[str, typer.Argument()],
    incident: Annotated[str, typer.Option("--incident")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Execute one action by id. This is what each containment pipeline job runs."""

    asyncio.run(_act(action_id, incident, dry_run))


async def _act(action_id: str, incident_id: str, dry_run: bool) -> None:
    import httpx

    from defuse.automate.sandbox import BASELINE, SandboxGitLab
    from defuse.execute.executors import ExecutionContext
    from defuse.execute.gcp import GcloudOps, RecordingGcpOps
    from defuse.execute.runner import SUCCESS, run_plan
    from defuse.service import IncidentService
    from defuse.store.repository import Store

    settings = get_settings()
    store = Store(settings.database_url)
    sandbox_lease = None
    lease_entered = False
    verification_http = None
    try:
        await store.create_all()
        row = await store.get_incident_row(incident_id)
        if row is None or row.plan is None:
            typer.echo("incident has no saved plan; run defuse plan first", err=True)
            raise typer.Exit(2)
        plan = Plan.model_validate(row.plan)
        if not any(
            row.namespace == ns or row.namespace.startswith(ns + "/") for ns in settings.namespaces
        ):
            typer.echo("incident is outside configured sandbox namespaces", err=True)
            raise typer.Exit(2)
        try:
            action = plan.action(action_id)
        except KeyError as exc:
            typer.echo(f"action is not in the saved incident plan: {action_id}", err=True)
            raise typer.Exit(2) from exc
        prior = [ActionRecord.model_validate(r) for r in await store.get_actions(incident_id)]
        completed = {r.action_id for r in prior if r.status in SUCCESS and not r.dry_run}
        simulation = row.origin == IncidentOrigin.SCENARIO.value
        backend = SandboxGitLab() if simulation else None
        if backend is not None:
            sandbox_lease = store.action_lock(incident_id, "sandbox-state")
            await sandbox_lease.__aenter__()
            lease_entered = True
            state = await store.get_artifact(incident_id, "sandbox.state")
            if state is not None:
                backend.restore(state)
            settings = settings.model_copy(
                update={
                    "known_good_refs": {str(p): BASELINE for p in (101, 102, 103)},
                    "sandbox_namespaces": row.namespace,
                    "auto_merge_remediation": True,
                    "sinkhole_url": "https://gitlab.test",
                }
            )
            verification_http = httpx.AsyncClient(transport=backend.transport())
        if not simulation and settings.gitlab_token is None:
            typer.echo("live actions require DEFUSE_GITLAB_TOKEN", err=True)
            raise typer.Exit(2)
        if not simulation and not dry_run and not settings.gcp_project:
            typer.echo("live actions require DEFUSE_GCP_PROJECT", err=True)
            raise typer.Exit(2)
        client = GitLabClient(
            settings.gitlab_url,
            None if simulation else settings.gitlab_token,
            settings.namespaces,
            dry_run=dry_run,
            transport=backend.transport() if backend else None,
        )
        ctx = ExecutionContext(
            incident_id,
            client,
            backend.gcp
            if backend
            else RecordingGcpOps()
            if dry_run
            else GcloudOps(settings.gcp_project or "", settings.gcp_zone),
            actor=settings.actor,
            dry_run=dry_run,
            isolation_tag=settings.isolation_tag,
            live_tag=settings.live_tag,
            simulation=simulation,
        )
        async with client:
            before_payload = await store.get_artifact(incident_id, "facts.before")
            service = IncidentService(
                store,
                settings,
                transport=backend.transport() if backend else None,
                gcp=backend.gcp if backend else None,
                broker=backend.broker() if backend else None,
                facts_provider=backend.facts if backend else None,
                verification_http=verification_http,
            )
            before_facts = CollectedFacts.model_validate(before_payload) if before_payload else None
            if before_facts is not None and row.ioc_set is not None:
                await service.configure_context(
                    ctx,
                    Incident.model_validate(row.data),
                    IOCSet.model_validate(row.ioc_set),
                    before_facts,
                    prior,
                )
            if action_id in completed and not dry_run:
                now = ctx.clock()
                record = ActionRecord(
                    incident_id=incident_id,
                    action_id=action.id,
                    kind=action.kind,
                    target=action.target,
                    actor=settings.actor,
                    status=RecordStatus.ALREADY_SATISFIED,
                    dry_run=False,
                    detail="already completed in the incident ledger",
                    started_at=now,
                    finished_at=now,
                )
                await store.append_action(record)
            else:
                single = plan.model_copy(
                    update={
                        "actions": (action,),
                        "layers": ((action_id,),),
                        "completed": tuple(sorted(completed)),
                    }
                )

                async def completed_now() -> set[str]:
                    return {
                        r["action_id"]
                        for r in await store.get_actions(incident_id)
                        if r["status"] in {s.value for s in SUCCESS} and not r["dry_run"]
                    }

                records = await run_plan(
                    ctx,
                    single,
                    store.append_action,
                    claim=lambda aid: store.action_lock(incident_id, aid),
                    completed=completed_now,
                )
                record = records[0]
        if backend is not None and not dry_run:
            await store.put_artifact(incident_id, "sandbox.state", backend.snapshot())
        await store.emit(incident_id, "action", record.model_dump(mode="json"), record.detail)
        status = (
            IncidentStatus.FAILED
            if record.status == RecordStatus.FAILED
            else IncidentStatus.CONTAINING
        )
        if not dry_run and (
            row.status != IncidentStatus.VERIFIED.value or record.status not in SUCCESS
        ):
            await store.upsert_incident(
                Incident.model_validate(row.data).model_copy(update={"status": status})
            )
        checked = await store.get_artifact(incident_id, "verification.latest")
        after = await store.get_artifact(incident_id, "facts.after")
        if (
            not dry_run
            and checked is not None
            and after is not None
            and before_facts is not None
            and row.ioc_set is not None
        ):
            from defuse.model.incident import Verification

            await service.verify(
                Incident.model_validate(row.data),
                IOCSet.model_validate(row.ioc_set),
                before_facts,
                CollectedFacts.model_validate(after),
                [record],
                checked_verification=Verification.model_validate(checked),
            )
        settings.records_dir.mkdir(parents=True, exist_ok=True)
        path = settings.records_dir / f"{_slug(incident_id)}-{_slug(action_id)}-{uuid4().hex}.json"
        path.write_text(record.model_dump_json(indent=2))
        typer.echo(f"{record.kind.value} {record.target}: {record.status.value} -> {path}")
        if record.status not in SUCCESS and record.status != RecordStatus.DRY_RUN:
            raise typer.Exit(1)
    finally:
        if verification_http is not None:
            await verification_http.aclose()
        if sandbox_lease is not None and lease_entered:
            await sandbox_lease.__aexit__(None, None, None)
        await store.dispose()


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "0.0.0.0",  # noqa: S104 - container binds all
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """Run the API server."""

    import uvicorn

    configure_logging()
    uvicorn.run("defuse.api.app:create_app", factory=True, host=host, port=port)


@app.command()
def demo() -> None:
    """Seed the scenario incident into the configured database and print its metrics."""

    asyncio.run(_demo())


async def _demo() -> None:
    from defuse.api.seed import SCENARIO_ID, seed_scenario
    from defuse.store.repository import Store

    settings = get_settings()
    store = Store(settings.database_url)
    await store.create_all()
    await seed_scenario(store, settings.model_copy(update={"seed_scenario": True}))
    row = await store.get_incident_row(SCENARIO_ID)
    if row is None:
        raise typer.Exit(1)
    typer.echo(
        json.dumps(
            {"incident": SCENARIO_ID, "status": row.status, "metrics": row.metrics}, indent=2
        )
    )
    await store.dispose()


def _scenario_ioc() -> IOCSet:
    from defuse.scenario import scenario_ioc

    return scenario_ioc()


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in value).strip("-")[:80]


if __name__ == "__main__":
    app()
