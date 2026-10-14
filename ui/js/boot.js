/* PCB Advisor UI - boot: runs last. Immediate top-level code that needs every other file already loaded. */

initResize();

/* ---------- start ---------- */
(async function start() {
  try {
    const p = await (await fetch('/api/projects')).json();
    PROJECTS = p.projects || [];
    if (!PROJECT) PROJECT = p.default || (PROJECTS[0] && PROJECTS[0].name) || 'demo';
    const st = await api('/api/state'); setState(st);
    const [sk, cfg] = await Promise.all([api('/api/skills', undefined, {soft: true}), api('/api/config', undefined, {soft: true})]);
    SKILLS = sk.skills || []; CONFIG = cfg;
    if (!S.idea.confirmed && !S.bom.length) tab = 'idea';
    if (URLQ.get('page')) page = URLQ.get('page');
    if (URLQ.get('tab')) tab = URLQ.get('tab');
    if (URLQ.get('sel')) sel = URLQ.get('sel');
    if (URLQ.get('sheet')) sheetId = URLQ.get('sheet');
    if (URLQ.get('convs')) convsOpen = true;
    if (page === 'settings') loadAltium();
    render(true);
  } catch (err) { document.body.innerHTML = '<p style="padding:20px">Could not load the project: ' + esc(err.message) + '</p>'; return; }
  setInterval(() => { if (!pending && !document.hidden) refresh(); }, 4000);
})();
