<script>
  import { DemoRunner } from '../demo/DemoRunner.js'

  let runner = null
  let running = false
  let progress = ''

  async function startDemo() {
    if (running) return
    runner  = new DemoRunner()
    running = true
    progress = 'Connessione agenti...'

    try {
      await runner.start()
      progress = 'Demo in esecuzione...'

      // Poll running state to detect auto-stop
      const poll = setInterval(() => {
        if (!runner?.running) {
          clearInterval(poll)
          running  = false
          progress = 'Demo completata'
          setTimeout(() => (progress = ''), 3000)
          runner = null
        }
      }, 500)
    } catch (e) {
      progress = 'Errore: backend non raggiungibile'
      running = false
      runner  = null
    }
  }

  function stopDemo() {
    runner?.stop()
    runner   = null
    running  = false
    progress = ''
  }

  // Stop everything and restart from a clean state: stop any scripted demo and
  // reset the world model. Agents return to their spawn positions and the AI
  // control layer idles until a new mission is issued — i.e. a fresh simulation.
  let resetting = false
  async function resetAll() {
    runner?.stop()
    runner   = null
    running  = false
    resetting = true
    progress = 'Reset in corso...'
    try {
      await fetch('/api/reset', { method: 'POST' })
      progress = 'Reset completato: invia una missione per ripartire'
    } catch (e) {
      progress = 'Reset fallito: backend non raggiungibile'
    } finally {
      resetting = false
      setTimeout(() => (progress = ''), 3500)
    }
  }
</script>

<div class="demo-bar">
  {#if !running}
    <button class="btn start" on:click={startDemo}>
      ▶ Avvia demo
    </button>
  {:else}
    <button class="btn stop" on:click={stopDemo}>
      ■ Ferma demo
    </button>
  {/if}

  <button
    class="btn reset"
    on:click={resetAll}
    disabled={resetting}
    title="Ferma tutto e riavvia da uno stato pulito"
  >
    ⟲ Reset
  </button>

  {#if progress}
    <span class="progress">{progress}</span>
  {/if}

  {#if running}
    <span class="badge">DEMO</span>
  {/if}
</div>

<style>
  .demo-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid #1a2a3a;
    background: #07111f;
    flex-shrink: 0;
  }
  .btn {
    font-family: monospace;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 0.06em;
    padding: 7px 16px;
    border-radius: 5px;
    border: none;
    cursor: pointer;
    transition: opacity 0.15s;
    text-transform: uppercase;
  }
  .btn:hover { opacity: 0.82; }
  .start { background: #003344; color: #00d4ff; border: 1px solid #00d4ff66; }
  .stop  { background: #3a0808; color: #ff6677; border: 1px solid #ff335566; }
  .reset { background: #2a1c00; color: #ffaa33; border: 1px solid #ffaa3366; }
  .btn:disabled { opacity: 0.5; cursor: default; }

  .progress {
    font-size: 12px;
    color: #6a9ab0;
    font-family: monospace;
    flex: 1;
  }
  .badge {
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.1em;
    color: #ffaa00;
    background: #3a2200;
    border: 1px solid #ffaa0066;
    border-radius: 4px;
    padding: 2px 8px;
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.5; }
  }
</style>
