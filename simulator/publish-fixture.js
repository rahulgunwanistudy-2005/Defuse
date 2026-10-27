'use strict';
// Explicit, finite publishing of an inert fixture. Never invoked by an install hook.
// There is no propagation loader, executable hook, watcher or credential collection in this package.
const { inertReason, instanceHost, projectPath } = require('./guards');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

function manifest(version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('fixture version must be exact semver');
  return { name: '@defuse-sandbox/strings', version, private: false,
    description: 'Defuse inert sandbox fixture; contains no install scripts', main: 'index.js' };
}

async function publishFixture({ dryRun = true, version = '2.4.1', request = fetch } = {}) {
  const reason = inertReason();
  if (reason) return { status: 'inert', reason };
  const id = process.env.CI_PROJECT_ID || '';
  if (!/^\d+$/.test(id)) throw new Error('a numeric sandbox CI_PROJECT_ID is required');
  const host = instanceHost();
  if (!/^[a-zA-Z0-9.-]+$/.test(host)) throw new Error('invalid instance hostname');
  const registry = `https://${host}/api/v4/projects/${id}/packages/npm/`;
  const packageJson = manifest(version);
  const record = { operation: 'publish_inert_fixture', project: projectPath(), project_id: Number(id),
    package: packageJson.name, version, dry_run: dryRun, status: 'dry_run', at: new Date().toISOString() };
  if (dryRun) return record;
  if (!Object.hasOwn(process.env, 'CI_JOB_TOKEN')) throw new Error('sandbox job authentication is required');
  // Authentication is passed only to the configured GitLab origin; no response body is logged.
  const response = await request(`https://${host}/api/v4/projects/${id}`, {
    headers: { 'JOB-TOKEN': process.env.CI_JOB_TOKEN }, redirect: 'error'
  });
  if (!response.ok) throw new Error(`sandbox project lookup returned HTTP ${response.status}`);
  const project = await response.json();
  if (project.path_with_namespace !== projectPath()) throw new Error('project id/path sandbox check failed');
  const previous = await request(registry + encodeURIComponent(packageJson.name), {
    headers: { 'JOB-TOKEN': process.env.CI_JOB_TOKEN }, redirect: 'error'
  });
  if (previous.status === 200) {
    const metadata = await previous.json();
    const installed = metadata.versions && metadata.versions[version];
    if (installed) {
      if (installed.scripts || installed.description !== packageJson.description) {
        throw new Error('existing version is not the inert fixture; refusing to overwrite it');
      }
      record.status = 'already_satisfied';
      return record;
    }
  } else if (previous.status !== 404) throw new Error('cannot verify existing fixture versions');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'defuse-inert-package-'));
  try {
    fs.writeFileSync(path.join(dir, 'package.json'), JSON.stringify(packageJson, null, 2));
    fs.writeFileSync(path.join(dir, 'index.js'), "module.exports = 'defuse inert fixture';\n");
    // Keep the credential as an npm environment reference, never write its resolved value.
    fs.writeFileSync(path.join(dir, '.npmrc'),
      `registry=${registry}\n//${host}/api/v4/projects/${id}/packages/npm/:_authToken=\${CI_JOB_TOKEN}\n`, { mode: 0o600 });
    execFileSync('npm', ['publish', '--ignore-scripts', '--registry', registry,
      '--userconfig', path.join(dir, '.npmrc')], { cwd: dir, stdio: 'ignore' });
    record.status = 'applied';
    return record;
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

if (require.main === module) {
  const dryRun = !process.argv.includes('--apply');
  const versionAt = process.argv.indexOf('--version');
  const version = versionAt >= 0 ? process.argv[versionAt + 1] : '2.4.1';
  const out = process.env.DEFUSE_SIM_RECORDS_DIR || 'records';
  publishFixture({ dryRun, version }).then((record) => {
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, `publish-${Date.now()}.json`), JSON.stringify(record, null, 2));
    process.stdout.write(JSON.stringify(record) + '\n');
  }).catch(() => {
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, `publish-failed-${Date.now()}.json`),
      JSON.stringify({ operation: 'publish_inert_fixture', dry_run: dryRun, status: 'failed' }));
    process.stderr.write('Sandbox fixture publication failed; no credential output was retained.\n');
    process.exitCode = 1;
  });
}
module.exports = { manifest, publishFixture };
