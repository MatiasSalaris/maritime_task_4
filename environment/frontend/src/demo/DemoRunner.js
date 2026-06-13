/**
 * DemoRunner — 3-phase scripted demo
 *
 * Phase 1 (0-8s):   all agents STATIONARY; mission set, CoT streams, P2P coordination
 * Phase 2 (8-38s):  agents sweep sectors; contact detection + intercept negotiation
 * Phase 3 (38-46s): mid-mission intent change; swarm re-coordinates and redirects
 *
 * Movement: Catmull-Rom spline interpolation → smooth turns at every waypoint
 * Planned path: dynamically trimmed as agent progresses → dashed line "converts" to solid trail
 */

// ── Timed waypoints [time_ms, lat, lon] ──────────────────────────────────────
// All agents hold at starting position until t=8000 (planning phase).
const PATHS = {
  agent_0: [                              // Alpha — WEST sector
    [0,     37.505, 15.070],              // hold during planning
    [8000,  37.505, 15.070],              // movement begins
    [18000, 37.555, 15.025],             // sweep NW
    [30000, 37.455, 15.025],             // sweep S
    [38000, 37.455, 15.075],             // sweep E  ← mission change
    [46000, 37.555, 15.075],             // redirect N
  ],
  agent_1: [                              // Bravo — CENTRAL sector
    [0,     37.490, 15.160],
    [8000,  37.490, 15.160],
    [18000, 37.555, 15.115],             // sweep N
    [30000, 37.450, 15.115],             // sweep S
    [37000, 37.450, 15.160],             // sweep E — near suspicious vessel
    [38000, 37.505, 15.145],             // redirect at mission change
    [46000, 37.575, 15.195],             // redirect NE
  ],
  agent_2: [                              // Charlie — EAST sector
    [0,     37.545, 15.170],
    [8000,  37.545, 15.170],
    [18000, 37.545, 15.245],             // sweep E
    [30000, 37.455, 15.245],             // sweep S
    [37000, 37.455, 15.195],             // sweep W — suspicious vessel area
    [38000, 37.460, 15.190],             // hold near suspicious vessel
    [46000, 37.530, 15.140],             // converge W
  ],
}

// ── Script ────────────────────────────────────────────────────────────────────
const SCRIPT = [
  // Phase 1: coordination (agents stationary)
  [  400, null,      'mission',
    'Pattuglia lo Stretto di Sicilia. Identifica e traccia qualsiasi unità senza transponder AIS valido.'],

  [  900, 'agent_0', 'task',    'Analisi missione, proposta assegnazione settori'],
  [ 1000, 'agent_0', 'cot',
    'Missione ricevuta. Tre asset disponibili: divido la zona di pattuglia in settori per copertura completa senza sovrapposizioni.\n'],
  [ 2500, 'agent_0', 'cot',
    'Proposta: Alpha → OVEST (lon 15.00-15.10), Bravo → CENTRO (15.10-15.19), Charlie → EST (15.19-15.28).\n'],
  [ 3500, 'agent_0', 'msg',
    ['all', 'proposal',
     { sectors: { agent_0:'WEST', agent_1:'CENTRAL', agent_2:'EAST' } },
     'La divisione in settori riduce le sovrapposizioni e garantisce copertura completa dell’AOR.']],

  [ 4300, 'agent_1', 'cot',
    'Proposta di Alpha ricevuta. Il settore CENTRO è coerente con la mia posizione attuale. Accetto.\n'],
  [ 5100, 'agent_1', 'task',    'Pattuglia settore CENTRO'],
  [ 5200, 'agent_1', 'msg',
    ['agent_0', 'ack', { sector:'CENTRAL' }, 'Settore centrale ottimale: confermo.']],

  [ 5600, 'agent_2', 'cot',
    'Proposta di Alpha valutata. Il settore EST è adatto alla mia rotta. Accetto.\n'],
  [ 6300, 'agent_2', 'task',    'Pattuglia settore EST'],
  [ 6400, 'agent_2', 'msg',
    ['agent_0', 'ack', { sector:'EAST' }, 'Settore est accettato. Avvio la scansione.']],

  [ 7700, 'agent_0', 'cot',
    'Tutti i peer hanno confermato. Sciame pronto: avvio la scansione del settore ovest.\n'],

  // Phase 2: patrol + contact event (movement started at t=8 000)
  [14000, 'agent_2', 'cot',
    'Contatto sospetto rilevato: nessuna identità AIS visibile e movimento anomalo per l’area.\n'],
  [15200, 'agent_2', 'msg',
    ['all', 'status',
     { contact:'suspicious_vessel', assessment:'needs_identification' },
     'Il contatto non corrisponde a un normale profilo commerciale AIS.']],

  [16000, 'agent_1', 'cot',
    'Charlie ha segnalato un contatto sospetto. Posso lasciare brevemente il CENTRO per identificarlo.\n'],
  [17000, 'agent_1', 'msg',
    ['agent_2', 'proposal',
     { action:'identify_suspicious_vessel' },
     'Richiedo passaggio: Bravo può identificare il contatto sospetto mentre Charlie mantiene la copertura del settore.']],

  [17600, 'agent_2', 'cot',
    'Richiesta di intercetto da Bravo ricevuta. La deviazione è efficiente: approvo.\n'],
  [18200, 'agent_2', 'msg',
    ['agent_1', 'ack',
     { action:'identify_suspicious_vessel' },
     'Approvato. Bravo identifica il contatto sospetto; Charlie mantiene il settore est.']],
  [18800, 'agent_1', 'task',   'Identifica contatto sospetto'],
  [19000, 'agent_1', 'cot',
    'Autorizzazione ricevuta. Correggo la rotta per identificare il contatto sospetto nella finestra di scansione corrente.\n'],

  // Phase 3: mission change at t=38 000
  [38000, null,      'mission_change',
    'CAMBIO DI INTENTO: estendere la pattuglia al settore nord. Priorità a qualsiasi unità senza transponder AIS: intercettare e seguire.'],

  [38600, 'agent_0', 'cot',
    'CAMBIO MISSIONE RICEVUTO\nNuovo obiettivo: estensione a nord, priorità ai contatti senza transponder.\nRitrasmetto l’intento aggiornato a tutti i peer.\n'],
  [39600, 'agent_0', 'msg',
    ['all', 'handoff',
     { update:'northern_extension', priority:'no_transponder' },
     'Missione aggiornata: riallocazione dei settori per copertura nord.']],

  [40400, 'agent_1', 'cot',
    'Cambio missione ricevuto. Passo il monitoraggio del contatto sospetto a Charlie e procedo verso nord.\n'],
  [41200, 'agent_1', 'msg',
    ['agent_2', 'handoff',
     { task:'monitor_suspicious_vessel' },
     'Passo il monitoraggio del contatto sospetto a Charlie. Bravo procede verso il settore nord.']],

  [41800, 'agent_2', 'cot',
    'Passaggio confermato. Monitoro il contatto sospetto. Bravo libero di procedere a nord.\n'],
  [42500, 'agent_2', 'task',   'Monitora contatto sospetto'],
  [42600, 'agent_2', 'msg',
    ['agent_1', 'ack',
     { task:'monitor_suspicious_vessel' },
     'Charlie monitora il contatto sospetto. Bravo proceda a nord.']],

  [43200, 'agent_1', 'task',   'Pattuglia estesa a nord'],
  [44000, 'agent_0', 'cot',
    'Sciame riallineato sul nuovo intento. Tutti i settori coperti. Estensione nord attiva.\n'],
]

const TOTAL_DURATION_MS = 47000
const PATH_INTERVAL_MS  = 50    // warp_to fire rate
const PLAN_REVEAL_MS    = 7800  // planned-path overlay hidden until planning phase ends
const PLAN_UPDATE_MS    = 500   // planned-path refresh rate (throttled)

// ── Catmull-Rom spline helpers ────────────────────────────────────────────────

function _cmComp(p0, p1, p2, p3, t) {
  const t2 = t*t, t3 = t2*t
  return 0.5 * ((2*p1) + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t2 + (-p0+3*p1-3*p2+p3)*t3)
}

/**
 * Interpolate position along PATHS[agentId] at timeMs using Catmull-Rom.
 * Hold segments (start == end position) are returned directly to avoid drift.
 */
function catmullAt(pts, timeMs) {
  if (!pts || pts.length === 0) return null
  for (let i = 0; i < pts.length - 1; i++) {
    const [t0, lat0, lon0] = pts[i]
    const [t1, lat1, lon1] = pts[i+1]
    if (timeMs >= t0 && timeMs <= t1) {
      // Hold segment — no movement
      if (Math.abs(lat0-lat1) < 1e-8 && Math.abs(lon0-lon1) < 1e-8) {
        return { lat: lat0, lon: lon0 }
      }
      const f = (timeMs - t0) / (t1 - t0)
      const [, p0lat, p0lon] = pts[Math.max(0, i-1)]
      const [, p3lat, p3lon] = pts[Math.min(pts.length-1, i+2)]
      return {
        lat: _cmComp(p0lat, lat0, lat1, p3lat, f),
        lon: _cmComp(p0lon, lon0, lon1, p3lon, f),
      }
    }
  }
  const last = pts[pts.length-1]
  return { lat: last[1], lon: last[2] }
}

/** Heading derived from spline tangent (finite difference, 150ms ahead). */
function catmullHeading(pts, timeMs) {
  const end = pts[pts.length-1][0]
  const p1 = catmullAt(pts, timeMs)
  const p2 = catmullAt(pts, Math.min(timeMs + 150, end))
  if (!p1 || !p2) return 0
  const dLat = p2.lat - p1.lat, dLon = p2.lon - p1.lon
  if (Math.abs(dLat) < 1e-9 && Math.abs(dLon) < 1e-9) return 0
  return (Math.atan2(dLon, dLat) * 180 / Math.PI + 360) % 360
}

/**
 * Generate splined planned-path points from fromTimeMs to end of PATHS.
 * Points are sampled every stepMs ms along the Catmull-Rom curve.
 * Returns [] when fromTimeMs is before PLAN_REVEAL_MS.
 */
function splinedPath(pts, fromTimeMs, stepMs = 500) {
  const end = pts[pts.length-1][0]
  const out  = []
  for (let t = fromTimeMs + stepMs; t <= end; t += stepMs) {
    const pos = catmullAt(pts, t)
    if (pos) out.push({ lat: pos.lat, lon: pos.lon })
  }
  return out
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

// ── DemoRunner ────────────────────────────────────────────────────────────────

export class DemoRunner {
  constructor() {
    this._ws             = {}
    this._timeouts       = []
    this._interval       = null
    this._running        = false
    this._lastPlanUpdate = -PLAN_UPDATE_MS  // force first update immediately
  }

  get running() { return this._running }

  async start() {
    if (this._running) return
    this._running = true
    this._lastPlanUpdate = -PLAN_UPDATE_MS

    // Reset backend state: clear path history, CoT, tasks, mission, message log
    try {
      await fetch('/api/reset', { method: 'POST' })
    } catch (e) {
      console.warn('[Demo] reset failed:', e)
    }

    try {
      await this._connectAll()
    } catch (e) {
      console.error('[Demo] WS connect failed:', e)
      this._running = false
      return
    }

    // Freeze physics + clear any pre-existing planned paths
    for (const id of Object.keys(PATHS)) {
      this._send(id, { type: 'action', payload: { speed_kn: 0, planned_path: [] } })
    }

    // Position + planned-path update loop
    const startTime = Date.now()
    this._interval = setInterval(() => {
      if (!this._running) return
      const elapsed = Date.now() - startTime

      // ── Position (20 Hz) ──────────────────────────────────────────────────
      for (const id of Object.keys(PATHS)) {
        const pos     = catmullAt(PATHS[id], elapsed)
        const heading = catmullHeading(PATHS[id], elapsed)
        if (pos) this._send(id, { type: 'action', payload: { warp_to: pos, heading } })
      }

      // ── Planned path (throttled, ~2 Hz) ───────────────────────────────────
      if (elapsed - this._lastPlanUpdate >= PLAN_UPDATE_MS) {
        this._lastPlanUpdate = elapsed
        for (const id of Object.keys(PATHS)) {
          const plan = elapsed >= PLAN_REVEAL_MS
            ? splinedPath(PATHS[id], elapsed)
            : []
          this._send(id, { type: 'action', payload: { planned_path: plan } })
        }
      }

      if (elapsed >= TOTAL_DURATION_MS) this._stopPath()
    }, PATH_INTERVAL_MS)

    // Scripted events
    for (const [t, agentId, action, args] of SCRIPT) {
      this._schedule(t, () => this._exec(agentId, action, args))
    }

    // Auto-stop
    this._schedule(TOTAL_DURATION_MS + 1000, () => this.stop())
  }

  stop() {
    this._running = false
    this._stopPath()
    this._timeouts.forEach(clearTimeout)
    this._timeouts = []
    for (const ws of Object.values(this._ws)) ws.close()
    this._ws = {}
  }

  // ── Private ──────────────────────────────────────────────────────────────────

  _stopPath() {
    if (this._interval) { clearInterval(this._interval); this._interval = null }
  }

  _schedule(delayMs, fn) {
    this._timeouts.push(setTimeout(() => { if (this._running) fn() }, delayMs))
  }

  async _connectAll() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    await Promise.all(
      Object.keys(PATHS).map(id => new Promise((resolve, reject) => {
        const ws = new WebSocket(`${proto}://${location.host}/ws/agent/${id}`)
        ws.onopen    = () => { this._ws[id] = ws; resolve() }
        ws.onerror   = () => reject(new Error(`WS failed for ${id}`))
        ws.onmessage = () => {}
      }))
    )
    console.info('[Demo] all three agent WS connections open')
  }

  _send(agentId, payload) {
    const ws = this._ws[agentId]
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload))
  }

  async _exec(agentId, action, args) {
    switch (action) {
      case 'mission':
        await fetch('/api/mission', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: args }),
        })
        break

      case 'mission_change':
        await fetch('/api/mission/change', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: args }),
        })
        break

      case 'task':
        this._send(agentId, { type: 'action', payload: { current_task: args } })
        break

      case 'cot':
        await this._streamCot(agentId, args)
        break

      case 'msg': {
        const [to, msgType, content, reasoning] = args
        this._send(agentId, { type: 'p2p_message', payload: { to, msg_type: msgType, content, reasoning } })
        break
      }
    }
  }

  async _streamCot(agentId, text) {
    const tokens = text.split(/(\s+)/)
    for (const token of tokens) {
      if (!this._running) return
      this._send(agentId, { type: 'cot_chunk', payload: { chunk: token } })
      if (token.trim().length > 0) await sleep(60)
    }
  }
}
