<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { Action, Plan, Replay, ReplayStep } from '$lib/api';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  const labels = $derived(new Map<string, Action>(
    [...data.plan.actions, ...data.naive.actions].map((a) => [a.id, a])
  ));

  const maxSteps = $derived(Math.max(data.replay.defuse.steps.length, data.replay.naive.steps.length));
  let step = $state(0);
  let playing = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  function play() {
    if (playing) {
      stop();
      return;
    }
    if (step >= maxSteps - 1) step = 0;
    playing = true;
    timer = setInterval(() => {
      if (step >= maxSteps - 1) {
        stop();
        return;
      }
      step += 1;
    }, 1100);
  }
  function stop() {
    playing = false;
    if (timer) clearInterval(timer);
  }
  onDestroy(stop);

  function shownSteps(r: Replay): ReplayStep[] {
    return r.steps.slice(0, step + 1);
  }
  function firedBy(r: Replay): boolean {
    return r.steps.slice(0, step + 1).some((s) => s.triggers.length > 0);
  }
  function label(id: string): string {
    return labels.get(id)?.label ?? id;
  }
</script>

<section>
  <div class="rp-head">
    <div>
      <h2>Revoke everything, or defuse it</h2>
      <p class="sub">
        The same incident, run two ways against the worm's published triggers. On the left, the
        naive "revoke it all now" baseline. On the right, Defuse's safe order. Step through, or
        press play.
      </p>
    </div>
    <div class="controls">
      <button class="play" onclick={play}>{playing ? 'Pause' : 'Play'}</button>
      <input
        type="range"
        min="0"
        max={maxSteps - 1}
        bind:value={step}
        oninput={stop}
        aria-label="Timeline step"
      />
      <span class="step-count mono">step {step + 1}/{maxSteps}</span>
    </div>
  </div>

  <div class="split">
    {#each [{ key: 'naive', r: data.replay.naive, title: 'Naive: revoke everything now' }, { key: 'defuse', r: data.replay.defuse, title: 'Defuse: safe order' }] as side (side.key)}
      <div class="side" class:lost={firedBy(side.r) && side.r.hosts_lost.length}>
        <header class="side-head">
          <h3>{side.title}</h3>
          <span class="verdict" class:bad={!side.r.safe} class:good={side.r.safe}>
            {side.r.safe ? 'contained' : 'detonated'}
          </span>
        </header>

        <div class="sentinel" class:shredded={firedBy(side.r) && side.r.hosts_lost.length}>
          <span class="sentinel-label">/srv/defuse-sentinel</span>
          <div class="files">
            {#each Array(9) as _, i (i)}
              <span class="file"></span>
            {/each}
          </div>
          <span class="sentinel-state">
            {firedBy(side.r) && side.r.hosts_lost.length ? 'destroyed' : 'intact'}
          </span>
        </div>

        <ol class="steps mist-scroll">
          {#each shownSteps(side.r) as s (s.layer)}
            <li class="rstep" class:has-trigger={s.triggers.length}>
              <div class="rstep-head">
                <span class="rstep-n mono">L{s.layer}</span>
                <span class="rstep-actions">{s.actions.length} action{s.actions.length === 1 ? '' : 's'}</span>
              </div>
              <ul class="rstep-list">
                {#each s.actions as a (a)}
                  <li>{label(a)}</li>
                {/each}
              </ul>
              {#each s.triggers as t (t.detail)}
                <div class="trigger">
                  <strong>{t.kind === 'dead_mans_switch' ? 'Dead-man’s switch' : 'Revocation handler'}</strong>
                  {t.detail}
                </div>
              {/each}
            </li>
          {/each}
        </ol>
      </div>
    {/each}
  </div>
</section>

<style>
  .rp-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--s-5);
    flex-wrap: wrap;
    margin-bottom: var(--s-4);
  }
  .sub {
    margin-top: var(--s-2);
    color: var(--text-soft);
    font-size: var(--t-sm);
    max-width: 62ch;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: var(--s-3);
  }
  .play {
    padding: var(--s-2) var(--s-4);
    border-radius: var(--r-chip);
    border: 1px solid var(--line-strong);
    background: var(--card);
    color: var(--text);
    font-weight: 600;
  }
  .play:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  input[type='range'] {
    width: 160px;
    accent-color: var(--accent);
  }
  .step-count {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--s-4);
  }
  .side {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: var(--r-tile);
    padding: var(--s-5);
    box-shadow: var(--shadow);
    transition: border-color 0.3s ease;
  }
  .side.lost {
    border-color: var(--alarm);
  }
  .side-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-3);
    margin-bottom: var(--s-4);
  }
  .side-head h3 {
    font-size: var(--t-md);
  }
  .verdict {
    font-size: var(--t-xs);
    font-weight: 600;
    padding: 2px var(--s-3);
    border-radius: var(--r-chip);
  }
  .verdict.good {
    background: var(--accent-soft);
    color: var(--accent);
  }
  .verdict.bad {
    background: var(--alarm-soft);
    color: var(--alarm);
  }
  .sentinel {
    border: 1px dashed var(--line-strong);
    border-radius: var(--r-sm);
    padding: var(--s-4);
    margin-bottom: var(--s-4);
    display: flex;
    flex-direction: column;
    gap: var(--s-3);
    align-items: center;
    transition: all 0.4s ease;
  }
  .sentinel.shredded {
    border-color: var(--alarm);
    background:
      var(--horizon),
      var(--alarm-soft);
  }
  .sentinel-label {
    font-family: var(--font-mono);
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .files {
    display: grid;
    grid-template-columns: repeat(9, 1fr);
    gap: 5px;
    width: 100%;
  }
  .file {
    height: 18px;
    border-radius: 3px;
    background: var(--accent);
    opacity: 0.75;
    transition: all 0.4s ease;
  }
  .shredded .file {
    background: var(--alarm);
    opacity: 0.25;
    transform: scaleY(0.3) skewX(18deg);
  }
  .sentinel-state {
    font-size: var(--t-xs);
    font-weight: 600;
    color: var(--text-soft);
  }
  .shredded .sentinel-state {
    color: var(--alarm);
  }
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    max-height: 44vh;
    overflow-y: auto;
  }
  .rstep {
    border: 1px solid var(--line);
    border-radius: var(--r-sm);
    padding: var(--s-3);
  }
  .rstep.has-trigger {
    border-color: var(--alarm);
    background: var(--alarm-soft);
  }
  .rstep-head {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    margin-bottom: var(--s-2);
  }
  .rstep-n {
    font-size: var(--t-xs);
    color: var(--text-faint);
  }
  .rstep-actions {
    font-size: var(--t-xs);
    color: var(--text-soft);
  }
  .rstep-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: var(--t-xs);
    color: var(--text-soft);
  }
  .trigger {
    margin-top: var(--s-2);
    font-size: var(--t-xs);
    color: var(--alarm);
  }
  .trigger strong {
    display: block;
    font-family: var(--font-display);
  }

  @media (max-width: 860px) {
    .split {
      grid-template-columns: 1fr;
    }
  }
</style>
