export function shortText(value, max = 110) {
  const text = String(value ?? '')
  if (text.length <= max) return text
  return text.slice(0, Math.max(0, max - 3)) + '...'
}

export function reasoningLines(cot) {
  return (cot ?? '')
    .split('\n')
    .filter(s => s.trim())
}

function cleanTask(task, compact = true) {
  const text = task || 'Awaiting orders'
  return compact ? shortText(text, 80) : text
}

function compactReason(line, compact = true) {
  if (!line) return ''
  return compact ? shortText(line, 120) : line
}

function messageTypeLabel(type) {
  return {
    proposal: 'proposta',
    ack: 'conferma',
    objection: 'obiezione',
    handoff: 'passaggio',
    report: 'rapporto',
    status: 'stato',
  }[type] ?? type
}

export function agentDecisionSummary(agent, messages = [], options = {}) {
  const compact = options.compact ?? true
  const lines = reasoningLines(agent?.cot_text)
  const latest = lines.at(-1) || ''
  const ownMsgs = (messages ?? [])
    .filter(m => m.msg_type !== 'status' && m.from_agent === agent?.id)
    .slice(-3)

  const lastMsg = ownMsgs.at(-1)
  const lastMsgText = lastMsg?.content?.text || lastMsg?.reasoning || ''
  return {
    decision: cleanTask(agent?.current_task, compact),
    why: compactReason(latest, compact) || 'Nessun ragionamento ricevuto.',
    coordination: lastMsg
      ? `${messageTypeLabel(lastMsg.msg_type)} a ${lastMsg.to_agent === 'all' ? 'tutti' : lastMsg.to_agent}: ${compact ? shortText(lastMsgText, 90) : lastMsgText}`
      : 'Nessun messaggio di coordinamento.',
    recentMessages: ownMsgs,
  }
}
