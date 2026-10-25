<script lang="ts">
  import { onMount } from 'svelte';

  let theme = $state<'light' | 'dark' | null>(null);

  onMount(() => {
    try {
      const saved = localStorage.getItem('defuse-theme');
      if (saved === 'light' || saved === 'dark') {
        theme = saved;
        document.documentElement.dataset.theme = saved;
      }
    } catch {
      /* storage blocked; fall back to system theme */
    }
  });

  function toggle() {
    const next =
      theme === 'dark'
        ? 'light'
        : theme === 'light'
          ? 'dark'
          : window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'light'
            : 'dark';
    theme = next;
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem('defuse-theme', next);
    } catch {
      /* best effort */
    }
  }
</script>

<button class="toggle" onclick={toggle} aria-label="Switch light or dark theme">
  <span class="dot" aria-hidden="true"></span>
  {theme ?? 'auto'}
</button>

<style>
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    padding: var(--s-1) var(--s-3);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-chip);
    background: transparent;
    color: var(--text-soft);
    font-size: var(--t-xs);
  }
  .toggle:hover {
    color: var(--text);
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--dawn);
  }
</style>
