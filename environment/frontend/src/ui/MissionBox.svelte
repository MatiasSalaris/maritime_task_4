<script>
  import { worldState } from '../store/worldStore.js'

  let text = ''
  let changing = false
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
        status = change ? '⚡ Intent changed' : '✓ Mission set'
        setTimeout(() => (status = ''), 3000)
      }
    } catch {
      status = '✕ Error'
    }
  }
</script>

<div class="box">
  <div class="title">MISSION INTENT</div>

  {#if $worldState.mission}
    <div class="current">
      <span class="label">ACTIVE:</span>
      <span class="text">{$worldState.mission}</span>
    </div>
  {/if}

  <textarea
    class="input"
    rows="3"
    placeholder="Type mission in plain English…"
    bind:value={text}
  />

  <div class="actions">
    <button class="btn primary" on:click={() => submit(false)}>
      Submit
    </button>
    <button class="btn warn" on:click={() => submit(true)}>
      Change Intent
    </button>
  </div>

  {#if status}
    <div class="status">{status}</div>
  {/if}
</div>

<style>
  .box {
    padding: 12px;
    border-bottom: 1px solid #1a2a3a;
  }
  .title {
    font-size: 9px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
    margin-bottom: 8px;
  }
  .current {
    font-size: 10px;
    color: #8ab0c0;
    margin-bottom: 8px;
    padding: 6px 8px;
    background: #0a1820;
    border-radius: 4px;
    border-left: 2px solid #00d4ff;
    line-height: 1.4;
  }
  .label { color: #4a7a9a; margin-right: 4px; }
  .text  { color: #c8d8e8; }
  .input {
    width: 100%;
    background: #0a1420;
    border: 1px solid #1a3a5a;
    border-radius: 4px;
    color: #c8d8e8;
    font-family: monospace;
    font-size: 11px;
    padding: 7px 9px;
    resize: none;
    outline: none;
    line-height: 1.5;
  }
  .input:focus { border-color: #00d4ff55; }
  .input::placeholder { color: #3a5a7a; }
  .actions {
    display: flex;
    gap: 6px;
    margin-top: 7px;
  }
  .btn {
    flex: 1;
    padding: 6px;
    border: none;
    border-radius: 4px;
    font-family: monospace;
    font-size: 10px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.85; }
  .primary { background: #004466; color: #00d4ff; }
  .warn    { background: #3a1a00; color: #ffaa00; }
  .status {
    margin-top: 6px;
    font-size: 10px;
    color: #00ff88;
    text-align: center;
  }
</style>
