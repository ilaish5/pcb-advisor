"""Fixes from the 23/11 browser verification: Next on every page, no phantom idea draft, Revert restores the canvas, the elapsed clock on
every Altium step, Restore of an archived project while the group is collapsed."""
import json
import pathlib
import re
import shutil
import subprocess

import constraints
import store

REPO = pathlib.Path(__file__).resolve().parent.parent


def _saved_idea_with_constraints_and_board_text(project):
    idea = store.load_idea(project)
    idea["goal"] = "ESP32-C3 sensor board, 40 x 30 mm, USB-C power"
    idea["agreed"] = [{"topic": "Size", "text": "Board 40x30 mm", "status": "agreed", "by": "student"}]
    idea["constraints"] = constraints.validate({"items": [
        {"kind": "mounting_hole", "status": "confirmed", "by": "agent"},
        {"kind": "keepout", "edge": "top", "depth_mm": 5, "status": "confirmed", "by": "agent"}]})
    idea["confirmed"] = True
    store.save_idea(project, idea)
    return idea


def test_a_freshly_loaded_idea_has_no_changes(empty):
    _saved_idea_with_constraints_and_board_text(empty)
    import model
    st = model.build(empty)
    assert st["idea_draft"]["changes"] == 0 and not st["idea_draft"]["active"]
    assert not store.has_idea_draft(empty)
    working = store.board_from_text(dict(store.load_idea_working(empty)))      # the board size read from the text is no change either
    assert store.idea_changes(store.load_idea(empty), working) == 0


def test_a_draft_that_only_differs_by_derived_fields_is_dropped(empty):
    _saved_idea_with_constraints_and_board_text(empty)
    again = store.board_from_text(json.loads(json.dumps(store.load_idea(empty))))
    again["constraints"] = constraints.validate(again["constraints"])
    store.save_idea_draft(empty, again)
    assert not store.has_idea_draft(empty)
    assert store.idea_draft_info(empty)["changes"] == 0


def test_the_editor_posting_the_diagram_back_unchanged_is_no_change(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "mcu", "text": "MCU"}])
    store.save_idea_from_draft(empty)
    d = json.loads(json.dumps(store.load_idea(empty)["diagram"]))
    for s in d["shapes"]:
        s["x"] = float(s["x"]) + 0.00001            # float noise
        s["w"] = int(s["w"])
    store.save_idea_draft(empty, dict(store.load_idea_working(empty), diagram=d))
    assert not store.has_idea_draft(empty)


def test_a_real_move_still_counts(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "mcu", "text": "MCU"}])
    store.save_idea_from_draft(empty)
    d = json.loads(json.dumps(store.load_idea(empty)["diagram"]))
    d["shapes"][0]["x"] = float(d["shapes"][0]["x"]) + 120
    store.save_idea_draft(empty, dict(store.load_idea_working(empty), diagram=d))
    assert store.idea_draft_info(empty)["changes"] == 1


# ---------------------------------------------------------------- helpers for the node-run tests

def _src(rel):
    return (REPO / "ui" / rel).read_text(encoding="utf-8")


def _fn(text, name):
    i = text.index(f"function {name}(")
    return text[i:text.index("\n}\n", i) + 3]


def _const(text, name):
    i = text.index(f"const {name} =")
    return text[i:text.index(";\n", i) + 2]


def _run(script, tmp_path):
    (tmp_path / "t.js").write_text(script, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _header_harness():
    shell = _src("js/shell.js")
    return ("globalThis.addEventListener = () => {};\nglobalThis.document ={addEventListener() {}, querySelector() { return null; }, documentElement: {}};\n"
            "globalThis.window = globalThis; globalThis.localStorage = {getItem() { return null; }, setItem() {}};\n"
            + _src("js/kit.js") + "\n" + _const(shell, "STAGES") + _const(shell, "STAGE_TITLES") + _const(shell, "stageOf")
            + _fn(shell, "stageNextBtn") + _fn(shell, "pageNextBtn") + "\nvar S = null;\n")


# ---------------------------------------------------------------- 1. Next on every stage page

def test_every_stage_page_header_has_a_next_button(tmp_path):
    script = _header_harness() + r"""
const out = {};
const to = h => (h.match(/data-act="stage-next"[^>]*data-to="(\w+)"/) || h.match(/data-to="(\w+)"[^>]*data-act="stage-next"/) || [])[1] || '';
const states = {self: sid => ({label: 'Do it here', act: 'go:' + sid}), empty: () => ({label: '', act: ''}), other: () => ({label: 'Elsewhere', act: 'go:bom'})};
for (const [kind, mk] of Object.entries(states)) {
  S = {stages: STAGES.map(([sid], i) => ({id: sid, state: 'in_progress', primary: i === 3, next: mk(sid)}))};
  for (const [id, title] of STAGES) out[kind + ':' + id] = to(viewHeader({title}));
}
S = {stages: STAGES.map(([sid], i) => ({id: sid, state: 'in_progress', primary: i === 4, next: {label: 'x', act: 'go:' + sid}}))};
out.library = to(viewHeader({title: 'Library'}));
out.sources = to(viewHeader({title: 'Sources'}));
out.settings = to(viewHeader({title: 'Settings'}));
S = {stages: []};
out.nostages = to(viewHeader({title: 'Library'}));
console.log(JSON.stringify(out));
"""
    out = _run(script, tmp_path)
    order = ["idea", "bom", "sch", "pcb", "rules", "outputs", "checks"]
    for kind in ("self", "empty"):
        for i, sid in enumerate(order[:-1]):
            if sid != "idea":                     # Idea draws its own (Confirm idea / Next: BOM)
                assert out[f"{kind}:{sid}"] == order[i + 1], (kind, sid, out)
        assert out[f"{kind}:checks"] == ""         # DFM is the last stage: nothing comes after it
    assert out["other:sch"] == "bom"               # the server's own target still wins
    assert out["library"] == "rules" and out["sources"] == "rules"     # the stage where the work goes on
    assert out["settings"] == "" and out["nostages"] == ""


def test_all_view_headers_pass_titles_the_next_button_knows():
    stage_titles = {"Idea", "BOM", "Schematic", "Layout", "Rules", "Outputs", "DFM"}
    seen = set()
    for f in (REPO / "ui" / "js" / "views").glob("*.js"):
        seen |= set(re.findall(r"viewHeader\(\{title: '([^']+)'", f.read_text(encoding="utf-8")))
    assert stage_titles <= seen
    assert seen - stage_titles <= {"Library", "Sources", "Settings"}, seen


# ---------------------------------------------------------------- 3. Revert restores the canvas

def test_revert_resets_the_editor_and_never_saves():
    idea = _src("js/views/idea.js")
    rev = idea[idea.index("onAct('draft-revert'"):idea.index("onAct('idea-restore'")]
    assert "/api/idea/draft/revert" in rev and "ideaResetCanvas()" in rev and "draft-save" not in rev
    reset = _fn(idea, "ideaResetCanvas")
    assert "resetData" in reset and "onSave" not in reset
    ed = _src("diagram.js")
    body = ed[ed.index("resetData(newData)"):ed.index("updateData(newData, touchedIds")]
    assert "clearTimeout(this.saveDebounceTimer)" in body and "saveNow" not in body and "isDirty = false" in body
    assert "this.serverSnapshot" in body       # updateData's "same as the server had" early return is what kept the drag


def test_revert_discards_a_dragged_diagram_and_saves_no_version(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "mcu", "text": "MCU"}])
    store.save_idea_from_draft(empty)
    versions = len(store.idea_versions(empty))
    d = json.loads(json.dumps(store.load_idea(empty)["diagram"]))
    d["shapes"][0]["x"] = float(d["shapes"][0]["x"]) + 120
    store.save_idea_draft(empty, dict(store.load_idea_working(empty), diagram=d))
    assert store.idea_draft_info(empty)["changes"] == 1
    assert store.revert_idea_draft(empty) is True
    assert store.load_idea_working(empty)["diagram"]["shapes"][0]["x"] == store.load_idea(empty)["diagram"]["shapes"][0]["x"]
    assert len(store.idea_versions(empty)) == versions         # Revert never saves a version


# ---------------------------------------------------------------- 4. the m:ss clock on every Altium step

def test_drc_started_from_rules_shows_the_elapsed_clock():
    rules = _src("js/views/rules.js")
    row = _fn(rules, "rulesDrcRow")
    assert "pvBusy === 'drc'" in row and "pvStepNote('pcb', true)" in row
    prev = _src("js/views/previews.js")
    note = _fn(prev, "pvStepNote")
    assert "busyOnly" in note and "pvElapsedHTML()" in note
    # every step's page draws its live line (spinner + m:ss) through pvStepNote, or the Rules row does it for the Layout step
    block = prev[prev.index("const PV_STEPS = {"):]
    pages = set(re.findall(r"\bpage: '(\w+)'", block[:block.index("\n};")]))
    everything = prev + _src("js/views/outputs.js") + rules
    for page in pages:
        # the schematic and layout pages ask for it through the canvas bar (pvBarHTML), the others call it under their header
        assert f"pvStepNote('{page}')" in everything or f"pvBarHTML('{page}'" in everything, page


# ---------------------------------------------------------------- 5. Restore of an archived project

def test_archived_group_is_open_when_short_and_restore_is_wired(tmp_path):
    shell = _src("js/shell.js")
    script = ("const esc = s => String(s);\nvar PROJECTS_ARCHIVED = [];\n" + _fn(shell, "projArchivedHTML")
              + "\nconst out = {};\nPROJECTS_ARCHIVED = [{name: 'a', title: 'A'}];\nout.few = projArchivedHTML();\n"
              "PROJECTS_ARCHIVED = [1, 2, 3, 4].map(n => ({name: 'p' + n, title: 'P' + n}));\nout.many = projArchivedHTML();\n"
              "console.log(JSON.stringify(out));")
    out = _run(script, tmp_path)
    assert '<details class="arch" open>' in out["few"] and 'data-act="unarchive-project"' in out["few"]
    assert '<details class="arch">' in out["many"]
    assert "onAct('unarchive-project'" in shell
