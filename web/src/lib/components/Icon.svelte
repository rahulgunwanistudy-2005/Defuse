<script lang="ts">
  let { name, size = 20 }: { name: string; size?: number } = $props();
  const paths: Record<string, string> = {
    arrow: 'M5 12h14m-5-5 5 5-5 5',
    play: 'm9 5 11 7-11 7V5Z',
    check: 'm5 12 4 4L19 6',
    graph: 'M6 6h.01M18 6h.01M12 18h.01M7.5 8.5l3 7m6-7-3 7M8 6h8',
    layers: 'm12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5',
    shield: 'm12 3 8 4v6c0 4-4 7-8 9-4-2-8-5-8-9V7l8-4Zm-4 9 3 3 5-6',
    clock: 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    search: 'm21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
    activity: 'M2 12h5l3-8 4 16 3-8h5',
    record: 'M6 3h9l4 4v14H6V3Zm8 0v6h5M9 13h7M9 17h7',
    sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    moon: 'M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z',
    menu: 'M4 6h16M4 12h16M4 18h16',
    close: 'm6 6 12 12M6 18 18 6',
    code: 'm8 5-6 7 6 7m8-14 6 7-6 7m-3-16-2 18'
  };
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.shield} /></svg>
