/* PCB Advisor UI - Final manufacturer checks view (DFM reports, triage table). */

function checksHTML(container) {
  const checks = S.checks || [];
  // one JLCDFM report can cover the bare board and the assembly (kind 'both'): it is in either card
  const pcbChecks = checks.filter(c => ['pcb', 'both'].includes(c.kind || 'pcb'));
  const smtChecks = checks.filter(c => ['smt', 'both'].includes(c.kind));

  if (!curPcbCheckStem && pcbChecks.length) curPcbCheckStem = pcbChecks[0].stem;
  if (!curSmtCheckStem && smtChecks.length) curSmtCheckStem = smtChecks[0].stem;
  if (curPcbCheckStem && !pcbChecks.some(c => c.stem === curPcbCheckStem)) {
    curPcbCheckStem = pcbChecks.length ? pcbChecks[0].stem : null;
  }
  if (curSmtCheckStem && !smtChecks.some(c => c.stem === curSmtCheckStem)) {
    curSmtCheckStem = smtChecks.length ? smtChecks[0].stem : null;
  }
  if (!curCheckStem && checks.length) {
    curCheckStem = curPcbCheckStem || curSmtCheckStem || checks[0].stem;
  }

  [curPcbCheckStem, curSmtCheckStem].forEach(stem => {
    if (!stem) return;
    if (!triageMap[stem] && !triageLoading[stem]) {
      triageLoading[stem] = true;
      api('/api/checks/triage?stem=' + encodeURIComponent(stem)).then(r => {
        triageMap[stem] = r.triage || [];
        triageLoading[stem] = false;
        renderCenter(true);
      }).catch(() => { triageLoading[stem] = false; });
    }
    if (!indexMap[stem] && !indexLoading[stem]) {
      indexLoading[stem] = true;
      api('/api/checks/index?stem=' + encodeURIComponent(stem)).then(r => {
        indexMap[stem] = r;
        indexLoading[stem] = false;
        renderCenter(true);
      }).catch(() => { indexLoading[stem] = false; });
    }
  });

  let statusKind = 'warn';
  let statusText = '';
  if (!pcbChecks.length && !smtChecks.length) {
    statusText = 'Missing both PCB DFM (bare board) and SMT DFM (assembly) reports before ordering assembly.';
  } else if (!pcbChecks.length) {
    statusText = 'Missing PCB DFM (bare board) report before ordering assembly.';
  } else if (!smtChecks.length) {
    statusText = 'Missing SMT DFM (assembly) report before ordering assembly.';
  } else {
    statusKind = 'ok';
    statusText = 'Both PCB DFM and SMT DFM reports uploaded — all manufacturer checks ready before ordering assembly.';
  }

  function renderCard(kind, title, desc, list, activeStem) {
    const curCheck = list.find(c => c.stem === activeStem);
    const triageRows = (activeStem && triageMap[activeStem]) ? triageMap[activeStem] : [];
    const idxData = (activeStem && indexMap[activeStem]) ? indexMap[activeStem] : null;
    const slices = (idxData && idxData.slices) || (curCheck ? (curCheck.slice_files || curCheck.slices || []) : []);

    return `<div class="card dfm-card" style="padding:16px;display:flex;flex-direction:column;gap:14px;min-width:0">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h3 style="margin:0;font-size:15px;font-weight:700">${esc(title)}</h3>
          <p style="margin:3px 0 0;color:var(--dim);font-size:12.5px">${esc(desc)}</p>
        </div>
        ${list.length ? `
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            ${curCheck && curCheck.kind === 'both' ? '<span class="tag plan" title="One JLCDFM report that covers the bare board and the assembly: it is listed in both cards">PCB + SMT in one report</span>' : ''}
            <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600">
              Report:
              <select class="check-stem-select" data-kind="${kind}" style="font-size:12px;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel2)">
                ${list.map(c => `<option value="${esc(c.stem)}" ${c.stem === activeStem ? 'selected' : ''}>${esc(c.stem)} (${c.slice_count || (c.slices && c.slices.length) || 0} slices)</option>`).join('')}
              </select>
            </label>
            <button class="btn pri" data-act="upload-dfm" data-kind="${kind}">Upload report (PDF)</button>
            ${activeStem ? `<button class="btn" data-act="add-triage-row" data-kind="${kind}" data-stem="${esc(activeStem)}">+ Add check row</button>` : ''}
          </div>` : ''}
      </div>
      ${!list.length ? `
        <div class="howto" style="margin:0">
          <b>No ${kind.toUpperCase()} reports ingested yet</b>
          <p style="margin:6px 0;font-size:12.5px;color:var(--dim)">Upload a ${kind === 'smt' ? 'SMT assembly' : 'PCB bare-board'} report PDF downloaded from dfm.jlcdfm.com.</p>
          <button class="btn pri" data-act="upload-dfm" data-kind="${kind}" style="margin-top:6px">Upload ${kind === 'smt' ? 'SMT' : 'PCB'} report (PDF)</button>
        </div>` : `
        <div class="sgroup" style="margin:0">
          <div class="sgh" style="margin-bottom:8px">
            <h4 style="margin:0;font-size:13px;font-weight:600">Triage table (${triageRows.length} checks)</h4>
            <p style="margin:2px 0 0;font-size:11.5px;color:var(--dim)">Report: <span class="m">${esc(activeStem)}</span> · All changes save automatically</p>
          </div>
          ${triageRows.length ? `
            <div class="tblwrap"><table class="triage-tbl">
              <thead>
                <tr>
                  <th>Section</th><th>Check</th><th>Worst</th><th>Level</th>
                  <th style="text-align:right">Danger</th><th style="text-align:right">Warning</th><th style="text-align:right">Good</th>
                  <th>Layer</th><th>Verdict</th><th>Fix</th><th>Evidence</th><th>Discuss</th><th></th>
                </tr>
              </thead>
              <tbody>
                ${triageRows.map((r, i) => `
                  <tr>
                    <td><input data-triage-field="section" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.section || '')}" placeholder="Section" style="min-width:110px"></td>
                    <td><input data-triage-field="check" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.check || '')}" placeholder="Check name" style="min-width:130px"></td>
                    <td><input data-triage-field="worst" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.worst || '')}" placeholder="Worst" style="width:70px"></td>
                    <td>
                      <select data-triage-field="level" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" style="width:85px">
                        ${['Danger', 'Warning', 'Good', 'Info'].map(lvl => `<option value="${lvl}" ${(r.level || '').toLowerCase() === lvl.toLowerCase() ? 'selected' : ''}>${lvl}</option>`).join('')}
                      </select>
                    </td>
                    <td><input type="number" data-triage-field="danger" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${r.danger ?? 0}" style="width:48px;text-align:right"></td>
                    <td><input type="number" data-triage-field="warning" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${r.warning ?? 0}" style="width:48px;text-align:right"></td>
                    <td><input type="number" data-triage-field="good" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${r.good ?? 0}" style="width:48px;text-align:right"></td>
                    <td><input data-triage-field="layer" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.layer || '')}" placeholder="Layer" style="width:80px"></td>
                    <td>
                      <select data-triage-field="verdict" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" style="width:105px;font-weight:600;color:${r.verdict === 'real' ? 'var(--bad)' : r.verdict === 'model' || r.verdict === 'by design' ? 'var(--ok)' : 'var(--warn)'}">
                        ${['unknown', 'real', 'model', 'by design'].map(v => `<option value="${v}" ${r.verdict === v ? 'selected' : ''}>${v}</option>`).join('')}
                      </select>
                    </td>
                    <td><input data-triage-field="fix" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.fix || '')}" placeholder="Suggested fix" style="min-width:140px"></td>
                    <td><input data-triage-field="evidence" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" value="${esc(r.evidence || '')}" placeholder="Slice / crop / ref" style="min-width:120px"></td>
                    <td><button class="btn" data-act="discuss-dfm" data-stem="${esc(activeStem)}" data-check="${esc(r.check || ('check-' + (i + 1)))}">Discuss</button></td>
                    <td><button class="x" data-act="del-triage-row" data-stem="${esc(activeStem)}" data-kind="${kind}" data-idx="${i}" title="Delete check">×</button></td>
                  </tr>
                `).join('')}
              </tbody>
            </table></div>` : `
            <div class="dnote">Triage table is empty. Click "+ Add check row" to begin triaging findings.</div>`}
        </div>
        <div class="sgroup" style="margin-top:14px">
          <div class="sgh" style="margin-bottom:8px">
            <h4 style="margin:0;font-size:13px;font-weight:600">Report slices (${slices.length})</h4>
            <p style="margin:2px 0 0;font-size:11.5px;color:var(--dim)">Extracted slices from <span class="m">${esc(activeStem)}.pdf</span> · Click to view in full size</p>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;max-height:480px;overflow-y:auto;padding:2px">
            ${slices.map((s, idx) => {
              const sliceFile = (typeof s === 'string' ? s : (s && s.file) ? s.file : String(s));
              return `
                <div class="card" style="padding:6px;display:flex;flex-direction:column;gap:5px;background:var(--panel2)">
                  <div style="font-family:var(--f-mono);font-size:11.5px;font-weight:600;display:flex;justify-content:space-between">
                    <span>Slice ${idx + 1}</span>
                    <span style="color:var(--dim);font-size:10.5px">${esc(sliceFile)}</span>
                  </div>
                  <div style="height:170px;overflow:hidden;border:1px solid var(--line2);border-radius:6px;cursor:pointer;background:var(--panel);display:flex;align-items:flex-start;justify-content:center" data-act="view-slice" data-stem="${esc(activeStem)}" data-slice="${esc(sliceFile)}">
                    <img src="/api/checks/slice?stem=${encodeURIComponent(activeStem)}&slice=${encodeURIComponent(sliceFile)}&${q()}" alt="Slice ${idx + 1}" style="width:100%;height:auto;display:block" loading="lazy">
                  </div>
                  <div style="display:flex;gap:5px">
                    <button class="btn" style="flex:1;font-size:12px;padding:3px 6px" data-act="view-slice" data-stem="${esc(activeStem)}" data-slice="${esc(sliceFile)}">View</button>
                    <a class="lnk" href="/api/checks/slice?stem=${encodeURIComponent(activeStem)}&slice=${encodeURIComponent(sliceFile)}&${q()}" target="_blank" rel="noopener" style="padding:3px 6px;font-size:11px;border:1px solid var(--line);border-radius:6px">Open</a>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>`}
    </div>`;
  }

  const statusBg = statusKind === 'ok' ? 'var(--ok-soft)' : 'var(--warn-soft)';
  const statusBorder = statusKind === 'ok' ? '#a3d9b8' : '#e3c98a';
  const statusColor = statusKind === 'ok' ? 'var(--ok)' : 'var(--warn)';
  const statusDot = statusKind === 'ok' ? 'var(--ok)' : 'var(--warn)';

  return `<div class="vhead">
    <div>
      <h2>Final manufacturer checks</h2>
      <p>Manufacturer fabrication (bare board) and assembly checks from dfm.jlcdfm.com. Inspect report slices and triage findings.</p>
    </div>
  </div>
  <div class="dfm-status" style="margin:12px 0 16px;padding:8px 12px;border-radius:8px;font-size:13px;display:flex;align-items:center;gap:8px;background:${statusBg};border:1px solid ${statusBorder};color:${statusColor}">
    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${statusDot};flex:none"></span>
    <span>${esc(statusText)}</span>
  </div>
  <div class="dfm-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:16px;align-items:start">
    ${renderCard('pcb', 'PCB DFM (bare board)', 'Bare board fabrication checks: trace/space, annular ring, drill, solder mask, silkscreen (from dfm.jlcdfm.com).', pcbChecks, curPcbCheckStem)}
    ${renderCard('smt', 'SMT DFM (assembly)', 'Assembly checks: pad/footprint vs part, component spacing, polarity/pin 1, fiducials, tall parts near edges, stencil/paste, BOM/CPL mismatch, rotation (from dfm.jlcdfm.com).', smtChecks, curSmtCheckStem)}
  </div>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('upload-dfm', async (el, d, e) => {
  uploadDfmKind = el.dataset.kind || d.kind || 'pcb';
  $('#dfmpick').click();
  return;
});
onAct('view-slice', async (el, d, e) => {
  openViewerSlice(d.stem, d.slice); return;
});
onAct('discuss-dfm', async (el, d, e) => {
  openPart('dfm:' + d.stem + ':' + d.check); return;
});
onAct('add-triage-row', async (el, d, e) => {
  const stem = d.stem || (d.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
  if (!stem) return;
  const kind = d.kind || 'pcb';
  const defaultSec = kind === 'smt' ? 'SMT DFM>Component assembly analysis' : 'PCB DFM>Routing layer analysis';
  triageMap[stem] = triageMap[stem] || [];
  triageMap[stem].push({section: defaultSec, check: 'Check ' + (triageMap[stem].length + 1), worst: '—', level: 'Warning', danger: 0, warning: 1, good: 0, layer: kind === 'smt' ? 'component_+_top' : 'Top', verdict: 'unknown', fix: '', evidence: ''});
  await api('/api/checks/triage', {stem: stem, rows: triageMap[stem]});
  renderCenter(true);
  toast('Row added');
  return;
});
onAct('del-triage-row', async (el, d, e) => {
  const stem = d.stem || (d.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
  const idx = parseInt(d.idx, 10);
  if (!stem || isNaN(idx) || !triageMap[stem]) return;
  triageMap[stem].splice(idx, 1);
  await api('/api/checks/triage', {stem: stem, rows: triageMap[stem]});
  renderCenter(true);
  toast('Row removed');
  return;
});
onChange(t => t.id === 'dfmpick', async e => {
  const f = e.target.files[0]; if (!f) return;
  const kind = uploadDfmKind || 'pcb';
  toast(`Uploading and slicing ${kind.toUpperCase()} DFM report…`);
  const buf = new Uint8Array(await f.arrayBuffer()); let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  try {
    const r = await api('/api/checks/upload', {name: f.name, data_b64: btoa(bin), kind: kind});
    if (kind === 'smt') {
      curSmtCheckStem = r.stem;
    } else {
      curPcbCheckStem = r.stem;
    }
    curCheckStem = r.stem;
    await refresh(true);
    toast(`Report uploaded: ${r.slices.length} slices extracted`);
  } catch (err) { /* toasted */ }
  e.target.value = ''; return;
});
onChange(t => t.classList.contains('check-stem-select') || t.id === 'check-stem-select', async e => {
  const kind = e.target.dataset.kind || 'pcb';
  if (kind === 'smt') curSmtCheckStem = e.target.value;
  else curPcbCheckStem = e.target.value;
  curCheckStem = e.target.value;
  renderCenter(true);
  return;
});
onChange(t => t.closest('[data-triage-field]'), async e => {
  const trg = e.target.closest('[data-triage-field]');
  if (trg) {
    const stem = trg.dataset.stem || (trg.dataset.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curCheckStem;
    if (stem) {
      const idx = parseInt(trg.dataset.idx, 10);
      const field = trg.dataset.triageField;
      if (!isNaN(idx) && triageMap[stem] && triageMap[stem][idx]) {
        let val = trg.value;
        if (['danger', 'warning', 'good'].includes(field)) val = parseInt(val, 10) || 0;
        triageMap[stem][idx][field] = val;
        try {
          await api('/api/checks/triage', {stem: stem, rows: triageMap[stem]});
          toast('Triage saved');
        } catch (err) { /* toasted */ }
      }
      return;
    }
  }
});
