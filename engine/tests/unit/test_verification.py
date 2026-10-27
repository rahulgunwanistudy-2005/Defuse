from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from defuse.model.facts import Degradation
from defuse.model.incident import CheckOutcome, IncidentStatus, Verification, VerificationCheck
from defuse.scenario import scenario_cleaned_facts, scenario_facts, scenario_ioc
from defuse.verify.verify import _sinkhole_check, next_status, verify_containment


def test_missing_evidence_never_counts_as_verified() -> None:
    verification = Verification(
        checked_at=datetime.now(UTC),
        checks=(
            VerificationCheck(
                id="sinkhole_quiet", outcome=CheckOutcome.UNVERIFIED, detail="unreachable"
            ),
        ),
    )
    assert not verification.passed
    assert not verification.fully_verified
    assert next_status(verification) == IncidentStatus.CONTAINED
    assert not Verification(checked_at=datetime.now(UTC), checks=()).passed


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (503, {}),
        (200, {}),
        (200, []),
        (200, {"count": -1}),
        (200, {"count": "0"}),
        (200, {"count": False}),
        (200, {"count": 0}),
        (200, {"count": 0, "observed_seconds": 119, "complete": True}),
        (200, {"count": 0, "observed_seconds": 120, "complete": False}),
    ],
)
async def test_bad_sinkhole_responses_never_pass(status: int, body: object) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    ) as client:
        check = await _sinkhole_check("https://sinkhole.test", 120, client)
    assert check.outcome == CheckOutcome.UNVERIFIED


@pytest.mark.parametrize(("count", "outcome"), [(0, CheckOutcome.PASSED), (1, CheckOutcome.FAILED)])
async def test_sinkhole_requires_a_valid_observation(count: int, outcome: CheckOutcome) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"count": count, "observed_seconds": 120, "complete": True}
            )
        )
    ) as client:
        check = await _sinkhole_check("https://sinkhole.test", 120, client)
    assert check.outcome == outcome


async def test_partial_collection_cannot_claim_verification() -> None:
    after = scenario_cleaned_facts().model_copy(
        update={
            "degradations": (
                Degradation(source="jobs", reason="forbidden", effect="job metadata unavailable"),
            )
        }
    )
    result = await verify_containment(scenario_ioc(), scenario_facts(), after, sentinel_intact=True)
    assert "collection_complete" in result.unverified
    assert not result.passed
