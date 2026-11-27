/* PCB Advisor UI - Outputs view: the files the tool wrote into the project's exports folder (OutJob, BOM, pick and place),
   and the actions that write them. The BOM export itself is the `export` act in bom.js (one handler, one toast).
   Names here start with out* because every ui/js file shares one global scope. */

const OUT_NEW_MS = 12000;                     // a file written this recently flashes once when it shows up
const OUT_OUTJOB = 'The OutJob makes Gerber RS-274X, NC drill, BOM, pick and place (CPL) and a schematic PDF.';

const outFlashed = new Set();                 // 'name|written' of the files that have flashed already

/* The manufacturing files (Altium's outputs, the Gerber zip) are refused by the server while the board has unrouted nets (or was never
   routed or checked) or the design is unfinished. Unverified or conflicting pins are a WARNING only (owner decision 24/11/2026): the page
   names the parts (stage 'outputs' pins_warning) and the files are made all the same. */
/* The one gate is the server's: stages[] 'outputs' is blocked exactly when store.manufacturing_block is not empty (unrouted nets, open pins,
   pins missing from the netlist, a draft). Its text lists everything at once; the open pins come with one "Mark all N as NC" and an "Ask the agent" each. */
function outGate() {
  const st = typeof stageOf === 'function' ? stageOf('outputs') : null;
  return st && st.gate && st.gate.blocked ? st.gate : null;
}
function outBlockWhy() {
  const g = outGate();
  return g ? g.why : '';
}
const OUT_RISKY = ['shell', 'thermal', 'duplicate'];      // pin_model.RISKY_KINDS: never swept up by "Mark all as NC"
function outGapItems(g) {
  const gaps = (g && g.gaps) || {};
  return [...(gaps.open || []).map(i => ({...i, gap: 'open'})), ...(gaps.unlisted || []).map(i => ({...i, gap: 'unlisted'})),
    ...(gaps.pads || []).map(i => ({...i, gap: 'pad'})), ...(gaps.nopad || []).map(i => ({...i, gap: 'nopad'}))];
}
// the pins one click may mark NC: not a pin naming no pad (nothing to mark), not a shell / exposed / duplicate pad (each is its own decision)
const outBulkItems = g => outGapItems(g).filter(i => i.gap !== 'nopad' && !OUT_RISKY.includes(i.kind));
const OUT_KIND = {
  shell: 'is a shell / mounting pad: connect it to GND or mark it no-connect',
  thermal: 'is an exposed pad or a tab: it almost certainly needs a net',
  duplicate: 'has the same function as a connected pad of this part: it almost certainly needs the same net',
};
function outGapRow(i) {
  const pin = `<span class="m">${esc(i.ref)}</span> ${i.gap === 'pad' || i.kind ? 'pad' : 'pin'} ${esc(i.num || i.name)}${i.name && i.num && i.name !== i.num ? ` (${esc(i.name)})` : ''}`;
  const ask = btn('Ask the agent', {kind: 'link', size: 'sm', act: 'nc-ask', ref: i.ref, num: i.num, pname: i.name, why: i.gap});
  if (i.gap === 'nopad') {
    const shown = (i.pads || []).slice(0, 12).join(', ') + ((i.pads || []).length > 12 ? ' ...' : '');
    return `<li>${pin}${i.net ? ` on net ${esc(i.net)}` : ''} is in the netlist, but footprint ${esc(i.footprint)} has no such pad (its pads: ${esc(shown)}) ${ask}</li>`;
  }
  const what = OUT_KIND[i.kind] || (i.gap === 'open' ? 'has no net and is not marked NC' : i.gap === 'unlisted' ? 'is in the library symbol but missing from the netlist' : 'is on the footprint but in no net');
  const net = i.suggest_net || '';
  const conn = net && i.wirable !== false ? btn(`Connect to ${net}`, {kind: 'link', size: 'sm', act: 'net-set-one', sh: i.sheet, ref: i.ref, num: i.num, net, title: `Puts ${i.ref} pad ${i.num || i.name} on ${net}`}) + ' ' : '';
  const why = i.wirable === false ? ' The library symbol has no pin for it, so it cannot be wired: pick another LCSC code if it needs a net.' : '';
  return `<li>${pin} ${what}.${why} ${conn}` +
    btn('Mark NC', {kind: 'link', size: 'sm', act: 'nc-mark-one', sh: i.sheet, ref: i.ref, num: i.num, title: 'Marks just this pin no-connect'}) + ' ' + ask + '</li>';
}
const ncItem = i => ({sheet: i.sheet, ref: i.ref, num: i.num});
/* The agent's NC proposal: pins it wants NC, held until the student approves. One click for the whole list; untick a pin to leave it out. */
function outNcProposal(g) {
  const items = (g && g.nc_proposal) || (typeof S !== 'undefined' && S.nc_proposal) || [];
  if (!items.length) return '';
  const rows = items.map(i => `<li><label><input type="checkbox" checked data-nc-sheet="${esc(i.sheet)}" data-nc-ref="${esc(i.ref)}" data-nc-num="${esc(i.num)}"> ` +
    `<span class="m">${esc(i.ref)}</span> pin ${esc(i.num || i.name)}${i.name && i.name !== i.num ? ` (${esc(i.name)})` : ''}</label></li>`).join('');
  const text = `The agent proposes marking ${items.length} ${items.length === 1 ? 'pin' : 'pins'} no-connect (NC). Untick any that should be wired.`;
  const acts = btn(`Approve ${items.length === 1 ? 'the NC mark' : 'all ' + items.length}`, {kind: 'line', size: 'sm', act: 'nc-approve', title: 'Marks the ticked pins NC in one go'}) +
    btn('Dismiss', {kind: 'link', size: 'sm', act: 'nc-dismiss'});
  return `<div data-nc-prop="1">${banner({tone: 'info', html: `${esc(text)}<ul>${rows}</ul>`, actions: acts})}</div>`;
}
const OUT_GATE_PAGE = {sch: 'Open Schematic', pcb: 'Open Layout', checks: 'Open DFM'};
/* the pins warning (never a block): the parts whose pins nobody checked or that differ from the datasheet, named by the server */
function outPinsWarn() {
  const st = typeof stageOf === 'function' ? stageOf('outputs') : null;
  return (st && st.pins_warning) || '';
}
function outPinsWarnNote() {
  const w = outPinsWarn();
  if (!w) return '';
  const acts = (typeof pinsConfirmAllBtn === 'function' ? pinsConfirmAllBtn() : '') + btn('Open DFM', {kind: 'link', page: 'checks'});
  return `<div data-pins-warn="1">${banner({tone: 'warn', text: w, actions: acts})}</div>`;
}
function outBlockNote(where) {
  const g = outGate();
  if (!g) return '';
  // a board that was never placed, routed or checked is "not started", not an error: neutral on Outputs, and nothing at all on the Schematic page
  if (g.quiet) return where === 'sch' ? '' : banner({tone: 'info', text: 'Not started yet: the board has not been placed, routed or checked. The manufacturing files are made once it is routed and checked.'});
  const why = where === 'sch' && g.board_started === false ? g.design : g.why;      // on the Schematic page only the design's own blockers count, not the board that is not there yet
  if (!why) return '';
  const items = outGapItems(g), bulk = outBulkItems(g);
  const acts = (bulk.length ? btn(`Mark all ${bulk.length} as NC`, {kind: 'line', size: 'sm', act: 'nc-mark-all', title: 'Marks these pins no-connect in the netlist (a No ERC cross when drawn). Shell, exposed and duplicate pads are not in it: decide each one. Connect any pin that is not meant to be NC first.'}) : '')
    + btn(OUT_GATE_PAGE[g.page] || OUT_GATE_PAGE.checks, {kind: 'link', page: OUT_GATE_PAGE[g.page] ? g.page : 'checks'});
  const list = items.length ? `<details class="pv-more"><summary>Show the ${items.length} ${items.length === 1 ? 'pin' : 'pins'}</summary><ul>${items.map(outGapRow).join('')}</ul></details>` : '';
  return `${outNcProposal(g)}${banner({tone: 'warn', html: `${esc(why)}${list}`, actions: acts})}`;
}
async function outNcPost(path, items, said) {
  const r = await api(path, items ? {items} : {}, {soft: true});
  if (!r || r.error) { toast((r && r.error) || "Couldn't mark the pins NC.", null, {bad: true}); return; }
  toast(said(r));
  await refresh(true);
}
const outMarked = r => `Marked ${r.marked} ${r.marked === 1 ? 'pin' : 'pins'} NC`;
onAct('nc-mark-all', () => outNcPost('/api/nc/mark', outBulkItems(outGate()).map(ncItem), outMarked));     // exactly the pins the button counts
onAct('net-set-one', async (el, d) => {      // a shell pad to GND, a duplicate pad to its twin's net
  const r = await api('/api/nc/mark', {items: [{sheet: d.sh, ref: d.ref, num: d.num}], net: d.net}, {soft: true});
  if (!r || r.error) { toast((r && r.error) || "Couldn't set the net.", null, {bad: true}); return; }
  toast(`${d.ref} pad ${d.num} is on ${d.net}`);
  await refresh(true);
});
onAct('nc-mark-one', (el, d) => outNcPost('/api/nc/mark', [{sheet: d.sh, ref: d.ref, num: d.num}], outMarked));
onAct('nc-approve', el => {
  const box = el.closest('[data-nc-prop]');
  const items = [...box.querySelectorAll('input[data-nc-ref]:checked')].map(c => ({sheet: c.dataset.ncSheet, ref: c.dataset.ncRef, num: c.dataset.ncNum}));
  return outNcPost('/api/nc/approve', items, r => r.marked ? outMarked(r) : 'No pin was ticked: the proposal is dropped');
});
onAct('nc-dismiss', () => outNcPost('/api/nc/dismiss', null, () => 'Dropped the NC proposal'));
onAct('nc-ask', (el, d) => {
  const what = d.why === 'open' ? 'has no net and is not marked NC' : d.why === 'nopad' ? 'is in the netlist but is not a pad of the footprint' : d.why === 'pad' ? 'is a pad of the footprint with no net' : 'is in the library symbol but missing from the netlist';
  askAbout({kind: 'part', id: d.ref, label: d.ref, text: `Pin ${d.num || d.pname} (${d.pname || ''}) of ${d.ref} ${what}. Which net does it belong to, or should it be NC? If NC, propose the NC list for all such pins in one go.`});
});

function outSize(n) {                         // 7467 -> "7.3 KB"
  n = Number(n) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}
function outAgo(iso) {                        // "just now", "5 min ago", "2 h ago", "3 days ago", then the date
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 45) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 7 * 86400) return `${Math.round(s / 86400)} days ago`;
  return whenText(new Date(t).toISOString());
}
const outFull = iso => (iso || '').replace('T', ' ').slice(0, 16);
const outUrl = name => `/api/export/${encodeURIComponent(name)}?${q()}`;
// Lineage (scripts/lineage.py): whether each file still matches what it was made from.
const OUT_LIN = {fresh: ['Current', 'ok'], stale: ['Out of date', 'warn'], edited: ['Edited by hand', 'bad'], unknown: ['No record', '']};
const outOld = files => files.filter(f => f.lineage && (f.lineage.status === 'stale' || f.lineage.status === 'edited'));
function outLineage(f) {
  const l = f.lineage;
  if (!l || !OUT_LIN[l.status]) return '';
  const [text, tone] = OUT_LIN[l.status];
  const made = l.written ? `Made ${outFull(l.written)}${l.tool ? ' by ' + l.tool : ''}${l.version ? ' (version ' + l.version + ')' : ''}.` : '';
  const why = (l.reasons || []).join('; ');
  return tag(text, tone, [made, why].filter(Boolean).join(' ') || (l.status === 'fresh' ? 'Matches the design it was made from' : ''));
}

/* ---------- Make again: rerun the exporter that made a stale or edited file (the lineage record's `tool`) ---------- */
const OUT_REMAKE_NO = {
  export_bom: 'a BOM export', export_cpl: 'the pick and place export', outjob: 'the OutJob generator',
  export_library: 'the library package export', gerber_zip: 'the Gerber zip',
};
const outAltiumLinked = () => !!(ALTIUM_DATA && ALTIUM_DATA.linked && ALTIUM_DATA.linked.project_file);
// What "Make again" does for one file: {kind: 'api' | 'altium' | 'none', label, why, edited}. Pure: only reads the lineage row.
function outRemakePlan(f) {
  const l = f && f.lineage;
  if (!l || (l.status !== 'stale' && l.status !== 'edited')) return {kind: 'none', label: '', why: '', edited: false};
  const edited = l.status === 'edited', tool = l.tool || '';
  if (tool === 'gerber_zip') {       // the zip is built from Altium's Gerbers: when the board was saved after them, Altium must write them again
    if ((l.reasons || []).some(r => /saved after|\.pcbdoc/i.test(r)))
      return {kind: 'altium', label: 'Generate the outputs in Altium first', edited,
        why: 'The board was saved after these Gerbers were generated. Altium writes the Gerbers; then the zip is made again.'};
    return {kind: 'api', label: 'Make again', why: 'Zips the newest Gerber and NC drill set of the linked Altium project again.', edited};
  }
  if (tool === 'export_bom' && !/_BOM_([a-z0-9]+)\.csv$/i.test(f.name || ''))
    return {kind: 'none', label: '', why: `Can't tell which BOM format ${f.name} is. Export it from the Export menu.`, edited};
  if (OUT_REMAKE_NO[tool]) return {kind: 'api', label: 'Make again', why: 'Runs the same export again.', edited};
  return {kind: 'none', label: '', why: tool ? `Made by "${tool}", which this view can't run again.` : 'No record of what made this file.', edited};
}
function outRemakeBtn(f) {
  const p = outRemakePlan(f);
  if (p.kind === 'none') return p.why ? `<span class="out-remake-why muted" title="${esc(p.why)}">No Make again</span>` : '';
  const altium = p.kind === 'altium', block = altium || p.kind === 'api' && /gerber_zip/.test((f.lineage && f.lineage.tool) || '') ? outBlockWhy() : '';
  const title = altium && !outAltiumLinked() ? 'Link an Altium project in Settings first: Altium has to write the Gerbers.' : block || p.why;
  return btn(p.label, {kind: 'line', size: 'sm', act: 'remake', name: f.name, title, disabled: (altium && !outAltiumLinked()) || !!block || !!pvBusy, cls: 'out-remake'});
}
// An in-page confirm dialog, not the browser one: resolves true on the confirm button, false on Cancel or Esc.
function outConfirm({title, body, confirm}) {
  return new Promise(resolve => {
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg';
    dlg.setAttribute('aria-labelledby', 'dlg-title');
    dlg.innerHTML = `<form method="dialog"><h2 id="dlg-title">${esc(title)}</h2><p>${esc(body)}</p>
      <div class="acts"><button type="button" class="btn" data-cancel>Cancel</button><button type="submit" class="btn pri" value="ok">${esc(confirm || 'OK')}</button></div></form>`;
    dlg.querySelector('[data-cancel]').addEventListener('click', () => dlg.close('cancel'));
    dlg.addEventListener('close', () => { const ok = dlg.returnValue === 'ok'; dlg.remove(); resolve(ok); });
    document.body.appendChild(dlg);
    dlg.showModal();
  });
}
const OUT_EDITED_ASK = 'This file was edited by hand; making it again replaces your edits.';
async function outRunExporter(f) {         // one api exporter; returns true when it wrote the file
  const tool = (f.lineage && f.lineage.tool) || '';
  if (tool === 'export_bom') {
    const m = /_BOM_([a-z0-9]+)\.csv$/i.exec(f.name);
    await api('/api/skill', {name: 'export_bom', args: [m[1]]});
  } else if (tool === 'export_cpl') {
    const r = await api('/api/cpl/export', {});
    ((r && r.warnings) || []).forEach(w => toast(w, null, {bad: true}));
  }
  else if (tool === 'outjob') await api('/api/outjob/generate', {filename: f.name});
  else if (tool === 'export_library') await api('/api/library/export', {});
  else if (tool === 'gerber_zip') {
    const r = await api('/api/jlc/gerber-zip', {}, {soft: true});
    if (!r || r.error) { toast((r && r.error) || "Couldn't make the Gerber zip.", null, {bad: true}); return false; }
    outAltNote = {text: `Gerber zip written, ${r.files.length} files.`, bad: false};
  } else return false;
  return true;
}
async function outRunAltium() {            // Altium writes the Gerbers; true when it did. The same step button as the header's: live list, Stop, one answer
  if (pvBusy) return false;
  await pvRunStep('outputs');
  const n = pvNote.outputs;
  return !!n && n.kind !== 'bad' && !n.stopped;      // stopped: Altium made nothing, so nothing is packed again
}
let outRemaking = false;
async function outRemake(files) {          // files: the lineage rows to make again, in order; one confirm for the edited ones
  if (outRemaking || !files.length) return;
  const plans = files.map(f => [f, outRemakePlan(f)]).filter(([, p]) => p.kind !== 'none');
  const edited = plans.filter(([, p]) => p.edited).map(([f]) => f.name);
  if (edited.length && !await outConfirm({title: 'Replace your edits?', confirm: 'Make again',
      body: edited.length === 1 ? OUT_EDITED_ASK : `${OUT_EDITED_ASK} (${edited.join(', ')})`})) return;
  outRemaking = true;
  let done = 0;
  try {
    let altium = false;
    for (const [f, p] of plans) {
      if (p.kind === 'altium') { altium = altium || outAltiumLinked(); continue; }
      if (await outRunExporter(f)) done++;
    }
    if (altium && await outRunAltium()) {  // then the zip, which is what the student asked for
      for (const [f, p] of plans) if (p.kind === 'altium' && await outRunExporter(f)) done++;
    } else if (plans.some(([, p]) => p.kind === 'altium') && !altium) toast('Link an Altium project first: Altium has to write the Gerbers.', null, {bad: true});
  } finally { outRemaking = false; }
  await refresh(true);                   // the lineage is read again, so the tag clears
  if (done) toast(done === 1 ? 'Made again' : `Made ${done} files again`);
}

function outLinked() {       // only when an Altium project is linked; the link is read once, then the view redraws
  if (!ALTIUM_DATA && !ALTIUM_ERR && typeof loadAltium === 'function') loadAltium().then(() => { if (ALTIUM_DATA && ALTIUM_DATA.linked) renderCenter(true); });
  return !!(ALTIUM_DATA && ALTIUM_DATA.linked && ALTIUM_DATA.linked.project_file);
}
/* The automatic route is the primary one: Altium writes the files (a step button with the live list and Stop). Without a linked Altium
   project the manual route (the OutJob to copy) stays primary. While the server's gate is closed (an unrouted board, an unfinished design) the
   generate button is held back, with the reason; unverified pins do not hold it. */
function outAltiumBtn(primary) {
  if (!outLinked()) return '';
  const why = outBlockWhy();
  return pvStepBtn('outputs', {kind: primary ? 'pri' : 'line', disabled: !!why, title: why || undefined});
}
const outOutjobBtn = primary => btn('Generate OutJob', {kind: primary ? 'pri' : 'line', act: 'gen-outjob', title: OUT_OUTJOB + ' Copy it into your Altium project folder.'});
function outHeader(files, hasAlt) {
  if (!files.length && !hasAlt) return viewHeader({title: 'Outputs'});
  const linked = outLinked();
  const actions = (linked ? outOutjobBtn(false) : '') + menu({label: 'Export', iconAfter: 'chev'}, outExportItems());
  const primary = linked ? outAltiumBtn(true) : outOutjobBtn(true);
  const old = outOld(files).length;
  const meta = metaLine([...(files.length ? [{n: files.length, label: files.length === 1 ? 'file' : 'files'}, {label: 'in exports/', always: true}] : []),
    {n: old, label: 'out of date', tone: 'warn', title: 'Made from a design that has changed since, or edited by hand: export again before ordering'}]);
  return viewHeader({title: 'Outputs', meta, actions, primary});
}
const outExportItems = () => [
  {label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}},
  {label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}},
  {label: 'Pick and place (CPL)', act: 'gen-cpl'},
  {label: 'Gerber zip for JLC', hint: outBlockWhy() ? 'blocked' : 'from Altium', act: 'gen-gerber-zip', disabled: !!outBlockWhy(), why: outBlockWhy()},
];
function outRow(f, showTimes, showLin) {
  const at = f.modified, key = f.name + '|' + at;          // the state lists each file with its size and when it was written (ISO)
  const fresh = !!at && !outFlashed.has(key) && Date.now() - new Date(at).getTime() < OUT_NEW_MS;
  if (at) outFlashed.add(key);
  return `<tr data-file="${esc(f.name)}"${fresh ? ' class="flash"' : ''}>
    <td class="out-n"><button type="button" class="out-open" data-act="view-export" data-name="${esc(f.name)}" title="Open ${esc(f.name)} beside this sheet">${esc(f.name)}</button></td>
    ${showTimes ? `<td class="muted c-mod" title="${esc(outFull(at))}">${at ? `<time datetime="${esc(at)}" data-ago>${esc(outAgo(at))}</time>` : ''}</td>` : ''}
    ${showLin ? `<td class="c-lin">${outLineage(f)}</td>` : ''}
    <td class="num">${esc(outSize(f.size))}</td>
    <td><div class="row-acts">${showLin ? outRemakeBtn(f) : ''}<a class="btn icon sm out-dl" href="${esc(outUrl(f.name))}" download="${esc(f.name)}" title="Download ${esc(f.name)}" aria-label="Download ${esc(f.name)}">${icon('download')}</a></div></td></tr>`;
}
/* ---------- what Altium wrote into its own outputs folder ("Project Outputs for ..."), read from the server ---------- */
let OUT_ALT = null, outAltFor = null, outAltNote = null;      // OUT_ALT: {root, folders:[{folder, files, newest}], files, newest}; outAltNote: {text, bad} of the last run
async function outLoadAlt() {
  const p = PROJECT;
  outAltFor = p;
  let r = null;
  try { r = await api('/api/altium/outputs', undefined, {soft: true}); } catch (err) { r = null; }
  if (p !== PROJECT) return;
  OUT_ALT = r && !r.error ? r : {root: '', folders: [], files: 0, newest: ''};
  if (mainView() === 'outputs' || sideView() === 'outputs') renderCenter(true);
}
/* ONE list: the files in exports/ and Altium's own output folders are rows of the same table. A folder row says where it is
   ("In Altium's outputs folder") in the status column, the file count in the size column; the top-level folder is not called ".". */
function outAltState() {
  if (outAltFor !== PROJECT) { OUT_ALT = null; outAltNote = null; }
  if (OUT_ALT === null && outAltFor !== PROJECT) outLoadAlt();
  return OUT_ALT && OUT_ALT.files ? OUT_ALT : null;
}
function outAltNoteHTML(files) {
  // the zip note is about the last run; once a file in the list is out of date it would sit next to "Out of date" and contradict it
  return outAltNote && !outOld(files || []).length ? banner({tone: outAltNote.bad ? 'bad' : 'ok', text: outAltNote.text}) : '';
}
function outAltRows(a, showTimes, showLin) {
  if (!a) return '';
  return a.folders.map(f => {
    const name = f.folder === '.' ? 'Altium outputs (top level)' : f.folder;
    return `<tr class="out-alt" data-folder="${esc(f.folder)}"><td class="out-n">${esc(name)}</td>`
      + (showTimes ? `<td class="muted c-mod" title="${esc(outFull(f.newest))}"><time datetime="${esc(f.newest)}" data-ago>${esc(outAgo(f.newest))}</time></td>` : '')
      + (showLin ? `<td class="c-lin">${tag("In Altium's outputs folder", '', (a.roots && a.roots.length ? a.roots : [a.root]).join('\n'))}</td>` : '')
      + `<td class="num">${f.files} ${f.files === 1 ? 'file' : 'files'}</td><td></td></tr>`;
  }).join('');
}
function outTable(files, a, timed) {
  const showTimes = timed || !!a, showLin = files.some(f => f.lineage) || !!a;
  return `<table class="tbl rows out-tbl"><thead><tr><th>Name</th>${showTimes ? '<th class="c-mod">Modified</th>' : ''}${showLin ? '<th class="c-lin">Status</th>' : ''}<th class="num">Size</th><th><span class="sr">Actions</span></th></tr></thead>
    <tbody>${files.map(f => outRow(f, showTimes, showLin)).join('')}${outAltRows(a, showTimes, showLin)}</tbody></table>`;
}
function outLimits(linked) {                  // only the reasons that are true now: no Altium project linked, the server's gate
  const r = [];
  if (!linked) r.push('The automatic run needs a linked Altium project.');
  if (outBlockWhy()) r.push('The Altium outputs and the Gerber zip are refused until the blocker above is fixed.');
  return r.join(' ');
}
const outPinRisks = () => (typeof pinRisksHTML === 'function' ? `<div class="vb out-risks">${pinRisksHTML()}</div>` : '').replace('<div class="vb out-risks"></div>', '');       // the accepted pin risks stay in view where the files are made
function outputsHTML(container) {
  const files = S.exports || [];
  const a = outAltState(), note = outAltNoteHTML(files);
  if (!files.length && a) {
    return outHeader([], true) + pvStepNoteCard('outputs') + outBlockNote() + outPinsWarnNote() + outPinRisks() + `<div class="vb">${note}${outTable([], a)}</div>`;
  }
  if (!files.length) {
    const linked = outLinked();
    return viewHeader({title: 'Outputs'}) + pvStepNoteCard('outputs') + outBlockNote() + outPinsWarnNote() + outPinRisks() + (note ? `<div class="vb">${note}</div>` : '') + emptyState('Nothing exported yet', linked ? 'Altium generates the outputs from the OutJob, or export the BOM and the pick and place file.' : 'Generate the OutJob for Altium, or export the BOM and the pick and place file.',
      (linked ? outAltiumBtn(true) + outOutjobBtn(false) : outOutjobBtn(true)) + menu({label: 'Export', iconAfter: 'chev'}, outExportItems()),
      outLimits(linked));
  }
  return `${outHeader(files)}${pvStepNoteCard('outputs')}${outBlockNote()}${outPinsWarnNote()}${outPinRisks()}<div class="vb">${note}${outTable(files, a, files.some(f => f.modified))}</div>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
// the BOM exports (`export`) are in bom.js; the OutJob and the pick and place file say what they wrote the same way:
// refresh the list, then a toast with a Download action
async function outWrote(message, file) {
  await refresh(true);
  toast(message, file ? {label: 'Download', onClick: () => bomDownload(file)} : undefined);
}
onAct('gen-outjob', async (el, d, e) => {
  const r = await api('/api/outjob/generate', {});
  await outWrote('OutJob generated. Copy it into your Altium project folder.', r.file || String(r.path || '').split(/[\\/]/).pop());
  return;
});
onAct('gen-cpl', async (el, d, e) => {
  const r = await api('/api/cpl/export', {});
  (r.warnings || []).forEach(w => toast(w, null, {bad: true}));
  await outWrote('Pick and place (CPL) exported', r.name);
  return;
});
onAct('gen-gerber-zip', async (el, d, e) => {     // the newest Gerber and NC drill set of the linked Altium project, in one zip for JLC
  const held = outBlockWhy();
  if (held) { toast(held, null, {bad: true}); return; }       // the server refuses it too; the menu item is disabled, this is for the palette
  const r = await dfmMakeZip();                  // the DFM view's step 1 is the same call; it shows the error when there is one
  if (!r) {
    toast(dfmZipErr || "Couldn't make the Gerber zip.", null, {bad: true});
    return;
  }
  const gaps = (r.missing || []).filter(m => m.level === 'problem').map(m => m.layer.toLowerCase());
  outAltNote = {text: `Gerber zip written, ${r.files.length} files.`, bad: false};     // stays on the page until the next run
  await outWrote(`Gerber zip written, ${r.files.length} files${gaps.length ? `. Missing: ${gaps.join(', ')}` : ''}`, r.zip);
  return;
});
onAct('gen-altium-outputs', async (el, d, e) => {      // the palette's way in: the same step button as the header's
  if (outBlockWhy()) { toast(outBlockWhy(), null, {bad: true}); return; }
  await pvRunStep('outputs');
});
onAct('remake', async (el, d, e) => {
  const f = (S.exports || []).find(x => x.name === d.name);
  if (f) await outRemake([f]);
  return;
});
onAct('remake-all', async (el, d, e) => {
  await outRemake(outOld(S.exports || []));
  return;
});
onAct('view-export', async (el, d, e) => {
  openFileAsTab({name: d.name, path: d.name, fileType: 'export'});
  return;
});
document.addEventListener('click', e => {       // a click anywhere on the row opens the file; the name and the download keep their own
  const tr = e.target.closest && e.target.closest('.out-tbl tbody tr[data-file]');
  if (tr && !e.target.closest('button, a')) openFileAsTab({name: tr.dataset.file, path: tr.dataset.file, fileType: 'export'});
});
setInterval(() => {                              // "5 min ago" keeps counting while the view stays open
  document.querySelectorAll('.out-tbl time[data-ago]').forEach(t => { t.textContent = outAgo(t.getAttribute('datetime')); });
}, 30000);
