<script>
  import { agentColor } from '../store/worldStore.js'

  export let agent
  export let selected = false
  export let onSelect = () => {}

  const STATUS_LABEL = {
    operational: '● OPERATIONAL',
    degraded:    '◐ DEGRADED',
    silent:      '○ SILENT',
  }
  const STATUS_COLOR = {
    operational: '#00ff88',
    degraded:    '#ffaa00',
    silent:      '#ff3355',
  }

  const TYPE_META = {
    USV: { label: '⛵ SURFACE', bg: '#001a2e', border: '#0055aa', text: '#4499dd' },
    UAV: { label: '✈ AERIAL',  bg: '#1a001a', border: '#8800cc', text: '#cc66ff' },
  }

  $: color      = agentColor(agent.id)
  $: statusText = STATUS_LABEL[agent.status]  ?? agent.status
  $: statusClr  = STATUS_COLOR[agent.status]  ?? '#ffffff'
  $: cotLines   = (agent.cot_text ?? '').split('\n').slice(-6).join('\n')
  $: typeMeta   = TYPE_META[(agent.type ?? '').toUpperCase()] ?? TYPE_META.USV

  function fmt(n) { return n?.toFixed(1) ?? '—' }

  async function forceStatus(status) {
    await fetch(`/api/agents/${agent.id}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="card" class:selected on:click={onSelect}
     style="--agent-color:{color}; --status-color:{statusClr}">

  <div class="header">
    <div class="name-row">
      <span class="dot" style="background:{color}"></span>
      <span class="name">{agent.name}</span>
      <span class="type-badge"
            style="background:{typeMeta.bg};border-color:{typeMeta.border};color:{typeMeta.text}">
        {typeMeta.label}
      </span>
      {#if agent.connected}
        <span class="connected-badge">AI</span>
      {/if}
    </div>
    <span class="status" style="color:{statusClr}">{statusText}</span>
  </div>

  <div class="metrics">
    <div class="metric">
      <span class="mkey">POS</span>
      <span class="mval">{fmt(agent.position?.lat)}°N {fmt(agent.position?.lon)}°E</span>
    </div>
    <div class="metric">
      <span class="mkey">HDG</span>
      <span class="mval">{fmt(agent.heading)}°</span>
    </div>
    <div class="metric">
      <span class="mkey">SPD</span>
      <span class="mval">{fmt(agent.speed_kn)} kn</span>
    </div>
  </div>

  {#if agent.current_task}
    <div class="task">{agent.current_task}</div>
  {/if}

  {#if cotLines}
    <div class="cot">
      <div class="cot-title">CHAIN OF THOUGHT</div>
      <div class="cot-text">{cotLines}</div>
    </div>
  {/if}

  <div class="controls">
    {#if agent.status !== 'silent'}
      <button class="ctrl-btn danger" title="Simulate comms loss"
              on:click|stopPropagation={() => forceStatus('silent')}>
        ✂ Disconnect
      </button>
    {:else}
      <button class="ctrl-btn ok"
              on:click|stopPropagation={() => forceStatus('operational')}>
        ↩ Reconnect
      </button>
    {/if}
  </div>
</div>

<style>
  .card {
    border-left: 3px solid var(--agent-color);
    padding: 12px 14px;
    border-bottom: 1px solid #111e2a;
    cursor: pointer;
    transition: background 0.15s;
  }
  .card:hover    { background: #0d1a26; }
  .card.selected { background: #0d2030; }

  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
  .name-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .dot  { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .name { font-size: 16px; font-weight: bold; color: #e0f0ff; letter-spacing: 0.04em; }
  .type-badge {
    font-size: 10px; font-weight: bold; letter-spacing: 0.06em;
    border: 1px solid; border-radius: 3px; padding: 1px 6px;
  }
  .connected-badge {
    font-size: 10px; background: #004433; color: #00ff88;
    border: 1px solid #00ff8844; border-radius: 3px; padding: 1px 5px;
    letter-spacing: 0.05em;
  }
  .status { font-size: 11px; letter-spacing: 0.05em; font-weight: bold; white-space: nowrap; }

  .metrics { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
  .metric  { display: flex; gap: 10px; font-size: 12px; }
  .mkey    { color: #4a7a9a; width: 32px; flex-shrink: 0; }
  .mval    { color: #c8d8e8; font-family: monospace; }

  .task {
    font-size: 12px;
    color: #8ab0c0;
    padding: 6px 8px;
    background: #0a1820;
    border-radius: 3px;
    border-left: 2px solid var(--agent-color);
    margin-bottom: 8px;
    line-height: 1.4;
  }

  .cot {
    background: #06101a;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 8px;
  }
  .cot-title { font-size: 10px; color: #3a6a8a; letter-spacing: 0.1em; margin-bottom: 5px; }
  .cot-text  {
    font-size: 12px; color: #8ab8d0; font-family: monospace;
    white-space: pre-wrap; line-height: 1.5; max-height: 90px; overflow: hidden;
  }

  .controls { display: flex; gap: 6px; }
  .ctrl-btn {
    font-size: 11px; font-family: monospace; padding: 4px 10px; border-radius: 3px;
    border: 1px solid; cursor: pointer; letter-spacing: 0.04em; transition: opacity 0.15s;
    text-transform: uppercase;
  }
  .ctrl-btn:hover { opacity: 0.8; }
  .ctrl-btn.danger { background: #200a0a; border-color: #ff335555; color: #ff6677; }
  .ctrl-btn.ok     { background: #0a2010; border-color: #00ff8844; color: #00ff88; }
</style>
