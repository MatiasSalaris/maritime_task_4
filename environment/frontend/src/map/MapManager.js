import maplibregl from 'maplibre-gl'
import { OVERLAY_MAP } from './overlays/index.js'

const DEMO_CENTER = [15.14, 37.50]  // Strait of Sicily
const DEMO_ZOOM   = 10

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

  async switchOverlay(overlayId) {
    if (overlayId === this._overlayId) return
    const overlay = OVERLAY_MAP[overlayId]
    if (!overlay) return

    this._overlayId = overlayId
    const center = this._map.getCenter()
    const zoom   = this._map.getZoom()

    // Tear down all custom layers before style swap
    for (const layer of Object.values(this._layers)) layer.teardown?.()

    await new Promise(resolve => {
      this._map.once('style.load', resolve)
      this._map.setStyle(overlay.style)
    })

    this._map.setCenter(center)
    this._map.setZoom(zoom)

    // Re-init all custom layers
    for (const layer of Object.values(this._layers)) layer.init?.()
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
