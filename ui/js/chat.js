/* PCB Advisor UI - chat: header and conversation list, messages, proposal cards, composer, suggestions, askAbout, sending.
   The chat is one column that shows on every view. State it owns: askCtx (the context chip), chatError, the working timer,
   the progress poll, the queue of messages typed while the agent works.
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
let chatPoller = null, chatPolling = false, chatProg = null;   // GET /api/chat/progress, once a second while pending: {current, steps, ...}
let chatStopping = false, chatStepsOpen = false;               // Stop was pressed; the turn's "Steps (n)" list is open (closed at each new turn)
let chatAtEnd = true;                     // the student is at the end of the thread: new content keeps it in view
let chatQueue = [], chatQid = 0;          // typed while the agent works: [{id, text, ctx, session}], sent as one message when the turn ends
let chatTail = null;                      // while the thread is drawn: the newest agent record, the only one whose cards have buttons
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
  if (ctx.send && ctx.text && kind && id) {      // a button's own question: sent at once, marked generated (the reply language follows what the student typed)
    if (typeof showChat === 'function') showChat();
    setView('chat');
    send(ctx.text, {ctx: {kind, id, label: String(ctx.label || id)}, generated: true});
    return;
  }
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
    : whenText(iso);          // the one date rule (kit/core): the year is always there
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
  note: 'Note', datasheet: 'Datasheet', dnp: 'Not-fitted flag', nobuy: 'Not-bought flag', refs: 'Designators', role: 'Role', library: 'Library', sheet: 'Sheet', cpl_rotation: 'CPL rotation (added in pick and place)'};
const propLabel = k => PROP_LABEL[k] || FIELD[k] || k;
const propLower = s => /^[A-Z]{2,}/.test(s) ? s : s.charAt(0).toLowerCase() + s.slice(1);
const propShow = (v, k) => k === 'cpl_rotation' ? (Number(v) ? `${Number(v) > 0 ? '+' : ''}${Number(v)}°` : 'none') : Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : (v === null || v === undefined) ? '' : String(v);
const propPlural = (n, one) => `${n} ${one}${n === 1 ? '' : 's'}`;

/* A delete proposal (store.delete_spec): null, or {whole, refs} - the refs it takes off its line (all of them for the whole line). */
function propDelete(p) {
  if (!p || p.kind === 'idea_diagram') return null;
  const c = p.changes || {};
  if (!(c.deleted || c.remove || String(p.kind || '').startsWith('delete'))) return null;
  const all = (p.before && p.before.refs) || ((lineByKey(p.line) || {}).refs) || [p.line];
  const part = Array.isArray(c.remove) ? c.remove : Array.isArray(c.refs) ? c.refs : null;
  return part && part.length && part.length < all.length ? {whole: false, refs: part} : {whole: true, refs: all};
}
const propDeleteText = (p, del) => del.whole ? `delete line ${p.line} (${del.refs.join(', ')})` : `remove ${del.refs.join(', ')} from line ${p.line}`;

/* The fields a proposal really changes: a value equal to the current one (after trimming) is not a change and is not listed or counted. */
function propChangedKeys(p) {
  const keys = Object.keys(p.changes || {});
  if (p.new || !p.before) return keys;
  return keys.filter(k => propShow(p.before[k], k).trim() !== propShow(p.changes[k], k).trim());
}

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
  const keys = propChangedKeys(p);
  const ref = diagram ? '' : ((lineByKey(p.line) || {}).refs || [p.line])[0];
  const refBtn = ref ? `<button type="button" class="ref" data-ref="${esc(ref)}">${esc(p.new ? p.line : ref)}</button>` : '';
  const labels = keys.map(k => propLabel(k));
  const del = propDelete(p);
  if (del) return propDeleteHTML(p, del);
  const what = labels.length > 2 ? propPlural(labels.length, 'field') : labels.map(propLower).join(' and ');
  if (p.status === 'approved' || p.status === 'rejected' || p.status === 'undone') {
    const ok = p.status === 'approved', undone = p.status === 'undone';
    const subj = diagram ? 'diagram changes' : `${refBtn} ${esc(p.new ? 'new line' : propLower(labels.join(', ')) || 'change')}`;
    const word = undone ? 'Undone' : ok ? (p.decided_by === 'auto' ? 'Done' : 'Approved') : 'Rejected';
    const undo = ok ? btn('Undo', {kind: 'link', size: 'sm', icon: 'undo', act: 'undo-change', pid: p.id, title: 'Put it back how it was'}) : '';
    return `<div class="prop-done ${ok ? 'ok' : 'no'}"><span class="${ok ? 'ok-t' : ''}">${icon(ok ? 'check' : 'x', 's')}</span><span>${word}: ${subj}</span>${undo}</div>`;
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
    const old = p.before ? propShow(p.before[k], k) : '', now = propShow(p.changes[k], k);
    const label = keys.length > 1 || p.library ? `<span class="k">${esc(propLabel(k))}</span> ` : '';
    return `<div class="row" dir="auto">${label}${old && !p.new ? `<s>${esc(old)}</s> &rarr; ` : ''}<b>${esc(now)}</b></div>`;
  });
  if (p.clears_offset) rows.push(`<div class="row"><span class="k">${esc(propLabel('cpl_rotation'))}</span> <span class="t">${esc(propShow(p.clears_offset, 'cpl_rotation'))} will be cleared (the part changes)</span></div>`);
  if (p.library) rows.push(`<div class="row"><span class="k">Library</span> <span class="t">Model from ${esc(p.library.model_source || 'the agent')}, needs your check</span></div>`);
  const title = p.new ? 'add a new line' : keys.length ? 'change the ' + what : 'change';
  const short = p.role_finding ? `<p class="why" dir="auto">${tag('Check qty', 'warn')} ${esc(p.role_finding)}</p>` : '';
  return `<div class="prop" data-pid="${pid}"><h4>${refBtn}: ${esc(title)}</h4><div class="chg">${rows.join('')}</div>${short}${why}${srcs}${acts()}</div>`;
}

/* A delete card: what goes (the line, its part, its refs). Approve is always the student's click (store: critical). */
function propDeleteHTML(p, del) {
  const text = propDeleteText(p, del);
  if (p.status === 'approved' || p.status === 'rejected' || p.status === 'undone') {
    const ok = p.status === 'approved', undone = p.status === 'undone';
    const word = undone ? 'Undone' : ok ? 'Approved' : 'Rejected';
    const undo = ok ? btn('Undo', {kind: 'link', size: 'sm', icon: 'undo', act: 'undo-change', pid: p.id, title: 'Put the line back'}) : '';
    return `<div class="prop-done ${ok ? 'ok' : 'no'}"><span class="${ok ? 'ok-t' : ''}">${icon(ok ? 'check' : 'x', 's')}</span><span>${word}: ${esc(text)}</span>${undo}</div>`;
  }
  const b = p.before || {}, name = [b.value || b.description, b.mpn].filter(v => v && !/^[-–—\s]+$/.test(v)).join(' · ');
  const why = p.reason ? `<p class="why" dir="auto">${esc(p.reason)}</p>` : '';
  const lead = chatLead === null || chatLead === p.id;
  return `<div class="prop" data-pid="${esc(p.id)}"><h4>${esc(text.charAt(0).toUpperCase() + text.slice(1))}</h4>` +
    `<div class="chg"><div class="row" dir="auto"><s>${esc(name || p.line)}</s></div></div>${why}` +
    `<div class="acts">${btn(del.whole ? 'Delete' : 'Remove', {kind: lead ? 'pri' : 'line', size: 'sm', decide: 'approved', pid: p.id})}${btn('Keep', {size: 'sm', decide: 'rejected', pid: p.id})}</div></div>`;
}

/* One-line summary of a proposal, for the lists inside a group. */
function propSummary(p) {
  if (p.kind === 'idea_diagram') return 'Diagram changes';
  const del = propDelete(p);
  if (del) return propDeleteText(p, del);
  const ref = ((lineByKey(p.line) || {}).refs || [p.line])[0];
  const keys = propChangedKeys(p).filter(k => k !== 'refs' || p.new);
  return `${p.new ? 'New ' : ''}${ref}: ${keys.map(k => propLabel(k).toLowerCase() + ' ' + propShow(p.changes[k], k)).join(', ')}`;
}
function propGroupTitle(ps) {
  const bom = ps.filter(p => p.kind !== 'idea_diagram').length, dia = ps.length - bom;
  return [bom && propPlural(bom, 'BOM line'), dia && propPlural(dia, 'diagram change')].filter(Boolean).join(', ');
}
/* ---- the proposed parts as ONE list, shared by this card and the BOM page ----
   Ticks are kept per proposal id, not per place, so unticking a row on the BOM page also unticks it in the chat card.
   A part whose MPN or notes say "unverified" starts unticked until the student ticks it. */
const PROP_ALREADY = /already (approved|rejected|undone)/i;       // the server's answer to a second click on the same card
let propTicks = {};
function propIsUnverified(p) {
  const c = p.changes || {};
  return /unverified/i.test([c.mpn, c.notes, p.notes].filter(Boolean).join(' '));
}
function propTicked(id) {
  if (Object.prototype.hasOwnProperty.call(propTicks, id)) return propTicks[id];
  const p = (S.proposals || []).find(x => x.id === id);
  return !(p && propIsUnverified(p));
}
/* the line's own code stands beside the proposal only while the MPN stays; a code that names another part (code_mismatch) never does */
function propKnownLcsc(c, known) {
  if (c.mpn && c.mpn !== known.mpn) return '';
  const s = (known.supply || {}).LCSC || {};          // only LCSC's answer: another supplier's code is its own part number
  if (s.code_mismatch) return '';
  return known.lcsc || s.code || '';
}
function propRowOf(p, extra) {
  const c = p.changes || {}, f = k => (c[k] === undefined || c[k] === null ? '' : propShow(c[k], k));
  if (p.kind === 'idea_diagram') return {id: p.id, ref: 'Diagram', role: 'Diagram changes', reason: p.reason, checked: propTicked(p.id), ...extra};
  const del = propDelete(p);
  if (del) return {id: p.id, ref: del.refs[0] || p.line, role: propDeleteText(p, del), reason: p.reason, checked: propTicked(p.id), ...extra};
  const ref = (Array.isArray(c.refs) && c.refs[0]) || ((lineByKey(p.line) || {}).refs || [p.line])[0];
  // the LCSC code the proposal does not carry is the one the line already has, or the code the stock check found (the export has it too)
  const known = lineByKey(p.line) || lineOfRef(ref) || {};
  const lcsc = f('lcsc') || propKnownLcsc(c, known) || p.lcsc_match || '';
  return {id: p.id, ref, isNew: !!p.new, mpn: f('mpn'), manufacturer: f('manufacturer'), package: f('package'), lcsc, value: f('value'),
    role: f('role'), reason: p.reason, short: p.role_finding, unverified: propIsUnverified(p), checked: propTicked(p.id), ...extra};
}
/* pending list: one row per proposal, with its tick */
function propListHTML(ps, cls) { return proposalTable(ps.map(p => propRowOf(p)), {cls}); }
/* The same three buttons under every list: Approve selected (N), Reject selected, Approve all. `ids` are the list's proposals. */
function propUnverifiedIds(ids) {
  return ids.filter(id => { const p = (S.proposals || []).find(x => x.id === id); return p && propIsUnverified(p); });
}
function propActsHTML(ids, lead) {
  const n = ids.filter(propTicked).length;
  const unv = propUnverifiedIds(ids).length;       // Approve all takes these too, so the button says so
  return `<div class="acts prop-acts">${btn(`Approve selected (${n})`, {kind: lead ? 'pri' : 'line', size: 'sm', act: 'prop-decide', decision: 'approved', scope: 'selected', disabled: !n})}` +
    `${btn('Reject selected', {size: 'sm', act: 'prop-decide', decision: 'rejected', scope: 'selected', disabled: !n})}` +
    `${btn(unv ? `Approve all (${unv} unverified)` : 'Approve all', {kind: 'line', size: 'sm', act: 'prop-decide', decision: 'approved', scope: 'all'})}</div>`;
}
/* after a tick changes: every copy of that tick, and every count and enabled state, follows the one shared state */
function propSyncUI() {
  document.querySelectorAll('input[data-ptick]').forEach(i => { i.checked = propTicked(i.dataset.ptick); });
  document.querySelectorAll('[data-pids]').forEach(box => {
    const n = box.dataset.pids.split(',').filter(Boolean).filter(propTicked).length;
    box.querySelectorAll('button[data-act="prop-decide"][data-scope="selected"]').forEach(b => {
      b.disabled = !n;
      if (b.dataset.decision === 'approved') { const sp = b.querySelector('span'); if (sp) sp.textContent = `Approve selected (${n})`; }
    });
  });
}
onChange(t => t.dataset && t.dataset.ptick !== undefined, async e => { propTicks[e.target.dataset.ptick] = e.target.checked; propSyncUI(); });
onAct('prop-decide', async (el, d) => {
  const box = el.closest('[data-pids]');
  const all = box ? box.dataset.pids.split(',').filter(Boolean) : [];
  const ids = d.scope === 'all' ? all : all.filter(propTicked);
  if (!ids.length) { toast('Tick at least one change'); return; }
  // Approve all also approves the parts flagged Unverified (they start unticked): one confirm names them, once
  const unv = d.scope === 'all' && d.decision === 'approved' ? propUnverifiedIds(ids) : [];
  if (unv.length) {
    const list = unv.map(id => { const r = propRowOf((S.proposals || []).find(p => p.id === id)); return `${r.ref}: ${r.mpn || '(no part number)'}`; });
    const ok = await askChoice({title: `Approve ${unv.length} unverified ${unv.length === 1 ? 'part' : 'parts'}?`,
      text: 'The agent could not confirm these part numbers. They are approved with the rest.', list, yes: `Approve all ${ids.length}`, no: false});
    if (ok !== true) return;
  }
  const r = await api('/api/proposals/batch', {ids, decision: d.decision});
  setState(r); render(true);
  const bad = (r.results || []).filter(x => !x.ok);
  const real = bad.filter(x => !PROP_ALREADY.test(x.error || ''));
  if (real.length) toast(`${real.length} not applied: ${real[0].error}`, null, {bad: true});
  else if (bad.length) toast('Already decided', null, {bad: false});       // a second click on a card that was just decided: nothing to do
});

/* Several proposals from one turn: ONE card. Pending: a table, one row per part with its tick; Approve selected / Reject selected
   / Approve all. Decided together (autonomy): one "Done" line with the table and an Undo per row. */
function propGroupHTML(ps, pending) {
  if (pending) {
    const lead = chatLead === null || ps.some(p => p.id === chatLead);
    return `<div class="prop batch" data-pids="${esc(ps.map(p => p.id).join(','))}"><h4>${esc(propGroupTitle(ps))}</h4>` +
      propListHTML(ps, 'ptbl-chat') + propActsHTML(ps.map(p => p.id), lead) + '</div>';
  }
  const rows = ps.map(p => propRowOf(p, {struck: p.status === 'undone',
    action: p.status === 'approved' ? btn('Undo', {kind: 'link', size: 'sm', icon: 'undo', act: 'undo-change', pid: p.id}) : '<span class="muted">undone</span>'}));
  const decidedBy = ps.every(p => p.decided_by === 'auto') ? 'Done' : 'Approved';
  const live = ps.filter(p => p.status === 'approved').length;
  return `<details class="prop-done ok prop-glist"><summary><span class="ok-t">${icon('check', 's')}</span><span>${decidedBy}: ${esc(propGroupTitle(ps))}${live < ps.length ? ` (${ps.length - live} undone)` : ''}</span></summary>${proposalTable(rows, {decided: true, cls: 'ptbl-chat'})}</details>`;
}
/* The cards under one agent message: decided ones as lines (grouped from two up), pending ones as one group card. */
function propsHTML(ids) {
  const ps = ids.map(id => (S.proposals || []).find(p => p.id === id)).filter(Boolean);
  const pending = ps.filter(p => p.status === 'pending');
  const done = ps.filter(p => p.status === 'approved' || p.status === 'undone');
  const other = ps.filter(p => p.status === 'rejected');
  // a delete is never part of Approve all: each pending delete is its own card (Delete / Keep), the rest is the group card
  const pendDel = pending.filter(p => propDelete(p)), pendRest = pending.filter(p => !propDelete(p));
  return (done.length > 1 ? propGroupHTML(done, false) : done.map(diffHTML).join('')) +
    other.map(diffHTML).join('') + (pendRest.length > 1 ? propGroupHTML(pendRest, true) : pendRest.map(diffHTML).join('')) + pendDel.map(diffHTML).join('');
}

/* ---------- partial turns, denials, queue ---------- */
const CHAT_PARTIAL = ['stopped', 'idle_timeout', 'total_timeout'];       // error kinds that keep the text and are drawn in the thread
const chatIsPartial = m => !!(m.partial || m.stopped || m.timed_out || CHAT_PARTIAL.includes(m.error_kind));
const chatStepName = x => String((x && typeof x === 'object' ? x.label : x) || '').trim();
const chatStepNames = m => (m.steps || []).map(chatStepName).filter(Boolean);
/* seconds the turn took: the record's own, else the gap between the student's message and the reply */
function chatElapsed(m) {
  if (typeof m.seconds === 'number') return Math.round(m.seconds);
  for (let j = S.chat.indexOf(m) - 1; j >= 0; j--) {
    if (S.chat[j].role !== 'user') continue;
    const a = Date.parse(S.chat[j].ts), b = Date.parse(m.ts);
    return isNaN(a) || isNaN(b) ? null : Math.max(0, Math.round((b - a) / 1000));
  }
  return null;
}
function chatPartialLine(m) {
  const n = chatElapsed(m), steps = chatStepNames(m);
  let head;
  if (m.error_kind === 'idle_timeout') {
    const s = m.idle_seconds ?? (CONFIG && CONFIG.agent && CONFIG.agent.idle_timeout_seconds);
    head = s ? `No output for ${s} s — stopped` : 'No output for a while — stopped';
  } else if (m.error_kind === 'total_timeout' || (m.timed_out && m.error_kind !== 'stopped')) {
    head = n != null ? `Stopped after ${n} s (time limit)` : 'Stopped at the time limit';
  } else head = n != null ? `Stopped after ${n} s` : 'Stopped';
  const shown = steps.slice(0, 5).join(', ') + (steps.length > 5 ? ` +${steps.length - 5} more` : '');
  return head + (steps.length ? ` · steps: ${shown}` : '');
}
/* A turn that did not finish: what it wrote, one muted line, and (on the newest one) Continue and Retry. */
function chatPartialHTML(m, live) {
  const raw = m.error && /^\[[^\]]+\]/.test(String(m.text || '')) ? '' : m.text;      // an engine error line is not an answer
  const steps = chatStepNames(m).slice(-12);
  const cont = 'Continue from where you stopped.' + (steps.length ? ' Steps already done: ' + steps.join('; ') : '');
  const acts = live ? `<div class="acts">${btn('Continue', {size: 'sm', act: 'chat-continue', text: cont})}${btn('Retry', {size: 'sm', act: 'retry'})}</div>` : '';
  return (raw ? `<div class="msg agent"><div class="txt" dir="auto">${chatDir(fmt(raw))}</div></div>` : '') +
    `<div class="chat-stopped" role="status"><span>${esc(chatPartialLine(m))}</span>${acts}</div>`;
}
/* what the advisor tried to run, as one line: the command, the file or the address, else the tool's name */
function chatDeniedLabel(d) {
  const i = d.input || {};
  return String(d.label || i.command || i.file_path || i.path || i.url || d.tool || 'a command');
}
/* One card per command the engine refused. A single command can be allowed for good; a combined one cannot. */
/* A refused shell command that is not one of the tool's own scripts (`python -c ...`, a heredoc, `ls`) is the agent's business:
   the server flags it `internal`, and an older record without the flag is judged the same way. Never offered as "Allow", never drawn. */
const chatDeniedInternal = d => d.internal != null ? !!d.internal
  : /^(Bash|PowerShell)$/.test(d.tool || '') && !/scripts[\\/]/.test((d.input || {}).command || '') || /(^|\s)(python[\d.]*|py)(\.exe)?\s+-[a-z]*c\b/i.test((d.input || {}).command || '');
function chatDeniedHTML(m, live) {
  if (!live) return '';
  return (m.denied || []).map((d, k) => {
    if (chatDeniedInternal(d)) return '';
    const id = d.id ?? k;
    const why = d.reason ? `<p class="why" dir="auto">${esc(d.reason)}</p>` : '';
    const body = d.compound
      ? `<p class="why">${m.split_retry ? 'It tried a combined command; the advisor is asked to run the parts one by one. Retry if it does not.' : 'It tried a combined command; Retry asks it to run them one by one.'}</p><div class="acts">${btn('Retry', {size: 'sm', act: 'retry'})}</div>`
      : `<div class="acts">${btn('Allow and retry', {kind: 'pri', size: 'sm', act: 'chat-allow', ts: m.ts, idx: id})}</div>`;
    return `<div class="prop chat-deny"><h4>The advisor wanted to run: <span class="m">${esc(chatDeniedLabel(d))}</span></h4>${why}${body}</div>`;
  }).join('');
}
const chatQueueOf = session => chatQueue.filter(q => q.session === session);
/* the messages typed while the agent works: muted bubbles under the thread, each removable */
function chatQueueHTML() {
  return chatQueueOf(S.session).map(q => `<div class="msg user queued"><div class="about">Queued${btn('', {kind: 'link', size: 'sm', icon: 'x', act: 'queue-remove', qid: q.id, title: 'Remove from the queue'})}</div>` +
    `<div class="bubble" dir="auto">${esc(q.text)}</div></div>`).join('');
}
function chatEnqueue(text) {
  if (window.usage) window.usage('queued', {text});
  const ctx = chatChip();
  if (ctx) chatSetChip(null);
  chatQueue = [...chatQueue, {id: ++chatQid, text, ctx, session: S.session}];
  chatAtEnd = true;                     // the student's own words: show them
  renderThread(true);
}
/* how a turn ended, for the queue: 'ok', 'stopped' (the student pressed Stop) or 'error' (nothing is sent) */
function chatOutcome(m) {
  if (!m || m.role !== 'agent') return 'ok';
  if (m.stopped || m.error_kind === 'stopped') return 'stopped';
  return m.error || chatIsPartial(m) ? 'error' : 'ok';
}
/* the queue of one conversation goes out as ONE message, texts joined by a blank line */
async function chatFlush(session) {
  const mine = chatQueueOf(session);
  if (!mine.length || !S || S.session !== session) return;
  chatQueue = chatQueue.filter(q => q.session !== session);
  const withCtx = mine.find(q => q.ctx);
  await send(mine.map(q => q.text).join('\n\n'), {ctx: withCtx ? withCtx.ctx : null, queued: true});
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
const CLAIMED_TIP = 'reported by the agent, not confirmed by the engine';
function toolMark(t) {
  if (t.s === 'claimed') return `<span class="dim-t" title="${CLAIMED_TIP}">${icon('check', 's')}</span>`;
  if (t.st === 'bad') return `<span class="bad-t">${icon('x', 's')}</span>`;
  return t.st === 'warn' ? `<span class="warn-t">${icon('alert', 's')}</span>` : `<span class="ok-t">${icon('check', 's')}</span>`;
}
/* "Worked: 3 steps", closed. Inside: each step in plain words; the command line (`raw`) is the last, muted detail. */
function toolsHTML(items) {
  if (!items || !items.length) return '';
  const mark = toolMark(items.find(t => t.st === 'bad') || items.find(t => t.st === 'warn') || items[0]);
  const tip = items.every(t => t.s === 'claimed') ? ` title="${CLAIMED_TIP}"` : '';
  const step = t => `<li${t.s === 'claimed' ? ` title="${CLAIMED_TIP}"` : ''}>${toolMark(t)}<span>${esc(t.t)}${t.d ? ` <span class="d">${esc(t.d)}</span>` : ''}${t.raw ? ` <span class="d raw">${esc(t.raw)}</span>` : ''}</span></li>`;
  return `<details class="runs"${tip}><summary>${mark}<span>Worked: ${items.length} step${items.length > 1 ? 's' : ''}</span></summary><ul>${items.map(step).join('')}</ul></details>`;
}
/* The chip under an agent reply, in words: "bom.propose:R1" is "BOM proposal: R1". The server's text after the kind
   (counts, file names) is kept as the detail; an unknown kind is its name, humanised. */
const CHAT_ACT_LABELS = {
  'bom.propose': 'BOM proposal', 'netlist.write': 'Netlist written: sheet', 'library.add': 'Library: part added',
  'library.build': 'Library built', 'part.attach_datasheet': 'Datasheet attached', 'thread.open': 'Conversation opened',
  'idea.propose': 'Idea proposal', 'idea.describe': 'Idea described', 'idea.confirm': 'Idea confirmed', 'idea.diagram': 'Diagram drawn',
  'idea.diagram.edit': 'Diagram changed', 'altium.draw_schematic': 'Altium: schematic drawn', 'altium.place_pcb': 'Altium: place parts',
  'altium.route_pcb': 'Altium: route', 'altium.skeleton': 'Altium: project skeleton', 'altium.add_sheet': 'Altium: sheet added',
  'jlc.gerber_zip': 'Gerber zip made', 'jlc.pickup': 'JLC report picked up', 'order.check': 'Order check', 'dfm.triage': 'DFM findings sorted',
};
/* A chip that names a part ("BOM proposal: R1") is a button: it opens the part, or the card that waits for it. Other chips stay text. */
const CHAT_ACT_REF = /^bom\.propose\s*:\s*([A-Za-z]+\d+[A-Za-z0-9_]*)/i;
function chatActChip(a, cls, tip) {
  const m = CHAT_ACT_REF.exec(String(a));
  const label = esc(chatActLabel(a));
  return m ? `<button type="button" class="chat-act ${cls}" data-act="chat-act-open" data-ref="${esc(m[1])}" title="${esc(tip || 'Show it')}">${label}</button>`
    : `<span class="chat-act ${cls}" title="${esc(tip || a)}">${label}</span>`;
}
onAct('chat-act-open', async (el, d) => {
  const ref = d.ref, l = lineOfRef(ref);
  const pend = (S.proposals || []).find(p => p.status === 'pending' && (p.line === ref || ((p.changes || {}).refs || []).includes(ref)));
  if (!pend && l) { select(l.key); return; }
  if (!pend) { toast(`${ref} is not in the BOM and no proposal for it is waiting`, null, {bad: false}); return; }
  const flash = () => {
    // the same card can also be listed on a page that is not shown (a phone shows one at a time): only a row on screen counts, the chat's first
    const rows = [...document.querySelectorAll(`tr[data-pid="${CSS.escape(pend.id)}"]`)].filter(r => r.getClientRects().length);
    const row = rows.find(r => r.closest('.chat')) || rows[0];
    if (!row) return false;
    row.scrollIntoView({block: 'center'});
    row.classList.add('flash');
    setTimeout(() => row.classList.remove('flash'), 1800);
    return true;
  };
  if (flash()) return;                       // the card is in the chat: stay (on a phone another view would hide it)
  go('workspace', 'bom');
  setTimeout(flash, 150);
});
function chatActLabel(a) {
  const s = String(a), m = s.match(/^([a-z_]+(?:\.[a-z_]+)+)\s*(?::\s*(.*))?$/is);
  if (!m) return s.length > 120 ? s.slice(0, 120) + '…' : s;
  const name = CHAT_ACT_LABELS[m[1]] || (m[1].replace(/[._]+/g, ' ').replace(/^./, c => c.toUpperCase()));
  const rest = (m[2] || '').trim();
  return rest ? `${name}${name.endsWith(':') || /sheet$/.test(name) ? ' ' : ': '}${rest.length > 120 ? rest.slice(0, 120) + '…' : rest}` : name;
}
/* A refused action: what failed and why, short. Altium's own text (a DRC list runs to 600 characters) opens on a click, so
   nothing is hidden and nothing has to be read to find the reason. */
function chatRefusedHTML(a) {
  const s = String(a);
  if (s.length <= 220) return `<span class="chat-act bad" title="Not applied">${esc(s)}</span>`;
  let cut = s.slice(0, 220).replace(/[\s;,(:][^\s;,(:]*$/, '');
  if (cut.length < 160) cut = s.slice(0, 220);          // no place to break (a long path): the reason still shows
  return `<details class="chat-act bad" title="Not applied"><summary>${esc(cut)}<span class="more">… more</span></summary>${esc(s.slice(cut.length))}</details>`;
}
/* which engine and model wrote an answer: "Claude Code · sonnet", muted under it */
function chatEngineName(id) {
  const e = ((CONFIG && CONFIG.engines) || []).find(x => x.id === id);
  return (e && (e.title || e.name)) || String(id || '').replace(/_/g, ' ');
}
function chatEngineLabel(id, model) { return id ? chatEngineName(id) + (model ? ' · ' + model : '') : ''; }
/* R2/W22: the "no check ran" footer goes on an agent answer that states a zero count of errors, issues, problems or violations as a claim about the
   design when no CHECK ran in its turn. "A check ran" is read from what the server recorded on the message (a tool chip with `check: true`, the
   script it ran, or an applied action that is a check), never from the words of a label. A document read or a web look-up is not a check. The same
   holds for an earlier agent message of the turn, or a "Scope:" line (the tool's own review).
   The claim: a zero count next to the word ("0 errors", "no ERC errors", "0 DRC violations", "Errors: 0", and the Hebrew forms with or without a digit).
   Numbers that are not such a count ("0 ohm", "PA0 and", "keep BOOT0 low") never match. Hebrew words are built from character codes (no Hebrew
   literal in the source). */
const CHAT_CHECK_SCRIPT = /^(?:verify_part|schematic|schematic_review|board|lint|validate_netlist|rules|order_check|requirements|dfm|drc_origin|drc_jlc_map|verify_sources)\.py$/i;
const CHAT_CHECK_ACTION = /^(?:altium\.run_drc|order\.check|dfm\.triage)\b/;
const heWord = (...codes) => String.fromCharCode(...codes);
const HE_ERRORS = [heWord(1513, 1490, 1497, 1488, 1493, 1514), heWord(1489, 1506, 1497, 1493, 1514), heWord(1492, 1508, 1512, 1493, 1514),
  heWord(1502, 1502, 1510, 1488, 1497, 1501)].join('|');
const HE_NONE = [heWord(1488, 1497, 1503), heWord(1500, 1488, ' '.charCodeAt(0), 1504, 1502, 1510, 1488, 1493), heWord(1500, 1500, 1488),
  heWord(1488, 1508, 1505), heWord(1500, 1488, 32, 1502, 1510, 1488, 1514, 1497)].join('|');
const CHAT_ZERO_CLAIM = [
  /(?:^|[^\w.,\/-])(?:0|zero|no)\s+(?:[\w-]+\s+){0,2}(?:errors?|issues?|problems?|violations?|findings?)\b/i,
  /\b(?:errors?|issues?|problems?|violations?|findings?)\s*[:=]\s*(?:0|zero|none)\b/i,
  new RegExp('(?:^|[^\\w.,/-])0\\s+(?:' + HE_ERRORS + ')', 'u'),
  new RegExp('(?:^|\\s)(?:' + HE_NONE + ')\\s+(?:\\S+\\s+)?(?:' + HE_ERRORS + ')', 'u'),
  new RegExp('(?:' + HE_ERRORS + ')\\s*:\\s*0'),
  /(?:^|[^\w.,\/-])0\s+(?:fehler|probleme|verstöße|erreurs|problèmes|errores|problemas)(?![\p{L}])/iu,
];
function chatHasCheck(m) {
  return (m.tools || []).some(x => x && (x.check === true || CHAT_CHECK_SCRIPT.test(String(x.script || ''))))
    || (m.applied || []).some(a => CHAT_CHECK_ACTION.test(String(a)));
}
function chatUncheckedClaim(m) {
  const t = m.text || '';
  if (m.role !== 'agent' || m.by === 'button' || m.followup || chatHasCheck(m) || /\bScope:/.test(t)) return false;
  if (!CHAT_ZERO_CLAIM.some(rx => rx.test(t))) return false;
  const chat = (typeof S !== 'undefined' && S && S.chat) || [];
  const at = chat.indexOf(m);
  for (let i = at > 0 ? at - 1 : chat.length - 1; i >= 0 && at !== 0; i--) {
    const p = chat[i];
    if (p.role === 'user') break;
    if (p.role === 'agent' && (chatHasCheck(p) || /\bScope:/.test(p.text || ''))) return false;
  }
  return true;
}
function chatNotChecked(m) {      // the tool's own review lists what it did not check: a click shows every item, never only the first few
  const l = m.not_checked || [];
  return l.length > 8 ? `<details class="chat-act"><summary>All ${l.length} things not checked</summary><ul>${l.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>` : '';
}
function chatEngineFoot(m) {
  const l = chatEngineLabel(m.engine, m.model);
  const claim = chatUncheckedClaim(m);
  const scope = claim ? '<div class="eng" title="R2/W22">No check ran behind this sentence: the model read the sheet and wrote it. It is not a statement that the sheet is correct.</div>' : '';
  return (l ? `<div class="eng" title="The engine and model that wrote this answer">${esc(l)}</div>` : '') + scope;
}
function msgHTML(m, undoTs) {
  if (m.role === 'user') {
    const about = m.source ? `<div class="about">About ${chip(m.source, '')}</div>`
      : m.about ? `<div class="about">About <span${(CHAT_CHIPS[m.about.kind] || {}).mono ? ' class="m"' : ''}>${esc(m.about.label)}</span></div>` : '';
    return `<div class="msg user">${about}<div class="bubble" dir="auto">${esc(m.text)}</div></div>`;
  }
  if (m.role === 'ctx') return ctxHTML(m.part);
  if (m.role === 'agent') {
    const live = m === chatTail;
    if (chatIsPartial(m)) return toolsHTML(m.tools) + chatPartialHTML(m, live) + propsHTML(m.proposals || (m.proposal ? [m.proposal] : [])) + chatDeniedHTML(m, live);
    if (m.error || m.decision) return '';      // a failed reply becomes Retry under the box; a decision is the proposal card's own state
    if (m.by === 'button') {                    // the note the server wrote for the agent after a button step: its text is not for the student, the chips are
      const chips = (m.applied || []).map(a => (m.warned || {})[a]
        ? `<span class="chat-act warn" title="Applied with warnings"><b>${esc(chatActLabel(a.split(/[:( ]/)[0]))} applied with warnings:</b> ${esc(m.warned[a])}</span>`
        : chatActChip(a, 'ok', a)).join('');
      return chips ? `<div class="msg agent note"><div class="acts">${chips}</div></div>` : '';
    }
    const props = propsHTML(m.proposals || (m.proposal ? [m.proposal] : []));
    const undo = m.ts === undoTs && ((m.applied || []).includes('idea.diagram.edit') || m.diagram_edit)
      ? `<div class="undo">${btn('Undo diagram change', {size: 'sm', icon: 'undo', act: 'undo-diagram', title: 'Undo diagram change'})}</div>` : '';
    // the agent thinks the idea is agreed: the student confirms with one click (no quote check)
    const ready = (m.applied || []).includes('idea.ready') && S.idea && !S.idea.confirmed
      ? `<div class="undo">${btn('Confirm idea', {size: 'sm', kind: 'line', icon: 'check', act: 'chat-confirm-idea', disabled: !((S.idea.agreed || []).length), title: 'Save the draft and mark the idea as agreed'})}</div>` : '';
    // an applied result that carries a warning is amber and shows it in full: "done" must never hide what Altium or a check flagged
    const warned = m.warned || {};
    const done = (m.applied || []).filter(a => a !== 'idea.ready').map(a => warned[a]
      ? `<span class="chat-act warn" title="Applied with warnings"><b>${esc(a.split(/[:( ]/)[0])} applied with warnings:</b> ${esc(warned[a])}</span>`
      : chatActChip(a, 'ok', a))
      .concat((m.refused || []).map(a => chatRefusedHTML(a) +
        (/^(altium|library)\./.test(a) && live ? btn('Retry', {kind: 'link', size: 'sm', act: 'suggest', text: 'Run this again: ' + String(a).slice(0, 300)}) : '')));
    const acts = done.length ? `<div class="acts">${done.join('')}</div>` : '';
    // the stored text ends with "(Not applied: ...)" for older readers; the red chips say it here
    if ((m.refused || []).length && m.text) m = {...m, text: m.text.replace(/\n*\((?:Not applied|\u05dc\u05d0 \u05d4\u05d5\u05d7\u05dc): [\s\S]*\)\s*$/, '')};
    // the engine writes its text before the actions run, so "placed" may stand above a red chip: say so before the text
    const nRef = (m.refused || []).length;
    const after = m.followup ? '<div class="chat-followup" role="note">After the results</div>' : '';     // the server's own second turn, written once the actions had answered
    const head = after + (nRef && m.text ? `<div class="acts"><span class="chat-act bad" role="note">Not all of this happened: ${nRef} step${nRef > 1 ? 's' : ''} failed (red, below)</span></div>` : '');
    return toolsHTML(m.tools) + (m.text ? `<div class="msg agent">${head}<div class="txt" dir="auto">${chatDir(fmt(m.text, m.cites))}</div>${chatNotChecked(m)}${acts}${undo}${ready}${chatEngineFoot(m)}</div>` : '') + props + chatDeniedHTML(m, live);
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
  bom: ['Check stock for the whole BOM', 'Which parts still need models?', 'Which parts need a second look?'],
  sch: ['Review this sheet', 'Check the power and ground connections'],
  pcb: ['What should I place first?', 'Which nets are critical?'],
  rules: ['Which rules are below the JLC minimum?', 'Why do my rules differ from the preset?'],
  outputs: ['What do I send to JLC?', 'Is the BOM ready to export?'],
  checks: ['What is still open?', 'Which findings are real issues?'],
  sources: ['Which parts have no datasheet?'],
};
/* The chips come from the project's state: the server's stages[] (the stage where the work goes on: its open issues, or its next step),
   then the page's own starter questions. When the agent's last turn asked a yes/no (its structured `ask`), the two answers come first
   as one-click quick replies. [{text, label, quick}] */
const CHAT_STAGE_NAMES = {idea: 'the idea', bom: 'the BOM', sch: 'the schematic', pcb: 'the layout', rules: 'the rules', outputs: 'the outputs', checks: 'DFM'};
function chatNextText(n) { return String(n && n.label || '').replace(/^Next:\s*/i, '').trim(); }
function chatSuggestionItems() {
  const items = [];
  const last = S.chat.at(-1);
  if (last && last.role === 'agent' && last.ask && last.ask.question) {
    items.push({text: last.ask.yes || 'Yes', quick: true}, {text: last.ask.no || 'No', quick: true});
  }
  if (currentRow().anchor) {
    items.push(...['Why did we pick this part?', 'Find an in-stock alternative', 'What should I check in the datasheet?'].map(text => ({text})));
    return items.slice(0, items.some(i => i.quick) ? 4 : 3);
  }
  const stages = Array.isArray(S.stages) ? S.stages : [];
  const here = stages.find(x => x && x.primary) || stages.find(x => x && x.state && x.state !== 'clean');
  const name = here && (CHAT_STAGE_NAMES[here.id] || here.id);
  if (here && here.state === 'issues') items.push({text: `What is wrong in ${name}${here.open ? ` (${here.open} open)` : ''}, and how do I fix it?`});
  const nxt = chatNextText(here && here.next);
  if (nxt) items.push({text: `Help me with the next step: ${nxt}`});
  items.push(...(CHAT_PROMPTS[chatStage()] || CHAT_PROMPTS.checks).map(text => ({text})));
  const seen = new Set();
  return items.filter(i => !seen.has(i.text) && seen.add(i.text)).slice(0, items.some(i => i.quick) ? 4 : 3);
}
const chatSuggestions = () => chatSuggestionItems().map(i => i.text);
function chatAnnounce(text) {
  const live = $('#chat-live');
  if (!live) return;
  live.textContent = '';
  setTimeout(() => { live.textContent = text; }, 40);
}
/* The thread follows its end only while the student is there. Scrolled up, they keep their place and "Jump to latest" shows. */
function chatFollow() {
  const sc = $('#msgs');
  if (!sc) return;
  if (chatAtEnd && sc.scrollHeight - sc.scrollTop - sc.clientHeight > 1) sc.scrollTop = sc.scrollHeight;
  const j = $('#chat-jump');
  if (j && j.hidden !== chatAtEnd) j.hidden = chatAtEnd;
}
function chatJump() {
  const sc = $('#msgs'), j = $('#chat-jump');
  const hadFocus = j && document.activeElement === j;
  chatAtEnd = true;
  chatFollow();
  if (hadFocus && sc) sc.focus({preventScroll: true});      // the button hides: focus stays in the chat
}
function renderThread(force) {
  const box = $('#chat-thread');
  if (!box) return;
  const key = JSON.stringify([S.session, S.chat.length, S.chat.at(-1)?.ts, S.proposals.map(p => p.status), (S.sources || []).length, chatQueueOf(S.session).map(q => q.id),
    S.chat.filter(m => m.cites).map(m => [m.ts, m.cites.state, Object.values(m.cites.items || {}).map(i => i.status)])]);
  if (!force && key === lastChatKey) return;
  lastChatKey = key;
  let undoTs = null;                                         // only the newest diagram edit can be undone
  for (const m of S.chat) if (m.role === 'agent' && ((m.applied || []).includes('idea.diagram.edit') || m.diagram_edit)) undoTs = m.ts;
  chatLead = null;
  chatTail = [...S.chat].reverse().find(m => m.role === 'agent') || null;
  for (const m of S.chat) for (const id of (m.proposals || (m.proposal ? [m.proposal] : []))) {
    const p = (S.proposals || []).find(x => x.id === id);
    if (p && p.status === 'pending') chatLead = id;
  }
  const html = (S.chat.length ? S.chat.map(m => msgHTML(m, undoTs)).join('') : '<p class="hint">Ask about parts, nets or rules. Routine changes are done for you and can be undone; important ones (parts, Altium, ordering) wait for your approval.</p>') + chatQueueHTML();
  chatLead = null;
  chatTail = null;
  // another conversation, or the student's own new message: show the end. An answer that arrives while they read above does not move them.
  if (chatSeen.session !== S.session || (S.chat.length > chatSeen.count && S.chat.at(-1).role === 'user')) chatAtEnd = true;
  if (html !== chatHtml) {
    box.innerHTML = html;
    chatHtml = html;
    chatFollow();
    document.fonts?.ready.then(chatFollow);      // fonts settle after this: still at the end, or the last reply's chips sit below the fold
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
  if (b) {
    b.disabled = pending ? chatStopping : !(t && t.value.trim());
    const mode = pending ? 'stop' : 'send';
    if (b.dataset.m !== mode) {                                // while the agent works the button is Stop; Enter still queues the text
      b.dataset.m = mode;
      b.classList.toggle('stop', pending);
      b.title = pending ? 'Stop' : 'Send';
      b.setAttribute('aria-label', b.title);
      b.innerHTML = icon(pending ? 'stop' : 'up');
    }
  }
  chatSugs();
}
/* what went wrong with the last message, if anything: {what, message, text, ctx} */
function chatCurrentError() {
  if (pending) return null;
  if (chatError && chatError.session === S.session) return {what: 'send your message', ...chatError};
  const last = S.chat.at(-1);
  if (last && last.role === 'agent' && (last.error || (last.error_kind && !CHAT_PARTIAL.includes(last.error_kind)) || chatIsPartial(last))) {
    const u = chatLastUser();
    if (chatIsPartial(last)) return null;                      // drawn in the thread, with its own Continue and Retry
    return {what: 'get an answer', message: chatPlain(last.text).replace(/^\[[^\]]+\]\s*/, '').slice(0, 160), text: u && u.text, ctx: u && chatCtxOf(u),
      kind: last.error_kind, retry_at: last.retry_at};
  }
  return null;
}
/* the starter questions: only when the box is free, so they never sit beside a question being written */
function chatSugs() {
  const sugs = $('#sugs'), inp = $('#input');
  if (!sugs || !S) return;
  const last = S.chat.at(-1);
  const show = !pending && !chatCurrentError() && !(inp && inp.value.trim()) && !chatChip() && (!last || last.role === 'agent' || last.role === 'ctx');
  const html = show ? chatSuggestionItems().map(s => `<button type="button" class="sug${s.quick ? ' quick' : ''}" data-act="suggest" data-text="${esc(s.text)}">${esc(s.text)}</button>`).join('') : '';
  if (sugs.dataset.html !== html) { sugs.innerHTML = html; sugs.dataset.html = html; chatFollow(); }
}
/* the local time a usage limit lifts: a clock time today, else the date too */
function chatResetAt(iso) {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return '';
  const t = d.toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'});
  return d.toDateString() === new Date().toDateString() ? t : whenText(iso, true);
}
/* One friendly card for an engine failure the server named; '' for any other kind, which keeps the plain error line. */
function chatErrorCard(err) {
  const retry = err.text ? btn('Retry', {size: 'sm', act: 'retry'}) : '';
  const card = (html, acts) => `<div class="note bad chat-card" role="alert"><span>${html}</span><span class="acts">${acts || ''}${retry}</span></div>`;
  const settings = label => btn(label, {kind: 'link', size: 'sm', act: 'chat-settings', title: 'Settings › Engine'});
  const checks = btn('Run checks', {kind: 'link', size: 'sm', act: 'chat-checks', title: 'Check what is missing and how to fix it'});
  if (err.kind === 'not_logged_in') return card('Claude Code is not signed in. Open a terminal, run <span class="m">claude auth login</span>, then press Retry.', checks);
  if (err.kind === 'not_installed') {
    return card('Claude Code is not installed. See the <a href="https://github.com/ilaish5/pcb-advisor#install-about-5-minutes" target="_blank" rel="noopener">install steps</a>, or pick another engine.', checks + settings('Open Settings › Engine'));
  }
  if (err.kind === 'usage_limit') {
    const at = chatResetAt(err.retry_at);
    return card('Your Claude plan limit is reached' + (at ? `; it resets at ${esc(at)}` : '') + '.', settings('Switch engine'));
  }
  return '';
}
function renderComposer() {
  const err = chatCurrentError();
  // the last item of the thread, right above the composer: the turn in flight, the follow-up round, or what went wrong
  const st = $('#chat-status');
  if (st) {
    const steps = chatProg && Array.isArray(chatProg.steps) ? chatProg.steps.map(chatStepName).filter(Boolean) : [];
    const fu = !pending && S && S.followup_running;       // the server's second turn checks the results of the actions (text only)
    const k = pending ? 'work' : fu ? 'followup' : err ? 'err:' + err.what + err.message + (err.kind || '') + (err.retry_at || '') : '';
    if (st.dataset.k !== k) {
      st.dataset.k = k;
      st.innerHTML = pending ? chatWorkHTML()
        : fu ? `<div class="chat-work chat-followup-run"><div class="chat-line"><span class="spin" aria-hidden="true"></span><span>Checking the results…</span>${btn('Stop', {size: 'sm', act: 'chat-followup-stop'})}</div></div>`
        : err ? (chatErrorCard(err) || errorLine(err.what, err.message, err.text ? btn('Retry', {size: 'sm', act: 'retry'}) : '')) : '';
    }
    if (pending) chatStepsSync(st, steps);
    chatFollow();
  }
  chatUpdateSend();
  renderChatChip();
  if (pending) chatTick();
}
/* The turn in flight, drawn once per turn and then patched, so an open list, the focus and the hover survive each poll:
   "Talking to Altium · 17 s" on one line, and under it "Steps (n)", closed until the student opens it. */
function chatWorkHTML() {
  return `<div class="chat-work live"><div class="chat-line"><span class="spin" aria-hidden="true"></span><span id="chat-clock">Working…</span></div>` +
    `<details class="chat-steps"${chatStepsOpen ? ' open' : ''} hidden><summary>Steps (<span class="n">0</span>)</summary><ul></ul></details></div>`;
}
function chatStepsSync(st, steps) {
  const d = st.querySelector('.chat-steps');
  if (!d) return;
  const k = steps.join('\n');
  if (d.dataset.k === k) return;
  d.dataset.k = k;
  d.hidden = !steps.length;
  d.querySelector('.n').textContent = steps.length;
  d.querySelector('ul').innerHTML = steps.map(x => `<li dir="auto" title="${esc(x)}">${esc(x)}</li>`).join('');
}
function chatTick() {
  const el = $('#chat-clock');
  if (!el) return;
  const s = Math.floor((Date.now() - chatSince) / 1000);
  const cur = chatProg && chatProg.current ? String(chatProg.current) : '';
  el.textContent = chatStopping ? 'Stopping…' : (cur || 'Working…') + (s >= 2 ? (cur ? ' · ' : ' ') + s + ' s' : '');
}
/* one look at the server's progress for the turn in flight; a failed look is ignored, the next second asks again */
async function chatPoll() {
  if (!pending || chatPolling) return;
  chatPolling = true;
  try {
    const p = await api('/api/chat/progress', undefined, {soft: true});
    if (pending && chatResumed && p && !p.error && !p.running) { chatPolling = false; await chatResumeEnd(); return; }       // the reply of a turn started before a reload has arrived
    if (pending && p && !p.error) { chatProg = p; chatFails = 0; renderComposer(); }
    else if (pending && chatResumed && ++chatFails >= 8) { chatPolling = false; await chatResumeEnd(); return; }       // the server does not answer: never stay busy for good
  } catch (e) { if (pending && chatResumed && ++chatFails >= 8) { chatPolling = false; await chatResumeEnd(); return; } }
  chatPolling = false;
}
/* A page loaded while the server is still working on a reply (the page that sent it was reloaded): show the working line until it arrives. */
let chatResumed = false, chatFails = 0;
async function chatResume() {
  if (pending) return;
  let p = null;
  try { p = await api('/api/chat/progress', undefined, {soft: true}); } catch (e) { return; }
  if (pending || !p || p.error || !p.running) return;
  pending = true;
  chatResumed = true;
  chatSince = Date.now() - (p.seconds || 0) * 1000;
  chatFails = 0;
  chatProg = p;
  chatStopping = false;
  chatStepsOpen = false;
  clearInterval(chatTimer); chatTimer = setInterval(chatTick, 1000);
  clearInterval(chatPoller); chatPoller = setInterval(chatPoll, 1000);
  renderChat(true);
}
async function chatResumeEnd() {
  pending = false;
  chatResumed = false;
  chatStopping = false;
  clearInterval(chatTimer);
  clearInterval(chatPoller);
  chatProg = null;
  const before = S.chat.length;
  for (let i = 0; i < 6; i++) {       // the answer is written just after the turn ends: read until it is there (about 5 s at most)
    try { await refresh(true); } catch (e) { /* the next refresh reads it */ }
    if (S.chat.length > before) break;
    await new Promise(r => setTimeout(r, 1000));
  }
  render(true);
  await chatFlush(S.session);       // what was typed while it worked goes now
}
async function chatStop() {
  if (!pending || chatStopping) return;
  chatStopping = true;
  chatUpdateSend();
  chatTick();
  try {
    const r = await api('/api/chat/stop', {}, {soft: true});
    if (r && r.error && pending) { chatStopping = false; chatUpdateSend(); chatTick(); }      // 409: the turn was over already (its answer is on the way): never stay on "Stopping…"
  } catch (e) { if (pending) { chatStopping = false; chatUpdateSend(); chatTick(); } }       // the click did not reach the server: Stop is offered again
}

function renderChat(force) {
  if (!S) return;
  const row = currentRow();
  const anc = chatAnchor(row);
  const title = $('#convtitle');
  if (title) title.textContent = (anc ? anc + ' · ' : '') + (row.title || 'New chat');
  const eng = $('#chat-engine');
  if (eng && CONFIG) eng.textContent = chatEngineLabel(CONFIG.engine, (CONFIG.agent && CONFIG.agent.model) || '');
  renderThread(force);
  renderConvs();
  renderComposer();
}

/* ---------- sending ---------- */
/* An action that changed Altium or the library leaves the pictures in the open Schematic / Layout view stale:
   drop what they cached so the next render draws them again (the BOM view already reads the new state). */
const CHAT_REDRAW = /^(altium\.(place_pcb|draw_schematic|route_pcb)|library\.build)\b/;
async function chatReloadViews(m) {
  if (!m || m.role !== 'agent' || !(m.applied || []).some(a => CHAT_REDRAW.test(String(a)))) return;
  svgCache = {key: '', text: ''};
  pcbSvgCache = {key: '', text: ''};
  pvSchErr = '';
  pvPcbErr = '';
  try { await loadAltium(true); } catch (e) { /* the pictures are drawn from the old link */ }
}
/* send(text) uses the chip in the composer; send(text, {ctx}) uses that context instead (Retry). */
async function send(text, opts) {
  text = (text || '').trim();
  if (!text || pending) return;
  const own = !(opts && 'ctx' in opts);
  const ctx = own ? chatChip() : opts.ctx;
  if (own) chatSetChip(null);
  chatError = null;
  pending = true;
  chatResumed = false;
  chatSince = Date.now();
  chatProg = null;
  chatStopping = false;
  chatStepsOpen = false;                // each turn's steps start closed
  const turnSession = S.session;
  let outcome = 'ok';
  clearInterval(chatTimer);
  chatTimer = setInterval(chatTick, 1000);
  clearInterval(chatPoller);
  chatPoller = setInterval(chatPoll, 1000);
  const entry = {role: 'user', text, ts: new Date().toISOString()};
  if (ctx && ctx.kind === 'file') entry.source = ctx.id;
  else if (ctx) entry.about = {kind: ctx.kind, id: ctx.id, label: ctx.label};
  if (opts && opts.generated) entry.generated = true;
  S.chat = [...S.chat, entry];
  renderChat(true);
  try {
    const payload = {text};
    if (ctx && ctx.kind === 'file') { payload.file = ctx.id; payload.source = ctx.id; }
    else if (ctx) payload.about = entry.about;
    if (entry.generated) payload.generated = true;
    if (opts && opts.queued) payload.queued = true;
    const res = await api('/api/chat', payload, {soft: true});      // soft: the error is drawn under the box, not toasted
    if (!res || res.error) throw new Error((res && res.error) || 'no answer');
    setState(res);
    outcome = chatOutcome(S.chat.at(-1));
    chatReloadViews(S.chat.at(-1)).catch(() => {});      // not awaited: a hung Altium read must not block send()
    const mountEl = document.querySelector('.diagram-mount-point');
    if (mountEl && mountEl._diagramEditor && res && res.idea && res.idea.diagram) {
      mountEl._diagramEditor.updateData(res.idea.diagram, res.diagram_touched || []);
    }
  } catch (e) {
    outcome = 'error';
    const msg = /failed to fetch|networkerror/i.test(e.message) ? 'no connection to the server' : e.message;
    chatError = {message: msg, text, ctx, session: S.session};
    S.chat = S.chat.filter(m => m !== entry);
    const inp = $('#input');
    if (inp && !inp.value.trim()) { inp.value = text; chatAutosize(); if (ctx && !chatChip()) chatSetChip(ctx); }     // the text is not lost
  }
  pending = false;
  chatStopping = false;
  clearInterval(chatTimer);
  clearInterval(chatPoller);
  chatProg = null;
  render(true);
  if (outcome !== 'error') await chatFlush(turnSession);      // an error keeps the queue; Retry or the next answer sends it
}
function chatSubmit() {
  const inp = $('#input');
  const t = inp.value.trim();
  if (!t) return;
  inp.value = '';
  chatAutosize();
  if (pending) { chatEnqueue(t); chatUpdateSend(); return; }      // typed while the agent works: it waits in the queue
  send(t);
}
async function openPart(anchor) {
  const r = await api('/api/thread/open', {anchor});
  SESSION = r.session; convsOpen = false;
  await refresh(true); setView('chat');
}
async function switchSession(id) { SESSION = id; convsOpen = false; await refresh(true); setView('chat'); }

/* ---------- events ---------- */
$('#form').addEventListener('submit', e => { e.preventDefault(); if (pending) chatStop(); else chatSubmit(); });      // the button is Stop while the agent works
$('#chat-status').addEventListener('toggle', e => { if (e.target.matches('.chat-steps')) { chatStepsOpen = e.target.open; chatFollow(); } }, true);
$('#msgs').addEventListener('scroll', e => {
  const sc = e.currentTarget;
  const sugsH = ($('#sugs') && $('#sugs').offsetHeight) || 0;
  chatAtEnd = sc.scrollHeight - sc.scrollTop - sc.clientHeight < Math.max(48, sugsH + 24);
  const j = $('#chat-jump');
  if (j && j.hidden !== chatAtEnd) j.hidden = chatAtEnd;
}, {passive: true});
// anything that changes the height of the thread or of the box (a reply, an open list, a font, the chat resized): follow the end if the student is there
if (window.ResizeObserver) { const ro = new ResizeObserver(() => chatFollow()); ['#msgs', '#chat-thread', '#chat-status', '#sugs'].forEach(q => { const el = $(q); if (el) ro.observe(el); }); }
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
onAct('rename', async (el, d, e) => {
  const row = currentRow();
  const t = (window.prompt('Name this conversation', row.title || '') || '').trim();
  if (!t || t === row.title) return;
  const r = await api('/api/sessions/rename', {title: t});
  if (r && r.sessions) S.sessions = r.sessions;
  await refresh(true);
});
onAct('suggest', async (el, d, e) => { send(d.text); });
onAct('retry', async (el, d, e) => {
  let err = chatCurrentError();
  if (!err || !err.text) {                                  // a partial record or a denial: the last student message again
    const u = chatLastUser();
    err = u ? {text: u.text, ctx: chatCtxOf(u)} : null;
  }
  if (!err || !err.text) return;
  const inp = $('#input');
  if (inp && inp.value.trim() === err.text) { inp.value = ''; chatAutosize(); }
  chatError = null;
  await send(err.text, {ctx: err.ctx || null});
});
onAct('chat-jump', async () => chatJump());
onAct('chat-followup-stop', async () => { try { await api('/api/chat/stop', {}, {soft: true}); } catch (e) { /* it ends on its own */ } });
onAct('chat-continue', async (el, d, e) => { await send(d.text, {ctx: null}); });
// Allow the one command the engine refused (the server builds the rule from its own record), then ask again
onAct('chat-allow', async (el, d, e) => {
  const u = chatLastUser();
  if (!u || pending) return;
  el.disabled = true;
  let r = null;
  try { r = await api('/api/chat/allow', {turn_ts: d.ts, index: Number(d.idx)}, {soft: true}); } catch (err) { r = {error: 'no connection to the server'}; }
  if (!r || r.error) { el.disabled = false; toast("Couldn't allow it: " + ((r && r.error) || 'no answer'), null, {bad: true}); return; }
  await send(u.text, {ctx: chatCtxOf(u)});
});
onAct('queue-remove', async (el, d, e) => { chatQueue = chatQueue.filter(q => String(q.id) !== d.qid); renderThread(true); });
// Settings › Engine: the page, then the row that picks the engine
onAct('chat-settings', async (el, d, e) => {
  go('settings');
  setTimeout(() => { const row = $('#set-provider'); if (row) row.scrollIntoView({block: 'center'}); }, 200);
});
onAct('chat-checks', async () => { go('settings'); setTimeout(() => { if (typeof pgDoctorRun === 'function') pgDoctorRun(); }, 200); });
onAct('chat-confirm-idea', async () => { setState(await api('/api/idea/confirm', {})); render(true); toast('Idea confirmed'); });
onAct('review-diagram', async (el, d, e) => { go('workspace', 'idea'); });
// Undo one applied change: the server appends a compensating entry; if later changes depend on it, it says so (409)
onAct('undo-change', async (el, d, e) => {
  const r = await api('/api/undo', {id: d.pid}); setState(r); render(true);
  // the delete threw out the pending changes for that line: an undo brings the line back, not those
  toast(r.superseded && r.superseded.length ? `Undone. ${r.superseded.length} pending change${r.superseded.length === 1 ? '' : 's'} for that line ${r.superseded.length === 1 ? 'was' : 'were'} dropped when it was deleted and ${r.superseded.length === 1 ? 'is' : 'are'} not back` : 'Undone');
});
