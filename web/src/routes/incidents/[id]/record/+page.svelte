<script lang="ts">
  import StatTile from '$lib/components/StatTile.svelte';
  import { fmtDuration } from '$lib/api';
  import { PHASE_COLOR } from '$lib/phases';
  import type { Phase } from '$lib/api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const inc = $derived(data.incident);
  const m = $derived(data.metrics);
  const v = $derived(inc.verification);

  const STATUS_TONE: Record<string, string> = {
    applied: 'safe',
    already_satisfied: 'safe',
    needs_operator: 'warn',
    dry_run: 'neutral',
    failed: 'alarm'
  };

  function clock(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
</script>

<section>
  <div class="tiles">
    <StatTile value={fmtDuration(m?.time_to_detect)} label="Time to detect" />
    <StatTile value={fmtDuration(m?.time_to_scope)} label="Time to scope" />
    <StatTile value={fmtDuration(m?.time_to_containment)} label="Time to containment" tone="safe" />
    <StatTile
      value={fmtDuration(m?.time_to_verified_remediation)}
      label="Time to verified remediation"
      tone="safe"
    />
  </div>
  <div class="meta-row">
    <span>{m?.actions_executed ?? 0} actions executed</span>
    <span>{m?.llm_credits ?? '—'} LLM credits this incident</span>
    <span>GitLab Security Standard timings, from stored timestamps</span>
  </div>

  {#if v}
    <div class="verify">
      <h2>Verification</h2>
      <ul class="checks">
        {#each v.checks as c (c.id)}
          <li class="check {c.outcome}">
            <span class="check-dot" aria-hidden="true"></span>
            <div>
              <span class="check-id">{c.id.replace(/_/g, ' ')}</span>
              <span class="check-detail">{c.detail}</span>
            </div>
            <span class="check-out">{c.outcome}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <div class="ledger">
    <h2>Action ledger</h2>
    <p class="sub">Append-only: every action, what it changed, and when. Each links to the
      GitLab job or MR that is the real record.</p>
    <div class="table mist-scroll">
      <table>
        <thead>
          <tr><th>Action</th><th>Target</th><th>Status</th><th>Detail</th><th>At</th></tr>
        </thead>
        <tbody>
          {#each data.actions as a (a.action_id + a.started_at)}
            <tr>
              <td>
                <span class="phase-dot" style={`background:${PHASE_COLOR[a.kind as Phase] ?? 'var(--line-strong)'}`}></span>
                {a.kind.replace(/_/g, ' ')}
              </td>
              <td class="mono tcell">{a.target}</td>
              <td><span class="st {STATUS_TONE[a.status] ?? 'neutral'}">{a.status.replace(/_/g, ' ')}</span></td>
              <td class="detail">
                {a.detail}
                {#if a.evidence_url}<a href={a.evidence_url}>evidence</a>{/if}
              </td>
              <td class="mono tcell">{clock(a.finished_at)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</section>

<style>
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--s-4);
    margin-bottom: var(--s-3);
  }
  .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-5);
    color: var(--text-faint);
    font-size: var(--t-xs);
    margin-bottom: var(--s-6);
  }
  .verify {
    margin-bottom: var(--s-6);
  }
  .verify h2,
  .ledger h2 {
    margin-bottom: var(--s-3);
  }
  .checks {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--s-2);
  }
  .check {
    display: flex;
    align-items: center;
    gap: var(--s-3);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    padding: var(--s-3) var(--s-4);
  }
  .check-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--line-strong);
    flex-shrink: 0;
  }
  .check.passed .check-dot {
    background: var(--accent);
  }
  .check.failed .check-dot {
    background: var(--alarm);
  }
  .check.unverified .check-dot {
    background: var(--warn);
  }
  .check div {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
  }
  .check-id {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-sm);
  }
  .check-detail {
    font-size: var(--t-xs);
    color: var(--text-soft);
  }
  .check-out {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .sub {
    color: var(--text-soft);
    font-size: var(--t-sm);
    margin-bottom: var(--s-4);
  }
  .table {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--t-sm);
  }
  th,
  td {
    text-align: left;
    padding: var(--s-3) var(--s-4);
    border-bottom: 1px solid var(--line);
    vertical-align: top;
  }
  th {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-xs);
    color: var(--text-faint);
    position: sticky;
    top: 0;
    background: var(--card);
  }
  tr:last-child td {
    border-bottom: none;
  }
  .tcell {
    font-size: var(--t-xs);
    word-break: break-all;
  }
  .detail {
    color: var(--text-soft);
    max-width: 36ch;
  }
  .detail a {
    color: var(--accent);
    margin-left: var(--s-2);
  }
  .phase-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: var(--s-2);
  }
  .st {
    font-size: var(--t-xs);
    font-weight: 600;
    padding: 1px var(--s-2);
    border-radius: var(--r-chip);
  }
  .st.safe {
    background: var(--accent-soft);
    color: var(--accent);
  }
  .st.warn {
    background: var(--warn-soft);
    color: var(--warn);
  }
  .st.alarm {
    background: var(--alarm-soft);
    color: var(--alarm);
  }
  .st.neutral {
    background: var(--card-sunk);
    color: var(--text-soft);
  }

  @media (max-width: 1040px) {
    .tiles {
      grid-template-columns: repeat(2, 1fr);
    }
    .checks {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 520px) {
    .tiles {
      grid-template-columns: 1fr;
    }
  }
</style>
