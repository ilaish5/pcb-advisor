/* PCB Advisor UI - update and about: the server checks GitHub once at every start (scripts/update.py); when this
   install is behind, the nav foot shows Update, and the first time per start a toast says so. Update fast-forwards,
   checks the new code starts, and the server restarts into it; the page reloads itself when it answers again.
   Settings > About shows the version and what the agent did in this project (scripts/introspect.py).
   Names here start with upd* / about* because every ui/js file shares one global scope. */

let UPD = null;                  // GET /api/update: {state, behind, can_update, commits, reason, version, ...}
let updToasted = false;
let updBusy = false;
let ABOUT = null;                // GET /api/introspect, for Settings
let aboutFor = null;

async function updLoad(refresh) {
  try {
    UPD = await api('/api/update' + (refresh ? '?refresh=1' : ''), undefined, {soft: true});
  } catch (e) {
    return;
  }
  if (UPD && UPD.state === 'checking') { setTimeout(() => updLoad(false), 3000); return; }  // the start-up check is still running
  renderNav();
  if (mainView() === 'settings') renderCenter(true);
  if (UPD && UPD.behind > 0 && !updToasted) {
    updToasted = true;
    toast(`An update is available (${plural(UPD.behind, 'change')}).`, {label: 'See what is new', onClick: updDialog});
  }
}

function updNavBtn() {           // only when there is something to update to
  if (!UPD || !(UPD.behind > 0)) return '';
  const tip = UPD.can_update ? `Update: ${plural(UPD.behind, 'new change')}` : `Update waiting: ${UPD.reason || ''}`;
  return `<button type="button" class="nitem upd" data-act="update-open" data-nav="update" title="${esc(tip)}" aria-label="${esc(tip)}">` +
    `<span class="no">${icon('download', 's')}<i class="upd-dot" aria-hidden="true"></i></span><span class="lbl">Update</span><span class="hint">${UPD.behind}</span></button>`;
}

function updDialog() {
  if (!UPD) return;
  const dlg = document.createElement('dialog');
  dlg.className = 'dlg upd-dlg';
  dlg.setAttribute('aria-labelledby', 'upd-title');
  const v = UPD.version || {};
  const list = (UPD.commits || []).map(c => `<li><span class="m">${esc(c.sha)}</span> ${esc(c.subject)} <span class="muted">${esc((c.date || '').slice(0, 10))}</span></li>`).join('');
  const more = UPD.behind > (UPD.commits || []).length ? `<li class="muted">and ${UPD.behind - UPD.commits.length} more</li>` : '';
  const why = UPD.can_update
    ? `<p class="muted">The server restarts on the new version; your projects and settings stay as they are. If the new version does not start, it goes back to ${esc(v.commit || 'this one')} by itself.</p>`
    : `<p class="note warn">${esc(UPD.reason || 'This install cannot update itself.')}</p>`;
  dlg.innerHTML = `<form method="dialog"><h2 id="upd-title">${plural(UPD.behind, 'new change')}</h2>
    <p class="muted">This install: ${esc(v.commit || '?')}${v.date ? ' (' + esc(v.date.slice(0, 10)) + ')' : ''}. Latest: ${esc(UPD.latest || '?')}.</p>
    <ul class="upd-list">${list}${more}</ul>${why}
    <div class="acts"><button type="button" class="btn" data-cancel>${UPD.can_update ? 'Later' : 'Close'}</button>${UPD.can_update ? '<button type="submit" class="btn pri" value="ok">Update now</button>' : ''}</div></form>`;
  dlg.querySelector('[data-cancel]').addEventListener('click', () => dlg.close('cancel'));
  dlg.addEventListener('close', () => {
    const ok = dlg.returnValue === 'ok';
    dlg.remove();
    if (ok) updApply();
  });
  document.body.appendChild(dlg);
  dlg.showModal();
}

async function updApply() {
  if (updBusy) return;
  updBusy = true;
  toast('Updating. This takes a few seconds.');
  let r;
  try {
    r = await api('/api/update', {});
  } catch (err) {           // the error toast already said why (agent busy, local edits, the new version did not start)
    updBusy = false;
    updLoad(false);
    return;
  }
  if (!r.restarting) {
    updBusy = false;
    toast(`Updated to ${r.to}. Restart the server to use it.`);
    return;
  }
  toast(`Updated to ${r.to}. Restarting…`);
  updWaitForServer(r.to, Date.now());
}

function updWaitForServer(to, t0) {   // the old server stops, the new one answers on the same port: then reload
  setTimeout(async () => {
    try {
      const res = await fetch('/api/update', {cache: 'no-store'});
      const st = res.ok ? await res.json() : null;
      if (st && st.version && st.version.commit === to) { location.reload(); return; }
    } catch (e) {
      /* not up yet */
    }
    if (Date.now() - t0 > 60000) {
      updBusy = false;
      toast('The server did not come back. Start it again with start.bat.', null, {bad: true});
      return;
    }
    updWaitForServer(to, t0);
  }, 1000);
}

onAct('update-open', async () => { await updLoad(true); updDialog(); });
onAct('update-check', async (el) => {
  el.disabled = true;
  await updLoad(true);
  el.disabled = false;
  if (UPD && !(UPD.behind > 0)) toast(UPD.error || UPD.reason || 'Up to date.');
  else updDialog();
});

/* ---------- Settings > About ---------- */
async function aboutLoad() {
  aboutFor = PROJECT;
  try {
    ABOUT = await api('/api/introspect', undefined, {soft: true});
  } catch (e) {
    ABOUT = {error: e.message};
  }
  if (mainView() === 'settings' || sideView() === 'settings') renderCenter(true);
}
const aboutMoney = x => (x >= 0.01 || x === 0 ? `$${x.toFixed(2)}` : `$${x.toFixed(4)}`);
function aboutHTML() {
  if (aboutFor !== PROJECT) { aboutLoad(); return loadingLine('Loading'); }
  if (!ABOUT) return loadingLine('Loading');
  if (ABOUT.error) return errorLine('read the usage', ABOUT.error);
  const v = ABOUT.version || {}, u = (UPD && UPD.state === 'done') ? UPD : (v.update || {});
  const s = ABOUT.summary || {}, o = ABOUT.outputs || {counts: {}};
  const ver = v.commit ? `${v.commit} (${(v.date || '').slice(0, 10)}, ${v.branch})` : 'not a git install';
  const upd = u.behind > 0 ? `${plural(u.behind, 'new change')} waiting` : (u.error ? `could not check: ${u.error}` : (u.reason || 'not checked yet'));
  const rows = [['Version', ver], ['Updates', upd, false]];
  if (s.turns) {
    rows.push(['Agent turns', `${s.turns} in this project (${s.failed} failed)`]);
    rows.push(['Engine time', `${(s.seconds / 60).toFixed(1)} min`]);
    rows.push(['Cost', aboutMoney(s.cost_usd || 0) + (s.uncosted_turns ? ` + ${plural(s.uncosted_turns, 'turn')} with no cost reported` : '')]);
    if (s.with_numbers) rows.push(['Sourced', `${s.sourced} of ${s.with_numbers} answers with numbers cite a source or a script run (${s.sourced_pct}%)`]);
    const top = Object.entries(s.scripts || {}).slice(0, 5).map(([k, n]) => `${k} ${n}`).join(', ');
    if (top) rows.push(['Scripts run', top]);
  } else rows.push(['Agent turns', 'none recorded in this project yet']);
  const oc = Object.entries(o.counts || {}).map(([k, n]) => `${n} ${k}`).join(', ');
  if (oc) rows.push(['Outputs', oc]);
  return kv(rows) + `<p class="set-foot">${btn('Check for updates', {kind: 'line', size: 'sm', act: 'update-check'})}</p>`;
}
