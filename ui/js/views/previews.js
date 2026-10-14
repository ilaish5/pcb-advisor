/* PCB Advisor UI - Schematic + PCB previews: zoom/pan, net highlight, component panel. */

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
  const newScale = Math.max(0.3, Math.min(8.0, z.scale * (factor || 1)));
  z.scale = newScale;
  updateZoomTransform(wrap, z);
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
function highlightNet(net) {
  if (!net) return;
  const schSvg = $('#schwrap svg') || $('#sch');
  if (schSvg) {
    schSvg.querySelectorAll('.hl-net').forEach(el => el.classList.remove('hl-net'));
    schSvg.querySelectorAll(`[data-net="${net}"]`).forEach(el => el.classList.add('hl-net'));
  }
  const pcbSvg = $('#pcbwrap svg');
  if (pcbSvg) {
    pcbSvg.querySelectorAll('.hl-net').forEach(el => el.classList.remove('hl-net'));
    pcbSvg.querySelectorAll(`[data-net="${net}"]`).forEach(el => el.classList.add('hl-net'));
  }
}
function updateZoomTransform(wrap, z) {
  if (!wrap) return;
  const svg = wrap.querySelector('svg');
  if (!svg) return;
  if (z.scale === 1 && z.x === 0 && z.y === 0) {
    svg.style.transform = '';
  } else {
    svg.style.transform = `translate(${z.x}px, ${z.y}px) scale(${z.scale})`;
  }
  svg.style.transformOrigin = 'center center';
}
function initZoomPan(wrapId, zoomState) {
  const wrap = typeof wrapId === 'string' ? document.getElementById(wrapId) : wrapId;
  if (!wrap || wrap.dataset.zoomInited) return;
  wrap.dataset.zoomInited = '1';

  wrap.addEventListener('wheel', e => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.87;
    applyZoom(zoomState, factor, wrap);
  }, {passive: false});

  wrap.addEventListener('mousedown', e => {
    // Retained for test compatibility; pan is handled via attachPanHelper pointer events
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
        // Press and hold right button (button === 2) and middle button (button === 1) = pan
        if (e.button === 2 || e.button === 1) return true;
        // Left-drag on empty space in the previews
        if (e.button === 0) {
          const interactive = e.target.closest && e.target.closest('g.part, g.net-label, g.power-port, g.port, g.pcb-comp, rect.pad, button, a, input, select');
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

function compPanelHTML() {
  if (!compPanel) return '';
  if (compPanel.loading) {
    return `
      <div class="comp-panel-h">
        <div><div class="comp-panel-ref">${esc(compPanel.ref)}</div><div class="comp-panel-sub">Loading component…</div></div>
        <button class="x" data-act="close-comp-panel" aria-label="Close component panel">×</button>
      </div>
      <div class="comp-panel-b"><div class="dnote">Loading component details…</div></div>`;
  }
  const d = compPanel.data;
  if (!d || d.error) {
    return `
      <div class="comp-panel-h">
        <div><div class="comp-panel-ref">${esc(compPanel.ref)}</div><div class="comp-panel-sub">Not found</div></div>
        <button class="x" data-act="close-comp-panel" aria-label="Close component panel">×</button>
      </div>
      <div class="comp-panel-b"><div class="warnbox">Component ${esc(compPanel.ref)} could not be loaded.</div></div>`;
  }
  const bom = d.bom || null;
  const pins = d.pins || [];
  const params = d.params || {};
  const paramKeys = Object.keys(params);

  return `
    <div class="comp-panel-h">
      <div>
        <div class="comp-panel-ref">${esc(d.ref)}</div>
        <div class="comp-panel-sub">${esc(d.value || d.comment || d.mpn || '')}</div>
      </div>
      <button class="x" data-act="close-comp-panel" aria-label="Close component panel">×</button>
    </div>
    <div class="comp-panel-b">
      <div class="comp-panel-actions">
        <button class="btn pri" data-act="ask-comp" data-ref="${esc(d.ref)}" data-mpn="${esc(d.mpn || '')}">Ask about this part</button>
        ${bom && bom.line ? `<button class="btn" data-act="show-in-bom" data-line="${esc(bom.line)}">Show in BOM</button>` : ''}
      </div>

      <div class="comp-props">
        <div class="comp-prop"><span class="comp-prop-k">Designator</span><span class="comp-prop-v m">${esc(d.ref)}</span></div>
        <div class="comp-prop"><span class="comp-prop-k">Value/Comment</span><span class="comp-prop-v">${esc(d.value || d.comment || '—')}</span></div>
        <div class="comp-prop"><span class="comp-prop-k">MPN</span><span class="comp-prop-v m">${esc(d.mpn || '—')}</span></div>
        <div class="comp-prop"><span class="comp-prop-k">Package</span><span class="comp-prop-v">${esc(d.footprint || d.package || '—')}</span></div>
        <div class="comp-prop"><span class="comp-prop-k">Sheet</span><span class="comp-prop-v">${esc(d.sheet || '—')}</span></div>
        <div class="comp-prop">
          <span class="comp-prop-k">BOM line</span>
          <span class="comp-prop-v">${bom ? `${esc(bom.line)}${bom.jlc_code ? ' · JLC: ' + esc(bom.jlc_code) : ''}${bom.stock != null ? ' · Stock: ' + num(bom.stock) : ''}` : '<span style="color:var(--dim)">Not in BOM</span>'}</span>
        </div>
        <div class="comp-prop">
          <span class="comp-prop-k">Datasheet</span>
          <span class="comp-prop-v">${d.datasheet ? `<button type="button" class="lnk" data-act="open-comp-datasheet" data-src="${esc(d.datasheet)}">${esc(d.datasheet)}</button>` : '<span style="color:var(--dim)">—</span>'}</span>
        </div>
      </div>

      ${d.description ? `<div style="font-size:12px;color:var(--dim)">${esc(d.description)}</div>` : ''}

      <div>
        <h4 style="margin:0 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim)">Pins (${pins.length})</h4>
        ${pins.length ? `
          <div class="tblwrap" style="max-height:220px;overflow-y:auto">
            <table class="comp-pins-tbl">
              <thead><tr><th>Pin</th><th>Name</th><th>Net</th></tr></thead>
              <tbody>
                ${pins.map(p => `
                  <tr>
                    <td class="m">${esc(p.number)}</td>
                    <td class="m">${esc(p.name)}</td>
                    <td>${p.net ? `<button type="button" class="ref net-btn" data-act="highlight-net" data-net="${esc(p.net)}" title="Highlight in preview">${esc(p.net)}</button>` : '<span style="color:var(--dim)">—</span>'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>` : '<div class="dnote">No pin information</div>'}
      </div>

      ${paramKeys.length ? `
        <div>
          <h4 style="margin:0 0 4px;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim)">Parameters (${paramKeys.length})</h4>
          <div class="tblwrap" style="max-height:160px;overflow-y:auto">
            <table class="comp-params-tbl">
              <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
              <tbody>
                ${paramKeys.map(k => `
                  <tr>
                    <td><b>${esc(k)}</b></td>
                    <td class="m" style="word-break:break-all">${esc(params[k])}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>` : ''}
    </div>`;
}

async function openCompPanel(ref, sheet) {
  compPanel = {ref, sheet, loading: true, data: null};
  renderCompPanel();
  try {
    const qUrl = `/api/sch/component?ref=${encodeURIComponent(ref)}${sheet ? '&sheet=' + encodeURIComponent(sheet) : ''}&${q()}`;
    const data = await api(qUrl, undefined, {soft: true});
    compPanel = {ref, sheet, loading: false, data};
    renderCompPanel();
  } catch (err) {
    compPanel = {ref, sheet, loading: false, data: {error: err.message}};
    renderCompPanel();
  }
}
function closeCompPanel() {
  compPanel = null;
  renderCompPanel();
}
function renderCompPanel() {
  const p = $('#comp-panel');
  if (!p) return;
  if (!compPanel) {
    p.hidden = true;
    p.innerHTML = '';
  } else {
    p.hidden = false;
    p.innerHTML = compPanelHTML();
  }
}

let schBusy = false;
function schHTML(container) {
  if (!S.sheets || !S.sheets.length) return `${guidanceBarHTML('sch')}<div class="vhead"><div><h2>Schematic preview</h2><p>No sheets yet. Ask the agent to draw one once the parts are chosen.</p></div></div>`;
  if (!sheetId || !S.sheets.find(s => s.id === sheetId)) sheetId = S.sheets[0].id;
  const schSelBar = schSel ? `
    <div class="sel-bar" id="sch-sel-bar" style="margin-bottom:6px">
      <span>Selected: <b>${esc(schSel.type)}: ${esc(schSel.name)}</b></span>
      <button class="btn pri" data-act="ask-sch" data-target="${esc(schSel.name)}" data-kind="${esc(schSel.type)}">Ask about this</button>
      <button class="btn" data-act="clear-sch-sel">Clear</button>
    </div>` : '';
  return `${guidanceBarHTML('sch')}
    <div class="vhead" style="margin-bottom:6px"><div><h2>Schematic preview</h2><p>Rendered from the netlist and linked SchDoc. Click any component or net to ask questions or inspect connections.</p></div></div>
    <div class="preview-layout" id="sch-preview-layout">
      <div class="preview-main">
        <div class="preview-toolbar">
          <div class="sheets">${S.sheets.map(s => `<button class="sheet" data-sheet="${esc(s.id)}" aria-pressed="${s.id === sheetId}"><span class="m">${esc(s.id)}</span> ${esc(s.title)}</button>`).join('')}</div>
          <div class="zoom-controls">
            <button type="button" class="zoom-btn" data-act="sch-zoom-in" title="Zoom in" aria-label="Zoom in">+</button>
            <button type="button" class="zoom-btn" data-act="sch-zoom-out" title="Zoom out" aria-label="Zoom out">−</button>
            <button type="button" class="zoom-btn" data-act="sch-zoom-fit" title="Fit to view">Fit</button>
          </div>
        </div>
        ${schSelBar}
        <div class="schwrap preview-box" id="schwrap">${svgCache.text ? svgCache.text : '<div class="dnote" style="margin:12px">Rendering schematic…</div>'}</div>
      </div>
      <aside class="comp-panel card" id="comp-panel" ${compPanel ? '' : 'hidden'} aria-label="Component details">
        ${compPanelHTML()}
      </aside>
    </div>`;
}

async function loadSheet() {
  const key = sheetId + '|' + JSON.stringify(lines().map(l => [l.key, l.mpn, l.value, l.dnp])) + JSON.stringify(S.sheets.map(s => Object.keys(s.parts).length));
  if (svgCache.key === key && svgCache.text) { afterSheet(); return; }
  const r = await fetch('/api/sheet.svg?' + q({sheet: sheetId}));
  if (!r.ok) { svgCache = {key: '', text: ''}; return; }
  svgCache = {key, text: await r.text()};
  const w = $('#schwrap'); if (w) { w.innerHTML = svgCache.text; afterSheet(); }
}
function afterSheet() {
  const wrap = $('#schwrap');
  if (wrap) initZoomPan('schwrap', schZoom);
  const svg = $('#schwrap svg') || $('#sch'); if (!svg) return;
  if (!svg.dataset.hl) {
    for (const g of svg.querySelectorAll('g.part')) {
      const b = g.getBBox(); if (!b.width) continue;
      const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      r.setAttribute('x', b.x - 6); r.setAttribute('y', b.y - 6); r.setAttribute('width', b.width + 12); r.setAttribute('height', b.height + 12);
      r.setAttribute('rx', 6); r.setAttribute('class', 'hlbox'); g.insertBefore(r, g.firstChild);
    }
    svg.dataset.hl = '1';
  }
  // Click on parts
  svg.querySelectorAll('g.part').forEach(g => {
    g.style.cursor = 'pointer';
    g.onclick = e => {
      e.stopPropagation();
      if (schZoom.didDrag) return;
      const ref = g.dataset.ref;
      schSel = {type: 'Component', name: ref};
      openCompPanel(ref, sheetId);
      const l = lineOfRef(ref);
      if (l) select(l.key);
      else renderCenter(true);
    };
  });
  // Click on net labels, power ports, ports
  svg.querySelectorAll('g.net-label, g.power-port, g.port').forEach(g => {
    g.style.cursor = 'pointer';
    g.onclick = e => {
      e.stopPropagation();
      if (schZoom.didDrag) return;
      const net = g.dataset.net || g.dataset.port || g.textContent.trim();
      const type = g.classList.contains('power-port') ? 'Power net' : g.classList.contains('port') ? 'Port' : 'Net';
      schSel = {type, name: net};
      highlightNet(net);
      renderCenter(true);
    };
  });
  applyFocus();
}
function applyFocus() {
  const svg = $('#schwrap svg') || $('#sch'); if (!svg) return;
  const l = sel && lineByKey(sel);
  svg.classList.toggle('focus', !!l);
  svg.querySelectorAll('g.part').forEach(g => g.classList.toggle('sel', !!l && (l.refs || []).includes(g.dataset.ref)));
}

/* ---------- pcb preview ---------- */
function formatPcbPreview(raw) {
  if (!raw) return '<div class="dnote" style="margin:12px;color:#94a3b8">Rendering PCB preview…</div>';
  if (typeof raw === 'string' && (raw.includes('Settings to view PCB') || raw.includes('No Altium .PcbDoc linked'))) {
    const m = raw.match(/<text[^>]*>([\s\S]*?)<\/text>/i);
    const msg = m ? m[1].replace(/&amp;/g, '&') : 'No Altium .PcbDoc linked. Link one in Settings to view PCB placement & routing preview.';
    return `<div class="pcb-empty-state" style="display:flex;align-items:center;justify-content:center;height:100%;min-height:300px;width:100%;padding:24px 32px;text-align:center;color:#94a0bd;font-size:14px;line-height:1.6;box-sizing:border-box;"><div style="max-width:540px;margin:auto">${esc(msg)}</div></div>`;
  }
  return raw;
}
function pcbHTML(container) {
  const plan = S.placement_plan || null;
  const selBar = pcbSel ? `
    <div class="sel-bar" id="pcb-sel-bar" style="margin-bottom:6px">
      <span>Selected: <b>${esc(pcbSel.type || 'Component')}: ${esc(pcbSel.name)}</b>${pcbSel.desc ? ' · ' + esc(pcbSel.desc) : ''}</span>
      <button class="btn pri" data-act="ask-pcb" data-target="${esc(pcbSel.name)}" data-kind="${esc(pcbSel.type || 'Component')}">Ask about this</button>
      <button class="btn" data-act="clear-pcb-sel">Clear</button>
    </div>` : '';
  const grpCount = (plan && plan.groups) ? plan.groups.length : 3;
  const koCount = (plan && plan.keep_outs) ? plan.keep_outs.length : 1;
  const netCount = (plan && plan.critical_nets) ? plan.critical_nets.length : 2;
  return `${guidanceBarHTML('pcb')}
    <div class="vhead" style="margin-bottom:6px"><div><h2>Placement & routing preview</h2><p>PcbDoc components, pads, and outline with proposed placement plan overlays. Toggle layers and click any component to ask about layout.</p></div>
      <div class="vacts">
        <button class="btn ${pcbLayers.top ? 'pri' : ''}" data-act="toggle-layer" data-layer="top">Top layer</button>
        <button class="btn ${pcbLayers.bottom ? 'pri' : ''}" data-act="toggle-layer" data-layer="bottom">Bottom layer</button>
        <button class="btn ${pcbLayers.plan ? 'pri' : ''}" data-act="toggle-layer" data-layer="plan">Plan overlay</button>
      </div>
    </div>
    <div class="preview-layout" id="pcb-preview-layout">
      <div class="preview-main">
        <div class="preview-toolbar">
          <div style="font-size:12px;font-weight:600;color:var(--dim)">PCB Layout View</div>
          <div class="zoom-controls">
            <button type="button" class="zoom-btn" data-act="pcb-zoom-in" title="Zoom in" aria-label="Zoom in">+</button>
            <button type="button" class="zoom-btn" data-act="pcb-zoom-out" title="Zoom out" aria-label="Zoom out">−</button>
            <button type="button" class="zoom-btn" data-act="pcb-zoom-fit" title="Fit to view">Fit</button>
          </div>
        </div>
        ${selBar}
        <div class="pcbwrap preview-box" id="pcbwrap">${pcbSvgCache.text ? formatPcbPreview(pcbSvgCache.text) : '<div class="dnote" style="margin:12px;color:#94a3b8">Rendering PCB preview…</div>'}</div>
      </div>
      <aside class="comp-panel card" id="comp-panel" ${compPanel ? '' : 'hidden'} aria-label="Component details">
        ${compPanelHTML()}
      </aside>
    </div>
    <div class="plan-card" id="plan-card" style="margin-top:12px">
      <h3 style="margin:0 0 8px;font-size:13px">Proposed placement & routing plan</h3>
      <div style="font-size:12.5px;color:var(--dim);margin-bottom:8px">The agent proposes placement zones, keep-outs, and critical-net priorities before you place parts in Altium.</div>
      <div class="kpis">
        <div class="kpi"><b>${grpCount}</b><span>functional zones</span></div>
        <div class="kpi"><b>${koCount}</b><span>keep-outs</span></div>
        <div class="kpi"><b>${netCount}</b><span>critical nets</span></div>
      </div>
    </div>`;
}
async function loadPcb() {
  const key = PROJECT + '|' + (ALTIUM_DATA?.linked?.pcb_file || '') + '|' + JSON.stringify(pcbLayers);
  if (pcbSvgCache.key === key && pcbSvgCache.text) { afterPcb(); return; }
  try {
    const r = await fetch('/api/preview/pcb.svg?' + q());
    if (!r.ok) {
      const w = $('#pcbwrap');
      if (w) w.innerHTML = '<div class="dnote" style="margin:12px;color:#94a3b8">No PcbDoc linked or preview unavailable. Link an Altium project with a .PcbDoc in Settings.</div>';
      return;
    }
    pcbSvgCache = {key, text: await r.text()};
    const w = $('#pcbwrap');
    if (w) { w.innerHTML = formatPcbPreview(pcbSvgCache.text); afterPcb(); }
  } catch (e) { /* ignored */ }
}
function afterPcb() {
  const wrap = $('#pcbwrap');
  if (wrap) initZoomPan('pcbwrap', pcbZoom);
  const svg = $('#pcbwrap svg');
  if (!svg) return;
  svg.classList.add('pcb-preview');
  svg.classList.toggle('hide-top', !pcbLayers.top);
  svg.classList.toggle('hide-bottom', !pcbLayers.bottom);
  svg.classList.toggle('hide-plan', !pcbLayers.plan);
  svg.querySelectorAll('g.pcb-comp').forEach(g => {
    g.style.cursor = 'pointer';
    g.onclick = e => {
      e.stopPropagation();
      if (pcbZoom.didDrag) return;
      const ref = g.dataset.ref || g.id?.replace(/^pcb-comp-/, '');
      if (ref) {
        pcbSel = {type: 'Component', name: ref, desc: g.querySelector('title')?.textContent || ''};
        openCompPanel(ref);
        renderCenter(true);
      }
    };
  });
  svg.querySelectorAll('rect.pad').forEach(g => {
    g.style.cursor = 'pointer';
    g.onclick = e => {
      e.stopPropagation();
      if (pcbZoom.didDrag) return;
      const net = g.dataset.net;
      if (net) {
        highlightNet(net);
        toast('Net ' + net);
      }
    };
  });
  svg.querySelectorAll('g.plan-group').forEach(g => {
    g.style.cursor = 'pointer';
    g.onclick = e => {
      e.stopPropagation();
      if (pcbZoom.didDrag) return;
      const grp = g.dataset.group;
      if (grp) {
        pcbSel = {type: 'Zone', name: grp, desc: g.querySelector('title')?.textContent || ''};
        renderCenter(true);
      }
    };
  });
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('clear-sch-anchor', async (el, d, e) => {
  schAnchor = null; renderCenter(true); return;
});
onAct('close-comp-panel', async (el, d, e) => {
  closeCompPanel(); return;
});
onAct('ask-comp', async (el, d, e) => {
  const ref = el.dataset.ref;
  const mpn = el.dataset.mpn;
  const txt = mpn ? `Tell me about ${ref} (${mpn}) in the circuit. What is its role and what should I check?` : `Tell me about ${ref} in the circuit. What is its role and what should I check?`;
  const inp = $('#input');
  if (inp) { inp.value = txt; inp.focus(); }
  setView('chat');
  return;
});
onAct('show-in-bom', async (el, d, e) => {
  const line = el.dataset.line;
  if (line) {
    select(line);
    go('workspace', 'bom');
  }
  return;
});
onAct('open-comp-datasheet', async (el, d, e) => {
  const src = el.dataset.src;
  if (src) {
    hitSrc = src;
    openViewerSource(src);
  }
  return;
});
onAct('highlight-net', async (el, d, e) => {
  const net = el.dataset.net;
  if (net) {
    highlightNet(net);
    toast('Highlighted net ' + net);
  }
  return;
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
onAct('ask-sch', async (el, d, e) => {
  const target = el.dataset.target, kind = el.dataset.kind || 'part';
  const txt = `Tell me about ${kind} ${target} on the schematic. What is its role and what should I check?`;
  const inp = $('#input');
  if (inp) { inp.value = txt; inp.focus(); }
  setView('chat');
  return;
});
onAct('clear-sch-sel', async (el, d, e) => {
  schSel = null; renderCenter(true); return;
});
onAct('ask-pcb', async (el, d, e) => {
  const target = el.dataset.target, kind = el.dataset.kind || 'part';
  const txt = `Tell me about the layout and routing of ${kind} ${target} on the PCB. What are the clearance, placement, and trace rules?`;
  const inp = $('#input');
  if (inp) { inp.value = txt; inp.focus(); }
  setView('chat');
  return;
});
onAct('clear-pcb-sel', async (el, d, e) => {
  pcbSel = null; renderCenter(true); return;
});
onAct('toggle-layer', async (el, d, e) => {
  const layer = el.dataset.layer;
  if (layer in pcbLayers) {
    pcbLayers[layer] = !pcbLayers[layer];
    afterPcb();
    renderCenter(true);
  }
  return;
});
