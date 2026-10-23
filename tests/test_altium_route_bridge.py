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
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append(cmds) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert res["pour"] == "GND"
    assert any(c[0] == "POLY" and c[3] == "GND" for cmds in sent for c in cmds)
    assert route.pour_net_for({"pads": doc["pads"][:2]}) is None


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
