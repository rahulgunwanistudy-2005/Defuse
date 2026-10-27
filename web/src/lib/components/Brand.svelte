<script lang="ts">
  let { compact = false }: { compact?: boolean } = $props();
</script>

<a class="brand" href="/" aria-label="Defuse home">
  <svg viewBox="0 0 36 36" fill="none" aria-hidden="true">
    <path d="M18 3 31 10v10c0 7-7 11-13 14C12 31 5 27 5 20V10L18 3Z" fill="currentColor" />
    <path d="m12 19 4 4 8-10" stroke="var(--card, white)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
  {#if !compact}<span>defuse</span>{/if}
</a>

<style>
  .brand { display: inline-flex; align-items: center; gap: 8px; color: var(--text); text-decoration: none; flex-shrink: 0; }
  svg { width: 30px; height: 32px; }
  span { font-size: 29px; font-weight: 600; letter-spacing: -1.6px; line-height: 1; }
</style>
