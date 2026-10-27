# Runbook

## Working local demo — no paid services

From the repository root, start the engine:

```sh
cd engine
uv sync --frozen
DEFUSE_DATABASE_URL=sqlite+aiosqlite:///./demo-complete.db uv run uvicorn defuse.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd web
npm ci --ignore-scripts --no-audit --no-fund
DEFUSE_API_BASE=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

Open http://127.0.0.1:5173. The fresh seeded scenario completes all 22 actions and reports
`verified`. Use a fresh database filename if an older demo already seeded an unfinished scenario.
Browse Map, Plan, Replay and Record. In Replay, Play compares the naive destroyed sentinel with
the safe plan's preserved sentinel. Record shows applied actions and positive verification checks.
All of this uses stateful inert transports and a synthetic display clock, clearly labeled Scenario.
It is not a real incident or a live timing measurement.

For three fresh model runs and reproducible evidence:

```sh
engine/.venv/bin/python scripts/record_local_runs.py
```

The files in `docs/evidence/local-runs/` include status, action ledger, checks and local wall-clock
measurements. To run one independent CLI workflow:

```sh
cd engine
uv run defuse workflow run --scenario --incident local-check --out /tmp/defuse-result.json
```

Use a fresh scenario incident ID each time. For a production console build, `npm run build`, then
`DEFUSE_API_BASE=http://127.0.0.1:8000 PORT=3000 node build`. The server forwards REST and SSE.

## Verification commands

```sh
cd engine
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m defuse.automate.flow_config --check
HYPOTHESIS_PROFILE=ci uv run pytest --cov=defuse --cov-fail-under=75
cd ../web
npm run check
npm run lint
npx playwright install chromium
npm test
cd ..
node simulator/selftest.js
docker compose config --quiet
```

Browser tests launch an isolated engine and production console. `PW_CHROMIUM` can select an
existing Chromium executable. Actual Docker builds need a running Docker daemon; configuration
validation alone does not establish that an image builds. `scripts/build-images.sh` requests SBOM
and provenance; `scripts/verify-images.sh` rejects missing attestations.

## Live sandbox integration

See `.env.example` for names and `docs/credential-broker.md` for the free local authority.
Supply existing GitLab sandbox authentication, exact namespace, runner-host mapping, trusted
baseline commit SHAs, explicit token-consumer bindings and a shared database. Configure GCP/WIF
and host access only when using real GCP actions. Apply `uv run alembic upgrade head` before use.
Never print credential values or use a shared production runner for this demonstration.

```sh
cd engine
uv run defuse plan /absolute/path/ioc.json --namespace defuse-sandbox --incident actual-incident
uv run defuse workflow run /absolute/path/ioc.json --namespace defuse-sandbox --incident actual-incident --dry-run
```

Review dry-run records and project settings before the live command without `--dry-run`.
Repository changes use stable MRs and full diff/content checks. Set
`DEFUSE_AUTO_MERGE_REMEDIATION=true` only on the prepared sandbox when automatic merge is intended;
otherwise pending merge approvals stop dependent work. Protected-branch policy remains enforced.

`defuse workflow prepare incidents/ID/request.json plan.gitlab-ci.yml` saves incident context
and compiles CI jobs. Each job loads saved facts/plan and coordinates through persistent leases.
Repeated successful actions are skipped; failed or operator-required prerequisites block dependents.
`defuse workflow export ID /tmp/record.json` exports the complete record.

Duo is opt-in (`DEFUSE_DUO_ENABLED=true`) and needs authenticated `glab` plus existing platform
access/credits. Register the four generated definitions in `.gitlab/duo/flows/`, configure triggers
and deny delete-class tools per `docs/governance.md`. No paid credits or upgrades are purchased.
`defuse workflow flow REQUEST.json --run --output OUTPUT.json` drafts in an isolated scratch
folder; `apply-flow` revalidates before creating an MR. `intake-pipeline` qualifies failed detector
evidence. `postmortem` creates an idempotent incident issue and a prevention-policy proposal.
Policy proposals require review/merge; they do not silently change variable scopes.

## Evidence still needed for submission

Run three real incidents in a configured sandbox; retain child-pipeline URLs, flow-authored MRs,
credential-provider and host verification, real timestamps and credit usage. Record the final public
video and GitLab catalog links. Hosting is excluded from this build task. No local test can create
account entitlement or establish live GitLab/GCP behavior without those accounts.
