from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from defuse.cli import app
from defuse.config import get_settings
from defuse.scenario import scenario_ioc
from defuse.store.repository import Store

runner = CliRunner()


@pytest.fixture
def isolated_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("DEFUSE_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/cli.db")
    monkeypatch.setenv("DEFUSE_RECORDS_DIR", str(tmp_path / "records"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_plan_requires_explicit_scenario_or_live_inputs(isolated_cli: Path) -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2
    assert "--scenario" in result.output


def test_plan_uses_the_supplied_ioc(isolated_cli: Path) -> None:
    ioc = scenario_ioc().model_copy(update={"id": "custom-ioc"})
    path = isolated_cli / "ioc.json"
    path.write_text(ioc.model_dump_json())
    result = runner.invoke(app, ["plan", str(path), "--scenario", "--incident", "custom"])
    assert result.exit_code == 0, result.output

    async def saved_id() -> str:
        store = Store(get_settings().database_url)
        try:
            row = await store.get_incident_row("custom")
            assert row is not None
            assert row.plan is not None
            return str(row.plan["ioc_id"])
        finally:
            await store.dispose()

    assert asyncio.run(saved_id()) == "custom-ioc"


def test_act_refuses_an_unknown_incident(isolated_cli: Path) -> None:
    result = runner.invoke(app, ["act", "isolate_host@host:x", "--incident", "unknown"])
    assert result.exit_code == 2
    assert "no saved plan" in result.output


def test_act_blocks_unfinished_dependencies_and_exits_nonzero(isolated_cli: Path) -> None:
    assert runner.invoke(app, ["plan", "--scenario", "--incident", "blocked"]).exit_code == 0
    result = runner.invoke(
        app, ["act", "snapshot_evidence@host:defuse-runner-1", "--incident", "blocked"]
    )
    assert result.exit_code == 1
    records = list((isolated_cli / "records").glob("*.json"))
    record = json.loads(records[0].read_text())
    assert record["status"] == "needs_operator"
    assert "isolate_host" in record["detail"]


def test_repeated_action_uses_the_saved_ledger(isolated_cli: Path) -> None:
    assert runner.invoke(app, ["plan", "--scenario", "--incident", "retry"]).exit_code == 0
    args = ["act", "isolate_host@host:defuse-runner-1", "--incident", "retry"]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.exit_code == second.exit_code == 0
    assert "already_satisfied" in second.output


def test_naive_baseline_cannot_be_compiled_for_execution(isolated_cli: Path) -> None:
    result = runner.invoke(
        app, ["plan", "--scenario", "--naive", "--out", str(isolated_cli / "unsafe.yml")]
    )
    assert result.exit_code == 2
    assert not (isolated_cli / "unsafe.yml").exists()


def test_each_compiled_action_works_in_a_fresh_cli_process_context(isolated_cli: Path) -> None:
    from defuse.graph import build_exposure_graph
    from defuse.plan.planner import plan_incident
    from defuse.scenario import scenario_facts

    assert runner.invoke(app, ["plan", "--scenario", "--incident", "separate-jobs"]).exit_code == 0
    plan = plan_incident(build_exposure_graph(scenario_ioc(), scenario_facts()))
    for layer in plan.layers:
        for action_id in layer:
            result = runner.invoke(app, ["act", action_id, "--incident", "separate-jobs"])
            assert result.exit_code == 0, result.output

    async def status() -> str:
        store = Store(get_settings().database_url)
        try:
            row = await store.get_incident_row("separate-jobs")
            assert row is not None
            return row.status
        finally:
            await store.dispose()

    assert asyncio.run(status()) == "verified"


def test_dry_run_after_completion_does_not_change_incident_status(isolated_cli: Path) -> None:
    assert runner.invoke(app, ["plan", "--scenario", "--incident", "dry-status"]).exit_code == 0
    args = ["act", "isolate_host@host:defuse-runner-1", "--incident", "dry-status", "--dry-run"]
    assert runner.invoke(app, args).exit_code == 0

    async def status() -> str:
        store = Store(get_settings().database_url)
        try:
            row = await store.get_incident_row("dry-status")
            assert row is not None
            return row.status
        finally:
            await store.dispose()

    assert asyncio.run(status()) == "scoped"
