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
    [37000, 37.450, 15.160],             // sweep E — near c003
    [38000, 37.505, 15.145],             // redirect at mission change
    [46000, 37.575, 15.195],             // redirect NE
  ],
  agent_2: [                              // Charlie — EAST sector
    [0,     37.545, 15.170],
    [8000,  37.545, 15.170],
    [18000, 37.545, 15.245],             // sweep E
    [30000, 37.455, 15.245],             // sweep S
    [37000, 37.455, 15.195],             // sweep W — c003 area
    [38000, 37.460, 15.190],             // hold at c003
    [46000, 37.530, 15.140],             // converge W
  ],
}

// ── Script ────────────────────────────────────────────────────────────────────
const SCRIPT = [
  // Phase 1: coordination (agents stationary)
  [  400, null,      'mission',
    'Patrol the Strait of Sicily. Identify and track any vessel without a valid AIS transponder.'],

  [  900, 'agent_0', 'task',    'Analysing mission, proposing sector allocation'],
  [ 1000, 'agent_0', 'cot',
    'Mission received. Three assets available — dividing patrol zone into sectors for full coverage with no overlap.\n'],
  [ 2500, 'agent_0', 'cot',
    'Proposing: Alpha → WEST (lon 15.00-15.10), Bravo → CENTRAL (15.10-15.19), Charlie → EAST (15.19-15.28).\n'],
  [ 3500, 'agent_0', 'msg',
    ['all', 'proposal',
     { sectors: { agent_0:'WEST', agent_1:'CENTRAL', agent_2:'EAST' } },
     'Sector split minimises overlap and guarantees full AoR coverage.']],

  [ 4300, 'agent_1', 'cot',
    'Proposal from Alpha received. CENTRAL sector aligns with current position. Accepting.\n'],
  [ 5100, 'agent_1', 'task',    'Patrol sector CENTRAL'],
  [ 5200, 'agent_1', 'msg',
    ['agent_0', 'ack', { sector:'CENTRAL' }, 'Central sector optimal — acknowledged.']],

  [ 5600, 'agent_2', 'cot',
    'Alpha proposal reviewed. EAST sector suits my heading. Accepting.\n'],
  [ 6300, 'agent_2', 'task',    'Patrol sector EAST'],
  [ 6400, 'agent_2', 'msg',
    ['agent_0', 'ack', { sector:'EAST' }, 'East sector accepted. Commencing sweep.']],

  [ 7700, 'agent_0', 'cot',
    'All peers confirmed. Swarm ready — commencing western sector sweep.\n'],

  // Phase 2: patrol + contact event (movement started at t=8 000)
  [14000, 'agent_2', 'cot',
    'Contact c003 — UNKNOWN vessel, bearing 280, 18 kn, no MMSI transponder. Anomalous profile.\n'],
  [15200, 'agent_2', 'msg',
    ['all', 'status',
     { contact:'c003', assessment:'ANOMALOUS', speed_kn:18, mmsi:null },
     'c003 does not match any commercial AIS profile — high speed, no transponder.']],

  [16000, 'agent_1', 'cot',
    'Charlie flagged c003. I can break from CENTRAL and intercept — requesting permission.\n'],
  [17000, 'agent_1', 'msg',
    ['agent_2', 'proposal',
     { action:'intercept_c003' },
     'Requesting authority to divert from CENTRAL and close on c003.']],

  [17600, 'agent_2', 'cot',
    'Bravo intercept request received. Diversion is efficient — approving.\n'],
  [18200, 'agent_2', 'msg',
    ['agent_1', 'ack',
     { action:'intercept_c003' },
     'Approved. Bravo on c003. Charlie holds eastern sector.']],
  [18800, 'agent_1', 'task',   'Intercept contact c003'],
  [19000, 'agent_1', 'cot',
    'Authority granted. Adjusting course to intercept c003 within current sweep window.\n'],

  // Phase 3: mission change at t=38 000
  [38000, null,      'mission_change',
    'CHANGE OF INTENT: extend patrol to northern sector. Priority shifts to any vessel without AIS transponder — intercept and shadow.'],

  [38600, 'agent_0', 'cot',
    '⚡ MISSION CHANGE RECEIVED\nNew objective: northern extension, priority on transponder-less contacts.\nRebroadcasting updated intent to all peers.\n'],
  [39600, 'agent_0', 'msg',
    ['all', 'handoff',
     { update:'northern_extension', priority:'no_transponder' },
     'Mission updated — re-allocating sectors for northern coverage.']],

  [40400, 'agent_1', 'cot',
    'Mission change received. Handing c003 watch to Charlie and proceeding north.\n'],
  [41200, 'agent_1', 'msg',
    ['agent_2', 'handoff',
     { task:'monitor_c003' },
     'Handing c003 to Charlie. Bravo proceeding to northern sector.']],

  [41800, 'agent_2', 'cot',
    'Handoff acknowledged. Taking c003 monitoring. Bravo clear to proceed north.\n'],
  [42500, 'agent_2', 'task',   'Monitor contact c003'],
  [42600, 'agent_2', 'msg',
    ['agent_1', 'ack',
     { task:'monitor_c003' },
     'Charlie on c003. Bravo proceed north.']],

  [43200, 'agent_1', 'task',   'Extended northern patrol'],
  [44000, 'agent_0', 'cot',
    'Swarm re-converged on new intent. All sectors covered. Northern extension active.\n'],
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
