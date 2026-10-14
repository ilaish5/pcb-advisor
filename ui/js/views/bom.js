/* PCB Advisor UI - BOM view: table, alternatives, Altium import, compare/export cards, part detail drawer. */

function altsHTML() {
  if (!altsCard) return '';
  const c = altsCard;
  const l = lineByKey(c.line);
  return `<div class="howto"><b>Alternatives for ${esc(c.line)} (${esc(c.mpn || l?.mpn || '')})</b> <button class="x" data-act="closecard" aria-label="Close">×</button>
    ${c.loading ? '<div class="dnote" style="margin-top:6px">Searching in-stock alternatives…</div>' :
      (!c.list || !c.list.length) ? '<div class="dnote" style="margin-top:6px">No in-stock alternatives found.</div>' :
      `<div class="tblwrap" style="margin-top:8px"><table class="bom">
        <thead><tr><th>Code</th><th>MPN</th><th>Manufacturer</th><th>Package</th><th>Type</th><th style="text-align:right">Stock</th><th style="text-align:right">Unit</th><th></th></tr></thead>
        <tbody>
          ${c.list.map(a => {
            const uPrice = (a.price_breaks && a.price_breaks[0]) ? a.price_breaks[0].price : null;
            return `<tr>
              <td class="m">${esc(a.code)}</td>
              <td class="m"><b>${esc(a.mpn)}</b></td>
              <td>${esc(a.manufacturer)}</td>
              <td class="m">${esc(a.package)}</td>
              <td><span class="lib ${a.library_type === 'Basic' || a.library_type === 'Preferred' ? 'ok' : a.library_type === 'Extended' ? 'warn' : 'std'}">${esc(a.library_type || '—')}</span></td>
              <td class="n">${num(a.stock)}</td>
              <td class="n">${money(uPrice)}</td>
              <td><button class="btn pri" data-act="propose-alt" data-line="${esc(c.line)}" data-mpn="${esc(a.mpn)}" data-pkg="${esc(a.package)}" data-desc="${esc(a.description || '')}" data-code="${esc(a.code)}" data-type="${esc(a.library_type || '')}">Propose</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`
    }
  </div>`;
}
const CODE_RISK = 'LCSC code is another part';    // store.CODE_RISK
async function loadImportInfo(force) {
  if (!force && impFor === PROJECT) return;
  impFor = PROJECT;
  try {
    const r = await api('/api/bom/import/candidates', undefined, {soft: true});
    impInfo = r && !r.error ? r : null;
  } catch (e) { impInfo = null; }
  const cs = impInfo ? impInfo.candidates : [];
  if (!cs.some(c => c.path === impSel)) impSel = cs.length ? cs[0].path : '';
  renderCenter(true);
}
function importHTML() {
  if (!impInfo || !impInfo.linked) return '';
  const empty = !lines().length, cs = impInfo.candidates || [];
  const label = c => `${c.folder.split(/[\\/]/).slice(-1)[0]}/${c.name} · ${c.rows} rows${c.has_lcsc ? ' · LCSC' : ''} · ${c.mtime.replace('T', ' ').slice(0, 16)}`;
  return `<div class="howto"><b>Import BOM from Altium</b> <span style="color:var(--dim)">Reads a BOM CSV exported from your Altium project and compares it with the schematic and the board. The files are never changed.</span>
    ${cs.length ? `<div class="imp-row"><select id="imp-csv" aria-label="BOM file">${cs.map(c => `<option value="${esc(c.path)}" ${c.path === impSel ? 'selected' : ''}>${esc(label(c))}</option>`).join('')}</select>
      <button class="btn" data-act="imp-scan" title="Look for BOM files again">Rescan</button>
      <button class="btn" data-act="imp-preview" ${impBusy ? 'disabled' : ''}>Preview</button>
      <button class="btn pri" data-act="imp-apply" ${empty && !impBusy ? '' : 'disabled'} ${empty ? '' : 'title="Import works into an empty BOM"'}>Import</button></div>`
      : `<div class="imp-row"><span class="dnote">No BOM CSV (a file with "bom" in its name) found in the Altium project. Export one from Altium (Reports, Bill of Materials), then rescan.</span>
      <button class="btn" data-act="imp-scan">Rescan</button></div>`}
    ${impReport ? importReportHTML(impReport) : ''}</div>`;
}
function importReportHTML(r) {
  const src = r.sources.find(s => s.role === 'bom_csv') || {}, sev = r.by_severity, pl = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const cls = s => s === 'error' ? 'bad' : s === 'warn' ? 'warn' : 'plan';
  const kinds = Object.entries(r.by_kind).sort((a, b) => b[1] - a[1]);
  return `<div class="imp-rep">
    <div style="margin-top:8px">${r.applied ? `<b>Imported ${r.imported_lines} lines</b>` : '<b>Preview</b>, nothing imported yet'} from ${esc(src.name)}: ${pl(r.csv.lines, 'line')}, ${pl(r.csv.refs, 'designator')}.
      ${pl(sev.error, 'error')}, ${pl(sev.warn, 'warning')}, ${pl(sev.info, 'note')}.</div>
    ${kinds.length ? `<div class="imp-tags">${kinds.map(([k, n]) => `<span class="tag plan">${esc(k)} ${n}</span>`).join('')}</div>
    <div class="tblwrap imp-tbl"><table class="imp"><thead><tr><th>Severity</th><th>Kind</th><th>Refs</th><th>Message</th></tr></thead><tbody>
      ${r.findings.map(f => `<tr><td><span class="tag ${cls(f.severity)}">${esc(f.severity)}</span></td><td class="m">${esc(f.kind)}</td><td class="m">${esc(f.refs.slice(0, 4).join(', '))}${f.refs.length > 4 ? ' +' + (f.refs.length - 4) : ''}</td><td class="msg">${esc(f.message)}</td></tr>`).join('')}
    </tbody></table></div>` : '<div class="dnote" style="margin-top:6px">The files agree.</div>'}
    <div style="margin-top:4px;color:var(--dim);font-size:12px">A finding is for you to decide: the imported lines keep what the BOM CSV says. Report: <span class="path">projects/${esc(PROJECT)}/checks/bom-import.md</span></div></div>`;
}
function bomHTML(container) {
  const t = S.totals, at = checkedAt();
  const uncheck = lines().filter(l => l.availability === 'unchecked' || l.supply == null).length;
  const extFee = t.extended_fee || 0;
  return `${guidanceBarHTML('bom')}
    <div class="vhead"><div><h2>Bill of materials</h2><p>The single source of truth. The agent proposes changes and you approve them. Click a row to see where the part sits in the schematic.</p></div>
    <div class="vacts"><button class="btn pri" data-act="check-all">Check all</button><button class="btn" data-act="check">Check stock</button><button class="btn" data-act="compare">Compare prices</button>
    <button class="btn" data-act="export" data-fmt="jlc">Export JLC</button><button class="btn" data-act="export" data-fmt="pcbway">Export PCBWay</button></div></div>
    ${compareCard ? compareHTML() : ''}${exportCard ? exportHTML() : ''}${altsCard ? altsHTML() : ''}
    ${importHTML()}
    <div class="kpis">
      <div class="kpi"><b>${t.lines}</b><span>lines</span></div>
      <div class="kpi"><b>${t.parts}</b><span>parts to place</span></div>
      <div class="kpi"><b>${money(t.cost_per_board ?? t.cost)}</b><span>cost / board</span></div>
      <div class="kpi ${extFee ? 'warn' : ''}"><b>${money(extFee)}</b><span>Extended fee <small style="color:var(--dim)">(assumption: $${CONFIG?.jlc?.extended_fee_usd || 3}/type)</small></span></div>
      <div class="kpi ${uncheck ? 'warn' : ''}"><b>${uncheck}</b><span>not checked</span></div>
      <div class="kpi ${t.out_of_stock ? 'bad' : ''}"><b>${t.out_of_stock}</b><span>out of stock</span></div>
      <div class="kpi ${t.to_verify ? 'warn' : ''}"><b>${t.to_verify}</b><span>to verify</span></div>
    </div>
    ${t.lines ? `<div class="tblwrap"><table class="bom"><thead><tr><th></th><th>Ref</th><th>Role</th><th>Value</th><th>Description</th><th>MPN</th><th>Package</th><th>Type</th><th>Qty</th><th>Stock</th><th>Unit</th><th>Cost/bd</th><th>Risk</th><th>Datasheet</th><th>Actions</th><th>Note</th></tr></thead><tbody>
    ${lines().map(l => { const b = best(l), q = qty(l);
      const refs = l.refs || [];
      const avail = l.availability || (status(l) === 'bad' ? 'none' : status(l) === 'warn' ? 'low' : status(l) === 'ok' ? 'ok' : 'unchecked');
      const dotCls = avail === 'ok' ? 'ok' : avail === 'low' ? 'warn' : avail === 'none' ? 'bad' : 'dim';
      const dotTip = `Availability: ${avail}${l.risk && l.risk.length ? ' · ' + l.risk.join(', ') : ''}${l.supply?.LCSC?.code_mismatch ? ' · ' + l.supply.LCSC.code_mismatch : ''}`;
      const lineCost = l.cost_per_board != null ? l.cost_per_board : (b ? b.price * q : null);
      const risks = l.risk || [];
      return `<tr data-key="${esc(l.key)}" class="${sel === l.key ? 'sel' : ''}">
        <td><span class="dot ${dotCls}" title="${esc(dotTip)}"></span></td>
        <td class="refs" title="${esc(refs.join(', '))}">${esc(refsLabel(refs))}</td>
        <td class="role"><input class="role-input" value="${esc(l.role || '')}" placeholder="Role in circuit" aria-label="Role ${esc(l.key)}" data-edit="role" data-line="${esc(l.key)}"></td>
        <td class="m">${esc(l.value)}</td><td>${esc(l.description)}</td>
        <td class="mpn"><input value="${esc(l.mpn)}" aria-label="MPN ${esc(l.key)}" data-edit="mpn" data-line="${esc(l.key)}"></td>
        <td class="m">${esc(l.package)}</td>
        <td><span class="lib ${l.library_type === 'Basic' || l.library_type === 'Preferred' ? 'ok' : l.library_type === 'Extended' ? 'warn' : 'std'}">${esc(l.library_type || '—')}</span></td>
        <td class="n">${l.dnp ? 'DNP' : q || '—'}</td>
        <td class="n ${avail === 'none' ? 'stock bad' : ''}">${q === 0 ? '—' : l.supply == null ? 'checking' : b ? `${num(b.stock)} <small>${b.s}</small>` : '0'}</td>
        <td class="n">${b ? money(b.price) : '—'}</td>
        <td class="n">${money(lineCost)}</td>
        <td>${risks.length ? risks.map(r => `<span class="tag ${r === 'out of stock' ? 'bad' : (r === 'low stock' || r === 'Extended fee' || r === CODE_RISK) ? 'warn' : 'plan'}"${r === CODE_RISK ? ` title="${esc(l.supply?.LCSC?.code_mismatch || '')}"` : ''}>${esc(r)}</span>`).join(' ') : '<span class="tag ok">ok</span>'}</td>
        <td>${l.datasheet ? chip(l.datasheet, '') : `<button class="btn" data-act="get-datasheet" data-line="${esc(l.key)}">Get datasheet</button>`}</td>
        <td><button class="btn" data-chat="${esc(l.key)}">Discuss</button> <button class="btn" data-act="alts" data-line="${esc(l.key)}">Alternatives</button></td>
        <td class="note"><input value="${esc(l.note)}" placeholder="Add a note" aria-label="Note ${esc(l.key)}" data-edit="note" data-line="${esc(l.key)}"></td></tr>`; }).join('')}
    </tbody></table></div>
    <p class="foot">Unit price at qty 10, shipping excluded. ${at ? 'Stock and prices checked ' + esc(at) + '; run Check stock again before any export.' : 'Not checked yet: run Check stock.'}</p>`
    : `<div class="dnote">The BOM is empty. Talk to the agent about the idea; it will propose parts and you approve them.</div>`}`;
}
function compareHTML() {
  const c = compareCard;
  return `<div class="howto"><b>Parts cost per board by supplier</b> (qty ${c.qty_break}, shipping excluded) <button class="x" data-act="closecard" aria-label="Close">×</button>
    <ul>${c.suppliers.map(r => `<li><b>${esc(r.supplier)}</b>: <span class="m">${money(r.cost_per_board)}</span>${r.not_checked.length ? ` · ${r.not_checked.length} lines not checked` : ''}${r.missing.length ? ` · missing: ${esc(r.missing.join(', '))}` : r.not_checked.length ? '' : ' · everything in stock'}</li>`).join('')}</ul></div>`;
}
function exportHTML() {
  const e = exportCard, name = e.file.split(/[\\/]/).pop();
  return `<div class="howto"><b>${esc(name)}</b> is ready: ${e.lines} lines. <a class="lnk" href="/api/export/${encodeURIComponent(name)}?${q()}">Download</a> <button class="x" data-act="closecard" aria-label="Close">×</button>
    ${e.left_out.length ? `<div>Left out (not fitted or not bought): <span class="m">${esc(e.left_out.join(', '))}</span></div>` : ''}
    ${e.needs_lcsc && e.needs_lcsc.length ? `<div>No LCSC number yet for: <span class="m">${esc(e.needs_lcsc.join(', '))}</span>. Run Check stock first.</div>` : ''}</div>`;
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('closecard', async (el, d, e) => {
  compareCard = exportCard = libExport = altsCard = null; render(true); return;
});
onAct('imp-scan', async (el, d, e) => {
  await loadImportInfo(true); toast('Looked for BOM files again'); return;
});
const runImport = async (el, d, e) => {
  const pick = $('#imp-csv'), csv = pick ? pick.value : impSel, apply = d.act === 'imp-apply';
  if (!csv) { toast('Pick a BOM file first'); return; }
  impSel = csv; impBusy = true; render(true);
  try {
    const r = await api('/api/bom/import', {csv, apply});
    impReport = r;
    if (r.state) setState(r.state);
    toast(apply ? `Imported ${r.imported_lines} lines from ${csv.split(/[\\/]/).pop()}` : 'Preview ready');
  } finally { impBusy = false; render(true); }
  return;
};
onAct('imp-preview', runImport);
onAct('imp-apply', runImport);
onAct('check-all', async (el, d, e) => {
  toast('Checking stock with JLC…'); { const r = await api('/api/parts/check', {}); setState(r); render(true); toast('Stock checked for all lines'); } return;
});
onAct('alts', async (el, d, e) => {
  const lineKey = el.dataset.line;
  const l = lineByKey(lineKey);
  altsCard = {line: lineKey, mpn: l ? l.mpn : '', loading: true, list: []};
  compareCard = exportCard = libExport = null;
  render(true);
  try {
    const list = await api(`/api/parts/alternatives?line=${encodeURIComponent(lineKey)}`);
    altsCard = {line: lineKey, mpn: l ? l.mpn : '', loading: false, list: Array.isArray(list) ? list : []};
  } catch (err) {
    altsCard = {line: lineKey, mpn: l ? l.mpn : '', loading: false, list: []};
  }
  render(true);
  return;
});
onAct('propose-alt', async (el, d, e) => {
  const lineKey = el.dataset.line;
  const mpn = el.dataset.mpn;
  const pkg = el.dataset.pkg;
  const desc = el.dataset.desc;
  const code = el.dataset.code;
  const libType = el.dataset.type;
  toast('Proposing alternative…');
  const res = await api('/api/bom/propose', {
    line: lineKey,
    changes: {mpn, package: pkg, description: desc},
    reason: `Alternative part proposed: ${code} (${libType || 'Standard'})`,
    sources: [`JLC ${code}`]
  });
  setState(res);
  altsCard = null;
  render(true);
  toast(`Proposed ${mpn} for line ${lineKey}`);
  return;
});
onAct('get-datasheet', async (el, d, e) => {
  const lineKey = el.dataset.line;
  toast('Fetching datasheet…');
  const res = await api('/api/parts/datasheet', {line: lineKey});
  if (res.error) {
    if (res.url) {
      alert(`Could not download datasheet automatically (${res.error}).\n\nPlease open this link, download the PDF, and upload it in Sources:\n${res.url}`);
    } else {
      toast('Could not find datasheet URL: ' + res.error);
    }
    return;
  }
  if (res.state) setState(res.state);
  render(true);
  toast('Datasheet added to ' + lineKey);
  return;
});
onAct('check', async (el, d, e) => {
  toast('Checking stock… this can take a little while'); { const r = await api('/api/skill', {name: 'check'}); setState(r.state); render(true);
    const errs = r.result.results.filter(x => x.error); toast('Stock checked' + (errs.length ? ` · ${errs.length} supplier error(s)` : '')); } return;
});
onAct('compare', async (el, d, e) => {
  { const r = await api('/api/skill', {name: 'compare'}); compareCard = r.result; exportCard = null; render(true); } return;
});
onAct('export', async (el, d, e) => {
  { const r = await api('/api/skill', {name: 'export_bom', args: [d.fmt]}); exportCard = r.result; compareCard = null; render(true); } return;
});
onChange(t => t.id === 'imp-csv', async e => {
  impSel = e.target.value; impReport = null; renderCenter(true); return;
});
onChange(t => t.closest('input[data-edit]'), async e => {
  const i = e.target.closest('input[data-edit]'); if (!i) return;
  const l = lineByKey(i.dataset.line); if (!l) return;
  const field = i.dataset.edit, val = i.value.trim();
  if (val === (l[field] ?? '') || (field === 'mpn' && !val)) return;
  try {
    setState(await api('/api/bom/edit', {line: l.key, field, value: val})); render(true);
    toast(field === 'mpn' ? `MPN updated. Checking stock for ${val}…` : 'Note saved');
    if (field === 'mpn') setTimeout(() => refresh(), 6000);
  } catch (err) { /* toasted */ }
});
