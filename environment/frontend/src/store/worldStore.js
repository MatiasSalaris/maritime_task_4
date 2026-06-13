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
  mission_status: 'idle',
  mission_result: null,
  doctrine: null,
  aor: null,
})

export const selectedAgentId = writable(null)
export const mapOverlay = writable('tactical')
export const wsStatus = writable('disconnected') // 'connected' | 'disconnected' | 'reconnecting'
export const godView = writable(false)

export const selectedAgent = derived(
  [worldState, selectedAgentId],
  ([$ws, $id]) => $ws.agents.find(a => a.id === $id) ?? null
)

// Agent colour palette — stable per id
const AGENT_COLORS = { agent_0: '#00d4ff', agent_1: '#00ff88', agent_2: '#ff8800' }
export function agentColor(id) {
  return AGENT_COLORS[id] ?? '#ffffff'
}

// Map an agent's current_task string to a compact, colour-coded action tag.
// Keeps the "what is it doing right now" legible at a glance in the bubble/card.
export function actionTag(task) {
  const t = (task ?? '').toLowerCase()
  if (!t)                                               return { label: 'ATTESA',      color: '#6a8a9a' }
  if (t.startsWith('idle'))                             return { label: 'IN ATTESA',   color: '#6a8a9a' }
  if (t.includes('hold') || t.includes('attesa'))       return { label: 'FERMO',       color: '#ffaa00' }
  if (t.includes('intercept') || t.includes('identif') || t.includes('ispeziona'))
                                                        return { label: 'ISPEZIONE',   color: '#ff5a3c' }
  if (t.includes('on station'))                         return { label: 'IN POSIZIONE', color: '#00ff88' }
  if (t.includes('ricerca'))                            return { label: 'RICERCA',     color: '#00d4ff' }
  if (t.includes('transit') || t.includes('patrol') || t.includes('sweep') ||
      t.includes('pattuglia') || t.includes('vai a') || t.includes('procedo'))
                                                        return { label: 'IN MOVIMENTO', color: '#00d4ff' }
  return { label: 'ATTIVO', color: '#00d4ff' }
}
