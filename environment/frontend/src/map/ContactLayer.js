const SOURCE_ID = 'contacts'
const LAYER_ID  = 'layer-contacts'
const LABEL_ID  = 'layer-contacts-labels'

const LABEL_COLORS = {
  AIS_COMMERCIAL: '#4488ff',
  AIS_FISHING:    '#aaddaa',
  UNKNOWN:        '#ffaa00',
  FLAGGED:        '#ff3355',
}

export class ContactLayer {
  constructor(map) {
    this._map = map
  }

  init() {
    this._map.addSource(SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })

    this._map.addLayer({
      id: LAYER_ID,
      type: 'circle',
      source: SOURCE_ID,
      paint: {
        'circle-radius': ['case', ['get', 'flagged'], 7, 5],
        'circle-color': [
          'match', ['get', 'label'],
          'AIS_COMMERCIAL', '#4488ff',
          'AIS_FISHING',    '#aaddaa',
          'UNKNOWN',        '#ffaa00',
          '#ff3355',
        ],
        'circle-opacity': 0.85,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': ['case', ['get', 'flagged'], 2, 0.5],
      },
    })

    this._map.addLayer({
      id: LABEL_ID,
      type: 'symbol',
      source: SOURCE_ID,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 9,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#c8d8e8',
        'text-halo-color': '#0a0e1a',
        'text-halo-width': 1,
      },
    })
  }

  update(contacts) {
    const src = this._map.getSource(SOURCE_ID)
    if (!src) return
    src.setData({
      type: 'FeatureCollection',
      features: contacts.map(c => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [c.position.lon, c.position.lat] },
        properties: { id: c.id, label: c.label, flagged: c.flagged, mmsi: c.mmsi ?? '' },
      })),
    })
  }

  teardown() {
    if (this._map.getLayer(LABEL_ID)) this._map.removeLayer(LABEL_ID)
    if (this._map.getLayer(LAYER_ID)) this._map.removeLayer(LAYER_ID)
    if (this._map.getSource(SOURCE_ID)) this._map.removeSource(SOURCE_ID)
  }
}
