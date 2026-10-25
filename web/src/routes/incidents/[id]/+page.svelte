<script lang="ts">
  import { onMount } from 'svelte';
  import StatTile from '$lib/components/StatTile.svelte';
  import { streamEvents, fmtDuration, type IncidentEvent } from '$lib/api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  let events = $state<IncidentEvent[]>([...data.events]);
  let live = $state(false);

  onMount(() => {
    const seen = new Set(events.map((e) => e.seq));
    return streamEvents(
      data.id,
      (e) => {
        if (!seen.has(e.seq)) {
          seen.add(e.seq);
          events = [...events, e];
        }
      },
      (state) => (live = state)
    );
  });

  const g = $derived(data.graph);
  const exposedSecrets = $derived(g ? g.nodes.filter((n) => n.kind === 'secret').length : 0);
  const rogue = $derived(g ? g.nodes.filter((n) => n.kind === 'package_version' && n.rogue).length : 0);
  const jobs = $derived(g ? g.nodes.filter((n) => n.kind === 'job').length : 0);
  const generations = $derived(g?.generations.length ?? 0);
  const m = $derived(data.metrics);

  const KIND_LABEL: Record<string, string> = {
    'incident.opened': 'Incident opened',
    'graph.grow': 'Exposure found',
    degradation: 'Could not see',
    'plan.ready': 'Plan ready',
    'containment.started': 'Containment started',
    action: 'Action',
    verified: 'Verified'
  };

  function tone(kind: string, payload: Record<string, unknown>): string {
    if (kind === 'verified') return (payload.passed as boolean) ? 'safe' : 'alarm';
    if (kind === 'degradation') return 'warn';
    if (kind === 'action') {
      const s = (payload.status as string) ?? '';
      if (s === 'failed') return 'alarm';
      if (s === 'needs_operator') return 'warn';
      return 'safe';
    }
    return 'neutral';
  }

  function clock(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
</script>

<section class="live">
  <div class="tiles">
    <StatTile
      value={fmtDuration(m?.time_to_containment)}
      label="Time to containment"
      foot="detected → last action"
    />
    <StatTile value={String(exposedSecrets)} label="Secrets exposed" foot="rotated in a safe order" />
    <StatTile value={String(rogue)} label="Rogue versions" tone={rogue ? 'alarm' : 'default'} foot="republished without provenance" />
    <StatTile value={String(jobs)} label="CI jobs infected" foot={`${generations} generation${generations === 1 ? '' : 's'} deep`} />
  </div>

  <div class="columns">
    <div class="col">
      <div class="col-head">
        <h2>Timeline</h2>
        <span class="live-dot" class:on={live}>{live ? 'live' : 'replay'}</span>
      </div>
      <ol class="feed mist-scroll">
        {#each events as e (e.seq)}
          <li class="event {tone(e.kind, e.payload)}">
            <span class="dot" aria-hidden="true"></span>
            <div class="event-body">
              <div class="event-top">
                <span class="event-kind">{KIND_LABEL[e.kind] ?? e.kind}</span>
                <time class="event-time mono">{clock(e.at)}</time>
              </div>
              <p class="event-msg">{e.message || e.kind}</p>
            </div>
          </li>
        {/each}
        {#if events.length === 0}
          <li class="event neutral"><div class="event-body"><p class="event-msg">Waiting for the first event…</p></div></li>
        {/if}
      </ol>
    </div>

    <aside class="col">
      <h2>What is exposed</h2>
      {#if g}
        <dl class="exposure">
          {#each g.generations as gen (gen.depth)}
            <div class="gen">
              <dt>Generation {gen.depth}</dt>
              <dd>
                {gen.versions.join(', ')}
                <span class="gen-meta">{gen.jobs} job{gen.jobs === 1 ? '' : 's'} · {gen.projects} project{gen.projects === 1 ? '' : 's'}</span>
              </dd>
            </div>
          {/each}
        </dl>
        <a class="jump" href={`/incidents/${data.id}/map`}>Open the exposure map →</a>
      {:else}
        <p class="muted">The exposure graph is not built yet.</p>
      {/if}
    </aside>
  </div>
</section>

<style>
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--s-4);
    margin-bottom: var(--s-6);
  }
  .columns {
    display: grid;
    grid-template-columns: 1.6fr 1fr;
    gap: var(--s-5);
    align-items: start;
  }
  .col {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
  }
  .col-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--s-4);
  }
  .live-dot {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .live-dot::before {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--line-strong);
  }
  .live-dot.on {
    color: var(--accent);
  }
  .live-dot.on::before {
    background: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }
  .feed {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 60vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .event {
    display: flex;
    gap: var(--s-3);
    padding: var(--s-3) 0;
    border-bottom: 1px solid var(--line);
  }
  .event:last-child {
    border-bottom: none;
  }
  .dot {
    margin-top: 6px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--line-strong);
    flex-shrink: 0;
  }
  .event.safe .dot {
    background: var(--accent);
  }
  .event.alarm .dot {
    background: var(--alarm);
  }
  .event.warn .dot {
    background: var(--warn);
  }
  .event-top {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-3);
  }
  .event-kind {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-sm);
  }
  .event-time {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .event-msg {
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .exposure {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
  }
  .gen dt {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-sm);
  }
  .gen dd {
    margin: 0;
    color: var(--text-soft);
    font-size: var(--t-sm);
    font-family: var(--font-mono);
    font-size: var(--t-xs);
    word-break: break-all;
  }
  .gen-meta {
    display: block;
    margin-top: 2px;
    color: var(--text-faint);
    font-family: var(--font-text);
  }
  .jump {
    display: inline-block;
    margin-top: var(--s-4);
    color: var(--accent);
    text-decoration: none;
    font-size: var(--t-sm);
    font-weight: 600;
  }
  .muted {
    color: var(--text-faint);
  }

  @media (max-width: 1040px) {
    .tiles {
      grid-template-columns: repeat(2, 1fr);
    }
    .columns {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 520px) {
    .tiles {
      grid-template-columns: 1fr;
    }
  }
</style>
