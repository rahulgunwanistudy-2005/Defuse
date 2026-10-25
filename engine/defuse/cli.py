"""The `defuse` CLI. Thin: it parses, wires dependencies and calls into the engine."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import structlog
import typer

from defuse.collect.gitlab import GitLabClient
from defuse.config import Settings, get_settings
from defuse.logging import configure_logging
from defuse.model.ioc import IOCSet

if TYPE_CHECKING:
    from defuse.collect.memory_backend import MemoryGitLab

app = typer.Typer(add_completion=False, help="Worm containment for GitLab CI.")
log = structlog.get_logger(__name__)


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
    except ValidationError as exc:
        for error in exc.errors():
            loc = ".".join(str(p) for p in error["loc"])
            typer.echo(f"{loc}: {error['msg']}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"ok: {loaded.id} ({len(loaded.packages)} package(s))")


@app.command()
def graph(
    ioc: Annotated[Path, typer.Argument()],
    scenario: Annotated[bool, typer.Option(help="use the built-in sandbox scenario facts")] = False,
) -> None:
    """Build the exposure graph and print its deterministic JSON."""

    from defuse.graph import build_exposure_graph
    from defuse.scenario import scenario_facts

    if not scenario:
        typer.echo("live collection needs a sandbox; use --scenario in this build", err=True)
        raise typer.Exit(2)
    built = build_exposure_graph(
        _load_ioc(ioc) if ioc.exists() else _scenario_ioc(), scenario_facts()
    )
    typer.echo(built.canonical_json())


@app.command("plan")
def plan_cmd(
    ioc: Annotated[Path, typer.Argument()] = Path("-"),
    naive: Annotated[bool, typer.Option(help="produce the revoke-everything baseline")] = False,
    scenario: Annotated[bool, typer.Option()] = True,
    out: Annotated[Path | None, typer.Option(help="write plan.gitlab-ci.yml here")] = None,
) -> None:
    """Plan containment. Prints the layered plan; --naive prints the detonator baseline."""

    from defuse.execute.compiler import CompileOptions, compile_child_pipeline
    from defuse.graph import build_exposure_graph
    from defuse.plan.planner import plan_incident, plan_naive
    from defuse.scenario import scenario_facts

    built = build_exposure_graph(_scenario_ioc(), scenario_facts())
    plan = plan_naive(built) if naive else plan_incident(built)
    for index, layer in enumerate(plan.layers):
        typer.echo(f"layer {index}:")
        for action_id in layer:
            typer.echo(f"  {plan.action(action_id).label}  [{action_id}]")
    if out is not None:
        out.write_text(compile_child_pipeline(plan, CompileOptions(incident_id="cli")))
        typer.echo(f"wrote {out}")


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
    from defuse.collect.memory_backend import MemoryGitLab
    from defuse.execute.executors import ExecutionContext, execute
    from defuse.execute.gcp import RecordingGcpOps
    from defuse.execute.runner import enrich
    from defuse.graph import build_exposure_graph
    from defuse.plan.planner import plan_incident
    from defuse.scenario import scenario_facts

    settings = get_settings()
    ioc, facts = _scenario_ioc(), scenario_facts()
    plan = enrich(plan_incident(build_exposure_graph(ioc, facts)), ioc, facts)
    backend = MemoryGitLab()
    client = _memory_client(settings, backend, dry_run)
    async with client:
        ctx = ExecutionContext(
            incident_id,
            client,
            RecordingGcpOps({h: [settings.live_tag] for h in ("defuse-runner-1",)}),
            actor=settings.actor,
            dry_run=dry_run,
            isolation_tag=settings.isolation_tag,
            live_tag=settings.live_tag,
        )
        record = await execute(ctx, plan.action(action_id))
    settings.records_dir.mkdir(parents=True, exist_ok=True)
    path = settings.records_dir / f"{incident_id}-{_slug(action_id)}.json"
    path.write_text(record.model_dump_json(indent=2))
    typer.echo(f"{record.kind.value} {record.target}: {record.status.value} -> {path}")


def _memory_client(settings: Settings, backend: MemoryGitLab, dry_run: bool) -> GitLabClient:
    return GitLabClient(
        settings.gitlab_url,
        settings.gitlab_token,
        settings.namespaces,
        dry_run=dry_run,
        transport=backend.transport(),
    )


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
