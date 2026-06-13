<script>
  import { godView } from '../store/worldStore.js'

  export let onModeChange  = (_mode) => {}   // 'rect' | 'circle' | 'poly' | null
  export let onClearArea   = () => {}
  export let onGridToggle  = () => {}
  export let activeMode    = null
  export let gridEnabled   = false
  export let hasArea       = false

  const TOOL_BTNS = [
    { id: 'rect',   label: '▭',  title: 'AOR rettangolare' },
    { id: 'circle', label: '◯',  title: 'AOR circolare' },
    { id: 'poly',   label: '⬡',  title: 'AOR poligonale: clic sui punti, doppio clic per chiudere' },
  ]

  function toggleMode(id) {
    onModeChange(activeMode === id ? null : id)
  }

  async function transmitAOR() {
    // Signal to parent that AOR should be sent to backend
    onModeChange('__transmit__')
  }

  function toggleGodView() {
    godView.update(v => !v)
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
    <button class="tool-btn clear" title="Cancella AOR" on:click={onClearArea}>✕</button>
  {/if}

  <div class="divider"></div>

  <div class="group-label">BOA</div>
  <button
    class="tool-btn buoy"
    class:active={activeMode === 'buoy'}
    title="Sposta la boa: clicca sulla mappa"
    on:click={() => toggleMode('buoy')}
  >◆</button>

  <div class="divider"></div>

  <div class="group-label">MAPPA</div>
  <button
    class="tool-btn"
    class:active={gridEnabled}
    title="Mostra/nascondi griglia MGRS"
    on:click={onGridToggle}
  >⊞</button>

  <div class="divider"></div>

  <div class="group-label">VISTA</div>
  <button
    class="tool-btn god-btn"
    class:god-active={$godView}
    title="Mostra/nascondi vista completa: rivela i contatti non rilevati"
    on:click={toggleGodView}
  >⊙</button>

  {#if activeMode && activeMode !== '__transmit__'}
    <div class="draw-hint">
      {#if activeMode === 'rect'}Clic e trascina per disegnare il riquadro{/if}
      {#if activeMode === 'circle'}Clic sul centro e trascina il raggio{/if}
      {#if activeMode === 'poly'}Clic sui punti, doppio clic per chiudere, ESC annulla{/if}
      {#if activeMode === 'buoy'}Clic sulla mappa per posizionare la boa{/if}
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
  .tool-btn.buoy { color: #ffd84a; border-color: #ffd84a55; font-size: 13px; }

  .god-btn { font-size: 16px; }
  .god-btn.god-active {
    background: #001a2a;
    border-color: #00aaff;
    color: #00d4ff;
    box-shadow: 0 0 8px rgba(0, 212, 255, 0.4);
  }

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
