'use strict';
// Inert worm simulator. On a guarded sandbox runner it: beacons variable NAMES to the
// sinkhole; if an over-scoped sandbox deploy token is present, republishes a sibling sandbox
// library with a bumped patch and no matching commit (provenance mismatch); commits a planted
// SessionStart hook; and on the persistent runner installs a watcher that, on a 401, deletes
// the dummy sentinel directory. Everywhere else it exits 0 in silence.

const { inertReason } = require('./guards');

async function main() {
  const reason = inertReason();
  if (reason) {
    // Silent no-op off the sandbox. This is the safety property.
    process.exit(0);
  }
  const behavior = require('./behavior');
  try {
    await behavior.run();
  } catch (err) {
    // A simulator must never break a real install; swallow and exit clean.
    console.error('[defuse-sim] contained error:', err && err.message);
  }
  process.exit(0);
}

main();
