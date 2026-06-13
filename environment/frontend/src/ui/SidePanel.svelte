<script>
  import { worldState, wsStatus, selectedAgentId } from '../store/worldStore.js'
  import MissionBox   from './MissionBox.svelte'
  import AgentCard    from './AgentCard.svelte'
  import MessageLog   from './MessageLog.svelte'
  import DemoControls from './DemoControls.svelte'

  const STATUS_DOT = { connected: '#00ff88', disconnected: '#ff3355', reconnecting: '#ffaa00' }
</script>

<aside class="panel">
  <!-- Header -->
  <div class="header">
    <div class="brand">MARITIME SWARM</div>
    <div class="ws-status">
      <span class="ws-dot" style="background:{STATUS_DOT[$wsStatus] ?? '#888'}"></span>
      <span class="ws-label">{$wsStatus.toUpperCase()}</span>
    </div>
  </div>

  <!-- Demo controls -->
  <DemoControls />

  <!-- Mission -->
  <MissionBox />

  <!-- Agent cards -->
  <div class="agents-section">
    <div class="section-title">VEHICLES</div>
    {#each ($worldState.agents ?? []) as agent (agent.id)}
      <AgentCard
        {agent}
        selected={$selectedAgentId === agent.id}
        onSelect={() => selectedAgentId.set(
          $selectedAgentId === agent.id ? null : agent.id
        )}
      />
    {/each}
  </div>

  <!-- Message log -->
  <MessageLog />
</aside>

<style>
  .panel {
    width: 370px;
    flex-shrink: 0;
    background: #060c18;
    border-right: 1px solid #1a2a3a;
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    z-index: 20;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid #1a2a3a;
    flex-shrink: 0;
  }
  .brand {
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 0.15em;
    color: #00d4ff;
  }
  .ws-status { display: flex; align-items: center; gap: 6px; }
  .ws-dot    { width: 8px; height: 8px; border-radius: 50%; }
  .ws-label  { font-size: 11px; letter-spacing: 0.1em; color: #4a7a9a; }

  .agents-section {
    flex-shrink: 0;
    max-height: 48vh;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #1a3a5a transparent;
  }
  .section-title {
    font-size: 11px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
    padding: 11px 14px 7px;
    border-bottom: 1px solid #111e2a;
  }
</style>
