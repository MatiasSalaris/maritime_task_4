// Renders mission points-of-interest (buoys, investigation points, rendezvous)
// as labelled diamond markers. POIs come straight from world_state.pois and are
// scenario-defined, so switching scenarios changes what's marked on the map.

const SRC = 'pois'
const LAYER_HALO  = 'layer-pois-halo'
const LAYER_DIAMOND = 'layer-pois-diamond'
const LAYER_LABEL = 'layer-pois-label'

function emptyFC() { return { type: 'FeatureCollection', features: [] } }

export class POILayer {
  constructor(map) { this._map = map }

  init() {
    this._map.addSource(SRC, { type: 'geojson', data: emptyFC() })

    this._map.addLayer({
      id: LAYER_HALO,
      type: 'circle',
      source: SRC,
      paint: {
        'circle-radius': 13,
        'circle-color': '#ffcc33',
        'circle-opacity': 0.14,
      },
    })

    // A rotated square reads as a diamond — distinct from round contacts.
    this._map.addLayer({
      id: LAYER_DIAMOND,
      type: 'symbol',
      source: SRC,
      layout: {
        'text-field': '◆',
        'text-size': 16,
        'text-allow-overlap': true,
        'text-rotation-alignment': 'viewport',
      },
      paint: {
        'text-color': '#ffcc33',
        'text-halo-color': '#1a1200',
        'text-halo-width': 1.4,
      },
    })

    this._map.addLayer({
      id: LAYER_LABEL,
      type: 'symbol',
      source: SRC,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 11,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
        'text-allow-overlap': true,
      },
      paint: {
        'text-color': '#ffe08a',
        'text-halo-color': '#060c18',
        'text-halo-width': 1.6,
      },
    })
  }

  update(pois) {
    const features = (pois ?? []).map(p => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.position.lon, p.position.lat] },
      properties: { id: p.id, label: p.label, visited: !!p.visited },
    }))
    this._map.getSource(SRC)?.setData({ type: 'FeatureCollection', features })
  }

  teardown() {
    for (const l of [LAYER_HALO, LAYER_DIAMOND, LAYER_LABEL]) {
      if (this._map.getLayer(l)) this._map.removeLayer(l)
    }
    if (this._map.getSource(SRC)) this._map.removeSource(SRC)
  }
}
