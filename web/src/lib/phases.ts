import type { Phase } from './api';

export const PHASES: Phase[] = [
  'isolate',
  'preserve',
  'eradicate',
  'rotate',
  'quarantine',
  'rebuild',
  'verify'
];

export const PHASE_COLOR: Record<Phase, string> = {
  isolate: 'var(--phase-isolate)',
  preserve: 'var(--phase-preserve)',
  eradicate: 'var(--phase-eradicate)',
  rotate: 'var(--phase-rotate)',
  quarantine: 'var(--phase-quarantine)',
  rebuild: 'var(--phase-rebuild)',
  verify: 'var(--phase-verify)'
};

export const NODE_GLYPH: Record<string, string> = {
  package_version: '◆',
  pipeline: '▤',
  job: '▸',
  runner: '⚙',
  host: '▣',
  secret: '⚿',
  project: '▦',
  registry_package: '◈',
  hook_file: '⟲',
  agent_session: '◐',
  watcher: '◉'
};

export const NODE_LABEL: Record<string, string> = {
  package_version: 'package version',
  pipeline: 'pipeline',
  job: 'CI job',
  runner: 'runner',
  host: 'host',
  secret: 'secret',
  project: 'project',
  registry_package: 'registry package',
  hook_file: 'planted hook',
  agent_session: 'agent session',
  watcher: 'watcher'
};
