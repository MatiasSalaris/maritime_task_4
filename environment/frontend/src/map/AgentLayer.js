import maplibregl from 'maplibre-gl'
import { agentColor } from '../store/worldStore.js'

const STATUS_RING = {
  operational: '#00ff88',
  degraded:    '#ffaa00',
  silent:      '#ff3355',
}

function shipSVG(color, ringColor, heading) {
  // Triangle pointing up = north; rotate by heading
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="-18 -18 36 36">
  <g transform="rotate(${heading})">
    <!-- Heading indicator line -->
    <line x1="0" y1="-10" x2="0" y2="-22"
          stroke="${color}" stroke-width="1.5" stroke-opacity="0.8"/>
    <!-- Status ring -->
    <circle cx="0" cy="0" r="13"
            fill="none" stroke="${ringColor}" stroke-width="2" stroke-opacity="0.75"/>
    <!-- Ship hull -->
    <polygon points="0,-10 7,8 0,5 -7,8"
             fill="${color}" stroke="#ffffff" stroke-width="1"/>
  </g>
</svg>`
}

export class AgentLayer {
  constructor(mapManager, onAgentClick) {
    this._mgr = mapManager
    this._markers = {}         // agent_id → maplibregl.Marker
    this._onAgentClick = onAgentClick
  }

  update(agents) {
    const seen = new Set()

    for (const agent of agents) {
      seen.add(agent.id)
      const color     = agentColor(agent.id)
      const ringColor = STATUS_RING[agent.status] ?? '#ffffff'

      if (!this._markers[agent.id]) {
        // Create new marker
        const el = document.createElement('div')
        el.style.cssText = 'cursor:pointer;'
        el.addEventListener('click', () => this._onAgentClick?.(agent.id))

        const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
          .setLngLat([agent.position.lon, agent.position.lat])
          .addTo(this._mgr.map)

        this._markers[agent.id] = { marker, el }
      }

      const { marker, el } = this._markers[agent.id]
      el.innerHTML = shipSVG(color, ringColor, agent.heading)
      marker.setLngLat([agent.position.lon, agent.position.lat])
    }

    // Remove markers for agents no longer in state
    for (const id of Object.keys(this._markers)) {
      if (!seen.has(id)) {
        this._markers[id].marker.remove()
        delete this._markers[id]
      }
    }
  }

  /**
   * Returns screen {x, y} for a given agent_id, or null.
   * Used by ThoughtBubble to position the overlay.
   */
  getScreenPos(agentId) {
    const entry = this._markers[agentId]
    if (!entry) return null
    const lngLat = entry.marker.getLngLat()
    return this._mgr.project(lngLat)
  }

  teardown() {
    for (const { marker } of Object.values(this._markers)) marker.remove()
    this._markers = {}
  }
}
