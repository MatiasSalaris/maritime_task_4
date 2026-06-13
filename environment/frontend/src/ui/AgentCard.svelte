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

  $: color      = agentColor(agent.id)
  $: statusText = STATUS_LABEL[agent.status]  ?? agent.status
  $: statusClr  = STATUS_COLOR[agent.status]  ?? '#ffffff'
  $: cotLines   = (agent.cot_text ?? '').split('\n').slice(-6).join('\n')

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
      <span class="type">{agent.type}</span>
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

  <!-- Controls (comm disruption etc) -->
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
    border-left: 2px solid var(--agent-color);
    padding: 10px 12px;
    border-bottom: 1px solid #111e2a;
    cursor: pointer;
    transition: background 0.15s;
  }
  .card:hover   { background: #0d1a26; }
  .card.selected{ background: #0d2030; }

  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 7px; }
  .name-row { display: flex; align-items: center; gap: 5px; }
  .dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .name { font-size: 13px; font-weight: bold; color: #e0f0ff; letter-spacing: 0.04em; }
  .type { font-size: 9px; color: #4a7a9a; letter-spacing: 0.08em; }
  .connected-badge {
    font-size: 8px; background: #004433; color: #00ff88;
    border: 1px solid #00ff8844; border-radius: 3px; padding: 1px 4px;
    letter-spacing: 0.05em;
  }
  .status { font-size: 9px; letter-spacing: 0.06em; font-weight: bold; }

  .metrics { display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }
  .metric  { display: flex; gap: 8px; font-size: 10px; }
  .mkey    { color: #4a7a9a; width: 28px; flex-shrink: 0; }
  .mval    { color: #c8d8e8; font-family: monospace; }

  .task {
    font-size: 10px;
    color: #8ab0c0;
    padding: 5px 7px;
    background: #0a1820;
    border-radius: 3px;
    border-left: 2px solid var(--agent-color);
    margin-bottom: 7px;
    line-height: 1.4;
  }

  .cot {
    background: #06101a;
    border-radius: 4px;
    padding: 7px 8px;
    margin-bottom: 7px;
  }
  .cot-title { font-size: 8px; color: #3a6a8a; letter-spacing: 0.1em; margin-bottom: 5px; }
  .cot-text  {
    font-size: 10px; color: #8ab8d0; font-family: monospace;
    white-space: pre-wrap; line-height: 1.5; max-height: 80px; overflow: hidden;
  }

  .controls { display: flex; gap: 5px; }
  .ctrl-btn {
    font-size: 9px; font-family: monospace; padding: 3px 8px; border-radius: 3px;
    border: 1px solid; cursor: pointer; letter-spacing: 0.04em; transition: opacity 0.15s;
    text-transform: uppercase;
  }
  .ctrl-btn:hover { opacity: 0.8; }
  .ctrl-btn.danger { background: #200a0a; border-color: #ff335555; color: #ff6677; }
  .ctrl-btn.ok     { background: #0a2010; border-color: #00ff8844; color: #00ff88; }
</style>
