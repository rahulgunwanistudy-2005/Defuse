# web

The Defuse incident console: SvelteKit 2 + Svelte 5 (runes) + TypeScript, plain CSS tokens.

Views: incident list; live timeline (SSE); exposure map (d3-force); plan DAG (ELK layered,
safety-constraint edges in `--bond`, explain panel); naive-vs-Defuse replay; record (metrics,
action ledger). Design direction in `DESIGN.md`.

```
npm install
DEFUSE_API=http://localhost:8000 npm run dev    # proxies /api to the engine
npm run check && npm run lint                    # svelte-check + eslint
npm run build                                    # adapter-node; set VITE_API_BASE for a split origin
PW_CHROMIUM=/path/to/chromium npm test           # Playwright e2e
```

Quality floor met: Lighthouse performance 99–100 and accessibility 95–96, responsive to 375px,
visible focus, `prefers-reduced-motion` honored, light and dark themes from one token set.
