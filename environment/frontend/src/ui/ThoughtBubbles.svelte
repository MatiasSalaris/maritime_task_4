<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, agentColor, actionTag } from '../store/worldStore.js'

  export let agentLayerRef = null
  export let mapRef        = null

  let bubbles = []
  let raf
  let collapsed = {}   // agent_id -> true when its bubble's CoT is collapsed

  function toggle(id) {
    collapsed = { ...collapsed, [id]: !collapsed[id] }
  }

  // How many recent thoughts to show in the floating bubble (the side-panel
  // AgentCard shows the full, scrollable chain).
  const MAX_LINES = 4

  function update() {
    raf = requestAnimationFrame(update)
    if (!agentLayerRef || !mapRef) return

    bubbles = ($worldState.agents ?? [])
      .map(a => {
        const pos = agentLayerRef.getScreenPos(a.id)
        if (!pos) return null
        const thoughts = (a.cot_text ?? '')
          .split('\n')
          .map(s => s.trim())
          .filter(Boolean)
          .slice(-MAX_LINES)
        if (!thoughts.length && !a.current_task) return null
        return { agent: a, x: pos.x, y: pos.y, thoughts, tag: actionTag(a.current_task) }
      })
      .filter(Boolean)
  }

  onMount(() => { raf = requestAnimationFrame(update) })
  onDestroy(() => cancelAnimationFrame(raf))
</script>

{#each bubbles as { agent, x, y, thoughts, tag } (agent.id)}
  {@const color = agentColor(agent.id)}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="bubble" class:collapsed={collapsed[agent.id]}
       style="left:{x}px; top:{y - 26}px; --clr:{color};"
       on:click={() => toggle(agent.id)}
       title={collapsed[agent.id] ? 'Click to expand reasoning' : 'Click to collapse reasoning'}>
    <div class="bhead">
      <span class="caret">{collapsed[agent.id] ? '▸' : '▾'}</span>
      <span class="bname">{agent.name}</span>
      <span class="btag" style="--t:{tag.color}">{tag.label}</span>
    </div>

    {#if !collapsed[agent.id]}
      {#if agent.current_task}
        <div class="btask">{agent.current_task}</div>
      {/if}

      {#if thoughts.length}
        <div class="cot">
          {#each thoughts as line, i}
            <div class="cot-line" class:latest={i === thoughts.length - 1}>{line}</div>
          {/each}
        </div>
      {/if}
    {/if}

    <div class="tail"></div>
  </div>
{/each}

<style>
  .bubble {
    position: absolute;
    transform: translate(-50%, -100%);
    max-width: 300px;
    min-width: 184px;
    background: rgba(6, 12, 24, 0.94);
    border: 1px solid var(--clr, #00d4ff);
    border-radius: 8px;
    padding: 7px 10px 9px;
    pointer-events: auto;
    cursor: pointer;
    z-index: 30;
    backdrop-filter: blur(5px);
    box-shadow: 0 0 16px var(--clr, #00d4ff)33;
  }

  .bubble.collapsed { min-width: 0; }

  .bhead {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 5px;
  }
  .caret {
    color: var(--clr, #00d4ff);
    font-size: 11px;
    line-height: 1;
    flex-shrink: 0;
  }
  .bname { flex: 1; }
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

  .cot {
    border-top: 1px solid #16283a;
    padding-top: 5px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .cot-line {
    font-family: monospace;
    font-size: 11px;
    line-height: 1.4;
    color: #5f7e90;          /* older thoughts: dim */
    white-space: pre-wrap;
  }
  .cot-line.latest {
    color: #b8dcec;          /* current thought: bright */
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
