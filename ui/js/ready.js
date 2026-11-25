/* PCB Advisor UI - readiness banner: GET /api/readiness on open and again whenever the server's S.rev changes (a link made, a file
   saved, a log grown). Shows what does not work and the one step to fix it. Nothing is drawn when everything is ready.
   A Dismiss is kept per problem instance (id:instance, localStorage, per project): the same problem stays hidden, one that comes back
   with other words (or after it was fixed and broke again) shows. */

const READY_KEY = () => 'pcb-ready-dismissed:' + (PROJECT || '');
const readyKey = p => p.id + ':' + (p.instance || '');
function readyDismissed() {
  try { const v = JSON.parse(localStorage.getItem(READY_KEY()) || '[]'); return Array.isArray(v) ? v : []; } catch (err) { return []; }
}
function readyDismiss(ids) {
  try { localStorage.setItem(READY_KEY(), JSON.stringify([...new Set([...readyDismissed(), ...ids])])); } catch (err) { /* private window: it shows again next time */ }
}

function readyBannerHTML(problems) {
  const rows = problems.map(p => `<li><b>${esc(p.title)}</b> <span class="ready-fix">${esc(p.fix)}</span>` +
    (p.page ? ` <button type="button" class="ready-go" data-ready-page="${esc(p.page)}">Open ${esc(p.page === 'settings' ? 'Settings' : p.page)}</button>` : '') + '</li>').join('');
  return `<div class="ready-bar" role="alert"><ul>${rows}</ul><button type="button" class="ready-x" data-ready-x aria-label="Dismiss">Dismiss</button></div>`;
}

/* A problem the student cannot act on from where they are (the project is not linked to Altium) is shown ONCE per project and instance,
   not on every page load: the keys already shown on an earlier load are remembered, those shown on this load stay until dismissed. */
const READY_ONCE_IDS = ['link'];
const READY_SHOWN_KEY = () => 'pcb-ready-shown:' + (PROJECT || '');
let readyShownBefore = null, readyShownNow = new Set();
function readySeenBefore() {
  if (readyShownBefore === null) {
    try { const v = JSON.parse(localStorage.getItem(READY_SHOWN_KEY()) || '[]'); readyShownBefore = new Set(Array.isArray(v) ? v : []); } catch (err) { readyShownBefore = new Set(); }
  }
  return readyShownBefore;
}
function readyRemember(keys) {
  const fresh = keys.filter(k => !readyShownNow.has(k));
  if (!fresh.length) return;
  fresh.forEach(k => readyShownNow.add(k));
  try { localStorage.setItem(READY_SHOWN_KEY(), JSON.stringify([...new Set([...readySeenBefore(), ...readyShownNow])])); } catch (err) { /* it shows again next time */ }
}
const readyOnceHidden = p => READY_ONCE_IDS.includes(p.id) && readySeenBefore().has(readyKey(p)) && !readyShownNow.has(readyKey(p));
const READY_ALTIUM_IDS = ['altium', 'link'], READY_ALTIUM_VIEWS = ['sch', 'pcb', 'rules', 'outputs', 'checks', 'settings'];
let readyAll = [];
let readyRev = null, readyBusy = false;
function readyShow() {       // Altium problems show only on an Altium step (Schematic, Layout, Rules, Outputs); the others show wherever the user is
  const host = $('#ready');
  if (!host) return;
  if (S && S.rev && readyRev !== null && S.rev !== readyRev && !readyBusy) { readyRev = S.rev; readyLoad(); }       // the project changed under the banner: ask again
  const onAltium = typeof mainView === 'function' && (READY_ALTIUM_VIEWS.includes(mainView()) || (typeof sideView === 'function' && READY_ALTIUM_VIEWS.includes(sideView())));
  const seen = readyDismissed();
  const problems = readyAll.filter(p => !seen.includes(readyKey(p)) && !readyOnceHidden(p) && (onAltium || !READY_ALTIUM_IDS.includes(p.id)));
  if (!problems.length) { if (!host.hidden) { host.hidden = true; host.innerHTML = ''; host.dataset.k = ''; } return; }
  readyRemember(problems.filter(p => READY_ONCE_IDS.includes(p.id)).map(readyKey));
  const html = readyBannerHTML(problems);
  if (host.dataset.k !== html) { host.dataset.k = html; host.innerHTML = html; }
  host.hidden = false;
  host.onclick = e => {
    if (e.target.closest('[data-ready-x]')) { readyDismiss(problems.map(readyKey)); readyShow(); return; }
    const go1 = e.target.closest('[data-ready-page]');
    if (go1) go(go1.dataset.readyPage);
  };
}
async function readyLoad() {
  if (readyBusy) return;
  readyBusy = true;
  readyRev = (S && S.rev) || '';
  let r = null;
  try { r = await api('/api/readiness', undefined, {soft: true}); } catch (err) { return; } finally { readyBusy = false; }
  if (!r || !Array.isArray(r.problems)) return;
  readyAll = r.problems;
  const gone = new Set(readyAll.map(readyKey));      // a problem that was fixed is forgotten: if it comes back, it is shown again
  readyShownNow.forEach(k => { if (!gone.has(k)) readyShownNow.delete(k); });
  readyShownBefore = new Set([...readySeenBefore()].filter(k => gone.has(k)));
  try { localStorage.setItem(READY_SHOWN_KEY(), JSON.stringify([...new Set([...readyShownBefore, ...readyShownNow])])); } catch (err) { /* ignored */ }
  readyShow();
}
