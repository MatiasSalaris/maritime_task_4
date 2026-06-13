<script>
  export let onModeChange  = (_mode) => {}   // 'rect' | 'circle' | 'poly' | null
  export let onClearArea   = () => {}
  export let onGridToggle  = () => {}
  export let activeMode    = null
  export let gridEnabled   = false
  export let hasArea       = false

  const TOOL_BTNS = [
    { id: 'rect',   label: '▭',  title: 'Rectangle AOR' },
    { id: 'circle', label: '◯',  title: 'Circle AOR' },
    { id: 'poly',   label: '⬡',  title: 'Polygon AOR (click pts, dbl-click close)' },
  ]

  function toggleMode(id) {
    onModeChange(activeMode === id ? null : id)
  }

  async function transmitAOR() {
    // Signal to parent that AOR should be sent to backend
    onModeChange('__transmit__')
  }
</script>

<div class="tools">
  <div class="group-label">AOR</div>

  {#each TOOL_BTNS as btn}
    <button
      class="tool-btn"
      class:active={activeMode === btn.id}
      title={btn.title}
      on:click={() => toggleMode(btn.id)}
    >{btn.label}</button>
  {/each}

  {#if hasArea}
    <button class="tool-btn clear" title="Clear AOR" on:click={onClearArea}>✕</button>
  {/if}

  <div class="divider"></div>

  <div class="group-label">MAP</div>
  <button
    class="tool-btn"
    class:active={gridEnabled}
    title="Toggle MGRS grid"
    on:click={onGridToggle}
  >⊞</button>

  {#if activeMode && activeMode !== '__transmit__'}
    <div class="draw-hint">
      {#if activeMode === 'rect'}Click & drag to draw box{/if}
      {#if activeMode === 'circle'}Click center · drag radius{/if}
      {#if activeMode === 'poly'}Click pts · dbl-click close · ESC cancel{/if}
    </div>
  {/if}
</div>

<style>
  .tools {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    background: rgba(6,12,24,0.90);
    border: 1px solid #1a2a3a;
    border-radius: 8px;
    padding: 8px 6px;
    backdrop-filter: blur(8px);
    width: 40px;
  }

  .group-label {
    font-size: 8px;
    letter-spacing: 0.1em;
    color: #3a6a8a;
    text-transform: uppercase;
    margin-bottom: 2px;
  }

  .divider {
    width: 24px;
    height: 1px;
    background: #1a2a3a;
    margin: 4px 0;
  }

  .tool-btn {
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid #1a3a4a;
    border-radius: 5px;
    color: #8ab0c0;
    font-size: 15px;
    cursor: pointer;
    transition: all 0.15s;
    padding: 0;
  }
  .tool-btn:hover  { background: #0d2030; color: #c8d8e8; }
  .tool-btn.active { background: #0d2a3a; border-color: #00d4ff; color: #00d4ff; }
  .tool-btn.clear  { border-color: #ff335544; color: #ff6677; font-size: 12px; }
  .tool-btn.clear:hover { background: #200a0a; }

  .draw-hint {
    position: absolute;
    left: 52px;
    top: 0;
    white-space: nowrap;
    background: rgba(6,12,24,0.92);
    border: 1px solid #1a3a5a;
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 11px;
    color: #00d4ff;
    letter-spacing: 0.04em;
    pointer-events: none;
  }
</style>
