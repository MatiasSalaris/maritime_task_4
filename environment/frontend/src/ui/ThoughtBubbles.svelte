<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, agentColor } from '../store/worldStore.js'

  export let agentLayerRef = null
  export let mapRef        = null

  let bubbles = []
  let raf

  function update() {
    raf = requestAnimationFrame(update)
    if (!agentLayerRef || !mapRef) return

    bubbles = ($worldState.agents ?? [])
      .filter(a => a.cot_text)
      .map(a => {
        const pos = agentLayerRef.getScreenPos(a.id)
        return pos ? { agent: a, x: pos.x, y: pos.y } : null
      })
      .filter(Boolean)
  }

  onMount(() => { raf = requestAnimationFrame(update) })
  onDestroy(() => cancelAnimationFrame(raf))
</script>

{#each bubbles as { agent, x, y } (agent.id)}
  {@const color = agentColor(agent.id)}
  {@const lines = (agent.cot_text ?? '').split('\n').slice(-5).join('\n')}
  <div class="bubble" style="left:{x}px; top:{y - 22}px; --clr:{color};">
    <div class="cot">{lines}</div>
    <div class="tail"></div>
  </div>
{/each}

<style>
  .bubble {
    position: absolute;
    transform: translate(-50%, -100%);
    max-width: 260px;
    min-width: 160px;
    background: rgba(6, 12, 24, 0.93);
    border: 1px solid var(--clr, #00d4ff);
    border-radius: 7px;
    padding: 8px 11px;
    pointer-events: none;
    z-index: 30;
    backdrop-filter: blur(5px);
    box-shadow: 0 0 16px var(--clr, #00d4ff)33;
  }
  .cot {
    font-family: monospace;
    font-size: 12px;
    color: #b0d8e8;
    white-space: pre-wrap;
    line-height: 1.5;
    max-height: 90px;
    overflow: hidden;
  }
  .tail {
    position: absolute;
    bottom: -7px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 6px solid transparent;
    border-right: 6px solid transparent;
    border-top: 7px solid var(--clr, #00d4ff);
  }
</style>
