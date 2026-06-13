<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, agentColor, actionTag } from '../store/worldStore.js'

  export let agentLayerRef = null
  export let mapRef        = null

  let bubbles = []
  let raf

  const MAX_TEXT = 76

  function shortText(value, max = MAX_TEXT) {
    const text = (value ?? '').replace(/\s+/g, ' ').trim()
    if (text.length <= max) return text
    return text.slice(0, max - 1).trimEnd() + '…'
  }

  function usefulThought(cot) {
    return (cot ?? '')
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .filter(s => !s.toLowerCase().startsWith('new mission'))
      .at(-1)
  }

  function update() {
    raf = requestAnimationFrame(update)
    if (!agentLayerRef || !mapRef) return

    bubbles = ($worldState.agents ?? [])
      .map(a => {
        const pos = agentLayerRef.getScreenPos(a.id)
        if (!pos) return null
        const thought = usefulThought(a.cot_text)
        if (!thought && !a.current_task) return null
        return {
          agent: a,
          x: pos.x,
          y: pos.y,
          task: shortText(a.current_task || 'Awaiting orders', 54),
          thought: shortText(thought, 82),
          tag: actionTag(a.current_task),
        }
      })
      .filter(Boolean)
  }

  onMount(() => { raf = requestAnimationFrame(update) })
  onDestroy(() => cancelAnimationFrame(raf))
</script>

{#each bubbles as { agent, x, y, task, thought, tag } (agent.id)}
  {@const color = agentColor(agent.id)}
  <div class="bubble" style="left:{x}px; top:{y - 26}px; --clr:{color};">
    <div class="bhead">
      <span class="bname">{agent.name}</span>
      <span class="btag" style="--t:{tag.color}">{tag.label}</span>
    </div>

    <div class="btask">{task}</div>

    {#if thought}
      <div class="note">{thought}</div>
    {/if}

    <div class="tail"></div>
  </div>
{/each}

<style>
  .bubble {
    position: absolute;
    transform: translate(-50%, -100%);
    width: 220px;
    background: rgba(6, 12, 24, 0.94);
    border: 1px solid var(--clr, #00d4ff);
    border-radius: 6px;
    padding: 7px 10px 9px;
    pointer-events: none;
    z-index: 30;
    backdrop-filter: blur(5px);
    box-shadow: 0 0 16px var(--clr, #00d4ff)33;
  }

  .bhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }
  .bname {
    font-family: monospace;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 0.06em;
    color: var(--clr, #00d4ff);
  }
  .btag {
    font-family: monospace;
    font-size: 9.5px;
    font-weight: bold;
    letter-spacing: 0.08em;
    color: var(--t, #00d4ff);
    border: 1px solid var(--t, #00d4ff);
    border-radius: 3px;
    padding: 1px 6px;
    background: color-mix(in srgb, var(--t, #00d4ff) 14%, transparent);
    white-space: nowrap;
  }

  .btask {
    font-family: monospace;
    font-size: 11px;
    color: #cfe6f2;
    margin-bottom: 6px;
    line-height: 1.35;
    border-left: 2px solid var(--clr, #00d4ff);
    padding-left: 6px;
  }

  .note {
    border-top: 1px solid #16283a;
    padding-top: 6px;
    font-family: monospace;
    font-size: 11px;
    line-height: 1.35;
    color: #8fb5c8;
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
