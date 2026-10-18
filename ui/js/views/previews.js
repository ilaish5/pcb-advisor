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
const pvZoomHTML = kind => `<div class="pv-zoom" role="group" aria-label="Zoom">` +
  btn('', {icon: 'zoomout', size: 'sm', title: 'Zoom out', act: kind + '-zoom-out'}) +
  btn('', {icon: 'zoomin', size: 'sm', title: 'Zoom in', act: kind + '-zoom-in'}) +
  btn('', {icon: 'fit', size: 'sm', title: 'Fit to view', act: kind + '-zoom-fit'}) + '</div>';

function schHTML(container) {
  const sheets = S.sheets || [];
  if (!sheets.length) return `<div class="pv">${viewHeader({title: 'Schematic'})}${emptyState('No schematic yet', 'The agent draws the sheets once the parts are chosen.')}</div>`;
  if (!sheetId || !sheets.find(s => s.id === sheetId)) pvSetSheet(sheets[0].id);
  const fresh = svgCache.text && svgCache.key.startsWith(sheetId + '|');
  const inner = fresh ? svgCache.text
    : pvSchErr ? `<div class="pv-note">${errorLine('draw the schematic', pvSchErr, btn('Try again', {size: 'sm', act: 'sch-retry'}))}</div>`
    : `<div class="pv-note">${loadingLine('Drawing the schematic')}</div>`;
  const tabs = sheets.length > 1 ? `<div class="pv-tabs" role="tablist" aria-label="Sheets">${sheets.map(s =>
    `<button type="button" role="tab" class="pv-tab" aria-selected="${s.id === sheetId}" tabindex="${s.id === sheetId ? 0 : -1}" data-act="sch-sheet" data-sheet="${esc(s.id)}">${esc(pvSheetLabel(s))}</button>`).join('')}</div>` : '';
  return `<div class="pv" data-pv="sch">` +
    viewHeader({title: 'Schematic', meta: metaLine([{n: sheets.length, label: sheets.length === 1 ? 'sheet' : 'sheets'}])}) + tabs +
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
const pcbKey = () => PROJECT + '|' + (ALTIUM_DATA?.linked?.pcb_file || '');
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
    return `<div class="pcb-empty-state">${emptyState('No PCB linked', 'Link an Altium project that has a PcbDoc to see the layout here.', btn('Link a project', {kind: 'pri', act: 'pv-link'}))}</div>`;
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
  if (pvNoPcb(text)) return `<div class="pv pv-empty" data-pv="pcb">${viewHeader({title: 'Layout'})}<div class="pv-stage" id="pcbwrap">${formatPcbPreview(text)}</div></div>`;
  const plan = pvPlan(), b = S.board || {}, cnt = k => plan && Array.isArray(plan[k]) ? plan[k].length : 0;
  const size = Array.isArray(b.size_mm) && b.size_mm.length === 2 ? b.size_mm.map(v => Math.round(v * 10) / 10).join(' × ') + ' mm' : '';
  const meta = metaLine([size, {n: b.layers, label: 'layers'}, {n: cnt('groups'), label: cnt('groups') === 1 ? 'zone' : 'zones'},
    {n: cnt('keep_outs'), label: cnt('keep_outs') === 1 ? 'keep-out' : 'keep-outs'}, {n: cnt('critical_nets'), label: cnt('critical_nets') === 1 ? 'critical net' : 'critical nets'}]);
  const layers = pcbLayerList(text, plan);
  const inner = pvPcbErr ? `<div class="pv-note">${errorLine('draw the layout', pvPcbErr, btn('Try again', {size: 'sm', act: 'pcb-retry'}))}</div>` : formatPcbPreview(text);
  const zoom = text || pvPcbErr ? pvZoomHTML('pcb') : '';
  return `<div class="pv" data-pv="pcb">` +
    viewHeader({title: 'Layout', meta, actions: seg(layers, Object.keys(pcbLayers).filter(k => pcbLayers[k]), {act: 'toggle-layer', label: 'Layers'})}) +
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
