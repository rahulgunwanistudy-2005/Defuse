"""Deterministic edits: remove matched hooks, restore trusted locks, propose policy."""

from __future__ import annotations

import json
from typing import Any

from defuse.automate.models import FileEdit
from defuse.collect.collector import HOOK_PATHS
from defuse.collect.lockfile import parse_npm_lockfile
from defuse.model.ioc import IOCSet


def clean_hook(path: str, text: str, ioc: IOCSet) -> str:
    if path not in HOOK_PATHS:
        raise ValueError("hook path is not supported by the deterministic remediator")
    patterns = [s.pattern for s in ioc.hook_signatures if s.kind == HOOK_PATHS[path]]
    if not patterns or not any(p in text for p in patterns):
        return text
    if path == "AGENTS.md":
        return "".join(
            line for line in text.splitlines(keepends=True) if not any(p in line for p in patterns)
        )
    doc = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("hook file must be a JSON object")
    if path.startswith(".claude/"):
        hooks = doc.get("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("Claude hooks must be an object")
        for event, entries in list(hooks.items()):
            if not isinstance(entries, list):
                raise ValueError("Claude hook event must contain a list")
            clean = []
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Claude hook entry must be an object")
                # Keep unrelated commands and matchers in the same SessionStart entry.
                nested = entry.get("hooks")
                if isinstance(nested, list):
                    retained = [h for h in nested if not _matches(h, patterns)]
                    if retained:
                        clean.append({**entry, "hooks": retained})
                elif not _matches(entry, patterns):
                    clean.append(entry)
            if clean:
                hooks[event] = clean
            else:
                del hooks[event]
        if not hooks:
            doc.pop("hooks", None)
    else:
        tasks = doc.get("tasks", [])
        if not isinstance(tasks, list):
            raise ValueError("VS Code tasks must be a list")
        doc["tasks"] = [task for task in tasks if not _matches(task, patterns)]
    result = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if any(p in result for p in patterns):
        raise ValueError("signature remains outside a supported hook location")
    return result


def _matches(item: Any, patterns: list[str]) -> bool:
    if isinstance(item, str):
        return any(p in item for p in patterns)
    if isinstance(item, list):
        return any(_matches(v, patterns) for v in item)
    if isinstance(item, dict):
        return any(_matches(v, patterns) for v in item.values())
    return False


def trusted_pin_edits(
    current_manifest: str,
    baseline_manifest: str,
    baseline_lock: str,
    ioc: IOCSet,
    rogue: set[tuple[str, str]],
) -> tuple[FileEdit, ...]:
    current, baseline, lock = map(json.loads, (current_manifest, baseline_manifest, baseline_lock))
    if not all(isinstance(x, dict) for x in (current, baseline, lock)):
        raise ValueError("trusted baseline files must be JSON objects")
    if lock.get("lockfileVersion") not in (2, 3):
        raise ValueError("trusted baseline requires an npm v2/v3 lockfile")
    resolved = parse_npm_lockfile(baseline_lock)
    if any(
        ioc.affected(name, version) or (name, version) in rogue for name, version, _ in resolved
    ):
        raise ValueError("trusted baseline still resolves an affected version")
    if current.get("scripts") != baseline.get("scripts"):
        raise ValueError("trusted baseline would change install/build scripts")
    if current.get("name") != baseline.get("name") or current.get("workspaces") != baseline.get(
        "workspaces"
    ):
        raise ValueError("trusted baseline belongs to a different package or workspace")
    for key in (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
        "peerDependencies",
        "overrides",
    ):
        if key in baseline:
            current[key] = baseline[key]
        else:
            current.pop(key, None)
    root = lock.get("packages", {}).get("")
    if not isinstance(root, dict):
        raise ValueError("trusted lockfile has no root package")
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        if root.get(key, {}) != current.get(key, {}):
            raise ValueError("trusted manifest and lockfile do not agree")
    return (
        FileEdit(
            action="update", file_path="package.json", content=json.dumps(current, indent=2) + "\n"
        ),
        FileEdit(action="update", file_path="package-lock.json", content=baseline_lock),
    )
