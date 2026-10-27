"""GCP operations behind the GcpOps protocol.

`RecordingGcpOps` is the default for scenarios, demos and tests: it keeps host state in memory
and never shells out. `GcloudOps` runs real `gcloud` commands and is wired only when a GCP
project is configured.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import structlog

log = structlog.get_logger(__name__)


class RecordingGcpOps:
    def __init__(self, hosts: dict[str, list[str]] | None = None) -> None:
        self._tags: dict[str, list[str]] = {h: list(t) for h, t in (hosts or {}).items()}
        self.commands: list[tuple[str, str]] = []
        self.snapshots: list[str] = []

    async def host_network_tags(self, host: str) -> list[str]:
        return list(self._tags.setdefault(host, ["runner-live"]))

    async def set_network_tags(self, host: str, tags: list[str]) -> None:
        self._tags[host] = sorted(tags)

    async def snapshot_disk(self, host: str, name: str | None = None) -> str:
        name = name or f"{host}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        if name not in self.snapshots:
            self.snapshots.append(name)
        return name

    async def run_command(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        return "recorded"


class GcloudOps:
    def __init__(self, project: str, zone: str) -> None:
        self._project = project
        self._zone = zone

    async def _gcloud(self, *args: str) -> str:
        cmd = ["gcloud", *args, f"--project={self._project}", "--quiet"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"gcloud {args[0]} failed: {err.decode()[:300]}")
        return out.decode().strip()

    async def host_network_tags(self, host: str) -> list[str]:
        out = await self._gcloud(
            "compute",
            "instances",
            "describe",
            host,
            f"--zone={self._zone}",
            "--format=value(tags.items)",
        )
        return [t for t in out.replace(";", ",").split(",") if t]

    async def set_network_tags(self, host: str, tags: list[str]) -> None:
        await self._gcloud(
            "compute",
            "instances",
            "set-tags",
            host,
            f"--zone={self._zone}",
            f"--tags={','.join(tags)}",
        )

    async def snapshot_disk(self, host: str, name: str | None = None) -> str:
        name = name or f"{host}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        present = json.loads(
            await self._gcloud(
                "compute", "snapshots", "list", f"--filter=name={name}", "--format=json(name)"
            )
        )
        if present:
            return name
        instance = json.loads(
            await self._gcloud(
                "compute",
                "instances",
                "describe",
                host,
                f"--zone={self._zone}",
                "--format=json(disks)",
            )
        )
        boot = next(d for d in instance["disks"] if d.get("boot"))
        disk = str(boot["source"]).rsplit("/", 1)[1]
        await self._gcloud(
            "compute", "disks", "snapshot", disk, f"--zone={self._zone}", f"--snapshot-names={name}"
        )
        return name

    async def run_command(self, host: str, command: str) -> str:
        return await self._gcloud(
            "compute",
            "ssh",
            host,
            f"--zone={self._zone}",
            "--tunnel-through-iap",
            f"--command={command}",
        )
