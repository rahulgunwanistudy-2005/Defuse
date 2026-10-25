// Typed client for the Defuse engine API, plus an SSE helper with reconnect/backoff.

export type IncidentStatus =
  | 'open'
  | 'scoped'
  | 'containing'
  | 'contained'
  | 'verified'
  | 'failed';

export interface IncidentSummary {
  id: string;
  title: string;
  ioc_id: string;
  origin: string;
  status: IncidentStatus;
  namespace: string;
  created_at: string;
  detected_at: string;
  has_plan: boolean;
}

export interface Metrics {
  time_to_detect: number | null;
  time_to_scope: number | null;
  time_to_containment: number | null;
  time_to_verified_remediation: number | null;
  actions_executed: number;
  llm_credits: number | null;
}

export interface Incident extends IncidentSummary {
  first_exposure_at: string | null;
  work_item_url: string | null;
  pipeline_url: string | null;
  ioc: Ioc | null;
  metrics: Metrics | null;
  verification: Verification | null;
}

export interface Ioc {
  id: string;
  title: string;
  source_urls: string[];
  ecosystem: string;
  packages: { name: string; versions: string[]; ranges: string[] }[];
  persistence_paths: string[];
  hook_signatures: { kind: string; pattern: string }[];
  window_start: string;
  window_end: string | null;
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  generation?: number;
  rogue?: boolean;
  [k: string]: unknown;
}
export interface GraphEdge {
  src: string;
  dst: string;
  kind: string;
  evidence: string;
}
export interface Generation {
  depth: number;
  versions: string[];
  jobs: number;
  projects: number;
}
export interface ExposureGraph {
  ioc_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  generations: Generation[];
}

export interface Action {
  id: string;
  kind: string;
  target: string;
  phase: Phase;
  priority: number;
  label: string;
  params: [string, string][];
}
export type Phase =
  | 'isolate'
  | 'preserve'
  | 'eradicate'
  | 'rotate'
  | 'quarantine'
  | 'rebuild'
  | 'verify';
export interface OrderingEdge {
  before: string;
  after: string;
  reason: 'constraint' | 'dependency' | 'operator';
  constraint_id: string | null;
  note: string;
}
export interface Plan {
  ioc_id: string;
  strategy: 'defuse' | 'naive';
  actions: Action[];
  edges: OrderingEdge[];
  layers: string[][];
  completed: string[];
}

export interface ConstraintSpec {
  id: string;
  title: string;
  rationale: string;
  source: string;
  source_url: string;
}
export interface Explanation {
  action_id: string;
  label: string;
  layer: number;
  phase: Phase;
  shaped_by: { before: string; reason: string; constraint_id: string | null; note: string }[];
  constraints: ConstraintSpec[];
  critical_path: string[];
  summary: string;
}

export interface Trigger {
  kind: 'revocation_handler' | 'dead_mans_switch';
  layer: number;
  host: string;
  cause: string[];
  detail: string;
}
export interface ReplayStep {
  layer: number;
  actions: string[];
  isolated_hosts: string[];
  running_watchers: string[];
  revoked_secrets: string[];
  triggers: Trigger[];
}
export interface Replay {
  strategy: string;
  steps: ReplayStep[];
  triggers: Trigger[];
  hosts_intact: string[];
  hosts_lost: string[];
  safe: boolean;
}
export interface ReplayPair {
  defuse: Replay;
  naive: Replay;
}

export interface ActionRecord {
  incident_id: string;
  action_id: string;
  kind: string;
  target: string;
  actor: string;
  status: string;
  dry_run: boolean;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  detail: string;
  evidence_url: string | null;
  started_at: string;
  finished_at: string;
}

export interface Verification {
  checked_at: string;
  checks: { id: string; outcome: 'passed' | 'failed' | 'unverified'; detail: string }[];
}

export interface IncidentEvent {
  seq: number;
  kind: string;
  at: string;
  payload: Record<string, unknown>;
  message: string;
}

const API_BASE =
  (typeof process !== 'undefined' && process.env?.DEFUSE_API_BASE) ||
  (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_BASE) ||
  '';

function url(path: string): string {
  return API_BASE ? API_BASE.replace(/\/$/, '') + path : path;
}

async function get<T>(fetchFn: typeof fetch, path: string): Promise<T> {
  const res = await fetchFn(url(path), { headers: { accept: 'application/json' } });
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  incidents: (f: typeof fetch) => get<IncidentSummary[]>(f, '/api/incidents'),
  incident: (f: typeof fetch, id: string) => get<Incident>(f, `/api/incidents/${id}`),
  graph: (f: typeof fetch, id: string) => get<ExposureGraph>(f, `/api/incidents/${id}/graph`),
  plan: (f: typeof fetch, id: string, strategy: 'defuse' | 'naive' = 'defuse') =>
    get<Plan>(f, `/api/incidents/${id}/plan?strategy=${strategy}`),
  explain: (f: typeof fetch, id: string, actionId: string) =>
    get<Explanation>(f, `/api/incidents/${id}/plan/explain/${encodeURIComponent(actionId)}`),
  replay: (f: typeof fetch, id: string) => get<ReplayPair>(f, `/api/incidents/${id}/replay`),
  actions: (f: typeof fetch, id: string) => get<ActionRecord[]>(f, `/api/incidents/${id}/actions`),
  metrics: (f: typeof fetch, id: string) => get<Metrics>(f, `/api/incidents/${id}/metrics`),
  events: (f: typeof fetch, id: string) =>
    get<IncidentEvent[]>(f, `/api/incidents/${id}/events.json`)
};

// SSE with capped exponential backoff. Falls back silently if EventSource is unavailable.
export function streamEvents(
  id: string,
  onEvent: (e: IncidentEvent) => void,
  onState?: (live: boolean) => void
): () => void {
  let source: EventSource | null = null;
  let closed = false;
  let delay = 1000;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    if (closed) return;
    source = new EventSource(url(`/api/incidents/${id}/events`));
    source.onopen = () => {
      delay = 1000;
      onState?.(true);
    };
    source.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data) as IncidentEvent);
      } catch {
        /* ignore malformed frame */
      }
    };
    source.onerror = () => {
      source?.close();
      onState?.(false);
      if (closed) return;
      timer = setTimeout(open, delay);
      delay = Math.min(delay * 2, 15000);
    };
  };
  open();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    source?.close();
  };
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}
