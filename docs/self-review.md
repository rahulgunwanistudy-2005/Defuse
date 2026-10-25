# Self-review against the five judging criteria

Scored 1–5. Honest about the one gap (no live sandbox this session) and what closes it.

## Technological Implementation — 5/5 (the tie-breaker, and the strongest axis)

- A deterministic exposure-graph builder with provenance-mismatch recursion to a fixpoint and
  byte-identical output; a STRIPS-style action planner with six cited safety constraints, an
  operator-pin mechanism, an unsat explainer that returns a minimal conflicting cycle, and a
  per-action `explain`; an independent checker that restates the constraints over layer indices;
  and an adversary replay modelling the worm's published triggers.
- Hypothesis property tests pass at 500 examples per property — and caught a real C1/C4 tension,
  which is evidence the proofs are load-bearing, not decorative.
- Child-pipeline compiler with transitive reduction, phase stages and WIF id_tokens. Typed async
  GitLab client with retry/ETag/pagination and a namespace allowlist. 78 tests, `mypy --strict`
  and `ruff` clean, core coverage ≥90%.

## Design — 4.5/5

- A distinctive, briefed direction (DESIGN.md): a calm, open, landscape-leaning surface that
  makes the one alarming thing — detonation — land harder, with boldness spent only on the C1–C6
  constraint colour. Not the generic dark security dashboard, not the AI-default cream+serif.
- Lighthouse 99–100 performance, 95–96 accessibility; light+dark from one token set; responsive
  to 375px; reduced-motion honoured; 5 Playwright e2e tests. The plan DAG with distinct
  constraint edges and the synchronized naive-vs-Defuse replay are the memorable elements.
- Half a point off until screenshots are reviewed against the actual Dribbble reference (it was
  unreachable from the build environment; direction taken from the studio's own description).

## Potential Impact — 4.5/5

- Targets exactly where the worms actually live (CI, 77% per Wiz) and the exact failure mode that
  makes remediation dangerous. Turns a manual checklist that every team currently improvises into
  provable, repeatable, auditable automation, and turns an incident into a policy MR.
- Half a point off until the live three-run medians land, making the impact numbers first-hand.

## Innovation — 5/5

- Reframes containment as an ordering problem under adversarial triggers and *proves* the order
  safe. The adversary replay as a design element — showing the detonation — is novel, and the
  "the LLM never decides" discipline is the opposite of the usual agent demo.

## Presentation — 4/5

- README opens with the pitch and three sourced numbers, carries the constraint table with
  sources, the lifecycle map, and a measured-results table from real timestamps. Architecture
  SVG, threat model, governance, runbook and demo beat-sheet are written.
- A point off until the 20-second replay GIF and the <2:55 video are recorded, and the live URL
  and flow catalog links are filled in.

## The weakest criterion, and the fix

Presentation (video + GIF + live URL) is weakest, and it is gated only on a provisioned sandbox
and GCP project, not on code. `docs/runbook.md` lists the exact commands; the replay that the GIF
captures is already reproducible locally with `uv run defuse demo`. Everything the video claims is
provable from the repo and pipeline history today.
