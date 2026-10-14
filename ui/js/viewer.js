/* PCB Advisor UI - documents. A document opens in the side sheet (shell.js openFileAsTab) and is drawn once by
   renderFileTabContent: PDF, image, DFM slice, CSV, text, markdown (js/markdown.js: the general reference documents), or the
   summary of an Altium file.
   Header: the file name, an Ask icon and a menu (Download, Open in new tab). Errors use errorLine, loading uses loadingLine.
   Opening is not here: every caller (chips, tables, the palette, links to Altium files) uses shell.js openFileAsTab, with
   fileType 'export' for a file the advisor wrote and {stem, slice, fileType: 'dfm'} for a DFM slice.
   Globals other files call: fileDownload (a Download button or toast), docBase. */

const DOC_PDF_BAD = 'This file is not a valid PDF (it may be empty or damaged). Upload it again.';
const DOC_IMG_EXT = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
const DOC_ALTIUM = ['sch', 'pcb', 'prj', 'rul', 'altium'];      // the fileType values shell.js gives an Altium document
const DOC_CSV_ROWS = 500;
const DOC_TEXT_CHARS = 300000;                                    // a text file is shown up to here; the rest is in Download

const docExt = n => (String(n).includes('.') ? '.' + String(n).split('.').pop() : '').toLowerCase();
const docBase = p => String(p || '').split(/[\\/]/).pop();
function docBytes(n) {
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
}
function docHost(url) {
  try { return new URL(url).hostname; } catch (e) { return url; }
}
/* start a download of a URL (a menu item is a button, so it cannot be a link) */
function fileDownload(url, name) {
  const a = document.createElement('a');
  a.href = url;
  a.download = name || '';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/* The first bytes of a response, without reading the whole file: enough to tell a PDF from something else. */
async function docFirstBytes(res, n) {
  if (!res.body || !res.body.getReader) return new Uint8Array(await res.arrayBuffer()).subarray(0, n);
  const reader = res.body.getReader();
  let got = new Uint8Array(0);
  while (got.length < n) {
    const {value, done} = await reader.read();
    if (done) break;
    const next = new Uint8Array(got.length + value.length);
    next.set(got);
    next.set(value, got.length);
    got = next;
  }
  reader.cancel();
  return got.subarray(0, n);
}

/* ---------- header ---------- */
function docHeader(o) {
  const items = [
    o.download && {label: 'Download', icon: 'download', act: 'doc-download', attrs: {url: o.download, name: o.name}},
    o.open && {label: 'Open in new tab', icon: 'ext', act: 'doc-open', attrs: {url: o.open}},
  ].filter(Boolean);
  const acts = btn('', {icon: 'chat', size: 'sm', title: 'Ask about this file', act: 'ask-file', file: o.name}) +
    (items.length ? menu({icon: 'more', size: 'sm', title: 'More'}, items) : '');
  return `<header class="doc-h"><div class="doc-t"><h2 class="m" title="${esc(o.title || o.name)}">${esc(o.name)}</h2>${o.sub ? `<div class="doc-sub">${o.sub}</div>` : ''}</div><div class="acts">${acts}</div></header>`;
}
/* what we know about a source: where it sits, its size, where it came from, its hash, and whether the agent can read its text */
function docSourceSub(name, where) {
  const s = srcByName(name), parts = [];
  if (s) {
    parts.push(`<span>${s.scope === 'shared' ? 'Shared' : 'Project'}</span>`);
    if (s.size && s.size !== '—') parts.push(`<span>${esc(s.size)}</span>`);
    if (s.url && /^https?:\/\//i.test(s.url)) parts.push(`<a href="${esc(s.url)}" target="_blank" rel="noopener" title="${esc(s.url)}">${esc(docHost(s.url))}</a>`);
    else if (s.origin) parts.push(`<span>${esc(s.origin)}</span>`);
    if (s.sha256 && s.sha256 !== '—') parts.push(`<span title="The start of the file's sha256">sha256 <span class="m">${esc(s.sha256)}</span></span>`);
    if (s.text) parts.push('<span>Text extracted</span>');
    else if (docExt(name) === '.pdf') parts.push('<span class="warn-t" title="The agent cannot quote this document">No text extracted</span>');
  }
  if (where) parts.push(`<span>${esc(where)}</span>`);
  return parts.join('');
}

/* ---------- one document ---------- */
async function renderFileTabContent(tabObj, container) {
  const name = tabObj.name || tabObj.path || 'file';
  const path = tabObj.path || name;
  const ext = docExt(name);
  const ft = tabObj.fileType || 'txt';
  const token = container.dataset.docKey;                      // a later document in the same pane makes this one stale
  const stale = () => container.dataset.docKey !== token;
  const body = () => container.querySelector('.doc-b');
  const paint = (cls, html) => { container.innerHTML = html.head + `<div class="doc-b${cls ? ' ' + cls : ''}">${html.body}</div>`; };

  const isSlice = !!(tabObj.stem && tabObj.slice) || ft === 'dfm';
  const isExport = ft === 'export';
  const isAltium = DOC_ALTIUM.includes(ft) && !isExport && (path !== name || !srcByName(name));
  const enc = encodeURIComponent;
  let raw, download, open;
  if (isSlice) {
    raw = `/api/checks/slice?stem=${enc(tabObj.stem || '')}&slice=${enc(tabObj.slice || name)}&${q()}`;
    download = open = raw;
  } else if (isExport) {
    raw = download = `/api/export/${enc(name)}?${q()}`;       // the server sends an export as a download, so there is no tab to open
  } else {
    raw = `/api/source/${enc(name)}?${q()}`;
    download = `/api/source/${enc(name)}?${q({download: '1'})}`;
    open = raw;
  }

  if (isSlice) {
    const slice = tabObj.slice || name;
    paint('doc-img', {head: docHeader({name: slice, sub: tabObj.stem ? `<span>${esc(tabObj.stem)}</span>` : '', download, open}),
      body: `<img src="${esc(raw)}" alt="${esc(slice)}">`});
    return;
  }

  if (isAltium) {
    const head = docHeader({name, title: path, sub: `<span class="m" title="${esc(path)}">${esc(path).replace(/([\\/])/g, '$1<wbr>')}</span>`});
    paint('', {head, body: loadingLine('Reading the file')});
    let html;
    try {
      const data = await api('/api/altium/file?path=' + enc(path), undefined, {soft: true});
      html = data.error ? errorLine('read ' + name, data.error) : docAltiumHTML(path, ext, data);
    } catch (err) {
      html = errorLine('read ' + name, err.message);
    }
    if (!stale() && body()) body().innerHTML = html;
    return;
  }

  if (!isExport && (ft === 'pdf' || ext === '.pdf')) {
    const m = (tabObj.where || '').match(/\b(?:p\.?|page)\s*(\d+)\b/i);
    const frame = raw + (m ? '#page=' + m[1] : '');
    const head = docHeader({name, sub: docSourceSub(name, m ? `Page ${m[1]}` : ''), download, open: frame});
    paint('', {head, body: loadingLine('Checking the PDF')});
    let bad = null;
    try {
      const res = await fetch(raw);
      if (!res.ok) bad = res.status === 404 ? 'It is not in this project or the shared sources.' : 'The server answered ' + res.status + '.';
      else if (String.fromCharCode.apply(null, await docFirstBytes(res, 8)).startsWith('%PDF-') === false) bad = DOC_PDF_BAD;
    } catch (e) {
      bad = e.message || 'The server did not answer.';
    }
    if (stale() || !body()) return;
    if (bad) { body().innerHTML = errorLine('open this PDF', bad); return; }
    body().classList.add('bleed');
    body().innerHTML = `<iframe class="doc-pdf" src="${esc(frame)}" title="${esc(name)}"></iframe>`;
    return;
  }

  if (!isExport && (DOC_IMG_EXT.includes(ext) || ft === 'img')) {
    paint('doc-img', {head: docHeader({name, sub: docSourceSub(name), download, open}), body: `<img src="${esc(raw)}" alt="${esc(name)}">`});
    return;
  }

  // CSV, text, markdown and anything else: read it, and say so when it is not text
  paint('', {head: docHeader({name, sub: isExport ? docExportSub(name) : docSourceSub(name, tabObj.where), download, open: isExport ? '' : open}), body: loadingLine('Loading')});
  let html;
  const md = ext === '.md' && !isExport;                       // a markdown source is read as a document, not as raw text
  try {
    const res = await fetch(raw);
    if (!res.ok) throw new Error(res.status === 404 ? 'It is not in this project.' : 'The server answered ' + res.status + '.');
    const buf = new Uint8Array(await res.arrayBuffer());
    if (buf.subarray(0, 4096).includes(0)) {
      html = emptyState('No preview for this file', 'Download it to open it in another program.', btn('Download', {kind: 'line', icon: 'download', act: 'doc-download', url: download, name}));
    } else {
      const text = new TextDecoder().decode(buf);
      html = ext === '.csv' ? docCsvHTML(text) : md ? docMarkdownHTML(text) : docTextHTML(text);
    }
  } catch (err) {
    html = errorLine('open ' + name, err.message);
  }
  if (stale() || !body()) return;
  body().innerHTML = html;
  if (md) docReveal(body(), tabObj.where);
}
function docExportSub(name) {
  const f = (S.exports || []).find(x => x.name === name);
  return `<span>Export</span>${f && f.size != null ? `<span>${esc(docBytes(f.size))}</span>` : ''}`;
}
const docCut = text => (text.length > DOC_TEXT_CHARS ? text.slice(0, DOC_TEXT_CHARS) : text);
const docMore = text => (text.length > DOC_TEXT_CHARS ? `<p class="doc-more">Showing the first ${num(DOC_TEXT_CHARS)} of ${num(text.length)} characters.</p>` : '');
function docTextHTML(text) {
  return `<pre class="doc-pre">${esc(docCut(text))}</pre>${docMore(text)}`;
}
function docMarkdownHTML(text) {
  return `<article class="md">${mdToHTML(docCut(text))}</article>${docMore(text)}`;
}
/* a citation names a section or a page: scroll to it and mark it, so the reader sees what was quoted */
function docReveal(box, where) {
  const el = mdFindSection(box, where);
  if (!el) return;
  el.classList.add('md-hit');
  el.scrollIntoView({block: 'start'});
}
function docCsvHTML(text) {
  const lns = text.split(/\r?\n/).filter(l => l.trim().length > 0);
  if (!lns.length) return '<p class="muted">This file is empty.</p>';
  const head = parseCsvLine(lns[0]);
  const rows = lns.slice(1, DOC_CSV_ROWS + 1).map(parseCsvLine);
  const total = lns.length - 1;
  return `<div class="tbl-wrap"><table class="tbl dense"><thead><tr>${head.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>` +
    `<tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` +
    (total > DOC_CSV_ROWS ? `<p class="doc-more">Showing ${DOC_CSV_ROWS} of ${num(total)} rows.</p>` : '');
}

/* ---------- an Altium file: one line of counts, then the lists that help ---------- */
function docAltiumHTML(path, ext, data) {
  const pl = (n, one, many) => ({n: n ?? 0, label: n === 1 ? one : (many || one + 's')});
  const sample = (n, shown) => (shown < n ? `First ${shown} of ${num(n)}` : '');
  const fileBtn = rel => {
    const dir = path.replace(/[\\/][^\\/]+$/, ''), sepc = path.includes('\\') ? '\\' : '/';
    const abs = (rel.includes(':') || rel.startsWith('/') || !dir) ? rel : dir + sepc + rel.replace(/[\\/]/g, sepc);
    return `<li><button type="button" class="btn link m" data-altium-path="${esc(abs)}" title="${esc(abs)}">${esc(docBase(rel))}</button></li>`;
  };
  let meta = '', out = '';
  if (ext === '.schdoc') {
    meta = metaLine([pl(data.components, 'component'), pl(data.wires, 'wire'), pl(data.net_labels, 'net label'), pl(data.power_ports, 'power port'),
      pl(data.ports, 'port'), pl(data.junctions, 'junction')]);
    const cs = data.components_sample || [];
    if (cs.length) {
      out += section('Components', `<div class="tbl-wrap"><table class="tbl dense"><thead><tr><th>Designator</th><th>Library part</th><th class="num">Pins</th></tr></thead>` +
        `<tbody>${cs.map(c => `<tr><td class="ref">${esc(c.ref)}</td><td><span class="m">${esc(c.lib_ref)}</span>${c.footprint ? `<span class="sub m">${esc(c.footprint)}</span>` : ''}</td><td class="num">${esc(c.pins)}</td></tr>`).join('')}</tbody></table></div>`,
        {meta: esc(sample(data.components, cs.length))});
    }
    const rc = Object.entries(data.record_counts || {});
    if (rc.length) {
      out += `<details class="disc doc-rc"><summary>Record types (${rc.length})</summary><div class="tbl-wrap"><table class="tbl dense"><thead><tr><th>Record</th><th class="num">Count</th></tr></thead>` +
        `<tbody>${rc.map(([k, n]) => `<tr><td class="m">${esc(k)}</td><td class="num">${esc(n)}</td></tr>`).join('')}</tbody></table></div></details>`;
    }
  } else if (ext === '.pcbdoc') {
    meta = metaLine([pl(data.components, 'component'), pl(data.nets, 'net'), pl(data.pads, 'pad'), pl(data.rules, 'rule'), pl(data.classes, 'class', 'classes')]);
    const pairs = [['Components', data.components_sample], ['Nets', data.nets_sample], ['Pads', data.pads_sample]]
      .filter(p => p[1] && p[1].length).map(([k, v]) => [k, `<span class="m">${esc(v.join(', '))}</span>`, true]);
    if (pairs.length) out += section('First few', kv(pairs));
  } else if (ext === '.prjpcb') {
    const sheets = data.sheets || [], pcbs = data.pcbs || [], jobs = data.outjobs || [], gone = data.missing || [];
    meta = metaLine([pl(data.documents, 'document'), pl(sheets.length, 'sheet'), pl(pcbs.length, 'PCB')]);
    if (sheets.length) out += section('Sheets', `<ul class="doc-list">${sheets.map(fileBtn).join('')}</ul>`);
    if (pcbs.length) out += section('PCBs', `<ul class="doc-list">${pcbs.map(fileBtn).join('')}</ul>`);
    if (jobs.length) out += section('OutJobs', `<ul class="doc-list">${jobs.map(o => `<li class="m">${esc(docBase(o))}</li>`).join('')}</ul>`);
    if (gone.length) out += `<div class="note warn doc-gone" title="${esc(gone.join('\n'))}"><span>${gone.length === 1 ? '1 document is' : gone.length + ' documents are'} missing: ${esc(gone.slice(0, 3).map(docBase).join(', '))}${gone.length > 3 ? ` and ${gone.length - 3} more` : ''}</span></div>`;
  } else if (ext === '.rul') {
    meta = metaLine([pl(data.rules, 'rule')]);
    const rs = data.rules_sample || [];
    if (rs.length) out += section('Rules', `<ul class="doc-list">${rs.map(r => `<li class="m">${esc(r)}</li>`).join('')}</ul>`, {meta: esc(sample(data.rules, rs.length))});
  }
  return `${meta ? `<div class="meta doc-meta">${meta}</div>` : ''}${out || '<p class="muted">Nothing to list for this file.</p>'}`;
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

/* ---------- action handlers (dispatched by the delegates in core.js) ---------- */
onAct('ask-file', async (el, d, e) => {
  if (d.file) askAbout({kind: 'file', id: d.file, label: d.file});
});
onAct('doc-download', async (el, d, e) => {
  if (d.url) fileDownload(d.url, d.name);
});
onAct('doc-open', async (el, d, e) => {
  if (d.url) window.open(d.url, '_blank', 'noopener');
});
