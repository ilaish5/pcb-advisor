/* Physical constraints of the board (mounting holes, edge parts, distances, keep-outs), shown inside the idea view.
   Items the agent proposes carry a "proposed" tag; the idea's one Save confirms all of them. */
function constraintItems() { return ((((typeof S !== 'undefined' && S) || {}).idea || {}).constraints || {}).items || []; }

function constraintText(i) {
  if (i.kind === 'mounting_hole') {
    const where = i.points_mm ? i.points_mm.length + ' at set points' : (i.corners || []).join(' ') + ', ' + i.inset_mm + ' mm in';
    return 'Mounting holes ' + i.diameter_mm + ' mm (' + where + ')';
  }
  if (i.kind === 'edge') return i.target + ' at the board edge' + (i.side && i.side !== 'any' ? ' (' + i.side + ')' : '');
  if (i.kind === 'keep_apart') return i.a + ' and ' + i.b + ' at least ' + i.min_mm + ' mm apart';
  if (i.kind === 'keepout') return 'No parts or copper in ' + (i.rect_mm ? i.rect_mm.join(', ') + ' mm' : (i.target || 'an area'));
  if (i.kind === 'attr') return i.target + ': ' + String(i.attr || '').replace(/_/g, ' ');
  return i.kind;
}

function constraintRowHTML(i) {
  const prop = i.status !== 'confirmed';
  return `<li class="cons-row" data-cid="${esc(i.id)}">
      <span class="cons-text">${esc(constraintText(i))}</span>
      ${prop ? tag('proposed', 'warn', 'Saved with the idea when you Save') : ''}
      ${i.note ? `<span class="muted cons-note">${esc(i.note)}</span>` : ''}
      ${btn('', {size: 'sm', icon: 'x', act: 'cons-remove', 'data-cid': i.id, title: 'Remove this constraint'})}
    </li>`;
}

/* Confirmed constraints that name no one part, and requirements about an edge that no constraint holds: one click settles each.
   Shown on the Layout page and under the constraints of the Idea. */
function constraintTargetsOpen() { return ((typeof S !== 'undefined' && S) || {}).constraint_targets || []; }

function constraintFixHTML() {
  const open = constraintTargetsOpen();
  const edges = ((((typeof S !== 'undefined' && S) || {}).design_findings || {}).open || []).filter(f => f.id === 'edge_uncovered');
  if (!open.length && !edges.length) return '';
  const all = (open[0] || {}).choices || ((((typeof S !== 'undefined' && S) || {}).bom || []).flatMap(l => (l.refs || []).map(ref => ({ref, label: l.value || ''}))));
  const pick = attrs => `<select class="in cons-pick" ${attrs} aria-label="Pick the part"><option value="">Another part…</option>${all.map(c =>
    `<option value="${esc(c.ref)}">${esc(c.ref + ' - ' + c.label)}</option>`).join('')}</select>`;
  const bind = f => `<li class="unv-row">${esc(f.message.split('. Candidates:')[0])} ` +
    f.candidates.map(c => btn(c.ref, {size: 'sm', kind: 'line', act: 'cons-bind', 'data-cid': f.id, 'data-field': f.field, 'data-ref': c.ref, title: 'This is ' + c.ref + ': ' + c.label})).join(' ') + ' ' +
    pick(`data-cons-pick="bind" data-cid="${esc(f.id)}" data-field="${esc(f.field)}"`) + ' ' +
    btn('Remove constraint', {size: 'sm', kind: 'link', act: 'cons-drop', 'data-cid': f.id}) + '</li>';
  const hold = f => `<li class="unv-row">${esc(f.message)} ` +
    (f.refs.length ? btn('Hold ' + f.refs.join(', ') + ' there', {size: 'sm', kind: 'line', act: 'cons-hold', 'data-refs': f.refs.join(' '), 'data-side': f.side})
      : pick(`data-cons-pick="hold" data-side="${esc(f.side)}" data-subject="${esc(f.subject || '')}"`)) + ' ' +
    btn('Intended', {size: 'sm', kind: 'link', act: 'design-intended', key: f.key, title: 'This is on purpose: hide it until the finding changes'}) + '</li>';
  const head = open.length ? `Placement is blocked: ${open.length} constraint${open.length > 1 ? 's name' : ' names'} no one part` : 'Requirements no constraint holds';
  return `<section class="dfm-unv cons-fix" aria-label="Constraints to settle"><h3>${esc(head)}</h3><ul>${open.map(bind).join('')}${edges.map(hold).join('')}</ul></section>`;
}

async function consSettle(path, bodies) {
  try { for (const b of bodies) await api(path, b); } catch (e) { /* api() showed the reason */ }
  await refresh(true);
}
onAct('cons-bind', el => consSettle('/api/idea/constraints/bind', [{id: el.getAttribute('data-cid'), field: el.getAttribute('data-field'), ref: el.getAttribute('data-ref')}]));
onAct('cons-drop', el => consSettle('/api/idea/constraints/bind', [{id: el.getAttribute('data-cid'), remove: true}]));
onAct('cons-hold', el => consSettle('/api/idea/constraints/hold-edge', el.getAttribute('data-refs').split(' ').map(ref => ({ref, side: el.getAttribute('data-side')}))));
onChange(t => t.dataset && t.dataset.consPick !== undefined, async e => {
  const t = e.target, ref = t.value;
  if (!ref) return;
  if (t.dataset.consPick === 'hold') await consSettle('/api/idea/constraints/hold-edge', [{ref, side: t.dataset.side, subject: t.dataset.subject || ''}]);
  else await consSettle('/api/idea/constraints/bind', [{id: t.dataset.cid, field: t.dataset.field, ref}]);
});

function constraintsHTML() {
  const items = constraintItems();
  const hasHoles = items.some(i => i.kind === 'mounting_hole');
  const rows = items.length ? `<ul class="cons-list" aria-label="Physical constraints">${items.map(constraintRowHTML).join('')}</ul>` : '';
  const add = hasHoles ? '' : `<div class="cons-add">
      <span class="muted">Holes</span>
      <input type="number" class="in cons-dia" min="0.5" max="10" step="any" value="3.2" aria-label="Hole diameter in mm" title="M3 screw: 3.2 mm"><span class="muted">mm, </span>
      <input type="number" class="in cons-inset" min="1" max="50" step="any" value="3.5" aria-label="Distance from the corners in mm"><span class="muted">mm from the corners</span>
      ${btn('Add 4 mounting holes', {size: 'sm', kind: 'line', act: 'cons-add-holes'})}
    </div>`;
  const warn = items.some(i => i.kind === 'mounting_hole' || i.kind === 'keepout')
    ? '<p class="muted cons-warn">Holes and keep-outs are placed as parts. Altium\'s Update PCB will offer to remove them: answer No.</p>' : '';
  return `<section class="idea-cons" aria-label="Physical constraints"><h4 class="cons-h">Board constraints</h4>${rows}${constraintFixHTML()}${add}${warn}</section>`;
}

async function consPost(items) {
  try {
    await api('/api/idea/constraints', {items});
    setState(await api('/api/state'));
    ideaRedraw();
    return true;
  } catch (e) { return false; }      // api() showed the reason
}
onAct('cons-add-holes', async (el) => {
  const row = el.closest('.cons-add');
  const dia = Number(row.querySelector('.cons-dia').value), inset = Number(row.querySelector('.cons-inset').value);
  if (!(dia > 0) || !(inset > 0)) { toast('Give the hole size and its distance from the corners in mm'); return; }
  if (await consPost(constraintItems().concat([{kind: 'mounting_hole', id: 'holes', diameter_mm: dia, inset_mm: inset, by: 'student', status: 'proposed'}]))) toast('Holes added: Save the idea to keep them');
});
onAct('cons-remove', async (el) => {
  const id = el.closest('.cons-row').getAttribute('data-cid');
  await consPost(constraintItems().filter(i => i.id !== id));
});
