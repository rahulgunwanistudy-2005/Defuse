"""The worm detector that the product pipeline's `detect` job runs.

Exits non-zero when a lockfile in the repo resolves a version matching any active IOC, or when a
provenance mismatch is found in the scenario facts. A non-zero exit on a human's routine push is
what fires the incident-commander flow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import structlog

from defuse.collect.lockfile import parse_npm_lockfile
from defuse.scenario import scenario_facts, scenario_ioc

log = structlog.get_logger(__name__)


def scan_repo(root: Path) -> list[tuple[str, str, str]]:
    ioc = scenario_ioc()
    hits: list[tuple[str, str, str]] = []
    for lockfile in root.rglob("package-lock.json"):
        if "node_modules" in lockfile.parts:
            continue
        for name, version, path in parse_npm_lockfile(lockfile.read_text(encoding="utf-8")):
            if ioc.affected(name, version):
                hits.append((name, version, f"{lockfile}:{path}"))
    return hits


def provenance_mismatches() -> list[str]:
    ioc = scenario_ioc()
    facts = scenario_facts()
    out: list[str] = []
    for pkg in facts.published_packages:
        if not ioc.in_window(pkg.created_at):
            continue
        if not pkg.pipeline_ids or pkg.commit_exists is False:
            out.append(f"{pkg.name}@{pkg.version} published with no matching commit")
    return out


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path.cwd()
    hits = scan_repo(root)
    # Provenance uses collected facts; in this build the scenario stands in for a live scan and
    # is only consulted when explicitly enabled, so a clean repo is clean.
    mismatches = provenance_mismatches() if os.environ.get("DEFUSE_SCAN_SCENARIO") == "1" else []
    for name, version, where in hits:
        log.error("detector.ioc_match", package=name, version=version, where=where)
    for m in mismatches:
        log.error("detector.provenance_mismatch", detail=m)
    if hits or mismatches:
        print(f"DETECTOR: {len(hits)} IOC match(es), {len(mismatches)} provenance mismatch(es)")
        return 1
    print("DETECTOR: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
