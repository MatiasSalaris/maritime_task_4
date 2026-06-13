<script>
  import { DemoRunner } from '../demo/DemoRunner.js'

  let runner = null
  let running = false
  let progress = ''

  async function startDemo() {
    if (running) return
    runner  = new DemoRunner()
    running = true
    progress = 'Connecting agents…'

    try {
      await runner.start()
      progress = 'Demo running…'

      // Poll running state to detect auto-stop
      const poll = setInterval(() => {
        if (!runner?.running) {
          clearInterval(poll)
          running  = false
          progress = 'Demo complete'
          setTimeout(() => (progress = ''), 3000)
          runner = null
        }
      }, 500)
    } catch (e) {
      progress = 'Error: backend not reachable'
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
</script>

<div class="demo-bar">
  {#if !running}
    <button class="btn start" on:click={startDemo}>
      ▶ Start Demo
    </button>
  {:else}
    <button class="btn stop" on:click={stopDemo}>
      ■ Stop Demo
    </button>
  {/if}

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
