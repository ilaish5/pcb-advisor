/* PCB Advisor UI - Library, Sources and Settings (Skills is a section of Settings; the old Skills page shows Settings
   scrolled to it). Sources has two scopes: Shared (general reference material every project sees) and Project (this
   project's own documents, including its parts' datasheets); "Add" always puts a document into the project.
   Settings saves each field on its own as it changes (debounced for text) and says "Saved" next to it for two seconds.
   Names here start with pg or set so they cannot clash with the other files in the shared script scope. */

const pgPl = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
const pgBase = p => String(p || '').split(/[\\/]/).pop();
const PG_LANGS = [['auto', 'Auto'], ['en', 'English'], ['he', '&#1506;&#1489;&#1512;&#1497;&#1514;']];   // labels are markup: the Hebrew name is an entity
const PG_RESTORE = 'python scripts/sources.py restore';
const PG_COURSE_LIB = 'course/ad20-essentials/m29-integrated-library.en.md';   // a general source: its name is its path under shared/reference

let srcUnmatched = [];                       // uploaded documents no part claimed yet: asked about in Sources
let srcFilter = 'all', srcBusy = '';        // Sources: which scope is shown, and what is being added right now
let libBusy = false;
let ALTIUM_ERR = null, altiumLoading = false, pgSkillsScrolled = false;
const pgOpen = {};                          // details that stay open across a redraw: {key: true}

/* ---------- Altium settings: loading, with an error that can be retried ---------- */
function pgShowsSettings() {
  return ['settings', 'skills'].includes(mainView()) || ['settings', 'skills'].includes(sideView());
}
async function loadAltium(force) {
  if (altiumLoading || (ALTIUM_ERR && !force)) return;
  altiumLoading = true;
  if (force) { ALTIUM_ERR = null; if (pgShowsSettings()) renderCenter(true); }
  try {
    const r = await api('/api/altium', undefined, {soft: true});
    if (!r || r.error) throw new Error((r && r.error) || 'no answer from the server');
    ALTIUM_DATA = r;
    ALTIUM_ERR = null;
  } catch (e) {
    ALTIUM_ERR = e.message || 'no answer from the server';
  }
  altiumLoading = false;
  if (pgShowsSettings()) renderCenter(true);
}
async function loadConfig() {
  try {
    CONFIG = await api('/api/config', undefined, {soft: true});
  } catch (e) {
    CONFIG = {error: e.message};
  }
  if (pgShowsSettings()) renderCenter(true);
}

/* ================================ Library ================================ */
const PG_LIB = {ok: ['Verified', 'ok'], review: ['To review', 'warn'], missing: ['Missing', 'bad']};

function libModels(r) {
  const one = (cls, ic, label, title) => `<span class="mdl ${cls}" title="${esc(title)}">${icon(ic, 's')}${esc(label)}</span>`;
  return `<div class="mdls">` +
    one(r.symbol ? 'ok' : 'no', r.symbol ? 'check' : 'x', 'Symbol', r.symbol ? 'Symbol is in the library' : 'No symbol yet') +
    one(r.footprint ? 'ok' : 'no', r.footprint ? 'check' : 'x', 'Footprint', r.footprint ? 'Footprint is in the library' : 'No footprint yet') +
    (r.step ? one('ok', 'check', '3D', '3D model from a STEP file') : one('dim', 'check', '3D simple', 'A simple 3D body, not a STEP model')) + '</div>';
}
/* One quiet action: Verify until the part has passed, then Accept. A part with no symbol has nothing to verify. */
function libAction(r) {
  if (r.verify === 'pass' && !r.accepted) return btn('Accept', {size: 'sm', accept: r.line, title: 'It passed the datasheet check. Accept it for the library.'});
  if (r.verify !== 'pass' && r.symbol) return btn('Verify', {size: 'sm', verify: r.line, title: 'Compare the pins with the datasheet'});
  return '';
}
function libRow(r) {
  const [text, tone] = PG_LIB[r.status] || [LIBTXT[r.status] || r.status, ''];
  const refs = r.refs || [];
  return `<tr data-key="${esc(r.line)}" tabindex="0" class="${sel === r.line ? 'sel' : ''}"${r.model_source ? ` title="${esc('Model from ' + r.model_source)}"` : ''}>
    <td title="${esc(refs.join(', '))}"><span class="ref">${esc(refsLabel(refs) || r.line)}</span>${r.mpn ? `<span class="sub m">${esc(r.mpn)}</span>` : ''}</td>
    <td>${libModels(r)}</td>
    <td>${tag(text, tone, r.issues || LIBTXT[r.status] || '')}</td>
    <td class="act">${libAction(r)}</td></tr>`;
}
/* shown after an export: how to get the package into Altium, and what is still unverified */
function libExportHTML() {
  if (!libExport) return '';
  const w = libExport.warnings || [];
  const course = srcByName(PG_COURSE_LIB);
  return `<details class="disc lib-how"><summary>How to install in Altium</summary><div class="lib-how-b">
    <ol><li>Unzip <span class="m">${esc(libExport.file)}</span>. Its <span class="m">library/</span> folder holds the SchLib, PcbLib and STEP files.</li>
    <li>In Altium, add them to an Integrated Library package and compile it. Compiling needs Altium on Windows.</li>
    <li>Open the Components panel menu, then File-based Libraries Preferences, Installed, Install, and pick the IntLib.</li></ol>
    ${course ? `<p class="muted">See ${chip(PG_COURSE_LIB, 'Module 29, Integrated Library')}</p>` : ''}
    ${w.length ? `<h3>Still unverified (${w.length})</h3><ul>${w.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div></details>`;
}
function libHTML(container) {
  const rows = S.library || [];
  const todo = rows.filter(r => r.status !== 'ok').length;
  const meta = metaLine([{n: rows.length, label: rows.length === 1 ? 'part' : 'parts'},
    {n: todo, label: 'to review', tone: 'warn', title: 'Parts that are not verified and accepted yet'}]);
  const primary = btn('Export IntLib', {kind: 'pri', act: 'libexport', disabled: !rows.length, title: 'Write the library package for Altium'});
  const body = rows.length
    ? `<div class="tbl-wrap"><table class="tbl rows lib-tbl"><thead><tr><th>Part</th><th>Models</th><th>Status</th><th><span class="sr">Action</span></th></tr></thead>
      <tbody>${rows.map(libRow).join('')}</tbody></table></div>`
    : emptyState('No library parts yet', 'Parts that are not in Altium\'s default libraries show up here with their symbol, footprint and 3D model.');
  return `${viewHeader({title: 'Library', meta, primary})}<div class="vb">${libExportHTML()}${body}</div>`;
}

/* ================================ Sources ================================ */
function srcTip(s) {
  return [s.name.includes('/') ? s.name : '', s.url ? 'Origin: ' + s.url : (s.origin ? 'Origin: ' + s.origin : ''), s.sha256 && s.sha256 !== '—' ? 'sha256 ' + s.sha256 : '', s.text ? 'Text extracted' : 'No extracted text']
    .filter(Boolean).join('\n');
}
// a general document is named by its path under shared/reference (the name a citation uses): the folders are shown quieter,
// and in a narrow sheet they give way first, so the file's own name stays readable
function srcLabel(name) {
  const cut = String(name).lastIndexOf('/') + 1;
  return (cut ? `<span class="dir">${esc(name.slice(0, cut))}</span>` : '') + `<span class="file">${esc(name.slice(cut))}</span>`;
}
function srcRow(s, showScope, cols) {
  const id = 'src-' + String(s.name).replace(/[^\w-]/g, '_');
  const name = s.present
    ? `<button type="button" class="src-name" data-src="${esc(s.name)}">${srcLabel(s.name)}</button>`
    : `<span class="src-name off">${srcLabel(s.name)}</span>${tag('Missing', 'warn', 'Not on this machine')}`;
  return `<tr id="${esc(id)}" class="${hitSrc === s.name ? 'flash' : ''}" title="${esc(srcTip(s))}">
    <td class="src-n"><div class="src-cell">${name}${showScope && s.scope === 'shared' ? tag('Shared', '', 'Shared with every project') : ''}</div></td>
    ${cols.type ? `<td class="muted">${esc(s.kind || '')}</td>` : ''}
    <td class="num">${esc(s.size)}</td>
    ${cols.used ? `<td class="muted">${s.used_for && s.used_for !== '—' ? esc(s.used_for) : ''}</td>` : ''}</tr>`;
}
function sourcesHTML(container) {
  const all = S.sources || [];
  const missing = all.filter(s => !s.present).length;
  const shown = all.filter(s => srcFilter === 'all' || s.scope === srcFilter);
  if (srcFilter === 'all') shown.sort((a, b) => (a.scope === b.scope ? 0 : a.scope === 'project' ? -1 : 1));   // this project's documents first
  const mine = all.filter(s => s.scope === 'project').length;
  const meta = metaLine([{n: mine, label: 'in this project'}, {n: all.length - mine, label: 'shared', title: 'General reference material every project sees'}, {n: missing, label: 'missing', tone: 'warn', title: 'Listed by a sidecar but not on this machine'}]);
  const actions = seg([{value: 'all', label: 'All'}, {value: 'shared', label: 'Shared', title: 'General reference material every project sees'},
    {value: 'project', label: 'Project', title: 'The documents of this project'}], srcFilter, {act: 'src-filter', label: 'Show'});
  const primary = menu({label: 'Add', kind: 'pri', icon: 'plus', iconAfter: 'chev'}, [
    {label: 'Upload file', icon: 'upload', act: 'upload'}, {label: 'From URL', icon: 'ext', act: 'addurl'}]);
  const note = missing
    ? `<div class="note warn"><span>${pgPl(missing, 'file')} missing. Run <code>${esc(PG_RESTORE)}</code>.</span><span class="acts">${btn('Copy', {size: 'sm', act: 'src-copy', title: 'Copy the command'})}</span></div>` : '';
  // a column that says the same thing on every row is left out: all PDFs need no Type, and no "used for" needs no column
  const cols = {type: shown.some(s => s.kind && s.kind !== 'PDF'), used: shown.some(s => s.used_for && s.used_for !== '—')};
  let body;
  if (!all.length) body = emptyState('No documents yet', 'Add a datasheet or a guide with Upload file or From URL. The agent can quote what is in here.');
  else if (!shown.length) body = `<p class="muted">${srcFilter === 'shared' ? 'No shared documents.' : 'This project has no documents of its own yet.'}</p>`;
  else body = `<div class="tbl-wrap"><table class="tbl dense rows src-tbl${cols.type || cols.used ? '' : ' slim'}"><thead><tr><th>Name</th>${cols.type ? '<th>Type</th>' : ''}<th class="num">Size</th>${cols.used ? '<th>Used for</th>' : ''}</tr></thead>
    <tbody>${shown.map(s => srcRow(s, srcFilter === 'all', cols)).join('')}</tbody></table></div>`;
  return `${viewHeader({title: 'Sources', meta, actions, primary})}<div class="vb">${note}${srcAskHTML()}${srcBusy ? loadingLine(srcBusy) : ''}${body}</div>`;
}
// a document no part claimed: which part is it for? ICs first, the passives need no datasheet
function srcAskHTML() {
  const names = srcUnmatched.filter(n => srcByName(n));
  if (!names.length) return '';
  const lines = (S.bom || []).filter(l => (l.refs || []).length && !l.datasheet);
  const isIc = l => !/^(R|C|L|D|LED|FB|Y|X|XTAL|J|P|H|TP|SW|F|FID|MH)\d/i.test(l.refs[0]);
  lines.sort((a, b) => isIc(b) - isIc(a));
  const opts = `<option value="">Which part is this for?</option>` + lines.map(l => `<option value="${esc(l.key)}">${esc(refsLabel(l.refs))} ${esc(l.mpn || l.value || '')}</option>`).join('');
  return names.map(n => `<div class="note"><span><span class="m">${esc(n)}</span> is not linked to a part yet.</span><span class="acts"><select class="in quiet" data-attach-doc="${esc(n)}" aria-label="Part for ${esc(n)}">${opts}</select></span></div>`).join('');
}
onChange(t => t.dataset && t.dataset.attachDoc !== undefined, async e => {
  if (!e.target.value) return;
  const r = await api('/api/parts/attach_datasheet', {line: e.target.value, name: e.target.dataset.attachDoc});
  srcUnmatched = srcUnmatched.filter(n => n !== e.target.dataset.attachDoc);
  setState(r); render(true);
  toast(attachMsg(r.attached));
});
function attachMsg(a) {
  return `${a.name} -> ${refsLabel(a.refs)}, ` + (a.status === 'verified' ? 'pins verified' : a.status === 'mismatch' ? 'pins conflict: ' + a.issues : 'nothing to check yet');
}
// a document the server just added shows where it landed: the new row is scrolled to and flashes once;
// what the matcher did with it is said in a toast, and a file nobody claimed gets a question
async function srcAdded(st) {
  const had = new Set((S.sources || []).map(s => s.name));
  const fresh = (st.sources || []).find(s => !had.has(s.name));
  if (st.matched || st.unmatched) {
    srcUnmatched = st.unmatched || [];
    const m = st.matched || [];
    if (m.length) setTimeout(() => toast(m.map(x => `${x.name} -> ${x.ref}, ` + (x.status === 'verified' ? 'pins verified' : x.status === 'mismatch' ? 'pins conflict: ' + x.issues : 'linked')).join('; ')), 50);
  }
  setState(st);
  if (fresh) hitSrc = fresh.name;
  srcBusy = '';
  render(true);
}

/* ================================ Settings ================================ */
function setRow(label, control, o) {
  o = o || {};
  return `<div class="set-row"><label${o.id ? ` for="${o.id}"` : ''}>${esc(label)}</label><div class="set-c">${control}${o.saved === false ? '' : '<span class="saved" aria-live="polite"></span>'}</div></div>`;
}
function setSel(id, attrs, options, value) {
  return `<select id="${id}" class="in" ${attrs}>${options.map(([v, text, extra]) => `<option value="${esc(v)}"${v === value ? ' selected' : ''}${extra || ''}>${text}</option>`).join('')}</select>`;
}
function setDetails(key, summary, body) {
  return `<details class="disc" data-open-key="${key}"${pgOpen[key] ? ' open' : ''}><summary>${esc(summary)}</summary>${body}</details>`;
}

/* Setup check: the same list as `python pcb.py doctor` (GET /api/doctor). The result is kept so a re-render keeps it. */
let PG_DOCTOR = null, PG_DOCTOR_BUSY = false;
function doctorHTML() {
  const run = btn(PG_DOCTOR_BUSY ? 'Checking…' : 'Run checks', {size: 'sm', act: 'doctor-run', disabled: PG_DOCTOR_BUSY});
  if (!PG_DOCTOR) return setRow('Setup', run, {saved: false});
  const tone = {ok: 'ok-t', warn: 'warn-t', fix: 'bad-t', skip: ''};
  const mark = {ok: '✓', warn: '!', fix: '✗', skip: '–'};
  const rows = PG_DOCTOR.checks.map(c => `<li><span class="${tone[c.status]}">${mark[c.status]}</span> <b>${esc(c.title)}</b>` +
    (c.detail ? ` <span class="muted">${esc(c.detail)}</span>` : '') +
    (c.fix && c.fix.command && c.status !== 'ok' ? `<div class="m">${esc(c.fix.command)} ${btn('Copy', {kind: 'link', size: 'sm', act: 'doctor-copy', cmd: c.fix.command})}</div>` : '') + '</li>').join('');
  return setRow('Setup', run, {saved: false}) + `<ul class="doctor-list" aria-live="polite">${rows}</ul>`;
}
async function pgDoctorRun() {
  PG_DOCTOR_BUSY = true; render(true);
  try { PG_DOCTOR = await api('/api/doctor?refresh=1'); } finally { PG_DOCTOR_BUSY = false; render(true); }
}
onAct('doctor-run', async () => { await pgDoctorRun(); });
onAct('doctor-copy', async (el, d) => {
  try { await navigator.clipboard.writeText(d.cmd); toast('Copied'); } catch (err) { toast(d.cmd); }
});

function setAgentHTML(c) {
  const engines = c.engines || [];
  const cur = engines.find(e => e.active);
  const opts = engines.map(e => [e.id, esc(e.title || e.id) + (e.available ? '' : ' (unavailable)'), e.status !== 'implemented' ? ' disabled' : '']);
  const lang = (c.user && c.user.language) || 'auto';
  return setRow('Engine', setSel('set-provider', 'data-set="agent.provider"', opts, cur ? cur.id : c.engine), {id: 'set-provider'}) +
    (cur && !cur.available ? `<div class="set-hint warn-t">${esc(cur.title || cur.id)} can't run now${cur.reason ? ': ' + esc(cur.reason) : ''}.</div>` : '') +
    setRow('Model', `<input id="set-model" class="in" data-set="agent.model" value="${esc((c.agent && c.agent.model) || '')}" placeholder="Engine default" autocomplete="off">`, {id: 'set-model'}) +
    setRow('Approvals', setSel('set-autonomy', 'data-set="agent.autonomy"', [
      ['ask', 'Ask me for every change'],
      ['important', 'Ask only for important changes (parts, Altium, ordering)'],
      ['auto', 'Do everything except ordering and deleting']], (c.agent && c.agent.autonomy) || 'important'), {id: 'set-autonomy'}) +
    doctorHTML() +
    setRow('Language', setSel('set-language', 'data-set="user.language"', PG_LANGS, lang), {id: 'set-language'}) +
    setRow('Your name', `<input id="set-name" class="in" data-set="user.name" value="${esc((c.user && c.user.name) || '')}" autocomplete="off">`, {id: 'set-name'});
}

// the linked project: "MyBoard.PrjPcb · Change · Unlink", and Change offers the recent projects and a typed path
function altLinkMenu(a, label) {
  const recent = (a.recent || []).map(r => ({label: r.name || pgBase(r.path), hint: r.exists ? '' : 'not found', act: 'altium-link', attrs: {path: r.path}, disabled: !r.exists, title: r.path}));
  return menu({label, kind: 'link'}, [...(recent.length ? [{group: 'Recent projects'}, ...recent, 'sep'] : []), {label: 'Browse path…', act: 'altium-browse'}]);
}
function altLinkedHTML(a) {
  const l = a.linked, sum = l.summary || {};
  const prjDir = (l.project_file || '').replace(/[\\/][^\\/]+$/, '');
  const sepc = (l.project_file || '').includes('\\') ? '\\' : '/';
  const abs = rel => (rel.includes(':') || rel.startsWith('/') || !prjDir) ? rel : prjDir + sepc + rel.replace(/[\\/]/g, sepc);
  const dotSep = '<span class="sep" aria-hidden="true">·</span>';
  let out = setRow('Project', `<span class="m set-prj" title="${esc(l.project_file)}">${esc(pgBase(l.project_file))}</span>${dotSep}${altLinkMenu(a, 'Change')}${dotSep}${btn('Unlink', {kind: 'link', act: 'altium-unlink'})}`, {saved: false});
  if (!l.exists) return out + '<div class="set-hint"><div class="note warn"><span>The project file is not on this machine. Change the link or unlink it.</span></div></div>';
  if (sum.error) return out + `<div class="set-hint">${errorLine('read the project', sum.error)}</div>`;

  const pcbs = sum.pcbs || [];
  const pcbPath = l.pcb_file || (pcbs.length === 1 ? abs(pcbs[0]) : '');
  const open = (id, path) => btn('Open', {kind: 'link', id, 'altium-path': path, title: 'Look inside this PCB document'});
  if (pcbs.length > 1) {
    const cur = pcbs.find(p => l.pcb_file && l.pcb_file.toLowerCase().includes(p.toLowerCase())) || pcbs[0];
    out += setRow('PcbDoc', setSel('altium-pcb-select', 'data-link="pcb"', pcbs.map(p => [p, esc(pgBase(p))]), cur) + open('altium-pcb-open', pcbPath || abs(cur)), {id: 'altium-pcb-select'});
  } else {
    out += setRow('PcbDoc', pcbPath ? `<button type="button" class="btn link m" data-altium-path="${esc(pcbPath)}" title="${esc(pcbPath)}">${esc(pgBase(pcbPath))}</button>` : '<span class="muted">None</span>', {saved: false});
  }
  out += setRow('Output folder', `<input id="altium-outdir" class="in" data-link="out" value="${esc(l.outputs_dir || '')}" placeholder="Where Altium writes its outputs" autocomplete="off">`, {id: 'altium-outdir'});
  const sheets = (l.sheets && l.sheets.length) ? l.sheets : (sum.sheets || []).map(abs);
  if (sheets.length) out += setRow('Sheets', `<div class="set-links">${sheets.map(sh => `<button type="button" class="btn link m" data-altium-path="${esc(sh)}" title="${esc(sh)}">${esc(pgBase(sh))}</button>`).join('')}</div>`, {saved: false});
  const gone = sum.missing || [];
  if (gone.length) out += `<div class="set-hint"><div class="note warn" title="${esc(gone.join('\n'))}"><span>${gone.length === 1 ? '1 document is' : gone.length + ' documents are'} missing: ${esc(gone.slice(0, 3).map(pgBase).join(', '))}${gone.length > 3 ? ` and ${gone.length - 3} more` : ''}</span></div></div>`;
  return out;
}
function setAltiumHTML(c) {
  if (ALTIUM_ERR) return errorLine('load the Altium settings', ALTIUM_ERR, btn('Retry', {size: 'sm', act: 'altium-retry'}));
  const a = ALTIUM_DATA;
  if (!a) return loadingLine('Reading the Altium settings');
  const installs = a.installs || [];
  const have = (c.altium && c.altium.install_path) || '';
  const auto = (a.active_install && a.active_install.path) || (installs[0] && installs[0].path) || '';
  let out = a.linked ? altLinkedHTML(a)
    : setRow('Project', `<span class="muted">Not linked</span><span class="sep" aria-hidden="true">·</span>${altLinkMenu(a, 'Link a project')}<span class="sep" aria-hidden="true">·</span>${btn('Create an Altium project', {kind: 'link', act: 'altium-create', title: 'Altium makes the project, an empty PCB and one sheet per planned sheet, with no components'})}`, {saved: false});
  if (installs.length || have) {
    const opts = [['', 'Newest (auto)'], ...installs.map(i => [i.path, esc((i.version ? 'Altium ' + i.version : i.build || 'Altium') + (i.exe ? '' : ' (no X2.EXE)'))])];
    if (have && !installs.some(i => i.path === have)) opts.push([have, esc(pgBase(have) || have)]);
    out += setRow('Install', setSel('set-altium-install', 'data-set="altium.install_path"', opts, have), {id: 'set-altium-install'});
  } else {
    out += setRow('Install', '<span class="muted">No Altium Designer found</span>', {saved: false});
  }
  out += setDetails('adv', 'Advanced', setRow('Altium folder', `<input id="set-altium-path" class="in" data-set="altium.install_path" value="${esc(have)}" placeholder="${esc(auto || 'Newest install')}" autocomplete="off">`, {id: 'set-altium-path'})
    + setRow('New projects in', `<input id="set-altium-base" class="in" data-set="altium.projects_dir" value="${esc((c.altium && c.altium.projects_dir) || '')}" placeholder="Public Documents/Altium folder (default) profile" autocomplete="off">`, {id: 'set-altium-base'}));
  return out;
}
function setSkillsHTML() {
  const built = (SKILLS || []).filter(s => s.available);
  if (!built.length) return '';
  return section('Skills', `<ul class="skills">${built.map(s => `<li><span class="sk-n">${esc(s.name)}</span><span class="sk-d">${esc(s.what)}</span></li>`).join('')}</ul>`, {id: 'set-skills'});
}
function settingsHTML(container) {
  pgSkillsScrolled = false;
  return settingsBody();
}
function settingsBody() {
  const c = CONFIG;
  const head = viewHeader({title: 'Settings'});
  if (!c || c.error || !c.user) {
    return head + `<div class="vb">${c ? errorLine('load the settings', c.error || 'the server sent nothing usable', btn('Retry', {size: 'sm', act: 'settings-retry'})) : loadingLine('Loading')}</div>`;
  }
  const theme = seg([{value: 'system', label: 'System'}, {value: 'light', label: 'Light'}, {value: 'dark', label: 'Dark'}], getThemePref(), {act: 'set-theme', label: 'Theme'});
  const mem = setDetails('mem', 'This conversation\'s memory', `<div class="set-mem"><textarea id="mem" class="in" rows="8" dir="auto" data-mem aria-label="This conversation's memory">${esc(S.memory)}</textarea>
    <div class="acts">${btn('Rewrite', {act: 'rewritemem', title: 'Let the agent rewrite the memory from the conversation'})}<span class="saved" aria-live="polite"></span></div></div>`);
  return head + `<div class="vb set-page">
    ${section('Appearance', setRow('Theme', theme, {saved: false}))}
    ${section('Agent', setAgentHTML(c))}
    ${section('Altium', setAltiumHTML(c))}
    ${section('Memory', mem)}
    ${setSkillsHTML()}
    ${typeof aboutHTML === 'function' ? section('About', aboutHTML(), {id: 'set-about'}) : ''}
    <p class="set-foot">${btn('Reset layout', {kind: 'link', act: 'reset-layout', title: 'Restore the default panel sizes and close the side sheet'})}</p></div>`;
}
// the old Skills page: Settings, scrolled to the Skills section the first time it is drawn
function skillsHTML(container) {
  if (!ALTIUM_DATA) loadAltium();
  if (!pgSkillsScrolled && (ALTIUM_DATA || ALTIUM_ERR)) {      // wait until the page has its full height
    pgSkillsScrolled = true;
    requestAnimationFrame(() => { const s = document.getElementById('set-skills'); if (s) s.scrollIntoView({block: 'start'}); });
  }
  return settingsBody();
}

/* ---------- autosave: each field saves alone, then says Saved ---------- */
const pgTimers = new Map();
function pgDirty(el) {
  if (el.tagName === 'SELECT') { const o = [...el.options].find(x => x.defaultSelected); return !o || o.value !== el.value; }
  return el.value !== el.defaultValue;
}
function pgClean(el) {
  if (el.tagName === 'SELECT') [...el.options].forEach(o => { o.defaultSelected = o.selected; });
  else el.defaultValue = el.value;
}
function pgSaved(el, text) {
  const slot = el.closest('.set-row, .set-mem');
  const s = slot && slot.querySelector('.saved');
  if (!s) return;
  s.textContent = text || 'Saved';
  clearTimeout(s._t);
  s._t = setTimeout(() => { s.textContent = ''; }, 2000);
}
function pgSet(id, value) {                    // put a saved value into another control that shows the same setting
  const el = document.getElementById(id);
  if (!el || el.value === value) return;
  if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === value)) return;
  el.value = value;
  pgClean(el);
}
async function pgSave(el) {
  if (!pgDirty(el)) return;
  const link = el.dataset.link !== undefined, mem = el.dataset.mem !== undefined;
  try {
    if (mem) {
      const r = await api('/api/memory', {text: el.value});
      if (r.trimmed) { el.value = r.memory; pgSaved(el, 'Saved, shortened to fit'); } else pgSaved(el);
    } else if (link) {
      const prj = ALTIUM_DATA && ALTIUM_DATA.linked && ALTIUM_DATA.linked.project_file;
      if (!prj) return;
      const pcb = document.getElementById('altium-pcb-select'), out = document.getElementById('altium-outdir');
      ALTIUM_DATA = await api('/api/altium/link', {path: prj, pcb_file: pcb ? pcb.value : undefined, outputs_dir: out && out.value.trim() ? out.value.trim() : undefined});
      const l = ALTIUM_DATA.linked || {};
      pgSet('altium-outdir', l.outputs_dir || '');
      const open = document.getElementById('altium-pcb-open');
      if (open && l.pcb_file) open.dataset.altiumPath = l.pcb_file;
      pgSaved(el);
      impFor = null;                          // the BOM's import candidates come from the output folder: ask again when it is drawn
    } else {
      const key = el.dataset.set, value = el.tagName === 'SELECT' ? el.value : el.value.trim();
      const r = await api('/api/config', {set: {[key]: value}});
      CONFIG = r.config;
      if (key === 'altium.install_path') { pgSet('set-altium-install', value); pgSet('set-altium-path', value); }
      if (key === 'agent.provider') {          // a model name belongs to one engine: draw the new engine's, and keep the focus
        renderCenter(true);
        el = document.getElementById('set-provider') || el;
        el.focus();
      }
      pgSaved(el);
    }
    pgClean(el);
  } catch (e) { /* api() already said what failed; the field keeps what was typed */ }
}
document.addEventListener('input', e => {
  const t = e.target;
  if (!t.matches || t.tagName === 'SELECT' || !t.matches('[data-set], [data-link], [data-mem]')) return;
  clearTimeout(pgTimers.get(t.id));
  pgTimers.set(t.id, setTimeout(() => pgSave(t), 700));
});
onChange(t => !!(t.matches && t.matches('[data-set], [data-link], [data-mem]')), async e => {
  clearTimeout(pgTimers.get(e.target.id));
  await pgSave(e.target);
});
document.addEventListener('toggle', e => {      // a disclosure the user opened stays open when the page is drawn again
  const d = e.target;
  if (d.matches && d.matches('details[data-open-key]')) pgOpen[d.dataset.openKey] = d.open;
}, true);
// the theme can also change from the command palette: keep the switch honest
new MutationObserver(() => {
  const v = getThemePref();
  document.querySelectorAll('[data-act="set-theme"]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === v)));
}).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});

// library rows: reachable with the keyboard, like the BOM rows
document.addEventListener('keydown', e => {
  const tr = e.target.closest && e.target.closest('.lib-tbl tbody tr[data-key]');
  if (!tr || e.target !== tr) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(tr.dataset.key); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const next = e.key === 'ArrowDown' ? tr.nextElementSibling : tr.previousElementSibling;
    if (next) { e.preventDefault(); next.focus(); }
  }
});

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('libexport', async (el, d, e) => {
  if (libBusy) return;
  libBusy = true;
  try {
    libExport = await api('/api/library/export', {});
    await refresh(true);                      // the new file also shows up in Outputs
    const url = `/api/export/${encodeURIComponent(libExport.file)}?${q()}`, file = libExport.file;
    toast(`${file} exported`, {label: 'Download', onClick: () => fileDownload(url, file)});
  } finally { libBusy = false; }
});
onAct('src-filter', async (el, d, e) => {
  srcFilter = d.value || 'all'; renderCenter(true);
});
onAct('src-copy', async (el, d, e) => {
  let ok = false;
  try { await navigator.clipboard.writeText(PG_RESTORE); ok = true; } catch (err) { /* no clipboard: fall back below */ }
  if (!ok) {
    const ta = document.createElement('textarea');
    ta.value = PG_RESTORE;
    document.body.appendChild(ta);
    ta.select();
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    ta.remove();
  }
  if (ok) { const s = el.querySelector('span'); if (s) { s.textContent = 'Copied'; setTimeout(() => { s.textContent = 'Copy'; }, 1500); } }
  else toast('Couldn\'t copy. Select the command and copy it.');
});
onAct('upload', async (el, d, e) => {
  $('#filepick').click();
});
onAct('addurl', async (el, d, e) => {
  const u = await askText({title: 'Add from URL', label: 'Address of the document', placeholder: 'https://', hint: 'A PDF or a text file. It is saved in this project.', confirm: 'Add'});
  if (!u) return;
  srcBusy = 'Fetching the document';
  renderCenter(true);
  try {
    const r = await api('/api/fetch_source', {url: u});
    if (r.error) { srcBusy = ''; renderCenter(true); toast(r.error); return; }
    await srcAdded(r);
  } catch (err) { srcBusy = ''; renderCenter(true); }
});
onChange(t => t.id === 'filepick', async e => {
  const f = e.target.files[0]; if (!f) return;
  srcBusy = `Adding ${f.name}`;
  renderCenter(true);
  try {
    const buf = new Uint8Array(await f.arrayBuffer()); let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    await srcAdded(await api('/api/upload', {name: f.name, data_b64: btoa(bin)}));
  } catch (err) { srcBusy = ''; renderCenter(true); }
  e.target.value = '';
});

async function pgLink(path) {
  ALTIUM_DATA = await api('/api/altium/link', {path});
  ALTIUM_ERR = null;
  renderCenter(true);
  impFor = null;                              // the BOM asks again whether a project is linked
}
onAct('altium-link', async (el, d, e) => { if (d.path) await pgLink(d.path); });
onAct('altium-browse', async (el, d, e) => {
  const p = await askText({title: 'Link an Altium project', label: 'Path to the .PrjPcb file or its folder', placeholder: 'C:\\Projects\\MyBoard\\MyBoard.PrjPcb', confirm: 'Link'});
  if (p) await pgLink(p);
});
onAct('altium-create', async (el, d, e) => {
  if (el.disabled) return;
  el.disabled = true;
  toast('Creating the Altium project. Altium may take a minute and flash while it works.');
  try {
    ALTIUM_DATA = await api('/api/altium/create', {});
    ALTIUM_ERR = null;
    impFor = null;                            // the BOM asks again whether a project is linked
    toast('Altium project created: ' + pgBase(ALTIUM_DATA.linked.project_file)
      + (ALTIUM_DATA.warning ? '. ' + ALTIUM_DATA.warning : ''));
  } catch (err) {
    // a failure can come after Altium already wrote and linked the project: show what is there now
    try { ALTIUM_DATA = await api('/api/altium'); impFor = null; } catch (e2) { /* keep the old view */ }
  }
  el.disabled = false;
  renderCenter(true);
});
onAct('altium-unlink', async (el, d, e) => {
  ALTIUM_DATA = await api('/api/altium/unlink', {});
  renderCenter(true);
  impFor = null;
});
onAct('altium-retry', async (el, d, e) => { await loadAltium(true); });
onAct('settings-retry', async (el, d, e) => { await loadConfig(); });
onAct('set-theme', async (el, d, e) => { setThemePref(d.value); });
onAct('rewritemem', async (el, d, e) => {
  if (el.disabled) return;
  const label = el.querySelector('span'), was = label ? label.textContent : '';
  el.disabled = true;
  if (label) label.textContent = 'Rewriting';
  try {
    const r = await api('/api/memory', {});
    const ta = $('#mem');
    if (ta && r.memory != null) { ta.value = r.memory; pgClean(ta); pgSaved(ta, 'Rewritten'); }
    if (r.rewritten && r.rewritten.ok === false) toast('Memory not rewritten: ' + (r.rewritten.reason || 'nothing to do'));
  } finally {
    el.disabled = false;
    if (label) label.textContent = was;
  }
});
