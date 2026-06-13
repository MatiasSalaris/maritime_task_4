<script>
  import { agentColor, actionTag, worldState } from '../store/worldStore.js'

  export let agent
  export let selected = false
  export let onSelect = () => {}

  const MSG_ICON  = { proposal: '◆', ack: '✓', objection: '✕', handoff: '→', report: '⚑', status: '●' }
  const MSG_COLOR = { proposal: '#00d4ff', ack: '#00ff88', objection: '#ff3355', handoff: '#ffaa00', report: '#ff8800', status: '#6a8a9a' }

  function agentName(id) {
    if (id === 'all') return 'ALL'
    return $worldState.agents?.find(a => a.id === id)?.name ?? id
  }

  function shortText(value, max = 110) {
    const text = (value ?? '').replace(/\s+/g, ' ').trim()
    if (text.length <= max) return text
    return text.slice(0, max - 1).trimEnd() + '…'
  }

  function usefulThought(cot) {
    return (cot ?? '')
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .filter(s => !s.toLowerCase().startsWith('new mission'))
      .at(-1)
  }

  $: comms = selected
    ? ($worldState.message_log ?? [])
        .filter(m => m.msg_type !== 'status' &&
                     (m.from_agent === agent.id || m.to_agent === agent.id || m.to_agent === 'all'))
        .slice(-4)
    : []

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
  $: tag        = actionTag(agent.current_task)
  $: typeMeta   = TYPE_META[(agent.type ?? '').toUpperCase()] ?? TYPE_META.USV
  $: taskText   = shortText(agent.current_task ?? 'Awaiting orders', 86)
  $: noteText   = shortText(usefulThought(agent.cot_text), 130)

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
      <span class="mkey">HDG</span>
      <span class="mval">{fmt(agent.heading)}°</span>
    </div>
    <div class="metric">
      <span class="mkey">SPD</span>
      <span class="mval">{fmt(agent.speed_kn)} kn</span>
    </div>
  </div>

  <div class="action-row">
    <span class="action-tag" style="--t:{tag.color}">{tag.label}</span>
    <span class="action-task">{taskText}</span>
  </div>

  {#if selected && noteText}
    <div class="note">
      <div class="detail-title">Latest reasoning</div>
      <div class="note-text">{noteText}</div>
    </div>
  {/if}

  {#if selected}
    <div class="comms">
      <div class="detail-title">Recent messages</div>
      {#if comms.length}
        <div class="comms-list">
          {#each comms as m (m.id)}
            <div class="cmsg">
              <span class="cdir">{m.from_agent === agent.id ? '▶ sent' : '◀ recv'}</span>
              <span class="cicon" style="color:{MSG_COLOR[m.msg_type] ?? '#888'}">{MSG_ICON[m.msg_type] ?? '?'}</span>
              <span class="cpeer">{m.from_agent === agent.id ? agentName(m.to_agent) : agentName(m.from_agent)}</span>
              <span class="ctype" style="color:{MSG_COLOR[m.msg_type] ?? '#888'}">{m.msg_type}</span>
              {#if m.reasoning}<div class="ctext">{shortText(m.reasoning, 120)}</div>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <div class="comms-empty">No messages yet.</div>
      {/if}
    </div>
  {/if}

  {#if selected}
    <div class="details">
      <span>{fmt(agent.position?.lat)}°N</span>
      <span>{fmt(agent.position?.lon)}°E</span>
    </div>

    <div class="controls">
      {#if agent.status !== 'silent'}
        <button class="ctrl-btn danger" title="Simulate comms loss"
                on:click|stopPropagation={() => forceStatus('silent')}>
          Disconnect
        </button>
      {:else}
        <button class="ctrl-btn ok"
                on:click|stopPropagation={() => forceStatus('operational')}>
          Reconnect
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .card {
    border-left: 3px solid var(--agent-color);
    padding: 10px 14px;
    border-bottom: 1px solid #111e2a;
    cursor: pointer;
    transition: background 0.15s;
  }
  .card:hover    { background: #0d1a26; }
  .card.selected { background: #0d2030; }

  .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 7px; }
  .name-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .dot  { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .name { font-size: 15px; font-weight: bold; color: #e0f0ff; letter-spacing: 0.02em; }
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

  .metrics { display: flex; gap: 16px; margin-bottom: 8px; }
  .metric  { display: flex; gap: 10px; font-size: 12px; }
  .mkey    { color: #4a7a9a; width: 32px; flex-shrink: 0; }
  .mval    { color: #c8d8e8; font-family: monospace; }

  .action-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .action-tag {
    font-size: 10px; font-weight: bold; letter-spacing: 0.08em;
    color: var(--t, #00d4ff);
    border: 1px solid var(--t, #00d4ff);
    border-radius: 3px; padding: 2px 7px;
    background: color-mix(in srgb, var(--t, #00d4ff) 14%, transparent);
    white-space: nowrap; flex-shrink: 0;
  }
  .action-task {
    font-size: 12px; color: #b6d4e4; font-family: monospace;
    line-height: 1.35;
  }

  .note {
    background: #06101a;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 8px;
  }
  .detail-title { font-size: 10px; color: #3a6a8a; letter-spacing: 0.08em; margin-bottom: 5px; text-transform: uppercase; }
  .note-text { font-size: 12px; color: #b8dcec; font-family: monospace; line-height: 1.45; }

  .comms { background: #06101a; border-radius: 4px; padding: 8px 10px; margin-bottom: 8px; }
  .comms-list { display: flex; flex-direction: column; gap: 5px; max-height: 118px; overflow-y: auto;
                scrollbar-width: thin; scrollbar-color: #1a3a5a transparent; }
  .cmsg { font-family: monospace; font-size: 11px; line-height: 1.35; }
  .cdir  { color: #4a7a9a; }
  .cicon { margin: 0 4px; }
  .cpeer { color: #c8d8e8; font-weight: bold; }
  .ctype { color: #6a8a9a; margin-left: 5px; }
  .ctext { color: #9fc0d0; padding: 1px 0 2px 10px; border-left: 2px solid #15303f; margin-top: 2px;
           white-space: pre-wrap; }
  .comms-empty { font-size: 11px; color: #3a5a7a; }

  .details {
    display: flex;
    gap: 12px;
    color: #6d92a6;
    font-family: monospace;
    font-size: 11px;
    margin-bottom: 8px;
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
