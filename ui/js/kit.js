/* kit.js: shared UI building blocks (icons, buttons, segmented controls, menus, view header, tags,
   empty and loading states, theme). Pure helpers with no app state; loaded before core.js.
   Every helper returns an HTML string; values are escaped here, labels passed as `html:` are not. */

const KIT_ICONS = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  chevr: '<path d="m9 6 6 6-6 6"/>',
  chevl: '<path d="m15 6-6 6 6 6"/>',
  chevu: '<path d="m18 15-6-6-6 6"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  side: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  upload: '<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4"/>',
  zoomin: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
  zoomout: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  /* Library model icons. Drawn inline, nothing is loaded from the network. 'chip' (footprint) is above; box and list-check follow the
     Tabler Icons (MIT, v3) shapes, redrawn in this 24px stroke grid; the symbol glyph is our own. */
  'model-symbol': '<rect x="7" y="5" width="10" height="14" rx="1.5"/><path d="M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  'model-3d': '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
  'model-pins': '<path d="M3.5 5.5l1.5 1.5 2.5-2.5M3.5 11.5l1.5 1.5 2.5-2.5M3.5 17.5l1.5 1.5 2.5-2.5"/><path d="M11 6h9M11 12h9M11 18h9"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
};

function kesc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function icon(name, cls) {
  return `<svg class="i${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true">${KIT_ICONS[name] || ''}</svg>`;
}
/* {act: "x", ref: "C1", title: "..", disabled: true, id: "..", "aria-label": ".."} -> attribute string.
   Plain keys become data-* except id/title/type/disabled/hidden and aria-* / role. */
function kattrs(o) {
  if (!o) return '';
  let s = '';
  for (const [k, v] of Object.entries(o)) {
    if (v === false || v == null) continue;
    const name = /^(id|title|type|disabled|hidden|role|tabindex|draggable|dir)$/.test(k) || /^(aria|data)-/.test(k) ? k : 'data-' + k;
    s += v === true ? ` ${name}` : ` ${name}="${kesc(v)}"`;
  }
  return s;
}
/* btn("Check stock", {kind: "pri", act: "check-all"}); btn("", {icon: "more", title: "More"}) is icon-only.
   kind: 'pri' | 'line' | 'danger' | 'link'; size: 'sm'. Other keys go through kattrs. */
function btn(label, o) {
  o = o || {};
  const {kind, size, icon: ic, iconAfter, html, cls, ...rest} = o;
  const iconOnly = !label && !html;
  if (iconOnly && rest.title && !rest['aria-label']) rest['aria-label'] = rest.title;
  if (rest.disabled) {       // not a dead button: it stays focusable and a click says why (data-why, shown by the handler below)
    rest['aria-disabled'] = 'true';
    rest.why = rest.why || rest.title || 'Not available right now.';
    delete rest.disabled;
  } else delete rest.why;
  const c = ['btn', kind, size, iconOnly ? 'icon' : '', cls].filter(Boolean).join(' ');
  return `<button type="button" class="${c}"${kattrs(rest)}>${ic ? icon(ic) : ''}${html || (label ? `<span>${kesc(label)}</span>` : '')}${iconAfter ? icon(iconAfter, 's') : ''}</button>`;
}
/* seg([{value: "top", label: "Top"}, ...], "top", {act: "layer", label: "Layers"}) -> segmented control.
   Each button gets data-act and data-value; the current one aria-pressed="true". Multi-select: pass an array as value. */
function seg(items, value, o) {
  o = o || {};
  const on = v => Array.isArray(value) ? value.includes(v) : v === value;
  return `<div class="seg" role="group"${o.label ? ` aria-label="${kesc(o.label)}"` : ''}>` + items.map(it =>
    `<button type="button" aria-pressed="${on(it.value)}"${kattrs({act: o.act, value: it.value, title: it.title, ...(it.attrs || {})})}>${it.icon ? icon(it.icon, 's') : ''}${kesc(it.label)}</button>`).join('') + '</div>';
}
/* menu(trigger, items): trigger is btn() options plus label, e.g. {label:'Export', iconAfter:'chev'} or {icon:'more', title:'More'}.
   items: {label, act, hint, danger, checked, disabled, attrs} | 'sep' | {group:'Label'}.
   Items are ordinary buttons with data-act, so the app's click delegate runs them; the menu closes itself afterwards. */
function menu(trigger, items, o) {
  o = o || {};
  const t = Object.assign({}, trigger);
  const label = t.label || '';
  delete t.label;
  t['aria-haspopup'] = 'menu';
  t['aria-expanded'] = 'false';
  t['data-menu'] = true;
  const body = items.filter(Boolean).map(it => {
    if (it === 'sep') return '<hr>';
    if (it.group) return `<div class="lbl">${kesc(it.group)}</div>`;
    if (it.html) return it.html;                  // a block the caller built (a search box, a collapsed group): kit-escaped by the caller
    const a = Object.assign({act: it.act, disabled: it.disabled, title: it.title}, it.attrs || {});
    if (a.disabled) { a['aria-disabled'] = 'true'; a.why = it.why || it.title || 'Not available right now.'; delete a.disabled; }      // a click says why (see the handler above)
    const role = it.checked != null ? 'menuitemradio' : 'menuitem';
    return `<button type="button" role="${role}"${it.checked != null ? ` aria-checked="${!!it.checked}"` : ''}${it.danger ? ' class="danger"' : ''}${kattrs(a)}>${it.icon ? icon(it.icon) : ''}<span>${kesc(it.label)}</span>${it.hint ? `<span class="d">${kesc(it.hint)}</span>` : ''}</button>`;
  }).join('');
  return `<span class="menu-anchor${o.cls ? ' ' + o.cls : ''}">${btn(label, t)}<div class="menu" role="menu" hidden>${body}</div></span>`;
}
function tag(text, tone, title) {
  return `<span class="tag${tone ? ' ' + tone : ''}"${title ? ` title="${kesc(title)}"` : ''}>${kesc(text)}</span>`;
}
function dot(tone, title) {
  return `<span class="dot${tone ? ' ' + tone : ''}"${title ? ` title="${kesc(title)}" role="img" aria-label="${kesc(title)}"` : ' aria-hidden="true"'}></span>`;
}
/* metaLine([{n:60, label:'lines'}, {n:'$41.37', label:'per board'}, {n:60, label:'to verify', tone:'warn', title:'...'}])
   Items with a falsy n and no `always` are skipped, so zero problems print nothing. A string item is used as is (escaped). */
function metaLine(items) {
  return items.filter(it => it && (typeof it === 'string' || it.always || (it.n !== 0 && it.n !== '' && it.n != null))).map(it => {
    if (typeof it === 'string') return `<span>${kesc(it)}</span>`;
    const cls = it.tone ? ` class="${it.tone}-t"` : '';
    return `<span${cls}${it.title ? ` title="${kesc(it.title)}"` : ''}>${it.n != null && it.n !== '' ? `<b>${kesc(it.n)}</b> ` : ''}${kesc(it.label || '')}</span>`;
  }).join('');
}
/* viewHeader({title, meta: metaLine(...) html, actions: html, primary: btn(...) html, next: btn(...) html, side: true})
   side:true adds the "Side by side" icon button (data-act="side-open"); the side pane hides it itself.
   The stage's Next button has ONE place: its own slot (.vh-next), the top-right corner of the header's first row, the same on every page
   and tab. A page cannot put it anywhere else: `actions` and `primary` are in the block beside the title, which wraps and gives way first. */
function viewHeader(o) {
  const side = o.side === false ? '' : btn('', {icon: 'side', title: 'Side by side', act: 'side-open', cls: 'side-btn'});
  // the Next button of a stage's page comes from the server's stages[] (shell.js stageNextBtn); Idea passes its own (o.next: Confirm idea
  // stays an action until the idea is agreed), a page that is already where the next step is (go:<itself>) has none
  const sid = o.stage || (typeof STAGES !== 'undefined' && (STAGES.find(s => s[1] === o.title) || [])[0]);
  const next = o.next != null ? o.next : sid ? (sid !== 'idea' && typeof stageNextBtn === 'function' ? stageNextBtn(sid) : '')
    : o.title === 'Sources' && typeof pageNextBtn === 'function' ? pageNextBtn() : '';
  // ONE filled button per header, and it is the last one on the right: when the stage's Next is the filled one, the page's own
  // action steps down to the outlined style (a done stage keeps "Download" or "Check" as a secondary action, not a second call to action)
  const primary = next && /class="btn pri\b/.test(next) && o.primary ? o.primary.replace(/class="btn pri\b/, 'class="btn line') : (o.primary || '');
  return `<header class="vh"><div class="vh-main"><div class="vh-t"><h1>${kesc(o.title)}</h1>${o.meta ? `<div class="meta">${o.meta}</div>` : ''}</div>` +
    `<div class="acts">${side}${o.actions || ''}${primary}</div></div><div class="vh-next">${next}</div></header>`;
}
function section(title, body, o) {
  o = o || {};
  return `<section class="sec"${o.id ? ` id="${kesc(o.id)}"` : ''}><div class="sec-h"><h2>${kesc(title)}</h2>${o.meta ? `<div class="meta">${o.meta}</div>` : ''}${o.actions ? `<div class="acts">${o.actions}</div>` : ''}</div>${body}</section>`;
}
function emptyState(title, text, actions, limits) {      // limits: one honest line on what the system cannot do yet
  return `<div class="empty"><h2>${kesc(title)}</h2>${text ? `<p>${kesc(text)}</p>` : ''}${limits ? `<p class="limits">${kesc(limits)}</p>` : ''}${actions ? `<div class="acts">${actions}</div>` : ''}</div>`;
}
function loadingLine(text) {
  return `<div class="loading" role="status"><span class="spin" aria-hidden="true"></span>${kesc(text || 'Loading')}</div>`;
}
/* banner({tone: 'info' | 'ok' | 'warn' | 'bad', text | html, actions, cls, title, role}) -> THE message strip of every page: an icon that
   says the severity, the message, the buttons on the right. The tone is the caller's structured fact (a failure is bad, an
   answer with warnings is warn, nothing else is), never guessed from the words. Nothing else draws class="note" (tests/test_ui_clarity.py). */
const BANNER_ICON = {ok: 'check', warn: 'alert', bad: 'alert', info: 'info'};
function banner(o) {
  const tone = BANNER_ICON[o.tone] ? o.tone : 'info';
  const role = o.role || (tone === 'bad' ? 'alert' : 'status');
  const c = ['note', tone === 'info' ? '' : tone, o.cls].filter(Boolean).join(' ');
  return `<div class="${c}" role="${role}"${o.title ? ` title="${kesc(o.title)}"` : ''}>${icon(BANNER_ICON[tone], 'note-i')}` +
    `<span>${o.html != null ? o.html : kesc(o.text)}</span>${o.actions ? `<span class="acts">${o.actions}</span>` : ''}</div>`;
}
function errorLine(what, message, actions) {
  return banner({tone: 'bad', text: `Couldn't ${what}: ${message}`, actions});
}
function kv(pairs) {
  return '<dl class="kv">' + pairs.filter(p => p && p[1] != null && p[1] !== '').map(([k, v, raw]) => `<dt>${kesc(k)}</dt><dd>${raw ? v : kesc(v)}</dd>`).join('') + '</dl>';
}

/* proposalTable(rows, {decided, cls}) -> the proposed parts as a real table, ONE ROW PER PROPOSAL, so every checkbox sits
   beside the one part it belongs to. Used by the chat group card and the BOM page (one component, one look).
   A row: {id, ref, isNew, mpn, manufacturer, package, lcsc, value, role, reason, checked, unverified, short, struck, action}.
   action = html for the last cell of a decided row (Undo). Pending rows get a tick; an unverified row is flagged. */
const PTBL_COLS = [['mpn', 'MPN', 'c-mpn'], ['manufacturer', 'Manufacturer', 'c-mfr'], ['package', 'Package', 'c-pkg'],
  ['lcsc', 'LCSC', 'c-lcsc'], ['value', 'Value', 'c-val'], ['role', 'Role', 'c-role']];
function proposalRow(r, decided) {
  const cells = PTBL_COLS.map(([k, , c]) => `<td class="${c}" dir="auto">${r[k] ? `<span class="${k === 'mpn' || k === 'lcsc' ? 'm' : ''}">${kesc(r[k])}</span>` : '<span class="muted">·</span>'}</td>`).join('');
  const flag = r.unverified ? '<span class="tag warn ptr-flag" title="The agent could not confirm this part number. Check it before you approve.">Unverified</span>' : '';
  const short = r.short ? `<span class="tag warn ptr-flag" title="${kesc(r.short)}">Check qty</span>` : '';
  const tick = decided ? '' : `<td class="c-tick"><input type="checkbox" data-ptick="${kesc(r.id)}"${r.checked ? ' checked' : ''} aria-label="Include ${kesc(r.ref)}"></td>`;
  const tail = decided ? `<td class="c-act">${r.action || ''}</td>` : '';
  const why = r.reason ? `<details class="ptr-why"><summary dir="auto">${kesc(r.reason)}</summary></details>` : '';
  return `<tr class="ptr${r.unverified ? ' unv' : ''}${r.struck ? ' struck' : ''}" data-pid="${kesc(r.id)}">${tick}` +
    `<th scope="row" class="c-ref">${r.isNew ? '<span class="t">New</span> ' : ''}<b>${kesc(r.ref)}</b></th>${cells}<td class="c-why">${flag}${short}${why}</td>${tail}</tr>`;
}
function proposalTable(rows, o) {
  o = o || {};
  const head = (o.decided ? '' : '<th class="c-tick"><span class="sr">Include</span></th>') + '<th class="c-ref">Ref</th>' +
    PTBL_COLS.map(([, label, c]) => `<th class="${c}">${label}</th>`).join('') + '<th class="c-why">Why</th>' + (o.decided ? '<th class="c-act"><span class="sr">Actions</span></th>' : '');
  return `<div class="ptbl-wrap${o.cls ? ' ' + kesc(o.cls) : ''}" tabindex="0" role="region" aria-label="Proposed parts"><table class="tbl ptbl"><thead><tr>${head}</tr></thead>` +
    `<tbody>${rows.map(r => proposalRow(r, o.decided)).join('')}</tbody></table></div>`;
}

/* ---------- menus: open, place, keyboard, close ---------- */
let kitOpenMenu = null;
function kitMenuClose(focusTrigger) {
  if (!kitOpenMenu) return;
  const {menu: m, trigger} = kitOpenMenu;
  m.hidden = true;
  trigger.setAttribute('aria-expanded', 'false');
  kitOpenMenu = null;
  if (focusTrigger) trigger.focus();
}
function kitMenuOpen(trigger) {
  const m = trigger.parentElement && trigger.parentElement.querySelector(':scope > .menu');
  if (!m) return;
  kitMenuClose();
  m.hidden = false;
  trigger.setAttribute('aria-expanded', 'true');
  const r = trigger.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  let left = r.right - mw;
  if (left < 8) left = Math.min(r.left, innerWidth - mw - 8);
  let top = r.bottom + 4;
  if (top + mh > innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  m.style.left = left + 'px';
  m.style.top = top + 'px';
  kitOpenMenu = {menu: m, trigger};
  const search = m.querySelector('[data-menu-search]');
  if (search) { search.value = ''; search.dispatchEvent(new Event('input', {bubbles: true})); search.focus(); return; }
  const first = m.querySelector('button:not([disabled])');
  if (first) first.focus();
}
/* true while a menu or a modal surface is open: the render loop must not rebuild the DOM under it */
function uiBusy() {
  return !!kitOpenMenu || !!document.querySelector('.palette-scrim, dialog[open]');
}
/* A button that cannot be used now (aria-disabled, from btn({disabled})) is not dead: the click says why and does nothing else.
   It runs first (capture) so no handler of the app sees the click. */
document.addEventListener('click', e => {
  const el = e.target.closest && e.target.closest('[aria-disabled="true"]');
  if (!el) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  if (el.closest('.menu') && typeof kitMenuClose === 'function') kitMenuClose();
  if (typeof toast === 'function') toast(el.dataset.why || el.getAttribute('title') || 'Not available right now.', null, {bad: false});
}, true);
document.addEventListener('click', e => {
  const trig = e.target.closest && e.target.closest('[data-menu]');
  if (trig) {
    e.preventDefault();
    e.stopPropagation();
    if (kitOpenMenu && kitOpenMenu.trigger === trig) kitMenuClose(); else kitMenuOpen(trig);
    return;
  }
  if (kitOpenMenu) {
    const inMenu = kitOpenMenu.menu.contains(e.target);
    if (!inMenu) kitMenuClose();
    else if (e.target.closest('button')) setTimeout(() => kitMenuClose(), 0);   // let the app's delegate run the item first
  }
}, true);
document.addEventListener('keydown', e => {
  if (!kitOpenMenu) return;
  const items = [...kitOpenMenu.menu.querySelectorAll('button:not([disabled])')].filter(b => b.offsetParent !== null);       // not the filtered-out or the collapsed
  if (document.activeElement && document.activeElement.matches('[data-menu-search]') && ['Home', 'End', 'ArrowUp'].includes(e.key)) { if (e.key === 'ArrowUp') e.preventDefault(); return; }       // the box keeps its own cursor keys
  const i = items.indexOf(document.activeElement);
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); kitMenuClose(true); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); (items[i + 1] || items[0]).focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); (items[i - 1] || items[items.length - 1]).focus(); }
  else if (e.key === 'Home') { e.preventDefault(); items[0] && items[0].focus(); }
  else if (e.key === 'End') { e.preventDefault(); items[items.length - 1] && items[items.length - 1].focus(); }
  else if (e.key === 'Tab') kitMenuClose();
}, true);
addEventListener('resize', () => kitMenuClose());
addEventListener('scroll', e => { if (kitOpenMenu && !kitOpenMenu.menu.contains(e.target)) kitMenuClose(); }, true);

/* ---------- theme: 'system' | 'light' | 'dark' (the <head> bootstrap applies it before first paint) ---------- */
const THEME_KEY = 'pcb_advisor_theme';
function getThemePref() {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch (e) {
    return 'system';
  }
}
function setThemePref(v) {
  try {
    if (v === 'light' || v === 'dark') localStorage.setItem(THEME_KEY, v);
    else localStorage.removeItem(THEME_KEY);
  } catch (e) {
    /* storage blocked: the choice lasts for this page only */
  }
  applyTheme(v);
}
function applyTheme(v) {
  const root = document.documentElement;
  if (v === 'light' || v === 'dark') root.dataset.theme = v;
  else delete root.dataset.theme;
}
