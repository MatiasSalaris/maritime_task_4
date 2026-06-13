/**
 * OperatingAreaLayer — renders the selected AOR on the MapLibre map.
 *
 * Visual: semi-transparent dark mask over everything OUTSIDE the AOR,
 * with a bright dashed border around the AOR itself.
 *
 * The mask uses a GeoJSON Polygon with a world-size outer ring and the
 * selected area as a hole (even-odd fill rule → inside is unmasked).
 */

const SRC_MASK   = 'aor-mask-source'
const SRC_BORDER = 'aor-border-source'
const LYR_MASK   = 'aor-mask-layer'
const LYR_BORDER = 'aor-border-layer'

// World-spanning outer ring (CCW = exterior in right-hand rule)
const WORLD_RING = [[-180,-85],[180,-85],[180,85],[-180,85],[-180,-85]]

const EMPTY_FEAT = { type: 'Feature', geometry: { type: 'Polygon', coordinates: [] } }

export class OperatingAreaLayer {
  constructor(map) {
    this._map = map
    this._geo = null   // current GeoJSON Polygon geometry or null
  }

  init() {
    const m = this._map

    m.addSource(SRC_MASK, { type: 'geojson', data: EMPTY_FEAT })
    m.addLayer({
      id: LYR_MASK, type: 'fill', source: SRC_MASK,
      paint: {
        'fill-color': '#000010',
        'fill-opacity': 0.48,
        'fill-antialias': true,
      },
    })

    m.addSource(SRC_BORDER, { type: 'geojson', data: EMPTY_FEAT })
    m.addLayer({
      id: LYR_BORDER, type: 'line', source: SRC_BORDER,
      paint: {
        'line-color': '#00d4ff',
        'line-width': 2,
        'line-opacity': 0.90,
        'line-dasharray': [8, 5],
      },
    })
  }

  /** Set a new operating area from a GeoJSON Polygon geometry. */
  setArea(polygonGeometry) {
    this._geo = polygonGeometry
    this._update()
  }

  /** Clear the operating area. */
  clear() {
    this._geo = null
    this._map.getSource(SRC_MASK)?.setData(EMPTY_FEAT)
    this._map.getSource(SRC_BORDER)?.setData(EMPTY_FEAT)
  }

  teardown() {
    if (this._map.getLayer(LYR_MASK))   this._map.removeLayer(LYR_MASK)
    if (this._map.getLayer(LYR_BORDER)) this._map.removeLayer(LYR_BORDER)
    if (this._map.getSource(SRC_MASK))  this._map.removeSource(SRC_MASK)
    if (this._map.getSource(SRC_BORDER))this._map.removeSource(SRC_BORDER)
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  _update() {
    if (!this._geo) return
    const inner = this._geo.coordinates[0]

    // Mask = world polygon with AOR hole (CW winding for hole)
    // GeoJSON winding: exterior CCW, holes CW
    // We reverse the AOR ring to make it CW
    const hole = [...inner].reverse()

    const maskFeat = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [WORLD_RING, hole],
      },
    }

    const borderFeat = {
      type: 'Feature',
      geometry: this._geo,
    }

    this._map.getSource(SRC_MASK)?.setData(maskFeat)
    this._map.getSource(SRC_BORDER)?.setData(borderFeat)
  }
}
