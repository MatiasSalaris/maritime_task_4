<script>
  const SPEEDS = [0.5, 1, 2, 4]
  let scale = 1

  async function setSpeed(s) {
    scale = s
    try {
      await fetch('/api/speed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scale: s }),
      })
    } catch (e) {
      console.error('[speed] failed:', e)
    }
  }
</script>

<div class="speed">
  <span class="label">SPEED</span>
  {#each SPEEDS as s}
    <button class:active={scale === s} on:click={() => setSpeed(s)}>{s}×</button>
  {/each}
</div>

<style>
  .speed {
    display: flex;
    align-items: center;
    gap: 4px;
    background: rgba(6, 12, 24, 0.85);
    border: 1px solid #1a2a3a;
    border-radius: 6px;
    padding: 5px 8px;
    font-family: monospace;
  }
  .label {
    font-size: 10px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
    margin-right: 4px;
  }
  button {
    background: transparent;
    border: 1px solid #1a3a5a;
    color: #8ab0c0;
    font-family: monospace;
    font-size: 12px;
    padding: 3px 8px;
    border-radius: 3px;
    cursor: pointer;
    transition: all 0.15s;
  }
  button:hover { border-color: #00d4ff; color: #00d4ff; }
  button.active {
    background: #0d2030;
    border-color: #00d4ff;
    color: #00d4ff;
    font-weight: bold;
  }
</style>
