/* PCB Advisor UI - Rules view: your board against the JLC preset, the .RUL export, extra rules and the calculators.
   Two segments (Rules | Calculators). The diff shows only the rows that need a look until "Show all" is on.
   Globals other files use: loadRules, rulesHTML, rulesSummary (the counts behind the header and the nav dot), runCalculator. */

const RULES_SEG_KEY = 'pcb_advisor_rules_seg';
const RULES_FRESH_MS = 15000;           // the board may change in Altium: read it again when the view is drawn after this long
const RULES_SRC = 'jlc/pcb-capabilities.en.md';    // a general source, named by its path under shared/reference: the document the preset values come from
let RULES_AT = 0, RULES_P = null;       // when RULES_DATA was read, and the read in flight
let rulesSeg = null;                    // 'rules' | 'calc', remembered as a UI preference
let rulesAll = false;                   // "Show all": every row of the diff, not only the ones that need attention
const rulesOpen = {};                   // which disclosures the user opened: howto, preset, extra
const rulesDraft = {};                  // the extra-rule form, kept while the view redraws

/* ---------- loading ---------- */
function loadRules(quiet) {
  if (RULES_P) return RULES_P;
  RULES_P = (async () => {
    let next;
    try {
      next = await api('/api/rules', undefined, {soft: true});
    } catch (e) {
      next = {error: e.message || 'the server did not answer'};
    }
    RULES_AT = Date.now();
    const changed = JSON.stringify(next) !== JSON.stringify(RULES_DATA);
    RULES_DATA = next;
    if (changed) {
      if (typeof renderNav === 'function') renderNav();      // the Rules dot in the nav reads RULES_DATA
      if (mainView() === 'rules' || sideView() === 'rules') renderCenter(!quiet);
    }
  })().finally(() => { RULES_P = null; });
  return RULES_P;
}
addEventListener('focus', () => {       // back from Altium: show the board as it is now
  if (RULES_DATA && !RULES_DATA.error && (mainView() === 'rules' || sideView() === 'rules') && Date.now() - RULES_AT > 5000) loadRules(true);
});

/* ---------- the verdict of one diff row ---------- */
/* verdict (the server's numeric judgement against the JLC minimum) -> [tag tone, label] */
const VERDICT = {
  same: ['', 'Matches'],
  safer: ['ok', 'Stricter'],
  tighter_ok: ['warn', 'Tighter than preset'],
  below_fab_min: ['bad', 'Below JLC minimum'],
  unknown: ['', 'Not judged'],
};
/* One "Result" per row. Below the JLC minimum wins over everything; then the status says whether the rule is missing
   or an extra on the board; otherwise the verdict decides. attention: the row needs a look. */
function rulesResult(d) {
  const [vc, vl] = VERDICT[d.verdict] || VERDICT.unknown;
  const st = d.status || d.Status;
  if (vc === 'bad') return {key: 'below', tone: 'bad', text: vl, rank: 0, attention: true};
  if (st === 'missing_on_board') return {key: 'missing', tone: 'warn', text: 'Missing', rank: 1, attention: true};
  if (st === 'extra_on_board') return {key: 'extra', tone: '', text: 'Extra', rank: 5, attention: false};
  if (st === 'match' || d.verdict === 'same') return {key: 'match', tone: '', text: 'Matches', rank: 4, attention: false};
  if (vc === 'ok') return {key: 'stricter', tone: 'ok', text: vl, rank: 3, attention: false};
  if (d.verdict === 'tighter_ok') return {key: 'tighter', tone: 'warn', text: vl, rank: 2, attention: true};
  return {key: 'differs', tone: 'warn', text: 'Differs', rank: 2, attention: true};   // the numbers differ and no JLC minimum judges them
}
/* {below, differ, rows}: below the JLC minimum, and the others that need a look. shell.js stageStatus('rules') may use it. */
function rulesSummary(rd) {
  const out = {below: 0, differ: 0, rows: 0, preset: ((rd && rd.preset && rd.preset.rules) || []).length};
  for (const d of (rd && rd.diff) || []) {
    const r = rulesResult(d);
    out.rows++;
    if (r.key === 'below') out.below++;
    else if (r.attention) out.differ++;
  }
  return out;
}
const rulesSegGet = () => {
  if (rulesSeg === null) rulesSeg = lsGet(RULES_SEG_KEY) === 'calc' ? 'calc' : 'rules';
  return rulesSeg;
};

/* ---------- header ---------- */
function rulesHeader(rd) {
  if (!rd || rd.error) return viewHeader({title: 'Rules'});
  const linked = rd.linked_pcb, sm = rulesSummary(rd);
  const meta = metaLine([
    {n: sm.preset, label: `${(rd.preset && rd.preset.name) || 'JLC'} preset rule${sm.preset === 1 ? '' : 's'}`, title: 'Picked from this board\'s layer count, copper weight and mask colour'},
    !linked && {always: true, label: 'No board linked'},
    linked && {n: sm.differ, label: 'differ on your board', tone: 'warn', title: 'Missing from the board, or different from the preset with no JLC minimum to judge them by'},
    linked && {n: sm.below, label: 'below JLC minimum', tone: 'bad', title: 'The fab may reject or alter these'},
    linked && !sm.differ && !sm.below && {always: true, label: 'Your board matches the preset'},
  ]);
  const actions = linked ? menu({icon: 'more', title: 'More'}, [
    {label: 'Preset only (.RUL)', act: 'rules-preset'}]) : '';
  const primary = `<a class="btn pri" href="/api/rules/export?${q()}" download="${esc(PROJECT)}-rules${linked ? '-board' : ''}.RUL" title="${linked ? 'All the rules of your board, with the JLC values filled in' : 'The JLC preset rules'}">${icon('download')}<span>Download .RUL</span></a>`;
  return viewHeader({title: 'Rules', meta, actions, primary});
}

/* ---------- the diff ---------- */
function rulesDiffRow(d) {
  const r = rulesResult(d);
  const name = d.rule || d.Rule || '', kind = d.kind || d.Kind || '';
  const bv = d['board value'] || d.board_value || '', pv = d['preset value'] || d.preset_value || '';
  const none = v => v && !/^[-–—\s]+$/.test(v) ? v.split(', ').map(esc).join('<br>') : '<span class="muted">—</span>';    // "Min: 5mil, Max: 40mil" on two lines
  const tagHTML = r.key === 'match' ? `<span class="muted" title="Matches">${icon('check', 's')}<span class="sr">Matches</span></span>` : tag(r.text, r.tone);
  const inline = d.detail && (r.attention || r.key === 'stricter');     // a match or an extra says it all in its tag; the title has the text
  return `<tr>
    <td><span class="rn">${esc(name)}</span>${kind && kind !== name ? `<span class="sub">${esc(kind)}</span>` : ''}</td>
    <td class="val" data-label="Your board">${none(bv)}</td>
    <td class="val" data-label="JLC preset">${none(pv)}</td>
    <td class="res" title="${esc(d.detail || '')}">${tagHTML}${inline ? `<span class="why">${esc(d.detail)}</span>` : ''}</td>
    <td><div class="row-acts">${btn('', {icon: 'chat', size: 'sm', title: `Ask about ${name}`, act: 'rules-ask', rule: name})}</div></td></tr>`;
}
function rulesDiffSection(rd) {
  const diff = rd.diff || [];
  const rated = diff.map(d => ({d, r: rulesResult(d)})).sort((a, b) => a.r.rank - b.r.rank);   // stable: the server's order within a rank
  const need = rated.filter(x => x.r.attention), shown = rulesAll ? rated : need;
  const toggle = rated.length > need.length
    ? `<label class="check"><input type="checkbox" id="rules-all"${rulesAll ? ' checked' : ''}>Show all ${rated.length}</label>` : '';
  let body;
  if (!diff.length) body = '<p class="muted">No rules found on the board.</p>';
  else if (!shown.length) body = '<p class="muted">Every rule matches the JLC preset or is stricter.</p>';
  else body = `<table class="tbl rules-tbl rules-diff"><thead><tr><th>Rule</th><th>Your board</th><th>JLC preset</th><th>Result</th><th><span class="sr">Actions</span></th></tr></thead>
    <tbody>${shown.map(x => rulesDiffRow(x.d)).join('')}</tbody></table>`;
  return section('Your board vs JLC preset', body, {meta: `<span class="m">${esc(rd.linked_pcb)}</span>`, actions: toggle});
}

/* ---------- the three disclosures ---------- */
function rulesDisc(id, title, body, open) {
  return `<details class="disc rules-disc" data-disc="${id}"${open ? ' open' : ''}><summary>${esc(title)}</summary><div class="rules-dbody">${body}</div></details>`;
}
function rulesHowTo(linked) {
  const steps = linked ? [
    'In Altium open Design » Rules, right-click Default Rule Set and choose Import Rules.',
    'Pick the .RUL and choose Replace existing. It holds all your board’s rules, with the JLC values filled in.',
    'Come back here to see the diff.',
  ] : [
    'In Altium open Design » Rules, right-click Default Rule Set and choose Import Rules.',
    'Pick the .RUL and choose Merge with existing. Altium adds the imported rules below your own, named like Clearance_1.',
    'Open Priorities and move each imported rule to the top, or delete the old rule of the same kind.',
    'Link your PcbDoc in Settings, then come back here to see the diff.',
  ];
  return `<ol class="rules-steps">${steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>` +
    (linked ? '<p class="muted">Preset only (.RUL) holds just the JLC rules: choose Merge with existing for that one.</p>' : '');
}
function rulesPresetTable(rd) {
  const p = (rd.preset && rd.preset.rules) || [];
  const cite = chip(RULES_SRC);                 // opens the document in the side sheet; marked broken if Sources does not list it
  return `<table class="tbl dense rules-tbl"><thead><tr><th>Rule</th><th>Constraints</th><th>Scope</th><th>Description</th></tr></thead><tbody>
    ${p.map(r => `<tr><td><span class="rn">${esc(r.name)}</span></td><td class="val">${esc(r.value || '—')}</td><td>${esc(r.scope1 || 'All')}</td><td class="muted wrapcell">${esc(r.description || '')}</td></tr>`).join('')}
    </tbody></table><p class="muted rules-src">Values from JLC&rsquo;s capabilities page, summarised in ${cite}.</p>`;
}
function rulesExtraBody(rd) {
  const ex = rd.extra || [];
  const dr = rulesDraft;
  const kinds = ['Width', 'Clearance', 'RoutingVias', 'ComponentClearance'];
  const table = ex.length
    ? `<p class="muted">Added to every .RUL you download.</p><table class="tbl dense rules-tbl"><thead><tr><th>Rule</th><th>Kind</th><th>Scope</th><th>Value</th></tr></thead><tbody>
      ${ex.map(r => `<tr><td><span class="rn">${esc(r.name)}</span></td><td>${esc(r.kind)}</td><td>${esc(r.scope1 || 'All')}</td><td class="val">${esc(r.value || '')}</td></tr>`).join('')}</tbody></table>`
    : '<p class="muted">No extra rules yet. Rules you add here go into every .RUL you download.</p>';
  return `${table}
    <div class="rules-add" role="group" aria-label="Add an extra rule">
      <label class="field"><span>Name</span><input class="in" id="er-name" data-draft="name" value="${esc(dr.name || '')}" placeholder="PowerNets_Width" autocomplete="off"></label>
      <label class="field"><span>Kind</span><select class="in" id="er-kind" data-draft="kind">${kinds.map(k => `<option value="${k}"${(dr.kind || 'Width') === k ? ' selected' : ''}>${k}</option>`).join('')}</select></label>
      <label class="field"><span>Scope</span><input class="in" id="er-scope" data-draft="scope" value="${esc(dr.scope || '')}" placeholder="InNetClass('PowerNets')" autocomplete="off"></label>
      <label class="field"><span>Value</span><input class="in" id="er-val" data-draft="val" value="${esc(dr.val || '')}" placeholder="20mil" autocomplete="off"></label>
      ${btn('Add rule', {kind: 'line', act: 'add-extra-rule'})}
    </div>`;
}
function rulesDiscs(rd) {
  const linked = !!rd.linked_pcb, n = ((rd.preset && rd.preset.rules) || []).length, ex = (rd.extra || []).length;
  return `<div class="rules-discs">
    ${rulesDisc('howto', 'How to import in Altium', rulesHowTo(linked), !!rulesOpen.howto)}
    ${rulesDisc('preset', `JLC preset (${n} rules)`, rulesPresetTable(rd), rulesOpen.preset ?? !linked)}
    ${rulesDisc('extra', ex ? `Extra rules (${ex})` : 'Extra rules', rulesExtraBody(rd), !!rulesOpen.extra)}
  </div>`;
}

/* ---------- calculators: the inputs update the result as you type ---------- */
function fmtOhm(n) {
  n = +n;
  if (!isFinite(n)) return String(n);
  if (n >= 1e6) return +(n / 1e6).toPrecision(3) + ' MΩ';
  if (n >= 1e3) return +(n / 1e3).toPrecision(3) + ' kΩ';
  return +n.toPrecision(3) + ' Ω';
}
/* id -> inputs (k = the field, step, def = the value it starts with), the /api/calc query, and the answer to show */
const CALCS = [
  {id: 'tw', title: 'Trace width',
    fields: [{k: 'current', label: 'Current (A)', step: 0.1, def: 1.5}, {k: 'rise', label: 'Temperature rise (°C)', step: 1, def: 10}, {k: 'oz', label: 'Copper (oz)', step: 0.5, def: 1}],
    query: v => `type=trace_width&current=${v.current}&rise=${v.rise}&oz=${v.oz}`,
    show: r => ({main: `${r.width_mm} mm`, sub: `${r.width_mil} mil, the minimum width`})},
  {id: 'div', title: 'Voltage divider',
    fields: [{k: 'vin', label: 'Vin (V)', step: 0.1, def: 5}, {k: 'vout', label: 'Target Vout (V)', step: 0.1, def: 3.3}],
    query: v => `type=divider&vin=${v.vin}&vout=${v.vout}`,
    show: r => ({main: `R1 ${fmtOhm(r.r1)}, R2 ${fmtOhm(r.r2)}`, sub: `E24 values, Vout ${r.vout} V (${r.error_pct}% off the target)`})},
  {id: 'led', title: 'LED resistor',
    fields: [{k: 'vs', label: 'Supply (V)', step: 0.1, def: 5}, {k: 'vf', label: 'LED forward voltage (V)', step: 0.1, def: 2}, {k: 'ma', label: 'LED current (mA)', step: 1, def: 20}],
    query: v => `type=led&v_supply=${v.vs}&v_forward=${v.vf}&i_forward_ma=${v.ma}`,
    show: r => ({main: fmtOhm(r.r_standard_ohm), sub: `${r.r_standard_ohm === r.r_exact_ohm ? 'an E24 value' : 'next E24 value up from ' + fmtOhm(r.r_exact_ohm)}, dissipates ${r.power_w} W`})},
  {id: 'via', title: 'Via current',
    fields: [{k: 'drill', label: 'Drill (mm)', step: 0.05, def: 0.3}, {k: 'rise', label: 'Temperature rise (°C)', step: 1, def: 10}],
    query: v => `type=via&drill_mm=${v.drill}&rise=${v.rise}`,
    show: r => ({main: `${r.current_a} A`, sub: `maximum through the barrel (area ${r.barrel_area_mil2} mil²)`})},
  {id: 'ms', title: 'Microstrip impedance',
    fields: [{k: 'w', label: 'Trace width (mm)', step: 0.05, def: 0.3}, {k: 'h', label: 'Height above plane (mm)', step: 0.05, def: 0.2}, {k: 'er', label: 'Dielectric constant', step: 0.1, def: 4.4}],
    query: v => `type=microstrip&width_mm=${v.w}&height_mm=${v.h}&er=${v.er}`,
    show: r => ({main: `${r.z0_ohm} Ω`, sub: 'characteristic impedance, Z0'})},
];
const calcVals = {};            // id -> {field: text typed}, kept while the view redraws
const calcOut = {};             // id -> {main, sub, formula, source} | {error} | {note}: the last answer
const calcSeq = {}, calcTimer = {};

function calcValue(c, k) {
  const v = calcVals[c.id] && calcVals[c.id][k];
  return v !== undefined ? v : String(c.fields.find(f => f.k === k).def);
}
function calcOutHTML(o) {
  if (!o) return '';
  if (o.note) return `<p class="muted">${esc(o.note)}</p>`;
  if (o.error) return `<p class="warn-t">${esc(o.error)}</p>`;
  return `<p class="calc-main"><b>${esc(o.main)}</b> <span class="muted">${esc(o.sub)}</span></p><p class="calc-src muted">${esc(o.formula)}<br>${esc(o.source)}</p>`;
}
function calcPaint(id) {
  const box = $('#res-' + id);
  if (box) box.innerHTML = calcOutHTML(calcOut[id]);
}
async function runCalculator(d) {      // d.calc = the calculator id; the inputs come from what was typed
  const c = CALCS.find(x => x.id === d.calc);
  if (!c) return;
  const v = {};
  for (const f of c.fields) {
    const n = parseFloat(calcValue(c, f.k));
    if (!(n > 0)) { calcOut[c.id] = {note: 'Enter a number above zero in every field.'}; calcPaint(c.id); return; }
    v[f.k] = n;
  }
  const seq = calcSeq[c.id] = (calcSeq[c.id] || 0) + 1;
  let res;
  try {
    res = await api('/api/calc?' + c.query(v), undefined, {soft: true});
  } catch (e) {
    res = {error: 'The calculator did not answer. Try again.'};
  }
  if (seq !== calcSeq[c.id]) return;   // a newer entry is already on its way
  calcOut[c.id] = res && !res.error ? {...c.show(res), formula: res.formula, source: res.source} : {error: (res && res.error) || 'No answer.'};
  calcPaint(c.id);
}
function calcSchedule(id) {            // about 300 ms after the last keystroke
  clearTimeout(calcTimer[id]);
  calcTimer[id] = setTimeout(() => runCalculator({calc: id}), 300);
}
function calcSection(c) {
  const fields = c.fields.map(f => `<label class="field"><span>${esc(f.label)}</span><input class="in" type="number" inputmode="decimal" step="any" data-calc="${c.id}" data-k="${f.k}" value="${esc(calcValue(c, f.k))}"></label>`).join('');
  return section(c.title, `<div class="calc-in">${fields}</div><div class="calc-out" id="res-${c.id}" role="status" aria-live="polite">${calcOutHTML(calcOut[c.id])}</div>`);
}
function calcsHTML() {
  for (const c of CALCS) if (!calcOut[c.id] && !calcSeq[c.id]) runCalculator({calc: c.id});    // first time: answer for the starting values
  return `<div class="rules-calcs">${CALCS.map(calcSection).join('')}</div>`;
}
document.addEventListener('input', e => {
  const t = e.target;
  if (!t || !t.closest) return;
  const c = t.dataset && t.dataset.calc;
  if (c) {
    (calcVals[c] = calcVals[c] || {})[t.dataset.k] = t.value;
    calcSchedule(c);
  } else if (t.dataset && t.dataset.draft) {
    rulesDraft[t.dataset.draft] = t.value;
  }
});
document.addEventListener('keydown', e => {      // Enter in the extra-rule form adds the rule
  if (e.key !== 'Enter' || !e.target.closest || e.target.tagName !== 'INPUT' || !e.target.closest('.rules-add')) return;
  e.preventDefault();
  const b = $('[data-act="add-extra-rule"]');
  if (b) b.click();
});
document.addEventListener('click', e => {       // a disclosure the user opened stays open when the view redraws
  const s = e.target.closest && e.target.closest('details[data-disc] > summary');
  if (s) rulesOpen[s.parentElement.dataset.disc] = !s.parentElement.open;      // the click has not toggled it yet
}, true);

/* ---------- the view ---------- */
function rulesHTML(container) {
  const rd = RULES_DATA;
  if (!rd) {
    if (!RULES_P) loadRules();
    return viewHeader({title: 'Rules'}) + `<div class="vb">${loadingLine('Reading the design rules')}</div>`;
  }
  if (rd.error) {
    return viewHeader({title: 'Rules'}) + `<div class="vb">${errorLine('load the design rules', rd.error, btn('Retry', {size: 'sm', act: 'rules-retry'}))}</div>`;
  }
  if (!RULES_P && Date.now() - RULES_AT > RULES_FRESH_MS) loadRules(true);
  const linked = !!rd.linked_pcb, segv = rulesSegGet();
  const switcher = `<div class="rules-seg">${seg([{value: 'rules', label: 'Rules'}, {value: 'calc', label: 'Calculators'}], segv, {act: 'rules-seg', label: 'Rules view'})}</div>`;
  let body;
  if (segv === 'calc') body = calcsHTML();
  else body = (linked ? rulesDiffSection(rd)
    : `<div class="note">No board linked. Link a project in ${btn('Settings', {kind: 'link', page: 'settings'})} to compare its rules.</div>`) + rulesDiscs(rd);
  return rulesHeader(rd) + `<div class="vb rules-vb">${switcher}${body}</div>`;
}
function rulesFocus(sel) {       // a redraw drops the focus; give it back to the control the user just used
  const el = $(sel);
  if (el) el.focus({preventScroll: true});
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('rules-seg', async (el, d, e) => {
  rulesSeg = d.value === 'calc' ? 'calc' : 'rules';
  lsSet(RULES_SEG_KEY, rulesSeg);
  renderCenter(true);
  rulesFocus(`.rules-seg button[data-value="${rulesSeg}"]`);
});
onChange(t => t.id === 'rules-all', async e => {
  rulesAll = e.target.checked;
  renderCenter(true);
  rulesFocus('#rules-all');
});
onAct('rules-retry', async (el, d, e) => {
  RULES_DATA = null;
  renderCenter(true);
});
onAct('rules-preset', async (el, d, e) => {      // the JLC rules alone, for Merge
  const a = document.createElement('a');
  a.href = `/api/rules/export?${q({plain: 1})}`;
  a.download = `${PROJECT}-rules.RUL`;
  document.body.appendChild(a);
  a.click();
  a.remove();
});
onAct('rules-ask', async (el, d, e) => {
  const row = ((RULES_DATA && RULES_DATA.diff) || []).find(x => (x.rule || x.Rule) === d.rule);
  const bv = row && (row['board value'] || row.board_value), pv = row && (row['preset value'] || row.preset_value);
  const r = row ? rulesResult(row) : null;
  const text = r ? `Should I change the ${d.rule} rule? My board has ${bv || 'nothing'}, the JLC preset has ${pv || 'nothing'} (${r.text.toLowerCase()}).` : '';
  askAbout({kind: 'rule', id: d.rule, label: d.rule, text});
});
onAct('add-extra-rule', async (el, d, e) => {
  const name = ($('#er-name')?.value || '').trim();
  const kind = $('#er-kind')?.value || 'Width';
  const scope1 = ($('#er-scope')?.value || 'All').trim() || 'All';
  const val = ($('#er-val')?.value || '').trim();
  if (!name || !val) { toast('Enter a name and a value for the rule.', null, {bad: true}); return; }
  const res = await api('/api/rules/extra', {rule: {name, kind, scope1, value: val}});
  if (RULES_DATA && res && Array.isArray(res.extra)) RULES_DATA.extra = res.extra;
  for (const k of Object.keys(rulesDraft)) delete rulesDraft[k];
  renderCenter(true);       // the new rule shows in the table
  rulesFocus('#er-name');
});
