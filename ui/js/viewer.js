/* PCB Advisor UI - file viewer drawer and file tabs (sources, Altium files, DFM slices, exports). */

async function renderFileTabContent(tabObj, container) {
  const name = tabObj.name || tabObj.path || 'file';
  const path = tabObj.path || name;
  const ext = (name.includes('.') ? '.' + name.split('.').pop() : '').toLowerCase();
  const fType = tabObj.fileType || 'txt';
  const rawBadge = (FILE_BADGES[fType] || fType || 'TXT').toUpperCase();
  const badgeText = ['PDF', 'SCH', 'PCB', 'IMG', 'TXT'].includes(rawBadge) ? rawBadge : (rawBadge === 'PNG' || rawBadge === 'JPG' ? 'IMG' : 'TXT');
  const badgeClass = badgeText.toLowerCase();

  const qDownload = q({ download: '1' });
  const downloadUrl = (tabObj.stem && tabObj.slice)
    ? `/api/checks/slice?stem=${encodeURIComponent(tabObj.stem)}&slice=${encodeURIComponent(tabObj.slice)}&${qDownload}`
    : `/api/source/${encodeURIComponent(name)}?${qDownload}`;
  const rawUrl = (tabObj.stem && tabObj.slice)
    ? `/api/checks/slice?stem=${encodeURIComponent(tabObj.stem)}&slice=${encodeURIComponent(tabObj.slice)}&${q()}`
    : `/api/source/${encodeURIComponent(name)}?${q()}`;

  if (fType === 'dfm' || tabObj.slice) {
    const sliceName = tabObj.slice || name;
    const stem = tabObj.stem || '';
    container.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge ${badgeClass}">${badgeText}</span><span title="${esc(sliceName)}">${esc(stem ? stem + ' / ' : '')}${esc(sliceName)}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(sliceName)}">Ask about this file</button>
          <a class="lnk" href="${esc(rawUrl)}" target="_blank" rel="noopener">Open in tab</a>
        </div>
      </div>
      <div class="viewer-b" style="align-items:center;justify-content:flex-start;background:var(--panel2);overflow:auto">
        <img src="${esc(rawUrl)}" alt="${esc(sliceName)}" style="max-width:100%;height:auto;border-radius:4px;box-shadow:var(--shadow)">
      </div>`;
    return;
  }

  if (fType === 'pdf' || ext === '.pdf') {
    let iframeUrl = rawUrl;
    const m = (tabObj.where || '').match(/\b(?:p\.?|page)\s*(\d+)\b/i);
    if (m) iframeUrl += '#page=' + m[1];
    container.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge ${badgeClass}">${badgeText}</span><span title="${esc(name)}">${esc(name)}${m ? ` (p. ${m[1]})` : ''}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
          <a class="lnk" href="${esc(downloadUrl)}" download>Download</a>
          <a class="lnk" href="${esc(iframeUrl)}" target="_blank" rel="noopener">Open in tab</a>
        </div>
      </div>
      <div class="viewer-b" style="padding:0">
        <iframe src="${esc(iframeUrl)}" style="width:100%;height:100%;border:0;flex:1;min-height:0" title="${esc(name)}"></iframe>
      </div>`;
    return;
  }

  if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext) || fType === 'img') {
    container.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge ${badgeClass}">${badgeText}</span><span title="${esc(name)}">${esc(name)}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
          <a class="lnk" href="${esc(downloadUrl)}" download>Download</a>
          <a class="lnk" href="${esc(rawUrl)}" target="_blank" rel="noopener">Open in tab</a>
        </div>
      </div>
      <div class="viewer-b" style="align-items:center;justify-content:center;background:var(--panel2)">
        <img src="${esc(rawUrl)}" alt="${esc(name)}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:4px">
      </div>`;
    return;
  }

  if (['.schdoc', '.pcbdoc', '.prjpcb', '.rul'].includes(ext) || fType === 'altium' || fType === 'sch' || fType === 'pcb') {
    container.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge ${badgeClass}">${badgeText}</span><span title="${esc(path)}">${esc(name)}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
        </div>
      </div>
      <div class="viewer-b"><div class="dnote">Loading Altium summary…</div></div>`;
    try {
      const data = await api('/api/altium/file?path=' + encodeURIComponent(path), undefined, { soft: true });
      const bodyEl = container.querySelector('.viewer-b');
      if (!bodyEl) return;
      if (data.error) {
        bodyEl.innerHTML = `<div class="warnbox"><b>Cannot read file:</b><div style="margin-top:4px">${esc(data.error)}</div></div>`;
        return;
      }
      let contentHtml = `<div><b>Path:</b> <span class="m path" style="word-break:break-all">${esc(path)}</span></div>`;
      if (ext === '.schdoc') {
        contentHtml += `
          <div class="kpis" style="margin-top:12px">
            <div class="kpi"><b>${data.components ?? 0}</b><span>components</span></div>
            <div class="kpi"><b>${data.wires ?? 0}</b><span>wires</span></div>
            <div class="kpi"><b>${data.net_labels ?? 0}</b><span>net labels</span></div>
            <div class="kpi"><b>${data.power_ports ?? 0}</b><span>power ports</span></div>
            <div class="kpi"><b>${data.ports ?? 0}</b><span>ports</span></div>
            <div class="kpi"><b>${data.junctions ?? 0}</b><span>junctions</span></div>
          </div>`;
      } else if (ext === '.pcbdoc') {
        contentHtml += `
          <div class="kpis" style="margin-top:12px">
            <div class="kpi"><b>${data.components ?? 0}</b><span>components</span></div>
            <div class="kpi"><b>${data.nets ?? 0}</b><span>nets</span></div>
            <div class="kpi"><b>${data.pads ?? 0}</b><span>pads</span></div>
            <div class="kpi"><b>${data.rules ?? 0}</b><span>rules</span></div>
            <div class="kpi"><b>${data.classes ?? 0}</b><span>classes</span></div>
          </div>`;
      } else {
        contentHtml += `<pre class="viewer-pre" style="margin-top:12px">${esc(JSON.stringify(data, null, 2))}</pre>`;
      }
      bodyEl.innerHTML = contentHtml;
    } catch (err) {
      const bodyEl = container.querySelector('.viewer-b');
      if (bodyEl) bodyEl.innerHTML = `<div class="warnbox"><b>Failed to load Altium summary:</b> ${esc(err.message)}</div>`;
    }
    return;
  }

  const exportUrl = (fType === 'export') ? `/api/export/${encodeURIComponent(name)}?${q()}` : rawUrl;
  container.innerHTML = `
    <div class="viewer-h">
      <div class="vtitle"><span class="badge ${badgeClass}">${badgeText}</span><span title="${esc(name)}">${esc(name)}</span></div>
      <div class="vacts">
        <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
        <a class="lnk" href="${esc(exportUrl)}" download>Download</a>
        <a class="lnk" href="${esc(exportUrl)}" target="_blank" rel="noopener">Open in tab</a>
      </div>
    </div>
    <div class="viewer-b"><div class="dnote">Loading…</div></div>`;
  try {
    const res = await fetch(exportUrl);
    const text = await res.text();
    const bodyEl = container.querySelector('.viewer-b');
    if (!bodyEl) return;
    if (ext === '.csv') {
      const lns = text.split(/\r?\n/).filter(l => l.trim().length > 0);
      const rows = lns.map(l => parseCsvLine(l));
      if (rows.length) {
        bodyEl.innerHTML = `<div class="tblwrap"><table class="viewer-tbl"><thead><tr>${rows[0].map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      } else {
        bodyEl.innerHTML = '<div class="dnote">Empty CSV</div>';
      }
    } else {
      bodyEl.innerHTML = `<pre class="viewer-pre">${esc(text)}</pre>`;
    }
  } catch (err) {
    const b = container.querySelector('.viewer-b');
    if (b) b.innerHTML = `<div class="dnote">Error: ${esc(err.message)}</div>`;
  }
}

/* ---------- file viewer ---------- */
function closeViewer() {
  const v = $('#viewer');
  if (v && !v.hidden) {
    v.hidden = true;
    v.innerHTML = '';
  }
}
function parseCsvLine(line) {
  const cells = [];
  let cur = '', inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === ',' && !inQ) {
      cells.push(cur.trim()); cur = '';
    } else {
      cur += ch;
    }
  }
  cells.push(cur.trim());
  return cells;
}
async function openViewerSource(name, where) {
  setView('work');
  openFileAsTab({ name, path: name, where });
  return;
  const known = srcByName(name);
  const size = (known && known.size) ? known.size : '';
  const ext = (name.includes('.') ? '.' + name.split('.').pop() : '').toLowerCase();
  const qDownload = q({download: '1'});
  const downloadUrl = `/api/source/${encodeURIComponent(name)}?${qDownload}`;
  const rawUrl = `/api/source/${encodeURIComponent(name)}?${q()}`;

  if (['.schdoc', '.pcbdoc', '.prjpcb', '.rul'].includes(ext)) {
    let resolved = null;
    if (ALTIUM_DATA && ALTIUM_DATA.linked) {
      const l = ALTIUM_DATA.linked;
      const allDocs = [...(l.sheets || []), l.pcb_file, l.project_file].filter(Boolean);
      resolved = allDocs.find(p => p.toLowerCase().endsWith(name.toLowerCase()));
    }
    if (resolved) {
      return openViewerAltium(resolved);
    }
  }

  if (ext === '.pdf') {
    let iframeUrl = rawUrl;
    const m = (where || '').match(/\b(?:p\.?|page)\s*(\d+)\b/i);
    if (m) iframeUrl += '#page=' + m[1];
    v.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge">PDF</span><span title="${esc(name)}">${esc(name)}${m ? ` (p. ${m[1]})` : ''}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
          <a class="lnk" href="${esc(downloadUrl)}" download>Download</a>
          <a class="lnk" href="${esc(iframeUrl)}" target="_blank" rel="noopener">Open in tab</a>
          <button class="x" data-act="closeviewer" aria-label="Close">×</button>
        </div>
      </div>
      <div class="viewer-b" style="padding:0">
        <div class="dnote" style="margin:16px">Checking PDF…</div>
      </div>`;
    try {
      const checkRes = await fetch(rawUrl);
      const buf = new Uint8Array(await checkRes.arrayBuffer());
      const headerStr = String.fromCharCode.apply(null, buf.subarray(0, 8));
      if (!headerStr.startsWith('%PDF-')) {
        const bodyEl = v.querySelector('.viewer-b');
        if (bodyEl) {
          bodyEl.style.padding = '14px';
          bodyEl.innerHTML = `<div class="warnbox" style="margin:14px"><b>Invalid PDF:</b> This file is not a valid PDF (it may be empty or damaged). Upload it again.</div>`;
        }
        return;
      }
    } catch (e) {
      // In case of error, continue or show error
    }
    const bodyEl = v.querySelector('.viewer-b');
    if (bodyEl) {
      bodyEl.style.padding = '0';
      bodyEl.innerHTML = `<iframe src="${esc(iframeUrl)}" style="width:100%;height:100%;border:0;flex:1;min-height:0" title="${esc(name)}"></iframe>`;
    }
    return;
  }

  if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext)) {
    v.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge">IMAGE</span><span title="${esc(name)}">${esc(name)}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
          <a class="lnk" href="${esc(downloadUrl)}" download>Download</a>
          <a class="lnk" href="${esc(rawUrl)}" target="_blank" rel="noopener">Open in tab</a>
          <button class="x" data-act="closeviewer" aria-label="Close">×</button>
        </div>
      </div>
      <div class="viewer-b" style="align-items:center;justify-content:center;background:var(--panel2)">
        <img src="${esc(rawUrl)}" alt="${esc(name)}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:4px">
      </div>`;
    return;
  }

  if (['.txt', '.text', '.md', '.markdown', '.csv', '.json'].includes(ext) || (known && known.text)) {
    v.innerHTML = `
      <div class="viewer-h">
        <div class="vtitle"><span class="badge">${esc(ext ? ext.slice(1).toUpperCase() : 'TEXT')}</span><span title="${esc(name)}">${esc(name)}</span></div>
        <div class="vacts">
          <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
          <a class="lnk" href="${esc(downloadUrl)}" download>Download</a>
          <a class="lnk" href="${esc(rawUrl)}" target="_blank" rel="noopener">Open in tab</a>
          <button class="x" data-act="closeviewer" aria-label="Close">×</button>
        </div>
      </div>
      <div class="viewer-b"><div class="dnote">Loading text…</div></div>`;
    try {
      const res = await fetch(rawUrl);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const text = await res.text();
      const bodyEl = v.querySelector('.viewer-b');
      if (!bodyEl) return;
      if (ext === '.csv') {
        const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
        const maxRows = 500;
        const rows = [];
        for (let i = 0; i < Math.min(lines.length, maxRows); i++) {
          rows.push(parseCsvLine(lines[i]));
        }
        if (rows.length) {
          const head = rows[0];
          const bodyRows = rows.slice(1);
          bodyEl.innerHTML = `<div class="tblwrap"><table class="viewer-tbl">` +
            `<thead><tr>${head.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>` +
            `<tbody>${bodyRows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody>` +
            `</table></div>` +
            (lines.length > maxRows ? `<div class="dnote" style="margin-top:8px">Showing 500 of ${lines.length} rows</div>` : '');
        } else {
          bodyEl.innerHTML = `<div class="dnote">Empty CSV file</div>`;
        }
      } else {
        bodyEl.innerHTML = `<pre class="viewer-pre">${esc(text)}</pre>`;
      }
    } catch (err) {
      const bodyEl = v.querySelector('.viewer-b');
      if (bodyEl) bodyEl.innerHTML = `<div class="warnbox"><b>Failed to load text:</b> ${esc(err.message)}</div>`;
    }
    return;
  }

  // Anything else: name, size and a "Download" link
  v.innerHTML = `
    <div class="viewer-h">
      <div class="vtitle"><span class="badge">FILE</span><span title="${esc(name)}">${esc(name)}</span></div>
      <div class="vacts">
        <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
        <button class="x" data-act="closeviewer" aria-label="Close">×</button>
      </div>
    </div>
    <div class="viewer-b">
      <div class="card" style="padding:16px;display:grid;gap:12px">
        <div><b>File name:</b> <span class="m">${esc(name)}</span></div>
        ${size ? `<div><b>Size:</b> ${esc(size)}</div>` : ''}
        <div><a class="btn pri" href="${esc(downloadUrl)}" download>Download</a></div>
      </div>
    </div>`;
}
async function openViewerAltium(path) {
  setView('work');
  const fileName = path.split(/[\\/]/).pop();
  const ext = (fileName.includes('.') ? '.' + fileName.split('.').pop() : '').toLowerCase();
  const fileType = ext === '.schdoc' ? 'sch' : ext === '.pcbdoc' ? 'pcb' : ext === '.prjpcb' ? 'prj' : ext === '.rul' ? 'rul' : 'sch';
  openFileAsTab({ name: fileName, path, fileType });
  return;
  v.innerHTML = `
    <div class="viewer-h">
      <div class="vtitle"><span class="badge">ALTIUM</span><span title="${esc(path)}">${esc(fileName)}</span></div>
      <div class="vacts">
        <button type="button" class="btn" data-act="ask-file" data-file="${esc(fileName)}">Ask about this file</button>
        <button class="x" data-act="closeviewer" aria-label="Close">×</button>
      </div>
    </div>
    <div class="viewer-b"><div class="dnote">Loading Altium summary…</div></div>`;

  try {
    const data = await api('/api/altium/file?path=' + encodeURIComponent(path), undefined, {soft: true});
    const bodyEl = v.querySelector('.viewer-b');
    if (!bodyEl) return;
    if (data.error) {
      bodyEl.innerHTML = `<div class="warnbox"><b>Cannot read file:</b><div style="margin-top:4px">${esc(data.error)}</div></div>`;
      return;
    }

    let contentHtml = `<div><b>Path:</b> <span class="m path" style="word-break:break-all">${esc(path)}</span></div>`;

    if (ext === '.schdoc') {
      contentHtml += `
        <div class="kpis" style="margin-top:12px">
          <div class="kpi"><b>${data.components ?? 0}</b><span>components</span></div>
          <div class="kpi"><b>${data.wires ?? 0}</b><span>wires</span></div>
          <div class="kpi"><b>${data.net_labels ?? 0}</b><span>net labels</span></div>
          <div class="kpi"><b>${data.power_ports ?? 0}</b><span>power ports</span></div>
          <div class="kpi"><b>${data.ports ?? 0}</b><span>ports</span></div>
          <div class="kpi"><b>${data.junctions ?? 0}</b><span>junctions</span></div>
        </div>`;
      if (data.components_sample && data.components_sample.length) {
        contentHtml += `<div class="dsec" style="margin-top:14px"><h4>Components sample (${data.components_sample.length} of ${data.components})</h4>
          <div class="tblwrap"><table class="viewer-tbl">
            <thead><tr><th>Designator</th><th>Library Ref</th><th>Footprint</th><th>Pins</th></tr></thead>
            <tbody>${data.components_sample.map(c => `<tr><td class="m refs">${esc(c.ref)}</td><td class="m">${esc(c.lib_ref)}</td><td class="m">${esc(c.footprint)}</td><td class="n">${c.pins}</td></tr>`).join('')}</tbody>
          </table></div></div>`;
      }
      if (data.record_counts && Object.keys(data.record_counts).length) {
        const counts = Object.entries(data.record_counts);
        contentHtml += `<div class="dsec" style="margin-top:14px"><h4>Record counts (${counts.length})</h4>
          <div class="tblwrap"><table class="viewer-tbl">
            <thead><tr><th>Record Type</th><th>Count</th></tr></thead>
            <tbody>${counts.map(([k, count]) => `<tr><td class="m">${esc(k)}</td><td class="n">${count}</td></tr>`).join('')}</tbody>
          </table></div></div>`;
      }
    } else if (ext === '.pcbdoc') {
      contentHtml += `
        <div class="kpis" style="margin-top:12px">
          <div class="kpi"><b>${data.components ?? 0}</b><span>components</span></div>
          <div class="kpi"><b>${data.nets ?? 0}</b><span>nets</span></div>
          <div class="kpi"><b>${data.pads ?? 0}</b><span>pads</span></div>
          <div class="kpi"><b>${data.rules ?? 0}</b><span>rules</span></div>
          <div class="kpi"><b>${data.classes ?? 0}</b><span>classes</span></div>
        </div>`;
      const samples = [
        ['Components sample', (data.components_sample || []).join(', ')],
        ['Nets sample', (data.nets_sample || []).join(', ')],
        ['Pads sample', (data.pads_sample || []).join(', ')],
      ];
      contentHtml += `<div class="card" style="margin-top:12px;padding:12px;display:grid;gap:8px">` +
        samples.filter(s => s[1]).map(([title, val]) => `<div><b>${title}:</b> <span class="m">${esc(val)}</span></div>`).join('') +
        `</div>`;
    } else if (ext === '.prjpcb') {
      const prjDir = path.replace(/[\\/][^\\/]+$/, '');
      const prjSep = path.includes('\\') ? '\\' : '/';
      const toAbs = rel => (rel.includes(':') || rel.startsWith('/') || !prjDir) ? rel : (prjDir + prjSep + rel.replace(/[\\/]/g, prjSep));
      contentHtml += `
        <div class="kpis" style="margin-top:12px">
          <div class="kpi"><b>${data.documents ?? 0}</b><span>documents</span></div>
          <div class="kpi"><b>${(data.sheets || []).length}</b><span>sheets</span></div>
          <div class="kpi"><b>${(data.pcbs || []).length}</b><span>PCBs</span></div>
        </div>`;
      if (data.sheets && data.sheets.length) {
        contentHtml += `<div class="dsec" style="margin-top:12px"><h4>Sheets (${data.sheets.length})</h4>
          <div style="display:flex;flex-wrap:wrap;gap:6px">` +
          data.sheets.map(s => `<button type="button" class="btn" data-altium-path="${esc(toAbs(s))}"><span class="m">${esc(s.split(/[\\/]/).pop())}</span></button>`).join('') +
          `</div></div>`;
      }
      if (data.pcbs && data.pcbs.length) {
        contentHtml += `<div class="dsec" style="margin-top:12px"><h4>PCBs (${data.pcbs.length})</h4>
          <div style="display:flex;flex-wrap:wrap;gap:6px">` +
          data.pcbs.map(p => `<button type="button" class="btn" data-altium-path="${esc(toAbs(p))}"><span class="m">${esc(p.split(/[\\/]/).pop())}</span></button>`).join('') +
          `</div></div>`;
      }
      if (data.outjobs && data.outjobs.length) {
        contentHtml += `<div class="dsec" style="margin-top:12px"><h4>Output Jobs (${data.outjobs.length})</h4>
          <div>${data.outjobs.map(o => `<span class="m">${esc(o)}</span>`).join(', ')}</div></div>`;
      }
      if (data.missing && data.missing.length) {
        contentHtml += `<div class="warnbox" style="margin-top:12px"><b>Missing documents (${data.missing.length}):</b><ul>${data.missing.map(m => `<li>${esc(m)}</li>`).join('')}</ul></div>`;
      }
    } else if (ext === '.rul') {
      contentHtml += `
        <div class="kpis" style="margin-top:12px">
          <div class="kpi"><b>${data.rules ?? 0}</b><span>rules</span></div>
        </div>`;
      if (data.rules_sample && data.rules_sample.length) {
        contentHtml += `<div class="dsec" style="margin-top:12px"><h4>Rules sample</h4>
          <ul>${data.rules_sample.map(r => `<li class="m">${esc(r)}</li>`).join('')}</ul></div>`;
      }
    } else {
      contentHtml += `<pre class="viewer-pre" style="margin-top:12px">${esc(JSON.stringify(data, null, 2))}</pre>`;
    }

    bodyEl.innerHTML = contentHtml;
  } catch (err) {
    const bodyEl = v.querySelector('.viewer-b');
    if (bodyEl) bodyEl.innerHTML = `<div class="warnbox"><b>Failed to load Altium summary:</b> ${esc(err.message)}</div>`;
  }
}
function openViewerSlice(stem, sliceName) {
  setView('work');
  openFileAsTab({ name: sliceName, stem, slice: sliceName, fileType: 'dfm' });
  return;
  const v = $('#viewer');
  if (!v) return;
  setView('work');
  v.hidden = false;
  const rawUrl = `/api/checks/slice?stem=${encodeURIComponent(stem)}&slice=${encodeURIComponent(sliceName)}&${q()}`;
  v.innerHTML = `
    <div class="viewer-h">
      <div class="vtitle"><span class="badge">DFM SLICE</span><span title="${esc(sliceName)}">${esc(stem)} / ${esc(sliceName)}</span></div>
      <div class="vacts">
        <button type="button" class="btn" data-act="ask-file" data-file="${esc(sliceName)}">Ask about this file</button>
        <a class="lnk" href="${esc(rawUrl)}" target="_blank" rel="noopener">Open in tab</a>
        <button class="x" data-act="closeviewer" aria-label="Close">×</button>
      </div>
    </div>
    <div class="viewer-b" style="align-items:center;justify-content:flex-start;background:var(--panel2);overflow:auto">
      <img src="${esc(rawUrl)}" alt="${esc(sliceName)}" style="max-width:100%;height:auto;border-radius:4px;box-shadow:var(--shadow)">
    </div>`;
}
async function openViewerExport(name) {
  setView('work');
  openFileAsTab({ name, path: name, fileType: 'export' });
  return;
  const v = $('#viewer');
  if (!v) return;
  setView('work');
  v.hidden = false;
  const rawUrl = `/api/export/${encodeURIComponent(name)}?${q()}`;
  const ext = (name.includes('.') ? '.' + name.split('.').pop() : '').toLowerCase();
  v.innerHTML = `
    <div class="viewer-h">
      <div class="vtitle"><span class="badge">EXPORT</span><span title="${esc(name)}">${esc(name)}</span></div>
      <div class="vacts">
        <button type="button" class="btn" data-act="ask-file" data-file="${esc(name)}">Ask about this file</button>
        <a class="lnk" href="${esc(rawUrl)}" download>Download</a>
        <button class="x" data-act="closeviewer" aria-label="Close">×</button>
      </div>
    </div>
    <div class="viewer-b"><div class="dnote">Loading…</div></div>`;
  try {
    const res = await fetch(rawUrl);
    const text = await res.text();
    const bodyEl = v.querySelector('.viewer-b');
    if (ext === '.csv') {
      const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
      const rows = lines.map(l => parseCsvLine(l));
      if (rows.length) {
        bodyEl.innerHTML = `<div class="tblwrap"><table class="viewer-tbl"><thead><tr>${rows[0].map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      } else { bodyEl.innerHTML = '<div class="dnote">Empty CSV</div>'; }
    } else {
      bodyEl.innerHTML = `<pre class="viewer-pre">${esc(text)}</pre>`;
    }
  } catch (err) {
    const b = v.querySelector('.viewer-b'); if (b) b.innerHTML = `<div class="dnote">Error: ${esc(err.message)}</div>`;
  }
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('closeviewer', async (el, d, e) => {
  closeViewer(); return;
});
onAct('ask-file', async (el, d, e) => {
  const f = el.dataset.file;
  if (f) {
    activeFileChip = f;
    renderChatChip();
    const inp = $('#input');
    if (inp) inp.focus();
    setView('chat');
  }
  return;
});
