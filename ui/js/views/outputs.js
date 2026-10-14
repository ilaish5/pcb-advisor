/* PCB Advisor UI - Altium outputs view. */

function outputsHTML(container) {
  const exports = S.exports || [];
  return `<div class="vhead">
    <div>
      <h2>Altium outputs</h2>
      <p>Fabrication and production files. Linked project directory is read-only; exports are generated in <span class="path">projects/${esc(PROJECT)}/exports/</span>. Copy them to your Altium outputs folder.</p>
    </div>
    <div class="vacts">
      <button class="btn pri" data-act="gen-outjob">Generate OutJob</button>
      <button class="btn" data-act="export" data-fmt="jlc">Export JLC BOM</button>
      <button class="btn" data-act="export" data-fmt="pcbway">Export Generic BOM</button>
      <button class="btn" data-act="gen-cpl">Export CPL</button>
    </div>
  </div>
  ${outjobBanner ? `<div class="howto"><b>OutJob ready</b> <button class="x" data-act="close-outjob-banner" aria-label="Close">×</button>
    <p style="margin:4px 0">${esc(outjobBanner.instruction || '')}</p>
    <code>${esc(outjobBanner.path || '')}</code>
    <div style="margin-top:6px"><a class="btn pri" href="/api/export/${encodeURIComponent((outjobBanner.path || '').split(/[\\/]/).pop())}?${q()}" download>Download OutJob</a></div>
  </div>` : ''}
  <div class="howto" style="margin-bottom:16px">
    <b>Fabrication workflow</b>
    <p style="margin:4px 0 0">1. Generate the ready OutJob file containing Gerber RS-274X, NC Drill, JLC BOM, Pick and Place CPL, and Schematic PDF.<br>
    2. Download the OutJob or copy it from <span class="path">projects/${esc(PROJECT)}/exports/</span> into your Altium project folder.<br>
    3. Export JLC BOM and Pick and Place CPL (CSV) ready for assembly ordering.</p>
  </div>
  <div class="sgroup">
    <div class="sgh">
      <h3>Generated export files (${exports.length})</h3>
      <p>Stored in <span class="path">projects/${esc(PROJECT)}/exports/</span></p>
    </div>
    ${exports.length ? `
      <div class="tblwrap"><table class="srct">
        <thead><tr><th>File name</th><th style="text-align:right">Size</th><th>Actions</th></tr></thead>
        <tbody>
          ${exports.map(f => `
            <tr>
              <td class="fname"><b>${esc(f.name)}</b></td>
              <td class="n">${num(f.size)} B</td>
              <td>
                <a class="lnk" href="/api/export/${encodeURIComponent(f.name)}?${q()}" download style="display:inline-block;padding:2px 8px;border:1px solid var(--line);border-radius:5px">Download</a>
                <button class="btn" data-act="view-export" data-name="${esc(f.name)}" style="margin-left:6px">View</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table></div>` : `
      <div class="dnote">No files in exports yet. Click Generate OutJob, Export JLC BOM, or Export CPL above.</div>`}
  </div>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('gen-outjob', async (el, d, e) => {
  toast('Generating Altium OutJob…');
  outjobBanner = await api('/api/outjob/generate', {});
  await refresh(true);
  toast('OutJob generated in exports/');
  return;
});
onAct('close-outjob-banner', async (el, d, e) => {
  outjobBanner = null; renderCenter(true); return;
});
onAct('gen-cpl', async (el, d, e) => {
  toast('Exporting CPL…');
  const r = await api('/api/cpl/export', {});
  await refresh(true);
  toast('Exported ' + r.count + ' parts to CPL');
  return;
});
onAct('view-export', async (el, d, e) => {
  openViewerExport(d.name); return;
});
