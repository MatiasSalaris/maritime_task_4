import { agentColor } from '../store/worldStore.js'

const SRC_HIST = id => `path-history-${id}`
const SRC_PLAN = id => `path-planned-${id}`
const LYR_HIST = id => `layer-hist-${id}`
const LYR_PLAN = id => `layer-plan-${id}`

const EMPTY = { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } }

export class PathLayer {
  constructor(map, agentIds) {
    this._map      = map
    this._agentIds = agentIds
    this._cache    = {}   // id → { hist: [[lon,lat]...], plan: [[lon,lat]...] }
  }

  init() {
    for (const id of this._agentIds) {
      const color = agentColor(id)

      this._map.addSource(SRC_HIST(id), { type: 'geojson', data: EMPTY })
      this._map.addLayer({
        id: LYR_HIST(id),
        type: 'line',
        source: SRC_HIST(id),
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': color,
          'line-width': 2.5,
          'line-opacity': 0.9,
        },
      })

      this._map.addSource(SRC_PLAN(id), { type: 'geojson', data: EMPTY })
      this._map.addLayer({
        id: LYR_PLAN(id),
        type: 'line',
        source: SRC_PLAN(id),
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': color,
          'line-width': 2,
          'line-opacity': 0.8,
          'line-dasharray': [7, 5],
        },
      })

      this._cache[id] = { hist: [], plan: [] }
    }
  }

  /** Cache the latest data-rate snapshot (~10 Hz). */
  update(agents) {
    for (const agent of agents) {
      const c = this._cache[agent.id]
      if (!c) continue
      c.hist = (agent.path_history ?? []).map(p => [p.lon, p.lat])
      c.plan = (agent.planned_path ?? []).map(p => [p.lon, p.lat])
    }
  }

  /**
   * Draw at the interpolated display tip (~60 fps), so the trace stays glued
   * to the icon with no stepping or lag.
   * @param {Object} disp - {id: {lon, lat}} interpolated positions
   */
  renderFrame(disp) {
    for (const id of this._agentIds) {
      const c = this._cache[id]
      const d = disp[id]
      if (!c || !d) continue
      const tip = [d.lon, d.lat]

      const histSrc = this._map.getSource(SRC_HIST(id))
      if (histSrc) {
        histSrc.setData(
          c.hist.length >= 1
            ? { type: 'Feature', geometry: { type: 'LineString', coordinates: [...c.hist, tip] } }
            : EMPTY
        )
      }

      const planSrc = this._map.getSource(SRC_PLAN(id))
      if (planSrc) {
        planSrc.setData(
          c.plan.length >= 1
            ? { type: 'Feature', geometry: { type: 'LineString', coordinates: [tip, ...c.plan] } }
            : EMPTY
        )
      }
    }
  }

  teardown() {
    for (const id of this._agentIds) {
      ;[LYR_HIST(id), LYR_PLAN(id)].forEach(l => {
        if (this._map.getLayer(l))  this._map.removeLayer(l)
      })
      ;[SRC_HIST(id), SRC_PLAN(id)].forEach(s => {
        if (this._map.getSource(s)) this._map.removeSource(s)
      })
    }
  }
}
