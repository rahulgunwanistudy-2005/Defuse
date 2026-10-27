<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import {
    forceSimulation,
    forceLink,
    forceManyBody,
    forceCenter,
    forceCollide,
    type Simulation
  } from 'd3-force';
  import { NODE_GLYPH, NODE_LABEL } from '$lib/phases';
  import type { GraphEdge, GraphNode } from '$lib/api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  type Sim = GraphNode & { x: number; y: number; vx: number; vy: number; fx?: number | null; fy?: number | null };
  interface Link {
    source: Sim;
    target: Sim;
    kind: string;
    evidence: string;
  }

  const graph = untrack(() => data.graph);
  const KINDS = Array.from(new Set(graph.nodes.map((n) => n.kind)));
  let active = $state<Set<string>>(new Set(KINDS));
  let selected = $state<Sim | null>(null);
  let W = $state(900);
  let H = $state(560);

  let nodes: Sim[] = graph.nodes.map((n, i) => ({
    ...n,
    x: 450 + Math.cos(i) * 180,
    y: 280 + Math.sin(i) * 160,
    vx: 0,
    vy: 0
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let links: Link[] = graph.edges
    .map((e: GraphEdge) => ({
      source: byId.get(e.src)!,
      target: byId.get(e.dst)!,
      kind: e.kind,
      evidence: e.evidence
    }))
    .filter((l) => l.source && l.target);

  let tick = $state(0);
  let sim: Simulation<Sim, undefined> | null = null;

  const visibleNodes = $derived(nodes.filter((n) => active.has(n.kind)));
  const visibleLinks = $derived(
    links.filter((l) => active.has(l.source.kind) && active.has(l.target.kind))
  );

  function toggle(kind: string) {
    const next = new Set(active);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    active = next;
  }

  const CONSTRAINT_EDGES = new Set([
    'CAN_READ',
    'CAN_PUBLISH',
    'CAN_PUSH',
    'PUBLISHED',
    'PLANTED',
    'WATCHES'
  ]);

  function edgeTone(kind: string): string {
    if (kind === 'PUBLISHED') return 'var(--alarm)';
    if (kind === 'WATCHES' || kind === 'PLANTED') return 'var(--constraint)';
    if (CONSTRAINT_EDGES.has(kind)) return 'var(--warn)';
    return 'var(--line-strong)';
  }

  function genColor(n: GraphNode): string {
    if (n.kind !== 'package_version') return 'var(--card)';
    return n.rogue ? 'var(--alarm-soft)' : 'var(--accent-soft)';
  }

  onMount(() => {
    const box = document.getElementById('map-svg')!.getBoundingClientRect();
    W = box.width;
    H = Math.max(480, box.height);
    sim = forceSimulation<Sim>(nodes)
      .force(
        'link',
        forceLink<Sim, Link>(links)
          .id((d) => d.id)
          .distance((l) => (l.kind === 'PART_OF' ? 60 : 110))
          .strength(0.4)
      )
      .force('charge', forceManyBody().strength(-360))
      .force('center', forceCenter(W / 2, H / 2))
      .force('collide', forceCollide(42))
      .on('tick', () => (tick += 1));
    return () => sim?.stop();
  });

  let dragging: Sim | null = null;
  function down(n: Sim, ev: PointerEvent) {
    dragging = n;
    n.fx = n.x;
    n.fy = n.y;
    sim?.alphaTarget(0.3).restart();
    (ev.target as Element).setPointerCapture(ev.pointerId);
  }
  function move(ev: PointerEvent) {
    if (!dragging) return;
    const box = (ev.currentTarget as SVGElement).getBoundingClientRect();
    dragging.fx = ev.clientX - box.left;
    dragging.fy = ev.clientY - box.top;
  }
  function up() {
    if (dragging) {
      dragging.fx = null;
      dragging.fy = null;
    }
    dragging = null;
    sim?.alphaTarget(0);
  }
</script>

<section class="map-wrap">
  <div class="legend">
    <div class="filters">
      {#each KINDS as kind (kind)}
        <button class="chip" class:off={!active.has(kind)} onclick={() => toggle(kind)}>
          <span class="glyph" aria-hidden="true">{NODE_GLYPH[kind] ?? '•'}</span>
          {NODE_LABEL[kind] ?? kind}
        </button>
      {/each}
    </div>
    <div class="edge-key">
      <span><i style="background:var(--alarm)"></i>published (provenance mismatch)</span>
      <span><i style="background:var(--constraint)"></i>watches / planted</span>
      <span><i style="background:var(--warn)"></i>can read / publish</span>
      <span><i style="background:var(--line-strong)"></i>structure</span>
    </div>
  </div>

  <div class="stage">
    <svg
      id="map-svg"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Exposure graph"
      onpointermove={move}
      onpointerup={up}
      onpointerleave={up}
    >
      {#key tick}
        <g class="edges">
          {#each visibleLinks as l, i (i)}
            <line
              x1={l.source.x}
              y1={l.source.y}
              x2={l.target.x}
              y2={l.target.y}
              stroke={edgeTone(l.kind)}
              stroke-width={CONSTRAINT_EDGES.has(l.kind) ? 1.8 : 1}
              stroke-dasharray={l.kind === 'WATCHES' ? '4 3' : undefined}
              opacity="0.65"
            />
          {/each}
        </g>
        <g class="nodes">
          {#each visibleNodes as n (n.id)}
            <g
              class="node"
              class:sel={selected?.id === n.id}
              transform={`translate(${n.x},${n.y})`}
              onpointerdown={(e) => down(n, e)}
              onclick={() => (selected = n)}
              role="button"
              tabindex="0"
              onkeydown={(e) => e.key === 'Enter' && (selected = n)}
            >
              <circle r="20" fill={genColor(n)} stroke="var(--line-strong)" stroke-width="1.5" />
              <text class="glyph-node" text-anchor="middle" dy="5">{NODE_GLYPH[n.kind] ?? '•'}</text>
              <text class="node-label" text-anchor="middle" dy="34">{n.label.slice(0, 22)}</text>
            </g>
          {/each}
        </g>
      {/key}
    </svg>

    {#if selected}
      <aside class="inspect">
        <button class="close" onclick={() => (selected = null)} aria-label="Close">×</button>
        <span class="kind">{NODE_LABEL[selected.kind] ?? selected.kind}</span>
        <h3 class="mono">{selected.label}</h3>
        {#if selected.kind === 'package_version'}
          <p>Generation {selected.generation}{selected.rogue ? ' · rogue (no matching commit)' : ''}</p>
        {/if}
        <dl class="props">
          {#each Object.entries(selected) as [k, v] (k)}
            {#if !['x', 'y', 'vx', 'vy', 'fx', 'fy', 'id', 'label', 'kind', 'index'].includes(k) && v != null && typeof v !== 'object'}
              <dt>{k}</dt>
              <dd class="mono">{String(v)}</dd>
            {/if}
          {/each}
        </dl>
      </aside>
    {/if}
  </div>
</section>

<style>
  .legend {
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
    margin-bottom: var(--s-4);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    padding: var(--s-1) var(--s-3);
    border-radius: var(--r-chip);
    border: 1px solid var(--line-strong);
    background: var(--card);
    color: var(--text-soft);
    font-size: var(--t-xs);
  }
  .chip.off {
    opacity: 0.4;
    text-decoration: line-through;
  }
  .chip .glyph {
    font-size: var(--t-sm);
  }
  .edge-key {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-4);
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .edge-key span {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
  }
  .edge-key i {
    width: 14px;
    height: 3px;
    border-radius: 2px;
    display: inline-block;
  }
  .stage {
    position: relative;
    background: var(--canvas);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    overflow: hidden;
  }
  svg {
    display: block;
    width: 100%;
    height: 62vh;
    min-height: 480px;
    touch-action: none;
  }
  .node {
    cursor: grab;
  }
  .node:active {
    cursor: grabbing;
  }
  .node.sel circle {
    stroke: var(--accent);
    stroke-width: 2.5;
  }
  .glyph-node {
    font-size: 16px;
    fill: var(--text);
  }
  .node-label {
    font-family: var(--font-mono);
    font-size: 9px;
    fill: var(--text-faint);
  }
  .inspect {
    position: absolute;
    top: var(--s-4);
    right: var(--s-4);
    width: min(320px, 70%);
    background: var(--card);
    border: 1px solid var(--line-strong);
    border-radius: var(--r-tile);
    box-shadow: var(--shadow-lift);
    padding: var(--s-4);
  }
  .close {
    position: absolute;
    top: var(--s-2);
    right: var(--s-3);
    border: none;
    background: none;
    color: var(--text-faint);
    font-size: var(--t-md);
  }
  .kind {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .inspect h3 {
    font-size: var(--t-sm);
    word-break: break-all;
    margin: var(--s-1) 0 var(--s-3);
  }
  .inspect p {
    color: var(--text-soft);
    font-size: var(--t-sm);
    margin-bottom: var(--s-3);
  }
  .props {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px var(--s-3);
    font-size: var(--t-xs);
  }
  .props dt {
    color: var(--text-faint);
  }
  .props dd {
    margin: 0;
    word-break: break-all;
  }
</style>
