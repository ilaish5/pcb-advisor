"""E11, E13-E19 of docs/E2E-KILN-LTE-DEFECTS-2026-11-24.md: one count for unverified parts, the datasheet page finder, the outputs
(PDF container, side files, unsaved marks), the banner layout, banners that follow the state, plain progress words, "cannot" is not "I will",
and the Idea leftovers."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import pin_decisions
import serve
import store
from gateway import events

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
NODE = shutil.which("node")


def _js(name):
    return (UI / "js" / name).read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    eol = src.index("\n", i)
    if src[i:eol].rstrip().endswith("}") and src[i:eol].count("{") == src[i:eol].count("}"):
        return src[i:eol + 1]                                  # a one-line function
    return src[i:src.index("\n}\n", i) + 3]


def _node(tmp_path, script):
    f = tmp_path / "t.js"
    f.write_text(script, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ------------------------------------------------------------------ E11: one count

def test_pin_counts_counts_parts_by_designator_and_separates_conflicts():
    rows = [{"line": "D", "refs": ["D1", "D2", "D3"], "status": "unverified"}, {"line": "U1", "refs": ["U1"], "status": "unverified"},
            {"line": "U8", "refs": ["U8"], "status": "mismatch"}]
    assert store.pin_counts(rows) == {"parts": 5, "to_confirm": 4, "conflicts": 1, "lines": 3}
    assert store.pin_counts([]) == {"parts": 0, "to_confirm": 0, "conflicts": 0, "lines": 0}


def test_waiting_carries_the_one_count_and_the_agent_context_quotes_it(empty):
    from test_pin_waiting import _leds
    _leds(empty, {"D1": "N1", "D2": "N2", "D3": "N3"})
    w = pin_decisions.waiting(empty)
    assert w["parts"] == 3 and w["to_confirm"] == 3 and w["conflicts"] == 0 and w["questions"] == 1       # one row, three parts
    assert w["parts"] == store.pin_counts(store.pins_to_resolve(empty))["parts"]
    import agent
    ctx = json.loads(agent._summary({"project": empty, "stages": [], "sources": []}))
    assert ctx["pins_waiting_count"] == {"parts": 3, "to_confirm": 3, "conflicts": 0, "lines": 3} and len(ctx["pins_waiting"]) == 3


def test_every_page_reads_the_server_count_not_its_own():
    pins, checks, outputs, bom = _js("views/pins.js"), _js("views/checks.js"), _js("views/outputs.js"), _js("views/bom.js")
    assert "pinsCount('to_confirm')" in _fn(pins, "pinsConfirmAllBtn") and "pinsCount('to_confirm')" in pins[pins.index("onAct('accept-all-pins'"):]
    assert "pinsCount('parts')" in checks and "reduce(" not in _fn(pins, "pinsWaitingBar")
    # the Outputs page counts nothing itself: pins are a warning there, its text comes from the server (stage pins_warning)
    assert "pins_warning" in outputs and "dfmUnverified()" not in outputs
    assert "w.questions" not in checks                                     # the heading no longer prints the number of rows
    assert "to verify (library)" in bom                                           # the BOM counter says what it counts (lines, not parts)


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_button_dialog_and_banner_show_the_same_n_and_nothing_while_refreshing(tmp_path):
    pins = _js("views/pins.js")
    fns = "".join(_fn(pins, n) for n in ("pinsWaiting", "pinsBulkGroups", "pinsCount", "pinsNum", "pinsConfirmAllBtn", "pinsWaitingBar", "pinsAcceptTitle"))
    state = {"pin_decisions": {"waiting": {"parts": 24, "to_confirm": 22, "conflicts": 1, "questions": 15, "auto_verified": 0, "fetchable": 0,
             "groups": [{"refs": [f"R{i}"], "count": 1, "own_look": False} for i in range(14)] + [{"refs": ["U8"], "count": 1, "own_look": True}],
             "bulk": [], "blind": ["U1"]}}}
    script = ("let S=" + json.dumps(state) + ";let pinsBusy=0;const btn=(t)=>t;const esc=x=>x;const refsLabel=r=>r.join(',');"
              "const dfmRecheckBusyNow=()=>false;" + fns +
              "const a=pinsConfirmAllBtn(), b=pinsAcceptTitle(pinsCount('to_confirm'), pinsWaiting()), c=pinsWaitingBar(); pinsBusy=1;"
              "const d=pinsConfirmAllBtn(), e=pinsWaitingBar();process.stdout.write(JSON.stringify([a,b,c,d,e]));")
    a, b, c, d, e = _node(tmp_path, script)
    assert "Confirm all (22)" == a and "Accept 22 parts" in b and "22 parts wait" in c and "1 part needs" in c
    assert "(…)" in d and "…" in e and "22" not in d + e and "26" not in d + e                   # no old number while the fresh state is on its way


# ------------------------------------------------------------------ E13: datasheet page

TOC = ("Table of Contents\n1. GENERAL DESCRIPTIONS ........ 4\n3. PACKAGE TYPES AND PIN CONFIGURATIONS ......... 5\n"
       "3.1 Pin Configuration SOIC 208-mil ........ 5\n3.2 Pad Configuration WSON 6x5-mm ...... 5\n3.3 Pin Description SOIC 208-mil ........ 6\n")


def test_the_pin_page_finder_skips_contents_and_prefers_the_pin_table():
    text = ("W25Q128JV\f" + TOC + "\ffeatures\fblock diagram\f3.1 Pin Configuration SOIC 208-mil\nTop View\n/CS 1 8 VCC\f"
            "3.3 Pin Description SOIC 208-mil\nPin No. Pin Name I/O Function\n1 /CS I Chip Select\n7 /HOLD or /RESET (IO3)\n")
    assert pin_decisions.is_contents_page(TOC)
    got = pin_decisions.candidate_pages(text, "SOIC-8")
    assert 2 not in got and got[:2] == [6, 5]          # the pin table with the package first, the drawing next
    assert pin_decisions.candidate_pages("ABCD features\fblock\fPin Configuration and Functions\n1 VCC\n2 GND\n") == [3]


def test_an_ordinary_page_with_a_few_dots_is_not_contents():
    assert not pin_decisions.is_contents_page("Pin Configuration\n1 VCC ..... supply\n2 GND ..... ground\nNote 3.3 V")


# ------------------------------------------------------------------ E14: outputs

def test_the_pdf_container_is_run_and_the_template_opens_nothing(tmp_path):
    from altium import bridge
    import outjob
    f = tmp_path / "x.OutJob"
    f.write_text(outjob.OUTJOB_TEMPLATE.format(project="x"), encoding="latin-1")
    boxes = bridge.outjob_containers(f)
    assert [(m, k) for m, _, k in boxes] == [("Folder Structure", "GeneratedFiles"), ("PDF", "Publish")]     # the Print Job and Video media write nothing
    t = outjob.OUTJOB_TEMPLATE
    assert "OpenOutput2=0" in t and "PromptOverwrite2=0" in t and "OpenOutput3=0" in t and "AddToProject3=0" in t     # nothing opens, asks, or edits the project


def test_altiums_side_files_are_no_outputs():
    import outputs_check
    assert outputs_check.is_side_file("x-macro.APR_LIB") and outputs_check.is_side_file("Status Report.Txt") is True
    assert not outputs_check.is_side_file("x.GTL") and not outputs_check.is_side_file("x_Schematics.pdf")
    res = outputs_check.verify("p", [], outjob=None)
    assert "Schematic PDF" in res["missing"]


def test_the_bridge_publishes_the_pdf_and_clears_the_marks_the_outputs_left():
    pas = (ROOT / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="latin-1")
    assert "Kind = 'Publish'" in pas and "PublishToPDF" in pas and "RunOutJob(Field(Line, 1), Field(Line, 2), Field(Line, 3), Field(Line, 4))" in pas
    assert "procedure Unmark" in pas and "'UNMARK'" in pas and "(Cmd = 'RULESIN')" in pas
    py = (ROOT / "scripts" / "altium" / "bridge.py").read_text(encoding="utf-8")
    assert '("UNMARK", str(d))' in py and "not in unsaved" in py              # only a document that was saved before the run


# ------------------------------------------------------------------ E15: the banner

def test_a_banner_wraps_its_text_and_keeps_its_buttons():
    css = (UI / "styles" / "base.css").read_text(encoding="utf-8")
    assert re.search(r"\.note\{flex-wrap:wrap\}", css)
    text = re.search(r"\.note>span:not\(\.acts\)\{([^}]*)\}", css).group(1)
    assert "flex:1 1 14em" in text and "min-width:min(14em,100%)" in text and "overflow-wrap:anywhere" in text
    assert "max-width:100%" in re.search(r"\.note \.acts\{([^}]*)\}", css).group(1)


# ------------------------------------------------------------------ E16: banners follow the state

@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_a_failure_banner_goes_when_its_cause_is_gone(tmp_path):
    pv = _js("views/previews.js")
    fns = "".join(_fn(pv, n) for n in ("pvNoteCause", "pvCauseGone")) + re.search(r"const pvNetlistSheets = .*\n", pv).group(0) + re.search(r"const pvSheetSig = .*\n", pv).group(0)
    script = ("let S={sheets:[]};" + fns +
              "const none={kind:'bad',text:'There is no netlist sheet to draw: write the netlist first'};pvNoteCause(none);"
              "const r=[pvCauseGone(none)];"
              "S={sheets:[{id:'03',sections:[],parts:{R1:{nets:['A']}}}]};r.push(pvCauseGone(none));"          # a sheet appeared: gone
              "const sh={kind:'bad',text:'Sheet 03 cannot be drawn: pin 2 missing'};pvNoteCause(sh);r.push(pvCauseGone(sh));"   # the same sheet: stands
              "S={sheets:[{id:'03',sections:[],parts:{R1:{nets:['A','B']}}}]};r.push(pvCauseGone(sh));"         # the sheet changed: gone
              "S={sheets:[]};r.push(pvCauseGone(sh));"                                                         # the sheet is gone: gone
              "const ok={kind:'ok',text:'done'};pvNoteCause(ok);r.push(pvCauseGone(ok));process.stdout.write(JSON.stringify(r));")
    assert _node(tmp_path, script) == [False, True, False, True, True, False]
    assert "pvCauseGone(pvNote[page])" in pv                                # the page asks the state on every draw, not only when a step succeeded


# ------------------------------------------------------------------ E17: plain progress words

@pytest.mark.parametrize("label,plain", [
    ("Reading W25Q128JV.pdf", "Reading the datasheet"), ("Reading C:/x/notes/idea.json", "Reading the project files"),
    ("Searching for ^pin\\s*(?:no|name)", "Searching the project"), ("Searching the web: w25q128 datasheet", "Searching the web"),
    ("Opening www.winbond.com", "Opening a web page"), ("Editing idea.json", "Updating a file"), ("TodoWrite", "Working"),
    ("mcp__github__get_file_contents", "Working"), ("Grep", "Searching the project"), ("Running jlc.py search x", "Searching JLC"),
    ("Running ls /tmp", "Running a command"), ("Thinking", "Thinking"), ("Writing the answer", "Writing the answer")])
def test_the_progress_line_says_what_is_done_not_which_tool(label, plain):
    assert events.human(label) == plain
    assert events.human(plain) == plain                                       # applying it twice changes nothing


def test_the_turn_progress_holds_plain_words_and_the_log_keeps_the_detail():
    key = ("p", "s")
    serve._turn_start(key)
    try:
        serve._turn_event(key, {"kind": "tool", "label": "Searching for ^pin.*", "tool": "Grep", "ts": 1})
        p = serve.turn_progress(key)
        assert p["current"] == "Searching the project" and p["steps"][-1]["label"] == "Searching the project"
    finally:
        serve._turn_end(key)
    src = (ROOT / "scripts" / "gateway" / "claude_code.py").read_text(encoding="utf-8")
    assert '"label": lab, "input"' in src and "self.steps.append(events.human(lab))" in src       # calls keep the full label


# ------------------------------------------------------------------ E18: "I cannot draw by hand" is not "I will"

@pytest.mark.parametrize("text", [
    "I cannot draw by hand, please draw the schematic", "I cannot draw by myself, you draw it", "I can't draw it myself",
    "I am unable to draw myself", "אני לא יכול לשרטט בעצמי, תשרטט אתה", "לא יכול לשרטט בעצמי", "אני לא מסוגל לשרטט בעצמי"])
def test_a_negation_is_not_a_self_do(text):
    assert serve._self_verdict("draw", text) == ""
    assert not serve._STOP_ANY.search(text, "draw") or "don" in text.lower()


@pytest.mark.parametrize("text", ["I'll draw it myself", "אני אשרטט בעצמי", "I draw it myself", "don't draw", "אל תשרטט", "I can't wait, don't draw it myself"])
def test_a_real_self_do_or_a_hold_back_still_counts(text):
    assert serve._self_verdict("draw", text) == "self"


def test_cannot_applies_to_place_and_route_too():
    assert serve._self_verdict("place", "I cannot place the parts myself, you do it") == ""
    assert serve._self_verdict("route", "אני לא יכול לנתב בעצמי") == ""
    assert serve._self_verdict("route", "I'll route myself") == "self"


# ------------------------------------------------------------------ E19: Idea leftovers

def test_the_agent_may_not_copy_old_figures_without_saying_so():
    skill = (ROOT / "runtime" / "skills" / "idea-and-requirements" / "SKILL.md").read_text(encoding="utf-8")
    assert "based on an old one" in skill and "never the old figures" in skill


def test_the_size_a_text_states_is_read_before_any_save(empty):
    from altium import layout
    assert layout.board_size({"goal": "Controller, board 30x25 mm"}) == (30.0, 25.0)
    src = _js("views/idea.js")
    assert "/api/idea/board/read" in src and "boardFieldsFollowText" in src
    assert "row.contains(document.activeElement)" in src and "cur.source !== 'text'" in src       # never over a size the student typed
    srv = (ROOT / "scripts" / "serve.py").read_text(encoding="utf-8")
    assert '"/api/idea/board/read"' in srv


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_every_ui_script_still_parses(tmp_path):
    for name in ("views/pins.js", "views/checks.js", "views/previews.js", "views/idea.js", "views/outputs.js", "views/bom.js"):
        r = subprocess.run([NODE, "--check", str(UI / "js" / name)], capture_output=True, text=True)
        assert r.returncode == 0, name + r.stderr


@pytest.mark.parametrize("text", ["I can't wait, draw it", "I can't see the pins, draw them"])
def test_cant_not_before_the_action_is_no_inability(text):
    assert not serve.says_cannot(text)


@pytest.mark.parametrize("text", ["I can't draw", "I can't do it myself", "I cannot really route by hand"])
def test_cant_before_the_action_or_myself_is_an_inability(text):
    assert serve.says_cannot(text)


def test_a_package_family_word_alone_does_not_score_a_page():
    import pin_decisions
    text = "SOIC dimensions\fSOIC thermal notes\fPin Configuration and Functions\n8-pin SOIC\n1 VCC\n"
    assert pin_decisions.candidate_pages(text, "SOIC-8") == [3]
    assert pin_decisions.candidate_pages("SOIC notes\fSOIC notes", "SOIC") == []


def test_inspector_clears_pv_note_and_dfm_waiting_offers_confirm_pins_with_selected_ds():
    pv_css = (UI / "styles" / "previews.css").read_text(encoding="utf-8")
    assert ".work:has(>#detail:not([hidden])) .pv>.pv-note{padding-right:" in pv_css
    checks = _js("views/checks.js")
    fn = _fn(checks, "dfmWaitingHTML")
    assert "curDs" in fn and "(g.kind === 'ic' && curDs)" in fn
    assert "Change datasheet" in fn and "${d === curDs ? ' selected' : ''}" in fn
