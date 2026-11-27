"""F-C (fixes leave the app as hand steps with no tracked state), behaviour legs (a)-(e). One metric per lettered part.
(a) reuses T-D's measurement of hand-step advice without a ledger item (same rule, F-C's own id)."""
from __future__ import annotations

import hashlib
import json
import re
import time

from lib import Result, metric
from live import common, pins, seed
from live.driver import Page


@metric(id="F-C(a)", title="Every hand-step advice creates a ledger item (open -> fixed -> re-checked -> closed, or accepted)",
        root="R5", level="B", kind="behaviour")
def fc_a(ctx):
    from metrics import live_themes
    r = live_themes.td(ctx)                     # the T-D rule, measured again under F-C's id (no second definition)
    r.expected = "hand-step advice without a ledger item = 0 (ACCEPTANCE F-C(a); the T-D measurement)"
    return r


@metric(id="F-C(b)", title="'Done, check again' re-runs the check on the current file: the re-check record names its sha256",
        root="R5", p0=("P0-3",), level="B", kind="behaviour")
def fc_b(ctx):
    srv = common.private(ctx, "F-C(b)", fresh=True)
    rec = {}
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        pdir = srv.projects / srv.project
        bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
        cands = [ln for ln in bom if ln.get("datasheet") and (pdir / "sources" / ln["datasheet"]).is_file()
                 and (pdir / "sources" / (ln["datasheet"] + ".txt")).is_file() and ln.get("pins_status") == "verified"]
        ln = ctx.rng.choice(cands)
        f = pdir / "sources" / ln["datasheet"]
        f.write_bytes(f.read_bytes() + f"\n%canary {ctx.rng.randrange(10**9)}\n".encode())     # the file changed after its check
        new_sha = hashlib.sha256(f.read_bytes()).hexdigest()
        srv.restart()
        with Page(srv.url, srv.project) as P:
            P.open("checks")
            btn = P.page.get_by_role("button", name=re.compile(r"check (?:datasheets|again)", re.I))
            pressed = btn.count() > 0
            if pressed:
                btn.first.click()
                for _ in range(60):
                    P.page.wait_for_timeout(1000)
                    if not P.page.get_by_role("button", name=re.compile(r"checking", re.I)).count():
                        break
        st, state = srv.get("/api/state")
        blob = json.dumps(state)
        rec = {"line": ln["key"], "file": ln["datasheet"], "new_sha256": new_sha, "control_pressed": pressed,
               "record_names_current_sha": new_sha in blob or new_sha in (pdir / "bom.json").read_text(encoding="utf-8")}
    finally:
        srv.stop()
    ok = rec.get("control_pressed") and rec.get("record_names_current_sha")
    return Result("pass" if ok else "fail", measured=0 if ok else 1,
                  expected="after the file changes, the check-again control re-runs and its record carries the file's current sha256",
                  detail=json.dumps(rec), evidence=[common.save(ctx, "F-C(b)", rec)])


@metric(id="F-C(c)", title="'Unknown' is shown only where the oracle finds no detail",
        root="R5", level="B", kind="behaviour")
def fc_c(ctx):
    run = common.Run(ctx)
    # the detail Altium wrote: the DRC violation lines of the last DRC record (verbatim Altium text, read from the file)
    detail = {}
    for r in common.seed.read_jsonl(run.project_dir / "board-log.jsonl"):
        if r.get("op") == "drc" and isinstance(r.get("drc"), dict) and r["drc"].get("violations"):
            detail = {}
            for v in r["drc"]["violations"]:
                cls = v.split("(")[0].strip().lower()
                detail[cls] = detail.get(cls, 0) + 1
    texts = []
    with Page(run.url, run.project) as P:
        P.open()
        for st in ("pcb", "rules", "outputs", "checks"):
            P.stage(st)
            texts.append(P.text())
    hits = []
    for t in texts:
        for line in t.splitlines():
            if re.search(r"\bunknown\b", line, re.I):
                for cls, n in detail.items():
                    words = [w for w in re.findall(r"[a-z]+", cls) if len(w) >= 3 and w not in ("constraint", "minimum")]
                    head = re.split(r"\t|\(|:", line.lower())[0]          # the item the line is about (its first cell)
                    if words and all(w in head for w in words) and len(set(re.findall(r"[a-z]{3,}", head)) - set(words)) == 0:
                        hits.append({"line": line.strip()[:160], "oracle_detail_lines": n, "class": cls})
    seen = {h["line"] for h in hits}
    return Result("pass" if not hits else "fail", measured=len(seen),
                  expected="'Unknown' shown for an item the oracle has detail for = 0",
                  detail=json.dumps(hits)[:1500], evidence=[ctx.ev(run.project_dir / "board-log.jsonl", "Altium DRC lines"),
                                                           common.save(ctx, "F-C(c)", hits)])


VIA_ADVICE = re.compile(r"(?:add|place|put|use|drop)\s[^.]{0,60}\b(?:thermal\s+)?vias?\b[^.]{0,60}\b(?:in|under|inside|into)\s+(?:the\s+)?"
                        r"(?:EP|exposed pad|thermal pad|centre pad|center pad|pad)\b|\bvias?\b[^.]{0,30}\b(?:in|under) (?:the )?(?:EP|exposed pad)"
                        r"|\b(?:vias|them):?\s*\*{0,2}\s*add them in Altium", re.I)
NEGATED = re.compile(r"\b(?:cannot|can.t|never|don.t|do not|no)\b", re.I)


@metric(id="F-C(d)", title="Advice never breaks the system's own rules (via in an SMD pad)",
        root="R5", level="B", kind="behaviour")
def fc_d(ctx):
    run = common.Run(ctx)
    st, rules = run.get("/api/rules")
    rule_text = json.dumps(rules)
    forbids = bool(re.search(r"no via in an SMD pad|via-in-pad (?:is )?never|via in pad[^\"]{0,40}not allowed", rule_text, re.I))
    hits = []
    for r in common.chat_rows(run.project_dir):
        if r.get("role") != "agent":
            continue
        txt = str(r.get("text", ""))
        for para in re.split(r"\n+", txt):
            m = VIA_ADVICE.search(para)
            if m and not NEGATED.search(para[:max(0, m.start())][-40:] + m.group(0)):
                hits.append({"ts": r.get("ts"), "advice": para.strip()[:200]})
    n = len(hits) if forbids else 0
    return Result("pass" if n == 0 else "fail", measured=n,
                  expected="advice that contradicts a rule the system itself states (here: no via in an SMD pad) = 0",
                  detail=f"rule found in the served rule set: {forbids}; {hits[:3]}",
                  evidence=[common.save(ctx, "F-C(d)", {"forbids": forbids, "hits": hits})] +
                  [ctx.ev(f, "chat record") for f in sorted((run.project_dir / "chats").glob("*.jsonl"))])


SKIP_CTRL = re.compile(r"delete|remove|archive|revoke|dismiss|close|collapse|export|download|open in|new tab|build library|generate|"
                       r"make again|make all|upload|find my report|route|place|check board|apply rules|create|link|next:|confirm",
                       re.I)


def _files(d) -> dict:
    """The project's own files (not its logs or chats): path -> (size, mtime)."""
    out = {}
    for f in d.rglob("*"):
        if f.is_file() and f.suffix not in (".jsonl", ".log") and "chats" not in f.parts and "logs" not in f.parts:
            st = f.stat()
            out[str(f.relative_to(d))] = (st.st_size, st.st_mtime_ns)
    return out


@metric(id="F-C(e)", title="Controls with no effect: a click changes neither the page nor the API",
        root="R5", level="B", kind="behaviour")
def fc_e(ctx):
    run = common.Run(ctx)
    dead = []
    tried = 0
    with Page(run.url, run.project) as P:
        P.open()
        for st in ("idea", "bom", "sch", "pcb", "rules", "outputs", "checks"):
            P.stage(st)
            # every element that offers a click: buttons, links, role=button, focusable rows and anything with a pointer cursor
            n = P.eval("""() => { window.__acc = [...document.querySelectorAll('main *')].filter(e => {
                   const r = e.getBoundingClientRect(); if (!r.height || e.disabled || e.closest('svg')) return false;
                   if (e.matches('input,select,textarea,label,summary,details,option')) return false;
                   const offers = e.matches('button,a[href]:not([target=_blank]),[role=button],tr[tabindex],[data-act]');   // own click semantics; a new tab is not observable here
                   const handle = /resize|drag|choose file/i.test(e.getAttribute('aria-label') || e.title || e.innerText || '');
                   const current = e.matches('[aria-pressed=true],[aria-selected=true],[aria-current],.on,.active,.sel,.cur');
                   return offers && !handle && !current && !(e.parentElement && e.parentElement.closest('button,a[href],[role=button],[data-act]')); });
                 return window.__acc.length; }""")
            for i in range(min(n, 80)):
                lab = P.eval("i => { const e = window.__acc && window.__acc[i]; return e && e.isConnected ? "
                             "((e.innerText || e.getAttribute('aria-label') || e.title || e.tagName).trim().slice(0, 50)) : null; }", i)
                if not lab or SKIP_CTRL.search(lab):
                    continue
                sig = ("() => { const h = document.body.innerHTML; let x = 0; for (let k = 0; k < h.length; k++) x = (x * 31 + h.charCodeAt(k)) | 0; "
                       "return x + '|' + location.href + '|' + document.querySelectorAll('dialog[open],.toast:not([hidden])').length; }")
                before, files0 = P.eval(sig), _files(run.project_dir)
                try:
                    P.eval("i => window.__acc[i].click()", i)
                except Exception:
                    continue
                tried += 1
                P.page.wait_for_timeout(1000)
                for _ in range(10):                      # let a running request settle before judging the final state
                    if not P.eval("() => [...document.querySelectorAll('button')].some(b => /…$/.test(b.innerText.trim()))"):
                        break
                    P.page.wait_for_timeout(1000)
                if P.eval(sig) == before and _files(run.project_dir) == files0:
                    dead.append({"page": st, "control": lab})
                P.page.keyboard.press("Escape")
                if P.eval(sig) != before:
                    P.stage(st, wait_ms=600)
                    P.eval("""() => { window.__acc = [...document.querySelectorAll('main *')].filter(e => {
                       const r = e.getBoundingClientRect(); if (!r.height || e.disabled || e.closest('svg')) return false;
                       if (e.matches('input,select,textarea,label,summary,details,option')) return false;
                       const offers = e.matches('button,a[href]:not([target=_blank]),[role=button],tr[tabindex],[data-act]');
                       const handle = /resize|drag|choose file/i.test(e.getAttribute('aria-label') || e.title || e.innerText || '');
                       const current = e.matches('[aria-pressed=true],[aria-selected=true],[aria-current],.on,.active,.sel,.cur');
                       return offers && !handle && !current && !(e.parentElement && e.parentElement.closest('button,a[href],[role=button],[data-act]')); }); }""")
    return Result("pass" if not dead else "fail", measured=len(dead),
                  expected="enabled controls whose click leaves the page and the project files as they were = 0",
                  detail=f"tried {tried}; dead: {dead[:10]}", evidence=[common.save(ctx, "F-C(e)", {"tried": tried, "dead": dead})])
