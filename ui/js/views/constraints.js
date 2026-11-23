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
  return `<section class="idea-cons" aria-label="Physical constraints"><h4 class="cons-h">Board constraints</h4>${rows}${add}${warn}</section>`;
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
