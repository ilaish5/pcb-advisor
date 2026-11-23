/* Pin decisions (stream B). One click confirms a part's pins: a dialog shows the datasheet page next to the pin table, with one
   "Pins match" button and an optional "this pin is wrong" per row. No reason is asked for and no pin has to be ticked; the server
   records the basis itself (scripts/pin_decisions.py). "Accept all remaining" is one confirm for every part still open.
   S.pin_decisions = {accepted: [{line, refs, mpn, basis, ts, reason, evidence}], remaining: [{line, refs, mpn, issues}]}. */
const PIN_BASIS = {datasheet_page: 'checked against a datasheet page', polarity: 'polarity accepted by you', blind: 'accepted without a datasheet', legacy: 'accepted earlier'};
function pinsWhen(ts) { return ts ? String(ts).slice(0, 10) : ''; }

/* the accepted risks, with Revoke: DFM and Outputs show them so an accepted risk never disappears from view */
function pinRisksHTML() {
  const rows = (S.pin_decisions || {}).accepted || [];
  if (!rows.length) return '';
  const item = r => `<li class="unv-row"><span class="m">${esc(refsLabel(r.refs))}</span> ${esc(r.mpn || '')}
    <span class="unv-why">${esc(PIN_BASIS[r.basis] || r.basis)}${r.ts ? ' on ' + esc(pinsWhen(r.ts)) : ''}${r.reason ? ': ' + esc(r.reason) : ''}</span>
    ${btn('Revoke', {kind: 'line', size: 'sm', act: 'revoke-pins', line: r.line, title: 'Take your decision back: the part is unverified again'})}</li>`;
  return `<section class="dfm-unv pin-risks"><h3>Accepted risks <span class="muted">(${rows.length}) pins you accepted, not verified by a datasheet table</span></h3>
    <ul>${rows.map(item).join('')}</ul></section>`;
}
/* the line of the part panel: what the student decided, and the way back */
function pinsInspHTML(l) {
  const d = l.pin_decision;
  if (!d) return '';
  return `<p class="insp-foot pin-dec">Pins ${esc(PIN_BASIS[d.basis] || d.basis)}${d.ts ? ' on ' + esc(pinsWhen(d.ts)) : ''}. ${btn('Revoke', {kind: 'link', size: 'sm', act: 'revoke-pins', line: l.key})}</p>`;
}
/* The Verify button, only where Verify can decide: a part with a linked datasheet that is not a diode/LED. Otherwise the way
   forward is to look at the page (Confirm pins), which also takes a datasheet attached later. */
function pinsOpen_(l) { return !!l && (l.pins_status === 'unverified' || l.pins_status === 'mismatch'); }
function pinsCanVerify(l) {      // Verify is foregone for a diode/LED (text cannot tell anode from cathode) and for a part with no datasheet
  if (!pinsOpen_(l)) return true;
  return !!l.datasheet && !((l.refs || []).length && (l.refs || []).every(r => /^(D|LED)\d/i.test(r)));
}
function pinsConfirmBtn(key, o) {
  const l = (S.bom || []).find(b => b.key === key);
  return pinsOpen_(l) ? btn('Confirm pins', {...o, act: 'confirm-pins', line: key, title: 'Look at the datasheet page next to the pins, then one click'}) : '';
}
/* what the Verify toast says: the result and its first reason, never the bare word "unchecked" */
function verifyToast(v) {
  v = v || {};
  const head = {pass: 'Pins verified against the datasheet', mismatch: 'Pins conflict with the datasheet', unchecked: 'Could not verify the pins'}[v.verify] || ('Result: ' + v.verify);
  const why = String(v.issues || '').split(/;\s|\.\s/)[0].trim();
  return head + (why && v.verify !== 'pass' ? ': ' + why.slice(0, 170) : '') + (v.verify === 'unchecked' ? '. Attach a datasheet or use Confirm pins.' : '');
}
function pinsAcceptAllBtn() {
  const n = ((S.pin_decisions || {}).remaining || []).length;
  return n > 1 ? btn(`Accept all remaining (${n})`, {kind: 'line', size: 'sm', act: 'accept-all-pins', title: 'One confirm for every part below that has no conflict with its datasheet'}) : '';
}

function pinsDialogHTML(d, page) {
  const doc = (d.docs || [])[0];
  const pages = doc ? doc.candidate_pages : [];
  const bad = doc && doc.quality && doc.quality.state !== 'good'
    ? `<p class="warn-t pins-note">${esc(doc.quality.why || 'The text of this datasheet cannot be read by the tool')}. Look at the page yourself.</p>` : '';
  const left = doc
    ? `<div class="pins-doc"><div class="pins-pages">${pages.length ? 'Pin pages: ' + pages.map(p => `<button type="button" class="btn sm${p === page ? ' pri' : ''}" data-pins-page="${p}">p.${p}</button>`).join(' ') : '<span class="muted">No pin page found by text: scroll the datasheet.</span>'}</div>
       <iframe class="pins-frame" title="${esc(doc.name)}" src="/api/source/${encodeURIComponent(doc.name)}?${q()}#page=${page || 1}"></iframe></div>`
    : `<div class="pins-doc pins-nodoc"><p class="muted">No datasheet is linked to this part, so there is no page to compare with.</p>
       <p class="muted">Pins match accepts the pins as they are drawn. It is kept as an accepted risk and can be revoked.</p></div>`;
  const rows = (d.pins || []).map(p => `<tr><td class="m">${esc(p.ref)}</td><td class="m">${esc(p.num)}</td><td class="m">${esc(p.name)}</td><td>${p.net ? `<span class="m">${esc(p.net)}</span>` : '<span class="muted">—</span>'}</td>
    <td><label class="pins-wrong"><input type="checkbox" data-pin-wrong="${esc(p.num)}"> wrong</label></td></tr>`).join('');
  const why = d.polarised ? '<p class="muted pins-note">Diode or LED: check which pin is the anode and which the cathode.</p>' : (d.issues ? `<p class="muted pins-note">${esc(d.issues)}</p>` : '');
  return `<form method="dialog"><h2>Confirm pins of ${esc(refsLabel(d.refs))} <span class="muted">${esc(d.mpn)}</span></h2>
    <div class="pins-body">${left}<div class="pins-tbl-w"><table class="tbl pins-tbl"><thead><tr><th>Part</th><th>Pin</th><th>Name</th><th>Net</th><th></th></tr></thead><tbody>${rows}</tbody></table>${why}${bad}</div></div>
    <div class="acts"><button type="button" class="btn" data-cancel>Cancel</button><button type="submit" class="btn pri" value="ok">Pins match</button></div></form>`;
}
let pinsOpen = false;
async function pinsConfirm(key) {
  if (pinsOpen) return;
  pinsOpen = true;
  try {
    const d = await api('/api/pins/confirm-data?line=' + encodeURIComponent(key));
    const doc = (d.docs || [])[0];
    let page = doc && doc.candidate_pages.length ? doc.candidate_pages[0] : 1;
    const dlg = document.createElement('dialog');
    dlg.className = 'dlg pins-dlg';
    const paint = () => { dlg.innerHTML = pinsDialogHTML(d, page); dlg.querySelector('[data-cancel]').addEventListener('click', () => dlg.close('cancel')); };
    paint();
    dlg.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('[data-pins-page]');
      if (b) { const wrong = [...dlg.querySelectorAll('[data-pin-wrong]:checked')].map(x => x.dataset.pinWrong); page = Number(b.dataset.pinsPage); paint(); wrong.forEach(n => { const c = dlg.querySelector(`[data-pin-wrong="${CSS.escape(n)}"]`); if (c) c.checked = true; }); }
    });
    const result = await new Promise(resolve => {
      dlg.addEventListener('close', () => {
        const wrong = [...dlg.querySelectorAll('[data-pin-wrong]:checked')].map(x => x.dataset.pinWrong);
        const ok = dlg.returnValue === 'ok';
        dlg.remove();
        resolve(ok ? {wrong, page} : null);
      });
      document.body.appendChild(dlg);
      dlg.showModal();
      dlg.querySelector('button[value="ok"]').focus();
    });
    if (!result) return;
    const ev = doc && !result.wrong.length ? [{doc: doc.name, sha256: doc.sha256, page: result.page}] : [];
    const r = await api('/api/pins/confirm', {line: key, evidence: ev, wrong: result.wrong});
    await refresh(true);
    toast(r.flagged ? `Marked pin ${r.flagged.join(', ')} as wrong: the part stays in the list` : 'Pins confirmed');
  } finally { pinsOpen = false; }
}
onAct('confirm-pins', async (el, d) => { await pinsConfirm(d.line); });
onAct('revoke-pins', async (el, d) => { await api('/api/pins/revoke', {line: d.line}); await refresh(true); toast('Decision revoked: the pins are unverified again'); });
onAct('accept-all-pins', async () => {
  const rows = (S.pin_decisions || {}).remaining || [];
  if (!rows.length) return;
  const names = rows.map(r => refsLabel(r.refs)).join(', ');
  const yes = await askChoice({title: `Accept ${rows.length} parts as they are drawn?`, text: `${names}. No datasheet pin table was checked for these. They stay listed as accepted risks and each can be revoked.`, yes: 'Accept all', no: 'Not now'});
  if (!yes) return;
  await api('/api/pins/accept-all', {confirm: true, lines: rows.map(r => r.line)});
  await refresh(true);
  toast(`${rows.length} parts accepted`);
});
