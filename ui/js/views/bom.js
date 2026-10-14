/* PCB Advisor UI - BOM view: the parts table, the header actions, and the right-hand drawer (alternatives, price
   comparison, import from Altium). A part is edited in the inspector (inspector.js); the change handler for its
   role / note / MPN inputs is at the end of this file and works wherever the input sits. */

const CODE_RISK = 'LCSC code is another part';    // store.CODE_RISK
const BOM_EXPORTS = {jlc: 'BOM (JLC)', generic: 'BOM (generic)', pcbway: 'BOM (PCBWay)'};   // the names Outputs uses too
const BOM_STALE_MS = 24 * 3600 * 1000;
const BOM_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const BOM_SWAP = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4 3 8l4 4M3 8h13M17 20l4-4-4-4M21 16H8"/></svg>';
let bomDrawer = null;       // the open drawer: {kind: 'alts' | 'compare' | 'import', ...}
let bomDrawerProject = null;
let bomPrevSel = null;      // the part the inspector showed before the drawer took its place
let bomChecking = false;    // a stock check is running

const bomPl = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;

/* ---------- import candidates (Altium) ---------- */
async function loadImportInfo(force) {
  if (!force && impFor === PROJECT) return;
  impFor = PROJECT;
  try {
    const r = await api('/api/bom/import/candidates', undefined, {soft: true});
    impInfo = r && !r.error ? r : null;
  } catch (e) { impInfo = null; }
  const cs = impInfo ? impInfo.candidates : [];
  if (!cs.some(c => c.path === impSel)) impSel = cs.length ? cs[0].path : '';
  renderCenter(true);
}
const bomLinked = () => !!(impInfo && impInfo.linked);

/* ---------- table ---------- */
function bomStamp(at) {     // "2026-10-14 10:20" -> {text: '14 Oct 10:20', stale: older than 24 h}
  const d = new Date(String(at).replace(' ', 'T'));
  if (isNaN(d)) return {text: String(at), stale: false};
  const hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  return {text: `${d.getDate()} ${BOM_MONTHS[d.getMonth()]} ${hm}`, stale: Date.now() - d.getTime() > BOM_STALE_MS};
}
/* The problems of one line, worst first. A line that is not fitted or not bought has none. Only a problem gets a tag:
   a healthy line has an empty cell. The library type (Basic, Preferred, Extended) is not a problem: it is in the
   row's tooltip, the meta line sums the extended fee, and the inspector shows the type. */
function bomProblems(l, q, b) {
  if (!q) return [];
  const risks = l.risk || [], out = [];
  if (l.supply == null) {
    const lookup = (l.mpn || '').trim() || l.lcsc;
    out.push({rank: 5, text: 'Not checked', title: lookup ? 'Press Check stock' : 'Add an MPN to check stock'});
  } else if (!b || risks.includes('out of stock')) {
    out.push({rank: 0, text: 'Out of stock', tone: 'bad', title: `No supplier has ${q} in stock`});
  } else if (risks.includes('low stock')) {
    out.push({rank: 3, text: 'Low stock', tone: 'warn', title: `${num(b.stock)} in stock`});
  }
  if (risks.includes(CODE_RISK)) out.push({rank: 1, text: 'Code is another part', tone: 'warn', title: l.supply?.LCSC?.code_mismatch || ''});
  if (risks.includes('no exact MPN match')) out.push({rank: 2, text: 'No exact match', tone: 'warn', title: 'No supplier lists exactly this MPN'});
  // A model still to review is the normal state of a new or imported BOM: the meta line counts those, the Library page
  // lists them. Only a missing model is a problem worth a tag on the row.
  if (l.library === 'missing') out.push({rank: 4, text: 'No model', tone: 'warn', title: LIBTXT.missing});
  return out.sort((a, c) => a.rank - c.rank);
}
function bomTags(ps) {      // the worst problem; the others are counted, and named in the tooltip, so a row keeps its height
  if (!ps.length) return '';
  const rest = ps.slice(1);
  return tag(ps[0].text, ps[0].tone, ps[0].title) + (rest.length ? tag('+' + rest.length, '', 'Also: ' + rest.map(p => p.text).join(', ')) : '');
}
function bomRow(l) {
  const q = qty(l), b = best(l), refs = l.refs || [], label = refsLabel(refs);
  const real = v => (v && !/^[-–—\s]+$/.test(v)) ? v : '';        // "-" and an em dash stand for "none"
  const mpn = real(l.mpn), maker = real(l.manufacturer);
  const main = l.value || l.description || mpn || '';
  const sub = [mpn && mpn !== main ? `<span class="m">${esc(mpn)}</span>` : '', esc(maker)].filter(Boolean).join(' · ');
  const noStock = q > 0 && l.supply != null && !b;
  const maxStock = Math.max(0, ...Object.values(l.supply || {}).map(s => s.stock || 0));
  const stock = !q || l.supply == null ? '—' : num(b ? b.stock : maxStock);
  const cost = q && l.cost_per_board > 0 ? l.cost_per_board : null;
  const picked = sel === l.key || (bomDrawer && bomDrawer.line === l.key);
  return `<tr data-key="${esc(l.key)}" tabindex="0" class="${picked ? 'sel' : ''}${q ? '' : ' off'}">
    <td class="bom-ref" title="${esc(refs.join(', '))}">${esc(label)}</td>
    <td title="${esc([l.description, mpn, maker, l.library_type].filter(Boolean).join(' · '))}"><span class="main">${esc(main)}</span>${sub ? `<span class="sub">${sub}</span>` : ''}</td>
    <td class="c-pkg"><span class="clip" title="${esc(l.package)}">${esc(l.package)}</span></td>
    <td class="num">${l.dnp ? 'DNP' : q || '—'}</td>
    <td class="num${noStock ? ' bad-t' : ''}"${b ? ` title="${esc(b.s)}"` : ''}>${stock}</td>
    <td class="num c-unit">${b && q ? money(b.price) : '—'}</td>
    <td class="num"${b && q ? ` title="${esc(money(b.price))} each"` : ''}>${money(cost)}</td>
    <td class="tags">${bomTags(bomProblems(l, q, b))}</td>
    <td><div class="row-acts">${btn('', {icon: 'chat', size: 'sm', title: `Ask about ${label}`, act: 'ask-part', line: l.key})}${btn('', {html: BOM_SWAP, cls: 'icon', size: 'sm', title: 'Alternatives', 'aria-label': `Alternatives for ${label}`, act: 'alts', line: l.key})}</div></td></tr>`;
}
function bomHeader(t) {
  if (!t.lines) return viewHeader({title: 'BOM'});
  const fee = t.extended_fee || 0, cost = t.cost_per_board ?? t.cost ?? 0;
  const meta = metaLine([
    {n: t.lines, label: t.lines === 1 ? 'line' : 'lines'},
    {n: t.parts, label: t.parts === 1 ? 'part' : 'parts'},
    {n: cost > 0 ? money(cost) : '', label: 'per board'},
    fee > 0 && {always: true, label: `plus $${fee.toFixed(2)} extended fees`,
      title: `Assumes $${CONFIG?.jlc?.extended_fee_usd || 3} for each Extended part type, once per order. The JLC quote has the real fee.`},
    {n: t.checking, label: 'not checked', tone: 'warn', title: 'Lines with no stock answer yet'},
    {n: t.out_of_stock, label: 'out of stock', tone: 'bad', title: 'Lines no supplier has enough of'},
    {n: t.to_verify, label: 'to verify', tone: 'warn', title: 'Parts whose symbol, footprint or 3D model is not verified yet'},
  ]);
  const actions = menu({label: 'Export', iconAfter: 'chev'}, [
      {label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}},
      {label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}}]) +
    menu({icon: 'more', title: 'More'}, [
      {label: 'Compare prices', act: 'compare'},
      bomLinked() && {label: 'Import from Altium', act: 'imp-open'}]);
  const primary = btn(bomChecking ? 'Checking…' : 'Check stock', {kind: 'pri', act: 'check-all', disabled: bomChecking, title: 'Look up stock and prices for every line'});
  return viewHeader({title: 'BOM', meta, actions, primary});
}
function bomFoot() {
  const at = checkedAt(), st = at ? bomStamp(at) : null;
  return `<p class="bom-foot${st && st.stale ? ' stale' : ''}"${st && st.stale ? ' title="Prices change. Check stock again before you order."' : ''}>Prices at qty 10, excl. shipping. ${st ? `Checked ${esc(st.text)}.` : 'Not checked yet.'}</p>`;
}
function bomHTML(container) {
  const t = S.totals;
  if (bomDrawerProject !== PROJECT) { bomDrawer = null; bomPrevSel = null; bomDrawerProject = PROJECT; }     // a drawer belongs to one project
  loadImportInfo();       // whether an Altium project is linked decides the empty state and the menu
  const scroller = container && container.querySelector ? container.querySelector('.bom-scroll') : null;
  const top = scroller ? scroller.scrollTop : 0, left = scroller ? scroller.scrollLeft : 0;
  let body;
  if (!t.lines) {
    body = emptyState('No parts yet', bomLinked() ? 'Import the BOM you exported from Altium, or describe your idea in the chat.' : 'Describe your idea in the chat and the agent will propose parts.',
      bomLinked() ? btn('Import from Altium', {kind: 'pri', act: 'imp-open'}) : '');
  } else {
    body = `<div class="bom-scroll"><table class="tbl rows bom-tbl"><thead><tr><th>Ref</th><th>Part</th><th class="c-pkg">Package</th>
      <th class="num">Qty</th><th class="num">Stock</th><th class="num c-unit" title="Cheapest offer with enough stock, at qty 10">Unit</th><th class="num">Per board</th>
      <th><span class="sr">Problems</span></th><th><span class="sr">Actions</span></th></tr></thead>
      <tbody>${lines().map(bomRow).join('')}</tbody></table></div>${bomFoot()}`;
  }
  if (top || left) requestAnimationFrame(() => { const s = container.querySelector('.bom-scroll'); if (s) { s.scrollTop = top; s.scrollLeft = left; } });
  return `<div class="bom-view">${bomHeader(t)}${body}${bomDrawerHTML()}</div>`;
}

/* ---------- drawer ---------- */
function altsHTML(d) {
  if (d.loading) return loadingLine('Searching in-stock alternatives');
  if (d.error) return errorLine('load alternatives', d.error, btn('Retry', {size: 'sm', act: 'alts', line: d.line}));
  if (!d.list.length) return '<p class="muted">No in-stock alternatives found.</p>';
  return `<ul class="alts">${d.list.map((a, i) => {
    const unit = a.price_breaks && a.price_breaks[0] ? a.price_breaks[0].price : null;
    const meta = [a.manufacturer, a.package].filter(v => v && !/^[-—]+$/.test(v)).map(esc).join(' · ');
    const more = [a.code ? `<span class="m">${esc(a.code)}</span>` : '', esc(a.library_type), `${num(a.stock)} in stock`].filter(Boolean).join(' · ');
    return `<li><div class="alt-t"><span class="m alt-mpn">${esc(a.mpn)}</span>${meta ? `<span>${meta}</span>` : ''}<span>${more}</span></div>
      <div class="alt-e"><span class="num">${money(unit)}</span>${btn('Propose', {kind: 'line', size: 'sm', act: 'propose-alt', i})}</div></li>`;
  }).join('')}</ul>`;
}
function compareHTML(d) {
  if (d.loading) return loadingLine('Comparing suppliers');
  if (d.error) return errorLine('compare prices', d.error, btn('Retry', {size: 'sm', act: 'compare'}));
  const rows = d.result.suppliers, whole = r => !r.missing.length && !r.not_checked.length;
  const cheapest = Math.min(Infinity, ...rows.filter(r => whole(r) && r.cost_per_board > 0).map(r => r.cost_per_board));
  return `<ul class="cmp">${rows.map(r => {
    const unchecked = r.not_checked.length === 0 ? '' : bomPl(r.not_checked.length, 'line') + ' not checked';
    const missing = r.missing.length ? `no stock for ${esc(r.missing.slice(0, 5).join(', '))}${r.missing.length > 5 ? ' +' + (r.missing.length - 5) : ''}` : '';
    const note = whole(r) ? 'Everything in stock' : [unchecked, missing].filter(Boolean).join(' · ');
    const none = !(r.cost_per_board > 0);
    return `<li${whole(r) && r.cost_per_board === cheapest ? ' class="best"' : ''}><span class="cmp-n">${esc(r.supplier)}</span><span class="num">${none ? '—' : money(r.cost_per_board)}</span><span class="cmp-d">${note}</span></li>`;
  }).join('')}</ul>`;
}
function importHTML() {
  const empty = !lines().length, cs = (impInfo && impInfo.candidates) || [];
  const label = c => `${c.folder.split(/[\\/]/).slice(-1)[0]}/${c.name} · ${c.rows} rows${c.has_lcsc ? ' · LCSC' : ''} · ${bomStamp(c.mtime.replace('T', ' ')).text.replace(/ \d\d:\d\d$/, '')}`;
  const rescan = btn('', {icon: 'refresh', size: 'sm', title: 'Look for BOM files again', act: 'imp-scan'});
  const pick = cs.length
    ? `<div class="imp-pick"><select class="in" id="imp-csv" aria-label="BOM file">${cs.map(c => `<option value="${esc(c.path)}" title="${esc(c.mtime.replace('T', ' ').slice(0, 16))}" ${c.path === impSel ? 'selected' : ''}>${esc(label(c))}</option>`).join('')}</select>${rescan}</div>
      <div class="acts">${btn('Preview', {kind: 'line', act: 'imp-preview', disabled: impBusy})}${btn('Import', {kind: 'pri', act: 'imp-apply', disabled: !empty || impBusy, title: empty ? '' : 'Import works into an empty BOM'})}</div>
      ${empty ? '' : '<p class="muted">Import works into an empty BOM. Preview still shows what differs.</p>'}`
    : `<p class="muted">No BOM CSV found in the Altium project. Export one from Altium (Reports, Bill of Materials), then look again.</p><div class="acts">${btn('Look again', {kind: 'line', act: 'imp-scan'})}</div>`;
  return pick + (impReport ? importReportHTML(impReport) : '');
}
function importReportHTML(r) {
  const src = r.sources.find(s => s.role === 'bom_csv') || {}, sev = r.by_severity;
  const order = {error: 0, warn: 1, info: 2}, tone = s => s === 'error' ? 'bad' : s === 'warn' ? 'warn' : '';
  const all = [...r.findings].sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3)), shown = all.slice(0, 8);
  const counts = [[sev.error, 'error', 'bad-t'], [sev.warn, 'warning', 'warn-t'], [sev.info, 'note', '']].filter(c => c[0])
    .map(([n, w, cls]) => `<span class="${cls}">${bomPl(n, w)}</span>`).join(' · ');
  return `<div class="imp-rep"><div><b>${r.applied ? `Imported ${r.imported_lines} lines` : 'Preview, nothing imported yet'}</b>
      <span class="muted">from ${esc(src.name)}: ${bomPl(r.csv.lines, 'line')}, ${bomPl(r.csv.refs, 'designator')}</span></div>
    <div>${counts || '<span class="muted">No differences found</span>'}</div>
    ${shown.length ? `<table class="tbl dense"><thead><tr><th><span class="sr">Severity</span></th><th>Refs</th><th>Finding</th></tr></thead><tbody>
      ${shown.map(f => `<tr><td>${dot(tone(f.severity), f.severity)}</td><td class="m">${esc(f.refs.slice(0, 4).join(', '))}${f.refs.length > 4 ? ' +' + (f.refs.length - 4) : ''}</td><td><span class="m sub">${esc(f.kind)}</span>${esc(f.message)}</td></tr>`).join('')}
    </tbody></table>` : ''}
    <div class="acts">${btn('Open report', {kind: 'link', act: 'imp-report'})}${all.length > shown.length ? `<span class="muted">Showing ${shown.length} of ${all.length}</span>` : ''}</div></div>`;
}
function bomDrawerHTML() {
  const d = bomDrawer;
  if (!d) return '';
  const l = d.line ? lineByKey(d.line) : null;
  let title, sub = '', body;
  if (d.kind === 'alts') {
    title = 'Alternatives';
    sub = [l ? `<span class="m">${esc(refsLabel(l.refs || []))}</span>` : esc(d.line), d.mpn ? `<span class="m">${esc(d.mpn)}</span>` : ''].filter(Boolean).join(' · ');
    body = altsHTML(d);
  } else if (d.kind === 'compare') {
    title = 'Compare prices';
    sub = `Parts cost per board at qty ${d.result ? d.result.qty_break : 10}, excl. shipping`;
    body = compareHTML(d);
  } else {
    title = 'Import from Altium';
    body = importHTML();
  }
  return `<aside class="drawer bom-drawer" role="dialog" aria-label="${esc(title)}" tabindex="-1">
    <div class="drawer-h"><div class="t"><h2>${esc(title)}</h2>${sub ? `<p>${sub}</p>` : ''}</div>${btn('', {icon: 'x', size: 'sm', title: 'Close', act: 'bom-drawer-close'})}</div>
    <div class="drawer-b">${body}</div></aside>`;
}
/* the drawer takes the inspector's place while it is open, and gives it back on close */
function openBomDrawer(d) {
  if (!bomDrawer && sel) { bomPrevSel = sel; sel = null; }
  bomDrawer = d;
  if ($('.bom-view')) renderCenter(true); else go('workspace', 'bom');
  const el = $('.bom-drawer');
  if (el) el.focus({preventScroll: true});
}
function paintBomDrawer() {
  const had = document.activeElement && document.activeElement.closest && document.activeElement.closest('.bom-drawer');
  renderCenter(true);
  const el = $('.bom-drawer');
  if (had && el) el.focus({preventScroll: true});
}
function closeBomDrawer() {
  if (!bomDrawer) return;
  bomDrawer = null;
  if (bomPrevSel && sel == null && lineByKey(bomPrevSel)) sel = bomPrevSel;
  bomPrevSel = null;
  renderCenter(true);
}
function bomDownload(name) {
  const a = document.createElement('a');
  a.href = `/api/export/${encodeURIComponent(name)}?${q()}`;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
function bomKeepFocus(fn) {     // an edit re-renders the inspector: the field the user tabbed into must keep the focus
  const a = document.activeElement, d = a && a.dataset;
  const again = d && d.edit && d.line ? `input[data-edit="${d.edit}"][data-line="${CSS.escape(d.line)}"]` : '';
  fn();
  const n = again && $(again);
  if (n) n.focus();
}

/* ---------- keyboard and pointer: Esc closes the drawer; rows are reachable and move with the arrows ---------- */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && bomDrawer && !uiBusy()) { closeBomDrawer(); return; }
  const tr = e.target.closest && e.target.closest('.bom-view tbody tr[data-key]');
  if (!tr || e.target !== tr) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(tr.dataset.key); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const next = e.key === 'ArrowDown' ? tr.nextElementSibling : tr.previousElementSibling;
    if (next) { e.preventDefault(); next.focus(); }
  }
});
document.addEventListener('click', e => {      // picking a row hands the slot back to the inspector
  if (bomDrawer && e.target.closest && e.target.closest('.bom-view tbody tr[data-key]') && !e.target.closest('button')) {
    bomDrawer = null; bomPrevSel = null;
    const el = $('.bom-drawer');
    if (el) el.remove();
  }
}, true);

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('closecard', async (el, d, e) => {      // the Library export card (pages.js) still closes with this
  libExport = null; render(true); return;
});
onAct('bom-drawer-close', async (el, d, e) => {
  closeBomDrawer(); return;
});
onAct('ask-part', async (el, d, e) => {
  const l = lineByKey(d.line);
  askAbout({kind: 'part', id: d.line, label: l ? refsLabel(l.refs || []) : d.line}); return;
});

/* Check stock: the one action behind the header button and the command palette. Success shows in the table and the
   footer; a supplier that failed is said out loud. */
onAct('check-all', async (el, d, e) => {
  if (bomChecking) return;
  bomChecking = true;
  const inView = !!$('.bom-view');
  if (inView) renderCenter(true); else toast('Checking stock…');
  let errs = [];
  try {
    const r = await api('/api/skill', {name: 'check'});
    setState(r.state);
    errs = ((r.result && r.result.results) || []).filter(x => x.error);
  } catch (err) { /* api() already said it */ }
  bomChecking = false;
  render(true);
  if (errs.length) toast(`Stock checked. ${bomPl(errs.length, 'supplier lookup')} failed (${errs[0].supplier}: ${String(errs[0].error).slice(0, 80)})`);
  else if (!inView) toast('Stock checked');
  return;
});
onAct('compare', async (el, d, e) => {
  const mine = {kind: 'compare', loading: true};
  openBomDrawer(mine);
  try {
    const r = await api('/api/skill', {name: 'compare'}, {soft: true});
    if (bomDrawer !== mine) return;
    if (r && r.result) Object.assign(mine, {loading: false, result: r.result}); else Object.assign(mine, {loading: false, error: (r && r.error) || 'no answer'});
  } catch (err) {
    if (bomDrawer !== mine) return;
    Object.assign(mine, {loading: false, error: err.message || 'no answer'});
  }
  paintBomDrawer(); return;
});
onAct('export', async (el, d, e) => {
  const fmt = d.fmt || 'jlc', name = BOM_EXPORTS[fmt] || 'BOM';
  const r = await api('/api/skill', {name: 'export_bom', args: [fmt]});
  if (r.state) setState(r.state);      // the Outputs view lists the new file
  render(true);
  const res = r.result || {}, file = String(res.file || '').split(/[\\/]/).pop(), miss = res.needs_lcsc || [];
  toast(`${name} exported${miss.length ? `. No LCSC number for ${miss.slice(0, 3).join(', ')}${miss.length > 3 ? ' +' + (miss.length - 3) : ''} (run Check stock)` : ''}`,
    file ? {label: 'Download', onClick: () => bomDownload(file)} : undefined);
  return;
});

onAct('alts', async (el, d, e) => {
  const line = d.line || d.key;
  if (!line) return;
  const l = lineByKey(line), mine = {kind: 'alts', line, mpn: l ? l.mpn : '', loading: true, list: []};
  openBomDrawer(mine);
  try {
    const r = await api(`/api/parts/alternatives?line=${encodeURIComponent(line)}`, undefined, {soft: true});
    if (bomDrawer !== mine) return;
    if (Array.isArray(r)) Object.assign(mine, {loading: false, list: r}); else Object.assign(mine, {loading: false, error: (r && r.error) || 'no answer'});
  } catch (err) {
    if (bomDrawer !== mine) return;
    Object.assign(mine, {loading: false, error: err.message || 'no answer'});
  }
  paintBomDrawer(); return;
});
onAct('propose-alt', async (el, d, e) => {
  const alt = bomDrawer && bomDrawer.kind === 'alts' && bomDrawer.list[+d.i];
  if (!alt) return;
  const line = bomDrawer.line;
  const res = await api('/api/bom/propose', {
    line,
    changes: {mpn: alt.mpn, package: alt.package, description: alt.description || ''},
    reason: `Alternative part proposed: ${alt.code} (${alt.library_type || 'Standard'})`,
    sources: [`JLC ${alt.code}`]
  });
  setState(res);
  bomDrawer = null;
  if (bomPrevSel && sel == null && lineByKey(bomPrevSel)) sel = bomPrevSel;
  bomPrevSel = null;
  render(true);
  toast(`Proposed ${alt.mpn} for ${line}. Approve it in the chat.`);
  return;
});

onAct('imp-open', async (el, d, e) => {
  openBomDrawer({kind: 'import'});
  loadImportInfo(true); return;
});
onAct('imp-scan', async (el, d, e) => {
  await loadImportInfo(true); toast('Looked for BOM files again'); return;
});
const runImport = async (el, d, e) => {
  const pick = $('#imp-csv'), csv = pick ? pick.value : impSel, apply = d.act === 'imp-apply';
  if (!csv) { toast('Pick a BOM file first'); return; }
  impSel = csv; impBusy = true; renderCenter(true);
  try {
    const r = await api('/api/bom/import', {csv, apply});
    impReport = r;
    if (r.state) setState(r.state);
    if (apply) toast(`Imported ${r.imported_lines} lines from ${csv.split(/[\\/]/).pop()}`);
  } finally { impBusy = false; render(true); }
  return;
};
onAct('imp-preview', runImport);
onAct('imp-apply', runImport);
onAct('imp-report', async (el, d, e) => {     // the findings as plain text in a new tab; the .md is in the project's checks/ folder
  const r = impReport; if (!r) return;
  const src = r.sources.find(s => s.role === 'bom_csv') || {};
  const text = [`BOM import report: ${r.applied ? 'imported' : 'preview'}`, `File: ${src.name || ''}`, `Also saved in the project: checks/bom-import.md`, '',
    ...r.findings.map(f => `${String(f.severity).toUpperCase().padEnd(5)}  ${f.kind}  ${(f.refs || []).join(', ')}  ${f.message}`)].join('\n');
  const url = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'}));
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60000); return;
});
onChange(t => t.id === 'imp-csv', async e => {
  impSel = e.target.value; impReport = null; renderCenter(true); return;
});

onAct('get-datasheet', async (el, d, e) => {
  const lineKey = el.dataset.line;
  toast('Fetching datasheet…');
  const res = await api('/api/parts/datasheet', {line: lineKey});
  if (res.error) {
    if (res.url && /^https?:\/\//i.test(res.url)) {
      toast(`Couldn't download the datasheet (${res.error}). Open the link, save the PDF and add it in Sources.`,
        {label: 'Open link', onClick: () => window.open(res.url, '_blank', 'noopener')});
    } else {
      toast('Could not find a datasheet URL: ' + res.error);
    }
    return;
  }
  if (res.state) setState(res.state);
  render(true);
  toast('Datasheet added to ' + lineKey);
  return;
});

/* Role, note and MPN are edited in the inspector (<input data-edit="role|note|mpn" data-line="KEY">); a change is saved
   when the field is left. It works for an input anywhere. An unchanged value is not sent, and an MPN may not be empty. */
onChange(t => t.closest && t.closest('input[data-edit]'), async e => {
  const i = e.target.closest('input[data-edit]'); if (!i) return;
  const l = lineByKey(i.dataset.line); if (!l) return;
  const field = i.dataset.edit, val = i.value.trim();
  if (field === 'mpn' && !val) { i.value = l.mpn ?? ''; return; }
  if (val === (l[field] ?? '')) return;
  try {
    setState(await api('/api/bom/edit', {line: l.key, field, value: val}));
    bomKeepFocus(() => render(true));
    if (field === 'mpn') { toast(`MPN updated. Checking stock for ${val}…`); setTimeout(() => refresh(), 6000); }
  } catch (err) { /* toasted */ }
});
