export function shortText(value, max = 110) {
  const text = (value ?? '').replace(/\s+/g, ' ').trim()
  if (text.length <= max) return text
  return text.slice(0, max - 1).trimEnd() + '...'
}

export function reasoningLines(cot) {
  return (cot ?? '')
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean)
    .filter(s => !s.toLowerCase().startsWith('new mission'))
    .filter(s => !s.toLowerCase().startsWith('mission cleared'))
}

function cleanTask(task) {
  const text = shortText(task || 'Awaiting orders', 80)
  return text
    .replace(/^Patrolling sector /i, 'Patrol ')
    .replace(/^Intercepting /i, 'Inspect ')
    .replace(/^Escorting /i, 'Shadow ')
    .replace(/^Transit to /i, 'Go to ')
}

function compactReason(line) {
  if (!line) return ''
  return shortText(
    line
      .replace(/\bI (?:will|should|am going to)\b/gi, 'I')
      .replace(/\bmission\b/gi, 'order')
      .replace(/\boperating area\b/gi, 'area'),
    120,
  )
}

export function agentDecisionSummary(agent, messages = []) {
  const lines = reasoningLines(agent?.cot_text)
  const latest = lines.at(-1) || ''
  const ownMsgs = (messages ?? [])
    .filter(m => m.msg_type !== 'status' && m.from_agent === agent?.id)
    .slice(-3)

  const lastMsg = ownMsgs.at(-1)
  return {
    decision: cleanTask(agent?.current_task),
    why: compactReason(latest) || 'No reasoning received yet.',
    coordination: lastMsg
      ? `${lastMsg.msg_type} to ${lastMsg.to_agent === 'all' ? 'all' : lastMsg.to_agent}: ${shortText(lastMsg.reasoning || lastMsg.content?.text || '', 90)}`
      : 'No coordination message yet.',
    recentMessages: ownMsgs,
  }
}
