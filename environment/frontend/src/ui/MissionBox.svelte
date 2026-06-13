<script>
  import { worldState } from '../store/worldStore.js'

  // ── NATO operational doctrine profiles ────────────────────────────────────
  const DOCTRINES = [
    {
      code: 'PHASE0',
      label: 'Phase 0 — Shape',
      sublabel: 'FPCON NORMAL · Peacetime',
      color: '#00aa44',
      roe: 'Observe & report only. No engagement. Maintain safe intercept distance.',
    },
    {
      code: 'PHASE1',
      label: 'Phase 1 — Deter',
      sublabel: 'FPCON ALPHA · Heightened',
      color: '#88cc00',
      roe: 'Challenge & track. Non-lethal deterrence authorized. Self-defence rules apply.',
    },
    {
      code: 'MSO',
      label: 'Maritime Security Ops',
      sublabel: 'FPCON BRAVO · MSO / UNSCR',
      color: '#cc8800',
      roe: 'Intercept, challenge, board authorized. Log all contacts. Proportional force.',
    },
    {
      code: 'PHASE2',
      label: 'Phase 2 — Seize Initiative',
      sublabel: 'FPCON CHARLIE · Limited Combat',
      color: '#cc4400',
      roe: 'Proportional response authorized. Brief commander before escalation. Hostile intent = hostile act.',
    },
    {
      code: 'PHASE3',
      label: 'Phase 3 — Dominate',
      sublabel: 'FPCON DELTA · Full Combat Ops',
      color: '#cc0000',
      roe: 'Weapons free in AO per OPORD ROE Annex. All hostile contacts may be engaged.',
    },
  ]

  let text         = ''
  let status       = ''
  let selectedCode = 'PHASE0'
  let showDocRoe   = false

  $: activeDoctrine = DOCTRINES.find(d => d.code === selectedCode) ?? DOCTRINES[0]
  $: currentDoctrine = DOCTRINES.find(d => d.code === $worldState.doctrine) ?? null

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
      status = '✕ Connection error'
    }
  }

  async function applyDoctrine() {
    try {
      const r = await fetch('/api/doctrine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: selectedCode }),
      })
      if (r.ok) {
        status = `✓ Doctrine: ${activeDoctrine.label}`
        setTimeout(() => (status = ''), 3000)
      }
    } catch {
      status = '✕ Connection error'
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
    <button class="btn primary" on:click={() => submit(false)}>Submit</button>
    <button class="btn warn"    on:click={() => submit(true)}>Change Intent</button>
  </div>

  <!-- ── NATO Doctrine / ROE ─────────────────────────────────────────────── -->
  <div class="doctrine-section">
    <div class="doctrine-title">NATO DOCTRINE / ROE</div>

    {#if currentDoctrine}
      <div class="doctrine-active" style="border-left-color:{currentDoctrine.color}">
        <span class="doctrine-badge" style="color:{currentDoctrine.color}">
          ● {currentDoctrine.code}
        </span>
        <span class="doctrine-name">{currentDoctrine.label}</span>
      </div>
    {/if}

    <select class="doctrine-select" bind:value={selectedCode}>
      {#each DOCTRINES as d}
        <option value={d.code}>{d.label}</option>
      {/each}
    </select>

    <div class="doctrine-meta" style="border-left-color:{activeDoctrine.color}40">
      <div class="doctrine-sublabel" style="color:{activeDoctrine.color}">{activeDoctrine.sublabel}</div>
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="roe-row" on:click={() => showDocRoe = !showDocRoe}>
        <span class="roe-label">ROE</span>
        <span class="roe-toggle">{showDocRoe ? '▲' : '▼'}</span>
      </div>
      {#if showDocRoe}
        <div class="roe-text">{activeDoctrine.roe}</div>
      {/if}
    </div>

    <button class="btn doctrine-btn" style="border-color:{activeDoctrine.color}55;color:{activeDoctrine.color}"
            on:click={applyDoctrine}>
      Apply to Fleet
    </button>
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
  }
  .label { color: #4a7a9a; margin-right: 5px; }
  .text  { color: #c8d8e8; }
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

  /* ── Doctrine section ────────────────────────────────────────────────────── */
  .doctrine-section {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid #0f1e2a;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .doctrine-title {
    font-size: 10px;
    letter-spacing: 0.12em;
    color: #3a6a8a;
    margin-bottom: 2px;
  }
  .doctrine-active {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    background: #060e18;
    border-left: 2px solid #888;
    border-radius: 3px;
    font-size: 11px;
  }
  .doctrine-badge { font-weight: bold; letter-spacing: 0.05em; }
  .doctrine-name  { color: #8ab0c0; }

  .doctrine-select {
    width: 100%;
    background: #0a1420;
    border: 1px solid #1a3a5a;
    border-radius: 4px;
    color: #c8d8e8;
    font-family: monospace;
    font-size: 12px;
    padding: 6px 8px;
    cursor: pointer;
    outline: none;
  }
  .doctrine-select:focus { border-color: #00d4ff44; }
  .doctrine-select option { background: #0a1420; color: #c8d8e8; }

  .doctrine-meta {
    background: #060e18;
    border-left: 2px solid #1a3a5a;
    border-radius: 3px;
    padding: 6px 8px;
    font-size: 11px;
  }
  .doctrine-sublabel { font-weight: bold; letter-spacing: 0.04em; margin-bottom: 4px; }
  .roe-row {
    display: flex;
    justify-content: space-between;
    cursor: pointer;
    color: #4a7a9a;
    font-size: 10px;
    letter-spacing: 0.08em;
    user-select: none;
  }
  .roe-toggle { color: #4a7a9a; }
  .roe-text {
    margin-top: 5px;
    color: #8ab0c0;
    line-height: 1.55;
    font-size: 11px;
    font-style: italic;
  }

  .doctrine-btn {
    flex: none;
    padding: 6px;
    font-size: 11px;
  }

  .status {
    margin-top: 7px;
    font-size: 12px;
    color: #00ff88;
    text-align: center;
  }
</style>
