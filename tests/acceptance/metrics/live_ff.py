"""F-F (previews can be judged), behaviour legs: (a) Confirm-pins opens the datasheet page that holds the part's pin table,
(b) a symbol-pin vs pad-count difference is explained per pad. Geometry of the previews is T-G (not repeated here).
Pages come from the datasheet text the project keeps (sources/<doc>.txt, one form feed per page); pins and pads from the
part's own KiCad library files, read by the oracle."""
from __future__ import annotations

import json
import re

from lib import Result, metric
from live import common, seed
from live.driver import Page


def symbol_pins(path) -> list[tuple[str, str]]:
    txt = path.read_text(encoding="utf-8", errors="replace")
    return [(n, re.sub(r"~\{([^}]*)\}", r"\1", nm)) for nm, n in re.findall(r'\(name "([^"]*)"[^\n]*\n\s*\(number "([^"]*)"', txt)]


def footprint_pads(folder) -> list[tuple[str, str]]:
    """(pad number, pad type) of every pad in the part's .kicad_mod files; an unnamed pad has number ''."""
    out = []
    for f in sorted(folder.glob("*.kicad_mod")):
        for m in re.finditer(r'\(pad\s+(?:"([^"]*)"|(\S+))\s+(\w+)', f.read_text(encoding="utf-8", errors="replace")):
            out.append((m.group(1) if m.group(1) is not None else m.group(2), m.group(3)))
    return out


def pin_table_pages(doc_txt: str, names: list[str]) -> tuple[list[int], dict]:
    """Pages (1-based) that hold the part's pin table: a page naming at least min(8, half of) the part's distinct pin names
    and at least half as many as the best page (a long pin table spans several pages, each with a share of the pins)."""
    want = {part for n in names for part in re.split(r"[/\-()]", n.upper()) if re.search(r"[A-Z]", part) and len(part) >= 2}
    pages = doc_txt.split("\f")
    count = {}
    for i, p in enumerate(pages, 1):
        toks = set(re.findall(r"[A-Za-z0-9_+]+", p.upper()))          # PA0-WKUP and VDDA/VREF+ also count by their parts
        count[i] = len(want & toks)
    best = max(count.values() or [0])
    need = max(min(8, (len(want) + 1) // 2), (best + 1) // 2)
    return [i for i, c in count.items() if c >= need and best > 0], count


@metric(id="F-F(a)", title="Confirm pins opens the datasheet page holding the part's pin table (random part)",
        root="R2", level="B", kind="behaviour")
def ff_a(ctx):
    srv = common.private(ctx, "F-F", fresh=True)
    rec = {}
    try:
        srv.project = seed.seed_fixture(srv.projects, root=ctx.root)
        srv.restart()
        pdir = srv.projects / srv.project
        man = json.loads((pdir / "library" / "manifest.json").read_text(encoding="utf-8"))
        with Page(srv.url, srv.project) as P:
            P.open("checks")
            # canary: give back a random student decision so its part needs confirming again (random part, A5)
            revs = P.eval("() => [...document.querySelectorAll('main button')].filter(b => /^revoke$/i.test(b.innerText.trim()))"
                          ".map((b, i) => i)")
            if revs:
                k = ctx.rng.choice(revs)
                P.page.get_by_role("button", name=re.compile(r"^revoke$", re.I)).nth(k).click()
                P.page.wait_for_timeout(2500)
                P.reload()
                P.stage("checks")
            lines = P.eval("() => [...new Set([...document.querySelectorAll('[data-act=\"confirm-pins\"]')].map(b => b.dataset.line))]")
            if not lines:
                return Result("error", detail="no part offers Confirm pins on the DFM page (nothing to measure)")
            key = ctx.rng.choice(lines)
            P.page.locator(f'[data-act="confirm-pins"][data-line="{key}"]').first.click()
            P.page.wait_for_timeout(2500)
            src = P.eval("() => { const f = document.querySelector('dialog[open] iframe'); return f ? f.getAttribute('src') : null; }")
    finally:
        srv.stop()
    m = re.search(r"/api/source/([^?#]+).*#page=(\d+)", src or "")
    if not m:
        return Result("fail", measured=1, expected="the opened page is a pin-table page of the part's datasheet",
                      detail=f"{key}: Confirm pins opened no datasheet page ({src})")
    doc, page = m.group(1), int(m.group(2))
    ent = man.get(key) or {}
    sym = pdir / "library" / "easyeda" / str(ent.get("lcsc")) / "lib.kicad_sym"
    names = [nm for _, nm in symbol_pins(sym)] if sym.is_file() else []
    txt = (pdir / "sources" / (doc + ".txt"))
    good, score = pin_table_pages(txt.read_text(encoding="utf-8", errors="replace"), names) if txt.is_file() else ([], {})
    ok = page in good
    rec = {"line": key, "doc": doc, "opened": page, "pin_table_pages": good[:20], "names_on_opened_page": score.get(page, 0)}
    return Result("pass" if ok else "fail", measured=0 if ok else 1, expected="Confirm pins opens a page the oracle finds holding the part's pin table",
                  detail=json.dumps(rec), evidence=[common.save(ctx, "F-F(a)", rec), ctx.ev(txt, "datasheet text")] if txt.is_file() else [])


@metric(id="F-F(b)", title="A symbol-pin vs pad-count difference is explained per pad (NPTH pegs listed) in the footprint preview",
        root="R2", level="B", kind="behaviour")
def ff_b(ctx):
    run = common.Run(ctx)
    pdir = run.project_dir
    man = json.loads((pdir / "library" / "manifest.json").read_text(encoding="utf-8"))
    diffs = []
    for key, ent in man.items():
        d = pdir / "library" / "easyeda" / str(ent.get("lcsc"))
        if not (d / "lib.kicad_sym").is_file() or not (d / "lib.pretty").is_dir():
            continue
        pins = {n for n, _ in symbol_pins(d / "lib.kicad_sym")}
        pads = footprint_pads(d / "lib.pretty")
        if len(pins) != len(pads):
            extra = [n or f"(unnamed {t})" for n, t in pads if n not in pins]
            diffs.append({"line": key, "pins": len(pins), "pads": len(pads), "extra": extra})
    bad = []
    with Page(run.url, run.project) as P:
        P.open("bom")
        for dd in diffs:
            btn = P.page.locator(f'[data-act="lib-preview"][data-line="{dd["line"]}"][data-kind="footprint"]')
            if not btn.count():
                bad.append({**dd, "why": "no footprint preview"})
                continue
            btn.first.click()
            P.page.wait_for_timeout(2000)
            txt = P.eval("() => { const d = document.querySelector('dialog[open]'); return d ? d.innerText : ''; }")
            P.page.keyboard.press("Escape")
            unexplained = []
            for e in dd["extra"]:
                if e.startswith("(unnamed"):
                    if not re.search(r"NPTH|non-plated|mechanical|peg|locating|mounting|unnumbered|no number", txt, re.I):
                        unexplained.append(e)
                elif not re.search(r"(?<![\w])" + re.escape(e) + r"(?![\w])", txt):
                    unexplained.append(e)
            if unexplained or not re.search(rf"\b{dd['pads']}\b", txt):
                bad.append({**dd, "why": f"not explained per pad: {unexplained or 'pad count not stated'}"})
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected="parts whose pad count differs from the symbol's pin count without every extra pad named (NPTH pegs listed) = 0",
                  detail=json.dumps(bad)[:1500], evidence=[common.save(ctx, "F-F(b)", {"diffs": diffs, "bad": bad})])
