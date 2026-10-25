# Governance of Defuse's own agents

Rule: the LLM interprets, drafts and explains; deterministic code decides and acts. Every LLM
output is validated against a schema before anything consumes it.

## Tool governance for the Defuse flows

Background flows support Always Allow or Always Deny, and an unconfigured background rule
defaults to Always Allow. Defuse sets explicit rules so its flows cannot do more than their job:

| Flow | Allowed writes | Denied |
| --- | --- | --- |
| advisory-intake | create branch, commit `incidents/<iid>/ioc.json`, open MR, comment | delete-class tools, variable writes, token APIs |
| incident-commander | create work item, commit `incidents/<iid>/request.json`, open MR | delete-class tools |
| hook-sweeper | delete only the provided hook files, open one MR | any file outside the provided list (protected CI diff guard), delete-class tools |
| postmortem-policy | create work item, open a policy MR | delete-class tools, applying the policy itself |

Delete-class tools are denied for every flow. No flow rotates or revokes a credential — that is
the executor's job, under the namespace allowlist and the safe-order plan.

## Governance applied to infected targets

Defuse uses the same mechanism on the target: any agent identity that opened an infected repo
has its background write tools set to Deny until the planted hooks are removed. This is exactly
constraint C5, expressed as governance: `block_agent_identity` in the isolate phase,
`restore_agent_identity` only after `remove_hook_files` and verification.
