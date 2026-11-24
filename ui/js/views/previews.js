/* PCB Advisor UI - schematic and layout previews: sheet tabs, a pan and zoom canvas, selection, net highlight.
   Picking a part or a net only toggles classes on the drawn picture (applyFocus, highlightNet); the SVG is never rebuilt for
   it, so the zoom and the pan stay. What is selected is shown by the inspector (inspector.js). */

const PV_MIN = 0.3, PV_MAX = 8;
let pvReveal = null;        // {kind: 'sch' | 'pcb', ref?, net?}: bring this into view as soon as its picture is drawn
let pvSchErr = '', pvPcbErr = '', pvSchBusy = '', pcbFetching = null;

/* ---------- zoom and pan ---------- */
const pvClamp = s => Math.max(PV_MIN, Math.min(PV_MAX, s));
// Zoom by `factor` and keep the point (px, py), measured from the canvas centre, where it is on screen.
function zoomAt(wrap, z, factor, px, py) {
  const s1 = pvClamp(z.scale * factor), k = s1 / z.scale;
  z.x = px - k * (px - z.x);
  z.y = py - k * (py - z.y);
  z.scale = s1;
  updateZoomTransform(wrap, z);
}
function applyZoom(a, b, c) {
  let wrap, z, factor;
  if (typeof a === 'string' || (a && a.nodeType)) {
    wrap = typeof a === 'string' ? document.getElementById(a) : a;
    z = b;
    factor = c;
  } else {
    z = a;
    factor = b;
    wrap = typeof c === 'string' ? document.getElementById(c) : c;
  }
  if (!wrap || !z) return;
  zoomAt(wrap, z, factor || 1, 0, 0);
}
function resetZoom(a, b) {
  let wrap, z;
  if (typeof a === 'string' || (a && a.nodeType)) {
    wrap = typeof a === 'string' ? document.getElementById(a) : a;
    z = b;
  } else {
    z = a;
    wrap = typeof b === 'string' ? document.getElementById(b) : b;
  }
  if (!wrap || !z) return;
  z.scale = 1;
  z.x = 0;
  z.y = 0;
  pvFitContent(wrap);
  updateZoomTransform(wrap, z);
}
/* Fit means the DRAWING fills the view, not the page it sits on: the picture's viewBox keeps its margins, so at scale 1 a small sheet
   took a fifth of the width. The viewBox is narrowed to the drawn content (plus a margin); the first one is kept to give back. */
function pvFitContent(wrap) {
  const svg = wrap && wrap.querySelector && wrap.querySelector('svg');
  if (!svg || !svg.viewBox || !svg.viewBox.baseVal || !svg.getBBox) return;
  try {
    if (!svg.dataset.vb0) { const v = svg.viewBox.baseVal; svg.dataset.vb0 = [v.x, v.y, v.width, v.height].join(' '); }
    const [x, y, w, h] = svg.dataset.vb0.split(' ').map(Number), b = svg.getBBox();
    if (!(b.width > 0 && b.height > 0 && w > 0 && h > 0)) return;
    if (b.width * b.height > 0.8 * w * h) { svg.setAttribute('viewBox', svg.dataset.vb0); return; }      // the drawing already fills it
    const m = 0.04 * Math.max(b.width, b.height);
    svg.setAttribute('viewBox', [Math.max(x, b.x - m), Math.max(y, b.y - m), Math.min(w, b.width + 2 * m), Math.min(h, b.height + 2 * m)].join(' '));
  } catch (err) { /* the picture stays as it is */ }
}
function updateZoomTransform(wrap, z) {
  if (!wrap) return;
  const svg = wrap.querySelector('svg');
  if (!svg) return;
  if (z.scale === 1 && z.x === 0 && z.y === 0) svg.style.transform = '';
  else svg.style.transform = `translate(${z.x}px, ${z.y}px) scale(${z.scale})`;
  svg.style.transformOrigin = 'center center';
}
const PV_HIT = 'g.part, g.net-label, g.power-port, g.port, g.pcb-comp, g.plan-group, rect.pad, line.track, path.track, g.via, text[data-net], button, a, input, select';
function initZoomPan(wrapId, zoomState) {
  const wrap = typeof wrapId === 'string' ? document.getElementById(wrapId) : wrapId;
  if (!wrap || wrap.dataset.zoomInited) return;
  wrap.dataset.zoomInited = '1';

  wrap.addEventListener('wheel', e => {
    e.preventDefault();
    const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    const r = wrap.getBoundingClientRect();
    zoomAt(wrap, zoomState, Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2);
  }, {passive: false});

  // a press on the empty canvas puts the keyboard here: + and - zoom, 0 fits, the arrows pan
  wrap.addEventListener('mousedown', e => {
    if (e.button === 0 && !(e.target.closest && e.target.closest(PV_HIT))) wrap.focus({preventScroll: true});
  });
  wrap.addEventListener('keydown', e => {
    if (e.target !== wrap || e.ctrlKey || e.metaKey || e.altKey) return;
    const step = {ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60]}[e.key];
    if (e.key === '+' || e.key === '=') zoomAt(wrap, zoomState, 1.25, 0, 0);
    else if (e.key === '-' || e.key === '_') zoomAt(wrap, zoomState, 0.8, 0, 0);
    else if (e.key === '0') resetZoom(wrap, zoomState);
    else if (step) { zoomState.x += step[0]; zoomState.y += step[1]; updateZoomTransform(wrap, zoomState); }
    else return;
    e.preventDefault();
  });

  const panHelperFn = (typeof window !== 'undefined' && window.attachPanHelper) || (typeof DiagramEditor !== 'undefined' && DiagramEditor.attachPanHelper);
  if (panHelperFn) {
    panHelperFn(wrap, {
      getPan: () => ({ x: zoomState.x, y: zoomState.y }),
      setPan: (x, y) => {
        zoomState.x = x;
        zoomState.y = y;
        updateZoomTransform(wrap, zoomState);
      },
      canPan: (e) => {
        // the middle and the right button always pan; the left button pans on the empty canvas only
        if (e.button === 2 || e.button === 1) return true;
        if (e.button === 0) {
          const interactive = e.target.closest && e.target.closest('g.part, g.net-label, g.power-port, g.port, g.pcb-comp, g.plan-group, rect.pad, line.track, path.track, g.via, text[data-net], button, a, input, select');
          return !interactive;
        }
        return false;
      },
      onDown: (e) => {
        zoomState.dragging = true;
        zoomState.didDrag = false;
        zoomState.downX = e.clientX;
        zoomState.downY = e.clientY;
        zoomState.startX = e.clientX - zoomState.x;
        zoomState.startY = e.clientY - zoomState.y;
      },
      onDragStart: () => {
        zoomState.didDrag = true;
      },
      onUp: (e, { didDrag }) => {
        zoomState.dragging = false;
        if (didDrag) {
          zoomState.didDrag = true;
        }
      }
    });
  }
}
// Move and zoom so that the elements are in the middle of the canvas, with a short transition.
// The inspector is a drawer over the right edge of the sheet. What it covers of the canvas is not part of the view.
function pvViewport(wrap) {
  const w = wrap.getBoundingClientRect(), d = $('#detail');
  let right = w.right;
  if (d && !d.hidden) { const r = d.getBoundingClientRect(); if (r.width && r.left > w.left + 120 && r.left < w.right) right = r.left; }
  return {left: w.left, top: w.top, width: right - w.left, height: w.height, right, center: {x: w.left + w.width / 2, y: w.top + w.height / 2}};
}
function revealElements(wrap, z, els, wide) {
  const rects = els.map(el => el.getBoundingClientRect()).filter(r => r.width || r.height);
  const svg = wrap && wrap.querySelector('svg');
  if (!rects.length || !svg) return;
  const u = {l: Math.min(...rects.map(r => r.left)), t: Math.min(...rects.map(r => r.top)), r: Math.max(...rects.map(r => r.right)), b: Math.max(...rects.map(r => r.bottom))};
  const v = pvViewport(wrap), s0 = z.scale;
  const fit = Math.min(v.width * 0.6 / Math.max((u.r - u.l) / s0, 1), v.height * 0.6 / Math.max((u.b - u.t) / s0, 1));
  const s1 = pvClamp(Math.min(fit, wide ? 4 : 2.5)), k = s1 / s0;
  const px = (u.l + u.r) / 2 - v.center.x, py = (u.t + u.b) / 2 - v.center.y;
  // the point to bring to the middle of the free area, measured from the middle of the canvas
  const tx = (v.left + v.width / 2) - v.center.x;
  z.x = tx - k * (px - z.x);
  z.y = -k * (py - z.y);
  z.scale = s1;
  svg.style.transition = 'transform .28s ease';
  updateZoomTransform(wrap, z);
  setTimeout(() => { svg.style.transition = ''; }, 320);
}
// After something is picked on the drawing: if the inspector opens over it, slide the drawing aside. The zoom stays.
function pvKeepClear() {
  for (const kind of ['sch', 'pcb']) {
    const wrap = pvVisible(kind), svg = wrap && wrap.querySelector('svg');
    if (!svg) continue;
    const els = [...svg.querySelectorAll('g.part.sel, g.pcb-comp.sel, g.plan-group.sel, .hl-net')];
    const rects = els.map(el => el.getBoundingClientRect()).filter(r => r.width || r.height);
    if (!rects.length) continue;
    const v = pvViewport(wrap), z = kind === 'sch' ? schZoom : pcbZoom;
    const l = Math.min(...rects.map(r => r.left)), r = Math.max(...rects.map(r => r.right));
    const t = Math.min(...rects.map(r => r.top)), b = Math.max(...rects.map(r => r.bottom));
    let dx = 0, dy = 0;
    if (r > v.right - 16) dx = Math.max(-(r - (v.right - 24)), -(l - (v.left + 16)));      // out of the free area, to the right
    if (l < v.left + 8) dx = (v.left + 24) - l;
    const w = wrap.getBoundingClientRect();
    if (t < w.top + 8) dy = (w.top + 24) - t;
    else if (b > w.bottom - 8) dy = -(b - (w.bottom - 24));
    if (!dx && !dy) continue;
    z.x += dx; z.y += dy;
    svg.style.transition = 'transform .22s ease';
    updateZoomTransform(wrap, z);
    setTimeout(() => { svg.style.transition = ''; }, 260);
  }
}

/* ---------- selection and net highlight (class toggles only) ---------- */
function pvSelRefs() {
  const l = sel && lineByKey(sel);
  if (l) return new Set(l.refs || []);
  if (selThing && selThing.kind === 'ref') return new Set([selThing.ref]);
  return null;
}
const pvSvgs = () => ['#schwrap svg', '#pcbwrap svg'].map(s => $(s)).filter(Boolean);
function highlightNet(net) {
  for (const svg of pvSvgs()) {
    svg.querySelectorAll('.hl-net').forEach(el => el.classList.remove('hl-net'));
    svg.classList.toggle('netfocus', !!net);
    if (net) svg.querySelectorAll('[data-net]').forEach(el => { if (el.dataset.net === net) el.classList.add('hl-net'); });
  }
}
function applyFocus() {
  if (typeof inspNormalize === 'function') inspNormalize();
  const refs = pvSelRefs();
  const net = !refs && selNet ? selNet : null;
  const zone = selThing && selThing.kind === 'zone' ? selThing.name : null;
  const sch = $('#schwrap svg') || $('#sch');
  if (sch) {
    sch.classList.toggle('focus', !!refs);
    sch.querySelectorAll('g.part').forEach(g => g.classList.toggle('sel', !!refs && refs.has(g.dataset.ref)));
  }
  const pcb = $('#pcbwrap svg');
  if (pcb) {
    pcb.classList.toggle('focus', !!refs);
    pcb.querySelectorAll('g.pcb-comp').forEach(g => g.classList.toggle('sel', !!refs && refs.has(g.dataset.ref)));
    pcb.querySelectorAll('rect.pad').forEach(p => p.classList.toggle('sel', !!refs && refs.has(p.dataset.ref)));
    pcb.querySelectorAll('g.plan-group').forEach(g => g.classList.toggle('sel', !!zone && g.dataset.group === zone));
  }
  highlightNet(net);
}
// what the inspector's lists call to bring something into view in a preview that is open
function pvVisible(kind) {
  const w = $(kind === 'sch' ? '#schwrap' : '#pcbwrap');
  return w && w.querySelector('svg') ? w : null;
}
function pvRunReveal(kind) {
  const r = pvReveal;
  if (!r || r.kind !== kind) return;
  const wrap = pvVisible(kind);
  if (!wrap) return;                       // not drawn yet: afterSheet / afterPcb ask again
  pvReveal = null;
  const svg = wrap.querySelector('svg');
  const els = r.net ? [...svg.querySelectorAll('.hl-net')]
    : [...svg.querySelectorAll(kind === 'sch' ? 'g.part' : 'g.pcb-comp')].filter(g => g.dataset.ref === r.ref);
  revealElements(wrap, kind === 'sch' ? schZoom : pcbZoom, els, !!r.net);
}
function revealNet(net) {
  for (const kind of ['sch', 'pcb']) if (pvVisible(kind)) { pvReveal = {kind, net}; pvRunReveal(kind); }
}
function revealRef(ref) {
  for (const kind of ['sch', 'pcb']) if (pvVisible(kind)) { pvReveal = {kind, ref}; pvRunReveal(kind); }
}
function pvSetSheet(id) {
  if (!id || id === sheetId) return false;
  sheetId = id;
  svgCache = {key: '', text: ''};
  pvSchErr = '';
  schZoom.scale = 1; schZoom.x = 0; schZoom.y = 0;
  updateZoomTransform($('#schwrap'), schZoom);
  return true;
}
function showOnSchematic(key, sheet, ref) {
  const l = key ? lineByKey(key) : null;
  if (l) { selNet = null; selThing = null; sel = key; }
  const r = ref || (l ? (l.refs || [])[0] : '') || '';
  let sh = sheet || '';
  if (!sh && l) { const w = sheetsOfLine(l).find(x => x.ref === r) || sheetsOfLine(l)[0]; sh = (w && w.sheet) || l.sheet || ''; }
  if (sh && !(S.sheets || []).some(s => s.id === sh)) sh = '';
  pvReveal = {kind: 'sch', ref: r};
  if (!inspViews().includes('sch')) { pvSetSheet(sh); go('workspace', 'sch'); return; }
  if (pvSetSheet(sh)) { renderCenter(true); return; }
  applyFocus(); renderDetail(); pvRunReveal('sch');
}
function showOnLayout(key, ref) {
  const l = key ? lineByKey(key) : null;
  if (l) { selNet = null; selThing = null; sel = key; }
  pvReveal = {kind: 'pcb', ref: ref || (l ? (l.refs || [])[0] : '') || ''};
  if (!inspViews().includes('pcb')) { go('workspace', 'pcb'); return; }
  applyFocus(); renderDetail(); pvRunReveal('pcb');
}
function showNetOnSchematic(net) {
  pvReveal = {kind: 'sch', net};
  go('workspace', 'sch');
}

/* ---------- clicks on the drawn picture: one delegate per canvas ---------- */
function pvTarget(el, kind) {
  return el && el.closest ? el.closest(kind === 'sch' ? 'g.part, g.net-label, g.power-port, g.port, text[data-net]' : 'g.pcb-comp, rect.pad, g.plan-group, line.track, path.track, g.via') : null;
}
function pvActivate(t, kind) {
  if (t.matches('g.part, g.pcb-comp')) { pickPart(t.dataset.ref || (t.id || '').replace(/^pcb-comp-/, ''), kind === 'sch' ? sheetId : ''); return; }
  if (t.matches('g.plan-group')) { pickZone(t.dataset.group); return; }
  const net = t.dataset.net || t.dataset.port || (t.textContent || '').trim();
  if (net) pickNet(net);
}
function pvBind(wrap, kind) {
  if (wrap.dataset.pvBound) return;
  wrap.dataset.pvBound = '1';
  const z = kind === 'sch' ? schZoom : pcbZoom;
  wrap.addEventListener('click', e => {
    if (z.didDrag) return;                                  // the click that ends a pan
    const t = pvTarget(e.target, kind);
    if (t) { e.stopPropagation(); pvActivate(t, kind); return; }
    if (sel || selNet || selThing) closeInspector();        // the empty canvas clears the selection
  });
  wrap.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const t = pvTarget(e.target, kind);
    if (t && t === e.target) { e.preventDefault(); pvActivate(t, kind); }
  });
}
function pvLabel(ref) {
  const l = lineOfRef(ref);
  return l ? `${ref}, ${l.value || l.mpn || ''}`.replace(/, $/, '') : ref;
}

/* ---------- schematic ---------- */
/* A sheet's name is its title, not its file: a sheet only Altium has is named by its file ("Main"), but when the plan has the sheet of
   that number the plan's title is the real one ("02 Power"). The file name stays in the tooltip. */
const pvSheetNum = s => (String(s.altium ? (s.file || s.id) : s.id).trim().match(/^\d+/) || [''])[0];
function pvSheetTitle(s) {
  if (s.title && s.title !== s.id && s.title !== String(s.id).replace(/\.schdoc$/i, '')) return s.title;
  const n = s.altium ? pvSheetNum(s) : '';
  const plan = n ? ((S && S.sheets) || []).find(x => !x.altium && pvSheetNum(x) === n && x.title && x.title !== x.id) : null;
  return plan ? plan.title : '';
}
const pvSheetLabel = s => { const base = String(s.id).replace(/\.schdoc$/i, ''), t = pvSheetTitle(s); return t ? `${base} ${t}` : base; };
/* The plan sheet (netlist preview) and the sheet read from Altium can carry the same name: when both exist they are
   "01 Plan" and "01 Altium"; the full name stays as the tooltip. */
function pvTabLabel(s, all) {
  if (!(all || []).some(x => x.altium) || !(all || []).some(x => !x.altium)) return pvSheetLabel(s);
  const num = (String(s.altium ? (s.file || s.id) : s.id).trim().match(/^\S+/) || [''])[0].replace(/\.schdoc$/i, '');
  return `${num} ${s.altium ? 'Altium' : 'Plan'}`;
}
const pvZoomHTML = kind => `<div class="pv-zoom" role="group" aria-label="Zoom">` +
  btn('', {icon: 'zoomout', size: 'sm', title: 'Zoom out', act: kind + '-zoom-out'}) +
  btn('', {icon: 'zoomin', size: 'sm', title: 'Zoom in', act: kind + '-zoom-in'}) +
  btn('Fit', {icon: 'fit', size: 'sm', title: 'Fit the drawing to the view', act: kind + '-zoom-fit'}) + '</div>';

/* ---------- the Altium step buttons: the click is the consent (the agent asks in words instead) ---------- */
const PV_STEPS = {
  draw: {url: '/api/altium/draw-schematic', page: 'sch', doing: 'Drawing', ask: 'Replacing redraws every sheet that already has a drawing, from the netlist; each file as it is now is copied to .advisor-backup first.', label: 'Draw in Altium', again: 'Replace the existing drawing', busy: 'Altium is drawing the schematic. It may take a minute and flash while it works.',
         title: 'Altium draws the netlist on the schematic sheet, with the parts from the project library, and the saved sheet is checked against the netlist. Any file it changes is copied to .advisor-backup first.'},
  place: {url: '/api/altium/place', page: 'pcb', doing: 'Placing', ask: 'Replacing removes the parts and copper on the board and places again; the file as it is now is copied to .advisor-backup first.', label: 'Place parts', again: 'Replace the existing placement', busy: 'Altium is placing the parts. It may take a minute and flash while it works.',
          title: 'Altium places the parts of the netlist on the PcbDoc, and makes the board outline from the board size when there is none. The saved board is checked. The PcbDoc is copied to .advisor-backup first.'},
  route: {url: '/api/altium/route', page: 'pcb', doing: 'Routing', ask: 'Replacing removes the tracks, vias and pours and routes again; the file as it is now is copied to .advisor-backup first.', label: 'Route board', again: 'Replace the existing routes', busy: 'Altium is routing the board. Routing can take a couple of minutes and Altium will flash while it works.',
          title: 'Draws the tracks and vias on the placed board, plus a ground pour when it can, then checks the result with the design rule check. The PcbDoc is copied to .advisor-backup before it draws, and put back if a check fails.'},
  drc: {url: '/api/altium/drc', page: 'pcb', doing: 'Checking', label: 'Check board', busy: 'Altium is checking the board against every design rule. It may take a minute and flash while it works.',
         title: "Runs Altium's design rule check on the PcbDoc and keeps the answer. Nothing on the board is changed."},
  /* Rules (Rules page) and outputs (Outputs page) run the same machinery: the live list, Stop, and the answer after a reload. They never replace. */
  rules: {url: '/api/altium/import-rules', page: 'rules', doing: 'Applying', label: 'Apply rules in Altium', busy: 'Altium is applying the rules. It may take a minute and flash while it works.',
          title: 'Puts these rules into the linked PcbDoc by name; your own rules stay. The PcbDoc is copied to .advisor-backup first.',
          after: () => { if (typeof loadRules === 'function') loadRules(true); }},
  outputs: {url: '/api/altium/run-outjob', page: 'outputs', doing: 'Generating', label: 'Generate outputs in Altium', busy: 'Altium is generating the outputs. It may take a minute and flash while it works.',
            title: 'Altium runs the project OutJob: Gerber, NC drill, BOM and pick and place go into its outputs folder. Ours is added to the project first when it has none.',
            after: () => { if (typeof outLoadAlt === 'function') outLoadAlt(); }},
};
/* The board's own design rule check as one sentence and one tone, from S.board_check (the server keeps it): the Rules header and the
   Layout page's note both say it, so a reload or a dismissed note does not lose it. */
function drcSummary(c) {
  // the server stamps records with an ISO time (store.now_ms); a bare number is epoch ms. outAgo says '' for anything it cannot read.
  const when = c && c.ts && typeof outAgo === 'function' ? outAgo(/^\d+$/.test(String(c.ts)) ? new Date(Number(c.ts)).toISOString() : String(c.ts)) : '';
  let tone = '', text;
  if (!c) text = 'Board DRC: not run yet';
  else if (c.complete === false) { tone = 'warn'; text = 'Board DRC: the report was incomplete, run it again'; }
  else if (c.total) { tone = 'bad'; text = `Board DRC: ${plural(c.total, 'violation')}`; }
  else { tone = c.stale ? 'warn' : 'ok'; text = 'Board DRC: clean'; }
  if (c && c.stale) { tone = tone === 'ok' ? 'warn' : tone; text += ', but the board changed since: check it again'; }
  else if (c && when) text += ', ' + when;
  return {tone, text};
}
const pvSeedGone = {};       // page -> the board_check ts whose seeded note was dismissed
function pvSeedNote(page) {       // after a reload there is no note in memory: the last board check is the one on the Layout page
  const c = page === 'pcb' && S && S.board_check;
  if (!c || pvSeedGone[page] === c.ts) return null;
  const s = drcSummary(c);
  return {kind: s.tone || 'ok', text: s.text + '.', warnings: [], seeded: true};
}
let pvBusy = '';             // the step Altium is working on now: its line stays on the page until the answer comes
let pvNote = {};             // page ('sch' | 'pcb') -> {kind, text, warnings, replace}: what the last step answered, kept until dismissed
const PV_PREP = {'library.build': 'built the library', 'altium.add_pcb': 'added a PcbDoc', 'altium.import_rules': 'imported the JLC rules', 'outjob.generate': 'added the OutJob'};
let pvStartedAt = 0;         // when the step on screen began (ms): the server's start when it says one, else the click
/* "1:05": the time since the step began. Altium can work for minutes without a word, so the line says how long it has been. */
const pvClock = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const pvElapsedHTML = () => `<span class="pv-elapsed muted" aria-hidden="true">${pvClock(Date.now() - (pvStartedAt || Date.now()))}</span>`;
setInterval(() => {       // only the clock text is touched: the page is not redrawn once a second
  if (!pvBusy) return;
  const t = pvClock(Date.now() - (pvStartedAt || Date.now()));
  document.querySelectorAll('.pv-elapsed').forEach(el => { if (el.textContent !== t) el.textContent = t; });
}, 1000);
let pvStopping = false;      // Stop was pressed for the run on screen; the run ends before its next step
const pvPrepNames = r => (r.prepared || []).map(x => PV_PREP[String(x).split(':')[0]]).filter(Boolean).join(' and ');
let pvTimer = null, pvRun = null, pvRunSig = '', pvResumed = false;       // pvRun: what the server says about the run in progress (its list of steps)
function pvPollStart(resumed) {       // while a step runs: ask the server how far it is, about every 1.5 s; a failed read is ignored
  if (pvTimer) return;
  pvTimer = setInterval(async () => {
    if (!pvBusy) { pvPollStop(); return; }
    let r = null;
    try { r = await api('/api/altium/step-status' + (resumed ? '?take=1' : ''), undefined, {soft: true}); } catch (err) { return; }
    if (!pvBusy || !pvTimer || !r) return;
    if (r.running) {
      const sig = JSON.stringify((r.steps || []).map(x => x.state)) + (r.stopping ? 'stopping' : '');
      pvRun = r;
      if (r.started && !pvStartedAt) pvStartedAt = r.started * 1000;
      if (r.stopping) pvStopping = true;
      if (sig !== pvRunSig) { pvRunSig = sig; renderCenter(true); }          // only when a step changed: the picture is not redrawn for nothing
    } else if (resumed) {        // a reloaded page: the run ended. Its answer is here, or the page that started it already took it
      const step = pvBusy;
      pvPollStop();
      await pvFinish(step, r.step ? r : {gone: true}, false);
    }
  }, 1500);
}
function pvPollStop() { if (pvTimer) clearInterval(pvTimer); pvTimer = null; pvRun = null; pvRunSig = ''; }
function pvAltiumLinked() {       // only when an Altium project is linked; the link is read once, then the view redraws
  if (!ALTIUM_DATA && !ALTIUM_ERR && typeof loadAltium === 'function') loadAltium().then(() => { if (ALTIUM_DATA && ALTIUM_DATA.linked) renderCenter(true); });
  return !!(ALTIUM_DATA && ALTIUM_DATA.linked && ALTIUM_DATA.linked.project_file);
}
function pvStepBtn(step, o) {       // o.disabled / o.title: the page can hold the button back with its reason (Outputs: unverified pins)
  const c = PV_STEPS[step];
  o = o || {};
  return pvAltiumLinked() ? btn(pvBusy === step ? c.doing : c.label, {kind: o.kind || 'line', act: 'altium-step', step, title: o.title || c.title, disabled: pvBusy || o.disabled ? true : undefined}) : '';
}
function pvStepText(st, i, all) {       // the words of one step of the live list
  return st.state === 'running' && i === all.length - 1 ? PV_STEPS[pvBusy].busy : st.label + (st.state === 'done' && st.note ? ': ' + st.note : '');
}
function pvStepLine(st, i, all) {       // one line of the live list: done, running (spinner) or waiting; the step itself keeps its long hint
  const text = esc(pvStepText(st, i, all));
  if (st.state === 'running') return `<div class="loading" role="status"><span class="spin" aria-hidden="true"></span>${text} ${pvElapsedHTML()}</div>`;
  return `<div class="loading"><span aria-hidden="true">${st.state === 'done' ? '✓' : '&middot;'}</span>${text}${st.state === 'waiting' ? ' (waiting)' : st.state === 'stopped' ? ' (stopped)' : ''}</div>`;
}
function pvStopBtn() {       // the run stops before its next step; the last step is one Altium operation that cannot be cut
  const st = (pvRun && pvRun.steps) || [];
  const last = st.length && st[st.length - 1].state === 'running';
  // nothing left to stop (the one operation Altium is on is the last): no dead button for the whole step, a line that says why instead
  if (last && !pvStopping) return '<span class="muted pv-nostop">This step cannot be cut short. It ends by itself.</span>';
  return btn(pvStopping ? 'Stopping…' : 'Stop', {size: 'sm', kind: 'line', act: 'altium-step-stop', disabled: pvStopping ? true : undefined,
    title: 'Ends the run before its next step. The step Altium is working on finishes first.'});
}
const PV_LOG_OP = {draw: 'draw-schematic', place: 'place-pcb', route: 'route-pcb'};
/* A failure note is a message about a cause. When the cause is gone from the current state the note goes, with no click (E16):
   "There is no netlist sheet to draw" only while there is none; "Sheet 03 cannot be drawn" only while that sheet is there as it was
   when the draw refused it (a changed or removed sheet is a new question the next draw answers). pvNoteCause reads the cause once, from the
   words, and keeps what it was about; pvCauseGone looks at the state now. */
const pvNetlistSheets = () => (S && S.sheets || []).filter(x => !x.altium);
const pvSheetSig = id => { const x = pvNetlistSheets().find(y => String(y.id) === String(id)); return x ? JSON.stringify([x.sections, x.parts]) : ''; };
function pvNoteCause(n) {
  if (!n || n.cause !== undefined) return n;
  const t = String(n.text || '');
  if (n.kind === 'ok') n.cause = null;
  else if (/There is no netlist sheet to draw/.test(t)) n.cause = {kind: 'no_netlist'};
  else {
    const ids = [...t.matchAll(/Sheet (\S+) cannot be drawn/g)].map(m => m[1]);
    n.cause = ids.length ? {kind: 'sheets', sigs: Object.fromEntries(ids.map(id => [id, pvSheetSig(id)]))} : null;
  }
  return n;
}
function pvCauseGone(n) {
  const c = n && n.cause;
  if (!c || !S) return false;
  if (c.kind === 'no_netlist') return pvNetlistSheets().some(x => Object.keys(x.parts || {}).length);
  if (c.kind === 'sheets') return Object.entries(c.sigs).every(([id, sig]) => pvSheetSig(id) !== sig);
  return false;
}
function pvLaterOk(n) {        // the same step succeeded after this note was made: the note is stale
  const ok = (S && S.altium_ok) || {}, t = n.step && ok[PV_LOG_OP[n.step]];
  if (!(t && n.at && new Date(t).getTime() > n.at)) return false;
  if (n.step !== 'draw') return true;
  const named = [...String(n.text || '').matchAll(/Sheet (\S+) cannot be drawn/g)].map(m => m[1]);
  if (!named.length) return true;                  // the note names no sheet: any good draw answers it
  const drawn = (ok.draw_sheets || []).filter(d => new Date(d.ts).getTime() > n.at).flatMap(d => d.sheets);
  return named.every(id => drawn.some(st => st === id || st.startsWith(id + ' ')));      // a draw of other sheets leaves it standing
}
/* slim: the schematic and layout pages show this on the canvas (pvBarHTML): the run is ONE status line (pvRunSlim) that opens to the full
   list, and the answer is a compact banner. Rules and Outputs call it without slim: the full list under their header. */
function pvStepNote(page, busyOnly, slim) {       // under the header: Altium is working, or what the last step answered
  pvResume();
  const list = pvRun && pvRun.running && (pvRun.steps || []).length > 1 ? `<div class="pv-steps">${pvRun.steps.map(pvStepLine).join('')}</div>` : '';
  const busy = pvBusy && PV_STEPS[pvBusy].page === page && slim ? pvRunSlim() : pvBusy && PV_STEPS[pvBusy].page === page ? `<div class="pv-note">${list || `<div class="loading" role="status"><span class="spin" aria-hidden="true"></span>${esc(PV_STEPS[pvBusy].busy)} ${pvElapsedHTML()}</div>`}<div class="acts">${pvStopBtn()}</div></div>` : '';
  if (pvNote[page] && pvNote[page].kind !== 'ok' && (pvLaterOk(pvNote[page]) || pvCauseGone(pvNote[page]))) delete pvNote[page];
  const n = pvNote[page] || pvSeedNote(page);
  if (busy || !n || busyOnly) return busy;
  const acts = (n.partial ? btn('Route the rest and leave ' + n.partial.join(', ') + ' open', {size: 'sm', kind: 'line', act: 'altium-step', step: 'route', partial: '1', disabled: pvBusy ? true : undefined,
      title: 'Routes every net that can be routed, keeps those tracks, and leaves ' + n.partial.join(', ') + ' unrouted for you to finish in Altium'}) : '') +
    (n.replace ? btn(PV_STEPS[n.replace].again, {size: 'sm', kind: 'line', act: 'altium-step', step: n.replace, replace: '1', disabled: pvBusy ? true : undefined}) : '') +
    btn(n.replace ? 'Keep it' : 'Dismiss', {size: 'sm', kind: n.replace ? 'pri' : 'line', act: 'altium-step-dismiss', page});
  const c = pvCompact(n.text, n.from === 999 ? [] : n.warnings || []);
  const op = k => pvMoreOpen[page + ':' + k] ? ' open' : '';
  const more = c.warnings.length ? `<details class="pv-more" data-pvk="${page}:w"${op('w')}><summary>Show ${c.warnings.length} ${c.warnings.length === 1 ? 'warning' : 'warnings'}</summary><ul>${c.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul></details>` : '';
  const rest = c.rest ? `<details class="pv-more" data-pvk="${page}:r"${op('r')}><summary>Show details</summary><p>${esc(c.rest)}</p></details>` : '';
  const alerts = c.alerts.map(w => `<br>Warning: ${esc(w)}`).join('');
  return `<div class="pv-note">${banner({tone: n.kind, html: `${esc(c.head)}${alerts}${rest}${more}`, actions: acts})}</div>`;
}
let pvRunOpen = false;       // the full list of the run on screen is open under its status line (kept across redraws)
const pvFirstSentence = t => String(t).split(/(?<=\.)\s/)[0];
/* The run as ONE status line: what Altium is on now, its clock, "N more" for the steps still waiting, and Stop. Finished steps are not
   in the line; the toggle opens the whole list (done, running, waiting) under it. The long hint of the step is the tooltip and the list. */
function pvRunSlim() {
  const st = pvRun && pvRun.running ? pvRun.steps || [] : [], multi = st.length > 1;
  let i = multi ? st.findIndex(x => x.state === 'running') : -1;
  if (multi && i < 0) i = st.findIndex(x => x.state === 'waiting');
  if (multi && i < 0) i = st.length - 1;
  const full = multi ? pvStepText(st[i], i, st) : PV_STEPS[pvBusy].busy, waiting = st.filter(x => x.state === 'waiting').length;
  const done = st.filter(x => x.state === 'done').length;
  const label = waiting ? waiting + ' more' : multi ? 'All steps' : 'Details';
  const toggle = btn(label, {size: 'sm', kind: 'link', iconAfter: pvRunOpen ? 'chevu' : 'chev', act: 'pv-run-toggle', 'aria-expanded': String(pvRunOpen),
    title: multi ? `${plural(waiting, 'step')} waiting${done ? ', ' + done + ' done' : ''}. Show every step of this run.` : 'Show the whole line.'});
  const body = pvRunOpen ? `<div class="pv-steps">${multi ? st.map(pvStepLine).join('') : `<div class="loading">${esc(full)}</div>`}</div>` : '';
  return `<div class="pv-note pv-run"><div class="pv-run-line"><div class="loading" role="status" title="${esc(full)}"><span class="spin" aria-hidden="true"></span>` +
    `<span class="pv-run-txt">${esc(pvFirstSentence(full))}</span> ${pvElapsedHTML()}</div>${toggle}<div class="acts">${pvStopBtn()}</div></div>${body}</div>`;
}
/* The floating bar at the top of a canvas: the status of the step and its answer on the left, the layer switches on the right. It sits
   over the drawing, so the drawing keeps the whole height; its right edge keeps clear of the inspector drawer (previews.css). */
function pvBarHTML(page, extra) {
  const note = pvStepNote(page, false, true);
  return note || extra ? `<div class="pv-bar">${note ? `<div class="pv-bar-main">${note}</div>` : ''}${extra || ''}</div>` : '';
}
/* The layer switches: one "Layers" button on the canvas that opens the list (a checkbox look, the same buttons and toggle-layer as ever).
   The summary says how many are hidden, so a hidden layer is never a mystery. */
function pvLayersHTML(layers) {
  const hidden = layers.filter(l => !pcbLayers[l.value]).length, on = layers.filter(l => pcbLayers[l.value]).map(l => l.value);
  return `<details class="pv-layers" data-pvk="pcb:layers"${pvMoreOpen['pcb:layers'] ? ' open' : ''}><summary title="Show or hide the layers of the board">${icon('layers', 's')}<span>Layers</span>` +
    `<span class="pv-lhid"${hidden ? '' : ' hidden'}>${hidden} hidden</span></summary>${seg(layers, on, {act: 'toggle-layer', label: 'Layers'})}</details>`;
}
const pvMoreOpen = {};       // which "Show ..." toggles of the step notes are open, kept across redraws
document.addEventListener('toggle', e => { const k = e.target && e.target.dataset && e.target.dataset.pvk; if (k) pvMoreOpen[k] = e.target.open; }, true);
/* One summary for a step's note. The head keeps what matters: the first sentence, Altium's own check, the DRC line reduced to the rules
   with violations (and the total), and a partial route's open nets. The "(N warnings: ...)" tail moves into the warnings list (placement
   errors stay in the head), the other segments go behind "Show details". Nothing is dropped, so the board preview keeps its size.
   The two regexes are read by tests/test_ui_findings.py, which runs the same logic on the real strings. */
const PV_TAIL_RE = /\s*\((\d+) warnings?: ([^]*)\)\.?\s*$/;
const PV_DRC_RE = /(Altium DRC(?:, every rule)?: )((?:[A-Za-z][^,()]*(?:\([^,()]*\))? \d+, )+total \d+)( \(clean\))?/g;
function pvSegments(t) {       // split at "; " outside brackets: a parenthesis may hold a "; " of its own
  const out = [];
  let depth = 0, from = 0;
  for (let i = 0; i < t.length; i++) {
    if (t[i] === '(') depth++;
    else if (t[i] === ')') depth = Math.max(0, depth - 1);
    else if (depth === 0 && t[i] === ';' && t[i + 1] === ' ') { out.push(t.slice(from, i)); from = i + 2; }
  }
  out.push(t.slice(from));
  return out;
}
function pvCompact(text, warnings) {
  let t = String(text || '');
  let warns = (warnings || []).map(String);
  const tail = t.match(PV_TAIL_RE);
  if (tail) { t = t.slice(0, tail.index); if (!warns.length) warns = tail[2].split('; ').filter(Boolean); }
  const alerts = warns.filter(w => w.startsWith('placement error'));
  warns = warns.filter(w => !w.startsWith('placement error'));
  t = t.replace(PV_DRC_RE, (m, lead, list, clean) => {
    const items = list.split(', '), total = items.pop();
    const bad = items.filter(i => !/ 0$/.test(i));
    return lead + (bad.length ? bad.join(', ') + ', ' + total : clean ? 'clean' : total);
  });
  const segs = pvSegments(t);
  if (segs.length > 1) {
    const keep = (x, i) => i === 0 || /^own check|Altium DRC|^PARTIAL ROUTE/.test(x);
    return {head: segs.filter(keep).join('; '), rest: segs.filter((x, i) => !keep(x, i)).join('; '), warnings: warns, alerts};
  }
  const max = 220;
  if (t.length <= max) return {head: t, rest: '', warnings: warns, alerts};
  const sp = t.lastIndexOf(' ', max);
  return {head: t.slice(0, sp) + ' ...', rest: t.slice(sp).trim(), warnings: warns, alerts};
}
async function pvRunStep(step, replace, partial) {
  const c = PV_STEPS[step];
  if (pvBusy) return;
  pvBusy = step;
  pvStartedAt = Date.now();
  delete pvNote[c.page];
  renderCenter(true);
  pvPollStart(false);
  let r = null, lost = false;
  try { r = await api(c.url, partial ? {replace: !!replace, keep_partial: true} : {replace: !!replace}, {soft: true}); } catch (err) { lost = true; }
  pvPollStop();
  await pvFinish(step, r, lost);
}
async function pvFinish(step, r, lost) {       // the answer of a step (from its own POST, or read after a reload): the note, then the pages read again
  const at0 = Date.now();
  const c = PV_STEPS[step];
  pvBusy = '';
  pvStartedAt = 0;
  pvStopping = false;
  const first = r && r.done_first ? r.done_first + ' ' : '';        // a preparation ran and then the step itself stopped
  if (r && r.needs_replace) {
    // never replaced without a second click: the note says what is there and offers it. The first sentence says what is there; the rest is worded for the chat
    const found = r.error.replace(/^Altium refused a step: /, '').replace(/; nothing was changed[^]*$/, '').split('. ')[0].replace(/\.$/, '');       // without the script's own step log
    pvNote[c.page] = {kind: 'warn', text: first + found.charAt(0).toUpperCase() + found.slice(1) + '. ' + c.ask, replace: step};
  } else {
    if (lost) pvNote[c.page] = {kind: 'bad', text: 'Lost contact with the server while Altium was working. The step may still be running or may have finished: look at the board in Altium, and at the chat for its result, before starting it again.'};
    else if (r && r.gone) pvNote[c.page] = {kind: 'warn', text: 'The step ended while this page was loading, and its answer went to the page that started it. Look at the board in Altium, and at the chat, before starting it again.'};       // ended, not "succeeded": this page never saw the answer
    else if (r && r.stopped) pvNote[c.page] = {kind: 'warn', stopped: true, text: (pvPrepNames(r) ? 'Altium ' + pvPrepNames(r) + '. ' : '') + r.message};       // Stop: "Stopped after <step>; nothing after it ran."
    else if (!r || r.error) pvNote[c.page] = {kind: 'bad', text: first + ((r && r.error) || 'no answer from the server'), partial: r && Array.isArray(r.partial_offer) && r.partial_offer.length ? r.partial_offer : undefined};
    else pvNote[c.page] = {kind: (r.warnings || []).length ? 'warn' : 'ok', text: 'Altium: ' + (pvPrepNames(r) ? pvPrepNames(r) + ', then: ' : '') + (r.summary || 'done.'), warnings: r.warnings || [], from: c.page === 'outputs' ? 0 : c.page === 'rules' ? 999 : undefined};       // outputs: all warnings are listed; rules: the summary already says each one, so the list adds none
    if (pvNote[c.page]) { pvNote[c.page].step = step; pvNote[c.page].at = at0; }       // lets a later success (by button or chat) retire a failure note
    // a step that failed may still have changed a file (a drawing that does not match the netlist stays on disk): always read again
    try { await refresh(true); } catch (err) { /* the note still says what happened */ }
    if (pvNote[c.page]) pvNoteCause(pvNote[c.page]);       // the cause as the fresh state shows it: the note leaves when that changes (E16)
    if (typeof loadAltium === 'function') loadAltium(true);      // a draw can add a sheet to the project
    svgCache = {key: '', text: ''}; pvSchErr = ''; pcbSvgCache = {key: '', text: ''}; pvPcbErr = '';       // the picture is read again
  }
  if (c.after) c.after();       // the Rules and Outputs pages read what Altium holds again
  renderCenter(true);
}
async function pvResume() {       // once per page load: a step started before a reload is still running, or has left its answer to read
  if (pvResumed) return;
  pvResumed = true;
  let r = null;
  try { r = await api('/api/altium/step-status?take=1', undefined, {soft: true}); } catch (err) { return; }
  if (pvBusy || !r || !PV_STEPS[r.step]) return;
  pvBusy = r.step;
  if (r.started) pvStartedAt = r.started * 1000;
  if (r.running) { pvRun = r; renderCenter(true); pvPollStart(true); }
  else await pvFinish(r.step, r, false);
}
onAct('altium-step', async (el, d, e) => {
  if (el.disabled || !PV_STEPS[d.step]) return;
  await pvRunStep(d.step, d.replace === '1', d.partial === '1');
});
onAct('altium-step-stop', async (el, d, e) => {       // the run ends before its next step; the answer arrives through the same path as any run
  if (!pvBusy || pvStopping) return;
  pvStopping = true;
  renderCenter(true);
  try {
    const r = await api('/api/altium/step-stop', {}, {soft: true});
    if (r && r.error) { pvStopping = false; renderCenter(true); }       // 409: it had ended already; its answer is on the way
  } catch (err) { pvStopping = false; renderCenter(true); }
});
onAct('altium-step-dismiss', async (el, d, e) => {
  delete pvNote[d.page];
  if (S && S.board_check && d.page === 'pcb') pvSeedGone.pcb = S.board_check.ts;
  renderCenter(true);
});

const SCH_LIMITS = 'Not drawn automatically yet: a part whose library symbol is split into several separate blocks (for example a chip drawn as a power block and a signal block), and a circuit too big for one A4 sheet (it is refused with a plan to split it). Wires that run between two sheets are not drawn either. For these, draw that part by hand in Altium.';
const PCB_LIMITS = 'Not yet: the router is for small two-layer boards, with no differential pairs and no inner layers.';
const pvRealSheets = sheets => sheetCounts(sheets).total;       // the server's count (stage_sheets): the plan's sheets, else Altium's; one number on every page
function schHTML(container) {
  const sheets = S.sheets || [];
  if (!sheets.length) return `<div class="pv">${viewHeader({title: 'Schematic'})}${emptyState('No schematic yet', 'The agent draws the sheets once the parts are chosen.', '', SCH_LIMITS)}</div>`;
  if (!sheetId || !sheets.find(s => s.id === sheetId)) pvSetSheet(sheets[0].id);
  const fresh = svgCache.text && svgCache.key.startsWith(sheetId + '|');
  const inner = fresh ? svgCache.text
    : pvSchErr ? `<div class="pv-note">${errorLine('draw the schematic', pvSchErr, btn('Try again', {size: 'sm', act: 'sch-retry'}))}</div>`
    : `<div class="pv-note">${loadingLine('Drawing the schematic')}</div>`;
  const tabs = sheets.length > 1 ? `<div class="pv-tabs" role="tablist" aria-label="Sheets">${sheets.map(s =>
    `<button type="button" role="tab" class="pv-tab" aria-selected="${s.id === sheetId}" tabindex="${s.id === sheetId ? 0 : -1}" data-act="sch-sheet" data-sheet="${esc(s.id)}" title="${esc(pvSheetLabel(s) + (s.altium ? ' (read from Altium)' : ' (plan)'))}">${esc(pvTabLabel(s, sheets))}</button>`).join('')}</div>` : '';
  return `<div class="pv" data-pv="sch">` +
    viewHeader({title: 'Schematic', meta: metaLine([{n: pvRealSheets(sheets), label: pvRealSheets(sheets) === 1 ? 'sheet' : 'sheets'}]), actions: pvStepBtn('draw')}) + pvDraftNote() + (typeof outBlockNote === 'function' ? outBlockNote() : '') + tabs +
    `<div class="pv-stage"><div class="pv-canvas sch-canvas" id="schwrap" tabindex="0" aria-label="Schematic sheet ${esc(sheetId)}. Scroll to zoom, drag to pan.">${inner}</div>${pvZoomHTML('sch')}${pvBarHTML('sch')}</div></div>`;
}
// a drawn sheet that holds placeholder parts (a rectangle with the netlist's pins, no library symbol yet): one line, the same words as the stage's
const pvDraftNote = () => S && S.draft && S.draft.text ? banner({tone: 'warn', html: esc(S.draft.text) + '. Build the library, then draw again to replace them.'}) : '';
const pvSheetKey = () => sheetId + '|' + JSON.stringify(lines().map(l => [l.key, l.mpn, l.value, l.dnp])) + JSON.stringify((S.sheets || []).map(s => Object.keys(s.parts || {}).length));
async function loadSheet(container) {
  if (!S || !S.sheets || !S.sheets.length) return;
  if (!sheetId || !S.sheets.find(s => s.id === sheetId)) pvSetSheet(S.sheets[0].id);
  const id = sheetId, key = pvSheetKey();
  if (svgCache.key === key && svgCache.text) { afterSheet(); return; }
  if (pvSchBusy === key) return;                            // one request per picture
  pvSchBusy = key;
  try {
    const r = await fetch('/api/sheet.svg?' + q({sheet: id}));
    if (!r.ok) throw new Error(r.status === 404 ? 'the sheet was not found' : 'the server answered ' + r.status);
    svgCache = {key, text: await r.text()};
    pvSchErr = '';
  } catch (err) {
    svgCache = {key: '', text: ''};
    pvSchErr = err.message || 'no answer';
  } finally { pvSchBusy = ''; }
  const w = $('#schwrap');
  if (!w || sheetId !== id) return;
  if (pvSchErr) w.innerHTML = `<div class="pv-note">${errorLine('draw the schematic', pvSchErr, btn('Try again', {size: 'sm', act: 'sch-retry'}))}</div>`;
  else { w.innerHTML = svgCache.text; afterSheet(); }
}
function afterSheet() {
  const wrap = $('#schwrap');
  if (!wrap) return;
  initZoomPan(wrap, schZoom);
  pvBind(wrap, 'sch');
  const svg = wrap.querySelector('svg');
  if (!svg) return;
  for (const g of svg.querySelectorAll('g.part')) {
    if (!g.querySelector(':scope > rect.hlbox')) {         // the box that shows hover and selection around a part
      let b = null;
      try { b = g.getBBox(); } catch (e) { /* not displayed yet: the next call draws it */ }
      if (b && b.width) {
        const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        r.setAttribute('x', b.x - 6); r.setAttribute('y', b.y - 6); r.setAttribute('width', b.width + 12); r.setAttribute('height', b.height + 12);
        r.setAttribute('rx', 6); r.setAttribute('class', 'hlbox'); g.insertBefore(r, g.firstChild);
      }
    }
    g.setAttribute('role', 'button'); g.setAttribute('tabindex', '0'); g.setAttribute('aria-label', pvLabel(g.dataset.ref));
  }
  // the netlist renderer draws a net name as plain text: tag it, so a net can be picked and highlighted there too
  svg.querySelectorAll('text.net, text.pwr, text.pwr3, text.gt').forEach(t => { if (!t.dataset.net) t.dataset.net = t.textContent.trim(); });
  svg.querySelectorAll('g.net-label, g.power-port, g.port').forEach(g => { g.setAttribute('role', 'button'); g.setAttribute('aria-label', 'Net ' + (g.dataset.net || g.textContent.trim())); });
  applyFocus();
  updateZoomTransform(wrap, schZoom);
  pvRunReveal('sch');
}

/* ---------- layout (PCB) ---------- */
const pcbKey = () => PROJECT + '|' + (ALTIUM_DATA?.linked?.project_file || '') + '|' + (ALTIUM_DATA?.linked?.pcb_file || '');
const pvNoPcb = text => typeof text === 'string' && (text.includes('Settings to view PCB') || text.includes('No Altium .PcbDoc linked'));
// The picture, once per project. The inspector asks for it too (the pads tell which parts touch a net).
function pcbText() {
  const key = pcbKey();
  if (pcbSvgCache.key === key && pcbSvgCache.text) return Promise.resolve(pcbSvgCache.text);
  if (pcbFetching && pcbFetching.key === key) return pcbFetching.p;
  const p = fetch('/api/preview/pcb.svg?' + q()).then(async r => {
    if (!r.ok) throw new Error(r.status === 404 ? 'not found' : 'the server answered ' + r.status);
    const text = await r.text();
    pcbSvgCache = {key, text};
    return text;
  }).finally(() => { if (pcbFetching && pcbFetching.p === p) pcbFetching = null; });
  pcbFetching = {key, p};
  return p;
}
function formatPcbPreview(raw) {
  if (!raw) return `<div class="pv-note">${loadingLine('Drawing the layout')}</div>`;
  if (pvNoPcb(raw)) {
    const linked = raw.match(/data-linked-project="([^"]*)"/);
    if (linked) {                    // linked, but the project has no PcbDoc yet: say that, not "not linked"
      const name = linked[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#x27;/g, "'");
      return `<div class="pcb-empty-state">${emptyState('No PCB file in the project yet', `${name} is linked but has no .PcbDoc. In Altium: File > New > PCB, save it in the project, then come back here.`, '', PCB_LIMITS)}</div>`;
    }
    return `<div class="pcb-empty-state">${emptyState('No PCB linked', 'Link an Altium project that has a PcbDoc to see the layout here.', btn('Link a project', {kind: 'pri', act: 'pv-link'}) + btn('Create an Altium project', {act: 'altium-create'}), PCB_LIMITS)}</div>`;
  }
  return raw;
}
// the placement plan, or null when it holds nothing
function pvPlan() {
  const p = S.placement_plan;
  if (!p || typeof p !== 'object') return null;
  const n = k => Array.isArray(p[k]) ? p[k].length : 0;
  return n('groups') || n('keep_outs') || n('critical_nets') ? p : null;
}
function pcbHasLayer(svgText, id) {
  if (!svgText) return false;
  const m = svgText.match(new RegExp(`<g id="pcb-layer-${id}"[^>]*>([\\s\\S]*?)</g>`));
  return m ? m[1].trim().length > 0 : false;
}
function pcbLayerList(svgText, plan) {
  const all = [
    {value: 'top-copper', label: 'Top copper'},
    {value: 'bottom-copper', label: 'Bottom copper'},
    {value: 'inner', label: 'Inner'},
    {value: 'vias', label: 'Vias'},
    {value: 'silk-top', label: 'Silkscreen top'},
    {value: 'silk-bottom', label: 'Silkscreen bottom'},
    {value: 'outline', label: 'Outline'},
  ];
  const active = svgText
    ? all.filter(l => pcbHasLayer(svgText, l.value))
    : all.filter(l => l.value !== 'inner' && l.value !== 'silk-bottom');
  if (plan) active.push({value: 'plan', label: 'Plan'});
  return active;
}
function pcbHTML(container) {
  const text = pcbSvgCache.text;
  if (pvNoPcb(text)) return `<div class="pv pv-empty" data-pv="pcb">${viewHeader({title: 'Layout', actions: pvStepBtn('place')})}${pvStepNote('pcb')}<div class="pv-stage" id="pcbwrap">${formatPcbPreview(text)}</div></div>`;
  const plan = pvPlan(), b = S.board || {}, cnt = k => plan && Array.isArray(plan[k]) ? plan[k].length : 0;
  const size = Array.isArray(b.size_mm) && b.size_mm.length === 2 ? b.size_mm.map(v => Math.round(v * 10) / 10).join(' × ') + ' mm' : '';
  const cu = text && text.match(/data-copper-layers="(\d+)"/), copper = cu ? +cu[1] : b.layers;
  const meta = metaLine([size, {n: copper, label: 'copper layers'}, {n: cnt('groups'), label: cnt('groups') === 1 ? 'zone' : 'zones'},
    {n: cnt('keep_outs'), label: cnt('keep_outs') === 1 ? 'keep-out' : 'keep-outs'}, {n: cnt('critical_nets'), label: cnt('critical_nets') === 1 ? 'critical net' : 'critical nets'}]);
  const layers = pcbLayerList(text, plan);
  const inner = pvPcbErr ? `<div class="pv-note">${errorLine('draw the layout', pvPcbErr, btn('Try again', {size: 'sm', act: 'pcb-retry'}))}</div>` : formatPcbPreview(text);
  const zoom = text || pvPcbErr ? pvZoomHTML('pcb') : '';
  return `<div class="pv" data-pv="pcb">` +
    viewHeader({title: 'Layout', meta, actions: pvStepBtn('place') + pvStepBtn('route') + pvStepBtn('drc')}) +
    `<div class="pv-stage"><div class="pv-canvas pcb-canvas" id="pcbwrap" tabindex="0" aria-label="PCB layout. Scroll to zoom, drag to pan.">${inner}</div>${zoom}${pvBarHTML('pcb', pvLayersHTML(layers))}</div></div>`;
}
async function loadPcb(container) {
  if (!$('.pv[data-pv="pcb"]')) return;
  if (pcbSvgCache.key === pcbKey() && pcbSvgCache.text) { afterPcb(); return; }
  try { await pcbText(); pvPcbErr = ''; }
  catch (err) { pvPcbErr = err.message || 'no answer'; }
  const root = $('.pv[data-pv="pcb"]');
  if (!root) return;
  root.outerHTML = pcbHTML();                               // the empty state and the picture have different frames
  afterPcb();
}
/* The idea's board size differs from the outline the PcbDoc holds (the placer reads the size only when there is no outline): Layout offers
   to set the board to the idea's size. The change backs the PcbDoc up first and names parts that would fall outside. */
let pcbOutline = null;
function pcbOutlineOfferHTML() {
  const o = pcbOutline;
  if (!o || !o.differs || !o.idea || !o.pcb || !pvAltiumLinked()) return '';
  const mm = v => Math.round(v * 10) / 10;
  return `<div class="pv-note" id="pcb-outline-offer">${banner({tone: 'warn',
    html: `The board in Altium is ${mm(o.pcb[0])} × ${mm(o.pcb[1])} mm, the idea says ${mm(o.idea[0])} × ${mm(o.idea[1])} mm.`,
    actions: btn(`Set board to ${mm(o.idea[0])} × ${mm(o.idea[1])} mm`, {size: 'sm', kind: 'line', act: 'pcb-outline-resize', disabled: pvBusy ? true : undefined,
      title: 'Changes the board outline in the PcbDoc; the file is backed up first and the parts stay where they are'})})}</div>`;
}
async function loadPcbOutline() {
  const root = $('.pv[data-pv="pcb"]');
  if (!root || !pvAltiumLinked()) return;
  try { pcbOutline = await api('/api/altium/outline'); } catch (e) { pcbOutline = null; }
  const old = $('#pcb-outline-offer'), html = pcbOutlineOfferHTML();
  if (old) old.remove();
  const head = root.querySelector('header.vh');
  if (html && head) head.insertAdjacentHTML('afterend', html);
}
onAct('pcb-outline-resize', async (el) => {
  const o = pcbOutline;
  if (!o || !o.idea) return;
  el.disabled = true;
  try {
    const r = await api('/api/altium/outline-resize', {width: o.idea[0], height: o.idea[1]});
    toast(r.warnings && r.warnings.length ? 'Board resized. ' + r.warnings[0] : 'Board resized to ' + o.idea[0] + ' × ' + o.idea[1] + ' mm');
    pcbSvgCache.key = '';                       // the picture is read again
    await loadPcb();
  } catch (err) { toast(err.message || 'The board could not be resized'); el.disabled = false; }
  await loadPcbOutline();
});
function afterPcb() {
  loadPcbOutline();
  const wrap = $('#pcbwrap');
  const svg = wrap && wrap.querySelector('svg');
  if (!svg) return;
  initZoomPan(wrap, pcbZoom);
  pvBind(wrap, 'pcb');
  svg.classList.add('pcb-preview');
  applyPcbLayers();
  svg.querySelectorAll('g.pcb-comp').forEach(g => {
    const ref = g.dataset.ref || (g.id || '').replace(/^pcb-comp-/, '');
    g.setAttribute('role', 'button'); g.setAttribute('tabindex', '0'); g.setAttribute('aria-label', pvLabel(ref));
  });
  svg.querySelectorAll('g.plan-group').forEach(g => { g.setAttribute('role', 'button'); g.setAttribute('tabindex', '0'); g.setAttribute('aria-label', 'Zone ' + (g.dataset.group || '')); });
  applyFocus();
  updateZoomTransform(wrap, pcbZoom);
  pvRunReveal('pcb');
}
function applyPcbLayers() {
  const svg = $('#pcbwrap svg');
  if (!svg) return;
  for (const [k, on] of Object.entries(pcbLayers)) {
    svg.classList.toggle('hide-' + k, !on);
  }
  if ('top-copper' in pcbLayers) svg.classList.toggle('hide-top', !pcbLayers['top-copper']);
  if ('bottom-copper' in pcbLayers) svg.classList.toggle('hide-bottom', !pcbLayers['bottom-copper']);
}

/* ---------- keyboard: sheet tabs ---------- */
document.addEventListener('keydown', e => {
  const tabEl = e.target.closest && e.target.closest('.pv-tab');
  if (!tabEl || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End')) return;
  const tabs = [...tabEl.parentElement.querySelectorAll('.pv-tab')], i = tabs.indexOf(tabEl);
  const next = e.key === 'Home' ? tabs[0] : e.key === 'End' ? tabs[tabs.length - 1] : tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
  e.preventDefault();
  if (next) next.click();
  setTimeout(() => { const on = $('.pv-tab[aria-selected="true"]'); if (on) on.focus(); }, 0);
});

/* ---------- action handlers (dispatched by the click delegate in core.js) ---------- */
onAct('sch-sheet', async (el, d, e) => {
  if (pvSetSheet(d.sheet)) render(true); return;
});
onAct('sch-retry', async (el, d, e) => {
  svgCache = {key: '', text: ''}; pvSchErr = ''; renderCenter(true); return;
});
onAct('pcb-retry', async (el, d, e) => {
  pcbSvgCache = {key: '', text: ''}; pvPcbErr = ''; renderCenter(true); return;
});
onAct('sch-zoom-in', async (el, d, e) => {
  applyZoom('schwrap', schZoom, 1.25); return;
});
onAct('sch-zoom-out', async (el, d, e) => {
  applyZoom('schwrap', schZoom, 0.8); return;
});
onAct('sch-zoom-fit', async (el, d, e) => {
  resetZoom('schwrap', schZoom); return;
});
onAct('pcb-zoom-in', async (el, d, e) => {
  applyZoom('pcbwrap', pcbZoom, 1.25); return;
});
onAct('pcb-zoom-out', async (el, d, e) => {
  applyZoom('pcbwrap', pcbZoom, 0.8); return;
});
onAct('pcb-zoom-fit', async (el, d, e) => {
  resetZoom('pcbwrap', pcbZoom); return;
});
onAct('toggle-layer', async (el, d, e) => {
  const layer = d.value || d.layer;
  if (!layer || !(layer in pcbLayers)) return;
  pcbLayers[layer] = !pcbLayers[layer];
  el.setAttribute('aria-pressed', String(pcbLayers[layer]));
  const box = el.closest('.pv-layers'), tag = box && box.querySelector('.pv-lhid');       // "2 hidden" on the closed button follows the clicks
  if (tag) {
    const n = box.querySelectorAll('button[aria-pressed="false"]').length;
    tag.textContent = n + ' hidden';
    tag.hidden = !n;
  }
  applyPcbLayers();
  return;
});
onAct('pv-run-toggle', async (el, d, e) => {
  pvRunOpen = !pvRunOpen;
  renderCenter(true);
  setTimeout(() => { const b = $('[data-act="pv-run-toggle"]'); if (b) b.focus(); }, 0);      // the redraw must not drop the keyboard
});
// the layers list closes with Escape (the focus returns to its button) and with a click outside it
document.addEventListener('keydown', e => {
  const box = e.key === 'Escape' && e.target.closest && e.target.closest('.pv-layers[open]');
  if (box) { box.open = false; const s = box.querySelector('summary'); if (s) s.focus(); }
});
document.addEventListener('click', e => {
  document.querySelectorAll('.pv-layers[open]').forEach(b => { if (!b.contains(e.target)) b.open = false; });
});
onAct('pv-link', async (el, d, e) => {
  go('settings'); return;
});
