# Instructions for agents working in this repository

Defuse contains supply-chain worms on GitLab CI. Read `README.md` first, then `docs/architecture.md`.

## Rules

- The planner and executor are deterministic code. Do not move a decision into a prompt.
- Never read, print or log a secret value. Collectors request names and metadata only; the
  GraphQL variable query must not select `value` (a test enforces this).
- Every mutating action supports `--dry-run`, is idempotent, and writes an action record.
- Mutating GitLab calls outside the configured sandbox namespaces are refused in the client
  layer. Do not add a bypass.
- The simulator in `simulator/` is inert outside the sandbox. Do not remove or weaken any of
  its three guards.
- Safety constraints C1 to C6 live in `engine/defuse/plan/constraints.py` as data. A change to
  one needs a matching change to the property tests and to the README constraint table.

## Checks before you push

```
cd engine && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd web && npm run check && npm run lint && npm test
```

## Flows

Flow definitions live in `.gitlab/duo/flows/`. LLM output is validated against a schema
before anything consumes it. A flow that cannot fill a required field refuses and says which.
