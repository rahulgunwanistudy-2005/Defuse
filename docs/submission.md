# Defuse: worm containment for GitLab CI

Submission draft. Add verified public GitLab evidence and video before submitting.

## Problem and audience

Platform and security teams need to contain CI supply-chain incidents while accounting for
revocation watchers, persistent hooks and compromised publishing identities. An unordered
revoke-everything response can trigger the modeled adversary's destructive behavior.

## What is built

Defuse collects GitLab metadata without retrieving secret contents, builds an exposure graph,
plans under six explicit safety constraints and compiles the result to child-pipeline jobs.
Its deterministic executors isolate hosts/agents, preserve evidence, remediate repositories,
replace credentials through a separate authority, quarantine versions, rebuild and verify state.
An append-only ledger and persistent context support retries and explain every action.

A stateful local sandbox completes all 22 actions and reaches verified in three fresh runs.
The naive-versus-safe replay demonstrates the difference in ordering. These runs model external
services; their CPU measurements are not live incident timings.

## GitLab Duo

Four schema-validated flows interpret advisories and draft incident, hook and postmortem prose.
Code chooses targets, edits and action order. Generated definitions, packaged headless prompts,
validation/application commands and CI wiring are included. Account registration, triggers and
actual Duo runs still require a configured sandbox and existing access/credits.

## Infrastructure and cost

The repository includes container recipes, local Compose, build attestations and GCP Terraform.
Hosting was excluded from this completion task and no resources were deployed. The included
GitLab-native credential authority runs locally with SQLite; no paid secret manager is required.
No paid plans or credits are purchased automatically.

## Evidence and next acceptance steps

See `docs/review/engine-tests.xml`, `docs/review/web-tests.json` and
`docs/evidence/local-runs/`. Before entering as Hands-off, attach three actual child pipelines,
flow-authored MRs, real verification/credit metrics, public catalog links and the final video.
Actual container builds and remote CI must also pass.

Repository: https://github.com/rahulgunwanistudy-2005/Defuse
