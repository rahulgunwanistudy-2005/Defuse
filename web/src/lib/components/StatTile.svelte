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
    position: relative;
    background: var(--lime);
    color: #1b220a;
    border: 1px solid transparent;
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
    min-width: 0;
  }
  .value {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: var(--t-2xl);
    line-height: 1;
    letter-spacing: -0.055em;
    font-variant-numeric: tabular-nums;
  }
  .label {
    margin-top: var(--s-3);
    color: #3e4b1e;
    font-size: var(--t-sm);
  }
  .foot {
    margin-top: var(--s-1);
    color: #4a572b;
    font-size: var(--t-xs);
  }
  .tile::before, .tile::after {
    content: '';
    position: absolute;
    width: 17px;
    height: 28px;
    top: calc(50% - 14px);
    background: var(--page);
    border-radius: 50%;
  }
  .tile::before { left: -10px; }
  .tile::after { right: -10px; }
  .tile.alarm { background: var(--card); border-color: var(--alarm-soft); }
  .alarm .label { color: var(--text-soft); }
  .alarm .foot { color: var(--text-faint); }
  .alarm .value {
    color: var(--alarm);
  }
  .safe .value {
    color: #354b08;
  }
</style>
