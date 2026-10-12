/**
 * Lucidchart-like Block Diagram Editor (Vanilla JS & SVG)
 *
 * Features:
 * - Slim vertical icon rail on the left of the canvas (NO text labels, aria-labels & tooltips, ~20px icons, 36px targets)
 * - 4x4 Shapes Popover grid (16 shapes: rectangle, ellipse, diamond, triangle, rounded_rectangle, cloud,
 *   star, arrow_right, parallelogram, hexagon, octagon, double_arrow, speech_callout, cylinder, process, note_brace)
 * - Floating context bar above selection with icons only (fill/border palette, 3 line styles, 3 arrowheads, straight/elbow, text size T▾, bold, delete, overflow ⋯)
 * - Bottom-right zoom cluster (−, %, +, Fit) and rail bottom ⋯ more menu (Snap, Grid, Template)
 * - Infinite canvas with pan, zoom at cursor, dot grid, snap-to-grid, and fit
 * - Click or drag to place shapes/frames; multi-selection; resize handles; keyboard nudging & shortcuts
 * - Connectors with shape ports, following on move, straight/elbow routing, labels
 * - Frames with title at top-left, moving enclosed shapes, rendered behind shapes
 * - Debounced autosave (~600 ms) via /api/idea/diagram
 * - Right-drag pan helper, sanitizeModel, undo/redo, empty-state logic
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
          <path d="M ${w - 14} ${h} L ${w} ${h - 14} L ${w} ${h} Z" fill="rgba(0,0,0,0.15)"/>
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

      // Diagram data
      this.data = this.normalizeData(options.data || {});

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
      this.hoveredPort = null;
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
          if (!this.userHasPannedOrZoomed) {
            this.fitContent();
          }
        });
        this.resizeObserver.observe(this.mountEl);
      }
    }

    normalizeData(raw) {
      return sanitizeModel(raw);
    }

    updateData(newData, touchedIds = []) {
      if (!newData) return;
      const cleanServer = sanitizeModel(newData);
      const touchedSet = new Set(touchedIds || []);

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

    previewProposal(proposalData) {
      if (!proposalData) return;
      this.data = sanitizeModel(proposalData);
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
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = setTimeout(async () => {
        try {
          await this.onSave(clone(this.data));
          this.isDirty = false;
        } catch (e) {
          console.error('Diagram autosave failed:', e);
        } finally {
          this.saveDebounceTimer = null;
        }
      }, 600);
    }

    snap(val) {
      if (!this.snapToGrid) return val;
      return Math.round(val / this.gridSize) * this.gridSize;
    }

    screenToCanvas(clientX, clientY) {
      const rect = this.svgEl.getBoundingClientRect();
      const sx = clientX - rect.left;
      const sy = clientY - rect.top;
      return {
        x: (sx - this.panX) / this.scale,
        y: (sy - this.panY) / this.scale
      };
    }

    canvasToScreen(cx, cy) {
      const rect = this.svgEl.getBoundingClientRect();
      return {
        x: rect.left + this.panX + cx * this.scale,
        y: rect.top + this.panY + cy * this.scale
      };
    }

    /* ---------------- DOM & Layout ---------------- */

    initDom() {
      this.mountEl.innerHTML = '';
      this.mountEl.className = 'miro-diagram-editor';
      this.mountEl.style.cssText = 'position:relative;width:100%;height:100%;display:flex;flex-direction:row;overflow:hidden;background:#f8fafc;user-select:none;font-family:inherit;';

      // 1. Slim Vertical Left Rail
      const rail = document.createElement('div');
      rail.className = 'diag-left-rail';
      rail.setAttribute('role', 'toolbar');
      rail.setAttribute('aria-label', 'Diagram tools');
      rail.style.cssText = 'width:44px;flex:none;height:100%;display:flex;flex-direction:column;align-items:center;gap:4px;padding:6px 4px;background:#ffffff;border-right:1px solid #d6dce8;z-index:10;box-shadow:1px 0 3px rgba(0,0,0,0.03);position:relative;';

      rail.innerHTML = `
        <button type="button" class="diag-rail-btn active" data-tool="select" title="Select (V)" aria-label="Select (V)" aria-pressed="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 3l15 11-7 1.5 3.5 6.5-2.5 1.5-3.5-6.5-5.5 5.5z" fill="currentColor"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="hand" title="Hand (H)" aria-label="Hand (H)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v7M10 10.5V6a2 2 0 0 0-4 0v8a7 7 0 0 0 14 0v-4a2 2 0 0 0-4 0"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="text" title="Text (T)" aria-label="Text (T)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14M12 5v14"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="sticky" title="Sticky note (N)" aria-label="Sticky note (N)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h11l5 5v11H4z"/><path d="M15 4v5h5"/></svg></button>
        <button type="button" class="diag-rail-btn diag-shapes-rail-btn" data-act="toggle-shapes-popover" title="Block / Shapes (B)" aria-label="Block (B)" aria-pressed="false" aria-haspopup="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="connector" title="Connector (L)" aria-label="Connector (L)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 19L19 5M12 5h7v7"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="frame" title="Frame (F)" aria-label="Frame (F)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 3"/></svg></button>

        <div class="diag-rail-sep" style="width:24px;height:1px;background:#e2e8f0;margin:4px 0"></div>

        <button type="button" class="diag-rail-btn" data-tool="undo" title="Undo (Ctrl+Z)" aria-label="Undo (Ctrl+Z)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9h12a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5H7"/><path d="M7 5L3 9l4 4"/></svg></button>
        <button type="button" class="diag-rail-btn" data-tool="redo" title="Redo (Ctrl+Y)" aria-label="Redo (Ctrl+Y)" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 9H9a5 5 0 0 0-5 5v1a5 5 0 0 0 5 5h10"/><path d="M17 5l4 4-4 4"/></svg></button>

        <div style="margin-top:auto;display:flex;flex-direction:column;align-items:center;gap:4px">
          <button type="button" class="diag-rail-btn" data-act="toggle-more-menu" title="More options" aria-label="More options" aria-haspopup="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="19" cy="12" r="1.5" fill="currentColor"/></svg></button>
        </div>
      `;
      this.mountEl.appendChild(rail);
      this.railEl = rail;

      // 2. Canvas Container
      const canvasWrap = document.createElement('div');
      canvasWrap.className = 'diag-canvas-container';
      canvasWrap.style.cssText = 'position:relative;flex:1;min-width:0;height:100%;overflow:hidden;background:#f8fafc;';
      this.mountEl.appendChild(canvasWrap);
      this.canvasWrap = canvasWrap;

      // 3. SVG Canvas
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'diag-svg');
      svg.setAttribute('id', 'diag-svg');
      svg.setAttribute('viewBox', '0 0 860 520');
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', 'Interactive Block diagram');
      svg.setAttribute('width', '100%');
      svg.setAttribute('height', '100%');
      svg.style.cssText = 'display:block;width:100%;height:100%;cursor:default;';
      canvasWrap.appendChild(svg);
      this.svgEl = svg;

      // Defs (grid pattern, arrow markers)
      const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      defs.innerHTML = `
        <pattern id="diag-grid-pattern" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="10" cy="10" r="1.1" fill="#94a3b8" opacity="0.6"/>
        </pattern>
        <marker id="diag-arrow-end" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="context-stroke"/>
        </marker>
        <marker id="diag-arrow-start" viewBox="0 0 10 10" refX="2" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 9 1.5 L 0 5 L 9 8.5 z" fill="context-stroke"/>
        </marker>
      `;
      svg.appendChild(defs);

      // Grid background rect
      const gridRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      gridRect.setAttribute('class', 'diag-bg-grid');
      gridRect.setAttribute('width', '100%');
      gridRect.setAttribute('height', '100%');
      gridRect.setAttribute('fill', 'url(#diag-grid-pattern)');
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

      // 4. Floating Context Toolbar
      const ctxToolbar = document.createElement('div');
      ctxToolbar.className = 'diag-context-toolbar';
      ctxToolbar.setAttribute('role', 'toolbar');
      ctxToolbar.setAttribute('aria-label', 'Context actions');
      ctxToolbar.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;padding:3px 6px;box-shadow:0 4px 14px rgba(0,0,0,0.1);z-index:25;align-items:center;pointer-events:auto;gap:3px;';
      canvasWrap.appendChild(ctxToolbar);
      this.ctxToolbarEl = ctxToolbar;

      // 5. Shapes Popover (4x4 Grid)
      const shapesPopover = document.createElement('div');
      shapesPopover.className = 'diag-shapes-popover';
      shapesPopover.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,0.12);z-index:35;padding:8px;pointer-events:auto;';
      shapesPopover.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(4, 36px);gap:4px;">
          ${SHAPES_16.map(s => `
            <button type="button" class="diag-shape-grid-btn" data-shape-type="${s.type}" title="${escapeHtml(s.name)}${s.shortcut ? ' (' + s.shortcut + ')' : ''}" aria-label="${escapeHtml(s.name)}${s.shortcut ? ' (' + s.shortcut + ')' : ''}" style="width:36px;height:36px;display:flex;align-items:center;justify-content:center;background:transparent;border:1px solid transparent;border-radius:6px;cursor:pointer;padding:0;color:#334155;">
              ${getIconSvg(s.type, 20)}
            </button>
          `).join('')}
        </div>
      `;
      canvasWrap.appendChild(shapesPopover);
      this.shapesPopoverEl = shapesPopover;

      // 6. Color Palette Popover
      const palettePopover = document.createElement('div');
      palettePopover.className = 'diag-palette-popover';
      palettePopover.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,0.12);z-index:35;padding:8px;pointer-events:auto;width:196px;';
      palettePopover.innerHTML = `
        <div style="font-size:11px;font-weight:600;color:#64748b;margin-bottom:6px">PALETTE</div>
        <div style="display:grid;grid-template-columns:repeat(7, 22px);gap:4px;margin-bottom:8px">
          ${COLOR_SWATCHES.map(c => `
            <button type="button" class="diag-palette-swatch-btn" data-color-val="${escapeHtml(c)}" title="${c === 'none' ? 'None' : escapeHtml(c)}" aria-label="${c === 'none' ? 'None' : escapeHtml(c)}" style="width:22px;height:22px;border-radius:4px;border:1px solid #cbd5e1;cursor:pointer;padding:0;background:${c === 'none' ? 'linear-gradient(45deg, #fff 40%, #ef4444 48%, #ef4444 52%, #fff 60%)' : escapeHtml(c)}"></button>
          `).join('')}
        </div>
        <div style="font-size:11px;font-weight:600;color:#64748b;margin-bottom:6px">DOMAIN PRESETS</div>
        <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:4px;">
          ${DOMAIN_PRESETS.filter(d => d.id !== 'none').map(d => `
            <button type="button" class="diag-domain-swatch-btn" data-domain-id="${d.id}" title="${escapeHtml(d.name)}" aria-label="${escapeHtml(d.name)}" style="height:24px;border-radius:4px;border:1.5px solid ${escapeHtml(d.stroke)};background:${escapeHtml(d.fill)};cursor:pointer;font-size:10px;font-weight:600;color:${escapeHtml(d.text)};padding:0 3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              ${escapeHtml(d.name)}
            </button>
          `).join('')}
        </div>
      `;
      canvasWrap.appendChild(palettePopover);
      this.palettePopoverEl = palettePopover;

      // 7. Context Overflow Menu (⋯)
      const ctxOverflowMenu = document.createElement('div');
      ctxOverflowMenu.className = 'diag-ctx-overflow-menu';
      ctxOverflowMenu.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,0.12);z-index:35;padding:4px;pointer-events:auto;min-width:140px;';
      ctxOverflowMenu.innerHTML = `
        <button type="button" class="diag-menu-item" data-act="toggle-lock" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('lock', 16)} <span>Lock / Unlock</span>
        </button>
        <button type="button" class="diag-menu-item" data-act="bring-front" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('bring-front', 16)} <span>Bring to front</span>
        </button>
        <button type="button" class="diag-menu-item" data-act="send-back" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('send-back', 16)} <span>Send to back</span>
        </button>
      `;
      canvasWrap.appendChild(ctxOverflowMenu);
      this.ctxOverflowMenuEl = ctxOverflowMenu;

      // 8. Rail Bottom More Menu (⋯)
      const moreMenu = document.createElement('div');
      moreMenu.className = 'diag-more-menu';
      moreMenu.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,0.12);z-index:35;padding:4px;pointer-events:auto;min-width:170px;left:48px;bottom:10px;';
      moreMenu.innerHTML = `
        <button type="button" class="diag-menu-item" data-act="toggle-snap" title="Snap to grid" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('snap', 16)} <span style="flex:1">Snap to grid</span> <span class="diag-check-snap" style="color:#2563eb;font-weight:700">✓</span>
        </button>
        <button type="button" class="diag-menu-item" data-act="toggle-grid" title="Show dot grid" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('grid', 16)} <span style="flex:1">Dot grid</span> <span class="diag-check-grid" style="color:#2563eb;font-weight:700">✓</span>
        </button>
        <div style="height:1px;background:#e2e8f0;margin:4px 0"></div>
        <button type="button" class="diag-menu-item" data-act="load-template" title="Start from template" style="width:100%;text-align:left;display:flex;align-items:center;gap:8px;padding:6px 10px;border:0;background:none;border-radius:6px;font-size:12.5px;cursor:pointer;color:#334155;">
          ${getIconSvg('template', 16)} <span>Start from template</span>
        </button>
      `;
      canvasWrap.appendChild(moreMenu);
      this.moreMenuEl = moreMenu;

      // 9. Floating Zoom Cluster (Bottom-Right of Canvas)
      const zoomCluster = document.createElement('div');
      zoomCluster.className = 'diag-zoom-cluster';
      zoomCluster.setAttribute('role', 'toolbar');
      zoomCluster.setAttribute('aria-label', 'Zoom and view controls');
      zoomCluster.style.cssText = 'position:absolute;bottom:14px;right:14px;display:flex;align-items:center;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.06);padding:2px 4px;z-index:20;gap:2px;';
      zoomCluster.innerHTML = `
        <button type="button" class="diag-zoom-btn" data-act="zoom-out" title="Zoom Out" aria-label="Zoom Out" style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;background:none;border:0;border-radius:5px;cursor:pointer;color:#334155;">${getIconSvg('zoom-out', 16)}</button>
        <button type="button" class="diag-zoom-btn diag-zoom-val" data-act="zoom-reset" title="Click to reset zoom (100%)" aria-label="Reset zoom to 100%" style="min-width:44px;height:28px;padding:0 4px;font-family:monospace;font-size:12px;font-weight:600;display:flex;align-items:center;justify-content:center;background:none;border:0;border-radius:5px;cursor:pointer;color:#334155;">100%</button>
        <button type="button" class="diag-zoom-btn" data-act="zoom-in" title="Zoom In" aria-label="Zoom In" style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;background:none;border:0;border-radius:5px;cursor:pointer;color:#334155;">${getIconSvg('zoom-in', 16)}</button>
        <div style="width:1px;height:16px;background:#e2e8f0;margin:0 2px"></div>
        <button type="button" class="diag-zoom-btn" data-act="fit" title="Fit to view" aria-label="Fit to view" style="height:28px;padding:0 8px;display:flex;align-items:center;gap:4px;background:none;border:0;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600;color:#334155;">
          ${getIconSvg('fit', 14)} <span>Fit</span>
        </button>
      `;
      canvasWrap.appendChild(zoomCluster);
      this.zoomClusterEl = zoomCluster;

      // 10. Inline Text Editing Overlay
      const textOverlay = document.createElement('textarea');
      textOverlay.className = 'diag-text-overlay';
      textOverlay.style.cssText = 'position:absolute;display:none;z-index:40;background:#ffffff;border:1.5px solid #2563eb;border-radius:4px;padding:4px 6px;resize:none;outline:none;font-family:inherit;font-size:13px;line-height:1.3;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
      canvasWrap.appendChild(textOverlay);
      this.textOverlayEl = textOverlay;

      // 11. Empty State Card
      const emptyState = document.createElement('div');
      emptyState.className = 'diag-empty-state';
      emptyState.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:#64748b;z-index:5;pointer-events:none;background:rgba(255,255,255,0.94);padding:22px 30px;border-radius:12px;border:1px dashed #cbd5e1;box-shadow:0 4px 16px rgba(0,0,0,0.05);';
      emptyState.innerHTML = `
        <div style="font-size:15px;font-weight:600;color:#334155;margin-bottom:4px">Double-click to add a block, or press B</div>
        <div style="font-size:12px;color:#64748b;margin-bottom:14px">Use the toolbar to sketch blocks, connections, domains and notes</div>
        <button type="button" class="btn pri diag-start-template-btn" style="pointer-events:auto;font-weight:600">+ Start from template</button>
      `;
      canvasWrap.appendChild(emptyState);
      this.emptyStateEl = emptyState;

      // Inject Global Styles
      if (!document.getElementById('lucid-diagram-editor-styles')) {
        const style = document.createElement('style');
        style.id = 'lucid-diagram-editor-styles';
        style.textContent = `
          .diag-topbar { row-gap: 4px; }
          .diag-tb-btn svg + span { display: none; }
          .diag-rail-btn {
            width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
            border: 1px solid transparent; border-radius: 6px; background: transparent;
            cursor: pointer; padding: 0; color: #334155; transition: background 0.12s, color 0.12s, border-color 0.12s;
          }
          .diag-rail-btn:hover { background: #f1f5f9; color: #0f172a; }
          .diag-rail-btn.active, .diag-rail-btn[aria-pressed="true"] {
            background: #eef2ff !important; color: #2563eb !important; border-color: #c7d2fe !important;
          }
          .diag-rail-btn:disabled { opacity: 0.35; cursor: default; }

          .diag-ctx-btn {
            width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
            border: 1px solid transparent; border-radius: 6px; background: transparent;
            cursor: pointer; padding: 0; color: #334155; transition: background 0.12s, color 0.12s;
          }
          .diag-ctx-btn:hover { background: #f1f5f9; color: #0f172a; }
          .diag-ctx-btn.active, .diag-ctx-btn[aria-pressed="true"] {
            background: #eef2ff !important; color: #2563eb !important; border-color: #c7d2fe !important;
          }
          .diag-ctx-sep { width: 1px; height: 18px; background: #e2e8f0; margin: 0 2px; }

          .diag-zoom-btn:hover { background: #f1f5f9; color: #0f172a; }
          .diag-menu-item:hover { background: #f1f5f9; color: #0f172a; }
          .diag-shape-grid-btn:hover { background: #f1f5f9; color: #2563eb; }

          .diag-swatch-circle { width: 18px; height: 18px; border-radius: 50%; border: 1px solid rgba(0,0,0,0.15); display: inline-block; }
          .diag-swatch-ring { width: 16px; height: 16px; border-radius: 50%; border-width: 3px; border-style: solid; display: inline-block; background: transparent; }

          .diag-shape-node { cursor: pointer; }
          .diag-shape-node.is-selected { filter: drop-shadow(0 0 3px rgba(37,99,235,0.5)); }
          @keyframes diagPulseAnim {
            0% { filter: drop-shadow(0 0 1px rgba(37,99,235,0.8)); }
            50% { filter: drop-shadow(0 0 9px rgba(37,99,235,1)); }
            100% { filter: drop-shadow(0 0 1px rgba(37,99,235,0.8)); }
          }
          .diag-shape-node.diag-pulse { animation: diagPulseAnim 0.7s ease-in-out infinite; }
          .diag-port-dot { cursor: crosshair; fill: #ffffff; stroke: #2563eb; stroke-width: 2; transition: transform 0.1s; }
          .diag-port-dot:hover { transform: scale(1.35); fill: #2563eb; }
          .diag-handle { fill: #ffffff; stroke: #2563eb; stroke-width: 1.5; cursor: pointer; }

          .is-panning, .is-panning * { cursor: grabbing !important; }
        `;
        document.head.appendChild(style);
      }
    }

    /* ---------------- Event Listeners & Binding ---------------- */

    bindEvents() {
      // Toolbar rail & buttons
      this.mountEl.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;

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
          this.fitContent();
          return;
        }
        if (act === 'toggle-snap') {
          this.snapToGrid = !this.snapToGrid;
          this.moreMenuEl.querySelector('.diag-check-snap').style.display = this.snapToGrid ? '' : 'none';
          return;
        }
        if (act === 'toggle-grid') {
          this.showGrid = !this.showGrid;
          this.gridRect.style.display = this.showGrid ? '' : 'none';
          this.moreMenuEl.querySelector('.diag-check-grid').style.display = this.showGrid ? '' : 'none';
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

      // Pan helper (Right-drag, middle-drag, space+left-drag, hand tool)
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
          if (e.button === 0 && (this.spacePressed || this.tool === 'hand')) return true;
          return false;
        },
        onDragStart: () => {
          this.userHasPannedOrZoomed = true;
        },
        onUp: () => {
          this.svgEl.style.cursor = this.tool === 'hand' ? 'grab' : (this.tool === 'connector' || !['select', 'hand'].includes(this.tool) ? 'crosshair' : 'default');
        }
      });

      // Mouse events
      this.svgEl.addEventListener('mousedown', (e) => this.onMouseDown(e));
      window.addEventListener('mousemove', (e) => this.onMouseMove(e));
      window.addEventListener('mouseup', (e) => this.onMouseUp(e));
      this.svgEl.addEventListener('dblclick', (e) => this.onDoubleClick(e));

      // Global click to close popovers when clicking outside
      window.addEventListener('click', (e) => {
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
      window.addEventListener('keydown', (e) => this.onKeyDown(e));
      window.addEventListener('keyup', (e) => this.onKeyUp(e));

      // Text Overlay commit
      this.textOverlayEl.addEventListener('blur', () => this.commitTextEdit());
      this.textOverlayEl.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.commitTextEdit();
        } else if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this.commitTextEdit();
        }
      });
    }

    closeAllPopovers() {
      if (this.shapesPopoverEl) this.shapesPopoverEl.style.display = 'none';
      if (this.palettePopoverEl) this.palettePopoverEl.style.display = 'none';
      if (this.ctxOverflowMenuEl) this.ctxOverflowMenuEl.style.display = 'none';
      if (this.moreMenuEl) this.moreMenuEl.style.display = 'none';
    }

    toggleShapesPopover(anchorBtn) {
      const isVisible = this.shapesPopoverEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;

      const rect = anchorBtn.getBoundingClientRect();
      const wrapRect = this.canvasWrap.getBoundingClientRect();
      this.shapesPopoverEl.style.left = Math.max(10, rect.right - wrapRect.left + 6) + 'px';
      this.shapesPopoverEl.style.top = Math.max(10, rect.top - wrapRect.top) + 'px';
      this.shapesPopoverEl.style.display = 'block';
    }

    toggleMoreMenu(anchorBtn) {
      const isVisible = this.moreMenuEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;
      this.moreMenuEl.style.display = 'block';
    }

    togglePalettePopover(anchorBtn, type) {
      const isVisible = this.palettePopoverEl.style.display === 'block' && this.activePaletteTarget === type;
      this.closeAllPopovers();
      if (isVisible) return;

      this.activePaletteTarget = type;
      const rect = anchorBtn.getBoundingClientRect();
      const wrapRect = this.canvasWrap.getBoundingClientRect();
      this.palettePopoverEl.style.left = Math.max(10, rect.left - wrapRect.left) + 'px';
      this.palettePopoverEl.style.top = Math.max(10, rect.bottom - wrapRect.top + 6) + 'px';
      this.palettePopoverEl.style.display = 'block';
    }

    toggleCtxOverflow(anchorBtn) {
      const isVisible = this.ctxOverflowMenuEl.style.display === 'block';
      this.closeAllPopovers();
      if (isVisible) return;

      const rect = anchorBtn.getBoundingClientRect();
      const wrapRect = this.canvasWrap.getBoundingClientRect();
      this.ctxOverflowMenuEl.style.left = Math.max(10, rect.left - wrapRect.left) + 'px';
      this.ctxOverflowMenuEl.style.top = Math.max(10, rect.bottom - wrapRect.top + 6) + 'px';
      this.ctxOverflowMenuEl.style.display = 'block';
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

      // Update aria-pressed and active classes on rail buttons
      const isShapeTool = VALID_SHAPE_TYPES.has(tool) && tool !== 'sticky' && tool !== 'text';
      this.mountEl.querySelectorAll('.diag-rail-btn[data-tool]').forEach(b => {
        const active = b.dataset.tool === tool;
        b.classList.toggle('active', active);
        b.setAttribute('aria-pressed', active ? 'true' : 'false');
      });

      const shapesBtn = this.mountEl.querySelector('.diag-shapes-rail-btn');
      if (shapesBtn) {
        shapesBtn.classList.toggle('active', isShapeTool);
        shapesBtn.setAttribute('aria-pressed', isShapeTool ? 'true' : 'false');
      }

      if (tool === 'hand') {
        this.svgEl.style.cursor = 'grab';
      } else if (tool === 'connector') {
        this.svgEl.style.cursor = 'crosshair';
      } else if (tool === 'select') {
        this.svgEl.style.cursor = 'default';
      } else {
        this.svgEl.style.cursor = 'crosshair';
      }
    }

    /* ---------------- Mouse Interactions ---------------- */

    onMouseDown(e) {
      if (e.button === 2 || e.button === 1 || this.spacePressed || this.tool === 'hand') return;
      const canvasPos = this.screenToCanvas(e.clientX, e.clientY);

      // Port click -> start connecting
      const portEl = e.target.closest('.diag-port-dot');
      if (portEl) {
        e.stopPropagation();
        this.startConnecting(portEl.dataset.shapeId, portEl.dataset.side);
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
        if (shapeEl) {
          this.startConnecting(shapeEl.dataset.id, 'right');
        } else {
          this.startFreeConnecting(canvasPos.x, canvasPos.y);
        }
        return;
      }

      // Select mode
      if (this.tool === 'select') {
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
      const canvasPos = this.screenToCanvas(e.clientX, e.clientY);

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
        const portEl = document.elementFromPoint(e.clientX, e.clientY)?.closest('.diag-port-dot');
        if (portEl) {
          this.hoveredPort = { shape: portEl.dataset.shapeId, side: portEl.dataset.side };
        } else {
          this.hoveredPort = null;
        }
        this.renderConnectingPreview();
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
      const canvasPos = this.screenToCanvas(e.clientX, e.clientY);

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
      const canvasPos = this.screenToCanvas(e.clientX, e.clientY);

      // Shape double-click -> inline edit
      const shapeEl = e.target.closest('.diag-shape-node');
      if (shapeEl) {
        e.stopPropagation();
        this.startTextEdit('shape', shapeEl.dataset.id);
        return;
      }

      // Connector double-click -> edit label
      const connEl = e.target.closest('.diag-connector-node');
      if (connEl) {
        e.stopPropagation();
        this.startTextEdit('connector', connEl.dataset.id);
        return;
      }

      // Frame double-click -> edit title
      const frameEl = e.target.closest('.diag-frame-node');
      if (frameEl) {
        e.stopPropagation();
        this.startTextEdit('frame', frameEl.dataset.id);
        return;
      }

      // Empty canvas double-click -> add new block at click point, offset until free, caret in inline edit
      const shapeType = this.lastUsedShapeType || 'rectangle';
      const w = 160, h = 68;
      const free = this.findFreePosition(canvasPos.x - w / 2, canvasPos.y - h / 2, w, h);
      this.createShapeAt(shapeType, free.x, free.y, w, h, true);
    }

    onKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
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
          const center = this.screenToCanvas(rect.left + rect.width / 2, rect.top + rect.height / 2);
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
      }

      // Arrow keys nudge
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
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
      if (e.code === 'Space') {
        this.spacePressed = false;
        if (!this.isPanning) {
          this.svgEl.style.cursor = this.tool === 'hand' ? 'grab' : 'default';
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

    createShapeAt(type, x, y, w = null, h = null, autoEdit = false) {
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

      const normType = normalizeShapeType(type);
      const sz = defaultSizes[normType] || defaultSizes[type] || { w: 150, h: 70 };
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

      this.overlayLayer.innerHTML = `
        <rect x="${x}" y="${y}" width="${w}" height="${h}"
              fill="rgba(37,99,235,0.08)" stroke="#2563eb" stroke-width="1.5" stroke-dasharray="4 4" rx="4"/>
      `;
    }

    finishDrawingShape(pos) {
      this.overlayLayer.innerHTML = '';
      const w = Math.abs(pos.x - this.drawStart.x);
      const h = Math.abs(pos.y - this.drawStart.y);
      const x = Math.min(this.drawStart.x, pos.x);
      const y = Math.min(this.drawStart.y, pos.y);

      if (w < 10 && h < 10) {
        const free = this.findFreePosition(this.drawStart.x, this.drawStart.y, 160, 68);
        this.createShapeAt(this.drawShapeType, free.x, free.y, null, null, true);
      } else {
        this.createShapeAt(this.drawShapeType, x, y, w, h, true);
      }
    }

    /* ---------------- Connectors ---------------- */

    startConnecting(shapeId, side) {
      this.isConnecting = true;
      this.connectingFrom = { shape: shapeId, side };
      this.connectingCurrent = this.getShapePortPosition(shapeId, side);
    }

    startFreeConnecting(x, y) {
      this.isConnecting = true;
      this.connectingFrom = { x, y };
      this.connectingCurrent = { x, y };
    }

    renderConnectingPreview() {
      const fromPos = this.connectingFrom.shape
        ? this.getShapePortPosition(this.connectingFrom.shape, this.connectingFrom.side)
        : this.connectingFrom;
      const toPos = this.hoveredPort
        ? this.getShapePortPosition(this.hoveredPort.shape, this.hoveredPort.side)
        : this.connectingCurrent;

      const pathD = `M ${fromPos.x} ${fromPos.y} L ${toPos.x} ${toPos.y}`;
      this.overlayLayer.innerHTML = `
        <path d="${pathD}" stroke="#2563eb" stroke-width="2" stroke-dasharray="5 5" fill="none" marker-end="url(#diag-arrow-end)"/>
        <circle cx="${fromPos.x}" cy="${fromPos.y}" r="4" fill="#2563eb"/>
        <circle cx="${toPos.x}" cy="${toPos.y}" r="4" fill="#2563eb"/>
      `;
    }

    finishConnecting(pos) {
      this.overlayLayer.innerHTML = '';
      let toEndpoint = null;
      if (this.hoveredPort) {
        toEndpoint = { shape: this.hoveredPort.shape, side: this.hoveredPort.side };
      } else {
        toEndpoint = { x: this.snap(pos.x), y: this.snap(pos.y) };
      }

      const conn = {
        id: uid('conn'),
        from: this.connectingFrom,
        to: toEndpoint,
        label: '',
        stroke: '#64748b',
        style: 'solid',
        arrows: 'end',
        route: 'elbow'
      };
      this.data.connectors.push(conn);
      this.clearSelection();
      this.selectedConnectorIds.add(conn.id);
      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();
    }

    getShapePortPosition(shapeId, side) {
      const s = this.data.shapes.find(x => x.id === shapeId);
      if (!s) return { x: 0, y: 0 };
      if (side === 'top') return { x: s.x + s.w / 2, y: s.y };
      if (side === 'right') return { x: s.x + s.w, y: s.y + s.h / 2 };
      if (side === 'bottom') return { x: s.x + s.w / 2, y: s.y + s.h };
      if (side === 'left') return { x: s.x, y: s.y + s.h / 2 };
      return { x: s.x + s.w / 2, y: s.y + s.h / 2 };
    }

    getEndpointCoords(ep) {
      if (!ep) return { x: 0, y: 0 };
      if (ep.shape) {
        return this.getShapePortPosition(ep.shape, ep.side || 'right');
      }
      return { x: Number(ep.x) || 0, y: Number(ep.y) || 0 };
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

      this.overlayLayer.innerHTML = `
        <rect x="${x}" y="${y}" width="${w}" height="${h}"
              fill="rgba(37,99,235,0.08)" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="4 3"/>
      `;
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

    pasteClipboard() {
      if (!this.clipboard) return;
      this.clearSelection();
      const sanitized = sanitizeModel({
        shapes: this.clipboard.shapes || [],
        frames: this.clipboard.frames || []
      });
      (sanitized.shapes || []).forEach(orig => {
        const copy = clone(orig);
        copy.id = uid('shape');
        copy.x += 24;
        copy.y += 24;
        this.data.shapes.push(copy);
        this.selectedShapeIds.add(copy.id);
      });
      (sanitized.frames || []).forEach(orig => {
        const copy = clone(orig);
        copy.id = uid('frame');
        copy.x += 24;
        copy.y += 24;
        this.data.frames.push(copy);
        this.selectedFrameIds.add(copy.id);
      });
      this.saveHistory();
      this.triggerAutosave();
      this.render();
    }

    duplicateSelected() {
      this.copySelected();
      this.pasteClipboard();
    }

    /* ---------------- Inline Text Editing ---------------- */

    startTextEdit(type, id) {
      this.editingTextTarget = { type, id };
      let text = '', bounds = null, fontSz = 14, isBold = false, align = 'center';

      if (type === 'shape') {
        const s = this.data.shapes.find(x => x.id === id);
        if (!s) return;
        text = s.text || '';
        const sp = this.canvasToScreen(s.x, s.y);
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
        const mid = this.canvasToScreen((p1.x + p2.x) / 2 - 60, (p1.y + p2.y) / 2 - 16);
        bounds = { x: mid.x, y: mid.y, w: 120 * this.scale, h: 32 * this.scale };
        fontSz = 12;
      } else if (type === 'frame') {
        const f = this.data.frames.find(x => x.id === id);
        if (!f) return;
        text = f.title || '';
        const sp = this.canvasToScreen(f.x + 10, f.y + 6);
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

      overlay.focus();
      overlay.select();
    }

    commitTextEdit() {
      if (!this.editingTextTarget) return;
      const { type, id } = this.editingTextTarget;
      const newText = this.textOverlayEl.value.trim();
      this.textOverlayEl.style.display = 'none';
      this.editingTextTarget = null;

      if (type === 'shape') {
        const s = this.data.shapes.find(x => x.id === id);
        if (s && s.text !== newText) {
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

      const pattern = this.mountEl.querySelector('#diag-grid-pattern');
      if (pattern) {
        pattern.setAttribute('patternTransform', `translate(${this.panX}, ${this.panY}) scale(${this.scale})`);
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
          if (!this.userHasPannedOrZoomed) this.fitContent();
        });
        return;
      }

      // Ample padding so frames and shapes are never cut at right/bottom edges
      const pad = 60;
      const contentW = Math.max(1, maxX - minX + pad * 2);
      const contentH = Math.max(1, maxY - minY + pad * 2);

      const scale = Math.min(viewW / contentW, viewH / contentH, 1.15);
      this.scale = Math.max(0.18, scale);
      this.panX = (viewW - (maxX - minX) * this.scale) / 2 - minX * this.scale;
      this.panY = (viewH - (maxY - minY) * this.scale) / 2 - minY * this.scale;
      this.updateTransform();
    }

    renderFrames() {
      let html = '';
      this.data.frames.forEach(f => {
        const isSel = this.selectedFrameIds.has(f.id);
        const strokeColor = f.stroke || '#94a3b8';
        html += `
          <g class="diag-frame-node ${isSel ? 'is-selected' : ''}" data-id="${escapeHtml(f.id)}" transform="translate(${f.x}, ${f.y})">
            <rect width="${f.w}" height="${f.h}" rx="10"
                  fill="rgba(241, 245, 249, 0.45)"
                  stroke="${escapeHtml(isSel ? '#2563eb' : strokeColor)}"
                  stroke-width="${isSel ? 2.5 : 2}"
                  stroke-dasharray="8 6"/>
            <text x="12" y="24" fill="${escapeHtml(strokeColor)}" font-size="12" font-weight="700" letter-spacing="0.04em">
              ${escapeHtml(f.title.toUpperCase())}
            </text>
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

        let d = '';
        if (c.route === 'straight') {
          d = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
        } else {
          const midX = (p1.x + p2.x) / 2;
          d = `M ${p1.x} ${p1.y} H ${midX} V ${p2.y} H ${p2.x}`;
        }

        const strokeColor = isSel ? '#2563eb' : (c.stroke || '#64748b');
        const strokeWidth = isSel ? 3 : (c.style === 'thick' ? 3.5 : 2);
        const dashArray = c.style === 'dashed' ? '6 4' : (c.style === 'dotted' ? '2 3' : 'none');
        const markerEnd = (c.arrows === 'end' || c.arrows === 'both' || c.arrows === 'to') ? 'url(#diag-arrow-end)' : '';
        const markerStart = (c.arrows === 'start' || c.arrows === 'both') ? 'url(#diag-arrow-start)' : '';

        const mx = (p1.x + p2.x) / 2;
        const my = (p1.y + p2.y) / 2;
        let labelHtml = '';
        if (c.label) {
          const lw = Math.max(c.label.length * 7.5 + 16, 32);
          labelHtml = `
            <g class="diag-conn-label" transform="translate(${mx}, ${my})">
              <rect x="${-lw / 2}" y="-11" width="${lw}" height="22" rx="5" fill="#ffffff" stroke="${escapeHtml(strokeColor)}" stroke-width="1.2"/>
              <text text-anchor="middle" y="4.5" font-size="11" font-weight="600" fill="${escapeHtml(strokeColor)}">
                ${escapeHtml(c.label)}
              </text>
            </g>
          `;
        }

        html += `
          <g class="diag-connector-node ${isSel ? 'is-selected' : ''}" data-id="${escapeHtml(c.id)}">
            <path d="${escapeHtml(d)}" stroke="transparent" stroke-width="14" fill="none" style="cursor:pointer"/>
            <path d="${escapeHtml(d)}" stroke="${escapeHtml(strokeColor)}" stroke-width="${strokeWidth}"
                  stroke-dasharray="${escapeHtml(dashArray)}" fill="none"
                  marker-end="${escapeHtml(markerEnd)}" marker-start="${escapeHtml(markerStart)}"/>
            ${labelHtml}
          </g>
        `;
      });
      this.connectorsLayer.innerHTML = html;
    }

    renderShapes() {
      let html = '';
      const sortedShapes = [...this.data.shapes].sort((a, b) => (a.z || 0) - (b.z || 0));

      sortedShapes.forEach(s => {
        const isSel = this.selectedShapeIds.has(s.id);
        const strokeColor = isSel ? '#2563eb' : (s.stroke || '#2980b9');
        const strokeWidth = isSel ? Math.max(s.strokeWidth, 2.5) : s.strokeWidth;
        const dashArray = s.strokeStyle === 'dashed' ? '6 4' : (s.strokeStyle === 'dotted' ? '2 3' : 'none');
        const fontSz = s.fontSize === 'S' ? 12 : (s.fontSize === 'L' ? 17 : 14);

        const shapeSvg = renderShapeSvg(s, strokeColor, strokeWidth, dashArray);

        // Multiline centered text rendering
        const lines = (s.text || '').split('\n');
        let textAnchor = 'middle';
        let textX = s.w / 2;
        if (s.align === 'left') { textAnchor = 'start'; textX = 14; }
        if (s.align === 'right') { textAnchor = 'end'; textX = s.w - 14; }

        const lineHeight = fontSz * 1.35;
        const totalTextHeight = lines.length * lineHeight;
        const startY = (s.h - totalTextHeight) / 2 + fontSz * 0.9;

        const textColor = s.type === 'sticky' ? '#854d0e' : (s.domain ? (DOMAIN_PRESETS.find(d => d.id === s.domain)?.text || '#1e293b') : '#1e293b');
        const textLinesSvg = lines.map((line, i) => `
          <tspan x="${textX}" y="${startY + i * lineHeight}" font-size="${fontSz}" font-weight="${s.bold ? (i === 0 ? '700' : '500') : '400'}" fill="${escapeHtml(textColor)}">
            ${escapeHtml(line)}
          </tspan>
        `).join('');

        const lockIcon = s.locked ? `
          <g transform="translate(${s.w - 18}, 6)">
            <rect x="2" y="5" width="8" height="6" rx="1" fill="#64748b"/>
            <path d="M4 5V3a2 2 0 0 1 4 0v2" fill="none" stroke="#64748b" stroke-width="1.2"/>
          </g>
        ` : '';

        const isPulse = !!(this.pulsingShapeIds && this.pulsingShapeIds.has(s.id));
        html += `
          <g class="diag-shape-node ${isSel ? 'is-selected' : ''} ${isPulse ? 'diag-pulse' : ''}" data-id="${escapeHtml(s.id)}" transform="translate(${s.x}, ${s.y})">
            ${shapeSvg}
            <text text-anchor="${escapeHtml(textAnchor)}" style="pointer-events:none;">${textLinesSvg}</text>
            ${lockIcon}
          </g>
        `;
      });
      this.shapesLayer.innerHTML = html;
    }

    renderPorts() {
      if (!this.hoveredShapeId || this.isDraggingItems || this.isResizing) {
        if (!this.isConnecting) {
          const oldPorts = this.overlayLayer.querySelectorAll('.diag-port-dot');
          oldPorts.forEach(p => p.remove());
        }
        return;
      }
      const s = this.data.shapes.find(x => x.id === this.hoveredShapeId);
      if (!s) return;

      const ports = [
        { side: 'top', x: s.x + s.w / 2, y: s.y },
        { side: 'right', x: s.x + s.w, y: s.y + s.h / 2 },
        { side: 'bottom', x: s.x + s.w / 2, y: s.y + s.h },
        { side: 'left', x: s.x, y: s.y + s.h / 2 },
      ];

      let html = '';
      ports.forEach(p => {
        html += `<circle class="diag-port-dot" cx="${p.x}" cy="${p.y}" r="4.5"
                         data-shape-id="${escapeHtml(s.id)}" data-side="${escapeHtml(p.side)}"/>`;
      });

      const tmpDiv = document.createElement('div');
      tmpDiv.innerHTML = html;
      while (tmpDiv.firstChild) {
        this.overlayLayer.appendChild(tmpDiv.firstChild);
      }
    }

    renderSelectionHandles() {
      const totalSel = this.selectedShapeIds.size + this.selectedFrameIds.size;
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

      let handlesSvg = `
        <rect x="${x - 1}" y="${y - 1}" width="${w + 2}" height="${h + 2}"
              fill="none" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="3 3"/>
      `;
      handles.forEach(hd => {
        handlesSvg += `
          <rect class="diag-handle" x="${hd.x - r}" y="${hd.y - r}" width="${r * 2}" height="${r * 2}"
                style="cursor:${escapeHtml(hd.cursor)}" data-handle="${escapeHtml(hd.pos)}"
                data-target-id="${escapeHtml(item.id)}" data-target-type="${escapeHtml(type)}"/>
        `;
      });

      const tmp = document.createElement('div');
      tmp.innerHTML = handlesSvg;
      while (tmp.firstChild) {
        this.overlayLayer.appendChild(tmp.firstChild);
      }
    }

    renderContextToolbar() {
      const tb = this.ctxToolbarEl;
      const totalSel = this.selectedShapeIds.size + this.selectedConnectorIds.size + this.selectedFrameIds.size;
      if (totalSel === 0) {
        tb.style.display = 'none';
        return;
      }

      // Calculate selection bounding box
      let minX = Infinity, minY = Infinity, maxX = -Infinity;
      this.selectedShapeIds.forEach(id => {
        const s = this.data.shapes.find(x => x.id === id);
        if (s) {
          minX = Math.min(minX, s.x);
          minY = Math.min(minY, s.y);
          maxX = Math.max(maxX, s.x + s.w);
        }
      });
      this.selectedFrameIds.forEach(id => {
        const f = this.data.frames.find(x => x.id === id);
        if (f) {
          minX = Math.min(minX, f.x);
          minY = Math.min(minY, f.y);
          maxX = Math.max(maxX, f.x + f.w);
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
        }
      });

      const midScreen = this.canvasToScreen((minX + maxX) / 2, minY);
      const wrapRect = this.canvasWrap.getBoundingClientRect();
      const topPos = midScreen.y - wrapRect.top - 46;
      const leftPos = midScreen.x - wrapRect.left;

      tb.style.left = Math.max(10, leftPos - 140) + 'px';
      tb.style.top = Math.max(10, topPos) + 'px';
      tb.style.display = 'flex';

      const isShapeOnly = this.selectedShapeIds.size > 0 && !this.selectedConnectorIds.size && !this.selectedFrameIds.size;
      const isFrameOnly = this.selectedFrameIds.size > 0 && !this.selectedShapeIds.size && !this.selectedConnectorIds.size;
      const isConnOnly = this.selectedConnectorIds.size > 0 && !this.selectedShapeIds.size && !this.selectedFrameIds.size;

      if (isShapeOnly) {
        const firstShape = this.data.shapes.find(s => this.selectedShapeIds.has(s.id));
        const fillColor = firstShape?.fill === 'none' ? 'transparent' : (firstShape?.fill || '#ffffff');
        const strokeColor = firstShape?.stroke === 'none' ? '#cbd5e1' : (firstShape?.stroke || '#2980b9');

        tb.innerHTML = `
          <button type="button" class="diag-ctx-btn" data-act="toggle-ctx-shapes" title="Change shape" aria-label="Change shape">${getIconSvg('change-shape')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn" data-act="toggle-fill-palette" title="Fill colour" aria-label="Fill colour">
            <span class="diag-swatch-circle" style="background:${escapeHtml(fillColor)}"></span>
          </button>
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Border colour" aria-label="Border colour">
            <span class="diag-swatch-ring" style="border-color:${escapeHtml(strokeColor)}"></span>
          </button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn ${firstShape?.strokeStyle === 'solid' ? 'active' : ''}" data-act="set-border-style" data-val="solid" title="Solid border" aria-label="Solid border">${getIconSvg('line-solid')}</button>
          <button type="button" class="diag-ctx-btn ${firstShape?.strokeStyle === 'dashed' ? 'active' : ''}" data-act="set-border-style" data-val="dashed" title="Dashed border" aria-label="Dashed border">${getIconSvg('line-dashed')}</button>
          <button type="button" class="diag-ctx-btn ${firstShape?.strokeStyle === 'dotted' ? 'active' : ''}" data-act="set-border-style" data-val="dotted" title="Dotted border" aria-label="Dotted border">${getIconSvg('line-dotted')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn" data-act="cycle-font-size" title="Text size: ${firstShape?.fontSize || 'M'}" aria-label="Text size: ${firstShape?.fontSize || 'M'}">
            <span style="font-weight:700;font-size:13px;display:flex;align-items:center">T<span style="font-size:10px;margin-left:1px">▾</span></span>
          </button>
          <button type="button" class="diag-ctx-btn ${firstShape?.bold ? 'active' : ''}" data-act="toggle-bold" title="Bold" aria-label="Bold" aria-pressed="${!!firstShape?.bold}">${getIconSvg('bold')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn" data-act="delete-sel" title="Delete" aria-label="Delete" style="color:#ef4444">${getIconSvg('delete')}</button>
          <div class="diag-ctx-sep"></div>
          <button type="button" class="diag-ctx-btn" data-act="toggle-ctx-overflow" title="More options" aria-label="More options" aria-haspopup="true">${getIconSvg('more')}</button>
        `;
      } else if (isFrameOnly) {
        const firstFrame = this.data.frames.find(f => this.selectedFrameIds.has(f.id));
        const strokeColor = firstFrame?.stroke || '#94a3b8';

        tb.innerHTML = `
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Border colour" aria-label="Border colour">
            <span class="diag-swatch-ring" style="border-color:${escapeHtml(strokeColor)}"></span>
          </button>
          <div class="diag-ctx-sep"></div>
          <button type="button" class="diag-ctx-btn" data-act="edit-frame-title" title="Edit label" aria-label="Edit label">${getIconSvg('label')}</button>
          <div class="diag-ctx-sep"></div>
          <button type="button" class="diag-ctx-btn" data-act="delete-sel" title="Delete" aria-label="Delete" style="color:#ef4444">${getIconSvg('delete')}</button>
        `;
      } else if (isConnOnly) {
        const firstConn = this.data.connectors.find(c => this.selectedConnectorIds.has(c.id));
        const strokeColor = firstConn?.stroke || '#64748b';

        tb.innerHTML = `
          <button type="button" class="diag-ctx-btn" data-act="toggle-border-palette" title="Line colour" aria-label="Line colour">
            <span class="diag-swatch-ring" style="border-color:${escapeHtml(strokeColor)}"></span>
          </button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn ${firstConn?.style === 'solid' ? 'active' : ''}" data-act="set-conn-style" data-val="solid" title="Solid line" aria-label="Solid line">${getIconSvg('line-solid')}</button>
          <button type="button" class="diag-ctx-btn ${firstConn?.style === 'dashed' ? 'active' : ''}" data-act="set-conn-style" data-val="dashed" title="Dashed line" aria-label="Dashed line">${getIconSvg('line-dashed')}</button>
          <button type="button" class="diag-ctx-btn ${firstConn?.style === 'dotted' ? 'active' : ''}" data-act="set-conn-style" data-val="dotted" title="Dotted line" aria-label="Dotted line">${getIconSvg('line-dotted')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn ${firstConn?.arrows === 'none' ? 'active' : ''}" data-act="set-conn-arrows" data-val="none" title="No arrows" aria-label="No arrows">${getIconSvg('arrow-none')}</button>
          <button type="button" class="diag-ctx-btn ${firstConn?.arrows === 'end' ? 'active' : ''}" data-act="set-conn-arrows" data-val="end" title="Arrow at end" aria-label="Arrow at end">${getIconSvg('arrow-end')}</button>
          <button type="button" class="diag-ctx-btn ${firstConn?.arrows === 'both' ? 'active' : ''}" data-act="set-conn-arrows" data-val="both" title="Arrows both ends" aria-label="Arrows both ends">${getIconSvg('arrow-both')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn ${firstConn?.route === 'straight' ? '' : 'active'}" data-act="toggle-conn-route" title="Toggle straight/elbow route" aria-label="Toggle straight/elbow route">${getIconSvg('route-elbow')}</button>
          <button type="button" class="diag-ctx-btn" data-act="edit-conn-label" title="Edit label" aria-label="Edit label">${getIconSvg('label')}</button>
          <div class="diag-ctx-sep"></div>

          <button type="button" class="diag-ctx-btn" data-act="delete-sel" title="Delete" aria-label="Delete" style="color:#ef4444">${getIconSvg('delete')}</button>
        `;
      } else {
        // Mixed selection: common controls only (delete)
        tb.innerHTML = `
          <button type="button" class="diag-ctx-btn" data-act="delete-sel" title="Delete" aria-label="Delete" style="color:#ef4444">${getIconSvg('delete')}</button>
        `;
      }

      // Bind context toolbar clicks
      tb.onclick = (e) => this.onContextToolbarClick(e);
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
        this.emptyStateEl.style.display = isEmpty ? 'block' : 'none';
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

  DiagramEditor.attachPanHelper = attachPanHelper;
  DiagramEditor.sanitizeModel = sanitizeModel;
  if (typeof window !== 'undefined') {
    window.attachPanHelper = attachPanHelper;
    window.sanitizeModel = sanitizeModel;
  }

  return DiagramEditor;
});
