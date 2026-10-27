"""Run isolated local container smoke tests without live credentials or paid services."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def request(url: str) -> bytes:
    with urlopen(url, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("container endpoint did not return HTTP 200")
        return response.read()


def main() -> None:
    prefix = "defuse-smoke-" + uuid4().hex[:10]
    containers: list[str] = []
    docker("network", "create", prefix)
    results: dict[str, object] = {"checked_at": datetime.now(UTC).isoformat()}

    def start(component: str, port: int, *options: str) -> str:
        name = prefix + "-" + component
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            prefix,
            "--publish",
            f"127.0.0.1::{port}",
            *options,
            f"defuse/{component}:local",
        )
        containers.append(name)
        host = docker("port", name, f"{port}/tcp")
        base = "http://" + host
        route = "/" if component == "web" else "/healthz"
        deadline = time.monotonic() + 120
        while True:
            try:
                request(base + route)
                break
            except (URLError, TimeoutError, ConnectionError):
                if docker("inspect", "--format", "{{.State.Running}}", name) != "true":
                    raise RuntimeError(
                        component + " container exited during startup"
                    ) from None
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        component + " container did not become ready"
                    ) from None
                time.sleep(1)
        return base

    try:
        engine = start(
            "engine", 8000, "--env", "DEFUSE_DATABASE_URL=sqlite+aiosqlite:///:memory:"
        )
        incident = json.loads(request(engine + "/api/incidents/scenario-sandbox"))
        actions = json.loads(
            request(engine + "/api/incidents/scenario-sandbox/actions")
        )
        if incident["status"] != "verified" or len(actions) != 22:
            raise RuntimeError("container scenario did not verify all 22 actions")
        results["engine"] = {
            "health": "passed",
            "incident_status": incident["status"],
            "actions": len(actions),
            "glab": docker("exec", prefix + "-engine", "glab", "--version"),
            "gcloud": docker(
                "exec", prefix + "-engine", "gcloud", "version", "--format=json"
            ),
        }
        web = start(
            "web", 3000, "--env", f"DEFUSE_API_BASE=http://{prefix}-engine:8000"
        )
        if b"Defuse" not in request(web + "/incidents/scenario-sandbox/record"):
            raise RuntimeError("production web did not render the record")
        proxied = json.loads(request(web + "/api/incidents/scenario-sandbox"))
        if proxied["status"] != "verified":
            raise RuntimeError("production web API forwarding failed")
        results["web"] = {"record_page": "passed", "api_proxy": "passed"}
        sinkhole = start("sinkhole", 8080)
        results["sinkhole"] = {"health": json.loads(request(sinkhole + "/healthz"))}
        results["images"] = {
            component: json.loads(
                docker(
                    "image",
                    "inspect",
                    "--format",
                    "{{json .Id}}",
                    f"defuse/{component}:local",
                )
            )
            for component in ("engine", "web", "sinkhole")
        }
        results["status"] = "passed"
        output = Path("docs/evidence/docker-smoke.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
    finally:
        for name in reversed(containers):
            subprocess.run(
                ["docker", "rm", "--force", name], check=False, capture_output=True
            )
        subprocess.run(
            ["docker", "network", "rm", prefix], check=False, capture_output=True
        )


if __name__ == "__main__":
    main()
