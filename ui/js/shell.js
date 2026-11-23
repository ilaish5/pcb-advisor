/* PCB Advisor UI - shell: the app frame.
   Layout: navigation (left) | main sheet, plus an optional side sheet | chat column (right).
   What lives here: the stage trace and its status dots, what each sheet shows (mainItem / sideItem), go() and openSide(),
   the chat column (show, hide, resize, drawer and one-column modes) and the nav foot.
   Globals other files use: go, select (core.js), mainView, sideView, setView, showChat, hideChat, toggleChat, stageStatus,
   openSide, closeSide, toggleSide, openFileAsTab, renderStage, renderPage, resetLayout. */

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

/* ---------- stage status: the dot on each stage in the nav ----------
   One small mapper over S.stages, which the server derives (scripts/stages.py). Nothing is computed here from partial data:
   a stage the server did not send, or sent as not started, is neutral. clean = green, blocked = red, otherwise the stage's severity. */
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
function stageStatus(id) {
  const none = {tone: '', title: '', hint: ''};
  const st = S && Array.isArray(S.stages) ? S.stages.find(x => x && x.id === id) : null;
  if (!st) return none;
  const tone = st.state === 'clean' ? 'ok' : st.state === 'blocked' ? 'bad' : st.state === 'not_started' ? '' : (st.severity === 'bad' || st.severity === 'warn' ? st.severity : '');
  return {tone, title: st.reason || '', hint: tone && tone !== 'ok' && st.open > 0 ? String(st.open) : ''};
}
// The stage record of the server, and a page's Next button from stage.next ({label, act: 'go:<stage>'}); the primary stage's button is the filled one.
const stageOf = id => (S && Array.isArray(S.stages) ? S.stages.find(x => x && x.id === id) : null) || null;
function stageNextBtn(id) {
  const st = stageOf(id), n = st && st.next;
  if (!n || !n.label || !/^go:/.test(n.act || '')) return '';
  return btn(n.label, {kind: st.primary ? 'pri' : 'line', act: 'stage-next', stage: id, to: n.act.slice(3)});
}
onAct('stage-next', (el, d) => { if (d.to && STAGE_TITLES[d.to]) go('workspace', d.to); });

/* ---------- nav ---------- */
const initials = t => {
  const w = String(t || '').trim().split(/[\s_/\\-]+/).filter(Boolean);       // a title like "PCB/Blinker" is two words, not an avatar of "/B"
  return (w.length > 1 ? w[0][0] + w[1][0] : (w[0] || '?').slice(0, 2)).toUpperCase();
};
let lastNavHTML = '';
function navHTML() {
  const cur = PROJECTS.find(p => p.name === PROJECT) || {name: PROJECT, title: PROJECT};
  const ptitle = String(cur.title || cur.name || '');
  const switcher = menu({html: `<span class="mk">${esc(initials(ptitle))}</span><span class="nm">${esc(ptitle)}</span>${icon('chev', 's')}`, cls: 'proj', title: ptitle, 'data-nav': 'proj'},
    [...PROJECTS.map(p => ({label: p.title || p.name, attrs: {proj: p.name}, checked: p.name === PROJECT})), 'sep', {label: 'New project', act: 'newproj', icon: 'plus'}, {label: 'Download activity report (zip)', act: 'report-project', icon: 'file'}]);
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
    `<div class="navfoot">` + (typeof updNavBtn === 'function' ? updNavBtn() : '') +
    `<button type="button" class="nitem" data-act="palette" data-nav="search" title="Search (Ctrl K)"><span class="no">${icon('search', 's')}</span><span class="lbl">Search</span><kbd>Ctrl K</kbd></button>` +
    `<button type="button" class="nitem chat-sw" data-act="toggle-chat" data-nav="chat" aria-pressed="${shown}" title="Chat (Ctrl J)"><span class="no">${icon('chat', 's')}</span><span class="lbl">Chat</span><kbd>Ctrl J</kbd></button>` +
    `<button type="button" class="nitem" data-page="settings" data-nav="settings"${here === 'settings' ? ' aria-current="page"' : ''} title="Settings"><span class="no">${icon('gear', 's')}</span><span class="lbl">Settings</span></button>` +
    `</div>`;
}
// A late redraw of the nav (rules, triage and update data arrive a moment after the page loads) between the mouse going down and
// coming up on a button replaces that button: the browser then sends no click, so the first click on a stage was lost.
// The nav is not redrawn while the mouse is down on it; it catches up on release.
let navPressed = false;
document.addEventListener('pointerdown', e => { navPressed = !!(e.target.closest && e.target.closest('#nav')); }, true);
document.addEventListener('pointerup', () => {
  if (!navPressed) return;
  navPressed = false;
  setTimeout(() => renderNav(), 0);       // after the click event of this press has run
}, true);
document.addEventListener('pointercancel', () => { navPressed = false; }, true);
function renderNav() {
  const nav = $('#nav');
  if (!nav || !S || uiBusy() || navPressed) return;
  const html = navHTML();
  if (html === lastNavHTML && nav.firstChild) return;   // the 4s poll must not touch the DOM when nothing changed
  const focused = nav.contains(document.activeElement) ? document.activeElement.dataset.nav : null;
  lastNavHTML = html;
  nav.innerHTML = html;
  if (focused) { const b = nav.querySelector(`[data-nav="${focused}"]`); if (b) b.focus(); }
}

/* ONE sheet count for every page: the server's stage_sheets {plan, altium, total} (scripts/stages.py sheets_counts). Only when a state
   without it is on screen (an older server) the same rule is applied to the rows: the plan's sheets, else the ones read from Altium. */
function sheetCounts(rows) {
  const c = S && S.stage_sheets;
  if (c && typeof c.total === 'number') return c;
  rows = rows || (S && S.sheets) || [];
  const plan = rows.filter(s => !s.altium).length, altium = rows.filter(s => s.altium).length;
  return {plan, altium, total: plan || altium};
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
function renderItem(item, container, force) {
  const key = itemKey(item);
  const changed = container.dataset.item !== key;
  container.dataset.item = key;
  const idea = item.kind === 'stage' && item.stage === 'idea';
  container.classList.toggle('doc', item.kind === 'file');   // a document fills the sheet and scrolls inside itself
  if (item.kind === 'file') {
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
      v.classList.remove('doc');
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
  saveMain();
  saveSide();
  render(true);
}
// The sheet in the main pane is remembered per project, so a reload (or a restart) opens the page you were on; ?page= / ?tab= still win.
const MAIN_KEY = 'pcb_advisor_main:';
function saveMain() {
  if (PROJECT && mainItem && mainItem.kind !== 'file') lsSet(MAIN_KEY + PROJECT, mainItem.id);
}
function savedMain() {
  const it = itemFromRef(lsGet(MAIN_KEY + PROJECT));
  return it && it.kind !== 'file' ? it : null;
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
// The one way to open a document (a chip, a table row, the palette, a DFM slice, a link to an Altium file): it appears
// in the side sheet, which opens if needed, and the chat drawer or the narrow Chat view gives way to it.
// info = {name, path?, where?, fileType?, stem?, slice?}; fileType follows from the extension unless it is given
function openFileAsTab(info) {
  const it = fileItem(info);
  sideMemo.file = it;
  if (itemKey(it) === mainKey()) { mainItem = it; render(true); }   // already the main sheet: only a new page may differ
  else openSide(it);
  setView('work');
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
  const was = app.classList.contains('chat-open');
  app.classList.toggle('chat-open', chatDrawer);
  // the open drawer pushes the sheets aside (shell.css): their width changed without a window resize, so the views that
  // measure themselves on resize (the idea's requirement list) measure again
  if (was !== chatDrawer) requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
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
  const n = await askText({title: 'New project', label: 'Project name', placeholder: 'Temperature controller', confirm: 'Create'});
  if (!n) return;
  let r = await api('/api/projects/new', {name: n}, {soft: true});
  if (r && r.exists) {       // the name is taken: open that one, or make a numbered copy, never silently
    const open = await askChoice({title: 'Project exists', text: `A project named "${r.exists}" already exists.`, yes: 'Open it', no: 'Create a copy'});
    if (open === null) return;
    if (open) r = {created: r.exists};
    else r = await api('/api/projects/new', {name: n, allow_copy: true});
  } else if (!r || !r.created) { toast((r && r.error) || 'Could not create the project', null, {bad: true}); return; }
  if (window.usage) window.usage('click', {text: 'New project: Create', act: 'newproj', id: 'newproj', tag: 'button', project: r.created});      // the click belongs to the new project's log
  if (r.note) { try { sessionStorage.setItem('pcb-new-note', r.note); } catch (e) { /* the note is lost, the folder is still named in the project list */ } }
  const u = new URL(location.href);
  u.searchParams.set('project', r.created);
  u.searchParams.delete('session');
  location.href = u;
});
