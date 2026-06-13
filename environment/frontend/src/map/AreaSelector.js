/**
 * AreaSelector — interactive map drawing tool.
 *
 * Modes: 'rect' | 'circle' | 'poly'
 *
 * While drawing, map pan/scroll is disabled and a preview is drawn on a
 * temporary canvas.  On completion, `onChange(geojsonPolygon)` is called.
 */

export class AreaSelector {
  /**
   * @param {object}   map        - MapLibre map instance
   * @param {Element}  container  - map container div
   * @param {Function} onChange   - called with GeoJSON Polygon coordinates or null
   */
  constructor(map, container, onChange) {
    this._map      = map
    this._ctr      = container
    this._onChange = onChange
    this._mode     = null       // 'rect' | 'circle' | 'poly'
    this._state    = null       // drawing state
    this._pts      = []         // poly points (screen {x,y})

    // Temporary preview canvas
    this._canvas = document.createElement('canvas')
    this._canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:100;display:none;'
    container.appendChild(this._canvas)
    this._ctx = this._canvas.getContext('2d')

    // Bound handlers
    this._onDown  = e => this._handleDown(e)
    this._onMove  = e => this._handleMove(e)
    this._onUp    = e => this._handleUp(e)
    this._onClick = e => this._handleClick(e)
    this._onDbl   = e => this._handleDbl(e)
    this._onKey   = e => { if (e.key === 'Escape') this.cancel() }
  }

  get mode() { return this._mode }

  /** Activate a drawing mode. Call again with same mode to deactivate. */
  setMode(mode) {
    if (this._mode === mode) { this.cancel(); return }
    this.cancel()

    this._mode  = mode
    this._state = null
    this._pts   = []

    this._resizeCanvas()
    this._canvas.style.display = 'block'
    this._map.getCanvas().style.cursor = 'crosshair'
    this._map.dragPan.disable()
    this._map.scrollZoom.disable()

    if (mode === 'poly') {
      this._ctr.addEventListener('click',   this._onClick)
      this._ctr.addEventListener('dblclick',this._onDbl)
      this._ctr.addEventListener('mousemove', this._onMove)
    } else {
      this._ctr.addEventListener('mousedown', this._onDown)
      this._ctr.addEventListener('mousemove', this._onMove)
      window.addEventListener('mouseup', this._onUp)
    }
    window.addEventListener('keydown', this._onKey)
  }

  /** Abort current drawing without emitting a result. */
  cancel() {
    this._removeListeners()
    this._mode  = null
    this._state = null
    this._pts   = []
    this._canvas.style.display = 'none'
    this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height)
    this._map.getCanvas().style.cursor = ''
    this._map.dragPan.enable()
    this._map.scrollZoom.enable()
  }

  destroy() {
    this.cancel()
    window.removeEventListener('keydown', this._onKey)
    this._canvas.remove()
  }

  // ── Event handlers ─────────────────────────────────────────────────────────

  _handleDown(e) {
    if (e.button !== 0) return
    const { x, y } = this._pos(e)
    this._state = { x0: x, y0: y, x1: x, y1: y }
  }

  _handleMove(e) {
    if (!this._state && this._mode !== 'poly') return
    const { x, y } = this._pos(e)

    if (this._mode !== 'poly') {
      this._state.x1 = x
      this._state.y1 = y
    }
    this._drawPreview(x, y)
  }

  _handleUp(e) {
    if (!this._state) return
    const { x, y } = this._pos(e)
    this._state.x1 = x
    this._state.y1 = y

    const geo = this._mode === 'rect'
      ? this._rectGeo()
      : this._circleGeo()

    if (geo) this._emit(geo)
    this.cancel()
  }

  _handleClick(e) {
    if (e.detail > 1) return   // ignore clicks that are part of a double-click
    const { x, y } = this._pos(e)
    this._pts.push({ x, y })
    this._drawPreview(x, y)
  }

  _handleDbl(e) {
    if (this._pts.length < 3) return
    const geo = this._polyGeo()
    if (geo) this._emit(geo)
    this.cancel()
  }

  // ── Geometry builders (screen → map lngLat → GeoJSON) ─────────────────────

  _screenToLngLat(x, y) {
    return this._map.unproject([x, y])
  }

  _rectGeo() {
    const { x0, y0, x1, y1 } = this._state
    const sw = this._screenToLngLat(Math.min(x0,x1), Math.max(y0,y1))
    const ne = this._screenToLngLat(Math.max(x0,x1), Math.min(y0,y1))
    if (Math.abs(sw.lng-ne.lng) < 0.001 || Math.abs(sw.lat-ne.lat) < 0.001) return null
    // CW winding (hole convention)
    return [
      [sw.lng, sw.lat], [sw.lng, ne.lat],
      [ne.lng, ne.lat], [ne.lng, sw.lat],
      [sw.lng, sw.lat],
    ]
  }

  _circleGeo(steps = 64) {
    const { x0, y0, x1, y1 } = this._state
    const cx = x0, cy = y0
    const r  = Math.hypot(x1-x0, y1-y0)
    if (r < 5) return null
    const coords = []
    for (let i = 0; i <= steps; i++) {
      const a = (i / steps) * 2 * Math.PI
      const ll = this._screenToLngLat(cx + r*Math.cos(a), cy + r*Math.sin(a))
      coords.push([ll.lng, ll.lat])
    }
    return coords
  }

  _polyGeo() {
    const coords = this._pts.map(p => {
      const ll = this._screenToLngLat(p.x, p.y)
      return [ll.lng, ll.lat]
    })
    coords.push(coords[0])  // close ring
    return coords
  }

  _emit(ring) {
    this._onChange({
      type: 'Polygon',
      coordinates: [ring],
    })
  }

  // ── Preview drawing ─────────────────────────────────────────────────────────

  _drawPreview(curX, curY) {
    const ctx = this._ctx
    const { width, height } = this._canvas
    ctx.clearRect(0, 0, width, height)

    ctx.strokeStyle = '#00d4ff'
    ctx.lineWidth   = 1.5
    ctx.setLineDash([6, 4])

    if (this._mode === 'rect' && this._state) {
      const { x0, y0, x1, y1 } = this._state
      ctx.strokeRect(
        Math.min(x0,x1), Math.min(y0,y1),
        Math.abs(x1-x0), Math.abs(y1-y0),
      )
      // Corner handles
      ctx.setLineDash([])
      ctx.fillStyle = 'rgba(0,212,255,0.25)'
      ctx.fillRect(Math.min(x0,x1), Math.min(y0,y1), Math.abs(x1-x0), Math.abs(y1-y0))

    } else if (this._mode === 'circle' && this._state) {
      const { x0, y0, x1, y1 } = this._state
      const r = Math.hypot(x1-x0, y1-y0)
      ctx.beginPath()
      ctx.arc(x0, y0, r, 0, Math.PI*2)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle = 'rgba(0,212,255,0.18)'
      ctx.beginPath()
      ctx.arc(x0, y0, r, 0, Math.PI*2)
      ctx.fill()

    } else if (this._mode === 'poly' && this._pts.length > 0) {
      ctx.beginPath()
      this._pts.forEach((p, i) => {
        i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)
      })
      ctx.lineTo(curX, curY)
      ctx.stroke()
      // Vertex dots
      ctx.setLineDash([])
      ctx.fillStyle = '#00d4ff'
      this._pts.forEach(p => {
        ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2); ctx.fill()
      })
    }
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  _pos(e) {
    const r = this._ctr.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  _resizeCanvas() {
    this._canvas.width  = this._ctr.offsetWidth
    this._canvas.height = this._ctr.offsetHeight
  }

  _removeListeners() {
    this._ctr.removeEventListener('mousedown',  this._onDown)
    this._ctr.removeEventListener('mousemove',  this._onMove)
    this._ctr.removeEventListener('click',      this._onClick)
    this._ctr.removeEventListener('dblclick',   this._onDbl)
    window.removeEventListener('mouseup',       this._onUp)
    window.removeEventListener('keydown',       this._onKey)
  }
}
