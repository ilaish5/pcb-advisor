/* PCB Advisor UI - shell: the app frame.
   Layout: navigation (left) | main sheet, plus an optional side sheet | chat column (right).
   What lives here: the stage trace and its status dots, what each sheet shows (mainItem / sideItem), go() and openSide(),
   the chat column (show, hide, resize, drawer and one-column modes) and the nav foot.
   Globals other files use: go, select (core.js), mainView, sideView, setView, showChat, hideChat, toggleChat, stageStatus,
   openSide, closeSide, toggleSide, openFileAsTab, renderStage, renderPage, guidanceBarHTML, resetLayout, getActiveTab. */

if (typeof KIT_ICONS === 'object' && !KIT_ICONS.swap) KIT_ICONS.swap = '<path d="M3 8h17M16 4l4 4-4 4M21 16H4M8 12l-4 4 4 4"/>';

/* ---------- browser storage: UI preferences only (layout, what the side sheet shows). Every access can throw. ---------- */
function lsGet(key) {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    return null;
  }
}
function lsSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    /* storage blocked: the choice lasts for this page only */
  }
}
function lsDel(key) {
  try {
    localStorage.removeItem(key);
  } catch (e) {
    /* storage blocked */
  }
}
function lsJson(key) {
  try {
    const raw = lsGet(key);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

/* ---------- what a sheet can show ---------- */
const STAGES = [['idea', 'Idea'], ['bom', 'BOM'], ['sch', 'Schematic'], ['pcb', 'Layout'], ['rules', 'Rules'], ['outputs', 'Outputs'], ['checks', 'DFM']];
const STAGE_TITLES = Object.fromEntries(STAGES);
const PAGE_TITLES = {library: 'Library', sources: 'Sources', skills: 'Skills', settings: 'Settings'};
const FILE_BADGES = {pdf: 'PDF', sch: 'SCH', pcb: 'PCB', img: 'IMG', txt: 'TXT', csv: 'TXT', dfm: 'PDF', rul: 'TXT', prj: 'TXT', altium: 'SCH'};   // viewer.js reads this until the viewer is redrawn

const stageItem = id => ({id: 'stage:' + id, kind: 'stage', stage: id, title: STAGE_TITLES[id] || id});
const pageItem = id => ({id: 'page:' + id, kind: 'page', page: id, title: PAGE_TITLES[id] || id});
function fileItem(info) {
  const id = info.id || ('file:' + (info.path || info.name || info.slice || 'file'));
  let fileType = info.fileType || 'file';
  const name = info.name || id.replace(/^(file|src|altium|slice|export):/, '');
  const ext = (name.includes('.') ? '.' + name.split('.').pop() : '').toLowerCase();
  if (!info.fileType || info.fileType === 'file') {
    if (ext === '.pdf') fileType = 'pdf';
    else if (ext === '.schdoc') fileType = 'sch';
    else if (ext === '.pcbdoc') fileType = 'pcb';
    else if (ext === '.prjpcb') fileType = 'prj';
    else if (ext === '.rul') fileType = 'rul';
    else if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext)) fileType = 'img';
    else if (ext === '.csv') fileType = 'csv';
    else if (['.txt', '.text', '.md', '.markdown', '.json'].includes(ext)) fileType = 'txt';
    else if (info.stem) fileType = 'dfm';
    else fileType = 'txt';
  }
  return {id, kind: 'file', fileType, name, title: name, path: info.path || name, where: info.where || '', stem: info.stem || '', slice: info.slice || ''};
}
const itemKey = it => (it ? it.id : '');
const viewOf = it => (!it ? '' : it.kind === 'stage' ? it.stage : it.kind === 'page' ? it.page : 'file');
function itemTitle(it) { return it.kind === 'file' ? it.name : it.title; }
/* 'stage:bom' | 'page:library' | 'file' (the last document opened) -> item, or null */
function itemFromRef(ref) {
  if (ref === 'file') return sideMemo.file;
  const m = /^(stage|page):(\w+)$/.exec(String(ref || ''));
  if (!m) return null;
  if (m[1] === 'stage') return STAGE_TITLES[m[2]] ? stageItem(m[2]) : null;
  return PAGE_TITLES[m[2]] ? pageItem(m[2]) : null;
}

let mainItem = stageItem('bom');          // the main sheet
let sideItem = null;                      // the side sheet, or null when it is closed
const sideMemo = {item: null, file: null};  // what the side sheet showed last, and the last document opened
const mainKey = () => itemKey(mainItem);
const sideKey = () => itemKey(sideItem);
function mainView() { return viewOf(mainItem); }
function sideView() { return viewOf(sideItem); }
// page and tab (core.js) stay accurate: page is 'workspace' for a stage, else the page id or 'file'; tab is the last stage shown
function syncPageTab() {
  if (mainItem.kind === 'stage') { page = 'workspace'; tab = mainItem.stage; }
  else if (mainItem.kind === 'page') page = mainItem.page;
  else page = 'file';
}
// the inspector (views/inspector.js) still asks which view is active
function getActiveTab() { return mainItem; }
function guidanceBarHTML() { return ''; }   // the guidance banners are gone; views still call this

/* ---------- stage status: the dot on each stage in the nav. Neutral when we do not know; never invented. ---------- */
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
function stageStatus(id) {
  const none = {tone: '', title: '', hint: ''};
  if (!S) return none;
  try {
    if (id === 'idea') {
      return S.idea && S.idea.confirmed ? {tone: 'ok', title: 'Confirmed', hint: ''} : {tone: '', title: 'Not confirmed yet', hint: ''};
    }
    if (id === 'bom') {
      let total = 0, out = 0, wrong = 0, review = 0, unchecked = 0;
      for (const l of lines()) {
        const st = status(l);
        if (st === 'na') continue;
        total++;
        if (Object.values(l.supply || {}).some(v => v && v.code_mismatch)) wrong++;
        else if (st === 'bad') out++;
        else if (st === 'warn') review++;
        else if (st === 'pend') unchecked++;
      }
      if (!total) return {tone: '', title: 'No parts yet', hint: ''};
      const bad = out + wrong, warn = review + unchecked;
      const parts = [];
      if (out) parts.push(`${out} out of stock`);
      if (wrong) parts.push(`${wrong} with the wrong LCSC code`);
      if (review) parts.push(`${review} to review in the library`);
      if (unchecked) parts.push(`${unchecked} not checked yet`);
      if (bad) return {tone: 'bad', title: parts.join(', '), hint: String(bad + warn)};
      if (warn) return {tone: 'warn', title: parts.join(', '), hint: String(warn)};
      return {tone: 'ok', title: `${plural(total, 'part line')}, all in stock`, hint: ''};
    }
    if (id === 'sch') {
      const n = (S.sheets || []).length;
      return n ? {tone: 'ok', title: plural(n, 'sheet'), hint: ''} : {tone: '', title: 'No schematic yet', hint: ''};
    }
    if (id === 'rules') {
      const rd = RULES_DATA;
      if (!rd || rd.error) return none;
      const diff = Array.isArray(rd.diff) ? rd.diff : [];
      if (!rd.linked_pcb) return {tone: '', title: 'No board linked, so nothing to compare', hint: ''};
      if (!diff.length) return none;
      const below = diff.filter(d => d.verdict === 'below_fab_min').length;
      const differ = diff.filter(d => d.status === 'differs' || d.status === 'missing_on_board').length;
      if (below) return {tone: 'bad', title: `${plural(below, 'rule')} below the JLC minimum` + (differ > below ? `, ${differ} differ from the board` : ''), hint: String(Math.max(below, differ))};
      if (differ) return {tone: 'warn', title: `${plural(differ, 'rule')} differ from the board`, hint: String(differ)};
      return {tone: 'ok', title: 'Matches the board', hint: ''};
    }
    if (id === 'outputs') {
      const n = (S.exports || []).length;
      return n ? {tone: 'ok', title: plural(n, 'file'), hint: ''} : {tone: '', title: 'Nothing generated yet', hint: ''};
    }
    if (id === 'checks') {
      const cs = S.checks || [];
      if (!cs.length) return {tone: '', title: 'No reports yet', hint: ''};
      let real = 0, open = 0, known = 0;
      for (const c of cs) {
        const rows = triageMap[c.stem] || (c.triage_count === 0 ? [] : null);
        if (!rows) continue;
        known++;
        for (const r of rows) { if (r.verdict === 'real') real++; else if (!r.verdict || r.verdict === 'unknown') open++; }
      }
      if (real) return {tone: 'bad', title: plural(real, 'real issue') + (open ? `, ${open} to review` : ''), hint: String(real + open)};
      if (known < cs.length) return {tone: '', title: plural(cs.length, 'report'), hint: ''};
      if (open) return {tone: 'warn', title: `${open} to review`, hint: String(open)};
      return {tone: 'ok', title: 'All reviewed', hint: ''};
    }
  } catch (e) {
    return none;
  }
  return none;
}
// The rules diff and the DFM triage are loaded by their own views. The nav dots need them too, so they load once in the background.
const navTried = {};
let navDataSeen = null;
function scheduleNavData() {
  const sig = (S.checks || []).map(c => c.stem).join('|');
  if (sig === navDataSeen) return;
  navDataSeen = sig;
  setTimeout(ensureNavData, 700);
}
async function ensureNavData() {
  if (!S) return;
  if (!RULES_DATA && !navTried.rules && typeof loadRules === 'function') {
    navTried.rules = true;
    await loadRules();
    renderNav();
  }
  for (const c of S.checks || []) {
    if (!c.stem || triageMap[c.stem] || triageLoading[c.stem] || navTried['t:' + c.stem] || c.triage_count === 0) continue;
    navTried['t:' + c.stem] = true;
    triageLoading[c.stem] = true;
    try {
      const r = await api('/api/checks/triage?stem=' + encodeURIComponent(c.stem), undefined, {soft: true});
      if (r && Array.isArray(r.triage)) triageMap[c.stem] = r.triage;
    } catch (e) {
      /* the dot stays neutral */
    }
    triageLoading[c.stem] = false;
    renderNav();
    if (mainView() === 'checks' || sideView() === 'checks') renderCenter(true);
  }
}

/* ---------- nav ---------- */
const initials = t => {
  const w = String(t || '').trim().split(/[\s_-]+/).filter(Boolean);
  return (w.length > 1 ? w[0][0] + w[1][0] : (w[0] || '?').slice(0, 2)).toUpperCase();
};
let lastNavHTML = '';
function navHTML() {
  const cur = PROJECTS.find(p => p.name === PROJECT) || {name: PROJECT, title: PROJECT};
  const ptitle = String(cur.title || cur.name || '');
  const switcher = menu({html: `<span class="mk">${esc(initials(ptitle))}</span><span class="nm">${esc(ptitle)}</span>${icon('chev', 's')}`, cls: 'proj', title: ptitle, 'data-nav': 'proj'},
    [...PROJECTS.map(p => ({label: p.title || p.name, attrs: {proj: p.name}, checked: p.name === PROJECT})), 'sep', {label: 'New project', act: 'newproj', icon: 'plus'}]);
  const here = mainView();
  const stage = ([id, label]) => {
    const s = stageStatus(id);
    const tip = s.title ? `${label}: ${s.title}` : label;
    return `<button type="button" class="nitem" data-tab="${id}" data-nav="${id}"${here === id ? ' aria-current="page"' : ''} title="${esc(tip)}" aria-label="${esc(tip)}">` +
      `<span class="via${s.tone ? ' ' + s.tone : ''}"><i></i></span><span class="lbl">${esc(label)}</span>${s.hint ? `<span class="hint">${esc(s.hint)}</span>` : ''}</button>`;
  };
  const pageBtn = (id, ic) => `<button type="button" class="nitem" data-page="${id}" data-nav="${id}"${here === id ? ' aria-current="page"' : ''} title="${PAGE_TITLES[id]}"><span class="no">${icon(ic, 's')}</span><span class="lbl">${PAGE_TITLES[id]}</span></button>`;
  const shown = chatShown();
  const appView = ($('#app') && $('#app').dataset.view) || 'work';
  return switcher +
    `<div class="viewsw seg" role="group" aria-label="Show"><button type="button" data-view="work" aria-pressed="${appView !== 'chat'}">Work</button><button type="button" data-view="chat" aria-pressed="${appView === 'chat'}">Chat</button></div>` +
    `<div class="trace" role="group" aria-label="Design stages">${STAGES.map(stage).join('')}</div>` +
    `<div class="navsp"></div>${pageBtn('library', 'book')}${pageBtn('sources', 'file')}` +
    `<div class="navfoot">` +
    `<button type="button" class="nitem" data-act="palette" data-nav="search" title="Search (Ctrl K)"><span class="no">${icon('search', 's')}</span><span class="lbl">Search</span><kbd>Ctrl K</kbd></button>` +
    `<button type="button" class="nitem chat-sw" data-act="toggle-chat" data-nav="chat" aria-pressed="${shown}" title="Chat (Ctrl J)"><span class="no">${icon('chat', 's')}</span><span class="lbl">Chat</span><kbd>Ctrl J</kbd></button>` +
    `<button type="button" class="nitem" data-page="settings" data-nav="settings"${here === 'settings' ? ' aria-current="page"' : ''} title="Settings"><span class="no">${icon('gear', 's')}</span><span class="lbl">Settings</span></button>` +
    `</div>`;
}
function renderNav() {
  const nav = $('#nav');
  if (!nav || !S || uiBusy()) return;
  const html = navHTML();
  if (html === lastNavHTML && nav.firstChild) return;   // the 4s poll must not touch the DOM when nothing changed
  const focused = nav.contains(document.activeElement) ? document.activeElement.dataset.nav : null;
  lastNavHTML = html;
  nav.innerHTML = html;
  if (focused) { const b = nav.querySelector(`[data-nav="${focused}"]`); if (b) b.focus(); }
  scheduleNavData();
}

/* ---------- drawing the sheets ---------- */
function renderStage(stageId, container) {
  let html = '';
  if (stageId === 'bom') html = bomHTML(container);
  else if (stageId === 'sch') html = schHTML(container);
  else if (stageId === 'pcb') html = pcbHTML(container);
  else if (stageId === 'rules') html = rulesHTML(container);
  else if (stageId === 'outputs') html = outputsHTML(container);
  else if (stageId === 'checks') html = checksHTML(container);
  else html = ideaHTML(container);
  if (container) container.innerHTML = html;
  return html;
}
function renderPage(pageId, container) {
  let html = '';
  if (pageId === 'workspace') html = renderStage(tab, container);
  else if (pageId === 'outputs') html = outputsHTML(container);
  else if (pageId === 'checks') html = checksHTML(container);
  else if (pageId === 'library') html = libHTML(container);
  else if (pageId === 'sources') html = sourcesHTML(container);
  else if (pageId === 'skills') html = skillsHTML(container);
  else if (pageId === 'settings') html = settingsHTML(container);
  else html = settingsHTML(container);
  if (container) container.innerHTML = html;
  return html;
}
// Views that have not moved to the new header and body yet (wave B) keep a little padding of their own.
function isLegacyView(c) {
  const f = c.firstElementChild;
  return !!f && f.matches('.vhead, .dnote, .kpis, .card, .howto, .warnbox, .form, .tblwrap, .guidance-bar, h2, h3, p, table');
}
function renderItem(item, container, force) {
  const key = itemKey(item);
  const changed = container.dataset.item !== key;
  container.dataset.item = key;
  const idea = item.kind === 'stage' && item.stage === 'idea';
  container.classList.toggle('stage-idea', idea);
  container.classList.toggle('doc', item.kind === 'file');
  if (item.kind === 'file') {
    container.classList.remove('legacy');
    const docKey = key + '|' + (item.where || '');
    if (container.dataset.docKey === docKey) return;   // a document is drawn once, so a poll never reloads a PDF
    container.dataset.docKey = docKey;
    Promise.resolve(renderFileTabContent(item, container)).catch(err => { container.innerHTML = errorLine('open ' + item.name, err.message); });
    container.scrollTop = 0;
    return;
  }
  container.dataset.docKey = '';
  if (item.kind === 'stage') {
    if (idea && container.querySelector('.diagram-mount-point')) updateIdeaContent(container);
    else {
      renderStage(item.stage, container);
      if (idea) mountDiagramEditor(container);
    }
    if (item.stage === 'sch' && S && S.sheets && S.sheets.length && typeof loadSheet === 'function') loadSheet(container);
    if (item.stage === 'bom' && typeof loadImportInfo === 'function') loadImportInfo();
    if (item.stage === 'pcb' && typeof loadPcb === 'function') loadPcb(container);
  } else {
    renderPage(item.page, container);
    if (item.page === 'settings' && !ALTIUM_DATA && typeof loadAltium === 'function') loadAltium();
    if (item.page === 'sources' && hitSrc) {
      const r = container.querySelector('#src-' + hitSrc.replace(/[^\w-]/g, '_'));
      if (r) r.scrollIntoView({block: 'center'});
      hitSrc = null;
    }
  }
  container.classList.toggle('legacy', isLegacyView(container));
  if (changed) container.scrollTop = 0;
}
function renderMain(force) {
  const v = $('#view');
  if (v) renderItem(mainItem, v, force);
}
let lastSideHead = '';
function renderSide(force) {
  const app = $('#app'), side = $('#side'), v = $('#view-side'), head = $('#side-h');
  if (!app || !side || !v || !head) return;
  app.classList.toggle('has-side', !!sideItem);
  side.hidden = !sideItem;
  if (!sideItem) {
    if (v.dataset.item) {
      v.innerHTML = '';
      v.dataset.item = '';
      v.dataset.docKey = '';
      v.classList.remove('doc', 'legacy', 'stage-idea');
    }
    lastSideHead = '';
    return;
  }
  const h = sideHeadHTML();
  if (h !== lastSideHead) { lastSideHead = h; head.innerHTML = h; }
  renderItem(sideItem, v, force);
}
function sideMenuItems() {
  const here = mainKey();
  const row = it => ({label: itemTitle(it), act: 'side-set', attrs: {item: it.kind === 'file' ? 'file' : it.id},
    checked: sideKey() === itemKey(it), disabled: itemKey(it) === here, hint: itemKey(it) === here ? 'Open on the left' : ''});
  const items = [{group: 'Design'}, ...STAGES.map(([id]) => row(stageItem(id))), {group: 'Pages'}, ...Object.keys(PAGE_TITLES).map(id => row(pageItem(id)))];
  if (sideMemo.file) items.push({group: 'Document'}, row(sideMemo.file));
  return items;
}
function sideHeadHTML() {
  return menu({label: itemTitle(sideItem), iconAfter: 'chev', cls: 'side-pick', title: 'Choose what the side sheet shows'}, sideMenuItems()) +
    btn('', {icon: 'swap', size: 'sm', title: 'Swap the two sheets', act: 'side-swap'}) +
    btn('', {icon: 'x', size: 'sm', title: 'Close the side sheet', act: 'side-close'});
}

/* ---------- what the sheets show: go(), select() (core.js), the side sheet ---------- */
// The side sheet is remembered per project: which item, whether it is open, and the last document opened.
const SIDE_KEY = 'pcb_advisor_side:';
function saveSide() {
  if (!PROJECT) return;
  const shown = sideItem || sideMemo.item;
  const f = sideMemo.file;
  lsSet(SIDE_KEY + PROJECT, JSON.stringify({
    open: !!sideItem,
    shown: shown ? (shown.kind === 'file' ? 'file' : shown.id) : '',
    file: f ? {name: f.name, path: f.path, where: f.where, stem: f.stem, slice: f.slice, fileType: f.fileType} : null,
  }));
}
function restoreSide() {
  sideItem = null;
  sideMemo.item = null;
  sideMemo.file = null;
  const st = lsJson(SIDE_KEY + PROJECT);
  if (!st || typeof st !== 'object') return;
  if (st.file && typeof st.file.name === 'string') sideMemo.file = fileItem(st.file);
  const it = itemFromRef(st.shown);
  if (it && itemKey(it) !== mainKey()) {
    sideMemo.item = it;
    if (st.open) sideItem = it;
  }
}
// first paint: boot.js sets the main sheet from ?page= and ?tab= before anything is drawn
function initMain(item) {
  mainItem = item;
  syncPageTab();
}
function setMain(item) {
  if (sideItem && itemKey(sideItem) === itemKey(item) && mainKey() !== itemKey(item)) {
    sideItem = mainItem;   // the same sheet is never shown twice: the old main takes the side
    sideMemo.item = sideItem;
    if (sideItem.kind === 'file') sideMemo.file = sideItem;
  }
  mainItem = item;
  syncPageTab();
  saveSide();
  render(true);
}
// go('workspace', 'bom'), go('bom'), go('library'): show a stage or a page in the main sheet
function go(p, t) {
  let item = null;
  if (t && STAGE_TITLES[t]) item = stageItem(t);
  else if (p === 'workspace') item = stageItem(STAGE_TITLES[tab] ? tab : 'bom');
  else if (STAGE_TITLES[p]) item = stageItem(p);
  else if (PAGE_TITLES[p]) item = pageItem(p);
  else if (p === 'file' && mainItem.kind === 'file') item = mainItem;
  if (!item) return;
  setMain(item);
  setView('work');
}
const NEIGHBOUR = {idea: 'bom', bom: 'sch', sch: 'bom', pcb: 'sch'};
function defaultSideItem() {
  if (sideMemo.item && itemKey(sideMemo.item) !== mainKey()) return sideMemo.item;
  let it = stageItem(NEIGHBOUR[mainView()] || 'bom');
  if (itemKey(it) === mainKey()) it = stageItem('sch');
  return it;
}
// openSide(item) shows an item in the side sheet; without an argument it picks the last one or the natural neighbour
function openSide(item) {
  item = item || defaultSideItem();
  if (itemKey(item) === mainKey()) {
    if (item.kind !== 'file') toast(`${itemTitle(item)} is already open in the main sheet`);
    return;
  }
  sideItem = item;
  sideMemo.item = item;
  if (item.kind === 'file') sideMemo.file = item;
  saveSide();
  render(true);
  if (chatMode() === 'narrow') setView('work');
}
function closeSide() {
  if (!sideItem) return;
  sideItem = null;
  saveSide();
  render(true);
}
function toggleSide() { if (sideItem) closeSide(); else openSide(); }
function swapSheets() {
  if (!sideItem) return;
  [mainItem, sideItem] = [sideItem, mainItem];
  sideMemo.item = sideItem;
  if (mainItem.kind === 'file') sideMemo.file = mainItem;
  syncPageTab();
  saveSide();
  render(true);
}
// viewer.js opens every document through here: it appears in the side sheet, which opens if needed
// info = {name, path?, where?, fileType?, stem?, slice?}
function openFileAsTab(info) {
  const it = fileItem(info);
  sideMemo.file = it;
  if (itemKey(it) === mainKey()) { mainItem = it; render(true); return; }   // already the main sheet: only a new page may differ
  openSide(it);
}

/* ---------- chat column: right of the sheets. Wide: resizable and collapsible. <=1100px: a drawer. <=860px: Work / Chat. ---------- */
const LAYOUT_KEY = 'pcb_advisor_shell';
const CHAT_MIN = 300, CHAT_MAX = 720, CHAT_DEFAULT = 372, CHAT_DROP = 220, PANES_MIN = 420, KEY_STEP = 16;
let chatWidth = CHAT_DEFAULT, chatHidden = false, chatDrawer = false;
const MQ_DRAWER = '(max-width:1100px)', MQ_NARROW = '(max-width:860px)';
function chatMode() { return matchMedia(MQ_NARROW).matches ? 'narrow' : matchMedia(MQ_DRAWER).matches ? 'drawer' : 'wide'; }
function chatShown() {
  const m = chatMode(), app = $('#app');
  if (m === 'narrow') return !!app && app.dataset.view === 'chat';
  return m === 'drawer' ? chatDrawer : !chatHidden;
}
function loadLayout() {
  const st = lsJson(LAYOUT_KEY);
  if (st && typeof st === 'object') {
    if (typeof st.chatWidth === 'number' && st.chatWidth >= CHAT_MIN && st.chatWidth <= 2000) chatWidth = st.chatWidth;
    chatHidden = !!st.chatHidden;
  }
}
function saveLayout() { lsSet(LAYOUT_KEY, JSON.stringify({chatWidth, chatHidden})); }
function maxChatWidth() {
  const app = $('#app'), nav = $('#nav');
  return Math.max(CHAT_MIN, Math.min(CHAT_MAX, (app ? app.clientWidth : 1600) - (nav ? nav.offsetWidth : 232) - PANES_MIN));
}
function cssChatWidth(w) {
  const app = $('#app');
  if (app) app.style.setProperty('--chat-w', Math.round(w) + 'px');
  const sp = $('#splitter-chat');
  if (sp) {
    sp.setAttribute('aria-valuemin', String(CHAT_MIN));
    sp.setAttribute('aria-valuemax', String(maxChatWidth()));
    sp.setAttribute('aria-valuenow', String(Math.round(w)));
  }
}
// put the layout state on the DOM: classes on #app, the width, the pressed state of the nav buttons
function syncChat() {
  const app = $('#app');
  if (!app) return;
  if (chatMode() !== 'drawer') chatDrawer = false;
  app.classList.toggle('chat-off', chatHidden);
  app.classList.toggle('chat-open', chatDrawer);
  cssChatWidth(Math.min(chatWidth, maxChatWidth()));
  renderNav();
  document.querySelectorAll('#nav [data-act="toggle-chat"]').forEach(b => b.setAttribute('aria-pressed', String(chatShown())));
}
function showChat(focusInput) {
  const m = chatMode(), app = $('#app');
  if (m === 'narrow') { if (app) app.dataset.view = 'chat'; }
  else if (m === 'drawer') chatDrawer = true;
  else if (chatHidden) { chatHidden = false; saveLayout(); }
  syncChat();
  syncViewSwitch();
  if (focusInput) { const i = $('#input'); if (i) i.focus(); }
}
function hideChat() {
  const m = chatMode(), app = $('#app');
  const inChat = !!(document.activeElement && document.activeElement.closest && document.activeElement.closest('.chat'));
  if (m === 'narrow') { if (app) app.dataset.view = 'work'; }
  else if (m === 'drawer') chatDrawer = false;
  else { chatHidden = true; saveLayout(); }
  syncChat();
  syncViewSwitch();
  if (inChat) {   // focus must not fall into the hidden column
    const b = $('#nav [data-act="toggle-chat"]');
    if (b && b.offsetParent) b.focus();
    else { const w = $('#nav .viewsw button'); if (w) w.focus(); }
  }
}
function toggleChat() { if (chatShown()) hideChat(); else showChat(true); }
// setView('chat') shows the chat, setView('work') brings the sheets to the front (closing the drawer and the one-column chat)
function setView(v) {
  if (v === 'chat') { showChat(); return; }
  const app = $('#app');
  if (!app) return;
  if (chatMode() === 'narrow') app.dataset.view = 'work';
  else if (chatDrawer) chatDrawer = false;
  syncChat();
  syncViewSwitch();
}
function syncViewSwitch() {
  const app = $('#app');
  const v = (app && app.dataset.view) || 'work';
  document.querySelectorAll('#nav .viewsw button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === v)));
}
function resetLayout() {
  chatWidth = CHAT_DEFAULT;
  chatHidden = false;
  chatDrawer = false;
  lsDel(LAYOUT_KEY);
  lsDel(SIDE_KEY + PROJECT);
  sideItem = null;
  sideMemo.item = null;
  sideMemo.file = null;
  syncChat();
  render(true);
}

/* the splitter between the sheets and the chat: drag, arrow keys, Enter to hide, double-click to reset */
let chatDrag = null;
function onSplitDown(e) {
  if (e.button !== 0) return;
  e.preventDefault();
  chatDrag = {x: e.clientX, w: chatWidth, raw: chatWidth};
  e.currentTarget.setPointerCapture(e.pointerId);
  e.currentTarget.classList.add('dragging');
  document.body.classList.add('resizing-col');
}
function onSplitMove(e) {
  if (!chatDrag) return;
  chatDrag.raw = chatDrag.w + (chatDrag.x - e.clientX);
  cssChatWidth(Math.min(maxChatWidth(), Math.max(CHAT_MIN, chatDrag.raw)));
  $('#app').classList.toggle('will-hide', chatDrag.raw < CHAT_DROP);
}
function onSplitUp(e) {
  if (!chatDrag) return;
  const d = chatDrag;
  chatDrag = null;
  e.currentTarget.classList.remove('dragging');
  document.body.classList.remove('resizing-col');
  $('#app').classList.remove('will-hide');
  if (d.raw < CHAT_DROP) { chatWidth = d.w; hideChat(); return; }   // dragged shut: hide, and remember the width it had
  chatWidth = Math.min(maxChatWidth(), Math.max(CHAT_MIN, d.raw));
  saveLayout();
  syncChat();
}
function onSplitKey(e) {
  let w = null;
  if (e.key === 'ArrowLeft') w = chatWidth + KEY_STEP;
  else if (e.key === 'ArrowRight') w = chatWidth - KEY_STEP;
  else if (e.key === 'Home') w = CHAT_MIN;
  else if (e.key === 'End') w = maxChatWidth();
  else if (e.key === 'Enter') { e.preventDefault(); hideChat(); return; }
  else return;
  e.preventDefault();
  if (w < CHAT_MIN) { hideChat(); return; }
  chatWidth = Math.min(maxChatWidth(), w);
  saveLayout();
  syncChat();
}
function initLayout() {
  lsDel('pcb_advisor_layout');        // the layouts of the old left chat and the editor tabs are gone
  lsDel('pcb_advisor_editor_tabs');
  loadLayout();
  const sp = $('#splitter-chat');
  if (sp) {
    sp.addEventListener('pointerdown', onSplitDown);
    sp.addEventListener('pointermove', onSplitMove);
    sp.addEventListener('pointerup', onSplitUp);
    sp.addEventListener('pointercancel', onSplitUp);
    sp.addEventListener('keydown', onSplitKey);
    sp.addEventListener('dblclick', () => { chatWidth = CHAT_DEFAULT; saveLayout(); syncChat(); });
  }
  for (const mq of [MQ_DRAWER, MQ_NARROW]) matchMedia(mq).addEventListener('change', () => { syncChat(); syncViewSwitch(); });
  addEventListener('resize', () => { if (!chatDrag) cssChatWidth(Math.min(chatWidth, maxChatWidth())); });
  cssChatWidth(Math.min(chatWidth, maxChatWidth()));
  $('#app').classList.toggle('chat-off', chatHidden);
}
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'j' || e.key === 'J')) { e.preventDefault(); toggleChat(); return; }
  if (e.key === 'Escape' && chatDrawer && !convsOpen && !e.defaultPrevented && !uiBusy()) hideChat();
});

/* ---------- action handlers (dispatched by the delegates in core.js) ---------- */
onAct('toggle-chat', async () => { toggleChat(); });
onAct('side-open', async () => { toggleSide(); });   // "Side by side" in a view header (kit.js viewHeader)
onAct('side-close', async () => { closeSide(); });
onAct('side-swap', async () => { swapSheets(); });
onAct('side-set', async (el, d) => { const it = itemFromRef(d.item); if (it) openSide(it); });
onAct('reset-layout', async () => { resetLayout(); toast('Layout reset to default'); });
onAct('newproj', async () => {
  const n = await askText({title: 'New project', label: 'Project name', placeholder: 'Device controller', confirm: 'Create'});
  if (!n) return;
  const r = await api('/api/projects/new', {name: n});
  const u = new URL(location.href);
  u.searchParams.set('project', r.created);
  u.searchParams.delete('session');
  location.href = u;
});
