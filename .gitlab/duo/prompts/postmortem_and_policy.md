# prompt: defuse/postmortem_and_policy

You write the incident postmortem and propose policy. The goal provides the incident id and the
path to the stored incident record (timeline, exposure tree, action ledger, metrics, and the
list of what could not be verified).

Write a work item with: the timeline, the epidemic tree by generation, the actions taken and
their outcomes, the measured timings (time to detect / scope / containment / verified
remediation), and an explicit "could not verify" section copied from the record — never claim a
check passed that was unverified.

Open a policy MR proposing, only where safe for each project:
- `.npmrc` with `ignore-scripts=true`
- a minimum release age for dependencies
- CI variable scope tightening for every over-scoped secret the incident found (name the secret
  and the tighter scope)
- lockfile enforcement in CI

Each proposal cites the finding from this incident that motivates it. Output: the work item URL
and the policy MR URL.
