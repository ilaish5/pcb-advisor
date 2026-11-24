"""
The BOM view (ui/js/views/bom.js, ui/styles/bom.css): a header with one primary, a table without inputs (one row per line, with
its models: the Library page is merged in), and a right-hand drawer for alternatives, price comparison and the Altium import.

The UI has no JS test runner here, so these read the UI source (tests/ui_source.py) the way the other UI tests do;
the behaviour itself was driven in headless Edge when it was written (scripts in the redesign scratchpad).
"""
import pathlib
import re

from ui_source import ui_all, ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
BOM = (REPO / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")
KIT_JS = (REPO / "ui" / "js" / "kit.js").read_text(encoding="utf-8")
CSS = (REPO / "ui" / "styles" / "bom.css").read_text(encoding="utf-8")
ALL = ui_all()
JS = ui_js()


def _fn(name):
    """The source of one top-level function of bom.js, up to the next top-level statement."""
    start = BOM.index(f"function {name}(")
    nxt = re.search(r"\n(?:async function |function |onAct\(|onChange\(|const |let |document\.|/\*)", BOM[start + 10:])
    return BOM[start:start + 10 + (nxt.start() if nxt else 20000)]


def _handler(act):
    """The source of one onAct handler of bom.js."""
    start = BOM.index(f"onAct('{act}'")
    nxt = re.search(r"\n(?:onAct\(|onChange\(|const |function |async function |/\*)", BOM[start + 10:])
    return BOM[start:start + 10 + (nxt.start() if nxt else 20000)]


# ---------------------------------------------------------------- the table

def test_the_table_has_no_inputs_and_no_inline_styles():
    """A part is edited in the inspector. The table is read-only and styled from bom.css."""
    code = re.sub(r"/\*.*?\*/", "", BOM, flags=re.S)
    table = code        # the pending-change list (shared proposalTable in kit.js) ticks proposals, not parts
    assert "<input" not in table and "<textarea" not in code and "<select" in _fn("importHTML")   # the import picker is the one control
    assert "propListHTML" in _fn("bomPendingBox") and "type=\"checkbox\"" in KIT_JS
    assert "style=" not in code
    assert "data-edit" not in _fn("bomRow")


def test_the_table_columns_and_the_row_contract():
    html = _fn("bomHTML")
    assert 'class="tbl rows bom-tbl"' in html
    # one table for the ordering data and the Altium models (the Library page is merged in): docs/mockups/parts-merged.html
    assert re.findall(r"<th[^>]*>([^<]+)</th>", html) == ["Ref", "Part", "Qty", "Models", "Supply", "Status"]
    row = _fn("bomRow")
    assert 'data-key="${esc(l.key)}"' in row and 'tabindex="0"' in row             # core selects a part by tr[data-key]
    assert "refsLabel(refs)" in row and 'title="${esc(refs.join(\', \'))}"' in row  # a short label, the full list in the title
    assert "row-acts" in row and "act: 'ask-part'" in row and "act: 'alts'" in row
    # the actions are icon buttons: each says what it does
    assert "title: `Ask about ${label}`" in row and "'aria-label': `Alternatives for ${label}`" in row


def test_the_table_scrolls_inside_the_sheet_with_its_head_pinned():
    assert ".bom-scroll{flex:1;min-height:0;overflow:auto" in CSS
    assert '<div class="bom-scroll">' in _fn("bomHTML")
    assert "scrollTop" in _fn("bomHTML")                  # a re-render (a stock check, an edit) keeps the scroll position
    # nothing in a cell wraps onto a second line (long designator lists end in an ellipsis, the full list is the
    # cell's title), so a row keeps its height
    assert ".bom-tbl td{white-space:nowrap}" in CSS


def test_the_supply_cell_is_one_tag_worst_first():
    sup = _fn("bomSupply")
    for text in ("Not checked", "No stock", "Low stock", "Extended fee", "In stock"):
        assert f"text: '{text}'" in sup, text
    order = [sup.index(f"text: '{t}'") for t in ("Not checked", "No stock", "Low stock", "Extended fee", "In stock")]
    assert order == sorted(order)                           # the worst answer wins
    assert "if (!q) return {text: '', risks: []};" in sup   # a line that is not fitted or not bought has no supply tag
    # the supplier risks that are not about stock are counted beside the tag, and named in its title
    assert "CODE_RISK" in sup and "'no exact MPN match'" in sup
    assert "'+' + sup.risks.length" in _fn("bomRow")


def test_the_status_cell_is_one_tag_from_the_build_or_the_pins():
    st = _fn("bomStatus")
    assert "libBuildTag(r)" in st and "PG_LIB[r.status]" in st      # the Library page's own words
    for text in ("Missing", "Footprint error", "Pins conflict", "Verify pins", "Accepted risk", "Altium default"):
        assert f"text: '{text}'" in st, text
    # every status says itself in one short sentence (the long converter text is in the part panel, never in the table)
    assert st.count("say:") >= 8 and "issue_list" not in st and "libIssues" not in BOM
    assert "tag(st.text, st.tone, st.say" in _fn("bomRow")


def test_the_models_cell_draws_the_library_icons_without_the_built_word():
    m = _fn("bomModels")
    assert "libIconsHTML(r || libRowOf(l), {built: false})" in m
    assert "l.library === 'std'" in m                     # an Altium default part has no models of its own


def test_a_placeholder_dash_is_not_shown_as_an_mpn():
    row = _fn("bomRow")
    assert "const real = v =>" in row and "real(l.mpn)" in row and "real(l.manufacturer)" in row


def test_the_part_column_takes_what_is_left_so_the_table_never_outgrows_its_sheet():
    """Bug: with a fixed 200px for the part name the table needed 973px in a 930px sheet (1600x1000, chat open): a thin
    horizontal scrollbar. The column that is cut with an ellipsis must be the one that gives way."""
    flat = CSS.replace(" ", "")
    assert ".bom-tbl.c-part{width:100%;max-width:0}" in flat
    main = re.search(r"\.bom-tbl \.main,\.bom-tbl \.sub\{([^}]*)\}", CSS).group(1)
    assert "max-width" not in main and "text-overflow:ellipsis" in main
    assert '<th class="c-part">Part</th>' in _fn("bomHTML") and '<td class="c-part"' in _fn("bomRow")


def test_a_narrow_sheet_drops_the_row_icons_first():
    assert "@container (max-width:560px){.bom-tbl th:last-child,.bom-tbl td:last-child{display:none}}" in CSS
    assert "container-type:inline-size" in CSS
    # not on .bom-view: layout containment there would trap the fixed-position header menus
    assert not re.search(r"\.bom-view\{[^}]*container-type", CSS)


# ---------------------------------------------------------------- the header

def test_the_header_has_one_primary_and_the_rest_in_menus():
    head = _fn("bomHeader")
    assert head.count("kind: t.lines ? 'pri' : 'line'") == 1 and head.count("'pri'") == 1 and "'Check stock'" in head and "act: 'check-all'" in head and "act: 'libbuild'" in head
    assert "viewHeader({title: 'BOM'" in head
    for needle in ("label: BOM_EXPORTS.jlc", "label: BOM_EXPORTS.generic", "fmt: 'jlc'", "fmt: 'generic'",
                   "label: 'Compare prices', act: 'compare'", "bomLinked() && {label: 'Import from Altium', act: 'imp-open'}"):
        assert needle in head, needle
    # the meta line says only what is non-zero, with a tone
    for needle in ("t.checking", "t.out_of_stock", "t.to_verify", "tone: 'bad'", "tone: 'warn'"):
        assert needle in head, needle
    assert "guidanceBarHTML" not in BOM and "kpi" not in BOM and "vhead" not in BOM


def test_the_empty_bom_says_what_to_do_and_offers_the_import_only_when_it_can_work():
    html = _fn("bomHTML")
    assert "emptyState('No parts yet'" in html
    assert "Describe your idea in the chat and the agent will propose parts." in html
    assert "btn('Import from Altium', {kind: 'pri', act: 'imp-open'})" in html
    assert "bomLinked()" in html


def test_the_footer_goes_amber_when_the_prices_are_a_day_old():
    assert "const BOM_STALE_MS = 24 * 3600 * 1000;" in BOM
    foot = _fn("bomFoot")
    assert "Prices at qty 10, excl. shipping." in foot and "Checked ${esc(st.text)}." in foot
    assert "' stale'" in foot and "Not checked yet." in foot
    assert ".bom-foot.stale{color:var(--warn)}" in CSS
    stamp = _fn("bomStamp")
    assert "stale: Date.now() - d.getTime() > BOM_STALE_MS" in stamp
    assert "whenText(at, true)" in stamp             # "14 Oct 2026 10:20": the year is always there


# ---------------------------------------------------------------- one Check stock

def test_check_stock_is_one_action_for_the_button_and_the_palette():
    assert ALL.count("onAct('check-all'") == 1
    assert "onAct('check'" not in ALL and "data-act=\"check\"" not in ALL
    handler = _handler("check-all")
    assert "'/api/skill', {name: 'check'}" in handler      # the path that reports each supplier's answer
    assert "if (bomChecking) return;" in handler           # a second press while one runs does nothing
    assert "setState(r.state)" in handler
    # a supplier that failed is said out loud
    assert "filter(x => x.error)" in handler and "supplier lookup" in handler and "toast(" in handler
    assert "bomChecking" in _fn("bomHeader") and "'Checking…'" in _fn("bomHeader")      # the button shows it is running


# ---------------------------------------------------------------- export feedback

def test_an_export_says_so_and_offers_the_download():
    handler = _handler("export")
    assert "'/api/skill', {name: 'export_bom', args: [fmt]}" in handler
    assert "if (r.state) setState(r.state)" in handler and "render(true)" in handler    # the Outputs view lists the file
    assert "exported" in handler and "label: 'Download'" in handler and "bomDownload(file)" in handler
    assert "needs_lcsc" in handler                                                    # a line with no LCSC number is said, not hidden
    assert "/api/export/${encodeURIComponent(name)}" in _fn("bomDownload")
    assert "jlc: 'BOM (JLC)', generic: 'BOM (generic)'" in BOM                        # the names Outputs uses too
    assert "exportCard" not in BOM                                                    # no card above the table any more


# ---------------------------------------------------------------- the drawer

def test_the_drawer_is_a_labelled_dialog_that_esc_closes():
    drawer = _fn("bomDrawerHTML")
    assert 'class="drawer bom-drawer" role="dialog" aria-label="${esc(title)}" tabindex="-1"' in drawer
    assert "title: 'Close'" in drawer and "act: 'bom-drawer-close'" in drawer and "onAct('bom-drawer-close'" in BOM
    assert "e.key === 'Escape' && bomDrawer && !uiBusy()" in BOM       # not while a dialog is on top of it
    assert "el.focus({preventScroll: true})" in _fn("openBomDrawer")   # the keyboard lands in the drawer
    # it takes the inspector's place while open and gives it back
    assert "bomPrevSel" in _fn("openBomDrawer") and "bomPrevSel" in _fn("closeBomDrawer")


def test_a_drawer_belongs_to_one_project_and_one_request():
    assert "bomDrawerProject !== PROJECT" in _fn("bomHTML")
    # an answer that arrives after the drawer was closed or replaced is dropped
    assert _handler("alts").count("bomDrawer !== mine") == 2
    assert _handler("compare").count("bomDrawer !== mine") == 2


def test_alternatives_take_the_line_from_a_row_or_from_the_inspector_menu():
    handler = _handler("alts")
    assert "d.line || d.key" in handler
    assert "/api/parts/alternatives?line=${encodeURIComponent(line)}" in handler
    assert "act: 'alts', line: d.line" in _fn("altsHTML")              # the retry button
    # a proposal goes through the same approval as any change: nothing is applied here
    prop = _handler("propose-alt")
    assert "/api/bom/propose" in prop and "Approve it in the chat" in prop


def test_the_cheapest_complete_supplier_is_in_ink_not_colour():
    html = _fn("compareHTML")
    assert "whole(r) && r.cost_per_board === cheapest" in html and 'class="best"' in html
    assert ".cmp li.best .num" in CSS and "color:var(--ink)" in CSS


def test_the_import_report_is_compact_and_escapes_the_file_text():
    rep = _fn("importReportHTML")
    assert "slice(0, 8)" in rep and "Open report" in rep                  # a handful of findings, the rest in the report
    assert "esc(f.message)" in rep and "esc(f.kind)" in rep
    assert "esc(c.path)" in _fn("importHTML")


# ---------------------------------------------------------------- editing contract with the inspector

def test_role_note_and_mpn_save_from_any_input_marked_data_edit():
    change = BOM[BOM.index("onChange(t => t.closest && t.closest('input[data-edit]')"):]
    assert "'/api/bom/edit', {line: l.key, field, value: val}" in change
    assert "if (field === 'mpn' && !val)" in change and "i.value = l.mpn ?? ''" in change    # an MPN is never emptied
    assert "if (val === (l[field] ?? '')) return;" in change                                   # an unchanged field is not sent
    assert "bomKeepFocus" in change                                                              # tabbing through the fields keeps the focus


def test_the_inspector_fields_match_the_handler():
    insp = (REPO / "ui" / "js" / "views" / "inspector.js").read_text(encoding="utf-8")
    assert 'data-edit="${name}"' in insp and 'data-line="${esc(l.key)}"' in insp
    assert re.search(r"act: 'alts'", insp)                           # the menu entry opens the drawer in bom.js


# ---------------------------------------------------------------- the stylesheet

def test_the_bom_stylesheet_uses_tokens_not_hex_colours():
    # every colour in the view's stylesheet comes from a token
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b(?![\w-])", CSS.replace("#imp-csv", ""))
    assert "rgb" not in CSS
    for legacy in (".refs{", ".lib{", ".foot{", ".dsec", ".detail{", ".y{", ".nn{"):
        assert legacy not in CSS, f"{legacy} was left over from the old frame, it is not the BOM's"
    for old in (".kpi", ".bom .mpn", ".role-input", ".imp-card", ".imp-tbl", "table.bom"):
        assert old not in CSS, old
