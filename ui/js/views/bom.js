/* PCB Advisor UI - BOM view: the one parts table (ordering data and Altium models of every line: the Library page is
   merged into it), the header actions, the supply card, and the right-hand drawer (alternatives, price comparison, import
   from Altium). A part is edited in the inspector (inspector.js); the change handler for its
   role / note / MPN inputs is at the end of this file and works wherever the input sits. */

const CODE_RISK = 'LCSC code is another part';    // store.CODE_RISK
const BOM_EXPORTS = {jlc: 'BOM (JLC)', generic: 'BOM (generic)', pcbway: 'BOM (PCBWay)'};   // the names Outputs uses too
const BOM_STALE_MS = 24 * 3600 * 1000;
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
  return {text: whenText(at, true), stale: Date.now() - d.getTime() > BOM_STALE_MS};
}
/* ---------- the parts table: one row per BOM line, with its ordering data and its Altium models ----------
   The BOM and the Library were two tables of the same lines. They are one now: Ref, Part, Qty, Models (the four icons of
   pages.js libIconsHTML), Supply (one tag; a click opens the supply card), Status (one tag from the library build or the pins).
   The long text (the converter's notes, every supplier, the datasheet) is in the part panel (inspector.js) and the supply card. */
const bomLibType = l => l.library_type || (l.supply && l.supply.LCSC && l.supply.LCSC.library_type) || '';
const bomExt = l => /^ext/i.test(bomLibType(l));
const bomLibRow = l => (S.library || []).find(r => r.line === l.key) || null;
/* Supply: one tag. Worst first: not checked, no stock, low stock, then Extended (a fee per part type), else in stock.
   The supplier risks that are not about stock (the code is another part, no exact MPN match) are counted beside it. */
function bomSupply(l, q, b) {
  if (!q) return {text: '', risks: []};
  const risks = l.risk || [], extra = [];
  if (risks.includes(CODE_RISK)) extra.push({text: 'Code is another part', title: l.supply?.LCSC?.code_mismatch || 'The LCSC code belongs to another part'});
  if (risks.includes('no exact MPN match')) extra.push({text: 'No exact match', title: 'No supplier lists exactly this MPN'});
  let s;
  if (l.supply == null) {
    const lookup = (l.mpn || '').trim() || l.lcsc;
    s = {text: 'Not checked', tone: '', title: lookup ? 'Not checked yet. Press Check stock.' : 'Add an MPN to check stock.'};
  } else if (!b || risks.includes('out of stock')) s = {text: 'No stock', tone: 'bad', title: `No supplier has ${q} in stock`};
  else if (risks.includes('low stock')) s = {text: 'Low stock', tone: 'warn', title: `${num(b.stock)} in stock`};
  else if (bomExt(l)) s = {text: 'Extended fee', tone: 'warn', title: `In stock (${num(b.stock)}). Extended part: JLC charges a fee for each type, once per order`};
  else s = {text: 'In stock', tone: 'ok', title: `${num(b.stock)} in stock at ${b.s}`};
  return Object.assign(s, {risks: extra});
}
/* Status: one tag and one short sentence (the tag's title in the table; the part panel shows it, with the converter's full notes).
   A problem with the pins or the build comes first; a line the build made fine says how far it got. */
function bomStatus(l) {
  const r = bomLibRow(l);
  if (!r && l.library === 'std') return {text: 'Altium default', tone: '', say: 'A part of the Altium default library: nothing to build.'};
  const bs = r ? r.build_status : '';
  if (bs === 'missing') return {text: 'Missing', tone: 'bad', say: 'The library build made no model for this part.'};
  if (bs === 'error' || l.library === 'error') return {text: 'Footprint error', tone: 'bad', say: 'The footprint has errors, so it is not drawn, placed or made.'};
  if (l.pins_status === 'mismatch') return {text: 'Pins conflict', tone: 'bad', say: 'The pins differ from the datasheet: look at them and confirm or fix them.'};
  if (l.pins_status === 'unverified') return {text: 'Verify pins', tone: 'warn', say: 'The pins are not checked against a datasheet yet.'};
  if (!r) return l.library === 'missing' ? {text: 'Missing', tone: 'bad', say: 'No symbol or footprint yet. Press Build library.'} : {text: 'To review', tone: 'warn', say: 'Not reviewed yet.'};
  if (l.pin_decision) return {text: 'Accepted risk', tone: 'warn', say: 'You accepted these pins without a datasheet pin table.'};
  if (bs) {
    const [text, tone] = libBuildTag(r);
    const say = r.built ? (bs === 'warn' ? 'Built, with notes to check.' : 'In the compiled library.')
      : bs === 'warn' ? 'Ready to build, with notes to check.' : 'Press Build library to put it in Altium.';
    return {text, tone, say};
  }
  const [text, tone] = PG_LIB[r.status] || [LIBTXT[r.status] || r.status, ''];
  const say = {ok: 'Symbol and footprint verified.', review: 'Not reviewed yet: verify or accept it.',
    missing: 'No symbol or footprint yet. Press Build library.'}[r.status] || '';
  return {text, tone, say};
}
function bomModels(l) {
  const r = bomLibRow(l);
  if (!r && l.library === 'std') return '<span class="muted" title="Altium default library: no models of its own">·</span>';
  return libIconsHTML(r || libRowOf(l), {built: false});
}
/* A line whose refs are on no netlist sheet while sheets exist (store: l.off_sheet): it shows "not on any sheet" and a Delete. */
function bomOrphan(l) {
  const refs = l.refs || [], off = l.off_sheet || [];
  return refs.length > 0 && off.length === refs.length;
}
function bomRow(l) {
  const q = qty(l), b = best(l), refs = l.refs || [], label = refsLabel(refs);
  const real = v => (v && !/^[-–—\s]+$/.test(v)) ? v : '';        // "-" and an em dash stand for "none"
  const mpn = real(l.mpn), maker = real(l.manufacturer);
  const main = l.value || l.description || mpn || '';
  const sub = mpn && mpn !== main ? mpn : maker;
  const sup = bomSupply(l, q, b), st = bomStatus(l);
  const picked = sel === l.key || (bomDrawer && bomDrawer.line === l.key);
  const orphan = bomOrphan(l);
  const supCell = sup.text ? `<button type="button" class="sup-btn" data-act="sup-open" data-line="${esc(l.key)}" aria-haspopup="dialog" aria-expanded="${bomSupOpen === l.key}" aria-label="${esc(`Supply of ${label}: ${sup.text}. Open the stock and supplier details`)}" title="${esc(sup.title + '. Click for every supplier')}">${tag(sup.text, sup.tone)}</button>` +
      (sup.risks.length ? tag('+' + sup.risks.length, 'warn', sup.risks.map(x => x.text).join(', ') + '. Click the supply tag to see why.') : '')
    : '<span class="muted">·</span>';
  return `<tr data-key="${esc(l.key)}" tabindex="0" class="${picked ? 'sel' : ''}${q ? '' : ' off'}">
    <td class="bom-ref" title="${esc(refs.join(', '))}">${esc(label)}</td>
    <td class="c-part" title="${esc([l.description, mpn, maker, l.package, l.library_type].filter(Boolean).join(' · '))}"><span class="main">${esc(main)}</span>${sub ? `<span class="sub m">${esc(sub)}</span>` : ''}</td>
    <td class="num">${l.dnp ? 'DNP' : q || '—'}</td>
    <td class="c-mdl">${bomModels(l)}</td>
    <td class="c-sup">${supCell}</td>
    <td class="c-st">${tag(st.text, st.tone, st.say + (st.tone ? ' Click the row for the details.' : ''))}${l.role_finding ? tag('Check qty', 'warn', l.role_finding) : ''}${orphan ? tag('not on any sheet', 'warn', `${label} is on no schematic sheet. If it is not part of the design, delete it (Undo puts it back).`) : ''}</td>
    <td><div class="row-acts">${orphan ? btn('', {icon: 'trash', size: 'sm', title: `Delete ${label} from the BOM`, act: 'bom-delete', line: l.key}) : ''}${btn('', {icon: 'chat', size: 'sm', title: `Ask about ${label}`, act: 'ask-part', line: l.key})}${btn('', {html: BOM_SWAP, cls: 'icon', size: 'sm', title: 'Alternatives', 'aria-label': `Alternatives for ${label}`, act: 'alts', line: l.key})}</div></td></tr>`;
}
/* Two header buttons, side by side and always there: Check stock (the BOM's) and Build library (the models'). viewHeader has one
   primary, so Build library is the primary and Check stock the last action; the stage's Next keeps its own slot. */
function bomHeader(t) {
  const lib = S.library || [];
  const check = btn(bomChecking ? 'Checking…' : 'Check stock', {kind: 'line', act: 'check-all', disabled: bomChecking || !t.lines, title: 'Look up stock and prices for every line'});
  // an empty BOM has nothing to build: both stay (disabled, outlined) and the empty state's own button is the one filled button
  const build = btn(libBusy === 'build' ? 'Building…' : 'Build library', {kind: t.lines ? 'pri' : 'line', act: 'libbuild', disabled: !!libBusy || !t.lines,
    title: 'Download, convert and generate the models, compile the IntLib in Altium and install it'});
  if (!t.lines) return viewHeader({title: 'BOM', actions: check, primary: build});
  const fee = t.extended_fee || 0, cost = t.cost_per_board ?? t.cost ?? 0;
  const meta = metaLine([
    {n: t.lines, label: t.lines === 1 ? 'line' : 'lines'},
    {n: t.parts, label: t.parts === 1 ? 'part' : 'parts', title: 'Parts to place, by quantity. Lines marked DNP are not counted.'},
    {n: cost > 0 ? money(cost) : '', label: (t.checking > 0 || t.in_stock < t.buy) && cost > 0 ? `per board (priced lines only: ${t.in_stock} of ${t.buy})` : 'per board',
      title: t.checking > 0 ? `${t.checking} line${t.checking === 1 ? ' has' : 's have'} no stock answer yet (checked in the background, or press Check stock), so this total is incomplete.` : t.in_stock < t.buy ? 'Lines with no in-stock offer are not in this total.' : ''},
    fee > 0 && {always: true, label: `plus ${money(fee)} extended fees`,
      title: `Assumes ${money(CONFIG?.jlc?.extended_fee_usd ?? 3.07)} for each Extended part type, once per order. The JLC quote has the real fee.`},
    {n: t.checking, label: 'not checked', tone: 'warn', title: 'Lines with no stock answer yet'},
    {n: t.out_of_stock, label: 'out of stock', tone: 'bad', title: 'Lines no supplier has enough of'},
    {n: t.library_error, label: 'footprint error', tone: 'bad', title: 'Parts whose footprint has errors: they are not drawn, placed or made until you pick another LCSC code or let the tool generate the footprint.'},
    {n: t.to_verify, label: 'to verify (library)', tone: 'warn', title: 'BOM lines whose symbol, footprint or 3D model nobody has confirmed yet (lines, not parts; the pins waiting for you are counted in the line below the header). Open each line (its Status says what is left) and accept or fix it.'},
  ]);
  const actions = menu({label: 'Export', iconAfter: 'chev'}, [
      {label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}},
      {label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}},
      'sep',
      {label: 'Library package', act: 'libexport', disabled: !!libBusy || !lib.length, title: 'Write a package of the library files to compile yourself'}]) +
    menu({icon: 'more', title: 'More'}, [
      {label: 'Compare prices', act: 'compare'},
      bomLinked() && {label: 'Import from Altium', act: 'imp-open'},
      {label: 'Prepare library only', act: 'libprepare', disabled: !!libBusy, title: 'Get and convert the models without touching Altium'}]) +
    check;
  return viewHeader({title: 'BOM', meta, actions, primary: build});
}
/* what the Library page said above its table: the build's note, the pins waiting for a decision, the export's install steps, the icon legend */
function bomLibNote() {
  if (libBusy === 'build') return banner({tone: 'info', text: 'Building in Altium. It can take a few minutes and Altium may flash while it works.'});
  if (!libNote) return '';
  return banner({tone: libNote.tone, text: libNote.text, actions: /No Altium project is linked/.test(libNote.text)
    ? btn('Create an Altium project', {size: 'sm', act: 'altium-create', title: 'Altium makes the project, an empty PCB and one sheet per planned sheet, with no components'}) + btn('Link a project', {size: 'sm', act: 'pv-link'}) : ''});
}
function bomTop() {
  const html = bomLibNote() + pinsWaitingBar() + libExportHTML() + libLegendHTML();
  return `<div class="bom-top">${html}</div>`;
}

/* ---------- the supply card: every supplier's stock and price, the LCSC code and type, when it was checked ----------
   It opens from the Supply cell (a button: Enter or a click), sits by it, and closes on Esc, an outside click or its X;
   the focus goes back to the cell. It lives in <body>, so a redraw of the table does not take it away: the redraw paints it again. */
let bomSupOpen = null;      // the line whose supply card is open
function bomSupCardHTML(l) {
  const q = qty(l), b = best(l), refs = l.refs || [], label = refsLabel(refs) || l.key;
  const sup = bomSupply(l, q, b), lt = bomLibType(l);
  let at = '';
  for (const v of Object.values(l.supply || {})) if (v && (v.checked_at || '') > at) at = v.checked_at;
  const facts = kv([
    ['LCSC', l.lcsc ? `<span class="m">${esc(l.lcsc)}</span>${lt ? ' ' + tag(lt, bomExt(l) ? 'warn' : '', bomExt(l) ? 'Extended part: JLC charges a fee for each type, once per order' : 'JLC part type') : ''}` : '<span class="muted">none</span>', true],
    lt && !l.lcsc ? ['JLC type', lt] : null,
    ['Quantity', l.dnp ? 'DNP (not fitted)' : q ? `${q} per board` : 'not bought'],
    ['Unit price', b && q ? `${money(b.price)} at ${b.s}` : '—'],
    ['Per board', q && l.cost_per_board > 0 ? money(l.cost_per_board) : '—'],
    ['Checked', at ? inspWhen(at) : 'not yet'],
  ]);
  const risks = sup.risks.map(x => `<p class="warn-t">${esc(x.text)}${x.title ? ': ' + esc(x.title) : ''}</p>`).join('');
  const stock = q ? inspStockHTML(l) : '<p class="muted">Not fitted or not bought: nothing to order.</p>';
  return `<div class="sup-h"><div><h2 id="sup-pop-t">${esc(label)}</h2><p class="m">${esc(l.mpn || l.value || '')}</p></div>` +
    btn('', {icon: 'x', size: 'sm', title: 'Close (Esc)', act: 'sup-close'}) + `</div>` +
    `<div class="sup-b">${sup.text ? `<p>${tag(sup.text, sup.tone)} <span class="muted">${esc(sup.title)}</span></p>` : ''}${facts}${risks}${stock}</div>` +
    `<div class="sup-f">${btn('Check stock', {kind: 'line', size: 'sm', act: 'check-all', disabled: bomChecking})}${btn('Alternatives', {kind: 'line', size: 'sm', act: 'alts', line: l.key})}</div>`;
}
function bomSupPlace(pop, anchor) {
  const a = anchor.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
  const left = Math.max(8, Math.min(a.right - w, window.innerWidth - w - 8));
  const below = a.bottom + 6 + h <= window.innerHeight - 8;
  pop.style.left = left + 'px';
  pop.style.top = (below ? a.bottom + 6 : Math.max(8, a.top - 6 - h)) + 'px';
}
function bomSupAnchor(key) { return document.querySelector(`.bom-view .sup-btn[data-line="${CSS.escape(key)}"]`); }
function bomSupPaint() {
  const pop = document.getElementById('sup-pop');
  const l = bomSupOpen && lineByKey(bomSupOpen), anchor = l && bomSupAnchor(bomSupOpen);
  if (!l || !anchor) { if (pop) bomSupClose(false); return; }
  const had = pop && pop.contains(document.activeElement);
  const el = pop || document.createElement('div');
  if (!pop) {
    el.id = 'sup-pop';
    el.className = 'sup-pop';
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-labelledby', 'sup-pop-t');
    el.tabIndex = -1;
    document.body.appendChild(el);
  }
  el.innerHTML = bomSupCardHTML(l);
  bomSupPlace(el, anchor);
  anchor.setAttribute('aria-expanded', 'true');
  if (!pop || had) el.focus({preventScroll: true});
}
function bomSupClose(refocus) {
  const pop = document.getElementById('sup-pop'), key = bomSupOpen;
  bomSupOpen = null;
  if (pop) pop.remove();
  const a = key && bomSupAnchor(key);
  if (a) { a.setAttribute('aria-expanded', 'false'); if (refocus) a.focus({preventScroll: true}); }
}
// Esc closes the card before anything else (the inspector, the drawer) hears it; a click outside it closes it too
window.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !bomSupOpen || !document.getElementById('sup-pop')) return;
  e.preventDefault(); e.stopPropagation();
  bomSupClose(true);
}, true);
document.addEventListener('pointerdown', e => {
  if (!bomSupOpen) return;
  const t = e.target;
  if (t.closest && (t.closest('#sup-pop') || t.closest(`.sup-btn[data-line="${CSS.escape(bomSupOpen)}"]`))) return;
  bomSupClose(false);
}, true);
function bomSupFollow() {      // the table scrolled or the window changed size: the card stays by its cell
  const pop = document.getElementById('sup-pop'), a = bomSupOpen && bomSupAnchor(bomSupOpen);
  if (pop && a) bomSupPlace(pop, a);
}
window.addEventListener('resize', bomSupFollow);
document.addEventListener('scroll', bomSupFollow, true);

// The BOM and the schematic disagree on the parts: the server says which designators differ (only when both sides are known).
function bomPending() { return (S.proposals || []).filter(p => p.status === 'pending' && p.kind === 'bom'); }
// The pending BOM proposals: the shared proposal table (chat.js propListHTML), one row and one tick per part, with the
// same three buttons as the chat card. Ticks are shared with the chat card by proposal id.
function bomPendingBox(pend, cls) {
  // a delete is never part of Approve all: it gets its own card (Delete / Keep) under the list
  const dels = pend.filter(p => propDelete(p)), rest = pend.filter(p => !propDelete(p));
  const list = rest.length ? `<div class="bom-pend ${cls || ''}" data-pids="${esc(rest.map(p => p.id).join(','))}">${propListHTML(rest)}${propActsHTML(rest.map(p => p.id), true)}</div>` : '';
  return list + dels.map(diffHTML).join('');
}
function bomPendingNote(pend) {
  return pend.length ? `<div class="pv-note">${banner({tone: 'info', cls: 'bom-pend-note', html: `${esc(bomPl(pend.length, 'proposed change'))} waiting for your approval.${bomPendingBox(pend)}`})}</div>` : '';
}
function bomCountNote() {
  const c = S.bom_count_check;
  return c && c.message ? `<div class="pv-note">${banner({tone: 'warn', cls: 'bom-count-note', text: c.message})}</div>` : '';
}
function bomFoot() {
  const at = checkedAt(), st = at ? bomStamp(at) : null;
  return `<p class="bom-foot${st && st.stale ? ' stale' : ''}"${st && st.stale ? ' title="Prices change. Check stock again before you order."' : ''}>Prices at qty 10, excl. shipping. ${st ? `Checked ${esc(st.text)}.` : 'Not checked yet.'} ${btn('Before you order', {kind: 'link', size: 'sm', act: 'order-open', title: 'Stock again, and in-stock alternatives by footprint'})}</p>`;
}
function bomHTML(container) {
  const t = S.totals;
  if (bomDrawerProject !== PROJECT) { bomDrawer = null; bomPrevSel = null; bomDrawerProject = PROJECT; }     // a drawer belongs to one project
  loadImportInfo();       // whether an Altium project is linked decides the empty state and the menu
  const scroller = container && container.querySelector ? container.querySelector('.bom-scroll') : null;
  const top = scroller ? scroller.scrollTop : 0, left = scroller ? scroller.scrollLeft : 0;
  let body;
  const pend = bomPending();
  if (!t.lines && pend.length) {
    body = emptyState(`${bomPl(pend.length, 'proposed part')} waiting for your approval`, 'The agent proposed these parts in the chat. Approve them to add them to the BOM.',
      bomPendingBox(pend, 'bom-pend-empty'));
  } else if (!t.lines) {
    body = emptyState('No parts yet', bomLinked() ? 'Import the BOM you exported from Altium, or describe your idea in the chat.' : 'Describe your idea in the chat and the agent will propose parts.',
      bomLinked() ? btn('Import from Altium', {kind: 'pri', act: 'imp-open'}) : '');
  } else {
    body = `<div class="bom-scroll">${bomTop()}<table class="tbl rows bom-tbl"><thead><tr><th>Ref</th><th class="c-part">Part</th><th class="num">Qty</th>
      <th class="c-mdl" title="Symbol, footprint, 3D, pins: green present, grey missing, red needs fixing">Models</th>
      <th class="c-sup" title="Stock at the suppliers. Click a tag for every supplier, the LCSC code and the prices">Supply</th>
      <th class="c-st" title="What the library build made of the part, or what its pins still need">Status</th><th><span class="sr">Actions</span></th></tr></thead>
      <tbody>${lines().map(bomRow).join('')}</tbody></table></div>${bomFoot()}`;
  }
  if (top || left) requestAnimationFrame(() => { const s = container.querySelector('.bom-scroll'); if (s) { s.scrollTop = top; s.scrollLeft = left; } });
  if (bomSupOpen) requestAnimationFrame(bomSupPaint);      // the card follows the redraw: new numbers, the new cell
  return `<div class="bom-view">${bomHeader(t)}${t.lines ? bomPendingNote(pend) + bomCountNote() : ''}${body}${bomDrawerHTML()}</div>`;
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
/* Before you order: design fixes value + package + pins, ordering may swap the MPN / LCSC code freely on the SAME footprint
   (no library or board change). Another or unproven footprint is a design change. */
const ORDER_CLASS = {swap_free: ['Swap possible', 'warn'], design_change: ['Design change', 'bad'], no_alternative: ['No alternative', 'bad']};
function orderHTML(d) {
  if (d.loading) return loadingLine('Checking what you can order');
  if (d.error) return errorLine('check the order', d.error, btn('Retry', {size: 'sm', act: 'order-open'}));
  const all = d.result.lines, todo = all.filter(l => ORDER_CLASS[l.class]), unchecked = all.filter(l => l.class === 'unchecked').length;
  const head = `<p class="muted">${todo.length ? `${bomPl(todo.length, 'line')} to fix before you order.` : 'Every checked line is in stock.'}${unchecked ? ` ${bomPl(unchecked, 'line')} not checked yet.` : ''}</p>
    <div class="acts">${btn('Check stock again', {kind: 'line', size: 'sm', act: 'order-open', recheck: '1'})}</div>`;
  const notes = (d.result.params_stale || []).map(n => `<p class="muted">${esc(n)}</p>`).join('');
  return head + notes + `<ul class="alts">${todo.map(l => {
    const [text, tone] = ORDER_CLASS[l.class];
    const alts = l.alternatives.map((a, i) => {
      const meta = [a.manufacturer, a.package, a.code].filter(v => v && !/^[-—]+$/.test(v)).map(esc).join(' · ');
      const act = a.match === 'same' ? btn('Swap (same footprint)', {kind: 'line', size: 'sm', act: 'order-swap', line: l.line, i})
        : `<span class="muted" title="${esc(a.why)}">Changes the board: library + PCB update</span>`;
      return `<div class="alt-t"><span class="m alt-mpn">${esc(a.mpn)}</span><span>${meta}</span><span>${num(a.stock)} in stock</span></div>
        <div class="alt-e"><span class="num">${money(a.unit_price)}</span>${act}</div>`;
    }).join('');
    return `<li><div class="alt-t"><span class="m">${esc(refsLabel(l.refs || []))}</span><span class="m">${esc(l.mpn || '')}</span>${tag(text, tone, `Needs ${l.need}, ${num(l.stock)} in stock`)}</div>${alts}</li>`;
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
  } else if (d.kind === 'order') {
    title = 'Before you order';
    sub = 'Swap the part freely only on the same footprint';
    body = orderHTML(d);
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
  bomSupClose(false);
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
onAct('bom-drawer-close', async (el, d, e) => {
  closeBomDrawer(); return;
});
onAct('sup-open', async (el, d, e) => {
  if (bomSupOpen === d.line) { bomSupClose(true); return; }
  bomSupClose(false);
  bomSupOpen = d.line;
  bomSupPaint();
});
onAct('sup-close', async (el, d, e) => { bomSupClose(true); });
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
  const gone = res.left_out_text ? '. ' + res.left_out_text.replace(/\.$/, '') : '';      // DNP lines and parts on no drawn sheet: named, never silent
  toast(`${name} exported${miss.length ? `. No LCSC number for ${miss.slice(0, 3).join(', ')}${miss.length > 3 ? ' +' + (miss.length - 3) : ''} (run Check stock)` : ''}${gone}`,
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
    changes: {mpn: alt.mpn, package: alt.package, description: alt.description || '',
      ...(alt.code ? {lcsc: alt.code} : {}), ...(alt.manufacturer && !/^[-—]+$/.test(alt.manufacturer) ? {manufacturer: alt.manufacturer} : {})},
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

onAct('order-open', async (el, d, e) => {
  const mine = {kind: 'order', loading: true};
  openBomDrawer(mine);
  try {
    const r = d.recheck === '1' ? await api('/api/order/check', {recheck: true}, {soft: true}) : await api('/api/order/check', undefined, {soft: true});
    if (bomDrawer !== mine) return;
    if (r && r.lines) Object.assign(mine, {loading: false, result: r}); else Object.assign(mine, {loading: false, error: (r && r.error) || 'no answer'});
  } catch (err) {
    if (bomDrawer !== mine) return;
    Object.assign(mine, {loading: false, error: err.message || 'no answer'});
  }
  if (d.recheck === '1') { try { setState(await api('/api/state')); } catch (err) { /* the table shows the old answer */ } }
  paintBomDrawer(); return;
});
onAct('order-swap', async (el, d, e) => {      // an order-only swap: the footprint is proven again on the server
  const row = bomDrawer && bomDrawer.kind === 'order' && bomDrawer.result.lines.find(l => l.line === d.line);
  const alt = row && row.alternatives[+d.i];
  if (!alt || alt.match !== 'same') return;
  const res = await api('/api/bom/propose', {
    line: d.line,
    changes: {mpn: alt.mpn, lcsc: alt.code, ...(alt.manufacturer && !/^[-—]+$/.test(alt.manufacturer) ? {manufacturer: alt.manufacturer} : {}), footprint_lock: alt.footprint},
    reason: `order-only swap: same footprint ${alt.footprint} (${alt.code}, ${alt.stock} in stock)`,
    sources: [`JLC ${alt.code}`]
  });
  setState(res);
  bomDrawer = null;
  if (bomPrevSel && sel == null && lineByKey(bomPrevSel)) sel = bomPrevSel;
  bomPrevSel = null;
  render(true);
  const kept = res.proposed && res.proposed.footprint_lock;       // the server proves the footprint again, and says when it could not
  toast(kept ? `Proposed ${alt.mpn} for ${d.line}. The footprint stays. Approve it in the chat.`
    : `Proposed ${alt.mpn} for ${d.line} as a design change: ${(res.proposed && res.proposed.lock_note) || 'the footprint is not proven the same'}. Approve it in the chat.`);
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

/* Delete a BOM line (data-line), or only some refs of it (data-refs="R22,R23"): one confirmation that names the line and refs,
   then an Undo toast. The server records it as an applied change, so the history's Undo restores it too. */
onAct('bom-delete', async (el, d, e) => {
  const l = lineByKey(d.line); if (!l) return;
  const all = l.refs || [], refs = d.refs ? d.refs.split(',').filter(Boolean) : all;
  const whole = refs.length === all.length;
  const name = [l.value || l.description, l.mpn].filter(v => v && !/^[-–—\s]+$/.test(v)).join(' · ');
  const yes = await askChoice({title: whole ? `Delete ${refsLabel(all) || l.key} from the BOM?` : `Remove ${refsLabel(refs)} from line ${l.key}?`,
    text: `${whole ? 'Line ' + l.key : 'Line ' + l.key + ' keeps ' + all.filter(r => !refs.includes(r)).join(', ')}${name ? ' (' + name + ')' : ''}. You can undo it.`,
    list: [`Refs: ${refs.join(', ') || l.key}`], yes: whole ? 'Delete' : 'Remove', no: false});
  if (!yes) return;
  let r;
  try { r = await api('/api/bom/delete', whole ? {line: l.key} : {line: l.key, refs}); } catch (err) { return; }      // toasted
  if (sel === l.key && whole && typeof closeInspector === 'function') closeInspector();
  setState(r); render(true);
  const what = whole ? `${refsLabel(all) || l.key} deleted` : `${refsLabel(refs)} removed from ${l.key}`;
  toast(what, {label: 'Undo', onClick: async () => {
    try { setState(await api('/api/undo', {id: r.deleted.id})); render(true); toast(`${refsLabel(refs) || l.key} is back in the BOM`); } catch (err) { /* toasted */ }
  }});
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

/* A datasheet picked from the computer: it is uploaded like any source, then linked to this line and its pins are checked.
   Get datasheet (above) is the other way in: the agent finds and downloads it. */
let dsPickLine = '';
onAct('datasheet-file', (el) => {
  dsPickLine = el.dataset.line || '';
  $('#dspick').click();
});
onChange(t => t.id === 'dspick', async e => {
  const f = e.target.files[0], line = dsPickLine;
  e.target.value = '';
  if (!f || !line) return;
  toast(`Adding ${f.name}…`);
  try {
    const buf = new Uint8Array(await f.arrayBuffer()); let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    await api('/api/upload', {name: f.name, data_b64: btoa(bin)});
    const name = f.name.replace(/^.*[\/]/, '').replace(/[<>:"|?*\x00-\x1f]/g, '_');      // the name the server saved it under
    const r = await api('/api/parts/attach_datasheet', {line, name});
    setState(r);
    render(true);
    toast(attachMsg(r.attached));
  } catch (err) { /* api() has already said what went wrong */ }
});
