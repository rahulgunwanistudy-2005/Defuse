<script lang="ts">
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import type { Snippet } from 'svelte';
  import type { LayoutData } from './$types';

  let { data, children }: { data: LayoutData; children: Snippet } = $props();
  const inc = $derived(data.incident);
</script>

<svelte:head><title>{inc.title} — Defuse</title></svelte:head>

<header class="inc-head">
  <div class="horizon" aria-hidden="true"></div>
  <div class="inc-head-row">
    <div class="inc-id">
      <a class="back" href="/">incidents</a>
      <span class="sep">/</span>
      <span class="mono">{inc.id}</span>
    </div>
    <StatusBadge status={inc.status} />
  </div>
  <h1>{inc.title}</h1>
  <p class="inc-sub">
    {inc.namespace}
    {#if inc.work_item_url}· <a href={inc.work_item_url}>work item</a>{/if}
  </p>
</header>

<div class="view">
  {@render children()}
</div>

<style>
  .inc-head {
    position: relative;
    padding: var(--s-6) var(--s-7) var(--s-4);
    overflow: hidden;
  }
  .horizon {
    position: absolute;
    inset: 0 0 auto 0;
    height: 200px;
    background: var(--horizon);
    pointer-events: none;
  }
  .inc-head-row {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-4);
    margin-bottom: var(--s-3);
  }
  .inc-id {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    font-size: var(--t-sm);
    color: var(--text-faint);
  }
  .back {
    color: var(--text-soft);
    text-decoration: none;
    border-bottom: 1px solid var(--line-strong);
  }
  .back:hover {
    color: var(--text);
  }
  .inc-head h1 {
    position: relative;
    font-size: var(--t-2xl);
    max-width: 28ch;
  }
  .inc-sub {
    position: relative;
    margin-top: var(--s-2);
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .view {
    padding: 0 var(--s-7) var(--s-8);
  }
  @media (max-width: 760px) {
    .inc-head {
      padding: var(--s-5) var(--s-4) var(--s-3);
    }
    .view {
      padding: 0 var(--s-4) var(--s-6);
    }
    .inc-head h1 {
      font-size: var(--t-xl);
    }
  }
</style>
