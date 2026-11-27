/* PCB Advisor UI - the Findings list (the ledger): what is open, what you did, what you accepted, and what the tool cannot do.
   State: S.ledger = {counts, items[]} from the server (scripts/ledger.py); the limits come from /api/limits (scripts/limits.py).
   A finding moves open -> "Done, check again" -> closed (only when the tool re-checked the file), or -> accepted with a reason. */

let ledgerLimits = [];          // [{id, title, page, says, instead, status, item}]
let ledgerLimitsKey = '';
let ledgerBusy = '';            // the id of the item whose check is running

const LEDGER_STATE = {open: ['Open', 'warn'], student_fixed: ['Waiting for the check', 'warn'], closed: ['Closed', 'ok'], accepted: ['Accepted', '']};

async function ledgerLoadLimits() {
  const key = String(PROJECT) + '|' + ((S && S.ledger && S.ledger.items) || []).map(i => i.id + i.state).join(',');
  if (key === ledgerLimitsKey) return;
  ledgerLimitsKey = key;
  try {
    const r = await api('/api/limits', undefined, {soft: true});
    if (r && Array.isArray(r.limits)) { ledgerLimits = r.limits; if (typeof render === 'function') render(true); }
  } catch (e) { /* the page works without the list */ }
}

function ledgerItemHTML(it) {
  const [stateText, tone] = LEDGER_STATE[it.state] || [it.state, ''];
  const busy = ledgerBusy === it.id;
  const check = it.check_result && it.check_result.detail ? `<p class="muted lg-check">${esc(it.check_result.status === 'pass' ? 'Checked: ' : it.check_result.status === 'fail' ? 'Checked, still there: ' : 'Not checked: ')}${esc(it.check_result.detail)}</p>` : '';
  const conflict = it.conflict ? `<p class="warn-t lg-conflict">Do not do this: it breaks a rule of this tool (${esc(it.conflict.rule)}). ${esc(it.conflict.why)}</p>` : '';
  const reason = it.state === 'accepted' ? `<p class="muted lg-reason">Accepted because: ${esc(it.reason)}</p>` : '';
  const open = it.state === 'open' || it.state === 'student_fixed';
  const acts = open
    ? (it.kind === 'limit' ? '' : btn(busy ? 'Checking...' : 'Done, check again', {kind: 'line', size: 'sm', act: 'ledger-done', lid: it.id, disabled: busy || undefined,
        title: 'The tool checks the file again as it is now. Only a check that passes closes this finding.'})) +
      btn('Accept with a reason', {kind: 'link', size: 'sm', act: 'ledger-accept', lid: it.id, jlc: it.jlc_reject ? '1' : undefined,
        title: it.jlc_reject ? 'The fab may reject this. You need a reason and to confirm making it anyway.' : 'You say in a sentence why this is fine. It is kept with the outputs.'})
    : it.state === 'accepted' ? btn('Open it again', {kind: 'link', size: 'sm', act: 'ledger-reopen', lid: it.id}) : '';
  const hist = (it.history || []).slice(-6).map(h => `<li><span class="m">${esc(String(h.ts || '').replace('T', ' ').slice(0, 16))}</span> ${esc(h.note || h.state)}</li>`).join('');
  return `<li class="lg-item" data-lg="${esc(it.id)}" data-state="${esc(it.state)}"><div class="lg-head"><span class="chip m">${esc(it.id)}</span> <strong>${esc(it.title)}</strong>
    <span class="tag ${tone}">${esc(stateText)}</span></div>${conflict}${check}${reason}
    <details class="lg-more"><summary>Details</summary><p>${esc(it.detail || 'No more detail.')}</p><ul class="lg-hist">${hist}</ul></details>
    <div class="acts">${acts}</div></li>`;
}

function ledgerLimitHTML(l) {
  const tracked = l.item ? `<span class="chip m">${esc(l.item.id)}</span> <span class="tag">${esc((LEDGER_STATE[l.item.state] || [l.item.state])[0])}</span>` : '';
  if (l.status === 'works') return '';
  return `<li class="lg-limit" data-limit="${esc(l.id)}"><strong>${esc(l.title)}</strong> <span class="tag">Not automated</span> ${tracked}
    <p class="muted">${esc(l.says)} ${esc(l.instead)}</p>${l.item ? '' : btn('Add to my list', {kind: 'link', size: 'sm', act: 'ledger-limit', lid: l.id, title: 'Keeps this on your Findings list so it is not forgotten'})}</li>`;
}

/* The card of one page: its open findings, the limits that belong to it. On Outputs: every open finding of the project. */
function ledgerCardHTML(page) {
  ledgerLoadLimits();
  const L = (S && S.ledger) || {counts: {}, items: []};
  const all = page === 'outputs';
  const items = (L.items || []).filter(i => (all || i.page === page) && i.kind !== 'limit' || (all && i.kind === 'limit'));
  const open = items.filter(i => i.state === 'open' || i.state === 'student_fixed');
  const lims = all ? [] : ledgerLimits.filter(l => l.page === page && l.status !== 'works');
  if (!items.length && !lims.length) return '';
  const head = all ? `Findings: ${open.length} open${L.counts && L.counts.accepted ? `, ${L.counts.accepted} accepted` : ''}` : 'Findings on this page';
  return `<section class="lg-card" data-ledger="${esc(page)}" aria-label="Findings"><h3>${esc(head)}</h3>
    ${items.length ? `<ul class="lg-list">${items.map(ledgerItemHTML).join('')}</ul>` : ''}
    ${lims.length ? `<details class="lg-limits"${items.length ? '' : ' open'}><summary>What the tool does not do here (${lims.length})</summary><ul class="lg-list">${lims.map(ledgerLimitHTML).join('')}</ul></details>` : ''}</section>`;
}

onAct('ledger-done', async (el, d) => {
  ledgerBusy = d.lid;
  if (typeof render === 'function') render(true);
  try {
    const r = await api('/api/ledger/done', {id: d.lid}, {soft: true});
    if (r && r.error) toast(r.error, null, {bad: true});
    else if (r && r.check_result) toast(r.state === 'closed' ? `${r.id} closed: the file was checked again.` : `${r.id}: ${r.check_result.detail}`, null, {bad: r.state !== 'closed'});
  } catch (e) { toast('The check could not run: ' + e.message, null, {bad: true}); }
  ledgerBusy = '';
  await refresh(true);
});
onAct('ledger-accept', async (el, d) => {
  const reason = await askText({title: 'Accept this finding', label: 'Why is it fine? (one sentence)', placeholder: 'For example: JLC accepts this gap for this board', confirm: 'Accept',
    hint: 'The reason is kept with the outputs. If you change the board file afterwards, the finding opens again.'});
  if (!reason) return;
  let anyway = false;
  if (d.jlc) {
    const ok = await askChoice({title: 'The fab may reject this', text: 'JLC may refuse or change the board because of this finding. Make it anyway?', yes: 'Make it anyway', no: false});
    if (!ok) return;
    anyway = true;
  }
  const r = await api('/api/ledger/accept', {id: d.lid, reason, make_anyway: anyway}, {soft: true});
  if (r && r.error) { toast(r.error, null, {bad: true}); return; }
  await refresh(true);
});
onAct('ledger-reopen', async (el, d) => { await api('/api/ledger/reopen', {id: d.lid}); await refresh(true); });
onAct('ledger-limit', async (el, d) => {
  await api('/api/limits/hit', {id: d.lid, context: 'added from the page'});
  ledgerLimitsKey = '';
  await refresh(true);
});
onAct('ledger-show', () => {
  const el = document.querySelector('[data-ledger]');
  if (el) { el.scrollIntoView({block: 'start', behavior: 'smooth'}); el.setAttribute('tabindex', '-1'); el.focus({preventScroll: true}); }
});

/* Every stage and page shows its Findings card, whatever its own renderer drew (so a limit is stated on the page where its control lives, not in chat only). */
function ledgerAppendCard(container, page) {
  if (!container || !page || typeof ledgerCardHTML !== 'function') return;
  const old = container.querySelector('[data-ledger-auto]');
  if (old) old.remove();
  if (container.querySelector('[data-ledger="' + page + '"]')) return;       // the page drew its own
  const html = ledgerCardHTML(page);
  if (!html) return;
  const w = document.createElement('div');
  w.setAttribute('data-ledger-auto', page);
  w.className = 'vb';
  w.innerHTML = html;
  container.appendChild(w);
}
