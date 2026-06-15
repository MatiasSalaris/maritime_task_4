<script>
  import { onMount } from 'svelte'

  export let onSelect = () => {}   // (scenario) => void
  export let onClose  = null       // if set, shows a close button

  let scenarios = []
  let loading = true
  let busy = null   // id being loaded

  onMount(async () => {
    try {
      const r = await fetch('/api/scenarios')
      scenarios = (await r.json()).scenarios ?? []
    } catch (e) {
      console.error('[scenarios] load failed', e)
    } finally {
      loading = false
    }
  })

  async function pick(s) {
    busy = s.id
    try {
      await fetch('/api/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: s.id }),
      })
      onSelect(s)
    } catch (e) {
      console.error('[scenarios] select failed', e)
    } finally {
      busy = null
    }
  }
</script>

<div class="backdrop">
  <div class="panel">
    <div class="head">
      <div class="title">SELECT SCENARIO</div>
      {#if onClose}
        <button class="close" on:click={onClose}>✕</button>
      {/if}
    </div>
    <div class="sub">Pick a tactical picture. The lead asset is briefed with the scenario's mission.</div>

    {#if loading}
      <div class="empty">Loading scenarios…</div>
    {:else}
      <div class="grid">
        {#each scenarios as s (s.id)}
          <button class="card" class:busy={busy === s.id} on:click={() => pick(s)} disabled={busy}>
            <div class="tag">{s.tag}</div>
            <div class="name">{s.name}</div>
            <div class="blurb">{s.blurb}</div>
            <div class="mission">“{s.mission}”</div>
            {#if busy === s.id}<div class="loading-tag">Launching…</div>{/if}
          </button>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: absolute;
    inset: 0;
    background: rgba(3, 7, 14, 0.86);
    backdrop-filter: blur(4px);
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Courier New', monospace;
  }
  .panel {
    width: min(880px, 92vw);
    max-height: 88vh;
    overflow-y: auto;
    background: #060c18;
    border: 1px solid #1a3a5a;
    border-radius: 10px;
    padding: 20px 22px;
    box-shadow: 0 0 40px rgba(0, 212, 255, 0.15);
  }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .title { font-size: 16px; font-weight: bold; letter-spacing: 0.18em; color: #00d4ff; }
  .close {
    background: transparent; border: 1px solid #2a4a5a; color: #8ab0c0;
    border-radius: 4px; padding: 3px 9px; cursor: pointer; font-family: monospace;
  }
  .close:hover { border-color: #00d4ff; color: #00d4ff; }
  .sub { font-size: 12px; color: #4a7a9a; margin: 6px 0 16px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .card {
    text-align: left;
    background: #0a1422;
    border: 1px solid #1a2a3a;
    border-left: 3px solid #00d4ff;
    border-radius: 6px;
    padding: 12px 14px;
    cursor: pointer;
    transition: all 0.15s;
    color: #c8d8e8;
  }
  .card:hover { background: #0d2030; border-color: #00d4ff; }
  .card:disabled { opacity: 0.5; cursor: default; }
  .tag {
    font-size: 9.5px; letter-spacing: 0.12em; color: #00d4ff;
    border: 1px solid #00d4ff55; border-radius: 3px; padding: 1px 6px;
    display: inline-block; margin-bottom: 6px;
  }
  .name { font-size: 14px; font-weight: bold; color: #e0f0ff; margin-bottom: 5px; }
  .blurb { font-size: 12px; color: #8ab0c0; line-height: 1.4; margin-bottom: 6px; }
  .mission { font-size: 11px; color: #5f8296; font-style: italic; line-height: 1.4; }
  .loading-tag { font-size: 11px; color: #00ff88; margin-top: 6px; }
  .empty { font-size: 13px; color: #4a7a9a; text-align: center; padding: 30px; }
</style>
