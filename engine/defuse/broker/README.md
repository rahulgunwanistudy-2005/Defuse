# Local credential authority

A separate loopback process using existing GitLab APIs and a local SQLite metadata journal.
No paid external secret manager is required. It issues project/deploy token replacements,
installs them into explicit project/group consumers without reading existing CI secret contents,
and returns metadata-only receipts. Newly issued values stay inside this process and are not
logged, journaled, or returned to the containment engine.

Run `uvicorn defuse.broker.app:create_app --factory --host 127.0.0.1 --port 8040`.
Configure a dedicated `DEFUSE_BROKER_GITLAB_TOKEN` and shared `DEFUSE_CREDENTIAL_BROKER_TOKEN`.
Native API availability depends on existing GitLab permissions and entitlement; no upgrades run.
Non-GitLab credentials require explicitly configured local provider commands that attest upstream
revocation. Missing/failed providers refuse replacement. See `docs/credential-broker.md`.
