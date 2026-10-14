/* PCB Advisor UI - core: globals/state, api + render helpers, generic text helpers, the action registry and the
   document click/change delegates. Classic scripts (no modules): every ui/js file shares one global scope and they load
   in this order: core, shell, chat, views/*, viewer, boot (see the <script> tags at the end of ui/index.html).
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
let convsOpen = false, pending = false, compareCard = null, exportCard = null, libExport = null, altsCard = null;
let impInfo = null, impFor = null, impSel = '', impReport = null, impBusy = false;   // import a BOM from Altium
let outjobBanner = null, curCheckStem = null, curPcbCheckStem = null, curSmtCheckStem = null, uploadDfmKind = 'pcb', schAnchor = null;
let triageMap = {}, triageLoading = {}, indexMap = {}, indexLoading = {};
let svgCache = {key: '', text: ''};
let pcbSvgCache = {key: '', text: ''};
let pcbLayers = {top: true, bottom: true, plan: true};
let schSel = null, pcbSel = null;
let compPanel = null;
let activeFileChip = null;
let schZoom = {scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, didDrag: false, downX: 0, downY: 0};
let pcbZoom = {scale: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, didDrag: false, downX: 0, downY: 0};

let diagLinkingFrom = null;

let lastChatKey = '', lastCenterKey = '';

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
  if (!r.ok && !opts.soft) { toast(data.error || ('Error ' + r.status)); throw new Error(data.error || r.status); }
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
function chip(name, where) {
  const known = srcByName(name);
  return `<button class="src ${known ? '' : 'broken'}" data-src="${esc(name)}" ${where ? `data-where="${esc(where)}"` : ''} title="${known ? '' : 'Not in Sources'}"><b>${esc(name)}</b>${where ? ' · ' + esc(where) : ''}</button>`;
}
function inline(t) {
  // t is escaped text. Citations and refs become buttons; **bold** and `code` are the only markup.
  return t
    .replace(/\{\{src:([^|}]+)(?:\|([^}]*))?\}\}/g, (m, n, w) => chip(n.trim().replace(/&amp;/g, '&'), (w || '').trim().replace(/&amp;/g, '&')))
    .replace(/\{\{ref:([^}]+)\}\}/g, (m, r) => `<button class="ref" data-ref="${r}">${r}</button>`)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<span class="m">$1</span>');
}
function fmt(text) {
  const out = []; let list = null;
  const flush = () => { if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${i}</li>`).join('')}</${list.t}>`); list = null; } };
  for (const raw of String(text || '').split('\n')) {
    const line = esc(raw);
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

function renderCenter(force) {
  const active = document.activeElement;
  if (!force && active && active.closest && active.closest('.editor-content') && /INPUT|TEXTAREA|SELECT/.test(active.tagName)) return;   // do not eat an edit in progress
  $('#whead').innerHTML = wheadHTML();
  initTabScroller();
  renderEditorGroups(force);
  renderDetail();
}
function renderDetail() {
  // The inspector (views/inspector.js) decides whether it has something to show for the current view and selection.
  const d = $('#detail');
  const html = typeof inspectorHTML === 'function' ? inspectorHTML() : '';
  d.hidden = !html;
  d.innerHTML = html;
}
function render(force) {
  if (!S) return;
  document.title = S.title + ' · PCB Advisor';
  renderNav();
  renderChat(force);
  const key = JSON.stringify([S.bom, S.proposals, S.library, S.sources, S.sheets, S.idea, S.requirements, S.totals, S.memory, S.exports, S.checks, page, tab, sel, compareCard, exportCard, libExport, sheetId, altsCard, outjobBanner, curCheckStem, schAnchor, impInfo, impSel, impReport, impBusy]);
  if (force || key !== lastCenterKey) { lastCenterKey = key; renderCenter(force); }
}
function go(p, t) {
  page = p;
  if (t) {
    tab = t;
    openStageInActiveGroup(t);
  } else if (p === 'workspace') {
    openStageInActiveGroup(tab || 'bom');
  } else {
    openPageAsTab(p);
  }
  if (p === 'settings') loadAltium();
  render(true);
  setView('work');
}
function select(key, goSch) {
  sel = key;
  if (goSch) {
    openStageInActiveGroup('sch');
    return;
  }
  const actTab = getActiveTab();
  if (!(actTab && ((actTab.kind === 'stage' && (actTab.stage === 'bom' || actTab.stage === 'sch')) || (actTab.kind === 'page' && actTab.page === 'library')))) {
    openStageInActiveGroup('bom');
    return;
  }
  document.querySelectorAll('.view tr[data-key]').forEach(tr => tr.classList.toggle('sel', tr.dataset.key === key));
  applyFocus();
  renderDetail();
  setView('work');
}
function setView(v) { if (matchMedia('(max-width:860px)').matches) $('#app').dataset.view = v; }
function toast(msg, action) {
  const t = $('#toast');
  t.innerHTML = '';
  const span = document.createElement('span');
  span.textContent = msg;
  t.appendChild(span);
  if (action && action.label && action.onClick) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-sm';
    btn.style.cssText = 'margin-left:8px;padding:1px 6px;font-size:11px;background:#3b82f6;color:#fff;border:none;border-radius:4px;cursor:pointer;';
    btn.textContent = action.label;
    btn.onclick = (e) => { e.stopPropagation(); t.hidden = true; action.onClick(); };
    t.appendChild(btn);
  }
  t.hidden = false;
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.hidden = true, action ? 5000 : 3600);
}

/* ---------- events ---------- */
// One click / change delegate for the whole page. An area owns its handlers: it registers them in its own file with
//   onAct('name', async (el, d, e) => { ... })      el = the matched button/row/svg group, d = el.dataset, e = the event
//   onChange(t => bool, async e => { ... })         first registered test that accepts e.target wins
// The generic data-* routes below (decide, accept, verify, thread, proj, tab, page, view, src, altiumPath, ref, show,
// chat, sheet, calc) run first and win over a data-act on the same element, exactly as the old if-chain did.
const ACTIONS = Object.create(null);
function onAct(name, fn) { ACTIONS[name] = fn; }
const CHANGE_HANDLERS = [];
function onChange(test, fn) { CHANGE_HANDLERS.push({test, fn}); }
document.addEventListener('click', async e => {
  const grpEl = e.target.closest('.editor-group');
  if (grpEl && grpEl.dataset.groupId && editorState.activeGroupId !== grpEl.dataset.groupId) {
    editorState.activeGroupId = grpEl.dataset.groupId;
    document.querySelectorAll('.editor-group').forEach(g => g.classList.toggle('active', g.dataset.groupId === editorState.activeGroupId));
    saveStoredEditorState(editorState);
  }
  const edTabEl = e.target.closest('.editor-tab');
  if (edTabEl && !e.target.closest('[data-act="close-tab"]')) {
    activateTabInGroup(edTabEl.dataset.tabId, edTabEl.dataset.groupId);
    return;
  }
  const el = e.target.closest('button, tr[data-key], g.part, g.diag-block, g[data-tab], g[data-act], a');
  if (!el) return;
  if (el.tagName === 'A') return;
  if (diagLinkingFrom) {
    const blockEl = el.closest('g.diag-block');
    const destId = blockEl ? blockEl.dataset.bid : null;
    if (destId && destId !== diagLinkingFrom) {
      const label = prompt('Signal or voltage label (e.g. SPI, I2C, 3.3V, SAFETY):', 'SPI');
      if (label !== null) {
        const links = S.idea.links || [];
        links.push({from: diagLinkingFrom, to: destId, label: label.trim(), safety: /safety/i.test(label)});
        diagLinkingFrom = null;
        await api('/api/idea', {blocks: S.idea.blocks || [], links});
        renderCenter(true);
        toast('Blocks connected');
        return;
      }
    }
    if (el.dataset.act !== 'diag-link-start') {
      diagLinkingFrom = null;
      renderCenter(true);
    }
  }
  if (el.matches('g.part')) { const l = lineOfRef(el.dataset.ref); if (l) select(l.key); return; }
  if (el.matches('tr[data-key]')) { if (e.target.closest('input')) return; if (!e.target.closest('button')) { select(el.dataset.key); return; } }
  const d = el.dataset;
  try {
    // A registered data-act wins over the generic data-* routes below, so a button may carry data-ref / data-src as
    // arguments for its action (btn() in kit.js turns plain keys into data-* attributes).
    const fn = d.act && ACTIONS[d.act];
    if (fn) { await fn(el, d, e); return; }
    if (d.decide) { setState(await api('/api/proposal', {id: d.pid, decision: d.decide})); render(true); toast(d.decide === 'approved' ? 'Change applied' : 'Rejected'); return; }
    if (d.accept) { setState(await api('/api/library/accept', {line: d.accept})); render(true); toast('Accepted'); return; }
    if (d.verify) { toast('Verifying…'); const r = await api('/api/skill', {name: 'verify', args: [d.verify]}); setState(r.state); render(true); toast('Result: ' + r.result.verify); return; }
    if (d.thread !== undefined && el.dataset.thread !== undefined) { if (d.thread) switchSession(d.thread); return; }
    if (d.proj) { ALTIUM_DATA = null; const u = new URL(location.href); u.searchParams.set('project', d.proj); u.searchParams.delete('session'); location.href = u; return; }
    if (d.tab) {
      openStageInActiveGroup(d.tab);
      const curTab = document.querySelector(`.tabs-scroller .tab[data-tab="${d.tab}"], .tabs .tab[data-tab="${d.tab}"]`);
      if (curTab) curTab.scrollIntoView({ inline: 'nearest', block: 'nearest' });
      return;
    }
    if (d.page) {
      if (d.page === 'workspace') openStageInActiveGroup(tab || 'bom');
      else openPageAsTab(d.page);
      return;
    }
    if (d.view) { setView(d.view); return; }
    if (d.src) { hitSrc = d.src; openViewerSource(d.src, el.dataset.where); return; }
    if (d.altiumPath) { openViewerAltium(d.altiumPath); return; }
    if (d.ref) { const l = lineOfRef(d.ref); if (l) select(l.key); return; }
    if (d.show) { select(d.show, true); return; }
    if (d.chat) { openPart(d.chat); return; }
    if (d.sheet) { sheetId = d.sheet; svgCache = {key: '', text: ''}; render(true); return; }
    if (d.calc) { await runCalculator(d); return; }
  } catch (err) { /* api() already toasted */ }
  if (el.classList.contains('sug')) { send(el.textContent); return; }
});
document.addEventListener('change', async e => {
  for (const h of CHANGE_HANDLERS) {
    if (h.test(e.target)) { await h.fn(e); return; }
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeViewer(); closeCompPanel(); }
});
