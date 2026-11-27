/* Library quick previews: one click on a model icon (Symbol, Footprint, 3D, Pins) opens a dialog over the page, Esc closes it.
   The geometry comes from /api/library/preview (scripts/model_preview.py reads the part's own files); the 3D view is views/model3d.js.
   Names here start with mp so they cannot clash with the other files in the shared script scope.
   The dialog is modal on purpose: the page is not drawn again under it (uiBusy), so the 3D canvas is never thrown away. */
let mpDlg = null, mpView = null, mpToken = 0, mpCur = null;      // the dialog, the running 3D view, the latest load, {line, kind}

const MP_TITLE = {symbol: 'Symbol', footprint: 'Footprint', model: '3D model', pins: 'Pins'};
const MP_FS_MIN = 0.0001;

function mpNum(v) { return Math.round(v * 1000) / 1000; }
function mpSpan(b) { return [b[2] - b[0], b[3] - b[1]]; }

/* ---------- the symbol: body and pins, with their numbers and names (mil, y up -> y down) ---------- */
function mpArcPath(cx, cy, r, a0, a1, Y) {
  const rad = d => d * Math.PI / 180;
  const sweep = ((a1 - a0) % 360 + 360) % 360 || 360;
  const p = a => [cx + r * Math.cos(rad(a)), Y(cy + r * Math.sin(rad(a)))];
  const [x0, y0] = p(a0), [x1, y1] = p(a0 + sweep);
  return `M${mpNum(x0)} ${mpNum(y0)}A${mpNum(r)} ${mpNum(r)} 0 ${sweep > 180 ? 1 : 0} 0 ${mpNum(x1)} ${mpNum(y1)}`;
}
function mpSymbolSVG(d) {
  const [w0, h0] = mpSpan(d.bounds);
  const m = Math.max(120, Math.max(w0, h0) * 0.28);
  const x0 = d.bounds[0] - m, y0 = -d.bounds[3] - m, w = w0 + 2 * m, h = h0 + 2 * m;
  const fs = Math.max(26, Math.min(64, Math.max(w, h) / 24));
  const Y = y => -y;
  const gfx = d.gfx.map(g => {
    if (g.k === 'rect') return `<rect class="sy-body" x="${Math.min(g.x1, g.x2)}" y="${Y(Math.max(g.y1, g.y2))}" width="${Math.abs(g.x2 - g.x1)}" height="${Math.abs(g.y2 - g.y1)}"/>`;
    if (g.k === 'poly') return `<${g.fill ? 'polygon' : 'polyline'} class="${g.fill ? 'sy-body' : 'sy-line'}" points="${g.pts.map(p => p[0] + ',' + Y(p[1])).join(' ')}"/>`;
    if (Math.abs(g.a1 - g.a0) >= 360) return `<circle class="sy-line" cx="${g.cx}" cy="${Y(g.cy)}" r="${g.r}"/>`;
    return `<path class="sy-line" d="${mpArcPath(g.cx, g.cy, g.r, g.a0, g.a1, Y)}"/>`;
  }).join('');
  const pins = d.pins.map(p => {
    const mx = (p.x + p.cx) / 2, my = (p.y + p.cy) / 2, horiz = p.dy === 0;
    const num = horiz ? `<text class="sy-num" x="${mx}" y="${Y(p.y) - fs * 0.3}" text-anchor="middle" font-size="${fs}">${esc(p.num)}</text>`
      : `<text class="sy-num" x="${p.x + fs * 0.4}" y="${Y(my) + fs * 0.35}" font-size="${fs}">${esc(p.num)}</text>`;
    let name = '';
    if (p.name && p.name !== p.num) {
      if (horiz) name = `<text class="sy-name" x="${p.x - p.dx * fs * 0.5}" y="${Y(p.y) + fs * 0.35}" text-anchor="${p.dx < 0 ? 'start' : 'end'}" font-size="${fs}">${esc(p.name)}</text>`;
      else {
        const X = p.x + fs * 0.35, YY = Y(p.y) + p.dy * fs * 0.5;          // inside the body, reading upward
        name = `<text class="sy-name" transform="rotate(-90 ${X} ${YY})" x="${X}" y="${YY}" text-anchor="${p.dy > 0 ? 'end' : 'start'}" font-size="${fs}">${esc(p.name)}</text>`;
      }
    }
    return `<g><line class="sy-pin" x1="${p.x}" y1="${Y(p.y)}" x2="${p.cx}" y2="${Y(p.cy)}"/><circle class="sy-end" cx="${p.cx}" cy="${Y(p.cy)}" r="${fs * 0.14}"/>${num}${name}</g>`;
  }).join('');
  return `<svg class="mp-svg" viewBox="${mpNum(x0)} ${mpNum(y0)} ${mpNum(w)} ${mpNum(h)}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Symbol ${esc(d.name)}, ${d.pins.length} pins">${gfx}${pins}</svg>`;
}

/* ---------- the footprint: pads at true scale (mm), pin 1 marked, courtyard and silk ---------- */
function mpFpPoints(d) {
  const xs = [d.bounds[0], d.bounds[2]], ys = [d.bounds[1], d.bounds[3]];
  for (const i of d.courtyard) {
    if (i.k === 'line') { xs.push(i.x1, i.x2); ys.push(i.y1, i.y2); }
    else if (i.k === 'poly') i.pts.forEach(p => { xs.push(p[0]); ys.push(p[1]); });
    else { xs.push(i.cx - i.r, i.cx + i.r); ys.push(i.cy - i.r, i.cy + i.r); }
  }
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
function mpFpArt(items, cls) {
  const Y = y => -y;
  return items.map(i => {
    if (i.k === 'line') return `<line class="${cls}" x1="${i.x1}" y1="${Y(i.y1)}" x2="${i.x2}" y2="${Y(i.y2)}" stroke-width="${Math.max(i.w || 0, 0.05)}"/>`;
    if (i.k === 'poly') return `<polygon class="${cls}" points="${i.pts.map(p => p[0] + ',' + Y(p[1])).join(' ')}" stroke-width="0.05"/>`;
    if (Math.abs(i.a1 - i.a0) >= 360) return `<circle class="${cls}" cx="${i.cx}" cy="${Y(i.cy)}" r="${i.r}" stroke-width="${Math.max(i.w || 0, 0.05)}"/>`;
    return `<path class="${cls}" d="${mpArcPath(i.cx, i.cy, i.r, i.a0, i.a1, Y)}" stroke-width="${Math.max(i.w || 0, 0.05)}"/>`;
  }).join('');
}
function mpPadSVG(p, one, fs) {
  const hw = p.w / 2, hh = p.h / 2;
  const rx = p.shape === 'round' || p.shape === 'oval' ? Math.min(hw, hh) : p.shape === 'roundrect' ? (p.radius || 0) : p.shape === 'octagon' ? Math.min(hw, hh) * 0.4 : 0;
  const hole = !p.hole ? '' : p.slot
    ? `<rect class="fp-hole" x="${-p.slot / 2}" y="${-p.hole / 2}" width="${p.slot}" height="${p.hole}" rx="${p.hole / 2}" transform="rotate(${-(p.slot_rot || 0)})"/>`
    : `<circle class="fp-hole" r="${p.hole / 2}"/>`;
  return `<g transform="translate(${p.x} ${-p.y}) rotate(${-p.rot})"><rect class="fp-pad${one ? ' p1' : ''}" x="${-hw}" y="${-hh}" width="${p.w}" height="${p.h}" rx="${rx}"/>${hole}</g>` +
    `<text class="fp-num${one ? ' p1' : ''}" x="${p.x}" y="${-p.y + fs * 0.35}" text-anchor="middle" font-size="${fs}">${esc(p.num)}</text>`;
}
function mpFootprintSVG(d) {
  const b = mpFpPoints(d), [w0, h0] = mpSpan(b);
  const span = Math.max(w0, h0, 1), m = Math.max(0.7, span * 0.12);
  const x0 = b[0] - m, y0 = -b[3] - m, w = w0 + 2 * m, h = h0 + 2 * m + m * 0.9;       // room under the part for the scale bar
  const smallest = Math.min(...d.pads.map(p => Math.min(p.w, p.h)).filter(v => v > MP_FS_MIN));
  const fs = Math.max(0.28, Math.min(smallest * 0.62, span / 9));
  const bar = span > 30 ? 10 : span > 12 ? 5 : span > 5 ? 2 : 1;
  const by = -b[1] + m * 0.55;
  const pads = d.pads.map(p => mpPadSVG(p, p.num === d.pin1, fs)).join('');
  return `<svg class="mp-svg" viewBox="${mpNum(x0)} ${mpNum(y0)} ${mpNum(w)} ${mpNum(h)}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Footprint ${esc(d.name)}, ${d.pads.length} pads, pin 1 marked">` +
    mpFpArt(d.fab, 'fp-fab') + mpFpArt(d.courtyard, 'fp-court') + mpFpArt(d.silk, 'fp-silk') + pads +
    `<g class="fp-scale"><line x1="${b[0]}" y1="${by}" x2="${b[0] + bar}" y2="${by}"/><text x="${b[0] + bar + fs * 0.4}" y="${by + fs * 0.35}" font-size="${fs}">${bar} mm</text></g></svg>`;
}
function mpFootprintFacts(d) {
  const f = [pgPl(d.pads.length, 'pad')];
  if (d.pitch) f.push(`pitch ${d.pitch} mm`);
  f.push(`pads span ${d.pad_extent[0]} × ${d.pad_extent[1]} mm`);
  f.push(d.courtyard_size ? `courtyard ${d.courtyard_size[0]} × ${d.courtyard_size[1]} mm` : 'no courtyard in the file');
  return f.join(' · ');
}

/* ---------- the dialog ---------- */
function mpDispose() {
  if (mpView) { try { mpView.dispose(); } catch (e) { /* the canvas is already gone */ } mpView = null; }
}
function mpTabs(row, kind) {
  return `<div class="mp-tabs" role="tablist" aria-label="Models">` + libModelStates(row).map(([k, state, text]) =>
    `<button type="button" role="tab" class="mp-tab ${state}" aria-selected="${k === kind}" data-mp-tab="${k}" title="${esc(text)}">` +
    `${icon(MIC_ICON[k], 'mic-g')}${esc(MIC_NAME[k])}</button>`).join('') + '</div>';
}
function mpFrame(row, kind, body) {
  const bom = (S.bom || []).find(b => b.key === row.line) || {};
  const refs = refsLabel(row.refs || []) || row.line;
  return `<div class="mp-h"><div><h2 id="mp-title">${esc(refs)} <span class="m muted">${esc(row.mpn || bom.mpn || '')}</span></h2>` +
    `<p class="muted mp-sub">${esc(MP_TITLE[kind])} preview</p></div><button type="button" class="btn icon" data-mp-close title="Close (Esc)" aria-label="Close preview">${icon('x')}</button></div>` +
    mpTabs(row, kind) + `<div class="mp-body" data-mp-kind="${kind}">${body}</div>`;
}
function mpMissing(what, row) {
  return `<div class="mp-empty"><p>${esc(what)}</p><div class="mp-acts">${btn('Build library', {kind: 'pri', size: 'sm', act: 'libbuild', disabled: !!libBusy, title: 'Download, convert and generate the models, then compile the IntLib'})}</div></div>`;
}
function mpPins(row) {
  const l = (S.bom || []).find(b => b.key === row.line) || {};
  const [state, text] = libPinsState(row);
  const st = l.pins_status || '';
  const head = {bad: 'Needs attention', ok: 'Checked', no: 'Not checked'}[state];
  const d = l.pin_decision;
  const facts = [
    l.datasheet ? `Datasheet: <span class="m">${esc(l.datasheet)}</span>` : 'No datasheet linked',
    d ? `Decision: ${esc(PIN_BASIS[d.basis] || d.basis)}${d.ts ? ' on ' + esc(pinsWhen(d.ts)) : ''}` : '',
  ].filter(Boolean).map(t => `<li>${t}</li>`).join('');
  const acts = row.symbol ? ((l.refs || []).length ? libAction(row) : '') : '';
  const pinCount = (l.pins || l.pin_count);
  return `<div class="mp-pins ${state}"><p class="mp-pins-h"><span class="tag ${state === 'bad' ? 'bad' : state === 'ok' ? 'ok' : ''}">${esc(head)}</span> ${st ? `<span class="muted">${esc(st)}</span>` : ''}</p>` +
    `<p>${esc(text)}</p>${pinCount ? `<p class="muted">${esc(String(pinCount))} pins</p>` : ''}<ul class="mp-facts">${facts}</ul>` +
    `${acts ? `<div class="mp-acts">${acts}</div>` : ''}</div>`;
}
async function mpPaint(line, kind) {
  const row = (S.library || []).find(r => r.line === line);
  if (!mpDlg || !row) return;
  const token = ++mpToken;
  mpDispose();
  mpCur = {line, kind};
  mpDlg.innerHTML = mpFrame(row, kind, '<p class="muted mp-loading">Loading...</p>');
  const set = html => { if (token === mpToken && mpDlg) mpDlg.querySelector('.mp-body').innerHTML = html; };
  const get = k => api('/api/library/preview?' + q({line, kind: k}), undefined, {soft: true});
  try {
    if (kind === 'pins') return set(mpPins(row));
    if (kind === 'symbol') {
      if (!row.symbol) return set(mpMissing('This line has no symbol yet.', row));
      const d = await get('symbol');
      if (d.error) return set(mpMissing(d.error, row));
      return set(`<div class="mp-fig">${mpSymbolSVG(d)}</div><p class="mp-cap">${esc(d.name)} · ${pgPl(d.pins.length, 'pin')}</p>` +
        `<p class="muted mp-src">${d.source === 'kicad_sym' ? 'Drawn from the KiCad symbol file of the part.' : 'Drawn from the symbol the build made for Altium (the part has no symbol file: it comes from the netlist).'}</p>`);
    }
    if (kind === 'footprint') {
      if (!row.footprint) return set(mpMissing('This line has no footprint yet.', row));
      const d = await get('footprint');
      if (d.error) return set(mpMissing(d.error, row));
      const errs = (d.errors || []).map(t => `<p class="warn-t">${esc(t)}</p>`).join('');
      return set(`<div class="mp-fig">${mpFootprintSVG(d)}</div><p class="mp-cap">${esc(d.name)} · ${esc(mpFootprintFacts(d))}</p>` +
        `<p class="muted mp-src"><span class="mp-key p1"></span> pin 1 &nbsp; <span class="mp-key court"></span> courtyard &nbsp; <span class="mp-key silk"></span> silkscreen. ` +
        `${d.source === 'kicad_mod' ? 'Drawn from the KiCad footprint file of the part.' : 'Drawn from the footprint the build made for Altium.'}</p>${errs}`);
    }
    const info = await get('model');
    if (info.error) return set(mpMissing(info.error, row));
    if (!info.step && !info.wrl) {
      return set(mpMissing(row.symbol || row.footprint ? 'This part has no 3D model file: it uses a simple generated body in Altium.' : 'No 3D model yet.', row));
    }
    set(`<div class="mp-3d" data-mp-3d><p class="muted mp-loading">Loading the 3D model...</p></div>` +
      `<p class="muted mp-src">Drag to rotate, scroll to zoom. ${info.wrl ? 'VRML model' : 'STEP model'} ${esc(info.name)}.</p>`);
    if (token !== mpToken) return;
    const box = mpDlg.querySelector('[data-mp-3d]');
    const view = await m3dStart(box, line, info);
    mpView = view;
    try {
      await view.ready;
      if (token === mpToken) box.querySelector('.mp-loading')?.remove();
    } catch (e) {
      if (token === mpToken) { mpView = null; box.innerHTML = `<p class="warn-t mp-loading">${esc(e.message || 'The 3D model could not be shown')}</p>`; }
    }
  } catch (e) {
    set(`<p class="warn-t">${esc(e.message || 'The preview could not be shown')}</p>`);
  }
}
function mpOpen(line, kind) {
  if (!(S.library || []).some(r => r.line === line)) return;
  if (!mpDlg) {
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg mp-dlg';
    dlg.setAttribute('aria-labelledby', 'mp-title');
    dlg.addEventListener('close', () => { mpToken++; mpDispose(); dlg.remove(); if (mpDlg === dlg) mpDlg = null; });
    dlg.addEventListener('click', e => {
      if (e.target === dlg || e.target.closest('[data-mp-close]')) { dlg.close(); return; }
      const tab = e.target.closest('[data-mp-tab]');
      if (tab && mpCur) { mpPaint(mpCur.line, tab.dataset.mpTab); return; }
      if (e.target.closest('.mp-acts button')) dlg.close();            // an action of the preview (Build library, Verify, Confirm pins): the page takes over
    });
    document.body.appendChild(dlg);
    mpDlg = dlg;
    dlg.showModal();
  }
  mpPaint(line, kind);
}
onAct('lib-preview', async (el, d) => { mpOpen(d.line, d.kind); });
