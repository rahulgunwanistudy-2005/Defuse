"""The worm detector that the product pipeline's `detect` job runs.

Exits non-zero when a lockfile in the repo resolves a version matching any active IOC, or when a
provenance mismatch is found in the scenario facts. A non-zero exit on a human's routine push is
what fires the incident-commander flow.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import structlog

from defuse.collect.lockfile import parse_npm_lockfile
from defuse.model.ioc import IOCSet
from defuse.scenario import scenario_facts, scenario_ioc

log = structlog.get_logger(__name__)


def scan_repo(root: Path, iocs: Sequence[IOCSet] | None = None) -> list[tuple[str, str, str]]:
    active = (scenario_ioc(),) if iocs is None else iocs
    hits: list[tuple[str, str, str]] = []
    for lockfile in root.rglob("package-lock.json"):
        if "node_modules" in lockfile.parts:
            continue
        for name, version, path in parse_npm_lockfile(lockfile.read_text(encoding="utf-8")):
            if any(ioc.affected(name, version) for ioc in active):
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
    parser = argparse.ArgumentParser(description="Scan lockfiles against validated active IOCs")
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--ioc", type=Path, action="append", default=[])
    parser.add_argument("--scenario", action="store_true", help="use fixture IOC and provenance")
    args = parser.parse_args(argv)
    paths = args.ioc or sorted((args.root / "incidents").glob("**/ioc.json"))
    try:
        iocs = [IOCSet.model_validate_json(path.read_text()) for path in paths]
    except (OSError, ValueError) as exc:
        print(f"DETECTOR: invalid IOC file: {exc}", file=sys.stderr)
        return 2
    if args.scenario:
        iocs.append(scenario_ioc())
    if not iocs:
        print(
            "DETECTOR: no active IOC files; provide --ioc or explicitly use --scenario",
            file=sys.stderr,
        )
        return 2
    hits = scan_repo(args.root, iocs)
    mismatches = provenance_mismatches() if args.scenario else []
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
