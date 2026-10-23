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
    state = {"box": (1000, 1000, 7000, 5000), "parts": 0, "cmds": [], "drawn": []}

    def read(p, geometry=False):
        return {"pads": [1], "tracks": state["drawn"]}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", read)
    monkeypatch.setattr(layout, "verify_layout", lambda *a, **k: [])

    def altium(cmds, **kw):                 # a new board holds the placeholder; OUTLINE changes it; PCBCHECK reports what it holds
        log = []
        for c in cmds:
            state["cmds"].append(c[0])
            if c[0] == "OUTLINE":
                state["box"] = tuple(round(float(v) / 0.0254) for v in c[2:6])
            if c[0] == "OUTLINEDRAW" and not state["drawn"]:
                state["draw_cmd"] = c
                x0, y0, x1, y1 = (float(v) for v in c[2:6])
                state["drawn"] = [dict(layer=57, x1_mm=a, y1_mm=b, x2_mm=cc, y2_mm=d, in_component=False)
                                  for a, b, cc, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))]
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
    assert state["cmds"].index("OUTLINEDRAW") == state["cmds"].index("OUTLINE") + 1      # the shape is drawn on Mechanical 1 too
    assert state["draw_cmd"][2:] == ("0", "0", "30", "25", "0.15")


def test_place_on_reports_a_board_whose_outline_layer_stays_empty(tmp_path, monkeypatch):
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
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: ["pcbcheck rect=1 objects=0 parts=0 tracks=0 outline_pts=4 box_mil=1000,1000,7000,5000"]
                        if cmds[-1][0] == "PCBCHECK" else [])
    res = bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, [{"ref": "R1", "footprint": "FP", "lib_ref": "R", "pins": []}], size=(30, 25))
    assert any("no drawing" in p for p in res["problems"])


def _rect_tracks(x0, y0, x1, y1, layer=57, comp=False):
    return [dict(layer=layer, x1_mm=a, y1_mm=b, x2_mm=c, y2_mm=d, in_component=comp)
            for a, b, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))]


def test_outline_drawing_problems():
    from altium import layout
    box = [0, 0, 30, 25]
    assert layout.outline_drawing_problems({"tracks": _rect_tracks(*box)}, box) == []
    assert "no drawing" in layout.outline_drawing_problems({"tracks": []}, box)[0]
    assert "no drawing" in layout.outline_drawing_problems({"tracks": _rect_tracks(*box, comp=True) + _rect_tracks(*box, layer=1)}, box)[0]
    assert "is [0, 0, 31, 25]" in layout.outline_drawing_problems({"tracks": _rect_tracks(0, 0, 31, 25)}, box)[0]
    open_ = _rect_tracks(*box)[:3]
    assert "not a closed" in layout.outline_drawing_problems({"tracks": open_}, box)[0]


def test_repair_outline_draws_only_on_an_empty_layer_of_a_rectangular_board(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"pcb")
    docs = {"tracks": []}
    sent = []
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: "bk")
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: docs)

    def altium(cmds, **kw):
        sent.append([c[0] for c in cmds])
        for c in cmds:
            if c[0] == "OUTLINEDRAW":
                docs["tracks"] = _rect_tracks(*(float(v) for v in c[2:6]))
        return ["pcbcheck rect=1 objects=3 parts=3 tracks=0 outline_pts=4 box_mil=0,0,1181,984"] if cmds[-1][0] == "PCBCHECK" else []
    monkeypatch.setattr(bridge, "run_commands", altium)
    res = bridge.repair_outline(tmp_path / "P.PrjPcb", pcb)
    assert res["drawn"] and res["backup"] == "bk" and res["box"] == [0.0, 0.0, 29.997, 24.994]
    assert sent[-1] == ["PROJECT", "OUTLINEDRAW", "PCBSAVE"]
    sent.clear()
    assert not bridge.repair_outline(tmp_path / "P.PrjPcb", pcb)["drawn"] and sent == []      # a drawing is there now: untouched
    docs["tracks"] = []                                  # not a rectangle: a warning, nothing sent but the check
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append(cmds) or ["pcbcheck rect=0 objects=3 parts=3 tracks=0 outline_pts=6 box_mil=0,0,1181,984"])
    res = bridge.repair_outline(tmp_path / "P.PrjPcb", pcb)
    assert not res["drawn"] and "not a plain rectangle" in res["warning"] and all(c[0] != "OUTLINEDRAW" for run in sent for c in run)
