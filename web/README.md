# Defuse web

SvelteKit 2, Svelte 5 and TypeScript. The Agentix-inspired landscape landing page opens the existing incident console: live timeline (SSE), exposure map, safety plan and explanations, adversary replay, verification evidence and action ledger.

The landing page reads incidents, exposure counts and metrics from the engine. It includes search, status filters, reconnect and empty states. Scenario data and modeled timings are labeled. The frontend adds no mutation endpoints.

```sh
npm ci --ignore-scripts
DEFUSE_API_BASE=http://localhost:8000 npm run dev
npm run check
npm run lint
npm test
```

`npm test` builds the production app and starts it alongside an in-memory seeded engine. Set `PW_CHROMIUM=/path/to/chromium` if a custom browser executable is required.

To run the production build:

```sh
npm run build
HOST=127.0.0.1 PORT=5173 DEFUSE_API_BASE=http://localhost:8000 node build
```

API requests stay on the frontend’s origin and pass through the server-side `/api` proxy, including SSE streams. Configure `DEFUSE_API_BASE` at runtime; `DEFUSE_API` is retained as a fallback.

Visual choices, source references, fidelity limits and artwork provenance are documented in [DESIGN.md](DESIGN.md). The interface defaults to daylight, persists an optional dark theme, supports keyboard navigation and reduced motion, and adapts to mobile widths. Current desktop/mobile screenshots are in `../docs/evidence/frontend/`. Previous Lighthouse figures have not been re-measured for this redesign.
