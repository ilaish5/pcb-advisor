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

const READY_ALTIUM_IDS = ['altium', 'link'], READY_ALTIUM_VIEWS = ['sch', 'pcb', 'rules', 'outputs', 'checks', 'settings'];
let readyAll = [];
let readyRev = null, readyBusy = false;
function readyShow() {       // Altium problems show only on an Altium step (Schematic, Layout, Rules, Outputs); the others show wherever the user is
  const host = $('#ready');
  if (!host) return;
  if (S && S.rev && readyRev !== null && S.rev !== readyRev && !readyBusy) { readyRev = S.rev; readyLoad(); }       // the project changed under the banner: ask again
  const onAltium = typeof mainView === 'function' && (READY_ALTIUM_VIEWS.includes(mainView()) || (typeof sideView === 'function' && READY_ALTIUM_VIEWS.includes(sideView())));
  const seen = readyDismissed();
  const problems = readyAll.filter(p => !seen.includes(readyKey(p)) && (onAltium || !READY_ALTIUM_IDS.includes(p.id)));
  if (!problems.length) { if (!host.hidden) { host.hidden = true; host.innerHTML = ''; host.dataset.k = ''; } return; }
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
  readyShow();
}
