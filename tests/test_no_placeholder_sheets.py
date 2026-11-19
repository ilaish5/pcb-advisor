"""No empty placeholder SchDocs next to the drawn sheets (a live run split a design into four sheets via chat and was left with
Main.SchDoc, 02.SchDoc, 03.SchDoc and 04.SchDoc, all empty, beside the titled sheets the draw made, and the student was told to remove
them by hand): altium.add_sheet for a planned sheet makes the file the draw uses (<id> <title>.SchDoc) or nothing when it has one, a
bare '<id>.SchDoc' is that sheet's file, and the empty Main.SchDoc a new project starts with is drawn on by the first sheet."""
import pathlib

import pytest

import store
import workspace
from altium import bridge
from altium.prjpcb import read_prjpcb
from test_altium_bridge import FakeAltium
from test_altium_draw import SHEET, SYMS, simulate

SHEET2 = {**SHEET, "id": "02", "title": "Logic", "parts": [dict(p, ref={"U1": "U2", "R1": "R3", "R2": "R4"}[p["ref"]]) for p in SHEET["parts"]]}
SYMS2 = {**SYMS, "U2": SYMS["U1"], "R3": SYMS["R1"], "R4": SYMS["R2"]}


@pytest.fixture
def started(empty, home, monkeypatch):
    """A project linked to Altium before any sheet was planned (its one sheet is the empty Main.SchDoc), then split into two sheets."""
    fake = FakeAltium()
    saved = {}

    def run(commands, **kw):
        fake(commands, **kw)
        if any(c[0] == "PLACE" for c in commands):
            saved.update(simulate(commands))
        return []
    monkeypatch.setattr(bridge, "run_commands", run)
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    bridge.new_project(empty)
    store.write_sheet(empty, "01", SHEET)
    store.write_sheet(empty, "02", SHEET2)
    lp = bridge.library_paths(empty)
    lp["schlib"].parent.mkdir(parents=True, exist_ok=True)
    lp["schlib"].write_bytes(b"schlib")
    monkeypatch.setattr(bridge, "read_schlib", lambda path: {"symbols": [SYMS["U1"], SYMS["R1"]]})
    monkeypatch.setattr(store, "bom_lines", lambda project: [{"key": r, "refs": [r]} for r in SYMS2])
    monkeypatch.setattr(store, "library_manifest", lambda project: {r: {"symbol": SYMS2[r]["name"], "footprint": "FP"} for r in SYMS2})
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "read_schdoc", lambda path: {"components": []})
    import checks.schematic as cs
    monkeypatch.setattr(cs, "check_schematic", lambda doc: {"findings": []})
    drawn_on = set()
    from altium import draw
    monkeypatch.setattr(draw, "verify_sheet", lambda plan, saved_, fps: [])
    real_plan = draw.plan_sheet
    monkeypatch.setattr(draw, "plan_sheet", lambda sh, syms, lib, doc, **kw: (drawn_on.add(pathlib.Path(doc).name),
                                                                              real_plan(sh, syms, lib, doc, **kw))[1])
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: pathlib.Path(path).name not in drawn_on)
    return empty, fake, drawn_on


def _sheets(project):
    return sorted(read_prjpcb(bridge._linked(project))["sheets"])


def test_the_sheets_of_a_split_are_drawn_without_leaving_empty_placeholders(started):
    project, fake, drawn_on = started
    assert _sheets(project) == ["Main.SchDoc"]
    out = bridge.add_sheet(project, "02")                            # what the chat sent after the split ("sheet added: 02")
    assert pathlib.Path(out["file"]).name == "02 Logic.SchDoc"
    res = bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "02 Logic.SchDoc"}              # sheet 01 on the empty sheet the project started with
    assert _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]      # nothing new, nothing empty left
    assert res["stale"]["left"] == [] and not any("left in the project" in w for w in res["warnings"])
    params = [c for c in fake.flat() if c[0] == "PARAM" and c[2] == "Title"]
    assert [(pathlib.Path(c[1]).name, c[3]) for c in params][-1:] == [("Main.SchDoc", "Power")]       # its title block names sheet 01
    # a redraw finds the same files (the log keeps which file holds which sheet): no second copy of sheet 01
    drawn_on.clear()
    bridge.draw_schematic(project, replace=True)
    assert drawn_on == {"Main.SchDoc", "02 Logic.SchDoc"} and _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]
    assert bridge._sheet_doc(project, bridge._linked(project), "02").name == "02 Logic.SchDoc"


def test_adding_a_sheet_that_has_its_file_already_makes_nothing(started):
    project, fake, drawn_on = started
    bridge.draw_schematic(project)
    fake.runs.clear()
    for name in ("01", "02", "Logic", "02 Logic"):
        out = bridge.add_sheet(project, name)
        assert out.get("existing")
    assert out["file"].endswith("02 Logic.SchDoc") and not any(c[0] == "SCH" for c in fake.flat())
    assert _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]


def test_a_bare_id_sheet_made_earlier_is_that_sheets_file(started):
    project, fake, drawn_on = started
    prj = bridge._linked(project)
    bridge.run_commands([("PROJECT", str(prj)), ("SCH", str(prj.parent / "02.SchDoc")), ("SAVEPRJ", str(prj))])   # an older add_sheet
    bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "02.SchDoc"} and _sheets(project) == ["02.SchDoc", "Main.SchDoc"]


def test_the_placeholder_is_never_taken_when_it_holds_a_drawing_or_the_student_made_it(started, monkeypatch):
    project, fake, drawn_on = started
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: False)       # the student drew on Main.SchDoc
    bridge.draw_schematic(project)
    assert drawn_on == {"01 Power.SchDoc", "02 Logic.SchDoc"}
    assert "Main.SchDoc" in _sheets(project)


def test_a_free_name_still_makes_a_new_sheet(started):
    project, fake, drawn_on = started
    out = bridge.add_sheet(project, "Extra notes")
    assert pathlib.Path(out["file"]).name == "Extra notes.SchDoc" and not out.get("existing")
