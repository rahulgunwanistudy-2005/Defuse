"""Stateful, inert GitLab/credential/host sandbox. No remote publishing or propagation.

The same mutation/merge/verification code used by live integrations runs against this transport.
Repository files, memberships, package records and rebuilds change in memory, never on a host.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

import httpx

from defuse.automate.broker import CredentialBroker
from defuse.automate.models import CredentialReceipt, CredentialRequest
from defuse.collect.lockfile import parse_npm_lockfile
from defuse.collect.memory_backend import MemoryGitLab
from defuse.execute.gcp import RecordingGcpOps
from defuse.model.facts import CollectedFacts, DependencySource, ResolvedDependency
from defuse.scenario import scenario_facts

BASELINE = "0" * 40


class SandboxGcp(RecordingGcpOps):
    def __init__(self) -> None:
        super().__init__({"defuse-runner-1": ["runner-live"]})
        self.watcher_running = True
        self.persistence_present = True
        self.sentinel_intact = True

    async def run_command(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        if "systemctl --user stop" in command:
            self.watcher_running = False
        if "rm -f" in command:
            self.persistence_present = False
        if "test -d" in command:
            return "intact" if self.sentinel_intact else "missing"
        if "is-active" in command:
            return "active" if self.watcher_running else "inactive"
        return "recorded"


class SandboxGitLab(MemoryGitLab):
    def __init__(self) -> None:
        super().__init__()
        self.gcp = SandboxGcp()
        self.files: dict[tuple[int, str], dict[str, str]] = {}
        self.mrs: dict[tuple[int, int], dict[str, Any]] = {}
        self.commits: dict[str, dict[str, str]] = {}
        self.roles = {9500: 30}
        self.packages_deleted: set[int] = set()
        self.revoked: set[tuple[str, int]] = set()
        self.receipts: dict[str, CredentialReceipt] = {}
        self.rebuilds: dict[int, int] = {}
        self.issue_count = 0
        self.issues: dict[tuple[int, int], dict[str, Any]] = {}
        for pid, dep in (
            (101, "@defuse-sandbox/loader"),
            (102, "@defuse-sandbox/strings"),
            (103, None),
        ):
            bad = "1.0.3" if pid == 101 else "2.4.1"
            good = "1.0.2" if pid == 101 else "2.4.0"
            for ref, version in (("main", bad), (BASELINE, good)):
                dependencies = {dep: version} if dep else {}
                manifest = {
                    "name": f"sandbox-{pid}",
                    "version": "1.0.0",
                    "dependencies": dependencies,
                }
                packages: dict[str, Any] = {"": manifest}
                if dep:
                    packages["node_modules/" + dep] = {"version": version}
                self.files[pid, ref] = {
                    "package.json": json.dumps(manifest, indent=2) + "\n",
                    "package-lock.json": json.dumps(
                        {"lockfileVersion": 3, "packages": packages}, indent=2
                    )
                    + "\n",
                }
        self.files[102, "main"][".claude/settings.json"] = json.dumps(
            {
                "hooks": {"SessionStart": [{"command": "node defuse-sim-loader"}]},
                "permissions": {"allow": []},
            }
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        if path == "/replace":
            return self._broker(json.loads(request.content))
        if path == "/beacons":
            return httpx.Response(200, json={"count": 0, "observed_seconds": 120, "complete": True})
        match = re.match(r"/api/v4/projects/(\d+)(.*)", path)
        if match:
            pid, rest = int(match[1]), match[2]
            body = json.loads(request.content) if request.content else {}
            if not rest and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "id": pid,
                        "path_with_namespace": f"defuse-sandbox/p{pid}",
                        "default_branch": "main",
                    },
                )
            if rest.startswith("/repository/files/") and rest.endswith("/raw"):
                name = rest[len("/repository/files/") : -len("/raw")]
                ref = request.url.params.get("ref", "main")
                content = self.files.get((pid, ref), self.commits.get(ref, {})).get(name)
                return httpx.Response(404) if content is None else httpx.Response(200, text=content)
            if rest.startswith("/repository/branches/"):
                ref = rest[len("/repository/branches/") :]
                if (pid, ref) not in self.files:
                    return httpx.Response(404)
                sha = f"{pid:040x}"
                self.commits[sha] = self.files[pid, ref].copy()
                return httpx.Response(200, json={"commit": {"id": sha}})
            if rest == "/repository/commits" and request.method == "POST":
                branch = body["branch"]
                files = self.commits[body["start_sha"]].copy()
                for edit in body["actions"]:
                    if edit["action"] == "delete":
                        files.pop(edit["file_path"], None)
                    else:
                        files[edit["file_path"]] = edit["content"]
                self.files[pid, branch] = files
                sha = f"{len(self.commits) + 10000:040x}"
                self.commits[sha] = files.copy()
                self.mutations.append((request.method, path))
                return httpx.Response(201, json={"id": sha})
            if rest == "/merge_requests" and request.method == "GET":
                branch = request.url.params.get("source_branch")
                return httpx.Response(
                    200,
                    json=[
                        m
                        for (p, _), m in self.mrs.items()
                        if p == pid and (not branch or m["source_branch"] == branch)
                    ],
                )
            if rest == "/merge_requests" and request.method == "POST":
                iid = len(self.mrs) + 1
                sha = next(
                    k
                    for k, v in reversed(self.commits.items())
                    if v == self.files[pid, body["source_branch"]]
                )
                mr = {
                    "iid": iid,
                    "state": "opened",
                    "sha": sha,
                    "source_branch": body["source_branch"],
                    "target_branch": body["target_branch"],
                    "web_url": f"https://gitlab.test/defuse-sandbox/p{pid}/-/merge_requests/{iid}",
                }
                old = self.files[pid, body["target_branch"]]
                new = self.commits[sha]
                mr["_diffs"] = [
                    {"old_path": n, "new_path": n}
                    for n in sorted(old.keys() | new.keys())
                    if old.get(n) != new.get(n)
                ]
                self.mrs[pid, iid] = mr
                self.mutations.append((request.method, path))
                return httpx.Response(201, json=mr)
            mr_match = re.match(r"/merge_requests/(\d+)(.*)", rest)
            if mr_match:
                mr = self.mrs[pid, int(mr_match[1])]
                if mr_match[2] == "/diffs":
                    return httpx.Response(200, json=mr["_diffs"])
                if request.method == "PUT":
                    self.files[pid, mr["target_branch"]] = self.commits[mr["sha"]].copy()
                    mr["state"] = "merged"
                    self.mutations.append((request.method, path))
                return httpx.Response(200, json=mr)
            if rest.startswith("/members/"):
                uid = int(rest.rsplit("/", 1)[1])
                if request.method == "PUT":
                    self.roles[uid] = body["access_level"]
                    self.mutations.append((request.method, path))
                return httpx.Response(
                    200, json={"id": uid, "access_level": self.roles.get(uid, 30)}
                )
            if rest == "/issues":
                if request.method == "GET":
                    return httpx.Response(
                        200, json=[i for (p, _), i in self.issues.items() if p == pid]
                    )
                self.issue_count += 1
                issue = {
                    "iid": self.issue_count,
                    "title": body["title"],
                    "web_url": f"https://gitlab.test/defuse-sandbox/p{pid}/-/issues/{self.issue_count}",
                }
                self.issues[pid, self.issue_count] = issue
                self.mutations.append((request.method, path))
                return httpx.Response(201, json=issue)
            if rest == "/pipeline" and request.method == "POST":
                pipeline = 7000 + pid
                self.rebuilds[pid] = pipeline
                self.mutations.append((request.method, path))
                return httpx.Response(201, json={"id": pipeline})
            pl = re.match(r"/pipelines/(\d+)(/jobs)?$", rest)
            if pl and int(pl[1]) in self.rebuilds.values():
                if pl[2]:
                    return httpx.Response(
                        200, json=[{"id": 8000 + pid, "status": "success", "runner": {"id": 200}}]
                    )
                return httpx.Response(
                    200,
                    json={
                        "id": int(pl[1]),
                        "status": "success",
                        "web_url": f"https://gitlab.test/defuse-sandbox/p{pid}/-/pipelines/{pl[1]}",
                    },
                )
            if request.method == "DELETE":
                if rest.startswith("/packages/"):
                    self.packages_deleted.add(int(rest.rsplit("/", 1)[1]))
                if rest.startswith(("/access_tokens/", "/deploy_tokens/")):
                    self.revoked.add((rest.split("/")[1], int(rest.rsplit("/", 1)[1])))
        return super()._handle(request)

    def _broker(self, body: dict[str, Any]) -> httpx.Response:
        request = CredentialRequest.model_validate(body)
        key = request.incident_id + ":" + request.action_id
        receipt = self.receipts.get(key)
        if receipt is None:
            receipt = CredentialReceipt(
                receipt_id=f"sandbox-{len(self.receipts) + 1}",
                incident_id=request.incident_id,
                action_id=request.action_id,
                target=request.target,
                namespace=request.namespace,
                installed=True,
                old_revoked=request.retire_old,
                consumer_refs=tuple(c.ref for c in request.consumers),
                replacement_id=f"replacement-{len(self.receipts) + 1}",
            )
            self.receipts[key] = receipt
        return httpx.Response(200, json=receipt.model_dump(mode="json"))

    def broker(self) -> CredentialBroker:
        return CredentialBroker("https://gitlab.test", transport=self.transport())

    async def facts(self) -> CollectedFacts:
        facts = scenario_facts()
        jobs = []
        for job in facts.jobs:
            if job.project_id in self.rebuilds:
                lock = self.files[job.project_id, "main"]["package-lock.json"]
                resolved = tuple(
                    ResolvedDependency(
                        name=n,
                        version=v,
                        source=DependencySource.LOCKFILE,
                        evidence="successful sandbox rebuild lockfile",
                    )
                    for n, v, _ in parse_npm_lockfile(lock)
                )
                jobs.append(
                    job.model_copy(
                        update={
                            "id": job.id + 100000,
                            "pipeline_id": self.rebuilds[job.project_id],
                            "runner_id": 200,
                            "resolved": resolved,
                            "started_at": datetime.now(UTC),
                        }
                    )
                )
            else:
                jobs.append(job)
        hooks = tuple(
            h
            for h in facts.hook_findings
            if "defuse-sim-loader" in self.files[h.project_id, "main"].get(h.path, "")
        )
        return facts.model_copy(
            update={
                "jobs": tuple(jobs),
                "hook_findings": hooks,
                "published_packages": tuple(
                    p for p in facts.published_packages if p.package_id not in self.packages_deleted
                ),
                "watcher_findings": facts.watcher_findings if self.gcp.watcher_running else (),
                "access_tokens": tuple(
                    t.model_copy(update={"active": ("access_tokens", t.id) not in self.revoked})
                    for t in facts.access_tokens
                ),
                "deploy_tokens": tuple(
                    t.model_copy(update={"revoked": ("deploy_tokens", t.id) in self.revoked})
                    for t in facts.deploy_tokens
                ),
            }
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "routes": self._routes,
            "files": [{"project": p, "ref": r, "files": f} for (p, r), f in self.files.items()],
            "mrs": [{"project": p, "iid": i, "mr": m} for (p, i), m in self.mrs.items()],
            "commits": self.commits,
            "roles": self.roles,
            "packages_deleted": sorted(self.packages_deleted),
            "revoked": [list(x) for x in self.revoked],
            "receipts": {k: v.model_dump(mode="json") for k, v in self.receipts.items()},
            "rebuilds": self.rebuilds,
            "mutations": self.mutations,
            "issues": [{"project": p, "iid": i, "issue": v} for (p, i), v in self.issues.items()],
            "gcp": {
                "tags": self.gcp._tags,
                "commands": self.gcp.commands,
                "snapshots": self.gcp.snapshots,
                "watcher_running": self.gcp.watcher_running,
                "persistence_present": self.gcp.persistence_present,
                "sentinel_intact": self.gcp.sentinel_intact,
            },
        }

    def restore(self, state: dict[str, Any]) -> None:
        self._routes = state["routes"]
        self.files = {(int(x["project"]), x["ref"]): x["files"] for x in state["files"]}
        self.mrs = {(int(x["project"]), int(x["iid"])): x["mr"] for x in state["mrs"]}
        self.commits = state["commits"]
        self.roles = {int(k): v for k, v in state["roles"].items()}
        self.packages_deleted = set(state["packages_deleted"])
        self.revoked = {(str(k), int(v)) for k, v in state["revoked"]}
        self.receipts = {
            k: CredentialReceipt.model_validate(v) for k, v in state["receipts"].items()
        }
        self.rebuilds = {int(k): v for k, v in state["rebuilds"].items()}
        self.mutations = [tuple(x) for x in state["mutations"]]
        self.issues = {
            (int(x["project"]), int(x["iid"])): x["issue"] for x in state.get("issues", [])
        }
        self.issue_count = max((i for _, i in self.issues), default=0)
        self.gcp._tags = state["gcp"]["tags"]
        self.gcp.commands = [tuple(x) for x in state["gcp"]["commands"]]
        self.gcp.snapshots = state["gcp"]["snapshots"]
        self.gcp.watcher_running = state["gcp"]["watcher_running"]
        self.gcp.persistence_present = state["gcp"]["persistence_present"]
        self.gcp.sentinel_intact = state["gcp"]["sentinel_intact"]
