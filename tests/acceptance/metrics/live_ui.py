"""Live (behaviour) metrics on what the pages show: U1, U5, U7, U8, F-I(e), F-I(f).

Each reads the rendered DOM of a real browser on a running server (A2: Playwright, no product import) and compares it with
the project's files (A1). Elements are found by what a student reads (role words in aria-label / title / text), not by a
product class name, except the tone, which is read from the class tokens the page uses for colour (ok / warn / bad) and,
when no token is there, from the computed colour.
"""
from __future__ import annotations

import json
import re

from lib import Result, metric
from live import common, pins
from live.driver import Page

TONE_JS = r"""
(el) => {
  const toks = String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || '').split(/\s+/);
  for (const t of toks) { if (/^(ok|good|pass|green|success)$/.test(t)) return 'ok';
                          if (/^(warn|amber|caution)$/.test(t)) return 'warn';
                          if (/^(bad|err|error|red|fail|danger)$/.test(t)) return 'bad'; }
  const c = getComputedStyle(el).color.match(/\d+/g) || [0,0,0];
  const [r,g,b] = c.map(Number);
  if (g > 100 && g > r * 1.4 && g > b * 1.2) return 'ok';
  return 'neutral';
}
"""

ROW_PINS_JS = """
() => [...document.querySelectorAll('tr[data-key]')].map(tr => {
  const chip = [...tr.querySelectorAll('[aria-label],[title]')].find(e => /^\\s*pins\\b/i.test(e.getAttribute('aria-label') || e.getAttribute('title') || ''));
  return {key: tr.getAttribute('data-key'), label: chip ? (chip.getAttribute('aria-label') || chip.getAttribute('title')) : null,
          cls: chip ? String(chip.className) : null, idx: chip ? [...document.querySelectorAll('*')].indexOf(chip) : -1};
})
"""


def _bom(project_dir):
    return json.loads((project_dir / "bom.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- U1
@metric(id="U1", title="Pins chip is green only where the oracle's W14 status is verified, accepted or not_applicable",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def u1(ctx):
    run = common.Run(ctx)
    lines = _bom(run.project_dir)
    with Page(run.url, run.project) as P:
        P.open("bom")
        rows = P.eval(ROW_PINS_JS)
        tones = {}
        for r in rows:
            if r["idx"] >= 0:
                el = P.page.locator("*").nth(r["idx"])
                tones[r["key"]] = el.evaluate(TONE_JS)
        snap = P.snapshot("bom")
    bad, missing = [], []
    for ln in lines:
        st, why = pins.oracle_status(ln, run.project_dir)
        row = next((r for r in rows if r["key"] == ln.get("key")), None)
        if row is None or row["label"] is None:
            missing.append(ln.get("key"))               # the chip must exist: hiding it fails (anti-gaming)
            continue
        if tones.get(ln["key"]) == "ok" and st not in ("verified", "accepted", "not_applicable"):
            bad.append({"line": ln["key"], "oracle": st, "why": why, "chip": row["label"][:80]})
    n = len(bad) + len(missing)
    ev = [ctx.ev(run.project_dir / "bom.json", "BOM lines"),
          common.save(ctx, "U1-dom", {"rows": rows, "tones": tones, "snap": snap})]
    return Result("pass" if n == 0 else "fail", measured=n,
                  expected="green pins chips over a line the oracle finds not verified/accepted/not_applicable = 0, and no line without a chip",
                  detail=f"green over not_checked: {[b['line'] for b in bad]}; lines with no pins chip: {missing}", evidence=ev)


# ---------------------------------------------------------------- U5
ACCEPT_WORDS = re.compile(r"\baccept\b|\bwaive\b", re.I)


@metric(id="U5(ui)", title="Every finding class has Accept with a required reason; accepted items carry it to the manifest",
        root="R5", level="B", kind="behaviour")
def u5(ctx):
    run = common.Run(ctx)
    found = []
    ev = []
    # (a) the manifest of the outputs: accepted items with an empty reason
    for m in sorted((run.project_dir / "exports").glob("*manifest*.json")):
        d = json.loads(m.read_text(encoding="utf-8"))
        ev.append(ctx.ev(m, "order manifest"))
        for a in d.get("accepted_risks") or []:
            if not str(a.get("reason") or "").strip():
                found.append({"what": "manifest accepted item with empty reason", "item": a.get("line")})
    # (b) the DRC finding class on the Layout page: an Accept control must exist next to the DRC findings
    with Page(run.url, run.project) as P:
        P.open("pcb")
        drc = P.eval("""() => [...document.querySelectorAll('main *')].filter(e => /\\bDRC\\b/.test(e.innerText || '') &&
                 /\\d+\\s+violation/.test(e.innerText || '') && ![...e.children].some(c => /\\bDRC\\b/.test(c.innerText || '')))
                 .map(e => e.closest('div,section,p') || e)
                 .map(e => ({text: e.innerText.slice(0, 300),
                            controls: [...e.querySelectorAll('button,a,[role=button]')].map(b => (b.innerText || b.title || '').trim())}))""")
        snap = P.snapshot("pcb")
    if drc:
        if not any(ACCEPT_WORDS.search(c) for d in drc for c in d["controls"]):
            found.append({"what": "DRC findings shown with no Accept-with-reason control", "item": drc[0]["text"][:80]})
    ev.append(common.save(ctx, "U5-dom", {"drc": drc, "snap": snap}))
    # (c) canary: accept a random not-checked line with an empty reason on a private copy; it must be refused
    srv = common.private(ctx, "U5", fresh=True)
    try:
        from live import seed
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        cands = [ln for ln in _bom(srv.projects / srv.project) if pins.oracle_status(ln, srv.projects / srv.project)[0] == "not_checked"]
        if cands:
            ln = ctx.rng.choice(cands)
            st, body = srv.post("/api/pins/accept", {"line": ln["key"], "reason": ""})
            after = next((x for x in _bom(srv.projects / srv.project) if x["key"] == ln["key"]), {})
            took = st == 200 and isinstance(after.get("pin_decision"), dict)
            ev.append(common.save(ctx, "U5-canary", {"line": ln["key"], "status": st, "after": after.get("pin_decision")}))
            if took:
                found.append({"what": "accept with an empty reason was taken (canary)", "item": ln["key"]})
    finally:
        srv.stop()
    return Result("pass" if not found else "fail", measured=len(found),
                  expected="accepted with empty reason = 0 and every finding class has an Accept-with-reason control",
                  detail="; ".join(f"{f['what']}: {f['item']}" for f in found), evidence=ev)


# ---------------------------------------------------------------- U7
@metric(id="U7", title="Outputs readiness: no green dot with open items; a 'Before you order' card lists each open count with a link",
        root="R2", p0=("P0-3",), level="B", kind="behaviour")
def u7(ctx):
    run = common.Run(ctx)
    lines = _bom(run.project_dir)
    unverified = [ln["key"] for ln in lines if pins.oracle_status(ln, run.project_dir)[0] == "not_checked"]
    facts = run.project_dir / "board-facts.json"
    drc_total = json.loads(facts.read_text(encoding="utf-8")).get("drc_total") if facts.is_file() else None
    open_items = len(unverified) + (drc_total or 0)
    with Page(run.url, run.project) as P:
        P.open("outputs")
        nav = P.eval("""() => { const n = [...document.querySelectorAll('nav *,[class*=nav] *')].find(e =>
              (e.getAttribute('data-nav') || e.getAttribute('data-tab')) === 'outputs' ||
              /^outputs\\b/i.test(e.getAttribute('aria-label') || ''));
              if (!n) return null; const dot = n.querySelector('[class*=via],[class*=dot]') || n;
              return {label: n.getAttribute('aria-label') || n.innerText, cls: String(dot.className)}; }""")
        dot_tone = P.page.locator('[data-nav="outputs"] [class*=via], [data-nav="outputs"] [class*=dot]').first.evaluate(TONE_JS) \
            if nav else "absent"
        card = P.eval("""() => { const h = [...document.querySelectorAll('h1,h2,h3,h4,h5,strong,b,summary,[class*=title],[class*=head]')]
              .find(e => /before you order/i.test(e.innerText || '') && !e.closest('button')); if (!h) return null;
              const box = h.closest('section,article,[class*=card],div'); return {text: box.innerText.slice(0, 3000),
              links: [...box.querySelectorAll('a,button')].map(b => (b.innerText || '').trim())}; }""")
        snap = P.snapshot("outputs")
    viol = []
    if dot_tone == "ok" and open_items > 0:
        viol.append("Outputs nav dot is green with open items")
    need = {"DRC": re.compile(r"\bDRC\b", re.I), "unverified parts": re.compile(r"unverified|not (?:checked|verified)", re.I),
            "open conditions": re.compile(r"condition|requirement", re.I)}
    for what, rx in need.items():
        if not card or not rx.search(card["text"]) or not card["links"]:
            viol.append(f"'Before you order' card does not list {what} with a link")
    if card and unverified and str(len(unverified)) not in card["text"]:
        viol.append(f"card count of unverified parts != oracle {len(unverified)}")
    ev = [ctx.ev(run.project_dir / "bom.json", "BOM"), common.save(ctx, "U7-dom", {"nav": nav, "dot": dot_tone, "card": card, "snap": snap})]
    if facts.is_file():
        ev.append(ctx.ev(facts, "board facts (DRC total, corroboration only)"))
    return Result("pass" if not viol else "fail", measured=len(viol),
                  expected="green dot with open items = 0; card lists DRC JLC-reject, unverified parts, open conditions, each with a link",
                  detail=f"dot={dot_tone}; oracle unverified={unverified}; DRC total (board-facts, corroboration)={drc_total}; " + "; ".join(viol),
                  evidence=ev)


# ---------------------------------------------------------------- U8
LAYOUT_WORDS = re.compile(r"\blayout\b|\bDRC\b|\broute\b|\bplacement\b", re.I)
PAGE_WORDS = {"outputs": re.compile(r"output|gerber|order|JLC|export|CPL|manifest|file", re.I)}
ENGINE_TITLES = {"claude_code": re.compile(r"claude code", re.I), "antigravity": re.compile(r"antigravity", re.I),
                 "codex": re.compile(r"codex", re.I)}


@metric(id="U8", title="Chips act on the current page only; each answer's engine label equals the turn's engine",
        root="R5", level="B", kind="behaviour")
def u8(ctx):
    run = common.Run(ctx)
    turns = [t for t in common.seed.read_jsonl(run.project_dir / "turns-log.jsonl") if t.get("kind") == "chat"]
    rows = common.chat_rows(run.project_dir)
    agents = [r for r in rows if r.get("role") == "agent" and r.get("engine")]
    with Page(run.url, run.project) as P:
        P.open("outputs")
        chips = P.eval("""() => [...document.querySelectorAll('.chat button, [class*=chat] button, [class*=chip]')]
              .filter(b => b.offsetParent && /\\?$|^(help|what|fix|show|check)/i.test((b.innerText || '').trim()))
              .map(b => (b.innerText || '').trim()).filter(t => t.length > 8)""")
        footers = P.eval("""() => [...document.querySelectorAll('[class*=msg]')].filter(m => /\\bagent\\b/.test(m.className))
              .map(m => { const f = m.querySelector('[class*=eng]');
                          const t = m.querySelector('[class*=txt]') || m;
                          return {label: f ? f.innerText.trim() : null, text: (t.innerText || '').trim().slice(0, 400)}; })""")
        snap = P.snapshot("outputs")
    viol = []
    for c in chips:            # a chip on Outputs that talks about the layout's objects acts on another page
        if LAYOUT_WORDS.search(c) and not PAGE_WORDS["outputs"].search(c):
            viol.append({"chip on Outputs about another page": c})
    # engine label per answer: each DOM answer is matched to its chat record by its opening words; the record says
    # which engine wrote it (the turn's engine), the footer must say the same
    def norm(t):
        return re.sub(r"[^a-z0-9]+", " ", re.sub(r"[*_`#>\[\]]", "", str(t).lower())).strip()[:60]
    by_text = {}
    for r in agents:
        by_text.setdefault(norm(r.get("text", "")), r)
    matched = 0
    for f in footers:
        rec = by_text.get(norm(f["text"])) if f["label"] else None
        if not rec:
            continue
        matched += 1
        rx = ENGINE_TITLES.get(rec["engine"])
        if rx and not rx.search(f["label"]):
            viol.append({"answer": f["text"][:60], "label": f["label"], "engine in record": rec["engine"]})
    eng_turns = {t.get("engine") for t in turns}
    ev = [common.save(ctx, "U8-dom", {"chips": chips, "footers": footers, "snap": snap})]
    for f in sorted((run.project_dir / "chats").glob("*.jsonl")):
        ev.append(ctx.ev(f, "chat record"))
    return Result("pass" if not viol else "fail", measured=len(viol),
                  expected="chips about another page's objects = 0 and engine label mismatches = 0",
                  detail=f"engines in turns-log: {sorted(e for e in eng_turns if e)}; answers matched to records: {matched}; {viol[:6]}", evidence=ev)


# ---------------------------------------------------------------- F-I(e), F-I(f)
@metric(id="F-I(e)", title="DFM page states JLC's sign-in limit at the control and asks for the report PDF",
        root="R1", level="B", kind="behaviour")
def fi_e(ctx):
    run = common.Run(ctx)
    with Page(run.url, run.project) as P:
        P.open("checks")
        info = P.eval("""() => ({text: document.querySelector('main') ? document.querySelector('main').innerText : document.body.innerText,
              pdf: [...document.querySelectorAll('input[type=file]')].map(i => i.accept || '')})""")
        snap = P.snapshot("checks")
    text = info["text"]
    # the limit in words: the tool cannot get JLC's verdict itself because it needs the student's sign-in
    limit = re.search(r"(cannot|can.t|not able|unable|no way)[^.]{0,120}(sign[ -]?in|log[ -]?in|account)|"
                      r"(sign[ -]?in|log[ -]?in|account)[^.]{0,120}(cannot|can.t|not able|unable|only you)", text, re.I)
    ask_pdf = re.search(r"(upload|add|drop|choose)[^.]{0,80}(report|PDF)", text, re.I) and \
        (any("pdf" in a.lower() for a in info["pdf"]) or re.search(r"\bPDF\b", text))
    miss = [w for w, ok in (("sign-in limit stated", limit), ("report PDF asked for", ask_pdf)) if not ok]
    return Result("pass" if not miss else "fail", measured=len(miss),
                  expected="the DFM page says the tool cannot get JLC's verdict without the student's sign-in, and asks for the report PDF",
                  detail=f"missing: {miss}", evidence=[common.save(ctx, "F-I(e)-dom", {"info": info, "snap": snap})])


@metric(id="F-I(f)", title="At 1366x768 the Outputs files table and the full export path are visible without scrolling",
        root="R1", level="B", kind="behaviour")
def fi_f(ctx):
    run = common.Run(ctx)
    with Page(run.url, run.project) as P:
        P.open("outputs")
        geo = P.eval("""() => { const vh = innerHeight; const t = [...document.querySelectorAll('table')].find(t =>
              /\\bname\\b/i.test(t.innerText) && /(modified|size|status)/i.test(t.innerText));
              const r = t ? t.getBoundingClientRect() : null;
              const first = t ? t.querySelector('tbody tr') : null; const fr = first ? first.getBoundingClientRect() : null;
              const path = [...document.querySelectorAll('main *')].find(e => e.children.length === 0 &&
                  /([A-Za-z]:\\\\|\\/)[^\\s]*exports/.test(e.innerText || ''));
              const pr = path ? path.getBoundingClientRect() : null;
              return {vh, table: r && [r.top, r.bottom], first_row: fr && [fr.top, fr.bottom],
                      path: path ? path.innerText : null, path_box: pr && [pr.top, pr.bottom]}; }""")
        snap = P.snapshot("outputs")
        P.page.screenshot(path=str(common.EVID / "F-I(f)-outputs.png")) if common.EVID.exists() else None
    viol = []
    if not geo["first_row"] or geo["first_row"][1] > geo["vh"]:
        viol.append(f"files table first row not in view (row bottom {geo['first_row']}, viewport {geo['vh']})")
    if not geo["path"]:
        viol.append("no full export folder path shown")
    elif geo["path_box"][1] > geo["vh"]:
        viol.append("export path below the fold")
    return Result("pass" if not viol else "fail", measured=len(viol),
                  expected="files table (first row) and the full export path inside the 1366x768 viewport without scrolling",
                  detail="; ".join(viol), evidence=[common.save(ctx, "F-I(f)-dom", {"geo": geo, "snap": snap})])


# ---------------------------------------------------------------- U6
@metric(id="U6", title="A skipped rule shows on its own row with its reason after a reload, and the Rules status is not clear",
        root="R2", p0=("P0-1", "P0-3"), level="B", kind="behaviour")
def u6(ctx):
    import urllib.request
    from live import seed
    srv = common.private(ctx, "U6", fresh=True)
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        pdir = srv.projects / srv.project
        tok = "R" + "".join(ctx.rng.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))
        kind = "Kind" + tok[1:]                                   # a random kind no importer can write (canary)
        rules = json.loads((pdir / "rules.json").read_text(encoding="utf-8"))
        rules.append({"name": tok, "kind": kind, "scope1": "All", "scope2": "All", "values": {"gap": "10mil"}, "enabled": True})
        (pdir / "rules.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
        srv.restart()
        with urllib.request.urlopen(f"{srv.url}/api/rules/export?project={srv.project}") as r:
            rul = r.read().decode("utf-8", "replace")
        skipped = [x["name"] for x in rules if x.get("enabled") is not False and x["name"] not in rul]
        with Page(srv.url, srv.project) as P:
            P.open("rules")
            P.reload()
            P.stage("rules")
            P.eval("() => document.querySelectorAll('main details').forEach(d => d.open = true)")
            txt = P.text()
            dot = P.page.locator('[data-nav="rules"] [class*=via]').first.evaluate(TONE_JS)
            snap = P.snapshot("rules")
    finally:
        srv.stop()
    unmarked = []
    for name in skipped:
        row = re.search(re.escape(name) + r"[^\n]*", txt)
        if not (row and re.search(r"skip|not (?:written|exported|imported)|left out|unsupported|cannot", row.group(0), re.I)):
            unmarked.append(name)
    v = len(unmarked) + (1 if skipped and dot == "ok" else 0)
    return Result("pass" if v == 0 else "fail", measured=v,
                  expected="skipped rules without their own row + reason after a reload = 0, and no clear (green) Rules status while one exists",
                  detail=f"left out of the .RUL: {skipped} (canary {tok}, kind {kind}); unmarked: {unmarked}; Rules dot: {dot}",
                  evidence=[common.save(ctx, "U6", {"skipped": skipped, "dot": dot, "snap": snap})])
