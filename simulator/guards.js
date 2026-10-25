'use strict';
// The three guards. All must pass, or the simulator exits 0 and does nothing.
// This is what makes the package inert everywhere except the Defuse sandbox.

const ALLOWED_HOSTS = (process.env.DEFUSE_SIM_ALLOWED_HOSTS || 'gitlab.com').split(',');
const SANDBOX_PREFIX = process.env.DEFUSE_SIM_NAMESPACE || 'defuse-sandbox/';

function instanceHost() {
  const url = process.env.CI_SERVER_HOST || '';
  return url.trim();
}

function projectPath() {
  return (process.env.CI_PROJECT_PATH || '').trim();
}

// Returns the reason it is inert, or null when all guards pass.
function inertReason() {
  if (process.env.DEFUSE_SIM !== '1') return 'DEFUSE_SIM is not set to 1';
  const host = instanceHost();
  if (!ALLOWED_HOSTS.includes(host)) return `instance host ${host || '(none)'} is not allow-listed`;
  const path = projectPath();
  if (!path.startsWith(SANDBOX_PREFIX)) return `project ${path || '(none)'} is outside ${SANDBOX_PREFIX}`;
  return null;
}

module.exports = { inertReason, instanceHost, projectPath, ALLOWED_HOSTS, SANDBOX_PREFIX };
