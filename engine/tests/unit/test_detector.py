import json
from pathlib import Path

from defuse.detector import main, provenance_mismatches, scan_repo
from defuse.model.ioc import AffectedPackage
from defuse.scenario import scenario_ioc


def test_clean_repo_passes(tmp_path: Path) -> None:
    assert scan_repo(tmp_path) == []
    ioc = tmp_path / "ioc.json"
    ioc.write_text(scenario_ioc().model_dump_json())
    assert main([str(tmp_path), "--ioc", str(ioc)]) == 0


def test_affected_lockfile_is_flagged(tmp_path: Path) -> None:
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "node_modules/@defuse-sandbox/loader": {
                "name": "@defuse-sandbox/loader",
                "version": "1.0.3",
            }
        },
    }
    (tmp_path / "package-lock.json").write_text(json.dumps(lock))
    hits = scan_repo(tmp_path)
    assert hits
    assert hits[0][0] == "@defuse-sandbox/loader"
    assert main([str(tmp_path), "--scenario"]) == 1


def test_scenario_has_a_provenance_mismatch() -> None:
    assert any("2.4.1" in m for m in provenance_mismatches())


def test_detector_uses_committed_active_ioc_files(tmp_path: Path) -> None:
    path = tmp_path / "incidents" / "42" / "ioc.json"
    path.parent.mkdir(parents=True)
    ioc = scenario_ioc().model_copy(
        update={"packages": (AffectedPackage(name="custom-package", versions=("9.0.0",)),)}
    )
    path.write_text(ioc.model_dump_json())
    lock = {"lockfileVersion": 3, "packages": {"node_modules/custom-package": {"version": "9.0.0"}}}
    (tmp_path / "package-lock.json").write_text(json.dumps(lock))
    assert main([str(tmp_path)]) == 1


def test_detector_refuses_without_active_iocs(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
