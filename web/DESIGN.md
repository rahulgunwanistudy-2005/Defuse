# Defuse frontend: Agentix reference implementation

## Brief and sources

Recreate the visual language of [Emote Agency’s Agentix landing page](https://dribbble.com/shots/27733315-Agentix-AI-Agents-Landing-Page), wrapping Defuse’s existing deterministic engine and API. Reference inspected on 2026-10-27 through the public Dribbble page and its full-resolution images. Firecrawl was unavailable because the connected account had no remaining credits; the public page and image assets were inspected directly instead.

Inspected references:

- [Landscape, centered headline, floating pill navigation and glass tiles](https://cdn.dribbble.com/userupload/49030135/file/d296ff88090f525fa63c96b302591bc2.png)
- [Lime ticket-shaped metric cards and workflow strip](https://cdn.dribbble.com/userupload/49030134/file/9200caf4cf4d6dbd4fc3dfff84cc6152.png)
- [Landscape closing section, translucent CTA and lime footer](https://cdn.dribbble.com/userupload/49030136/file/2a4f5099501e2af7f8c35f833f0d0dd5.png)
- The public animation also showed oversized sequential numerals and cloud illustrations.

The reference is a design presentation, not an inspectable production website. Its CSS, exact typeface, timing curves, breakpoints and hover states are unavailable. The implementation closely follows the inspected composition; the typeface, exact spacing, responsive behavior and motion timing are implementation choices, not extracted values. The scenery is newly generated reference-guided artwork, not an exact source asset.

## Visual system

The reference’s whitespace, alpine scenery, soft peach/lavender clouds, olive buttons, lime cards and translucent tiles define the direction. Defuse’s incident data and safety vocabulary replace Agentix’s marketing content. No customer counts or performance claims are imported from the reference.

| Role | Value | Evidence |
| --- | --- | --- |
| Page | `#FCFCFA` | Published Dribbble palette |
| Ink | `#171B10` | Visual approximation of dark olive text |
| Primary olive | `#4B6209` | Visual approximation of reference CTA |
| Lime | `#B2C446` | Visual approximation of ticket cards/footer |
| Landscape blue | `#445EB2`, `#16315C` | Published Dribbble palette; carried through artwork |
| Pastel accent | `#CAA2A4`, `#E6A26C` | Published Dribbble palette; carried through clouds |
| Alarm | `#B43F32` | Defuse semantic failure state |
| Constraint | `#586AA4` | Defuse semantic safety edge state |

`src/lib/tokens.css` is the single source for semantic colors, spacing and shape. Dark mode is a complementary Defuse theme, not a state shown by the reference. Daylight is the default; the user’s theme choice persists.

Typography uses DM Sans for both headlines and UI, with regular-weight display text, tight headline tracking, and a restrained italic olive accent. IBM Plex Mono remains limited to literal identifiers, package specs and code. These are chosen equivalents; the reference font could not be verified.

## Layout and components

- Full-width alpine hero with a centered floating navigation pill, centered two-line headline, working console/replay links, pastel cloud banks, gently drifting frosted squares and two contextual glass panels.
- Four lime ticket cards showing the connected engine’s incident count and the featured incident’s exposed jobs, executed actions and containment duration. Unavailable values show a dash. Scenario timing is labeled.
- Three sequential workflow tabs with oversized numerals, cloud/graph illustrations, keyboard support, and links to the real map, plan and evidence views.
- Engine-backed incident list with search, active/verified filters, manual refresh, explicit empty and disconnected states, and reconnect behavior.
- Explanatory disclosure rows, a landscape closing CTA, and a lime footer.
- Incident views share the same typography, palette, rounded cards, capsule navigation, semantic status tones and theme control. Existing graph, plan, replay, ledger and SSE implementations remain connected.

The landing content is centered within a maximum width of 1240px; the hero and closing scene are full bleed. Metrics use four columns, then two on mobile. Workflow and FAQ sections stack on small screens. The incident table becomes wrapping rows. Console navigation remains visible on small screens.

## Motion and accessibility

A single 850ms hero entrance, 22-second cloud drift and 9-second glass-tile float recreate the reference’s atmosphere. These timings are chosen approximations. Controls use short state transitions. `prefers-reduced-motion` disables atmospheric movement and smooth scrolling. The existing adversary replay advances only when the user presses Play.

Visible focus, a skip link, semantic headings, accessible tab state and arrow-key navigation, named search and theme controls, native disclosure elements, and decorative image alternatives are included.

## Backend boundary

The landing loader uses the existing `/api/incidents`, graph and metrics endpoints. The same-origin proxy remains the backend boundary. Navigation opens the existing incident routes. Missing optional graph/metric responses display dashes; a failed incident-list response shows a reconnect state. The interface makes no new mutating requests. The planner, executor, C1–C6 data, sandbox restrictions, secret handling and simulator guards are unchanged.

## Artwork

- `static/images/alpine-landscape.png`: newly generated alpine lake illustration with white negative space for real HTML content.
- `static/images/pastel-cloud.png`: newly generated peach/lavender cloud on a transparent background.
- `static/images/provenance.json`: generation method, reference and exact prompts.

Both assets were created with the built-in image generation tool and copied into the project. No marketing text or UI is baked into the artwork.
