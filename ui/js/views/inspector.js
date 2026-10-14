/* Inspector: the right-hand drawer (#detail) for the selected part. core.js renderDetail() asks inspectorHTML()
   and hides the drawer when it returns ''. */

function inspectorHTML() {
  const actTab = getActiveTab();
  const isTabRelevant = actTab && ((actTab.kind === 'stage' && (actTab.stage === 'bom' || actTab.stage === 'sch' || actTab.stage === 'pcb')) || (actTab.kind === 'page' && actTab.page === 'library'));
  const show = !!sel && lineByKey(sel) && (isTabRelevant || ((page === 'workspace' && (tab === 'bom' || tab === 'sch' || tab === 'pcb')) || page === 'library'));
  return show ? detailHTML() : '';
}

function detailHTML() {
  const l = lineByKey(sel); if (!l) return '';
  const b = best(l), where = sheetsOfLine(l);
  const nets = [...new Set(where.flatMap(w => w.nets || []))];
  const e = l.library_entry || {};
  const mk = v => v ? '<b class="y">✓</b>' : '<b class="nn">✗</b>';
  const refs = l.refs || [];
  return `<div class="dt">
    <div class="dt-h"><div><div class="refs">${esc(refs.join(', '))}</div><h3>${esc(l.mpn)}</h3><p>${esc(l.manufacturer)} · ${esc(l.package)} · ${esc(l.description)}</p></div><button class="x" data-act="close" aria-label="Close">×</button></div>
    <div class="dt-a"><button class="btn pri" data-act="ask-anchor" data-anchor="${esc(l.key)}">Ask about this</button><button class="btn" data-chat="${esc(l.key)}">Discuss this part</button><button class="btn" data-act="alts" data-line="${esc(l.key)}">Alternatives</button>${where.length ? `<button class="btn" data-show="${esc(l.key)}">Show on schematic</button>` : ''}</div>
    ${l.role ? `<div class="dsec"><h4>Role</h4><div class="dnote">${esc(l.role)}</div></div>` : ''}
    ${where.length ? `<div class="dsec"><h4>Where it's used</h4><div class="where">${where.map(w => `<button data-show="${esc(l.key)}"><span class="r">${esc(w.ref)}</span><span class="s">Sheet ${esc(w.sheet)} · ${esc(w.section)}${w.title ? ' · ' + esc(w.title) : ''}</span></button>`).join('')}</div></div>` : ''}
    ${nets.length ? `<div class="dsec"><h4>Nets</h4><div class="netl">${nets.map(n => `<button class="secb" data-net="${esc(n)}" style="cursor:pointer">${esc(n)}</button>`).join('')}</div></div>` : ''}
    ${qty(l) ? `<div class="dsec"><h4>Stock and price</h4>${l.supply == null ? '<div class="dnote">Checking… the agent re-checks stock when the MPN changes. You can also press Check stock.</div>' : `<table class="sup"><thead><tr><th>Supplier</th><th style="text-align:right">Stock</th><th style="text-align:right">Unit @10</th></tr></thead><tbody>
      ${SUPS.map(s => { const v = l.supply[s]; return `<tr class="${b && b.s === s ? 'best' : ''}"><td>${s}</td><td class="n">${v ? num(v.stock) : 'not checked'}</td><td class="n">${v ? money(v.unit_price) : '—'}</td></tr>`; }).join('')}
      </tbody></table><div class="checked">Checked ${esc(b ? (b.at || '').replace('T', ' ').slice(0, 16) : checkedAt() || '')}${b ? ` · cheapest: ${b.s}` : ' · no supplier has stock'}</div>`}</div>` : ''}
    <div class="dsec"><h4>Library</h4>${l.library === 'std' ? `<div class="dnote">Standard part from Altium's default libraries.</div>` :
      `<div class="libg"><div>Symbol${mk(e.symbol)}</div><div>Footprint${mk(e.footprint)}</div><div>3D${e.step ? '<b class="y">STEP</b>' : '<b class="q">Simple</b>'}</div></div>
       <div class="checked">Model from ${esc(e.model_source || '—')} · <span class="lib ${esc(l.library)}">${esc(LIBTXT[l.library])}</span></div>${e.issues ? `<div class="dnote issue">${esc(e.issues)}</div>` : ''}`}</div>
    <div class="dsec"><h4>Datasheet</h4>${l.datasheet ? chip(l.datasheet, '') : `<div style="display:flex;align-items:center;gap:8px"><div class="dnote" style="flex:1">None stored.</div><button class="btn" data-act="get-datasheet" data-line="${esc(l.key)}">Get datasheet</button></div>`}</div>
    ${l.note ? `<div class="dsec"><h4>Note</h4><div class="dnote">${esc(l.note)}</div></div>` : ''}
  </div>`;
}

/* ---------- action handlers ---------- */
onAct('ask-anchor', async (el, d, e) => {
  if (d.anchor) openPart(d.anchor); return;
});
onAct('close', async (el, d, e) => {
  sel = null; renderDetail(); document.querySelectorAll('#view tr.sel').forEach(r => r.classList.remove('sel')); applyFocus(); return;
});
