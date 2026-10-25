## Task: build Defuse end to end
## Goal: an advisory goes in; a contained, verified state comes out, in a provably safe order.

### Steps (vertical slices)
- [x] 1. Skeleton: layout, license, CI lint+test, Terraform
- [x] 2. Sandbox simulator + sinkhole (inert, guarded)
- [x] 3. Collectors + exposure graph (deterministic JSON, contract tests)
- [x] 4. Planner: constraints C1-C6, unsat explainer, explain(), property tests at 500 examples
- [x] 5. Executor: child pipeline compiler, action executors, ledger, verification, metrics
- [x] 6. Duo flows: advisory-intake, incident-commander, hook-sweeper, postmortem-policy
- [x] 7. Console (Agentix-inspired design): list, console, graph, plan, replay, record
- [~] 8. Hardening: degradations + partial-permission reporting done; 500-job load test pending
- [x] 9. Submission assets (README, docs, submission.md, self-review.md; video/GIF/live URL pending sandbox)

### Risks / open questions
- No live GitLab sandbox or GCP project in the build session (docs/decisions.md D3).
- Dribbble reference unreachable from the build environment (D5).
- GitLab `needs:` limit of 50 per job: compiler emits the transitive reduction.
- Tool governance has no public API yet: agent blocking uses project membership role.

### Done criteria
- [x] mypy --strict, ruff, svelte-check, eslint clean
- [x] Coverage >= 90% on model, graph, plan, execute/compiler; >= 75% overall (92% core)
- [x] Property tests green at 500 examples per property
- [x] Every number in README traces to a stored metric or a cited source

### Review
Built end to end on `main`: deterministic engine (graph, planner, executor, verify) with 78
tests, 500-example property proofs and an independent safety checker; typed async GitLab client
with a namespace allowlist and no-secret-value collectors; FastAPI + SSE; a SvelteKit console in
the Agentix-inspired direction (Lighthouse 99-100, a11y 95-96, 5 e2e tests); the inert guarded
simulator and sinkhole; four Duo flows; the product .gitlab-ci.yml and a GitHub Actions mirror;
Terraform for the GCP/WIF deployment; and the full submission docs. Deferred, all gated only on a
provisioned sandbox + GCP project (not code): live three-run medians, the replay GIF and the
video, the live console URL, the flow catalog links, and the 500-job load test (docs/runbook.md).
