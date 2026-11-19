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
    assert pathlib.Path(out["file"]).name == "Main.SchDoc" and out.get("adopted")      # the first one added takes the empty Main
    out = bridge.add_sheet(project, "03 Spare")                      # a sheet that is not planned: a file of its own
    assert pathlib.Path(out["file"]).name == "03 Spare.SchDoc"
    res = bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "01 Power.SchDoc"}
    assert _sheets(project) == ["01 Power.SchDoc", "03 Spare.SchDoc", "Main.SchDoc"]      # no empty look-alike of 01 or 02
    assert not any("Main" in w for w in res["warnings"])
    params = [c for c in fake.flat() if c[0] == "PARAM" and c[2] == "Title"]
    assert [(pathlib.Path(c[1]).name, c[3]) for c in params][-1:] == [("Main.SchDoc", "Logic")]       # its title block names sheet 02
    # a redraw finds the same files (the log keeps which file holds which sheet): no second copy
    drawn_on.clear()
    bridge.draw_schematic(project, replace=True)
    assert drawn_on == {"Main.SchDoc", "01 Power.SchDoc"} and len(_sheets(project)) == 3
    assert bridge._sheet_doc(project, bridge._linked(project), "02").name == "Main.SchDoc"


def test_a_split_drawn_straight_away_draws_sheet_01_on_main(started):
    project, fake, drawn_on = started
    res = bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "02 Logic.SchDoc"}              # sheet 01 on the empty sheet the project started with
    assert _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]      # nothing new, nothing empty left
    assert res["stale"]["left"] == [] and not any("left in the project" in w for w in res["warnings"])
    params = [c for c in fake.flat() if c[0] == "PARAM" and c[2] == "Title"]
    assert [(pathlib.Path(c[1]).name, c[3]) for c in params][-1:] == [("Main.SchDoc", "Power")]


def test_adding_a_sheet_that_has_its_file_already_makes_nothing(started):
    project, fake, drawn_on = started
    bridge.draw_schematic(project)
    fake.runs.clear()
    for name in ("01", "02", "02 Logic"):
        out = bridge.add_sheet(project, name)
        assert out.get("existing")
    assert out["file"].endswith("02 Logic.SchDoc") and not any(c[0] == "SCH" for c in fake.flat())
    with pytest.raises(bridge.BridgeError, match="02 Logic.SchDoc"):      # by its title alone: said, not passed off as done
        bridge.add_sheet(project, "Logic")
    assert _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]


def test_adding_the_first_planned_sheet_takes_over_the_empty_main(started):
    project, fake, drawn_on = started
    fake.runs.clear()
    out = bridge.add_sheet(project, "01")
    assert out.get("adopted") and pathlib.Path(out["file"]).name == "Main.SchDoc"
    assert not any(c[0] == "SCH" for c in fake.flat()) and _sheets(project) == ["Main.SchDoc"]
    assert store.sheet_docs(project) == {"01": "Main.SchDoc"}
    bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "02 Logic.SchDoc"}
    assert _sheets(project) == ["02 Logic.SchDoc", "Main.SchDoc"]


def test_the_page_knows_main_holds_sheet_01(started):
    import model
    project, fake, drawn_on = started
    bridge.draw_schematic(project)
    assert "01" in model.altium_ok(project)["draw_sheets"][-1]["sheets"]      # the note "Sheet 01 cannot be drawn" clears
    assert [s["id"] for s in model.sheets(project)] == ["01", "02"]          # no extra "Main" tab


def test_main_saved_with_a_drawing_is_not_taken_and_an_adopted_sheet_is_never_wiped(started, monkeypatch):
    project, fake, drawn_on = started
    import altium.schdoc
    hand = set()
    monkeypatch.setattr(bridge, "save_open_sheets", lambda prj, docs: (hand.update(pathlib.Path(d).name for d in docs), [])[1])
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: pathlib.Path(path).name not in drawn_on | hand)
    fake.runs.clear()
    out = bridge.add_sheet(project, "01")      # the same through add_sheet: no mapping to Main, a file of its own
    assert "Main.SchDoc" in hand and not out.get("adopted") and pathlib.Path(out["file"]).name == "01 Power.SchDoc"
    assert "Main.SchDoc" not in store.sheet_docs(project).values()
    bridge.draw_schematic(project)       # the unsaved hand drawing on Main is saved first: Main is no longer empty
    assert drawn_on == {"01 Power.SchDoc", "02 Logic.SchDoc"}


def test_the_skeleton_saves_main_before_taking_it(started, monkeypatch):
    project, fake, drawn_on = started
    import altium.schdoc
    hand = set()
    monkeypatch.setattr(bridge, "save_open_sheets", lambda prj, docs: (hand.update(pathlib.Path(d).name for d in docs), [])[1])
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: pathlib.Path(path).name not in hand)
    bridge.skeleton(project)
    assert "Main.SchDoc" in hand and "Main.SchDoc" not in store.sheet_docs(project).values()


def test_an_adopted_sheet_is_drawn_without_replace(started, monkeypatch):
    project, fake, drawn_on = started
    from altium import draw
    seen = {}
    real = draw.plan_sheet
    monkeypatch.setattr(draw, "plan_sheet", lambda sh, syms, lib, doc, **kw: (seen.__setitem__(pathlib.Path(doc).name, kw["replace"]),
                                                                              real(sh, syms, lib, doc, **kw))[1])
    bridge.draw_schematic(project, replace=True)
    assert seen["Main.SchDoc"] is False
    assert [c[2] for c in fake.flat() if c[0] == "DRAWCHECK" and c[1].endswith("Main.SchDoc")] == ["0"]


def test_a_bare_id_sheet_with_a_drawing_the_tool_did_not_make_is_left_alone(started, monkeypatch):
    project, fake, drawn_on = started
    prj = bridge._linked(project)
    fake([("PROJECT", str(prj)), ("SCH", str(prj.parent / "02.SchDoc"))])          # the student's own 02.SchDoc, drawn on
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "is_blank_sheet", lambda path: pathlib.Path(path).name not in drawn_on | {"02.SchDoc"})
    bridge.draw_schematic(project)
    assert drawn_on == {"Main.SchDoc", "02 Logic.SchDoc"} and "02.SchDoc" in _sheets(project)


def test_the_files_are_recorded_before_the_check_and_a_lost_file_is_reported(started, monkeypatch):
    project, fake, drawn_on = started
    import checks.schematic as cs

    def broken(doc):
        raise RuntimeError("check broke off")
    monkeypatch.setattr(cs, "check_schematic", broken)
    with pytest.raises(RuntimeError):
        bridge.draw_schematic(project)
    assert store.sheet_docs(project) == {"01": "Main.SchDoc", "02": "02 Logic.SchDoc"}
    assert "02 logic.schdoc" in bridge._tool_made_sheets(project)             # the file it made is known as its own
    # renamed in Altium to a name that still starts with the id: that file is the sheet's from now on
    bridge._log(project, "sheet-docs", sheet_docs={"02": "Old name.SchDoc"})
    assert bridge._sheet_doc(project, bridge._linked(project), "02").name == "02 Logic.SchDoc"
    assert store.sheet_docs(project)["02"] == "02 Logic.SchDoc"
    bridge._log(project, "sheet-docs", sheet_docs={"01": "Renamed.SchDoc"})       # recorded, but no longer in the project
    fake.runs.clear()
    with pytest.raises(bridge.BridgeError, match="no longer in the Altium project"):
        bridge.draw_schematic(project, replace=True)
    assert not any(c[0] == "SCH" for c in fake.flat())


def test_a_title_two_sheets_share_asks_for_the_id(started, monkeypatch):
    project, fake, drawn_on = started
    monkeypatch.setattr(bridge, "_sheets", lambda p: [("01", "Logic", SHEET), ("02", "Logic", SHEET2)])
    fake.runs.clear()
    with pytest.raises(bridge.BridgeError, match="by its id"):
        bridge.add_sheet(project, "logic")
    assert fake.runs == []


def test_the_full_rp2040_route_is_marked_slow():
    import configparser
    ini = configparser.ConfigParser()
    ini.read(pathlib.Path(__file__).parents[1] / "pytest.ini")
    assert "slow:" in ini["pytest"]["markers"]
    import test_live_rp2040_routing as t
    marked = [n for n, f in vars(t).items() if n.startswith("test_") and any(m.name == "slow" for m in getattr(f, "pytestmark", []))]
    assert len(marked) == 1


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
