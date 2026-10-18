"""The example project that every install ships: examples/led-chaser -> projects/led-chaser."""
import json

import project
import render_sheet
import store
import workspace

NAME = "led-chaser"


def test_init_creates_the_example_and_never_overwrites(home):
    report = workspace.init()
    assert f"projects/{NAME}" in report["created"]
    assert project.exists(NAME)

    notes = project.dir_of(NAME) / "notes.md"
    notes.write_text("mine", encoding="utf-8")
    again = workspace.init()
    assert f"projects/{NAME}" not in again["created"]
    assert notes.read_text(encoding="utf-8") == "mine"


def test_example_has_no_altium_link(home):
    workspace.init()
    link = project.altium_link(NAME)
    assert not link.get("project_file") and not link.get("pcb_file")
    assert not list(project.dir_of(NAME).rglob("*.PcbDoc")) and not list(project.dir_of(NAME).rglob("*.OutJob"))


def test_example_is_in_the_project_list_and_confirmed(home):
    workspace.init()
    row = next(p for p in project.list_all() if p["name"] == NAME)
    assert row["confirmed"] and row["lines"] == 12 and row["sheets"] == 1


def test_bom_and_sheet_agree(home):
    workspace.init()
    lines = store.bom(NAME, write=False)
    refs = {r for l in lines for r in l["refs"]}
    assert len(refs) == 23                       # J1, R1-5, U1-2, C1-5, D1-10
    assert sum(len(l["refs"]) for l in lines) == len(refs)
    assert not any(l.get("lcsc") for l in lines)  # no invented part numbers
    sheet = store.load_sheet(NAME, "01")
    assert store.validate_sheet(sheet, refs) == []
    assert {p["ref"] for p in sheet["parts"]} == refs


def test_clock_and_counter_wiring(home):
    workspace.init()
    sheet = store.load_sheet(NAME, "01")
    pins = {p["ref"]: {q["num"]: q["net"] for q in p["pins"]} for p in sheet["parts"]}
    assert pins["U1"]["2"] == pins["U1"]["6"] == "THR"
    assert pins["U2"]["14"] == pins["U1"]["3"] == "CLK"
    anodes = [next(q["net"] for q in p["pins"] if q["name"] == "A") for p in sheet["parts"] if p["ref"].startswith("D")]
    assert anodes == [f"Q{i}" for i in range(10)]
    assert [pins["U2"][str(n)] for n in (3, 2, 4, 7, 10, 1, 5, 6, 9, 11)] == anodes


def test_sheet_renders(home):
    workspace.init()
    svg = render_sheet.render(NAME, "01")
    assert svg.startswith("<svg") and 'data-ref="U2"' in svg and 'data-ref="D10"' in svg
