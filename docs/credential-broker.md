# Free local credential service

The default choice is the included GitLab-native credential authority. It runs locally with
SQLite and existing GitLab APIs; it requires no paid secret-manager subscription. It does not
purchase plans, enable billing or create cloud resources. API availability still depends on the
GitLab account's existing permissions and entitlement; unavailable operations fail explicitly.

The containment engine and collectors never receive secret values. A separate authority process
handles only newly issued replacement credentials, installs them into explicitly named consumers,
and returns a metadata receipt. It never requests existing variable contents. Newly issued values
are not logged, stored in the journal or returned to the engine. Keep this process private.

## Setup

Provide authentication through your existing local environment or CI secret settings. Do not
paste credentials into command arguments, repository files or screenshots.

- Authority only: `DEFUSE_BROKER_GITLAB_TOKEN`, dedicated sandbox-scoped GitLab authentication.
- Both processes: `DEFUSE_CREDENTIAL_BROKER_TOKEN`, shared request authentication.
- Engine only: `DEFUSE_CREDENTIAL_BROKER_URL=http://127.0.0.1:8040`.
- Both: `DEFUSE_SANDBOX_NAMESPACES`, the exact allow-listed namespace.
- Authority: `DEFUSE_BROKER_JOURNAL`, a persistent private SQLite metadata file.

From `engine/` run:

```sh
uv run uvicorn defuse.broker.app:create_app --factory --host 127.0.0.1 --port 8040
```

The service issues GitLab project/deploy tokens with a limited lifetime and no scope escalation,
updates every configured consumer with its original environment scope/protection, and only then
returns success. Automatic project-token replacement refuses roles above Developer. Some GitLab
plans restrict project access tokens: use an already available supported token type or self-managed
sandbox; Defuse will not upgrade your account. Missing bindings refuse before issuance.

Non-GitLab credentials require a local provider command configured by target in
`DEFUSE_BROKER_PROVIDER_COMMANDS` (a JSON object of executable argument arrays). The command gets
a metadata CredentialRequest on stdin and returns private JSON containing `replacement`,
`replacement_id`, and `old_revoked: true`. The provider owns upstream issuance and revocation.
No generic variable replacement can truthfully prove an external npm/cloud credential was revoked;
without a configured provider the action refuses. No provider command runs in the local scenario.

## Receipt boundary

Schemas are in `.gitlab/duo/schemas/credential-*.schema.json`. The engine sends `POST /replace`;
incident/action IDs identify the operation. The authority independently checks sandbox membership,
consumer ownership, scopes and authentication. SQLite tracks operation fingerprints and metadata
receipts; completed retries return the same receipt. Target leases prevent simultaneous replacement
through separate authority processes sharing that journal.

The adapter requires exact incident/action/target/namespace matches and a receipt covering every
consumer scope. Extra fields and incomplete installation are rejected. A later revoke action retires
only the old GitLab identity. Failed replacement cannot unblock dependent actions. The modeled
sandbox broker creates no usable credentials; local tests do not certify a live credential rotation.
