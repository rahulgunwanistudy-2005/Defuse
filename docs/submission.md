# Devpost submission — Defuse: worm containment for GitLab CI

**Path A (new project). Autonomy level: Hands-off.**

## The problem

A Shai-Hulud-class supply-chain worm doesn't just infect developer laptops — only 23% of
Shai-Hulud 2.0 infections were on dev machines (Wiz, Dec 2025). It lives in CI: runners,
containers, and the secrets CI jobs can read. It republishes packages through the victim's own
release workflow with valid provenance, and it moves between organizations every few minutes (The
Hacker News / Microsoft, Aug 2026). And it plants triggers that turn remediation into a weapon: a
revocation watcher that fires when a stolen token is revoked, and a dead-man's switch that wipes
the host when registry and source access are lost together (SANS ISC; GitLab VR, 2026/2025).

Every public response is a manual checklist. GitLab's own published guidance stops at Dependency
Scanning plus asking an agent "are we affected". Nobody computes the exposure and executes a
containment whose *order* is safe.

## Who it is for

Platform and security teams running CI on GitLab, during a live incident.

## What it does

An advisory goes in; a contained, verified project comes out, with no human in the middle after
the first intent. Defuse reads GitLab metadata (never secret values), builds a deterministic
exposure graph including the epidemic tree from provenance mismatches, plans containment under
six cited safety constraints, compiles the plan into a GitLab dynamic child pipeline whose graph
reads as the plan, executes it idempotently with an append-only ledger, and verifies the result
against the sinkhole and a sentinel directory. It proves the order is safe two ways: Hypothesis
property tests over 500 random exposure graphs, and an adversary replay that detonates the naive
"revoke everything" baseline while the Defuse plan stays intact.

## How it uses GitLab Duo Agent Platform

Four custom flows (flow-registry v1): advisory-intake (advisory → schema-validated IOC, with a
calibrated refusal on ambiguity), incident-commander (a detector failure on a human push opens an
incident), hook-sweeper (one guarded MR per repo), postmortem-policy (the record plus a policy
MR). The LLM interprets, drafts and explains; deterministic code decides and acts; every LLM
output is schema-validated. Explicit tool-governance rules deny delete-class tools for every flow.

## Google Cloud usage

Terraform deploys engine, web and sinkhole to Cloud Run, Postgres to Cloud SQL, and a persistent
GCE runner. CI authenticates to GCP through Workload Identity Federation with GitLab id_tokens —
no static keys. Host isolation is a network-tag swap caught by a deny-all-egress firewall rule.
Cloud Trace via OpenTelemetry.

## What was hard

The planner. Containment is an ordering problem under adversarial triggers, and the constraints
genuinely conflict: a publish-capable secret that is *watched* must be rotated early to stop
propagation (C4) yet cannot be touched until its host is neutralized (C1). Getting the planner,
an independent checker, and an adversary model to all agree — and proving it over 500 generated
graphs — took real care, and surfaced a true C1/C4 tension that the property tests caught.

## What's next

Record live three-run medians against a provisioned sandbox; a read-only MCP server so Duo or
Claude Code can ask "why was token X rotated before Y?"; a second ecosystem (PyPI).

## Links

- Repo: https://github.com/rahulgunwanistudy-2005/Defuse
- Live console: _recorded after `terraform apply` (docs/runbook.md)_
- Video: _under 2:55, beat sheet in docs/demo-script.md_
