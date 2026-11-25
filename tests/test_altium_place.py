"""altium.place_pcb / route_pcb: the consent guard per action, the DRC report parser, the PCBCHECK log parser."""
import pathlib

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


def test_parse_drc_lists_every_rule_and_is_clean_only_when_read_in_full(tmp_path):
    good = ("Rule Violations|Clearance Constraint (Gap=0.127mm) (All),(All)|0\nRule Violations|Short-Circuit Constraint (Allowed=No)|0\n"
            "Rule Violations|Width Constraint (Min=0.127mm)|0\nRule Violations|Un-Routed Net Constraint ( (All) )|3\nRule Violations|Total|3\n")
    f = tmp_path / "a.txt"
    f.write_text(good, encoding="cp1252")
    r = bridge.parse_drc(f)
    assert r["total"] == 3 and r["complete"] and not r["clean"] and not bridge.drc_clean(r)
    assert bridge.drc_line(r) == "Clearance 0, Short-Circuit 0, Width 0, Un-Routed Net 3, total 3"
    f.write_text(good.replace("|3\n", "|0\n"), encoding="cp1252")
    r = bridge.parse_drc(f)
    assert r["clean"] and bridge.drc_clean(r) and bridge.drc_line(r).endswith("total 0 (clean)")


@pytest.mark.parametrize("text", ["", "nothing useful here\n", "Rule Violations|Clearance|x\nRule Violations|Width|0\n",
                                  "Rule Violations|Clearance|0\nRule Violations|Clearance|2\n",
                                  "Rule Violations|Clearance|0\nClearance|||Track too close\n",           # details but a zero total
                                  "Rule Violations|Clearance|0\nRule Violations|Width\n"])
def test_a_malformed_or_partial_drc_report_is_unchecked_never_clean(tmp_path, text):
    f = tmp_path / "m.txt"
    f.write_text(text, encoding="cp1252")
    r = bridge.parse_drc(f)
    assert not r["clean"] and not r["complete"] and not bridge.drc_clean(r)
    assert bridge.drc_line(r).startswith("unchecked")
    assert not bridge.drc_clean(None) and bridge.drc_line(None).startswith("unchecked")
    assert not bridge.drc_clean({"rules": {"Clearance": 0}, "total": 0})        # no "complete" flag: not clean


def test_total_line_is_not_a_rule_and_must_match_the_sum(tmp_path):
    body = "Rule Violations|Clearance|0\nRule Violations|Un-Routed Net Constraint|2\n"
    f = tmp_path / "t.txt"
    f.write_text(body + "Rule Violations|Total|2\n", encoding="cp1252")
    r = bridge.parse_drc(f)
    assert r["total"] == 2 and r["complete"] and "Total" not in r["rules"]
    for bad in (body, body + "Rule Violations|Total|5\n"):          # no Total line (truncated) / a Total that does not add up
        f.write_text(bad, encoding="cp1252")
        r = bridge.parse_drc(f)
        assert not r["complete"] and not r["clean"] and bridge.drc_line(r).startswith("unchecked")


def test_real_altium_batch_report_parses_complete_with_the_right_total():
    import pathlib
    fx = pathlib.Path(__file__).parent / "fixtures" / "drc" / "unrouted-20.txt"
    r = bridge.parse_drc(fx)
    assert r["complete"] and r["total"] == 20 and r["unrouted"] == 12 and not r["clean"] and "Total" not in r["rules"]
    assert len(r["rules"]) == 18 and len(r["violations"]) == 20
    assert bridge.drc_line(r).endswith("total 20") and "Un-Routed Net 12" in bridge.drc_line(r)


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


def _place_fakes(monkeypatch, tmp_path, shape, writes=True, modified=False):
    """place_on on a board that Altium reports with a 30 x 25 mm outline, whose board shape record is `shape` (mm); logs the steps."""
    import altium.pcbdoc as pcbdoc
    from altium import layout
    lib = tmp_path / "L.PcbLib"
    lib.write_bytes(b"x")
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"pcb")
    fp = {"name": "FP", "pads": [{"x": 0, "y": 0, "xsize": 40, "ysize": 40, "rotation": 0, "name": "1"}], "extent": {}}
    monkeypatch.setattr(bridge, "read_pcblib", lambda p: {"footprints": [fp]})
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {})
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: "bk")
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {"pads": [1], "tracks": _rect_tracks(0, 0, 30, 25)})
    monkeypatch.setattr(layout, "verify_layout", lambda *a, **k: [])
    held = {"shape": shape}
    steps = []
    monkeypatch.setattr(pcbdoc, "board_shape_box", lambda p: held["shape"])

    def set_shape(p, box):
        steps.append(("SETSHAPE", [round(v, 1) for v in box]))
        if writes:
            held["shape"] = list(box)
        return writes
    monkeypatch.setattr(pcbdoc, "set_board_shape", set_shape)

    def altium(cmds, **kw):
        steps.extend((c[0],) for c in cmds)
        if cmds[-1][0] == "DOCSTATE":
            return ["docstate open modified=%d" % modified]
        if cmds[-1][0] == "PCBCHECK":
            return ["pcbcheck rect=1 objects=1 parts=1 tracks=0 outline_pts=4 box_mil=0,0,1181,984"]
        return []
    monkeypatch.setattr(bridge, "run_commands", altium)
    res = bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, [{"ref": "R1", "footprint": "FP", "lib_ref": "R", "pins": []}], size=(30, 25))
    return res, steps


def test_place_sets_the_board_shape_to_the_outline_when_altium_kept_the_new_board_one(tmp_path, monkeypatch):
    res, steps = _place_fakes(monkeypatch, tmp_path, [25.4, 25.4, 177.8, 127.0])
    assert not res["problems"] and not res["warnings"]
    assert ("SETSHAPE", [0.0, 0.0, 30.0, 25.0]) in steps and steps.index(("REVERT",)) < steps.index(("SETSHAPE", [0.0, 0.0, 30.0, 25.0]))


def test_place_leaves_a_matching_board_shape_alone(tmp_path, monkeypatch):
    res, steps = _place_fakes(monkeypatch, tmp_path, [0.0, 0.0, 30.0, 25.0])
    assert not res["warnings"] and not any(s[0] in ("SETSHAPE", "REVERT") for s in steps)


def test_place_warns_only_when_the_board_shape_cannot_be_set(tmp_path, monkeypatch):
    res, _ = _place_fakes(monkeypatch, tmp_path, [25.4, 25.4, 177.8, 127.0], writes=False)
    assert not res["problems"] and any("could not be set" in w and "Redefine Board Shape" in w for w in res["warnings"])
    res, steps = _place_fakes(monkeypatch, tmp_path, [25.4, 25.4, 177.8, 127.0], modified=True)       # unsaved edits: the board is not closed
    assert any("unsaved changes" in w for w in res["warnings"]) and not any(s[0] in ("SETSHAPE", "REVERT") for s in steps)


def test_place_says_each_layout_warning_once_in_the_order_it_was_first_given(tmp_path, monkeypatch):
    """The planner and the check of the saved board both find "C1 is 3.2 mm from U2 pin 3 VIN ...": the place step's warnings list it once."""
    from altium import layout
    same = "C1 is 3.2 mm from U2 pin 3 VIN: place it as close as possible"
    plan = layout.plan_placement
    monkeypatch.setattr(layout, "plan_placement", lambda *a, **k: dict(plan(*a, **k), warnings=["first", same, "first"]))
    monkeypatch.setattr(layout, "decap_distance_warnings", lambda doc, parts: [same, "last"])
    res, _ = _place_fakes(monkeypatch, tmp_path, [0.0, 0.0, 30.0, 25.0])
    assert res["warnings"] == ["first", same, "last"]


def test_place_on_derives_connector_dirs_so_no_false_270_warning(tmp_path, monkeypatch):
    """Every connector gets its opening from its footprint (layout.opening_dir) as connector_dirs: the planner then has no reason to
    say "check the mating face (270 deg)" for it; a connector whose opening cannot be told is left out (still warned about)."""
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
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {"pads": [1], "tracks": []})
    monkeypatch.setattr(layout, "verify_layout", lambda *a, **k: [])
    monkeypatch.setattr(layout, "opening_dir", lambda f: 90.0)
    seen = {}
    real = layout.plan_placement

    def spy(parts, footprints, outline, **kw):
        seen.update(kw)
        return real(parts, footprints, outline, **kw)
    monkeypatch.setattr(layout, "plan_placement", spy)
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: ["pcbcheck rect=1 objects=2 parts=2 tracks=0 outline_pts=4 box_mil=0,0,1181,984"])
    parts = [{"ref": "J1", "footprint": "FP", "lib_ref": "J", "pins": []}, {"ref": "R1", "footprint": "FP", "lib_ref": "R", "pins": []}]
    try:
        bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, parts, size=(30, 25))
    except Exception:           # noqa: BLE001  (only the planner's arguments are looked at)
        pass
    assert seen["connector_dirs"] == {"J1": 90.0}

# ---------------------------------------------------------------- wave 3: Place on a routed board says what it deletes

def test_routing_words_are_plain_numbers():
    assert bridge._routing_words({"tracks": 12, "vias": 1, "pours": 2}) == "12 tracks, 1 via and 2 pours"
    assert bridge._routing_words({"tracks": 1}) == "1 track"
    assert bridge._routing_words({}) == "" and bridge._routing_words({"tracks": 0, "vias": 0}) == ""


def _routed_place(monkeypatch, tmp_path, replace, refuse):
    pcb, lib = tmp_path / "B.PcbDoc", tmp_path / "L.PcbLib"
    pcb.write_bytes(b"pcb")
    lib.write_bytes(b"x")
    monkeypatch.setattr(bridge, "read_pcblib", lambda p: {"footprints": [{"name": "FP"}]})
    monkeypatch.setattr(bridge, "_routing_lost", lambda p: {"tracks": 40, "vias": 6, "pours": 1})

    def altium(cmds, **kw):
        if refuse:
            raise bridge.BridgeError("Altium refused a step: the board already has 47 parts or copper objects; nothing was changed")
        return ["pcbcheck rect=1 objects=47 parts=5 tracks=40 outline_pts=4 box_mil=0,0,1181,984"]
    monkeypatch.setattr(bridge, "run_commands", altium)
    return bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, [{"ref": "R1", "footprint": "FP", "lib_ref": "FP", "pins": []}],
                           size=(30, 25), replace=replace)


def test_a_refusal_on_a_routed_board_names_what_a_new_placement_deletes(monkeypatch, tmp_path):
    with pytest.raises(bridge.BridgeError) as e:
        _routed_place(monkeypatch, tmp_path, replace=False, refuse=True)
    msg = str(e.value)
    assert "47 parts or copper objects, among them routing of 40 tracks, 6 vias and 1 pour that placing again deletes" in msg
    assert serve.needs_replace(e.value)                       # still the one Replace confirm of the UI, now an informed one


# ---------------------------------------------------------------- E10: change the outline of a board that already exists

def _resize_fakes(monkeypatch, tmp_path, old=(0.0, 0.0, 100.0, 80.0), parts=(("U1", 50.0, 40.0), ("J1", 95.0, 70.0)), modified=False, kept=False):
    import altium.pcbdoc as pcbdoc
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"pcb")
    sent, shape, docs = [], {"box": list(old)}, {"tracks": _rect_tracks(*old)}
    monkeypatch.setattr(bridge, "_linked", lambda project: tmp_path / "P.PrjPcb")
    monkeypatch.setattr(bridge, "_project_pcb", lambda project: pcb)
    monkeypatch.setattr(bridge, "_log", lambda *a, **k: None)
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: sent.append(["BACKUP"]) or "bk")
    monkeypatch.setattr(bridge, "_board_size", lambda project: (120.0, 90.0))
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {"components": [{"ref": r, "x_mm": x, "y_mm": y} for r, x, y in parts],
                                                                          "tracks": docs["tracks"]})
    monkeypatch.setattr(pcbdoc, "board_shape_box", lambda p: list(shape["box"]))

    def write_shape(p, box):
        shape["box"] = list(box)
        return ""
    monkeypatch.setattr(bridge, "_write_shape", write_shape)

    def altium(cmds, **kw):
        sent.append([c[0] for c in cmds])
        out = []
        for c in cmds:
            if c[0] == "DOCSTATE":
                out.append("docstate open modified=1" if modified else "docstate open modified=0")
            if c[0] == "OUTLINERESIZE":
                old_box = [float(v) for v in c[2:6]]
                shape["last"] = old_box
                if kept:
                    out.append("outlineresize drawn=0 kept=6")
                else:
                    docs["tracks"] = _rect_tracks(*old_box)
                    out.append("outlineresize drawn=4")
            if c[0] == "PCBCHECK":
                box = shape.get("last") or list(old)
                out.append("pcbcheck rect=1 objects=3 parts=2 tracks=0 outline_pts=4 box_mil=" + ",".join(str(round(v / bridge.MM_PER_MIL)) for v in box))
        return out
    monkeypatch.setattr(bridge, "run_commands", altium)
    return sent, shape


def test_resize_outline_sets_the_new_size_after_a_backup_and_reads_it_back(tmp_path, monkeypatch):
    sent, shape = _resize_fakes(monkeypatch, tmp_path)
    res = bridge.resize_outline("p", 120, 90)
    assert res["box"] == pytest.approx([0.0, 0.0, 120.0, 90.0], abs=0.02) and res["old_box"] == pytest.approx([0.0, 0.0, 100.0, 80.0], abs=0.02) and res["backup"] == "bk"
    assert res["outside"] == [] and res["problems"] == [] and shape["box"] == [0.0, 0.0, 120.0, 90.0]          # the board shape follows
    flat = [x for run in sent for x in run]
    assert flat.index("BACKUP") < flat.index("OUTLINERESIZE") < flat.index("PCBSAVE") < flat.index("REVERT")
    assert bridge.resize_outline("p")["box"] == [0.0, 0.0, 120.0, 90.0]                                         # the idea's size when none is given


def test_resize_outline_refuses_a_board_with_unsaved_changes_and_changes_nothing(tmp_path, monkeypatch):
    sent, shape = _resize_fakes(monkeypatch, tmp_path, modified=True)
    with pytest.raises(bridge.BridgeError, match="unsaved changes.*Nothing was changed"):
        bridge.resize_outline("p", 120, 90)
    assert "BACKUP" not in [x for run in sent for x in run] and "OUTLINERESIZE" not in [x for run in sent for x in run]


def test_resize_outline_warns_about_the_parts_that_fall_outside_and_leaves_them(tmp_path, monkeypatch):
    sent, shape = _resize_fakes(monkeypatch, tmp_path)
    res = bridge.resize_outline("p", 60, 50)
    assert res["outside"] == ["J1"] and any("J1" in w and "outside" in w for w in res["warnings"])
    assert shape["box"] == [0.0, 0.0, 60.0, 50.0]


def test_resize_outline_leaves_an_outline_drawing_of_the_students_own(tmp_path, monkeypatch):
    sent, shape = _resize_fakes(monkeypatch, tmp_path, kept=True)
    res = bridge.resize_outline("p", 120, 90)
    assert any("drawing of your own" in w for w in res["warnings"])


def test_resize_outline_checks_the_numbers(tmp_path, monkeypatch):
    sent, shape = _resize_fakes(monkeypatch, tmp_path)
    for bad in ((5, 90), (120, 900), ("x", 90)):
        with pytest.raises(bridge.BridgeError, match="Nothing was changed"):
            bridge.resize_outline("p", *bad)
    assert not sent


def test_outline_status_says_when_the_idea_and_the_pcbdoc_differ(tmp_path, monkeypatch):
    _resize_fakes(monkeypatch, tmp_path)
    st = bridge.outline_status("p")
    assert st["idea"] == [120.0, 90.0] and st["pcb"] == [100.0, 80.0] and st["differs"] and st["parts"] == 2
    monkeypatch.setattr(bridge, "_board_size", lambda project: (100.0, 80.0))
    assert not bridge.outline_status("p")["differs"]
    monkeypatch.setattr(bridge, "_board_size", lambda project: None)
    assert not bridge.outline_status("p")["differs"]


def test_the_server_and_the_layout_page_offer_the_resize():
    root = pathlib.Path(__file__).resolve().parent.parent
    srv = (root / "scripts" / "serve.py").read_text(encoding="utf-8")
    assert '"/api/altium/outline-resize"' in srv and "bridge.resize_outline(" in srv and "bridge.outline_status(" in srv
    js = (root / "ui" / "js" / "views" / "previews.js").read_text(encoding="utf-8")
    assert "Set board to" in js and "pcb-outline-resize" in js
    pas = (root / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    assert "OUTLINERESIZE" in pas and "DrawBegin(Field(Line, 1), Field(Line, 2), Field(Line, 3))" in pas


def test_resize_outline_uses_the_footprint_not_only_its_origin(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    sent, shape = _resize_fakes(monkeypatch, tmp_path)
    orig = pcbdoc.read_pcbdoc
    pad = {"ref": "U1", "x_mm": 58.0, "y_mm": 40.0, "sx_mm": 2.0, "sy_mm": 1.0, "rot": 0.0}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {**orig(p, geometry), "components": [{"ref": "U1", "x_mm": 55.0, "y_mm": 40.0}],
                                                                          "pads": [pad]})
    assert bridge.resize_outline("p", 60, 50)["outside"] == []     # the pad reaches 59 mm: inside
    pad["x_mm"] = 59.5                                             # the origin (55) is inside, the pad's edge (60.5) is not
    assert bridge.resize_outline("p", 60, 50)["outside"] == ["U1"]


def test_resize_outline_refuses_when_copper_would_lie_outside_and_warns_when_routed(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    sent, shape = _resize_fakes(monkeypatch, tmp_path)
    orig = pcbdoc.read_pcbdoc
    extra = {"layer": 1, "x1_mm": 10.0, "y1_mm": 10.0, "x2_mm": 90.0, "y2_mm": 10.0, "in_component": False}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {**orig(p, geometry), "tracks": list(orig(p, geometry).get("tracks", [])) + [extra]})
    with pytest.raises(bridge.BridgeError, match="copper.*Nothing was changed"):
        bridge.resize_outline("p", 60, 50)
    assert "OUTLINERESIZE" not in [x for run in sent for x in run]
    res = bridge.resize_outline("p", 120, 90)            # bigger: nothing is cut off, but the student is told the pours stay old
    assert any("already routed or poured" in w for w in res["warnings"])


def test_outline_resize_deletes_only_tracks_on_the_old_corners_and_a_skeleton_keeps_the_sheet_style():
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    assert "TrackOnCorners(O, ox0, oy0, ox1, oy1)" in pas and "(k = 4)" in pas
    tb = pas[pas.index("procedure TitleBlock("):]
    tb = tb[:tb.index("{ The PCB of a path")]
    assert "SheetHasParts(Sch)" in tb and "SheetSetup(Sch)" in tb and tb.index("SheetHasParts") < tb.index("SheetSetup(Sch)")


def test_sheet_fit_says_unknown_not_too_big_when_a_sheet_errors(monkeypatch):
    monkeypatch.setattr(bridge, "library_paths", lambda p: {"schlib": "x"})
    monkeypatch.setattr(bridge, "_project_symbols", lambda lp: ({}, ""))
    monkeypatch.setattr(bridge, "drawn_names", lambda p: {})
    monkeypatch.setattr(bridge, "_sheets", lambda p: [("01", "T", {"parts": []})])

    def boom(*a, **k):
        raise RuntimeError("symbol broke")
    monkeypatch.setattr(bridge, "_sheet_symbols", boom)
    res = bridge.sheet_fit("p")
    assert res[0]["fits"] is None and "symbol broke" in res[0]["message"]
