<script>
  import { worldState, agentColor } from '../store/worldStore.js'
  import { afterUpdate } from 'svelte'

  let el

  afterUpdate(() => {
    if (el) el.scrollTop = el.scrollHeight
  })

  const TYPE_ICON = {
    proposal: '◆',
    ack:      '✓',
    objection:'✕',
    handoff:  '→',
    status:   '●',
  }
  const TYPE_COLOR = {
    proposal: '#00d4ff',
    ack:      '#00ff88',
    objection:'#ff3355',
    handoff:  '#ffaa00',
    status:   '#666',
  }

  function agentName(id) {
    const a = $worldState.agents?.find(a => a.id === id)
    return a?.name ?? id
  }

  function ts(unix) {
    if (!unix) return ''
    const d = new Date(unix * 1000)
    return d.toTimeString().slice(0, 8)
  }
</script>

<div class="log-section">
  <div class="title">MESSAGE LOG</div>
  <div class="log" bind:this={el}>
    {#each ($worldState.message_log ?? []) as msg (msg.id)}
      <div class="entry">
        <span class="ts">{ts(msg.sent_at)}</span>
        <span class="icon" style="color:{TYPE_COLOR[msg.msg_type] ?? '#888'}">
          {TYPE_ICON[msg.msg_type] ?? '?'}
        </span>
        <span class="from" style="color:{agentColor(msg.from_agent)}">{agentName(msg.from_agent)}</span>
        <span class="arrow">→</span>
        <span class="to"   style="color:{agentColor(msg.to_agent)}">{agentName(msg.to_agent)}</span>
        <span class="type" style="color:{TYPE_COLOR[msg.msg_type] ?? '#888'}">{msg.msg_type}</span>
      </div>
      {#if msg.reasoning}
        <div class="reasoning">{msg.reasoning}</div>
      {/if}
    {/each}
    {#if !($worldState.message_log?.length)}
      <div class="empty">Awaiting messages…</div>
    {/if}
  </div>
</div>

<style>
  .log-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding-top: 10px;
  }
  .title {
    font-size: 11px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
    padding: 0 14px 7px 14px;
    flex-shrink: 0;
  }
  .log {
    flex: 1;
    overflow-y: auto;
    padding: 0 14px 14px 14px;
    scrollbar-width: thin;
    scrollbar-color: #1a3a5a transparent;
  }
  .entry {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    padding: 4px 0;
    border-bottom: 1px solid #0d1820;
    flex-wrap: wrap;
  }
  .ts     { color: #3a5a7a; font-family: monospace; flex-shrink: 0; font-size: 11px; }
  .icon   { font-size: 11px; flex-shrink: 0; }
  .from, .to { font-weight: bold; }
  .arrow  { color: #3a5a7a; }
  .type   { font-size: 10px; letter-spacing: 0.05em; margin-left: auto; }
  .reasoning {
    font-size: 11px;
    color: #6a9ab0;
    font-family: monospace;
    padding: 3px 8px 5px 8px;
    line-height: 1.45;
    border-left: 2px solid #1a3a5a;
    margin-left: 14px;
    margin-bottom: 2px;
  }
  .empty { font-size: 13px; color: #3a5a7a; text-align: center; padding: 24px; }
</style>
