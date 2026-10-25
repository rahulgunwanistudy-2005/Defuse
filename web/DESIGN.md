# Defuse console — design plan

Two-pass per the frontend-design skill. The brief (session section 7) asks for an EOD /
incident-command instrument; the owner asks to carry the aesthetic of Emote Agency's "Agentix"
shot — calm landscapes, open space, modular interface elements floating over the scene, a few
focused moments, large scannable KPIs — onto that instrument. Those two pull in useful tension:
a calm, open, almost horizon-like surface makes the one alarming thing (a worm detonating, a
revoke firing a handler) land harder than another dark-gradient security dashboard would.

## Subject, audience, job

- **Subject.** Containing a self-replicating supply-chain worm on GitLab CI, in a provably safe
  order under adversarial triggers.
- **Audience.** A platform or security engineer mid-incident: stressed, scanning for the truth
  in seconds, deciding whether the plan's order is safe.
- **Primary job.** Show what is exposed and why the plan's order will not detonate it.

## Pass 1 — tokens

### Colour (calm surface, scarce alarm, one expressive gradient)

Agentix trades the dark-gradient AI look for open daylight, so Defuse reads on a cool, calm
paper — not warm cream (#F4F1EA is the AI tell), not tinted-near-black. Alarm is scarce so it
means something. One expressive gradient (Agentix's "expressive gradients") is reserved for the
hero horizon and the detonation moment only.

- `--mist` `#E7ECF1` — page. A cool, open, slightly-blue daylight, not white, not cream.
- `--ink` `#16222C` — primary text and structure. A true deep slate-blue, a chosen colour, not a tinted black.
- `--signal` `#0E8A6B` — safe / primary / "contained". A calm, trustworthy green-teal (the trust play), not acid.
- `--ember` `#D6402A` — alarm, detonation, failed checks. Used on at most one element per view.
- `--bond` `#6B4BD6` — the safety-constraint colour. Only C1–C6 edges and their locks wear it, nowhere else, so the plan's safety is legible at a glance. This is where the design spends its boldness.
- Gradient `--dawn` — `#2E3A8C` indigo → `#E9A23B` amber, a dawn over a ridge. Hero horizon and the detonation sweep only.

Phase ramp (the containment stages, a real sequence, so a muted sequential ramp is honest):
`isolate → preserve → eradicate → rotate → quarantine → rebuild → verify` as seven steps from
cool slate to signal-green, never rainbow.

Dark theme ("night watch") derives from the same tokens: `--ink` becomes the surface near
`#0F1821`, `--mist` the text, the gradient and the five accents keep their hue with lifted
lightness so contrast holds.

### Type

- **Display** — Space Grotesk. Technical, calm, a little mechanical; carries the instrument feel without a serif-display cliché.
- **Text** — Hanken Grotesk. Humanist, legible at a glance, clearly distinct from the display face in width and warmth.
- **Mono** — IBM Plex Mono, only where the content is literally code: action ids, secret names, package specs, commit shas. Not for labels (that is a tell).

Scale from The Elements of Typographic Style, ~1.25: 12.8 / 16 / 20 / 25 / 31 / 39 / 49. Body
16px, measure under 72ch. Weights do the emphasis; no all-caps labels, no single-word accent in
a headline, no eyebrow over every heading.

### Layout

Incident-command board: a quiet left rail of views, an open canvas with real whitespace, modular
cards floating over a thin horizon gradient at the top of each view. Left-aligned throughout;
numbers right-aligned in tables. Phase progress is a horizontal placard strip (hazmat/aviation
checklist), not a stepper with 01/02/03 unless the content is truly ordered — it is, so the
strip is numbered by phase.

```
 ┌───────────────────────────────────────────────────────────────┐
 │  ◇ defuse            ·  incident: @defuse-sandbox loader worm   │  ← thin horizon gradient
 ├────────┬──────────────────────────────────────────────────────┤
 │ Live   │   what is exposed            why the order is safe     │
 │ Map    │   ┌───────────┐  ┌───────────┐  ┌───────────┐          │
 │ Plan   │   │ time to    │  │ secrets    │  │ rogue      │  ← large scannable KPI tiles
 │ Replay │   │ containment│  │ exposed    │  │ versions   │        │
 │ Record │   │   3m 07s   │  │     4      │  │     1      │        │
 │        │   └───────────┘  └───────────┘  └───────────┘          │
 │        │   ░░ horizon fills as the exposure map grows ░░        │
 └────────┴──────────────────────────────────────────────────────┘
```

Plan view (the memorable element): ELK layered DAG, phase columns labelled, dependency edges a
thin grey, **safety-constraint edges in `--bond` with a small lock** and the C-id; hovering an
action raises a panel naming the constraint that placed it and its critical path.

```
 isolate        preserve     eradicate    rotate         ...   verify
 ┌─────────┐                               ┌─────────┐
 │ isolate │────────dep────────────────────│ rotate  │
 │  host   │══════ C1 🔒 ═══════════════════│ (npm)   │   ══ = constraint edge (--bond)
 └─────────┘                               └─────────┘   ── = dependency (grey)
```

Replay view: a synchronized split — naive baseline left, Defuse plan right — on one timeline,
ending with the sentinel shredded on the left and intact on the right; the detonation is the one
place `--ember` and the `--dawn` sweep appear together.

## Pass 2 — review against the brief and the AI defaults

Worked through the generic version and cut toward it where I'd drifted:

- Not the warm-cream-+-serif-+-terracotta look (#1 tell): the surface is cool daylight, the
  faces are two grotesques, no terracotta.
- Not the dark-gradient-acid-accent security-dashboard look: Agentix's whole point, and the
  brief's, is to avoid it.
- No SaaS-card-kit: cards share a surface but hierarchy comes from size and the horizon, radii
  differ by role (tiles 14px, chips 999px, the canvas 0), shadows are one soft token used
  sparingly, gradients are not decoration — they appear twice.
- No template chrome: no ALL-CAPS eyebrows, no `A · B · C` meta strings, no `→` glued to links,
  no mono for ordinary labels. Numbered markers appear only on the phase strip, which is a
  genuine sequence.
- Boldness spent in one place: the `--bond` safety edges in the plan view. Everything else is
  quiet so that reads.

Motion: one orchestrated moment — the exposure map drawing itself in as SSE events arrive on the
live view, and the replay's two timelines advancing together. No per-card fade-up on scroll.
`prefers-reduced-motion` drops both to instant state changes.
