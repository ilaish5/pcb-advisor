/* PCB Advisor UI - readiness banner: on open, once, GET /api/readiness. Shows what does not work and the one step to fix it.
   Nothing is drawn when everything is ready. A dismissed problem stays hidden for that project (localStorage); a new problem shows. */

const READY_KEY = () => 'pcb-ready-dismissed:' + (PROJECT || '');
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

async function readyLoad() {
  let r = null;
  try { r = await api('/api/readiness', undefined, {soft: true}); } catch (err) { return; }
  const host = $('#ready');
  if (!host || !r || !Array.isArray(r.problems)) return;
  const seen = readyDismissed();
  const problems = r.problems.filter(p => !seen.includes(p.id));
  if (!problems.length) return;
  host.innerHTML = readyBannerHTML(problems);
  host.hidden = false;
  host.onclick = e => {
    if (e.target.closest('[data-ready-x]')) { readyDismiss(problems.map(p => p.id)); host.hidden = true; host.innerHTML = ''; return; }
    const go1 = e.target.closest('[data-ready-page]');
    if (go1) go(go1.dataset.readyPage);
  };
}
