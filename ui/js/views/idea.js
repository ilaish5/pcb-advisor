/* PCB Advisor UI - Idea view: the agreed requirements (a flat list), the block diagram (ui/diagram.js) and the agent's
   diagram proposals. Shell hooks: ideaHTML(container), updateIdeaContent(container), mountDiagramEditor(container). */

const ideaEditors = new Set();   // live DiagramEditors; one per Idea sheet on screen, destroyed when their canvas leaves the page
let ideaPreviewPid = '';         // id of the diagram proposal shown on the canvas ('' = none)
let ideaForce = false;           // set around my own redraws: the list is redrawn even while a form is open
let ideaSplit = null;            // cap on the requirements list, percent of the sheet body (0 = the default); null = not read yet
let ideaSplitDrag = null;
const IDEA_SPLIT_KEY = 'pcb_advisor_idea_split';
const IDEA_SPLIT_MIN = 12, IDEA_SPLIT_MAX = 70, IDEA_SPLIT_STEP = 3;

/* ---------- small helpers ---------- */
const ideaDiagram = () => (S && S.idea && S.idea.diagram) || {shapes: [], connectors: [], frames: []};
const ideaItems = () => (S && S.idea && S.idea.agreed) || [];
const ideaGoal = () => ((S && S.idea && S.idea.goal) || '').trim();
const descProposed = () => !!ideaGoal() && S.idea.goal_status === 'proposed';
function pendingDiagramProposal() {
  return ((S && S.proposals) || []).find(p => p.kind === 'idea_diagram' && p.status === 'pending') || null;
}
function proposalDiagram(p) {
  return p && p.changes && p.changes.diagram && typeof p.changes.diagram === 'object' ? p.changes.diagram : null;
}
function ideaDate(iso) {
  const d = iso ? new Date(iso) : null;
  if (!d || isNaN(d)) return '';
  const o = {day: 'numeric', month: 'short'};
  if (d.getFullYear() !== new Date().getFullYear()) o.year = 'numeric';
  return d.toLocaleDateString(undefined, o);
}
function loadIdeaSplit() {
  try {
    const v = parseFloat(localStorage.getItem(IDEA_SPLIT_KEY));
    return v >= IDEA_SPLIT_MIN && v <= IDEA_SPLIT_MAX ? v : 0;
  } catch (e) {
    return 0;   // storage blocked: the default split
  }
}
function saveIdeaSplit(pct) {
  try {
    if (pct) localStorage.setItem(IDEA_SPLIT_KEY, String(Math.round(pct * 10) / 10));
    else localStorage.removeItem(IDEA_SPLIT_KEY);
  } catch (e) {
    /* storage blocked: the split lasts for this page only */
  }
}
function ideaSplitPct() {
  if (ideaSplit === null) ideaSplit = loadIdeaSplit();
  return ideaSplit;
}
// A call that changes the project: the new state replaces S. api() has already toasted an error answer; only a dead server is left to say.
async function ideaPost(url, body) {
  try {
    const res = await api(url, body);
    setState(res);
    return res;
  } catch (e) {
    if (e instanceof TypeError) toast("Couldn't reach the server");
    return null;
  }
}
function ideaRedraw() {
  ideaForce = true;
  try { render(true); } finally { ideaForce = false; }
}

/* ---------- the diagram editor: one per canvas, destroyed with it ---------- */
function releaseIdeaEditors(container) {
  for (const ed of [...ideaEditors]) {
    if (!ed.mountEl.isConnected || (container && container.contains(ed.mountEl))) {
      ed.destroy();
      ideaEditors.delete(ed);
    }
  }
}
// The proposal on the canvas, if there is one and it is still pending; otherwise the live diagram.
function syncIdeaCanvas() {
  const p = pendingDiagramProposal();
  const prev = p && ideaPreviewPid === p.id ? proposalDiagram(p) : null;
  if (!prev) ideaPreviewPid = '';
  for (const ed of ideaEditors) ed.setPreview(prev);
}
function mountDiagramEditor(container) {
  const mountEl = (container || document).querySelector('.diagram-mount-point');
  if (!mountEl) return;
  releaseIdeaEditors(null);
  if (mountEl._diagramEditor) return;
  if (typeof DiagramEditor === 'undefined') {
    const sc = document.createElement('script');
    sc.src = '/ui/diagram.js';
    sc.onload = () => mountDiagramEditor(container);
    document.head.appendChild(sc);
    return;
  }
  const mountProject = PROJECT;
  const ed = DiagramEditor.mount(mountEl, {
    project: PROJECT,
    session: SESSION,
    data: ideaDiagram(),
    onSave: async (diagData) => {
      // a save flushed as the project is switched must not land in the project that is now open
      if (PROJECT !== mountProject) return;
      if (S && S.idea) S.idea.diagram = diagData;
      await api('/api/idea/diagram', {diagram: diagData});
    },
    onServerUndo: async () => {
      const res = await api('/api/idea/diagram/undo', {});
      if (res && res.diagram) {
        setState(res);
        return res.diagram;
      }
    },
    // an editor that cleans up after itself (its canvas left the page) must not stay in the set
    onDestroy: e => { ideaEditors.delete(e); },
    // the editor left the preview by itself (the diagram changed under it): the bar must stop saying "previewing"
    onPreview: on => {
      if (on) return;
      ideaPreviewPid = '';
      const canvas = mountEl.closest('.idea-canvas');
      if (canvas) refreshIdeaBar(canvas);
    }
  });
  mountEl._diagramEditor = ed;
  ideaEditors.add(ed);
  syncIdeaCanvas();
}

/* ---------- pieces of the sheet ---------- */
function ideaHeaderHTML() {
  const I = (S && S.idea) || {}, items = ideaItems();
  const proposed = items.filter(i => i.status !== 'confirmed').length + (descProposed() ? 1 : 0);
  const when = ideaDate(I.confirmed_at);
  const meta = metaLine([
    {n: items.length, label: items.length === 1 ? 'requirement' : 'requirements'},
    {n: proposed, label: 'proposed', tone: 'warn', title: 'The agent proposed these. Accept or dismiss each one.'},
    I.confirmed ? 'confirmed' + (when ? ' ' + when : '') : ''
  ]);
  let primary;
  if (I.confirmed) {
    primary = btn('Next: BOM', {kind: 'pri', act: 'idea-next'});
  } else {
    const why = !items.length ? 'Add a requirement first' : (proposed ? 'Accept or dismiss the proposals first' : 'Mark the idea as agreed');
    primary = btn('Confirm idea', {kind: 'pri', act: 'confirmidea', disabled: !items.length || proposed > 0, title: why});
  }
  return viewHeader({title: 'Idea', meta, primary});
}

function reqRowHTML(i, idx) {
  const proposed = i.status !== 'confirmed';
  const by = i.by === 'student' ? 'Written by you' : 'Suggested by the agent';
  const acts = proposed
    ? btn('Accept', {size: 'sm', icon: 'check', act: 'confirm-req', title: 'Agree to this requirement'}) +
      btn('Dismiss', {size: 'sm', act: 'delete-req', title: 'Remove this proposal'})
    : btn('', {size: 'sm', icon: 'edit', act: 'edit-req', title: 'Edit requirement'}) +
      btn('', {size: 'sm', icon: 'trash', act: 'delete-req', title: 'Delete requirement'});
  return `<li class="req-row${proposed ? ' is-proposed' : ''}" tabindex="${idx === 0 ? 0 : -1}" data-index="${idx}" data-topic="${esc(i.topic)}" title="${esc(by)}">
      <span class="req-drag-handle" title="Drag to reorder" aria-label="Drag to reorder">${icon('grip')}</span>
      <div class="req-main">
        <div class="req-view"><p class="req-line" dir="auto">${proposed ? tag('Proposed', 'warn') + ' ' : ''}<b class="req-topic">${esc(i.topic)}</b> <span class="req-text">${esc(i.text)}</span></p></div>
        <div class="req-edit-form" hidden>
          <input type="text" class="in req-edit-topic" value="${esc(i.topic)}" maxlength="60" placeholder="Topic" aria-label="Topic">
          <textarea class="in req-edit-text" maxlength="1000" rows="3" placeholder="Requirement" aria-label="Requirement" title="Enter saves, Shift+Enter adds a line, Esc cancels" dir="auto">${esc(i.text)}</textarea>
          <div class="acts">${btn('Save', {size: 'sm', kind: 'line', act: 'save-req'})}${btn('Cancel', {size: 'sm', act: 'cancel-req'})}</div>
        </div>
      </div>
      <div class="req-acts">${acts}</div>
    </li>`;
}

function descHTML() {
  const I = (S && S.idea) || {};
  const goal = (I.goal || '').trim();
  const proposed = descProposed();
  const by = I.goal_by === 'agent' ? 'Suggested by the agent' : 'Written by you';
  const titleAttr = goal ? ` title="${esc(by)}"` : '';
  const acts = proposed
    ? btn('Accept', {size: 'sm', icon: 'check', act: 'confirm-desc', title: 'Agree to this description'}) +
      btn('Dismiss', {size: 'sm', act: 'dismiss-desc', title: 'Remove this proposal'})
    : (goal ? btn('', {size: 'sm', icon: 'edit', act: 'edit-desc', title: 'Edit description'}) : '');
  const content = goal
    ? `<p class="desc-text" dir="auto">${proposed ? tag('Proposed', 'warn') + ' ' : ''}${esc(goal)}</p>`
    : `<button type="button" class="desc-empty" data-act="edit-desc">Describe the board in a few sentences</button>`;
  return `<div class="desc-block${proposed ? ' is-proposed' : ''}"${titleAttr}>
      <div class="desc-main">
        <div class="desc-view">${content}</div>
        <div class="desc-edit-form" hidden>
          <textarea class="in desc-edit-text" maxlength="3000" rows="3" placeholder="Describe the board in a few sentences" aria-label="Board description" title="Ctrl+Enter saves, Esc cancels" dir="auto">${esc(goal)}</textarea>
          <div class="acts">${btn('Save', {size: 'sm', kind: 'line', act: 'save-desc'})}${btn('Cancel', {size: 'sm', act: 'cancel-desc'})}</div>
        </div>
      </div>
      <div class="desc-acts">${acts}</div>
    </div>`;
}

function requirementsHTML() {
  const items = ideaItems(), cap = ideaSplitPct();
  const desc = descHTML();
  const body = items.length
    ? `<ul class="req-list" aria-label="Requirements">${items.map(reqRowHTML).join('')}</ul>`
    : `<p class="req-empty">Nothing agreed yet. Describe your idea in the chat, or add a requirement yourself.</p>`;
  const split = items.length
    ? `<div class="idea-split" role="separator" aria-orientation="horizontal" aria-label="Resize the requirements list" tabindex="0" aria-valuemin="${IDEA_SPLIT_MIN}" aria-valuemax="${IDEA_SPLIT_MAX}" aria-valuenow="${cap || 30}" title="Drag to resize, double-click to reset"></div>`
    : '';
  return `<section class="idea-reqs"${cap ? ` style="max-height:${cap}%"` : ''} aria-label="Agreed requirements">
      <div class="req-scroll">${desc}${body}</div>
      <div class="req-add-row">
        <button type="button" class="btn sm" data-act="show-add-req">+ Add requirement</button>
        <div class="req-add-form" hidden>
          <input type="text" class="in req-add-topic" maxlength="60" placeholder="Topic" aria-label="Topic">
          <textarea class="in req-add-text" maxlength="1000" rows="2" placeholder="Requirement" aria-label="Requirement" title="Enter adds it, Shift+Enter adds a line, Esc cancels" dir="auto"></textarea>
          <div class="acts">${btn('Add', {size: 'sm', kind: 'line', act: 'create-req'})}${btn('Cancel', {size: 'sm', act: 'cancel-add-req'})}</div>
        </div>
      </div>
      ${split}
    </section>`;
}

// The agent's pending diagram proposal, as a slim bar on top of the canvas.
function proposalBarHTML() {
  const p = pendingDiagramProposal();
  if (!p) return '';
  const hasDiagram = !!proposalDiagram(p);
  const previewing = hasDiagram && ideaPreviewPid === p.id;
  const decide = (label, what, kind) => btn(label, {size: 'sm', kind, pid: p.id, decide: what});
  const acts = previewing
    ? decide('Apply', 'approved', 'line') + btn('Back', {size: 'sm', act: 'idea-review-back'})
    : (hasDiagram ? btn('Review', {size: 'sm', kind: 'line', act: 'idea-review', pid: p.id}) : decide('Apply', 'approved', 'line')) + decide('Dismiss', 'rejected');
  return `<div class="idea-prop" role="status" data-key="${esc(p.id)}:${previewing ? 'p' : 'n'}"${p.reason ? ` title="${esc(p.reason)}"` : ''}>
      ${dot('warn')}<span class="idea-prop-msg">${previewing ? "Previewing the agent's changes" : 'The agent suggests changes to the diagram'}</span>
      <span class="acts">${acts}</span>
    </div>`;
}
function refreshIdeaBar(canvas) {
  const bar = canvas.querySelector('.idea-prop');
  const html = proposalBarHTML();
  if (!html) { if (bar) bar.remove(); return; }
  const key = (html.match(/data-key="([^"]*)"/) || [])[1];
  if (bar && bar.getAttribute('data-key') === key) return;
  if (bar) bar.outerHTML = html;
  else canvas.insertAdjacentHTML('afterbegin', html);
}
// A list that scrolls shows its handle; one that fits has nothing to resize.
function markIdeaCapped(container) {
  const reqs = container.querySelector('.idea-reqs'), scroll = reqs && reqs.querySelector('.req-scroll');
  if (reqs && scroll) reqs.classList.toggle('is-capped', scroll.scrollHeight > scroll.clientHeight + 1);
}

/* ---------- the shell hooks ---------- */
function ideaHTML(container) {
  if (container) releaseIdeaEditors(container);   // the canvas below replaces the old one
  const head = ideaHeaderHTML(), reqs = requirementsHTML();
  if (container) container._ideaSig = {head, reqs};
  // the placeholder svg is what a test (and a slow script load) sees until DiagramEditor.mount() builds the editor in its place
  return `<div class="idea-view">
    ${head}
    <div class="idea-body">
      ${reqs}
      <div class="idea-canvas">
        ${proposalBarHTML()}
        <div class="diagram-mount-point">
          <svg class="diag-svg" id="diag-svg" viewBox="0 0 860 520" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Interactive block diagram"></svg>
        </div>
      </div>
    </div>
  </div>`;
}

// The poll and every action redraw only what changed; the canvas (and its pan, zoom and selection) stays.
function updateIdeaContent(container) {
  if (!container.querySelector('.idea-view')) return;
  const sig = container._ideaSig || (container._ideaSig = {});
  const head = ideaHeaderHTML();
  if (head !== sig.head) {
    sig.head = head;
    const vh = container.querySelector('.idea-view > .vh');
    if (vh) vh.outerHTML = head;
  }
  const reqs = requirementsHTML();
  const open = container.querySelector('.req-edit-form:not([hidden]), .req-add-form:not([hidden]), .desc-edit-form:not([hidden])');   // never eat what is being typed
  if (reqs !== sig.reqs && (!open || ideaForce)) {
    sig.reqs = reqs;
    const old = container.querySelector('.idea-reqs');
    if (old) {
      const top = (old.querySelector('.req-scroll') || {}).scrollTop || 0;
      old.outerHTML = reqs;
      const fresh = container.querySelector('.req-scroll');
      if (fresh) fresh.scrollTop = top;
    }
  }
  markIdeaCapped(container);
  const canvas = container.querySelector('.idea-canvas');
  if (canvas) refreshIdeaBar(canvas);
  const mountEl = container.querySelector('.diagram-mount-point');
  if (mountEl && mountEl._diagramEditor) {
    mountEl._diagramEditor.updateData(ideaDiagram());
    syncIdeaCanvas();
  }
}

/* ---------- requirements: edit, add, delete, move ---------- */
const reqRowOf = el => (el && el.closest ? el.closest('.req-row') : null);
const reqIndex = row => parseInt(row.dataset.index, 10);
function focusReq(idx) {
  const row = document.querySelector(`.req-row[data-index="${idx}"]`);
  if (row) row.focus();
}
function openReqEdit(row, field) {
  const view = row.querySelector('.req-view'), form = row.querySelector('.req-edit-form');
  if (!view || !form) return;
  view.hidden = true;
  form.hidden = false;
  row.classList.add('is-editing');
  const target = form.querySelector(field === 'topic' ? '.req-edit-topic' : '.req-edit-text');
  if (!target) return;
  target.focus();
  const n = target.value.length;
  target.setSelectionRange(field === 'topic' ? 0 : n, n);
}
function closeReqEdit(row) {
  const view = row.querySelector('.req-view'), form = row.querySelector('.req-edit-form');
  if (view) view.hidden = false;
  if (form) form.hidden = true;
  row.classList.remove('is-editing');
  row.focus();
}
async function saveReq(row) {
  const topic = (row.querySelector('.req-edit-topic')?.value || '').trim();
  const text = (row.querySelector('.req-edit-text')?.value || '').trim();
  if (!topic || !text) { toast('A requirement needs a topic and some text'); return; }
  const idx = reqIndex(row);
  if (await ideaPost('/api/idea/item/update', {index: idx, old_topic: row.dataset.topic, topic, text})) {
    ideaRedraw();
    focusReq(idx);
  }
}
async function deleteReq(row) {
  const idx = reqIndex(row), topic = row.dataset.topic, proposed = row.classList.contains('is-proposed');
  const res = await ideaPost('/api/idea/item/delete', {index: idx, topic});
  if (!res) return;
  const gone = res.deleted;
  ideaRedraw();
  focusReq(Math.min(idx, ideaItems().length - 1));
  toast((proposed ? 'Dismissed "' : 'Deleted "') + topic + '"', gone && {
    label: 'Undo',
    onClick: async () => {
      const back = await ideaPost('/api/idea/item', {topic: gone.topic, text: gone.text});
      if (!back) return;
      const last = ideaItems().length - 1;
      if (last !== idx) await ideaPost('/api/idea/item/move', {from: last, to: idx});   // back where it was
      ideaRedraw();
    }
  });
}
async function moveReq(row, delta) {
  const idx = reqIndex(row), to = idx + delta;
  if (to < 0 || to >= ideaItems().length) return;
  if (await ideaPost('/api/idea/item/move', {from: idx, to})) {
    ideaRedraw();
    focusReq(to);
  }
}
async function createReq(addRow) {
  const topic = (addRow.querySelector('.req-add-topic')?.value || '').trim();
  const text = (addRow.querySelector('.req-add-text')?.value || '').trim();
  if (!topic || !text) { toast('A requirement needs a topic and some text'); return; }
  if (await ideaPost('/api/idea/item', {topic, text})) ideaRedraw();
}
function closeAddReq(addRow) {
  const form = addRow.querySelector('.req-add-form'), btn0 = addRow.querySelector('[data-act="show-add-req"]');
  if (form) form.hidden = true;
  if (btn0) { btn0.hidden = false; btn0.focus(); }
}

/* ---------- description: edit, save ---------- */
const descBlockOf = el => (el && el.closest ? el.closest('.desc-block') : null);
function openDescEdit(block) {
  const view = block.querySelector('.desc-view'), form = block.querySelector('.desc-edit-form');
  if (!view || !form) return;
  view.hidden = true;
  form.hidden = false;
  block.classList.add('is-editing');
  const ta = form.querySelector('.desc-edit-text');
  if (!ta) return;
  ta.focus();
  const n = ta.value.length;
  ta.setSelectionRange(n, n);
}
function closeDescEdit(block) {
  const view = block.querySelector('.desc-view'), form = block.querySelector('.desc-edit-form');
  if (view) view.hidden = false;
  if (form) form.hidden = true;
  block.classList.remove('is-editing');
  const btn0 = block.querySelector('[data-act="edit-desc"], .desc-text');
  if (btn0) btn0.focus();
}
async function saveDesc(block) {
  const text = (block.querySelector('.desc-edit-text')?.value || '').trim();
  if (await ideaPost('/api/idea/goal', {text})) ideaRedraw();
}

// Keyboard: Enter saves (Shift+Enter is a new line), Esc cancels; on a row Enter edits, Delete removes, Alt+arrows move.
document.addEventListener('keydown', e => {
  const t = e.target;
  if (!t || !t.matches || e.isComposing) return;
  if (t.matches('.desc-edit-text')) {
    const block = descBlockOf(t);
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (block) saveDesc(block);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (block) closeDescEdit(block);
    }
  } else if (t.matches('.req-edit-text, .req-edit-topic')) {
    const row = reqRowOf(t);
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (row) saveReq(row); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (row) closeReqEdit(row); }
  } else if (t.matches('.req-add-topic, .req-add-text')) {
    const addRow = t.closest('.req-add-row');
    if (e.key === 'Enter' && !e.shiftKey && t.matches('.req-add-text')) { e.preventDefault(); if (addRow) createReq(addRow); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (addRow) closeAddReq(addRow); }
  } else if (t.matches('.req-row')) {
    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      e.stopPropagation();
      moveReq(t, e.key === 'ArrowUp' ? -1 : 1);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const next = e.key === 'ArrowUp' ? t.previousElementSibling : t.nextElementSibling;
      if (next) next.focus();
    } else if (e.key === 'Enter' || e.key === 'F2') {
      e.preventDefault();
      openReqEdit(t, 'text');
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      e.stopPropagation();   // the diagram editor listens on window and must not delete a block as well
      deleteReq(t);
    }
  } else if (t.matches('.idea-split')) {
    splitKey(e, t);
  }
});
document.addEventListener('focusin', e => {
  const row = e.target.matches && e.target.matches('.req-row') ? e.target : null;
  if (!row) return;
  const list = row.parentElement;
  list.querySelectorAll('.req-row[tabindex="0"]').forEach(r => { if (r !== row) r.tabIndex = -1; });   // one tab stop for the whole list
  row.tabIndex = 0;
});

// Reorder by dragging the grip (only the grip starts a drag, so the text stays selectable).
document.addEventListener('pointerdown', e => {
  const grip = e.target.closest ? e.target.closest('.req-drag-handle') : null;
  const row = grip && reqRowOf(grip);
  if (row) row.draggable = true;
});
document.addEventListener('dragstart', e => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row && e.dataTransfer) {
    e.dataTransfer.setData('text/plain', row.dataset.index);
    e.dataTransfer.effectAllowed = 'move';
  }
});
document.addEventListener('dragover', e => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row && e.dataTransfer) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    row.classList.add('drag-over');
  }
});
document.addEventListener('dragleave', e => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row) row.classList.remove('drag-over');
});
document.addEventListener('dragend', () => {
  document.querySelectorAll('.req-row[draggable="true"]').forEach(r => { r.draggable = false; r.classList.remove('drag-over'); });
});
document.addEventListener('drop', async e => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (!row || !e.dataTransfer) return;
  e.preventDefault();
  row.classList.remove('drag-over');
  const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
  const toIdx = reqIndex(row);
  if (!isNaN(fromIdx) && !isNaN(toIdx) && fromIdx !== toIdx) {
    if (await ideaPost('/api/idea/item/move', {from: fromIdx, to: toIdx})) {
      ideaRedraw();
      focusReq(toIdx);
    }
  }
});

/* ---------- the split between the list and the canvas ---------- */
function applyIdeaSplit(reqs, pct) {
  reqs.style.maxHeight = pct ? pct + '%' : '';
  const sp = reqs.querySelector('.idea-split');
  if (sp) sp.setAttribute('aria-valuenow', String(Math.round(pct || 30)));
}
function ideaSplitNow(reqs) {   // the height the list has now, as a percent of the sheet body
  const body = reqs.parentElement;
  return body && body.clientHeight ? reqs.offsetHeight / body.clientHeight * 100 : 30;
}
function splitKey(e, sp) {
  const reqs = sp.closest('.idea-reqs');
  if (!reqs) return;
  let pct = null;
  if (e.key === 'ArrowUp') pct = ideaSplitNow(reqs) - IDEA_SPLIT_STEP;
  else if (e.key === 'ArrowDown') pct = ideaSplitNow(reqs) + IDEA_SPLIT_STEP;
  else if (e.key === 'Home') pct = IDEA_SPLIT_MIN;
  else if (e.key === 'End') pct = IDEA_SPLIT_MAX;
  else if (e.key === 'Enter') pct = 0;
  else return;
  e.preventDefault();
  ideaSplit = pct ? Math.min(IDEA_SPLIT_MAX, Math.max(IDEA_SPLIT_MIN, pct)) : 0;
  saveIdeaSplit(ideaSplit);
  applyIdeaSplit(reqs, ideaSplit);
}
document.addEventListener('pointerdown', e => {
  const sp = e.target.closest ? e.target.closest('.idea-split') : null;
  const reqs = sp && sp.closest('.idea-reqs');
  if (!reqs || e.button !== 0) return;
  e.preventDefault();
  const scroll = reqs.querySelector('.req-scroll'), add = reqs.querySelector('.req-add-row');
  ideaSplitDrag = {sp, reqs, y: e.clientY, h: reqs.offsetHeight, bodyH: reqs.parentElement.clientHeight,
    natural: scroll.scrollHeight + (add ? add.offsetHeight : 0)};   // a list never grows past its content
  sp.classList.add('is-drag');
  try { sp.setPointerCapture(e.pointerId); } catch (err) { /* the window listeners below still follow the pointer */ }
});
document.addEventListener('pointermove', e => {
  const d = ideaSplitDrag;
  if (!d) return;
  const h = Math.min(Math.max(d.h + e.clientY - d.y, d.bodyH * IDEA_SPLIT_MIN / 100), Math.min(d.natural, d.bodyH * IDEA_SPLIT_MAX / 100));
  ideaSplit = Math.round(h / d.bodyH * 1000) / 10;
  applyIdeaSplit(d.reqs, ideaSplit);
});
document.addEventListener('pointerup', () => {
  const d = ideaSplitDrag;
  if (!d) return;
  ideaSplitDrag = null;
  d.sp.classList.remove('is-drag');
  saveIdeaSplit(ideaSplit);
  const c = d.reqs.closest('#view, #view-side');
  if (c) markIdeaCapped(c);
});
document.addEventListener('dblclick', e => {
  const sp = e.target.closest ? e.target.closest('.idea-split') : null;
  const reqs = sp && sp.closest('.idea-reqs');
  if (!reqs) return;
  ideaSplit = 0;
  saveIdeaSplit(0);
  applyIdeaSplit(reqs, 0);
  const c = reqs.closest('#view, #view-side');
  if (c) markIdeaCapped(c);
});
window.addEventListener('resize', () => {
  document.querySelectorAll('#view, #view-side').forEach(c => { if (c.querySelector('.idea-reqs')) markIdeaCapped(c); });
});

/* ---------- action handlers (dispatched by the delegates in core.js) ---------- */
onAct('confirmidea', async () => {
  if (await ideaPost('/api/idea/confirm', {})) ideaRedraw();
});
onAct('idea-next', () => go('workspace', 'bom'));
onAct('idea-review', (el, d) => {
  ideaPreviewPid = d.pid;
  syncIdeaCanvas();
  ideaRedraw();
});
onAct('idea-review-back', () => {
  ideaPreviewPid = '';
  syncIdeaCanvas();
  ideaRedraw();
});
onAct('undo-diagram', async () => {
  const res = await ideaPost('/api/idea/diagram/undo', {});
  if (!res || !res.diagram) return;
  const mountEl = document.querySelector('.diagram-mount-point');
  if (mountEl && mountEl._diagramEditor) mountEl._diagramEditor.updateData(res.diagram);
  render(true);
  toast('Diagram change undone');
});
onAct('edit-desc', (el) => {
  const block = descBlockOf(el);
  if (block) openDescEdit(block);
});
onAct('cancel-desc', (el) => {
  const block = descBlockOf(el);
  if (block) closeDescEdit(block);
});
onAct('save-desc', (el) => {
  const block = descBlockOf(el);
  if (block) return saveDesc(block);
});
onAct('confirm-desc', async () => {
  if (await ideaPost('/api/idea/goal/confirm', {})) ideaRedraw();
});
onAct('dismiss-desc', async () => {
  if (await ideaPost('/api/idea/goal/dismiss', {})) ideaRedraw();
});
onAct('edit-req', (el) => {
  const row = reqRowOf(el);
  if (row) openReqEdit(row, 'text');
});
// The words themselves are not buttons (the app's click handler only routes buttons), so a click on the topic or the text opens the edit.
document.addEventListener('click', e => {
  const words = e.target.closest ? e.target.closest('.req-topic, .req-text') : null;
  const row = words && reqRowOf(words);
  if (!row || row.classList.contains('is-editing')) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed) return;   // dragging over the words to copy them is not an edit
  openReqEdit(row, words.classList.contains('req-topic') ? 'topic' : 'text');
});
document.addEventListener('click', e => {
  const words = e.target.closest ? e.target.closest('.desc-text') : null;
  const block = words && descBlockOf(words);
  if (!block || block.classList.contains('is-editing')) return;
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed) return;
  openDescEdit(block);
});
onAct('cancel-req', (el) => {
  const row = reqRowOf(el);
  if (row) closeReqEdit(row);
});
onAct('save-req', (el) => {
  const row = reqRowOf(el);
  if (row) return saveReq(row);
});
onAct('confirm-req', async (el) => {
  const row = reqRowOf(el);
  if (!row) return;
  const idx = reqIndex(row);
  if (await ideaPost('/api/idea/item/confirm', {index: idx, topic: row.dataset.topic})) {
    ideaRedraw();
    focusReq(idx);
  }
});
onAct('delete-req', (el) => {
  const row = reqRowOf(el);
  if (row) return deleteReq(row);
});
onAct('show-add-req', (el) => {
  const addRow = el.closest('.req-add-row'), form = addRow && addRow.querySelector('.req-add-form');
  if (!form) return;
  el.hidden = true;
  form.hidden = false;
  form.querySelector('.req-add-topic').focus();
});
onAct('cancel-add-req', (el) => {
  const addRow = el.closest('.req-add-row');
  if (addRow) closeAddReq(addRow);
});
onAct('create-req', (el) => {
  const addRow = el.closest('.req-add-row');
  if (addRow) return createReq(addRow);
});
