"""Parse npm lockfiles and job traces for resolved package versions."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

_TRACE_SPEC = re.compile(
    r"(?<![\w@/.-])((?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*)@(\d+\.\d+\.\d+(?:-[\w.]+)?)\b"
)


def _name_from_path(path: str) -> str | None:
    marker = "node_modules/"
    if marker not in path:
        return None
    return path.rsplit(marker, 1)[1] or None


def parse_npm_lockfile(text: str) -> list[tuple[str, str, str]]:
    """Return (name, version, lockfile path) for every installed package.

    Supports lockfileVersion 1 (`dependencies`, nested) and 2/3 (`packages`).
    Malformed input returns an empty list rather than raising: the caller falls back to traces.
    """

    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    found: set[tuple[str, str, str]] = set()
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path, meta in packages.items():
            name = _name_from_path(path)
            if name and isinstance(meta, dict) and isinstance(meta.get("version"), str):
                found.add((meta.get("name") or name, meta["version"], path))
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        found.update(_walk_v1(deps, "node_modules"))
    return sorted(found)


def _walk_v1(deps: dict[str, Any], prefix: str) -> Iterator[tuple[str, str, str]]:
    for name, meta in deps.items():
        if not isinstance(meta, dict):
            continue
        path = f"{prefix}/{name}"
        version = meta.get("version")
        if isinstance(version, str) and not version.startswith(("file:", "git", "http")):
            yield (name, version, path)
        nested = meta.get("dependencies")
        if isinstance(nested, dict):
            yield from _walk_v1(nested, f"{path}/node_modules")


def scan_trace(text: str) -> list[tuple[str, str, int]]:
    """Return (name, version, line number) for every `name@x.y.z` mention in a job trace."""

    found: dict[tuple[str, str], int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _TRACE_SPEC.finditer(line):
            key = (match.group(1), match.group(2))
            found.setdefault(key, number)
    return sorted((n, v, line) for (n, v), line in found.items())
