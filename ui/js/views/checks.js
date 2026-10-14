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

const dfmPl = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
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
  const ready = t.known && t.n > 0 && !t.open && !t.real;     // reports alone do not make a board ready: every finding is judged
  const meta = metaLine([
    {n: t.n, label: t.n === 1 ? 'finding' : 'findings'},
    {n: t.open, label: 'to review', tone: 'warn', title: 'Findings nobody has judged yet'},
    {n: t.real, label: t.real === 1 ? 'real issue' : 'real issues', tone: 'bad', title: 'Findings that need a change on the board'},
    ready && {always: true, label: 'Ready to order', tone: 'ok', title: 'Every finding is judged and none is a real issue'},
    t.known && !t.n && {always: true, label: 'No findings listed yet', title: 'Add the findings of the report, or ask the agent to list them'},
  ]);
  return viewHeader({title: 'DFM', meta, primary: dfmUpload({kind: 'pri'})});
}
function dfmUpload(trigger) {
  if (dfmBusy) return btn('Uploading…', {kind: trigger.kind, disabled: true});
  return menu(Object.assign({label: 'Upload report', icon: 'upload', iconAfter: 'chev', title: 'Upload the PDF report from jlcdfm.com'}, trigger), [
    {label: 'Bare board', act: 'upload-dfm', attrs: {kind: 'pcb'}},
    {label: 'Assembly', act: 'upload-dfm', attrs: {kind: 'smt'}},
    {label: 'Both in one report', act: 'upload-dfm', attrs: {kind: 'both'}},
  ]);
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
  if (!curCheckStem && checks.length) {
    curCheckStem = curPcbCheckStem || curSmtCheckStem || checks[0].stem;
  }
  if (!dfmSegUser && !pcbChecks.length && smtChecks.length) dfmSeg = 'smt';    // only an assembly report so far

  if (!checks.length) {
    return viewHeader({title: 'DFM'}) + emptyState('No DFM report yet', 'Upload the PDF report from jlcdfm.com (bare board, assembly, or both).',
      dfmUpload({kind: 'pri'}) + '<a class="btn link" href="https://jlcdfm.com" target="_blank" rel="noopener">Open jlcdfm.com</a>');
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
  return `${dfmHeader(checks.length)}<div class="vb dfm-vb"><div class="dfm-bar">${seg(DFM_SEGS, kind, {act: 'dfm-seg', label: 'Report type'})}${picker}</div>${body}</div>`;
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
onAct('add-triage-row', async (el, d, e) => {
  const stem = d.stem || (d.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
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
  const stem = d.stem || (d.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
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
    for (const k of ['t:', 'i:']) { delete dfmTried[k + r.stem]; delete dfmErr[k + r.stem]; }
    delete indexMap[r.stem]; delete triageMap[r.stem]; delete dfmSig[r.stem];
    if (kind !== 'smt') curPcbCheckStem = r.stem;
    if (kind !== 'pcb') curSmtCheckStem = r.stem;
    curCheckStem = r.stem;
    if (kind !== 'both') { dfmSeg = kind; dfmSegUser = true; }
    dfmOpen = '';
  } catch (err) { dfmFail(err); }
  dfmBusy = false;
  e.target.value = '';
  await refresh(true);
  return;
});
onChange(t => t.classList.contains('check-stem-select') || t.id === 'check-stem-select', async e => {
  const kind = e.target.dataset.kind || 'pcb';
  if (kind === 'smt') curSmtCheckStem = e.target.value;
  else curPcbCheckStem = e.target.value;
  curCheckStem = e.target.value;
  dfmOpen = '';
  renderCenter(true);
  return;
});
// a verdict, a fix or an evidence text: the triage row is changed and the table saved; no toast per change
onChange(t => t.closest && t.closest('[data-triage-field]'), async e => {
  const field = e.target.closest('[data-triage-field]');
  const stem = field.dataset.stem || (field.dataset.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
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
