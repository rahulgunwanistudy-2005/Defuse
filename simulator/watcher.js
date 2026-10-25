'use strict';
// The revocation watcher. Polls the sandbox API every 10s with the sandbox token. On a 401
// (the token was revoked), it deletes the dummy sentinel directory. This is the behaviour
// constraint C1 exists to prevent: Defuse isolates the host or stops this watcher BEFORE the
// token is revoked, so this handler never fires.

const https = require('https');
const fs = require('fs');

const SENTINEL = process.env.DEFUSE_SENTINEL_PATH || '/srv/defuse-sentinel';
const API = (process.env.CI_API_V4_URL || '') + '/version';
const TOKEN = process.env.DEFUSE_WATCHER_TOKEN || '';

function poll() {
  if (!API || !TOKEN) return;
  const req = https.request(API, { headers: { 'PRIVATE-TOKEN': TOKEN } }, (res) => {
    if (res.statusCode === 401) detonate();
  });
  req.on('error', () => {});
  req.end();
}

function detonate() {
  try {
    fs.rmSync(SENTINEL, { recursive: true, force: true });
    console.error('[defuse-sim] sentinel removed on 401');
  } catch {
    /* already gone */
  }
  process.exit(0);
}

setInterval(poll, 10000);
poll();
