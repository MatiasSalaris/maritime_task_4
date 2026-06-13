<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, mapOverlay } from './store/worldStore.js'
  import { createClient }         from './ws/WorldStateClient.js'
  import { MapManager }           from './map/MapManager.js'
  import { AgentLayer }           from './map/AgentLayer.js'
  import { PathLayer }            from './map/PathLayer.js'
  import { ContactLayer }         from './map/ContactLayer.js'
  import { AnimationCanvas }      from './map/AnimationCanvas.js'
  import { MilitaryGrid }         from './map/MilitaryGrid.js'
  import { AreaSelector }         from './map/AreaSelector.js'
  import { OperatingAreaLayer }   from './map/OperatingAreaLayer.js'
  import SidePanel                from './ui/SidePanel.svelte'
  import OverlayPicker            from './ui/OverlayPicker.svelte'
  import ThoughtBubbles           from './ui/ThoughtBubbles.svelte'
  import MapTools                 from './ui/MapTools.svelte'
  import { selectedAgentId }      from './store/worldStore.js'

  const AGENT_IDS = ['agent_0', 'agent_1', 'agent_2']

  let mapContainer
  let mapMgr, agentLayer, pathLayer, contactLayer, animCanvas
  let militaryGrid, areaSelector, areaLayer
  let wsClient
  let ready = false

  // ── AOR tool state ─────────────────────────────────────────────────────────
  let drawMode    = null    // 'rect' | 'circle' | 'poly' | null
  let gridEnabled = false
  let hasArea     = false
  let pendingGeo  = null    // GeoJSON Polygon geometry waiting to be sent

  // Reactive layer updates
  $: if (ready && $worldState.agents) {
    agentLayer?.update($worldState.agents)
    pathLayer?.update($worldState.agents)
    contactLayer?.update($worldState.contacts ?? [])
  }

  // Feed p2p messages to animation canvas
  let lastMsgCount = 0
  $: {
    const msgs = $worldState.messages_in_flight ?? []
    if (msgs.length > lastMsgCount) msgs.slice(lastMsgCount).forEach(m => animCanvas?.addPacket(m))
    lastMsgCount = msgs.length
  }

  // Sync AOR from world state (in case of page reload after AOR was set)
  $: if (ready && $worldState.aor) {
    areaLayer?.setArea($worldState.aor)
    hasArea = true
    pendingGeo = null
  }

  function switchOverlay(id) { mapMgr.switchOverlay(id) }

  function handleModeChange(mode) {
    if (mode === '__transmit__') { sendAOR(); return }

    drawMode = mode
    if (mode) {
      areaSelector?.setMode(mode)
    } else {
      areaSelector?.cancel()
    }
  }

  function handleAreaReady(geo) {
    pendingGeo = geo
    areaLayer?.setArea(geo)
    hasArea = true
    drawMode = null
    sendAOR()
  }

  async function sendAOR() {
    if (!pendingGeo) return
    try {
      await fetch('/api/aor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ geometry: pendingGeo }),
      })
    } catch (e) {
      console.error('[AOR] send failed:', e)
    }
  }

  async function clearArea() {
    areaLayer?.clear()
    hasArea = false
    pendingGeo = null
    drawMode = null
    areaSelector?.cancel()
    await fetch('/api/aor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ geometry: null }),
    }).catch(() => {})
  }

  function toggleGrid() {
    if (militaryGrid) gridEnabled = militaryGrid.toggle()
  }

  onMount(async () => {
    mapMgr = new MapManager(mapContainer)
    await mapMgr.init('tactical')

    const map = mapMgr.map

    // Base map layers
    pathLayer    = new PathLayer(map, AGENT_IDS)
    contactLayer = new ContactLayer(map)
    areaLayer    = new OperatingAreaLayer(map)
    pathLayer.init()
    contactLayer.init()
    areaLayer.init()

    agentLayer    = new AgentLayer(mapMgr, id => selectedAgentId.set(id))
    animCanvas    = new AnimationCanvas(mapContainer, agentLayer)
    militaryGrid  = new MilitaryGrid(mapContainer, map)

    // Area selector — emits geometry when drawing completes
    areaSelector = new AreaSelector(map, mapContainer, geo => {
      handleAreaReady(geo)
    })

    wsClient = createClient()
    ready    = true
  })

  onDestroy(() => {
    wsClient?.destroy()
    agentLayer?.teardown()
    pathLayer?.teardown()
    contactLayer?.teardown()
    areaLayer?.teardown()
    animCanvas?.destroy()
    militaryGrid?.destroy()
    areaSelector?.destroy()
    mapMgr?.destroy()
  })
</script>

<SidePanel />

<div class="map-area">
  <div class="map-container" bind:this={mapContainer}></div>

  <!-- Overlay picker — top-right -->
  <div class="overlay-widget">
    <OverlayPicker onSwitch={switchOverlay} />
  </div>

  <!-- Map tools — top-left (AOR drawing + MGRS grid toggle) -->
  <div class="tools-widget">
    <MapTools
      activeMode={drawMode}
      {gridEnabled}
      {hasArea}
      onModeChange={handleModeChange}
      onClearArea={clearArea}
      onGridToggle={toggleGrid}
    />
  </div>

  <!-- Thought bubbles -->
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

  .tools-widget {
    position: absolute;
    top: 14px;
    left: 14px;
    z-index: 20;
  }

  .bubbles-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 30;
  }

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
