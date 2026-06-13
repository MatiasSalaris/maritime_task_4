/**
 * Canvas overlay that draws animated "message packets" flying between agents.
 * Each packet travels from sender to receiver over ~1.5 s.
 */

const TYPE_COLORS = {
  proposal: '#00d4ff',
  ack:      '#00ff88',
  objection:'#ff3355',
  handoff:  '#ffaa00',
  status:   '#888888',
}

const TYPE_SYMBOLS = {
  proposal: '◆',
  ack:      '✓',
  objection:'✕',
  handoff:  '→',
  status:   '●',
}

const DURATION_MS = 1500

export class AnimationCanvas {
  constructor(mapContainer, agentLayerRef) {
    this._agentLayer = agentLayerRef
    this._canvas = document.createElement('canvas')
    this._canvas.style.cssText = `
      position:absolute; top:0; left:0; pointer-events:none; z-index:10;
    `
    mapContainer.appendChild(this._canvas)
    this._ctx = this._canvas.getContext('2d')
    this._packets = []
    this._raf = null
    this._resize()
    window.addEventListener('resize', () => this._resize())
    this._loop()
  }

  _resize() {
    this._canvas.width  = this._canvas.offsetWidth  || window.innerWidth
    this._canvas.height = this._canvas.offsetHeight || window.innerHeight
  }

  addPacket(msg) {
    this._packets.push({ ...msg, startedAt: performance.now() })
  }

  _loop() {
    this._raf = requestAnimationFrame(() => this._loop())
    const ctx = this._ctx
    const now = performance.now()

    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height)

    this._packets = this._packets.filter(p => (now - p.startedAt) < DURATION_MS * 1.1)

    for (const pkt of this._packets) {
      const t = Math.min(1, (now - pkt.startedAt) / DURATION_MS)

      const fromPos = this._agentLayer.getScreenPos(pkt.from_agent)
      const toPos   = pkt.to_agent === 'all'
        ? null
        : this._agentLayer.getScreenPos(pkt.to_agent)

      if (!fromPos) continue

      const color = TYPE_COLORS[pkt.msg_type] ?? '#ffffff'

      if (toPos) {
        // Draw trajectory line (faint)
        ctx.beginPath()
        ctx.moveTo(fromPos.x, fromPos.y)
        ctx.lineTo(toPos.x, toPos.y)
        ctx.strokeStyle = color + '33'
        ctx.lineWidth = 1
        ctx.stroke()

        // Draw moving dot
        const x = fromPos.x + (toPos.x - fromPos.x) * t
        const y = fromPos.y + (toPos.y - fromPos.y) * t
        ctx.beginPath()
        ctx.arc(x, y, 5, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()

        // Symbol above dot
        ctx.font = '10px monospace'
        ctx.fillStyle = '#ffffff'
        ctx.fillText(TYPE_SYMBOLS[pkt.msg_type] ?? '?', x - 4, y - 8)
      } else {
        // Broadcast — draw expanding ring
        const radius = 15 + t * 40
        ctx.beginPath()
        ctx.arc(fromPos.x, fromPos.y, radius, 0, Math.PI * 2)
        ctx.strokeStyle = color + Math.round((1 - t) * 255).toString(16).padStart(2, '0')
        ctx.lineWidth = 2
        ctx.stroke()
      }
    }
  }

  destroy() {
    cancelAnimationFrame(this._raf)
    this._canvas.remove()
  }
}
