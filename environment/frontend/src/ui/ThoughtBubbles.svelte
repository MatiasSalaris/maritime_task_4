<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, agentColor } from '../store/worldStore.js'

  export let agentLayerRef = null   // AgentLayer instance for getScreenPos()
  export let mapRef = null          // MapManager instance

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
  {@const lines = (agent.cot_text ?? '').split('\n').slice(-4).join('\n')}
  <div
    class="bubble"
    style="left:{x}px; top:{y - 20}px; --clr:{color};"
  >
    <div class="cot">{lines}</div>
    <div class="tail"></div>
  </div>
{/each}

<style>
  .bubble {
    position: absolute;
    transform: translate(-50%, -100%);
    max-width: 220px;
    background: rgba(6, 12, 24, 0.92);
    border: 1px solid var(--clr, #00d4ff);
    border-radius: 6px;
    padding: 6px 9px;
    pointer-events: none;
    z-index: 30;
    backdrop-filter: blur(4px);
    box-shadow: 0 0 12px var(--clr, #00d4ff)33;
  }
  .cot {
    font-family: monospace;
    font-size: 9.5px;
    color: #b0d8e8;
    white-space: pre-wrap;
    line-height: 1.45;
    max-height: 72px;
    overflow: hidden;
  }
  .tail {
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid var(--clr, #00d4ff);
  }
</style>
