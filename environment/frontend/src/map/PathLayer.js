import { agentColor } from '../store/worldStore.js'

// Two layers per path: a wide soft glow + a sharp line on top
const SRC_HIST   = id => `path-history-${id}`
const SRC_PLAN   = id => `path-planned-${id}`
const LYR_HIST_G = id => `layer-hist-glow-${id}`   // glow (wide, faint)
const LYR_HIST   = id => `layer-hist-${id}`         // solid line
const LYR_PLAN_G = id => `layer-plan-glow-${id}`    // glow
const LYR_PLAN   = id => `layer-plan-${id}`         // dashed line

export class PathLayer {
  constructor(map, agentIds) {
    this._map = map
    this._agentIds = agentIds
  }

  init() {
    for (const id of this._agentIds) {
      const color = agentColor(id)
      const empty = { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } }

      // ── History path ────────────────────────────────────────────────────────
      this._map.addSource(SRC_HIST(id), { type: 'geojson', data: empty })

      // glow layer (wide, transparent)
      this._map.addLayer({
        id: LYR_HIST_G(id), type: 'line', source: SRC_HIST(id),
        paint: {
          'line-color': color,
          'line-width': 8,
          'line-opacity': 0.18,
          'line-blur': 4,
        },
      })
      // sharp line
      this._map.addLayer({
        id: LYR_HIST(id), type: 'line', source: SRC_HIST(id),
        paint: {
          'line-color': color,
          'line-width': 2.5,
          'line-opacity': 0.80,
        },
      })

      // ── Planned path ─────────────────────────────────────────────────────────
      this._map.addSource(SRC_PLAN(id), { type: 'geojson', data: empty })

      // glow
      this._map.addLayer({
        id: LYR_PLAN_G(id), type: 'line', source: SRC_PLAN(id),
        paint: {
          'line-color': color,
          'line-width': 6,
          'line-opacity': 0.15,
          'line-blur': 3,
        },
      })
      // dashed line
      this._map.addLayer({
        id: LYR_PLAN(id), type: 'line', source: SRC_PLAN(id),
        paint: {
          'line-color': color,
          'line-width': 2,
          'line-opacity': 0.90,
          'line-dasharray': [7, 5],
        },
      })
    }
  }

  update(agents) {
    const empty = { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } }

    for (const agent of agents) {
      const histSrc = this._map.getSource(SRC_HIST(agent.id))
      if (histSrc) {
        if (agent.path_history?.length >= 2) {
          histSrc.setData({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: agent.path_history.map(p => [p.lon, p.lat]) },
          })
        } else {
          histSrc.setData(empty)
        }
      }

      const planSrc = this._map.getSource(SRC_PLAN(agent.id))
      if (planSrc) {
        if (agent.planned_path?.length >= 1) {
          const current   = [agent.position.lon, agent.position.lat]
          const waypoints = agent.planned_path.map(p => [p.lon, p.lat])
          planSrc.setData({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: [current, ...waypoints] },
          })
        } else {
          planSrc.setData(empty)
        }
      }
    }
  }

  teardown() {
    for (const id of this._agentIds) {
      const layers = [LYR_HIST_G(id), LYR_HIST(id), LYR_PLAN_G(id), LYR_PLAN(id)]
      const sources = [SRC_HIST(id), SRC_PLAN(id)]
      layers.forEach(l  => { if (this._map.getLayer(l))   this._map.removeLayer(l)  })
      sources.forEach(s => { if (this._map.getSource(s))  this._map.removeSource(s) })
    }
  }
}
