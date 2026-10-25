<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';

  let { children } = $props();

  const views = [
    { href: '', label: 'Live', hint: 'Incident timeline' },
    { href: 'map', label: 'Map', hint: 'Exposure graph' },
    { href: 'plan', label: 'Plan', hint: 'Safe-order DAG' },
    { href: 'replay', label: 'Replay', hint: 'Naive vs Defuse' },
    { href: 'record', label: 'Record', hint: 'Metrics & evidence' }
  ];

  const incidentId = $derived($page.params.id);
  const current = $derived(($page.url.pathname.split('/').pop() ?? '') || '');
  const activeView = $derived(
    incidentId && views.some((v) => v.href === current) ? current : 'home'
  );
</script>

<div class="shell">
  <aside class="rail">
    <a class="brand" href="/">
      <span class="mark" aria-hidden="true"></span>
      <span class="word">defuse</span>
    </a>
    {#if incidentId}
      <nav aria-label="Incident views">
        {#each views as v (v.href)}
          <a
            class="navlink"
            class:active={activeView === v.href}
            href={`/incidents/${incidentId}/${v.href}`}
            aria-current={activeView === v.href ? 'page' : undefined}
          >
            <span class="navlabel">{v.label}</span>
            <span class="navhint">{v.hint}</span>
          </a>
        {/each}
      </nav>
    {:else}
      <p class="raillead">
        Worm containment for GitLab CI. Pick an incident to see what it exposed and why the
        order is safe.
      </p>
    {/if}
    <div class="railfoot">
      <ThemeToggle />
      <a class="repo" href="https://github.com/rahulgunwanistudy-2005/Defuse">source</a>
    </div>
  </aside>
  <main class="canvas mist-scroll">
    {@render children()}
  </main>
</div>

<style>
  .shell {
    display: grid;
    grid-template-columns: var(--rail) 1fr;
    min-height: 100vh;
  }
  .rail {
    position: sticky;
    top: 0;
    align-self: start;
    height: 100vh;
    display: flex;
    flex-direction: column;
    gap: var(--s-5);
    padding: var(--s-5) var(--s-4);
    background: var(--card);
    border-right: 1px solid var(--line);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--s-3);
    text-decoration: none;
    font-family: var(--font-display);
    font-weight: 700;
    font-size: var(--t-md);
    letter-spacing: -0.02em;
  }
  .mark {
    width: 20px;
    height: 20px;
    border-radius: 6px;
    background: var(--dawn);
    box-shadow: 0 0 0 3px var(--constraint-soft);
  }
  .raillead {
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  nav {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
  }
  .navlink {
    display: flex;
    flex-direction: column;
    padding: var(--s-2) var(--s-3);
    border-radius: var(--r-sm);
    text-decoration: none;
    color: var(--text-soft);
    border-left: 2px solid transparent;
    transition: background 0.14s ease, color 0.14s ease;
  }
  .navlink:hover {
    background: var(--card-sunk);
    color: var(--text);
  }
  .navlink.active {
    background: var(--accent-soft);
    color: var(--text);
    border-left-color: var(--accent);
  }
  .navlabel {
    font-family: var(--font-display);
    font-weight: 600;
  }
  .navhint {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .navlink.active .navhint {
    color: var(--text-soft);
  }
  .railfoot {
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-3);
    font-size: var(--t-sm);
  }
  .repo {
    color: var(--text-soft);
    text-decoration: none;
    border-bottom: 1px solid var(--line-strong);
  }
  .repo:hover {
    color: var(--text);
  }
  .canvas {
    min-width: 0;
    background: var(--page);
  }

  @media (max-width: 760px) {
    .shell {
      grid-template-columns: 1fr;
    }
    .rail {
      position: static;
      height: auto;
      flex-direction: row;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--s-3);
    }
    .brand {
      margin-right: auto;
    }
    .raillead {
      display: none;
    }
    nav {
      flex-direction: row;
      flex-wrap: wrap;
      order: 3;
      width: 100%;
    }
    .navlink {
      flex: 1 1 auto;
    }
    .navhint {
      display: none;
    }
    .railfoot {
      margin-top: 0;
    }
  }
</style>
