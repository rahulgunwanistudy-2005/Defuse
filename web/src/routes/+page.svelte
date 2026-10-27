<script lang="ts">
  import { invalidateAll } from '$app/navigation';
  import Brand from '$lib/components/Brand.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import AmbientTiles from '$lib/components/AmbientTiles.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { fmtDuration } from '$lib/api';
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
  let filter = $state('all');
  let search = $state('');
  let selectedStep = $state(0);
  let retrying = $state(false);
  const featured = $derived(data.featured);
  const consoleUrl = $derived(featured ? `/incidents/${featured.id}/` : '#incidents');
  const jobs = $derived(data.graph?.nodes.filter(n => n.kind === 'job').length ?? null);
  const visibleIncidents = $derived(data.incidents.filter(incident =>
    (filter === 'all' || (filter === 'verified' ? incident.status === 'verified' : !['verified', 'contained'].includes(incident.status))) &&
    `${incident.title} ${incident.namespace} ${incident.id}`.toLowerCase().includes(search.toLowerCase())
  ));
  const steps = [
    { title: 'See the whole picture.', label: 'Map the exposure', icon: 'graph', body: 'Trace affected CI jobs to runners, credential scopes, rogue packages, and planted agent hooks. Metadata only. Secret values stay private.', view: 'map', action: 'Explore the map' },
    { title: 'Make the next move safe.', label: 'Plan the safe order', icon: 'layers', body: 'The deterministic planner orders every action against six safety constraints. Inspect the dependencies and the reason behind each step.', view: 'plan', action: 'Inspect the plan' },
    { title: 'Know it is contained.', label: 'Verify the outcome', icon: 'shield', body: 'Follow the action ledger, inspect verification checks, and compare the safe plan with the naive baseline in an inert adversary replay.', view: 'record', action: 'Review the evidence' }
  ];
  const selected = $derived(steps[selectedStep]);
  const questions = [
    { title: 'Why does the order matter?', body: 'A worm can watch for credential revocation and trigger a destructive handler. Defuse isolates the host or stops its watcher first, preserves evidence, then removes persistence and rotates credentials in the safe order.' },
    { title: 'Does Defuse read my secrets?', body: 'No. Collectors request variable names, scopes, and metadata only. Credential replacement is handled by a separate authority. Secret values are never collected, displayed, or logged by the containment engine.' },
    { title: 'What can I see in the console?', body: 'Each incident has a live event timeline, an interactive exposure map, an ordered action plan with safety explanations, a naive-versus-Defuse replay, and an action ledger with verification evidence.' },
    { title: 'Is the local scenario live containment?', body: 'The seeded scenario uses inert modeled services and simulated incident timings. It demonstrates the complete workflow, but does not establish real GitLab or cloud containment. The console labels scenario data explicitly.' }
  ];
  async function retry() { retrying = true; try { await invalidateAll(); } finally { retrying = false; } }
  function moveTab(event: KeyboardEvent, i: number) {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    selectedStep = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (i + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
    document.getElementById(`step-tab-${selectedStep}`)?.focus();
  }
</script>

<svelte:head>
  <title>Defuse — contain the threat, keep your world intact</title>
  <link rel="preload" as="image" href="/images/alpine-landscape.png" />
</svelte:head>

<div class="landing">
  <section class="hero" aria-labelledby="hero-title">
    <img class="landscape" src="/images/alpine-landscape.png" alt="" fetchpriority="high" width="1586" height="992" />
    <img class="cloud cloud-left" src="/images/pastel-cloud.png" alt="" width="2172" height="724" />
    <img class="cloud cloud-right" src="/images/pastel-cloud.png" alt="" width="2172" height="724" />
    <AmbientTiles glass />
    <header class="landing-header">
      <nav class="nav-pill" aria-label="Main navigation"><Brand /><div class="nav-links"><a href="#how-it-works">How it works</a><a href="#incidents">Incidents</a></div><a class="button nav-cta" href={consoleUrl}>Open console <Icon name="arrow" size={16} /></a></nav>
      <div class="theme"><ThemeToggle /></div>
    </header>
    <div class="hero-copy">
      <span class="eyebrow"><span class="signal-dot"></span>Worm containment for GitLab CI</span>
      <h1 id="hero-title">Contain the supply-chain worm.<br />{' '}Keep your world <em>intact.</em></h1>
      <p>From the first exposure to the final verification.<br class="desktop-break" /> Every action, in the one order that keeps you safe.</p>
      <div class="hero-actions"><a class="button" href={consoleUrl}>Explore your workspace <Icon name="arrow" size={17} /></a><a class="replay-link" href={featured ? `${consoleUrl}replay` : '#how-it-works'}><span class="play-icon"><Icon name="play" size={12} /></span>{featured ? 'Watch the replay' : 'See how it works'}</a></div>
    </div>
    <div class="landscape-card status-card">
      <div class="glass-icon"><Icon name="shield" size={21} /></div><div><span class="glass-label">{featured ? 'Latest incident' : 'Your workspace'}</span><strong>{featured ? featured.status.charAt(0).toUpperCase() + featured.status.slice(1) : data.unavailable ? 'Awaiting connection' : 'Ready when you are'}</strong></div>
      {#if featured}<span class="status-check"><Icon name={featured.status === 'verified' ? 'check' : 'activity'} size={17} /></span>{/if}
      <span class="glass-foot">{featured?.origin === 'scenario' ? 'Local modeled scenario' : featured ? featured.namespace : 'Connect the engine to get started'}</span>
    </div>
    <div class="landscape-card order-card"><span class="glass-label"><Icon name="layers" size={14} /> Built around the safe order</span><div class="mini-phases"><span><Icon name="shield" size={16} />Isolate</span><i></i><span><Icon name="layers" size={16} />Preserve</span><i></i><span><Icon name="check" size={16} />Verify</span></div><span class="glass-foot">6 constraints. Every plan.</span></div>
    <div class="hero-bottom"><span>Clarity in the middle of an incident.</span><a href="#overview" aria-label="Explore Defuse overview">↓</a></div>
  </section>

  <section class="overview section-wrap" id="overview" aria-labelledby="overview-title">
    <AmbientTiles />
    <div class="section-intro"><span class="eyebrow">Your engine. A clearer picture.</span><h2 id="overview-title">Complex threats.<br />One safe order.</h2><p>See what is exposed, understand the plan,<br class="desktop-break" /> and follow every action through to verification.</p></div>
    <div class="stats" aria-label="Workspace metrics">
      <article class="ticket"><span>Incidents in your workspace</span><strong>{data.unavailable ? '—' : data.incidents.length}</strong><small>From the connected engine</small></article>
      <article class="ticket"><span>CI jobs exposed</span><strong>{jobs ?? '—'}</strong><small>Latest incident’s exposure graph</small></article>
      <article class="ticket"><span>Actions executed</span><strong>{data.metrics?.actions_executed ?? '—'}</strong><small>Latest incident’s action ledger</small></article>
      <article class="ticket"><span>Time to containment</span><strong class="duration">{fmtDuration(data.metrics?.time_to_containment)}</strong><small>{featured?.origin === 'scenario' ? 'Modeled scenario timing' : 'Latest incident’s measured timing'}</small></article>
    </div>
    <div class="integration-strip" aria-label="Defuse workflow"><span><Icon name="code" />GitLab CI</span><span><Icon name="graph" />Exposure graph</span><span><Icon name="layers" />Safe-order planner</span><span><Icon name="shield" />Verified evidence</span></div>
  </section>

  <section class="workflow section-wrap" id="how-it-works" aria-labelledby="workflow-title">
    <div class="section-intro"><span class="eyebrow">A little clarity goes a long way</span><h2 id="workflow-title">From exposure.<br />To peace of mind.</h2><p>One connected workflow. A reason behind every move.</p></div>
    <div class="step-tabs" role="tablist" aria-label="Containment workflow">{#each steps as step, i (step.label)}<button role="tab" id={`step-tab-${i}`} aria-controls="workflow-panel" aria-selected={selectedStep === i} tabindex={selectedStep === i ? 0 : -1} class:chosen={selectedStep === i} onclick={() => selectedStep = i} onkeydown={(event) => moveTab(event, i)}><span>{i + 1}</span>{step.label}</button>{/each}</div>
    <div class="workflow-panel" role="tabpanel" id="workflow-panel" aria-labelledby={`step-tab-${selectedStep}`} tabindex="0">
      <div class="step-visual" aria-hidden="true"><span class="step-number">{selectedStep + 1}</span><img class="step-cloud" src="/images/pastel-cloud.png" alt="" loading="lazy" width="2172" height="724" /><div class="flow-diagram"><div class="flow-node"><Icon name={selected.icon} size={27} /></div><span class="connector"></span><div class="flow-branches"><span><Icon name="check" size={15} /></span><span><Icon name="check" size={15} /></span><span><Icon name="check" size={15} /></span></div></div></div>
      <div class="step-copy"><Icon name={selected.icon} size={28} /><h3>{selected.title}</h3><p>{selected.body}</p><a class="text-link" href={featured ? `${consoleUrl}${selected.view}` : '#incidents'}>{featured ? selected.action : 'View your workspace'} <Icon name="arrow" size={17} /></a></div>
    </div>
  </section>

  <section class="incidents section-wrap" id="incidents" aria-labelledby="incidents-title">
    <div class="workspace-heading"><div><span class="eyebrow">{data.unavailable ? 'Your containment workspace' : 'Connected to the engine'}</span><h2 id="incidents-title">Your containment workspace.</h2><p>The full picture, from first signal to verified outcome.</p></div><button class="refresh-button" onclick={retry} disabled={retrying} aria-label={retrying ? 'Refreshing incidents' : 'Refresh incidents'}><Icon name="activity" size={16} /><span>{retrying ? 'Refreshing…' : 'Refresh'}</span></button></div>
    {#if data.unavailable}
      <div class="empty engine-error" role="status"><Icon name="activity" size={30} /><h3>The engine is unavailable.</h3><p>Start the engine service and check the frontend’s API connection, then refresh to load your incidents.</p><button class="button" onclick={retry} disabled={retrying}>{retrying ? 'Reconnecting…' : 'Reconnect to engine'}</button></div>
    {:else if data.incidents.length === 0}
      <div class="empty"><Icon name="shield" size={32} /><h3>A clear workspace.</h3><p>No incidents yet. Run the local scenario or submit an advisory through your configured intake flow to open one.</p><code>uv run defuse demo</code></div>
    {:else}
      <div class="workspace-tools"><div class="filters" aria-label="Filter incidents">{#each ['all', 'active', 'verified'] as option (option)}<button class:chosen={filter === option} aria-pressed={filter === option} onclick={() => filter = option}>{option.charAt(0).toUpperCase() + option.slice(1)}{#if option === 'all'}<span>{data.incidents.length}</span>{/if}</button>{/each}</div><label class="search"><Icon name="search" size={16} /><input aria-label="Search incidents" type="search" placeholder="Find an incident…" bind:value={search} /></label></div>
      <ul class="incident-list">{#each visibleIncidents as incident (incident.id)}<li><a class="incident-row" href={`/incidents/${incident.id}/`}><span class="incident-icon"><Icon name="shield" size={23} /></span><span class="incident-info"><strong>{incident.title}</strong><span>{incident.namespace}<span class="meta-separator">/</span>{incident.id}</span></span><span class="incident-state">{#if incident.origin === 'scenario'}<span class="scenario-tag">Local scenario</span>{/if}<StatusBadge status={incident.status} /></span><span class="row-arrow"><Icon name="arrow" size={20} /></span></a></li>{:else}<li class="no-results">No incidents match this view. <button onclick={() => { search = ''; filter = 'all'; }}>Clear filters</button></li>{/each}</ul>
      <p class="workspace-note"><Icon name="shield" size={14} />Metadata only. Secret values are never collected.{#if featured?.origin === 'scenario'}<span>Local scenarios use modeled services and timings.</span>{/if}</p>
    {/if}
  </section>

  <section class="questions section-wrap" aria-labelledby="questions-title"><div><span class="eyebrow">A few things worth knowing</span><h2 id="questions-title">Confidence comes<br />from understanding.</h2><p>Containment should be explainable.<br />Right down to the next action.</p></div><div class="faq-list">{#each questions as question (question.title)}<details><summary>{question.title}<span aria-hidden="true">+</span></summary><p>{question.body}</p></details>{/each}</div></section>
  <section class="closing" aria-labelledby="closing-title"><div class="closing-landscape" aria-hidden="true"></div><AmbientTiles /><div class="closing-card"><span class="eyebrow">Every action, in the right order</span><h2 id="closing-title">Keep the threat contained.<br />Keep your world intact.</h2><p>Your exposure. Your plan. The evidence to trust it.</p><a class="button" href={consoleUrl}>Open your workspace <Icon name="arrow" size={17} /></a></div></section>
  <footer class="landing-footer"><Brand /><nav aria-label="Footer navigation"><a href="#how-it-works">How it works</a><a href="#incidents">Workspace</a><a href="https://github.com/rahulgunwanistudy-2005/Defuse" target="_blank" rel="noreferrer">Source code <Icon name="arrow" size={14} /></a></nav><p>Defuse · Worm containment for GitLab CI</p></footer>
</div>

<style>
  .landing { background: var(--card); overflow: clip; }
  .hero { min-height: 930px; height: min(1000px, 110vh); position: relative; isolation: isolate; background: #fff; color: #171b10; }
  .landscape { position: absolute; z-index: -3; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: center bottom; }
  .cloud { position: absolute; z-index: -1; width: 440px; height: auto; pointer-events: none; animation: cloud-drift 22s ease-in-out infinite alternate; }
  .cloud-left { top: 120px; left: -210px; } .cloud-right { top: 155px; right: -225px; transform: scaleX(-1); animation-direction: alternate-reverse; }
  .landing-header { padding-top: 30px; position: relative; z-index: 4; }
  .nav-pill { display: flex; align-items: center; gap: 32px; margin: auto; width: fit-content; max-width: calc(100% - 40px); padding: 7px 7px 7px 18px; background: var(--card); border: 1px solid var(--line); border-radius: 100px; box-shadow: 0 5px 24px #17200b0a; }
  .nav-links { display: flex; gap: 25px; align-items: center; } .nav-links a { text-decoration: none; font-size: 12px; color: var(--text-soft); } .nav-links a:hover { color: var(--accent); }
  .nav-cta { padding: 13px 18px; font-size: 12px; } .theme { position: absolute; right: 34px; top: 43px; }
  .hero-copy { margin: 117px auto 0; position: relative; text-align: center; padding: 0 20px; animation: arrive .85s cubic-bezier(.2,.7,.2,1) both; }
  .eyebrow { display: inline-flex; align-items: center; gap: 7px; background: var(--accent-soft); color: var(--text); padding: 6px 12px; border-radius: 100px; font-size: 12px; font-weight: 450; width: fit-content; }
  .hero .eyebrow { background: #edf0e2; color: #3d4c1d; } .signal-dot { width: 5px; height: 5px; border-radius: 50%; background: #59711a; }
  .hero h1 { font-size: clamp(46px, 5.6vw, 82px); line-height: 1.06; letter-spacing: -.065em; font-weight: 450; margin: 24px auto 22px; max-width: 1100px; } .hero h1 em { font-weight: 450; color: #4b6209; }
  .hero-copy > p { font-size: 16px; line-height: 1.65; color: #65685c; margin: auto; } .hero-actions { display: flex; justify-content: center; gap: 25px; align-items: center; margin-top: 27px; } .hero-actions .button { background: #4b6209; color: #fff; }
  .replay-link { display: inline-flex; gap: 9px; align-items: center; font-size: 13px; text-decoration: none; color: #414632; } .play-icon { display: inline-flex; align-items: center; justify-content: center; height: 28px; width: 28px; border-radius: 50%; border: 1px solid #ccd3bc; }
  .landscape-card { position: absolute; background: #ffffffe0; border: 1px solid #ffffffb3; box-shadow: 0 8px 35px #152d3412; backdrop-filter: blur(18px); border-radius: 17px; color: #293522; }
  .status-card { left: 12%; bottom: 160px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 13px; width: 260px; padding: 17px; transform: rotate(-3deg); }
  .glass-icon { display: flex; align-items: center; justify-content: center; background: #edf1df; color: #53671d; width: 41px; height: 44px; border-radius: 11px; } .glass-label { display: flex; align-items: center; gap: 6px; font-size: 10px; color: #5f6b57; }
  .status-card strong { display: block; font-weight: 550; font-size: 19px; line-height: 1.4; } .status-check { display: grid; place-items: center; border: 1px solid #d7dfc7; width: 28px; height: 28px; border-radius: 50%; color: #5c751c; }
  .glass-foot { grid-column: 1 / -1; font-size: 10px; color: #66715f; border-top: 1px solid #cbd3bf88; padding-top: 10px; } .order-card { right: 10%; bottom: 110px; width: 300px; padding: 17px 20px; transform: rotate(3deg); }
  .mini-phases { display: flex; gap: 9px; align-items: center; margin: 18px 0 14px; } .mini-phases > span { display: flex; flex-direction: column; align-items: center; gap: 7px; font-size: 10px; flex: 1; } .mini-phases i { width: 18px; height: 1px; background: #becaa8; } .order-card .glass-foot { display: block; }
  .hero-bottom { position: absolute; bottom: 24px; left: 4%; right: 4%; display: flex; align-items: center; justify-content: space-between; color: white; text-shadow: 0 1px 5px #123; font-size: 11px; } .hero-bottom a { display: grid; place-items: center; width: 32px; height: 32px; border: 1px solid #fff8; border-radius: 50%; text-decoration: none; font-size: 18px; }
  .section-wrap { max-width: 1240px; margin: auto; padding: 110px 50px; position: relative; scroll-margin-top: 20px; } .section-intro { text-align: center; position: relative; }
  h2 { font-size: clamp(34px, 4.1vw, 56px); line-height: 1.1; letter-spacing: -.055em; font-weight: 450; margin-top: 24px; } .section-intro > p { margin: 20px auto 0; font-size: 15px; color: var(--text-soft); line-height: 1.7; }
  .overview { max-width: 1400px; padding-top: 110px; padding-bottom: 30px; } .overview .section-intro { margin-bottom: 60px; }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; max-width: 1140px; margin: auto; position: relative; }
  .ticket { padding: 28px 26px; min-width: 0; background: var(--lime); border-radius: 35px; color: #1b220a; position: relative; } .ticket::before, .ticket::after { content: ''; position: absolute; width: 30px; height: 44px; background: var(--card); top: calc(50% - 22px); border-radius: 50%; } .ticket::before { left: -18px; } .ticket::after { right: -18px; }
  .ticket > span { font-size: 12px; font-weight: 500; } .ticket strong { font-weight: 500; font-size: clamp(36px, 4.4vw, 65px); line-height: 1; letter-spacing: -.07em; display: block; margin-top: 44px; white-space: nowrap; } .ticket strong.duration { font-size: clamp(28px, 3.3vw, 49px); min-height: 1.33em; } .ticket small { display: block; font-size: 10px; color: #3e4b1e; margin-top: 16px; }
  .integration-strip { position: relative; display: grid; grid-template-columns: repeat(4, 1fr); max-width: 1140px; margin: 24px auto 0; background: var(--card-sunk); border-radius: 20px; padding: 25px 10px; } .integration-strip > span { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 8px; border-right: 1px solid var(--line); font-size: 14px; font-weight: 500; letter-spacing: -.03em; } .integration-strip > span:last-child { border: 0; }
  .step-tabs { display: grid; grid-template-columns: repeat(3, 1fr); border-bottom: 1px solid var(--line); margin-top: 55px; } .step-tabs button { padding: 18px 8px; display: flex; gap: 12px; align-items: center; justify-content: center; color: var(--text-soft); background: none; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; font-size: 14px; } .step-tabs button > span { display: grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; border: 1px solid var(--line); font-size: 12px; } .step-tabs button.chosen { color: var(--accent); border-bottom-color: var(--accent); } .step-tabs button.chosen > span { background: var(--accent); color: var(--card); border-color: var(--accent); }
  .workflow-panel { display: grid; grid-template-columns: 1fr 1fr; min-height: 380px; align-items: center; gap: 70px; margin-top: 40px; } .step-visual { min-height: 320px; position: relative; overflow: hidden; display: flex; align-items: flex-end; padding: 30px; background: var(--canvas); border-radius: 24px; } .step-number { font-size: 310px; font-weight: 500; line-height: .85; letter-spacing: -.1em; color: var(--accent); opacity: .9; } .step-cloud { position: absolute; width: 225px; height: auto; top: 35px; right: -20px; }
  .flow-diagram { display: flex; align-items: center; position: absolute; bottom: 45px; right: 35px; } .flow-node, .flow-branches > span { display: grid; place-items: center; border: 1px solid var(--line); background: var(--card); color: var(--accent); border-radius: 16px; box-shadow: var(--shadow); } .flow-node { height: 70px; width: 70px; } .connector { height: 1px; width: 45px; background: var(--line-strong); } .flow-branches { display: flex; flex-direction: column; gap: 9px; } .flow-branches > span { height: 40px; width: 40px; border-radius: 10px; }
  .step-copy { padding-right: 25px; } .step-copy > :global(svg) { color: var(--accent); margin-bottom: 22px; } .step-copy h3 { font-size: 32px; font-weight: 450; letter-spacing: -.04em; } .step-copy p { color: var(--text-soft); font-size: 15px; line-height: 1.8; margin: 20px 0 24px; } .text-link { display: inline-flex; align-items: center; gap: 12px; color: var(--accent); text-decoration: none; font-size: 14px; font-weight: 500; } .text-link:hover { text-decoration: underline; }
  .incidents { padding-top: 60px; } .workspace-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; } .workspace-heading h2 { font-size: clamp(32px, 3.5vw, 46px); margin-top: 20px; } .workspace-heading p { font-size: 14px; color: var(--text-soft); margin-top: 18px; }
  .refresh-button { display: flex; align-items: center; gap: 7px; padding: 9px 14px; background: var(--card); color: var(--text-soft); border: 1px solid var(--line); border-radius: 50px; font-size: 12px; } .refresh-button:hover { border-color: var(--accent); color: var(--accent); }
  .workspace-tools { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin: 35px 0 20px; } .filters { display: flex; gap: 4px; background: var(--canvas); padding: 5px; border: 1px solid var(--line); border-radius: 50px; } .filters button { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border: 0; border-radius: 50px; color: var(--text-soft); background: none; font-size: 12px; } .filters button.chosen { background: var(--card); color: var(--text); box-shadow: var(--shadow); } .filters button span { padding: 0 5px; border-radius: 4px; background: var(--accent-soft); color: var(--accent); }
  .search { display: flex; align-items: center; gap: 10px; border: 1px solid var(--line); padding: 10px 14px; border-radius: 50px; color: var(--text-faint); } .search input { border: 0; outline: none; background: transparent; color: var(--text); width: 165px; font-size: 12px; min-width: 0; } .search:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .incident-list { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line); border-radius: 22px; overflow: hidden; } .incident-list li + li { border-top: 1px solid var(--line); } .incident-row { display: flex; align-items: center; gap: 18px; padding: 25px; text-decoration: none; background: var(--card); transition: background .2s; } .incident-row:hover { background: var(--canvas); } .incident-icon { display: grid; place-items: center; width: 49px; height: 52px; border-radius: 14px; background: var(--accent-soft); color: var(--accent); flex-shrink: 0; }
  .incident-info { display: flex; flex-direction: column; gap: 7px; min-width: 0; } .incident-info > strong { font-size: 15px; font-weight: 500; letter-spacing: -.02em; } .incident-info > span { font-size: 11px; color: var(--text-soft); overflow-wrap: anywhere; } .meta-separator { padding: 0 8px; color: var(--line-strong); } .incident-state { margin-left: auto; display: flex; gap: 12px; align-items: center; flex-shrink: 0; } .scenario-tag { font-size: 10px; color: var(--text-faint); } .row-arrow { color: var(--text-faint); margin-left: 12px; }
  .workspace-note { display: flex; align-items: center; gap: 7px; color: var(--text-faint); font-size: 10px; padding-top: 17px; max-width: none; flex-wrap: wrap; } .workspace-note > span { margin-left: auto; }
  .empty { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 18px; padding: 50px 25px; margin-top: 30px; border: 1px solid var(--line); background: var(--canvas); border-radius: 22px; } .empty > :global(svg) { color: var(--accent); } .empty h3 { font-size: 24px; font-weight: 500; } .empty p { font-size: 14px; color: var(--text-soft); max-width: 55ch; } .empty code { padding: 10px 18px; border: 1px solid var(--line); border-radius: 10px; background: var(--card); } .no-results { padding: 40px; text-align: center; font-size: 14px; color: var(--text-soft); } .no-results button { background: none; border: 0; text-decoration: underline; color: var(--accent); }
  .questions { display: grid; grid-template-columns: 1fr 1.1fr; gap: 90px; padding-top: 40px; padding-bottom: 120px; } .questions h2 { font-size: 41px; } .questions > div > p { margin-top: 20px; font-size: 14px; color: var(--text-soft); line-height: 1.8; } .faq-list { padding-top: 3px; } details { border-bottom: 1px solid var(--line); } summary { cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 22px 0; list-style: none; font-size: 14px; } summary::-webkit-details-marker { display: none; } summary span { font-size: 22px; font-weight: 400; color: var(--text-soft); transition: transform .2s; } details[open] summary span { transform: rotate(45deg); } details p { font-size: 13px; color: var(--text-soft); line-height: 1.8; padding-bottom: 25px; }
  .closing { position: relative; min-height: 730px; padding: 50px 24px 270px; isolation: isolate; background: #fff; } .closing-landscape { position: absolute; inset: 0; z-index: -2; background: url('/images/alpine-landscape.png') center bottom / cover; filter: saturate(.8) brightness(.65) hue-rotate(8deg); mask-image: linear-gradient(transparent 0%, #000 65%); }
  .closing-card { position: relative; margin: auto; max-width: 850px; padding: 62px 30px; text-align: center; background: color-mix(in srgb, var(--card) 82%, transparent); border: 1px solid var(--line); border-radius: 40px; backdrop-filter: blur(20px); box-shadow: inset 0 0 35px #fff2; } .closing-card h2 { font-size: 48px; } .closing-card p { font-size: 15px; margin: 20px auto 28px; color: var(--text-soft); }
  .landing-footer { background: var(--lime); color: #1c260a; display: grid; grid-template-columns: 1fr 2fr 1fr; align-items: center; padding: 55px 5%; gap: 30px; } .landing-footer :global(.brand) { color: #1c260a; } .landing-footer :global(.brand svg path:last-child) { stroke: var(--lime); } .landing-footer nav { display: flex; justify-content: center; gap: 28px; } .landing-footer a { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; text-decoration: none; } .landing-footer a:hover { text-decoration: underline; } .landing-footer p { text-align: right; font-size: 10px; }
  :global([data-theme='dark']) .hero .landscape { filter: brightness(.48) saturate(.75); } :global([data-theme='dark']) .hero { background: var(--card); color: var(--text); } :global([data-theme='dark']) .hero h1 em { color: var(--accent); } :global([data-theme='dark']) .hero-copy > p, :global([data-theme='dark']) .replay-link { color: var(--text-soft); } :global([data-theme='dark']) .cloud { opacity: .65; } :global([data-theme='dark']) .closing { background: var(--card); } :global([data-theme='dark']) .step-tabs button.chosen > span { color: #17200b; }
  @keyframes arrive { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } } @keyframes cloud-drift { from { translate: 0 0; } to { translate: 24px 8px; } }
  @media (min-width: 1700px) { .hero { min-height: 1080px; } .hero-copy { margin-top: 160px; } }
  @media (max-width: 1000px) {
    .hero { min-height: 850px; height: 100vh; } .hero-copy { margin-top: 110px; } .hero h1 { font-size: 62px; } .status-card { left: 7%; bottom: 140px; } .order-card { right: 7%; bottom: 80px; } .theme { top: 108px; right: 20px; } .section-wrap { padding-left: 30px; padding-right: 30px; }
    .ticket { padding: 24px 20px; } .ticket > span { font-size: 11px; } .ticket strong { font-size: 48px; } .ticket strong.duration { font-size: 33px; min-height: 1.45em; } .integration-strip > span { font-size: 12px; gap: 6px; } .workflow-panel { gap: 30px; } .step-copy { padding-right: 0; } .questions { gap: 40px; } .questions h2 { font-size: 34px; } .landing-footer { grid-template-columns: 1fr 2fr; } .landing-footer p { grid-column: 1 / -1; text-align: center; justify-self: center; }
  }
  @media (max-width: 700px) {
    .hero { min-height: 820px; height: 100svh; max-height: 1000px; } .landscape { object-position: 56% bottom; } .landing-header { padding-top: 20px; } .nav-pill { gap: 15px; padding-left: 15px; width: calc(100% - 32px); justify-content: space-between; } .nav-links { display: none; } .nav-cta { padding: 12px 16px; } .theme { top: 92px; right: 19px; }
    .hero-copy { margin-top: 106px; padding: 0 19px; } .hero h1 { font-size: clamp(39px, 8.7vw, 60px); line-height: 1.1; letter-spacing: -.06em; margin-top: 22px; } .hero h1 br { display: none; } .hero .eyebrow { font-size: 10px; } .hero-copy > p { font-size: 13px; max-width: 32ch; } .desktop-break { display: none; } .hero-actions { gap: 14px; margin-top: 23px; flex-direction: column; } .hero-actions .button { font-size: 12px; padding: 14px 20px; } .replay-link { font-size: 12px; background: #ffffffd9; padding: 5px 10px; border-radius: 50px; }
    .cloud { width: 275px; } .cloud-left { left: -162px; top: 120px; } .cloud-right { right: -180px; top: 110px; } .status-card { width: 220px; left: 6%; bottom: 110px; padding: 12px; gap: 10px; } .status-card strong { font-size: 16px; } .glass-icon { width: 35px; height: 37px; } .glass-foot { font-size: 9px; } .order-card { display: none; } .hero-bottom { bottom: 18px; left: 6%; right: 6%; font-size: 10px; }
    .section-wrap { padding: 75px 20px; } .overview { padding-bottom: 20px; } .overview .section-intro { margin-bottom: 35px; } .eyebrow { font-size: 10px; } h2 { margin-top: 18px; font-size: 38px; } .section-intro > p { font-size: 13px; } .stats { grid-template-columns: repeat(2, 1fr); gap: 12px; } .ticket { border-radius: 26px; padding: 22px; } .ticket > span { font-size: 10px; } .ticket strong { margin-top: 30px; font-size: 52px; } .ticket strong.duration { font-size: 30px; min-height: 1.73em; display: flex; align-items: flex-end; } .ticket small { font-size: 9px; }
    .integration-strip { grid-template-columns: repeat(2, 1fr); padding: 13px 6px; gap: 10px 0; border-radius: 15px; } .integration-strip > span { font-size: 11px; padding: 9px 3px; } .integration-strip > span:nth-child(2) { border: 0; } .step-tabs { margin-top: 30px; } .step-tabs button { font-size: 10px; padding: 13px 4px; gap: 6px; flex-direction: column; } .step-tabs button > span { width: 22px; height: 22px; font-size: 10px; }
    .workflow-panel { grid-template-columns: 1fr; gap: 28px; margin-top: 25px; } .step-visual { min-height: 260px; } .step-number { font-size: 250px; } .step-copy { padding: 0 8px; } .step-copy > :global(svg) { display: none; } .step-copy h3 { font-size: 28px; } .step-copy p { font-size: 13px; margin-top: 15px; } .text-link { font-size: 13px; }
    .incidents { padding-top: 20px; } .workspace-heading { align-items: flex-start; gap: 10px; } .workspace-heading h2 { font-size: 34px; } .workspace-heading p { font-size: 12px; margin-top: 14px; } .refresh-button { margin-top: 4px; padding: 9px; } .refresh-button > span { display: none; }
    .workspace-tools { flex-direction: column; align-items: stretch; margin: 25px 0 15px; gap: 12px; } .filters { align-self: flex-start; } .filters button { font-size: 11px; padding: 7px 14px; } .search { padding: 11px 14px; } .search input { width: 100%; } .incident-row { flex-wrap: wrap; gap: 12px; padding: 20px 16px; } .incident-icon { width: 39px; height: 42px; } .incident-info { width: calc(100% - 55px); } .incident-info > strong { font-size: 13px; } .incident-info > span { font-size: 10px; } .incident-state { margin-left: 52px; } .row-arrow { margin-left: auto; } .workspace-note { font-size: 9px; gap: 5px; } .workspace-note > span { margin-left: 0; width: 100%; }
    .questions { grid-template-columns: 1fr; padding-top: 0; gap: 25px; } .questions h2 { font-size: 34px; } .questions > div > p { font-size: 13px; } summary { font-size: 12px; padding: 20px 0; } .closing { min-height: 620px; padding: 35px 20px 210px; } .closing-card { padding: 38px 20px; border-radius: 28px; } .closing-card h2 { font-size: 34px; } .closing-card p { font-size: 12px; } .closing-card .button { font-size: 12px; } .closing-landscape { background-size: auto 100%; } .landing-footer { grid-template-columns: 1fr; justify-items: center; gap: 25px; padding: 35px 20px; } .landing-footer nav { gap: 22px; } .landing-footer p { font-size: 9px; }
  }
</style>
