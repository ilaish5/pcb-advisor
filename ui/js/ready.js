/* PCB Advisor UI - readiness banner: on open, once, GET /api/readiness. Shows what does not work and the one step to fix it.
   Nothing is drawn when everything is ready. Dismissing hides it until the page is opened again. */

function readyBannerHTML(problems) {
  const rows = problems.map(p => `<li><b>${esc(p.title)}</b> <span class="ready-fix">${esc(p.fix)}</span>` +
    (p.page ? ` <button type="button" class="ready-go" data-ready-page="${esc(p.page)}">Open ${esc(p.page === 'settings' ? 'Settings' : p.page)}</button>` : '') + '</li>').join('');
  return `<div class="ready-bar" role="alert"><ul>${rows}</ul><button type="button" class="ready-x" data-ready-x aria-label="Dismiss">Dismiss</button></div>`;
}

async function readyLoad() {
  let r = null;
  try { r = await api('/api/readiness', undefined, {soft: true}); } catch (err) { return; }
  const host = $('#ready');
  if (!host || !r || !Array.isArray(r.problems) || !r.problems.length) return;
  host.innerHTML = readyBannerHTML(r.problems);
  host.hidden = false;
  host.onclick = e => {
    if (e.target.closest('[data-ready-x]')) { host.hidden = true; host.innerHTML = ''; return; }
    const go1 = e.target.closest('[data-ready-page]');
    if (go1) go(go1.dataset.readyPage);
  };
}
