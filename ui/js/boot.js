/* PCB Advisor UI - boot: runs last. Immediate top-level code that needs every other file already loaded. */

initLayout();

// The first sheet: ?page= names a page or a stage, ?tab= a stage; with neither, an empty project opens on the idea.
function initialMain() {
  const p = URLQ.get('page'), t = URLQ.get('tab');
  if (p && PAGE_TITLES[p]) return pageItem(p);
  if (p && STAGE_TITLES[p]) return stageItem(p);
  if (t && STAGE_TITLES[t]) return stageItem(t);
  return stageItem(!S.idea.confirmed && !S.bom.length ? 'idea' : 'bom');
}

/* ---------- start ---------- */
(async function start() {
  try {
    const p = await (await fetch('/api/projects')).json();
    PROJECTS = p.projects || [];
    if (!PROJECT) PROJECT = p.default || (PROJECTS[0] && PROJECTS[0].name) || 'demo';
    const st = await api('/api/state'); setState(st);
    const [sk, cfg] = await Promise.all([api('/api/skills', undefined, {soft: true}), api('/api/config', undefined, {soft: true})]);
    SKILLS = sk.skills || []; CONFIG = cfg;
    initMain(initialMain());
    restoreSide();
    if (URLQ.get('sel')) sel = URLQ.get('sel');
    if (URLQ.get('sheet')) sheetId = URLQ.get('sheet');
    if (URLQ.get('convs')) convsOpen = true;
    render(true);
    updLoad(false);                // the server checked GitHub at its start: offer Update when this install is behind
  } catch (err) { document.body.innerHTML = '<p style="padding:20px">Could not load the project: ' + esc(err.message) + '</p>'; return; }
  setInterval(() => { if (!pending && !document.hidden) refresh(); }, 4000);
})();
