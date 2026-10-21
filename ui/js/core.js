/* PCB Advisor UI - core: globals/state, api + render helpers, generic text helpers, the action registry and the
   document click/change delegates. Classic scripts (no modules): every ui/js file shares one global scope and they load
   in this order: kit, core, shell, chat, views/*, viewer, palette, boot (see the <script> tags at the end of ui/index.html).
   Top-level code in a file must not READ a let/const that a later file declares; functions may (they run later). */

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SUPS = ['LCSC','Mouser','DigiKey'];
const URLQ = new URLSearchParams(location.search);

/* ---------- state ---------- */
let S = null;                 // the whole project, from /api/state
let PROJECT = URLQ.get('project') || null;
let SESSION = URLQ.get('session') || null;
let PROJECTS = [], SKILLS = null, CONFIG = null, ALTIUM_DATA = null, RULES_DATA = null;
let page = 'workspace', tab = 'bom', sel = null, hitSrc = null, sheetId = null;
let convsOpen = false, pending = false, libExport = null;
let impInfo = null, impFor = null, impSel = '', impReport = null, impBusy = false;   // import a BOM from Altium
let curPcbCheckStem = null, curSmtCheckStem = null, uploadDfmKind = 'pcb';
let triageMap = {}, triageLoading = {}, indexMap = {}, indexLoading = {};
let svgCache = {key: '', text: ''};
let pcbSvgCache = {key: '', text: ''};
let pcbLayers = {'top-copper': true, 'bottom-copper': true, inner: true, vias: true, 'silk-top': true, 'silk-bottom': true, outline: true, plan: true};
let schZoom = {scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, didDrag: false, downX: 0, downY: 0};
let pcbZoom = {scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, didDrag: false, downX: 0, downY: 0};

let lastChatKey = '', lastCenterKey = '', pendingRender = false;

const q = (extra = {}) => {
  const p = new URLSearchParams({project: PROJECT, ...(SESSION ? {session: SESSION} : {}), ...extra});
  return p.toString();
};
async function api(path, body, opts = {}) {
  const sep = path.includes('?') ? '&' : '?';
  const url = path + sep + q();
  const r = body === undefined
    ? await fetch(url)
    : await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  let data = null;
  try { data = await r.json(); } catch (e) { data = {error: 'bad response'}; }
  if (!r.ok && !opts.soft) { toast(data.error || ('Error ' + r.status), null, {bad: true}); throw new Error(data.error || r.status); }
  return data;
}
function setState(st) {
  S = st;
  if (st.session) SESSION = st.session;
}
async function refresh(force) {
  try {
    const st = await api('/api/state');
    setState(st);
    render(force);
  } catch (e) { /* the toast already said it */ }
}

/* ---------- derived values ---------- */
const lines = () => (S ? S.bom : []);
const lineByKey = k => lines().find(l => l.key === k);
const lineOfRef = r => lines().find(l => (l.refs || []).includes(r));
const qty = l => (l.dnp || l.nobuy) ? 0 : (l.refs || []).length;
function best(l) {
  if (!l.supply) return null;
  let b = null;
  for (const s of SUPS) {
    const v = l.supply[s]; if (!v || v.unit_price == null) continue;
    if ((v.stock || 0) >= Math.max(qty(l), 1) && (!b || v.unit_price < b.price)) b = {s, stock: v.stock, price: v.unit_price, at: v.checked_at};
  }
  return b;
}
function status(l) {
  if (l.nobuy || l.dnp) return 'na';
  if (l.supply == null) return 'pend';
  if (!best(l)) return 'bad';
  if (l.library === 'review' || l.library === 'missing') return 'warn';
  return 'ok';
}
const money = p => p == null ? '—' : '$' + (p < 0.01 ? p.toFixed(4) : p < 1 ? p.toFixed(3) : p.toFixed(2));
const num = n => (n ?? 0).toLocaleString('en-US');
// "C3, C4, C5, C8" -> "C3–C5, C8": only refs that really follow each other become a range
function refRuns(refs) {
  const split = r => { const m = /^(.*?)(\d+)$/.exec(r); return m ? [m[1], +m[2]] : [r, null]; };
  const sorted = [...refs].sort((a, b) => { const [pa, na] = split(a), [pb, nb] = split(b);
    return pa < pb ? -1 : pa > pb ? 1 : (na ?? -1) - (nb ?? -1); });
  const runs = [];
  for (const r of sorted) {
    const [p, n] = split(r), last = runs.at(-1);
    if (last && n != null && last.p === p && last.n + 1 === n) { last.n = n; last.refs.push(r); }
    else runs.push({p, n, refs: [r]});
  }
  return runs.map(x => x.refs.length > 2 ? x.refs[0] + '–' + x.refs.at(-1) : x.refs.join(', '));
}
function refsLabel(refs) {
  const runs = refRuns(refs);
  return runs.length > 3 ? `${runs.slice(0, 3).join(', ')} … (${refs.length})` : runs.join(', ');
}
const LIBTXT = {std: 'Altium default', ok: 'In library · verified', review: 'In library · to review', missing: 'Missing'};
const FIELD = {mpn: 'MPN', manufacturer: 'Manufacturer', package: 'Package', value: 'Value', description: 'Description',
  note: 'Note', datasheet: 'Datasheet', dnp: 'Not fitted', nobuy: 'Not bought', refs: 'Designators', role: 'Role'};
const sheetsOfLine = l => {
  const out = [];
  for (const r of l.refs || []) for (const sh of S.sheets) {
    const p = sh.parts[r]; if (!p) continue;
    const sec = (sh.sections || []).find(x => x.id === p.section);
    out.push({ref: r, sheet: sh.id, section: p.section, title: sec ? sec.title : '', nets: p.nets});
  }
  return out;
};
const checkedAt = () => {
  let t = '';
  for (const l of lines()) for (const s of Object.values(l.supply || {})) if ((s.checked_at || '') > t) t = s.checked_at;
  return t ? t.replace('T', ' ').slice(0, 16) : null;
};
const srcByName = n => (S.sources || []).find(s => s.name === n);

/* ---------- text: citations, refs, lists ---------- */
// The server checks every quote of an agent reply after the reply is stored (scripts/background.py); the result
// rides on the record as `cites`: {state: 'checking'} or {state: 'done', items: {'file|locator': {status, reason}}}.
let fmtCites = null;               // the record fmt() is drawing, so a chip can show its check
function citeState(name, where) {
  const c = fmtCites, it = c && c.items && c.items[`${name}|${where || ''}`];
  if (!it) return c && c.state === 'checking' ? {cls: 'cite-checking', mark: '…', tip: 'Checking the quote in the file'} : null;
  if (it.status === 'ok') return {cls: 'cite-ok', mark: '✓', tip: it.reason || 'Found in the file'};
  return {cls: 'cite-bad', mark: '⚠', tip: it.status === 'missing_file' ? (it.reason || 'File not in Sources') : 'Quote not found in file: ' + (it.reason || '')};
}
function chip(name, where) {
  const known = srcByName(name), cs = citeState(name, where);
  const title = cs ? cs.tip : (known ? '' : 'Not in Sources');
  const broken = cs ? cs.cls === 'cite-bad' && !known : !known;     // the server read the file: its verdict wins
  return `<button class="src ${broken ? 'broken' : ''}${cs ? ' ' + cs.cls : ''}" data-src="${esc(name)}" ${where ? `data-where="${esc(where)}"` : ''} title="${esc(title)}"><b>${esc(name)}</b>${where ? ' · ' + esc(where) : ''}` +
    (cs ? `<span class="cite-m" aria-hidden="true">${cs.mark}</span><span class="sr"> (${esc(cs.tip)})</span>` : '') + '</button>';
}
// chip() escapes again, and the check is keyed by the raw text: a quoted locator ("...") must match it.
const unesc = s => s.replace(/&(amp|lt|gt|quot|#39);/g, (m, e) => ({amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'"}[e]));
function inline(t) {
  // t is escaped text. Citations and refs become buttons; **bold** and `code` are the only markup.
  return t
    .replace(/\{\{src:([^|}]+)(?:\|([^}]*))?\}\}/g, (m, n, w) => chip(unesc(n.trim()), unesc((w || '').trim())))
    .replace(/\{\{ref:([^}]+)\}\}/g, (m, r) => `<button class="ref" data-ref="${r}">${r}</button>`)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<span class="m">$1</span>');
}
function fmt(text, cites) {
  fmtCites = cites || null;
  try { return fmtLines(text); } finally { fmtCites = null; }
}
function fmtLines(text) {
  const out = []; let list = null, rows = null;
  // a citation's own | ({{src:a.pdf|p. 3}}) is not a cell border
  const cells = l => l.trim().replace(/^\||\|$/g, '').split(/\|(?![^{}]*\}\})/).map(c => inline(c.trim()));
  const flushRows = () => {
    if (!rows) return;
    const [head, ...body] = rows; rows = null;
    out.push(`<div class="tbl-wrap"><table class="tbl dense"><thead><tr>${head.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>` +
      body.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('') + '</tbody></table></div>');
  };
  const flush = () => { flushRows(); if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${i}</li>`).join('')}</${list.t}>`); list = null; } };
  for (const raw of String(text || '').split('\n')) {
    const line = esc(raw);
    if (/^\s*\|.*\|\s*$/.test(line)) {               // a pipe table row; the |---| separator row is dropped
      if (!rows) { flush(); rows = []; }
      if (!/^\s*\|[\s:|-]+\|\s*$/.test(line)) rows.push(cells(line));
      continue;
    }
    flushRows();
    const ul = /^\s*[-*] (.*)$/.exec(line), ol = /^\s*\d+[.)] (.*)$/.exec(line);
    if (ul || ol) {
      const t = ul ? 'ul' : 'ol';
      if (!list || list.t !== t) { flush(); list = {t, items: []}; }
      list.items.push(inline((ul || ol)[1]));
    } else if (!line.trim()) { flush(); }
    else if (list && /^\s{2,}/.test(raw)) { list.items[list.items.length - 1] += '<br>' + inline(line.trim()); }
    else { flush(); out.push(`<p>${inline(line)}</p>`); }
  }
  flush();
  return out.join('');
}

/* ---------- render ---------- */
// The main sheet (#view), the optional side sheet (#view-side) and the inspector (#detail) are drawn from S by shell.js.
function renderCenter(force) {
  const active = document.activeElement;
  if (!force && active && active.closest && active.closest('#view, #view-side, #detail') && /INPUT|TEXTAREA|SELECT/.test(active.tagName)) return;   // do not eat an edit in progress
  renderMain(force);
  renderSide(force);
  renderDetail();
}
function renderDetail() {
  // The inspector (views/inspector.js) decides whether it has something to show for the current view and selection.
  const d = $('#detail');
  if (!d) return;
  const html = typeof inspectorHTML === 'function' ? inspectorHTML() : '';
  d.hidden = !html;
  d.innerHTML = html;
}
function render(force) {
  if (!S) return;
  // Never rebuild what is under an open menu, the palette or a dialog. A forced render that had to wait runs afterwards.
  if (uiBusy()) { pendingRender = pendingRender || !!force; return; }
  if (pendingRender) { force = true; pendingRender = false; }
  // The selection (sel) is not part of the centre key: select() marks rows and the drawing itself, so a poll after a
  // click must not rebuild the sheet (that reset the schematic and PCB zoom).
  document.title = S.title + ' · PCB Advisor';
  renderNav();
  renderChat(force);
  const key = JSON.stringify([S.bom, S.proposals, S.library, S.sources, S.sheets, S.idea, S.idea_draft, S.totals, S.memory, S.exports, S.checks, page, tab, mainKey(), sideKey(), libExport, sheetId, impInfo, impSel, impReport, impBusy, libBusy, libNote]);
  if (force || key !== lastCenterKey) { lastCenterKey = key; renderCenter(force); }
}
// go('workspace', 'bom') or go('bom') shows a stage in the main sheet; go('library') a page. See shell.js.
// select(key) marks a part and opens the inspector; it leaves bom, sch, pcb and library where they are.
function select(key, goSch) {
  sel = key;
  if (goSch) {
    if (sideView() !== 'sch') go('workspace', 'sch');
    else { markSelected(); applyFocusSafe(); renderDetail(); }
    return;
  }
  if (!['bom', 'sch', 'pcb', 'library'].includes(mainView()) && sideView() !== 'bom') {
    go('workspace', 'bom');
    return;
  }
  markSelected();
  applyFocusSafe();
  renderDetail();
  setView('work');
}
function markSelected() {
  document.querySelectorAll('tr[data-key]').forEach(tr => tr.classList.toggle('sel', tr.dataset.key === sel));
}
function applyFocusSafe() { if (typeof applyFocus === 'function') applyFocus(); }
/* One toast at a time, for errors and Undo. Success shows in place. toast(msg, {label, onClick}, {bad: true}) */
function toast(msg, action, opts) {
  const t = $('#toast');
  if (!t) return;
  const bad = opts && opts.bad != null ? !!opts.bad : /^(error|failed|couldn.t|could not|can.t|cannot)\b/i.test(String(msg));
  t.className = 'toast' + (bad ? ' bad' : '');
  t.setAttribute('role', 'status');
  t.textContent = '';
  const span = document.createElement('span');
  span.textContent = msg;
  t.appendChild(span);
  if (action && action.label && action.onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = action.label;
    b.onclick = e => { e.stopPropagation(); t.hidden = true; action.onClick(); };
    t.appendChild(b);
  }
  t.hidden = false;
  clearTimeout(toast.h);
  toast.h = setTimeout(() => { t.hidden = true; }, bad || action ? 6000 : 3600);
}
/* A small dialog that asks for one line of text, instead of prompt(). Resolves to the trimmed text, or null when cancelled.
   askText({title, label, value, placeholder, hint, confirm}) */
function askText(o) {
  o = o || {};
  return new Promise(resolve => {
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg';
    dlg.setAttribute('aria-labelledby', 'dlg-title');
    dlg.innerHTML = `<form method="dialog"><h2 id="dlg-title">${esc(o.title || '')}</h2>
      <label class="field"><span>${esc(o.label || '')}</span><input class="in" name="v" value="${esc(o.value || '')}" placeholder="${esc(o.placeholder || '')}" autocomplete="off" required>${o.hint ? `<small>${esc(o.hint)}</small>` : ''}</label>
      <div class="acts"><button type="button" class="btn" data-cancel>Cancel</button><button type="submit" class="btn pri" value="ok">${esc(o.confirm || 'OK')}</button></div></form>`;
    // Cancel is not a submit button: Enter in the field submits the form through its first submit button, which must be the OK one
    dlg.querySelector('[data-cancel]').addEventListener('click', () => dlg.close('cancel'));
    dlg.addEventListener('close', () => {
      const v = dlg.querySelector('input').value.trim();
      const ok = dlg.returnValue === 'ok' && v;
      dlg.remove();
      resolve(ok ? v : null);
    });
    document.body.appendChild(dlg);
    dlg.showModal();
    dlg.querySelector('input').select();
  });
}

/* ---------- events ---------- */
// One click / change delegate for the whole page. An area owns its handlers: it registers them in its own file with
//   onAct('name', async (el, d, e) => { ... })      el = the matched button/row/svg group, d = el.dataset, e = the event
//   onChange(t => bool, async e => { ... })         first registered test that accepts e.target wins
// The generic data-* routes below (decide, accept, verify, thread, proj, tab, page, view, src, altiumPath, ref, show,
// chat, sheet) run first and win over a data-act on the same element, exactly as the old if-chain did.
const ACTIONS = Object.create(null);
function onAct(name, fn) { ACTIONS[name] = fn; }
const CHANGE_HANDLERS = [];
function onChange(test, fn) { CHANGE_HANDLERS.push({test, fn}); }
document.addEventListener('click', async e => {
  const el = e.target.closest('button, tr[data-key], g.part, g[data-tab], g[data-act], a');
  if (!el) return;
  if (el.tagName === 'A') return;
  // A menu item runs its action first. The menu closes on its own timer after this handler, but the render that the
  // action triggers must not be held back by a menu that is about to close, so close it now.
  if (el.closest('.menu') && typeof kitMenuClose === 'function') kitMenuClose();
  if (el.matches('g.part')) { const l = lineOfRef(el.dataset.ref); if (l) select(l.key); return; }
  if (el.matches('tr[data-key]')) { if (e.target.closest('input')) return; if (!e.target.closest('button')) { select(el.dataset.key); return; } }
  const d = el.dataset;
  try {
    // A registered data-act wins over the generic data-* routes below, so a button may carry data-ref / data-src as
    // arguments for its action (btn() in kit.js turns plain keys into data-* attributes).
    const fn = d.act && ACTIONS[d.act];
    if (fn) { await fn(el, d, e); return; }
    if (d.decide) { setState(await api('/api/proposal', {id: d.pid, decision: d.decide})); render(true); return; }      // the proposal card shows the decision; no toast
    if (d.accept) { setState(await api('/api/library/accept', {line: d.accept})); render(true); toast('Accepted'); return; }
    if (d.verify) { toast('Verifying…'); const r = await api('/api/skill', {name: 'verify', args: [d.verify]}); setState(r.state); render(true); toast('Result: ' + r.result.verify); return; }
    if (d.thread !== undefined && el.dataset.thread !== undefined) { if (d.thread) switchSession(d.thread); return; }
    if (d.proj) { ALTIUM_DATA = null; const u = new URL(location.href); u.searchParams.set('project', d.proj); u.searchParams.delete('session'); location.href = u; return; }
    if (d.tab) { go('workspace', d.tab); return; }
    if (d.page) { go(d.page); return; }
    if (d.view) { setView(d.view); return; }
    if (d.src) { openFileAsTab({name: d.src, path: d.src, where: d.where}); return; }
    if (d.altiumPath) { openFileAsTab({name: docBase(d.altiumPath), path: d.altiumPath}); return; }
    if (d.ref) { const l = lineOfRef(d.ref); if (l) select(l.key); return; }
    if (d.show) { select(d.show, true); return; }
    if (d.chat) { openPart(d.chat); return; }
    if (d.sheet) { sheetId = d.sheet; svgCache = {key: '', text: ''}; render(true); return; }
  } catch (err) { /* api() already toasted */ }
  if (el.classList.contains('sug')) { send(el.textContent); return; }
});
document.addEventListener('change', async e => {
  for (const h of CHANGE_HANDLERS) {
    if (h.test(e.target)) { await h.fn(e); return; }
  }
});
