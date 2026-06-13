/**
 * MilitaryGrid — MGRS / UTM grid overlay drawn on a canvas.
 *
 * Canvas sits below agent markers (z-index 8).
 * Redraws on every MapLibre 'render' event.
 * Grid spacing adapts to zoom: 100 km → 10 km → 1 km → 100 m.
 */

// ── WGS84 constants ───────────────────────────────────────────────────────────
const _A   = 6378137.0
const _F   = 1 / 298.257223563
const _B   = _A * (1 - _F)
const _E2  = 2*_F - _F*_F          // first eccentricity squared
const _EP2 = _E2 / (1 - _E2)       // second eccentricity squared
const _K0  = 0.9996
const _DEG = Math.PI / 180

// ── UTM forward (lat/lon → UTM) ───────────────────────────────────────────────
function toUTM(latDeg, lonDeg) {
  const lat = latDeg * _DEG
  const lon = lonDeg * _DEG
  const zone = Math.floor((lonDeg + 180) / 6) + 1
  const lon0 = ((zone - 1) * 6 - 180 + 3) * _DEG

  const N  = _A / Math.sqrt(1 - _E2 * Math.sin(lat)**2)
  const T  = Math.tan(lat)**2
  const C  = _EP2 * Math.cos(lat)**2
  const Av = Math.cos(lat) * (lon - lon0)

  const e2 = _E2, e4 = e2*e2, e6 = e4*e2
  const M = _A * (
    (1 - e2/4 - 3*e4/64 - 5*e6/256)          * lat
    - (3*e2/8 + 3*e4/32 + 45*e6/1024)        * Math.sin(2*lat)
    + (15*e4/256 + 45*e6/1024)               * Math.sin(4*lat)
    - (35*e6/3072)                            * Math.sin(6*lat)
  )

  const E = _K0 * N * (Av + (1-T+C)*Av**3/6 + (5-18*T+T**2+72*C-58*_EP2)*Av**5/120) + 500000
  let  Nv = _K0 * (M + N*Math.tan(lat)*(Av**2/2 + (5-T+9*C+4*C**2)*Av**4/24 + (61-58*T+T**2+600*C-330*_EP2)*Av**6/720))
  if (latDeg < 0) Nv += 10000000

  return { zone, easting: E, northing: Nv }
}

// ── UTM inverse (UTM → lat/lon) ───────────────────────────────────────────────
function fromUTM(easting, northing, zone, isNorth) {
  const x  = easting - 500000
  const y  = isNorth ? northing : northing - 10000000
  const e1 = (1 - Math.sqrt(1-_E2)) / (1 + Math.sqrt(1-_E2))
  const M  = y / _K0
  const mu = M / (_A * (1 - _E2/4 - 3*_E2**2/64 - 5*_E2**3/256))

  const phi1 = mu
    + (3*e1/2     - 27*e1**3/32)  * Math.sin(2*mu)
    + (21*e1**2/16 - 55*e1**4/32) * Math.sin(4*mu)
    + (151*e1**3/96)               * Math.sin(6*mu)
    + (1097*e1**4/512)             * Math.sin(8*mu)

  const sp  = Math.sin(phi1), cp = Math.cos(phi1)
  const N1  = _A / Math.sqrt(1 - _E2*sp**2)
  const T1  = Math.tan(phi1)**2
  const C1  = _EP2 * cp**2
  const R1  = _A * (1-_E2) / Math.pow(1 - _E2*sp**2, 1.5)
  const D   = x / (N1 * _K0)

  const lat = phi1 - (N1*Math.tan(phi1)/R1) * (
      D**2/2
    - (5+3*T1+10*C1-4*C1**2-9*_EP2)*D**4/24
    + (61+90*T1+298*C1+45*T1**2-252*_EP2-3*C1**2)*D**6/720
  )
  const lon0 = ((zone-1)*6 - 180 + 3) * _DEG
  const lon  = lon0 + (
      D - (1+2*T1+C1)*D**3/6
    + (5-2*C1+28*T1-3*C1**2+8*_EP2+24*T1**2)*D**5/120
  ) / cp

  return { lat: lat/_DEG, lon: lon/_DEG }
}

// ── MGRS label helpers ────────────────────────────────────────────────────────

const _ROW_LETTERS = 'ABCDEFGHJKLMNPQRSTUV'   // 20, no I or O
// Column letters by zone set (zone%3 → set index)
const _COL_SETS = [
  'STUVWXYZ',   // zone%3=0  (e.g., zones 3,6,...,33,...)
  'ABCDEFGH',   // zone%3=1  (e.g., zones 1,4,...,31,...)
  'JKLMNPQR',   // zone%3=2  (e.g., zones 2,5,...,32,...)
]
const _LAT_BANDS = 'CDEFGHJKLMNPQRSTUVWX'  // 20, no I or O

function _latBand(latDeg) {
  return _LAT_BANDS[Math.max(0, Math.min(19, Math.floor((latDeg + 80) / 8)))]
}

function _col100(easting, zone) {
  const letters = _COL_SETS[zone % 3]
  const idx = Math.max(0, Math.min(7, Math.floor(easting / 100000) - 1))
  return letters[idx]
}

function _row100(northing, zone) {
  const base = (zone % 2 === 0) ? 5 : 0   // even zones start at F (index 5)
  return _ROW_LETTERS[(Math.floor(northing / 100000) + base) % 20]
}

// Format coordinates within a 100km square for the given grid step
function _innerRef(easting, northing, step) {
  const eRef = Math.round(easting) % 100000
  const nRef = Math.round(northing) % 100000
  if (step >= 100000) return ''
  if (step >= 10000) {
    return `${Math.floor(eRef/10000)}${Math.floor(nRef/10000)}`
  }
  if (step >= 1000) {
    return `${String(Math.floor(eRef/1000)).padStart(2,'0')}${String(Math.floor(nRef/1000)).padStart(2,'0')}`
  }
  return `${String(Math.floor(eRef/100)).padStart(3,'0')}${String(Math.floor(nRef/100)).padStart(3,'0')}`
}

// ── Grid spacing per zoom ─────────────────────────────────────────────────────
function _spacing(zoom) {
  if (zoom >= 14) return    100
  if (zoom >= 12) return   1000
  if (zoom >= 10) return  10000
  if (zoom >= 7)  return 100000
  return null   // too zoomed out
}

// ── MilitaryGrid class ────────────────────────────────────────────────────────

export class MilitaryGrid {
  constructor(mapContainer, map) {
    this._map       = map
    this._container = mapContainer
    this._enabled   = false

    this._canvas = document.createElement('canvas')
    this._canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:8;'
    mapContainer.appendChild(this._canvas)
    this._ctx = this._canvas.getContext('2d')

    this._onRender = () => this._draw()
    this._onResize = () => this._resize()
    this._resize()
    window.addEventListener('resize', this._onResize)
  }

  get enabled() { return this._enabled }

  toggle() {
    this._enabled = !this._enabled
    if (this._enabled) {
      this._map.on('render', this._onRender)
      this._draw()
    } else {
      this._map.off('render', this._onRender)
      this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height)
    }
    return this._enabled
  }

  destroy() {
    this._map.off('render', this._onRender)
    window.removeEventListener('resize', this._onResize)
    this._canvas.remove()
  }

  // ── Internal ────────────────────────────────────────────────────────────────

  _resize() {
    this._canvas.width  = this._container.offsetWidth
    this._canvas.height = this._container.offsetHeight
  }

  _draw() {
    const { width, height } = this._canvas
    const ctx  = this._ctx
    ctx.clearRect(0, 0, width, height)

    const zoom    = this._map.getZoom()
    const spacing = _spacing(zoom)
    if (!spacing) return

    const bounds  = this._map.getBounds()
    const centerLat = (bounds.getNorth() + bounds.getSouth()) / 2
    const centerLon = (bounds.getEast()  + bounds.getWest())  / 2
    const { zone }  = toUTM(centerLat, centerLon)
    const isNorth   = centerLat >= 0

    // UTM extents of visible area (with small margin)
    const sw = toUTM(bounds.getSouth(), bounds.getWest())
    const ne = toUTM(bounds.getNorth(), bounds.getEast())
    const eMin = Math.floor(sw.easting  / spacing) * spacing
    const eMax = Math.ceil (ne.easting  / spacing) * spacing
    const nMin = Math.floor(sw.northing / spacing) * spacing
    const nMax = Math.ceil (ne.northing / spacing) * spacing

    // ── Draw northing (horizontal) lines ──────────────────────────────────────
    for (let n = nMin; n <= nMax; n += spacing) {
      const is100km = (n % 100000 === 0)
      ctx.beginPath()
      ctx.strokeStyle = is100km ? 'rgba(255,165,40,0.8)' : 'rgba(255,165,40,0.40)'
      ctx.lineWidth   = is100km ? 1.5 : 0.8

      // Sample line at 5 evenly-spaced eastings for slight curvature
      for (let i = 0; i <= 4; i++) {
        const e = eMin + (eMax - eMin) * (i / 4)
        try {
          const { lat, lon } = fromUTM(e, n, zone, isNorth)
          const pt = this._map.project([lon, lat])
          i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y)
        } catch { /* out of valid range */ }
      }
      ctx.stroke()
    }

    // ── Draw easting (vertical) lines ─────────────────────────────────────────
    for (let e = eMin; e <= eMax; e += spacing) {
      const is100km = (e % 100000 === 0)
      ctx.beginPath()
      ctx.strokeStyle = is100km ? 'rgba(255,165,40,0.8)' : 'rgba(255,165,40,0.40)'
      ctx.lineWidth   = is100km ? 1.5 : 0.8

      for (let i = 0; i <= 4; i++) {
        const n = nMin + (nMax - nMin) * (i / 4)
        try {
          const { lat, lon } = fromUTM(e, n, zone, isNorth)
          const pt = this._map.project([lon, lat])
          i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y)
        } catch { /* skip */ }
      }
      ctx.stroke()
    }

    // ── Labels ────────────────────────────────────────────────────────────────
    if (zoom < 8) return

    ctx.font         = `bold ${zoom >= 12 ? 10 : 9}px 'Courier New', monospace`
    ctx.textBaseline = 'top'
    ctx.textAlign    = 'left'

    for (let e = eMin; e <= eMax; e += spacing) {
      for (let n = nMin; n <= nMax; n += spacing) {
        const is100km = (e % 100000 === 0) && (n % 100000 === 0)
        try {
          const { lat, lon } = fromUTM(e, n, zone, isNorth)
          const pt = this._map.project([lon, lat])
          const px = pt.x + 3, py = pt.y + 2

          if (is100km && zoom >= 8) {
            // Full GZD + 100km designator
            const band = _latBand(lat)
            const col  = _col100(e, zone)
            const row  = _row100(n, zone)
            const label = `${zone}${band} ${col}${row}`
            ctx.fillStyle = 'rgba(0,0,0,0.75)'
            ctx.fillRect(px - 1, py - 1, ctx.measureText(label).width + 4, 14)
            ctx.fillStyle = '#ffaa28'
            ctx.fillText(label, px, py)
          } else if (!is100km && zoom >= 10) {
            // Inner grid reference (2-digit or 3-digit)
            const inner = _innerRef(e, n, spacing)
            if (!inner) continue
            ctx.fillStyle = 'rgba(0,0,0,0.60)'
            ctx.fillRect(px - 1, py - 1, ctx.measureText(inner).width + 3, 12)
            ctx.fillStyle = 'rgba(255,165,40,0.85)'
            ctx.fillText(inner, px, py)
          }
        } catch { /* skip */ }
      }
    }

    // ── GZD label at top-left of viewport ─────────────────────────────────────
    const band = _latBand(centerLat)
    const gzdLabel = `GZD ${zone}${band}  MGRS`
    ctx.font = 'bold 11px "Courier New", monospace'
    ctx.fillStyle = 'rgba(0,0,0,0.80)'
    ctx.fillRect(8, 8, ctx.measureText(gzdLabel).width + 10, 18)
    ctx.fillStyle = '#ffaa28'
    ctx.textBaseline = 'middle'
    ctx.fillText(gzdLabel, 13, 17)
  }
}
