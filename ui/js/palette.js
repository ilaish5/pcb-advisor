/* PCB Advisor UI - command palette (Ctrl K, or Search in the nav). Go to a stage or page, find a part, a net or a file,
   run an action. It never reads the DOM of the sheets: everything comes from S and the registered actions.
   Globals: openPalette(), closePalette(). Loaded after viewer.js (it opens documents) and before boot.js. */

const PAL_MAX = 8;                // at most this many rows per group
let pal = null;                   // {scrim, input, ul, q, idx, opts, opener} while the palette is open

/* ---------- what can be found ---------- */
function palGoTo() {
  const out = [];
  for (const [id, label] of STAGES) out.push({g: 'Go to', label, d: stageStatus(id).title, fields: [[label, 1], [id, .9]], run: () => go('workspace', id)});
  for (const id of ['library', 'sources', 'settings', 'skills']) out.push({g: 'Go to', label: PAGE_TITLES[id], fields: [[PAGE_TITLES[id], 1], [id, .9]], run: () => go(id)});
  return out;
}
function palParts() {
  return lines().map(l => {
    const refs = l.refs || [];
    const sub = [l.value, l.mpn].filter(Boolean).join(' · ');
    return {g: 'Parts', cls: 'ref', refs, label: refs[0] || l.mpn || '', sub,
      fields: [...refs.map(r => [r, 1.2]), [l.mpn, 1], [l.value, .9], [l.manufacturer, .7], [l.description, .5], [l.package, .5]],
      run: () => {
        select(l.key);
        setTimeout(() => { const tr = [...document.querySelectorAll('tr[data-key]')].find(t => t.dataset.key === l.key); if (tr) tr.scrollIntoView({block: 'center'}); }, 60);
      }};
  });
}
function palNets() {
  const sheetsOf = new Map();
  for (const sh of (S.sheets || [])) {
    for (const p of Object.values(sh.parts || {})) {
      for (const n of (p && p.nets) || []) {
        if (!sheetsOf.has(n)) sheetsOf.set(n, new Set());
        sheetsOf.get(n).add(sh.id);
      }
    }
  }
  return [...sheetsOf].map(([name, ids]) => ({g: 'Nets', cls: 'netn', label: name, d: [...ids].slice(0, 2).join(', '), fields: [[name, 1]], run: () => palShowNet(name, [...ids])}));
}
// go to the schematic (unless it is already showing), then light the net once the drawing is there
function palShowNet(name, sheetIds) {
  if (mainView() !== 'sch' && sideView() !== 'sch') go('workspace', 'sch');
  if (sheetIds.length && !sheetIds.includes(sheetId || (S.sheets[0] && S.sheets[0].id))) {
    sheetId = sheetIds[0];
    svgCache = {key: '', text: ''};
    render(true);
  }
  let tries = 40;
  const lit = () => {
    if (document.querySelector('#schwrap svg')) { if (typeof highlightNet === 'function') highlightNet(name); return; }
    if (--tries > 0) setTimeout(lit, 100);
  };
  lit();
}
function palFiles() {
  const out = [];
  for (const s of (S.sources || [])) out.push({g: 'Files', cls: 'm', label: s.name, d: 'Source', fields: [[s.name, 1]], run: () => openViewerSource(s.name)});
  for (const x of (S.exports || [])) out.push({g: 'Files', cls: 'm', label: x.name, d: 'Export', fields: [[x.name, 1]], run: () => openViewerExport(x.name)});
  return out;
}
// an action in the registry, run the way a button would run it
function palAct(label, act, data, kw) {
  if (!ACTIONS[act]) return null;
  return {g: 'Actions', label, fields: [[label, 1], [kw || '', .8]], run: async () => {
    const b = document.createElement('button');
    b.dataset.act = act;
    Object.assign(b.dataset, data || {});
    try { await ACTIONS[act](b, b.dataset, null); } catch (e) { /* api() already said it */ }
  }};
}
function palActions() {
  const theme = getThemePref();
  const mk = (label, fn, kw, d) => ({g: 'Actions', label, d, fields: [[label, 1], [kw, .8]], run: fn});
  return [
    palAct('Check stock', 'check-all', null, 'bom prices availability'),
    palAct('Generate OutJob', 'gen-outjob', null, 'altium outputs'),
    palAct('Export BOM (JLC)', 'export', {fmt: 'jlc'}, 'bom csv jlcpcb assembly'),
    mk(chatShown() ? 'Hide chat' : 'Show chat', () => toggleChat(), 'agent ask', 'Ctrl J'),
    mk(sideItem ? 'Close side sheet' : 'Open side sheet', () => toggleSide(), 'side by side split'),
    mk('Theme: System', () => setThemePref('system'), 'dark light appearance', theme === 'system' ? 'Current' : ''),
    mk('Theme: Light', () => setThemePref('light'), 'appearance', theme === 'light' ? 'Current' : ''),
    mk('Theme: Dark', () => setThemePref('dark'), 'appearance night', theme === 'dark' ? 'Current' : ''),
  ].filter(Boolean);
}

/* ---------- matching: exact > prefix > start of a word > inside > letters in order; every word must match ---------- */
function palTok(field, tok) {
  if (!field) return 0;
  const f = String(field).toLowerCase();
  if (f === tok) return 100;
  let i = f.indexOf(tok), best = 0;
  while (i !== -1 && best < 80) {
    if (i === 0) best = 80;
    else if (/[\s\-_/.,(]/.test(f[i - 1])) best = Math.max(best, 60);
    else best = Math.max(best, 40);
    i = f.indexOf(tok, i + 1);
  }
  if (best) return best;
  if (tok.length >= 3 && f.length <= 24) {   // letters in order in a short name, for "outjb" -> "OutJob"
    let at = 0;
    for (const ch of tok) { at = f.indexOf(ch, at); if (at === -1) return 0; at++; }
    return 10;
  }
  return 0;
}
function palScore(item, toks) {
  let total = 0;
  for (const t of toks) {
    let best = 0;
    for (const [text, w] of item.fields) best = Math.max(best, palTok(text, t) * w);
    if (!best) return 0;
    total += best;
  }
  return total;
}
function palSearch(q, all) {
  const toks = q.toLowerCase().split(/\s+/).filter(Boolean);
  const order = ['Go to', 'Parts', 'Nets', 'Files', 'Actions'];
  const groups = [];
  for (const g of order) {
    if (!toks.length && g !== 'Go to' && g !== 'Actions') continue;   // an empty box shows where to go and what to do
    const rows = all.filter(it => it.g === g).map((it, i) => ({it, i, s: toks.length ? palScore(it, toks) : 1})).filter(r => r.s > 0);
    rows.sort((a, b) => b.s - a.s || a.i - b.i);
    if (rows.length) groups.push([g, rows.slice(0, PAL_MAX).map(r => r.it)]);
  }
  return groups;
}

/* ---------- the box ---------- */
function palRow(it) {
  let label = it.label;
  if (it.refs && it.refs.length > 1) {
    const toks = pal.q.toLowerCase().split(/\s+/).filter(Boolean);
    const hit = it.refs.find(r => toks.some(t => r.toLowerCase().startsWith(t))) || it.refs[0];
    label = hit + ' +' + (it.refs.length - 1);
  }
  return `<span class="pl${it.cls ? ' ' + it.cls : ''}">${esc(label)}</span>${it.sub ? `<span class="sub">${esc(it.sub)}</span>` : ''}${it.d ? `<span class="d">${esc(it.d)}</span>` : ''}`;
}
function palDraw() {
  const groups = palSearch(pal.q, pal.all);
  let html = '', n = 0;
  pal.opts = [];
  for (const [g, items] of groups) {
    html += `<li class="g" role="presentation">${esc(g)}</li>`;
    for (const it of items) {
      html += `<li role="presentation"><button type="button" role="option" id="pal-o${n}" data-i="${n}" aria-selected="false">${palRow(it)}</button></li>`;
      pal.opts.push(it);
      n++;
    }
  }
  pal.ul.innerHTML = n ? html : `<li class="pe" role="presentation">No results for ${esc(pal.q)}</li>`;
  pal.idx = -1;
  palSelect(n ? 0 : -1);
}
function palSelect(i) {
  const n = pal.opts.length;
  if (!n) { pal.input.removeAttribute('aria-activedescendant'); return; }
  i = (i + n) % n;
  const prev = pal.ul.querySelector('[aria-selected="true"]');
  if (prev) prev.setAttribute('aria-selected', 'false');
  const cur = pal.ul.querySelector(`#pal-o${i}`);
  if (!cur) return;
  cur.setAttribute('aria-selected', 'true');
  pal.input.setAttribute('aria-activedescendant', cur.id);
  pal.idx = i;
  cur.scrollIntoView({block: 'nearest'});
}
function openPalette() {
  if (pal || !S) return;
  if (document.querySelector('dialog[open]')) return;
  if (typeof kitMenuClose === 'function') kitMenuClose();
  const scrim = document.createElement('div');
  scrim.className = 'palette-scrim';
  scrim.innerHTML = `<div class="palette" role="dialog" aria-modal="true" aria-label="Search">
    <input type="text" role="combobox" aria-expanded="true" aria-controls="pal-list" aria-autocomplete="list" aria-label="Search parts, nets, files and actions" placeholder="Search parts, nets, files, actions" autocomplete="off" spellcheck="false">
    <ul id="pal-list" role="listbox" aria-label="Results"></ul></div>`;
  const all = [...palGoTo(), ...palParts(), ...palNets(), ...palFiles(), ...palActions()];
  pal = {scrim, input: scrim.querySelector('input'), ul: scrim.querySelector('ul'), q: '', idx: -1, opts: [], all, opener: document.activeElement};
  document.body.appendChild(scrim);
  scrim.addEventListener('mousedown', e => { if (e.target === scrim) closePalette(); });
  pal.input.addEventListener('input', () => { pal.q = pal.input.value; palDraw(); });
  pal.input.addEventListener('keydown', palKey);
  pal.ul.addEventListener('mousemove', e => {
    const b = e.target.closest('[role="option"]');
    if (b && +b.dataset.i !== pal.idx) palSelect(+b.dataset.i);
  });
  pal.ul.addEventListener('click', e => {
    const b = e.target.closest('[role="option"]');
    if (b) palRun(+b.dataset.i);
  });
  palDraw();
  pal.input.focus();
}
function closePalette() {
  if (!pal) return;
  const {scrim, opener} = pal;
  pal = null;
  scrim.remove();
  if (opener && opener.isConnected && opener.focus) opener.focus();
  render();   // anything that was held back while the palette was open
}
function palRun(i) {
  const it = pal && pal.opts[i];
  if (!it) return;
  closePalette();
  setTimeout(() => { it.run(); }, 0);
}
function palKey(e) {
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closePalette(); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); palSelect(pal.idx + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); palSelect(pal.idx - 1); }
  else if (e.key === 'Enter') { e.preventDefault(); palRun(pal.idx); }
  else if (e.key === 'Tab') e.preventDefault();   // focus stays in the box
}
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    if (pal) closePalette(); else openPalette();
  }
});
onAct('palette', async () => { openPalette(); });
