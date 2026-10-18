/* PCB Advisor UI - DFM view: the JLCDFM reports of the bare board and the assembly, the findings list (one verdict each),
   and the report slices. The findings are triage rows (projects/<p>/checks/<stem>/triage.json); every change goes through
   /api/checks/triage and is saved silently. Names here start with dfm* because every ui/js file shares one global scope. */

// the verdict a finding gets: [stored value, label, what it means]. 'model' is JLC's own model being off, not the board.
const DFM_VERDICTS = [
  ['unknown', 'Not reviewed', 'Nobody has judged this finding yet'],
  ['real', 'Real issue', 'The board needs a change'],
  ['model', 'False alarm', "JLC's model of the part or board is off; the files are right"],
  ['by design', 'By design', 'The finding is true and intended'],
];
const DFM_SEGS = [{value: 'pcb', label: 'Bare board'}, {value: 'smt', label: 'Assembly'}];
// the report a segment shows; with nothing for its own kind, the other one's (a project with only an assembly report)
const dfmStemFor = kind => (kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curPcbCheckStem || curSmtCheckStem;
const DFM_VCLASS = {'unknown': 'v-open', 'real': 'v-real', 'model': 'v-done', 'by design': 'v-done'};

let dfmSeg = 'pcb';          // the segment on show: 'pcb' (bare board) or 'smt' (assembly)
let dfmSegUser = false;      // the user chose it, so it is not switched for them
let dfmOpen = '';            // the finding that shows its fix and evidence: 'stem|index'
let dfmBusy = false;         // a report is being uploaded and sliced
let dfmErr = {};             // 't:'+stem / 'i:'+stem -> why the findings or the slices did not load
let dfmTried = {};           // what was asked for already, so a failure is not asked again on every render
let dfmSig = {};             // stem -> fingerprint of the findings as loaded or last saved
let dfmSeen = {};            // stem -> the fingerprint the state carried last
let dfmSaving = {};          // stem -> saves in flight
let dfmQueue = {};           // stem -> the last save, so two saves of one table go out in order

// the JLC check done together: the guide, the Gerber zip, and finding the report the student exported
let dfmGuide = false;        // the guide shows above the findings (header menu); with no report at all it is the whole view
let dfmFor = null;           // the project the state below belongs to
let dfmZip = null;           // the Gerber zip as it is on disk ({exists, files, missing, ...}); null until asked
let dfmZipBusy = false;      // the zip is being made
let dfmZipErr = '';          // why it could not be made
let dfmZipAsked = false, dfmZipTried = null, dfmZipLoading = false;
let dfmLooking = false;      // "Find my report" is running; the look when the window regains focus stays silent
let dfmFindBusy = false, dfmFindAt = 0;
let dfmPending = [];         // reports found whose header does not say what they cover: [{name, bytes, arrived}]
let dfmFolder = '';          // the Downloads folder the last look used
const DFM_JLC = 'https://jlcdfm.com';
const DFM_FOCUS_MS = 4000;   // the look on focus runs at most this often

const dfmVerdict = r => {
  const v = String((r && r.verdict) || 'unknown').toLowerCase();
  return DFM_VERDICTS.some(x => x[0] === v) ? v : 'unknown';
};
const dfmReport = stem => (S.checks || []).find(c => c.stem === stem);
const dfmVisible = () => typeof mainView === 'function' && (mainView() === 'checks' || sideView() === 'checks');
function dfmRepaint() {           // never rebuilds a field the user is typing in (renderCenter checks the focus)
  if (dfmVisible()) renderCenter();
  if (typeof renderNav === 'function') renderNav();
}
function dfmFail(err) {           // api() has toasted the reasons the server gave; a lost connection has none
  if (err instanceof TypeError) toast("Couldn't reach the app. Check that it is still running.");
}

/* ---------- loading: once per report, and again when the agent or a script changes a table ---------- */
async function dfmFetchTriage(stem) {
  triageLoading[stem] = true;
  dfmTried['t:' + stem] = true;
  try {
    const r = await api('/api/checks/triage?stem=' + encodeURIComponent(stem), undefined, {soft: true});
    if (r && Array.isArray(r.triage)) { triageMap[stem] = r.triage; dfmSig[stem] = r.sig || ''; delete dfmErr['t:' + stem]; }
    else dfmErr['t:' + stem] = (r && r.error) || 'no answer';
  } catch (err) { dfmErr['t:' + stem] = err.message || 'no answer'; }
  triageLoading[stem] = false;
  dfmRepaint();
}
async function dfmFetchIndex(stem) {
  indexLoading[stem] = true;
  dfmTried['i:' + stem] = true;
  try {
    const r = await api('/api/checks/index?stem=' + encodeURIComponent(stem), undefined, {soft: true});
    if (r && !r.error) { indexMap[stem] = r; delete dfmErr['i:' + stem]; }
    else dfmErr['i:' + stem] = (r && r.error) || 'no answer';
  } catch (err) { dfmErr['i:' + stem] = err.message || 'no answer'; }
  indexLoading[stem] = false;
  dfmRepaint();
}
// called when the view is drawn; every request is guarded, so drawing again asks for nothing twice
function dfmSync() {
  for (const c of S.checks || []) {
    const st = c.stem, have = triageMap[st];
    if (have && !dfmSig[st]) dfmSig[st] = c.triage_sig || '';        // the nav loaded it: take it as current
    else if (have && c.triage_sig && c.triage_sig !== dfmSig[st] && c.triage_sig !== dfmSeen[st] && !dfmSaving[st]) dfmFetchTriage(st);   // changed from outside
    dfmSeen[st] = c.triage_sig;
    if (!have && !triageLoading[st] && !dfmTried['t:' + st]) dfmFetchTriage(st);
  }
  const shown = dfmSeg === 'smt' ? curSmtCheckStem : curPcbCheckStem;
  if (shown && !indexMap[shown] && !indexLoading[shown] && !dfmTried['i:' + shown]) dfmFetchIndex(shown);
}

/* ---------- saving: silent; the table is saved whole, in order, and a failed save loads the table again ---------- */
function dfmSave(stem) {
  dfmSaving[stem] = (dfmSaving[stem] || 0) + 1;
  const run = () => api('/api/checks/triage', {stem, rows: triageMap[stem]});
  const p = (dfmQueue[stem] || Promise.resolve()).then(run, run);
  dfmQueue[stem] = p.catch(() => {});
  return p.then(r => { if (r && r.sig) dfmSig[stem] = r.sig; return r; }).finally(() => { dfmSaving[stem]--; });
}
async function dfmSaveOrReload(stem) {
  try { await dfmSave(stem); return true; }
  catch (err) { dfmFail(err); dfmFetchTriage(stem); return false; }
}
function dfmSaved(field) {        // a small "Saved" beside the field for two seconds
  const mark = field.closest('.field') && field.closest('.field').querySelector('.saved');
  if (!mark) return;
  mark.textContent = 'Saved';
  clearTimeout(mark._t);
  mark._t = setTimeout(() => { mark.textContent = ''; }, 2000);
}

/* ---------- the numbers ---------- */
// across every report once (a 'both' report is one report): a table that is loaded counts from its rows, else from the state
function dfmTotals() {
  let n = 0, open = 0, real = 0, known = true;
  for (const c of S.checks || []) {
    const rows = triageMap[c.stem];
    if (rows) {
      n += rows.length;
      for (const r of rows) { const v = dfmVerdict(r); if (v === 'unknown') open++; else if (v === 'real') real++; }
    } else if (c.triage_open != null) { n += c.triage_count || 0; open += c.triage_open; real += c.triage_real || 0; }
    else known = false;
  }
  return {n, open, real, known};
}
function dfmHeader(reports) {
  if (!reports) return viewHeader({title: 'DFM'});
  const t = dfmTotals();
  const unv = dfmUnverified().length;
  const ready = t.known && t.n > 0 && !t.open && !t.real && !unv;     // reports alone do not make a board ready: every finding is judged
  const meta = metaLine([
    {n: t.n, label: t.n === 1 ? 'finding' : 'findings'},
    {n: t.open, label: 'to review', tone: 'warn', title: 'Findings nobody has judged yet'},
    {n: t.real, label: t.real === 1 ? 'real issue' : 'real issues', tone: 'bad', title: 'Findings that need a change on the board'},
    {n: unv, label: 'unverified', tone: 'warn', title: 'Parts whose pins came from the agent, not a datasheet'},
    ready && {always: true, label: 'Ready to order', tone: 'ok', title: 'Every finding is judged and none is a real issue'},
    t.known && !t.n && {always: true, label: 'No findings listed yet', title: 'Add the findings of the report, or ask the agent to list them'},
  ]);
  const more = menu({icon: 'more', title: 'More'}, [{label: dfmGuide ? 'Hide how to check at JLC' : 'How to check at JLC', act: 'dfm-guide'}]);
  return viewHeader({title: 'DFM', meta, actions: more, primary: dfmUpload({kind: 'pri'})});
}
// Parts placed with pins from the agent: the one place the missing datasheet blocks. Resolved by a verified datasheet or an explicit accept.
function dfmUnverified() {
  return (S.bom || []).filter(l => (l.refs || []).length && !l.dnp && !l.nobuy && (l.pins_status === 'unverified' || l.pins_status === 'mismatch'));
}
function dfmUnverifiedHTML() {
  const rows = dfmUnverified();
  if (!rows.length) return '';
  const item = l => `<li class="unv-row"><span class="m">${esc(refsLabel(l.refs))}</span> ${esc(l.mpn || l.value || '')}
    <span class="unv-why">${l.pins_status === 'mismatch' ? 'Pins conflict with the datasheet: ' + esc(l.pins_issues || '') : 'Pins from the agent; add the datasheet to verify'}</span>
    ${btn('Accept as is', {kind: 'line', size: 'sm', act: 'accept-pins', line: l.key, title: 'You checked these pins yourself'})}</li>`;
  return `<section class="dfm-unv"><h3>Unverified parts <span class="m">(${rows.length}) to resolve before ordering</span></h3>
    <p class="m">Drop each datasheet in Sources and re-check, or accept the pins as is.</p>
    <ul>${rows.map(item).join('')}</ul>${btn('Re-check datasheets', {kind: 'line', size: 'sm', act: 'recheck-pins'})}</section>`;
}
onAct('accept-pins', async (el, d) => { await api('/api/pins/accept', {line: d.line}); await refresh(true); });
onAct('recheck-pins', async () => { await api('/api/final/unverified'); await refresh(true); });
function dfmUpload(trigger) {
  if (dfmBusy || dfmLooking) return btn(dfmLooking ? 'Looking…' : 'Uploading…', {kind: trigger.kind, disabled: true});
  return menu(Object.assign({label: 'Upload report', icon: 'upload', iconAfter: 'chev', title: 'Add the PDF report from jlcdfm.com'}, trigger), [
    {label: 'Find my report', hint: 'in Downloads', act: 'dfm-find'},
    'sep',
    {group: 'From a file'},
    {label: 'Bare board', act: 'upload-dfm', attrs: {kind: 'pcb'}},
    {label: 'Assembly', act: 'upload-dfm', attrs: {kind: 'smt'}},
    {label: 'Both in one report', act: 'upload-dfm', attrs: {kind: 'both'}},
  ]);
}

/* ---------- the guide: four steps, the zip, the report ---------- */
function dfmProjectGuard() {       // the zip and the pending reports belong to one project
  if (dfmFor === PROJECT) return;
  dfmFor = PROJECT; dfmZip = null; dfmZipErr = ''; dfmZipAsked = false; dfmZipTried = null; dfmPending = []; dfmFolder = ''; dfmGuide = false;
}
function dfmZipSet(r) { dfmZip = r; dfmZipErr = ''; dfmZipAsked = true; }
async function dfmZipLoad() {
  const p = PROJECT;
  dfmZipLoading = true;
  try {
    const r = await api('/api/jlc/gerber-zip', undefined, {soft: true});
    if (p === PROJECT) dfmZip = r && !r.error ? r : {exists: false};
  } catch (err) { if (p === PROJECT) dfmZip = {exists: false}; }
  dfmZipLoading = false;
  dfmRepaint();
}
// the zip step shows the zip as it is on disk: asked once, and again when its file changes (the agent can make it too)
function dfmZipSync() {
  const ex = (S.exports || []).find(f => /_gerbers\.zip$/i.test(f.name));
  const mark = ex ? ex.modified || ex.name : '';
  if (dfmZipLoading || (dfmZipAsked && mark === dfmZipTried)) return;
  dfmZipTried = mark; dfmZipAsked = true;
  dfmZipLoad();
}
// builds the zip from the Altium outputs; the one place that does it (the guide and Outputs > Export). Returns the result or null.
async function dfmMakeZip() {
  if (dfmZipBusy) return null;
  const p = PROJECT;
  dfmZipBusy = true; dfmZipErr = '';
  if (dfmVisible()) renderCenter(true);
  let r = null;
  try { r = await api('/api/jlc/gerber-zip', {}, {soft: true}); } catch (err) { dfmFail(err); }
  dfmZipBusy = false;
  if (p !== PROJECT) return null;
  if (r && !r.error) { dfmZipSet(r); await refresh(true); }
  else dfmZipErr = (r && r.error) || 'no answer';
  if (dfmVisible()) renderCenter(true);
  return r && !r.error ? r : null;
}
const dfmNames = names => `<p class="dfm-files">${names.map(n => `<span class="m">${esc(n)}</span>`).join(' ')}</p>`;
function dfmZipBody() {
  if (dfmZipBusy) return loadingLine('Reading your Altium outputs');
  const err = dfmZipErr ? errorLine('make the zip', dfmZipErr) : '';
  const z = dfmZip;
  if (!z) return err || loadingLine('Looking for the zip');
  if (!z.exists) return err || '<p>Writes one zip with the newest Gerber and NC drill files of your Altium project. Altium\'s own folder is only read.</p>';
  const gaps = z.missing || [], problems = gaps.filter(m => m.level === 'problem'), notes = gaps.filter(m => m.level !== 'problem');
  const url = `/api/export/${encodeURIComponent(z.zip)}?${q()}`;
  let out = err;
  out += `<p class="dfm-zip"><span class="m">${esc(z.zip)}</span><span>${(z.files || []).length} files, written <time datetime="${esc(z.generated)}" title="${esc(outFull(z.generated))}">${esc(outAgo(z.generated))}</time></span>` +
    `<a class="btn icon sm" href="${esc(url)}" download="${esc(z.zip)}" title="Download ${esc(z.zip)}" aria-label="Download ${esc(z.zip)}">${icon('download')}</a></p>`;
  out += dfmNames((z.files || []).map(f => f.name));
  out += problems.map(m => `<div class="note warn"><span><b>${esc(m.layer)}</b> (<span class="m">${esc(m.ext)}</span>) is missing. ${esc(m.why)}</span></div>`).join('');
  out += (z.warnings || []).map(w => `<div class="note warn"><span>${esc(w)}</span></div>`).join('');
  if (notes.length) out += `<p class="muted">${notes.map(m => `${esc(m.layer)} (<span class="m">${esc(m.ext)}</span>) is not in the set. ${esc(m.why)}`).join(' ')}</p>`;
  const a = z.assembly || {};
  out += a.bom && a.cpl
    ? `<p>For assembly, also upload <span class="m">${esc(a.bom)}</span> and <span class="m">${esc(a.cpl)}</span> (Outputs).</p>`
    : '<p>For assembly you also need the BOM and the pick and place file. Export them from Outputs.</p>';
  return out;
}
const dfmStep = (title, actions, body) => `<li class="dfm-step"><div class="dfm-step-h"><h3>${esc(title)}</h3>${actions ? `<div class="acts">${actions}</div>` : ''}</div>` +
  `${body ? `<div class="dfm-step-b">${body}</div>` : ''}</li>`;
function dfmGuideHTML(empty) {
  dfmZipSync();
  const folder = dfmFolder ? `<span class="m">${esc(dfmFolder)}</span>` : 'your Downloads folder';
  const zipBtn = btn(dfmZip && dfmZip.exists ? 'Make it again' : 'Get the zip', {kind: 'line', size: 'sm', act: 'dfm-zip', disabled: dfmZipBusy});
  const steps = [
    dfmStep('Get the Gerber zip', zipBtn, dfmZipBody()),
    dfmStep('Open jlcdfm.com and sign in', `<a class="btn line sm" href="${DFM_JLC}" target="_blank" rel="noopener"><span>Open jlcdfm.com</span>${icon('ext', 's')}</a>`,
      '<p>Use your own JLCPCB account. The advisor never asks for your password.</p>'),
    dfmStep('Upload and run the checks', '', '<p>Upload the zip and run PCB DFM. For assembly, also run SMT DFM with the BOM and CPL. Then export the PDF report.</p>'),
    dfmStep('Find my report', btn('Find my report', {kind: 'line', size: 'sm', act: 'dfm-find', disabled: dfmLooking}),
      `<p>Save the PDF in ${folder}. The advisor looks there when you come back to this window.</p>`),
  ];
  const ask = btn('Ask', {kind: 'line', size: 'sm', icon: 'chat', act: 'ask-jlc-upload', title: 'Ask the agent to walk you through the upload'});
  const hide = empty ? '' : btn('Hide', {kind: 'line', size: 'sm', act: 'dfm-guide'});
  const lead = empty ? '<p class="dfm-lead">No report yet. The advisor prepares the files and picks up the report; you sign in and upload at JLC.</p>' : '';
  return section('How to check at JLC', `${lead}<ol class="dfm-steps">${steps.join('')}</ol>`, {id: 'dfm-guide', actions: ask + hide});
}
function dfmPendingHTML() {        // a report whose header does not say what it covers: ask, never guess
  return dfmPending.map(p => `<div class="note"><span><span class="m">${esc(p.name)}</span> is in Downloads. What does it cover?</span><span class="acts">` +
    [['pcb', 'Bare board'], ['smt', 'Assembly'], ['both', 'Both']].map(([k, l]) => btn(l, {kind: 'line', size: 'sm', act: 'dfm-kind', 'data-kind': k, 'data-file': p.name})).join('') +
    '</span></div>').join('');
}

/* ---------- findings ---------- */
function dfmLevel(r) {            // the report's level as a dot: danger is bad, warning is warn, good is ok, anything else says nothing
  const l = String(r.level || '').toLowerCase();
  if (l === 'danger') return ['bad', 'Danger'];
  if (l === 'warning') return ['warn', 'Warning'];
  if (l === 'good') return ['ok', 'Good'];
  return ['none', r.level ? String(r.level) : 'Info'];
}
// the findings of a report that belong in a segment: a 'both' report holds the bare board and the assembly analyses
// (sections 'PCB DFM>...' and 'SMT DFM>...'), the others are one kind
function dfmRows(stem, segKind) {
  const c = dfmReport(stem), both = !!c && c.kind === 'both';
  return (triageMap[stem] || []).map((r, i) => ({r, i})).filter(({r}) => !both || (/^\s*smt\b/i.test(r.section || '') ? segKind === 'smt' : segKind === 'pcb'));
}
function dfmField(label, field, stem, i, value, hint) {
  return `<label class="field"><span>${esc(label)}<small class="saved" aria-live="polite"></small></span>
    <textarea class="in quiet" rows="2" dir="auto" data-triage-field="${field}" data-stem="${esc(stem)}" data-idx="${i}" placeholder="${esc(hint)}">${esc(value || '')}</textarea></label>`;
}
function dfmDetailRow(stem, i) {
  const r = (triageMap[stem] || [])[i];
  if (!r) return '';
  const facts = [r.worst && !/^(null|—|-)$/.test(r.worst) ? `Worst ${r.worst}` : '', r.level ? `Level ${String(r.level).toLowerCase()}` : ''].filter(Boolean).join(' · ');
  return `<tr class="dfm-x"><td></td><td colspan="7"><div class="dfm-xb">
    ${dfmField('Fix', 'fix', stem, i, r.fix, 'What to change, or why nothing needs to')}
    ${dfmField('Evidence', 'evidence', stem, i, r.evidence, 'What you checked: slice, crop, designator')}
    <div class="dfm-xf"><span>${esc(facts)}</span>${btn('Remove finding', {kind: 'danger', size: 'sm', icon: 'trash', act: 'del-triage-row', stem, idx: i})}</div>
  </div></td></tr>`;
}
function dfmRow(stem, x) {
  const {r, i} = x, v = dfmVerdict(r), open = dfmOpen === stem + '|' + i;
  const [tone, level] = dfmLevel(r), name = r.check || 'Check ' + (i + 1);
  const count = (n, cls) => `<td class="num${cls ? ' ' + cls : ''}${n ? '' : ' z'}">${num(n || 0)}</td>`;
  const opts = DFM_VERDICTS.map(([val, label, tip]) => `<option value="${esc(val)}" title="${esc(tip)}"${v === val ? ' selected' : ''}>${esc(label)}</option>`).join('');
  return `<tr class="dfm-r${open ? ' open' : ''}${v === 'model' || v === 'by design' ? ' done' : ''}" data-stem="${esc(stem)}" data-idx="${i}" tabindex="0" aria-expanded="${open}">
    <td class="lv">${dot(tone, `${level} in the report`)}</td>
    <td class="ck"><span class="main">${esc(name)}</span></td>
    <td class="ly c-layer" title="${esc(r.layer || '')}">${esc(r.layer || '')}</td>
    ${count(r.danger)}${count(r.warning, 'c-warn')}<td class="num c-good${r.good ? '' : ' z'}">${num(r.good || 0)}</td>
    <td><select class="in quiet dfm-v ${DFM_VCLASS[v]}" data-triage-field="verdict" data-stem="${esc(stem)}" data-idx="${i}" aria-label="Verdict for ${esc(name)}">${opts}</select></td>
    <td class="c-ask"><div class="row-acts">${btn('', {icon: 'chat', size: 'sm', title: `Ask about ${name}`, act: 'ask-dfm', stem, check: name})}</div></td></tr>${open ? dfmDetailRow(stem, i) : ''}`;
}
function dfmFindings(stem, segKind) {
  if (!triageMap[stem]) {
    return dfmErr['t:' + stem] ? errorLine('load the findings', dfmErr['t:' + stem], btn('Retry', {size: 'sm', act: 'dfm-retry', stem})) : loadingLine('Loading findings');
  }
  const list = dfmRows(stem, segKind), groups = [];
  for (const x of list) {
    const s = x.r.section || '';
    let g = groups.find(h => h.s === s);
    if (!g) groups.push(g = {s, rows: []});
    g.rows.push(x);
  }
  const add = btn('Add finding', {icon: 'plus', size: 'sm', act: 'add-triage-row', stem, 'data-kind': segKind});
  if (!list.length) {
    return `<p class="muted dfm-none">Nothing is listed for this report yet.</p><div class="acts dfm-end">${add}${btn('Ask the agent to list them', {size: 'sm', act: 'ask-dfm-report', stem})}</div>`;
  }
  const head = s => esc(s.includes('>') ? s.slice(s.indexOf('>') + 1).trim() : s || 'Other');     // 'PCB DFM>Routing layer analysis'
  return `<table class="tbl rows dfm-tbl"><thead><tr><th class="lv"><span class="sr">Level</span></th><th class="ck-h">Check</th><th class="c-layer">Layer</th>
      <th class="num">Danger</th><th class="num c-warn">Warning</th><th class="num c-good">Good</th><th>Verdict</th><th class="c-ask"><span class="sr">Actions</span></th></tr></thead>
    <tbody>${groups.map(g => `<tr class="grp"><td colspan="8" title="${esc(g.s)}">${head(g.s)}<span class="n">${g.rows.length}</span></td></tr>${g.rows.map(x => dfmRow(stem, x)).join('')}`).join('')}</tbody></table>
    <div class="acts dfm-end">${add}</div>`;
}

/* ---------- slices ---------- */
function dfmSlices(stem) {
  const idx = indexMap[stem];
  if (!idx) return dfmErr['i:' + stem] ? errorLine('load the report slices', dfmErr['i:' + stem], btn('Retry', {size: 'sm', act: 'dfm-retry', stem})) : loadingLine('Loading slices');
  const files = (idx.slices || []).map(s => (typeof s === 'string' ? s : s && s.file) || '').filter(Boolean);
  if (!files.length) return '';
  const url = f => `/api/checks/slice?stem=${encodeURIComponent(stem)}&slice=${encodeURIComponent(f)}&${q()}`;
  return section('Report slices', `<div class="dfm-strip">${files.map((f, n) =>
    `<button type="button" class="dfm-th" data-act="view-slice" data-stem="${esc(stem)}" data-slice="${esc(f)}" title="Open slice ${n + 1} beside the findings" aria-label="Open slice ${n + 1}">
      <img src="${esc(url(f))}" alt="" loading="lazy"><span class="num">${n + 1}</span></button>`).join('')}</div>`);
}

function checksHTML(container) {
  const checks = S.checks || [];
  // one JLCDFM report can cover the bare board and the assembly (kind 'both'): it is listed in either segment
  const pcbChecks = checks.filter(c => ['pcb', 'both'].includes(c.kind || 'pcb'));
  const smtChecks = checks.filter(c => ['smt', 'both'].includes(c.kind));

  if (!curPcbCheckStem && pcbChecks.length) curPcbCheckStem = pcbChecks[0].stem;
  if (!curSmtCheckStem && smtChecks.length) curSmtCheckStem = smtChecks[0].stem;
  if (curPcbCheckStem && !pcbChecks.some(c => c.stem === curPcbCheckStem)) {
    curPcbCheckStem = pcbChecks.length ? pcbChecks[0].stem : null;
  }
  if (curSmtCheckStem && !smtChecks.some(c => c.stem === curSmtCheckStem)) {
    curSmtCheckStem = smtChecks.length ? smtChecks[0].stem : null;
  }
  if (!dfmSegUser && !pcbChecks.length && smtChecks.length) dfmSeg = 'smt';    // only an assembly report so far

  dfmProjectGuard();
  if (!checks.length) {          // nothing to review yet: the view is the guide to getting a report
    return `${viewHeader({title: 'DFM', primary: dfmUpload({kind: 'pri'})})}<div class="vb dfm-vb">${dfmUnverifiedHTML()}${dfmPendingHTML()}${dfmGuideHTML(true)}</div>`;
  }
  dfmSync();

  const kind = dfmSeg === 'smt' ? 'smt' : 'pcb';
  const list = kind === 'smt' ? smtChecks : pcbChecks;
  const stem = kind === 'smt' ? curSmtCheckStem : curPcbCheckStem;
  const cur = list.find(c => c.stem === stem);
  const picker = list.length > 1
    ? `<select class="in quiet check-stem-select" data-kind="${kind}" aria-label="Report">${list.map(c => `<option value="${esc(c.stem)}"${c.stem === stem ? ' selected' : ''}>${esc(c.stem)}</option>`).join('')}</select>`
    : (cur ? `<span class="m dfm-rep" title="${esc(cur.original_name || cur.stem)}">${esc(cur.stem)}</span>` : '');
  let body;
  if (!cur) {
    body = emptyState(`No ${kind === 'smt' ? 'assembly' : 'bare board'} report yet`,
      `Upload the ${kind === 'smt' ? 'assembly' : 'bare board'} report from jlcdfm.com, or one report that covers both.`,
      dfmBusy ? '' : btn(`Upload ${kind === 'smt' ? 'assembly' : 'bare board'} report`, {kind: 'line', act: 'upload-dfm', 'data-kind': kind}));
  } else {
    body = dfmFindings(stem, kind) + dfmSlices(stem);
  }
  return `${dfmHeader(checks.length)}<div class="vb dfm-vb">${dfmUnverifiedHTML()}${dfmPendingHTML()}${dfmGuide ? dfmGuideHTML(false) : ''}<div class="dfm-bar">${seg(DFM_SEGS, kind, {act: 'dfm-seg', label: 'Report type'})}${picker}</div>${body}</div>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('upload-dfm', async (el, d, e) => {
  uploadDfmKind = el.dataset.kind || d.kind || 'pcb';
  $('#dfmpick').click();
  return;
});
onAct('dfm-seg', async (el, d) => {
  dfmSeg = d.value === 'smt' ? 'smt' : 'pcb';
  dfmSegUser = true;
  dfmOpen = '';
  renderCenter(true);
});
onAct('dfm-retry', async (el, d) => {
  for (const k of ['t:', 'i:']) { delete dfmTried[k + d.stem]; delete dfmErr[k + d.stem]; }
  delete indexMap[d.stem];
  renderCenter(true);
});
onAct('view-slice', async (el, d, e) => {
  openFileAsTab({name: d.slice, path: d.stem + '/' + d.slice, stem: d.stem, slice: d.slice, fileType: 'dfm'});
  return;
});
onAct('ask-dfm', async (el, d, e) => {
  askAbout({kind: 'dfm', id: d.stem + ':' + d.check, label: d.check});
  return;
});
onAct('ask-dfm-report', async (el, d, e) => {
  askAbout({kind: 'dfm', id: d.stem, label: d.stem, text: 'List the findings of this report in the DFM table, then tell me which ones look real.'});
  return;
});
onAct('ask-jlc-upload', async (el, d, e) => {
  askAbout({kind: 'dfm', id: 'jlc-upload', label: 'JLC upload', text: 'Walk me through the JLC DFM upload'});
  return;
});
onAct('dfm-guide', async (el, d, e) => {
  dfmGuide = !dfmGuide;
  renderCenter(true);
  return;
});
onAct('dfm-zip', async (el, d, e) => {
  await dfmMakeZip();
  return;
});
onAct('dfm-find', async (el, d, e) => {
  await dfmFindReports(true);
  return;
});
onAct('dfm-kind', async (el, d, e) => {           // the answer to "what does it cover?" for a report the header did not settle
  await dfmFindReports(true, {name: d.file, kind: d.kind});
  return;
});
onAct('add-triage-row', async (el, d, e) => {
  const stem = d.stem || dfmStemFor(d.kind);
  if (!stem || !triageMap[stem]) return;
  const kind = d.kind === 'smt' ? 'smt' : 'pcb';
  const name = await askText({title: 'Add finding', label: 'Check name', placeholder: kind === 'smt' ? 'Pin outer edge' : 'Silkscreen to pad', confirm: 'Add'});
  if (!name) return;
  const rows = triageMap[stem];
  const section = (dfmRows(stem, kind).slice(-1)[0] || {r: {}}).r.section || (kind === 'smt' ? 'SMT DFM>Component assembly analysis' : 'PCB DFM>Routing layer analysis');
  rows.push({section, check: name, worst: '', level: 'Info', danger: 0, warning: 0, good: 0, layer: '', verdict: 'unknown', fix: '', evidence: ''});
  dfmOpen = stem + '|' + (rows.length - 1);
  renderCenter(true);
  const fix = $(`textarea[data-triage-field="fix"][data-stem="${CSS.escape(stem)}"][data-idx="${rows.length - 1}"]`);
  if (fix) { fix.focus({preventScroll: true}); fix.scrollIntoView({block: 'nearest'}); }
  await dfmSaveOrReload(stem);
  return;
});
onAct('del-triage-row', async (el, d, e) => {
  const stem = d.stem || dfmStemFor(d.kind);
  const idx = parseInt(d.idx, 10);
  if (!stem || isNaN(idx) || !triageMap[stem] || !triageMap[stem][idx]) return;
  const [gone] = triageMap[stem].splice(idx, 1);
  dfmOpen = '';
  renderCenter(true);
  if (!await dfmSaveOrReload(stem)) return;
  toast(`Removed ${gone.check || 'the finding'}`, {label: 'Undo', onClick: async () => {
    const rows = triageMap[stem] || (triageMap[stem] = []);
    rows.splice(Math.min(idx, rows.length), 0, gone);
    renderCenter(true);
    await dfmSaveOrReload(stem);
  }});
  return;
});

onChange(t => t.id === 'dfmpick', async e => {
  const f = e.target.files[0]; if (!f) return;
  const kind = uploadDfmKind || 'pcb';
  dfmBusy = true;
  renderCenter(true);
  try {
    const buf = new Uint8Array(await f.arrayBuffer()); let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    const r = await api('/api/checks/upload', {name: f.name, data_b64: btoa(bin), kind: kind});
    dfmAdopt([{stem: r.stem, kind}]);
  } catch (err) { dfmFail(err); }
  dfmBusy = false;
  e.target.value = '';
  await refresh(true);
  return;
});
/* ---------- a report that came in (uploaded, or found in Downloads): show it, then keep looking when the student comes back ---------- */
function dfmAdopt(found) {
  for (const f of found) {
    for (const k of ['t:', 'i:']) { delete dfmTried[k + f.stem]; delete dfmErr[k + f.stem]; }
    delete indexMap[f.stem]; delete triageMap[f.stem]; delete dfmSig[f.stem];
    if (f.kind !== 'smt') curPcbCheckStem = f.stem;
    if (f.kind !== 'pcb') curSmtCheckStem = f.stem;
  }
  const last = found[found.length - 1];
  if (last && last.kind !== 'both') { dfmSeg = last.kind; dfmSegUser = true; }
  dfmOpen = '';
}
// pick = {name, kind} adds that one file of Downloads; with nothing, the reports that arrived since the last one.
// manual: the student asked, so an empty result is said; the look on focus stays quiet unless it finds something.
async function dfmFindReports(manual, pick) {
  if (dfmFindBusy) return;
  const p = PROJECT;
  dfmFindBusy = true; dfmFindAt = Date.now();
  if (manual) { dfmLooking = true; if (dfmVisible()) renderCenter(true); }
  let r = null;
  try { r = await api('/api/jlc/pickup', pick || {}, {soft: true}); } catch (err) { if (manual) dfmFail(err); }
  dfmFindBusy = false; dfmLooking = false;
  if (p !== PROJECT) return;
  if (!r || r.error) {
    if (manual && r) toast(r.error, null, {bad: true});
    if (dfmVisible()) renderCenter(true);
    return;
  }
  if (r.folder) dfmFolder = r.folder;
  const pending = JSON.stringify(dfmPending);
  const handled = new Set([...(r.pending || []), ...(r.found || []), ...(r.skipped || [])].map(x => x.name));
  if (pick) handled.add(pick.name);                  // asked about by name: answered, or gone
  // a report waits for its answer even when a later look no longer lists it (it is older than the report added meanwhile)
  dfmPending = (r.pending || []).concat(dfmPending.filter(x => !handled.has(x.name)));
  const found = r.found || [];
  if (found.length) {
    dfmAdopt(found);
    await refresh(true);
    toast(found.length === 1 ? `Found ${found[0].name}, added` : `Found ${found.length} reports, added`);
    return;
  }
  if (manual && !dfmPending.length) {
    const skipped = (r.skipped || []).find(s => !/already added/.test(s.reason));
    const older = r.older_files || [];
    if (!r.folder_exists) toast(`The folder ${r.folder} does not exist. Add the report from a file instead.`, null, {bad: true});
    else if (skipped) toast(`${skipped.name}: ${skipped.reason}`);
    else if ((r.skipped || []).length) toast('That report is already added.');
    else if (older.length) toast(`No new JLCDFM report in Downloads. ${older.length === 1 ? 'An older one is' : 'Older ones are'} there.`,
      {label: 'Add the newest', onClick: () => dfmFindReports(true, {name: older[0].name})});
    else toast('No new JLCDFM report in Downloads yet.');
  }
  if (pending !== JSON.stringify(dfmPending) || manual) { if (dfmVisible()) renderCenter(true); }
}
function dfmLookOnFocus() {
  if (!dfmVisible() || document.hidden || Date.now() - dfmFindAt < DFM_FOCUS_MS) return;
  dfmFindReports(false);
}
addEventListener('focus', dfmLookOnFocus);
document.addEventListener('visibilitychange', dfmLookOnFocus);

onChange(t => t.classList.contains('check-stem-select') || t.id === 'check-stem-select', async e => {
  const kind = e.target.dataset.kind || 'pcb';
  if (kind === 'smt') curSmtCheckStem = e.target.value;
  else curPcbCheckStem = e.target.value;
  dfmOpen = '';
  renderCenter(true);
  return;
});
// a verdict, a fix or an evidence text: the triage row is changed and the table saved; no toast per change
onChange(t => t.closest && t.closest('[data-triage-field]'), async e => {
  const field = e.target.closest('[data-triage-field]');
  const stem = field.dataset.stem || dfmStemFor(field.dataset.kind);
  const idx = parseInt(field.dataset.idx, 10), name = field.dataset.triageField;
  const row = stem && triageMap[stem] && triageMap[stem][idx];
  if (!row || isNaN(idx) || row[name] === field.value) return;
  row[name] = field.value;
  if (name === 'verdict') {      // the counts in the header and the row's look follow the verdict at once; the select keeps the focus
    const again = `select[data-triage-field="verdict"][data-stem="${CSS.escape(stem)}"][data-idx="${idx}"]`;
    renderCenter(true);
    const n = $(again);
    if (n) n.focus({preventScroll: true});
    renderNav();
    await dfmSaveOrReload(stem);
    return;
  }
  if (await dfmSaveOrReload(stem)) dfmSaved(field);
});

/* ---------- a finding opens and closes in place: its fix and evidence; the row is a keyboard stop ---------- */
function dfmToggle(tr) {
  const stem = tr.dataset.stem, idx = parseInt(tr.dataset.idx, 10), key = stem + '|' + idx, was = dfmOpen === key;
  const body = tr.parentElement;
  body.querySelectorAll('tr.dfm-x').forEach(x => x.remove());
  body.querySelectorAll('tr.dfm-r.open').forEach(r => { r.classList.remove('open'); r.setAttribute('aria-expanded', 'false'); });
  dfmOpen = was ? '' : key;
  if (!was) {
    tr.classList.add('open');
    tr.setAttribute('aria-expanded', 'true');
    tr.insertAdjacentHTML('afterend', dfmDetailRow(stem, idx));
  }
}
document.addEventListener('click', e => {
  const tr = e.target.closest && e.target.closest('.dfm-tbl tr.dfm-r');
  if (tr && !e.target.closest('button, a, select, input, textarea, label')) dfmToggle(tr);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && e.target.closest && e.target.closest('.dfm-tbl tr.dfm-x') && dfmOpen) {      // Esc inside an open finding closes it
    const open = e.target.closest('tbody').querySelector('tr.dfm-r.open');
    if (!open) return;
    e.preventDefault();
    if (e.target.blur) e.target.blur();                  // a text that was just typed is saved by its change event
    dfmToggle(open);
    open.focus();
    return;
  }
  const tr = e.target.closest && e.target.closest('.dfm-tbl tr.dfm-r');
  if (!tr || e.target !== tr) return;
  if (e.key === 'Escape' && dfmOpen && tr.classList.contains('open')) { e.preventDefault(); dfmToggle(tr); return; }
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dfmToggle(tr); return; }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const rows = [...tr.closest('tbody').querySelectorAll('tr.dfm-r')], next = rows[rows.indexOf(tr) + (e.key === 'ArrowDown' ? 1 : -1)];
  if (next) { e.preventDefault(); next.focus(); }
});
