<script>
  import { worldState } from '../store/worldStore.js'

  let text   = ''
  let status = ''

  async function submit(change = false) {
    if (!text.trim()) return
    const url = change ? '/api/mission/change' : '/api/mission'
    try {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (r.ok) {
        status = change ? 'Intento aggiornato' : 'Missione inviata'
        setTimeout(() => (status = ''), 3000)
      }
    } catch {
      status = '✕ Errore di connessione'
    }
  }

  $: missionStatus = $worldState.mission_status ?? ($worldState.mission ? 'active' : 'idle')
  $: missionResult = $worldState.mission_result ?? null
  $: missionLabel = missionStatus === 'completed' ? 'Completata' : 'Attiva'
  $: resultText = missionResult
    ? [
        missionResult.contact_id ? `target ${missionResult.contact_id}` : null,
        missionResult.completed_by_name ? `da ${missionResult.completed_by_name}` : null,
        missionResult.lat && missionResult.lon ? `${Number(missionResult.lat).toFixed(4)}N ${Number(missionResult.lon).toFixed(4)}E` : null,
      ].filter(Boolean).join(' · ')
    : ''

</script>

<div class="box">
  <div class="title">MISSIONE</div>

  {#if $worldState.mission}
    <div class="current" class:completed={missionStatus === 'completed'}>
      <span class="label">{missionLabel}</span>
      <span class="text">{$worldState.mission}</span>
      {#if missionStatus === 'completed' && resultText}
        <span class="result">{resultText}</span>
      {/if}
    </div>
  {/if}

  <textarea
    class="input"
    rows="3"
    placeholder="Scrivi un ordine per lo sciame..."
    bind:value={text}
  />

  <div class="actions">
    <button class="btn primary" on:click={() => submit(false)}>Avvia</button>
    <button class="btn warn"    on:click={() => submit(true)}>Aggiorna</button>
  </div>

  {#if status}
    <div class="status">{status}</div>
  {/if}
</div>

<style>
  .box {
    padding: 14px;
    border-bottom: 1px solid #1a2a3a;
  }
  .title {
    font-size: 11px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
    margin-bottom: 9px;
  }
  .current {
    font-size: 12px;
    color: #8ab0c0;
    margin-bottom: 9px;
    padding: 7px 10px;
    background: #0a1820;
    border-radius: 4px;
    border-left: 2px solid #00d4ff;
    line-height: 1.5;
    display: grid;
    gap: 3px;
  }
  .current.completed {
    border-left-color: #00ff88;
    background: #071c14;
  }
  .label { color: #4a7a9a; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
  .current.completed .label { color: #00ff88; }
  .text  {
    color: #c8d8e8;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .result {
    color: #8fd8b8;
    font-size: 11px;
    line-height: 1.35;
  }
  .input {
    width: 100%;
    background: #0a1420;
    border: 1px solid #1a3a5a;
    border-radius: 4px;
    color: #c8d8e8;
    font-family: monospace;
    font-size: 13px;
    padding: 8px 10px;
    resize: none;
    outline: none;
    line-height: 1.5;
    box-sizing: border-box;
  }
  .input:focus { border-color: #00d4ff55; }
  .input::placeholder { color: #3a5a7a; }
  .actions {
    display: flex;
    gap: 7px;
    margin-top: 8px;
  }
  .btn {
    flex: 1;
    padding: 7px;
    border: 1px solid transparent;
    border-radius: 4px;
    font-family: monospace;
    font-size: 12px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: opacity 0.15s;
    background: transparent;
  }
  .btn:hover { opacity: 0.85; }
  .primary { background: #004466; color: #00d4ff; border-color: #004466; }
  .warn    { background: #3a1a00; color: #ffaa00; border-color: #3a1a00; }

  .status {
    margin-top: 7px;
    font-size: 12px;
    color: #00ff88;
    text-align: center;
  }
</style>
