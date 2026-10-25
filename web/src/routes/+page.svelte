<script lang="ts">
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  const numbers = [
    {
      figure: '23%',
      body: 'of Shai-Hulud 2.0 infections were on developer machines. The rest ran in CI runners and containers — where Defuse looks.',
      cite: 'Wiz, Dec 2025'
    },
    {
      figure: '2–7 min',
      body: 'between organizations for the Aug 2026 keyv worm, republishing with valid provenance through the victim’s own release workflow.',
      cite: 'The Hacker News / Microsoft, Aug 2026'
    },
    {
      figure: 'one order',
      body: 'is safe. Revoking a stolen token can fire the attacker’s handler; cutting publish and source access together wipes the host. Defuse finds the order that does neither.',
      cite: 'SANS ISC, Aug 2026 · GitLab VR, Nov 2025'
    }
  ];
</script>

<svelte:head><title>Defuse — worm containment for GitLab CI</title></svelte:head>

<header class="hero">
  <div class="horizon" aria-hidden="true"></div>
  <div class="hero-body">
    <p class="kicker">Worm containment for GitLab CI</p>
    <h1>
      When a supply-chain worm hits your pipelines, the dangerous move is to panic and revoke
      everything at once.
    </h1>
    <p class="lede">
      Defuse maps every CI job the worm ran in, every secret it could read, every package it
      could republish and every agent hook it planted — then contains it in the one order that
      does not detonate it.
    </p>
  </div>
</header>

<section class="numbers" aria-label="Why this matters">
  {#each numbers as n (n.cite)}
    <article class="number">
      <div class="figure">{n.figure}</div>
      <p>{n.body}</p>
      <div class="cite">{n.cite}</div>
    </article>
  {/each}
</section>

<section class="incidents" aria-label="Incidents">
  <div class="sec-head">
    <h2>Incidents</h2>
    <p>Each one carries its exposure graph, its safe-order plan, the naive-versus-Defuse replay,
      and the measured timings.</p>
  </div>

  {#if data.incidents.length === 0}
    <div class="empty">
      <p>No incidents yet. Start the engine with a seeded scenario, or merge an advisory work
        item to open one.</p>
      <code>uv run defuse demo</code>
    </div>
  {:else}
    <ul class="list">
      {#each data.incidents as incident (incident.id)}
        <li>
          <a class="row" href={`/incidents/${incident.id}/`}>
            <div class="row-main">
              <span class="row-title">{incident.title}</span>
              <span class="row-meta mono">{incident.namespace} · {incident.ioc_id}</span>
            </div>
            <div class="row-side">
              {#if incident.origin === 'scenario'}<span class="tag">scenario</span>{/if}
              <StatusBadge status={incident.status} />
            </div>
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .hero {
    position: relative;
    padding: var(--s-8) var(--s-7) var(--s-6);
    overflow: hidden;
  }
  .horizon {
    position: absolute;
    inset: 0 0 auto 0;
    height: 320px;
    background: var(--horizon);
    pointer-events: none;
  }
  .hero-body {
    position: relative;
    max-width: 58ch;
  }
  .kicker {
    color: var(--constraint);
    font-weight: 600;
    font-size: var(--t-sm);
    margin-bottom: var(--s-3);
  }
  .hero h1 {
    font-size: var(--t-3xl);
    max-width: 20ch;
  }
  .lede {
    margin-top: var(--s-4);
    font-size: var(--t-md);
    color: var(--text-soft);
  }
  .numbers {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--s-4);
    padding: 0 var(--s-7) var(--s-6);
  }
  .number {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
  }
  .figure {
    font-family: var(--font-display);
    font-weight: 700;
    font-size: var(--t-xl);
    letter-spacing: -0.02em;
    background: var(--dawn);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    width: fit-content;
  }
  .number p {
    margin-top: var(--s-2);
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .cite {
    margin-top: var(--s-3);
    color: var(--text-faint);
    font-size: var(--t-xs);
  }
  .incidents {
    padding: 0 var(--s-7) var(--s-8);
  }
  .sec-head {
    margin-bottom: var(--s-4);
  }
  .sec-head p {
    margin-top: var(--s-2);
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-4);
    padding: var(--s-4) var(--s-5);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    text-decoration: none;
    color: inherit;
    transition: border-color 0.14s ease, box-shadow 0.14s ease, transform 0.14s ease;
  }
  .row:hover {
    border-color: var(--line-strong);
    box-shadow: var(--shadow-lift);
    transform: translateY(-1px);
  }
  .row-main {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .row-title {
    font-family: var(--font-display);
    font-weight: 600;
  }
  .row-meta {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .row-side {
    display: flex;
    align-items: center;
    gap: var(--s-3);
    flex-shrink: 0;
  }
  .tag {
    font-size: var(--t-xs);
    color: var(--text-faint);
    border: 1px dashed var(--line-strong);
    border-radius: var(--r-chip);
    padding: 1px var(--s-2);
  }
  .empty {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-6);
    color: var(--text-soft);
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
    align-items: flex-start;
  }
  .empty code {
    background: var(--card-sunk);
    padding: var(--s-2) var(--s-3);
    border-radius: var(--r-sm);
  }

  @media (max-width: 900px) {
    .numbers {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: 760px) {
    .hero {
      padding: var(--s-6) var(--s-4) var(--s-5);
    }
    .hero h1 {
      font-size: var(--t-2xl);
    }
    .numbers,
    .incidents {
      padding-left: var(--s-4);
      padding-right: var(--s-4);
    }
  }
</style>
