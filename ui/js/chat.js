/* PCB Advisor UI - chat: messages, suggestions, conversations list, sending, the chat chip. */

function renderChatChip() {
  const el = $('#chat-chip');
  if (!el) return;
  if (!activeFileChip) {
    el.hidden = true;
    el.innerHTML = '';
  } else {
    el.hidden = false;
    el.innerHTML = `<span class="chip-lbl">About: <b>${esc(activeFileChip)}</b></span><button type="button" class="chip-x" data-act="clear-file-chip" aria-label="Remove file context">×</button>`;
  }
}

/* The one entry point for every "Ask" button in the app.
   ctx = {kind: 'part'|'net'|'file'|'dfm'|'rule'|'zone', id, label, text?}. Puts the context in the composer, shows the
   chat and focuses it. (First version: prefills text; a file uses the existing file chip.) */
function askAbout(ctx) {
  if (!ctx) return;
  const inp = $('#input');
  if (ctx.kind === 'file') { activeFileChip = ctx.id; renderChatChip(); }
  else if (inp && ctx.text) inp.value = ctx.text;
  else if (inp && !inp.value.trim()) inp.value = `About ${ctx.label || ctx.id}: `;
  if (typeof showChat === 'function') showChat();
  setView('chat');
  if (inp) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
}

/* ---------- chat ---------- */
function diffHTML(p) {
  if (!p) return '';
  const keys = Object.keys(p.changes || {});
  const rows = keys.map(k => [FIELD[k] || k, p.before ? p.before[k] : null, p.changes[k]]);
  if (p.library) rows.push(['Library', 'Missing', 'Model from ' + (p.library.model_source || 'agent') + ' · needs your check']);
  const cls = p.status === 'approved' ? 'ok' : p.status === 'rejected' ? 'no' : '';
  const ref = (lineByKey(p.line)?.refs || [p.line])[0];
  const show = v => Array.isArray(v) ? v.join(', ') : (v === null || v === undefined || v === '') ? '—' : String(v);
  return `<div class="diff ${cls}"><div class="diff-h">Proposed BOM change <button class="ref" data-ref="${esc(ref)}">${esc(p.new ? 'new line ' + p.line : ref)}</button></div>
    <table>${rows.map(r => `<tr><td>${esc(r[0])}</td><td><span class="old">${esc(show(r[1]))}</span> → <span class="new">${esc(show(r[2]))}</span></td></tr>`).join('')}</table>
    <p class="diff-n">${esc(p.reason || '')} ${(p.sources || []).map(s => chip(s, '')).join(' ')}</p>
    ${p.status === 'pending' ? `<div class="diff-a"><button class="btn pri" data-decide="approved" data-pid="${esc(p.id)}">Approve change</button><button class="btn" data-decide="rejected" data-pid="${esc(p.id)}">Reject</button></div>`
      : p.status === 'approved' ? `<div class="diff-s">Approved · BOM, schematic and library updated</div>` : `<div class="diff-s">Rejected · ${esc(p.line)} unchanged</div>`}
  </div>`;
}
function ctxHTML(part) {
  if (!part) return '';
  const secs = [...new Set((part.where || []).map(w => `${w.sheet}:${w.block}${w.title ? ' (' + w.title + ')' : ''}`))].join(', ');
  return `<div class="ctx"><b>The agent has this part's context:</b> <span class="m">${esc(part.mpn)}</span>${secs ? ' · sheet ' + esc(secs) : ''}${part.datasheet ? ' · ' + chip(part.datasheet, '') : ''}
    <div class="nets">${(part.nets || []).map(n => `<span>${esc(n)}</span>`).join('')}</div></div>`;
}
function toolsHTML(items) {
  return `<div class="tools">${items.map(t => `<div class="tool ${esc(t.st || 'ok')}"><span class="ti"></span><span class="tt">${esc(t.t)}</span><span class="td">${esc(t.d || '')}</span></div>`).join('')}</div>`;
}
function stageHTML() {
  if (!S.idea.confirmed) return '';
  const when = (S.idea.confirmed_at || '').slice(0, 10);
  return `<div class="stage"><div class="stage-k">Stage 1 · Idea · confirmed${when ? ' ' + esc(when) : ''}</div><div class="stage-t">${esc(S.title)}</div>
    <div class="stage-d">${S.sheets.length} sheet${S.sheets.length === 1 ? '' : 's'} · ${S.totals.lines} BOM lines</div><button class="lnk" data-tab="idea">Open the idea summary</button></div>`;
}
function msgHTML(m) {
  if (m.role === 'user') return `<div class="msg user">${m.source ? `<div style="font-size:11px;color:var(--dim);margin-bottom:2px">About: ${chip(m.source, '')}</div>` : ''}<div class="bubble" dir="auto">${esc(m.text)}</div></div>`;
  if (m.role === 'ctx') return ctxHTML(m.part);
  if (m.role === 'agent') {
    const props = (m.proposals || (m.proposal ? [m.proposal] : [])).map(id => diffHTML(S.proposals.find(p => p.id === id))).join('');
    const hasDiagEdit = (m.applied || []).includes('idea.diagram.edit') || m.diagram_edit;
    const undoBtn = hasDiagEdit ? `<div style="margin-top:8px"><button type="button" class="btn btn-sm" data-act="undo-diagram" title="Undo diagram change" style="font-size:12px;padding:3px 8px;display:inline-flex;align-items:center;gap:4px">Undo diagram change</button></div>` : '';
    return (m.tools && m.tools.length ? toolsHTML(m.tools) : '') +
      `<div class="msg agent"><div class="who">PCB Advisor</div><div class="txt" dir="auto">${fmt(m.text)}${undoBtn}</div></div>` + props;
  }
  return '';
}
function currentRow() { return (S.sessions || []).find(r => r.id === S.session) || {}; }
function suggestions() {
  const row = currentRow();
  if (row.anchor) return ['Why did we pick this part?', 'Find an in-stock alternative', 'What should I check in the datasheet?'];
  if (row.id === 'idea' || !S.idea.confirmed) return ['What is still open?', 'What should I decide first?'];
  return ['Check stock for the whole BOM', 'Compare supplier prices', 'What is still open?'];
}
function preview(r) { return r.messages ? r.messages + ' message' + (r.messages === 1 ? '' : 's') : 'No messages yet'; }
function renderConvs() {
  const box = $('#convs');
  box.hidden = !convsOpen;
  $('[data-act="convs"]').setAttribute('aria-expanded', convsOpen);
  if (!convsOpen) return;
  const rows = S.sessions || [];
  const item = r => {
    const l = r.anchor ? lineByKey(r.anchor) : null;
    const anc = r.anchor ? (l && l.refs.length > 3 ? `${l.refs[0]}…${l.refs.at(-1)}` : (l ? l.refs.join(',') : r.anchor)) : '';
    return `<button class="conv" data-thread="${esc(r.id)}" aria-current="${r.id === S.session}"><span class="t"><span>${anc ? `<span class="anc">${esc(anc)}</span>` : ''}${esc(r.title)}</span><small>${esc((r.updated || '').slice(5, 10))}</small></span><span class="p">${esc(preview(r))}</span></button>`;
  };
  const proj = rows.filter(r => !r.anchor), parts = rows.filter(r => r.anchor);
  box.innerHTML = `<h4>Project conversations</h4>${proj.map(item).join('')}` + (parts.length ? `<h4>About a part</h4>${parts.map(item).join('')}` : '');
}
function renderChat(force) {
  const key = JSON.stringify([S.session, S.chat.length, S.chat.at(-1)?.ts, S.proposals.map(p => p.status), pending, S.idea.confirmed]);
  if (!force && key === lastChatKey) { renderConvs(); return; }
  lastChatKey = key;
  const row = currentRow();
  const l = row.anchor ? lineByKey(row.anchor) : null;
  $('#convtitle').textContent = (l ? l.refs[0] + (l.refs.length > 1 ? '…' : '') + ' · ' : '') + (row.title || 'Conversation');
  const box = $('#msgs');
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80 || force;
  let html = row.anchor ? '' : stageHTML();
  html += S.chat.length ? S.chat.map(msgHTML).join('')
    : `<div class="msg agent"><div class="who">PCB Advisor</div><div class="txt"><p>New conversation in ${esc(S.title)}. I can see the BOM, the schematic and all sources.</p></div></div>`;
  if (pending) html += toolsHTML([{t: 'Working…', d: '', st: 'run'}]);
  box.innerHTML = html;
  if (stick) box.scrollTop = box.scrollHeight;
  $('#sugs').innerHTML = suggestions().map(s => `<button class="sug" type="button">${esc(s)}</button>`).join('');
  $('#sendbtn').disabled = pending;
  renderChatChip();
  renderConvs();
}
async function send(text) {
  text = (text || '').trim(); if (!text || pending) return;
  pending = true;
  const fileContext = activeFileChip;
  activeFileChip = null;
  renderChatChip();
  const userEntry = {role: 'user', text, ts: new Date().toISOString()};
  if (fileContext) userEntry.source = fileContext;
  S.chat = [...S.chat, userEntry];
  renderChat(true);
  try {
    const payload = {text};
    if (fileContext) { payload.file = fileContext; payload.source = fileContext; }
    const res = await api('/api/chat', payload);
    setState(res);
    const mountEl = document.querySelector('.diagram-mount-point');
    if (mountEl && mountEl._diagramEditor && res && res.idea && res.idea.diagram) {
      mountEl._diagramEditor.updateData(res.idea.diagram, res.diagram_touched || []);
    }
  }
  catch (e) { /* toast shown */ }
  pending = false;
  render(true);
}
async function openPart(anchor) {
  const r = await api('/api/thread/open', {anchor});
  SESSION = r.session; convsOpen = false;
  await refresh(true); setView('chat');
}
async function switchSession(id) { SESSION = id; convsOpen = false; await refresh(true); setView('chat'); }

$('#form').addEventListener('submit', e => { e.preventDefault(); const i = $('#input'); const t = i.value; i.value = ''; i.style.height = ''; send(t); });
$('#input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#form').requestSubmit(); } });

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('clear-file-chip', async (el, d, e) => {
  activeFileChip = null; renderChatChip(); return;
});
onAct('convs', async (el, d, e) => {
  convsOpen = !convsOpen; renderConvs(); return;
});
onAct('new', async (el, d, e) => {
  const r = await api('/api/sessions/new', {}); SESSION = r.created; convsOpen = false; await refresh(true); return;
});
