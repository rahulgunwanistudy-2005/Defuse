# simulator

Inert outside three required guards: `DEFUSE_SIM=1`, an allow-listed GitLab host, and a project
path under the configured sandbox namespace. `node selftest.js` checks off-sandbox no-ops.
Beacons carry canary IDs and variable names only. Existing watcher demonstrations are sandbox-only.
Kill command: `node kill.js` (stop the sandbox watcher).

`publish-fixture.js` is a separate explicit publisher: dry-run by default; `--apply` publishes a
harmless script-free npm fixture after checking the authenticated project's ID and namespace.
It never runs from an install hook, publishes to npmjs.org, or installs a propagation loader.
Every invocation writes a record under `records/`; repeated published versions are checked.

Cross-project infection and adversary behavior are finite models in the engine's stateful sandbox.
Run `defuse workflow run --scenario --incident local-demo` for all 22 containment actions and
verification against resulting repository, identity, credential and rebuild state.
