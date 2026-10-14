/* PCB Advisor UI - Library, Sources, Skills and Settings pages. */

async function loadAltium() {
  try {
    ALTIUM_DATA = await api('/api/altium', undefined, {soft: true});
    if (page === 'settings') renderCenter(true);
  } catch (e) { /* error toasted */ }
}

function libHTML(container) {
  const rows = S.library || [];
  const mk = v => v ? '<span class="y">✓</span>' : '<span class="nn">✗</span>';
  return `${guidanceBarHTML('library')}
    <div class="vhead"><div><h2><span class="m">${esc(PROJECT)}.IntLib</span></h2><p>Only parts that aren't in Altium's default libraries. Each has a symbol, a footprint and a 3D model, and shows whether it was checked against its datasheet and accepted by you.</p></div>
    <div class="vacts"><button class="btn pri" data-act="libexport">Export for Altium</button></div></div>
    ${libExport ? `<div class="howto"><b>${esc(libExport.file)}</b>: ${libExport.parts} parts. <a class="lnk" href="/api/export/${encodeURIComponent(libExport.file)}?${q()}">Download</a> <button class="x" data-act="closecard" aria-label="Close">×</button>
      ${libExport.warnings.length ? `<div class="warnbox"><b>Still unverified</b> (${libExport.warnings.length}):<ul>${libExport.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul></div>` : '<div>Every part is verified and accepted.</div>'}
      <div class="dnote">This writes the manifest and the part files. Compiling the IntLib itself needs Altium on Windows.</div></div>` : ''}
    ${rows.length ? `<div class="tblwrap"><table class="libt"><thead><tr><th>Part</th><th>MPN</th><th style="text-align:center">Symbol</th><th style="text-align:center">Footprint</th><th style="text-align:center">3D</th><th>Model from</th><th>Status</th><th></th></tr></thead><tbody>
    ${rows.map(r => `<tr data-key="${esc(r.line)}" class="${sel === r.line ? 'sel' : ''}"><td class="refs">${esc((r.refs || []).join(', '))}</td>
      <td class="m">${esc(r.mpn)}</td><td class="c">${mk(r.symbol)}</td><td class="c">${mk(r.footprint)}</td><td class="c">${r.step ? '<span class="y">STEP</span>' : '<span class="q">Simple body</span>'}</td>
      <td>${esc(r.model_source || '—')}${r.issues ? `<div class="issue">${esc(r.issues)}</div>` : ''}</td><td><span class="lib ${esc(r.status)}">${esc(LIBTXT[r.status])}</span></td>
      <td><button class="btn" data-chat="${esc(r.line)}">Discuss</button>${r.verify === 'pass' && !r.accepted ? ` <button class="btn pri" data-accept="${esc(r.line)}">Accept</button>` : ''}${r.verify !== 'pass' && r.symbol ? ` <button class="btn" data-verify="${esc(r.line)}">Verify</button>` : ''}</td></tr>`).join('')}
    </tbody></table></div>` : '<div class="dnote">No non-standard parts yet.</div>'}
    <div class="howto"><b>Install in Altium</b>
      <code>Components panel ▸ ☰ ▸ File-based Libraries Preferences ▸ Installed ▸ Install…</code>
      ${srcByName('AD20 Essentials Course Exercises.pdf') ? chip('AD20 Essentials Course Exercises.pdf', 'Module 29, Integrated Library') : ''}</div>`;
}
function srcTable(list) {
  if (!list.length) return '<div class="dnote">Nothing here yet.</div>';
  return `<div class="tblwrap"><table class="srct"><thead><tr><th>File</th><th>Type</th><th style="text-align:right">Size</th><th>Origin</th><th>sha256</th><th>Text</th><th>Used for</th></tr></thead><tbody>
    ${list.map(s => `<tr id="src-${esc(s.name).replace(/[^\w-]/g, '_')}" class="${hitSrc === s.name ? 'hit flash' : ''}"><td class="fname">${s.present ? `<button type="button" class="fname-btn" data-src="${esc(s.name)}">${esc(s.name)}</button> <a href="/api/source/${encodeURIComponent(s.name)}?${q()}" target="_blank" rel="noopener" class="ext-lnk" title="Open in new tab" aria-label="Open in new tab">↗</a>` : esc(s.name)}${s.present ? '' : ' <span class="tag plan">not here</span>'}</td><td><span class="kind">${esc(s.kind)}</span></td><td class="n">${esc(s.size)}</td>
      <td class="org">${esc(s.origin)}</td><td class="hash">${esc(s.sha256)}</td><td>${s.text ? '<span class="y">✓</span>' : '—'}</td><td class="cite">${esc(s.used_for)}</td></tr>`).join('')}
    </tbody></table></div>`;
}
function sourcesHTML(container) {
  const sh = (S.sources || []).filter(s => s.scope === 'shared'), pr = (S.sources || []).filter(s => s.scope === 'project');
  return `${guidanceBarHTML('sources')}
    <div class="vhead"><div><h2>Sources</h2><p>Everything the agent may cite. Each file sits next to a <span class="m">.json</span> sidecar (url, sha256, size) and its extracted <span class="m">.txt</span>, so a quote can be checked word for word.</p></div>
    <div class="vacts"><button class="btn" data-act="addurl">Add from URL</button><button class="btn pri" data-act="upload">Upload file</button></div></div>
    <div class="sgroup"><div class="sgh"><h3>Shared library</h3><p>Available in every project · <span class="path">shared/datasheets/</span></p></div>${srcTable(sh)}</div>
    <div class="sgroup"><div class="sgh"><h3>Project sources</h3><p>Only ${esc(S.title)} · <span class="path">projects/${esc(PROJECT)}/sources/</span></p></div>${srcTable(pr)}</div>
    ${(S.sources || []).some(s => !s.present) ? `<div class="sidecar">Files marked "not here" are listed by their sidecar but are not on this machine. Run <span class="m">python scripts/sources.py restore</span> to fetch them.</div>` : ''}`;
}
function skillsHTML(container) {
  const sk = SKILLS || [];
  return `${guidanceBarHTML('skills')}
    <div class="vhead"><div><h2>Skills</h2><p>What the agent can do. You don't call these directly: ask in the chat and the agent picks the right one. The BOM page buttons run the same scripts.</p></div></div>
    <div class="skills">${sk.map(s => `<div class="skill"><span class="t">${esc(s.name)}<span class="tag ${s.available ? 'ok' : 'plan'}">${s.available ? 'Available' : 'Not built yet'}</span></span><span class="d">${esc(s.what)}</span>${s.script ? `<span class="u">scripts/skills/${esc(s.script)}</span>` : ''}</div>`).join('')}</div>`;
}
function settingsHTML(container) {
  const c = CONFIG; if (!c) return '<div class="dnote">Loading…</div>';
  const engines = c.engines || [];
  const a = ALTIUM_DATA;
  let altBlock = '<div class="form" style="margin-top:18px"><div class="dnote">Loading Altium settings…</div></div>';
  if (a) {
    const installs = a.installs || [];
    const installsHTML = installs.length
      ? `<div style="display:grid;gap:4px">` +
        installs.map(i => `<div><span class="m">${esc(i.version || 'Version unknown')}</span>: <span class="path">${esc(i.path)}</span>${i.exe ? ' <small style="color:var(--ok)">✓ X2.EXE</small>' : ''}</div>`).join('') +
        `</div>`
      : `<div class="dnote">No Altium Designer install found in the registry</div>`;

    const detectedPath = (a.active_install && a.active_install.path) || (installs[0] && installs[0].path) || '';
    const currentPath = (CONFIG && CONFIG.altium && CONFIG.altium.install_path) || a.install_path || '';

    let linkedHTML = '';
    if (a.linked) {
      const l = a.linked;
      const sum = l.summary || {};
      const pcbs = sum.pcbs || [];
      const prjDir = l.project_file ? l.project_file.replace(/[\\/][^\\/]+$/, '') : '';
      const prjSep = (l.project_file && l.project_file.includes('\\')) ? '\\' : '/';
      const resolvePcb = rel => (rel.includes(':') || rel.startsWith('/') || !prjDir) ? rel : (prjDir + prjSep + rel.replace(/[\\/]/g, prjSep));

      let pcbPicker = '';
      if (pcbs.length > 1) {
        const selectedPcbRel = pcbs.find(p => (l.pcb_file && (l.pcb_file.endsWith(p) || l.pcb_file.toLowerCase().includes(p.toLowerCase())))) || pcbs[0];
        const selectedPcbPath = l.pcb_file || resolvePcb(selectedPcbRel);
        pcbPicker = `<label>PcbDoc<div style="display:flex;gap:8px;align-items:center"><select id="altium-pcb-select" style="flex:1">` +
          pcbs.map(p => {
            const isSel = (l.pcb_file && (l.pcb_file.endsWith(p) || l.pcb_file.toLowerCase().includes(p.toLowerCase())));
            return `<option value="${esc(p)}" ${isSel ? 'selected' : ''}>${esc(p)}</option>`;
          }).join('') +
          `</select><button type="button" class="btn" data-altium-path="${esc(selectedPcbPath)}">View</button></div></label>`;
      } else if (pcbs.length === 1) {
        const pcbPath = l.pcb_file || resolvePcb(pcbs[0]);
        pcbPicker = `<div>PcbDoc: <button type="button" class="btn" data-altium-path="${esc(pcbPath)}"><span class="m">${esc(pcbs[0])}</span></button></div>`;
      } else {
        pcbPicker = `<div>PcbDoc: ${l.pcb_file ? `<button type="button" class="btn" data-altium-path="${esc(l.pcb_file)}"><span class="m">${esc(l.pcb_file.split(/[\\/]/).pop())}</span></button>` : '<span class="m">None</span>'}</div>`;
      }

      const sheetsList = (l.sheets && l.sheets.length)
        ? l.sheets
        : ((sum.sheets || []).map(s => resolvePcb(s)));
      const sheetsHTML = sheetsList.length
        ? `<div style="display:grid;gap:4px">` +
          `<div style="font-size:12px;color:var(--dim)">Sheets (${sheetsList.length}):</div>` +
          `<div style="display:flex;flex-wrap:wrap;gap:6px">` +
          sheetsList.map(sh => {
            const shName = sh.split(/[\\/]/).pop();
            return `<button type="button" class="btn" data-altium-path="${esc(sh)}"><span class="m">${esc(shName)}</span></button>`;
          }).join('') +
          `</div></div>`
        : '';

      const missingHTML = (sum.missing && sum.missing.length)
        ? `<div class="warnbox"><b>Missing documents (${sum.missing.length}):</b><ul>${sum.missing.map(m => `<li>${esc(m)}</li>`).join('')}</ul></div>`
        : '';

      linkedHTML = `
        <div class="card" style="padding:10px 14px;display:grid;gap:8px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <b>Linked project: ${esc(sum.name || l.project_file.split(/[\\/]/).pop())}</b>
            <button class="btn" data-act="altium-unlink">Unlink</button>
          </div>
          <div>Project file: <button type="button" class="btn" data-altium-path="${esc(l.project_file)}"><span class="m">${esc(l.project_file)}</span></button>${l.exists ? '' : ' <span class="tag plan">file missing</span>'}</div>
          ${pcbPicker}
          <label>Output folder<input id="altium-outdir" value="${esc(l.outputs_dir || '')}" placeholder="Outputs folder path"></label>
          ${sheetsHTML}
          ${missingHTML}
        </div>`;
    } else {
      linkedHTML = `<div class="dnote">No Altium project linked</div>`;
    }

    const recent = a.recent || [];
    const recentHTML = recent.length
      ? `<div style="display:grid;gap:6px">` +
        recent.map(r => `
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:3px 0;${r.exists ? '' : 'opacity:0.5'}">
            <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0">
              <b>${esc(r.name)}</b> <span class="path">${esc(r.path)}</span>${r.exists ? '' : ' <small>(not found)</small>'}
            </div>
            <button class="btn" data-act="altium-link" data-path="${esc(r.path)}">Link</button>
          </div>`).join('') +
        `</div>`
      : '<div class="dnote">No recent projects found in the registry</div>';

    altBlock = `
      <div class="form" style="margin-top:18px">
        <b>Altium Designer</b>
        <label>Detected installs${installsHTML}</label>
        <label>Altium path <small>(blank = newest detected)</small>
          <div style="display:flex;gap:8px">
            <input id="set-altium-path" value="${esc(currentPath)}" placeholder="${esc(detectedPath)}" style="flex:1">
            <button class="btn" data-act="saveset">Save path</button>
          </div>
        </label>
        <div>${linkedHTML}</div>
        <label>Recent projects
          ${recentHTML}
          <div style="display:flex;gap:8px;margin-top:6px">
            <input id="altium-custom-path" placeholder="Path to .PrjPcb or project folder" style="flex:1">
            <button class="btn pri" data-act="altium-link-custom">Link</button>
          </div>
        </label>
      </div>`;
  }

  return `${guidanceBarHTML('settings')}
    <div class="vhead"><div><h2>Settings</h2><p>Saved to <span class="m">${esc(c.config_file)}</span>.</p></div></div>
    <div class="form">
      <label>Engine<select id="set-provider">${engines.map(e => `<option value="${esc(e.id)}" ${e.active ? 'selected' : ''} ${e.status !== 'implemented' ? 'disabled' : ''}>${esc(e.id)}${e.available ? '' : ' (unavailable: ' + esc(e.reason || '') + ')'}</option>`).join('')}</select></label>
      <label>Model <small>(blank = the engine's default)</small><input id="set-model" value="${esc(c.agent.model || '')}"></label>
      <label>Language<select id="set-language">${['auto', 'en', 'he'].map(l => `<option ${c.user.language === l ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label>Your name<input id="set-name" value="${esc(c.user.name || '')}"></label>
      <div><button class="btn pri" data-act="saveset">Save</button></div>
    </div>
    <div class="form" style="margin-top:18px"><b>Layout</b>
      <div style="display:flex;align-items:center;gap:10px">
        <button type="button" class="btn" data-act="reset-layout">Reset layout</button>
        <small style="color:var(--dim)">Restores default panel widths.</small>
      </div>
    </div>
    ${altBlock}
    <div class="form" style="margin-top:18px"><b>This conversation's memory</b>
      <textarea id="mem" rows="9" dir="auto">${esc(S.memory)}</textarea>
      <div><button class="btn" data-act="savemem">Save memory</button> <button class="btn" data-act="rewritemem">Rewrite now</button></div></div>
    <p class="foot">Project folder: <span class="m">${esc(c.home)}</span></p>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('libexport', async (el, d, e) => {
  libExport = await api('/api/library/export', {}); render(true); return;
});
onAct('upload', async (el, d, e) => {
  $('#filepick').click(); return;
});
onAct('addurl', async (el, d, e) => {
  { const u = prompt('Address of the document (a PDF or text file)'); if (!u) return; toast('Fetching…');
    const r = await api('/api/fetch_source', {url: u}); if (r.error) { toast(r.error); return; } setState(r); render(true); toast('Added'); } return;
});
onAct('altium-link', async (el, d, e) => {
  const p = el.dataset.path; if (!p) return;
  ALTIUM_DATA = await api('/api/altium/link', {path: p}); render(true); toast('Linked Altium project'); return;
});
onAct('altium-link-custom', async (el, d, e) => {
  const inp = $('#altium-custom-path'); const p = inp ? inp.value.trim() : '';
  if (!p) { toast('Path required'); return; }
  ALTIUM_DATA = await api('/api/altium/link', {path: p}); render(true); toast('Linked Altium project'); return;
});
onAct('altium-unlink', async (el, d, e) => {
  ALTIUM_DATA = await api('/api/altium/unlink', {}); render(true); toast('Unlinked Altium project'); return;
});
onAct('saveset', async (el, d, e) => {
  const set = {'agent.provider': $('#set-provider').value, 'agent.model': $('#set-model').value, 'user.language': $('#set-language').value, 'user.name': $('#set-name').value};
  const ap = $('#set-altium-path');
  if (ap) set['altium.install_path'] = ap.value.trim();
  const r = await api('/api/config', {set}); CONFIG = r.config; await loadAltium(); render(true); toast('Saved'); return;
});
onAct('savemem', async (el, d, e) => {
  await api('/api/memory', {text: $('#mem').value}); await refresh(true); toast('Memory saved'); return;
});
onAct('rewritemem', async (el, d, e) => {
  toast('Rewriting…'); await api('/api/memory', {}); await refresh(true); return;
});
onChange(t => t.id === 'altium-pcb-select' || t.id === 'altium-outdir', async e => {
  if (!ALTIUM_DATA || !ALTIUM_DATA.linked || !ALTIUM_DATA.linked.project_file) return;
  const pcbEl = $('#altium-pcb-select');
  const pcb = pcbEl ? pcbEl.value : (ALTIUM_DATA.linked.pcb_file || undefined);
  const outEl = $('#altium-outdir');
  const out = outEl ? outEl.value.trim() : (ALTIUM_DATA.linked.outputs_dir || undefined);
  try {
    ALTIUM_DATA = await api('/api/altium/link', {path: ALTIUM_DATA.linked.project_file, pcb_file: pcb, outputs_dir: out});
    render(true);
    toast('Project link updated');
  } catch (err) { /* toasted */ }
  return;
});
onChange(t => t.id === 'filepick', async e => {
  const f = e.target.files[0]; if (!f) return;
  const buf = new Uint8Array(await f.arrayBuffer()); let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  try { setState(await api('/api/upload', {name: f.name, data_b64: btoa(bin)})); render(true); toast('Uploaded ' + f.name); } catch (err) { /* toasted */ }
  e.target.value = ''; return;
});
