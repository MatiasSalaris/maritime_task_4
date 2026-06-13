import maplibregl from 'maplibre-gl'
import { agentColor } from '../store/worldStore.js'

const DEG_PER_KM = 1 / 111.32

function hexToRgba(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${a})`
}

/**
 * Sensor footprint rings rendered as DOM markers (CSS circles) rather than
 * GeoJSON polygons. DOM markers are repositioned synchronously with the agent
 * icon on every map render, so the ring stays perfectly glued to the icon with
 * no worker-pipeline lag. The pixel radius is recomputed each frame from the
 * map projection, so it scales correctly with zoom.
 */
export class SensorLayer {
  constructor(map, agentIds) {
    this._map      = map
    this._agentIds = agentIds
    this._markers  = {}   // id → { marker, ring }
  }

  init() {
    for (const id of this._agentIds) {
      const color = agentColor(id)

      // 0-size anchor container at the agent point …
      const el = document.createElement('div')
      el.style.cssText = 'width:0;height:0;pointer-events:none;'

      // … with a circle child centered on it (independent of its size)
      const ring = document.createElement('div')
      ring.style.cssText = `
        position:absolute; left:0; top:0;
        transform:translate(-50%,-50%);
        border-radius:50%;
        box-sizing:border-box;
        border:1px dashed ${color};
        background:${hexToRgba(color, 0.06)};
        pointer-events:none;
        width:0; height:0;
      `
      el.appendChild(ring)

      const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([0, 0])
        .addTo(this._map)

      this._markers[id] = { marker, ring }
    }
  }

  /**
   * Position + size each ring at the interpolated display position (~60 fps).
   * @param {Object} disp - {id: {lon, lat, range}}
   */
  renderFrame(disp) {
    for (const id of this._agentIds) {
      const m = this._markers[id]
      const d = disp[id]
      if (!m || !d) continue

      m.marker.setLngLat([d.lon, d.lat])

      // Pixel radius from a north-offset point at the sensor range
      const c = this._map.project([d.lon, d.lat])
      const e = this._map.project([d.lon, d.lat + (d.range ?? 4.0) * DEG_PER_KM])
      const px = Math.max(2, Math.hypot(e.x - c.x, e.y - c.y))
      const size = `${px * 2}px`
      m.ring.style.width  = size
      m.ring.style.height = size
    }
  }

  teardown() {
    for (const { marker } of Object.values(this._markers)) marker.remove()
    this._markers = {}
  }
}
