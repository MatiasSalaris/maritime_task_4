import maplibregl from 'maplibre-gl'
import { agentColor } from '../store/worldStore.js'

const STATUS_RING = {
  operational: '#00ff88',
  degraded:    '#ffaa00',
  silent:      '#ff3355',
}

// Icons are drawn NORTH-UP; heading is applied via marker.setRotation()
// (a cheap GPU CSS transform) so we never rewrite innerHTML per frame.
function usvSVG(color, ringColor) {
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="-19 -19 38 38">
  <line x1="0" y1="-12" x2="0" y2="-22"
        stroke="${color}" stroke-width="1.5" stroke-opacity="0.85"/>
  <circle cx="0" cy="0" r="13"
          fill="none" stroke="${ringColor}" stroke-width="2" stroke-opacity="0.75"/>
  <polygon points="0,-12 6,2 5,10 -5,10 -6,2"
           fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.8"/>
  <rect x="-2.5" y="-1" width="5" height="6" rx="0.5"
        fill="#ffffff" fill-opacity="0.25"/>
</svg>`
}

function uavSVG(color, ringColor) {
  return `
<svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="-19 -19 38 38">
  <line x1="0" y1="-13" x2="0" y2="-22"
        stroke="${color}" stroke-width="1.5" stroke-opacity="0.85"/>
  <circle cx="0" cy="0" r="13"
          fill="none" stroke="${ringColor}" stroke-width="2" stroke-opacity="0.75" stroke-dasharray="4 2"/>
  <polygon points="0,-13 2.5,-4 2.5,8 0,12 -2.5,8 -2.5,-4"
           fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.8"/>
  <polygon points="0,-2 13,6 12,8 0,4"   fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.5"/>
  <polygon points="0,-2 -13,6 -12,8 0,4" fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.5"/>
  <polygon points="0,8 5,12 4,13 0,10"  fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.4"/>
  <polygon points="0,8 -5,12 -4,13 0,10" fill="${color}" fill-opacity="0.85" stroke="#ffffff" stroke-width="0.4"/>
</svg>`
}

function iconSVG(type, color, ringColor) {
  return (type ?? '').toUpperCase() === 'UAV'
    ? uavSVG(color, ringColor)
    : usvSVG(color, ringColor)
}

// Shortest-path angular interpolation (degrees)
function lerpAngle(a, b, t) {
  let d = ((b - a + 540) % 360) - 180
  return a + d * t
}

export class AgentLayer {
  constructor(mapManager, onAgentClick) {
    this._mgr          = mapManager
    this._onAgentClick = onAgentClick
    this._markers      = {}   // id → { marker, el, iconKey }
    this._state        = {}   // id → motion state
    this._onFrame      = null
    this._raf          = null
    this._lastT        = 0
  }

  /** Register a per-frame callback receiving interpolated positions. */
  onFrame(fn) { this._onFrame = fn }

  /** Feed the latest world snapshot (data rate, ~10 Hz). */
  update(agents) {
    const seen = new Set()

    for (const agent of agents) {
      seen.add(agent.id)
      const color     = agentColor(agent.id)
      const ringColor = STATUS_RING[agent.status] ?? '#ffffff'
      const lon = agent.position.lon
      const lat = agent.position.lat
      const hdg = agent.heading ?? 0

      // Create marker on first sight (icon drawn once, north-up)
      if (!this._markers[agent.id]) {
        const el = document.createElement('div')
        el.style.cssText = 'cursor:pointer;'
        el.addEventListener('click', () => this._onAgentClick?.(agent.id))
        const marker = new maplibregl.Marker({
          element: el, anchor: 'center', rotationAlignment: 'map',
        })
          .setLngLat([lon, lat])
          .setRotation(hdg)
          .addTo(this._mgr.map)
        this._markers[agent.id] = { marker, el, iconKey: '' }
        this._state[agent.id] = {
          dLon: lon, dLat: lat, dHdg: hdg,   // displayed (interpolated)
          tLon: lon, tLat: lat, tHdg: hdg,   // target (from data)
          range: agent.sensor_range_km ?? 4.0,
          type: agent.type,
        }
      }

      // Update target + meta
      const s = this._state[agent.id]
      s.tLon = lon; s.tLat = lat; s.tHdg = hdg
      s.range = agent.sensor_range_km ?? s.range
      s.type  = agent.type

      // Re-render the icon only when its appearance (type/status) changes
      const m = this._markers[agent.id]
      const iconKey = `${agent.type}|${agent.status}`
      if (m.iconKey !== iconKey) {
        m.el.innerHTML = iconSVG(agent.type, color, ringColor)
        m.iconKey = iconKey
      }
    }

    // Drop disconnected agents
    for (const id of Object.keys(this._markers)) {
      if (!seen.has(id)) {
        this._markers[id].marker.remove()
        delete this._markers[id]
        delete this._state[id]
      }
    }

    if (!this._raf) this._start()
  }

  _start() {
    this._lastT = performance.now()
    const loop = (now) => {
      this._raf = requestAnimationFrame(loop)
      const dt = Math.min(0.1, (now - this._lastT) / 1000)
      this._lastT = now
      // Critically-damped exponential smoothing (~70 ms time constant):
      // catches up to fresh 10 Hz data quickly with no visible stepping.
      const k = 1 - Math.exp(-dt / 0.07)

      for (const id of Object.keys(this._state)) {
        const s = this._state[id]
        s.dLon += (s.tLon - s.dLon) * k
        s.dLat += (s.tLat - s.dLat) * k
        s.dHdg  = lerpAngle(s.dHdg, s.tHdg, k)

        const m = this._markers[id]
        if (m) {
          m.marker.setLngLat([s.dLon, s.dLat])
          m.marker.setRotation(s.dHdg)
        }
      }

      if (this._onFrame) this._onFrame(this.displayPositions())
    }
    this._raf = requestAnimationFrame(loop)
  }

  /** {id: {lon, lat, heading, range}} at interpolated (display) positions. */
  displayPositions() {
    const out = {}
    for (const [id, s] of Object.entries(this._state)) {
      out[id] = { lon: s.dLon, lat: s.dLat, heading: s.dHdg, range: s.range }
    }
    return out
  }

  getScreenPos(agentId) {
    const entry = this._markers[agentId]
    if (!entry) return null
    return this._mgr.project(entry.marker.getLngLat())
  }

  teardown() {
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null }
    for (const { marker } of Object.values(this._markers)) marker.remove()
    this._markers = {}
    this._state = {}
  }
}
