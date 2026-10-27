"""Compile a plan into a GitLab dynamic child pipeline.

One job per action, DAG edges become `needs:`, stages follow the containment phases so the
GitLab pipeline graph reads as the plan. Output is deterministic YAML.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import yaml

from defuse.model.plan import GCP_ACTIONS, Phase, Plan

MAX_NEEDS = 50
_RESOURCE_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class CompileOptions:
    incident_id: str
    image: str = "$CI_REGISTRY_IMAGE/engine:$CI_COMMIT_SHORT_SHA"
    runner_tags: tuple[str, ...] = ("saas-linux-small-amd64",)
    dry_run: bool = False
    wif_audience: str | None = None
    wif_provider: str | None = None
    gcp_service_account: str | None = None
    extra_variables: dict[str, str] = field(default_factory=dict)
    record_project_id: int | None = None


def transitive_reduction(nodes: list[str], edges: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Drop every edge implied by a longer path. Input must be acyclic."""

    succ: dict[str, set[str]] = defaultdict(set)
    indegree = dict.fromkeys(nodes, 0)
    for before, after in edges:
        if after not in succ[before]:
            succ[before].add(after)
            indegree[after] += 1
    order: list[str] = []
    ready = sorted(n for n, d in indegree.items() if d == 0)
    while ready:
        node = ready.pop(0)
        order.append(node)
        for nxt in sorted(succ[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(nodes):
        raise ValueError("cannot reduce a cyclic graph")
    reach: dict[str, set[str]] = {}
    for node in reversed(order):
        reach[node] = set()
        for nxt in succ[node]:
            reach[node] |= {nxt} | reach[nxt]
    kept: set[tuple[str, str]] = set()
    for before in nodes:
        for after in succ[before]:
            implied = any(after in reach[mid] for mid in succ[before] if mid != after)
            if not implied:
                kept.add((before, after))
    return kept


def resource_group(target: str) -> str:
    return "containment-" + _RESOURCE_SAFE.sub("-", target).strip("-")[:120]


def compile_child_pipeline(plan: Plan, options: CompileOptions) -> str:
    if plan.strategy != "defuse":
        raise ValueError("the naive baseline is replay-only and cannot be executed")
    if options.wif_audience and not (options.wif_provider and options.gcp_service_account):
        raise ValueError("WIF requires a provider and a containment service account")
    order = [a for layer in plan.layers for a in layer]
    actions = {a.id: a for a in plan.actions}
    pending = set(order)
    edges = [(e.before, e.after) for e in plan.edges if e.before in pending and e.after in pending]
    needs: dict[str, list[str]] = defaultdict(list)
    for before, after in sorted(transitive_reduction(order, edges)):
        needs[after].append(before)

    stage_rank: dict[str, int] = {}
    for aid in order:
        rank = actions[aid].phase.rank
        for dep in needs[aid]:
            rank = max(rank, stage_rank[dep])
        stage_rank[aid] = rank

    phases = list(Phase)
    used = sorted({stage_rank[a] for a in order})
    document: dict[str, Any] = {
        "stages": [phases[r].value for r in used],
        "default": {
            "image": options.image,
            "tags": list(options.runner_tags),
            "interruptible": False,
        },
        "variables": {
            "DEFUSE_INCIDENT_ID": options.incident_id,
            "DEFUSE_DRY_RUN": "1" if options.dry_run else "0",
            **dict(sorted(options.extra_variables.items())),
        },
    }

    gates: dict[str, dict[str, Any]] = {}
    for aid in order:
        action = actions[aid]
        deps = needs[aid]
        if len(deps) > MAX_NEEDS:
            chunks = [deps[i : i + MAX_NEEDS] for i in range(0, len(deps), MAX_NEEDS)]
            deps = []
            for number, chunk in enumerate(chunks):
                gate = f"gate {number} for {aid}"
                gates[gate] = {
                    "stage": phases[max(stage_rank[d] for d in chunk)].value,
                    "needs": [{"job": d, "artifacts": False} for d in chunk],
                    "script": ['echo "gate passed"'],
                }
                deps.append(gate)
        job: dict[str, Any] = {
            "stage": phases[stage_rank[aid]].value,
            "needs": [{"job": d, "artifacts": False} for d in deps],
            "variables": {"DEFUSE_ACTION_ID": aid},
            "resource_group": resource_group(action.target),
            "environment": {"name": "containment", "action": "access"},
            "script": [
                'defuse act "$DEFUSE_ACTION_ID" --incident "$DEFUSE_INCIDENT_ID"'
                + (" --dry-run" if options.dry_run else "")
            ],
            "artifacts": {
                "when": "always",
                "paths": ["records/"],
                "expire_in": "90 days",
            },
        }
        if action.kind in GCP_ACTIONS and options.wif_audience:
            job["id_tokens"] = {"GCP_ID_TOKEN": {"aud": options.wif_audience}}
            job["before_script"] = _wif_login(options)
        document[aid] = job
    document.update(gates)
    if options.record_project_id is not None:
        document["stages"].append("record")
        predecessors = {e.before for e in plan.edges if e.before in pending and e.after in pending}
        terminals = sorted(pending - predecessors)
        document["publish incident record"] = {
            "stage": "record",
            "needs": [{"job": aid, "artifacts": False} for aid in terminals],
            "script": [
                f'defuse workflow postmortem "$DEFUSE_INCIDENT_ID" {options.record_project_id}'
            ],
            "artifacts": {"when": "always", "paths": ["records/"]},
        }
    return yaml.safe_dump(document, sort_keys=False, width=100, allow_unicode=True)


def _wif_login(options: CompileOptions) -> list[str]:
    return [
        'echo "$GCP_ID_TOKEN" > "$CI_BUILDS_DIR/.gcp_jwt"',
        "gcloud iam workload-identity-pools create-cred-config "
        f'"{options.wif_provider}" '
        f'--service-account="{options.gcp_service_account}" '
        '--credential-source-file="$CI_BUILDS_DIR/.gcp_jwt" '
        '--output-file="$CI_BUILDS_DIR/.gcp_creds.json"',
        'export GOOGLE_APPLICATION_CREDENTIALS="$CI_BUILDS_DIR/.gcp_creds.json"',
        'gcloud auth login --cred-file="$GOOGLE_APPLICATION_CREDENTIALS" --quiet',
    ]
