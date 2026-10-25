<script lang="ts">
  let { status }: { status: string } = $props();
  const tone: Record<string, string> = {
    verified: 'safe',
    contained: 'safe',
    containing: 'work',
    scoped: 'work',
    open: 'work',
    failed: 'alarm'
  };
</script>

<span class="badge {tone[status] ?? 'work'}">{status}</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 2px var(--s-3);
    border-radius: var(--r-chip);
    font-size: var(--t-xs);
    font-weight: 600;
    letter-spacing: 0.01em;
    border: 1px solid transparent;
  }
  .safe {
    background: var(--accent-soft);
    color: var(--accent);
  }
  .work {
    background: var(--card-sunk);
    color: var(--text-soft);
    border-color: var(--line);
  }
  .alarm {
    background: var(--alarm-soft);
    color: var(--alarm);
  }
</style>
