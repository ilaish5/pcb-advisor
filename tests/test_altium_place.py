"""altium.place_pcb / route_pcb: the consent guard per action, the DRC report parser, the PCBCHECK log parser."""
import pytest

import serve
from altium import bridge


def test_place_consent():
    said = "please place the parts for me"
    assert serve._consent("place", {"student_said": said}, said) == ""
    assert serve._consent("place", {"student_said": "place"}, said) != ""
    mine = "I'll place them myself"
    assert serve._consent("place", {"student_said": mine}, mine) != ""


def test_place_consent_is_not_route_consent():
    said = "I'll route myself, you place"
    assert serve._consent("route", {"student_said": said}, said) != ""


def test_replace_needs_words():
    said = "place them for me"
    assert serve._consent("place", {"student_said": said, "replace": True}, said) != ""
    said2 = "place them again, replace what is there"
    assert serve._consent("place", {"student_said": said2, "replace": True, "replace_said": "replace"}, said2) == ""


def test_route_consent_needs_route_word():
    said = "yes, route it for me"
    assert serve._consent("route", {"student_said": said}, said) == ""
    said = "yes please"
    assert serve._consent("route", {"student_said": said}, said) != ""


def test_parse_drc(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("Rule Violations|Un-Routed Net Constraint|13\nRule Violations|Clearance|0\nUn-Routed Net Constraint|||Net GND unrouted\n",
                 encoding="cp1252")
    r = bridge.parse_drc(f)
    assert r["unrouted"] == 13 and r["total"] == 13 and len(r["violations"]) == 1
    assert bridge.parse_drc(tmp_path / "none.txt") is None


def test_pcbcheck_info():
    log = ["pcbcheck objects=0 parts=0 tracks=0 outline_pts=4 box_mil=1000,1000,7000,5000"]
    i = bridge._pcbcheck_info(log)
    assert i["box_mil"] == (1000, 1000, 7000, 5000) and i["points"] == 4
    assert bridge._pcbcheck_info(["nothing"]) is None


def test_a_schematic_yes_is_not_consent_to_place_or_route():
    for said in ("yes", "yes, go ahead", "ok do it", "תשרטט לבד"):
        assert serve._consent("place", {"student_said": said}, said) != ""
        assert serve._consent("route", {"student_said": said}, said) != ""
    assert serve._consent("place", {"student_said": "תמקם את הרכיבים"}, "תמקם את הרכיבים") == ""
    assert serve._consent("route", {"student_said": "please route the board"}, "please route the board") == ""
    assert serve._consent("route", {"student_said": "please place the parts"}, "please place the parts") != ""    # a place yes is not a route yes


def test_pcbcheck_box_comes_from_the_corners_not_the_cached_bounding_rectangle():
    """Live bug: on a board made by create_project, OUTLINE moved the corners and the file was saved right, but
    BoardOutline.BoundingRectangle is cached and still said 1000,1000,7000,5000, so every placement was undone as "outline not
    as planned". PCBCHECK must take the box from the segments (it only falls back to the rectangle for arcs)."""
    import pathlib
    src = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="cp1252")
    body = src[src.index("procedure PcbCheck("):src.index("function NetOf(")]
    assert "O.Segments[i].Kind" in body and "bx0" in body
    assert "CoordToMils(R.Left)" not in body and "CoordToMils(R.Right)" not in body


def test_place_on_a_new_board_creates_the_outline_and_checks_it_after_the_save(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    from altium import layout
    lib = tmp_path / "L.PcbLib"
    lib.write_bytes(b"x")
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"pcb")
    fp = {"name": "FP", "pads": [{"x": 0, "y": 0, "xsize": 40, "ysize": 40, "rotation": 0, "name": "1"}], "extent": {}}
    monkeypatch.setattr(bridge, "read_pcblib", lambda p: {"footprints": [fp]})
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {})
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: None)
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {"pads": [1]})
    monkeypatch.setattr(layout, "verify_layout", lambda *a, **k: [])
    state = {"box": (1000, 1000, 7000, 5000), "parts": 0, "cmds": []}

    def altium(cmds, **kw):                 # a new board holds the placeholder; OUTLINE changes it; PCBCHECK reports what it holds
        log = []
        for c in cmds:
            state["cmds"].append(c[0])
            if c[0] == "OUTLINE":
                state["box"] = tuple(round(float(v) / 0.0254) for v in c[2:6])
            if c[0] == "PLACEFP":
                state["parts"] += 1
            if c[0] == "PCBCHECK":
                log.append("pcbcheck rect=1 objects=%d parts=%d tracks=0 outline_pts=4 box_mil=%d,%d,%d,%d"
                           % ((state["parts"], state["parts"]) + state["box"]))
        return log
    monkeypatch.setattr(bridge, "run_commands", altium)
    parts = [{"ref": "R1", "footprint": "FP", "lib_ref": "R", "pins": []}]
    res = bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, parts, size=(30, 25))
    assert res["problems"] == [] and res["outline_created"] and res["outline"] == [0.0, 0.0, 30.0, 25.0]
    assert "OUTLINE" in state["cmds"] and state["box"] == (0, 0, 1181, 984)
