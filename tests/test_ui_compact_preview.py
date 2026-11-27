"""The Layout and Schematic pages give the drawing the height: one header row, the layer switches and the Altium run status on the canvas."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PREV = (REPO / "ui" / "js" / "views" / "previews.js").read_text(encoding="utf-8")
CSS = (REPO / "ui" / "styles" / "previews.css").read_text(encoding="utf-8")


def _fn(text, name):
    i = text.index(f"function {name}(")
    return text[i:text.index("\n}\n", i) + 3]


def _const(text, name):
    i = text.index(f"const {name} =")
    return text[i:text.index(";\n", i) + 2]


def test_the_layer_switches_live_in_the_canvas_overlay_not_the_header():
    html = _fn(PREV, "pcbHTML")
    header = html[html.index("viewHeader({title: 'Layout', meta"):html.index("`<div class=\"pv-stage\">")]
    assert "seg(" not in header and "toggle-layer" not in header and "pvLayersHTML" not in header      # the header holds the steps only
    stage = html[html.index("`<div class=\"pv-stage\">"):]
    assert "pvBarHTML('pcb', pvLayersHTML(layers))" in stage and stage.index("pv-canvas") < stage.index("pvBarHTML")    # on the canvas, in its stage
    layers = _fn(PREV, "pvLayersHTML")
    assert "<details" in layers and "toggle-layer" in layers and "data-pvk=\"pcb:layers\"" in layers      # one compact control, open state kept across redraws
    assert "pv-lhid" in layers and "hidden" in layers                                                       # and it says how many layers are hidden
    bar = _fn(PREV, "pvBarHTML")
    assert 'class="pv-bar"' in bar and "pvStepNote(page, false, true)" in bar
    # the schematic has no layers, but its run status is on its canvas too
    sch = _fn(PREV, "schHTML")
    assert "pvBarHTML('sch')" in sch and "pvStepNote(" not in sch
    # one handler as before: a press toggles the layer and the picture
    assert "onAct('toggle-layer'" in PREV and "pcbLayers[layer] = !pcbLayers[layer]" in PREV and "applyPcbLayers()" in PREV


def test_the_canvas_overlay_floats_over_the_drawing_and_the_header_is_one_row():
    bar = re.search(r"\.pv-bar\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "position:absolute" in bar and "pointer-events:none" in bar                 # over the picture; only its controls take the mouse
    assert re.search(r"\.pv-layers\s*\{[^}]*position:relative", CSS) and ".pv-layers>summary" in CSS
    head = re.search(r"\.pv>\.vh\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "flex:none" in head
    assert "align-items:center" in re.search(r"\.pv>\.vh\s+\.vh-main\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    base = (REPO / "ui" / "styles" / "base.css").read_text(encoding="utf-8")
    assert re.search(r"\.vh-main>\.acts\s*\{[^}]*margin-left:auto", base)                # the actions at the right end of the title row; Next has its own slot
    stage = re.search(r"\.pv-stage\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "flex:1" in stage and "min-height:0" in stage                               # the canvas still takes the rest of the pane
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CSS)


def test_the_page_steps_read_the_run_as_one_status_line_and_rules_and_outputs_keep_the_full_list():
    note = _fn(PREV, "pvStepNote")
    assert "slim" in note and "pvRunSlim()" in note and "pvStopBtn()" in note and "pvElapsedHTML()" in note
    run = _fn(PREV, "pvRunSlim")
    assert "pv-run-line" in run and "' more'" in run and "pvStopBtn()" in run and "pvElapsedHTML()" in run
    assert "pvRunOpen" in run and "aria-expanded" in run and "act: 'pv-run-toggle'" in run
    assert "onAct('pv-run-toggle'" in PREV
    for rel in ("rules.js", "outputs.js"):
        src = (REPO / "ui" / "js" / "views" / rel).read_text(encoding="utf-8")
        assert not re.search(r"pvStepNote\([^)]*,\s*(false|true),\s*true\)", src), rel      # their step list stays under their header


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_collapsed_the_run_is_one_line_with_the_count_and_stop_and_opens_to_the_whole_list(tmp_path):
    script = (
        "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');\n"
        "const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;\n"
        "globalThis.addEventListener = () => {}; globalThis.document = {addEventListener() {}};\n"
        + (REPO / "ui" / "js" / "kit.js").read_text(encoding="utf-8") + "\n"
        "const PV_STEPS = {place: {busy: 'Altium is placing the parts. It may take a minute and flash while it works.'}};\n"
        "let pvBusy = 'place', pvStartedAt = 0, pvStopping = false, pvRun = null, pvRunOpen = false;\n"
        "const pvClock = () => '0:35', pvDetailHTML = () => '';\n"
        + _const(PREV, "pvElapsedHTML") + _fn(PREV, "pvStepText") + _fn(PREV, "pvStepLine") + _fn(PREV, "pvStopBtn")
        + _const(PREV, "pvFirstSentence") + _fn(PREV, "pvRunSlim") + "\n"
        "const out = {};\n"
        "pvRun = {running: true, steps: [{label: 'Building the library', state: 'done', note: 'ok'}, {label: 'Placing the parts', state: 'running'},"
        " {label: 'Checking', state: 'waiting'}, {label: 'Routing', state: 'waiting'}]};\n"
        "out.closed = pvRunSlim();\n"
        "pvRunOpen = true; out.open = pvRunSlim(); pvRunOpen = false;\n"
        "pvRun = {running: true, steps: [{label: 'a', state: 'done'}, {label: 'b', state: 'running'}]};\n"
        "out.last = pvRunSlim();\n"
        "pvStopping = true; out.stopping = pvRunSlim();\n"
        "console.log(JSON.stringify(out));")
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    closed = out["closed"]
    assert closed.count("pv-run-line") == 1 and "<div class=\"pv-steps\">" not in closed          # collapsed: the one line, no list
    assert "Placing the parts" in closed and "0:35" in closed and "2 more" in closed and ">Stop<" in closed
    assert "Building the library" not in closed and "Routing" not in closed                         # the finished and the waiting steps are folded away
    assert 'aria-expanded="false"' in closed
    assert 'aria-expanded="true"' in out["open"]
    for label in ("Building the library", "Placing the parts", "Checking", "Routing"):            # open: every step, finished ones included
        assert label in out["open"]
    assert "(waiting)" in out["open"] and out["open"].count("pv-run-line") == 1
    assert '<span class="pv-run-txt">Altium is placing the parts.</span>' in out["last"]               # the line is the first sentence; the hint is its tooltip
    assert "may take a minute" in out["last"] and "This step cannot be cut short" in out["last"] and ">Stop<" not in out["last"]  # the last operation cannot be cut
    assert "Stopping…" in out["stopping"] and "aria-disabled" in out["stopping"]


# ---- the Next button has one place on every page ----

VIEWS = REPO / "ui" / "js" / "views"
KIT = (REPO / "ui" / "js" / "kit.js").read_text(encoding="utf-8")
BASE = (REPO / "ui" / "styles" / "base.css").read_text(encoding="utf-8")


def test_viewheader_has_a_fixed_slot_for_next_that_pages_cannot_move():
    vh = _fn(KIT, "viewHeader")
    assert vh.count("${next}") == 1 and 'class="vh-next">${next}</div></header>' in vh        # the last thing in the header, in its own slot
    acts = vh[vh.index('<div class="acts">'):vh.index('</div></div><div class="vh-next">')]
    assert "${next}" not in acts and "stageNextBtn" not in acts                                # not among the page's actions
    grid = re.search(r"\.vh\s*\{([^}]*)\}", BASE).group(1).replace(" ", "")
    assert "display:grid" in grid and "grid-template-columns:minmax(0,1fr)auto" in grid       # the title and actions give way; Next keeps its column
    slot = re.search(r"\.vh-next\s*\{([^}]*)\}", BASE).group(1).replace(" ", "")
    assert "grid-column:2" in slot and "grid-row:1" in slot                                    # top right, first row, whatever the actions do
    assert not re.search(r"\.vh-next[^{]*\{[^}]*(position|order|margin|transform)", BASE)      # nothing moves it
    assert not re.search(r"\.vh-next|stage-next", CSS)                                         # no page stylesheet repositions it


def test_no_view_draws_a_next_button_outside_the_slot():
    for f in sorted(VIEWS.glob("*.js")):
        src = f.read_text(encoding="utf-8")
        assert "stageNextBtn(" not in src and "pageNextBtn(" not in src, f.name                # only viewHeader asks for them
        assert "act: 'stage-next'" not in src and 'data-act="stage-next"' not in src, f.name
        assert "<header" not in src and 'class="vh"' not in src, f.name                        # every header is viewHeader's
        for m in re.finditer(r"btn\('Next\b", src):
            assert f.name == "idea.js" and src[:m.start()].endswith("next = "), (f.name, src[max(0, m.start() - 30):m.start() + 30])      # Idea's own, passed as `next`
    idea = (VIEWS / "idea.js").read_text(encoding="utf-8")
    assert "viewHeader({title: 'Idea', meta, primary, next})" in idea and "primary = btn('Next" not in idea     # Idea's Next goes through the slot too


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_next_is_rendered_once_in_the_slot_for_every_kind_of_header(tmp_path):
    script = (
        "globalThis.addEventListener = () => {}; globalThis.document = {addEventListener() {}};\n"
        + KIT + "\nconst STAGES = [['bom', 'BOM'], ['idea', 'Idea']];\n"
        "const stageNextBtn = id => btn('Next: Schematic', {kind: 'line', act: 'stage-next', stage: id, to: 'sch'});\n"
        "const pageNextBtn = () => btn('Next: Rules', {kind: 'line', act: 'stage-next', stage: 'rules', to: 'rules'});\n"
        "const out = {bom: viewHeader({title: 'BOM', actions: btn('Check', {act: 'x'}), primary: btn('Go', {kind: 'pri', act: 'y'})}),\n"
        "  src: viewHeader({title: 'Sources'}), set: viewHeader({title: 'Settings'}),\n"
        "  idea: viewHeader({title: 'Idea', next: btn('Next: BOM', {kind: 'pri', act: 'idea-next'}), primary: btn('Confirm idea', {kind: 'pri', act: 'c'})}),\n"
        "  ideaOpen: viewHeader({title: 'Idea', primary: btn('Confirm idea', {kind: 'pri', act: 'c'})})};\n"
        "console.log(JSON.stringify(out));")
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    for key, text in (("bom", "Next: Schematic"), ("src", "Next: Rules"), ("idea", "Next: BOM")):
        html = out[key]
        slot = html[html.index('<div class="vh-next">'):]
        assert text in slot and html.count("Next:") == 1, key                                    # once, and in the slot
    assert 'class="vh-next"></div>' in out["set"] and "Next:" not in out["set"]                  # a page with none keeps an empty slot
    assert 'class="vh-next"></div>' in out["ideaOpen"] and "Confirm idea" in out["ideaOpen"]      # Idea before it is agreed: Confirm is an action, no Next
