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
  updateZoomTransform(wrap, z);
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
const pvSheetLabel = s => s.title && s.title !== s.id ? `${s.id} ${s.title}` : s.id;
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
  btn('', {icon: 'fit', size: 'sm', title: 'Fit to view', act: kind + '-zoom-fit'}) + '</div>';

/* ---------- the Altium step buttons: the click is the consent (the agent asks in words instead) ---------- */
const PV_STEPS = {
  draw: {url: '/api/altium/draw-schematic', page: 'sch', doing: 'Drawing', ask: 'Replacing redraws every sheet that already has a drawing, from the netlist; each file as it is now is copied to .advisor-backup first.', label: 'Draw in Altium', again: 'Replace the existing drawing', busy: 'Altium is drawing the schematic. It may take a minute and flash while it works.',
         title: 'Altium draws the netlist on the schematic sheet, with the parts from the project library, and the saved sheet is checked against the netlist. Any file it changes is copied to .advisor-backup first.'},
  place: {url: '/api/altium/place', page: 'pcb', doing: 'Placing', ask: 'Replacing removes the parts and copper on the board and places again; the file as it is now is copied to .advisor-backup first.', label: 'Place parts', again: 'Replace the existing placement', busy: 'Altium is placing the parts. It may take a minute and flash while it works.',
          title: 'Altium places the parts of the netlist on the PcbDoc, and makes the board outline from the board size when there is none. The saved board is checked. The PcbDoc is copied to .advisor-backup first.'},
  route: {url: '/api/altium/route', page: 'pcb', doing: 'Routing', ask: 'Replacing removes the tracks, vias and pours and routes again; the file as it is now is copied to .advisor-backup first.', label: 'Route board', again: 'Replace the existing routes', busy: 'Altium is routing the board. Routing can take a couple of minutes and Altium will flash while it works.',
          title: 'Draws the tracks and vias on the placed board, plus a ground pour when it can, then checks the result with the design rule check. The PcbDoc is copied to .advisor-backup before it draws, and put back if a check fails.'},
  /* Rules (Rules page) and outputs (Outputs page) run the same machinery: the live list, Stop, and the answer after a reload. They never replace. */
  rules: {url: '/api/altium/import-rules', page: 'rules', doing: 'Applying', label: 'Apply rules in Altium', busy: 'Altium is applying the rules. It may take a minute and flash while it works.',
          title: 'Puts these rules into the linked PcbDoc by name; your own rules stay. The PcbDoc is copied to .advisor-backup first.',
          after: () => { if (typeof loadRules === 'function') loadRules(true); }},
  outputs: {url: '/api/altium/run-outjob', page: 'outputs', doing: 'Generating', label: 'Generate outputs in Altium', busy: 'Altium is generating the outputs. It may take a minute and flash while it works.',
            title: 'Altium runs the project OutJob: Gerber, NC drill, BOM and pick and place go into its outputs folder. Ours is added to the project first when it has none.',
            after: () => { if (typeof outLoadAlt === 'function') outLoadAlt(); }},
};
let pvBusy = '';             // the step Altium is working on now: its line stays on the page until the answer comes
let pvNote = {};             // page ('sch' | 'pcb') -> {kind, text, warnings, replace}: what the last step answered, kept until dismissed
const PV_PREP = {'library.build': 'built the library', 'altium.add_pcb': 'added a PcbDoc', 'altium.import_rules': 'imported the JLC rules', 'outjob.generate': 'added the OutJob'};
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
function pvStepLine(st, i, all) {       // one line of the live list: done, running (spinner) or waiting; the step itself keeps its long hint
  const text = esc(st.state === 'running' && i === all.length - 1 ? PV_STEPS[pvBusy].busy : st.label + (st.state === 'done' && st.note ? ': ' + st.note : ''));
  if (st.state === 'running') return `<div class="loading" role="status"><span class="spin" aria-hidden="true"></span>${text}</div>`;
  return `<div class="loading"><span aria-hidden="true">${st.state === 'done' ? '✓' : '&middot;'}</span>${text}${st.state === 'waiting' ? ' (waiting)' : st.state === 'stopped' ? ' (stopped)' : ''}</div>`;
}
function pvStopBtn() {       // the run stops before its next step; the last step is one Altium operation that cannot be cut
  const st = (pvRun && pvRun.steps) || [];
  const last = st.length && st[st.length - 1].state === 'running';
  return btn(pvStopping ? 'Stopping…' : 'Stop', {size: 'sm', kind: 'line', act: 'altium-step-stop', disabled: pvStopping || last ? true : undefined,
    title: last ? 'This step finishes as one Altium operation' : 'Ends the run before its next step. The step Altium is working on finishes first.'});
}
const PV_LOG_OP = {draw: 'draw-schematic', place: 'place-pcb', route: 'route-pcb'};
function pvLaterOk(n) {        // the same step succeeded after this note was made: the note is stale
  const t = n.step && S && S.altium_ok && S.altium_ok[PV_LOG_OP[n.step]];
  return !!(t && n.at && new Date(t).getTime() > n.at);
}
function pvStepNote(page) {       // under the header: Altium is working, or what the last step answered
  pvResume();
  const list = pvRun && pvRun.running && (pvRun.steps || []).length > 1 ? `<div class="pv-steps">${pvRun.steps.map(pvStepLine).join('')}</div>` : '';
  const busy = pvBusy && PV_STEPS[pvBusy].page === page ? `<div class="pv-note">${list || loadingLine(PV_STEPS[pvBusy].busy)}<div class="acts">${pvStopBtn()}</div></div>` : '';
  if (pvNote[page] && pvNote[page].kind !== 'ok' && pvLaterOk(pvNote[page])) delete pvNote[page];
  const n = pvNote[page];
  if (busy || !n) return busy;
  const acts = (n.partial ? btn('Route the rest and leave ' + n.partial.join(', ') + ' open', {size: 'sm', kind: 'line', act: 'altium-step', step: 'route', partial: '1', disabled: pvBusy ? true : undefined,
      title: 'Routes every net that can be routed, keeps those tracks, and leaves ' + n.partial.join(', ') + ' unrouted for you to finish in Altium'}) : '') +
    (n.replace ? btn(PV_STEPS[n.replace].again, {size: 'sm', kind: 'line', act: 'altium-step', step: n.replace, replace: '1', disabled: pvBusy ? true : undefined}) : '') +
    btn(n.replace ? 'Keep it' : 'Dismiss', {size: 'sm', act: 'altium-step-dismiss', page});
  const c = pvCompact(n.text, n.from === 999 ? [] : n.warnings || []);
  const op = k => pvMoreOpen[page + ':' + k] ? ' open' : '';
  const more = c.warnings.length ? `<details class="pv-more" data-pvk="${page}:w"${op('w')}><summary>Show ${c.warnings.length} ${c.warnings.length === 1 ? 'warning' : 'warnings'}</summary><ul>${c.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul></details>` : '';
  const rest = c.rest ? `<details class="pv-more" data-pvk="${page}:r"${op('r')}><summary>Show details</summary><p>${esc(c.rest)}</p></details>` : '';
  const alerts = c.alerts.map(w => `<br>Warning: ${esc(w)}`).join('');
  return `<div class="pv-note"><div class="note ${n.kind}" role="${n.kind === 'bad' ? 'alert' : 'status'}"><span>${esc(c.head)}${alerts}${rest}${more}</span><span class="acts">${acts}</span></div></div>`;
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
  renderCenter(true);
});

const SCH_LIMITS = 'Not drawn automatically yet: a part whose library symbol is split into several separate blocks (for example a chip drawn as a power block and a signal block), and a circuit too big for one A4 sheet (it is refused with a plan to split it). Wires that run between two sheets are not drawn either. For these, draw that part by hand in Altium.';
const PCB_LIMITS = 'Not yet: the router is for small two-layer boards, with no differential pairs and no inner layers.';
const pvRealSheets = sheets => (sheets.filter(s => !s.altium).length || sheets.length);       // a sheet read from Altium that the plan also has is one sheet, not two
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
    viewHeader({title: 'Schematic', meta: metaLine([{n: pvRealSheets(sheets), label: pvRealSheets(sheets) === 1 ? 'sheet' : 'sheets'}]), actions: pvStepBtn('draw')}) + pvStepNote('sch') + tabs +
    `<div class="pv-stage"><div class="pv-canvas sch-canvas" id="schwrap" tabindex="0" aria-label="Schematic sheet ${esc(sheetId)}. Scroll to zoom, drag to pan.">${inner}</div>${pvZoomHTML('sch')}</div></div>`;
}
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
    viewHeader({title: 'Layout', meta, actions: pvStepBtn('place') + pvStepBtn('route') + seg(layers, Object.keys(pcbLayers).filter(k => pcbLayers[k]), {act: 'toggle-layer', label: 'Layers'})}) + pvStepNote('pcb') +
    `<div class="pv-stage"><div class="pv-canvas pcb-canvas" id="pcbwrap" tabindex="0" aria-label="PCB layout. Scroll to zoom, drag to pan.">${inner}</div>${zoom}</div></div>`;
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
function afterPcb() {
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
  applyPcbLayers();
  return;
});
onAct('pv-link', async (el, d, e) => {
  go('settings'); return;
});
