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

function translateTask(text) {
  return text
    .replace(/^Awaiting orders$/i, 'In attesa di ordini')
    .replace(/^Idle$/i, 'In attesa')
    .replace(/^Patrolling sector /i, 'Pattuglia ')
    .replace(/^Patrolling /i, 'Pattuglia ')
    .replace(/^Intercepting /i, 'Ispeziona ')
    .replace(/^Escorting /i, 'Segue ')
    .replace(/^Transit to /i, 'Vai a ')
    .replace(/^Identified /i, 'Identificato ')
    .replace(/^Reported /i, 'Segnalato ')
}

function cleanTask(task, compact = true) {
  const text = translateTask(task || 'Awaiting orders')
  return compact ? shortText(text, 80) : text
}

function compactReason(line, compact = true) {
  if (!line) return ''
  const text = line
    .replace(/\bI (?:will|should|am going to)\b/gi, 'I')
    .replace(/\bmission\b/gi, 'order')
    .replace(/\boperating area\b/gi, 'area')
  return compact ? shortText(text, 120) : text
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
  const lastMsgText = lastMsg?.reasoning || lastMsg?.content?.text || ''
  return {
    decision: cleanTask(agent?.current_task, compact),
    why: compactReason(latest, compact) || 'Nessun ragionamento ricevuto.',
    coordination: lastMsg
      ? `${messageTypeLabel(lastMsg.msg_type)} a ${lastMsg.to_agent === 'all' ? 'tutti' : lastMsg.to_agent}: ${compact ? shortText(lastMsgText, 90) : lastMsgText}`
      : 'Nessun messaggio di coordinamento.',
    recentMessages: ownMsgs,
  }
}
