"""Dependency-policy enforcement using lockfile and published release metadata only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from pydantic import Field

from defuse.automate.models import StrictModel
from defuse.collect.lockfile import parse_npm_lockfile


class DependencyPolicy(StrictModel):
    incident_id: str
    lockfile_required: bool = True
    minimum_release_age_hours: float = Field(default=24, ge=0)
    variable_scope_review: tuple[dict[str, str], ...] = ()
    install_scripts: str = "require_explicit_review"


async def check_dependencies(
    root: Path,
    policy: DependencyPolicy,
    *,
    registry: str = "https://registry.npmjs.org",
    http: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> list[str]:
    parsed = urlsplit(registry)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("release metadata registry must be an HTTPS URL without credentials")
    manifest = root / "package.json"
    lock = root / "package-lock.json"
    if not manifest.exists():
        return []
    if not lock.exists():
        return ["package-lock.json is required"] if policy.lockfile_required else []
    resolved = parse_npm_lockfile(lock.read_text())
    clock = now or datetime.now(UTC)
    failures = []
    cache: dict[str, dict[str, str]] = {}
    client = http or httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        for name, version, _ in resolved:
            if policy.minimum_release_age_hours <= 0:
                continue
            if name not in cache:
                response = await client.get(registry.rstrip("/") + "/" + quote(name, safe=""))
                if response.status_code != 200:
                    failures.append(f"{name}: publication metadata unavailable")
                    cache[name] = {}
                    continue
                body = response.json()
                cache[name] = body.get("time", {}) if isinstance(body, dict) else {}
            timestamp = cache[name].get(version)
            if not timestamp:
                failures.append(f"{name}@{version}: release timestamp unavailable")
                continue
            try:
                published = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age = (clock - published).total_seconds() / 3600
            except (ValueError, TypeError):
                failures.append(f"{name}@{version}: invalid release timestamp")
                continue
            if age < policy.minimum_release_age_hours:
                failures.append(
                    f"{name}@{version}: younger than {policy.minimum_release_age_hours:g} hours"
                )
    finally:
        if http is None:
            await client.aclose()
    return sorted(set(failures))
