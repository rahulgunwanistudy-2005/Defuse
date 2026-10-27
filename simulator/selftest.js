'use strict';
// Proves the guards keep the simulator inert outside the sandbox. Runs in plain Node, no CI.
const assert = require('assert');

function withEnv(env, fn) {
  const saved = { ...process.env };
  for (const k of Object.keys(process.env)) delete process.env[k];
  Object.assign(process.env, env);
  try { return fn(); } finally {
    for (const k of Object.keys(process.env)) delete process.env[k];
    Object.assign(process.env, saved);
  }
}

delete require.cache[require.resolve('./guards')];
const { inertReason } = require('./guards');

// 1. No DEFUSE_SIM -> inert
withEnv({}, () => assert.ok(inertReason(), 'must be inert with no env'));

// 2. DEFUSE_SIM but wrong host -> inert
withEnv({ DEFUSE_SIM: '1', CI_SERVER_HOST: 'evil.example.com', CI_PROJECT_PATH: 'defuse-sandbox/app-a' },
  () => assert.match(inertReason(), /not allow-listed/));

// 3. Right host but project outside sandbox -> inert
withEnv({ DEFUSE_SIM: '1', CI_SERVER_HOST: 'gitlab.com', CI_PROJECT_PATH: 'victim-corp/app' },
  () => assert.match(inertReason(), /outside/));

// 4. All three guards pass -> active (null reason)
withEnv({ DEFUSE_SIM: '1', CI_SERVER_HOST: 'gitlab.com', CI_PROJECT_PATH: 'defuse-sandbox/app-a' },
  () => assert.strictEqual(inertReason(), null, 'must be active inside the sandbox'));

// 5. behavior reads only variable NAMES, never values
const { readableVariableNames } = require('./behavior');
withEnv({ NPM_TOKEN: 'super-secret-value', PATH: '/usr/bin' }, () => {
  const names = readableVariableNames();
  assert.ok(names.includes('NPM_TOKEN'), 'collects the name');
  assert.ok(!names.join('|').includes('super-secret-value'), 'never the value');
});

console.log('simulator self-test: all guards hold');

// Published fixture packages contain no executable install hooks or propagation loader.
const fixture = require('./publish-fixture');
const fixtureManifest = fixture.manifest('2.4.1');
assert.strictEqual(fixtureManifest.scripts, undefined);
assert.strictEqual(fixtureManifest.name, '@defuse-sandbox/strings');
assert.throws(() => fixture.manifest('latest'));
