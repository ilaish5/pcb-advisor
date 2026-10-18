/**
 * Block Diagram Editor (Vanilla JS & SVG)
 *
 * Features:
 * - A small floating toolbar on the top edge of the canvas (icons only, aria-labels & tooltips, 32px targets)
 * - 4x4 Shapes Popover grid (16 shapes: rectangle, ellipse, diamond, triangle, rounded_rectangle, cloud,
 *   star, arrow_right, parallelogram, hexagon, octagon, double_arrow, speech_callout, cylinder, process, note_brace)
 * - Floating context bar above (or below) the selection with icons only (fill/border palette, 3 line styles, 3 arrowheads, straight/elbow, text size T▾, bold, delete, overflow ⋯)
 * - Bottom-right zoom cluster (−, %, +, Fit) and a ⋯ more menu on the toolbar (Snap, Grid, Template)
 * - Infinite canvas with pan, zoom at cursor, dot grid, snap-to-grid, and fit
 * - Click or drag to place shapes/frames; multi-selection; resize handles; keyboard nudging & shortcuts
 * - Connectors with shape ports, following on move, straight/elbow routing, labels
 * - Frames with title at top-left, moving enclosed shapes, rendered behind shapes
 * - Debounced autosave (~600 ms) via options.onSave
 * - Right-drag pan helper, sanitizeModel, undo/redo, empty-state logic
 * - Read-only preview of a proposed diagram (setPreview), destroy() for a clean hand-over
 *
 * Look: every colour of the chrome comes from the app's CSS tokens (ui/styles/idea.css). The stored colours of
 * blocks and lines are data; the dark theme only changes how they are drawn (see displayFill and friends).
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.DiagramEditor = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {

  const DOMAIN_PRESETS = [
    { id: 'power', name: 'Power', fill: '#fef3e2', stroke: '#e67e22', text: '#b45309' },
    { id: 'mcu', name: 'MCU', fill: '#ebf5fb', stroke: '#2980b9', text: '#1d4ed8' },
    { id: 'sensing', name: 'Sensors', fill: '#e8f8f0', stroke: '#27ae60', text: '#15803d' },
    { id: 'comms', name: 'RF / Comms', fill: '#f3ebf9', stroke: '#8e44ad', text: '#6c3483' },
    { id: 'drive', name: 'Drive / IO', fill: '#fdedec', stroke: '#c0392b', text: '#b91c1c' },
    { id: 'ui', name: 'UI / Indicators', fill: '#f2f4f4', stroke: '#7f8c8d', text: '#4b5563' },
    { id: 'sticky', name: 'Note', fill: '#fef9c3', stroke: '#ca8a04', text: '#854d0e' },
    { id: 'white', name: 'White', fill: '#ffffff', stroke: '#94a3b8', text: '#1e293b' },
    { id: 'none', name: 'None', fill: 'none', stroke: '#64748b', text: '#0f172a' },
  ];

  const COLOR_SWATCHES = [
    'none', '#ffffff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#cbd5e1', '#94a3b8',
    '#64748b', '#1e293b', '#0f172a', '#ef4444', '#f97316', '#eab308',
    '#22c55e', '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899', '#fef3e2',
    '#ebf5fb', '#e8f8f0', '#f3ebf9', '#fdedec', '#f2f4f4', '#fef9c3'
  ];

  const STROKE_SWATCHES = [
    'none', '#e67e22', '#2980b9', '#27ae60', '#8e44ad', '#c0392b', '#7f8c8d',
    '#ca8a04', '#94a3b8', '#64748b', '#1e293b', '#0f172a', '#ef4444', '#3b82f6'
  ];

  const SHAPES_16 = [
    { type: 'rectangle', name: 'Rectangle', shortcut: 'B' },
    { type: 'ellipse', name: 'Ellipse', shortcut: 'E' },
    { type: 'diamond', name: 'Diamond', shortcut: 'D' },
    { type: 'triangle', name: 'Triangle' },
    { type: 'rounded_rectangle', name: 'Rounded rectangle (pill)' },
    { type: 'cloud', name: 'Cloud' },
    { type: 'star', name: 'Star' },
    { type: 'arrow_right', name: 'Arrow right' },
    { type: 'parallelogram', name: 'Parallelogram' },
    { type: 'hexagon', name: 'Hexagon' },
    { type: 'octagon', name: 'Octagon' },
    { type: 'double_arrow', name: 'Double arrow' },
    { type: 'speech_callout', name: 'Speech callout' },
    { type: 'cylinder', name: 'Cylinder (database)' },
    { type: 'process', name: 'Process' },
    { type: 'note_brace', name: 'Note / brace' }
  ];

  const STARTER_TEMPLATE = {
    shapes: [
      {
        id: 's_pwr',
        type: 'rectangle',
        x: 100,
        y: 120,
        w: 160,
        h: 68,
        text: 'Power Supply\n3.3 V LDO Regulator',
        fill: '#fef3e2',
        stroke: '#e67e22',
        strokeStyle: 'solid',
        strokeWidth: 2,
        fontSize: 'M',
        bold: true,
        align: 'center',
        z: 1,
        locked: false,
        domain: 'power'
      },
      {
        id: 's_mcu',
        type: 'rectangle',
        x: 360,
        y: 110,
        w: 180,
        h: 88,
        text: 'Microcontroller\nSTM32F401 (MCU)',
        fill: '#ebf5fb',
        stroke: '#2980b9',
        strokeStyle: 'solid',
        strokeWidth: 2,
        fontSize: 'M',
        bold: true,
        align: 'center',
        z: 2,
        locked: false,
        domain: 'mcu'
      },
      {
        id: 's_io',
        type: 'rectangle',
        x: 640,
        y: 120,
        w: 160,
        h: 68,
        text: 'Sensors / IO\nI2C Sensor Hub',
        fill: '#e8f8f0',
        stroke: '#27ae60',
        strokeStyle: 'solid',
        strokeWidth: 2,
        fontSize: 'M',
        bold: true,
        align: 'center',
        z: 3,
        locked: false,
        domain: 'sensing'
      }
    ],
    connectors: [
      {
        id: 'c_pwr_mcu',
        from: { shape: 's_pwr', side: 'right' },
        to: { shape: 's_mcu', side: 'left' },
        label: '3.3 V Power',
        stroke: '#e67e22',
        style: 'solid',
        arrows: 'end',
        route: 'elbow'
      },
      {
        id: 'c_mcu_io',
        from: { shape: 's_mcu', side: 'right' },
        to: { shape: 's_io', side: 'left' },
        label: 'I2C Bus',
        stroke: '#27ae60',
        style: 'solid',
        arrows: 'both',
        route: 'elbow'
      }
    ],
    frames: [
      {
        id: 'f_main',
        x: 60,
        y: 50,
        w: 780,
        h: 210,
        title: 'Core System Domain',
        stroke: '#94a3b8'
      }
    ]
  };

  function uid(prefix = 'id') {
    return prefix + '_' + Math.random().toString(36).substr(2, 9);
  }

  function clone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* ---------- display colours ----------
     The stored colours of a block, line or frame (fill, stroke, text) are data: they are saved, shown to the agent and
     never rewritten. In the dark theme the editor changes only what it draws, so a pale block does not glow on a dark
     canvas. The preset domains have hand-tuned pairs; every other colour goes through a lightness rule. */
  const DARK_FILL = {
    '#fef3e2': '#3a2c1b', '#ebf5fb': '#192b3b', '#e8f8f0': '#173024', '#f3ebf9': '#2b1f38',
    '#fdedec': '#3a2123', '#f2f4f4': '#27292c', '#fef9c3': '#37321a', '#ffffff': '#232327'
  };
  const DARK_STROKE = {
    '#e67e22': '#f0a35e', '#2980b9': '#6fb4e8', '#27ae60': '#5fd18f', '#8e44ad': '#bb8fd8', '#c0392b': '#ef7b72',
    '#7f8c8d': '#a1adae', '#ca8a04': '#e6b94a', '#94a3b8': '#8493a8', '#64748b': '#94a3b8'
  };
  const DARK_TEXT = {
    '#b45309': '#f4bd85', '#1d4ed8': '#9ec0f7', '#15803d': '#86dfae', '#6c3483': '#d3aee8', '#b91c1c': '#f4a29b',
    '#4b5563': '#c5ccd4', '#854d0e': '#efd07a', '#1e293b': '#e6e9ee', '#0f172a': '#f1f3f6'
  };
  const PALE_TEXT = '#eef2f7';
  const INK_TEXT = '#0f172a';
  const CANVAS_LUMA = { light: 0.93, dark: 0.009 };   // relative luminance of --canvas in each theme

  function diagramIsDark() {
    const root = typeof document !== 'undefined' ? document.documentElement : null;
    const t = root && root.dataset ? root.dataset.theme : '';
    if (t === 'dark') return true;
    if (t === 'light') return false;
    return !!(typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }

  // '#rgb' / '#rrggbb' / 'rgb(...)' -> {r, g, b}; null for 'none', 'transparent' and names we do not know
  function parseColor(c) {
    const s = String(c == null ? '' : c).trim().toLowerCase();
    if (!s || s === 'none' || s === 'transparent') return null;
    if (s === 'white') return { r: 255, g: 255, b: 255 };
    if (s === 'black') return { r: 0, g: 0, b: 0 };
    let m = /^#([0-9a-f]{3,8})$/.exec(s);
    if (m) {
      let h = m[1];
      if (h.length === 3 || h.length === 4) h = h.split('').map(x => x + x).join('');
      if (h.length !== 6 && h.length !== 8) return null;
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
    }
    m = /^rgba?\(([^)]+)\)$/.exec(s);
    if (m) {
      const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
      if (p.length < 3 || p.slice(0, 3).some(isNaN)) return null;
      return { r: p[0], g: p[1], b: p[2] };
    }
    return null;
  }

  function rgbToHsl({ r, g, b }) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    return [h * 60, s, l];
  }

  function hslToHex(h, s, l) {
    const a = s * Math.min(l, 1 - l);
    const f = n => {
      const k = (n + h / 30) % 12;
      const v = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
      return Math.round(v * 255).toString(16).padStart(2, '0');
    };
    return '#' + f(0) + f(8) + f(4);
  }

  function luminance({ r, g, b }) {
    const ch = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
  }

  function contrastRatio(l1, l2) {
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  function displayFill(c, dark) {
    if (!dark) return c;
    const hit = DARK_FILL[String(c).trim().toLowerCase()];
    if (hit) return hit;
    const rgb = parseColor(c);
    if (!rgb) return c;
    const [h, s, l] = rgbToHsl(rgb);
    if (l > 0.55) return hslToHex(h, s * 0.55, Math.min(0.5, Math.max(0.12, 0.12 + (1 - l) * 0.9)));
    if (l < 0.18) return hslToHex(h, s, 0.22);
    return c;
  }

  function displayStroke(c, dark) {
    if (!dark) return c;
    const hit = DARK_STROKE[String(c).trim().toLowerCase()];
    if (hit) return hit;
    const rgb = parseColor(c);
    if (!rgb) return c;
    const [h, s, l] = rgbToHsl(rgb);
    if (l < 0.3) return hslToHex(h, s, 0.78);
    if (l < 0.6) return hslToHex(h, s, Math.min(0.7, l + 0.22));
    return c;
  }

  function displayText(c, dark) {
    if (!dark) return c;
    const hit = DARK_TEXT[String(c).trim().toLowerCase()];
    if (hit) return hit;
    const rgb = parseColor(c);
    if (!rgb) return c;
    const [h, s, l] = rgbToHsl(rgb);
    return l < 0.5 ? hslToHex(h, s * 0.6, 0.82) : c;
  }

  // Text must stay readable on what it sits on (the block's drawn fill, or the canvas for a block with no fill), in both themes.
  function readableText(text, fill, dark) {
    const raw = String(fill == null ? '' : fill).trim().toLowerCase();
    let bgL;
    const bg = parseColor(fill);
    if (bg) bgL = luminance(bg);
    else if (!raw || raw === 'none' || raw === 'transparent') bgL = dark ? CANVAS_LUMA.dark : CANVAS_LUMA.light;
    else return text;   // a colour name we cannot measure: leave the text alone
    const fg = parseColor(text);
    if (fg && contrastRatio(luminance(fg), bgL) >= 4.5) return text;
    const pale = contrastRatio(luminance(parseColor(PALE_TEXT)), bgL);
    const ink = contrastRatio(luminance(parseColor(INK_TEXT)), bgL);
    return pale >= ink ? PALE_TEXT : INK_TEXT;
  }

  let editorSeq = 0;   // ids of the svg defs are per editor, so two editors on one page do not share a grid or arrowheads

  const ID_REGEX = /^[A-Za-z0-9_.:-]{1,64}$/;
  const COLOR_REGEX = /^(#[0-9A-Fa-f]{3,8}|rgba?\([0-9., %]+\)|[a-zA-Z]{1,20})$/;
  const VALID_SHAPE_TYPES = new Set([
    'box', 'block', 'rectangle', 'ellipse', 'diamond', 'triangle',
    'rounded_rectangle', 'rounded-rectangle', 'pill',
    'cloud', 'star', 'arrow_right', 'arrow-right',
    'parallelogram', 'hexagon', 'octagon',
    'double_arrow', 'double-arrow',
    'speech_callout', 'speech-callout', 'callout',
    'cylinder', 'database', 'process',
    'note_brace', 'note-brace', 'brace',
    'sticky', 'text'
  ]);
  const VALID_STROKE_STYLES = new Set(['solid', 'dashed', 'dotted', 'thick']);
  const VALID_ALIGN = new Set(['left', 'center', 'right']);
  const VALID_FONT_SIZES = new Set(['S', 'M', 'L']);
  const VALID_CONNECT_ARROWS = new Set(['none', 'end', 'both', 'start', 'to']);
  const VALID_CONNECT_ROUTES = new Set(['straight', 'elbow', 'curved']);
  const VALID_ENDPOINT_SIDES = new Set(['top', 'bottom', 'left', 'right']);
  // Connection points: 4 sides + 4 corners, all on the drawn outline (see anchorPoint)
  const VALID_ENDPOINT_POINTS = new Set([
    'top', 'right', 'bottom', 'left',
    'top-left', 'top-right', 'bottom-right', 'bottom-left'
  ]);
  // Screen-pixel radii for connector end snapping / detaching
  const SNAP_RADIUS_PX = 16;
  const DETACH_RADIUS_PX = 24;
  const VALID_DOMAINS = new Set([
    'power', 'sensing', 'sensors', 'mcu', 'comms', 'rf',
    'drive', 'io', 'ui', 'sticky', 'white', 'none'
  ]);

  function normalizeShapeType(type) {
    if (!type) return 'rectangle';
    const t = String(type).toLowerCase();
    if (t === 'block' || t === 'box') return 'rectangle';
    if (t === 'pill' || t === 'rounded-rectangle') return 'rounded_rectangle';
    if (t === 'arrow-right') return 'arrow_right';
    if (t === 'double-arrow') return 'double_arrow';
    if (t === 'callout' || t === 'speech-callout') return 'speech_callout';
    if (t === 'database') return 'cylinder';
    if (t === 'brace' || t === 'note-brace' || t === 'note') return 'note_brace';
    return t;
  }

  /**
   * Pure geometry: anchor points ON the drawn outline of a shape (not its bounding box).
   * Point names: top, right, bottom, left, top-left, top-right, bottom-right, bottom-left.
   * Shapes with fewer natural points map the missing names to the nearest outline point.
   * Never throws; unknown names resolve to 'right'. Values are plain numbers.
   */
  const ANCHOR_NAMES = ['top', 'right', 'bottom', 'left', 'top-left', 'top-right', 'bottom-right', 'bottom-left'];
  const C45 = Math.SQRT1_2;
  // Fractions [fx, fy] of the box, in ANCHOR_NAMES order, for polygon-like shapes (matching renderShapeSvg)
  const ANCHOR_FRACTIONS = {
    rectangle: [[.5, 0], [1, .5], [.5, 1], [0, .5], [0, 0], [1, 0], [1, 1], [0, 1]],
    diamond: [[.5, 0], [1, .5], [.5, 1], [0, .5], [.25, .25], [.75, .25], [.75, .75], [.25, .75]],
    triangle: [[.5, 0], [.75, .5], [.5, 1], [.25, .5], [.375, .25], [.625, .25], [1, 1], [0, 1]],
    parallelogram: [[.6, 0], [.9, .5], [.4, 1], [.1, .5], [.2, 0], [1, 0], [.8, 1], [0, 1]],
    hexagon: [[.5, 0], [1, .5], [.5, 1], [0, .5], [.22, 0], [.78, 0], [.78, 1], [.22, 1]],
    octagon: [[.5, 0], [1, .5], [.5, 1], [0, .5], [.14, .14], [.86, .14], [.86, .86], [.14, .86]],
    arrow_right: [[.5, .25], [1, .5], [.5, .75], [0, .5], [0, .25], [.6, 0], [.6, 1], [0, .75]],
    double_arrow: [[.5, .25], [1, .5], [.5, .75], [0, .5], [.28, 0], [.72, 0], [.72, 1], [.28, 1]],
    cloud: [[.55, .0925], [.95, .52], [.5, .89], [.08, .5], [.35, .22], [.75, .22], [.8, .8], [.2, .8]],
    note_brace: [[.3, 0], [.92, .5], [.3, 1], [0, .5], [.12, .38], [.92, .3], [.92, .7], [.12, .62]]
  };

  function anchorPoint(shape, pointName) {
    const sh = shape || {};
    const x = Number(sh.x) || 0, y = Number(sh.y) || 0;
    const w = Number(sh.w) || 0, h = Number(sh.h) || 0;
    const type = normalizeShapeType(sh.type);
    let idx = ANCHOR_NAMES.indexOf(pointName);
    if (idx < 0) idx = 1; // unknown / missing name -> 'right' (on the outline)
    let fx, fy;
    if (type === 'ellipse') {
      const t = [[.5, 0], [1, .5], [.5, 1], [0, .5],
        [.5 - .5 * C45, .5 - .5 * C45], [.5 + .5 * C45, .5 - .5 * C45],
        [.5 + .5 * C45, .5 + .5 * C45], [.5 - .5 * C45, .5 + .5 * C45]][idx];
      fx = t[0]; fy = t[1];
    } else if (type === 'rounded_rectangle' || type === 'speech_callout') {
      const bh = type === 'speech_callout' ? 0.76 * h : h;
      const r = type === 'speech_callout' ? Math.min(6, w / 2, bh / 2) : Math.min(w, h) / 2;
      const d = r * (1 - C45);
      const px = [w / 2, w, w / 2, 0, d, w - d, w - d, d][idx];
      const py = [0, bh / 2, bh, bh / 2, d, d, bh - d, bh - d][idx];
      if (type === 'speech_callout' && idx === 7) return { x: x + 0.15 * w, y: y + h }; // tail tip
      return { x: x + px, y: y + py };
    } else if (type === 'cylinder') {
      const ry = 0.18 * h;
      const t = [[.5, 0], [1, .5], [.5, 1], [0, .5],
        [.5 - .5 * C45, ry * (1 - C45) / (h || 1)], [.5 + .5 * C45, ry * (1 - C45) / (h || 1)],
        [.5 + .5 * C45, 1 - ry * (1 - C45) / (h || 1)], [.5 - .5 * C45, 1 - ry * (1 - C45) / (h || 1)]][idx];
      fx = t[0]; fy = t[1];
    } else if (type === 'star') {
      // outer tips (angles -90, -18, 54, 126, 198) and inner notches (18, 90, 162) as in renderShapeSvg
      const rx = w / 2, ry = h / 2, irx = rx * 0.42, iry = ry * 0.42;
      const rad = a => a * Math.PI / 180;
      const tip = a => ({ x: x + rx + rx * Math.cos(rad(a)), y: y + ry + ry * Math.sin(rad(a)) });
      const notch = a => ({ x: x + rx + irx * Math.cos(rad(a)), y: y + ry + iry * Math.sin(rad(a)) });
      return [tip(-90), notch(18), notch(90), notch(162), tip(198), tip(-18), tip(54), tip(126)][idx];
    } else {
      const t = (ANCHOR_FRACTIONS[type] || ANCHOR_FRACTIONS.rectangle)[idx];
      fx = t[0]; fy = t[1];
    }
    return { x: x + fx * w, y: y + fy * h };
  }

  function sanitizeModel(raw) {
    if (!raw || typeof raw !== 'object') {
      return { shapes: [], connectors: [], frames: [] };
    }
    const rawShapes = Array.isArray(raw.shapes) ? raw.shapes : [];
    const rawConnectors = Array.isArray(raw.connectors) ? raw.connectors : [];
    const rawFrames = Array.isArray(raw.frames) ? raw.frames : [];

    const num = (v, def) => (typeof v === 'number' && Number.isFinite(v) ? v : (Number.isFinite(Number(v)) ? Number(v) : def));
    const col = (v, def) => (typeof v === 'string' && COLOR_REGEX.test(v.trim()) ? v.trim() : def);
    const safeId = (v, prefix) => (typeof v === 'string' && ID_REGEX.test(v.trim()) ? v.trim() : uid(prefix));
    const safeEnum = (v, validSet, def) => (typeof v === 'string' && validSet.has(v) ? v : def);

    const idMap = {};
    const shapes = rawShapes.map((s, idx) => {
      if (!s || typeof s !== 'object') s = {};
      const sid = safeId(s.id, 'shape');
      if (s.id && s.id !== sid) {
        idMap[s.id] = sid;
      }
      const rawDom = typeof s.domain === 'string' ? s.domain.toLowerCase() : '';
      const domainVal = VALID_DOMAINS.has(rawDom) ? rawDom : '';
      const defFill = domainVal ? (DOMAIN_PRESETS.find(d => d.id === domainVal)?.fill || '#ffffff') : '#ffffff';
      const defStroke = domainVal ? (DOMAIN_PRESETS.find(d => d.id === domainVal)?.stroke || '#2980b9') : '#2980b9';

      const cleanType = safeEnum(s.type, VALID_SHAPE_TYPES, 'rectangle');

      const clean = {
        id: sid,
        type: cleanType,
        x: num(s.x, 0),
        y: num(s.y, 0),
        w: Math.max(1, num(s.w, 160)),
        h: Math.max(1, num(s.h, 68)),
        text: s.text != null ? String(s.text) : '',
        fill: col(s.fill, defFill),
        stroke: col(s.stroke, defStroke),
        strokeStyle: safeEnum(s.strokeStyle, VALID_STROKE_STYLES, 'solid'),
        strokeWidth: Math.min(50, Math.max(0, num(s.strokeWidth, 2))),
        fontSize: (typeof s.fontSize === 'number' && Number.isFinite(s.fontSize)) ? s.fontSize : safeEnum(s.fontSize, VALID_FONT_SIZES, 'M'),
        bold: s.bold !== false,
        align: safeEnum(s.align, VALID_ALIGN, 'center'),
        z: num(s.z, idx + 1),
        locked: !!s.locked,
      };
      if (domainVal) {
        clean.domain = domainVal;
      }
      if (typeof s.role === 'string') {
        clean.role = s.role;
      }
      return clean;
    });

    const connectors = rawConnectors.map((c) => {
      if (!c || typeof c !== 'object') c = {};
      const cid = safeId(c.id, 'conn');

      const sanitizeEp = (ep, defaultSide, defPos) => {
        if (!ep || typeof ep !== 'object') return { x: defPos.x, y: defPos.y };
        if (ep.shape != null) {
          const rawShapeId = String(ep.shape);
          const mappedShapeId = idMap[rawShapeId] || rawShapeId;
          if (typeof ep.point === 'string' && VALID_ENDPOINT_POINTS.has(ep.point)) {
            return { shape: safeId(mappedShapeId, 'shape'), point: ep.point };
          }
          return {
            shape: safeId(mappedShapeId, 'shape'),
            side: safeEnum(ep.side, VALID_ENDPOINT_SIDES, defaultSide)
          };
        }
        return {
          x: num(ep.x, defPos.x),
          y: num(ep.y, defPos.y)
        };
      };

      return {
        id: cid,
        from: sanitizeEp(c.from, 'right', { x: 0, y: 0 }),
        to: sanitizeEp(c.to, 'left', { x: 100, y: 100 }),
        label: c.label != null ? String(c.label) : '',
        stroke: col(c.stroke, '#64748b'),
        style: safeEnum(c.style, VALID_STROKE_STYLES, 'solid'),
        arrows: safeEnum(c.arrows, VALID_CONNECT_ARROWS, 'end'),
        route: safeEnum(c.route, VALID_CONNECT_ROUTES, 'elbow')
      };
    });

    const frames = rawFrames.map((f) => {
      if (!f || typeof f !== 'object') f = {};
      return {
        id: safeId(f.id, 'frame'),
        x: num(f.x, 0),
        y: num(f.y, 0),
        w: Math.max(1, num(f.w, 320)),
        h: Math.max(1, num(f.h, 200)),
        title: f.title != null ? String(f.title) : 'Domain Frame',
        stroke: col(f.stroke, '#94a3b8')
      };
    });

    return { shapes, connectors, frames };
  }

  /**
   * Shared pan helper for zoomable views.
   */
  function attachPanHelper(target, options = {}) {
    if (!target) return null;

    let activePointerId = null;
    let isDown = false;
    let isPanning = false;
    let downX = 0, downY = 0;
    let downButton = 0;
    let startPanX = 0, startPanY = 0;
    let didDrag = false;
    let suppressContextMenu = false;
    let prevCursor = '';

    const getPan = options.getPan || (() => ({ x: 0, y: 0 }));
    const setPan = options.setPan || (() => {});
    const canPan = options.canPan || ((e) => {
      if (e.button === 2 || e.button === 1) return true;
      if (e.button === 0) {
        if (typeof options.allowLeftPan === 'function') return options.allowLeftPan(e);
        return !!options.allowLeftPan;
      }
      return false;
    });

    function onPointerDown(e) {
      if (!canPan(e)) return;

      isDown = true;
      isPanning = false;
      didDrag = false;
      downX = e.clientX;
      downY = e.clientY;
      downButton = e.button;
      activePointerId = e.pointerId;

      const cur = getPan();
      startPanX = cur.x || 0;
      startPanY = cur.y || 0;

      if (options.onDown) {
        options.onDown(e, { startX: startPanX, startY: startPanY, button: downButton });
      }

      try {
        target.setPointerCapture(e.pointerId);
      } catch (_) {}
    }

    function onPointerMove(e) {
      if (!isDown || activePointerId !== e.pointerId) return;

      const dx = e.clientX - downX;
      const dy = e.clientY - downY;

      if (!didDrag && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
        didDrag = true;
        isPanning = true;
        prevCursor = target.style.cursor;
        target.style.cursor = 'grabbing';
        target.classList.add('is-panning');
        if (downButton === 2) {
          suppressContextMenu = true;
        }
        if (options.onDragStart) {
          options.onDragStart(e, { dx, dy, button: downButton });
        }
      }

      if (isPanning) {
        const nx = startPanX + dx;
        const ny = startPanY + dy;
        setPan(nx, ny, dx, dy, e);
        if (options.onPan) {
          options.onPan({ x: nx, y: ny, dx, dy, e });
        }
      }
    }

    function onPointerUp(e) {
      if (!isDown || (activePointerId !== null && activePointerId !== e.pointerId)) return;

      isDown = false;
      if (activePointerId !== null) {
        try {
          target.releasePointerCapture(activePointerId);
        } catch (_) {}
        activePointerId = null;
      }

      if (isPanning) {
        target.classList.remove('is-panning');
        target.style.cursor = prevCursor;
        isPanning = false;
      }

      if (options.onUp) {
        options.onUp(e, { didDrag, button: downButton });
      }

      if (suppressContextMenu) {
        setTimeout(() => { suppressContextMenu = false; }, 300);
      }
    }

    function onContextMenu(e) {
      if (suppressContextMenu) {
        e.preventDefault();
        e.stopPropagation();
        suppressContextMenu = false;
      }
    }

    target.addEventListener('pointerdown', onPointerDown);
    target.addEventListener('pointermove', onPointerMove);
    target.addEventListener('pointerup', onPointerUp);
    target.addEventListener('pointercancel', onPointerUp);
    target.addEventListener('contextmenu', onContextMenu);
    window.addEventListener('contextmenu', onContextMenu, true);

    return {
      destroy() {
        target.removeEventListener('pointerdown', onPointerDown);
        target.removeEventListener('pointermove', onPointerMove);
        target.removeEventListener('pointerup', onPointerUp);
        target.removeEventListener('pointercancel', onPointerUp);
        target.removeEventListener('contextmenu', onContextMenu);
        window.removeEventListener('contextmenu', onContextMenu, true);
      },
      isDragging: () => didDrag
    };
  }

  /**
   * Clean inline SVG icon generator (~20px stroke style).
   */
  function getIconSvg(name, size = 20) {
    const s = size;
    const base = (inner) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:block;flex:none">${inner}</svg>`;

    switch (name) {
      case 'select':
        return base(`<path d="M4 3l15 11-7 1.5 3.5 6.5-2.5 1.5-3.5-6.5-5.5 5.5z" fill="currentColor"/>`);
      case 'hand':
        return base(`<path d="M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v7M10 10.5V6a2 2 0 0 0-4 0v8a7 7 0 0 0 14 0v-4a2 2 0 0 0-4 0"/>`);
      case 'text':
        return base(`<path d="M5 5h14M12 5v14"/>`);
      case 'sticky':
        return base(`<path d="M4 4h11l5 5v11H4z"/><path d="M15 4v5h5"/>`);
      case 'connector':
        return base(`<path d="M5 19L19 5M12 5h7v7"/>`);
      case 'frame':
        return base(`<rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 3"/>`);
      case 'undo':
        return base(`<path d="M3 9h12a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5H7"/><path d="M7 5L3 9l4 4"/>`);
      case 'redo':
        return base(`<path d="M21 9H9a5 5 0 0 0-5 5v1a5 5 0 0 0 5 5h10"/><path d="M17 5l4 4-4 4"/>`);
      case 'more':
        return base(`<circle cx="5" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="19" cy="12" r="1.5" fill="currentColor"/>`);
      case 'zoom-in':
        return base(`<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>`);
      case 'zoom-out':
        return base(`<line x1="5" y1="12" x2="19" y2="12"/>`);
      case 'fit':
        return base(`<path d="M15 3h6v6M9 21H3v-6M21 9l-7 7M3 15l7-7"/>`);
      case 'change-shape':
        return base(`<rect x="3" y="3" width="8" height="8" rx="1"/><path d="M13 17l4-7 4 7z"/><path d="M18 4h3v3M6 20H3v-3"/>`);
      case 'bold':
        return base(`<path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/>`);
      case 'delete':
        return base(`<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>`);
      case 'label':
        return base(`<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1" fill="currentColor"/>`);
      case 'check':
        return base(`<path d="M5 12.5l4.5 4.5L19 7.5"/>`);
      case 'line-solid':
        return base(`<line x1="3" y1="12" x2="21" y2="12" stroke-width="2.2"/>`);
      case 'line-dashed':
        return base(`<line x1="3" y1="12" x2="21" y2="12" stroke-width="2.2" stroke-dasharray="4 3"/>`);
      case 'line-dotted':
        return base(`<line x1="3" y1="12" x2="21" y2="12" stroke-width="2.4" stroke-dasharray="1.5 2.5" stroke-linecap="round"/>`);
      case 'arrow-none':
        return base(`<line x1="3" y1="12" x2="21" y2="12" stroke-width="2"/>`);
      case 'arrow-end':
        return base(`<line x1="3" y1="12" x2="20" y2="12" stroke-width="2"/><path d="M14 6l6 6-6 6"/>`);
      case 'arrow-both':
        return base(`<line x1="4" y1="12" x2="20" y2="12" stroke-width="2"/><path d="M8 6L2 12l6 6M16 6l6 6-6 6"/>`);
      case 'route-elbow':
        return base(`<path d="M4 19h8V5h8"/>`);
      case 'route-straight':
        return base(`<line x1="4" y1="19" x2="20" y2="5"/>`);
      case 'lock':
        return base(`<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M7 10V6a5 5 0 0 1 10 0v4"/>`);
      case 'unlock':
        return base(`<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M7 10V6a5 5 0 0 1 9.5-2"/>`);
      case 'bring-front':
        return base(`<rect x="7" y="7" width="13" height="13" rx="2"/><path d="M4 14V5a1 1 0 0 1 1-1h9"/>`);
      case 'send-back':
        return base(`<rect x="4" y="4" width="13" height="13" rx="2"/><path d="M10 17v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-2"/>`);
      case 'snap':
        return base(`<path d="M4 4h4v4H4zM16 4h4v4h-4zM4 16h4v4H4zM16 16h4v4h-4z"/><circle cx="12" cy="12" r="2" fill="currentColor"/>`);
      case 'grid':
        return base(`<circle cx="6" cy="6" r="1.5" fill="currentColor"/><circle cx="12" cy="6" r="1.5" fill="currentColor"/><circle cx="18" cy="6" r="1.5" fill="currentColor"/><circle cx="6" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="18" cy="12" r="1.5" fill="currentColor"/><circle cx="6" cy="18" r="1.5" fill="currentColor"/><circle cx="12" cy="18" r="1.5" fill="currentColor"/><circle cx="18" cy="18" r="1.5" fill="currentColor"/>`);
      case 'template':
        return base(`<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 17.5h7M17.5 14v7"/>`);

      // 16 Shapes Icons (standardized to 24x24 viewBox)
      case 'rectangle':
      case 'block':
        return base(`<rect x="3" y="5" width="18" height="14" rx="2"/>`);
      case 'ellipse':
        return base(`<ellipse cx="12" cy="12" rx="9" ry="7"/>`);
      case 'diamond':
        return base(`<path d="M12 3l9 9-9 9-9-9z"/>`);
      case 'triangle':
        return base(`<path d="M12 3l9 17H3z"/>`);
      case 'rounded_rectangle':
      case 'pill':
        return base(`<rect x="3" y="7" width="18" height="10" rx="5"/>`);
      case 'cloud':
        return base(`<path d="M7 17a4 4 0 0 1-1.5-7.7A5 5 0 0 1 15 7.5a4 4 0 0 1 4 4.5A3.5 3.5 0 0 1 18 17z"/>`);
      case 'star':
        return base(`<polygon points="12,2 15,9 22,9.5 17,14.5 18.5,21.5 12,18 5.5,21.5 7,14.5 2,9.5 9,9"/>`);
      case 'arrow_right':
        return base(`<path d="M3 9h11V5l7 7-7 7v-4H3z"/>`);
      case 'parallelogram':
        return base(`<path d="M6 5h15l-3 14H3z"/>`);
      case 'hexagon':
        return base(`<path d="M7 4h10l5 8-5 8H7l-5-8z"/>`);
      case 'octagon':
        return base(`<path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z"/>`);
      case 'double_arrow':
        return base(`<path d="M2 12l5-5v3h10V7l5 5-5 5v-3H7v3z"/>`);
      case 'speech_callout':
        return base(`<path d="M3 4h18v12H9l-5 4v-4H3z"/>`);
      case 'cylinder':
      case 'database':
        return base(`<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>`);
      case 'process':
        return base(`<rect x="3" y="4" width="18" height="16" rx="1"/><line x1="7" y1="4" x2="7" y2="20"/><line x1="17" y1="4" x2="17" y2="20"/>`);
      case 'note_brace':
      case 'brace':
        return base(`<path d="M8 3c-3 0-4 3-4 6 0 1.8-1 3-2 3 1 0 2 1.2 2 3 0 3 1 6 4 6"/><line x1="12" y1="8" x2="20" y2="8"/><line x1="12" y1="12" x2="20" y2="12"/><line x1="12" y1="16" x2="20" y2="16"/>`);

      default:
        return base(`<rect x="4" y="4" width="16" height="16" rx="2"/>`);
    }
  }

  /**
   * Render SVG markup for all shape types scaled to w and h.
   */
  function renderShapeSvg(s, strokeColor, strokeWidth, dashArray) {
    const w = s.w;
    const h = s.h;
    const fill = escapeHtml(s.fill);
    const stroke = escapeHtml(strokeColor);
    const sw = strokeWidth;
    const da = escapeHtml(dashArray);
    const stype = normalizeShapeType(s.type);

    switch (stype) {
      case 'ellipse':
        return `<ellipse cx="${w / 2}" cy="${h / 2}" rx="${w / 2}" ry="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;

      case 'diamond':
        return `<path d="M ${w / 2} 0 L ${w} ${h / 2} L ${w / 2} ${h} L 0 ${h / 2} Z" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;

      case 'triangle':
        return `<path d="M ${w / 2} 0 L ${w} ${h} L 0 ${h} Z" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;

      case 'rounded_rectangle': {
        const r = Math.min(w, h) / 2;
        return `<rect width="${w}" height="${h}" rx="${r}" ry="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'cloud': {
        const d = `M ${0.2 * w} ${0.8 * h} ` +
          `C ${0.05 * w} ${0.8 * h}, 0 ${0.65 * h}, ${0.08 * w} ${0.5 * h} ` +
          `C ${0.02 * w} ${0.35 * h}, ${0.15 * w} ${0.15 * h}, ${0.35 * w} ${0.22 * h} ` +
          `C ${0.45 * w} ${0.05 * h}, ${0.65 * w} ${0.05 * h}, ${0.75 * w} ${0.22 * h} ` +
          `C ${0.9 * w} ${0.18 * h}, ${w} ${0.35 * h}, ${0.95 * w} ${0.52 * h} ` +
          `C ${1.02 * w} ${0.68 * h}, ${0.92 * w} ${0.82 * h}, ${0.8 * w} ${0.8 * h} ` +
          `C ${0.7 * w} ${0.92 * h}, ${0.3 * w} ${0.92 * h}, ${0.2 * w} ${0.8 * h} Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'star': {
        const cx = w / 2, cy = h / 2;
        const rx = w / 2, ry = h / 2;
        const irx = rx * 0.42, iry = ry * 0.42;
        const pts = [];
        for (let i = 0; i < 5; i++) {
          const outerAngle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
          pts.push(`${cx + rx * Math.cos(outerAngle)},${cy + ry * Math.sin(outerAngle)}`);
          const innerAngle = outerAngle + Math.PI / 5;
          pts.push(`${cx + irx * Math.cos(innerAngle)},${cy + iry * Math.sin(innerAngle)}`);
        }
        return `<polygon points="${pts.join(' ')}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'arrow_right': {
        const d = `M 0 ${0.25 * h} H ${0.6 * w} V 0 L ${w} ${0.5 * h} L ${0.6 * w} ${h} V ${0.75 * h} H 0 Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'parallelogram': {
        const d = `M ${0.2 * w} 0 L ${w} 0 L ${0.8 * w} ${h} L 0 ${h} Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'hexagon': {
        const d = `M ${0.22 * w} 0 L ${0.78 * w} 0 L ${w} ${0.5 * h} L ${0.78 * w} ${h} L ${0.22 * w} ${h} L 0 ${0.5 * h} Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'octagon': {
        const cw = 0.28 * w, ch = 0.28 * h;
        const d = `M ${cw} 0 L ${w - cw} 0 L ${w} ${ch} L ${w} ${h - ch} L ${w - cw} ${h} L ${cw} ${h} L 0 ${h - ch} L 0 ${ch} Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'double_arrow': {
        const d = `M 0 ${0.5 * h} L ${0.28 * w} 0 V ${0.25 * h} H ${0.72 * w} V 0 L ${w} ${0.5 * h} L ${0.72 * w} ${h} V ${0.75 * h} H ${0.28 * w} V ${h} Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'speech_callout': {
        const bh = 0.76 * h;
        const r = 6;
        const d = `M ${r} 0 H ${w - r} Q ${w} 0 ${w} ${r} V ${bh - r} Q ${w} ${bh} ${w - r} ${bh} H ${0.35 * w} L ${0.15 * w} ${h} L ${0.22 * w} ${bh} H ${r} Q 0 ${bh} 0 ${bh - r} V ${r} Q 0 0 ${r} 0 Z`;
        return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
      }

      case 'cylinder': {
        const ry = 0.18 * h;
        const bodyD = `M 0 ${ry} A ${w / 2} ${ry} 0 0 1 ${w} ${ry} V ${h - ry} A ${w / 2} ${ry} 0 0 1 0 ${h - ry} Z`;
        const rimD = `M 0 ${ry} A ${w / 2} ${ry} 0 0 0 ${w} ${ry}`;
        return `<g>
          <path d="${bodyD}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
          <path d="${rimD}" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
        </g>`;
      }

      case 'process': {
        const barW = 0.15 * w;
        return `<g>
          <rect width="${w}" height="${h}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
          <line x1="${barW}" y1="0" x2="${barW}" y2="${h}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
          <line x1="${w - barW}" y1="0" x2="${w - barW}" y2="${h}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
        </g>`;
      }

      case 'note_brace': {
        const d = `M ${0.3 * w} 0 ` +
          `C ${0.16 * w} 0, ${0.12 * w} ${0.2 * h}, ${0.12 * w} ${0.38 * h} ` +
          `C ${0.12 * w} ${0.46 * h}, 0 ${0.5 * h}, 0 ${0.5 * h} ` +
          `C 0 ${0.5 * h}, ${0.12 * w} ${0.54 * h}, ${0.12 * w} ${0.62 * h} ` +
          `C ${0.12 * w} ${0.8 * h}, ${0.16 * w} ${h}, ${0.3 * w} ${h}`;
        return `<g>
          <rect width="${w}" height="${h}" fill="${fill}" stroke="none"/>
          <path d="${d}" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>
          <line x1="${0.42 * w}" y1="${0.3 * h}" x2="${0.92 * w}" y2="${0.3 * h}" stroke="${stroke}" stroke-width="${Math.max(1.2, sw * 0.8)}" stroke-linecap="round"/>
          <line x1="${0.42 * w}" y1="${0.5 * h}" x2="${0.92 * w}" y2="${0.5 * h}" stroke="${stroke}" stroke-width="${Math.max(1.2, sw * 0.8)}" stroke-linecap="round"/>
          <line x1="${0.42 * w}" y1="${0.7 * h}" x2="${0.92 * w}" y2="${0.7 * h}" stroke="${stroke}" stroke-width="${Math.max(1.2, sw * 0.8)}" stroke-linecap="round"/>
        </g>`;
      }

      case 'sticky':
        return `
          <rect width="${w}" height="${h}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>
          <path d="M ${w - 14} ${h} L ${w} ${h - 14} L ${w} ${h} Z" fill="${stroke}" fill-opacity="0.35"/>
        `;

      case 'text':
        return `<rect width="${w}" height="${h}" fill="transparent" stroke="none"/>`;

      case 'rectangle':
      default:
        return `<rect width="${w}" height="${h}" rx="4" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${da}"/>`;
    }
  }

  class DiagramEditor {
    constructor(mountEl, options = {}) {
      this.mountEl = mountEl;
      this.options = options;
      this.onSave = options.onSave || (async () => {});
      this.saveDebounceTimer = null;
      this.destroyed = false;
      this.iid = ++editorSeq;
      this.dark = diagramIsDark();
      this.listeners = [];          // [target, type, fn, options] of everything bound outside this editor's own DOM
      this.kbActive = false;        // the last press was on this canvas, so keys with no focused element are ours

      // Diagram data
      this.data = this.normalizeData(options.data || {});
      this.serverSnapshot = JSON.stringify(this.data);   // what the server last had; a poll that brings the same changes nothing

      // Preview of a proposed diagram: read-only; the live data waits in `stash`
      this.previewing = false;
      this.stash = null;
      this.previewSnap = '';
      this.previewChanged = new Set();

      // Canvas view state
      this.panX = 0;
      this.panY = 0;
      this.scale = 1.0;
      this.snapToGrid = true;
      this.showGrid = true;
      this.gridSize = 20;

      // Auto-fit tracking
      this.userHasPannedOrZoomed = false;

      // Active tool: 'select', 'hand', 'text', 'sticky', 'connector', 'frame' or shape type
      this.tool = 'select';
      this.lastUsedShapeType = 'rectangle';

      // Selection state: IDs
      this.selectedShapeIds = new Set();
      this.selectedConnectorIds = new Set();
      this.selectedFrameIds = new Set();

      // Undo / Redo history & server sync
      this.history = [];
      this.historyIndex = -1;
      this.isDirty = false;
      this.canServerUndo = false;
      this.pulsingShapeIds = null;
      this.pulseTimer = null;
      this.saveHistory();
      this.isDirty = false;   // the first snapshot is the server's, not an edit

      // Interaction flags & cache
      this.isPanning = false;
      this.panStartX = 0;
      this.panStartY = 0;
      this.spacePressed = false;

      this.isMarquee = false;
      this.marqueeStart = { x: 0, y: 0 };
      this.marqueeEnd = { x: 0, y: 0 };

      this.isDraggingItems = false;
      this.dragStartPos = { x: 0, y: 0 };
      this.dragOrigPositions = {};
      this.dragContainedShapeIds = [];

      this.isResizing = false;
      this.resizeHandle = null;
      this.resizeTargetId = null;
      this.resizeTargetType = null;
      this.resizeOrigBounds = null;

      this.isDrawingShape = false;
      this.drawShapeType = null;
      this.drawStart = { x: 0, y: 0 };

      this.isConnecting = false;
      this.connectingFrom = null;
      this.connectingCurrent = { x: 0, y: 0 };
      this.connectSnap = null; // { target, nearShapeIds } while a connector end is being drawn/dragged
      this.draggingConnEnd = null; // { id, end } while dragging an end handle of a connector
      this.lastPointerClient = null; // last pointer position (client px), used for paste-at-cursor
      this.hoveredShapeId = null;

      this.clipboard = null;
      this.editingTextTarget = null;
      this.activePaletteTarget = null; // 'fill' or 'border'

      this.initDom();
      this.bindEvents();
      this.render();
      this.updateEmptyState();
      this.fitContent();

      // ResizeObserver to auto-fit if user hasn't panned/zoomed
      if (typeof ResizeObserver !== 'undefined' && this.mountEl) {
        this.resizeObserver = new ResizeObserver(() => {
          if (!this.alive()) return;
          if (!this.userHasPannedOrZoomed) {
            this.fitContent();
          }
        });
        this.resizeObserver.observe(this.mountEl);
      }

      // The theme changes what is drawn (not what is stored): redraw when it flips
      this.onTheme = () => {
        const dark = diagramIsDark();
        if (dark === this.dark || !this.alive()) return;
        this.dark = dark;
        this.closeAllPopovers();
        this.render();
      };
      if (typeof window !== 'undefined' && window.matchMedia) {
        this.themeQuery = window.matchMedia('(prefers-color-scheme: dark)');
        if (this.themeQuery.addEventListener) this.themeQuery.addEventListener('change', this.onTheme);
      }
      if (typeof MutationObserver !== 'undefined') {
        this.themeObserver = new MutationObserver(this.onTheme);
        this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      }
    }

    /** False once destroyed, or when the canvas has left the page without anyone saying so (then it cleans up itself). */
    alive() {
      if (this.destroyed) return false;
      if (!this.mountEl.isConnected) {
        this.destroy();
        return false;
      }
      return true;
    }

    /** Bind outside this editor's own DOM; destroy() undoes every one of these. */
    listen(target, type, fn, opts) {
      target.addEventListener(type, fn, opts);
      this.listeners.push([target, type, fn, opts]);
    }

    /** Let go of the page: send a pending edit, stop every listener, timer and observer. Safe to call twice. */
    destroy() {
      if (this.destroyed) return;
      this.flushSave();
      this.destroyed = true;
      for (const [target, type, fn, opts] of this.listeners) target.removeEventListener(type, fn, opts);
      this.listeners = [];
      if (this.panHelper) this.panHelper.destroy();
      if (this.resizeObserver) this.resizeObserver.disconnect();
      if (this.themeObserver) this.themeObserver.disconnect();
      if (this.themeQuery && this.themeQuery.removeEventListener) this.themeQuery.removeEventListener('change', this.onTheme);
      clearTimeout(this.pulseTimer);
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = null;
      if (this.mountEl) {
        this.mountEl.classList.remove('miro-diagram-editor', 'is-preview');
        this.mountEl._diagramEditor = null;
      }
      if (this.options && typeof this.options.onDestroy === 'function') this.options.onDestroy(this);
    }

    normalizeData(raw) {
      return sanitizeModel(raw);
    }

    /** The diagram that belongs to the project: while a proposal is on show, it is the one set aside. */
    liveData() {
      return this.previewing && this.stash ? this.stash.data : this.data;
    }

    isPreviewing() {
      return this.previewing;
    }

    /**
     * Show a proposed diagram, read-only, in place of the live one (setPreview(null) puts the live one back).
     * Blocks and lines that are new or different are marked so the change can be seen at a glance.
     */
    setPreview(proposed) {
      if (this.destroyed) return;
      if (!proposed) {
        if (this.previewing) this.endPreview();
        return;
      }
      const clean = sanitizeModel(proposed);
      const snap = JSON.stringify(clean);
      if (this.previewing && this.previewSnap === snap) return;
      if (!this.previewing) {
        this.commitTextEdit();
        this.stash = { data: this.data, canServerUndo: this.canServerUndo };
        this.clearSelection();
        this.isDraggingItems = this.isResizing = this.isMarquee = this.isDrawingShape = this.isConnecting = false;
        this.draggingConnEnd = null;
      }
      const live = this.stash.data;
      const was = new Map();
      for (const list of [live.shapes, live.connectors, live.frames]) for (const it of list) was.set(it.id, JSON.stringify(it));
      this.previewChanged = new Set();
      for (const list of [clean.shapes, clean.connectors, clean.frames]) {
        for (const it of list) if (was.get(it.id) !== JSON.stringify(it)) this.previewChanged.add(it.id);
      }
      this.previewing = true;
      this.previewSnap = snap;
      this.data = clean;
      this.mountEl.classList.add('is-preview');
      this.render();
      if (!this.userHasPannedOrZoomed) this.fitContent();
      if (this.options.onPreview) this.options.onPreview(true);
    }

    endPreview() {
      if (!this.previewing) return;
      this.previewing = false;
      this.previewSnap = '';
      this.previewChanged = new Set();
      if (this.stash) {
        this.data = this.stash.data;
        this.canServerUndo = this.stash.canServerUndo;
      }
      this.stash = null;
      this.mountEl.classList.remove('is-preview');
      this.clearSelection();
      this.render();
      if (!this.userHasPannedOrZoomed) this.fitContent();
      if (this.options.onPreview) this.options.onPreview(false);
    }

    updateData(newData, touchedIds = []) {
      if (!newData || this.destroyed) return;
      const cleanServer = sanitizeModel(newData);
      const touchedSet = new Set(touchedIds || []);
      const snap = JSON.stringify(cleanServer);

      // The same diagram the server had last time (the poll, an echo of our own save): nothing to do, and the
      // undo history, the selection and the view stay as they are.
      if (!touchedSet.size && snap === this.serverSnapshot) return;
      this.serverSnapshot = snap;
      if (this.previewing) this.endPreview();

      if (this.isDirty || this.saveDebounceTimer !== null) {
        // Student has unsaved local edits: merge by ID
        // agent-touched IDs take the server version; others keep local version
        const serverShapeMap = new Map((cleanServer.shapes || []).map(s => [s.id, s]));
        const localShapes = (this.data.shapes || []);
        const mergedShapes = [];
        const seenShapeIds = new Set();

        for (const ls of localShapes) {
          if (touchedSet.has(ls.id)) {
            if (serverShapeMap.has(ls.id)) {
              mergedShapes.push(clone(serverShapeMap.get(ls.id)));
            }
          } else {
            mergedShapes.push(clone(ls));
          }
          seenShapeIds.add(ls.id);
        }
        for (const ss of (cleanServer.shapes || [])) {
          if (!seenShapeIds.has(ss.id)) {
            mergedShapes.push(clone(ss));
            seenShapeIds.add(ss.id);
          }
        }

        const serverConnMap = new Map((cleanServer.connectors || []).map(c => [c.id, c]));
        const localConns = (this.data.connectors || []);
        const mergedConns = [];
        const seenConnIds = new Set();

        for (const lc of localConns) {
          if (touchedSet.has(lc.id)) {
            if (serverConnMap.has(lc.id)) {
              mergedConns.push(clone(serverConnMap.get(lc.id)));
            }
          } else {
            mergedConns.push(clone(lc));
          }
          seenConnIds.add(lc.id);
        }
        for (const sc of (cleanServer.connectors || [])) {
          if (!seenConnIds.has(sc.id)) {
            mergedConns.push(clone(sc));
            seenConnIds.add(sc.id);
          }
        }

        const serverFrameMap = new Map((cleanServer.frames || []).map(f => [f.id, f]));
        const localFrames = (this.data.frames || []);
        const mergedFrames = [];
        const seenFrameIds = new Set();

        for (const lf of localFrames) {
          if (touchedSet.has(lf.id)) {
            if (serverFrameMap.has(lf.id)) {
              mergedFrames.push(clone(serverFrameMap.get(lf.id)));
            }
          } else {
            mergedFrames.push(clone(lf));
          }
          seenFrameIds.add(lf.id);
        }
        for (const sf of (cleanServer.frames || [])) {
          if (!seenFrameIds.has(sf.id)) {
            mergedFrames.push(clone(sf));
            seenFrameIds.add(sf.id);
          }
        }

        this.data = sanitizeModel({
          shapes: mergedShapes,
          connectors: mergedConns,
          frames: mergedFrames
        });
      } else {
        this.data = cleanServer;
      }

      if (touchedIds && touchedIds.length > 0) {
        this.pulsingShapeIds = new Set(touchedIds);
        this.canServerUndo = true;
        clearTimeout(this.pulseTimer);
        this.pulseTimer = setTimeout(() => {
          this.pulsingShapeIds = null;
          this.renderShapes();
        }, 2000);
      }

      this.history = [JSON.stringify(this.data)];
      this.historyIndex = 0;
      this.updateUndoRedoButtons();

      this.render();
      this.updateEmptyState();
      if (!this.userHasPannedOrZoomed) {
        this.fitContent();
      }
    }

    saveHistory() {
      const snap = JSON.stringify(this.data);
      if (this.historyIndex >= 0 && this.history[this.historyIndex] === snap) {
        return;
      }
      this.isDirty = true;
      this.history = this.history.slice(0, this.historyIndex + 1);
      this.history.push(snap);
      if (this.history.length > 50) this.history.shift();
      this.historyIndex = this.history.length - 1;
      this.updateUndoRedoButtons();
    }

    async undo() {
      if (this.historyIndex > 0) {
        this.historyIndex--;
        this.data = sanitizeModel(JSON.parse(this.history[this.historyIndex]));
        this.clearSelection();
        this.render();
        this.triggerAutosave();
        this.updateUndoRedoButtons();
        this.updateEmptyState();
      } else if (this.canServerUndo || (this.options && (this.options.onServerUndo || this.options.project))) {
        try {
          let undoneData = null;
          if (this.options && this.options.onServerUndo) {
            undoneData = await this.options.onServerUndo();
          } else {
            const url = '/api/idea/diagram/undo' + (this.options && this.options.project ? `?project=${encodeURIComponent(this.options.project)}` : '');
            const res = await fetch(url, { method: 'POST' });
            if (res.ok) {
              const json = await res.json();
              undoneData = json.diagram;
            }
          }
          if (undoneData) {
            this.canServerUndo = false;
            this.data = sanitizeModel(undoneData);
            this.serverSnapshot = JSON.stringify(this.data);
            this.history = [JSON.stringify(this.data)];
            this.historyIndex = 0;
            this.clearSelection();
            this.render();
            this.updateUndoRedoButtons();
            this.updateEmptyState();
          }
        } catch (e) {
          console.warn('Server diagram undo failed:', e);
        }
      }
    }

    redo() {
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex++;
        this.data = sanitizeModel(JSON.parse(this.history[this.historyIndex]));
        this.clearSelection();
        this.render();
        this.triggerAutosave();
        this.updateUndoRedoButtons();
        this.updateEmptyState();
      }
    }

    updateUndoRedoButtons() {
      const undoBtn = this.mountEl.querySelector('[data-tool="undo"]');
      const redoBtn = this.mountEl.querySelector('[data-tool="redo"]');
      if (undoBtn) undoBtn.disabled = this.historyIndex <= 0 && !this.canServerUndo;
      if (redoBtn) redoBtn.disabled = this.historyIndex >= this.history.length - 1;
    }

    triggerAutosave() {
      if (this.previewing || this.destroyed) return;   // a preview is never saved
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = setTimeout(() => this.saveNow(), 600);
    }

    /** Send the live diagram to onSave. Not called while a preview is up unless a save was already waiting: the live one goes, never the preview. */
    async saveNow() {
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = null;
      const sent = clone(this.liveData());
      try {
        await this.onSave(sent);
        this.isDirty = false;
        this.serverSnapshot = JSON.stringify(sanitizeModel(sent));
      } catch (e) {
        console.error('Diagram autosave failed:', e);
      }
    }

    /** A pending edit goes out now (the editor is about to go away). */
    flushSave() {
      if (this.saveDebounceTimer === null) return;
      this.saveNow();
    }

    snap(val) {
      if (!this.snapToGrid) return val;
      return Math.round(val / this.gridSize) * this.gridSize;
    }

    /**
     * The ONE client -> diagram coordinate conversion. Uses the inverse screen CTM of the
     * pan/zoom group, so it is right at any zoom/pan, scroll, pane resize or svg letterboxing.
     */
    clientToDiagram(clientX, clientY) {
      try {
        const ctm = this.viewportEl.getScreenCTM();
        if (ctm) {
          const pt = this.svgEl.createSVGPoint();
          pt.x = clientX;
          pt.y = clientY;
          const p = pt.matrixTransform(ctm.inverse());
          return { x: p.x, y: p.y };
        }
      } catch (_) { /* fall through (e.g. detached/hidden svg) */ }
      const rect = this.svgEl.getBoundingClientRect();
      return {
        x: (clientX - rect.left - this.panX) / this.scale,
        y: (clientY - rect.top - this.panY) / this.scale
      };
    }

    /** Inverse of clientToDiagram (diagram coords -> client coords). */
    diagramToClient(cx, cy) {
      try {
        const ctm = this.viewportEl.getScreenCTM();
        if (ctm) {
          const pt = this.svgEl.createSVGPoint();
          pt.x = cx;
          pt.y = cy;
          const p = pt.matrixTransform(ctm);
          return { x: p.x, y: p.y };
        }
      } catch (_) { /* fall through */ }
      const rect = this.svgEl.getBoundingClientRect();
      return {
        x: rect.left + this.panX + cx * this.scale,
        y: rect.top + this.panY + cy * this.scale
      };
    }

    /** Screen pixels -> diagram units at the current zoom. */
    pxToDiagram(px) {
      return px / (this.scale || 1);
    }

    /* ---------------- DOM & Layout ---------------- */

    initDom() {
      const iid = this.iid;
      this.mountEl.innerHTML = '';
      // The mount point keeps its own class (the shell and the chat find the canvas by it); the look is in idea.css
      this.mountEl.classList.add('miro-diagram-editor');

      // 1. Canvas container: the drawing, and everything that floats over it
      const canvasWrap = document.createElement('div');
      canvasWrap.className = 'diag-canvas-container';
      this.mountEl.appendChild(canvasWrap);
      this.canvasWrap = canvasWrap;

      // 2. SVG canvas
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'diag-svg');
      svg.setAttribute('id', 'diag-svg');
      // No viewBox: user units == CSS px, so pan/zoom maths and clientToDiagram() agree exactly.
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', 'Interactive block diagram');
      svg.setAttribute('width', '100%');
      svg.setAttribute('height', '100%');
      svg.style.cursor = 'default';
      canvasWrap.appendChild(svg);
      this.svgEl = svg;

      // Defs (grid pattern, arrow markers); the ids are per editor
      this.markerEndRef = `url(#diag-arrow-end-${iid})`;
      this.markerStartRef = `url(#diag-arrow-start-${iid})`;
      const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      defs.innerHTML = `
        <pattern id="diag-grid-pattern-${iid}" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle class="diag-dot" cx="10" cy="10" r="1.1"/>
        </pattern>
        <marker id="diag-arrow-end-${iid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="context-stroke"/>
        </marker>
        <marker id="diag-arrow-start-${iid}" viewBox="0 0 10 10" refX="2" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 9 1.5 L 0 5 L 9 8.5 z" fill="context-stroke"/>
        </marker>
      `;
      svg.appendChild(defs);
      this.gridPatternEl = defs.querySelector('pattern');

      // Grid background rect
      const gridRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      gridRect.setAttribute('class', 'diag-bg-grid');
      gridRect.setAttribute('width', '100%');
      gridRect.setAttribute('height', '100%');
      gridRect.setAttribute('fill', `url(#diag-grid-pattern-${iid})`);
      svg.appendChild(gridRect);
      this.gridRect = gridRect;

      // Viewport group
      const viewport = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      viewport.setAttribute('class', 'diag-viewport');
      svg.appendChild(viewport);
      this.viewportEl = viewport;

      // Layers
      this.framesLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      this.framesLayer.setAttribute('class', 'diag-layer-frames');
      viewport.appendChild(this.framesLayer);

      this.connectorsLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      this.connectorsLayer.setAttribute('class', 'diag-layer-connectors');
      viewport.appendChild(this.connectorsLayer);

      this.shapesLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      this.shapesLayer.setAttribute('class', 'diag-layer-shapes');
      viewport.appendChild(this.shapesLayer);

      this.overlayLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      this.overlayLayer.setAttribute('class', 'diag-layer-overlay');
      viewport.appendChild(this.overlayLayer);

      // 3. The toolbar: a small floating bar on the top edge of the canvas (icons only; labels are tooltips)
      const rail = document.createElement('div');
      rail.className = 'diag-rail';
      rail.setAttribute('role', 'toolbar');
      rail.setAttribute('aria-label', 'Diagram tools');

      rail.innerHTML = `
        <button type="button" class="diag-rail-btn active" data-tool="select" title="Select (V)" aria-label="Select (V)" aria-pressed="true">${getIconSvg('select', 18)}</button>
        <button type="button" class="diag-rail-btn" data-tool="hand" title="Hand (H)" aria-label="Hand (H)" aria-pressed="false">${getIconSvg('hand', 18)}</button>
        <span class="diag-sep" aria-hidden="true"></span>
        <button type="button" class="diag-rail-btn" data-tool="text" title="Text (T)" aria-label="Text (T)" aria-pressed="false">${getIconSvg('text', 18)}</button>
        <button type="button" class="diag-rail-btn" data-tool="sticky" title="Sticky note (N)" aria-label="Sticky note (N)" aria-pressed="false">${getIconSvg('sticky', 18)}</button>
        <button type="button" class="diag-rail-btn diag-shapes-rail-btn" data-act="toggle-shapes-popover" title="Block (B)" aria-label="Block (B)" aria-pressed="false" aria-haspopup="true">${getIconSvg('rectangle', 18)}</button>
        <button type="button" class="diag-rail-btn" data-tool="connector" title="Connector (L)" aria-label="Connector (L)" aria-pressed="false">${getIconSvg('connector', 18)}</button>
        <button type="button" class="diag-rail-btn" data-tool="frame" title="Frame (F)" aria-label="Frame (F)" aria-pressed="false">${getIconSvg('frame', 18)}</button>
        <span class="diag-sep" aria-hidden="true"></span>
        <button type="button" class="diag-rail-btn" data-tool="undo" title="Undo (Ctrl+Z)" aria-label="Undo (Ctrl+Z)">${getIconSvg('undo', 18)}</button>
        <button type="button" class="diag-rail-btn" data-tool="redo" title="Redo (Ctrl+Y)" aria-label="Redo (Ctrl+Y)">${getIconSvg('redo', 18)}</button>
        <span class="diag-sep" aria-hidden="true"></span>
        <button type="button" class="diag-rail-btn" data-act="toggle-more-menu" title="More options" aria-label="More options" aria-haspopup="true">${getIconSvg('more', 18)}</button>
      `;
      canvasWrap.appendChild(rail);
      this.railEl = rail;

      // 4. Floating context toolbar (filled in by renderContextToolbar)
      const ctxToolbar = document.createElement('div');
      ctxToolbar.className = 'diag-context-toolbar';
      ctxToolbar.setAttribute('role', 'toolbar');
      ctxToolbar.setAttribute('aria-label', 'Selection tools');
      canvasWrap.appendChild(ctxToolbar);
      this.ctxToolbarEl = ctxToolbar;

      // 5. Shapes popover (4x4 grid)
      const shapesPopover = document.createElement('div');
      shapesPopover.className = 'diag-shapes-popover diag-popover';
      shapesPopover.innerHTML = `
        <div class="diag-shape-grid" role="group" aria-label="Shapes">
          ${SHAPES_16.map(s => `
            <button type="button" class="diag-shape-grid-btn" data-shape-type="${s.type}" title="${escapeHtml(s.name)}${s.shortcut ? ' (' + s.shortcut + ')' : ''}" aria-label="${escapeHtml(s.name)}${s.shortcut ? ' (' + s.shortcut + ')' : ''}">${getIconSvg(s.type, 20)}</button>
          `).join('')}
        </div>
      `;
      canvasWrap.appendChild(shapesPopover);
      this.shapesPopoverEl = shapesPopover;

      // 6. Colour palette popover (built when it opens: its swatches follow the theme and the selection)
      const palettePopover = document.createElement('div');
      palettePopover.className = 'diag-palette-popover diag-popover';
      canvasWrap.appendChild(palettePopover);
      this.palettePopoverEl = palettePopover;

      // 7. Context overflow menu
      const ctxOverflowMenu = document.createElement('div');
      ctxOverflowMenu.className = 'diag-ctx-overflow-menu diag-popover diag-menu';
      ctxOverflowMenu.setAttribute('role', 'menu');
      ctxOverflowMenu.innerHTML = `
        <button type="button" class="diag-menu-item" role="menuitem" data-act="toggle-lock">${getIconSvg('lock', 16)}<span>Lock or unlock</span></button>
        <button type="button" class="diag-menu-item" role="menuitem" data-act="bring-front">${getIconSvg('bring-front', 16)}<span>Bring to front</span></button>
        <button type="button" class="diag-menu-item" role="menuitem" data-act="send-back">${getIconSvg('send-back', 16)}<span>Send to back</span></button>
      `;
      canvasWrap.appendChild(ctxOverflowMenu);
      this.ctxOverflowMenuEl = ctxOverflowMenu;

      // 8. Toolbar "more" menu
      const moreMenu = document.createElement('div');
      moreMenu.className = 'diag-more-menu diag-popover diag-menu';
      moreMenu.setAttribute('role', 'menu');
      moreMenu.innerHTML = `
        <button type="button" class="diag-menu-item" role="menuitemcheckbox" aria-checked="true" data-act="toggle-snap">${getIconSvg('snap', 16)}<span>Snap to grid</span><span class="diag-check">${getIconSvg('check', 16)}</span></button>
        <button type="button" class="diag-menu-item" role="menuitemcheckbox" aria-checked="true" data-act="toggle-grid">${getIconSvg('grid', 16)}<span>Dot grid</span><span class="diag-check">${getIconSvg('check', 16)}</span></button>
        <hr>
        <button type="button" class="diag-menu-item" role="menuitem" data-act="load-template">${getIconSvg('template', 16)}<span>Start from template</span></button>
      `;
      canvasWrap.appendChild(moreMenu);
      this.moreMenuEl = moreMenu;

      // 9. Zoom cluster (bottom right of the canvas)
      const zoomCluster = document.createElement('div');
      zoomCluster.className = 'diag-zoom-cluster';
      zoomCluster.setAttribute('role', 'toolbar');
      zoomCluster.setAttribute('aria-label', 'Zoom and view');
      zoomCluster.innerHTML = `
        <button type="button" class="diag-zoom-btn" data-act="zoom-out" title="Zoom out" aria-label="Zoom out">${getIconSvg('zoom-out', 16)}</button>
        <button type="button" class="diag-zoom-btn diag-zoom-val" data-act="zoom-reset" title="Reset zoom to 100%" aria-label="Reset zoom to 100%">100%</button>
        <button type="button" class="diag-zoom-btn" data-act="zoom-in" title="Zoom in" aria-label="Zoom in">${getIconSvg('zoom-in', 16)}</button>
        <span class="diag-sep" aria-hidden="true"></span>
        <button type="button" class="diag-zoom-btn diag-fit-btn" data-act="fit" title="Fit to view" aria-label="Fit to view">${getIconSvg('fit', 14)}<span>Fit</span></button>
      `;
      canvasWrap.appendChild(zoomCluster);
      this.zoomClusterEl = zoomCluster;

      // 10. Inline text editing overlay
      const textOverlay = document.createElement('textarea');
      textOverlay.className = 'diag-text-overlay';
      textOverlay.setAttribute('aria-label', 'Edit text');
      canvasWrap.appendChild(textOverlay);
      this.textOverlayEl = textOverlay;

      // 11. Empty state: a line of help and one button, no card
      const emptyState = document.createElement('div');
      emptyState.className = 'diag-empty-state';
      emptyState.innerHTML = `
        <div class="diag-empty-title">Double-click to add a block</div>
        <div class="diag-empty-sub">or press B. Connect blocks by dragging from their edge.</div>
        <button type="button" class="btn line diag-start-template-btn" data-act="load-template">Start from template</button>
      `;
      canvasWrap.appendChild(emptyState);
      this.emptyStateEl = emptyState;
    }

    /* ---------------- Event Listeners & Binding ---------------- */

    bindEvents() {
      // Toolbar and zoom buttons
      this.mountEl.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        // A preview is read-only: only the view controls work
        if (this.previewing && !['zoom-in', 'zoom-out', 'zoom-reset', 'fit'].includes(btn.dataset.act)) return;

        const tool = btn.dataset.tool;
        if (tool) {
          if (tool === 'undo') return this.undo();
          if (tool === 'redo') return this.redo();
          this.closeAllPopovers();
          this.setTool(tool);
          return;
        }

        const act = btn.dataset.act;
        if (act === 'toggle-shapes-popover') {
          e.stopPropagation();
          this.toggleShapesPopover(btn);
          return;
        }
        if (act === 'toggle-more-menu') {
          e.stopPropagation();
          this.toggleMoreMenu(btn);
          return;
        }
        if (act === 'zoom-in') {
          this.userHasPannedOrZoomed = true;
          this.zoomAtCenter(1.2);
          return;
        }
        if (act === 'zoom-out') {
          this.userHasPannedOrZoomed = true;
          this.zoomAtCenter(0.8);
          return;
        }
        if (act === 'zoom-reset') {
          this.userHasPannedOrZoomed = true;
          this.scale = 1.0;
          this.updateTransform();
          return;
        }
        if (act === 'fit') {
          this.userHasPannedOrZoomed = false;   // Fit means "keep it in view" again
          this.fitContent();
          return;
        }
        if (act === 'toggle-snap') {
          this.snapToGrid = !this.snapToGrid;
          btn.setAttribute('aria-checked', String(this.snapToGrid));
          return;
        }
        if (act === 'toggle-grid') {
          this.showGrid = !this.showGrid;
          this.gridRect.style.display = this.showGrid ? '' : 'none';
          btn.setAttribute('aria-checked', String(this.showGrid));
          return;
        }
        if (act === 'load-template' || e.target.closest('.diag-start-template-btn')) {
          this.closeAllPopovers();
          this.loadTemplate();
          return;
        }
      });

      // Shapes popover grid selection
      this.shapesPopoverEl.addEventListener('click', (e) => {
        const shapeBtn = e.target.closest('.diag-shape-grid-btn');
        if (!shapeBtn) return;
        e.stopPropagation();
        const shapeType = shapeBtn.dataset.shapeType;
        this.selectShapeFromPopover(shapeType);
      });

      // Palette popover color click
      this.palettePopoverEl.addEventListener('click', (e) => {
        const swatchBtn = e.target.closest('.diag-palette-swatch-btn');
        if (swatchBtn) {
          e.stopPropagation();
          const col = swatchBtn.dataset.colorVal;
          this.applyPaletteColor(col);
          return;
        }
        const domBtn = e.target.closest('.diag-domain-swatch-btn');
        if (domBtn) {
          e.stopPropagation();
          const domId = domBtn.dataset.domainId;
          this.applyDomainPreset(domId);
          return;
        }
      });

      // Context menu / overflow items click
      this.ctxOverflowMenuEl.addEventListener('click', (e) => {
        const item = e.target.closest('.diag-menu-item');
        if (!item) return;
        e.stopPropagation();
        const act = item.dataset.act;
        if (act === 'toggle-lock') {
          this.selectedShapeIds.forEach(id => {
            const s = this.data.shapes.find(x => x.id === id);
            if (s) s.locked = !s.locked;
          });
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        } else if (act === 'bring-front') {
          const maxZ = Math.max(0, ...this.data.shapes.map(s => s.z || 0));
          this.selectedShapeIds.forEach(id => {
            const s = this.data.shapes.find(x => x.id === id);
            if (s) s.z = maxZ + 1;
          });
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        } else if (act === 'send-back') {
          const minZ = Math.min(0, ...this.data.shapes.map(s => s.z || 0));
          this.selectedShapeIds.forEach(id => {
            const s = this.data.shapes.find(x => x.id === id);
            if (s) s.z = minZ - 1;
          });
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        }
        this.closeAllPopovers();
      });

      // Canvas Zoom wheel
      this.canvasWrap.addEventListener('wheel', (e) => {
        if (e.target.closest('.diag-popover')) return;   // a long popover scrolls itself
        e.preventDefault();
        this.userHasPannedOrZoomed = true;
        const rect = this.svgEl.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        const newScale = Math.min(Math.max(this.scale * factor, 0.15), 5.0);
        this.panX = mx - (mx - this.panX) * (newScale / this.scale);
        this.panY = my - (my - this.panY) * (newScale / this.scale);
        this.scale = newScale;
        this.updateTransform();
      }, { passive: false });

      // Pan helper (Right-drag, middle-drag, space+left-drag, hand tool; any left-drag in a preview)
      this.panHelper = attachPanHelper(this.svgEl, {
        getPan: () => ({ x: this.panX, y: this.panY }),
        setPan: (x, y) => {
          this.userHasPannedOrZoomed = true;
          this.panX = x;
          this.panY = y;
          this.updateTransform();
        },
        canPan: (e) => {
          if (e.button === 2 || e.button === 1) return true;
          if (e.button === 0 && (this.spacePressed || this.tool === 'hand' || this.previewing)) return true;
          return false;
        },
        onDragStart: () => {
          this.userHasPannedOrZoomed = true;
        },
        onUp: () => {
          this.svgEl.style.cursor = this.restCursor();
        }
      });

      // Mouse events
      this.svgEl.addEventListener('mousedown', (e) => this.onMouseDown(e));
      this.listen(window, 'mousemove', (e) => { if (this.alive()) this.onMouseMove(e); });
      this.listen(window, 'mouseup', (e) => { if (this.alive()) this.onMouseUp(e); });
      this.svgEl.addEventListener('dblclick', (e) => this.onDoubleClick(e));

      // Keys belong to the canvas once it has been pressed, until something else is
      this.listen(window, 'pointerdown', (e) => { this.kbActive = this.mountEl.contains(e.target); }, true);

      // Global click to close popovers when clicking outside
      this.listen(window, 'click', (e) => {
        if (!this.alive()) return;
        if (!e.target.closest('.diag-shapes-popover') &&
            !e.target.closest('.diag-palette-popover') &&
            !e.target.closest('.diag-ctx-overflow-menu') &&
            !e.target.closest('.diag-more-menu') &&
            !e.target.closest('[data-act="toggle-shapes-popover"]') &&
            !e.target.closest('[data-act="toggle-more-menu"]') &&
            !e.target.closest('[data-act="toggle-fill-palette"]') &&
            !e.target.closest('[data-act="toggle-border-palette"]') &&
            !e.target.closest('[data-act="toggle-ctx-shapes"]') &&
            !e.target.closest('[data-act="toggle-ctx-overflow"]')) {
          this.closeAllPopovers();
        }
      });

      // Keyboard shortcuts
      this.listen(window, 'keydown', (e) => { if (this.alive()) this.onKeyDown(e); });
      this.listen(window, 'keyup', (e) => { if (this.alive()) this.onKeyUp(e); });

      // Text Overlay commit
      this.textOverlayEl.addEventListener('blur', () => this.commitTextEdit());
      this.textOverlayEl.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          this.cancelTextEdit();
        } else if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.commitTextEdit();
        }
      });
    }

    /** The cursor of the canvas when nothing is being dragged. */
    restCursor() {
      if (this.previewing || this.tool === 'hand') return 'grab';
      return this.tool === 'select' ? 'default' : 'crosshair';
    }

    closeAllPopovers() {
      if (this.shapesPopoverEl) this.shapesPopoverEl.style.display = 'none';
      if (this.palettePopoverEl) this.palettePopoverEl.style.display = 'none';
      if (this.ctxOverflowMenuEl) this.ctxOverflowMenuEl.style.display = 'none';
      if (this.moreMenuEl) this.moreMenuEl.style.display = 'none';
    }

    /** Show a popover just below its button, inside the canvas (above the button when there is no room below). */
    placePopover(pop, anchorBtn) {
      pop.style.display = 'block';
      const a = anchorBtn.getBoundingClientRect();
      const w = this.canvasWrap.getBoundingClientRect();
      const pw = pop.offsetWidth, ph = pop.offsetHeight;
      let left = a.left - w.left;
      let top = a.bottom - w.top + 6;
      if (left + pw > w.width - 8) left = w.width - pw - 8;
      if (top + ph > w.height - 8) top = a.top - w.top - ph - 6;
      pop.style.left = Math.max(8, left) + 'px';
      pop.style.top = Math.max(8, top) + 'px';
    }

    toggleShapesPopover(anchorBtn) {
      const isVisible = this.shapesPopoverEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;
      this.shapesPopoverEl.querySelectorAll('.diag-shape-grid-btn').forEach(b => {
        b.classList.toggle('is-current', b.dataset.shapeType === this.lastUsedShapeType);
      });
      this.placePopover(this.shapesPopoverEl, anchorBtn);
    }

    toggleMoreMenu(anchorBtn) {
      const isVisible = this.moreMenuEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;
      this.placePopover(this.moreMenuEl, anchorBtn);
    }

    /** The stored colour the first selected item has for 'fill' or 'border' (lower case), to mark it in the palette. */
    currentPaletteColour(type) {
      const shape = this.data.shapes.find(x => this.selectedShapeIds.has(x.id));
      let c = null;
      if (type === 'fill') {
        c = shape && shape.fill;
      } else if (shape) {
        c = shape.stroke;
      } else {
        const conn = this.data.connectors.find(x => this.selectedConnectorIds.has(x.id));
        const frame = this.data.frames.find(x => this.selectedFrameIds.has(x.id));
        c = (conn && conn.stroke) || (frame && frame.stroke);
      }
      return c ? String(c).toLowerCase() : '';
    }

    /** Palette markup: swatches for the fill or the border, and the domain presets. Swatches show how a colour is drawn in this theme. */
    paletteHtml(type) {
      const dark = this.dark;
      const cur = this.currentPaletteColour(type);
      const list = type === 'fill' ? COLOR_SWATCHES : STROKE_SWATCHES;
      const drawn = c => (type === 'fill' ? displayFill(c, dark) : displayStroke(c, dark));
      const swatches = list.map(c => {
        const none = c === 'none';
        const label = none ? 'No colour' : c;
        return `<button type="button" class="diag-palette-swatch-btn${none ? ' diag-swatch-none' : ''}${c.toLowerCase() === cur ? ' is-current' : ''}" data-color-val="${escapeHtml(c)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"${none ? '' : ` style="background:${escapeHtml(drawn(c))}"`}></button>`;
      }).join('');
      const domains = DOMAIN_PRESETS.filter(d => d.id !== 'none').map(d => {
        const fill = displayFill(d.fill, dark);
        const text = readableText(displayText(d.text, dark), fill, dark);
        return `<button type="button" class="diag-domain-swatch-btn" data-domain-id="${d.id}" title="${escapeHtml(d.name)}" aria-label="${escapeHtml(d.name)}" style="background:${escapeHtml(fill)};border-color:${escapeHtml(displayStroke(d.stroke, dark))};color:${escapeHtml(text)}">${escapeHtml(d.name)}</button>`;
      }).join('');
      return `<div class="diag-pal-label">Colours</div><div class="diag-pal-grid">${swatches}</div>` +
        `<div class="diag-pal-label">Domains</div><div class="diag-pal-domains">${domains}</div>`;
    }

    togglePalettePopover(anchorBtn, type) {
      const isVisible = this.palettePopoverEl.style.display === 'block' && this.activePaletteTarget === type;
      this.closeAllPopovers();
      if (isVisible) return;

      this.activePaletteTarget = type;
      this.palettePopoverEl.innerHTML = this.paletteHtml(type);
      this.placePopover(this.palettePopoverEl, anchorBtn);
    }

    toggleCtxOverflow(anchorBtn) {
      const isVisible = this.ctxOverflowMenuEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;
      this.placePopover(this.ctxOverflowMenuEl, anchorBtn);
    }

    selectShapeFromPopover(shapeType) {
      this.lastUsedShapeType = shapeType;
      this.updateShapesRailButton();

      if (this.selectedShapeIds.size > 0) {
        // Change type of selected shapes
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.type = shapeType;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      } else {
        // Switch tool to place this shape
        this.setTool(shapeType);
      }
      this.closeAllPopovers();
    }

    updateShapesRailButton() {
      const shapesBtn = this.mountEl.querySelector('.diag-shapes-rail-btn');
      if (shapesBtn) {
        shapesBtn.innerHTML = getIconSvg(this.lastUsedShapeType || 'rectangle');
        const shObj = SHAPES_16.find(s => s.type === this.lastUsedShapeType) || { name: 'Shapes' };
        shapesBtn.title = `${shObj.name} (B)`;
        shapesBtn.setAttribute('aria-label', `${shObj.name} (B)`);
      }
    }

    applyPaletteColor(color) {
      if (!this.activePaletteTarget) return;

      if (this.activePaletteTarget === 'fill') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.fill = color;
        });
      } else if (this.activePaletteTarget === 'border') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.stroke = color;
        });
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.stroke = color;
        });
        this.selectedFrameIds.forEach(id => {
          const f = this.data.frames.find(x => x.id === id);
          if (f) f.stroke = color;
        });
      }

      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.closeAllPopovers();
    }

    applyDomainPreset(domId) {
      const preset = DOMAIN_PRESETS.find(d => d.id === domId);
      if (!preset) return;

      this.selectedShapeIds.forEach(id => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s) {
          s.fill = preset.fill;
          s.stroke = preset.stroke;
          s.domain = domId;
        }
      });

      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.closeAllPopovers();
    }

    setTool(tool) {
      this.tool = tool;
      // the line tool starts clean: what was selected (and its handles and toolbar) is let go first
      if (tool === 'connector' && (this.selectedShapeIds.size || this.selectedConnectorIds.size || this.selectedFrameIds.size)) {
        this.clearSelection();
        this.render();
      }

      // Update aria-pressed and active classes on rail buttons
      const isShapeTool = VALID_SHAPE_TYPES.has(tool) && tool !== 'sticky' && tool !== 'text';
      this.mountEl.querySelectorAll('.diag-rail-btn[data-tool]:not([data-tool="undo"]):not([data-tool="redo"])').forEach(b => {
        const active = b.dataset.tool === tool;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', active ? 'true' : 'false');
      });

      const shapesBtn = this.mountEl.querySelector('.diag-shapes-rail-btn');
      if (shapesBtn) {
        shapesBtn.classList.toggle('active', isShapeTool);
        shapesBtn.setAttribute('aria-pressed', isShapeTool ? 'true' : 'false');
      }

      this.svgEl.style.cursor = this.restCursor();
    }

    /* ---------------- Mouse Interactions ---------------- */

    onMouseDown(e) {
      if (e.button === 2 || e.button === 1 || this.spacePressed || this.tool === 'hand' || this.previewing) return;
      const canvasPos = this.clientToDiagram(e.clientX, e.clientY);

      // Connector end handle -> drag the end (re-attach / detach)
      const endHandleEl = e.target.closest('.diag-conn-end-handle');
      if (endHandleEl) {
        e.stopPropagation();
        this.startDraggingConnEnd(endHandleEl.dataset.connId, endHandleEl.dataset.end);
        return;
      }

      // Port click -> start connecting
      const portEl = e.target.closest('.diag-port-dot');
      if (portEl) {
        e.stopPropagation();
        this.startConnecting(portEl.dataset.shapeId, portEl.dataset.point);
        return;
      }

      // Resize handle click
      const handleEl = e.target.closest('.diag-handle');
      if (handleEl) {
        e.stopPropagation();
        this.isResizing = true;
        this.resizeHandle = handleEl.dataset.handle;
        this.resizeTargetId = handleEl.dataset.targetId;
        this.resizeTargetType = handleEl.dataset.targetType;
        const item = this.getItemById(this.resizeTargetId, this.resizeTargetType);
        if (item) {
          this.resizeOrigBounds = { x: item.x, y: item.y, w: item.w, h: item.h };
        }
        return;
      }

      // Check click on items
      const shapeEl = e.target.closest('.diag-shape-node');
      const connEl = e.target.closest('.diag-connector-node');
      const frameEl = e.target.closest('.diag-frame-node');

      // Active shape/frame creation
      if (VALID_SHAPE_TYPES.has(this.tool) || this.tool === 'frame') {
        this.isDrawingShape = true;
        this.drawShapeType = this.tool;
        this.drawStart = { x: canvasPos.x, y: canvasPos.y };
        return;
      }

      // Connector tool
      if (this.tool === 'connector') {
        const startSnap = this.findSnapTarget(canvasPos).target;
        if (startSnap) {
          this.startConnecting(startSnap.shape, startSnap.point);
        } else {
          this.startFreeConnecting(canvasPos.x, canvasPos.y);
        }
        return;
      }

      // Select mode
      if (this.tool === 'select') {
        // A double-click is found here: the first press redraws the nodes, and the browser then sends no dblclick.
        const kind = shapeEl ? 'shape' : (connEl ? 'connector' : (frameEl ? 'frame' : ''));
        const pressedId = (shapeEl || connEl || frameEl || {dataset: {}}).dataset.id;
        const last = this.lastPress, now = Date.now();
        this.lastPress = kind ? {kind, id: pressedId, t: now, x: e.clientX, y: e.clientY} : null;
        if (kind && last && last.kind === kind && last.id === pressedId && now - last.t < 400 &&
            Math.hypot(e.clientX - last.x, e.clientY - last.y) < 6) {
          e.preventDefault();   // the press must not move focus off the text box it opens
          e.stopPropagation();
          this.lastPress = null;
          this.startTextEdit(kind, pressedId);
          return;
        }
        if (shapeEl) {
          e.stopPropagation();
          const sid = shapeEl.dataset.id;
          const isShift = e.shiftKey;
          const shape = this.data.shapes.find(s => s.id === sid);

          if (!isShift && !this.selectedShapeIds.has(sid)) {
            this.clearSelection();
          }
          if (isShift) {
            if (this.selectedShapeIds.has(sid)) this.selectedShapeIds.delete(sid);
            else this.selectedShapeIds.add(sid);
          } else {
            this.selectedShapeIds.add(sid);
          }
          this.render();

          if (shape && !shape.locked) {
            this.startDraggingItems(canvasPos);
          }
          return;
        }

        if (connEl) {
          e.stopPropagation();
          const cid = connEl.dataset.id;
          if (!e.shiftKey) this.clearSelection();
          this.selectedConnectorIds.add(cid);
          this.render();
          return;
        }

        if (frameEl) {
          e.stopPropagation();
          const fid = frameEl.dataset.id;
          if (!e.shiftKey) this.clearSelection();
          this.selectedFrameIds.add(fid);
          this.render();
          this.startDraggingFrame(fid, canvasPos);
          return;
        }

        // Marquee on empty space
        if (!e.shiftKey) {
          this.clearSelection();
          this.render();
        }
        this.isMarquee = true;
        this.marqueeStart = { x: canvasPos.x, y: canvasPos.y };
        this.marqueeEnd = { x: canvasPos.x, y: canvasPos.y };
      }
    }

    onMouseMove(e) {
      this.lastPointerClient = { x: e.clientX, y: e.clientY };
      const canvasPos = this.clientToDiagram(e.clientX, e.clientY);

      if (this.isPanning) {
        this.userHasPannedOrZoomed = true;
        this.panX = e.clientX - this.panStartX;
        this.panY = e.clientY - this.panStartY;
        this.updateTransform();
        return;
      }

      if (this.isDrawingShape) {
        this.renderDrawingShapePreview(canvasPos);
        return;
      }

      if (this.isConnecting) {
        this.connectingCurrent = { x: canvasPos.x, y: canvasPos.y };
        this.connectSnap = this.findSnapTarget(canvasPos);
        this.renderConnectingPreview();
        return;
      }

      if (this.draggingConnEnd) {
        this.doDragConnEnd(canvasPos);
        return;
      }

      if (this.isResizing) {
        this.doResize(canvasPos);
        return;
      }

      if (this.isDraggingItems) {
        this.doDragItems(canvasPos);
        return;
      }

      if (this.isMarquee) {
        this.marqueeEnd = { x: canvasPos.x, y: canvasPos.y };
        this.renderMarquee();
        return;
      }

      const shapeNode = e.target.closest ? e.target.closest('.diag-shape-node') : null;
      const sid = shapeNode ? shapeNode.dataset.id : null;
      if (sid !== this.hoveredShapeId) {
        this.hoveredShapeId = sid;
        this.renderPorts();
      }
    }

    onMouseUp(e) {
      const canvasPos = this.clientToDiagram(e.clientX, e.clientY);

      if (this.isPanning) {
        this.isPanning = false;
        this.svgEl.style.cursor = this.tool === 'hand' ? 'grab' : 'default';
      }

      if (this.isDrawingShape) {
        this.finishDrawingShape(canvasPos);
        this.isDrawingShape = false;
        this.setTool('select');
      }

      if (this.isConnecting) {
        this.finishConnecting(canvasPos);
        this.isConnecting = false;
        this.setTool('select');
      }

      if (this.draggingConnEnd) {
        this.finishDragConnEnd(canvasPos);
      }

      if (this.isResizing) {
        this.isResizing = false;
        this.resizeHandle = null;
        this.resizeTargetId = null;
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (this.isDraggingItems) {
        this.isDraggingItems = false;
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (this.isMarquee) {
        this.finishMarquee();
        this.isMarquee = false;
      }
    }

    onDoubleClick(e) {
      if (this.previewing) return;
      const canvasPos = this.clientToDiagram(e.clientX, e.clientY);

      // The first click redraws the nodes (selection), so e.target can be a node that is already gone, or the layer
      // around it: ask what is under the pointer now.
      const hit = document.elementFromPoint(e.clientX, e.clientY);
      const at = hit && this.svgEl.contains(hit) ? hit : e.target;

      // Shape double-click -> inline edit
      const shapeEl = at.closest('.diag-shape-node');
      if (shapeEl) {
        e.stopPropagation();
        this.startTextEdit('shape', shapeEl.dataset.id);
        return;
      }

      // Connector double-click -> edit label
      const connEl = at.closest('.diag-connector-node');
      if (connEl) {
        e.stopPropagation();
        this.startTextEdit('connector', connEl.dataset.id);
        return;
      }

      // Frame double-click -> edit title
      const frameEl = at.closest('.diag-frame-node');
      if (frameEl) {
        e.stopPropagation();
        this.startTextEdit('frame', frameEl.dataset.id);
        return;
      }

      // Empty canvas double-click -> add new block at click point, offset until free, caret in inline edit
      const shapeType = this.lastUsedShapeType || 'rectangle';
      const w = 160, h = 68;
      this.createShapeAt(shapeType, canvasPos.x - w / 2, canvasPos.y - h / 2, w, h, true);
    }

    /**
     * Do keys belong to this canvas? Only when they come from inside it, or from nowhere in particular (the page
     * itself) right after the canvas was pressed. Never from a text field: the requirements list, the chat and the
     * canvas' own text overlay all have their own keys.
     */
    ownsKeys(e) {
      const t = e.target;
      if (t && t.nodeType === 1) {
        const tag = t.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable) return false;
      }
      if (!t || t === document.body || t === document.documentElement) return this.kbActive;
      return this.mountEl.contains(t);
    }

    onKeyDown(e) {
      if (!this.ownsKeys(e) || this.previewing) {
        return;
      }
      // Space or Enter on a focused toolbar button presses that button
      if ((e.code === 'Space' || e.key === 'Enter') && e.target.closest && e.target.closest('button')) {
        return;
      }

      if (e.code === 'Space' && !this.spacePressed) {
        this.spacePressed = true;
        this.svgEl.style.cursor = 'grab';
      }

      const key = e.key.toLowerCase();
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        if (key === 'v') this.setTool('select');
        if (key === 'h') this.setTool('hand');
        if (key === 't') this.setTool('text');
        if (key === 'n') this.setTool('sticky');
        if (key === 'l') this.setTool('connector');
        if (key === 'f') this.setTool('frame');
        if (key === 'b') {
          // B shortcut: place block at centre of view, offset until free, caret in inline edit
          const rect = this.canvasWrap.getBoundingClientRect();
          const center = this.clientToDiagram(rect.left + rect.width / 2, rect.top + rect.height / 2);
          const w = 160, h = 68;
          const free = this.findFreePosition(center.x - w / 2, center.y - h / 2, w, h);
          this.createShapeAt(this.lastUsedShapeType || 'rectangle', free.x, free.y, w, h, true);
        }
        if (key === 'e' || key === 'o') this.setTool('ellipse');
        if (key === 'd') this.setTool('diamond');
        if (key === 'escape') {
          this.closeAllPopovers();
          this.clearSelection();
          this.setTool('select');
          this.render();
        }
        if (key === 'delete' || key === 'backspace') {
          this.deleteSelected();
        }
        if (key === 'enter' || key === 'f2') {
          // Enter or F2 edits the text of the one selected block (or line label, frame title)
          const one = this.selectedShapeIds.size + this.selectedConnectorIds.size + this.selectedFrameIds.size === 1;
          if (one) {
            e.preventDefault();
            this.startTextEditOfSelection();
          }
        }
      }

      // Arrow keys nudge what is selected (and leave the page's own arrow keys alone when nothing is)
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key) &&
          (this.selectedShapeIds.size || this.selectedFrameIds.size)) {
        e.preventDefault();
        const step = e.shiftKey ? (this.snapToGrid ? this.gridSize * 2 : 10) : (this.snapToGrid ? this.gridSize : 1);
        let dx = 0, dy = 0;
        if (e.key === 'ArrowUp') dy = -step;
        if (e.key === 'ArrowDown') dy = step;
        if (e.key === 'ArrowLeft') dx = -step;
        if (e.key === 'ArrowRight') dx = step;
        this.nudgeSelected(dx, dy);
      }

      // Ctrl / Meta shortcuts
      if (e.ctrlKey || e.metaKey) {
        if (key === 'z') {
          e.preventDefault();
          if (e.shiftKey) this.redo();
          else this.undo();
        } else if (key === 'y') {
          e.preventDefault();
          this.redo();
        } else if (key === 'a') {
          e.preventDefault();
          this.selectAll();
        } else if (key === 'c') {
          this.copySelected();
        } else if (key === 'v') {
          this.pasteClipboard();
        } else if (key === 'd') {
          e.preventDefault();
          this.duplicateSelected();
        }
      }
    }

    onKeyUp(e) {
      if (e.code === 'Space' && this.spacePressed) {
        this.spacePressed = false;
        if (!this.isPanning) {
          this.svgEl.style.cursor = this.restCursor();
        }
      }
    }

    /* ---------------- Shape Placement & Free Position ---------------- */

    findFreePosition(x, y, w, h) {
      let curX = this.snap(x);
      let curY = this.snap(y);
      const step = Math.max(20, this.gridSize || 20);
      const maxAttempts = 100;
      let attempts = 0;

      const collides = (cx, cy) => {
        return this.data.shapes.some(s => {
          return !(cx + w <= s.x || cx >= s.x + s.w || cy + h <= s.y || cy >= s.y + s.h);
        });
      };

      while (collides(curX, curY) && attempts < maxAttempts) {
        curX += step;
        curY += step;
        attempts++;
      }
      return { x: curX, y: curY };
    }

    getDefaultSize(type) {
      const defaultSizes = {
        rectangle: { w: 160, h: 68 },
        block: { w: 160, h: 68 },
        ellipse: { w: 140, h: 80 },
        diamond: { w: 120, h: 100 },
        triangle: { w: 140, h: 100 },
        rounded_rectangle: { w: 160, h: 68 },
        cloud: { w: 160, h: 100 },
        star: { w: 120, h: 120 },
        arrow_right: { w: 160, h: 70 },
        parallelogram: { w: 160, h: 70 },
        hexagon: { w: 150, h: 80 },
        octagon: { w: 130, h: 90 },
        double_arrow: { w: 170, h: 70 },
        speech_callout: { w: 160, h: 90 },
        cylinder: { w: 140, h: 90 },
        process: { w: 160, h: 68 },
        note_brace: { w: 140, h: 80 },
        sticky: { w: 140, h: 140 },
        text: { w: 120, h: 36 },
        frame: { w: 320, h: 220 }
      };

      const nt = normalizeShapeType(type);
      return defaultSizes[nt] || defaultSizes[type] || { w: 150, h: 70 };
    }

    createShapeAt(type, x, y, w = null, h = null, autoEdit = false) {
      const normType = normalizeShapeType(type);
      const sz = this.getDefaultSize(type);
      const finalW = w ? Math.max(30, w) : sz.w;
      const finalH = h ? Math.max(25, h) : sz.h;

      if (normType === 'frame' || type === 'frame') {
        const frame = {
          id: uid('frame'),
          x: this.snap(x),
          y: this.snap(y),
          w: this.snap(finalW),
          h: this.snap(finalH),
          title: 'Domain Frame',
          stroke: '#94a3b8'
        };
        this.data.frames.push(frame);
        this.clearSelection();
        this.selectedFrameIds.add(frame.id);
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        this.updateEmptyState();
        if (autoEdit) {
          this.startTextEdit('frame', frame.id);
        }
        return;
      }

      const isSticky = normType === 'sticky';
      const isText = normType === 'text';

      // Default new block text: empty with caret in inline edit
      const initialText = isSticky ? 'Note' : '';

      const shape = {
        id: uid('shape'),
        type: normType,
        x: this.snap(x),
        y: this.snap(y),
        w: this.snap(finalW),
        h: this.snap(finalH),
        text: initialText,
        fill: isSticky ? '#fef9c3' : (isText ? 'none' : '#ffffff'),
        stroke: isSticky ? '#ca8a04' : (isText ? 'none' : '#2980b9'),
        strokeStyle: 'solid',
        strokeWidth: isText ? 0 : 2,
        fontSize: 'M',
        bold: !isSticky,
        align: isText ? 'left' : 'center',
        z: this.data.shapes.length + 1,
        locked: false
      };

      this.data.shapes.push(shape);
      this.clearSelection();
      this.selectedShapeIds.add(shape.id);
      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();

      if (autoEdit) {
        this.startTextEdit('shape', shape.id);
      }
    }

    renderDrawingShapePreview(pos) {
      const x = Math.min(this.drawStart.x, pos.x);
      const y = Math.min(this.drawStart.y, pos.y);
      const w = Math.abs(pos.x - this.drawStart.x);
      const h = Math.abs(pos.y - this.drawStart.y);

      this.overlayLayer.innerHTML = `<rect class="diag-draw-preview" x="${x}" y="${y}" width="${w}" height="${h}" rx="4"/>`;
    }

    finishDrawingShape(pos) {
      this.overlayLayer.innerHTML = '';
      const w = Math.abs(pos.x - this.drawStart.x);
      const h = Math.abs(pos.y - this.drawStart.y);

      if (w < 10 && h < 10) {
        // Click: shape centred on the cursor
        const sz = this.getDefaultSize(this.drawShapeType);
        this.createShapeAt(this.drawShapeType, pos.x - sz.w / 2, pos.y - sz.h / 2, null, null, true);
      } else {
        // Drag: spans exactly from press point to release point (both ends snapped, not the size)
        const x0 = this.snap(Math.min(this.drawStart.x, pos.x));
        const y0 = this.snap(Math.min(this.drawStart.y, pos.y));
        const x1 = this.snap(Math.max(this.drawStart.x, pos.x));
        const y1 = this.snap(Math.max(this.drawStart.y, pos.y));
        this.createShapeAt(this.drawShapeType, x0, y0, x1 - x0, y1 - y0, true);
      }
    }

    /* ---------------- Connectors ---------------- */

    getConnectionPoints(shape) {
      return ANCHOR_NAMES.map(name => {
        const p = anchorPoint(shape, name);
        return { name, x: p.x, y: p.y };
      });
    }

    snapFreePos(pos) {
      return { x: this.snap(pos.x), y: this.snap(pos.y) };
    }

    /**
     * Magnet: find the connection point to snap a connector end to.
     * Within SNAP_RADIUS_PX (screen px) of a shape its points are shown (nearShapeIds) and the
     * nearest point wins. Inside a shape without a specific point -> its nearest side midpoint.
     */
    findSnapTarget(pos) {
      const snapR = this.pxToDiagram(SNAP_RADIUS_PX);
      const nearShapeIds = new Set();
      const sorted = [...this.data.shapes].sort((a, b) => (b.z || 0) - (a.z || 0));
      let best = null;
      let inside = null;
      for (const s of sorted) {
        const inExpanded = pos.x >= s.x - snapR && pos.x <= s.x + s.w + snapR &&
                           pos.y >= s.y - snapR && pos.y <= s.y + s.h + snapR;
        if (!inExpanded) continue;
        nearShapeIds.add(s.id);
        for (const p of this.getConnectionPoints(s)) {
          const d = Math.hypot(p.x - pos.x, p.y - pos.y);
          if (d <= snapR && (!best || d < best.dist)) {
            best = { shape: s.id, point: p.name, x: p.x, y: p.y, dist: d };
          }
        }
        if (!inside && pos.x >= s.x && pos.x <= s.x + s.w && pos.y >= s.y && pos.y <= s.y + s.h) {
          inside = s;
        }
      }
      if (!best && inside) {
        best = this.nearestSidePoint(inside, pos);
      }
      return { target: best, nearShapeIds };
    }

    nearestSidePoint(shape, pos) {
      let best = null;
      for (const p of this.getConnectionPoints(shape)) {
        if (!VALID_ENDPOINT_SIDES.has(p.name)) continue;
        const d = Math.hypot(p.x - pos.x, p.y - pos.y);
        if (!best || d < best.dist) {
          best = { shape: shape.id, point: p.name, x: p.x, y: p.y, dist: d };
        }
      }
      return best;
    }

    /**
     * Endpoint to store when a connector end is dropped at pos.
     * keepNear: when dragging an existing end, a drop within DETACH_RADIUS_PX of a shape
     * still attaches (nearest side midpoint); only a drop further away detaches.
     */
    resolveEndForDrop(pos, keepNear) {
      const sr = this.findSnapTarget(pos);
      if (sr.target) return { shape: sr.target.shape, point: sr.target.point };
      if (keepNear) {
        const dr = this.pxToDiagram(DETACH_RADIUS_PX);
        let near = null;
        for (const s of this.data.shapes) {
          const dx = Math.max(s.x - pos.x, 0, pos.x - (s.x + s.w));
          const dy = Math.max(s.y - pos.y, 0, pos.y - (s.y + s.h));
          const d = Math.hypot(dx, dy);
          if (d <= dr && (!near || d < near.d)) near = { s, d };
        }
        if (near) {
          const sp = this.nearestSidePoint(near.s, pos);
          if (sp) return { shape: sp.shape, point: sp.point };
        }
      }
      const f = this.snapFreePos(pos);
      return { x: f.x, y: f.y };
    }

    /** SVG markup (numbers only) showing connection points of nearby shapes, nearest highlighted. */
    connectionPointsHtml(snapRes) {
      if (!snapRes) return '';
      const r = this.pxToDiagram(4.5);
      const rHi = this.pxToDiagram(7);
      const sw = this.pxToDiagram(1.5);
      let html = '';
      for (const sid of snapRes.nearShapeIds) {
        const s = this.data.shapes.find(x => x.id === sid);
        if (!s) continue;
        for (const p of this.getConnectionPoints(s)) {
          const hi = !!(snapRes.target && snapRes.target.shape === sid && snapRes.target.point === p.name);
          html += `<circle class="diag-conn-point${hi ? ' is-snap' : ''}" cx="${p.x}" cy="${p.y}" r="${hi ? rHi : r}" stroke-width="${sw}" pointer-events="none"/>`;
        }
      }
      return html;
    }

    /** Small end marker: filled when attached to a shape, hollow circle when loose. */
    endMarkerHtml(pos, attached, color) {
      const r = this.pxToDiagram(4.5);
      const sw = this.pxToDiagram(1.8);
      return attached
        ? `<circle cx="${pos.x}" cy="${pos.y}" r="${r}" fill="${color}" pointer-events="none"/>`
        : `<circle class="diag-conn-free-end" cx="${pos.x}" cy="${pos.y}" r="${r}" stroke="${color}" stroke-width="${sw}" pointer-events="none"/>`;
    }

    startConnecting(shapeId, point) {
      this.isConnecting = true;
      this.connectingFrom = { shape: shapeId, point: point };
      this.connectingCurrent = this.getShapePortPosition(shapeId, point);
      this.connectSnap = null;
    }

    startFreeConnecting(x, y) {
      const f = this.snapFreePos({ x, y });
      this.isConnecting = true;
      this.connectingFrom = { x: f.x, y: f.y };
      this.connectingCurrent = { x, y };
      this.connectSnap = null;
    }

    renderConnectingPreview() {
      const from = this.connectingFrom;
      const fromPos = this.getEndpointCoords(from);
      const sr = this.connectSnap;
      const target = sr && sr.target;
      const toPos = target ? { x: target.x, y: target.y } : this.snapFreePos(this.connectingCurrent);
      const pathD = `M ${fromPos.x} ${fromPos.y} L ${toPos.x} ${toPos.y}`;
      this.overlayLayer.innerHTML =
        `<path class="diag-conn-preview" d="${pathD}" pointer-events="none"/>` +
        this.connectionPointsHtml(sr) +
        this.endMarkerHtml(fromPos, !!from.shape, 'var(--sig)') +
        this.endMarkerHtml(toPos, !!target, 'var(--sig)');
    }

    finishConnecting(pos) {
      this.overlayLayer.innerHTML = '';
      this.connectSnap = null;
      const to = this.resolveEndForDrop(pos, false);
      const from = this.connectingFrom;
      const fromPos = this.getEndpointCoords(from);
      const toPos = this.getEndpointCoords(to);
      const sameEnd = from.shape && to.shape && from.shape === to.shape && (from.point || from.side) === to.point;
      if (sameEnd || Math.hypot(fromPos.x - toPos.x, fromPos.y - toPos.y) < this.pxToDiagram(6)) {
        this.render();
        return;
      }

      const conn = {
        id: uid('conn'),
        from: from,
        to: to,
        label: '',
        stroke: '#64748b',
        style: 'solid',
        arrows: 'end',
        route: 'elbow'
      };
      this.data.connectors.push(conn);
      this.clearSelection();   // the new line is not left selected either
      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();
    }

    /* Dragging one end handle of the selected connector */
    startDraggingConnEnd(connId, end) {
      if (end !== 'from' && end !== 'to') return;
      this.draggingConnEnd = { id: connId, end };
      this.connectSnap = null;
    }

    doDragConnEnd(pos) {
      const d = this.draggingConnEnd;
      const c = d && this.data.connectors.find(x => x.id === d.id);
      if (!c) return;
      this.connectSnap = this.findSnapTarget(pos);
      const t = this.connectSnap.target;
      c[d.end] = t ? { shape: t.shape, point: t.point } : this.snapFreePos(pos);
      this.render();
      this.overlayLayer.insertAdjacentHTML('beforeend', this.connectionPointsHtml(this.connectSnap));
    }

    finishDragConnEnd(pos) {
      const d = this.draggingConnEnd;
      this.draggingConnEnd = null;
      this.connectSnap = null;
      const c = d && this.data.connectors.find(x => x.id === d.id);
      if (c) {
        c[d.end] = this.resolveEndForDrop(pos, true);
      }
      this.saveHistory();
      this.triggerAutosave();
      this.render();
    }

    getShapePortPosition(shapeId, point) {
      const s = this.data.shapes.find(x => x.id === shapeId);
      if (!s) return { x: 0, y: 0 };
      return anchorPoint(s, point);
    }

    /** Attached ends are recomputed from the shape every render, so they follow move/resize/undo/agent edits. */
    getEndpointCoords(ep) {
      if (!ep) return { x: 0, y: 0 };
      if (ep.shape) {
        return this.getShapePortPosition(ep.shape, ep.point || ep.side || 'right');
      }
      return { x: Number(ep.x) || 0, y: Number(ep.y) || 0 };
    }

    /** Exit direction of an end: 'v' for top/bottom, 'h' for left/right, null for corners/free ends. */
    endpointDir(ep) {
      const p = ep && ep.shape ? (ep.point || ep.side) : null;
      if (p === 'top' || p === 'bottom') return 'v';
      if (p === 'left' || p === 'right') return 'h';
      return null;
    }

    /** The shape of an elbow route: 'hv' / 'vh' when the ends leave on different axes (a side to a top or bottom:
     *  one bend, out along the start's axis and in along the end's), else 'h' / 'v' (two bends, a middle leg). */
    elbowKind(c, p1, p2) {
      const d1 = this.endpointDir(c.from), d2 = this.endpointDir(c.to);
      if (d1 && d2 && d1 !== d2) return d1 === 'h' ? 'hv' : 'vh';
      const dir = d1 || d2 || (Math.abs(p2.x - p1.x) >= Math.abs(p2.y - p1.y) ? 'h' : 'v');
      return dir === 'v' ? 'v' : 'h';
    }

    buildConnectorPath(c, p1, p2) {
      if (c.route === 'straight') {
        return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
      }
      const k = this.elbowKind(c, p1, p2);
      if (k === 'hv') return `M ${p1.x} ${p1.y} H ${p2.x} V ${p2.y}`;
      if (k === 'vh') return `M ${p1.x} ${p1.y} V ${p2.y} H ${p2.x}`;
      if (k === 'v') {
        const midY = (p1.y + p2.y) / 2;
        return `M ${p1.x} ${p1.y} V ${midY} H ${p2.x} V ${p2.y}`;
      }
      const midX = (p1.x + p2.x) / 2;
      return `M ${p1.x} ${p1.y} H ${midX} V ${p2.y} H ${p2.x}`;
    }

    /** Where a connector's label sits: on the path, in the middle of its longest leg for a one-bend route. */
    connectorLabelPoint(c, p1, p2) {
      if (c.route !== 'straight') {
        const k = this.elbowKind(c, p1, p2);
        const dx = Math.abs(p2.x - p1.x), dy = Math.abs(p2.y - p1.y);
        if (k === 'hv') return dx >= dy ? { x: (p1.x + p2.x) / 2, y: p1.y } : { x: p2.x, y: (p1.y + p2.y) / 2 };
        if (k === 'vh') return dy >= dx ? { x: p1.x, y: (p1.y + p2.y) / 2 } : { x: (p1.x + p2.x) / 2, y: p2.y };
      }
      return { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
    }

    /* ---------------- Dragging & Movement ---------------- */

    startDraggingItems(pos) {
      this.isDraggingItems = true;
      this.dragStartPos = { x: pos.x, y: pos.y };
      this.dragOrigPositions = {};
      this.selectedShapeIds.forEach(id => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s && !s.locked) {
          this.dragOrigPositions[id] = { x: s.x, y: s.y };
        }
      });
    }

    startDraggingFrame(frameId, pos) {
      this.isDraggingItems = true;
      this.dragStartPos = { x: pos.x, y: pos.y };
      this.dragOrigPositions = {};
      const f = this.data.frames.find(x => x.id === frameId);
      if (f) {
        this.dragOrigPositions[frameId] = { x: f.x, y: f.y };
        this.dragContainedShapeIds = [];
        this.data.shapes.forEach(s => {
          const cx = s.x + s.w / 2;
          const cy = s.y + s.h / 2;
          if (cx >= f.x && cx <= f.x + f.w && cy >= f.y && cy <= f.y + f.h) {
            this.dragContainedShapeIds.push(s.id);
            this.dragOrigPositions[s.id] = { x: s.x, y: s.y };
          }
        });
      }
    }

    doDragItems(pos) {
      const rawDx = pos.x - this.dragStartPos.x;
      const rawDy = pos.y - this.dragStartPos.y;
      const dx = this.snapToGrid ? this.snap(rawDx) : rawDx;
      const dy = this.snapToGrid ? this.snap(rawDy) : rawDy;

      Object.entries(this.dragOrigPositions).forEach(([id, orig]) => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s) {
          s.x = Math.round(orig.x + dx);
          s.y = Math.round(orig.y + dy);
        }
        const f = this.data.frames.find(x => x.id === id);
        if (f) {
          f.x = Math.round(orig.x + dx);
          f.y = Math.round(orig.y + dy);
        }
      });

      this.render();
    }

    nudgeSelected(dx, dy) {
      let moved = false;
      this.selectedShapeIds.forEach(id => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s && !s.locked) {
          s.x += dx;
          s.y += dy;
          moved = true;
        }
      });
      this.selectedFrameIds.forEach(id => {
        const f = this.data.frames.find(x => x.id === id);
        if (f) {
          f.x += dx;
          f.y += dy;
          moved = true;
        }
      });
      if (moved) {
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }
    }

    /* ---------------- Resizing ---------------- */

    doResize(pos) {
      const h = this.resizeHandle;
      const orig = this.resizeOrigBounds;
      if (!orig) return;

      let newX = orig.x, newY = orig.y, newW = orig.w, newH = orig.h;

      if (h.includes('e')) newW = Math.max(30, orig.w + (pos.x - (orig.x + orig.w)));
      if (h.includes('s')) newH = Math.max(25, orig.h + (pos.y - (orig.y + orig.h)));
      if (h.includes('w')) {
        const potentialW = orig.w - (pos.x - orig.x);
        if (potentialW >= 30) {
          newX = pos.x;
          newW = potentialW;
        }
      }
      if (h.includes('n')) {
        const potentialH = orig.h - (pos.y - orig.y);
        if (potentialH >= 25) {
          newY = pos.y;
          newH = potentialH;
        }
      }

      if (this.snapToGrid) {
        newX = this.snap(newX);
        newY = this.snap(newY);
        newW = this.snap(newW);
        newH = this.snap(newH);
      }

      const item = this.getItemById(this.resizeTargetId, this.resizeTargetType);
      if (item) {
        item.x = newX;
        item.y = newY;
        item.w = Math.max(30, newW);
        item.h = Math.max(25, newH);
      }
      this.render();
    }

    getItemById(id, type) {
      if (type === 'frame') return this.data.frames.find(f => f.id === id);
      return this.data.shapes.find(s => s.id === id);
    }

    /* ---------------- Marquee Selection ---------------- */

    renderMarquee() {
      const x = Math.min(this.marqueeStart.x, this.marqueeEnd.x);
      const y = Math.min(this.marqueeStart.y, this.marqueeEnd.y);
      const w = Math.abs(this.marqueeEnd.x - this.marqueeStart.x);
      const h = Math.abs(this.marqueeEnd.y - this.marqueeStart.y);

      this.overlayLayer.innerHTML = `<rect class="diag-marquee" x="${x}" y="${y}" width="${w}" height="${h}"/>`;
    }

    finishMarquee() {
      this.overlayLayer.innerHTML = '';
      const mx = Math.min(this.marqueeStart.x, this.marqueeEnd.x);
      const my = Math.min(this.marqueeStart.y, this.marqueeEnd.y);
      const mw = Math.abs(this.marqueeEnd.x - this.marqueeStart.x);
      const mh = Math.abs(this.marqueeEnd.y - this.marqueeStart.y);

      if (mw < 4 && mh < 4) return;

      this.data.shapes.forEach(s => {
        if (s.x < mx + mw && s.x + s.w > mx && s.y < my + mh && s.y + s.h > my) {
          this.selectedShapeIds.add(s.id);
        }
      });
      this.data.frames.forEach(f => {
        if (f.x < mx + mw && f.x + f.w > mx && f.y < my + mh && f.y + f.h > my) {
          this.selectedFrameIds.add(f.id);
        }
      });
      this.render();
    }

    clearSelection() {
      this.selectedShapeIds.clear();
      this.selectedConnectorIds.clear();
      this.selectedFrameIds.clear();
      this.ctxToolbarEl.style.display = 'none';
      this.closeAllPopovers();
    }

    selectAll() {
      this.clearSelection();
      this.data.shapes.forEach(s => this.selectedShapeIds.add(s.id));
      this.data.connectors.forEach(c => this.selectedConnectorIds.add(c.id));
      this.data.frames.forEach(f => this.selectedFrameIds.add(f.id));
      this.render();
    }

    deleteSelected() {
      if (!this.selectedShapeIds.size && !this.selectedConnectorIds.size && !this.selectedFrameIds.size) return;
      const sIds = new Set(this.selectedShapeIds);
      this.data.shapes = this.data.shapes.filter(s => !sIds.has(s.id));
      this.data.connectors = this.data.connectors.filter(c => {
        if (this.selectedConnectorIds.has(c.id)) return false;
        if (c.from.shape && sIds.has(c.from.shape)) return false;
        if (c.to.shape && sIds.has(c.to.shape)) return false;
        return true;
      });
      this.data.frames = this.data.frames.filter(f => !this.selectedFrameIds.has(f.id));

      this.clearSelection();
      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();
    }

    copySelected() {
      const copiedShapes = this.data.shapes.filter(s => this.selectedShapeIds.has(s.id));
      const copiedFrames = this.data.frames.filter(f => this.selectedFrameIds.has(f.id));
      if (copiedShapes.length || copiedFrames.length) {
        this.clipboard = { shapes: clone(copiedShapes), frames: clone(copiedFrames) };
      }
    }

    pasteClipboard(atCursor = true) {
      if (!this.clipboard) return;
      this.clearSelection();
      const sanitized = sanitizeModel({
        shapes: this.clipboard.shapes || [],
        frames: this.clipboard.frames || []
      });
      // Paste at cursor: centre the pasted group's bounding box on the pointer (when it is over the canvas)
      let offX = 24, offY = 24;
      const lp = this.lastPointerClient;
      if (atCursor && lp) {
        const r = this.svgEl.getBoundingClientRect();
        if (lp.x >= r.left && lp.x <= r.right && lp.y >= r.top && lp.y <= r.bottom) {
          const items = [...(sanitized.shapes || []), ...(sanitized.frames || [])];
          if (items.length) {
            const bx0 = Math.min(...items.map(i => i.x));
            const by0 = Math.min(...items.map(i => i.y));
            const bx1 = Math.max(...items.map(i => i.x + i.w));
            const by1 = Math.max(...items.map(i => i.y + i.h));
            const cur = this.clientToDiagram(lp.x, lp.y);
            offX = this.snap(cur.x - (bx1 - bx0) / 2) - bx0;
            offY = this.snap(cur.y - (by1 - by0) / 2) - by0;
          }
        }
      }
      (sanitized.shapes || []).forEach(orig => {
        const copy = clone(orig);
        copy.id = uid('shape');
        copy.x += offX;
        copy.y += offY;
        this.data.shapes.push(copy);
        this.selectedShapeIds.add(copy.id);
      });
      (sanitized.frames || []).forEach(orig => {
        const copy = clone(orig);
        copy.id = uid('frame');
        copy.x += offX;
        copy.y += offY;
        this.data.frames.push(copy);
        this.selectedFrameIds.add(copy.id);
      });
      this.saveHistory();
      this.triggerAutosave();
      this.render();
    }

    duplicateSelected() {
      this.copySelected();
      this.pasteClipboard(false);
    }

    /* ---------------- Inline Text Editing ---------------- */

    startTextEdit(type, id) {
      this.editingTextTarget = { type, id };
      let text = '', bounds = null, fontSz = 14, isBold = false, align = 'center';

      if (type === 'shape') {
        const s = this.data.shapes.find(x => x.id === id);
        if (!s) return;
        text = s.text || '';
        const sp = this.diagramToClient(s.x, s.y);
        bounds = { x: sp.x, y: sp.y, w: s.w * this.scale, h: s.h * this.scale };
        fontSz = s.fontSize === 'S' ? 12 : (s.fontSize === 'L' ? 17 : 14);
        isBold = s.bold;
        align = s.align;
      } else if (type === 'connector') {
        const c = this.data.connectors.find(x => x.id === id);
        if (!c) return;
        text = c.label || '';
        const p1 = this.getEndpointCoords(c.from);
        const p2 = this.getEndpointCoords(c.to);
        const lp = this.connectorLabelPoint(c, p1, p2);    // the editor opens where the label is drawn
        const mid = this.diagramToClient(lp.x - 60, lp.y - 16);
        bounds = { x: mid.x, y: mid.y, w: 120 * this.scale, h: 32 * this.scale };
        fontSz = 12;
      } else if (type === 'frame') {
        const f = this.data.frames.find(x => x.id === id);
        if (!f) return;
        text = f.title || '';
        const sp = this.diagramToClient(f.x + 10, f.y + 6);
        bounds = { x: sp.x, y: sp.y, w: Math.min(220, f.w) * this.scale, h: 32 * this.scale };
        fontSz = 13;
        isBold = true;
        align = 'left';
      }

      if (!bounds) return;

      const overlay = this.textOverlayEl;
      overlay.value = text;
      const wrapRect = this.canvasWrap.getBoundingClientRect();
      overlay.style.left = (bounds.x - wrapRect.left) + 'px';
      overlay.style.top = (bounds.y - wrapRect.top) + 'px';
      overlay.style.width = Math.max(90, bounds.w) + 'px';
      overlay.style.height = Math.max(34, bounds.h) + 'px';
      overlay.style.fontSize = Math.max(11, fontSz * this.scale) + 'px';
      overlay.style.fontWeight = isBold ? '700' : '400';
      overlay.style.textAlign = align;
      overlay.style.display = 'block';

      // preventScroll: focusing an overlay near the edge would scroll the overflow:hidden wrap = a view jump
      overlay.focus({ preventScroll: true });
      overlay.select();
      this.canvasWrap.scrollTop = 0;
      this.canvasWrap.scrollLeft = 0;
    }

    /** Edit the text of the single selected item: a block's text, a line's label or a frame's title. */
    startTextEditOfSelection() {
      if (this.previewing) return;
      const sid = [...this.selectedShapeIds][0], cid = [...this.selectedConnectorIds][0], fid = [...this.selectedFrameIds][0];
      if (sid) this.startTextEdit('shape', sid);
      else if (cid) this.startTextEdit('connector', cid);
      else if (fid) this.startTextEdit('frame', fid);
    }

    /** Esc: close the editor and keep the text as it was. */
    cancelTextEdit() {
      this.editingTextTarget = null;   // the blur that follows then has nothing to commit
      this.textOverlayEl.style.display = 'none';
      this.mountEl.focus({ preventScroll: true });
    }

    commitTextEdit() {
      if (!this.editingTextTarget) return;
      const { type, id } = this.editingTextTarget;
      const newText = this.textOverlayEl.value.trim();
      this.textOverlayEl.style.display = 'none';
      this.editingTextTarget = null;

      if (type === 'shape') {
        const s = this.data.shapes.find(x => x.id === id);
        // a block keeps its words when the box is emptied (an empty new block stays empty: nothing changed)
        if (s && newText && s.text !== newText) {
          s.text = newText;
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        }
      } else if (type === 'connector') {
        const c = this.data.connectors.find(x => x.id === id);
        if (c && c.label !== newText) {
          c.label = newText;
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        }
      } else if (type === 'frame') {
        const f = this.data.frames.find(x => x.id === id);
        if (f && f.title !== newText) {
          f.title = newText || 'Domain Frame';
          this.saveHistory();
          this.triggerAutosave();
          this.render();
        }
      }
    }

    /* ---------------- Rendering & SVG Generation ---------------- */

    render() {
      this.renderFrames();
      this.renderConnectors();
      this.renderShapes();
      this.renderSelectionHandles();
      this.renderContextToolbar();
      this.updateZoomIndicator();
      this.updateEmptyState();
    }

    updateTransform() {
      const matrix = `matrix(${this.scale}, 0, 0, ${this.scale}, ${this.panX}, ${this.panY})`;
      this.viewportEl.setAttribute('transform', matrix);

      if (this.gridPatternEl) {
        this.gridPatternEl.setAttribute('patternTransform', `translate(${this.panX}, ${this.panY}) scale(${this.scale})`);
      }
      this.renderContextToolbar();
      this.updateZoomIndicator();
    }

    updateZoomIndicator() {
      const zoomValEl = this.mountEl.querySelector('.diag-zoom-val');
      if (zoomValEl) {
        zoomValEl.textContent = `${Math.round(this.scale * 100)}%`;
      }
    }

    zoomAtCenter(factor) {
      const rect = this.canvasWrap.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const newScale = Math.min(Math.max(this.scale * factor, 0.15), 5.0);
      this.panX = cx - (cx - this.panX) * (newScale / this.scale);
      this.panY = cy - (cy - this.panY) * (newScale / this.scale);
      this.scale = newScale;
      this.updateTransform();
    }

    fitContent() {
      const allItems = [...(this.data.shapes || []), ...(this.data.frames || [])];
      if (!allItems.length && (!this.data.connectors || !this.data.connectors.length)) {
        this.panX = 60;
        this.panY = 60;
        this.scale = 1.0;
        this.updateTransform();
        return;
      }

      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      allItems.forEach(item => {
        minX = Math.min(minX, item.x);
        minY = Math.min(minY, item.y);
        maxX = Math.max(maxX, item.x + item.w);
        maxY = Math.max(maxY, item.y + item.h);
      });

      (this.data.connectors || []).forEach(c => {
        const p1 = this.getEndpointCoords(c.from);
        const p2 = this.getEndpointCoords(c.to);
        minX = Math.min(minX, p1.x, p2.x);
        minY = Math.min(minY, p1.y, p2.y);
        maxX = Math.max(maxX, p1.x, p2.x);
        maxY = Math.max(maxY, p1.y, p2.y);
      });

      const rect = this.canvasWrap.getBoundingClientRect();
      const viewW = rect.width || this.canvasWrap.clientWidth || 800;
      const viewH = rect.height || this.canvasWrap.clientHeight || 500;

      if (viewW <= 0 || viewH <= 0) {
        requestAnimationFrame(() => {
          if (this.alive() && !this.userHasPannedOrZoomed) this.fitContent();
        });
        return;
      }

      // Ample padding so frames and shapes are never cut at right/bottom edges
      const pad = 60;
      const contentW = Math.max(1, maxX - minX + pad * 2);
      const contentH = Math.max(1, maxY - minY + pad * 2);

      // The toolbar floats on the top edge: when the canvas is tall enough, the drawing is fitted below it
      const topInset = viewH >= 300 ? 44 : 0;
      const fitH = viewH - topInset;
      const scale = Math.min(viewW / contentW, fitH / contentH, 1.15);
      this.scale = Math.max(0.18, scale);
      this.panX = (viewW - (maxX - minX) * this.scale) / 2 - minX * this.scale;
      this.panY = topInset + (fitH - (maxY - minY) * this.scale) / 2 - minY * this.scale;
      this.updateTransform();
    }

    renderFrames() {
      let html = '';
      this.data.frames.forEach(f => {
        const isSel = this.selectedFrameIds.has(f.id);
        const strokeColor = displayStroke(f.stroke || '#94a3b8', this.dark);
        const changed = this.previewing && this.previewChanged.has(f.id);
        html += `
          <g class="diag-frame-node${isSel ? ' is-selected' : ''}${changed ? ' is-changed' : ''}" data-id="${escapeHtml(f.id)}" transform="translate(${f.x}, ${f.y})">
            <rect class="diag-frame-fill" width="${f.w}" height="${f.h}" rx="10"
                  stroke="${escapeHtml(isSel ? 'var(--sig)' : strokeColor)}"
                  stroke-width="${isSel ? 2.5 : 2}"
                  stroke-dasharray="8 6"/>
            <text x="12" y="24" fill="${escapeHtml(strokeColor)}" font-size="12" font-weight="600">${escapeHtml(f.title)}</text>
          </g>
        `;
      });
      this.framesLayer.innerHTML = html;
    }

    renderConnectors() {
      let html = '';
      this.data.connectors.forEach(c => {
        const p1 = this.getEndpointCoords(c.from);
        const p2 = this.getEndpointCoords(c.to);
        const isSel = this.selectedConnectorIds.has(c.id);
        const changed = this.previewing && this.previewChanged.has(c.id);

        const d = this.buildConnectorPath(c, p1, p2);

        const strokeColor = isSel ? 'var(--sig)' : displayStroke(c.stroke || '#64748b', this.dark);
        const strokeWidth = isSel ? 3 : (c.style === 'thick' ? 3.5 : 2);
        const dashArray = c.style === 'dashed' ? '6 4' : (c.style === 'dotted' ? '2 3' : 'none');
        const markerEnd = (c.arrows === 'end' || c.arrows === 'both' || c.arrows === 'to') ? this.markerEndRef : '';
        const markerStart = (c.arrows === 'start' || c.arrows === 'both') ? this.markerStartRef : '';

        const { x: mx, y: my } = this.connectorLabelPoint(c, p1, p2);
        let labelHtml = '';
        if (c.label) {
          const lw = Math.max(c.label.length * 7.5 + 16, 32);
          labelHtml = `
            <g class="diag-conn-label" transform="translate(${mx}, ${my})">
              <rect class="diag-conn-label-box" x="${-lw / 2}" y="-11" width="${lw}" height="22" rx="5" stroke="${escapeHtml(strokeColor)}" stroke-width="1.2"/>
              <text text-anchor="middle" y="4.5" font-size="11" font-weight="600" fill="${escapeHtml(strokeColor)}">
                ${escapeHtml(c.label)}
              </text>
            </g>
          `;
        }

        html += `
          <g class="diag-connector-node${isSel ? ' is-selected' : ''}${changed ? ' is-changed' : ''}" data-id="${escapeHtml(c.id)}">
            <path d="${escapeHtml(d)}" stroke="transparent" stroke-width="14" fill="none" style="cursor:pointer"/>
            <path d="${escapeHtml(d)}" stroke="${escapeHtml(strokeColor)}" stroke-width="${strokeWidth}"
                  stroke-dasharray="${escapeHtml(dashArray)}" fill="none"
                  marker-end="${escapeHtml(markerEnd)}" marker-start="${escapeHtml(markerStart)}"/>
            ${c.from && c.from.shape ? '' : this.endMarkerHtml(p1, false, escapeHtml(strokeColor))}
            ${c.to && c.to.shape ? '' : this.endMarkerHtml(p2, false, escapeHtml(strokeColor))}
            ${labelHtml}
          </g>
        `;
      });
      this.connectorsLayer.innerHTML = html;
    }

    /** How a block is drawn in the current theme: fill, outline and text colours. The stored colours are not touched. */
    shapeColors(s) {
      const dark = this.dark;
      const fill = displayFill(s.fill, dark);
      const stroke = displayStroke(s.stroke || '#2980b9', dark);
      const preset = s.domain ? DOMAIN_PRESETS.find(d => d.id === s.domain) : null;
      const lightText = s.type === 'sticky' ? '#854d0e' : ((preset && preset.text) || '#1e293b');
      return { fill, stroke, text: readableText(displayText(lightText, dark), fill, dark) };
    }

    renderShapes() {
      let html = '';
      const sortedShapes = [...this.data.shapes].sort((a, b) => (a.z || 0) - (b.z || 0));

      sortedShapes.forEach(s => {
        const isSel = this.selectedShapeIds.has(s.id);
        const col = this.shapeColors(s);
        const strokeColor = isSel ? 'var(--sig)' : col.stroke;
        const strokeWidth = isSel ? Math.max(s.strokeWidth, 2.5) : s.strokeWidth;
        const dashArray = s.strokeStyle === 'dashed' ? '6 4' : (s.strokeStyle === 'dotted' ? '2 3' : 'none');
        const fontSz = s.fontSize === 'S' ? 12 : (s.fontSize === 'L' ? 17 : 14);

        const shapeSvg = renderShapeSvg(Object.assign({}, s, { fill: col.fill }), strokeColor, strokeWidth, dashArray);

        // Multiline centered text rendering
        const lines = (s.text || '').split('\n');
        let textAnchor = 'middle';
        let textX = s.w / 2;
        if (s.align === 'left') { textAnchor = 'start'; textX = 14; }
        if (s.align === 'right') { textAnchor = 'end'; textX = s.w - 14; }

        const lineHeight = fontSz * 1.35;
        const totalTextHeight = lines.length * lineHeight;
        const startY = (s.h - totalTextHeight) / 2 + fontSz * 0.9;

        const textLinesSvg = lines.map((line, i) => `
          <tspan x="${textX}" y="${startY + i * lineHeight}" font-size="${fontSz}" font-weight="${s.bold ? (i === 0 ? '700' : '500') : '400'}" fill="${escapeHtml(col.text)}">
            ${escapeHtml(line)}
          </tspan>
        `).join('');

        const lockIcon = s.locked ? `
          <g class="diag-lock" transform="translate(${s.w - 18}, 6)">
            <rect x="2" y="5" width="8" height="6" rx="1"/>
            <path d="M4 5V3a2 2 0 0 1 4 0v2" stroke-width="1.2"/>
          </g>
        ` : '';

        const isPulse = !!(this.pulsingShapeIds && this.pulsingShapeIds.has(s.id));
        const changed = this.previewing && this.previewChanged.has(s.id);
        html += `
          <g class="diag-shape-node ${isSel ? 'is-selected' : ''} ${isPulse ? 'diag-pulse' : ''} ${changed ? 'is-changed' : ''}" data-id="${escapeHtml(s.id)}" transform="translate(${s.x}, ${s.y})">
            ${shapeSvg}
            <text text-anchor="${escapeHtml(textAnchor)}" style="pointer-events:none;">${textLinesSvg}</text>
            ${lockIcon}
          </g>
        `;
      });
      this.shapesLayer.innerHTML = html;
    }

    renderPorts() {
      if (this.isConnecting || this.draggingConnEnd) return;
      this.overlayLayer.querySelectorAll('.diag-port-dot').forEach(p => p.remove());
      if (!this.hoveredShapeId || this.isDraggingItems || this.isResizing) {
        return;
      }
      const s = this.data.shapes.find(x => x.id === this.hoveredShapeId);
      if (!s) return;

      const r = this.pxToDiagram(4.5);
      let html = '';
      this.getConnectionPoints(s).forEach(p => {
        html += `<circle class="diag-port-dot" cx="${p.x}" cy="${p.y}" r="${r}" stroke-width="${this.pxToDiagram(1.5)}"
                         data-shape-id="${escapeHtml(s.id)}" data-point="${escapeHtml(p.name)}"/>`;
      });
      this.overlayLayer.insertAdjacentHTML('beforeend', html);
    }

    renderSelectionHandles() {
      // render() redraws the overlay from scratch (a drag-preview overlay is added after render by its caller)
      this.overlayLayer.innerHTML = '';
      const totalSel = this.selectedShapeIds.size + this.selectedFrameIds.size;

      // One selected connector: two end handles (hollow when loose, filled when attached)
      if (totalSel === 0 && this.selectedConnectorIds.size === 1) {
        const cid = [...this.selectedConnectorIds][0];
        const c = this.data.connectors.find(x => x.id === cid);
        if (c) {
          const er = this.pxToDiagram(6);
          const ew = this.pxToDiagram(2);
          let endsSvg = '';
          [['from', c.from], ['to', c.to]].forEach(([end, ep]) => {
            const pos = this.getEndpointCoords(ep);
            const attached = !!(ep && ep.shape);
            endsSvg += `<circle class="diag-conn-end-handle${attached ? ' is-attached' : ''}" cx="${pos.x}" cy="${pos.y}" r="${er}"
                          stroke-width="${ew}" style="cursor:move"
                          data-conn-id="${escapeHtml(c.id)}" data-end="${escapeHtml(end)}"/>`;
          });
          this.overlayLayer.insertAdjacentHTML('beforeend', endsSvg);
        }
        return;
      }
      if (totalSel !== 1) return;

      let item = null, type = 'shape';
      if (this.selectedShapeIds.size === 1) {
        const sid = [...this.selectedShapeIds][0];
        item = this.data.shapes.find(s => s.id === sid);
      } else if (this.selectedFrameIds.size === 1) {
        const fid = [...this.selectedFrameIds][0];
        item = this.data.frames.find(f => f.id === fid);
        type = 'frame';
      }

      if (!item || item.locked) return;

      const x = item.x, y = item.y, w = item.w, h = item.h;
      const r = 4;
      const handles = [
        { pos: 'nw', x, y, cursor: 'nwse-resize' },
        { pos: 'n', x: x + w / 2, y, cursor: 'ns-resize' },
        { pos: 'ne', x: x + w, y, cursor: 'nesw-resize' },
        { pos: 'e', x: x + w, y: y + h / 2, cursor: 'ew-resize' },
        { pos: 'se', x: x + w, y: y + h, cursor: 'nwse-resize' },
        { pos: 's', x: x + w / 2, y: y + h, cursor: 'ns-resize' },
        { pos: 'sw', x, y: y + h, cursor: 'nesw-resize' },
        { pos: 'w', x, y: y + h / 2, cursor: 'ew-resize' },
      ];

      let handlesSvg = `<rect class="diag-sel-box" x="${x - 1}" y="${y - 1}" width="${w + 2}" height="${h + 2}"/>`;
      handles.forEach(hd => {
        handlesSvg += `
          <rect class="diag-handle" x="${hd.x - r}" y="${hd.y - r}" width="${r * 2}" height="${r * 2}"
                style="cursor:${escapeHtml(hd.cursor)}" data-handle="${escapeHtml(hd.pos)}"
                data-target-id="${escapeHtml(item.id)}" data-target-type="${escapeHtml(type)}"/>
        `;
      });

      this.overlayLayer.insertAdjacentHTML('beforeend', handlesSvg);
    }

    renderContextToolbar() {
      const tb = this.ctxToolbarEl;
      const totalSel = this.selectedShapeIds.size + this.selectedConnectorIds.size + this.selectedFrameIds.size;
      if (totalSel === 0 || this.previewing) {
        tb.style.display = 'none';
        return;
      }

      // Calculate selection bounding box
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      this.selectedShapeIds.forEach(id => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s) {
          minX = Math.min(minX, s.x);
          minY = Math.min(minY, s.y);
          maxX = Math.max(maxX, s.x + s.w);
          maxY = Math.max(maxY, s.y + s.h);
        }
      });
      this.selectedFrameIds.forEach(id => {
        const f = this.data.frames.find(x => x.id === id);
        if (f) {
          minX = Math.min(minX, f.x);
          minY = Math.min(minY, f.y);
          maxX = Math.max(maxX, f.x + f.w);
          maxY = Math.max(maxY, f.y + f.h);
        }
      });
      this.selectedConnectorIds.forEach(id => {
        const c = this.data.connectors.find(x => x.id === id);
        if (c) {
          const p1 = this.getEndpointCoords(c.from);
          const p2 = this.getEndpointCoords(c.to);
          minX = Math.min(minX, p1.x, p2.x);
          minY = Math.min(minY, p1.y, p2.y);
          maxX = Math.max(maxX, p1.x, p2.x);
          maxY = Math.max(maxY, p1.y, p2.y);
        }
      });
      if (!Number.isFinite(minX)) {
        tb.style.display = 'none';
        return;
      }

      const isShapeOnly = this.selectedShapeIds.size > 0 && !this.selectedConnectorIds.size && !this.selectedFrameIds.size;
      const isFrameOnly = this.selectedFrameIds.size > 0 && !this.selectedShapeIds.size && !this.selectedConnectorIds.size;
      const isConnOnly = this.selectedConnectorIds.size > 0 && !this.selectedShapeIds.size && !this.selectedFrameIds.size;
      const dark = this.dark;
      const on = v => (v ? 'active' : '');
      // swatches show how a colour is drawn in this theme; a colour of 'none' is a slashed swatch
      const swatch = (kind, stored, drawn) => (!stored || stored === 'none')
        ? `<span class="diag-swatch-${kind} diag-swatch-none"></span>`
        : `<span class="diag-swatch-${kind}" style="${kind === 'circle' ? 'background' : 'border-color'}:${escapeHtml(drawn)}"></span>`;
      let html;

      if (isShapeOnly) {
        const firstShape = this.data.shapes.find(s => this.selectedShapeIds.has(s.id));
        const fill = firstShape ? firstShape.fill : '#ffffff';
        const stroke = firstShape ? firstShape.stroke : '#2980b9';
        const size = (firstShape && firstShape.fontSize) || 'M';

        html = `
          <button type="button" class="diag-ctx-btn" data-act="edit-shape-text" title="Edit text (Enter)" aria-label="Edit text (Enter)">${getIconSvg('label')}</button>
          <span class="diag-sep" aria-hidden="true"></span>
          <button type="button" class="diag-ctx-btn" data-act="toggle-ctx-shapes" title="Change shape" aria-label="Change shape">${getIconSvg('change-shape')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn" data-act="toggle-fill-palette" title="Fill colour" aria-label="Fill colour">${swatch('circle', fill, displayFill(fill, dark))}</button>
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Border colour" aria-label="Border colour">${swatch('ring', stroke, displayStroke(stroke, dark))}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn ${on(firstShape?.strokeStyle === 'solid')}" data-act="set-border-style" data-val="solid" title="Solid border" aria-label="Solid border" aria-pressed="${firstShape?.strokeStyle === 'solid'}">${getIconSvg('line-solid')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstShape?.strokeStyle === 'dashed')}" data-act="set-border-style" data-val="dashed" title="Dashed border" aria-label="Dashed border" aria-pressed="${firstShape?.strokeStyle === 'dashed'}">${getIconSvg('line-dashed')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstShape?.strokeStyle === 'dotted')}" data-act="set-border-style" data-val="dotted" title="Dotted border" aria-label="Dotted border" aria-pressed="${firstShape?.strokeStyle === 'dotted'}">${getIconSvg('line-dotted')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn diag-ctx-text" data-act="cycle-font-size" title="Text size: ${escapeHtml(size)}" aria-label="Text size: ${escapeHtml(size)}"><span>T</span><small>${escapeHtml(size)}</small></button>
          <button type="button" class="diag-ctx-btn ${on(firstShape?.bold)}" data-act="toggle-bold" title="Bold" aria-label="Bold" aria-pressed="${!!firstShape?.bold}">${getIconSvg('bold')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn danger" data-act="delete-sel" title="Delete" aria-label="Delete">${getIconSvg('delete')}</button>
          <span class="diag-sep" aria-hidden="true"></span>
          <button type="button" class="diag-ctx-btn" data-act="toggle-ctx-overflow" title="More options" aria-label="More options" aria-haspopup="true">${getIconSvg('more')}</button>
        `;
      } else if (isFrameOnly) {
        const firstFrame = this.data.frames.find(f => this.selectedFrameIds.has(f.id));
        const stroke = (firstFrame && firstFrame.stroke) || '#94a3b8';

        html = `
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Border colour" aria-label="Border colour">${swatch('ring', stroke, displayStroke(stroke, dark))}</button>
          <span class="diag-sep" aria-hidden="true"></span>
          <button type="button" class="diag-ctx-btn" data-act="edit-frame-title" title="Edit label" aria-label="Edit label">${getIconSvg('label')}</button>
          <span class="diag-sep" aria-hidden="true"></span>
          <button type="button" class="diag-ctx-btn danger" data-act="delete-sel" title="Delete" aria-label="Delete">${getIconSvg('delete')}</button>
        `;
      } else if (isConnOnly) {
        const firstConn = this.data.connectors.find(c => this.selectedConnectorIds.has(c.id));
        const stroke = (firstConn && firstConn.stroke) || '#64748b';

        html = `
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Line colour" aria-label="Line colour">${swatch('ring', stroke, displayStroke(stroke, dark))}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn ${on(firstConn?.style === 'solid')}" data-act="set-conn-style" data-val="solid" title="Solid line" aria-label="Solid line" aria-pressed="${firstConn?.style === 'solid'}">${getIconSvg('line-solid')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstConn?.style === 'dashed')}" data-act="set-conn-style" data-val="dashed" title="Dashed line" aria-label="Dashed line" aria-pressed="${firstConn?.style === 'dashed'}">${getIconSvg('line-dashed')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstConn?.style === 'dotted')}" data-act="set-conn-style" data-val="dotted" title="Dotted line" aria-label="Dotted line" aria-pressed="${firstConn?.style === 'dotted'}">${getIconSvg('line-dotted')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn ${on(firstConn?.arrows === 'none')}" data-act="set-conn-arrows" data-val="none" title="No arrows" aria-label="No arrows" aria-pressed="${firstConn?.arrows === 'none'}">${getIconSvg('arrow-none')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstConn?.arrows === 'end')}" data-act="set-conn-arrows" data-val="end" title="Arrow at end" aria-label="Arrow at end" aria-pressed="${firstConn?.arrows === 'end'}">${getIconSvg('arrow-end')}</button>
          <button type="button" class="diag-ctx-btn ${on(firstConn?.arrows === 'both')}" data-act="set-conn-arrows" data-val="both" title="Arrows both ends" aria-label="Arrows both ends" aria-pressed="${firstConn?.arrows === 'both'}">${getIconSvg('arrow-both')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn ${on(firstConn?.route !== 'straight')}" data-act="toggle-conn-route" title="Switch between straight and elbow" aria-label="Switch between straight and elbow">${getIconSvg('route-elbow')}</button>
          <button type="button" class="diag-ctx-btn" data-act="edit-conn-label" title="Edit label" aria-label="Edit label">${getIconSvg('label')}</button>
          <span class="diag-sep" aria-hidden="true"></span>

          <button type="button" class="diag-ctx-btn danger" data-act="delete-sel" title="Delete" aria-label="Delete">${getIconSvg('delete')}</button>
        `;
      } else {
        // Mixed selection: common controls only (delete)
        html = `
          <button type="button" class="diag-ctx-btn danger" data-act="delete-sel" title="Delete" aria-label="Delete">${getIconSvg('delete')}</button>
        `;
      }

      // Redrawn on every pan and zoom: only touch the buttons when they changed, so a focused button stays focused
      if (tb._html !== html) {
        tb.innerHTML = html;
        tb._html = html;
      }
      tb.onclick = (e) => this.onContextToolbarClick(e);
      tb.style.display = 'flex';
      this.placeContextToolbar(minX, minY, maxX, maxY);
    }

    /** Above the selection; below it when there is no room above (or when above would sit on the toolbar). */
    placeContextToolbar(minX, minY, maxX, maxY) {
      const tb = this.ctxToolbarEl;
      const wrap = this.canvasWrap.getBoundingClientRect();
      const topPt = this.diagramToClient((minX + maxX) / 2, minY);
      const bottomPt = this.diagramToClient((minX + maxX) / 2, maxY);
      const tw = tb.offsetWidth, th = tb.offsetHeight;
      const left = Math.min(Math.max(8, topPt.x - wrap.left - tw / 2), Math.max(8, wrap.width - tw - 8));

      let y = topPt.y - wrap.top - th - 10;
      const rail = this.railEl.getBoundingClientRect();
      const overRail = left < rail.right - wrap.left + 8 && left + tw > rail.left - wrap.left - 8;
      const minTop = overRail ? rail.bottom - wrap.top + 8 : 8;
      if (y < minTop) y = bottomPt.y - wrap.top + 10;
      y = Math.max(minTop, Math.min(y, wrap.height - th - 8));
      tb.style.left = left + 'px';
      tb.style.top = y + 'px';
    }

    onContextToolbarClick(e) {
      const btn = e.target.closest('[data-act]');
      if (!btn) return;
      const act = btn.dataset.act;

      if (act === 'toggle-ctx-shapes') {
        e.stopPropagation();
        this.toggleShapesPopover(btn);
        return;
      }
      if (act === 'toggle-fill-palette') {
        e.stopPropagation();
        this.togglePalettePopover(btn, 'fill');
        return;
      }
      if (act === 'toggle-border-palette') {
        e.stopPropagation();
        this.togglePalettePopover(btn, 'border');
        return;
      }
      if (act === 'toggle-ctx-overflow') {
        e.stopPropagation();
        this.toggleCtxOverflow(btn);
        return;
      }

      if (act === 'set-border-style') {
        const val = btn.dataset.val;
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.strokeStyle = val;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'cycle-font-size') {
        const sizes = ['S', 'M', 'L'];
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) {
            const nextIdx = (sizes.indexOf(s.fontSize) + 1) % sizes.length;
            s.fontSize = sizes[nextIdx];
          }
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'toggle-bold') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.bold = !s.bold;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'set-conn-style') {
        const val = btn.dataset.val;
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.style = val;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'set-conn-arrows') {
        const val = btn.dataset.val;
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.arrows = val;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'toggle-conn-route') {
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.route = c.route === 'straight' ? 'elbow' : 'straight';
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
        return;
      }

      if (act === 'edit-shape-text') {
        this.startTextEditOfSelection();
        return;
      }

      if (act === 'edit-conn-label') {
        const cid = [...this.selectedConnectorIds][0];
        if (cid) this.startTextEdit('connector', cid);
        return;
      }

      if (act === 'edit-frame-title') {
        const fid = [...this.selectedFrameIds][0];
        if (fid) this.startTextEdit('frame', fid);
        return;
      }

      if (act === 'delete-sel') {
        this.deleteSelected();
        return;
      }
    }

    /* ---------------- Empty State & Templates ---------------- */

    updateEmptyState() {
      const isEmpty = (!this.data.shapes || this.data.shapes.length === 0) &&
                      (!this.data.connectors || this.data.connectors.length === 0) &&
                      (!this.data.frames || this.data.frames.length === 0);
      if (this.emptyStateEl) {
        this.emptyStateEl.style.display = isEmpty && !this.previewing ? 'grid' : 'none';
      }
    }

    loadTemplate() {
      this.data = clone(STARTER_TEMPLATE);
      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();
      this.fitContent();
    }

    static mount(mountEl, options) {
      return new DiagramEditor(mountEl, options);
    }
  }

  DiagramEditor.anchorPoint = anchorPoint;
  DiagramEditor.attachPanHelper = attachPanHelper;
  DiagramEditor.sanitizeModel = sanitizeModel;
  if (typeof window !== 'undefined') {
    window.anchorPoint = anchorPoint;
    window.attachPanHelper = attachPanHelper;
    window.sanitizeModel = sanitizeModel;
  }

  return DiagramEditor;
});
