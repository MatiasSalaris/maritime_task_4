import { worldState, wsStatus } from '../store/worldStore.js'

const RECONNECT_MS = 3000

class WorldStateClient {
  constructor() {
    this._ws = null
    this._handlers = {}
    this._dead = false
  }

  on(type, fn) {
    this._handlers[type] = fn
    return this
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/ws/frontend`
    wsStatus.set('reconnecting')
    this._ws = new WebSocket(url)

    this._ws.onopen = () => {
      wsStatus.set('connected')
      console.info('[WS] connected')
    }

    this._ws.onmessage = (ev) => {
      let msg
      try { msg = JSON.parse(ev.data) } catch { return }
      const handler = this._handlers[msg.type]
      if (handler) handler(msg)
    }

    this._ws.onclose = () => {
      wsStatus.set('disconnected')
      if (!this._dead) {
        console.warn('[WS] disconnected — reconnecting in', RECONNECT_MS, 'ms')
        setTimeout(() => this.connect(), RECONNECT_MS)
      }
    }

    this._ws.onerror = () => this._ws.close()
  }

  destroy() {
    this._dead = true
    this._ws?.close()
  }
}

export function createClient() {
  const client = new WorldStateClient()

  client
    .on('world_state', ({ payload }) => {
      worldState.set(payload)
    })
    .on('cot_chunk', ({ agent_id, chunk }) => {
      worldState.update(s => {
        const agent = s.agents.find(a => a.id === agent_id)
        if (agent) {
          agent.cot_text = (agent.cot_text ?? '') + chunk
          if (agent.cot_text.length > 2000) agent.cot_text = agent.cot_text.slice(-2000)
          const text = (chunk ?? '').trim()
          if (text) {
            agent.decision_log = [
              ...(agent.decision_log ?? []),
              { sent_at: Date.now() / 1000, text },
            ].slice(-80)
          }
        }
        return { ...s }
      })
    })
    .on('p2p_message', ({ payload }) => {
      worldState.update(s => ({
        ...s,
        messages_in_flight: [...(s.messages_in_flight ?? []), payload],
      }))
    })

  client.connect()
  return client
}
