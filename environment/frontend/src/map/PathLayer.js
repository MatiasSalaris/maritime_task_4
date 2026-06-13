import { agentColor } from '../store/worldStore.js'

const HISTORY_SOURCE  = id => `path-history-${id}`
const PLANNED_SOURCE  = id => `path-planned-${id}`
const HISTORY_LAYER   = id => `layer-path-history-${id}`
const PLANNED_LAYER   = id => `layer-path-planned-${id}`

export class PathLayer {
  constructor(map, agentIds) {
    this._map = map
    this._agentIds = agentIds
  }

  init() {
    for (const id of this._agentIds) {
      const color = agentColor(id)

      // History path
      this._map.addSource(HISTORY_SOURCE(id), {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } },
      })
      this._map.addLayer({
        id: HISTORY_LAYER(id),
        type: 'line',
        source: HISTORY_SOURCE(id),
        paint: {
          'line-color': color,
          'line-width': 1.5,
          'line-opacity': 0.45,
          'line-dasharray': [2, 0],
        },
      })

      // Planned path
      this._map.addSource(PLANNED_SOURCE(id), {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] } },
      })
      this._map.addLayer({
        id: PLANNED_LAYER(id),
        type: 'line',
        source: PLANNED_SOURCE(id),
        paint: {
          'line-color': color,
          'line-width': 1.5,
          'line-opacity': 0.7,
          'line-dasharray': [6, 4],
        },
      })
    }
  }

  update(agents) {
    for (const agent of agents) {
      const histSrc = this._map.getSource(HISTORY_SOURCE(agent.id))
      if (histSrc && agent.path_history?.length >= 2) {
        histSrc.setData({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: agent.path_history.map(p => [p.lon, p.lat]),
          },
        })
      }

      const planSrc = this._map.getSource(PLANNED_SOURCE(agent.id))
      if (planSrc && agent.planned_path?.length >= 2) {
        planSrc.setData({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: agent.planned_path.map(p => [p.lon, p.lat]),
          },
        })
      }
    }
  }

  teardown() {
    for (const id of this._agentIds) {
      for (const lyr of [HISTORY_LAYER(id), PLANNED_LAYER(id)]) {
        if (this._map.getLayer(lyr)) this._map.removeLayer(lyr)
      }
      for (const src of [HISTORY_SOURCE(id), PLANNED_SOURCE(id)]) {
        if (this._map.getSource(src)) this._map.removeSource(src)
      }
    }
  }
}
