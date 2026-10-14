/* PCB Advisor UI - inspector: the one right-hand drawer (#detail). core.js renderDetail() asks inspectorHTML() and hides the
   drawer when it returns ''. It shows what is selected on the BOM, the schematic, the layout or in the library:
     - a part         sel (a BOM line key, set by select() in core.js)
     - a net          selNet (a net name)
     - something else selThing: {kind: 'ref', ref, sheet} for a designator that is not in the BOM, or {kind: 'zone', name}
   Picking a net or something else clears sel, so exactly one of them is shown. A part is edited in place: role, note and
   MPN are <input data-edit="..." data-line="KEY">, saved by the change handler in bom.js. */

let selNet = null;          // the net the inspector shows
let selThing = null;        // a designator that is only on a sheet, or a plan zone
let inspComp = {};          // 'REF|sheet' -> {state: 'loading' | 'ok' | 'none', data, at}: /api/sch/component answers
let inspMore = {};          // which long lists the user expanded: {nets, parts, where}
let inspKeptKey = '';        // what the drawing was last slid aside for
let inspPinsOpen = false;   // the Pins disclosure stays as the user left it while the selection changes
let inspPadsMemo = null;    // {text, map}: net -> [{ref, pin}], read from the layout picture

const INSP_VIEWS = ['bom', 'sch', 'pcb', 'library'];
const INSP_CAP = {where: 8, nets: 12, parts: 40};

/* ---------- which views show it, and what it shows ---------- */
function inspViews() {
  if (typeof mainView === 'function') return [mainView(), typeof sideView === 'function' ? sideView() : null];
  return [page === 'workspace' ? tab : page];
}
const inspVisible = () => inspViews().some(v => INSP_VIEWS.includes(v));
const inspOn = v => inspViews().includes(v);

// Keeps the three kinds of selection exclusive: a part (sel) wins over a net, a net over something else.
function inspNormalize() {
  if (sel) { selNet = null; selThing = null; }
  else if (selNet) selThing = null;
}
function inspKind() {
  inspNormalize();
  if (sel && lineByKey(sel)) return 'part';
  if (selNet) return 'net';
  if (selThing) return selThing.kind;
  return '';
}
function inspectorHTML() {
  let html = '';
  if (inspVisible()) {
    const k = inspKind();
    if (k === 'part') html = inspPartHTML(lineByKey(sel));
    else if (k === 'net') html = inspNetHTML(selNet);
    else if (k === 'zone') html = inspZoneHTML(selThing.name);
    else if (k === 'ref') html = inspRefHTML(selThing);
  }
  // a pick on a drawing slides it aside when the drawer would cover the pick (once per pick, so zoom and pan are not fought)
  const key = html ? [sel, selNet, selThing && (selThing.ref || selThing.name)].join('|') : '';
  if (key !== inspKeptKey) { inspKeptKey = key; if (key && typeof pvKeepClear === 'function') requestAnimationFrame(() => requestAnimationFrame(pvKeepClear)); }
  if (html) requestAnimationFrame(() => { const d = $('#detail'); if (d && d.offsetWidth) document.documentElement.style.setProperty('--insp-w', d.offsetWidth + 'px'); });
  return html;
}

/* ---------- small pieces ---------- */
function inspWhen(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false}).replace(',', '');
}
const inspPl = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
function inspSec(title, body, actions, id) {
  return `<section${id ? ` id="${id}"` : ''}><div class="insp-sh"><h3>${esc(title)}</h3>${actions ? `<div class="acts">${actions}</div>` : ''}</div>${body}</section>`;
}
function inspHead(title, sub, actions, plain) {
  return `<div class="drawer-h"><div class="t"><h2${plain ? ' class="plain"' : ''}>${esc(title)}</h2>${sub ? `<p>${sub}</p>` : ''}</div>` +
    `<div class="acts">${actions || ''}${btn('', {icon: 'x', size: 'sm', title: 'Close', act: 'close'})}</div></div>`;
}
const inspMoreBtn = (what, n) => btn(`+${n} more`, {kind: 'link', size: 'sm', act: 'insp-more', what});
function inspNetChip(n) {
  return `<button type="button" class="insp-net" data-act="pick-net" data-net="${esc(n)}" title="Highlight ${esc(n)}">${esc(n)}</button>`;
}
function inspHasPcb() {   // unknown (not loaded yet) counts as yes
  return !(ALTIUM_DATA && ALTIUM_DATA.linked && !ALTIUM_DATA.linked.pcb_file);
}
const inspRefsOf = l => (l && l.refs) || [];
const inspFirstRef = l => inspRefsOf(l)[0] || '';

/* ---------- component details: pins, and the nets of a designator ---------- */
function inspFetchComp(c, ref, sheet) {
  c.busy = true;
  return api('/api/sch/component?' + q({ref, ...(sheet ? {sheet} : {})}), undefined, {soft: true})
    .then(d => { c.state = d && !d.error && Array.isArray(d.pins) ? 'ok' : 'none'; c.data = d; })
    .catch(() => { c.state = c.data ? c.state : 'none'; })
    .finally(() => { c.busy = false; c.at = Date.now(); inspPatch(); });
}
// One answer per designator, kept for the session and refreshed quietly after a minute (the schematic may have changed).
function inspComponent(ref, sheet) {
  if (!ref) return null;
  const k = ref + '|' + (sheet || '');
  let c = inspComp[k];
  if (!c) { c = inspComp[k] = {state: 'loading', data: null, at: Date.now(), busy: false}; inspFetchComp(c, ref, sheet); }
  else if (!c.busy && Date.now() - c.at > 60000) inspFetchComp(c, ref, sheet);
  return c;
}
// the sheet to ask for: where the BOM says the part is, else the open sheet
function inspSheetFor(l, ref) {
  const w = l ? sheetsOfLine(l).find(x => x.ref === ref) : null;
  return (w && w.sheet) || (l && l.sheet) || '';
}
function inspLoadFor(l, ref, sheet) {
  const refs = l ? inspRefsOf(l).slice(0, 4) : [ref];
  return refs.map(r => inspComponent(r, l ? inspSheetFor(l, r) : sheet));
}

function inspNetsOfLine(l, comps) {
  const nets = new Set(sheetsOfLine(l).flatMap(w => w.nets || []));
  for (const c of comps) if (c && c.data && c.data.pins) for (const p of c.data.pins) if (p.net) nets.add(p.net);
  return [...nets].filter(Boolean).sort((a, b) => a.localeCompare(b, 'en', {numeric: true}));
}

/* the part's three lists that fill in after the component details arrive: where used, nets, pins */
function inspWhereHTML(l) {
  const w = sheetsOfLine(l);
  let rows = w.map(x => ({ref: x.ref, sheet: x.sheet, text: `Sheet ${x.sheet}${x.title ? ' · ' + x.title : x.section ? ' · ' + x.section : ''}`}));
  if (!rows.length && l.sheet) rows = [{ref: refsLabel(inspRefsOf(l)), first: inspFirstRef(l), sheet: l.sheet, text: `Sheet ${l.sheet}`}];
  if (!rows.length) return '';
  const shown = inspMore.where ? rows : rows.slice(0, INSP_CAP.where);
  return inspSec('Where used', `<div class="insp-rows">${shown.map(r =>
    `<button type="button" class="insp-row" data-act="show-sch" data-key="${esc(l.key)}" data-sheet="${esc(r.sheet)}" data-ref="${esc(r.first || r.ref)}"><span class="ref">${esc(r.ref)}</span><span class="muted">${esc(r.text)}</span></button>`).join('')}` +
    `${rows.length > shown.length ? inspMoreBtn('where', rows.length - shown.length) : ''}</div>`);
}
function inspNetsHTML(l, comps) {
  const nets = inspNetsOfLine(l, comps);
  const waiting = comps.some(c => c && c.state === 'loading');
  if (!nets.length) return waiting ? inspSec('Nets', loadingLine('Reading the schematic')) : '';
  const shown = inspMore.nets ? nets : nets.slice(0, INSP_CAP.nets);
  return inspSec('Nets', `<div class="insp-nets">${shown.map(inspNetChip).join('')}${nets.length > shown.length ? inspMoreBtn('nets', nets.length - shown.length) : ''}</div>`);
}
function inspPinsHTML(comp, ref) {
  if (!comp) return '';
  if (comp.state === 'loading') return `<div class="insp-pins-wait">${loadingLine('Reading the pins')}</div>`;
  const pins = comp.state === 'ok' ? comp.data.pins : [];
  if (!pins.length) return '';
  return `<details class="disc" id="insp-pins-d"${inspPinsOpen ? ' open' : ''}><summary>${esc(`Pins of ${ref} (${pins.length})`)}</summary>` +
    `<table class="tbl dense insp-pins"><thead><tr><th>Pin</th><th>Name</th><th>Net</th></tr></thead><tbody>` +
    pins.map(p => `<tr><td class="m">${esc(p.number)}</td><td class="m">${esc(p.name)}</td><td>${p.net ? inspNetChip(p.net) : '<span class="muted">—</span>'}</td></tr>`).join('') +
    `</tbody></table></details>`;
}
// the dynamic parts of a part or a loose designator
function inspDyn(l, ref) {
  const comps = l ? inspLoadFor(l, ref, '') : inspLoadFor(null, ref, selThing && selThing.sheet);
  const first = comps[0];
  return {
    where: l ? inspWhereHTML(l) : '',
    nets: l ? inspNetsHTML(l, comps) : inspNetsHTML({refs: [ref], key: ref, sheet: selThing && selThing.sheet}, comps),
    pins: inspPinsHTML(first, ref),
  };
}
// the answer arrived: fill the three lists in place, so the rest of the drawer (and an input being edited) is left alone
function inspPatch() {
  const root = $('#detail .insp');
  if (!root || !root.dataset.dyn) return;
  const a = document.activeElement;
  if (a && root.contains(a) && a.closest('#insp-where-h, #insp-nets-h, #insp-pins-h, #insp-parts-h')) return;   // a button the user is on
  const put = (id, html) => { const h = $(id); if (h) h.innerHTML = html; };
  const kind = root.dataset.kind, k = root.dataset.k;
  if (kind === 'net') {
    if (selNet !== k) return;
    put('#insp-parts-h', inspNetPartsInner(k));
    const n = inspNetCount(k); put('#insp-net-count', n ? ' · ' + n : '');
    return;
  }
  let dyn = null;
  if (kind === 'part') { const l = lineByKey(k); if (l && sel === l.key) dyn = inspDyn(l, inspFirstRef(l)); }
  else if (kind === 'ref' && selThing && selThing.ref === k) dyn = inspDyn(null, k);
  if (!dyn) return;
  put('#insp-where-h', dyn.where); put('#insp-nets-h', dyn.nets); put('#insp-pins-h', dyn.pins);
}
document.addEventListener('toggle', e => { if (e.target && e.target.id === 'insp-pins-d') inspPinsOpen = e.target.open; }, true);

/* ---------- a part ---------- */
function inspStockHTML(l) {
  if (!qty(l)) return '';
  if (l.supply == null) return inspSec('Stock and price', '<p class="muted">Not checked yet</p>');
  const b = best(l);
  let at = '';
  for (const v of Object.values(l.supply)) if (v && (v.checked_at || '') > at) at = v.checked_at;
  const rows = SUPS.map(s => {
    const v = l.supply[s];
    return `<div class="insp-sup${b && b.s === s ? ' best' : ''}"><span>${esc(s)}</span>` +
      `<span class="num">${v ? esc(num(v.stock)) + ' in stock' : 'not checked'}</span>` +
      `<span class="num"${v && v.qty_break ? ` title="Unit price at ${esc(v.qty_break)} pieces"` : ''}>${v && v.unit_price != null ? esc(money(v.unit_price)) : ''}</span></div>`;
  }).join('');
  const foot = [at ? 'Checked ' + inspWhen(at) : '', b ? '' : '<span class="warn-t">No supplier has enough stock</span>'].filter(Boolean).join(' · ');
  return inspSec('Stock and price', `<div class="insp-sups">${rows}</div>${foot ? `<p class="insp-foot">${foot}</p>` : ''}`);
}
// value and description, left out where they only repeat the MPN already shown above
function inspDesc(l) {
  const mpn = String(l.mpn || '').trim().toLowerCase();
  return [l.value, l.description].filter(x => x && String(x).trim().toLowerCase() !== mpn).filter((x, i, a) => a.indexOf(x) === i).join(' · ');
}
function inspLibHTML(l) {
  if (l.library === 'std') return inspSec('Library', '<p class="muted">Altium default library</p>');
  const e = l.library_entry || {};
  const ck = on => on ? `<span class="ok-t">${icon('check', 's')}</span>` : '<span class="muted">none</span>';
  const tone = {ok: 'ok', review: 'warn', missing: 'bad'}[l.library] || '';
  const act = e.verify === 'pass' && !e.accepted ? btn('Accept', {size: 'sm', kind: 'line', accept: l.key})
    : e.verify !== 'pass' && e.symbol ? btn('Verify', {size: 'sm', kind: 'line', verify: l.key}) : '';
  const status = tag(({ok: 'Verified', review: 'To review', missing: 'Missing'})[l.library] || l.library, tone);
  return inspSec('Library',
    `<div class="insp-lib"><span>Symbol ${ck(e.symbol)}</span><span>Footprint ${ck(e.footprint)}</span><span>3D ${e.step ? 'STEP' : '<span class="muted">simple</span>'}</span></div>` +
    `${e.model_source ? `<p class="insp-foot">Model: ${esc(e.model_source)}</p>` : ''}${e.issues ? `<p class="insp-foot warn-t">${esc(e.issues)}</p>` : ''}`, status + act);
}
function inspDatasheetHTML(l) {
  if (l.datasheet) {
    const known = !!srcByName(l.datasheet);
    return inspSec('Datasheet', known ? btn('', {kind: 'link', src: l.datasheet, html: `<span class="m">${esc(l.datasheet)}</span>`})
      : `<span class="m muted" title="Not in Sources">${esc(l.datasheet)}</span>`);
  }
  return inspSec('Datasheet', '<p class="muted">None stored</p>', btn('Get datasheet', {size: 'sm', kind: 'line', act: 'get-datasheet', line: l.key}));
}
function inspPartHTML(l) {
  const refs = inspRefsOf(l), first = inspFirstRef(l);
  const dyn = inspDyn(l, first);
  const onSheet = !!(sheetsOfLine(l).length || l.sheet);
  const items = [
    {label: 'Alternatives', act: 'alts', attrs: {line: l.key}},
    {label: 'Show on schematic', act: 'show-sch', attrs: {key: l.key}, disabled: !onSheet},
    {label: 'Show on layout', act: 'show-pcb', attrs: {key: l.key}, disabled: !inspHasPcb()},
    l.datasheet ? {label: 'Open datasheet', attrs: {src: l.datasheet}} : {label: 'Get datasheet', act: 'get-datasheet', attrs: {line: l.key}},
  ];
  const acts = btn('Ask', {kind: 'pri', size: 'sm', act: 'insp-ask', key: l.key}) + menu({icon: 'more', size: 'sm', title: 'More'}, items);
  const field = (name, label, value, ph, mono) => [label, `<input class="in quiet${mono ? ' m' : ''}" data-edit="${name}" data-line="${esc(l.key)}" value="${esc(value || '')}" placeholder="${ph}" aria-label="${label}" autocomplete="off" spellcheck="false">`, true];
  const sub = [l.manufacturer, l.package].filter(Boolean).map(esc).join(' · ');
  return `<div class="insp" data-kind="part" data-k="${esc(l.key)}" data-dyn="1">` +
    inspHead(refsLabel(refs) || l.key, sub, acts) +
    `<div class="drawer-b">` +
    `<div>${kv([field('mpn', 'MPN', l.mpn, 'MPN', true), field('role', 'Role', l.role, 'Add a role'), field('note', 'Note', l.note, 'Add a note')])}` +
    `${inspDesc(l) ? `<p class="insp-desc">${esc(inspDesc(l))}</p>` : ''}</div>` +
    `<div id="insp-where-h">${dyn.where}</div><div id="insp-nets-h">${dyn.nets}</div>` +
    inspStockHTML(l) + inspLibHTML(l) + inspDatasheetHTML(l) +
    `<div id="insp-pins-h">${dyn.pins}</div>` +
    `</div></div>`;
}

/* a designator that is on a sheet or the layout but not in the BOM */
function inspRefHTML(t) {
  const dyn = inspDyn(null, t.ref);
  const c = inspComp[t.ref + '|' + (t.sheet || '')];
  const d = c && c.state === 'ok' ? c.data : null;
  const sub = d ? [d.value || d.comment, d.package || d.footprint].filter(Boolean).map(esc).join(' · ') : '';
  return `<div class="insp" data-kind="ref" data-k="${esc(t.ref)}" data-dyn="1">` +
    inspHead(t.ref, sub, btn('Ask', {kind: 'pri', size: 'sm', act: 'insp-ask', ref: t.ref})) +
    `<div class="drawer-b"><p class="muted">Not in the BOM</p>` +
    `${d && d.description ? `<p class="insp-desc">${esc(d.description)}</p>` : ''}` +
    `<div id="insp-where-h"></div><div id="insp-nets-h">${dyn.nets}</div><div id="insp-pins-h">${dyn.pins}</div></div></div>`;
}

/* ---------- a net ---------- */
// Which parts touch a net. The BOM has no such list, so it is read from what is loaded: the netlist sheets, the pads of the
// layout picture and the pins of the components fetched for the part inspector.
function inspPadMap() {
  const text = pcbSvgCache && pcbSvgCache.text;
  if (!text || text.includes('Settings to view PCB')) return null;
  if (inspPadsMemo && inspPadsMemo.text === text) return inspPadsMemo.map;
  const map = new Map();
  try {
    const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
    for (const p of doc.querySelectorAll('rect.pad')) {
      const net = p.getAttribute('data-net'), ref = p.getAttribute('data-ref');
      if (!net || !ref) continue;
      const t = (p.querySelector('title') || {}).textContent || '';
      const pin = t.startsWith(ref + '.') ? t.slice(ref.length + 1).split(':')[0].replace(/\s*\(TH\)$/, '') : '';
      if (!map.has(net)) map.set(net, []);
      map.get(net).push({ref, pin});
    }
  } catch (e) { return null; }
  inspPadsMemo = {text, map};
  return map;
}
function inspNetParts(net) {
  const m = new Map();
  const add = (ref, pin) => { if (!m.has(ref)) m.set(ref, new Set()); if (pin) m.get(ref).add(pin); };
  for (const sh of S.sheets || []) for (const [ref, p] of Object.entries(sh.parts || {})) if ((p.nets || []).includes(net)) add(ref, '');
  const pads = inspPadMap();
  if (pads) for (const p of pads.get(net) || []) add(p.ref, p.pin);
  for (const c of Object.values(inspComp)) if (c.state === 'ok' && c.data) for (const p of c.data.pins || []) if (p.net === net) add(c.data.ref, p.number);
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], 'en', {numeric: true}));
}
const inspNetCount = net => { const n = inspNetParts(net).length; return n ? inspPl(n, 'part') : ''; };
function inspNetPartsInner(net) {
  const rows = inspNetParts(net);
  if (!rows.length) return pcbSvgCache && pcbSvgCache.text ? '<p class="muted">No connected parts found</p>' : loadingLine('Reading the layout');
  const shown = inspMore.parts ? rows : rows.slice(0, INSP_CAP.parts);
  return '<div class="insp-rows">' + shown.map(([ref, pins]) => {
    const l = lineOfRef(ref), pl = [...pins];
    return `<button type="button" class="insp-row" data-act="pick-part" data-ref="${esc(ref)}"><span class="ref">${esc(ref)}</span>` +
      `<span class="muted">${esc(l ? (l.value || l.mpn || '') : '')}</span>` +
      `<span class="pin m">${pl.length === 1 ? 'pin ' + esc(pl[0]) : pl.length > 1 ? esc(inspPl(pl.length, 'pin')) : ''}</span></button>`;
  }).join('') + (rows.length > shown.length ? inspMoreBtn('parts', rows.length - shown.length) : '') + '</div>';
}
function inspNetHTML(net) {
  // the layout picture holds the pads: make sure it is loaded
  if (typeof pcbText === 'function' && !(pcbSvgCache && pcbSvgCache.text)) pcbText().then(inspPatch).catch(() => {});
  const crit = ((S.placement_plan || {}).critical_nets || []).find(n => n.net === net);
  const count = inspNetCount(net);
  return `<div class="insp" data-kind="net" data-k="${esc(net)}" data-dyn="1">` +
    inspHead(net, `Net<span id="insp-net-count">${count ? ' · ' + count : ''}</span>`,
      btn('Ask', {kind: 'pri', size: 'sm', act: 'ask-net', net}) + btn('Highlight', {size: 'sm', act: 'hl-net', net, title: 'Show this net on the schematic'})) +
    `<div class="drawer-b">${crit ? inspSec('Critical net', `<p>${esc(crit.note || 'Marked critical in the placement plan.')}</p>`) : ''}` +
    inspSec('Connected parts', `<div id="insp-parts-h">${inspNetPartsInner(net)}</div>`) + `</div></div>`;
}

/* ---------- a plan zone ---------- */
function inspZoneHTML(name) {
  const g = ((S.placement_plan || {}).groups || []).find(x => x.name === name) || {};
  const mm = v => v == null ? '' : String(Math.round(v * 10) / 10);
  const pairs = [['Size', g.w != null && g.h != null ? `${mm(g.w)} × ${mm(g.h)} mm` : ''], ['Position', g.x != null && g.y != null ? `x ${mm(g.x)}, y ${mm(g.y)} mm` : '']];
  return `<div class="insp" data-kind="zone" data-k="${esc(name)}">` +
    inspHead(name, 'Placement zone', btn('Ask', {kind: 'pri', size: 'sm', act: 'ask-zone', zone: name}), true) +
    `<div class="drawer-b">${g.note ? `<p>${esc(g.note)}</p>` : ''}${kv(pairs)}</div></div>`;
}

/* ---------- picking things (the previews and the lists call these) ---------- */
function inspRefresh() {
  if (typeof markSelected === 'function') markSelected();
  if (typeof applyFocus === 'function') applyFocus();
  renderDetail();
}
function pickNet(net) {
  if (!net) return;
  sel = null; selThing = null; selNet = net; inspMore = {};
  inspRefresh();
}
function pickZone(name) {
  if (!name) return;
  sel = null; selNet = null; selThing = {kind: 'zone', name}; inspMore = {};
  inspRefresh();
}
function pickPart(ref, sheet) {
  if (!ref) return;
  inspMore = {};
  const l = lineOfRef(ref);
  selNet = null; selThing = null;
  if (l) { select(l.key); return; }
  sel = null; selThing = {kind: 'ref', ref, sheet: sheet || ''};
  inspRefresh();
}
function closeInspector() {
  sel = null; selNet = null; selThing = null; inspMore = {};
  inspRefresh();
}
function clearSelection() { closeInspector(); }

/* ---------- keyboard: Esc closes it unless something on top (menu, palette, dialog, viewer, drawer) is open ---------- */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || e.defaultPrevented || uiBusy()) return;
  const d = $('#detail');
  if (!d || d.hidden) return;
  if (typeof bomDrawer !== 'undefined' && bomDrawer) return;
  const v = $('#viewer');
  if (v && !v.hidden) return;
  const a = document.activeElement;
  if (a && a !== document.body && !a.closest('#detail, #view, #view-side')) return;     // typing in the chat, a field elsewhere
  closeInspector();
});

/* ---------- action handlers (dispatched by the click delegate in core.js) ---------- */
onAct('close', async (el, d, e) => {
  closeInspector(); return;
});
onAct('insp-ask', async (el, d, e) => {
  const l = d.key && lineByKey(d.key);
  if (l) askAbout({kind: 'part', id: l.key, label: refsLabel(l.refs || []) || l.key});
  else if (d.ref) askAbout({kind: 'part', id: d.ref, label: d.ref});
  return;
});
onAct('ask-net', async (el, d, e) => {
  if (d.net) askAbout({kind: 'net', id: d.net, label: d.net}); return;
});
onAct('ask-zone', async (el, d, e) => {
  if (d.zone) askAbout({kind: 'zone', id: d.zone, label: d.zone}); return;
});
onAct('show-sch', async (el, d, e) => {
  showOnSchematic(d.key, d.sheet, d.ref); return;
});
onAct('show-pcb', async (el, d, e) => {
  showOnLayout(d.key, d.ref); return;
});
onAct('pick-net', async (el, d, e) => {
  pickNet(d.net);
  if (typeof revealNet === 'function') revealNet(d.net);
  return;
});
onAct('pick-part', async (el, d, e) => {
  pickPart(d.ref);
  if (typeof revealRef === 'function') revealRef(d.ref);
  return;
});
onAct('hl-net', async (el, d, e) => {
  if (!d.net) return;
  if (inspOn('sch') || inspOn('pcb')) { if (typeof revealNet === 'function') revealNet(d.net); }
  else if (typeof showNetOnSchematic === 'function') showNetOnSchematic(d.net);
  return;
});
onAct('insp-more', async (el, d, e) => {
  if (d.what) { inspMore[d.what] = true; renderDetail(); } return;
});
