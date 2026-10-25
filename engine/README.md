# engine

The Defuse engine: Python 3.12 package `defuse`, a FastAPI service and the `defuse` CLI.

| Package | What it does |
| --- | --- |
| `defuse/model` | Pydantic types: IOC set, graph nodes and edges, actions, plan, incident |
| `defuse/collect` | Async GitLab and GCP collectors (metadata only, never secret values) |
| `defuse/graph` | Exposure graph and epidemic tree, deterministic JSON |
| `defuse/plan` | Action catalog, safety constraints C1-C6, layered planner, unsat explainer |
| `defuse/execute` | Action executors, child-pipeline compiler, dry-run, action ledger |
| `defuse/verify` | Post-containment checks and Security Standard timing metrics |
| `defuse/api` | REST + Server-Sent Events for the console |

Run: `uv sync && uv run defuse --help`. Serve: `uv run uvicorn defuse.api.app:create_app --factory`.
Test: `uv run pytest` (property tests use the `ci` Hypothesis profile at 500 examples).
