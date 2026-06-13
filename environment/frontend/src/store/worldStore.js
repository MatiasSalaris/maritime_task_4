import { writable, derived } from 'svelte/store'

export const worldState = writable({
  time: 0,
  agents: [],
  contacts: [],
  pois: [],
  geofences: [],
  messages_in_flight: [],
  message_log: [],
  mission: null,
})

export const selectedAgentId = writable(null)
export const mapOverlay = writable('tactical')
export const wsStatus = writable('disconnected') // 'connected' | 'disconnected' | 'reconnecting'

export const selectedAgent = derived(
  [worldState, selectedAgentId],
  ([$ws, $id]) => $ws.agents.find(a => a.id === $id) ?? null
)

// Agent colour palette — stable per id
const AGENT_COLORS = { agent_0: '#00d4ff', agent_1: '#00ff88', agent_2: '#ff8800' }
export function agentColor(id) {
  return AGENT_COLORS[id] ?? '#ffffff'
}
