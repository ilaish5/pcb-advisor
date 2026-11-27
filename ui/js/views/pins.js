/* Pin decisions (stream B). One click confirms a part's pins: a dialog shows the datasheet page next to the pin table, with one
   "Pins match" button and an optional "this pin is wrong" per row. No reason is asked for and no pin has to be ticked; the server
   records the basis itself (scripts/pin_decisions.py). "Accept all remaining" is one confirm for every part still open.
   S.pin_decisions = {accepted: [{line, refs, mpn, basis, ts, reason, evidence}], remaining: [{line, refs, mpn, issues}]}. */
const PIN_BASIS = {datasheet_page: 'checked against a datasheet page', polarity: 'polarity accepted by you', blind: 'accepted without a datasheet', legacy: 'accepted earlier', library_model: 'matches the library model of its LCSC part'};
function pinsWhen(ts) { return ts ? whenText(ts) : ''; }

/* the accepted pins, with Revoke: DFM and Outputs show them so an accepted risk never disappears from view. Split by basis: a part the
   student checked against a datasheet page is NOT "not verified by a datasheet" (E12, 24/11/2026); the rest (polarity, blind, legacy) are. */
const PIN_PAGE_CHECKED = r => r.basis === 'datasheet_page';
function pinRisksList(rows, head, note) {
  if (!rows.length) return '';
  const item = r => `<li class="unv-row"><span class="m">${esc(refsLabel(r.refs))}</span> ${esc(r.mpn || '')}
    <span class="unv-why">${esc(PIN_BASIS[r.basis] || r.basis)}${r.ts ? ' on ' + esc(pinsWhen(r.ts)) : ''}${r.reason ? ': ' + esc(r.reason) : ''}</span>
    ${btn('Revoke', {kind: 'line', size: 'sm', act: 'revoke-pins', line: r.line, title: 'Take your decision back: the part is unverified again'})}</li>`;
  return `<section class="dfm-unv pin-risks"><h3>${head} <span class="muted">(${rows.length}) ${note}</span></h3>
    <ul>${rows.map(item).join('')}</ul></section>`;
}
function pinRisksHTML() {
  const rows = (S.pin_decisions || {}).accepted || [];
  if (!rows.length) return '';
  return pinRisksList(rows.filter(PIN_PAGE_CHECKED), 'Checked by you', 'pins you checked against a datasheet page')
    + pinRisksList(rows.filter(r => !PIN_PAGE_CHECKED(r)), 'Accepted risks', 'pins you accepted without checking a datasheet page');
}
/* the line of the part panel: what the student decided, and the way back */
function pinsInspHTML(l) {
  const d = l.pin_decision;
  if (!d && l.pins_basis === 'library_model') return `<p class="insp-foot pin-dec">Pins ${esc(PIN_BASIS.library_model)}${l.lcsc ? ' (' + esc(l.lcsc) + ')' : ''}: nothing to confirm.</p>`;
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
/* The waiting line, on every page that shows the waiting parts (Library, DFM, Outputs): one sentence and one button for everything the
   server cannot settle itself. S.pin_decisions.waiting = {questions, own_look, auto_verified, fetchable, groups: [{id, lines, refs, mpn,
   status, issues, kind, blind, own_look, count}], bulk: [line], blind: [ref]} (scripts/pin_decisions.py waiting). Identical parts are one
   group, so five LEDs read "D1-D5" and count as one question. A mismatch is never in the bulk: its own row has its own button. */
function pinsWaiting() { return (S.pin_decisions || {}).waiting || null; }
function pinsBulkGroups() { const w = pinsWaiting(); return w ? (w.groups || []).filter(g => !g.own_look) : []; }
/* THE counts (E11): the server's store.pin_counts, never one of our own. While a decision or a re-check is on its way to the server the
   numbers on screen are old, so they are not shown at all until the fresh state is in (pinsBusy): no 26, then 8, then 1. */
let pinsBusy = 0;
function pinsCount(kind) { const w = pinsWaiting(); return w ? (w[kind || 'parts'] || 0) : 0; }
function pinsNum(n) { return pinsBusy ? '…' : String(n); }
async function pinsWhile(fn) { pinsBusy++; try { return await fn(); } finally { pinsBusy--; } }
function pinsConfirmAllBtn(o) {
  const g = pinsBulkGroups();
  const n = pinsCount('to_confirm');
  return n ? btn(g.length > 1 || n > 1 ? `Confirm all (${pinsNum(n)})` : 'Confirm', {kind: 'line', size: 'sm', act: 'accept-all-pins', disabled: !!pinsBusy, ...(o || {}),
    title: 'Accepts the pins of every part named here as they are drawn. Each stays listed as an accepted risk and can be revoked.'}) : '';
}
function pinsAcceptAllBtn() { return pinsConfirmAllBtn(); }       // the name the DFM list used
function pinsWaitingBar() {
  const w = pinsWaiting();
  if (!w || !w.questions) return '';
  const g = pinsBulkGroups(), own = (w.groups || []).filter(x => x.own_look);
  const n = pinsCount('to_confirm'), nOwn = pinsCount('conflicts');
  const names = g.slice(0, 6).map(x => refsLabel(x.refs)).join(', ') + (g.length > 6 ? ` and ${g.length - 6} more` : '');
  const head = n ? `<strong>${pinsNum(n)} ${n === 1 ? 'part waits' : 'parts wait'} for your confirmation</strong> <span class="m">${esc(names)}</span>` : '';
  const ownTxt = nOwn ? `${n ? ' · ' : ''}<strong>${pinsNum(nOwn)} ${nOwn === 1 ? 'part needs' : 'parts need'} your own look</strong> <span class="m">${esc(own.map(x => refsLabel(x.refs)).join(', '))}</span>` : '';
  const auto = w.auto_verified ? `<span class="muted"> · ${w.auto_verified} already matched ${w.auto_verified === 1 ? 'its' : 'their'} library model</span>` : '';
  const fetch = w.fetchable ? btn(dfmRecheckBusyNow() ? 'Fetching…' : 'Fetch datasheets', {kind: 'line', size: 'sm', act: 'recheck-pins', title: 'The tool downloads the datasheet itself and checks the pins against it'}) : '';
  return `<div class="pins-bar" role="status"><span class="pins-bar-t">${head}${ownTxt}${auto}</span>${pinsConfirmAllBtn()}${fetch}</div>`;
}
function dfmRecheckBusyNow() { return typeof dfmRecheckBusy !== 'undefined' && dfmRecheckBusy; }
/* a row that needs its own look (a mismatch): its own pin button (the quick preview and the part panel) */
function pinsOwnLookBtn(key, o) {
  const l = (S.bom || []).find(b => b.key === key);
  return l && l.pins_status === 'mismatch' ? btn('Confirm pins', {...o, act: 'confirm-pins', line: key, title: 'Look at the conflict, then one click'}) : '';
}

/* The datasheet opens at the pin page, fitted to the width of the frame with the viewer's own sidebar closed (PDF open parameters), in a
   dialog that takes nearly the whole window: the page is readable without a click or a scroll. The pin table sits beside it in sheet
   order, so each row can be compared with the page one after the other. */
const PINS_PDF_PARAMS = 'zoom=page-width&view=FitH&pagemode=none&navpanes=0';
function pinsDocUrl(doc, page) { return `/api/source/${encodeURIComponent(doc.name)}?${q()}#page=${page || 1}&${PINS_PDF_PARAMS}`; }
function pinsDialogHTML(d, page) {
  const doc = (d.docs || [])[0];
  const pages = doc ? doc.candidate_pages : [];
  const bad = doc && doc.quality && doc.quality.state !== 'good'
    ? `<p class="warn-t pins-note">${esc(doc.quality.why || 'The text of this datasheet cannot be read by the tool')}. Look at the page yourself.</p>` : '';
  const left = doc
    ? `<div class="pins-doc"><div class="pins-pages">${pages.length ? 'Pin pages: ' + pages.map(p => `<button type="button" class="btn sm${p === page ? ' pri' : ''}" data-pins-page="${p}">p.${p}</button>`).join(' ') : '<span class="muted">No pin page found by text: scroll the datasheet.</span>'}
       <a class="pins-open" href="${pinsDocUrl(doc, page)}" target="_blank" rel="noopener">Open in a new tab</a></div>
       <iframe class="pins-frame" title="${esc(doc.name)}" src="${pinsDocUrl(doc, page)}"></iframe></div>`
    : `<div class="pins-doc pins-nodoc"><p class="muted">${d.missing_doc
      ? `The datasheet ${esc(d.missing_doc)} is linked to this part but its file is not on this computer, so there is no page to compare with. Attach the file on the Sources page.`
      : 'No datasheet is linked to this part, so there is no page to compare with.'}</p>
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
    if (!d.wired) { toast(`Nothing to confirm yet: no pin of ${refsLabel(d.refs)} is wired. It is asked about once a pin is connected.`); return; }
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
    let reason = '';
    if (!ev.length && !result.wrong.length) {        // no datasheet page to cite: the student's own sentence is the record
      reason = await askText({title: `Accept ${refsLabel(d.refs)} on your word?`, label: 'Why is it fine?', placeholder: 'e.g. I checked the pins against the datasheet', confirm: 'Accept'});
      if (!reason) return;
    }
    const r = await pinsWhile(async () => { const x = await api('/api/pins/confirm', {line: key, evidence: ev, wrong: result.wrong, ...(reason ? {reason} : {})}); await refresh(true); return x; });
    render(true);
    toast(r.flagged ? `Marked pin ${r.flagged.join(', ')} as wrong: the part stays in the list` : 'Pins confirmed');
  } finally { pinsOpen = false; }
}
onAct('confirm-pins', async (el, d) => { await pinsConfirm(d.line); });
onAct('revoke-pins', async (el, d) => { await pinsWhile(async () => { await api('/api/pins/revoke', {line: d.line}); await refresh(true); }); render(true); toast('Decision revoked: the pins are unverified again'); });
/* One click. Only when the line holds a part nothing but the student's word settles (an IC with no datasheet check) is the click
   asked once more, naming those parts: that is a real engineering check the click would skip. Anything else is done at once, with Undo. */
function pinsAcceptTitle(n, w) {
  const one = (pinsBulkGroups()[0] || {}).refs || [];
  return `Accept ${n === 1 && one.length === 1 ? one[0] : n + ' parts'} on your word?`;
}
function pinsAcceptText(blind) {
  return `${blind.join(', ')}: no datasheet pin table was checked for ${blind.length === 1 ? 'this part' : 'these parts'}. Every part accepted here stays listed as an accepted risk and can be revoked.`;
}
onAct('accept-all-pins', async () => {
  const w = pinsWaiting();
  const lines = w ? w.bulk || [] : ((S.pin_decisions || {}).remaining || []).map(r => r.line);
  if (!lines.length) return;
  const blind = w ? w.blind || [] : [];
  // No datasheet pin table backs this click, so the student says in a sentence why it is fine: that sentence is the record. Never invented.
  const n = pinsCount('to_confirm') || blind.length || lines.length;
  const named = blind.length > 0;
  const ask = {title: named ? pinsAcceptTitle(n, w) : `Accept ${n === 1 ? 'this part' : n + ' parts'} on your word?`, label: 'Why is it fine?',
    placeholder: 'e.g. I checked the pins against the datasheet', hint: named ? pinsAcceptText(blind) : 'It stays listed as an accepted risk and can be revoked.', confirm: 'Accept all'};
  const reason = await askText(ask);
  if (!reason) return;
  let r = null;
  await pinsWhile(async () => { if (typeof render === 'function') render(true); r = await api('/api/pins/accept-all', {confirm: true, lines, reason}); await refresh(true); });
  if (typeof render === 'function') render(true);
  const done = (r && r.accepted) || lines;
  toast(`${done.length} ${done.length === 1 ? 'part' : 'parts'} confirmed`, {label: 'Undo', onClick: async () => {
    for (const l of done) await api('/api/pins/revoke', {line: l});
    await refresh(true);
    toast('Decisions revoked: the pins are unverified again');
  }});
});
