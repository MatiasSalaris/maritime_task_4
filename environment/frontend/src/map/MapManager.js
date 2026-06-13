import maplibregl from 'maplibre-gl'
import { OVERLAY_MAP } from './overlays/index.js'

const DEMO_CENTER = [15.14, 37.50]  // Strait of Sicily
const DEMO_ZOOM   = 11

export class MapManager {
  constructor(container) {
    this._container = container
    this._map = null
    this._overlayId = 'tactical'
    this._layers = {}    // registered layer managers
  }

  init(overlayId = 'tactical') {
    this._overlayId = overlayId
    const overlay = OVERLAY_MAP[overlayId]

    this._map = new maplibregl.Map({
      container: this._container,
      style: overlay.style,
      center: DEMO_CENTER,
      zoom: DEMO_ZOOM,
      attributionControl: false,
    })

    this._map.addControl(new maplibregl.NavigationControl(), 'bottom-right')
    this._map.addControl(new maplibregl.ScaleControl({ unit: 'nautical' }), 'bottom-left')
    this._map.addControl(
      new maplibregl.AttributionControl({ compact: true }), 'bottom-right'
    )

    return new Promise(resolve => this._map.on('load', resolve))
  }

  switchOverlay(overlayId) {
    if (overlayId === this._overlayId) return
    const overlay = OVERLAY_MAP[overlayId]
    if (!overlay) return
    this._overlayId = overlayId

    // All overlays share source IDs 'base' + 'seamarks' — swap tile URLs only.
    for (const [srcId, srcDef] of Object.entries(overlay.style.sources)) {
      const src = this._map.getSource(srcId)
      if (src && srcDef.tiles) src.setTiles(srcDef.tiles)
    }

    // Apply per-overlay paint tweaks (brightness, contrast, saturation, opacity).
    // Each overlay defines the full set of paint props so nothing bleeds across switches.
    for (const layerDef of overlay.style.layers) {
      if (!layerDef.paint || !this._map.getLayer(layerDef.id)) continue
      for (const [key, val] of Object.entries(layerDef.paint)) {
        this._map.setPaintProperty(layerDef.id, key, val)
      }
    }
  }

  registerLayer(name, layerManager) {
    this._layers[name] = layerManager
  }

  get map() { return this._map }

  project(lngLat) {
    return this._map.project(lngLat)
  }

  destroy() {
    this._map?.remove()
  }
}
