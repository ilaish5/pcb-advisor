"""Part C themes (T-A .. T-J) and F-B / F-G, the behaviour parts that need no Altium. The confusion counts of Part C are an
A12 rerun quantity (an oracle judge over a full rerun); what is measured here is each theme's stated behaviour on a live server.
"""
from __future__ import annotations

import json
import re
import time

import thresholds as TH
from lib import Result, metric
from live import common, corpora, faults, pins, seed
from live.driver import Page

# ------------------------------------------------------------------ T-A


@metric(id="T-A", title="Running state survives a reload and a server restart mid-operation, with phase and progress from the work",
        root="R1", p0=("P0-2",), level="B", kind="behaviour")
def ta(ctx):
    srv = common.private(ctx, "T-A", fresh=True)
    trials = []
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        with Page(srv.url, srv.project) as P:
            P.open()
            for k in range(4):                    # 3 reloads and 1 server restart, each at a random moment of a 40 s turn
                restart = k == 3
                common.queue_turn(srv, {"steps": [{"tool": "Read", "input": {"file_path": "bom.json"}, "delay": 0.5},
                                                  {"tool": "Grep", "input": {"pattern": "VDD"}, "delay": 1.0}, {"sleep": 40}],
                                        "final": f"Turn {k} done."}, name=f"T-A {k}")
                box = P.page.get_by_placeholder(re.compile(r"ask", re.I)).first
                box.fill(f"Check the supply pins, round {k}")
                box.press("Enter")
                P.page.wait_for_timeout(int(ctx.rng.uniform(4, 12) * 1000))
                if restart:
                    srv.restart()
                P.reload(wait_ms=2000)
                s = P.eval("""() => [...document.querySelectorAll('[class*=status],[class*=progress],[aria-busy=true]')]
                     .filter(e => e.getBoundingClientRect().height > 0).map(e => e.innerText.trim()).filter(Boolean)""")
                shows = [t for t in s if not re.match(r"^\s*(working|thinking)\W*$", t, re.I)]
                trials.append({"trial": k, "restart": restart, "running_after_reload": s, "ok": bool(shows)})
                for _ in range(60):               # let the turn end before the next trial
                    if f"Turn {k} done." in P.text() or not faults.engine_pids(srv):
                        break
                    P.page.wait_for_timeout(1000)
                P.page.wait_for_timeout(1500)
    finally:
        srv.stop()
    lost = [t for t in trials if not t["ok"]]
    return Result("pass" if not lost else "fail", measured=len(lost),
                  expected="trials (3 reloads + 1 server restart, random moments) after which the page shows no running state with its phase = 0",
                  detail=json.dumps(trials)[:1500], evidence=[common.save(ctx, "T-A-trials", trials)])


# ------------------------------------------------------------------ T-B / F-B
def _num(rx: str, text: str):
    m = re.search(rx, text, re.I | re.M)
    return int(m.group(1)) if m else None


def _fields(pdir):
    """The frozen field list (tb_fields corpus) resolved against the project's files: {id: (artifact value, page, DOM regex)}."""
    bom = json.loads((pdir / "bom.json").read_text(encoding="utf-8"))
    idea = json.loads((pdir / "idea.json").read_text(encoding="utf-8")) if (pdir / "idea.json").is_file() else {}
    proj = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    rules = json.loads((pdir / "rules.json").read_text(encoding="utf-8")) if (pdir / "rules.json").is_file() else []
    parts = sum(int(ln.get("qty") or len(ln.get("refs") or [])) for ln in bom if not ln.get("dnp"))
    statuses = [pins.oracle_status(ln, pdir)[0] for ln in bom]
    sheets = sorted((pdir / "netlist").glob("*.json"))
    nets = set()
    for s in sheets:
        for p in json.loads(s.read_text(encoding="utf-8")).get("parts", []):
            nets |= {pn.get("net") for pn in p.get("pins", []) if pn.get("net")}
    exports = [f for f in (pdir / "exports").glob("*") if f.is_file()] if (pdir / "exports").is_dir() else []
    srcs = [f for f in (pdir / "sources").glob("*") if f.suffix.lower() in (".pdf", ".html", ".htm")] if (pdir / "sources").is_dir() else []
    out = {
        "bom.lines": (len(bom), "bom", r"^\s*(\d+)\s+lines?\b"),
        "bom.parts": (parts, "bom", r"^\s*(\d+)\s+parts?\b"),
        "bom.unverified": (statuses.count("not_checked"), "checks", r"unverified parts \((\d+)\)"),
        "bom.accepted_risks": (sum(isinstance(ln.get("pin_decision"), dict) and ln["pin_decision"].get("basis") != "datasheet_page"
                                   for ln in bom), "outputs", r"accepted risks \((\d+)\)"),     # a page check by the student is not a risk
        "board.layers": (int((proj.get("board") or {}).get("layers") or 0), "pcb", r"(\d+)\s+copper layers?"),
        "idea.requirements": (len(idea.get("agreed") or []), "idea", r"(\d+)\s+(?:requirements?|agreed)"),
        "rules.extra": (len(rules) if isinstance(rules, list) else len(rules.get("extra", [])), "rules", r"extra rules \((\d+)\)"),
        "sch.sheets": (len(sheets), "sch", r"^\s*(\d+)\s+sheets?\b"),
        "sch.nets": (len(nets), "sch", r"(\d+)\s+nets?\b"),
        "outputs.files": (len(exports), "outputs", r"^\s*(\d+)\s+files?\b"),
        "sources.documents": (len(srcs), "sources", r"(\d+)\s+(?:documents?|sources?|files?)\b"),
    }
    for ln in bom:
        out[f"bom.qty[{ln['key']}]"] = (int(ln.get("qty") or len(ln.get("refs") or [])), "bom-row:" + ln["key"], r"")
    return out


def _dom_value(P, page: str, rx: str):
    if page.startswith("bom-row:"):
        key = page.split(":", 1)[1]
        P.stage("bom", wait_ms=1500)
        cells = P.eval("k => { const tr = document.querySelector(`tr[data-key=\"${CSS.escape(k)}\"]`); "
                       "return tr ? [...tr.querySelectorAll('td')].map(t => t.innerText.trim()) : null; }", key)
        if not cells:
            return None
        nums = [c for c in cells if re.fullmatch(r"\d+", c)]
        return int(nums[0]) if nums else None
    if page == "sources":
        P.eval("go('sources')")
        P.page.wait_for_timeout(1500)
    else:
        P.stage(page, wait_ms=1500)
    main = P.eval("() => (document.querySelector('main') || document.body).innerText")
    return _num(rx, main)


def _tb(ctx, tag: str):
    run = common.Run(ctx)
    spec = corpora.header("tb_fields")
    fields = _fields(run.project_dir)
    ids = [f for f in fields if not f.startswith("bom.qty[")]
    pool = ids + ctx.rng.sample([f for f in fields if f.startswith("bom.qty[")], 3)
    draw = ctx.rng.sample(pool, min(spec["draw"], len(pool)))
    rows = []
    with Page(run.url, run.project) as P:
        P.open()
        for fid in draw:
            want, page, rx = fields[fid]
            got = _dom_value(P, page, rx)
            rows.append({"field": fid, "artifact": want, "dom": got, "equal": got == want})
    bad = [r for r in rows if not r["equal"]]
    not_here = [f["id"] for f in spec["fields"] if not f.get("computable_here")]
    return rows, bad, not_here, run


@metric(id="T-B", title="Page and files agree: N random fields from the frozen list, DOM value = artifact value (missing = mismatch)",
        root="R1", p0=("P0-3",), level="B", kind="behaviour")
def tb(ctx):
    rows, bad, not_here, run = _tb(ctx, "T-B")
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected=f"fields where DOM != artifact (a field not shown counts) = 0 of {len(rows)} drawn",
                  detail=f"mismatches: {bad[:8]}; agent leg (scripted question) and {len(not_here)} board/Gerber fields are the local/E phase",
                  evidence=[common.save(ctx, "T-B-fields", rows), ctx.ev(corpora.VISIBLE / "tb_fields.json", "T-B field list")])


@metric(id="F-B", title="Page, chat and numbers agree (T-B fields) and every on-page count equals the list it summarises",
        root="R1", p0=("P0-3",), level="B", kind="behaviour")
def fb(ctx):
    rows, bad, _, run = _tb(ctx, "F-B")
    # every on-page count is the length of a list the page can show: BOM 'N lines' vs rows, Unverified (N) vs items
    with Page(run.url, run.project) as P:
        P.open("bom")
        n_lines = _num(r"^\s*(\d+)\s+lines?\b", P.text())
        rows_shown = P.eval("() => document.querySelectorAll('tr[data-key]').length")
        P.stage("checks")
        txt = P.text()
        n_unv = _num(r"unverified parts \((\d+)\)", txt)
        listed = len(re.findall(r"^(?:Confirm pins)$", txt, re.M))
    counts = [{"count": "BOM lines", "shown": n_lines, "list": rows_shown},
              {"count": "Unverified parts", "shown": n_unv, "list": listed}]
    cbad = [c for c in counts if c["shown"] != c["list"]]
    n = len(bad) + len(cbad)
    return Result("pass" if n == 0 else "fail", measured=n,
                  expected="field mismatches + counts that differ from the list they summarise = 0",
                  detail=f"field mismatches {bad[:6]}; count/list mismatches {cbad}",
                  evidence=[common.save(ctx, "F-B", {"fields": rows, "counts": counts})])


# ------------------------------------------------------------------ T-C
@metric(id="T-C", title="No green over unverified, partial or stale state anywhere (oracle status per item; staleness canary)",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def tc(ctx):
    run = common.Run(ctx)
    bom = json.loads((run.project_dir / "bom.json").read_text(encoding="utf-8"))
    bad = []
    with Page(run.url, run.project) as P:
        P.open("bom")
        chips = P.eval("""() => [...document.querySelectorAll('tr[data-key]')].map(tr => {
            const c = [...tr.querySelectorAll('[aria-label],[title]')].find(e => /^\\s*pins\\b/i.test(e.getAttribute('aria-label') || ''));
            return {key: tr.getAttribute('data-key'), ok: !!c && /(^|\\s)(ok|good|pass)(\\s|$)/.test(String(c.className))}; })""")
        P.stage("checks")
        dfm = P.text()
    for c in chips:
        ln = next((x for x in bom if x["key"] == c["key"]), None)
        if ln and c["ok"] and pins.oracle_status(ln, run.project_dir)[0] == "not_checked":
            bad.append(f"BOM pins chip green on {c['key']} (oracle: not checked)")
    # 'Checked by you' entries: a student check against a page needs its evidence to still match the file (stale otherwise)
    for ln in bom:
        dec = ln.get("pin_decision")
        if isinstance(dec, dict) and dec.get("basis") == "datasheet_page" and ln["key"] in dfm:
            ok, why = pins.evidence_ok({**ln, "pins_evidence": (dec.get("evidence") or [None])[0] if isinstance(dec.get("evidence"), list) else dec.get("evidence")}, run.project_dir)
            if not ok:
                bad.append(f"'Checked by you' on {ln['key']}: {why}")
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected="green / 'checked' over items the oracle finds not checked, partial or stale = 0",
                  detail="; ".join(bad[:12]), evidence=[ctx.ev(run.project_dir / "bom.json", "BOM"), common.save(ctx, "T-C", {"chips": chips, "bad": bad})])


# ------------------------------------------------------------------ T-D
HAND_STEP = re.compile(r"\bin Altium\b[^.]{0,80}\b(?:move|set|change|edit|tent|fix|delete|add|run|open|drag|disable)|"
                       r"\b(?:by hand|manually|yourself)\b", re.I)


@metric(id="T-D", title="Every hand-step advice is a tracked ledger item (open / fixed / accepted with reason)",
        root="R5", level="B", kind="behaviour")
def td(ctx):
    run = common.Run(ctx)
    advice = [r for r in common.chat_rows(run.project_dir) if r.get("role") == "agent" and HAND_STEP.search(str(r.get("text", "")))]
    ledgers = {}
    for path in ("/api/ledger", "/api/findings", "/api/keeping/decisions"):
        st, body = run.get(path)
        if st == 200 and isinstance(body, (dict, list)):
            ledgers[path] = body
    items = []
    for body in ledgers.values():
        for it in (body if isinstance(body, list) else body.get("items") or body.get("decisions") or []):
            if isinstance(it, dict) and it.get("state") in ("open", "fixed", "accepted", "closed"):
                items.append(json.dumps(it, ensure_ascii=False))
    missing = []
    for r in advice:
        refs = set(re.findall(r"\b[A-Z]{1,3}\d{1,3}\b", str(r.get("text", ""))))
        if not any(any(ref in it for ref in refs) for it in items):
            missing.append({"ts": r.get("ts"), "advice": re.search(HAND_STEP, r["text"]).group(0)})
    return Result("pass" if not missing else "fail", measured=len(missing),
                  expected="hand-step advice in the chat with no ledger item (state open/fixed/accepted) naming its objects = 0",
                  detail=f"ledger endpoints answering: {list(ledgers) or 'none'}; e.g. {missing[:3]}",
                  evidence=[common.save(ctx, "T-D", {"missing": missing, "ledger_items": len(items)})] +
                  [ctx.ev(f, "chat record") for f in sorted((run.project_dir / "chats").glob("*.jsonl"))])


# ------------------------------------------------------------------ T-E
LEAKS = [r"bom\.propose", r"student_said", r"chat\.ask", r"p20\d{12,}", r"\w+\.py\b", r"checks/"]     # ACCEPTANCE T-E, frozen


@metric(id="T-E", title="Chat format: no internal identifiers, no tables wider than the column, each message <= 10 lines",
        root="R5", level="B", kind="behaviour")
def te(ctx):
    run = common.Run(ctx)
    max_lines = TH.CHAT_MAX_LINES["value"]
    with Page(run.url, run.project) as P:
        P.open()
        msgs = P.eval("""() => { const col = document.querySelector('[class*=chat]'); const cw = col ? col.getBoundingClientRect().width : innerWidth;
            return [...document.querySelectorAll('[class*=msg]')].filter(m => /\\bagent\\b/.test(m.className)).map(m => {
              const t = m.querySelector('[class*=txt]') || m; const cs = getComputedStyle(t);
              const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
              return {text: t.innerText, lines: Math.round(t.getBoundingClientRect().height / lh),
                      wide_tables: [...t.querySelectorAll('table')].filter(tb => tb.scrollWidth > t.clientWidth + 1 || tb.getBoundingClientRect().width > cw).length}; }); }""")
    leaks = [{"leak": m.group(0), "in": x["text"][:80]} for x in msgs for rx in LEAKS for m in [re.search(rx, x["text"])] if m]
    wide = sum(x["wide_tables"] for x in msgs)
    long = sum(1 for x in msgs if x["lines"] > max_lines)
    n = len(leaks) + wide + long
    return Result("pass" if n == 0 else "fail", measured={"leaks": len(leaks), "wide_tables": wide, f"messages_over_{max_lines}_lines": long},
                  expected=f"internal identifiers 0, tables wider than the chat column 0, agent messages over {max_lines} rendered lines 0 (OD-6)",
                  detail=f"of {len(msgs)} agent messages; leaks e.g. {leaks[:4]}", evidence=[common.save(ctx, "T-E", {"msgs": msgs, "leaks": leaks})])


# ------------------------------------------------------------------ T-F
@metric(id="T-F", title="Repeat consistency (10 probe questions asked twice agree) and no ledger decision contradicted",
        root="R1", level="E", kind="behaviour")
def tf(ctx):
    import os
    from lib import not_run
    if os.environ.get("ACCEPTANCE_REAL_ENGINE") != "1":
        return not_run("needs a real agent engine answering 10 questions drawn from corpora/probe_questions.json twice "
                       "(ACCEPTANCE_REAL_ENGINE=1, local/E phase) and a product ledger to compare against: the oracle's fake "
                       "engine would only repeat its own script", expected="10/10 consistent; 0 contradictions")
    return not_run("real-engine run not implemented in the cloud phase")


# ------------------------------------------------------------------ T-G
CONTRAST_JS = r"""
() => { const lum = c => { const v = c.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const rgb = s => (s.match(/[\d.]+/g) || []).map(Number);
  const bg = el => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor);
                       if (c.length >= 3 && (c.length < 4 || c[3] > 0.5)) return c.slice(0, 3); } return [255, 255, 255]; };
  const out = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (w.nextNode()) { const n = w.currentNode, el = n.parentElement; if (!el || seen.has(el) || !n.textContent.trim()) continue;
    seen.add(el); const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === 'hidden' || el.closest('svg,[aria-hidden=true]')) continue;
    const f = rgb(cs.color).slice(0, 3), b = bg(el); const L1 = lum(f), L2 = lum(b);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const big = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.66 && parseInt(cs.fontWeight) >= 700);
    if (ratio < (big ? 3 : 4.5) && !el.closest('button[disabled],[aria-disabled=true]')) out.push({text: n.textContent.trim().slice(0, 40), ratio: Math.round(ratio * 100) / 100}); }
  return out; }
"""


@metric(id="T-G", title="Previews can be judged: text contrast >= 4.5:1 (WCAG 1.4.3), net select by name on the schematic, zoom >= 400%",
        root="R2", level="B", kind="behaviour")
def tg(ctx):
    run = common.Run(ctx)
    low, info = [], {}
    with Page(run.url, run.project) as P:
        P.open()
        for st in ("bom", "sch", "pcb", "outputs"):
            P.stage(st)
            low += [dict(x, page=st) for x in P.eval(CONTRAST_JS)]
        P.stage("sch")
        net_box = P.eval("""() => [...document.querySelectorAll('input')].filter(i => i.getBoundingClientRect().height > 0)
            .map(i => (i.placeholder || i.getAttribute('aria-label') || '')).filter(t => /\\bnet\\b/i.test(t))""")
        zoom_ctl = P.eval("""() => [...document.querySelectorAll('button,[role=slider],select')].filter(b => b.getBoundingClientRect().height > 0)
            .map(b => (b.innerText || b.title || b.getAttribute('aria-label') || '').trim()).filter(t => /zoom|\\d+\\s*%|fit/i.test(t))""")
        info = {"net_inputs": net_box, "zoom_controls": zoom_ctl}
    v = len(low) + (0 if net_box else 1)
    return Result("pass" if v == 0 else "fail", measured={"low_contrast_texts": len(low), "net_select_by_name": bool(net_box)},
                  expected="text below 4.5:1 (3:1 for large text) = 0, and a net can be selected by name on the schematic preview",
                  detail=f"low contrast e.g. {low[:5]}; {info}; footprint geometry vs PcbLib (W15/W17 readers) and the 400% zoom "
                         "measurement are the local phase", evidence=[common.save(ctx, "T-G", {"low": low, **info})])


# ------------------------------------------------------------------ T-H / F-G
def _th(ctx):
    viol, rec = [], {}
    srv = common.private(ctx, "T-H", fresh=True)
    try:
        n = ctx.rng.randrange(10, 61)
        for i in range(n):
            seed.seed_synthetic(srv.projects, f"proj-{i:02d}-{ctx.rng.randrange(1000)}", {})
        linked = seed.seed_fixture(srv.projects, root=ctx.root)
        unlinked = "empty-first-use"
        seed.seed_synthetic(srv.projects, unlinked, {})
        srv.project = unlinked
        srv.start()
        with Page(srv.url, unlinked) as P:
            P.open()
            vis = P.eval("""() => { const vh = innerHeight; return [...document.querySelectorAll('button,a,[role=menuitem]')].filter(b =>
                /new project/i.test(b.innerText || '') && b.getBoundingClientRect().height > 0 && b.getBoundingClientRect().bottom <= vh).length; }""")
            one_click = vis > 0
            if not one_click:
                P.page.locator("[data-act=projects], .proj-btn, [aria-haspopup=true]").first.click()
                P.page.wait_for_timeout(800)
                one_click = P.eval("""() => { const vh = innerHeight; return [...document.querySelectorAll('button,a,[role=menuitem]')].some(b =>
                    /new project/i.test(b.innerText || '') && b.getBoundingClientRect().height > 0 && b.getBoundingClientRect().bottom <= vh); }""")
            rec["projects"] = n
            rec["new_project_visible_1_click"] = one_click
            if not one_click:
                viol.append(f"'New project' not visible within one click without scrolling ({n} projects)")
            # New project asks for the layer count
            P.page.evaluate("document.querySelector('[data-act=newproj]') && document.querySelector('[data-act=newproj]').click()")
            P.page.wait_for_timeout(800)
            dlg = P.eval("() => { const d = document.querySelector('dialog[open],[role=dialog]'); return d ? d.innerText : ''; }")
            rec["new_project_dialog"] = dlg
            if not re.search(r"layer", dlg, re.I):
                viol.append("New project does not ask for the layer count")
            P.page.keyboard.press("Escape")
            # the empty project's pages: exactly one runnable first step; enabled controls that are refused = 0
            for st in ("idea", "bom", "sch", "pcb", "rules", "outputs", "checks"):
                P.stage(st)
                pri = P.eval("""() => [...document.querySelectorAll('main button')].filter(b => !b.disabled && b.getBoundingClientRect().height > 0
                    && /(^|\\s)(pri|primary)(\\s|$)/.test(b.className)).map(b => b.innerText.trim())""")
                rec[f"{st}.primary"] = pri
                if len(pri) != 1:
                    viol.append(f"empty {st} page shows {len(pri)} runnable first steps (want exactly 1)")
                labels = P.eval("""() => [...document.querySelectorAll('main button')].filter(b => !b.disabled && b.getBoundingClientRect().height > 0)
                    .map(b => b.innerText.trim()).filter(t => t && t.length < 40)""")
                for lab in labels:
                    if re.search(r"delete|remove|archive|revoke|dismiss|close|collapse|export|download", lab, re.I):
                        continue
                    before = len(P.api)
                    try:
                        P.page.get_by_role("button", name=lab, exact=True).first.click(timeout=2000)
                    except Exception:
                        continue
                    P.page.wait_for_timeout(1200)
                    refused = [a for a in P.api[before:] if a["method"] == "POST" and a["status"] >= 400]
                    toast = P.eval("() => { const t = document.querySelector('.toast.bad'); return t && !t.hidden ? t.innerText : ''; }")
                    why = toast or (json.dumps(refused[0].get("body")) if refused else "")
                    if (refused or toast) and re.search(r"not Windows|Altium Designer installed|Downloads|does not exist", why, re.I):
                        rec.setdefault("machine_refusals_not_counted", []).append(f"{st}: {lab}: {why[:100]}")
                    elif refused or toast:
                        viol.append(f"empty {st}: enabled '{lab}' is refused ({why[:120]})")
                    P.page.keyboard.press("Escape")
                    P.stage(st, wait_ms=800)
            # "not linked" banner iff the project has no Altium path
            P.stage("sch")                       # the page where 27/11 showed the banner (C29)
            unl_banner = bool(re.search(r"not linked", P.text(), re.I))
            P.project = linked
            P.open("sch")
            lnk_banner = bool(re.search(r"not linked", P.text(), re.I))
            rec["banner"] = {"unlinked": unl_banner, "linked": lnk_banner}
            if not unl_banner or lnk_banner:
                viol.append(f"'not linked' banner: unlinked project {unl_banner}, linked project {lnk_banner}")
    finally:
        srv.stop()
    return viol, rec


@metric(id="T-H", title="Start-up and first use: New project in one click, layer count asked, one first step per empty page, no refused enabled control",
        root="R5", level="B", kind="behaviour")
def th(ctx):
    viol, rec = _th(ctx)
    return Result("pass" if not viol else "fail", measured=len(viol), expected="T-H behaviour violations (precondition violations included) = 0",
                  detail="; ".join(viol)[:2500], evidence=[common.save(ctx, "T-H", rec)])


@metric(id="F-G", title="Start-up and navigation (measured as Part C T-H)", root="R5", level="B", kind="behaviour")
def fg(ctx):
    viol, rec = _th(ctx)
    return Result("pass" if not viol else "fail", measured=len(viol), expected="T-H violations = 0 (ACCEPTANCE F-G: 'Metric: Part C T-H')",
                  detail="; ".join(viol)[:2500], evidence=[common.save(ctx, "F-G", rec)])


# ------------------------------------------------------------------ T-I
@metric(id="T-I", title="Every badge or count on Rules, Layout and DRC equals the length of the list it opens",
        root="R4", level="B", kind="behaviour")
def ti(ctx):
    run = common.Run(ctx)
    rows = []
    with Page(run.url, run.project) as P:
        P.open()
        for st in ("rules", "pcb"):
            P.stage(st)
            cands = P.eval("""() => [...document.querySelectorAll('main button, main summary, main a')].filter(b => b.getBoundingClientRect().height > 0)
                .map(b => (b.innerText || '').trim()).filter(t => /\\((\\d+)\\)|show all (\\d+)|(\\d+) of (\\d+)|^\\d+ violations?/i.test(t) && t.length < 60)""")
            for lab in cands:
                m = re.search(r"\((\d+)\)|show all (\d+)|(\d+) violations?", lab, re.I)
                if not m:
                    continue
                want = int(next(g for g in m.groups() if g))
                # a summary opens its own <details>: count the item rows inside it (rows with cells, list items)
                inside = P.eval("""t => { const s = [...document.querySelectorAll('main summary')].find(x => x.innerText.trim() === t);
                    if (!s) return null; const d = s.closest('details'); d.open = true;
                    return [...d.querySelectorAll('tr, li')].filter(r => r.querySelector('td') || r.tagName === 'LI').length; }""", lab)
                if inside is not None:
                    P.page.wait_for_timeout(500)
                    rows.append({"page": st, "badge": lab, "count": want, "rows_added": inside})
                    continue
                vis_rows = "() => [...document.querySelectorAll('main tr, main li')].filter(e => e.getBoundingClientRect().height > 0).length"
                before = P.eval(vis_rows)
                try:
                    P.page.get_by_text(lab, exact=True).first.click(timeout=2000)
                except Exception:
                    continue
                P.page.wait_for_timeout(1200)
                after = P.eval(vis_rows)
                rows.append({"page": st, "badge": lab, "count": want, "rows_added": after - before})
        # the Layout nav badge: the DRC count it shows vs the list of violations the page shows
        P.stage("pcb")
        badge = P.eval("() => { const n = document.querySelector('[data-nav=pcb] .hint'); return n ? n.innerText : null; }")
        drc_rows = P.eval("() => document.querySelectorAll('main [class*=drc] li, main [class*=drc] tr').length")
        if badge and badge.isdigit():
            rows.append({"page": "nav", "badge": f"Layout {badge}", "count": int(badge), "rows_added": drc_rows})
    bad = [r for r in rows if r["count"] != r["rows_added"]]
    return Result("pass" if not bad else "fail", measured=len(bad), expected="badges whose number differs from the rows of the list they open = 0",
                  detail=json.dumps(bad)[:1500], evidence=[common.save(ctx, "T-I", rows)])


# ------------------------------------------------------------------ T-J
@metric(id="T-J", title="An order note / README export generated from the files is listed in the Outputs files table",
        root="R1", level="B", kind="behaviour")
def tj(ctx):
    run = common.Run(ctx)
    with Page(run.url, run.project) as P:
        P.open("outputs")
        names = P.eval("""() => [...document.querySelectorAll('main table tr')].map(r => (r.querySelector('td') || {}).innerText || '')
            .map(t => t.trim()).filter(Boolean)""")
    note = [n for n in names if re.search(r"order[ _-]?note|readme", n, re.I)]
    return Result("pass" if note else "fail", measured=len(note), expected="order-note / README exports in the Outputs files table >= 1 (its W35 contradictions = 0 is W35's artifact metric)",
                  detail=f"files listed: {names[:12]}", evidence=[common.save(ctx, "T-J", names)])
