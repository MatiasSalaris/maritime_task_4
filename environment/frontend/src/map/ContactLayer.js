const SRC_ACTIVE = 'contacts-active'
const SRC_GHOST  = 'contacts-ghost'
const SRC_GOD    = 'contacts-god'

const LAYER_ACTIVE_HALO   = 'layer-contacts-active-halo'
const LAYER_ACTIVE_CIRCLE = 'layer-contacts-active-circle'
const LAYER_ACTIVE_LABEL  = 'layer-contacts-active-label'
const LAYER_ACTIVE_TYPE   = 'layer-contacts-active-type'

const LAYER_GHOST_RING    = 'layer-contacts-ghost-ring'
const LAYER_GHOST_FILL    = 'layer-contacts-ghost-fill'
const LAYER_GHOST_LABEL   = 'layer-contacts-ghost-label'

const LAYER_GOD_RING      = 'layer-contacts-god-ring'
const LAYER_GOD_CIRCLE    = 'layer-contacts-god-circle'
const LAYER_GOD_LABEL     = 'layer-contacts-god-label'

const COLOR_BY_LABEL = [
  'match', ['get', 'label'],
  'AIS_COMMERCIAL', '#4ea0ff',
  'AIS_FISHING',    '#7fe0a0',
  'UNKNOWN',        '#ff5a3c',
  '#ff3355',
]

function haversineKm(aLat, aLon, bLat, bLon) {
  const R = 6371.0
  const dLat = (bLat - aLat) * Math.PI / 180
  const dLon = (bLon - aLon) * Math.PI / 180
  const s = Math.sin(dLat / 2) ** 2 +
    Math.cos(aLat * Math.PI / 180) * Math.cos(bLat * Math.PI / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(s))
}

function timeAgo(seconds) {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60)   return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

function emptyFC() {
  return { type: 'FeatureCollection', features: [] }
}

export class ContactLayer {
  /**
   * @param {Object} map
   * @param {Object} animCanvas - AnimationCanvas for detection pings
   */
  constructor(map, animCanvas) {
    this._map        = map
    this._animCanvas = animCanvas
    // client-side track memory: id → { natoId, firstSeen, lastSeen, lastPos }
    this._tracks     = new Map()
    this._natoCount  = 0
    // cached at data rate; consumed at 60 fps in renderFrame()
    this._contacts   = []
    this._godView    = false
    this._worldTime  = 0
  }

  setAnimCanvas(c) { this._animCanvas = c }

  /** Wipe all track memory (call on demo/world reset). */
  reset() {
    this._tracks.clear()
    this._natoCount = 0
  }

  init() {
    // ── ACTIVE ────────────────────────────────────────────────────────────────
    this._map.addSource(SRC_ACTIVE, { type: 'geojson', data: emptyFC() })

    // pulsing halo behind active contacts (shows it's "lit up" by a sensor)
    this._map.addLayer({
      id: LAYER_ACTIVE_HALO,
      type: 'circle',
      source: SRC_ACTIVE,
      paint: {
        'circle-radius': ['case', ['get', 'flagged'], 16, 13],
        'circle-color': COLOR_BY_LABEL,
        'circle-opacity': 0.18,
        'circle-blur': 0.6,
      },
    })

    this._map.addLayer({
      id: LAYER_ACTIVE_CIRCLE,
      type: 'circle',
      source: SRC_ACTIVE,
      paint: {
        'circle-radius': ['case', ['get', 'flagged'], 7, 5],
        'circle-color': COLOR_BY_LABEL,
        'circle-opacity': 1.0,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.6,
      },
    })

    this._map.addLayer({
      id: LAYER_ACTIVE_LABEL,
      type: 'symbol',
      source: SRC_ACTIVE,
      layout: {
        'text-field': ['coalesce', ['get', 'nato_id'], ['get', 'label']],
        'text-size': 11,
        'text-offset': [0, 1.3],
        'text-anchor': 'top',
        'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': '#0a0e1a',
        'text-halo-width': 1.6,
      },
    })

    this._map.addLayer({
      id: LAYER_ACTIVE_TYPE,
      type: 'symbol',
      source: SRC_ACTIVE,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 8,
        'text-offset': [0, 2.6],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#9fc0d0',
        'text-halo-color': '#0a0e1a',
        'text-halo-width': 1,
      },
    })

    // ── GHOST ─────────────────────────────────────────────────────────────────
    this._map.addSource(SRC_GHOST, { type: 'geojson', data: emptyFC() })

    this._map.addLayer({
      id: LAYER_GHOST_RING,
      type: 'circle',
      source: SRC_GHOST,
      paint: {
        'circle-radius': 9,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': '#8a99aa',
        'circle-stroke-width': 1.4,
        'circle-stroke-opacity': 0.55,
      },
    })

    this._map.addLayer({
      id: LAYER_GHOST_FILL,
      type: 'circle',
      source: SRC_GHOST,
      paint: {
        'circle-radius': 4,
        'circle-color': '#8a99aa',
        'circle-opacity': 0.45,
      },
    })

    this._map.addLayer({
      id: LAYER_GHOST_LABEL,
      type: 'symbol',
      source: SRC_GHOST,
      layout: {
        'text-field': ['format',
          ['coalesce', ['get', 'nato_id'], '?'], {},
          '\n', {},
          ['get', 'time_ago'], { 'font-scale': 0.82 },
        ],
        'text-size': 10,
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
        'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
      },
      paint: {
        'text-color': '#8a99aa',
        'text-halo-color': '#0a0e1a',
        'text-halo-width': 1.2,
      },
    })

    // ── GOD VIEW (undetected) ──────────────────────────────────────────────────
    this._map.addSource(SRC_GOD, { type: 'geojson', data: emptyFC() })

    // Outer dashed "untracked" ring — clearly visible but distinct from a
    // sensor-confirmed (filled, white-edged) active contact.
    this._map.addLayer({
      id: LAYER_GOD_RING,
      type: 'circle',
      source: SRC_GOD,
      paint: {
        'circle-radius': ['case', ['get', 'flagged'], 11, 9],
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': COLOR_BY_LABEL,
        'circle-stroke-width': 1.6,
        'circle-stroke-opacity': 0.85,
      },
    })

    this._map.addLayer({
      id: LAYER_GOD_CIRCLE,
      type: 'circle',
      source: SRC_GOD,
      paint: {
        'circle-radius': ['case', ['get', 'flagged'], 5, 4],
        'circle-color': COLOR_BY_LABEL,
        'circle-opacity': 0.55,
      },
    })

    this._map.addLayer({
      id: LAYER_GOD_LABEL,
      type: 'symbol',
      source: SRC_GOD,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 9,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#aab8c6',
        'text-halo-color': '#0a0e1a',
        'text-halo-width': 1.2,
      },
    })
  }

  _assignNato(contact) {
    this._natoCount += 1
    const n = String(this._natoCount).padStart(3, '0')
    if (contact.flagged) return `TGT-${n}`
    if (contact.mmsi)    return `AIS-${n}`
    return `UNK-${n}`
  }

  /** Cache the latest data-rate snapshot; detection happens in renderFrame(). */
  update(contacts, godView, worldTime) {
    this._contacts  = contacts ?? []
    this._godView   = godView
    this._worldTime = worldTime ?? (Date.now() / 1000)
  }

  /**
   * Detect + reveal contacts at the interpolated agent positions (~60 fps), so
   * a contact is shown exactly when it falls inside a drawn sensor ring.
   * @param {Object} disp - {id: {lon, lat, range}} interpolated agent positions
   */
  renderFrame(disp) {
    const now    = this._worldTime
    const godView = this._godView
    const agents = Object.values(disp ?? {})

    const active = []
    const ghost  = []
    const god    = []

    for (const c of this._contacts) {
      const detected = agents.some(a =>
        haversineKm(a.lat, a.lon, c.position.lat, c.position.lon) <= (a.range ?? 4.0)
      )

      let track = this._tracks.get(c.id)

      if (detected) {
        if (!track) {
          // NEW detection → assign NATO id + fire red ping
          track = {
            natoId: this._assignNato(c),
            firstSeen: now,
            lastSeen: now,
            lastPos: { lon: c.position.lon, lat: c.position.lat },
          }
          this._tracks.set(c.id, track)
          this._animCanvas?.addPing({ lon: c.position.lon, lat: c.position.lat }, '#ff3344')
        }
        track.lastSeen = now
        track.lastPos  = { lon: c.position.lon, lat: c.position.lat }

        active.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [c.position.lon, c.position.lat] },
          properties: {
            id: c.id, label: c.label, flagged: !!c.flagged,
            nato_id: track.natoId,
          },
        })
      } else if (godView) {
        // GOD VIEW: reveal the contact at its TRUE current position, whether it
        // was ever tracked or not. Keeps a known track's NATO id as the label.
        god.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [c.position.lon, c.position.lat] },
          properties: {
            id: c.id,
            label: track ? track.natoId : c.label,
            flagged: !!c.flagged,
          },
        })
      } else if (track) {
        // Fog of war: previously seen but now lost → GHOST at last known position
        ghost.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [track.lastPos.lon, track.lastPos.lat] },
          properties: {
            id: c.id, label: c.label, flagged: !!c.flagged,
            nato_id: track.natoId,
            time_ago: timeAgo(now - track.lastSeen),
          },
        })
      }
    }

    this._map.getSource(SRC_ACTIVE)?.setData({ type: 'FeatureCollection', features: active })
    this._map.getSource(SRC_GHOST)?.setData({ type: 'FeatureCollection', features: ghost })
    this._map.getSource(SRC_GOD)?.setData({ type: 'FeatureCollection', features: god })
  }

  teardown() {
    const layers = [
      LAYER_ACTIVE_HALO, LAYER_ACTIVE_CIRCLE, LAYER_ACTIVE_LABEL, LAYER_ACTIVE_TYPE,
      LAYER_GHOST_RING, LAYER_GHOST_FILL, LAYER_GHOST_LABEL,
      LAYER_GOD_RING, LAYER_GOD_CIRCLE, LAYER_GOD_LABEL,
    ]
    const sources = [SRC_ACTIVE, SRC_GHOST, SRC_GOD]
    for (const l of layers)  if (this._map.getLayer(l))  this._map.removeLayer(l)
    for (const s of sources) if (this._map.getSource(s)) this._map.removeSource(s)
  }
}
