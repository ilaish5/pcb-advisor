"""Failure paths that need no Altium (ACCEPTANCE P0-4 frozen list, the non-Altium part), and the capture of what the page shows
for each. Shared by P0-4 (is it readable), P0-2 (does it end visibly and stay) and P0-1 (is the item named).

A path = trigger(ctx, srv, P, token) on a private server + the words its title must use. `token` is a random object name
(A5): the rule name, the URL path, the file name. The capture takes every visible element that appeared after the trigger
and reads it as a student would: first line (the title), its weight, how many lines the collapsed view has, the controls.
"""
from __future__ import annotations

import json
import re
import time

from live import common, faults, seed

# P0-4 collapsed-view forbidden list (frozen: ACCEPTANCE P0-4 + T-E regexes)
FORBIDDEN = {
    "file path": re.compile(r"[A-Za-z]:\\\\?[\w .-]+\\|(?<![\w.])/(?:tmp|home|Users|var|opt)/[\w./ -]+|\\\\[\w.-]+\\"),
    "exception or error class": re.compile(r"\b\w*(?:Error|Exception)\b(?=[:\s(]|$)|Traceback|\[Errno \d+\]"),
    "WinError / HRESULT / hex code": re.compile(r"WinError|HRESULT|\b0x[0-9A-Fa-f]{4,}\b"),
    "script or file name": re.compile(r"\b[\w-]+\.(?:py|pas|js)\b"),
    "internal id": re.compile(r"\bp20\d{12,}\b|\btoolu_\w+|\b[0-9a-f]{12,}\b"),
    "float noise": re.compile(r"\d\.\d*(?:9{4,}|0{4,}[1-9])\d*"),
    "internal action name": re.compile(r"bom\.propose|student_said|chat\.ask|\bchecks/"),
}
TITLE_MAX = 70
COLLAPSED_MAX_LINES = 3

# Elements that can carry a failure: notices, toasts, banners, alerts, and agent chat messages.
CANDIDATES_JS = r"""
() => {
  const vis = el => { if (el.closest('details:not([open]) > :not(summary)')) return false;     // folded away in a closed <details>
    if (el.checkVisibility && !el.checkVisibility({checkVisibilityCSS: true})) return false;
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const sel = '[role=alert],[role=status],.toast,[class*=toast],[class*=banner],[class*=notice],[class*=err],[class*=bad],[class*=warn],[class*=fail],.msg.agent,[class*=msg][class*=agent]';
  const out = [];
  document.querySelectorAll(sel).forEach((el, i) => {
    if (!vis(el)) return;
    if (el.closest('tr[data-key]') || el.matches('.tag,[class*=via],[class*=chip]') && !el.matches('[role=alert]')) return;
    const txt = (el.innerText || '').trim(); if (!txt) return;
    // the collapsed view: text not inside a closed <details> or an element hidden by a collapsed control
    const first = (() => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT,
        {acceptNode: n => n.textContent.trim() && vis(n.parentElement) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT});
        const n = w.nextNode(); return n ? n.parentElement : null; })();
    // rendered lines: distinct line boxes of the visible text (Range client rects grouped by their top)
    const tops = new Set(); const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) { const n = tw.currentNode; if (!n.textContent.trim() || !vis(n.parentElement)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (r.width > 1 && r.height > 1) tops.add(Math.round(r.top / 4)); }
    const details = el.querySelector('details:not([open]) > summary, [aria-expanded=false]');
    out.push({key: el.tagName + '|' + String(el.className) + '|' + txt.slice(0, 120), text: txt,
      first_line: txt.split('\n')[0].trim(), first_weight: first ? parseInt(getComputedStyle(first).fontWeight) : 0,
      lines: tops.size,
      details: details ? (details.innerText || details.getAttribute('aria-label') || 'details').trim() : null,
      buttons: [...el.querySelectorAll('button,a')].filter(vis).map(b => (b.innerText || b.title || '').trim()),
      cls: String(el.className), path: (() => { let p = [], e = el; while (e && e !== document.body) { p.unshift(e.tagName + ([...(e.parentElement||{children:[]}).children].indexOf(e))); e = e.parentElement; } return p.join('>'); })()});
  });
  return out;
}
"""


def visible_failures(P) -> list[dict]:
    return P.eval(CANDIDATES_JS)


PROGRESS = re.compile(r"status|progress|spin|busy|working", re.I)


def _busy(P) -> bool:
    return bool(P.eval("""() => [...document.querySelectorAll('[class*=chat-status],[class*=spin],[aria-busy=true]')]
        .some(e => e.getBoundingClientRect().height > 0)"""))


def capture(P, trigger, wait_s: float = 30.0, settle_s: float = 1.0) -> dict:
    """Run trigger(); return every candidate element that was not there before, each with the time it was first seen,
    and whether it was still visible 15 s later. Waits while the page shows a running state (the operation has not ended)."""
    before = {c["key"] for c in visible_failures(P)}
    t0 = time.time()
    trigger()
    seen: dict = {}
    end = t0 + wait_s
    while time.time() < end:
        for c in visible_failures(P):
            if c["key"] not in before and c["key"] not in seen:
                c["t_seen"] = round(time.time() - t0, 1)
                seen[c["key"]] = c
        final = [k for k, c in seen.items() if not PROGRESS.search(c["cls"])]
        if final and not _busy(P) and time.time() - t0 > min(seen[k]["t_seen"] for k in final) + settle_s:
            break
        P.page.wait_for_timeout(400)
    P.page.wait_for_timeout(15000)
    still = {c["key"] for c in visible_failures(P)}
    for k, c in seen.items():
        c["still_after_15s"] = k in still
    return {"t0": t0, "new": list(seen.values())}


def judge_title(title: str, token: str, action_words: re.Pattern) -> list[str]:
    """Deterministic part of the P0-4 title check: the title names the injected object (its random token) and the action."""
    bad = []
    if token.lower() not in title.lower():
        bad.append(f"title does not name the object ({token})")
    if not action_words.search(title):
        bad.append("title does not name the action")
    return bad


def readability(c: dict, token: str, action_words: re.Pattern, original: str | None) -> list[str]:
    """P0-4 checks on one captured failure element. Returns the violations."""
    v = []
    title = c["first_line"]
    collapsed = c["text"] if not c.get("details") else c["text"]     # the visible text is the collapsed view
    if c["first_weight"] < 600:
        v.append("no bold title")
    if len(title) > TITLE_MAX:
        v.append(f"title longer than {TITLE_MAX} chars ({len(title)})")
    v += judge_title(title, token, action_words)
    if not c.get("details"):
        v.append("no collapsed Details control")
    for what, rx in FORBIDDEN.items():
        m = rx.search(collapsed)
        if m:
            v.append(f"collapsed view shows {what}: {m.group(0)[:40]!r}")
    if c["lines"] > COLLAPSED_MAX_LINES:
        v.append(f"collapsed view is {c['lines']} lines (> {COLLAPSED_MAX_LINES})")
    if not c.get("still_after_15s"):
        v.append("message disappeared within 15 s")
    if original and original.strip() and _norm(original) not in _norm(c.get("expanded", c["text"])):
        v.append("expanded view does not hold the original text word for word")
    return v


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def pick_failure(cap: dict, token: str) -> dict | None:
    """The element the trigger produced: the newest that names the token, else the newest bad-toned one, else the newest."""
    new = cap["new"]
    if not new:
        return None
    new = [c for c in new if not PROGRESS.search(c["cls"])] or new
    named = [c for c in new if token.lower() in c["text"].lower()]
    pool = named or [c for c in new if re.search(r"bad|err|fail|alert|toast", c["cls"])] or new
    return sorted(pool, key=lambda c: c["t_seen"])[-1]


def _errors_in(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("error", "message") and isinstance(v, str) and v.strip():
                out.append(v)
            else:
                _errors_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _errors_in(v, out)


def server_record(P, srv, t0: float) -> str | None:
    """The server's own words for the failure (word-for-word source of the expanded view): the first error text in an
    API answer after the trigger, else the newest agent chat record written after it."""
    for a in P.api:
        if a["t"] >= t0 and a["path"] not in ("/api/state", "/api/chat/progress"):
            errs = []
            _errors_in(a.get("body"), errs)
            if errs:
                return errs[0]
    rows = common.chat_rows(srv.projects / srv.project)
    late = [r for r in rows if r.get("role") == "agent"]
    if late:
        r = late[-1]
        return " ".join(str(x) for x in [r.get("text", "")] + list(r.get("refused") or []) if x)
    return None


# ------------------------------------------------------------------ the paths
def _api_call(P, path: str, body: dict) -> None:
    """Call the page's own api() helper (the path a button takes), so its own error display runs."""
    P.page.evaluate("([p, b]) => api(p, b).catch(() => {})", [path, body])


def path_rule_kind(ctx, srv, P, token):
    """An unsupported rule kind submitted through the Extra rules path."""
    kind = "Kind" + token
    original = {"error": None}

    def trig():
        _api_call(P, "/api/rules/extra", {"name": token, "kind": kind, "scope1": "All", "scope2": "All", "values": {}})
    P.stage("rules")
    cap = capture(P, trig)
    st, body = srv.post("/api/rules/extra", {"name": token + "x", "kind": kind, "values": {}})    # the server's own record of the error
    original["error"] = (body or {}).get("error", "").replace(token + "x", token) if isinstance(body, dict) else ""
    return cap, original["error"], re.compile(r"rule", re.I), token


def path_url_404(ctx, srv, P, token, nf=None):
    """A URL source that returns 404."""
    url = f"http://127.0.0.1:{nf.server_address[1]}/datasheets/{token}.pdf"

    P.page.evaluate("go('sources')")
    P.page.wait_for_timeout(1500)

    def trig():                     # the Sources page's "Add from URL" control, as a student uses it
        P.page.evaluate("document.querySelector('[data-act=addurl]').click()")   # the item of the Add menu
        dlg = P.page.locator('dialog input, [role=dialog] input, .modal input').first
        dlg.fill(url)
        dlg.press("Enter")
    cap = capture(P, trig, wait_s=60)
    return cap, None, re.compile(r"fetch|download|source|get|load|add", re.I), token


def path_stock_unreachable(ctx, srv, P, token):
    """JLC and LCSC unreachable while the student checks stock (the server's network goes to a port nobody listens on)."""
    P.stage("bom")
    btn = P.page.get_by_role("button", name=re.compile(r"check stock", re.I)).first

    def trig():
        btn.click()
    cap = capture(P, trig, wait_s=40)
    return cap, None, re.compile(r"stock|price|check", re.I), "LCSC"


def path_engine_killed(ctx, srv, P, token):
    """The agent engine dies mid-turn."""
    common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": f"{token}.md"}, "delay": 0.5}, {"sleep": 60}],
                            "final": "never"}, name=f"die-{token}")
    box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first

    def trig():
        box.fill(f"Please look at {token}")
        box.press("Enter")
        t = time.time()
        while not faults.engine_pids(srv) and time.time() - t < 15:
            time.sleep(0.2)
        time.sleep(2)
        faults.kill_engine(srv)
    cap = capture(P, trig, wait_s=40)
    return cap, None, re.compile(r"answer|agent|engine|turn|reply", re.I), "engine"


def path_guard_revert(ctx, srv, P, token):
    """A file under the install is written during an agent turn (by a process that is not the agent); the guard reverts it."""
    target = srv.wt / "shared" / f"acc-canary-{token}.md"
    common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "x"}, "delay": 0.5}, {"sleep": 4}],
                            "final": "Done looking."}, name=f"guard-{token}")
    box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first

    def trig():
        box.fill("What is open?")
        box.press("Enter")
        t = time.time()
        while not faults.engine_pids(srv) and time.time() - t < 15:
            time.sleep(0.2)
        faults.foreign_write(target, f"canary {token}\n")
    cap = capture(P, trig, wait_s=40)
    try:
        target.unlink()
    except OSError:
        pass
    return cap, None, re.compile(r"restor|revert|put back|undo|changed|wrote|edit", re.I), f"acc-canary-{token}"


PATHS = {
    "unsupported rule kind": path_rule_kind,
    "URL source 404": path_url_404,
    "JLC and LCSC unreachable": path_stock_unreachable,
    "agent engine killed": path_engine_killed,
    "guard revert": path_guard_revert,
}


def run_paths(ctx, names=None, tag="P0-4") -> list[dict]:
    """Run each failure path once, in a random order (ctx.rng), on its own private fixture server; return one record each."""
    from live.driver import Page
    names = list(names or PATHS)
    ctx.rng.shuffle(names)
    out = []
    for name in names:
        token = "".join(ctx.rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))
        env, nf = None, None
        if name == "JLC and LCSC unreachable":
            env = faults.proxy_env(faults.refusing_port())
        srv = common.private(ctx, f"{tag}-{name}", env=env, fresh=True)
        try:
            srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
            srv.restart()
            if name == "URL source 404":
                nf = faults.not_found_server()
            with Page(srv.url, srv.project) as P:
                P.open()
                fn = PATHS[name]
                cap, original, words, tok = fn(ctx, srv, P, token, nf=nf) if nf else fn(ctx, srv, P, token)
                c = pick_failure(cap, tok)
                if c is not None and c.get("details"):
                    try:          # open the details and read the expanded view
                        P.page.locator(f"text={c['details']}").first.click(timeout=3000)
                        P.page.wait_for_timeout(500)
                        c["expanded"] = next((x["text"] for x in visible_failures(P) if x["path"] == c["path"]), c["text"])
                    except Exception:
                        c["expanded"] = c["text"]
                original = original or server_record(P, srv, cap["t0"])
                persisted = None
                if c is not None:
                    P.reload()
                    persisted = tok.lower() in P.text().lower() or c["first_line"][:30] in P.text()
                out.append({"path": name, "token": tok, "captured": c, "all_new": cap["new"], "original": original,
                            "words": words.pattern, "after_reload": persisted})
        finally:
            srv.stop()
            if nf:
                nf.shutdown()
    return out
