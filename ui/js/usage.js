/* PCB Advisor UI - usage log: what the person saw and clicked, and the page's own errors. Loaded first, needs nothing else.
   Events are batched and sent to this machine's server (POST /api/log/usage), which writes them to the project's usage-log.jsonl.
   Never logged: keystrokes, input values, password fields, file contents. Every failure here is silent. */
(function () {
  var SID = Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  var Q = [], seen = {}, lastView = null, errs = 0;
  window.USAGE_SESSION = SID;

  function cut(s, n) { s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n) : s; }
  function proj() { try { return typeof PROJECT !== 'undefined' && PROJECT ? PROJECT : ''; } catch (e) { return ''; } }
  function view() {
    try { return typeof mainKey === 'function' ? mainKey() + (sideKey() ? '|' + sideKey() : '') : ''; } catch (e) { return ''; }
  }
  function localIso() {
    var d = new Date(), p = function (n, w) { return ('00' + n).slice(-(w || 2)); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' +
      p(d.getSeconds()) + '.' + p(d.getMilliseconds(), 3);
  }
  function usage(kind, f) {
    try {
      f = f || {};
      for (var k in f) if (typeof f[k] === 'string' && f[k].length > 2000) f[k] = f[k].slice(0, 2000);      // no single text runs away
      f.kind = kind; f.project = f.project || proj(); f.ts = localIso();      // f.project: an event that belongs to another project than the open one (a project just created)
      if (kind !== 'view') f.view = view();
      Q.push(f);
      if (Q.length > 500) Q.shift();                // bounded: the oldest goes first
    } catch (e) { /* silent */ }
  }
  window.usage = usage;

  // how many events from the front of the queue fit one request (at most 100 and about 40 KB: sendBeacon allows 64 KB)
  function batchSize() {
    var n = 0, size = 0;
    while (n < Q.length && n < 100) { size += JSON.stringify(Q[n]).length; if (size > 40000 && n > 0) break; n++; }
    return n;
  }
  var sending = false;
  // events leave the queue only once the server (or the browser, for a beacon) has accepted them
  function flush(beacon) {
    try {
      for (var i = 0; i < (beacon ? 5 : 1) && Q.length && (beacon || !sending); i++) {
        var n = batchSize(), body = JSON.stringify({session: SID, events: Q.slice(0, n)});
        if (beacon && navigator.sendBeacon) {
          if (!navigator.sendBeacon('/api/log/usage', new Blob([body], {type: 'text/plain'}))) return;
          Q.splice(0, n);
        } else {
          sending = true;
          fetch('/api/log/usage', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body, keepalive: true})
            .then(function (r) { if (r.ok || (r.status >= 400 && r.status < 500)) Q.splice(0, n); sending = false; })   // a 4xx is a refusal for good: do not resend it
            .catch(function () { sending = false; });
          return;
        }
      }
    } catch (e) { sending = false; }
  }
  setInterval(function () { flush(false); }, 2000);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(true); });
  window.addEventListener('pagehide', function () { flush(true); });

  // a note that stays on screen is logged once per view, not again each time the page is drawn again
  var seenCount = 0;
  function once(key) {
    if (seen[key]) return false;
    if (++seenCount > 300) { seen = {}; seenCount = 1; }
    seen[key] = 1;
    return true;
  }
  /* what the page shows the person: a toast, a note, a prompt (level: ok | error | prompt). force: a toast, which is an event, not a state */
  window.usageShown = function (text, level, force) {
    text = cut(text, 600);
    if (text && (force || once(view() + '|' + level + '|' + text))) usage('shown', {text: text, level: level || 'ok'});
  };

  // the screen shown: checked once a second, so every way of navigating is covered without touching it
  setInterval(function () {
    var v = view();
    if (v !== lastView) { lastView = v; seen = {}; seenCount = 0; usage('view', {name: v || '(loading)'}); }
  }, 1000);

  document.addEventListener('click', function (e) {
    try {
      var el = e.target && e.target.closest && e.target.closest('button, a, summary, [data-act], [data-tab], [data-key], [role=button], select, input[type=checkbox], input[type=radio]');
      if (!el || el.type === 'password') return;
      if (el.getAttribute('data-act') === 'newproj') return;        // shell.js logs the creation under the new project
      var cls = typeof el.className === 'string' ? el.className : '';
      var box = el.type === 'checkbox' || el.type === 'radio';
      var lab = box ? (el.closest('label') ? el.closest('label').innerText : '') : '';
      var key = box ? (el.getAttribute('data-ptick') || el.getAttribute('data-preset-toggle') || el.getAttribute('data-extra-toggle') ||
        el.getAttribute('data-std-pick') || '') : '';
      var rec = {text: cut(box ? (lab || el.getAttribute('aria-label') || el.name || key || el.id) : (el.innerText || el.getAttribute('aria-label') || el.title || el.value), 80),
        id: el.id || key, act: el.getAttribute('data-act') || el.getAttribute('data-tab') || '', tag: el.tagName.toLowerCase(), cls: cut(cls, 60)};
      if (box) rec.checked = !!el.checked;           // the click has already changed it: this is the state now
      usage('click', rec);
    } catch (x) { /* silent */ }
  }, true);
  document.addEventListener('change', function (e) {
    try {
      var t = e.target;
      if (t && t.type === 'file' && t.files) usage('upload', {files: Array.prototype.map.call(t.files, function (f) { return {name: f.name, size: f.size}; })});
    } catch (x) { /* silent */ }
  }, true);
  document.addEventListener('submit', function (e) {
    try { var f = e.target; usage('submit', {id: f.id || '', text: cut(f.getAttribute && f.getAttribute('aria-label') || f.id || 'form', 80)}); } catch (x) { /* silent */ }
  }, true);
  // dialogs: what they asked, and what the person chose
  document.addEventListener('close', function (e) {
    try { if (e.target && e.target.tagName === 'DIALOG') usage('choice', {text: cut(e.target.innerText, 200), choice: e.target.returnValue || 'cancel'}); } catch (x) { /* silent */ }
  }, true);
  try {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        Array.prototype.forEach.call(m.addedNodes, function (n) {
          if (!n.matches) return;
          var sel = 'dialog, .note, .pv-note, [role=alert], .calc-warn';
          var hits = Array.prototype.slice.call(n.querySelectorAll(sel));
          if (n.matches(sel)) hits.unshift(n);
          hits.forEach(function (hit) {
            window.usageShown(hit.innerText, hit.tagName === 'DIALOG' ? 'prompt' : (/\b(bad|warn)\b/.test(hit.className) || hit.getAttribute('role') === 'alert') ? 'error' : 'ok');
          });
        });
      });
    }).observe(document.documentElement, {childList: true, subtree: true});
  } catch (e) { /* silent */ }

  /* errors: to the run log and the usage log through /api/log/client; at most 20 per page load */
  function report(message, source, line, column, stack) {
    try {
      if (errs++ >= 20) return;
      var body = JSON.stringify({message: cut(message, 1000), source: cut(source, 300), line: line || 0, column: column || 0,
        stack: String(stack || '').slice(0, 3000), view: view(), session: SID});
      var q = proj() ? '?project=' + encodeURIComponent(proj()) : '';
      fetch('/api/log/client' + q, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body, keepalive: true}).catch(function () {});
    } catch (x) { /* silent */ }
  }
  window.addEventListener('error', function (e) { report(e.message, e.filename, e.lineno, e.colno, e.error && e.error.stack); });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    report(r && r.message ? r.message : String(r), '', 0, 0, r && r.stack);
  });
})();
