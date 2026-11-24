"""UI clarity rules (Wave 3 stream 3): one money rule, one date rule, one unit rule, one banner component, one button order, the
sheet count from the server, the remembered page, no white flash, the size parser, the elapsed clock. Static source tests plus
node-run tests of the pure helpers."""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
UI = REPO / "ui"
JS = UI / "js"


def _src(rel):
    return (UI / rel).read_text(encoding="utf-8")


def _fn(text, name):
    i = text.index(f"function {name}(")
    j = text.index("\n}\n", i) + 3
    return text[i:j]


def _const(text, name):
    i = text.index(f"const {name} =")
    first = text.index("\n", i)
    j = text.index("\n};\n", i) + 4 if text[i:first].rstrip().endswith("{") else text.index(";\n", i) + 2      # a block body ends at "};"
    return text[i:j]


def _node(script, tmp_path):
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


# ---- 49: one money rule ----
@needs_node
def test_money_has_one_rule_and_a_fee_is_not_rounded_to_a_whole_number(tmp_path):
    core = _src("js/core.js")
    cases = [3.07, 3, 0.1, 0.125, 0.0123, 0.0004, 12.5, None, 0, 41.37]
    script = _fn(core, "money") + ";process.stdout.write(JSON.stringify(" + json.dumps(cases) + ".map(money)));"
    out = _node(script, tmp_path)
    assert out == ["$3.07", "$3.00", "$0.10", "$0.125", "$0.012", "$0.0004", "$12.50", "—", "$0.0000", "$41.37"]
    bom = _src("js/views/bom.js")
    assert "toFixed(" not in _fn(bom, "bomHeader") and "money(fee)" in bom      # the extended fee goes through money()
    assert "toFixed(2)" not in _src("js/update.js").split("aboutMoney")[1].split("\n")[0]


# ---- 63: one date rule, always with the year ----
@needs_node
def test_dates_always_carry_the_year(tmp_path):
    core = _src("js/core.js")
    script = _const(core, "WHEN_MONTHS") + _fn(core, "whenText") + (
        ";process.stdout.write(JSON.stringify([whenText('2026-11-20T14:05:00'), whenText('2026-11-20 14:05', true), whenText(''), whenText('junk')]));")
    a, b, c, d = _node(script, tmp_path)
    assert a == "20 Nov 2026" and b == "20 Nov 2026 14:05" and c == "" and d == "junk"
    for rel in ("js/views/bom.js", "js/views/inspector.js", "js/views/idea.js", "js/views/outputs.js", "js/views/pins.js"):
        assert "whenText(" in _src(rel), rel
    assert "MONTHS" not in _src("js/views/bom.js") + _src("js/views/outputs.js")      # no second month table


# ---- 64: mm everywhere, source tags in words ----
@needs_node
def test_lengths_are_mm_and_source_tags_are_words(tmp_path):
    core = _src("js/core.js")
    script = _const(core, "mmOfMil") + _const(core, "lenText") + _const(core, "srcTags") + (
        ";process.stdout.write(JSON.stringify([lenText('Min: 248.0315mil, Max: 40mil'), srcTags('floor 0.1 mm [P1, P3] and [P13]'), lenText('0.2 mm')]));")
    a, b, c = _node(script, tmp_path)
    assert a == "Min: 6.3 mm, Max: 1.016 mm"
    assert b == "floor 0.1 mm (JLC source 1, 3) and (JLC source 13)"
    assert c == "0.2 mm"
    rules = _src("js/views/rules.js")
    assert "lenText(v)" in rules and "srcTags(d.detail)" in rules


def test_stop_is_not_a_dead_button_and_the_clock_runs():
    prev = _src("js/views/previews.js")
    stop = _fn(prev, "pvStopBtn")
    assert "pv-nostop" in stop and "disabled: pvStopping ? true : undefined" in stop      # disabled only while it is stopping
    assert "pvElapsedHTML()" in prev and "setInterval(" in prev and "pv-elapsed" in prev    # 65: the time since the step began
    assert "pvStartedAt = Date.now()" in prev and "r.started * 1000" in prev                # a reload keeps the server's start
    assert "Fit'" in prev and "pvFitContent(wrap)" in prev                                   # 64: Fit names itself and fits the drawing


# ---- 52: one banner component, one button hierarchy ----
def test_one_banner_component_draws_every_note():
    kit = _src("js/kit.js")
    assert "function banner(" in kit and "BANNER_ICON" in kit
    for f in list(JS.glob("*.js")) + list((JS / "views").glob("*.js")):
        if f.name in ("kit.js", "chat.js"):
            continue
        assert 'class="note' not in f.read_text(encoding="utf-8"), f.name + " draws its own note, use banner()"
    base = _src("styles/base.css")
    assert ".note>.note-i" in base and ".note.warn>.note-i" in base


def test_the_default_button_looks_like_a_button_and_the_filled_one_is_last():
    base = _src("styles/base.css")
    assert re.search(r"^\.btn\{border:1px solid", base, re.M)          # secondary = outlined, not bare text
    assert ".btn.icon,.btn.link{border-color:transparent" in base       # tertiary = bare
    kit = _src("js/kit.js")
    vh = _fn(kit, "viewHeader")
    assert vh.index("${next}") > vh.index("${primary}") > vh.index("${o.actions || ''}")      # the actions, the page's own primary, then the Next slot last
    assert "btn pri" in vh                                              # one filled button per header: the page's own steps down when Next is filled


@needs_node
def test_header_demotes_the_page_primary_when_next_is_the_filled_one(tmp_path):
    kit = _src("js/kit.js")
    script = (
        "const STAGES=[['bom','BOM']];const stageOf=()=>({next:{act:'go:sch'},primary:true});"
        "const stageNextBtn=()=>'<button class=\"btn pri\">Next</button>';"
        + _fn(kit, "kesc") + "const KIT_ICONS={};" + _fn(kit, "icon") + _fn(kit, "kattrs") + _fn(kit, "btn") + _fn(kit, "viewHeader") +
        ";process.stdout.write(JSON.stringify([viewHeader({title:'BOM',stage:'bom',primary:btn('Check',{kind:'pri'})}),"
        "viewHeader({title:'BOM',stage:'idea',primary:btn('Check',{kind:'pri'})})]));")
    with_next, without = _node(script, tmp_path)
    assert with_next.count("btn pri") == 1 and "btn line" in with_next
    assert "btn pri" in without and without.count("btn pri") == 1


# ---- 48: LCSC code and part type in the table ----
def test_the_bom_table_shows_the_lcsc_code_and_the_part_type():
    bom = _src("js/views/bom.js")
    # the merged table has no LCSC column: the code and the type are on the supply card a click on the Supply tag opens,
    # and in the part panel; an Extended part says so on the row itself (its Supply tag reads Extended fee)
    card = _fn(bom, "bomSupCardHTML")
    assert "esc(l.lcsc)" in card and "tag(lt, bomExt(l)" in card
    assert "bomExt(l)" in _fn(bom, "bomSupply") and "'Extended fee'" in _fn(bom, "bomSupply")
    assert "l.library_type" in bom and "LCSC.library_type" in bom
    assert "bomLibType(l)" in _src("js/views/inspector.js")


# ---- 53 / 54: the page is remembered, no white flash ----
def test_the_page_is_remembered_across_a_reload():
    shell, boot = _src("js/shell.js"), _src("js/boot.js")
    assert "saveMain()" in _fn(shell, "setMain") and "MAIN_KEY" in shell
    init = _fn(boot, "initialMain")
    assert init.index("URLQ.get('page')") < init.index("savedMain()") < init.index("stageItem(!S.idea.confirmed")      # ?page= wins, then the saved page


def test_the_first_paint_has_the_frame_colour_before_any_script():
    html = _src("index.html")
    assert html.index('id="first-paint"') < html.index("/ui/diagram.js") < html.index("/ui/styles/base.css")
    assert 'name="color-scheme"' in html and "prefers-color-scheme:dark" in html
    frame = re.search(r"--frame:(#\w+)", _src("styles/base.css")).group(1).upper()
    assert frame in html.upper()                                                # the inline colour is the stylesheet's


# ---- 34 / 33: the sheet count comes from the server ----
@needs_node
def test_one_sheet_count_from_the_server(tmp_path):
    shell = _src("js/shell.js")
    script = ("let S={stage_sheets:{plan:3,altium:1,total:3},sheets:[{altium:true},{altium:true}]};" + _fn(shell, "sheetCounts") +
              ";const a=sheetCounts().total;S={sheets:[{},{},{altium:true}]};const b=sheetCounts().total;S={sheets:[{altium:true},{altium:true}]};"
              "process.stdout.write(JSON.stringify([a,b,sheetCounts().total]));")
    assert _node(script, tmp_path) == [3, 2, 2]
    prev = _src("js/views/previews.js")
    assert "sheetCounts(sheets).total" in prev and "sheetCounts().total" in _src("js/viewer.js")
    assert "pvSheetTitle(s)" in prev      # the sheet is named by its title, the file name is the fallback


# ---- 56 / 57 / 59: board size and the draft bar ----
def test_board_size_is_read_from_the_idea_text_in_the_state_and_in_hebrew():
    from altium import layout
    assert layout.board_size({"requirements": [{"topic": "", "text": 'הלוח בגודל 5 על 3 ס"מ'}]}) == (50.0, 30.0)
    assert layout.board_size({"requirements": [{"topic": "", "text": "גודל הלוח: 5 על 3 סנטימטר"}]}) == (50.0, 30.0)
    assert layout.board_size({"requirements": [{"topic": "", "text": "לוח בגודל 40 על 25 מילימטר"}]}) == (40.0, 25.0)
    assert layout.board_size({"requirements": [{"topic": "", "text": "גודל לוח כ-40x30 מ\"מ"}]}) == (40.0, 30.0)
    model = (REPO / "scripts" / "model.py").read_text(encoding="utf-8")
    assert "store.board_from_text(dict(idea))" in model            # the fields are filled without waiting for a Save


def test_nothing_cleared_says_nothing_and_an_empty_draft_has_no_bar():
    idea = _src("js/views/idea.js")
    setter = idea[idea.index("onAct('set-board-size'"):idea.index("onAct('confirmidea'")]
    assert "!w && !h && !(cur.width_mm || cur.height_mm)) return" in setter
    assert setter.index("!w && !h && !(cur.width_mm") < setter.index("'Board size cleared'")
    bar = _fn(idea, "draftBarHTML")
    assert "D.active && (D.changes || 0) > 0" in bar and "Not saved yet" in bar and "D.first" in bar
    assert ".idea-reqs{flex:0 1 auto;display:flex;flex-direction:column;min-height:150px;max-height:36%}" in _src("styles/idea.css")


def test_the_draft_info_says_when_nothing_was_ever_saved(tmp_path, monkeypatch):
    import store
    monkeypatch.setattr(store, "idea_exists", lambda project: False)
    monkeypatch.setattr(store, "idea_versions", lambda project: [])
    monkeypatch.setattr(store, "idea_draft_path", lambda project: tmp_path / "none.json")
    assert store.idea_draft_info("p")["first"] is True


# ---- 61 / 62 ----
def test_outputs_shows_the_pin_risks_and_the_last_board_check_survives_a_reload():
    out = _src("js/views/outputs.js")
    assert out.count("outPinRisks()") >= 2 and "pinRisksHTML()" in out
    prev = _src("js/views/previews.js")
    assert "pvSeedNote(page)" in _fn(prev, "pvStepNote") and "S.board_check" in prev
    assert "drcSummary(c)" in _src("js/views/rules.js")      # one sentence for the Rules header and the Layout note


@needs_node
def test_the_avatar_of_a_title_with_a_slash_is_two_letters(tmp_path):
    shell = _src("js/shell.js")
    script = _const(shell, "initials") + ";process.stdout.write(JSON.stringify([initials('PCB/Blinker'), initials('/ב'), initials('blink'), initials('')]));"
    assert _node(script, tmp_path) == ["PB", "ב", "BL", "?"]
    assert "split(/[\\s_/\\\\-]+/)" in shell


def test_the_model_is_a_choice_with_the_engine_default_first():
    pg = _src("js/views/pages.js")
    m = _fn(pg, "setModelSel")
    assert "['', 'Engine default']" in m and "(set earlier)" in m and "setSel(" in m
    assert "list=\"set-model-list\"" not in pg
