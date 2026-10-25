'use strict';
// Emergency stop: stop and remove the watcher, delete markers. Safe to run anywhere.
const { execSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

try { execSync('systemctl --user disable --now defuse-watcher.service', { stdio: 'ignore' }); } catch {}
const unit = path.join(os.homedir(), '.config', 'systemd', 'user', 'defuse-watcher.service');
try { fs.rmSync(unit, { force: true }); } catch {}
try { execSync('systemctl --user daemon-reload', { stdio: 'ignore' }); } catch {}
console.log('defuse simulator stopped and removed');
