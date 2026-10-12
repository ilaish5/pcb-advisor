/**
 * Miro-like Block Diagram Editor (Vanilla JS & SVG)
 *
 * Features:
 * - Infinite canvas with pan, zoom at cursor, dot grid, snap-to-grid, and fit
 * - Toolbar: Select (V), Hand (H), Block (B), Ellipse (E), Diamond (D),
 *            Sticky note (N), Text (T), Connector (L), Frame (F)
 * - Click or drag to place shapes/frames
 * - Multi-selection (click, Shift+click, marquee drag)
 * - Move by drag, 8 resize handles, arrow key nudging (Shift = 10x)
 * - Delete/Backspace, Duplicate (Ctrl+C/V/D), Undo/Redo (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z)
 * - Double-click inline text editing (multiline, Enter+Shift, S/M/L, bold, align)
 * - Floating context toolbar (fill swatches incl. domain presets, border style/width,
 *   text size, z-order, lock, delete, connector styles/arrows/routes)
 * - Connectors with 4 shape ports, attached follow on move, free endpoints, straight/elbow, labels
 * - Frames with title at top-left, moves enclosed shapes, renders behind shapes
 * - Domain palette presets (Power, MCU, Sensing, Comms/RF, Drive/IO, UI)
 * - Empty state hint with "Start from template"
 * - Debounced autosave (~600 ms) via /api/idea/diagram
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
    '#ffffff', '#fef3e2', '#ebf5fb', '#e8f8f0', '#f3ebf9', '#fdedec', '#f2f4f4', '#fef9c3', '#0f172a', 'none'
  ];

  const STROKE_SWATCHES = [
    '#e67e22', '#2980b9', '#27ae60', '#8e44ad', '#c0392b', '#7f8c8d', '#ca8a04', '#94a3b8', '#0f172a'
  ];

  const STARTER_TEMPLATE = {
    shapes: [
      {
        id: 's_pwr',
        type: 'block',
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
        type: 'block',
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
        type: 'block',
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
      .replace(/"/g, '&quot;');
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

      // Active tool: 'select', 'hand', 'block', 'ellipse', 'diamond', 'sticky', 'text', 'connector', 'frame'
      this.tool = 'select';

      // Selection state: arrays of IDs
      this.selectedShapeIds = new Set();
      this.selectedConnectorIds = new Set();
      this.selectedFrameIds = new Set();

      // Undo / Redo history
      this.history = [];
      this.historyIndex = -1;
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
      this.dragOrigPositions = {}; // id -> {x, y}
      this.dragContainedShapeIds = [];

      this.isResizing = false;
      this.resizeHandle = null;
      this.resizeTargetId = null;
      this.resizeTargetType = null; // 'shape' or 'frame'
      this.resizeOrigBounds = null;

      this.isDrawingShape = false;
      this.drawShapeType = null;
      this.drawStart = { x: 0, y: 0 };

      this.isConnecting = false;
      this.connectingFrom = null; // { shape: id, side: 'top'|'right'|'bottom'|'left' }
      this.connectingCurrent = { x: 0, y: 0 };
      this.hoveredPort = null; // { shape: id, side: '...' }

      this.hoveredShapeId = null;

      this.clipboard = null;
      this.editingTextTarget = null; // { type: 'shape'|'connector'|'frame', id: ... }

      this.initDom();
      this.bindEvents();
      this.fitContent();
    }

    normalizeData(raw) {
      const d = {
        shapes: Array.isArray(raw.shapes) ? raw.shapes : [],
        connectors: Array.isArray(raw.connectors) ? raw.connectors : [],
        frames: Array.isArray(raw.frames) ? raw.frames : []
      };
      // Normalize shapes
      d.shapes.forEach((s, idx) => {
        if (!s.id) s.id = uid('shape');
        if (!s.type) s.type = 'block';
        s.x = Number(s.x) || 0;
        s.y = Number(s.y) || 0;
        s.w = Math.max(30, Number(s.w) || 160);
        s.h = Math.max(25, Number(s.h) || 68);
        s.text = s.text != null ? String(s.text) : '';
        s.fill = s.fill || '#ffffff';
        s.stroke = s.stroke || '#2980b9';
        s.strokeStyle = s.strokeStyle || 'solid';
        s.strokeWidth = Number(s.strokeWidth) || 2;
        s.fontSize = s.fontSize || 'M';
        s.bold = s.bold !== false;
        s.align = s.align || 'center';
        s.z = Number(s.z) || (idx + 1);
        s.locked = !!s.locked;
      });
      // Normalize connectors
      d.connectors.forEach((c) => {
        if (!c.id) c.id = uid('conn');
        if (!c.from) c.from = { x: 0, y: 0 };
        if (!c.to) c.to = { x: 100, y: 100 };
        c.label = c.label != null ? String(c.label) : '';
        c.stroke = c.stroke || '#64748b';
        c.style = c.style || 'solid';
        c.arrows = c.arrows || 'end';
        c.route = c.route || 'elbow';
      });
      // Normalize frames
      d.frames.forEach((f) => {
        if (!f.id) f.id = uid('frame');
        f.x = Number(f.x) || 0;
        f.y = Number(f.y) || 0;
        f.w = Math.max(80, Number(f.w) || 320);
        f.h = Math.max(60, Number(f.h) || 200);
        f.title = f.title != null ? String(f.title) : 'Domain Frame';
        f.stroke = f.stroke || '#94a3b8';
      });
      return d;
    }

    updateData(newData) {
      if (!newData) return;
      this.data = this.normalizeData(newData);
      this.render();
      this.updateEmptyState();
    }

    saveHistory() {
      const snap = JSON.stringify(this.data);
      if (this.historyIndex >= 0 && this.history[this.historyIndex] === snap) {
        return;
      }
      this.history = this.history.slice(0, this.historyIndex + 1);
      this.history.push(snap);
      if (this.history.length > 50) this.history.shift();
      this.historyIndex = this.history.length - 1;
      this.updateUndoRedoButtons();
    }

    undo() {
      if (this.historyIndex > 0) {
        this.historyIndex--;
        this.data = JSON.parse(this.history[this.historyIndex]);
        this.clearSelection();
        this.render();
        this.triggerAutosave();
        this.updateUndoRedoButtons();
      }
    }

    redo() {
      if (this.historyIndex < this.history.length - 1) {
        this.historyIndex++;
        this.data = JSON.parse(this.history[this.historyIndex]);
        this.clearSelection();
        this.render();
        this.triggerAutosave();
        this.updateUndoRedoButtons();
      }
    }

    updateUndoRedoButtons() {
      const undoBtn = this.mountEl.querySelector('[data-tool="undo"]');
      const redoBtn = this.mountEl.querySelector('[data-tool="redo"]');
      if (undoBtn) undoBtn.disabled = this.historyIndex <= 0;
      if (redoBtn) redoBtn.disabled = this.historyIndex >= this.history.length - 1;
    }

    triggerAutosave() {
      clearTimeout(this.saveDebounceTimer);
      this.saveDebounceTimer = setTimeout(async () => {
        try {
          await this.onSave(clone(this.data));
        } catch (e) {
          console.error('Diagram autosave failed:', e);
        }
      }, 600);
    }

    snap(val) {
      if (!this.snapToGrid) return val;
      return Math.round(val / this.gridSize) * this.gridSize;
    }

    // Convert Screen (DOM) coordinates to Canvas (SVG User Space)
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

    /* ---------------- DOM & Setup ---------------- */

    initDom() {
      this.mountEl.innerHTML = '';
      this.mountEl.className = 'miro-diagram-editor';
      this.mountEl.style.cssText = 'position:relative;width:100%;height:100%;display:flex;flex-direction:column;overflow:hidden;background:#f8fafc;user-select:none;font-family:inherit;';

      // 1. Top Toolbar
      const toolbar = document.createElement('div');
      toolbar.className = 'diag-topbar';
      toolbar.style.cssText = 'display:flex;align-items:center;gap:4px;padding:6px 12px;background:#ffffff;border-bottom:1px solid #d6dce8;flex-wrap:wrap;z-index:10;box-shadow:0 1px 2px rgba(0,0,0,0.03);';
      toolbar.innerHTML = `
        <div class="diag-tool-group" style="display:flex;gap:2px">
          <button type="button" class="diag-tb-btn active" data-tool="select" title="Select (V)"><svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M4 2l16 11-7 2 4 7-3 1.5-4-7-4 4.5z"/></svg> <span>Select (V)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="hand" title="Hand / Pan (H)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v7M10 10.5V6a2 2 0 0 0-4 0v8a7 7 0 0 0 14 0v-4a2 2 0 0 0-4 0"/></svg> <span>Hand (H)</span></button>
        </div>
        <div class="diag-sep" style="width:1px;height:20px;background:#e2e8f0;margin:0 4px"></div>
        <div class="diag-tool-group" style="display:flex;gap:2px">
          <button type="button" class="diag-tb-btn" data-tool="block" title="Block / Rectangle (B)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="4"/></svg> <span>Block (B)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="ellipse" title="Ellipse (E)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="12" rx="9" ry="7"/></svg> <span>Ellipse (E)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="diamond" title="Diamond (D)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l9 10-9 10-9-10z"/></svg> <span>Diamond (D)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="sticky" title="Sticky note (N)"><svg width="15" height="15" viewBox="0 0 24 24" fill="#fef08a" stroke="#ca8a04" stroke-width="1.8"><path d="M4 3h16v13l-5 5H4z"/></svg> <span>Sticky (N)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="text" title="Text (T)"><svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M5 4v3h5v12h4V7h5V4z"/></svg> <span>Text (T)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="connector" title="Connector / Line (L)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19L19 4M14 4h5v5"/></svg> <span>Connector (L)</span></button>
          <button type="button" class="diag-tb-btn" data-tool="frame" title="Frame / Domain (F)"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"><rect x="3" y="3" width="18" height="18" rx="2"/></svg> <span>Frame (F)</span></button>
        </div>
        <div class="diag-sep" style="width:1px;height:20px;background:#e2e8f0;margin:0 4px"></div>
        <div class="diag-tool-group" style="display:flex;gap:2px">
          <button type="button" class="diag-tb-btn" data-tool="undo" title="Undo (Ctrl+Z)">↶</button>
          <button type="button" class="diag-tb-btn" data-tool="redo" title="Redo (Ctrl+Y)">↷</button>
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:6px">
          <button type="button" class="diag-tb-btn" data-act="zoom-out" title="Zoom Out">−</button>
          <button type="button" class="diag-tb-btn diag-zoom-val" data-act="zoom-reset" title="Click to reset zoom" style="font-family:monospace;min-width:44px;font-size:12px;text-align:center">100%</button>
          <button type="button" class="diag-tb-btn" data-act="zoom-in" title="Zoom In">+</button>
          <button type="button" class="diag-tb-btn" data-act="fit" title="Fit all elements">Fit</button>
          <div class="diag-sep" style="width:1px;height:20px;background:#e2e8f0;margin:0 2px"></div>
          <button type="button" class="diag-tb-btn ${this.snapToGrid ? 'active' : ''}" data-act="toggle-snap" title="Toggle Snap to Grid">Snap</button>
          <button type="button" class="diag-tb-btn ${this.showGrid ? 'active' : ''}" data-act="toggle-grid" title="Toggle Dot Grid">Grid</button>
          <button type="button" class="diag-tb-btn" data-act="load-template" title="Start from template">+ Template</button>
        </div>
      `;
      this.mountEl.appendChild(toolbar);

      // 2. Canvas Container
      const canvasWrap = document.createElement('div');
      canvasWrap.className = 'diag-canvas-container';
      canvasWrap.style.cssText = 'position:relative;flex:1;min-height:0;width:100%;overflow:hidden;background:#f8fafc;';
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

      // Defs (pattern, markers)
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

      // Viewport group (transforms with pan and zoom)
      const viewport = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      viewport.setAttribute('class', 'diag-viewport');
      svg.appendChild(viewport);
      this.viewportEl = viewport;

      // Layers inside viewport
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
      ctxToolbar.style.cssText = 'position:absolute;display:none;background:#ffffff;border:1px solid #cbd5e1;border-radius:8px;padding:4px 8px;box-shadow:0 4px 14px rgba(0,0,0,0.12);z-index:20;font-size:12px;gap:6px;align-items:center;pointer-events:auto;';
      canvasWrap.appendChild(ctxToolbar);
      this.ctxToolbarEl = ctxToolbar;

      // 5. Inline Text Editing Overlay
      const textOverlay = document.createElement('textarea');
      textOverlay.className = 'diag-text-overlay';
      textOverlay.style.cssText = 'position:absolute;display:none;z-index:30;background:#ffffff;border:1.5px solid #2563eb;border-radius:4px;padding:4px 6px;resize:none;outline:none;font-family:inherit;font-size:13px;line-height:1.3;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
      canvasWrap.appendChild(textOverlay);
      this.textOverlayEl = textOverlay;

      // 6. Empty State Element
      const emptyState = document.createElement('div');
      emptyState.className = 'diag-empty-state';
      emptyState.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:#64748b;z-index:5;pointer-events:none;background:rgba(255,255,255,0.92);padding:20px 28px;border-radius:12px;border:1px dashed #cbd5e1;box-shadow:0 4px 12px rgba(0,0,0,0.04);';
      emptyState.innerHTML = `
        <div style="font-size:15px;font-weight:600;color:#334155;margin-bottom:4px">Double-click to add a block, or press B</div>
        <div style="font-size:12px;color:#64748b;margin-bottom:12px">Use the toolbar to sketch blocks, connections, domains and notes</div>
        <button type="button" class="btn pri diag-start-template-btn" style="pointer-events:auto">+ Start from template</button>
      `;
      canvasWrap.appendChild(emptyState);
      this.emptyStateEl = emptyState;

      // Add CSS styles for toolbar buttons and handles
      if (!document.getElementById('miro-diagram-editor-styles')) {
        const style = document.createElement('style');
        style.id = 'miro-diagram-editor-styles';
        style.textContent = `
          .diag-tb-btn {
            border: 1px solid transparent; background: transparent; border-radius: 6px;
            padding: 4px 8px; font-size: 12.5px; font-weight: 500; color: #334155;
            cursor: pointer; display: inline-flex; align-items: center; gap: 5px; line-height: 1;
            transition: background 0.12s, border-color 0.12s, color 0.12s;
          }
          .diag-tb-btn:hover { background: #f1f5f9; color: #0f172a; }
          .diag-tb-btn.active { background: #e0e7ff; color: #2563eb; border-color: #93c5fd; font-weight: 600; }
          .diag-tb-btn:disabled { opacity: 0.35; cursor: default; }
          .diag-shape-node { cursor: pointer; }
          .diag-shape-node.is-selected { filter: drop-shadow(0 0 3px rgba(37,99,235,0.5)); }
          .diag-port-dot { cursor: crosshair; fill: #ffffff; stroke: #2563eb; stroke-width: 2; transition: transform 0.1s; }
          .diag-port-dot:hover { transform: scale(1.35); fill: #2563eb; }
          .diag-handle { fill: #ffffff; stroke: #2563eb; stroke-width: 1.5; cursor: pointer; }
          .diag-swatch { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #cbd5e1; cursor: pointer; display: inline-block; }
          .diag-swatch:hover { transform: scale(1.15); }
        `;
        document.head.appendChild(style);
      }
    }

    /* ---------------- Event Listeners ---------------- */

    bindEvents() {
      // Toolbar buttons
      this.mountEl.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        const tool = btn.dataset.tool;
        if (tool) {
          if (tool === 'undo') return this.undo();
          if (tool === 'redo') return this.redo();
          this.setTool(tool);
          return;
        }
        const act = btn.dataset.act;
        if (act === 'zoom-in') this.zoomAtCenter(1.2);
        if (act === 'zoom-out') this.zoomAtCenter(0.8);
        if (act === 'zoom-reset') { this.scale = 1.0; this.updateTransform(); }
        if (act === 'fit') this.fitContent();
        if (act === 'toggle-snap') {
          this.snapToGrid = !this.snapToGrid;
          btn.classList.toggle('active', this.snapToGrid);
        }
        if (act === 'toggle-grid') {
          this.showGrid = !this.showGrid;
          btn.classList.toggle('active', this.showGrid);
          this.gridRect.style.display = this.showGrid ? '' : 'none';
        }
        if (act === 'load-template' || e.target.closest('.diag-start-template-btn')) {
          this.loadTemplate();
        }
      });

      // Canvas Zoom: wheel event
      this.canvasWrap.addEventListener('wheel', (e) => {
        e.preventDefault();
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

      // Mouse Down on canvas
      this.svgEl.addEventListener('mousedown', (e) => this.onMouseDown(e));
      window.addEventListener('mousemove', (e) => this.onMouseMove(e));
      window.addEventListener('mouseup', (e) => this.onMouseUp(e));

      // Double Click on canvas / shapes
      this.svgEl.addEventListener('dblclick', (e) => this.onDoubleClick(e));

      // Keyboard shortcuts
      window.addEventListener('keydown', (e) => this.onKeyDown(e));
      window.addEventListener('keyup', (e) => this.onKeyUp(e));

      // Text Overlay Commit
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

    setTool(tool) {
      this.tool = tool;
      this.mountEl.querySelectorAll('[data-tool]').forEach((b) => {
        b.classList.toggle('active', b.dataset.tool === tool);
      });
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
      if (e.button === 2) return; // Right click ignored
      const canvasPos = this.screenToCanvas(e.clientX, e.clientY);

      // 1. Pan with Space held or Middle Mouse (button 1) or Hand tool
      if (this.spacePressed || e.button === 1 || this.tool === 'hand') {
        this.isPanning = true;
        this.panStartX = e.clientX - this.panX;
        this.panStartY = e.clientY - this.panY;
        this.svgEl.style.cursor = 'grabbing';
        return;
      }

      // Check for port dot click (Start connecting)
      const portEl = e.target.closest('.diag-port-dot');
      if (portEl) {
        e.stopPropagation();
        const shapeId = portEl.dataset.shapeId;
        const side = portEl.dataset.side;
        this.startConnecting(shapeId, side);
        return;
      }

      // Check for resize handle click
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

      // Check click on Shape / Connector / Frame
      const shapeEl = e.target.closest('.diag-shape-node');
      const connEl = e.target.closest('.diag-connector-node');
      const frameEl = e.target.closest('.diag-frame-node');

      // 2. Active Shape Creation Tool
      if (['block', 'ellipse', 'diamond', 'sticky', 'text', 'frame'].includes(this.tool)) {
        this.isDrawingShape = true;
        this.drawShapeType = this.tool;
        this.drawStart = { x: canvasPos.x, y: canvasPos.y };
        return;
      }

      // 3. Active Connector Tool
      if (this.tool === 'connector') {
        if (shapeEl) {
          const sid = shapeEl.dataset.id;
          this.startConnecting(sid, 'right');
        } else {
          // Free connector start
          this.startFreeConnecting(canvasPos.x, canvasPos.y);
        }
        return;
      }

      // 4. Select Mode
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

          // Start dragging items if not locked
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

          // Start dragging frame (and its contained shapes)
          this.startDraggingFrame(fid, canvasPos);
          return;
        }

        // Clicked on empty space -> start Marquee selection
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

      // Panning
      if (this.isPanning) {
        this.panX = e.clientX - this.panStartX;
        this.panY = e.clientY - this.panStartY;
        this.updateTransform();
        return;
      }

      // Drawing shape preview
      if (this.isDrawingShape) {
        this.renderDrawingShapePreview(canvasPos);
        return;
      }

      // Connecting line preview
      if (this.isConnecting) {
        this.connectingCurrent = { x: canvasPos.x, y: canvasPos.y };
        // Check hovered port or shape
        const portEl = document.elementFromPoint(e.clientX, e.clientY)?.closest('.diag-port-dot');
        if (portEl) {
          this.hoveredPort = { shape: portEl.dataset.shapeId, side: portEl.dataset.side };
        } else {
          this.hoveredPort = null;
        }
        this.renderConnectingPreview();
        return;
      }

      // Resizing item
      if (this.isResizing) {
        this.doResize(canvasPos);
        return;
      }

      // Dragging items
      if (this.isDraggingItems) {
        this.doDragItems(canvasPos);
        return;
      }

      // Marquee selection
      if (this.isMarquee) {
        this.marqueeEnd = { x: canvasPos.x, y: canvasPos.y };
        this.renderMarquee();
        return;
      }

      // Hover over shape (shows port dots)
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

      // Double-click on shape -> edit text
      const shapeEl = e.target.closest('.diag-shape-node');
      if (shapeEl) {
        e.stopPropagation();
        const sid = shapeEl.dataset.id;
        this.startTextEdit('shape', sid);
        return;
      }

      // Double-click on connector -> edit label
      const connEl = e.target.closest('.diag-connector-node');
      if (connEl) {
        e.stopPropagation();
        const cid = connEl.dataset.id;
        this.startTextEdit('connector', cid);
        return;
      }

      // Double-click on frame title / frame -> edit frame title
      const frameEl = e.target.closest('.diag-frame-node');
      if (frameEl) {
        e.stopPropagation();
        const fid = frameEl.dataset.id;
        this.startTextEdit('frame', fid);
        return;
      }

      // Double-click on empty canvas -> add default block
      this.createShapeAt('block', this.snap(canvasPos.x - 80), this.snap(canvasPos.y - 34));
    }

    onKeyDown(e) {
      // Ignore if currently typing in an input or textarea
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
      }

      if (e.code === 'Space' && !this.spacePressed) {
        this.spacePressed = true;
        this.svgEl.style.cursor = 'grab';
      }

      // Shortcuts
      const key = e.key.toLowerCase();
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        if (key === 'v') this.setTool('select');
        if (key === 'h') this.setTool('hand');
        if (key === 'b') this.setTool('block');
        if (key === 'e' || key === 'o') this.setTool('ellipse');
        if (key === 'd') this.setTool('diamond');
        if (key === 'n') this.setTool('sticky');
        if (key === 't') this.setTool('text');
        if (key === 'l') this.setTool('connector');
        if (key === 'f') this.setTool('frame');
        if (key === 'escape') {
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

      // Ctrl shortcuts
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

    /* ---------------- Shape & Frame Creation ---------------- */

    createShapeAt(type, x, y, w = null, h = null) {
      const defaultSizes = {
        block: { w: 160, h: 68 },
        ellipse: { w: 140, h: 80 },
        diamond: { w: 120, h: 100 },
        sticky: { w: 140, h: 140 },
        text: { w: 120, h: 36 },
        frame: { w: 320, h: 220 }
      };
      const sz = defaultSizes[type] || { w: 150, h: 70 };
      const finalW = w ? Math.max(30, w) : sz.w;
      const finalH = h ? Math.max(25, h) : sz.h;

      if (type === 'frame') {
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
      } else {
        const isSticky = type === 'sticky';
        const isText = type === 'text';
        const shape = {
          id: uid('shape'),
          type,
          x: this.snap(x),
          y: this.snap(y),
          w: this.snap(finalW),
          h: this.snap(finalH),
          text: isSticky ? 'Note' : (isText ? 'Text label' : 'Block name'),
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
      }

      this.saveHistory();
      this.triggerAutosave();
      this.render();
      this.updateEmptyState();
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

      // If clicked without dragging, use default size
      if (w < 10 && h < 10) {
        this.createShapeAt(this.drawShapeType, this.drawStart.x, this.drawStart.y);
      } else {
        this.createShapeAt(this.drawShapeType, x, y, w, h);
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
        // Find all shapes whose center is inside the frame
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
      const dx = pos.x - (h.includes('w') ? orig.x : orig.x + orig.w);
      const dy = pos.y - (h.includes('n') ? orig.y : orig.y + orig.h);

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

      if (mw < 4 && mh < 4) return; // Tiny accidental drag

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
      // Delete attached connectors
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
      const idMap = {};
      (this.clipboard.shapes || []).forEach(orig => {
        const copy = clone(orig);
        const oldId = copy.id;
        copy.id = uid('shape');
        idMap[oldId] = copy.id;
        copy.x += 24;
        copy.y += 24;
        this.data.shapes.push(copy);
        this.selectedShapeIds.add(copy.id);
      });
      (this.clipboard.frames || []).forEach(orig => {
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
      let text = '', bounds = null, fontSz = 14, isBold = false, align = 'center', color = '#0f172a';

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
    }

    updateTransform() {
      const matrix = `matrix(${this.scale}, 0, 0, ${this.scale}, ${this.panX}, ${this.panY})`;
      this.viewportEl.setAttribute('transform', matrix);

      // Adjust pattern background
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
      const rect = this.svgEl.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const newScale = Math.min(Math.max(this.scale * factor, 0.15), 5.0);
      this.panX = cx - (cx - this.panX) * (newScale / this.scale);
      this.panY = cy - (cy - this.panY) * (newScale / this.scale);
      this.scale = newScale;
      this.updateTransform();
    }

    fitContent() {
      const allItems = [...this.data.shapes, ...this.data.frames];
      if (!allItems.length) {
        this.panX = 40;
        this.panY = 40;
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

      const pad = 60;
      const contentW = maxX - minX + pad * 2;
      const contentH = maxY - minY + pad * 2;
      const rect = this.svgEl.getBoundingClientRect();
      const viewW = rect.width || 800;
      const viewH = rect.height || 500;

      const scale = Math.min(viewW / contentW, viewH / contentH, 1.25);
      this.scale = Math.max(0.2, scale);
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
          <g class="diag-frame-node ${isSel ? 'is-selected' : ''}" data-id="${f.id}" transform="translate(${f.x}, ${f.y})">
            <rect width="${f.w}" height="${f.h}" rx="10"
                  fill="rgba(241, 245, 249, 0.45)"
                  stroke="${isSel ? '#2563eb' : strokeColor}"
                  stroke-width="${isSel ? 2.5 : 2}"
                  stroke-dasharray="8 6"/>
            <text x="12" y="24" fill="${strokeColor}" font-size="12" font-weight="700" letter-spacing="0.04em">
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
          // Elbow orthogonal route
          const midX = (p1.x + p2.x) / 2;
          d = `M ${p1.x} ${p1.y} H ${midX} V ${p2.y} H ${p2.x}`;
        }

        const strokeColor = isSel ? '#2563eb' : (c.stroke || '#64748b');
        const strokeWidth = isSel ? 3 : 2;
        const dashArray = c.style === 'dashed' ? '6 4' : (c.style === 'dotted' ? '2 3' : 'none');
        const markerEnd = (c.arrows === 'end' || c.arrows === 'both') ? 'url(#diag-arrow-end)' : '';
        const markerStart = (c.arrows === 'start' || c.arrows === 'both') ? 'url(#diag-arrow-start)' : '';

        // Label at midpoint
        const mx = (p1.x + p2.x) / 2;
        const my = (p1.y + p2.y) / 2;
        let labelHtml = '';
        if (c.label) {
          const lw = Math.max(c.label.length * 7.5 + 16, 32);
          labelHtml = `
            <g class="diag-conn-label" transform="translate(${mx}, ${my})">
              <rect x="${-lw / 2}" y="-11" width="${lw}" height="22" rx="5" fill="#ffffff" stroke="${strokeColor}" stroke-width="1.2"/>
              <text text-anchor="middle" y="4.5" font-size="11" font-weight="600" fill="${strokeColor}">
                ${escapeHtml(c.label)}
              </text>
            </g>
          `;
        }

        html += `
          <g class="diag-connector-node ${isSel ? 'is-selected' : ''}" data-id="${c.id}">
            <!-- Wider transparent hover path -->
            <path d="${d}" stroke="transparent" stroke-width="14" fill="none" style="cursor:pointer"/>
            <path d="${d}" stroke="${strokeColor}" stroke-width="${strokeWidth}"
                  stroke-dasharray="${dashArray}" fill="none"
                  marker-end="${markerEnd}" marker-start="${markerStart}"/>
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

        let shapeSvg = '';
        if (s.type === 'ellipse') {
          shapeSvg = `<ellipse cx="${s.w / 2}" cy="${s.h / 2}" rx="${s.w / 2}" ry="${s.h / 2}"
                               fill="${s.fill}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-dasharray="${dashArray}"/>`;
        } else if (s.type === 'diamond') {
          const pts = `${s.w / 2},0 ${s.w},${s.h / 2} ${s.w / 2},${s.h} 0,${s.h / 2}`;
          shapeSvg = `<polygon points="${pts}" fill="${s.fill}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-dasharray="${dashArray}"/>`;
        } else if (s.type === 'sticky') {
          shapeSvg = `
            <rect width="${s.w}" height="${s.h}" rx="2" fill="${s.fill}" stroke="${strokeColor}" stroke-width="${strokeWidth}"/>
            <path d="M ${s.w - 14} ${s.h} L ${s.w} ${s.h - 14} L ${s.w} ${s.h} Z" fill="rgba(0,0,0,0.15)"/>
          `;
        } else if (s.type === 'text') {
          shapeSvg = `<rect width="${s.w}" height="${s.h}" fill="transparent" stroke="none"/>`;
        } else {
          // Rounded rectangle block
          shapeSvg = `<rect width="${s.w}" height="${s.h}" rx="8" fill="${s.fill}" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-dasharray="${dashArray}"/>`;
        }

        // Multiline text rendering
        const lines = (s.text || '').split('\n');
        let textAnchor = 'middle';
        let textX = s.w / 2;
        if (s.align === 'left') { textAnchor = 'start'; textX = 12; }
        if (s.align === 'right') { textAnchor = 'end'; textX = s.w - 12; }

        const lineHeight = fontSz * 1.35;
        const totalTextHeight = lines.length * lineHeight;
        const startY = (s.h - totalTextHeight) / 2 + fontSz * 0.9;

        const textLinesSvg = lines.map((line, i) => `
          <tspan x="${textX}" y="${startY + i * lineHeight}" font-size="${fontSz}" font-weight="${s.bold ? (i === 0 ? '700' : '500') : '400'}" fill="${s.type === 'sticky' ? '#854d0e' : (s.domain ? (DOMAIN_PRESETS.find(d=>d.id===s.domain)?.text || '#1e293b') : '#1e293b')}">
            ${escapeHtml(line)}
          </tspan>
        `).join('');

        const lockIcon = s.locked ? `
          <g transform="translate(${s.w - 18}, 6)">
            <rect x="2" y="5" width="8" height="6" rx="1" fill="#64748b"/>
            <path d="M4 5V3a2 2 0 0 1 4 0v2" fill="none" stroke="#64748b" stroke-width="1.2"/>
          </g>
        ` : '';

        html += `
          <g class="diag-shape-node ${isSel ? 'is-selected' : ''}" data-id="${s.id}" transform="translate(${s.x}, ${s.y})">
            ${shapeSvg}
            <text text-anchor="${textAnchor}" style="pointer-events:none;">${textLinesSvg}</text>
            ${lockIcon}
          </g>
        `;
      });
      this.shapesLayer.innerHTML = html;
    }

    renderPorts() {
      // If a shape is hovered and not dragging/connecting, show connection ports
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
                         data-shape-id="${s.id}" data-side="${p.side}"/>`;
      });

      // Preserve existing overlay items if any
      const tmpDiv = document.createElement('div');
      tmpDiv.innerHTML = html;
      while (tmpDiv.firstChild) {
        this.overlayLayer.appendChild(tmpDiv.firstChild);
      }
    }

    renderSelectionHandles() {
      // 8 Resize handles for single selected shape or frame
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
                style="cursor:${hd.cursor}" data-handle="${hd.pos}"
                data-target-id="${item.id}" data-target-type="${type}"/>
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

      // Calculate bounding box in screen coordinates
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

      // Shape Context Toolbar
      if (this.selectedShapeIds.size > 0) {
        const firstShape = this.data.shapes.find(s => this.selectedShapeIds.has(s.id));
        tb.innerHTML = `
          <!-- Fill Swatches -->
          <div style="display:flex;align-items:center;gap:3px" title="Fill Color">
            ${COLOR_SWATCHES.slice(0, 7).map(c => `
              <span class="diag-swatch" data-act="set-fill" data-val="${c}" style="background:${c === 'none' ? 'linear-gradient(45deg, #fff 40%, red 50%, #fff 60%)' : c}"></span>
            `).join('')}
          </div>
          <div class="diag-sep" style="width:1px;height:18px;background:#e2e8f0"></div>
          <!-- Border Style -->
          <select class="diag-ctx-sel" data-act="set-border-style" style="border:1px solid #cbd5e1;border-radius:4px;padding:2px 4px;font-size:11px" title="Border Style">
            <option value="solid" ${firstShape?.strokeStyle === 'solid' ? 'selected' : ''}>Solid</option>
            <option value="dashed" ${firstShape?.strokeStyle === 'dashed' ? 'selected' : ''}>Dashed</option>
            <option value="dotted" ${firstShape?.strokeStyle === 'dotted' ? 'selected' : ''}>Dotted</option>
          </select>
          <!-- Border Width -->
          <select class="diag-ctx-sel" data-act="set-border-width" style="border:1px solid #cbd5e1;border-radius:4px;padding:2px 4px;font-size:11px" title="Border Width">
            <option value="1" ${firstShape?.strokeWidth === 1 ? 'selected' : ''}>1px</option>
            <option value="2" ${firstShape?.strokeWidth === 2 ? 'selected' : ''}>2px</option>
            <option value="3" ${firstShape?.strokeWidth === 3 ? 'selected' : ''}>3px</option>
            <option value="4" ${firstShape?.strokeWidth === 4 ? 'selected' : ''}>4px</option>
          </select>
          <!-- Text Size -->
          <button type="button" class="btn" data-act="cycle-font-size" style="padding:1px 6px;font-size:11px" title="Font Size (S/M/L)">${firstShape?.fontSize || 'M'}</button>
          <!-- Z-Order -->
          <button type="button" class="btn" data-act="bring-front" style="padding:1px 5px;font-size:11px" title="Bring to front">▲</button>
          <button type="button" class="btn" data-act="send-back" style="padding:1px 5px;font-size:11px" title="Send to back">▼</button>
          <!-- Lock -->
          <button type="button" class="btn" data-act="toggle-lock" style="padding:1px 6px;font-size:11px" title="Lock / Unlock">${firstShape?.locked ? '🔒' : '🔓'}</button>
          <!-- Delete -->
          <button type="button" class="btn" data-act="delete-sel" style="padding:1px 6px;color:#ef4444;font-size:11px" title="Delete">🗑</button>
        `;
      } else if (this.selectedConnectorIds.size > 0) {
        // Connector Context Toolbar
        const firstConn = this.data.connectors.find(c => this.selectedConnectorIds.has(c.id));
        tb.innerHTML = `
          <!-- Connector Stroke Swatches -->
          <div style="display:flex;align-items:center;gap:3px" title="Stroke Color">
            ${STROKE_SWATCHES.slice(0, 5).map(c => `
              <span class="diag-swatch" data-act="set-conn-stroke" data-val="${c}" style="background:${c}"></span>
            `).join('')}
          </div>
          <div class="diag-sep" style="width:1px;height:18px;background:#e2e8f0"></div>
          <!-- Line Style -->
          <button type="button" class="btn" data-act="toggle-conn-style" style="padding:1px 6px;font-size:11px">${firstConn?.style || 'solid'}</button>
          <!-- Arrows -->
          <select class="diag-ctx-sel" data-act="set-conn-arrows" style="border:1px solid #cbd5e1;border-radius:4px;padding:2px 4px;font-size:11px" title="Arrow Heads">
            <option value="none" ${firstConn?.arrows === 'none' ? 'selected' : ''}>None</option>
            <option value="end" ${firstConn?.arrows === 'end' ? 'selected' : ''}>End (→)</option>
            <option value="both" ${firstConn?.arrows === 'both' ? 'selected' : ''}>Both (↔)</option>
          </select>
          <!-- Route -->
          <select class="diag-ctx-sel" data-act="set-conn-route" style="border:1px solid #cbd5e1;border-radius:4px;padding:2px 4px;font-size:11px" title="Routing">
            <option value="elbow" ${firstConn?.route === 'elbow' ? 'selected' : ''}>Elbow</option>
            <option value="straight" ${firstConn?.route === 'straight' ? 'selected' : ''}>Straight</option>
          </select>
          <!-- Label -->
          <button type="button" class="btn" data-act="edit-conn-label" style="padding:1px 6px;font-size:11px">Label</button>
          <!-- Delete -->
          <button type="button" class="btn" data-act="delete-sel" style="padding:1px 6px;color:#ef4444;font-size:11px" title="Delete">🗑</button>
        `;
      } else if (this.selectedFrameIds.size > 0) {
        // Frame Context Toolbar
        tb.innerHTML = `
          <span style="font-size:11px;font-weight:600;color:#64748b">Frame Color:</span>
          <div style="display:flex;align-items:center;gap:3px">
            ${STROKE_SWATCHES.slice(0, 5).map(c => `
              <span class="diag-swatch" data-act="set-frame-stroke" data-val="${c}" style="background:${c}"></span>
            `).join('')}
          </div>
          <button type="button" class="btn" data-act="edit-frame-title" style="padding:1px 6px;font-size:11px">Rename</button>
          <button type="button" class="btn" data-act="delete-sel" style="padding:1px 6px;color:#ef4444;font-size:11px" title="Delete">🗑</button>
        `;
      }

      // Bind Context Toolbar Actions
      tb.onchange = (e) => this.onContextToolbarChange(e);
      tb.onclick = (e) => this.onContextToolbarClick(e);
    }

    onContextToolbarClick(e) {
      const target = e.target.closest('[data-act]');
      if (!target) return;
      const act = target.dataset.act;

      if (act === 'set-fill') {
        const val = target.dataset.val;
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) {
            s.fill = val;
            // Preset stroke match if domain
            const matchDom = DOMAIN_PRESETS.find(d => d.fill === val);
            if (matchDom && matchDom.stroke) s.stroke = matchDom.stroke;
          }
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'set-conn-stroke') {
        const val = target.dataset.val;
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.stroke = val;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'set-frame-stroke') {
        const val = target.dataset.val;
        this.selectedFrameIds.forEach(id => {
          const f = this.data.frames.find(x => x.id === id);
          if (f) f.stroke = val;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
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
      }

      if (act === 'bring-front') {
        const maxZ = Math.max(0, ...this.data.shapes.map(s => s.z || 0));
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.z = maxZ + 1;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'send-back') {
        const minZ = Math.min(0, ...this.data.shapes.map(s => s.z || 0));
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.z = minZ - 1;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'toggle-lock') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.locked = !s.locked;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'toggle-conn-style') {
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.style = c.style === 'dashed' ? 'solid' : 'dashed';
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'edit-conn-label') {
        const cid = [...this.selectedConnectorIds][0];
        if (cid) this.startTextEdit('connector', cid);
      }

      if (act === 'edit-frame-title') {
        const fid = [...this.selectedFrameIds][0];
        if (fid) this.startTextEdit('frame', fid);
      }

      if (act === 'delete-sel') {
        this.deleteSelected();
      }
    }

    onContextToolbarChange(e) {
      const target = e.target.closest('[data-act]');
      if (!target) return;
      const act = target.dataset.act;

      if (act === 'set-border-style') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.strokeStyle = target.value;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'set-border-width') {
        this.selectedShapeIds.forEach(id => {
          const s = this.data.shapes.find(x => x.id === id);
          if (s) s.strokeWidth = Number(target.value) || 2;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'set-conn-arrows') {
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.arrows = target.value;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }

      if (act === 'set-conn-route') {
        this.selectedConnectorIds.forEach(id => {
          const c = this.data.connectors.find(x => x.id === id);
          if (c) c.route = target.value;
        });
        this.saveHistory();
        this.triggerAutosave();
        this.render();
      }
    }

    /* ---------------- Empty State & Templates ---------------- */

    updateEmptyState() {
      const isEmpty = this.data.shapes.length === 0 && this.data.frames.length === 0;
      this.emptyStateEl.style.display = isEmpty ? 'block' : 'none';
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

  return DiagramEditor;
});
