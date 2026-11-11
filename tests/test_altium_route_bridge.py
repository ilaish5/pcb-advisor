"""Review round for scripts/altium/bridge.py place / route: partial consent, restore on every failure, outline shape, drawn schematic."""
import pytest

import serve
from altium import bridge, route
from altium.ole import AltiumReadError
from test_altium_route import pad, rules  # noqa: F401


def test_partial_needs_a_partial_word_and_the_drc_message_is_a_partial_problem():
    said = "ok, keep what you can if some nets fail"
    assert serve._partial_consent({"partial": True, "partial_said": "keep what you can"}, said)
    assert not serve._partial_consent({"partial": True, "partial_said": "ok, route it"}, "ok, route it")        # no partial word
    assert not serve._partial_consent({"partial": True, "partial_said": "keep what you can"}, "route it")      # not their words
    assert serve._partial_consent({"partial": True, "partial_said": "חלקי זה בסדר"}, "חלקי זה בסדר")
    assert not serve._partial_consent({"partial_said": "partial is fine"}, "partial is fine")                    # partial flag missing
    # the DRC message route_on writes for un-routed nets is one a partly routed board has by definition
    assert bridge._partial_ok("Altium's design rule check reports 3 un-routed connections")
    assert bridge._partial_ok("not routed: GND (no way)") and bridge._partial_ok("the saved board still has open nets: GND (R1-1)")
    assert not bridge._partial_ok("Altium's design rule check reports 2 new Clearance Constraint violations")


def test_pcbcheck_rect_flag():
    assert bridge._pcbcheck_info(["pcbcheck rect=1 objects=0 parts=0 tracks=0 outline_pts=4 box_mil=0,0,10,10"])["rect"] is True
    assert bridge._pcbcheck_info(["pcbcheck rect=0 objects=0 parts=0 tracks=0 outline_pts=4 box_mil=0,0,10,10"])["rect"] is False
    assert bridge._pcbcheck_info(["pcbcheck objects=0 parts=0 tracks=0 outline_pts=5 box_mil=0,0,10,10"])["rect"] is False
    assert bridge._pcbcheck_info(["pcbcheck objects=0 parts=0 tracks=0 outline_pts=4 box_mil=0,0,10,10"])["rect"] is True


def test_four_point_outline_that_is_not_a_rectangle_is_refused(tmp_path, monkeypatch):
    lib = tmp_path / "L.PcbLib"
    lib.write_bytes(b"x")
    monkeypatch.setattr(bridge, "read_pcblib", lambda p: {"footprints": [{"name": "FP"}]})
    monkeypatch.setattr(bridge, "run_commands",
                        lambda cmds, **kw: ["pcbcheck rect=0 objects=0 parts=0 tracks=0 outline_pts=4 box_mil=0,0,4000,3000"])
    parts = [{"ref": "R1", "footprint": "FP", "lib_ref": "R", "pins": []}]
    with pytest.raises(bridge.BridgeError, match="not a rectangle"):
        bridge.place_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", lib, parts, size=(40, 30))


def test_place_refuses_until_the_schematic_is_drawn(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "_linked", lambda p: tmp_path / "P.PrjPcb")
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: tmp_path / "B.PcbDoc")
    monkeypatch.setattr(bridge, "library_paths", lambda p: {"pcblib": tmp_path / "L.PcbLib"})
    monkeypatch.setattr(bridge, "_netlist_parts", lambda p: [{"ref": "R1"}, {"ref": "C1"}])
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {"R1": ("uid", "Sheet1")})          # C1 is not drawn
    monkeypatch.setattr(bridge, "place_on", lambda *a, **k: pytest.fail("placed without the schematic"))
    with pytest.raises(bridge.BridgeError, match="C1.*draw it first|draw it first"):
        bridge.place_pcb("p")


def _route_fakes(monkeypatch, tmp_path, drc_raises=False, read_raises=False):
    """A board that route_on can plan and 'draw' without Altium; records the restore calls."""
    import altium.pcbdoc as pcbdoc
    doc = {"nets": ["A"], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A")], "rules": []}
    calls = {"restore": 0, "run": []}
    state = {"read": 0}

    def fake_run(cmds, **kw):
        calls["run"].append([c[0] for c in cmds])
        return ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"]

    def fake_read(path, geometry=False):
        state["read"] += 1
        if geometry and read_raises:
            raise AltiumReadError(str(path), "cannot read")
        return dict(doc, tracks=[], vias=[])

    def fake_drc(prj, pcb, report):
        if state["read"] > 1 and drc_raises:
            raise bridge.BridgeError("Altium did not write the design rule check report.")
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0}

    monkeypatch.setattr(bridge, "run_commands", fake_run)
    monkeypatch.setattr(bridge, "run_drc", fake_drc)
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: str(tmp_path / "bk"))
    monkeypatch.setattr(bridge, "_restore", lambda prj, pcb, bk: calls.__setitem__("restore", calls["restore"] + 1) or True)
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", fake_read)
    return calls


def test_failed_read_back_after_routing_restores_the_backup(tmp_path, monkeypatch):
    calls = _route_fakes(monkeypatch, tmp_path, read_raises=True)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert calls["restore"] == 1 and res["restored"] and res["problems"] and "put back" in res["summary"]


def test_drc_raising_after_routing_restores_the_backup(tmp_path, monkeypatch):
    calls = _route_fakes(monkeypatch, tmp_path, drc_raises=True)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert calls["restore"] == 1 and res["restored"] and "put back" in res["summary"]


def test_route_commands_are_sent_with_the_pour_when_ground_has_three_pads(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    calls = _route_fakes(monkeypatch, tmp_path)
    doc = {"nets": ["A", "GND"], "rules": [], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A"), pad("C1", "1", 5, 9, "GND"),
                                                         pad("C2", "1", 10, 9, "GND"), pad("C3", "1", 15, 9, "GND")]}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)          # Altium filled the polygon
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append(cmds) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert res["pour"] == "GND" and "GND poured on the bottom layer" in res["summary"] and not res["pour_warning"]
    assert any(c[0] == "POLY" and c[3] == "GND" for cmds in sent for c in cmds)
    assert route.pour_net_for({"pads": doc["pads"][:2]}) is None


def test_a_pour_with_no_copper_in_the_saved_file_is_not_reported_as_poured(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    _route_fakes(monkeypatch, tmp_path)
    doc = {"nets": ["A", "GND"], "rules": [], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A"), pad("C1", "1", 5, 9, "GND"),
                                                         pad("C2", "1", 10, 9, "GND"), pad("C3", "1", 15, 9, "GND")]}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 0)          # polygon drawn, Regions6 empty
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert res["pour"] is None and "poured" not in res["summary"]
    assert "did not fill it (no copper)" in res["pour_warning"] and "Repour All" in res["pour_warning"]


def test_poured_copper_counts_polygon_regions_on_the_layer_from_the_file():
    import pathlib
    from altium.pcbdoc import poured_copper
    fx = pathlib.Path(__file__).parent / "fixtures" / "altium" / "finished-board.PcbDoc"
    assert poured_copper(fx, 32) > 0 and poured_copper(fx, 7) == 0


def _pas():
    import pathlib
    return (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")


def test_pascal_never_counts_or_removes_footprint_copper_and_removes_in_one_pass():
    src = _pas()
    copper = src[src.index("function PcbIsCopper"):src.index("function PcbObjCount")]
    assert "InComponent" in copper and copper.index("InComponent") < copper.index("Result := True")
    rem = src[src.index("procedure PcbRemoveKind"):src.index("function PcbPlacedCount")]
    assert "TInterfaceList" in rem and "repeat" not in rem and rem.index("L.Add(O)") < rem.index("RemovePCBObject")


def test_pascal_has_the_pour_and_the_rectangle_check():
    src = _pas()
    assert "procedure PcbPoly" in src and "Cmd = 'POLY'" in src and "RemoveDead := True" in src
    chk = src[src.index("procedure PcbCheck"):src.index("function NetOf")]
    assert "rect=" in chk and "S1.vx <> S2.vx" in chk


def test_route_pcb_asks_for_the_jlc_rules_first(monkeypatch):
    """Widths, clearances and vias come from the board rules: with Altium's defaults (rules not imported) nothing is routed."""
    import pytest
    from altium import bridge
    monkeypatch.setattr(bridge, "_linked", lambda p: "x.PrjPcb")
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: "x.PcbDoc")
    monkeypatch.setattr(bridge, "rules_missing", lambda p: ["JLC Clearance", "JLC Via"])
    called = []
    monkeypatch.setattr(bridge, "route_on", lambda *a, **k: called.append(1))
    with pytest.raises(bridge.BridgeError, match="Import the JLC rules first"):
        bridge.route_pcb("p")
    assert not called


def test_a_read_only_step_leaves_the_modified_mark_as_it_found_it():
    """The script remembers whether Altium held the document with unsaved changes before a read-only step (DRC, read-backs, checks)
    and clears the mark the step may have left; the Python side lists DOCSTATE as read-only."""
    import re as _re
    src = _pas()
    m = _re.search(r"procedure Dispatch\(Line: String\);.*?\nend;", src, _re.S)
    assert m, "Dispatch wrapper missing"
    body = m.group(0)
    assert "DocDirty(" in body and "DispatchStep(Line)" in body and "SetModified(False)" in body
    for cmd in ("DRC", "PCBEXTENT", "PCBCHECK"):
        assert f"Cmd = '{cmd}'" in body
    assert "DOCSTATE" in src and "DOCSTATE" in bridge.READ_ONLY


def _gnd_doc():
    return {"nets": ["A", "GND"], "rules": [], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A"), pad("C1", "1", 5, 9, "GND"),
                                                         pad("C2", "1", 10, 9, "GND"), pad("C3", "1", 15, 9, "GND")]}


def test_the_board_is_reloaded_before_the_tracks_and_the_pour_are_drawn(tmp_path, monkeypatch):
    """T28: a board placed in the same Altium session kept the placing script's pad nets and the pour shorted other-net through-hole pads."""
    import altium.pcbdoc as pcbdoc
    _route_fakes(monkeypatch, tmp_path)
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    draw = next(i for i, c in enumerate(sent) if "ROUTEBEGIN" in c)
    assert sent[draw - 1] == ["PROJECT", "REVERT"]


def test_a_pour_that_breaks_the_rules_is_taken_off_and_the_tracks_stay(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    calls = _route_fakes(monkeypatch, tmp_path)
    from altium import layout
    monkeypatch.setattr(layout, "unrouted", lambda d: [])        # the fake read-back has no tracks
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    sent = []
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 0 if any("POLYDEL" in c for c in sent) else 4)
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    drcs = []

    def fake_drc(prj, pcb, report):
        drcs.append(1)
        if len(drcs) == 2:          # after drawing: the pour is too close to a pad of another net
            return {"rules": {"Clearance Constraint (Gap=6mil)": 2, "Short-Circuit Constraint": 1},
                    "violations": ["Clearance Constraint (Gap=6mil): (Collision < 6mil) Between Pad J1-1 And Polygon Region (14 hole(s)) Bottom Layer"] * 2
                    + ["Short-Circuit Constraint: Between Pad J1-1 And Polygon Region Bottom Layer"], "unrouted": 0, "total": 3}
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0}

    monkeypatch.setattr(bridge, "run_drc", fake_drc)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert any("POLYDEL" in c for c in sent) and len(drcs) == 3
    assert not res["problems"] and not res["restored"] and calls["restore"] == 0
    assert res["pour"] is None and "taken off" in res["pour_warning"] and "poured" not in res["summary"]


def test_a_rule_break_that_is_not_the_pour_still_restores_the_board(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    calls = _route_fakes(monkeypatch, tmp_path)
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    n = []

    def fake_drc(prj, pcb, report):
        n.append(1)
        if len(n) == 2:
            return {"rules": {"Clearance Constraint (Gap=6mil)": 1}, "violations": ["Clearance Constraint (Gap=6mil): Between Track A And Track B"],
                    "unrouted": 0, "total": 1}
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0}

    monkeypatch.setattr(bridge, "run_drc", fake_drc)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert not any("POLYDEL" in c for c in sent) and res["restored"] and calls["restore"] == 1 and res["problems"]


def test_a_stale_board_shape_means_no_pour_with_the_reason(tmp_path, monkeypatch):
    """Dark sensor LED: Altium held the placeholder shape 25.4..177.8 mm, so every polygon stayed empty (T24)."""
    import altium.pcbdoc as pcbdoc
    _route_fakes(monkeypatch, tmp_path)
    from altium import layout
    monkeypatch.setattr(layout, "unrouted", lambda d: [])        # the fake read-back has no tracks
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "board_shape_box", lambda path: [25.4, 25.4, 177.8, 127.0])
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append(cmds) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert not any(c[0] == "POLY" for cmds in sent for c in cmds)
    assert res["pour"] is None and "board shape Altium holds" in res["pour_warning"] and "Redefine Board Shape" in res["pour_warning"]
    assert not res["problems"]


def test_board_shape_box_reads_the_region_record_or_says_nothing(tmp_path):
    import struct
    from altium import pcbdoc
    blob = b"|LAYERSTACKID={ABC}" + b"\x00" + struct.pack("<I", 4) + struct.pack("<8d", 0, 0, 1e7, 0, 1e7, 5e6, 0, 5e6)
    monkey = pcbdoc.open_doc

    class Ole:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    pcbdoc.open_doc = lambda p: Ole()
    real = pcbdoc._optional_stream
    try:
        pcbdoc._optional_stream = lambda ole, name: blob
        assert pcbdoc.board_shape_box("x") == [0.0, 0.0, 25.4, 12.7]
        pcbdoc._optional_stream = lambda ole, name: b""
        assert pcbdoc.board_shape_box("x") is None
    finally:
        pcbdoc.open_doc, pcbdoc._optional_stream = monkey, real


def _pour_broken_fakes(monkeypatch, tmp_path, copper_after, read_after_raises=False):
    """The pour breaks the rules (DRC 2), POLYDEL runs, then the file is read again: `copper_after` polygon records are left."""
    import altium.pcbdoc as pcbdoc
    from altium import layout
    calls = _route_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(layout, "unrouted", lambda d: [])
    sent = []
    doc = _gnd_doc()

    def read(path, geometry=False):
        if read_after_raises and any("POLYDEL" in c for c in sent):
            raise AltiumReadError(str(path), "cannot read")
        return dict(doc, tracks=[], vias=[])

    monkeypatch.setattr(pcbdoc, "read_pcbdoc", read)
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: copper_after if any("POLYDEL" in c for c in sent) else 4)
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    n = []

    def fake_drc(prj, pcb, report):
        n.append(1)
        if len(n) == 2:
            return {"rules": {"Short-Circuit Constraint": 1}, "violations": ["Short-Circuit Constraint: Between Pad J1-1 And Polygon Region"],
                    "unrouted": 0, "total": 1}
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0}

    monkeypatch.setattr(bridge, "run_drc", fake_drc)
    return calls, sent


def test_a_pour_taken_off_is_checked_in_the_file_for_left_over_polygon_copper(tmp_path, monkeypatch):
    calls, _ = _pour_broken_fakes(monkeypatch, tmp_path, copper_after=3)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert res["problems"] and res["restored"] and calls["restore"] == 1       # polygon copper left: the pour is not off, the board goes back


def test_a_failed_read_back_after_taking_the_pour_off_restores_the_backup(tmp_path, monkeypatch):
    calls, _ = _pour_broken_fakes(monkeypatch, tmp_path, copper_after=0, read_after_raises=True)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert calls["restore"] == 1 and res["restored"] and "put back" in res["summary"]


def test_unsaved_edits_made_while_planning_stop_the_route_before_the_revert(tmp_path, monkeypatch):
    """PCBCHECK ran before the DRC and the planning; REVERT closes without a prompt: the state is asked again just before it."""
    _route_fakes(monkeypatch, tmp_path)
    sent = []

    def run(cmds, **kw):
        sent.append([c[0] for c in cmds])
        if cmds[-1][0] == "DOCSTATE":
            return ["docstate open modified=1"]
        return ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"]

    monkeypatch.setattr(bridge, "run_commands", run)
    with pytest.raises(bridge.BridgeError, match="unsaved changes"):
        bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert ["PROJECT", "REVERT"] not in sent and not any("ROUTEBEGIN" in c for c in sent)
