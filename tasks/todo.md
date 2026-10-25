## Task: build Defuse end to end
## Goal: an advisory goes in; a contained, verified state comes out, in a provably safe order.

### Steps (vertical slices)
- [ ] 1. Skeleton: layout, license, CI lint+test, Terraform skeleton
- [ ] 2. Sandbox simulator + sinkhole (inert, guarded)
- [ ] 3. Collectors + exposure graph (deterministic JSON, contract tests)
- [ ] 4. Planner: constraints C1-C6, unsat explainer, explain(), property tests at 500 examples
- [ ] 5. Executor: child pipeline compiler, action executors, ledger, verification, metrics
- [ ] 6. Duo flows: advisory-intake, incident-commander, hook-sweeper, postmortem-policy
- [ ] 7. Console (Agentix-inspired design): list, console, graph, plan, replay, record
- [ ] 8. Hardening: degradations, timeouts, rate limits, 500-job load test
- [ ] 9. Submission assets

### Risks / open questions
- No live GitLab sandbox or GCP project in the build session (docs/decisions.md D3).
- Dribbble reference unreachable from the build environment (D5).
- GitLab `needs:` limit of 50 per job: compiler emits the transitive reduction.
- Tool governance has no public API yet: agent blocking uses project membership role.

### Done criteria
- [ ] mypy --strict, ruff, svelte-check clean
- [ ] Coverage >= 90% on model, graph, plan, execute/compiler; >= 75% overall
- [ ] Property tests green at 500 examples per property
- [ ] Every number in README traces to a stored metric or a cited source

### Review
(filled after completion)
