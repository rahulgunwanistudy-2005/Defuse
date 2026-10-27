# Frontend redesign verification

Captured on 2026-10-27 against the production SvelteKit build and the engine's inert, in-memory local scenario. The displayed incident timings are modeled scenario timestamps, not measured live GitLab containment.

- `landing-desktop.png`: 1440 × 1000 desktop hero.
- `landing-full.png`: complete desktop landing page.
- `landing-mobile.png`: 375 × 812 mobile hero.
- `workspace-mobile.png`: mobile incident list.
- `console-desktop.png`: connected incident timeline and metrics.

Validation: `npm run check`, `npm run lint`, `npm run build`, and the 17-test Playwright suite. Browser coverage includes engine-derived landing metrics, console links, live-event reconnection without duplicates, plan explanation, replay, ledger, all five mobile console routes, workflow keyboard navigation, incident search/filter recovery, engine failure/reconnect, empty data, theme persistence and reduced motion. Visual capture also checks for browser runtime errors and page overflow.

Reference and implementation details are recorded in `web/DESIGN.md`; generated artwork and exact prompts are saved under `web/static/images/`.
