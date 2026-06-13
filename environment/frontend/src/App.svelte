<script>
  import { onMount, onDestroy } from 'svelte'
  import { worldState, mapOverlay, godView } from './store/worldStore.js'
  import { createClient }         from './ws/WorldStateClient.js'
  import { MapManager }           from './map/MapManager.js'
  import { AgentLayer }           from './map/AgentLayer.js'
  import { PathLayer }            from './map/PathLayer.js'
  import { ContactLayer }         from './map/ContactLayer.js'
  import { SensorLayer }          from './map/SensorLayer.js'
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
  const AGENT_TYPES = { agent_0: 'USV', agent_1: 'USV', agent_2: 'UAV' }

  let mapContainer
  let mapMgr, agentLayer, pathLayer, contactLayer, animCanvas
  let sensorLayer
  let militaryGrid, areaSelector, areaLayer
  let wsClient
  let ready = false

  // ── AOR tool state ─────────────────────────────────────────────────────────
  let drawMode    = null    // 'rect' | 'circle' | 'poly' | null
  let gridEnabled = false
  let hasArea     = false
  let pendingGeo  = null    // GeoJSON Polygon geometry waiting to be sent

  // Reactive layer updates (data rate ~10 Hz): feed targets + cache geometry.
  // The actual drawing of the trace / sensor rings happens at 60 fps in the
  // AgentLayer rAF callback (see onMount), interpolated for smooth motion.
  // Single path: reruns on every world tick AND immediately when god view is
  // toggled (both $worldState and $godView are referenced here).
  $: if (ready && $worldState.agents) {
    agentLayer?.update($worldState.agents)   // sets interpolation targets
    pathLayer?.update($worldState.agents)    // caches history / planned coords
    // Cache contacts; detection + reveal happen at 60 fps in renderFrame, using
    // the interpolated agent positions (consistent with the drawn sensor rings).
    contactLayer?.update($worldState.contacts ?? [], $godView, $worldState.time)
  }

  // Detect a world reset (path history collapses to empty) → wipe track memory
  // so previously-detected contacts don't linger as ghosts after a fresh start.
  let _prevHistLen = 0
  $: if (ready) {
    const histLen = ($worldState.agents ?? []).reduce((n, a) => n + (a.path_history?.length ?? 0), 0)
    if (_prevHistLen > 4 && histLen === 0) contactLayer?.reset()
    _prevHistLen = histLen
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
    // Start clean: wipe any preserved backend state from a previous session
    // so a page refresh always begins from a blank world.
    try { await fetch('/api/reset', { method: 'POST' }) } catch (e) { /* non-fatal */ }

    mapMgr = new MapManager(mapContainer)
    await mapMgr.init('tactical')

    const map = mapMgr.map

    // Base map layers. Order matters: the operating-area mask is added FIRST so
    // it sits *below* the tracks and contacts — otherwise its dark fill would
    // dim/occlude contacts that are inside or outside a drawn area.
    areaLayer    = new OperatingAreaLayer(map)
    pathLayer    = new PathLayer(map, AGENT_IDS, AGENT_TYPES)
    contactLayer = new ContactLayer(map)
    areaLayer.init()
    pathLayer.init()
    contactLayer.init()

    // Live sensor footprint rings (computed client-side from agent positions)
    sensorLayer = new SensorLayer(map, AGENT_IDS)
    sensorLayer.init()

    agentLayer    = new AgentLayer(mapMgr, id => selectedAgentId.set(id))
    animCanvas    = new AnimationCanvas(mapContainer, agentLayer)
    animCanvas.setMap(map)
    contactLayer.setAnimCanvas(animCanvas)
    militaryGrid  = new MilitaryGrid(mapContainer, map)

    // Smooth 60 fps rendering: the trace and sensor rings are drawn from the
    // AgentLayer's interpolated positions, so they stay glued to the icon.
    agentLayer.onFrame(disp => {
      pathLayer?.renderFrame(disp)
      sensorLayer?.renderFrame(disp)
      // Detect/reveal contacts from the SAME interpolated positions the sensor
      // rings are drawn at, so "inside a ring" and "shown" always agree.
      contactLayer?.renderFrame(disp)
    })

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
    sensorLayer?.teardown()
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

  <!-- Map tools — top-left (AOR drawing + MGRS grid toggle + GOD VIEW) -->
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
