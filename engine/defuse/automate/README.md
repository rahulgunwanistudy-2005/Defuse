# automate

Deterministic repository remediation, credential receipt validation, agent isolation, and
successful-rebuild checks. LLMs draft prose or interpret advisories; they never choose targets,
file contents, action order or completion status.

`repository.py` checks complete MR diffs and contents before merge and verifies the target
branch afterwards. `broker.py` accepts metadata receipts from a credential authority that owns
replacement values. `sandbox.py` exercises these integrations without any remote side effects.
`flows.py` validates every output; `flow_config.py` generates self-contained Duo YAML and schemas.
