"""Post-containment verification and Security Standard timing metrics."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from defuse.graph.build import build_exposure_graph
from defuse.model.facts import CollectedFacts
from defuse.model.graph import EdgeKind, NodeKind, PackageVersionNode
from defuse.model.incident import (
    ActionRecord,
    CheckOutcome,
    Incident,
    IncidentStatus,
    Metrics,
    RecordStatus,
    Verification,
    VerificationCheck,
)
from defuse.model.ioc import IOCSet


async def verify_containment(
    ioc: IOCSet,
    before: CollectedFacts,
    after: CollectedFacts,
    *,
    sinkhole_url: str | None = None,
    sinkhole_window: float = 120.0,
    sentinel_intact: bool | None = None,
    http: httpx.AsyncClient | None = None,
    checked_at: datetime | None = None,
) -> Verification:
    graph = build_exposure_graph(ioc, after)
    checks: list[VerificationCheck] = []

    still_resolving = [
        n.label for n in graph.by_kind(NodeKind.JOB) if graph.into(n.id, EdgeKind.RESOLVED_IN)
    ]
    checks.append(
        VerificationCheck(
            id="no_affected_resolution",
            outcome=CheckOutcome.FAILED if still_resolving else CheckOutcome.PASSED,
            detail=(
                "no job resolves an affected version"
                if not still_resolving
                else f"{len(still_resolving)} job(s) still resolve an affected version"
            ),
        )
    )

    before_rogue = {
        n.label
        for n in build_exposure_graph(ioc, before).by_kind(NodeKind.PACKAGE_VERSION)
        if isinstance(n, PackageVersionNode) and n.rogue
    }
    after_rogue = {
        n.label
        for n in graph.by_kind(NodeKind.PACKAGE_VERSION)
        if isinstance(n, PackageVersionNode) and n.rogue
    }
    new_rogue = sorted(after_rogue - before_rogue)
    checks.append(
        VerificationCheck(
            id="no_new_publishes",
            outcome=CheckOutcome.FAILED if new_rogue else CheckOutcome.PASSED,
            detail="no new rogue publishes" if not new_rogue else f"new: {', '.join(new_rogue)}",
        )
    )

    checks.append(await _sinkhole_check(sinkhole_url, sinkhole_window, http))
    checks.append(_sentinel_check(sentinel_intact))
    return Verification(checked_at=checked_at or datetime.now(UTC), checks=tuple(checks))


async def _sinkhole_check(
    url: str | None, window: float, http: httpx.AsyncClient | None
) -> VerificationCheck:
    if url is None:
        return VerificationCheck(
            id="sinkhole_quiet",
            outcome=CheckOutcome.UNVERIFIED,
            detail="no sinkhole configured",
        )
    client = http or httpx.AsyncClient(timeout=10.0)
    try:
        response = await client.get(f"{url.rstrip('/')}/beacons", params={"window": window})
        count = int(response.json().get("count", 0))
    except (httpx.HTTPError, ValueError) as exc:
        return VerificationCheck(
            id="sinkhole_quiet",
            outcome=CheckOutcome.UNVERIFIED,
            detail=f"sinkhole unreachable: {exc}",
        )
    finally:
        if http is None:
            await client.aclose()
    return VerificationCheck(
        id="sinkhole_quiet",
        outcome=CheckOutcome.PASSED if count == 0 else CheckOutcome.FAILED,
        detail=f"{count} beacon(s) in the last {window:.0f}s",
    )


def _sentinel_check(intact: bool | None) -> VerificationCheck:
    if intact is None:
        return VerificationCheck(
            id="sentinel_intact", outcome=CheckOutcome.UNVERIFIED, detail="sentinel not checked"
        )
    return VerificationCheck(
        id="sentinel_intact",
        outcome=CheckOutcome.PASSED if intact else CheckOutcome.FAILED,
        detail="sentinel directory intact" if intact else "sentinel directory was destroyed",
    )


def compute_metrics(
    incident: Incident,
    records: Sequence[ActionRecord],
    verification: Verification | None,
    *,
    llm_credits: float | None = None,
) -> Metrics:
    applied = [
        r for r in records if r.status in (RecordStatus.APPLIED, RecordStatus.ALREADY_SATISFIED)
    ]

    def span(start: datetime | None, end: datetime | None) -> float | None:
        if start is None or end is None:
            return None
        return round((end - start).total_seconds(), 1)

    first = incident.first_exposure_at
    containment_end = max((r.finished_at for r in applied), default=None)
    verified_at = verification.checked_at if verification and verification.passed else None
    return Metrics(
        time_to_detect=span(first, incident.detected_at),
        time_to_scope=span(incident.detected_at, incident.created_at),
        time_to_containment=span(incident.detected_at, containment_end),
        time_to_verified_remediation=span(incident.detected_at, verified_at),
        actions_executed=len(applied),
        llm_credits=llm_credits,
    )


def next_status(verification: Verification | None) -> IncidentStatus:
    if verification is None:
        return IncidentStatus.CONTAINED
    return IncidentStatus.VERIFIED if verification.passed else IncidentStatus.FAILED
