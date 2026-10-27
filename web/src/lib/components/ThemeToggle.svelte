<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  let theme = $state<'light' | 'dark'>('light');
  onMount(() => {
    try {
      const saved = localStorage.getItem('defuse-theme');
      if (saved === 'light' || saved === 'dark') theme = saved;
      document.documentElement.dataset.theme = theme;
    } catch { /* Use the reference's daylight palette when storage is blocked. */ }
  });
  function toggle() {
    theme = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('defuse-theme', theme); } catch { /* best effort */ }
  }
</script>
<button class="toggle" onclick={toggle} aria-label="Switch light or dark theme" aria-pressed={theme === 'dark'} title={theme === 'dark' ? 'Use light theme' : 'Use dark theme'}><Icon name={theme === 'dark' ? 'moon' : 'sun'} size={17} /></button>
<style>
  .toggle { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; padding: 0; border: 1px solid var(--line); border-radius: 50%; background: var(--card); color: var(--text-soft); }
  .toggle:hover { color: var(--accent); border-color: var(--accent); }
</style>
