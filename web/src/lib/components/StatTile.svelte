<script lang="ts">
  let {
    value,
    label,
    foot = '',
    tone = 'default'
  }: {
    value: string;
    label: string;
    foot?: string;
    tone?: 'default' | 'alarm' | 'safe';
  } = $props();
</script>

<div class="tile" class:alarm={tone === 'alarm'} class:safe={tone === 'safe'}>
  <div class="value">{value}</div>
  <div class="label">{label}</div>
  {#if foot}<div class="foot">{foot}</div>{/if}
</div>

<style>
  .tile {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
    min-width: 0;
  }
  .value {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-2xl);
    line-height: 1;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .label {
    margin-top: var(--s-3);
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .foot {
    margin-top: var(--s-1);
    color: var(--text-faint);
    font-size: var(--t-xs);
  }
  .alarm .value {
    color: var(--alarm);
  }
  .safe .value {
    color: var(--accent);
  }
</style>
