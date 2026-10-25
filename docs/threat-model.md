# Threat model and the safety constraints

Defuse defends CI projects on GitLab against a Shai-Hulud-class self-replicating supply-chain
worm. The adversary has already run inside one or more CI jobs and holds whatever those jobs
could read. The danger is not only the compromise but the **remediation**: the worm plants
triggers that turn a naive cleanup into a detonation.

## Adversary capabilities (from the sources in the README)

- Reads every CI variable, project token and deploy token the infected job could read.
- Republishes packages through the victim's own release workflow, with valid provenance.
- Plants re-infection hooks: Claude Code `SessionStart` hooks, VS Code run-on-open tasks.
- Installs a **revocation watcher**: when a stolen token is revoked, an attacker handler fires.
- Arms a **dead-man's switch**: losing GitHub and npm access at the same moment wipes `$HOME`.

## The constraints

Each is encoded as data in `engine/defuse/plan/constraints.py` with a one-sentence rationale and
a source. The independent checker in `plan/check.py` restates all six over layer indices.

| ID | Rule | Why | Source |
| --- | --- | --- | --- |
| C1 | A watched secret may be rotated/revoked only after its host is isolated or the watcher stopped | revoking it fires the attacker's handler | SANS ISC, Aug 5 2026 |
| C2 | Snapshot a host before any eradication on it | preserve the forensic record | SANS ISC, Aug 5 2026 |
| C3 | On a live host, never remove registry-publish and source access in the same layer | dead-man's switch wipes the host | GitLab VR, Nov 24 2025 |
| C4 | Rotate publish-capable secrets before all others | stop propagation first | Microsoft, Aug 4 2026 |
| C5 | Remove planted hooks before re-enabling any agent that opened the repo | prevent re-infection | The Hacker News, Aug 2026 |
| C6 | Rebuild only after the exposed runner is paused | rebuild on a clean host | GitLab VR, Nov 24 2025 |

A watched publish-capable secret is held late by C1; because an isolated host cannot propagate,
C4 does not also apply to it. The planner and the checker agree on this exclusion, and the
property tests assert both over 500 generated exposure graphs.

## What Defuse does not claim

- It does not detect the initial compromise; it contains a known one from an advisory or a
  detector hit.
- Where it lacks access (for example group audit events need Owner), it degrades gracefully and
  records exactly what it could not see in the incident record, rather than guessing.
