# simulator — inert worm simulator (sandbox only)

Makes the threat real on camera without ever being malware. Published only to the **sandbox
project's own package registry**, never to npmjs.org.

## The three guards (`guards.js`)

`preinstall.js` exits 0 and does nothing unless **all three** hold:

1. `DEFUSE_SIM=1` is set.
2. `CI_SERVER_HOST` is in the allow-list (default `gitlab.com`, override `DEFUSE_SIM_ALLOWED_HOSTS`).
3. `CI_PROJECT_PATH` is under the sandbox namespace (default `defuse-sandbox/`).

`node selftest.js` proves the package is inert off the sandbox and never reads a secret value.

## Behaviour once guarded (`behavior.js`)

- Beacons a random canary id and the **names** of readable CI variables (never values) to the sinkhole.
- If an over-scoped sandbox deploy token is present, republishes a sibling sandbox library with a
  bumped patch and the same loader, with no matching commit — the provenance mismatch Defuse detects.
- Commits a planted `.claude/settings.json` `SessionStart` hook to the sandbox repo.
- On the persistent runner only, installs a user systemd watcher that polls the API every 10s and,
  on a 401, deletes `/srv/defuse-sentinel/` (dummy files). That deletion is the visible detonation.

## Kill switch

`npm run kill` (or `node kill.js`) stops and removes the watcher and its unit file. Safe anywhere.
