/* PCB Advisor UI - Outputs view: the files the tool wrote into the project's exports folder (OutJob, BOM, pick and place),
   and the actions that write them. The BOM export itself is the `export` act in bom.js (one handler, one toast).
   Names here start with out* because every ui/js file shares one global scope. */

const OUT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const OUT_NEW_MS = 12000;                     // a file written this recently flashes once when it shows up
const OUT_OUTJOB = 'The OutJob makes Gerber RS-274X, NC drill, BOM, pick and place (CPL) and a schematic PDF.';

const outFlashed = new Set();                 // 'name|written' of the files that have flashed already

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
  const d = new Date(t);
  return `${d.getDate()} ${OUT_MONTHS[d.getMonth()]}`;
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
  const altium = p.kind === 'altium';
  const title = altium && !outAltiumLinked() ? 'Link an Altium project in Settings first: Altium has to write the Gerbers.' : p.why;
  return btn(p.label, {kind: 'line', size: 'sm', act: 'remake', name: f.name, title, disabled: altium && !outAltiumLinked(), cls: 'out-remake'});
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
  } else if (tool === 'export_cpl') await api('/api/cpl/export', {});
  else if (tool === 'outjob') await api('/api/outjob/generate', {filename: f.name});
  else if (tool === 'export_library') await api('/api/library/export', {});
  else if (tool === 'gerber_zip') {
    const r = await api('/api/jlc/gerber-zip', {}, {soft: true});
    if (!r || r.error) { toast((r && r.error) || "Couldn't make the Gerber zip.", null, {bad: true}); return false; }
  } else return false;
  return true;
}
async function outRunAltium() {            // Altium writes the Gerbers; true when it did
  toast('Generating the outputs in Altium. It may take a minute and flash while it works.');
  try { await api('/api/altium/run-outjob', {}); return true; } catch (err) { return false; }   // the error toast already said why
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

function outAltiumBtn() {       // only when an Altium project is linked; the link is read once, then the view redraws
  if (!ALTIUM_DATA && !ALTIUM_ERR && typeof loadAltium === 'function') loadAltium().then(() => { if (ALTIUM_DATA && ALTIUM_DATA.linked) renderCenter(true); });
  return ALTIUM_DATA && ALTIUM_DATA.linked && ALTIUM_DATA.linked.project_file
    ? btn('Generate outputs in Altium', {kind: 'line', act: 'gen-altium-outputs', title: 'Altium runs the project OutJob: Gerber, NC drill, BOM and pick and place go into its outputs folder. Ours is added first when the project has none.'}) : '';
}
function outHeader(files) {
  if (!files.length) return viewHeader({title: 'Outputs'});
  const actions = outAltiumBtn() + menu({label: 'Export', iconAfter: 'chev'}, outExportItems());
  const primary = btn('Generate OutJob', {kind: 'pri', act: 'gen-outjob', title: OUT_OUTJOB});
  const old = outOld(files).length;
  const meta = metaLine([{n: files.length, label: files.length === 1 ? 'file' : 'files'}, {label: 'in exports/', always: true},
    {n: old, label: 'out of date', tone: 'warn', title: 'Made from a design that has changed since, or edited by hand: export again before ordering'}]);
  return viewHeader({title: 'Outputs', meta, actions, primary});
}
const outExportItems = () => [
  {label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}},
  {label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}},
  {label: 'Pick and place (CPL)', act: 'gen-cpl'},
  {label: 'Gerber zip for JLC', hint: 'from Altium', act: 'gen-gerber-zip'},
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
function outputsHTML(container) {
  const files = S.exports || [];
  if (!files.length) {
    return viewHeader({title: 'Outputs'}) + emptyState('Nothing exported yet', 'Generate the OutJob for Altium, or export the BOM and the pick and place file.',
      btn('Generate OutJob', {kind: 'pri', act: 'gen-outjob', title: OUT_OUTJOB}) + outAltiumBtn() + menu({label: 'Export', iconAfter: 'chev'}, outExportItems()));
  }
  const showTimes = files.some(f => f.modified), showLin = files.some(f => f.lineage);
  return `${outHeader(files)}<div class="vb"><table class="tbl rows out-tbl"><thead><tr><th>Name</th>${showTimes ? '<th class="c-mod">Modified</th>' : ''}${showLin ? '<th class="c-lin">Status</th>' : ''}<th class="num">Size</th><th><span class="sr">Actions</span></th></tr></thead>
    <tbody>${files.map(f => outRow(f, showTimes, showLin)).join('')}</tbody></table></div>`;
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
  await outWrote('Pick and place (CPL) exported', r.name);
  return;
});
onAct('gen-gerber-zip', async (el, d, e) => {     // the newest Gerber and NC drill set of the linked Altium project, in one zip for JLC
  const r = await dfmMakeZip();                  // the DFM view's step 1 is the same call; it shows the error when there is one
  if (!r) {
    toast(dfmZipErr || "Couldn't make the Gerber zip.", null, {bad: true});
    return;
  }
  const gaps = (r.missing || []).filter(m => m.level === 'problem').map(m => m.layer.toLowerCase());
  await outWrote(`Gerber zip written, ${r.files.length} files${gaps.length ? `. Missing: ${gaps.join(', ')}` : ''}`, r.zip);
  return;
});
onAct('gen-altium-outputs', async (el, d, e) => {      // Altium writes the files; it may take a minute and flash while it works
  if (el.disabled) return;
  el.disabled = true;
  toast('Generating the outputs in Altium. It may take a minute and flash while it works.');
  try {
    const r = await api('/api/altium/run-outjob', {});
    await outWrote(`Altium wrote ${r.files.length} files${r.added ? ' (OutJob added to the project)' : ''}.`);
  } catch (err) { /* the error toast already said why */ }
  el.disabled = false;
  renderCenter(true);
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
