# Build completion, excluding hosting

The local implementation now completes collection, graph/planning, 22 containment actions,
verification and agent restoration through the same deterministic action code used by live adapters.
Three fresh modeled runs are committed as evidence under `docs/evidence/local-runs/`.

| Area | Implemented and locally checked | External evidence still required |
| --- | --- | --- |
| Collection | Metadata-only paginated GraphQL variables, unsafe REST refusal, scoped client | Actual sandbox recordings and permissions |
| Remediation | Stable MRs, exact diffs/content, trusted baseline pins, merge verification | Protected-branch configuration and trusted SHAs |
| Credentials | Authenticated local GitLab authority, receipt validation, consumer installation | Existing GitLab entitlement; provider for non-GitLab secrets |
| Agent governance | Project-role isolation, durable checkpoint, verified restoration | Effective account/role configuration |
| Execution | Shared context/leases, dry-run, ledger, clean rebuild and job verification | Shared CI database, executor image and clean runners |
| Duo | Generated v1 definitions, packaged prompts, schemas, headless validation/application | Registration, triggers, authenticated CLI and available credits |
| Records/policy | Incident export, idempotent issue/MR, executable age/lockfile checks | Review/merge proposed policies; scoped variables need review |
| Sinkhole | Durable observations; restart cannot fake a quiet window | A reachable service observing the complete real window |
| Packaging | Engine/web Dockerfiles, Compose, SBOM/provenance scripts, executable CI | Docker daemon/image build, registry and remote CI run |
| Console | Production API/SSE forwarding, graph, plan, replay, ledger, mobile checks | Final public submission recording |

No paid credential-manager service is needed: see `credential-broker.md`. Nothing in this run
purchases credits, upgrades plans or provisions hosting. Native GitLab APIs depend on permissions
already available; missing rights fail explicitly.

The inert simulator retains all three guards. An explicit publisher can publish a harmless,
script-free fixture to the allow-listed sandbox registry. Cross-project spread, dangerous watcher
triggers and destruction are modeled, not implemented as an autonomously spreading payload.

Local success is evidence of implementation and modeled behavior. It is not proof of live
hands-off containment, platform activation, image build or a submission-ready public entry.
