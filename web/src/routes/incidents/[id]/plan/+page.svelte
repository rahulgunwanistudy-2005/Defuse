<script lang="ts">
  import { onMount } from 'svelte';
  import { PHASE_COLOR } from '$lib/phases';
  import { api, type Action, type Explanation, type OrderingEdge } from '$lib/api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const plan = data.plan;
  const actionById = new Map(plan.actions.map((a) => [a.id, a]));
  const layerOf = new Map<string, number>();
  plan.layers.forEach((layer, i) => layer.forEach((id) => layerOf.set(id, i)));

  interface Positioned {
    id: string;
    x: number;
    y: number;
    w: number;
    h: number;
    action: Action;
  }
  interface Routed {
    edge: OrderingEdge;
    points: { x: number; y: number }[];
  }

  let laidOut = $state<Positioned[]>([]);
  let routed = $state<Routed[]>([]);
  let width = $state(1000);
  let height = $state(600);
  let selected = $state<string | null>(null);
  let explanation = $state<Explanation | null>(null);
  let loadingExplain = $state(false);

  const NODE_W = 184;
  const NODE_H = 58;

  async function select(id: string) {
    selected = id;
    explanation = null;
    loadingExplain = true;
    try {
      explanation = await api.explain(fetch, data.id, id);
    } catch {
      explanation = null;
    } finally {
      loadingExplain = false;
    }
  }

  const criticalSet = $derived(new Set(explanation?.critical_path ?? []));

  function edgeTone(edge: OrderingEdge): string {
    return edge.reason === 'constraint'
      ? 'var(--constraint)'
      : edge.reason === 'operator'
        ? 'var(--warn)'
        : 'var(--line-strong)';
  }

  function isHighlighted(edge: OrderingEdge): boolean {
    return (
      selected != null &&
      criticalSet.has(edge.before) &&
      criticalSet.has(edge.after) &&
      Math.abs((layerOf.get(edge.before) ?? 0) - (layerOf.get(edge.after) ?? 0)) >= 0
    );
  }

  onMount(async () => {
    // Load ELK after first paint and lay out in a worker so the main thread stays responsive.
    const { default: ELK } = await import('elkjs/lib/elk.bundled.js');
    const elk = new ELK({
      workerFactory: () =>
        new Worker(new URL('elkjs/lib/elk-worker.min.js', import.meta.url), { type: 'module' })
    });
    const graph = {
      id: 'root',
      layoutOptions: {
        'elk.algorithm': 'layered',
        'elk.direction': 'RIGHT',
        'elk.layered.spacing.nodeNodeBetweenLayers': '96',
        'elk.spacing.nodeNode': '26',
        'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
        'elk.edgeRouting': 'ORTHOGONAL'
      },
      children: plan.actions.map((a) => ({ id: a.id, width: NODE_W, height: NODE_H })),
      edges: plan.edges.map((e, i) => ({ id: `e${i}`, sources: [e.before], targets: [e.after] }))
    };
    const res = await elk.layout(graph);
    width = (res.width ?? 1000) + 40;
    height = (res.height ?? 600) + 40;
    laidOut = (res.children ?? []).map((c: any) => ({
      id: c.id,
      x: c.x + 20,
      y: c.y + 20,
      w: c.width,
      h: c.height,
      action: actionById.get(c.id)!
    }));
    routed = (res.edges ?? []).map((e: any, i: number) => {
      const section = e.sections?.[0];
      const pts = section
        ? [section.startPoint, ...(section.bendPoints ?? []), section.endPoint].map((p: any) => ({
            x: p.x + 20,
            y: p.y + 20
          }))
        : [];
      return { edge: plan.edges[i], points: pts };
    });
  });

  function path(points: { x: number; y: number }[]): string {
    if (points.length === 0) return '';
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  }
</script>

<section>
  <div class="plan-head">
    <div>
      <h2>Why the order is safe</h2>
      <p class="sub">
        {plan.actions.length} actions in {plan.layers.length} layers. Thin grey edges are
        dependencies; coloured edges are safety constraints — hover or select an action to see
        which rule placed it.
      </p>
    </div>
    <div class="edge-key">
      <span><i style="background:var(--constraint)"></i>safety constraint (C1–C6)</span>
      <span><i style="background:var(--warn)"></i>operator pin</span>
      <span><i style="background:var(--line-strong)"></i>dependency</span>
    </div>
  </div>

  <div class="plan-grid">
    <div class="canvas-wrap mist-scroll">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Containment plan graph">
        <defs>
          <marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill="var(--line-strong)" />
          </marker>
          <marker id="arrow-c" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill="var(--constraint)" />
          </marker>
        </defs>
        <g class="edges">
          {#each routed as r, i (i)}
            <path
              d={path(r.points)}
              fill="none"
              stroke={edgeTone(r.edge)}
              stroke-width={r.edge.reason === 'constraint' ? 2 : 1.2}
              stroke-dasharray={r.edge.reason === 'dependency' ? '5 4' : undefined}
              marker-end={r.edge.reason === 'constraint' ? 'url(#arrow-c)' : 'url(#arrow)'}
              opacity={selected ? (isHighlighted(r.edge) ? 1 : 0.18) : 0.75}
            />
            {#if r.edge.constraint_id && r.points.length}
              <g transform={`translate(${r.points[Math.floor(r.points.length / 2)].x},${r.points[Math.floor(r.points.length / 2)].y})`}>
                <rect x="-16" y="-10" width="32" height="18" rx="9" fill="var(--constraint-soft)" stroke="var(--constraint)" stroke-width="1" />
                <text class="cedge" text-anchor="middle" dy="4">🔒{r.edge.constraint_id}</text>
              </g>
            {/if}
          {/each}
        </g>
        <g class="nodes">
          {#each laidOut as n (n.id)}
            <g
              transform={`translate(${n.x},${n.y})`}
              class="pnode"
              class:sel={selected === n.id}
              class:dim={selected != null && selected !== n.id && !criticalSet.has(n.id)}
              onclick={() => select(n.id)}
              role="button"
              tabindex="0"
              onkeydown={(e) => e.key === 'Enter' && select(n.id)}
            >
              <rect width={n.w} height={n.h} rx="12" fill="var(--card)" stroke="var(--line-strong)" />
              <rect width="5" height={n.h} rx="2.5" fill={PHASE_COLOR[n.action.phase]} />
              <text class="pphase" x="16" y="20">{n.action.phase}</text>
              <text class="plabel" x="16" y="40">{n.action.label.slice(0, 26)}</text>
            </g>
          {/each}
        </g>
      </svg>
    </div>

    <aside class="explain">
      {#if !selected}
        <div class="explain-empty">
          <h3>Select an action</h3>
          <p>Every action's place is explained by the constraints and dependencies that shaped
            it, and by the critical path that stops it running sooner.</p>
        </div>
      {:else if loadingExplain}
        <p class="muted">Explaining…</p>
      {:else if explanation}
        <span class="phase-tag" style={`color:${PHASE_COLOR[explanation.phase]}`}>{explanation.phase} · layer {explanation.layer}</span>
        <h3>{explanation.label}</h3>
        <p class="summary">{explanation.summary}</p>

        {#if explanation.constraints.length}
          <h4>Safety constraints</h4>
          <ul class="constraints">
            {#each explanation.constraints as c (c.id)}
              <li>
                <div class="c-top"><span class="c-id">🔒 {c.id}</span><span class="c-title">{c.title}</span></div>
                <p>{c.rationale}</p>
                <a class="c-src" href={c.source_url}>{c.source}</a>
              </li>
            {/each}
          </ul>
        {/if}

        {#if explanation.shaped_by.length}
          <h4>Placed after</h4>
          <ul class="shaped">
            {#each explanation.shaped_by as s (s.before + s.note)}
              <li>
                <code>{actionById.get(s.before)?.label ?? s.before}</code>
                <span class="shaped-note">{s.note}</span>
              </li>
            {/each}
          </ul>
        {/if}

        <h4>Critical path</h4>
        <ol class="path">
          {#each explanation.critical_path as step (step)}
            <li>{actionById.get(step)?.label ?? step}</li>
          {/each}
        </ol>
      {/if}
    </aside>
  </div>
</section>

<style>
  .plan-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--s-5);
    margin-bottom: var(--s-4);
    flex-wrap: wrap;
  }
  .sub {
    margin-top: var(--s-2);
    color: var(--text-soft);
    font-size: var(--t-sm);
    max-width: 60ch;
  }
  .edge-key {
    display: flex;
    flex-direction: column;
    gap: var(--s-1);
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .edge-key span {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
  }
  .edge-key i {
    width: 16px;
    height: 3px;
    border-radius: 2px;
  }
  .plan-grid {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: var(--s-5);
    align-items: start;
  }
  .canvas-wrap {
    background: var(--canvas);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    overflow: auto;
    max-height: 72vh;
  }
  svg {
    display: block;
    min-width: 100%;
  }
  .pnode {
    cursor: pointer;
  }
  .pnode.sel rect:first-of-type {
    stroke: var(--accent);
    stroke-width: 2.5;
  }
  .pnode.dim {
    opacity: 0.32;
  }
  .pphase {
    font-family: var(--font-text);
    font-size: 10px;
    fill: var(--text-faint);
  }
  .plabel {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 12px;
    fill: var(--text);
  }
  .cedge {
    font-size: 9px;
    fill: var(--constraint);
    font-family: var(--font-mono);
  }
  .explain {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
    position: sticky;
    top: var(--s-4);
    max-height: 72vh;
    overflow-y: auto;
  }
  .explain-empty h3 {
    margin-bottom: var(--s-2);
  }
  .explain-empty p,
  .muted {
    color: var(--text-soft);
    font-size: var(--t-sm);
  }
  .phase-tag {
    font-size: var(--t-xs);
    font-weight: 600;
  }
  .explain h3 {
    margin: var(--s-1) 0 var(--s-3);
    font-size: var(--t-md);
  }
  .summary {
    color: var(--text-soft);
    font-size: var(--t-sm);
    margin-bottom: var(--s-4);
  }
  .explain h4 {
    font-family: var(--font-display);
    font-size: var(--t-xs);
    text-transform: none;
    color: var(--text-faint);
    margin: var(--s-4) 0 var(--s-2);
    font-weight: 600;
  }
  .constraints {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
  }
  .constraints li {
    background: var(--constraint-soft);
    border-radius: var(--r-sm);
    padding: var(--s-3);
  }
  .c-top {
    display: flex;
    align-items: baseline;
    gap: var(--s-2);
  }
  .c-id {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--constraint);
    font-size: var(--t-xs);
  }
  .c-title {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: var(--t-sm);
  }
  .constraints p {
    margin: var(--s-1) 0;
    font-size: var(--t-xs);
    color: var(--text-soft);
  }
  .c-src {
    font-size: var(--t-xs);
    color: var(--constraint);
  }
  .shaped,
  .path {
    margin: 0;
    padding-left: var(--s-5);
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    font-size: var(--t-xs);
  }
  .shaped {
    list-style: none;
    padding-left: 0;
  }
  .shaped code {
    display: block;
    color: var(--text);
  }
  .shaped-note {
    color: var(--text-faint);
  }
  .path li {
    color: var(--text-soft);
  }

  @media (max-width: 960px) {
    .plan-grid {
      grid-template-columns: 1fr;
    }
    .explain {
      position: static;
      max-height: none;
    }
  }
</style>
