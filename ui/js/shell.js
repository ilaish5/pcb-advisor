/* PCB Advisor UI - shell: nav, project menu, stage guidance, editor tabs/groups/split/drag-and-drop, layout + splitters. */

/* ---------- nav ---------- */
const ICON = {
  ws: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2.5" y="2.5" width="6" height="6" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="11.5" y="2.5" width="6" height="6" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="2.5" y="11.5" width="15" height="6" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  lib: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="5" y="4" width="10" height="12" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M2 7h3M2 10h3M2 13h3M15 7h3M15 10h3M15 13h3" stroke="currentColor" stroke-width="1.6"/></svg>',
  src: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 3.5h8l4 4v9H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 3.5v4h4M7 11h6M7 14h4" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>',
  sk: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M11 2 4 11h5l-1 7 7-9h-5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  chat: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4h14v9H8l-4 3v-3H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  set: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="2.6" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M4.7 15.3l1.6-1.6M13.7 6.3l1.6-1.6" stroke="currentColor" stroke-width="1.6"/></svg>',
};
function renderNav() {
  const ni = (id, icon, label, cnt) => `<button class="nitem" data-page="${id}" aria-current="${page === id}" title="${label}">${ICON[icon]}<span class="lbl">${label}</span>${cnt != null ? `<span class="cnt">${cnt}</span>` : ''}</button>`;
  const libCount = (S.library || []).filter(r => r.status === 'ok' || r.status === 'review').length;
  const expCount = (S.exports || []).length;
  const chkCount = (S.checks || []).length;
  $('#nav').innerHTML = `
    <div class="brand"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="12" height="14" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M2 9h4M2 15h4M18 9h4M18 15h4" stroke="currentColor" stroke-width="1.8"/></svg><span>PCB Advisor</span></div>
    <div class="ngroup projects"><div class="nlabel">Projects</div>
      ${(() => { const cur = PROJECTS.find(p => p.name === PROJECT) || {name: PROJECT, title: PROJECT}; const ct = String(cur.title || cur.name || '');
        return `<button type="button" class="nitem pcur" id="projbtn" data-act="projmenu" aria-haspopup="menu" aria-expanded="false" aria-controls="projmenu" title="${esc(ct)}"><span class="pdot"></span><span class="pini">${esc(ct.charAt(0).toUpperCase())}</span><span class="lbl">${esc(ct)}</span><span class="pcaret" aria-hidden="true">&#9662;</span></button>
      <div class="pmenu" id="projmenu" role="menu" aria-label="Projects" hidden>
        ${PROJECTS.map(p => `<button type="button" class="pmitem" role="menuitem" tabindex="-1" data-proj="${esc(p.name)}" aria-current="${p.name === PROJECT}"><span class="pdot"></span><span class="lbl">${esc(p.title)}</span></button>`).join('')}
        <div class="psep"></div>
        <button type="button" class="pmitem" role="menuitem" tabindex="-1" data-act="newproj"><span class="lbl">+ New project</span></button>
      </div>`; })()}
    </div>
    <div class="ngroup"><div class="nlabel">${esc(S.title)}</div>
      <button class="nitem mobile-only" data-view="chat" title="Chat">${ICON.chat}<span class="lbl">Chat</span></button>
      ${ni('workspace', 'ws', 'Workspace')}
      <div class="nsub">${[['idea', 'Idea'], ['bom', 'BOM'], ['sch', 'Schematic'], ['pcb', 'Placement & routing'], ['rules', 'Rules'], ['outputs', 'Altium outputs'], ['checks', 'Final manufacturer checks']].map(([id, l]) => `<button data-tab="${id}" aria-current="${page === 'workspace' && tab === id}">${l}</button>`).join('')}</div>
      ${ni('outputs', 'ws', 'Altium outputs', expCount)}
      ${ni('checks', 'ws', 'Final manufacturer checks', chkCount)}
      ${ni('library', 'lib', 'Altium library', libCount)}
      ${ni('sources', 'src', 'Sources', (S.sources || []).length)}
      ${ni('skills', 'sk', 'Skills', SKILLS ? SKILLS.filter(s => s.available).length : null)}
    </div>
    <div class="nfoot">${ni('settings', 'set', 'Settings')}</div>`;
}

/* ---------- project picker dropdown ---------- */
function toggleProjMenu(open) {
  const btn = document.getElementById('projbtn'), menu = document.getElementById('projmenu');
  if (!btn || !menu) return;
  const want = open === undefined ? menu.hidden : !!open;
  menu.hidden = !want;
  btn.setAttribute('aria-expanded', String(want));
  if (want) {
    const r = btn.getBoundingClientRect();
    menu.style.left = Math.max(4, r.left) + 'px';
    menu.style.top = (r.bottom + 4) + 'px';
    const cur = menu.querySelector('[aria-current="true"]') || menu.querySelector('[role="menuitem"]');
    if (cur) cur.focus();
  }
}
function closeProjMenu(refocus) {
  const menu = document.getElementById('projmenu');
  if (!menu || menu.hidden) return;
  toggleProjMenu(false);
  if (refocus) { const b = document.getElementById('projbtn'); if (b) b.focus(); }
}
document.addEventListener('click', e => {
  if (!e.target.closest('#projmenu, #projbtn') || e.target.closest('#projmenu [role="menuitem"]')) closeProjMenu(false);
}, true);
document.addEventListener('keydown', e => {
  const menu = document.getElementById('projmenu');
  if (!menu || menu.hidden) return;
  if (e.key === 'Escape') { closeProjMenu(true); return; }
  if (e.key === 'Tab') { closeProjMenu(false); return; }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const items = [...menu.querySelectorAll('[role="menuitem"]')];
    if (!items.length) return;
    e.preventDefault();
    const i = items.indexOf(document.activeElement);
    items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
  }
});

/* ---------- stage guidance ---------- */
function stageGuidance(targetTab) {
  if (targetTab === 'idea') {
    return S.idea && S.idea.confirmed
      ? 'Idea confirmed. Review block diagram domains and connections, or continue refining parts on the BOM tab.'
      : 'Refine requirements and the block diagram. Confirm the idea when the architecture is solid to proceed to the BOM.';
  }
  if (targetTab === 'bom') {
    const t = S.totals;
    const uncheck = lines().filter(l => l.availability === 'unchecked' || l.supply == null).length;
    if (t.out_of_stock) return `${t.out_of_stock} line(s) out of stock. Ask the agent for pin-compatible alternatives or click 'Alternatives'.`;
    if (t.to_verify) return `${t.to_verify} line(s) have unverified library footprints/symbols. Verify against datasheets before export.`;
    if (uncheck) return `${uncheck} part(s) have unchecked stock. Click 'Check stock' to update availability and prices.`;
    return 'BOM is fully verified and in stock. Ready to review schematic sheets or export for PCB fab.';
  }
  if (targetTab === 'sch') {
    return (S.sheets && S.sheets.length)
      ? 'Click any component or net in the schematic preview to inspect connections or ask the agent questions.'
      : 'No schematic sheets yet. Chat with the agent to generate schematic sheets from the BOM.';
  }
  if (targetTab === 'pcb') {
    return 'Inspect placement plan, keep-out zones, and component footprint orientation on top/bottom layers.';
  }
  if (targetTab === 'library') {
    return 'Verify symbols, footprints, and 3D STEP models for custom parts, then export .IntLib for Altium.';
  }
  if (targetTab === 'sources') {
    return 'Manage referenced datasheets, manuals, and design guides cited by the agent during part selection.';
  }
  if (targetTab === 'skills') {
    return 'Browse automated skills for DRC, supply checks, and Altium export workflows.';
  }
  if (targetTab === 'settings') {
    return 'Configure your LLM provider, Altium Designer installation path, and linked .PrjPcb project.';
  }
  return 'Follow project progress and interact with the advisor.';
}
function guidanceBarHTML(t) {
  return `<div class="guidance-bar"><span class="g-icon">💡</span><span class="g-lbl">What to do now:</span><span class="g-txt">${esc(stageGuidance(t))}</span></div>`;
}

/* ---------- center ---------- */
let tabScrollerObserver = null;

function updateTabArrows() {
  const scroller = $('#tabs-scroller') || $('.tabs-scroller') || $('.tabs');
  if (!scroller) return;
  const leftBtn = document.querySelector('[aria-label="Scroll tabs left"]');
  const rightBtn = document.querySelector('[aria-label="Scroll tabs right"]');
  const maxScroll = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
  const canLeft = scroller.scrollLeft > 2;
  const canRight = scroller.scrollLeft < maxScroll - 2;

  if (leftBtn) {
    leftBtn.disabled = !canLeft;
    leftBtn.hidden = !canLeft;
    leftBtn.style.visibility = canLeft ? 'visible' : 'hidden';
  }
  if (rightBtn) {
    rightBtn.disabled = !canRight;
    rightBtn.hidden = !canRight;
    rightBtn.style.visibility = canRight ? 'visible' : 'hidden';
  }
}

function scrollTabsBy(dir) {
  const scroller = $('#tabs-scroller') || $('.tabs-scroller') || $('.tabs');
  if (!scroller) return;
  const delta = Math.round(scroller.clientWidth * 0.7) * (dir > 0 ? 1 : -1);
  scroller.scrollBy({ left: delta, behavior: 'smooth' });
  setTimeout(updateTabArrows, 200);
}

function initTabScroller() {
  const scroller = $('#tabs-scroller') || $('.tabs-scroller') || $('.tabs');
  if (!scroller) {
    if (tabScrollerObserver) {
      tabScrollerObserver.disconnect();
      tabScrollerObserver = null;
    }
    return;
  }

  scroller.addEventListener('scroll', updateTabArrows, { passive: true });

  scroller.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && e.deltaY !== 0) {
      e.preventDefault();
      scroller.scrollBy({ left: e.deltaY, behavior: 'smooth' });
    }
  }, { passive: false });

  if (typeof ResizeObserver !== 'undefined') {
    if (tabScrollerObserver) tabScrollerObserver.disconnect();
    tabScrollerObserver = new ResizeObserver(() => {
      updateTabArrows();
    });
    tabScrollerObserver.observe(scroller);
    const wrap = scroller.closest('.tabs-wrap') || scroller.parentElement;
    if (wrap && wrap !== scroller) tabScrollerObserver.observe(wrap);
  }

  const leftBtn = document.querySelector('[aria-label="Scroll tabs left"]');
  const rightBtn = document.querySelector('[aria-label="Scroll tabs right"]');
  if (leftBtn) leftBtn.onclick = () => scrollTabsBy(-1);
  if (rightBtn) rightBtn.onclick = () => scrollTabsBy(1);

  const curTab = scroller.querySelector(`.tab[data-tab="${tab}"]`);
  if (curTab) {
    curTab.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }

  updateTabArrows();
  setTimeout(updateTabArrows, 50);
}

/* ---------- editor groups & tabs state ---------- */
const EDITOR_TABS_STORAGE_KEY = 'pcb_advisor_editor_tabs';

const STAGE_TITLES = {
  idea: 'Idea',
  bom: 'BOM',
  sch: 'Schematic',
  pcb: 'Placement & routing',
  rules: 'Rules',
  outputs: 'Altium outputs',
  checks: 'Final manufacturer checks'
};

const PAGE_TITLES = {
  library: 'Altium library',
  sources: 'Sources',
  skills: 'Skills',
  settings: 'Settings'
};

function createStageTab(stageId) {
  const s = stageId || 'bom';
  return {
    id: 'stage:' + s,
    kind: 'stage',
    stage: s,
    title: STAGE_TITLES[s] || s
  };
}

function createFileTab(fileInfo) {
  const id = fileInfo.id || ('file:' + (fileInfo.path || fileInfo.name || fileInfo.slice || 'file'));
  let fileType = fileInfo.fileType || 'file';
  const name = fileInfo.name || id.replace(/^(file|src|altium|slice|export):/, '');
  const ext = (name.includes('.') ? '.' + name.split('.').pop() : '').toLowerCase();
  if (!fileInfo.fileType || fileInfo.fileType === 'file') {
    if (ext === '.pdf') fileType = 'pdf';
    else if (['.schdoc'].includes(ext)) fileType = 'sch';
    else if (['.pcbdoc'].includes(ext)) fileType = 'pcb';
    else if (['.prjpcb'].includes(ext)) fileType = 'prj';
    else if (['.rul'].includes(ext)) fileType = 'rul';
    else if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext)) fileType = 'img';
    else if (['.csv'].includes(ext)) fileType = 'csv';
    else if (['.txt', '.text', '.md', '.markdown', '.json'].includes(ext)) fileType = 'txt';
    else if (fileInfo.stem) fileType = 'dfm';
    else fileType = 'txt';
  }
  return {
    id,
    kind: 'file',
    fileType,
    name,
    title: name,
    path: fileInfo.path || name,
    where: fileInfo.where || '',
    stem: fileInfo.stem || '',
    slice: fileInfo.slice || ''
  };
}

function createPageTab(pageId) {
  return {
    id: 'page:' + pageId,
    kind: 'page',
    page: pageId,
    title: PAGE_TITLES[pageId] || pageId
  };
}

function getStoredEditorState() {
  try {
    const raw = localStorage.getItem(EDITOR_TABS_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    /* storage unavailable */
  }
  return null;
}

function saveStoredEditorState(st) {
  try {
    localStorage.setItem(EDITOR_TABS_STORAGE_KEY, JSON.stringify(st));
  } catch (e) {
    /* storage unavailable */
  }
}

function removeStoredEditorState() {
  try {
    localStorage.removeItem(EDITOR_TABS_STORAGE_KEY);
  } catch (e) {
    /* storage unavailable */
  }
}

function getDefaultEditorState() {
  const initialStage = (!S || (!S.idea?.confirmed && !(S.bom || []).length)) ? 'idea' : (tab || 'bom');
  const stageTab = createStageTab(initialStage);
  return {
    groups: [
      {
        id: 'g1',
        tabs: [stageTab],
        activeTabId: stageTab.id
      }
    ],
    activeGroupId: 'g1',
    isSplit: false,
    splitRatio: 0.5,
    stageStripCollapsed: false
  };
}

let editorState = (function() {
  const saved = getStoredEditorState();
  if (saved && Array.isArray(saved.groups) && saved.groups.length > 0) {
    saved.groups.forEach(g => {
      if (!Array.isArray(g.tabs)) g.tabs = [];
      if (!g.activeTabId && g.tabs.length) g.activeTabId = g.tabs[0].id;
    });
    if (!saved.groups[0].tabs.length) {
      const def = createStageTab('bom');
      saved.groups[0].tabs.push(def);
      saved.groups[0].activeTabId = def.id;
    }
    if (saved.splitRatio == null) saved.splitRatio = 0.5;
    if (!saved.activeGroupId) saved.activeGroupId = saved.groups[0].id;
    return saved;
  }
  return getDefaultEditorState();
})();

function getActiveGroup() {
  let g = editorState.groups.find(x => x.id === editorState.activeGroupId);
  if (!g) {
    g = editorState.groups[0];
    if (g) editorState.activeGroupId = g.id;
  }
  return g;
}

function getActiveTab() {
  const g = getActiveGroup();
  if (!g || !g.tabs.length) return null;
  return g.tabs.find(t => t.id === g.activeTabId) || g.tabs[0];
}

function activateTabInGroup(tabId, groupId) {
  const g = editorState.groups.find(x => x.id === groupId);
  if (!g) return;
  const t = g.tabs.find(x => x.id === tabId);
  if (!t) return;
  g.activeTabId = t.id;
  editorState.activeGroupId = g.id;
  if (t.kind === 'stage') {
    tab = t.stage;
    page = 'workspace';
  } else if (t.kind === 'page') {
    page = t.page;
  }
  saveStoredEditorState(editorState);
  renderCenter(true);
}

function closeTab(tabId, groupId) {
  const g = editorState.groups.find(x => x.id === groupId);
  if (!g) return;
  const idx = g.tabs.findIndex(x => x.id === tabId);
  if (idx === -1) return;
  g.tabs.splice(idx, 1);
  if (g.activeTabId === tabId) {
    if (g.tabs.length > 0) {
      g.activeTabId = g.tabs[Math.min(idx, g.tabs.length - 1)].id;
    } else {
      g.activeTabId = null;
    }
  }
  if (!g.tabs.length) {
    if (editorState.isSplit) {
      unsplitEditor();
      toast('Unsplit: group closed');
      return;
    } else {
      const def = createStageTab(tab || 'bom');
      g.tabs.push(def);
      g.activeTabId = def.id;
    }
  }
  saveStoredEditorState(editorState);
  renderCenter(true);
}

function openStageInActiveGroup(stageId) {
  tab = stageId;
  page = 'workspace';
  for (const g of editorState.groups) {
    const existing = g.tabs.find(t => t.kind === 'stage' && t.stage === stageId);
    if (existing) {
      g.activeTabId = existing.id;
      editorState.activeGroupId = g.id;
      saveStoredEditorState(editorState);
      renderCenter(true);
      return;
    }
  }
  const actGroup = getActiveGroup();
  const newTab = createStageTab(stageId);
  actGroup.tabs.push(newTab);
  actGroup.activeTabId = newTab.id;
  saveStoredEditorState(editorState);
  renderCenter(true);
}

function openFileAsTab(fileInfo) {
  const tabObj = createFileTab(fileInfo);
  for (const g of editorState.groups) {
    const existing = g.tabs.find(t => t.id === tabObj.id);
    if (existing) {
      g.activeTabId = existing.id;
      editorState.activeGroupId = g.id;
      saveStoredEditorState(editorState);
      renderCenter(true);
      return;
    }
  }
  const actGroup = getActiveGroup();
  actGroup.tabs.push(tabObj);
  actGroup.activeTabId = tabObj.id;
  saveStoredEditorState(editorState);
  renderCenter(true);
}

function openPageAsTab(pageId) {
  page = pageId;
  for (const g of editorState.groups) {
    const existing = g.tabs.find(t => t.kind === 'page' && t.page === pageId);
    if (existing) {
      g.activeTabId = existing.id;
      editorState.activeGroupId = g.id;
      saveStoredEditorState(editorState);
      renderCenter(true);
      return;
    }
  }
  const actGroup = getActiveGroup();
  const pageTab = createPageTab(pageId);
  actGroup.tabs.push(pageTab);
  actGroup.activeTabId = pageTab.id;
  saveStoredEditorState(editorState);
  renderCenter(true);
}

function splitEditor() {
  if (editorState.isSplit) return;
  const g1 = editorState.groups[0] || { id: 'g1', tabs: [createStageTab('bom')], activeTabId: 'stage:bom' };
  editorState.groups = [g1];
  let g2Tabs = [];
  if (g1.tabs.length >= 2) {
    const moveIdx = g1.tabs.findIndex(t => t.id !== g1.activeTabId);
    if (moveIdx !== -1) {
      g2Tabs = g1.tabs.splice(moveIdx, 1);
    } else {
      g2Tabs = [g1.tabs.pop()];
    }
  } else {
    const curStage = g1.tabs[0]?.kind === 'stage' ? g1.tabs[0].stage : 'bom';
    const nextStage = curStage === 'idea' ? 'bom' : curStage === 'bom' ? 'sch' : 'bom';
    g2Tabs = [createStageTab(nextStage)];
  }
  const g2 = {
    id: 'g2',
    tabs: g2Tabs,
    activeTabId: g2Tabs[0].id
  };
  editorState.groups.push(g2);
  editorState.isSplit = true;
  editorState.activeGroupId = 'g2';
  if (editorState.splitRatio == null) editorState.splitRatio = 0.5;
  saveStoredEditorState(editorState);
  renderCenter(true);
  toast('Split into two editor groups');
}

function unsplitEditor() {
  if (!editorState.isSplit) return;
  const g1 = editorState.groups[0];
  const g2 = editorState.groups[1];
  if (g1 && g2) {
    for (const t of g2.tabs) {
      if (t.kind === 'stage' && g1.tabs.some(x => x.kind === 'stage' && x.stage === t.stage)) {
        continue;
      }
      g1.tabs.push(t);
    }
  }
  editorState.groups = [g1];
  editorState.isSplit = false;
  editorState.activeGroupId = 'g1';
  saveStoredEditorState(editorState);
  renderCenter(true);
  toast('Editor unsplit to single group');
}

function applyEditorSplitStyles() {
  const g1 = $('#group-g1');
  const g2 = $('#group-g2');
  const divider = $('#editor-split-divider');
  if (!editorState.isSplit || !g2 || !divider) {
    if (g1) { g1.style.flex = '1'; g1.style.width = ''; }
    if (g2) g2.style.display = 'none';
    if (divider) divider.style.display = 'none';
    return;
  }
  const ratio = editorState.splitRatio || 0.5;
  if (g1) {
    g1.style.display = 'flex';
    g1.style.flex = `${ratio}`;
  }
  if (divider) {
    divider.style.display = 'flex';
  }
  if (g2) {
    g2.style.display = 'flex';
    g2.style.flex = `${1 - ratio}`;
  }
}

let activeEditorSplitDrag = null;

function onEditorDividerPointerDown(e) {
  if (e.button !== undefined && e.button !== 0) return;
  const divider = e.currentTarget;
  try { divider.setPointerCapture(e.pointerId); } catch (err) {}
  divider.classList.add('dragging');
  document.body.classList.add('resizing-col');
  const container = $('#editor-groups-container');
  const rect = container ? container.getBoundingClientRect() : { left: 0, width: 1000 };
  activeEditorSplitDrag = {
    pointerId: e.pointerId,
    divider,
    containerLeft: rect.left,
    containerWidth: rect.width
  };
  e.preventDefault();
}

function onEditorDividerPointerMove(e) {
  if (!activeEditorSplitDrag || activeEditorSplitDrag.pointerId !== e.pointerId) return;
  const currentX = e.clientX;
  const ratio = (currentX - activeEditorSplitDrag.containerLeft) / activeEditorSplitDrag.containerWidth;
  if (ratio < 0.12 || ratio > 0.88) {
    onEditorDividerPointerUp(e);
    unsplitEditor();
    toast('Unsplit: divider dragged to edge');
    return;
  }
  editorState.splitRatio = Math.max(0.12, Math.min(0.88, ratio));
  applyEditorSplitStyles();
}

function onEditorDividerPointerUp(e) {
  if (!activeEditorSplitDrag || (e && e.pointerId !== undefined && activeEditorSplitDrag.pointerId !== e.pointerId)) return;
  if (activeEditorSplitDrag.divider) {
    try { activeEditorSplitDrag.divider.releasePointerCapture(activeEditorSplitDrag.pointerId); } catch (err) {}
    activeEditorSplitDrag.divider.classList.remove('dragging');
  }
  document.body.classList.remove('resizing-col');
  activeEditorSplitDrag = null;
  saveStoredEditorState(editorState);
}

function onEditorDividerDblClick(e) {
  editorState.splitRatio = 0.5;
  applyEditorSplitStyles();
  saveStoredEditorState(editorState);
  toast('Split reset to 50/50');
}

function onEditorDividerKeyDown(e) {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault();
    const delta = e.key === 'ArrowLeft' ? -0.05 : 0.05;
    const newRatio = (editorState.splitRatio || 0.5) + delta;
    if (newRatio < 0.12 || newRatio > 0.88) {
      unsplitEditor();
      toast('Unsplit: divider moved to edge');
      return;
    }
    editorState.splitRatio = Math.max(0.12, Math.min(0.88, newRatio));
    applyEditorSplitStyles();
    saveStoredEditorState(editorState);
  }
}

let dragTabInfo = null;

function initGroupTabsDnd(groupEl, group) {
  groupEl.querySelectorAll('.editor-tab').forEach(tabEl => {
    tabEl.ondragstart = e => {
      dragTabInfo = { tabId: tabEl.dataset.tabId, fromGroupId: tabEl.dataset.groupId };
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', tabEl.dataset.tabId);
      tabEl.classList.add('dragging');
    };
    tabEl.ondragend = () => {
      tabEl.classList.remove('dragging');
      dragTabInfo = null;
      document.querySelectorAll('.drop-zone').forEach(el => el.hidden = true);
    };
  });

  const tabsBar = groupEl.querySelector('.editor-tabs');
  if (tabsBar) {
    tabsBar.ondragover = e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
    };
    tabsBar.ondrop = e => {
      e.preventDefault();
      if (!dragTabInfo) return;
      const targetGroupId = group.id;
      const tabId = dragTabInfo.tabId;
      const sourceGroupId = dragTabInfo.fromGroupId;
      const srcGroup = editorState.groups.find(g => g.id === sourceGroupId);
      const dstGroup = editorState.groups.find(g => g.id === targetGroupId);
      if (!srcGroup || !dstGroup) return;

      const tabIdx = srcGroup.tabs.findIndex(t => t.id === tabId);
      if (tabIdx === -1) return;
      const tabObj = srcGroup.tabs[tabIdx];

      const targetTabEl = e.target.closest('.editor-tab');
      let insertIdx = dstGroup.tabs.length;
      if (targetTabEl && targetTabEl.dataset.tabId) {
        const tIdx = dstGroup.tabs.findIndex(t => t.id === targetTabEl.dataset.tabId);
        if (tIdx !== -1) insertIdx = tIdx;
      }

      if (sourceGroupId === targetGroupId) {
        srcGroup.tabs.splice(tabIdx, 1);
        if (insertIdx > tabIdx) insertIdx--;
        srcGroup.tabs.splice(insertIdx, 0, tabObj);
        srcGroup.activeTabId = tabObj.id;
      } else {
        if (tabObj.kind === 'stage' && dstGroup.tabs.some(t => t.kind === 'stage' && t.stage === tabObj.stage)) {
          toast(`Stage ${tabObj.title} is already open in this group`);
          return;
        }
        srcGroup.tabs.splice(tabIdx, 1);
        if (srcGroup.activeTabId === tabId && srcGroup.tabs.length) {
          srcGroup.activeTabId = srcGroup.tabs[Math.max(0, tabIdx - 1)].id;
        }
        dstGroup.tabs.splice(insertIdx, 0, tabObj);
        dstGroup.activeTabId = tabObj.id;
        editorState.activeGroupId = dstGroup.id;
        if (!srcGroup.tabs.length && editorState.isSplit) {
          unsplitEditor();
          return;
        }
      }
      saveStoredEditorState(editorState);
      renderCenter(true);
    };
  }

  const bodyEl = groupEl.querySelector('.editor-group-body');
  if (bodyEl) {
    bodyEl.ondragover = e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const rect = bodyEl.getBoundingClientRect();
      const isLeft = (e.clientX - rect.left) < (rect.width / 2);
      const leftZone = bodyEl.querySelector('.drop-zone-left');
      const rightZone = bodyEl.querySelector('.drop-zone-right');
      if (leftZone && rightZone) {
        leftZone.hidden = !isLeft;
        rightZone.hidden = isLeft;
      }
    };
    bodyEl.ondragleave = e => {
      if (!bodyEl.contains(e.relatedTarget)) {
        const leftZone = bodyEl.querySelector('.drop-zone-left');
        const rightZone = bodyEl.querySelector('.drop-zone-right');
        if (leftZone) leftZone.hidden = true;
        if (rightZone) rightZone.hidden = true;
      }
    };
    bodyEl.ondrop = e => {
      e.preventDefault();
      const leftZone = bodyEl.querySelector('.drop-zone-left');
      const rightZone = bodyEl.querySelector('.drop-zone-right');
      if (leftZone) leftZone.hidden = true;
      if (rightZone) rightZone.hidden = true;
      if (!dragTabInfo) return;
      const rect = bodyEl.getBoundingClientRect();
      const isLeft = (e.clientX - rect.left) < (rect.width / 2);
      dropTabOnBodyHalf(dragTabInfo.tabId, dragTabInfo.fromGroupId, group.id, isLeft ? 'left' : 'right');
    };
  }
}

function dropTabOnBodyHalf(tabId, sourceGroupId, targetGroupId, half) {
  const srcGroup = editorState.groups.find(g => g.id === sourceGroupId);
  if (!srcGroup) return;
  const tabIdx = srcGroup.tabs.findIndex(t => t.id === tabId);
  if (tabIdx === -1) return;
  const tabObj = srcGroup.tabs[tabIdx];

  if (!editorState.isSplit) {
    if (srcGroup.tabs.length <= 1) {
      const curStage = tabObj.kind === 'stage' ? tabObj.stage : 'bom';
      const otherStage = curStage === 'idea' ? 'bom' : curStage === 'bom' ? 'sch' : 'bom';
      srcGroup.tabs.push(createStageTab(otherStage));
    }
    srcGroup.tabs.splice(tabIdx, 1);
    const newGroup = {
      id: 'g2',
      tabs: [tabObj],
      activeTabId: tabObj.id
    };
    if (half === 'left') {
      editorState.groups = [newGroup, srcGroup];
      editorState.groups[0].id = 'g1';
      editorState.groups[1].id = 'g2';
      editorState.activeGroupId = 'g1';
    } else {
      editorState.groups = [srcGroup, newGroup];
      editorState.activeGroupId = 'g2';
    }
    editorState.isSplit = true;
    editorState.splitRatio = 0.5;
    saveStoredEditorState(editorState);
    renderCenter(true);
    toast('Split view created by tab drop');
  } else {
    const dstGroup = half === 'left' ? editorState.groups[0] : editorState.groups[1];
    if (!dstGroup) return;
    if (dstGroup.id === sourceGroupId) return;
    if (tabObj.kind === 'stage' && dstGroup.tabs.some(t => t.kind === 'stage' && t.stage === tabObj.stage)) {
      toast(`Stage ${tabObj.title} is already open in this group`);
      return;
    }
    srcGroup.tabs.splice(tabIdx, 1);
    if (srcGroup.activeTabId === tabId && srcGroup.tabs.length) {
      srcGroup.activeTabId = srcGroup.tabs[Math.max(0, tabIdx - 1)].id;
    }
    dstGroup.tabs.push(tabObj);
    dstGroup.activeTabId = tabObj.id;
    editorState.activeGroupId = dstGroup.id;
    if (!srcGroup.tabs.length) {
      unsplitEditor();
      toast('Unsplit: source group was empty');
      return;
    }
    saveStoredEditorState(editorState);
    renderCenter(true);
    toast(`Tab moved to ${half} group`);
  }
}

function moveActiveTabWithKeyboard(direction) {
  const actGroup = getActiveGroup();
  if (!actGroup || !actGroup.tabs.length) return;
  const curTab = actGroup.tabs.find(t => t.id === actGroup.activeTabId) || actGroup.tabs[0];
  if (!curTab) return;

  if (!editorState.isSplit) {
    if (actGroup.tabs.length <= 1) {
      const curStage = curTab.kind === 'stage' ? curTab.stage : 'bom';
      const otherStage = curStage === 'idea' ? 'bom' : curStage === 'bom' ? 'sch' : 'bom';
      actGroup.tabs.push(createStageTab(otherStage));
    }
    splitEditor();
  } else {
    const otherGroup = editorState.groups.find(g => g.id !== actGroup.id);
    if (!otherGroup) return;
    if (curTab.kind === 'stage' && otherGroup.tabs.some(t => t.kind === 'stage' && t.stage === curTab.stage)) {
      toast(`Stage ${curTab.title} is already open in the other group`);
      return;
    }
    const idx = actGroup.tabs.findIndex(t => t.id === curTab.id);
    actGroup.tabs.splice(idx, 1);
    if (actGroup.tabs.length) {
      actGroup.activeTabId = actGroup.tabs[Math.max(0, idx - 1)].id;
    }
    otherGroup.tabs.push(curTab);
    otherGroup.activeTabId = curTab.id;
    editorState.activeGroupId = otherGroup.id;
    if (!actGroup.tabs.length) {
      unsplitEditor();
      return;
    }
    saveStoredEditorState(editorState);
    renderCenter(true);
    toast(`Moved ${curTab.title} to ${direction} group`);
  }
}

const FILE_BADGES = {
  pdf: 'PDF',
  sch: 'SCH',
  pcb: 'PCB',
  img: 'IMG',
  txt: 'TXT',
  csv: 'TXT',
  dfm: 'PDF',
  rul: 'TXT',
  prj: 'TXT',
  altium: 'SCH'
};

function renderEditorTab(t, groupId, isActive) {
  let badgeHTML = '';
  if (t.kind === 'stage') {
    badgeHTML = `<span class="tab-stage-mark">◆</span>`;
  } else if (t.kind === 'file') {
    const rawBadge = (FILE_BADGES[t.fileType] || t.fileType || 'TXT').toUpperCase();
    const badgeText = ['PDF', 'SCH', 'PCB', 'IMG', 'TXT'].includes(rawBadge) ? rawBadge : (rawBadge === 'PNG' || rawBadge === 'JPG' ? 'IMG' : 'TXT');
    badgeHTML = `<span class="badge ${badgeText.toLowerCase()}">${badgeText}</span>`;
  }
  return `<div class="editor-tab ${isActive ? 'active' : ''}" draggable="true" data-tab-id="${esc(t.id)}" data-group-id="${groupId}" role="tab" aria-selected="${isActive}">
    ${badgeHTML}
    <span class="tab-title" title="${esc(t.title || t.name || t.id)}">${esc(t.title || t.name || t.id)}</span>
    <button type="button" class="tab-close" data-act="close-tab" data-tab-id="${esc(t.id)}" data-group-id="${groupId}" aria-label="Close tab" title="Close tab">×</button>
  </div>`;
}

function renderGroupTabs(groupEl, group) {
  const tabsContainer = groupEl.querySelector('.editor-tabs');
  if (tabsContainer) {
    tabsContainer.innerHTML = group.tabs.map(t => renderEditorTab(t, group.id, t.id === group.activeTabId)).join('');
  }
  const splitBtn = groupEl.querySelector('.editor-split-btn');
  if (splitBtn) {
    if (editorState.isSplit) {
      splitBtn.dataset.act = 'unsplit-editor';
      splitBtn.setAttribute('aria-label', 'Unsplit editor');
      splitBtn.setAttribute('title', 'Unsplit editor (▭)');
      splitBtn.textContent = '▭';
    } else {
      splitBtn.dataset.act = 'split-editor';
      splitBtn.setAttribute('aria-label', 'Split editor');
      splitBtn.setAttribute('title', 'Split editor (⇆)');
      splitBtn.textContent = '⇆';
    }
  }
}

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

function renderGroupContent(group, container, force) {
  const activeTab = group.tabs.find(t => t.id === group.activeTabId) || group.tabs[0];
  if (!activeTab) {
    container.innerHTML = '<div class="dnote" style="margin:20px">No open tabs in this editor group.</div>';
    return;
  }
  container.dataset.activeTabKind = activeTab.kind;
  container.dataset.activeTabId = activeTab.id;
  container.classList.toggle('stage-idea', activeTab.stage === 'idea' || activeTab.id === 'idea');

  if (activeTab.kind === 'stage') {
    if (activeTab.stage === 'idea' && container.querySelector('.diagram-mount-point')) {
      updateIdeaContent(container);
    } else {
      renderStage(activeTab.stage, container);
      if (activeTab.stage === 'idea') mountDiagramEditor(container);
    }
    if (activeTab.stage === 'sch' && S && S.sheets && S.sheets.length) loadSheet(container);
    if (activeTab.stage === 'rules' && !RULES_DATA) loadRules();
    if (activeTab.stage === 'bom') loadImportInfo();
    if (activeTab.stage === 'pcb') loadPcb(container);
  } else if (activeTab.kind === 'page') {
    renderPage(activeTab.page, container);
    if (activeTab.page === 'settings' && !ALTIUM_DATA) loadAltium();
    if (activeTab.page === 'sources' && hitSrc) {
      const r = container.querySelector('#src-' + hitSrc.replace(/[^\w-]/g, '_'));
      if (r) r.scrollIntoView({ block: 'center' });
      hitSrc = null;
    }
  } else if (activeTab.kind === 'file') {
    renderFileTabContent(activeTab, container);
  }
}

function renderEditorGroups(force) {
  const container = $('#editor-groups-container');
  if (!container) return;

  const isSplit = !!(editorState.isSplit && editorState.groups.length >= 2);
  container.classList.toggle('is-split', isSplit);

  // Group 1
  const g1 = editorState.groups[0];
  const g1El = $('#group-g1');
  if (g1El && g1) {
    g1El.classList.toggle('active', editorState.activeGroupId === g1.id);
    renderGroupTabs(g1El, g1);
    const view1 = g1El.querySelector('.editor-content');
    if (view1) renderGroupContent(g1, view1, force);
    initGroupTabsDnd(g1El, g1);
  }

  // Divider
  let dividerEl = $('#editor-divider');
  if (isSplit) {
    if (!dividerEl) {
      dividerEl = document.createElement('div');
      dividerEl.className = 'editor-divider';
      dividerEl.id = 'editor-divider';
      dividerEl.tabIndex = 0;
      dividerEl.setAttribute('aria-label', 'Resize editor split');
      dividerEl.setAttribute('title', 'Drag to resize split (double click for 50/50)');
      dividerEl.addEventListener('pointerdown', onEditorDividerPointerDown);
      dividerEl.addEventListener('dblclick', onEditorDividerDblClick);
      dividerEl.addEventListener('keydown', onEditorDividerKeyDown);
      const g2El = $('#group-g2');
      if (g2El) container.insertBefore(dividerEl, g2El);
      else container.appendChild(dividerEl);
    }
    dividerEl.style.display = '';
  } else if (dividerEl) {
    dividerEl.style.display = 'none';
  }

  // Group 2
  const g2 = isSplit ? editorState.groups[1] : null;
  let g2El = $('#group-g2');
  if (isSplit && g2) {
    if (!g2El) {
      g2El = document.createElement('div');
      g2El.className = 'editor-group';
      g2El.id = 'group-g2';
      g2El.dataset.groupId = 'g2';
      g2El.innerHTML = `
        <div class="editor-tabs-bar" id="tabs-bar-g2">
          <div class="editor-tabs" role="tablist" aria-label="Editor tabs group 2"></div>
          <div class="editor-group-actions">
            <button type="button" class="editor-split-btn" data-act="unsplit-editor" data-group-id="g2" aria-label="Unsplit editor" title="Unsplit editor (▭)">▭</button>
          </div>
        </div>
        <div class="editor-group-body">
          <div class="drop-zone drop-zone-left" hidden>Drop to split left</div>
          <div class="drop-zone drop-zone-right" hidden>Drop to split right</div>
          <div class="view editor-content" id="view-g2" data-group-id="g2"></div>
        </div>
      `;
      container.appendChild(g2El);
    }
    g2El.style.display = '';
    g2El.classList.toggle('active', editorState.activeGroupId === g2.id);
    renderGroupTabs(g2El, g2);
    const view2 = g2El.querySelector('.editor-content');
    if (view2) renderGroupContent(g2, view2, force);
    initGroupTabsDnd(g2El, g2);
  } else if (g2El) {
    g2El.style.display = 'none';
  }

  applyEditorSplitStyles();
}

function wheadHTML() {
  const isCollapsed = !!(editorState && editorState.stageStripCollapsed);
  const toggleBtn = `<button type="button" class="stage-strip-toggle" data-act="toggle-stage-strip" aria-label="${isCollapsed ? 'Expand stage strip' : 'Collapse stage strip'}" title="${isCollapsed ? 'Expand stage strip' : 'Collapse stage strip'}">${isCollapsed ? '▾' : '▴'}</button>`;
  const wheadEl = $('#whead');
  if (wheadEl) wheadEl.classList.toggle('collapsed', isCollapsed);
  if (isCollapsed) {
    return `<div style="display:flex;align-items:center;justify-content:space-between;width:100%"><span style="font-size:11.5px;color:var(--dim);font-weight:600">STAGES LAUNCHER</span>${toggleBtn}</div>`;
  }
  const t = S ? S.totals : {lines:0};
  const actTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
  const activeStage = (actTab && actTab.kind === 'stage') ? actTab.stage : null;
  const items = [
    ['idea', '1', 'Idea', (S && S.idea && S.idea.confirmed) ? `<span class="st ok">Confirmed</span>` : `<span class="st dim">Open</span>`],
    ['bom', '2', 'BOM', t.out_of_stock ? `<span class="st bad">${t.out_of_stock} out of stock</span>` : t.to_verify ? `<span class="st warn">${t.to_verify} to review</span>` : t.checking ? `<span class="st dim">checking</span>` : t.lines ? `<span class="st ok">Ready</span>` : `<span class="st dim">Empty</span>`],
    ['sch', '3', 'Schematic', `<span class="st dim">${(S && S.sheets) ? S.sheets.length : 0} sheet${(S && S.sheets && S.sheets.length === 1) ? '' : 's'}</span>`],
    ['pcb', '4', 'Placement & routing', `<span class="st dim">Plan</span>`],
    ['rules', '5', 'Rules', RULES_DATA ? `<span class="st ok">${RULES_DATA.preset?.rules?.length || 7} preset</span>` : `<span class="st dim">JLC preset</span>`],
    ['outputs', '6', 'Altium outputs', `<span class="st dim">${((S && S.exports) || []).length} file${((S && S.exports) || []).length === 1 ? '' : 's'}</span>`],
    ['checks', '7', 'Final manufacturer checks', `<span class="st dim">${((S && S.checks) || []).length} report${((S && S.checks) || []).length === 1 ? '' : 's'}</span>`],
  ];
  return `<div class="tabs-wrap"><button type="button" class="tab-arrow prev" data-act="scroll-tabs-left" aria-label="Scroll tabs left" title="Scroll tabs left">‹</button><div class="tabs tabs-scroller" id="tabs-scroller" role="tablist">${items.map(([id, n, label, st]) => `<button class="tab" role="tab" data-tab="${id}" aria-selected="${activeStage === id}"><span class="n">${n}</span>${label}${st}</button>`).join('')}</div><button type="button" class="tab-arrow next" data-act="scroll-tabs-right" aria-label="Scroll tabs right" title="Scroll tabs right">›</button>${toggleBtn}</div>`;
}

/* ---------- layout resizing & persistence ---------- */
const LAYOUT_STORAGE_KEY = 'pcb_advisor_layout';
const MIN_CENTER_WIDTH = 240;
const COLLAPSE_SIDE_THRESHOLD = 120;
const COLLAPSE_CENTER_THRESHOLD = 120;
const COLLAPSE_NAV_THRESHOLD = 55;
const RESIZE_KEY_STEP = 16;

const DEFAULT_LAYOUT = {
  chatWidth: 340,
  navWidth: 216,
  chatHidden: false,
  centerHidden: false,
  navHidden: false,
  lastChatWidth: 340,
  lastNavWidth: 216
};

function getStoredLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    /* storage unavailable */
  }
  return null;
}

function saveLayoutToStorage(st) {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(st));
  } catch (e) {
    /* storage unavailable */
  }
}

function removeLayoutFromStorage() {
  try {
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
  } catch (e) {
    /* storage unavailable */
  }
}

let layoutState = Object.assign({}, DEFAULT_LAYOUT);
const _saved = getStoredLayout();
if (_saved && typeof _saved === 'object') {
  if (typeof _saved.chatWidth === 'number' && _saved.chatWidth >= 0) layoutState.chatWidth = _saved.chatWidth;
  if (typeof _saved.navWidth === 'number' && _saved.navWidth >= 0) layoutState.navWidth = _saved.navWidth;
  if (typeof _saved.lastChatWidth === 'number' && _saved.lastChatWidth >= COLLAPSE_SIDE_THRESHOLD) layoutState.lastChatWidth = _saved.lastChatWidth;
  if (typeof _saved.lastNavWidth === 'number' && _saved.lastNavWidth >= COLLAPSE_NAV_THRESHOLD) layoutState.lastNavWidth = _saved.lastNavWidth;
  layoutState.chatHidden = !!_saved.chatHidden;
  layoutState.centerHidden = !!_saved.centerHidden;
  layoutState.navHidden = !!_saved.navHidden;
}

function applyLayout() {
  const app = $('#app');
  if (!app) return;
  if (matchMedia('(max-width:860px)').matches) return;

  const chat = app.querySelector('.chat');
  const work = app.querySelector('.work');
  const nav = app.querySelector('.nav');
  const splitChat = $('#splitter-chat');
  const splitNav = $('#splitter-nav');

  if (chat) chat.hidden = !!layoutState.chatHidden;
  if (work) work.hidden = !!layoutState.centerHidden;
  if (nav) nav.hidden = !!layoutState.navHidden;

  const chatCol = layoutState.chatHidden ? '0px' : `${layoutState.chatWidth || 340}px`;
  const navCol = layoutState.navHidden ? '0px' : `${layoutState.navWidth || 216}px`;

  if (layoutState.centerHidden) {
    if (!layoutState.chatHidden && !layoutState.navHidden) {
      app.style.gridTemplateColumns = '1fr 6px 0px 6px 1fr';
    } else if (!layoutState.chatHidden) {
      app.style.gridTemplateColumns = '1fr 6px 0px 6px 0px';
    } else if (!layoutState.navHidden) {
      app.style.gridTemplateColumns = '0px 6px 0px 6px 1fr';
    } else {
      if (work) work.hidden = false;
      layoutState.centerHidden = false;
      app.style.gridTemplateColumns = '0px 6px minmax(0,1fr) 6px 0px';
    }
  } else {
    app.style.gridTemplateColumns = `${chatCol} 6px minmax(0,1fr) 6px ${navCol}`;
  }

  if (nav && !layoutState.navHidden) {
    const isCompact = (layoutState.navWidth >= 60 && layoutState.navWidth <= 150);
    nav.classList.toggle('compact', isCompact);
  }

  if (splitChat) {
    splitChat.setAttribute('aria-valuenow', layoutState.chatHidden ? 0 : layoutState.chatWidth);
    splitChat.setAttribute('aria-expanded', !layoutState.chatHidden);
  }
  if (splitNav) {
    splitNav.setAttribute('aria-valuenow', layoutState.navHidden ? 0 : layoutState.navWidth);
    splitNav.setAttribute('aria-expanded', !layoutState.navHidden);
  }

  saveLayoutToStorage(layoutState);
}

function resetLayout() {
  removeLayoutFromStorage();
  layoutState = Object.assign({}, DEFAULT_LAYOUT);
  applyLayout();
  removeStoredEditorState();
  editorState = getDefaultEditorState();
  renderCenter(true);
}

let activeDrag = null;

function onSplitterPointerDown(e, type) {
  if (e.button !== undefined && e.button !== 0) return;
  if (matchMedia('(max-width:860px)').matches) return;

  const splitter = e.currentTarget;
  try { splitter.setPointerCapture(e.pointerId); } catch (err) {}
  splitter.classList.add('dragging');
  document.body.classList.add('resizing-col');

  activeDrag = {
    type,
    pointerId: e.pointerId,
    splitter,
    startX: e.clientX,
    startChatW: layoutState.chatWidth,
    startNavW: layoutState.navWidth,
    wasChatHidden: layoutState.chatHidden,
    wasNavHidden: layoutState.navHidden,
    wasCenterHidden: layoutState.centerHidden
  };

  e.preventDefault();
}

function onSplitterPointerMove(e) {
  if (!activeDrag || activeDrag.pointerId !== e.pointerId) return;

  const app = $('#app');
  if (!app) return;
  const appRect = app.getBoundingClientRect();
  const cs = getComputedStyle(app);
  const padLeft = parseFloat(cs.paddingLeft) || 16;
  const padRight = parseFloat(cs.paddingRight) || 16;
  const totalW = appRect.width - padLeft - padRight - 12;

  if (activeDrag.type === 'chat') {
    const currentNavW = layoutState.navHidden ? 0 : (layoutState.navWidth || 216);
    const availForChatAndCenter = Math.max(0, totalW - currentNavW);
    const targetW = e.clientX - appRect.left - padLeft;

    if (targetW < COLLAPSE_SIDE_THRESHOLD) {
      layoutState.chatHidden = true;
      layoutState.chatWidth = 0;
    } else {
      layoutState.chatHidden = false;
      const remainingForCenter = availForChatAndCenter - targetW;
      if (layoutState.centerHidden) {
        if (remainingForCenter >= COLLAPSE_CENTER_THRESHOLD) {
          layoutState.centerHidden = false;
          layoutState.chatWidth = Math.round(Math.min(availForChatAndCenter - MIN_CENTER_WIDTH, targetW));
          layoutState.lastChatWidth = layoutState.chatWidth;
        } else {
          layoutState.chatWidth = Math.round(Math.min(availForChatAndCenter, targetW));
          layoutState.lastChatWidth = layoutState.chatWidth;
        }
      } else {
        if (remainingForCenter < COLLAPSE_CENTER_THRESHOLD) {
          layoutState.centerHidden = true;
          layoutState.chatWidth = Math.round(Math.min(availForChatAndCenter, targetW));
          layoutState.lastChatWidth = layoutState.chatWidth;
        } else if (remainingForCenter < MIN_CENTER_WIDTH) {
          layoutState.centerHidden = false;
          layoutState.chatWidth = Math.max(COLLAPSE_SIDE_THRESHOLD, Math.round(availForChatAndCenter - MIN_CENTER_WIDTH));
          layoutState.lastChatWidth = layoutState.chatWidth;
        } else {
          layoutState.centerHidden = false;
          layoutState.chatWidth = Math.round(targetW);
          layoutState.lastChatWidth = layoutState.chatWidth;
        }
      }
    }
    applyLayout();
  } else if (activeDrag.type === 'nav') {
    const currentChatW = layoutState.chatHidden ? 0 : (layoutState.chatWidth || 340);
    const availForNavAndCenter = Math.max(0, totalW - currentChatW);
    const targetW = (appRect.right - padRight) - e.clientX;

    if (targetW < COLLAPSE_NAV_THRESHOLD) {
      layoutState.navHidden = true;
      layoutState.navWidth = 0;
    } else {
      layoutState.navHidden = false;
      const remainingForCenter = availForNavAndCenter - targetW;
      if (layoutState.centerHidden) {
        if (remainingForCenter >= COLLAPSE_CENTER_THRESHOLD) {
          layoutState.centerHidden = false;
          layoutState.navWidth = Math.round(Math.min(availForNavAndCenter - MIN_CENTER_WIDTH, targetW));
          layoutState.lastNavWidth = layoutState.navWidth;
        } else {
          layoutState.navWidth = Math.round(Math.min(availForNavAndCenter, targetW));
          layoutState.lastNavWidth = layoutState.navWidth;
        }
      } else {
        if (remainingForCenter < COLLAPSE_CENTER_THRESHOLD) {
          layoutState.centerHidden = true;
          layoutState.navWidth = Math.round(Math.min(availForNavAndCenter, targetW));
          layoutState.lastNavWidth = layoutState.navWidth;
        } else if (remainingForCenter < MIN_CENTER_WIDTH) {
          layoutState.centerHidden = false;
          layoutState.navWidth = Math.max(COLLAPSE_NAV_THRESHOLD, Math.round(availForNavAndCenter - MIN_CENTER_WIDTH));
          layoutState.lastNavWidth = layoutState.navWidth;
        } else {
          layoutState.centerHidden = false;
          layoutState.navWidth = Math.round(targetW);
          layoutState.lastNavWidth = layoutState.navWidth;
        }
      }
    }
    applyLayout();
  }
}

function onSplitterPointerUp(e) {
  if (!activeDrag || (e && e.pointerId !== undefined && activeDrag.pointerId !== e.pointerId)) return;
  if (activeDrag.splitter) {
    try { activeDrag.splitter.releasePointerCapture(activeDrag.pointerId); } catch (err) {}
    activeDrag.splitter.classList.remove('dragging');
  }
  document.body.classList.remove('resizing-col');
  activeDrag = null;
  saveLayoutToStorage(layoutState);
}

function onSplitterKeyDown(e, type) {
  if (matchMedia('(max-width:860px)').matches) return;

  const app = $('#app');
  if (!app) return;
  const appRect = app.getBoundingClientRect();
  const cs = getComputedStyle(app);
  const padLeft = parseFloat(cs.paddingLeft) || 16;
  const padRight = parseFloat(cs.paddingRight) || 16;
  const totalW = appRect.width - padLeft - padRight - 12;

  if (e.key === 'Enter') {
    e.preventDefault();
    if (layoutState.centerHidden) {
      layoutState.centerHidden = false;
      applyLayout();
      return;
    }
    if (type === 'chat') {
      if (layoutState.chatHidden) {
        layoutState.chatHidden = false;
        layoutState.chatWidth = layoutState.lastChatWidth || 340;
      } else {
        layoutState.lastChatWidth = layoutState.chatWidth;
        layoutState.chatHidden = true;
        layoutState.chatWidth = 0;
      }
    } else if (type === 'nav') {
      if (layoutState.navHidden) {
        layoutState.navHidden = false;
        layoutState.navWidth = layoutState.lastNavWidth || 216;
      } else {
        layoutState.lastNavWidth = layoutState.navWidth;
        layoutState.navHidden = true;
        layoutState.navWidth = 0;
      }
    }
    applyLayout();
    return;
  }

  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault();
    const delta = (e.key === 'ArrowRight' ? RESIZE_KEY_STEP : -RESIZE_KEY_STEP);

    if (type === 'chat') {
      if (delta > 0) {
        if (layoutState.chatHidden) {
          layoutState.chatHidden = false;
          layoutState.chatWidth = Math.max(COLLAPSE_SIDE_THRESHOLD, layoutState.lastChatWidth || 340);
        } else {
          const currentNavW = layoutState.navHidden ? 0 : (layoutState.navWidth || 216);
          const avail = totalW - currentNavW;
          const targetW = layoutState.chatWidth + delta;
          const remCenter = avail - targetW;
          if (remCenter < COLLAPSE_CENTER_THRESHOLD) {
            layoutState.centerHidden = true;
            layoutState.chatWidth = Math.min(avail, targetW);
          } else if (remCenter < MIN_CENTER_WIDTH) {
            layoutState.chatWidth = Math.max(COLLAPSE_SIDE_THRESHOLD, avail - MIN_CENTER_WIDTH);
          } else {
            layoutState.chatWidth = targetW;
          }
          layoutState.lastChatWidth = layoutState.chatWidth;
        }
      } else {
        if (layoutState.centerHidden) {
          layoutState.centerHidden = false;
        } else if (!layoutState.chatHidden) {
          const targetW = layoutState.chatWidth + delta;
          if (targetW < COLLAPSE_SIDE_THRESHOLD) {
            layoutState.lastChatWidth = layoutState.chatWidth;
            layoutState.chatHidden = true;
            layoutState.chatWidth = 0;
          } else {
            layoutState.chatWidth = targetW;
            layoutState.lastChatWidth = layoutState.chatWidth;
          }
        }
      }
      applyLayout();
    } else if (type === 'nav') {
      const navDelta = (e.key === 'ArrowLeft' ? RESIZE_KEY_STEP : -RESIZE_KEY_STEP);
      if (navDelta > 0) {
        if (layoutState.navHidden) {
          layoutState.navHidden = false;
          layoutState.navWidth = Math.max(60, layoutState.lastNavWidth || 216);
        } else {
          const currentChatW = layoutState.chatHidden ? 0 : (layoutState.chatWidth || 340);
          const avail = totalW - currentChatW;
          const targetW = layoutState.navWidth + navDelta;
          const remCenter = avail - targetW;
          if (remCenter < COLLAPSE_CENTER_THRESHOLD) {
            layoutState.centerHidden = true;
            layoutState.navWidth = Math.min(avail, targetW);
          } else if (remCenter < MIN_CENTER_WIDTH) {
            layoutState.navWidth = Math.max(COLLAPSE_NAV_THRESHOLD, avail - MIN_CENTER_WIDTH);
          } else {
            layoutState.navWidth = targetW;
          }
          layoutState.lastNavWidth = layoutState.navWidth;
        }
      } else {
        if (layoutState.centerHidden) {
          layoutState.centerHidden = false;
        } else if (!layoutState.navHidden) {
          const targetW = layoutState.navWidth + navDelta;
          if (targetW < COLLAPSE_NAV_THRESHOLD) {
            layoutState.lastNavWidth = layoutState.navWidth;
            layoutState.navHidden = true;
            layoutState.navWidth = 0;
          } else {
            layoutState.navWidth = targetW;
            layoutState.lastNavWidth = layoutState.navWidth;
          }
        }
      }
      applyLayout();
    }
  }
}

function onSplitterDblClick(e, type) {
  if (matchMedia('(max-width:860px)').matches) return;
  if (layoutState.centerHidden) {
    layoutState.centerHidden = false;
    applyLayout();
    return;
  }
  if (type === 'chat') {
    if (layoutState.chatHidden) {
      layoutState.chatHidden = false;
      layoutState.chatWidth = layoutState.lastChatWidth || 340;
    } else {
      layoutState.lastChatWidth = layoutState.chatWidth;
      layoutState.chatHidden = true;
      layoutState.chatWidth = 0;
    }
  } else if (type === 'nav') {
    if (layoutState.navHidden) {
      layoutState.navHidden = false;
      layoutState.navWidth = layoutState.lastNavWidth || 216;
    } else {
      layoutState.lastNavWidth = layoutState.navWidth;
      layoutState.navHidden = true;
      layoutState.navWidth = 0;
    }
  }
  applyLayout();
}

function initResize() {
  const splitChat = $('#splitter-chat');
  const splitNav = $('#splitter-nav');
  if (splitChat) {
    splitChat.addEventListener('pointerdown', e => onSplitterPointerDown(e, 'chat'));
    splitChat.addEventListener('keydown', e => onSplitterKeyDown(e, 'chat'));
    splitChat.addEventListener('dblclick', e => onSplitterDblClick(e, 'chat'));
  }
  if (splitNav) {
    splitNav.addEventListener('pointerdown', e => onSplitterPointerDown(e, 'nav'));
    splitNav.addEventListener('keydown', e => onSplitterKeyDown(e, 'nav'));
    splitNav.addEventListener('dblclick', e => onSplitterDblClick(e, 'nav'));
  }
  window.addEventListener('pointermove', onSplitterPointerMove);
  window.addEventListener('pointerup', onSplitterPointerUp);
  window.addEventListener('pointercancel', onSplitterPointerUp);
  window.addEventListener('resize', () => {
    if (matchMedia('(max-width:860px)').matches) {
      const app = $('#app');
      if (app) app.style.gridTemplateColumns = '';
    } else {
      applyLayout();
    }
  });
  applyLayout();
}

document.addEventListener('keydown', e => {
  if (e.ctrlKey && e.altKey) {
    if (e.key === 'ArrowLeft' || e.key === 'Left') {
      e.preventDefault();
      moveActiveTabWithKeyboard('left');
    } else if (e.key === 'ArrowRight' || e.key === 'Right') {
      e.preventDefault();
      moveActiveTabWithKeyboard('right');
    }
  }
});

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('projmenu', async (el, d, e) => {
  toggleProjMenu(); return;
});
onAct('scroll-tabs-left', async (el, d, e) => {
  scrollTabsBy(-1); return;
});
onAct('scroll-tabs-right', async (el, d, e) => {
  scrollTabsBy(1); return;
});
onAct('close-tab', async (el, d, e) => {
  closeTab(d.tabId || el.dataset.tabId, d.groupId || el.dataset.groupId); return;
});
onAct('split-editor', async (el, d, e) => {
  splitEditor(); return;
});
onAct('side-open', async (el, d, e) => {   // "Side by side" in a view header (kit.js viewHeader); the shell redesign replaces this
  splitEditor(); return;
});
onAct('unsplit-editor', async (el, d, e) => {
  unsplitEditor(); return;
});
onAct('toggle-stage-strip', async (el, d, e) => {
  editorState.stageStripCollapsed = !editorState.stageStripCollapsed; saveStoredEditorState(editorState); $('#whead').innerHTML = wheadHTML(); return;
});
onAct('reset-layout', async (el, d, e) => {
  resetLayout(); toast('Layout reset to default'); return;
});
onAct('newproj', async (el, d, e) => {
  const n = prompt('Name of the new project'); if (!n) return;
  const r = await api('/api/projects/new', {name: n}); const u = new URL(location.href); u.searchParams.set('project', r.created); u.searchParams.delete('session'); location.href = u; return;
});
