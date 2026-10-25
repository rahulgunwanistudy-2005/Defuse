import json
from pathlib import Path

from defuse.detector import main, provenance_mismatches, scan_repo


def test_clean_repo_passes(tmp_path: Path) -> None:
    assert scan_repo(tmp_path) == []
    assert main([str(tmp_path)]) == 0


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
    assert main([str(tmp_path)]) == 1


def test_scenario_has_a_provenance_mismatch() -> None:
    assert any("2.4.1" in m for m in provenance_mismatches())
