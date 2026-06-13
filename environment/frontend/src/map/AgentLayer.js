import maplibregl from 'maplibre-gl'
import { agentColor } from '../store/worldStore.js'

const STATUS_RING = {
  operational: '#00ff88',
  degraded:    '#ffaa00',
  silent:      '#ff3355',
}

// Surface vessel — elongated hull with bow pointing north, rotated by heading
function usvSVG(color, ringColor, heading) {
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="-19 -19 38 38">
  <g transform="rotate(${heading})">
    <line x1="0" y1="-12" x2="0" y2="-22"
          stroke="${color}" stroke-width="1.5" stroke-opacity="0.85"/>
    <circle cx="0" cy="0" r="13"
            fill="none" stroke="${ringColor}" stroke-width="2" stroke-opacity="0.75"/>
    <!-- Hull: pointed bow, flat stern -->
    <polygon points="0,-12 6,2 5,10 -5,10 -6,2"
             fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.8"/>
    <!-- Superstructure hint -->
    <rect x="-2.5" y="-1" width="5" height="6" rx="0.5"
          fill="#ffffff" fill-opacity="0.25"/>
  </g>
</svg>`
}

// Aerial drone — fixed-wing UAV silhouette (fuselage + swept wings + tail)
function uavSVG(color, ringColor, heading) {
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="-19 -19 38 38">
  <g transform="rotate(${heading})">
    <line x1="0" y1="-13" x2="0" y2="-22"
          stroke="${color}" stroke-width="1.5" stroke-opacity="0.85"/>
    <circle cx="0" cy="0" r="13"
            fill="none" stroke="${ringColor}" stroke-width="2" stroke-opacity="0.75" stroke-dasharray="4 2"/>
    <!-- Fuselage: pointed nose up, tapered tail -->
    <polygon points="0,-13 2.5,-4 2.5,8 0,12 -2.5,8 -2.5,-4"
             fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.8"/>
    <!-- Main wings (swept back) -->
    <polygon points="0,-2 13,6 12,8 0,4"   fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.5"/>
    <polygon points="0,-2 -13,6 -12,8 0,4" fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.5"/>
    <!-- Tail fins -->
    <polygon points="0,8 5,12 4,13 0,10"  fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.4"/>
    <polygon points="0,8 -5,12 -4,13 0,10" fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.4"/>
  </g>
</svg>`
}

function iconSVG(agent, color, ringColor) {
  const t = (agent.type ?? '').toUpperCase()
  return t === 'UAV'
    ? uavSVG(color, ringColor, agent.heading)
    : usvSVG(color, ringColor, agent.heading)
}

export class AgentLayer {
  constructor(mapManager, onAgentClick) {
    this._mgr = mapManager
    this._markers = {}         // agent_id → { marker, el }
    this._onAgentClick = onAgentClick
  }

  update(agents) {
    const seen = new Set()

    for (const agent of agents) {
      seen.add(agent.id)
      const color     = agentColor(agent.id)
      const ringColor = STATUS_RING[agent.status] ?? '#ffffff'

      if (!this._markers[agent.id]) {
        const el = document.createElement('div')
        el.style.cssText = 'cursor:pointer;'
        el.addEventListener('click', () => this._onAgentClick?.(agent.id))

        const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
          .setLngLat([agent.position.lon, agent.position.lat])
          .addTo(this._mgr.map)

        this._markers[agent.id] = { marker, el }
      }

      const { marker, el } = this._markers[agent.id]
      el.innerHTML = iconSVG(agent, color, ringColor)
      marker.setLngLat([agent.position.lon, agent.position.lat])
    }

    for (const id of Object.keys(this._markers)) {
      if (!seen.has(id)) {
        this._markers[id].marker.remove()
        delete this._markers[id]
      }
    }
  }

  getScreenPos(agentId) {
    const entry = this._markers[agentId]
    if (!entry) return null
    return this._mgr.project(entry.marker.getLngLat())
  }

  teardown() {
    for (const { marker } of Object.values(this._markers)) marker.remove()
    this._markers = {}
  }
}
