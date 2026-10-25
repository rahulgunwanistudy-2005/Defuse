# Architecture

Defuse turns a worm advisory into a contained, verified GitLab project, in an order that is
provably safe against the worm's own triggers. The planner and executor are deterministic code;
the LLM only interprets, drafts and explains, and every LLM output is schema-validated before
anything consumes it.

## The pipeline, end to end

```
advisory (human)                    ← the one human "intent in" moment
   │  advisory-intake flow (LLM → IOC JSON, schema-validated)
   ▼
IOC set ──► collectors ──► exposure graph ──► planner ──► child pipeline ──► verify
            (GitLab API,   (deterministic     (C1-C6      (one job per      (re-collect,
             metadata       JSON, epidemic     constraints, action, needs:   sinkhole,
             only)          tree)              layered DAG) = plan order)     sentinel)
                                                   │
                                              naive baseline (revoke-all) → replay → detonation
```

## Components

- **model** — Pydantic v2 types. `IOCSet` (npm ranges, hashes, hook signatures), the typed
  exposure graph (nodes and evidence-carrying edges), `CollectedFacts` (no secret values),
  actions, plans, incident records and metrics.
- **collect** — one typed async GitLab client (jittered retry honouring `Retry-After`, ETag
  conditional reads, Link-header pagination, bounded concurrency, a sandbox-namespace allowlist
  and a dry-run guard on every mutation) and the collectors that build `CollectedFacts`. The
  variable collector requests names and scopes only; a test fails if it ever selects a value.
- **graph** — builds the exposure graph deterministically: find jobs that resolved an affected
  version, expand to runners, hosts, readable secrets (respecting protected refs and environment
  scopes) and what those secrets can publish, then recurse on provenance mismatches to a
  fixpoint. The result serialises byte-identically.
- **plan** — the action catalog, constraints C1–C6 as cited data, the layered planner (priority
  tie-break, operator pins, an unsat explainer that returns a minimal conflicting cycle, and
  `explain(action)`), the naive baseline, the adversary replay, and an independent plan checker
  that restates C1–C6 directly over layer indices so a planner bug cannot hide from it.
- **execute** — the child-pipeline compiler (transitive reduction for `needs:`, phase stages,
  WIF id_tokens for GCP actions), idempotent executors with an append-only ledger, and the GCP
  ops (recording for demos, gcloud for live).
- **verify** — re-run collectors, confirm no affected resolution and no new rogue publishes,
  check the sinkhole is quiet and the sentinel intact, and compute the Security Standard timings
  from stored timestamps only.
- **api** — FastAPI REST + Server-Sent Events; OpenAPI at `/docs`.
- **store** — SQLAlchemy 2 async + Alembic; incidents, IOC sets, graph snapshots, plans, action
  records, metrics, events.

## Why the order is the whole point

Containment is an ordering problem under adversarial triggers. Two published behaviours make
naive remediation dangerous: a revocation watcher fires the attacker's handler the moment a
stolen token stops working, and a dead-man's switch wipes the host if registry-publish and
source access are lost together. The planner encodes these as hard constraints (C1, C3) and
orders every action so neither trigger ever fires. The adversary replay demonstrates the
difference: the naive "revoke everything now" plan detonates; the Defuse plan does not.

See `docs/threat-model.md` for the constraint derivations and `docs/governance.md` for tool
governance.
