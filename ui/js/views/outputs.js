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

function outHeader(files) {
  if (!files.length) return viewHeader({title: 'Outputs'});
  const actions = menu({label: 'Export', iconAfter: 'chev'}, outExportItems());
  const primary = btn('Generate OutJob', {kind: 'pri', act: 'gen-outjob', title: OUT_OUTJOB});
  const meta = metaLine([{n: files.length, label: files.length === 1 ? 'file' : 'files'}, {label: 'in exports/', always: true}]);
  return viewHeader({title: 'Outputs', meta, actions, primary});
}
const outExportItems = () => [
  {label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}},
  {label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}},
  {label: 'Pick and place (CPL)', act: 'gen-cpl'},
  {label: 'Gerber zip for JLC', hint: 'from Altium', act: 'gen-gerber-zip'},
];
function outRow(f, showTimes) {
  const at = f.modified, key = f.name + '|' + at;          // the state lists each file with its size and when it was written (ISO)
  const fresh = !!at && !outFlashed.has(key) && Date.now() - new Date(at).getTime() < OUT_NEW_MS;
  if (at) outFlashed.add(key);
  return `<tr data-file="${esc(f.name)}"${fresh ? ' class="flash"' : ''}>
    <td class="out-n"><button type="button" class="out-open" data-act="view-export" data-name="${esc(f.name)}" title="Open ${esc(f.name)} beside this sheet">${esc(f.name)}</button></td>
    ${showTimes ? `<td class="muted c-mod" title="${esc(outFull(at))}">${at ? `<time datetime="${esc(at)}" data-ago>${esc(outAgo(at))}</time>` : ''}</td>` : ''}
    <td class="num">${esc(outSize(f.size))}</td>
    <td><div class="row-acts"><a class="btn icon sm out-dl" href="${esc(outUrl(f.name))}" download="${esc(f.name)}" title="Download ${esc(f.name)}" aria-label="Download ${esc(f.name)}">${icon('download')}</a></div></td></tr>`;
}
function outputsHTML(container) {
  const files = S.exports || [];
  if (!files.length) {
    return viewHeader({title: 'Outputs'}) + emptyState('Nothing exported yet', 'Generate the OutJob for Altium, or export the BOM and the pick and place file.',
      btn('Generate OutJob', {kind: 'pri', act: 'gen-outjob', title: OUT_OUTJOB}) + menu({label: 'Export', iconAfter: 'chev'}, outExportItems()));
  }
  const showTimes = files.some(f => f.modified);
  return `${outHeader(files)}<div class="vb"><table class="tbl rows out-tbl"><thead><tr><th>Name</th>${showTimes ? '<th class="c-mod">Modified</th>' : ''}<th class="num">Size</th><th><span class="sr">Actions</span></th></tr></thead>
    <tbody>${files.map(f => outRow(f, showTimes)).join('')}</tbody></table></div>`;
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
