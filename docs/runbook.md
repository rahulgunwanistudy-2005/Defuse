# Runbook — producing the live evidence

This build session had no GitLab sandbox credentials or GCP project (docs/decisions.md D3), so
the live artifacts below are produced by running these commands against a provisioned sandbox.
Nothing in the repo is invented; the scenario numbers are the in-memory scenario's real timings.

## Local

```
cd engine && uv sync
uv run defuse demo                       # seed the scenario, print its real metrics
uv run uvicorn defuse.api.app:create_app --factory   # API + SSE at :8000, OpenAPI at /docs
cd ../web && DEFUSE_API=http://localhost:8000 npm run dev   # console at :5173
```

## Live (needs a sandbox + GCP project)

1. `cd infra && terraform init -backend-config=... && terraform apply` → Cloud Run URLs, WIF.
2. Record fixtures once: `uv run defuse fixtures record` (scrubs values; replaces the synthetic
   contract fixtures).
3. Run three containment passes from scratch; record median timings into the README table.
4. Create the four flows in the GitLab AI Catalog from `.gitlab/duo/flows/`; record their links.
