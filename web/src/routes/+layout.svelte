<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import Brand from '$lib/components/Brand.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';

  let { children } = $props();
  const views = [
    { href: '', label: 'Live', icon: 'activity' },
    { href: 'map', label: 'Map', icon: 'graph' },
    { href: 'plan', label: 'Plan', icon: 'layers' },
    { href: 'replay', label: 'Replay', icon: 'play' },
    { href: 'record', label: 'Record', icon: 'record' }
  ];
  const incidentId = $derived($page.params.id);
  const current = $derived($page.url.pathname.replace(/\/$/, '').split('/').pop() ?? '');
  const activeView = $derived(current === incidentId ? '' : current);
</script>

<a class="skip-link" href="#main">Skip to content</a>
{#if incidentId}
  <div class="console-shell">
    <header class="console-header">
      <Brand />
      <a class="workspace-back" href="/#incidents">Workspace <Icon name="arrow" size={15} /></a>
      <div class="header-end"><span class="engine-label"><span></span>Containment console</span><ThemeToggle /></div>
    </header>
    <nav class="view-nav" aria-label="Incident views">
      {#each views as v (v.href)}
        <a class:active={activeView === v.href} href={`/incidents/${incidentId}/${v.href}`} aria-current={activeView === v.href ? 'page' : undefined}>
          <Icon name={v.icon} size={17} /><span>{v.label}</span>
        </a>
      {/each}
    </nav>
    <main id="main" class="console-canvas mist-scroll">{@render children()}</main>
    <footer class="console-footer"><span>Every action. In the right order.</span><a href="/">defuse</a></footer>
  </div>
{:else}
  <main id="main">{@render children()}</main>
{/if}

<style>
  .console-shell { min-height: 100vh; }
  .console-header { display: flex; align-items: center; gap: 28px; padding: 22px 4%; background: var(--card); border-bottom: 1px solid var(--line); }
  .workspace-back { display: flex; align-items: center; gap: 8px; color: var(--text-soft); font-size: 13px; text-decoration: none; border-left: 1px solid var(--line); padding-left: 28px; }
  .workspace-back :global(svg) { transform: rotate(180deg); }
  .header-end { margin-left: auto; display: flex; align-items: center; gap: 24px; }
  .engine-label { display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--text-soft); }
  .engine-label > span { width: 6px; height: 6px; background: var(--accent); border-radius: 50%; }
  .view-nav { display: flex; justify-content: center; gap: 5px; width: fit-content; max-width: calc(100% - 32px); margin: 26px auto 0; background: var(--card); border: 1px solid var(--line); border-radius: 100px; padding: 6px; box-shadow: var(--shadow); }
  .view-nav a { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 23px; border-radius: 100px; color: var(--text-soft); font-size: 14px; text-decoration: none; transition: background .2s, color .2s; }
  .view-nav a:hover { background: var(--card-sunk); color: var(--text); }
  .view-nav a.active { background: var(--accent); color: var(--card); }
  .console-canvas { max-width: 1600px; margin: auto; min-width: 0; }
  .console-footer { display: flex; justify-content: space-between; max-width: 1504px; margin: auto; padding: 24px 48px; border-top: 1px solid var(--line); font-size: 12px; color: var(--text-faint); }
  .console-footer a { font-weight: 600; text-decoration: none; }
  @media (max-width: 700px) {
    .console-header { padding: 18px 20px; gap: 16px; }
    .workspace-back { padding-left: 16px; font-size: 12px; }
    .engine-label { display: none; }
    .view-nav { gap: 0; margin-top: 20px; width: calc(100% - 32px); }
    .view-nav a { flex: 1; font-size: 12px; gap: 5px; padding: 10px 6px; }
    .view-nav :global(svg) { width: 14px; }
    .console-footer { padding: 24px 20px; }
  }
</style>
