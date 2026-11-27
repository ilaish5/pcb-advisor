"""Priority 0 invariants, the parts that need no Altium (ACCEPTANCE Part 0). Behaviour metrics on private servers started
from --live-commit (default the pre-fix commit), with oracle-owned faults and the oracle's fake engine.

Altium paths (library build, place, route, DRC, outputs, Altium modal, bridge timeout, IntLib locked) are the local phase.
"""
from __future__ import annotations

import json
import re
import time

from lib import Result, metric
from live import common, failures, faults, pins, seed
from live.driver import Page

# ------------------------------------------------------------------ P0-4


@metric(id="P0-4", title="Every failure is readable at a glance: bold title naming action and object, Details collapsed, full text kept",
        root="P0", p0=("P0-4",), level="B", kind="behaviour")
def p0_4(ctx):
    recs = failures.run_paths(ctx, tag="P0-4")
    rows, bad = [], 0
    for r in recs:
        c = r["captured"]
        if c is None:
            v = ["nothing shown (silent failure)"]
        else:
            v = failures.readability(c, r["token"], re.compile(r["words"], re.I), r["original"])
            if r["after_reload"] is False:
                v.append("gone after a page reload")
        bad += bool(v)
        rows.append({"path": r["path"], "object": r["token"], "title": (c or {}).get("first_line", "")[:100], "violations": v})
    ev = [common.save(ctx, "P0-4-paths", recs)]
    return Result("pass" if bad == 0 else "fail", measured=bad,
                  expected=f"failure paths whose page message breaks a P0-4 rule = 0 (of {len(recs)} non-Altium paths, random order and objects)",
                  detail=json.dumps(rows)[:3000], evidence=ev)


# ------------------------------------------------------------------ P0-2
PHASE_GENERIC = re.compile(r"^\s*(working|thinking|loading|please wait|busy|running|checking)\W*$", re.I)
ELAPSED = re.compile(r"\b\d+\s*(?:s|sec|seconds?|min|minutes?)\b|\b\d+:\d\d\b", re.I)
STEP_OR_RANGE = re.compile(r"\b\d+\s*(?:/|of)\s*\d+\b|\b\d+\s*[-–]\s*\d+\s*(?:s|sec|min|minutes?)\b|\babout\s+\d+\s*(?:s|sec|min)", re.I)
NO_PROGRESS = re.compile(r"no progress|no (?:new )?output|nothing (?:has )?(?:happened|changed|moved)|stalled|stuck|not responding|"
                         r"no response|has(?:n.t| not) (?:moved|changed|answered|responded)|no sign of", re.I)
END_WORDS = re.compile(r"\b(done|finished|completed?|failed|stopped|cancell?ed|timed out|couldn.t|could not|error)\b", re.I)
RUNNING_JS = r"""
() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 &&
          getComputedStyle(e).visibility !== 'hidden'; };
  const els = [...document.querySelectorAll('[class*=status],[class*=progress],[class*=busy],[class*=running],[aria-busy=true],[role=progressbar]')]
     .filter(vis).map(e => (e.innerText || '').trim()).filter(Boolean);
  const btns = [...document.querySelectorAll('button')].filter(vis).map(b => (b.innerText || '').trim()).filter(t => /…$|\.\.\.$/.test(t));
  return {t: Date.now() / 1000, running: [...els, ...btns], body: document.body.innerText.slice(0, 100000)}; }
"""


def _compliant(texts: list[str]) -> bool:
    for t in texts:
        first = t.split("\n")[0]
        phase = re.sub(ELAPSED, "", first).strip(" ·-:")
        if phase and not PHASE_GENERIC.match(phase) and ELAPSED.search(t) and STEP_OR_RANGE.search(t):
            return True
    return False


def _observe(P, start, ended, max_s: float, every: float = 1.5) -> list[dict]:
    t0 = time.time()
    start()
    out = []
    while time.time() - t0 < max_s:
        s = P.eval(RUNNING_JS)
        s["dt"] = round(s.pop("t") - t0, 1)
        body = s.pop("body")
        s["ended"] = bool(ended(body, s))
        s["no_progress_words"] = bool(NO_PROGRESS.search(body))
        out.append(s)
        if s["ended"] and not s["running"]:
            break
        P.page.wait_for_timeout(int(every * 1000))
    return out


def _judge(op: str, snaps: list[dict], silence: tuple | None) -> list[str]:
    v = []
    first_run = next((s["dt"] for s in snaps if s["running"]), None)
    if first_run is None or first_run > 2.0:
        v.append(f"{op}: no visible running state within 2 s (first at {first_run})")
    last_ok, gaps = 0.0, 0
    end_t = next((s["dt"] for s in snaps if s["ended"] and not s["running"]), snaps[-1]["dt"] if snaps else 0)
    for s in snaps:
        if s["dt"] > end_t:
            break
        if _compliant(s["running"]):
            last_ok = s["dt"]
        elif s["dt"] - last_ok > 10:
            gaps += 1
            last_ok = s["dt"]           # count each further 10 s without a compliant update once
    if gaps:
        v.append(f"{op}: {gaps} gap(s) > 10 s without phase + elapsed + step k/n or expected range")
    if silence:
        a, b = silence
        said = any(s["no_progress_words"] for s in snaps if a + 60 <= s["dt"] <= b + 5)
        if not said:
            v.append(f"{op}: backend silent {b - a:.0f} s, the page never said 'no progress' after 60 s")
    if not any(s["ended"] for s in snaps):
        v.append(f"{op}: no end message within the observation window")
    return v


@metric(id="P0-2", title="Nothing waits silently: running state in 2 s, updates every 10 s, 'no progress' after 60 s, end message that stays",
        root="P0", p0=("P0-2",), level="B", kind="behaviour")
def p0_2(ctx):
    viol, rec = [], {}
    # (1) an agent turn: two tool steps, then the engine goes silent for 75 s (stall canary at a random point), then answers
    srv = common.private(ctx, "P0-2-agent", fresh=True)
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        lead = ctx.rng.uniform(2.0, 8.0)
        answer = f"Answer {ctx.rng.randrange(10**6)} is ready."
        common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "bom.json"}, "delay": lead / 2},
                                          {"tool": "Grep", "input": {"pattern": "VDD"}, "delay": lead / 2},
                                          {"sleep": 75}, {"text": "writing", "delay": 0.5}], "final": answer}, name="P0-2 stall")
        with Page(srv.url, srv.project) as P:
            P.open()
            box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first

            def start():
                box.fill("Which supply pins have no decoupling cap?")
                box.press("Enter")
            snaps = _observe(P, start, lambda body, s: answer in body, max_s=150)
            viol += _judge("agent turn", snaps, (lead + 1, lead + 76))
            P.reload()
            kept_reload = answer in P.text()
            srv.restart()
            P.reload()
            kept_restart = answer in P.text()
            if not (kept_reload and kept_restart):
                viol.append(f"agent turn: end message kept after reload={kept_reload}, after server restart={kept_restart}")
            rec["agent"] = snaps
    finally:
        srv.stop()
    # (2) JLC/LCSC stock check while the network hangs (a blackhole proxy: the backend makes no progress)
    hole = faults.blackhole_proxy()
    srv = common.private(ctx, "P0-2-stock", env=faults.proxy_env(hole.port), fresh=True)
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        with Page(srv.url, srv.project) as P:
            P.open("bom")
            btn = P.page.get_by_role("button", name=re.compile(r"check stock", re.I)).first
            snaps = _observe(P, btn.click, lambda body, s: bool(END_WORDS.search(body)) and not s["running"], max_s=110)
            end_text = None
            viol += _judge("stock check", snaps, (0.5, 105))
            P.reload()
            rec["stock"] = snaps
            rec["stock_after_reload"] = P.text()[:2000]
            if not any(s["ended"] for s in snaps) or not END_WORDS.search(P.text()):
                viol.append("stock check: no end message after a page reload")
    finally:
        srv.stop()
        hole.close()
    ev = [common.save(ctx, "P0-2-timeline", rec)]
    return Result("pass" if not viol else "fail", measured=len(viol),
                  expected="gaps > 10 s = 0, ops without a kept end message = 0, stalls not reported after 60 s = 0, running state within 2 s",
                  detail="; ".join(viol)[:3000], evidence=ev)


# ------------------------------------------------------------------ P0-1
def _logs_naming(project_dir, token: str, since: float) -> list[str]:
    hits = []
    for f in project_dir.rglob("*"):
        rel = f.relative_to(project_dir).as_posix() if f.is_file() else ""
        is_log = f.suffix in (".jsonl", ".log") or rel.startswith(("chats/", "logs/"))     # the project's logs, not its item stores
        if f.is_file() and is_log and f.stat().st_mtime >= since - 1:
            try:
                if token in f.read_text(encoding="utf-8", errors="replace"):
                    hits.append(str(f.relative_to(project_dir)))
            except OSError:
                pass
    return hits


@metric(id="P0-1", title="Nothing disappears silently: every skipped, reverted or not-applied item has a visible event and a log entry naming it",
        root="P0", p0=("P0-1",), level="B", kind="behaviour")
def p0_1(ctx):
    unmatched, rec = [], []
    srv = common.private(ctx, "P0-1", fresh=True)
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        pdir = srv.projects / srv.project
        # canary (a): a stored rule of a kind the .RUL writer cannot write (random name and kind), then Download .RUL
        tok = "R" + "".join(ctx.rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))
        rules = json.loads((pdir / "rules.json").read_text(encoding="utf-8")) if (pdir / "rules.json").is_file() else []
        rules.append({"name": tok, "kind": "Kind" + tok[1:], "scope1": "All", "scope2": "All", "values": {"gap": "10mil"}})
        (pdir / "rules.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
        srv.restart()
        t0 = time.time()
        import urllib.request
        with urllib.request.urlopen(f"{srv.url}/api/rules/export?project={srv.project}") as r:
            rul = r.read().decode("utf-8", "replace")
        in_rul = tok in rul
        with Page(srv.url, srv.project) as P:
            P.open("rules")
            P.reload()
            txt = P.text()
        row = re.search(re.escape(tok) + r".{0,200}", txt, re.S)
        visible = bool(row and re.search(r"skip|not (?:written|exported|in the)|cannot|unsupported|left out", row.group(0), re.I))
        logs = _logs_naming(pdir, tok, t0)
        rec.append({"canary": "rule the .RUL cannot hold", "item": tok, "in_rul": in_rul, "row": row.group(0)[:200] if row else None,
                    "visible": visible, "logs": logs})
        if not in_rul and not (visible and logs):
            unmatched.append(f"rule {tok} left out of the .RUL: visible={visible}, log={bool(logs)}")
        # canary (b): the student asks the agent to drop a random requirement; the agent's action is not applied
        idea = json.loads((pdir / "idea.json").read_text(encoding="utf-8"))
        topic = ctx.rng.choice([a["topic"] for a in idea.get("agreed", []) if a.get("topic")])
        common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "idea.json"}, "delay": 0.5}],
                                "final": f"I removed the requirement \"{topic}\" as you asked." +
                                common.actions_block([{"type": "idea.remove", "topic": topic, "reason": "the student asked"}])},
                          name="P0-1 drop")
        t0 = time.time()
        with Page(srv.url, srv.project) as P:
            P.open("idea")
            box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first
            box.fill(f"Please drop the requirement {topic}.")
            box.press("Enter")
            P.page.wait_for_timeout(8000)
            P.reload()
            txt = P.text()
        idea2 = json.loads((pdir / "idea.json").read_text(encoding="utf-8"))
        still = any(a.get("topic") == topic for a in idea2.get("agreed", []))
        # the event must name the item and say it was not applied, on the page where the item lives (Idea) + a log entry
        named = [m.group(0) for m in re.finditer(r"[^\n]*" + re.escape(topic) + r"[^\n]*", txt)
                 if re.search(r"not (?:applied|removed|done|run)|refused|couldn.t|could not|kept|unchanged|was not", m.group(0), re.I)]
        logs = [f for f in _logs_naming(pdir, topic, t0) if f.endswith(".jsonl")]
        rec.append({"canary": "agent drop of a requirement", "item": topic, "still_there": still, "named_events": named[:3], "logs": logs})
        if still and not (named and logs):
            unmatched.append(f"requirement '{topic}': the drop was not applied and no event names it")
        elif not still and not (named or logs):
            unmatched.append(f"requirement '{topic}' removed with no event naming it")
        # canary (c): a file under the install written by another process during an agent turn (random name)
        ftok = "acc-p01-" + "".join(ctx.rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))
        target = srv.wt / "shared" / f"{ftok}.md"
        common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "x"}, "delay": 0.5}, {"sleep": 4}],
                                "final": "Done looking."}, name="P0-1 guard")
        t0 = time.time()
        with Page(srv.url, srv.project) as P:
            P.open()
            box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first
            box.fill("What is still open?")
            box.press("Enter")
            tt = time.time()
            while not faults.engine_pids(srv) and time.time() - tt < 15:
                time.sleep(0.2)
            faults.foreign_write(target, "written by another process\n")
            P.page.wait_for_timeout(9000)
            P.reload()
            txt = P.text()
        gone = not target.exists()
        named = ftok in txt
        logs = _logs_naming(pdir, ftok, t0)
        rec.append({"canary": "foreign file during a turn", "item": ftok, "removed": gone, "visible": named, "logs": logs})
        if gone and not (named and logs):
            unmatched.append(f"file {ftok} removed: visible={named}, log={bool(logs)}")
        try:
            target.unlink()
        except OSError:
            pass
    finally:
        srv.stop()
    ev = [common.save(ctx, "P0-1-canaries", rec)]
    return Result("pass" if not unmatched else "fail", measured=len(unmatched),
                  expected="removed / skipped / not-applied canary items without a visible event AND a project-log entry naming them = 0",
                  detail="; ".join(unmatched), evidence=ev)


# ------------------------------------------------------------------ P0-3
CLAIM = re.compile(r"\b(?:now has|is now|are now|updated|fixed|done|added|removed|replaced|checked|verified|passes|no issues|"
                   r"all (?:good|fine|set)|fine as-is|is fine|matches|met)\b", re.I)
POSITIVE_TEXT = re.compile(r"^(?:checked|verified|built|current|done|ok|passes?|no issues|matches.*|every .* matches.*)$", re.I)
GREEN_JS = r"""
() => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return [...document.querySelectorAll('main *')].filter(e => vis(e) && e.children.length <= 2).filter(e => {
     const toks = String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className || '').split(/\s+/);
     return toks.some(t => /^(ok|good|pass|success)$/.test(t)); })
   .map(e => ({text: (e.innerText || e.getAttribute('aria-label') || e.getAttribute('title') || '').trim().slice(0, 120),
               label: (e.getAttribute('aria-label') || e.getAttribute('title') || '').slice(0, 120),
               evidence: e.closest('[data-evidence]') ? e.closest('[data-evidence]').getAttribute('data-evidence') : null})); }
"""


def _evidence_holds(ev: str | None, root) -> bool:
    """An A10 record: {path, sha256, in_scope, examined, failed}; holds when the file's sha256 is the file on disk now and
    examined = in scope with 0 failed."""
    if not ev:
        return False
    try:
        d = json.loads(ev)
        p = root / d["path"]
        import hashlib
        return (p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == d["sha256"]
                and d["examined"] == d["in_scope"] and d["failed"] == 0)
    except Exception:
        return False


@metric(id="P0-3", title="Nothing is called OK unless checked on this file completely: every green and every success claim has a holding evidence record",
        root="P0", p0=("P0-3",), level="B", kind="behaviour")
def p0_3(ctx):
    run = common.Run(ctx)
    unbacked, rec = [], {}
    with Page(run.url, run.project) as P:
        P.open()
        for st in ("idea", "bom", "sch", "pcb", "rules", "outputs", "checks"):
            P.stage(st)
            g = P.eval(GREEN_JS)
            rec[st] = g
            for x in g:
                if x["text"] or x["label"]:
                    if not _evidence_holds(x["evidence"], run.project_dir):
                        unbacked.append(f"{st}: green '{(x['text'] or x['label'])[:50]}'")
    # agent final messages with a success claim and no linked evidence record
    claims = []
    for r in common.chat_rows(run.project_dir):
        if r.get("role") != "agent":
            continue
        for sent in re.split(r"(?<=[.!])\s+", str(r.get("text", ""))):
            if CLAIM.search(sent) and not (r.get("evidence") or r.get("claims_evidence")):
                claims.append({"ts": r.get("ts"), "claim": sent[:140]})
    # staleness canary on a private copy: change a random BOM line's quantity after the outputs were made; every green
    # 'Current' on Outputs must turn away from green within one refresh
    srv = common.private(ctx, "P0-3", fresh=True)
    stale = []
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        pdir = srv.projects / srv.project
        with Page(srv.url, srv.project) as P:
            P.open("outputs")
            before = [x["text"] for x in P.eval(GREEN_JS)]
            bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
            ln = ctx.rng.choice(bom)
            ln["qty"] = int(ln.get("qty") or 1) + 1 + ctx.rng.randrange(3)
            (pdir / "bom.json").write_text(json.dumps(bom, indent=1), encoding="utf-8")
            P.reload()
            P.stage("outputs")
            after = [x["text"] for x in P.eval(GREEN_JS)]
        still = [t for t in after if t and t in before and re.search(r"current|checked|ok|verified", t, re.I)]
        if still:
            stale.append({"changed line": ln.get("key"), "still green": still})
    finally:
        srv.stop()
    n = len(unbacked) + len(claims) + len(stale)
    ev = [common.save(ctx, "P0-3-scan", {"green": rec, "claims": claims, "stale": stale})]
    for f in sorted((run.project_dir / "chats").glob("*.jsonl")):
        ev.append(ctx.ev(f, "chat record"))
    return Result("pass" if n == 0 else "fail", measured=n,
                  expected="green statuses without a holding A10 record + agent success claims without evidence + green kept after a staleness canary = 0",
                  detail=f"unbacked green {len(unbacked)} (e.g. {unbacked[:4]}); unbacked claims {len(claims)} (e.g. {[c['claim'] for c in claims[:2]]}); stale canary {stale}",
                  evidence=ev)
