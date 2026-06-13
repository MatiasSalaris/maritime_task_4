<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, mapOverlay } from './store/worldStore.js'
  import { createClient } from './ws/WorldStateClient.js'
  import { MapManager }   from './map/MapManager.js'
  import { AgentLayer }   from './map/AgentLayer.js'
  import { PathLayer }    from './map/PathLayer.js'
  import { ContactLayer } from './map/ContactLayer.js'
  import { AnimationCanvas } from './map/AnimationCanvas.js'
  import SidePanel       from './ui/SidePanel.svelte'
  import OverlayPicker   from './ui/OverlayPicker.svelte'
  import ThoughtBubbles  from './ui/ThoughtBubbles.svelte'
  import { selectedAgentId } from './store/worldStore.js'

  const AGENT_IDS = ['agent_0', 'agent_1', 'agent_2']

  let mapContainer
  let mapMgr, agentLayer, pathLayer, contactLayer, animCanvas
  let wsClient
  let ready = false

  // Reactive layer updates when world state changes
  $: if (ready && $worldState.agents) {
    agentLayer?.update($worldState.agents)
    pathLayer?.update($worldState.agents)
    contactLayer?.update($worldState.contacts ?? [])
  }

  // Feed new p2p messages to animation canvas
  let lastMsgCount = 0
  $: {
    const msgs = $worldState.messages_in_flight ?? []
    if (msgs.length > lastMsgCount) {
      const newMsgs = msgs.slice(lastMsgCount)
      newMsgs.forEach(m => animCanvas?.addPacket(m))
    }
    lastMsgCount = msgs.length
  }

  async function switchOverlay(id) {
    await mapMgr.switchOverlay(id)
    // Re-init layers after style swap
    pathLayer?.init()
    contactLayer?.init()
  }

  onMount(async () => {
    mapMgr = new MapManager(mapContainer)
    await mapMgr.init('tactical')

    pathLayer    = new PathLayer(mapMgr.map, AGENT_IDS)
    contactLayer = new ContactLayer(mapMgr.map)
    pathLayer.init()
    contactLayer.init()

    agentLayer   = new AgentLayer(mapMgr, id => selectedAgentId.set(id))
    animCanvas   = new AnimationCanvas(mapContainer, agentLayer)

    wsClient = createClient()
    ready = true
  })

  onDestroy(() => {
    wsClient?.destroy()
    agentLayer?.teardown()
    pathLayer?.teardown()
    contactLayer?.teardown()
    animCanvas?.destroy()
    mapMgr?.destroy()
  })
</script>

<SidePanel />

<div class="map-area">
  <div class="map-container" bind:this={mapContainer}></div>

  <!-- Overlay picker — top-right of map -->
  <div class="overlay-widget">
    <OverlayPicker onSwitch={switchOverlay} />
  </div>

  <!-- Thought bubbles rendered absolutely over the map -->
  {#if ready}
    <div class="bubbles-layer">
      <ThoughtBubbles agentLayerRef={agentLayer} mapRef={mapMgr} />
    </div>
  {/if}
</div>

<style>
  :global(body) {
    font-family: 'Courier New', monospace;
    background: #060c18;
    color: #c8d8e8;
  }

  .map-area {
    flex: 1;
    position: relative;
    overflow: hidden;
  }

  .map-container {
    width: 100%;
    height: 100%;
  }

  .overlay-widget {
    position: absolute;
    top: 14px;
    right: 14px;
    z-index: 20;
  }

  .bubbles-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 30;
  }

  /* MapLibre overrides to fit dark theme */
  :global(.maplibregl-ctrl-attrib) {
    background: rgba(6,12,24,0.7) !important;
    color: #3a5a7a !important;
    font-size: 9px !important;
  }
  :global(.maplibregl-ctrl-group) {
    background: rgba(6,12,24,0.85) !important;
    border: 1px solid #1a2a3a !important;
  }
  :global(.maplibregl-ctrl-group button) {
    background-color: transparent !important;
    color: #8ab0c0 !important;
  }
</style>
