/* PCB Advisor UI - Idea view: requirements, block diagram mount, legacy diag-* handlers, requirement keyboard/drag. */

let isDraggingDiag = false, dragBlockId = null, dragStartX = 0, dragStartY = 0, blockOrigX = 0, blockOrigY = 0;

const DOMAINS = {
  power: {id: 'power', name: 'Power', border: '#e67e22', fill: '#fef3e2', text: '#b45309'},
  sensing: {id: 'sensing', name: 'Sensing', border: '#27ae60', fill: '#e8f8f0', text: '#15803d'},
  mcu: {id: 'mcu', name: 'MCU', border: '#2980b9', fill: '#ebf5fb', text: '#1d4ed8'},
  comms: {id: 'comms', name: 'Comms', border: '#8e44ad', fill: '#f3ebf9', text: '#6c3483'},
  drive: {id: 'drive', name: 'Drive / Actuation', border: '#c0392b', fill: '#fdedec', text: '#b91c1c'},
  ui: {id: 'ui', name: 'UI / Indicators', border: '#7f8c8d', fill: '#f2f4f4', text: '#4b5563'},
};
const DOMAIN_KEYS = Object.keys(DOMAINS);

/* ---------- block diagram ---------- */
function mountDiagramEditor(container) {
  const mountEl = container ? container.querySelector('.diagram-mount-point') : document.querySelector('.diagram-mount-point');
  if (!mountEl) return;
  function doMount() {
    if (typeof DiagramEditor !== 'undefined' && DiagramEditor.mount) {
      if (mountEl._diagramEditor) {
        mountEl._diagramEditor.updateData((S && S.idea && S.idea.diagram) || {shapes: [], connectors: [], frames: []});
        return;
      }
      mountEl._diagramEditor = DiagramEditor.mount(mountEl, {
        project: PROJECT,
        session: SESSION,
        data: (S && S.idea && S.idea.diagram) || {shapes: [], connectors: [], frames: []},
        onSave: async (diagData) => {
          if (S && S.idea) S.idea.diagram = diagData;
          await api('/api/idea/diagram', {diagram: diagData});
        },
        onServerUndo: async () => {
          const res = await api('/api/idea/diagram/undo', {});
          if (res && res.diagram) {
            setState(res);
            return res.diagram;
          }
        }
      });
    }
  }
  if (typeof DiagramEditor === 'undefined') {
    const sc = document.createElement('script');
    sc.src = '/ui/diagram.js';
    sc.onload = doMount;
    document.head.appendChild(sc);
  } else {
    doMount();
  }
}

function agreedRequirementsHTML() {
  const I = (S && S.idea) || {}, items = I.agreed || [];
  const st = i => i.status === 'confirmed' ? ((i.by === 'student' ? 'From you' : "Agent's proposal") + ' · confirmed') : "Agent's proposal · not confirmed yet";

  const rowsHtml = items.map((i, idx) => `
    <div class="req-row" data-index="${idx}" data-topic="${esc(i.topic)}" draggable="true">
      <span class="req-drag-handle" title="Drag to reorder" aria-label="Drag to reorder">⠿</span>
      <div class="req-content" style="flex:1;min-width:0">
        <div class="req-view">
          <div style="display:flex;align-items:center;gap:6px">
            <strong class="req-topic" data-act="edit-req" title="Click to edit topic">${esc(i.topic)}</strong>
            <span class="req-by-status" style="font-size:11px;color:var(--dim)">(${esc(st(i))})</span>
          </div>
          <div class="req-text" data-act="edit-req" title="Click to edit text" dir="auto" style="font-size:13px;white-space:pre-wrap;cursor:pointer;margin-top:2px">${esc(i.text)}</div>
        </div>
        <div class="req-edit-form" hidden style="margin-top:4px">
          <input type="text" class="req-edit-topic" value="${esc(i.topic)}" maxlength="60" placeholder="Topic (max 60 chars)" style="width:100%;font-size:13px;padding:3px 6px;margin-bottom:4px;border:1px solid var(--line);border-radius:4px" />
          <textarea class="req-edit-text" maxlength="1000" rows="3" placeholder="Requirement (Enter saves, Shift+Enter newline, Esc cancels)" style="width:100%;font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:4px;resize:vertical;font-family:inherit">${esc(i.text)}</textarea>
          <div style="display:flex;gap:6px;align-items:center;margin-top:4px">
            <button type="button" class="btn btn-sm pri req-save-btn" data-act="save-req">Save</button>
            <button type="button" class="btn btn-sm req-cancel-btn" data-act="cancel-req">Cancel</button>
            <span style="font-size:11px;color:var(--dim)">Enter saves, Shift+Enter newline, Esc cancels</span>
          </div>
        </div>
      </div>
      <div class="req-actions">
        <button type="button" class="btn-icon req-edit-btn" data-act="edit-req" title="Edit requirement (✎)" aria-label="Edit requirement">✎</button>
        ${i.status !== 'confirmed' ? `<button type="button" class="btn-icon req-confirm-btn" data-act="confirm-req" title="Confirm requirement (✓)" aria-label="Confirm requirement">✓</button>` : ''}
        <button type="button" class="btn-icon req-del-btn" data-act="delete-req" title="Delete requirement (🗑)" aria-label="Delete requirement">🗑</button>
        <button type="button" class="btn-icon req-move-btn req-move-up" data-act="move-req-up" title="Move up (↑)" aria-label="Move up" ${idx === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" class="btn-icon req-move-btn req-move-down" data-act="move-req-down" title="Move down (↓)" aria-label="Move down" ${idx === items.length - 1 ? 'disabled' : ''}>↓</button>
      </div>
    </div>
  `).join('');

  return `
    <details class="card agreed-card" ${items.length ? '' : 'open'} style="flex:none;max-height:220px;min-height:0;display:flex;flex-direction:column;padding:6px 12px;overflow:hidden">
      <summary style="font-weight:600;cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px">
        <span>Agreed requirements</span>
        <span style="font-size:12px;color:var(--dim);font-weight:400">(${items.length} item${items.length === 1 ? '' : 's'})</span>
      </summary>
      <div class="agreed-items-list" style="overflow-y:auto;max-height:170px;margin-top:4px">
        ${items.length ? rowsHtml : '<div class="dnote" style="margin:4px 0">Nothing agreed yet. Chat with the advisor or add a requirement below.</div>'}
        <div class="req-add-row" style="padding:6px 0;margin-top:4px;border-top:1px dashed var(--line2)">
          <button type="button" class="btn btn-sm req-add-toggle-btn" data-act="show-add-req" style="display:inline-flex;align-items:center;gap:4px">+ Add requirement</button>
          <div class="req-add-form" hidden style="margin-top:6px;display:flex;flex-direction:column;gap:4px">
            <input type="text" class="req-add-topic" maxlength="60" placeholder="Topic (max 60 chars)" style="width:100%;font-size:13px;padding:3px 6px;border:1px solid var(--line);border-radius:4px" />
            <textarea class="req-add-text" maxlength="1000" rows="2" placeholder="Requirement (max 1000 chars)" style="width:100%;font-size:13px;padding:4px 6px;border:1px solid var(--line);border-radius:4px;resize:vertical;font-family:inherit"></textarea>
            <div style="display:flex;gap:6px;align-items:center;margin-top:2px">
              <button type="button" class="btn btn-sm pri req-create-btn" data-act="create-req">Add requirement</button>
              <button type="button" class="btn btn-sm req-cancel-add-btn" data-act="cancel-add-req">Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </details>
  `;
}

function updateIdeaContent(container) {
  const card = container.querySelector('.agreed-card');
  const active = document.activeElement;
  const isEditing = active && card && card.contains(active) && /INPUT|TEXTAREA/.test(active.tagName);
  if (card && !isEditing) {
    const parent = card.parentElement;
    if (parent) {
      const temp = document.createElement('div');
      temp.innerHTML = agreedRequirementsHTML();
      const newCard = temp.firstElementChild;
      if (newCard) {
        newCard.open = card.open;
        parent.replaceChild(newCard, card);
      }
    }
  }
  const mountEl = container.querySelector('.diagram-mount-point');
  if (mountEl && mountEl._diagramEditor && S && S.idea && S.idea.diagram) {
    mountEl._diagramEditor.updateData(S.idea.diagram);
  }
}

function ideaHTML(container) {
  const I = (S && S.idea) || {};
  const diagProp = (S.proposals || []).find(p => p.kind === 'idea_diagram' && p.status === 'pending');
  const propBanner = diagProp ? `
    <div class="warnbox" style="margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:10px">
      <div><b>Agent proposed block diagram update:</b> ${esc(diagProp.reason || 'New blocks and connections')}</div>
      <div style="display:flex;gap:6px">
        <button class="btn pri" data-pid="${esc(diagProp.id)}" data-decide="approved">Approve proposal</button>
        <button class="btn" data-pid="${esc(diagProp.id)}" data-decide="rejected">Reject</button>
      </div>
    </div>` : '';

  setTimeout(() => mountDiagramEditor(container), 0);

  return `${guidanceBarHTML('idea')}
    <div class="vhead" style="margin-bottom:8px;flex:none">
      <div>
        <h2>Idea & Architecture</h2>
        <p>${esc(I.goal) || 'What you and the agent agreed on before choosing parts. Every line is a decision you can come back to.'}</p>
      </div>
      <div class="vacts">
        <button class="btn" data-thread="${esc(((S.sessions || []).find(r => r.id === 'idea') || (S.sessions || []).find(r => !r.anchor) || {}).id || '')}">Open conversation</button>
        ${I.confirmed ? `<button class="btn" data-tab="bom">Next: BOM</button>` : `<button class="btn pri" data-act="confirmidea">Confirm the idea</button>`}
      </div>
    </div>
    ${propBanner}
    <div class="idea-layout" style="display:flex;flex-direction:column;flex:1;min-height:0;gap:8px;width:100%;height:100%;overflow:hidden">
      ${agreedRequirementsHTML()}
      <div class="card diagram-card" style="flex:1;min-height:0;display:flex;flex-direction:column;width:100%;height:100%;padding:0;position:relative;overflow:hidden">
        <div class="diagram-mount-point" style="width:100%;height:100%;flex:1;min-height:0;position:relative;display:flex;flex-direction:column">
          <svg class="diag-svg" id="diag-svg" viewBox="0 0 860 520" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Interactive Block diagram"></svg>
        </div>
      </div>
    </div>`;
}

/* ---------- diagram drag & inline edit ---------- */
document.addEventListener('mousedown', e => {
  const block = e.target.closest('g.diag-block');
  if (!block) return;
  if (e.target.closest('[data-act]')) return;
  dragBlockId = block.dataset.bid;
  const b = (S.idea.blocks || []).find(x => x.id === dragBlockId);
  if (!b) return;
  isDraggingDiag = true;
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  blockOrigX = b.x ?? 220;
  blockOrigY = b.y ?? 100;
  block.classList.add('dragging');
});
document.addEventListener('mousemove', e => {
  if (!isDraggingDiag || !dragBlockId) return;
  const b = (S.idea.blocks || []).find(x => x.id === dragBlockId);
  if (!b) return;
  const dx = e.clientX - dragStartX;
  const dy = e.clientY - dragStartY;
  b.x = Math.max(10, Math.round(blockOrigX + dx));
  b.y = Math.max(10, Math.round(blockOrigY + dy));
  const el = $(`g.diag-block[data-bid="${dragBlockId}"]`);
  if (el) el.setAttribute('transform', `translate(${b.x}, ${b.y})`);
});
document.addEventListener('mouseup', async e => {
  if (!isDraggingDiag) return;
  isDraggingDiag = false;
  const el = $(`g.diag-block[data-bid="${dragBlockId}"]`);
  if (el) el.classList.remove('dragging');
  dragBlockId = null;
  try {
    await api('/api/idea', {blocks: S.idea.blocks, links: S.idea.links || []});
    renderCenter(true);
  } catch (err) { /* toasted */ }
});
document.addEventListener('dblclick', async e => {
  const block = e.target.closest('g.diag-block');
  if (block) {
    const bid = block.dataset.bid;
    const b = (S.idea.blocks || []).find(x => x.id === bid);
    if (!b) return;
    const newLabel = prompt('Block name / part:', b.label || b.id);
    if (newLabel === null) return;
    const newRole = prompt('One-line role in circuit:', b.role || '') || '';
    b.label = newLabel.trim() || b.id;
    b.role = newRole.trim();
    try {
      await api('/api/idea', {blocks: S.idea.blocks, links: S.idea.links || []});
      renderCenter(true);
      toast('Block updated');
    } catch (err) { /* toasted */ }
    return;
  }
  const edge = e.target.closest('.diag-edge-label');
  if (edge) {
    const lidx = parseInt(edge.dataset.lidx, 10);
    const links = S.idea.links || [];
    const cur = links[lidx];
    if (!cur) return;
    const curLabel = Array.isArray(cur) ? (cur[2] || '') : (cur.label || '');
    const newLabel = prompt('Link label (voltage or bus, blank to delete):', curLabel);
    if (newLabel === null) return;
    if (newLabel.trim() === '') {
      links.splice(lidx, 1);
    } else {
      if (Array.isArray(cur)) {
        cur[2] = newLabel.trim();
        cur[3] = /safety/i.test(cur[2]);
      } else {
        cur.label = newLabel.trim();
        cur.safety = /safety/i.test(cur.label);
      }
    }
    try {
      await api('/api/idea', {blocks: S.idea.blocks, links});
      renderCenter(true);
      toast('Link updated');
    } catch (err) { /* toasted */ }
  }
});

// Inline requirement keyboard & drag listeners
document.addEventListener('keydown', (e) => {
  if (e.target.matches && e.target.matches('.req-edit-text')) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const saveBtn = e.target.closest('.req-row')?.querySelector('[data-act="save-req"]');
      if (saveBtn) saveBtn.click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      const cancelBtn = e.target.closest('.req-row')?.querySelector('[data-act="cancel-req"]');
      if (cancelBtn) cancelBtn.click();
    }
  } else if (e.target.matches && e.target.matches('.req-edit-topic')) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const saveBtn = e.target.closest('.req-row')?.querySelector('[data-act="save-req"]');
      if (saveBtn) saveBtn.click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      const cancelBtn = e.target.closest('.req-row')?.querySelector('[data-act="cancel-req"]');
      if (cancelBtn) cancelBtn.click();
    }
  } else if (e.target.matches && e.target.matches('.req-add-topic, .req-add-text')) {
    if (e.key === 'Enter' && !e.shiftKey && e.target.matches('.req-add-text')) {
      e.preventDefault();
      const addBtn = e.target.closest('.req-add-row')?.querySelector('[data-act="create-req"]');
      if (addBtn) addBtn.click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      const cancelBtn = e.target.closest('.req-add-row')?.querySelector('[data-act="cancel-add-req"]');
      if (cancelBtn) cancelBtn.click();
    }
  }
});
document.addEventListener('dragstart', (e) => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row && e.dataTransfer) {
    e.dataTransfer.setData('text/plain', row.dataset.index);
    e.dataTransfer.effectAllowed = 'move';
  }
});
document.addEventListener('dragover', (e) => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row && e.dataTransfer) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    row.classList.add('drag-over');
  }
});
document.addEventListener('dragleave', (e) => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row) row.classList.remove('drag-over');
});
document.addEventListener('drop', async (e) => {
  const row = e.target.closest ? e.target.closest('.req-row') : null;
  if (row && e.dataTransfer) {
    e.preventDefault();
    row.classList.remove('drag-over');
    const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const toIdx = parseInt(row.dataset.index, 10);
    if (!isNaN(fromIdx) && !isNaN(toIdx) && fromIdx !== toIdx) {
      try {
        const res = await api('/api/idea/item/move', {from: fromIdx, to: toIdx});
        setState(res);
        renderCenter(true);
      } catch (err) { toast(err.message || 'Error moving requirement'); }
    }
  }
});

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('undo-diagram', async (el, d, e) => {
  try {
    toast('Undoing diagram change…');
    const res = await api('/api/idea/diagram/undo', {});
    if (res && res.diagram) {
      setState(res);
      const mountEl = document.querySelector('.diagram-mount-point');
      if (mountEl && mountEl._diagramEditor) {
        mountEl._diagramEditor.updateData(res.diagram);
      }
      render(true);
      toast('Diagram change undone');
    }
  } catch (err) {
    toast(err.message || 'Error undoing diagram change');
  }
  return;
});
onAct('edit-req', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const v = reqRow.querySelector('.req-view');
    const f = reqRow.querySelector('.req-edit-form');
    if (v && f) {
      v.hidden = true;
      f.hidden = false;
      const isTopic = el.classList.contains('req-topic');
      const target = isTopic ? f.querySelector('.req-edit-topic') : f.querySelector('.req-edit-text');
      if (target) {
        target.focus();
        if (target.select) target.select();
      }
    }
  }
  return;
});
onAct('cancel-req', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const v = reqRow.querySelector('.req-view');
    const f = reqRow.querySelector('.req-edit-form');
    if (v && f) {
      v.hidden = false;
      f.hidden = true;
    }
  }
  return;
});
onAct('save-req', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const topic = (reqRow.querySelector('.req-edit-topic')?.value || '').trim();
    const text = (reqRow.querySelector('.req-edit-text')?.value || '').trim();
    const idx = parseInt(reqRow.dataset.index, 10);
    const oldTopic = reqRow.dataset.topic;
    if (!topic || topic.length > 60 || !text || text.length > 1000) {
      toast('Topic (1-60 chars) and text (1-1000 chars) required');
      return;
    }
    try {
      const res = await api('/api/idea/item/update', {index: idx, old_topic: oldTopic, topic, text});
      setState(res);
      renderCenter(true);
      toast(`Requirement "${topic}" updated`);
    } catch (err) {
      toast(err.message || 'Error updating requirement');
    }
  }
  return;
});
onAct('confirm-req', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const idx = parseInt(reqRow.dataset.index, 10);
    const topic = reqRow.dataset.topic;
    try {
      const res = await api('/api/idea/item/confirm', {index: idx, topic});
      setState(res);
      renderCenter(true);
      toast(`Requirement "${topic}" confirmed`);
    } catch (err) {
      toast(err.message || 'Error confirming requirement');
    }
  }
  return;
});
onAct('delete-req', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const idx = parseInt(reqRow.dataset.index, 10);
    const topic = reqRow.dataset.topic;
    try {
      const res = await api('/api/idea/item/delete', {index: idx, topic});
      const delItem = res.deleted;
      setState(res);
      renderCenter(true);
      toast(`Requirement "${topic}" deleted`, {
        label: 'Undo',
        onClick: async () => {
          if (delItem) {
            try {
              const undoRes = await api('/api/idea/item', {topic: delItem.topic, text: delItem.text});
              setState(undoRes);
              renderCenter(true);
              toast(`Restored "${delItem.topic}"`);
            } catch (e) { toast('Could not restore requirement'); }
          }
        }
      });
    } catch (err) {
      toast(err.message || 'Error deleting requirement');
    }
  }
  return;
});
onAct('move-req-up', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const idx = parseInt(reqRow.dataset.index, 10);
    if (idx > 0) {
      try {
        const res = await api('/api/idea/item/move', {from: idx, to: idx - 1});
        setState(res);
        renderCenter(true);
      } catch (err) { toast(err.message || 'Error moving requirement'); }
    }
  }
  return;
});
onAct('move-req-down', async (el, d, e) => {
  const reqRow = el.closest('.req-row');
  if (reqRow) {
    const idx = parseInt(reqRow.dataset.index, 10);
    try {
      const res = await api('/api/idea/item/move', {from: idx, to: idx + 1});
      setState(res);
      renderCenter(true);
    } catch (err) { toast(err.message || 'Error moving requirement'); }
  }
  return;
});
onAct('show-add-req', async (el, d, e) => {
  const addRow = el.closest('.req-add-row');
  if (addRow) {
    el.hidden = true;
    const form = addRow.querySelector('.req-add-form');
    if (form) {
      form.hidden = false;
      form.querySelector('.req-add-topic')?.focus();
    }
  }
  return;
});
onAct('cancel-add-req', async (el, d, e) => {
  const addRow = el.closest('.req-add-row');
  if (addRow) {
    const form = addRow.querySelector('.req-add-form');
    const btn = addRow.querySelector('.req-add-toggle-btn');
    if (form) form.hidden = true;
    if (btn) btn.hidden = false;
  }
  return;
});
onAct('create-req', async (el, d, e) => {
  const addRow = el.closest('.req-add-row');
  if (addRow) {
    const topic = (addRow.querySelector('.req-add-topic')?.value || '').trim();
    const text = (addRow.querySelector('.req-add-text')?.value || '').trim();
    if (!topic || topic.length > 60 || !text || text.length > 1000) {
      toast('Topic (1-60 chars) and text (1-1000 chars) required');
      return;
    }
    try {
      const res = await api('/api/idea/item', {topic, text});
      setState(res);
      renderCenter(true);
      toast(`Requirement "${topic}" added`);
    } catch (err) {
      toast(err.message || 'Error adding requirement');
    }
  }
  return;
});
onAct('diag-add', async (el, d, e) => {
  const name = prompt('Block name / MPN (e.g. ESP32-S3, TPS54302, USB-C):');
  if (!name || !name.trim()) return;
  const role = prompt('One-line role in circuit:', 'Controller / Power / Sensor') || '';
  const domChoice = prompt('Domain (' + DOMAIN_KEYS.join(', ') + '):', 'mcu') || 'mcu';
  const domain = DOMAINS[domChoice.toLowerCase()] ? domChoice.toLowerCase() : 'mcu';
  const newId = 'b_' + Date.now().toString(36);
  const blocks = S.idea.blocks || [];
  blocks.push({
    id: newId,
    label: name.trim(),
    role: role.trim(),
    domain,
    x: 220 + (blocks.length % 3) * 180,
    y: 80 + Math.floor(blocks.length / 3) * 110
  });
  await api('/api/idea', {blocks, links: S.idea.links || []});
  renderCenter(true);
  toast('Block added');
  return;
});
onAct('diag-del-block', async (el, d, e) => {
  const bid = d.bid;
  if (!confirm('Delete block ' + bid + '?')) return;
  const blocks = (S.idea.blocks || []).filter(b => b.id !== bid);
  const links = (S.idea.links || []).filter(l => {
    const from = Array.isArray(l) ? l[0] : (l.from || l.a);
    const to = Array.isArray(l) ? l[1] : (l.to || l.b);
    return from !== bid && to !== bid;
  });
  await api('/api/idea', {blocks, links});
  renderCenter(true);
  toast('Block deleted');
  return;
});
onAct('diag-cycle-domain', async (el, d, e) => {
  const bid = d.bid;
  const b = (S.idea.blocks || []).find(x => x.id === bid);
  if (b) {
    const idx = DOMAIN_KEYS.indexOf(b.domain || 'mcu');
    b.domain = DOMAIN_KEYS[(idx + 1) % DOMAIN_KEYS.length];
    await api('/api/idea', {blocks: S.idea.blocks, links: S.idea.links || []});
    renderCenter(true);
    toast('Domain set to ' + DOMAINS[b.domain].name);
  }
  return;
});
onAct('diag-link-start', async (el, d, e) => {
  diagLinkingFrom = d.bid;
  renderCenter(true);
  toast('Click destination block to link');
  return;
});
onAct('diag-cancel-link', async (el, d, e) => {
  diagLinkingFrom = null;
  renderCenter(true);
  return;
});
onAct('diag-edit-edge', async (el, d, e) => {
  const lidx = parseInt(d.lidx, 10);
  const links = S.idea.links || [];
  const cur = links[lidx];
  if (!cur) return;
  const curLabel = Array.isArray(cur) ? (cur[2] || '') : (cur.label || '');
  const newLabel = prompt('Link label (voltage or bus, blank to delete):', curLabel);
  if (newLabel === null) return;
  if (newLabel.trim() === '') {
    links.splice(lidx, 1);
  } else {
    if (Array.isArray(cur)) {
      cur[2] = newLabel.trim();
      cur[3] = /safety/i.test(cur[2]);
    } else {
      cur.label = newLabel.trim();
      cur.safety = /safety/i.test(cur.label);
    }
  }
  await api('/api/idea', {blocks: S.idea.blocks, links});
  renderCenter(true);
  toast('Link updated');
  return;
});
onAct('confirmidea', async (el, d, e) => {
  setState(await api('/api/idea/confirm', {})); render(true); toast('Idea confirmed'); return;
});
