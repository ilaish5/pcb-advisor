"""
The BOM and the Library are one table (docs/mockups/parts-merged.html, docs/PARTS-MERGED.md): one row per BOM line with Ref,
Part, Qty, Models, Supply, Status. A click on the Supply tag opens a small card with every supplier; the header has Check stock
and Build library side by side; there is no Library page or nav item, and every old way to it lands on the BOM.

The pure functions are run in node (bomSupply, bomStatus, bomHeader and the supply card) with the real kit.js; the wiring is
read from the source like the other UI tests do.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
JS = REPO / "ui" / "js"
BOM = (JS / "views" / "bom.js").read_text(encoding="utf-8")
PAGES = (JS / "views" / "pages.js").read_text(encoding="utf-8")
INSP = (JS / "views" / "inspector.js").read_text(encoding="utf-8")
KIT = (JS / "kit.js").read_text(encoding="utf-8")
CORE = (JS / "core.js").read_text(encoding="utf-8")
SHELL = (JS / "shell.js").read_text(encoding="utf-8")
BOOT = (JS / "boot.js").read_text(encoding="utf-8")
PALETTE = (JS / "palette.js").read_text(encoding="utf-8")
CSS = (REPO / "ui" / "styles" / "bom.css").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _fn(text, name):
    i = text.index(f"function {name}(")
    return text[i:text.index("\n}\n", i) + 3]


def _line(text, start):
    i = text.index(start)
    return text[i:text.index("\n", i) + 1]


def _run(body):
    """kit.js, the helpers of core.js the table needs, the library pieces of pages.js and the table functions of bom.js, then body."""
    core = "".join(_line(CORE, s) for s in ("const SUPS =", "const esc =", "const num =", "const qty =")) + "".join(
        _fn(CORE, n) for n in ("money", "best", "refRuns", "refsLabel"))
    pages = "".join(_line(PAGES, s) for s in ("const PG_LIB =", "const PG_SOURCE =", "const MIC_ICON =", "const MIC_WORD =", "const MIC_NAME =")) + "".join(
        _fn(PAGES, n) for n in ("libRowOf", "libPinsState", "libModelStates", "libIconsHTML", "libBuildTag"))
    bom = "".join(_line(BOM, s) for s in ("const CODE_RISK =", "const BOM_EXPORTS =", "const BOM_SWAP =", "const bomLibType =", "const bomExt =", "const bomLibRow =")) + "".join(
        _fn(BOM, n) for n in ("bomSupply", "bomStatus", "bomModels", "bomOrphan", "bomRow", "bomHeader", "bomSupCardHTML"))
    script = ("globalThis.addEventListener = () => {}; globalThis.document = {addEventListener() {}};\n" + KIT + "\n" + core +
              "const LIBTXT = {};\nlet S = {library: [], bom: []}, sel = null, bomDrawer = null, bomChecking = false, bomSupOpen = null, libBusy = '', CONFIG = null;\n"
              "const STAGES = [['idea', 'Idea'], ['bom', 'BOM'], ['sch', 'Schematic']];\n"
              "const stageNextBtn = id => btn('Next: Schematic', {kind: 'line', act: 'stage-next', stage: id, to: 'sch'});\n"
              "const bomLinked = () => false, whenText = s => String(s), inspWhen = s => String(s);\n"
              "const inspStockHTML = l => '<section data-test=\"insp-stock\">' + Object.keys(l.supply || {}).join(',') + '</section>';\n"
              + pages + bom + "\n" + body)
    r = subprocess.run([NODE, "-"], input=script, capture_output=True, text=True, encoding="utf-8")   # stdin: a script this long passes the Windows command line limit
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


LINE = {"key": "U2", "refs": ["U2"], "value": "CD4017", "mpn": "CD4017BM96", "lcsc": "C7472", "qty": 1, "library": "ok",
        "library_type": "Extended", "cost_per_board": 0.48, "risk": [],
        "supply": {"LCSC": {"stock": 41230, "unit_price": 0.48, "checked_at": "2026-11-24 05:48"},
                   "Mouser": {"stock": 0, "unit_price": 0.6, "checked_at": "2026-11-24 05:40"}}}


# ---------------------------------------------------------------- the Supply cell and its card

@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_the_supply_tag_is_one_answer_worst_first():
    lines = {
        "in_stock": {**LINE, "library_type": "Basic"},
        "extended": LINE,
        "low": {**LINE, "risk": ["low stock"]},
        "none": {**LINE, "supply": {"LCSC": {"stock": 0, "unit_price": 0.48}}},
        "unchecked": {**LINE, "supply": None},
        "dnp": {**LINE, "qty": 0, "dnp": True},
        "code": {**LINE, "library_type": "Basic", "risk": ["LCSC code is another part"]},
    }
    out = _run("const L = " + json.dumps(lines) + ";\nconst o = {}; for (const k in L) { const l = L[k]; const s = bomSupply(l, qty(l), best(l)); o[k] = [s.text, s.tone || '', s.risks.length]; }\n"
               "console.log(JSON.stringify(o));")
    assert out == {"in_stock": ["In stock", "ok", 0], "extended": ["Extended fee", "warn", 0], "low": ["Low stock", "warn", 0],
                   "none": ["No stock", "bad", 0], "unchecked": ["Not checked", "", 0], "dnp": ["", "", 0], "code": ["In stock", "ok", 1]}


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_the_supply_cell_is_a_keyboard_button_that_opens_the_card_and_the_row_still_opens_the_panel():
    out = _run("const L = " + json.dumps(LINE) + "; S.bom = [L];\nconsole.log(JSON.stringify({row: bomRow(L)}));")
    row = out["row"]
    cell = row[row.index('<td class="c-sup">'):row.index('<td class="c-st">')]
    # a real <button>: Tab reaches it, Enter and Space press it; it says it opens a dialog and whether it is open
    assert '<button type="button" class="sup-btn" data-act="sup-open" data-line="U2"' in cell
    assert 'aria-haspopup="dialog"' in cell and 'aria-expanded="false"' in cell and "Open the stock and supplier details" in cell
    # the row itself keeps its data-key: a click anywhere else in it selects the part and opens the inspector (core.js)
    assert row.startswith('<tr data-key="U2" tabindex="0"')
    assert "if (!e.target.closest('button')) { select(el.dataset.key); return; }" in CORE     # a click on the tag (a button) does not select


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_the_supply_card_has_every_supplier_the_code_the_type_the_prices_and_the_time():
    out = _run("const L = " + json.dumps(LINE) + "; S.bom = [L];\nconsole.log(JSON.stringify({card: bomSupCardHTML(L)}));")
    card = out["card"]
    assert 'data-test="insp-stock">LCSC,Mouser<' in card                    # every supplier: the part panel's own list (inspStockHTML)
    assert "C7472" in card and ">Extended<" in card                         # LCSC code and JLC type
    assert "<dt>Unit price</dt><dd>$0.480 at LCSC</dd>" in card or "<dt>Unit price</dt><dd>$0.48 at LCSC</dd>" in card
    assert "<dt>Per board</dt>" in card and "<dt>Checked</dt><dd>2026-11-24 05:48</dd>" in card
    assert 'id="sup-pop-t"' in card and "act: 'sup-close'" not in card and 'data-act="sup-close"' in card     # a labelled card with a close button
    assert 'data-act="alts"' in card and 'data-act="check-all"' in card


def test_the_supply_card_closes_on_esc_and_an_outside_click_and_gives_the_focus_back():
    paint, close = _fn(BOM, "bomSupPaint"), _fn(BOM, "bomSupClose")
    assert "el.setAttribute('role', 'dialog')" in paint and "aria-labelledby', 'sup-pop-t'" in paint
    assert "el.focus(" in paint                                              # the keyboard lands in the card
    assert "a.focus(" in close and "aria-expanded', 'false'" in close       # and goes back to the Supply cell
    # Esc: before anything else hears it (the inspector and the drawer also close on Esc)
    esc = BOM[BOM.index("window.addEventListener('keydown'"):]
    esc = esc[:esc.index("}, true);")]
    assert "e.key !== 'Escape'" in esc and "e.stopPropagation()" in esc and "bomSupClose(true)" in esc
    # an outside click (pointerdown, so it is before any click handler) closes it; the card and its own cell do not
    out = BOM[BOM.index("document.addEventListener('pointerdown'"):]
    out = out[:out.index("}, true);")]
    assert "closest('#sup-pop')" in out and ".sup-btn[data-line=" in out and "bomSupClose(false)" in out
    # the same cell toggles it; another cell moves it; a redraw paints it again by the new cell
    opener = BOM[BOM.index("onAct('sup-open'"):]
    assert "if (bomSupOpen === d.line) { bomSupClose(true); return; }" in opener[:400]
    assert "if (bomSupOpen) requestAnimationFrame(bomSupPaint);" in _fn(BOM, "bomHTML")
    assert "bomSupClose(false);" in _fn(BOM, "openBomDrawer")                # the Alternatives drawer takes over
    assert ".sup-pop{position:fixed;" in CSS and "box-shadow:var(--float)" in CSS


# ---------------------------------------------------------------- the header: two buttons, side by side, always

@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_check_stock_and_build_library_are_both_in_the_header_side_by_side():
    totals = {"lines": 2, "parts": 3, "cost_per_board": 1.2, "buy": 2, "in_stock": 2, "checking": 0, "to_verify": 1, "extended_fee": 3.07}
    out = _run("const t = " + json.dumps(totals) + ";\nconst a = bomHeader(t); libBusy = 'build'; bomChecking = true; const busy = bomHeader(t); libBusy = ''; bomChecking = false;\n"
               "console.log(JSON.stringify({full: a, busy, empty: bomHeader({lines: 0})}));")
    for key in ("full", "busy", "empty"):
        html = out[key]
        acts = html[html.index('<div class="acts">'):html.index('<div class="vh-next">')]
        check, build = acts.find('data-act="check-all"'), acts.find('data-act="libbuild"')
        assert check != -1 and build != -1, key                                              # both, whatever the state
        between = acts[check:build]
        assert between.count("<button") == 1, key                                            # side by side: nothing between them
        assert html.count('class="btn pri') <= 1, key                                       # one filled button at most
        assert "Next: Schematic" in html[html.index('<div class="vh-next">'):], key           # Next keeps its own slot
    assert "Checking…" in out["busy"] and "Building…" in out["busy"]
    assert "Library package" in out["full"] and "Prepare library only" in out["full"]          # the Library page's other two actions
    meta = out["full"][out["full"].index('<div class="meta">'):]
    for word in ("lines", "parts", "per board", "extended fees", "to verify"):
        assert word in meta, word


def test_the_page_keeps_the_library_pages_pieces_above_its_table():
    top = _fn(BOM, "bomTop")
    for piece in ("bomLibNote()", "pinsWaitingBar()", "libExportHTML()", "libLegendHTML()"):
        assert piece in top, piece
    assert "libIssues" not in BOM and "libIssues(row)" in _fn(INSP, "inspLibHTML")          # the converter's text: part panel only


# ---------------------------------------------------------------- no Library page, and every old way to it lands on the BOM

def test_there_is_no_library_nav_item_and_no_library_page():
    assert "library:" not in _line(SHELL, "const PAGE_TITLES =")
    nav = _fn(SHELL, "navHTML")
    assert "pageBtn('library'" not in nav and "pageBtn('sources', 'file')" in nav
    assert "'library'" not in _fn(SHELL, "renderPage") and "libHTML" not in "".join(p.read_text(encoding="utf-8") for p in JS.rglob("*.js"))
    assert "'library'" not in _line(PALETTE, "for (const id of [")


def test_every_old_way_to_the_library_lands_on_the_bom():
    assert "const PAGE_MOVED = {library: 'bom'};" in SHELL
    go = _fn(SHELL, "go")
    assert "if (PAGE_MOVED[p] && !t) p = PAGE_MOVED[p];" in go and go.index("PAGE_MOVED") < go.index("STAGE_TITLES[p]")   # go('library'), data-page="library"
    assert "if (PAGE_MOVED[m[2]]) return stageItem(PAGE_MOVED[m[2]]);" in _fn(SHELL, "itemFromRef")                       # a saved sheet 'page:library'
    init = _fn(BOOT, "initialMain")
    assert init.index("PAGE_MOVED[p]") < init.index("PAGE_TITLES[p]")                                                   # ?page=library
    assert "if (d.page) { go(d.page); return; }" in CORE                                                                  # data-page="library" goes through go()


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_the_redirect_runs():
    """The real go() and itemFromRef() of shell.js, with the sheet setter stubbed: each old reference opens the BOM stage."""
    script = ("const STAGES = [['idea', 'Idea'], ['bom', 'BOM'], ['sch', 'Schematic']];\nconst STAGE_TITLES = Object.fromEntries(STAGES);\n"
              + _line(SHELL, "const PAGE_TITLES =") + SHELL[SHELL.index("/* Pages that were merged"):SHELL.index("const PAGE_MOVED")] + _line(SHELL, "const PAGE_MOVED =")
              + _line(SHELL, "const stageItem =") + _line(SHELL, "const pageItem =") + "const sideMemo = {file: null};\nlet tab = 'bom', mainItem = stageItem('idea'), got = [];\n"
              + _fn(SHELL, "itemFromRef") + _fn(SHELL, "go").replace("setMain(item);", "got.push(item.id);").replace("setView('work');", "")
              + "go('library'); go('workspace', 'bom'); go('sources');\n"
              "console.log(JSON.stringify({got, saved: itemFromRef('page:library').id, src: itemFromRef('page:sources').id}));")
    r = subprocess.run([NODE, "-"], input=script, capture_output=True, text=True, encoding="utf-8")   # stdin: a script this long passes the Windows command line limit
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out == {"got": ["stage:bom", "stage:bom", "page:sources"], "saved": "stage:bom", "src": "page:sources"}


def test_no_view_still_names_the_library_page():
    """What the student reads never sends them to a page that is gone (code comments may still tell the history)."""
    for f in sorted(JS.rglob("*.js")):
        src = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        src = re.sub(r"(?m)(^|\s)//.*$", "", src)
        assert "Library page" not in src, f.name
    serve = (REPO / "scripts" / "serve.py").read_text(encoding="utf-8")
    assert "Library page" not in serve and "BOM page, Build library" in serve
    code = "".join(re.sub(r"(?m)(^|\s)//.*$", "", re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)) for p in JS.rglob("*.js"))
    assert not re.search(r"data-(nav|page)=\"library\"|page: 'library'|go\('library'\)", code)
