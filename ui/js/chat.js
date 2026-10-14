/* PCB Advisor UI - chat: header and conversation list, messages, proposal cards, composer, suggestions, askAbout, sending.
   The chat is one column that shows on every view. State it owns: askCtx (the context chip), chatError, the working timer.
   Server data it reads: S.chat, S.sessions (each with `last`), S.proposals. Globals other files rely on: askAbout, send,
   renderChat, renderChatChip, switchSession, openPart, diffHTML.
   Names here are prefixed (chat*, CHAT_*, prop*) because every ui/js file shares one global scope. */

/* ---------- the context chip ---------- */
/* What an "Ask" can point at. `mono`: the label is a designator, net or file name. `q`: the question put in an empty box. */
const CHAT_CHIPS = {
  part: {name: 'Part', mono: true, q: 'What should I check on this part?'},
  net: {name: 'Net', mono: true, q: 'What is this net connected to?'},
  file: {name: 'File', mono: true, q: 'What does this file say that matters for my board?'},
  dfm: {name: 'DFM finding', mono: false, q: 'Is this a real issue, and how would I fix it?'},
  rule: {name: 'Rule', mono: false, q: 'Should I change this rule?'},
  zone: {name: 'Zone', mono: false, q: 'Is this a good place for these parts?'},
};
let askCtx = null;                        // the chip in the composer: {kind, id, label}
let chatError = null;                     // a send that never reached an answer: {message, text, ctx, session}
let chatTimer = null, chatSince = 0;      // the "Working… 12 s" clock
let chatSeen = {session: null, count: 0}; // what the thread showed last, so only really new messages are announced
let chatHtml = '';                        // the thread's markup as last written, to leave the DOM alone when nothing changed
let chatLead = null;                      // while the thread is drawn: the one pending proposal whose Approve is the primary button

function chatSetChip(ctx) {
  askCtx = ctx;
  renderChatChip();
  chatSugs();
}
function chatChip() { return askCtx; }
function renderChatChip() {
  const el = $('#chat-chip');
  if (!el) return;
  const c = chatChip();
  const key = c ? [c.kind, c.id, c.label].join('|') : '';
  if (el.dataset.k === key) return;                           // the poll must not rebuild a chip whose × has focus
  el.dataset.k = key;
  if (!c) { el.hidden = true; el.innerHTML = ''; return; }
  const k = CHAT_CHIPS[c.kind] || {};
  el.hidden = false;
  el.innerHTML = `<span class="chip-t${k.mono ? ' m' : ''}" title="${esc((k.name || 'About') + ': ' + c.id)}">${esc(c.label)}</span>` +
    `<button type="button" class="chip-x" data-act="clear-chip" title="Remove context" aria-label="Remove context: ${esc(c.label)}">${icon('x', 's')}</button>`;
}

/* The one entry point for every "Ask" button in the app.
   ctx = {kind: 'part'|'net'|'file'|'dfm'|'rule'|'zone', id, label, text?}. Sets the chip, shows the chat, focuses the box.
   An empty box gets a default question (ctx.text, else one per kind); a draft is never overwritten. */
function askAbout(ctx) {
  if (!ctx) return;
  const kind = CHAT_CHIPS[ctx.kind] ? ctx.kind : null;
  const id = String(ctx.id ?? ctx.label ?? '').trim();
  if (kind && id) chatSetChip({kind, id, label: String(ctx.label || id)});
  if (typeof showChat === 'function') showChat();
  setView('chat');
  const inp = $('#input');
  if (!inp) return;
  const fresh = !inp.value.trim();
  if (fresh) {
    const q = ctx.text || (kind ? CHAT_CHIPS[kind].q : '');
    if (q) inp.value = q;
  }
  chatAutosize();
  chatUpdateSend();
  inp.focus();
  if (fresh && inp.value) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
}

/* ---------- small helpers ---------- */
/* a message as one line of plain text: citations and refs lose their markup */
const chatPlain = t => String(t || '').replace(/\{\{src:([^|}]+)(?:\|[^}]*)?\}\}/g, '$1').replace(/\{\{ref:([^}]+)\}\}/g, '$1')
  .replace(/[*`]/g, '').replace(/\s+/g, ' ').trim();
function chatWhen(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'})
    : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'});
}
const chatDir = html => html.replace(/<(p|ul|ol)>/g, '<$1 dir="auto">');    // each paragraph picks its own direction
function currentRow() { return (S.sessions || []).find(r => r.id === S.session) || {}; }
/* the readable name of what a conversation is anchored to: a part's refs ("F1", "C3 +21"); a DFM or net conversation says it in its title */
function chatAnchor(row) {
  if (!row.anchor || /^dfm:/.test(row.anchor)) return '';
  const l = lineByKey(row.anchor) || lineOfRef(row.anchor);
  if (!l || !l.refs || !l.refs.length) return '';
  return l.refs.length > 2 ? `${l.refs[0]} +${l.refs.length - 1}` : l.refs.join(', ');
}
function chatLastUser() {
  for (let i = S.chat.length - 1; i >= 0; i--) if (S.chat[i].role === 'user') return S.chat[i];
  return null;
}
const chatCtxOf = m => m.source ? {kind: 'file', id: m.source, label: m.source} : m.about ? {...m.about} : null;

/* ---------- proposal cards ---------- */
const PROP_LABEL = {lcsc: 'LCSC code', mpn: 'MPN', manufacturer: 'Manufacturer', package: 'Package', value: 'Value', description: 'Description',
  note: 'Note', datasheet: 'Datasheet', dnp: 'Not-fitted flag', nobuy: 'Not-bought flag', refs: 'Designators', role: 'Role', library: 'Library', sheet: 'Sheet'};
const propLabel = k => PROP_LABEL[k] || FIELD[k] || k;
const propLower = s => /^[A-Z]{2,}/.test(s) ? s : s.charAt(0).toLowerCase() + s.slice(1);
const propShow = v => Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : (v === null || v === undefined) ? '' : String(v);
const propPlural = (n, one) => `${n} ${one}${n === 1 ? '' : 's'}`;

/* How many blocks and links a diagram proposal touches: added, removed or moved/renamed, compared with what is on the canvas now. */
function propDiagramDelta(p) {
  const ch = p.changes || {}, bf = p.before || {};
  const nd = ch.diagram || {shapes: ch.shapes, connectors: ch.connectors};
  const od = bf.diagram || {};
  const touched = (next, prev, sig) => {
    if (!Array.isArray(next)) return 0;
    const before = new Map((prev || []).map(x => [x.id, sig(x)]));
    const seen = new Set();
    let n = 0;
    for (const x of next) { seen.add(x.id); if (before.get(x.id) !== sig(x)) n++; }
    for (const id of before.keys()) if (!seen.has(id)) n++;
    return n;
  };
  const shape = s => JSON.stringify([s.type, s.text, Math.round(s.x), Math.round(s.y), Math.round(s.w), Math.round(s.h)]);
  const conn = c => JSON.stringify([c.from, c.to, c.label || '']);
  let blocks = touched(nd.shapes, od.shapes, shape), links = touched(nd.connectors, od.connectors, conn);
  if (Array.isArray(ch.blocks)) blocks += touched(ch.blocks, bf.blocks, b => JSON.stringify(b));      // the older block/link format
  if (Array.isArray(ch.links)) { const lk = l => `${l.from}>${l.to}`; links += touched(ch.links.map(l => ({...l, id: lk(l)})), (bf.links || []).map(l => ({...l, id: lk(l)})), l => JSON.stringify(l)); }
  return {blocks, links};
}
function propDiagramText(p) {
  const {blocks, links} = propDiagramDelta(p);
  const bits = [blocks && propPlural(blocks, 'block'), links && propPlural(links, 'link')].filter(Boolean);
  return bits.length ? `Diagram: ${bits.join(', ')} changed` : 'Diagram: update proposed';
}

/* The card for one agent proposal (a BOM line change or a diagram change). Pending: heading, the change, why, Approve / Reject.
   Decided: one line. Approve and Reject carry data-decide + data-pid, the generic route in core.js. */
function diffHTML(p) {
  if (!p) return '';
  const diagram = p.kind === 'idea_diagram';
  const keys = Object.keys(p.changes || {});
  const ref = diagram ? '' : ((lineByKey(p.line) || {}).refs || [p.line])[0];
  const refBtn = ref ? `<button type="button" class="ref" data-ref="${esc(ref)}">${esc(p.new ? p.line : ref)}</button>` : '';
  const labels = keys.map(k => propLabel(k));
  const what = labels.length > 2 ? propPlural(labels.length, 'field') : labels.map(propLower).join(' and ');
  if (p.status === 'approved' || p.status === 'rejected') {
    const ok = p.status === 'approved';
    const subj = diagram ? 'diagram changes' : `${refBtn} ${esc(p.new ? 'new line' : propLower(labels.join(', ')) || 'change')}`;
    return `<div class="prop-done ${ok ? 'ok' : 'no'}"><span class="${ok ? 'ok-t' : ''}">${icon(ok ? 'check' : 'x', 's')}</span><span>${ok ? 'Approved' : 'Rejected'}: ${subj}</span></div>`;
  }
  const pid = esc(p.id);
  const why = p.reason ? `<p class="why" dir="auto">${esc(p.reason)}</p>` : '';
  const srcs = (p.sources || []).length ? `<p class="srcs">${p.sources.map(s => chip(s, '')).join(' ')}</p>` : '';
  // one primary in the thread: with several cards waiting, only the newest (nearest the box) has the filled Approve
  const lead = chatLead === null || chatLead === p.id;
  const acts = (extra) => `<div class="acts">${btn('Approve', {kind: lead ? 'pri' : 'line', size: 'sm', decide: 'approved', pid: p.id})}${btn('Reject', {size: 'sm', decide: 'rejected', pid: p.id})}${extra || ''}</div>`;
  if (diagram) {
    return `<div class="prop" data-pid="${pid}"><h4>${esc(propDiagramText(p))}</h4>${why}${srcs}` +
      acts(btn('Review on the canvas', {kind: 'link', act: 'review-diagram', cls: 'go'})) + '</div>';
  }
  const rows = keys.map(k => {
    const old = p.before ? propShow(p.before[k]) : '', now = propShow(p.changes[k]);
    const label = keys.length > 1 || p.library ? `<span class="k">${esc(propLabel(k))}</span> ` : '';
    return `<div class="row" dir="auto">${label}${old && !p.new ? `<s>${esc(old)}</s> &rarr; ` : ''}<b>${esc(now)}</b></div>`;
  });
  if (p.library) rows.push(`<div class="row"><span class="k">Library</span> <span class="t">Model from ${esc(p.library.model_source || 'the agent')}, needs your check</span></div>`);
  const title = p.new ? 'add a new line' : keys.length ? 'change the ' + what : 'change';
  return `<div class="prop" data-pid="${pid}"><h4>${refBtn}: ${esc(title)}</h4><div class="chg">${rows.join('')}</div>${why}${srcs}${acts()}</div>`;
}

/* ---------- messages ---------- */
/* the part card that opens a part conversation, as the one line at the top of the thread */
function ctxHTML(part) {
  if (!part) return '';
  const sec = (part.where || [])[0];
  const where = sec ? `Sheet ${sec.sheet}${sec.title ? ' · ' + sec.title : ''}` : '';
  const tip = [part.mpn, part.manufacturer, part.package, (part.nets || []).length ? 'Nets: ' + part.nets.join(', ') : ''].filter(Boolean).join(' · ');
  return `<div class="thread-h" title="${esc(tip)}"><button type="button" class="ref" data-ref="${esc(part.ref)}">${esc(part.ref)}</button>` +
    `${part.mpn ? `<span class="m">${esc(part.mpn)}</span>` : ''}${where ? `<span>${esc(where)}</span>` : ''}</div>`;
}
/* what the agent ran: one muted line, expanding to the steps when there are several */
function toolsHTML(items) {
  if (!items || !items.length) return '';
  const warn = items.some(t => t.st === 'warn');
  const mark = warn ? `<span class="warn-t">${icon('alert', 's')}</span>` : `<span class="ok-t">${icon('check', 's')}</span>`;
  if (items.length === 1) return `<div class="runs">${mark}<span>${esc([items[0].t, items[0].d].filter(Boolean).join(' · '))}</span></div>`;
  const step = t => `<li><span class="${t.st === 'warn' ? 'warn-t' : 'ok-t'}">${icon(t.st === 'warn' ? 'alert' : 'check', 's')}</span><span>${esc(t.t)}${t.d ? ` <span class="d">${esc(t.d)}</span>` : ''}</span></li>`;
  return `<details class="runs"><summary>${mark}<span>${esc(items[0].t)} · ${items.length} steps</span></summary><ul>${items.map(step).join('')}</ul></details>`;
}
function msgHTML(m, undoTs) {
  if (m.role === 'user') {
    const about = m.source ? `<div class="about">About ${chip(m.source, '')}</div>`
      : m.about ? `<div class="about">About <span${(CHAT_CHIPS[m.about.kind] || {}).mono ? ' class="m"' : ''}>${esc(m.about.label)}</span></div>` : '';
    return `<div class="msg user">${about}<div class="bubble" dir="auto">${esc(m.text)}</div></div>`;
  }
  if (m.role === 'ctx') return ctxHTML(m.part);
  if (m.role === 'agent') {
    if (m.error || m.decision) return '';      // a failed reply becomes Retry under the box; a decision is the proposal card's own state
    const props = (m.proposals || (m.proposal ? [m.proposal] : [])).map(id => diffHTML(S.proposals.find(p => p.id === id))).join('');
    const undo = m.ts === undoTs && ((m.applied || []).includes('idea.diagram.edit') || m.diagram_edit)
      ? `<div class="undo">${btn('Undo diagram change', {size: 'sm', icon: 'undo', act: 'undo-diagram', title: 'Undo diagram change'})}</div>` : '';
    return toolsHTML(m.tools) + (m.text ? `<div class="msg agent"><div class="txt" dir="auto">${chatDir(fmt(m.text))}</div>${undo}</div>` : '') + props;
  }
  return '';
}

/* ---------- conversation list ---------- */
function renderConvs() {
  const box = $('#convs'), trigger = $('[data-act="convs"]');
  if (!box) return;
  box.hidden = !convsOpen;
  if (trigger) trigger.setAttribute('aria-expanded', String(convsOpen));
  if (!convsOpen) { box.innerHTML = ''; delete box.dataset.html; return; }
  const item = r => {
    const last = r.id === S.session ? [...S.chat].reverse().find(m => (m.role === 'user' || m.role === 'agent') && m.text && !m.error && !m.decision) : r.last;
    const prev = last ? (last.role === 'user' ? 'You: ' : '') + chatPlain(last.text) : 'No messages yet';
    const anc = chatAnchor(r);
    return `<button type="button" class="conv" data-thread="${esc(r.id)}" aria-current="${r.id === S.session}">` +
      `<span class="ct"><span class="cn">${anc ? `<span class="anc">${esc(anc)}</span>` : ''}${esc(r.title || 'New chat')}</span><small>${esc(chatWhen(r.updated))}</small></span>` +
      `<span class="cp${last ? '' : ' none'}" dir="auto">${esc(prev)}</span></button>`;
  };
  const html = (S.sessions || []).map(item).join('');
  if (html !== box.dataset.html) {
    if (box.contains(document.activeElement) && box.dataset.html) return;      // never rebuild the list under the user's focus
    box.innerHTML = html;
    box.dataset.html = html;
  }
}
function chatCloseConvs(focusTrigger) {
  if (!convsOpen) return;
  convsOpen = false;
  renderConvs();
  if (focusTrigger) { const t = $('[data-act="convs"]'); if (t) t.focus(); }
}

/* ---------- the thread ---------- */
function chatStage() {
  let v = typeof mainView === 'function' ? mainView() : null;
  if (v && typeof v === 'object') v = v.tab || v.page || v.id || v.stage;
  if (!v) v = page === 'workspace' ? tab : page;
  return String(v || '').split(/[:/]/).pop();
}
const CHAT_PROMPTS = {
  idea: ['What is still open?', 'What should I decide first?'],
  bom: ['Check stock for the whole BOM', 'Compare supplier prices', 'Which parts need a second look?'],
  sch: ['Review this sheet', 'Check the power and ground connections'],
  pcb: ['What should I place first?', 'Which nets are critical?'],
  rules: ['Which rules are below the JLC minimum?', 'Why do my rules differ from the preset?'],
  outputs: ['What do I send to JLC?', 'Is the BOM ready to export?'],
  checks: ['What is still open?', 'Which findings are real issues?'],
  library: ['Which parts still need models?', 'Which models should I verify first?'],
  sources: ['Which parts have no datasheet?'],
};
function chatSuggestions() {
  if (currentRow().anchor) return ['Why did we pick this part?', 'Find an in-stock alternative', 'What should I check in the datasheet?'];
  return (CHAT_PROMPTS[chatStage()] || ['What is still open?', 'Check stock for the whole BOM', 'Compare supplier prices']).slice(0, 3);
}
function chatAnnounce(text) {
  const live = $('#chat-live');
  if (!live) return;
  live.textContent = '';
  setTimeout(() => { live.textContent = text; }, 40);
}
function renderThread(force) {
  const box = $('#msgs');
  if (!box) return;
  const key = JSON.stringify([S.session, S.chat.length, S.chat.at(-1)?.ts, S.proposals.map(p => p.status), (S.sources || []).length]);
  if (!force && key === lastChatKey) return;
  lastChatKey = key;
  let undoTs = null;                                         // only the newest diagram edit can be undone
  for (const m of S.chat) if (m.role === 'agent' && ((m.applied || []).includes('idea.diagram.edit') || m.diagram_edit)) undoTs = m.ts;
  chatLead = null;
  for (const m of S.chat) for (const id of (m.proposals || (m.proposal ? [m.proposal] : []))) {
    const p = (S.proposals || []).find(x => x.id === id);
    if (p && p.status === 'pending') chatLead = id;
  }
  const html = S.chat.length ? S.chat.map(m => msgHTML(m, undoTs)).join('') : '<p class="hint">Ask about parts, nets or rules. Any change the agent suggests waits for your approval.</p>';
  chatLead = null;
  const grew = chatSeen.session !== S.session || S.chat.length !== chatSeen.count;
  const nearEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  if (html !== chatHtml) {
    const top = box.scrollTop;
    box.innerHTML = html;
    chatHtml = html;
    box.scrollTop = grew || nearEnd ? box.scrollHeight : top;
  }
  if (chatSeen.session === S.session && S.chat.length > chatSeen.count) {       // announce only what arrived, never a re-render
    const fresh = S.chat.slice(chatSeen.count).filter(m => m.role === 'agent' && m.text && !m.error && !m.decision);
    if (fresh.length) chatAnnounce(chatPlain(fresh.at(-1).text).slice(0, 600));
  }
  chatSeen = {session: S.session, count: S.chat.length};
}

/* ---------- the composer ---------- */
function chatAutosize() {
  const t = $('#input');
  if (!t) return;
  t.style.height = 'auto';
  const cs = getComputedStyle(t);
  const lh = parseFloat(cs.lineHeight) || 20, pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
  const max = lh * 8 + pad;                                   // one line up to eight, then it scrolls
  t.style.height = Math.min(t.scrollHeight, max) + 'px';
  t.style.overflowY = t.scrollHeight > max ? 'auto' : 'hidden';
}
function chatUpdateSend() {
  const b = $('#sendbtn'), t = $('#input');
  if (b) b.disabled = pending || !(t && t.value.trim());
  chatSugs();
}
/* what went wrong with the last message, if anything: {what, message, text, ctx} */
function chatCurrentError() {
  if (pending) return null;
  if (chatError && chatError.session === S.session) return {what: 'send your message', ...chatError};
  const last = S.chat.at(-1);
  if (last && last.role === 'agent' && last.error) {
    const u = chatLastUser();
    return {what: 'get an answer', message: chatPlain(last.text).replace(/^\[[^\]]+\]\s*/, '').slice(0, 160), text: u && u.text, ctx: u && chatCtxOf(u)};
  }
  return null;
}
/* the starter questions: only when the box is free, so they never sit beside a question being written */
function chatSugs() {
  const sugs = $('#sugs'), inp = $('#input');
  if (!sugs || !S) return;
  const last = S.chat.at(-1);
  const show = !pending && !chatCurrentError() && !(inp && inp.value.trim()) && !chatChip() && (!last || last.role === 'agent' || last.role === 'ctx');
  const html = show ? chatSuggestions().map(s => `<button type="button" class="sug" data-act="suggest" data-text="${esc(s)}">${esc(s)}</button>`).join('') : '';
  if (sugs.dataset.html !== html) { sugs.innerHTML = html; sugs.dataset.html = html; }
}
function renderComposer() {
  const err = chatCurrentError();
  const st = $('#chat-status');
  if (st) {
    const k = pending ? 'work' : err ? 'err:' + err.what + err.message : '';
    if (st.dataset.k !== k) {
      st.dataset.k = k;
      st.innerHTML = pending ? `<span class="spin" aria-hidden="true"></span><span id="chat-clock">Working…</span>`
        : err ? errorLine(err.what, err.message, err.text ? btn('Retry', {size: 'sm', act: 'retry'}) : '') : '';
    }
  }
  chatUpdateSend();
  renderChatChip();
}
function chatTick() {
  const el = $('#chat-clock');
  if (!el) return;
  const s = Math.floor((Date.now() - chatSince) / 1000);
  el.textContent = 'Working…' + (s >= 2 ? ' ' + s + ' s' : '');
}

function renderChat(force) {
  if (!S) return;
  const row = currentRow();
  const anc = chatAnchor(row);
  const title = $('#convtitle');
  if (title) title.textContent = (anc ? anc + ' · ' : '') + (row.title || 'New chat');
  renderThread(force);
  renderConvs();
  renderComposer();
}

/* ---------- sending ---------- */
/* send(text) uses the chip in the composer; send(text, {ctx}) uses that context instead (Retry). */
async function send(text, opts) {
  text = (text || '').trim();
  if (!text || pending) return;
  const own = !(opts && 'ctx' in opts);
  const ctx = own ? chatChip() : opts.ctx;
  if (own) chatSetChip(null);
  chatError = null;
  pending = true;
  chatSince = Date.now();
  clearInterval(chatTimer);
  chatTimer = setInterval(chatTick, 1000);
  const entry = {role: 'user', text, ts: new Date().toISOString()};
  if (ctx && ctx.kind === 'file') entry.source = ctx.id;
  else if (ctx) entry.about = {kind: ctx.kind, id: ctx.id, label: ctx.label};
  S.chat = [...S.chat, entry];
  renderChat(true);
  try {
    const payload = {text};
    if (ctx && ctx.kind === 'file') { payload.file = ctx.id; payload.source = ctx.id; }
    else if (ctx) payload.about = entry.about;
    const res = await api('/api/chat', payload, {soft: true});      // soft: the error is drawn under the box, not toasted
    if (!res || res.error) throw new Error((res && res.error) || 'no answer');
    setState(res);
    const mountEl = document.querySelector('.diagram-mount-point');
    if (mountEl && mountEl._diagramEditor && res && res.idea && res.idea.diagram) {
      mountEl._diagramEditor.updateData(res.idea.diagram, res.diagram_touched || []);
    }
  } catch (e) {
    const msg = /failed to fetch|networkerror/i.test(e.message) ? 'no connection to the server' : e.message;
    chatError = {message: msg, text, ctx, session: S.session};
    S.chat = S.chat.filter(m => m !== entry);
    const inp = $('#input');
    if (inp && !inp.value.trim()) { inp.value = text; chatAutosize(); if (ctx && !chatChip()) chatSetChip(ctx); }     // the text is not lost
  }
  pending = false;
  clearInterval(chatTimer);
  render(true);
}
function chatSubmit() {
  const inp = $('#input');
  const t = inp.value.trim();
  if (!t || pending) return;               // while the agent works the text stays in the box
  inp.value = '';
  chatAutosize();
  send(t);
}
async function openPart(anchor) {
  const r = await api('/api/thread/open', {anchor});
  SESSION = r.session; convsOpen = false;
  await refresh(true); setView('chat');
}
async function switchSession(id) { SESSION = id; convsOpen = false; await refresh(true); setView('chat'); }

/* ---------- events ---------- */
$('#form').addEventListener('submit', e => { e.preventDefault(); chatSubmit(); });
$('#input').addEventListener('input', () => { chatAutosize(); chatUpdateSend(); });
$('#input').addEventListener('keydown', e => {
  // Enter sends, Shift+Enter is a new line, and Enter that confirms an IME composition (Hebrew, Chinese, ...) is left alone
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); chatSubmit(); }
});
document.addEventListener('click', e => {
  if (convsOpen && !e.target.closest('#convs, [data-act="convs"]')) chatCloseConvs();
});
document.addEventListener('keydown', e => {
  if (!convsOpen) return;
  if (e.key === 'Escape') { e.preventDefault(); chatCloseConvs(true); return; }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const rows = [...document.querySelectorAll('#convs .conv')];
  const i = rows.indexOf(document.activeElement);
  if (!rows.length || (i < 0 && !document.activeElement.closest('[data-act="convs"]'))) return;
  e.preventDefault();
  const next = e.key === 'ArrowDown' ? rows[i + 1] || rows[0] : (i > 0 ? rows[i - 1] : rows[rows.length - 1]);
  next.focus();
});

/* ---------- action handlers (dispatched by the delegates in core.js) ---------- */
onAct('clear-chip', async (el, d, e) => {
  chatSetChip(null);
  const inp = $('#input');
  if (inp) inp.focus();
});
onAct('convs', async (el, d, e) => {
  convsOpen = !convsOpen;
  renderConvs();
  if (convsOpen) { const cur = document.querySelector('#convs .conv[aria-current="true"]') || document.querySelector('#convs .conv'); if (cur) cur.focus(); }
});
onAct('new', async (el, d, e) => {
  const r = await api('/api/sessions/new', {});
  SESSION = r.created; convsOpen = false;
  await refresh(true);
  const inp = $('#input');
  if (inp) inp.focus();
});
onAct('suggest', async (el, d, e) => { send(d.text); });
onAct('retry', async (el, d, e) => {
  const err = chatCurrentError();
  if (!err || !err.text) return;
  const inp = $('#input');
  if (inp && inp.value.trim() === err.text) { inp.value = ''; chatAutosize(); }
  chatError = null;
  await send(err.text, {ctx: err.ctx || null});
});
onAct('review-diagram', async (el, d, e) => { go('workspace', 'idea'); });
