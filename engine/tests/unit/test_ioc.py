from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from defuse.model.ioc import AffectedPackage, IOCSet

WINDOW = datetime(2026, 8, 1, tzinfo=UTC)


def _ioc(**overrides: object) -> IOCSet:
    data: dict[str, object] = {
        "id": "keyv-worm",
        "title": "keyv-linked worm",
        "packages": [{"name": "keyv", "ranges": [">=5.1.0 <5.1.3"]}],
        "window_start": WINDOW,
    }
    data.update(overrides)
    return IOCSet.model_validate(data)


def test_range_and_exact_matching() -> None:
    pkg = AffectedPackage(name="keyv", versions=("6.0.1",), ranges=(">=5.1.0 <5.1.3",))
    assert pkg.matches("5.1.2")
    assert pkg.matches("6.0.1")
    assert not pkg.matches("5.1.3")
    assert not pkg.matches("not-a-version")


def test_package_without_selector_is_rejected() -> None:
    with pytest.raises(ValidationError, match="names no versions and no ranges"):
        AffectedPackage(name="keyv")


def test_bad_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AffectedPackage(name="keyv", ranges=(">>>1",))


def test_hash_must_be_sha256() -> None:
    with pytest.raises(ValidationError, match="sha256"):
        _ioc(file_hashes=["abc"])


def test_window_needs_timezone_and_order() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _ioc(window_start=datetime(2026, 8, 1))
    with pytest.raises(ValidationError, match="before"):
        _ioc(window_end=datetime(2026, 7, 1, tzinfo=UTC))


def test_window_and_affected() -> None:
    ioc = _ioc(window_end=datetime(2026, 9, 1, tzinfo=UTC))
    assert ioc.affected("keyv", "5.1.1")
    assert not ioc.affected("other", "5.1.1")
    assert ioc.in_window(datetime(2026, 8, 15, tzinfo=UTC))
    assert not ioc.in_window(datetime(2026, 7, 15, tzinfo=UTC))
    assert not ioc.in_window(datetime(2026, 9, 15, tzinfo=UTC))
