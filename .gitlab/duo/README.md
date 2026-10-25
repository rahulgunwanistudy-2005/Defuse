# .gitlab/duo

Source of truth for Defuse's GitLab Duo Agent Platform flows. The LLM interprets, drafts and
explains; deterministic code (the engine) decides and acts. Every LLM output is validated
against a schema before anything consumes it.

- `flows/` — flow registry v1 YAML (ambient environment; API-only flows use `coding_environment: none`).
- `prompts/` — the prompt body each flow's `prompt_id` refers to.
- `ioc.schema.json` — the schema `advisory-intake` output is validated against (generated from
  the Pydantic model; `uv run defuse schema write`).

Create each flow in the GitLab UI or AI Catalog from these files, then record its catalog link
in the top-level README. Tool governance: deny delete-class tools for these flows; allow only
the writes each one needs (see `docs/governance.md`).
