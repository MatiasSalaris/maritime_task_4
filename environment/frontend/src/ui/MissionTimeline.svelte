<script>
  import { worldState, agentColor } from '../store/worldStore.js'

  const TYPE_LABEL = {
    proposal: 'proposta',
    ack: 'conferma',
    objection: 'obiezione',
    handoff: 'passaggio',
    report: 'rapporto',
    status: 'stato',
  }

  function agentName(id) {
    if (id === 'all') return 'Tutti'
    return $worldState.agents?.find(a => a.id === id)?.name ?? id
  }

  function ts(unix) {
    if (!unix) return ''
    return new Date(unix * 1000).toTimeString().slice(0, 8)
  }

  function clean(text) {
    return (text ?? '').replace(/\s+/g, ' ').trim()
  }

  function messageText(m) {
    return clean(m.content?.text || '')
  }

  function reasoningText(m) {
    return clean(m.reasoning || '')
  }

  function priorityFromMission(mission) {
    const text = (mission ?? '').toLowerCase()
    if (text.includes('veloc') || text.includes('speed') || text.includes('rapida')) return 'velocità'
    if (text.includes('copertura') || text.includes('coverage')) return 'copertura'
    return 'bilanciata'
  }

  function laneName(agentId) {
    if (agentId === 'agent_0') return 'area ovest'
    if (agentId === 'agent_1') return 'area centrale'
    if (agentId === 'agent_2') return 'area est'
    return 'area assegnata'
  }

  function readableReasoning(text, agentId) {
    return clean(text)
      .replaceAll('AUTO', laneName(agentId))
      .replace(/fascia automatica dell.?AOR/gi, laneName(agentId))
      .replace(/fascia automatica/gi, laneName(agentId))
      .replace(/\bAOR\b/g, 'area operativa')
  }

  function isSearchProposal(m) {
    const text = clean(`${messageText(m)} ${reasoningText(m)}`).toLowerCase()
    return m.msg_type === 'proposal' && (text.includes('ricerca') || text.includes('boa') || text.includes('auto'))
  }

  function isSearchAck(m) {
    const text = clean(`${messageText(m)} ${reasoningText(m)}`).toLowerCase()
    return m.msg_type === 'ack' && (text.includes('continuo') || text.includes('confermo') || text.includes('ricerca'))
  }

  $: rawMessages = ($worldState.message_log ?? []).filter(m => m.msg_type !== 'status')
  $: searchStarts = rawMessages.filter(isSearchProposal)
  $: searchAcks = rawMessages.filter(isSearchAck)
  $: reports = rawMessages.filter(m => m.msg_type === 'report')

  $: messages = [
    searchStarts.length ? {
      kind: 'phase',
      t: Math.min(...searchStarts.map(m => m.sent_at ?? 0)),
      title: 'Ricerca distribuita',
      body: searchStarts
        .map(m => `${agentName(m.from_agent)} copre ${laneName(m.from_agent)}.`)
        .filter((v, i, a) => a.indexOf(v) === i)
        .join(' '),
    } : null,
    searchAcks.length ? {
      kind: 'phase',
      t: Math.min(...searchAcks.map(m => m.sent_at ?? 0)),
      title: 'Coordinamento confermato',
      body: 'Gli agenti confermano la divisione dell’area e continuano senza sovrapporsi.',
    } : null,
    ...reports.map(m => ({
      kind: 'report',
      t: m.sent_at ?? 0,
      from: m.from_agent,
      to: m.to_agent,
      type: m.msg_type,
      title: `${agentName(m.from_agent)} segnala il risultato`,
      body: explainMessage(m),
      detail: reasoningText(m),
    })),
    ...rawMessages
      .filter(m => !isSearchProposal(m) && !isSearchAck(m) && m.msg_type !== 'report')
      .map(m => ({
        kind: 'message',
        t: m.sent_at ?? 0,
        from: m.from_agent,
        to: m.to_agent,
        type: m.msg_type,
        title: `${agentName(m.from_agent)} -> ${agentName(m.to_agent)} · ${TYPE_LABEL[m.msg_type] ?? m.msg_type}`,
        body: explainMessage(m),
        detail: reasoningText(m),
      })),
  ].filter(Boolean)

  $: missionEvents = [
    $worldState.mission ? {
      kind: 'mission',
      t: messages[0]?.t ? messages[0].t - 0.001 : 0,
      title: 'Missione avviata',
      body: `Obiettivo: trovare la boa. Priorità: ${priorityFromMission($worldState.mission)}.`,
    } : null,
    $worldState.mission_status === 'completed' ? {
      kind: 'complete',
      t: Date.now() / 1000,
      title: 'Missione completata',
      body: resultText($worldState.mission_result),
    } : null,
  ].filter(Boolean)

  $: reasoningEvents = ($worldState.agents ?? [])
    .flatMap(a => (a.decision_log ?? []).map(entry => ({
      kind: 'reasoning',
      t: entry.sent_at ?? 0,
      from: a.id,
      title: `${a.name} · ragionamento`,
      body: readableReasoning(entry.text, a.id),
    })))
    .filter(e => e.body)

  $: taskEvents = ($worldState.agents ?? [])
    .filter(a => a.current_task)
    .map(a => ({
      kind: 'task',
      t: Date.now() / 1000,
      from: a.id,
      title: `${a.name} · ${$worldState.mission_status === 'completed' ? 'stato finale' : 'stato attuale'}`,
      body: humanTask(a.current_task, a.id),
    }))

  $: events = [...missionEvents, ...reasoningEvents, ...messages, ...taskEvents]
    .sort((a, b) => a.t - b.t)
    .slice(-48)

  function resultText(result) {
    if (!result) return ''
    const parts = [
      result.contact_id ? `target ${result.contact_id}` : null,
      result.completed_by_name ? `trovata da ${result.completed_by_name}` : null,
      result.lat && result.lon ? `${Number(result.lat).toFixed(4)}N ${Number(result.lon).toFixed(4)}E` : null,
    ].filter(Boolean)
    return parts.join(' · ')
  }

  function humanTask(task, agentId) {
    const text = clean(task)
    if (!text) return ''
    if (text.toLowerCase().includes('missione completata')) return text
    if (text.toLowerCase().includes('ricerca')) return `Sta cercando nella ${laneName(agentId)}.`
    return text.replaceAll('AUTO', 'area assegnata')
  }

  function explainMessage(m) {
    const text = messageText(m) || reasoningText(m)
    const lower = clean(`${messageText(m)} ${reasoningText(m)}`).toLowerCase()
    if (m.msg_type === 'report' && (lower.includes('boa') || lower.includes('buoy'))) {
      return 'La boa è stata rilevata. La ricerca può terminare.'
    }
    if (isSearchProposal(m)) return `${agentName(m.from_agent)} prende ${laneName(m.from_agent)} per evitare sovrapposizioni.`
    if (isSearchAck(m)) return `${agentName(m.from_agent)} conferma la propria area di ricerca.`
    return text.replaceAll('AUTO', 'area assegnata').replaceAll('fascia', 'area')
  }

  function download(name, mime, content) {
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  }

  function exportTxt() {
    const lines = events.map((e, i) => {
      const head = `${String(i + 1).padStart(2, '0')} ${ts(e.t)} ${e.title}`
      const label = ['reasoning', 'message', 'report'].includes(e.kind) ? 'perché' : 'dettaglio'
      const detail = e.detail && e.detail !== e.body ? `\n   ${label}: ${e.detail}` : ''
      return `${head}\n   ${e.body || '-'}${detail}`
    })
    download('missione-timeline.txt', 'text/plain;charset=utf-8', lines.join('\n\n'))
  }

  function esc(s) {
    return String(s ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
  }

  function exportSvg() {
    const rowH = 74
    const width = 980
    const height = Math.max(140, 70 + events.length * rowH)
    const rows = events.map((e, i) => {
      const y = 50 + i * rowH
      const color = e.from ? agentColor(e.from) : (e.kind === 'complete' ? '#00ff88' : '#ffaa00')
      return `
        <circle cx="34" cy="${y}" r="6" fill="${color}" />
        <text x="56" y="${y - 10}" fill="#d8ecf6" font-size="13" font-weight="700">${esc(ts(e.t))} ${esc(e.title)}</text>
        <text x="56" y="${y + 12}" fill="#8fb5c8" font-size="12">${esc(e.body || '-').slice(0, 150)}</text>
      `
    }).join('')
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <rect width="100%" height="100%" fill="#060c18"/>
      <text x="24" y="26" fill="#00d4ff" font-size="16" font-weight="700">Timeline missione</text>
      <line x1="34" y1="44" x2="34" y2="${height - 28}" stroke="#1a3a5a" stroke-width="2"/>
      ${rows}
    </svg>`
    download('missione-timeline.svg', 'image/svg+xml;charset=utf-8', svg)
  }
</script>

<div class="timeline">
  <div class="head">
    <div class="title">TIMELINE</div>
    <div class="actions">
      <button on:click={exportTxt} disabled={!events.length}>TXT</button>
      <button on:click={exportSvg} disabled={!events.length}>SVG</button>
    </div>
  </div>

  <div class="list">
    {#each events as e, i (`${e.kind}-${e.t}-${i}`)}
      <div class="event" style="--c:{e.from ? agentColor(e.from) : (e.kind === 'complete' ? '#00ff88' : '#ffaa00')}">
        <div class="dot"></div>
        <div class="content">
          <div class="meta">{ts(e.t)} · {e.title}</div>
          <div class="body">{e.body || '-'}</div>
          {#if e.detail && e.detail !== e.body}
            <details>
              <summary>{['message', 'report'].includes(e.kind) ? 'perché' : 'dettaglio'}</summary>
              <div class="detail">{e.detail}</div>
            </details>
          {/if}
        </div>
      </div>
    {/each}
    {#if !events.length}
      <div class="empty">Nessuna timeline disponibile.</div>
    {/if}
  </div>
</div>

<style>
  .timeline {
    border-top: 1px solid #1a2a3a;
    background: #07111b;
    min-height: 160px;
    max-height: 30vh;
    display: flex;
    flex-direction: column;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 14px 7px;
    border-bottom: 1px solid #111e2a;
    flex-shrink: 0;
  }
  .title {
    font-size: 11px;
    letter-spacing: 0.12em;
    color: #4a7a9a;
  }
  .actions { display: flex; gap: 5px; }
  button {
    font-family: monospace;
    font-size: 10px;
    color: #00d4ff;
    background: #061420;
    border: 1px solid #1a4a6a;
    border-radius: 3px;
    padding: 3px 7px;
    cursor: pointer;
  }
  button:disabled { opacity: 0.4; cursor: default; }
  .list {
    overflow-y: auto;
    padding: 8px 14px 12px;
    scrollbar-width: thin;
    scrollbar-color: #1a3a5a transparent;
  }
  .event {
    display: grid;
    grid-template-columns: 12px 1fr;
    gap: 8px;
    position: relative;
    padding-bottom: 10px;
  }
  .event::before {
    content: '';
    position: absolute;
    left: 5px;
    top: 14px;
    bottom: 0;
    width: 1px;
    background: #15303f;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--c);
    margin-top: 4px;
    box-shadow: 0 0 8px color-mix(in srgb, var(--c) 45%, transparent);
    z-index: 1;
  }
  .meta {
    font-size: 11px;
    color: #d2e8f4;
    line-height: 1.35;
    font-weight: bold;
  }
  .body {
    font-size: 11px;
    color: #8fb5c8;
    line-height: 1.35;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin-top: 2px;
  }
  details {
    margin-top: 4px;
    color: #4a7a9a;
    font-size: 10px;
  }
  summary { cursor: pointer; }
  .detail {
    margin-top: 3px;
    color: #6a9ab0;
    line-height: 1.35;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .empty {
    font-size: 12px;
    color: #3a5a7a;
    text-align: center;
    padding: 18px;
  }
</style>
