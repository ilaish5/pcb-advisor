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
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}

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
    _route_fakes(monkeypatch, tmp_path)
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


_POUR_DOC = {"nets": ["A", "GND"], "rules": [], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A"), pad("C1", "1", 5, 9, "GND"),
                                                          pad("C2", "1", 10, 9, "GND"), pad("C3", "1", 15, 9, "GND")]}


def _pour_route(monkeypatch, tmp_path, check):
    import altium.pcbdoc as pcbdoc
    import altium.pourcheck as pourcheck
    calls = _route_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(_POUR_DOC, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)
    monkeypatch.setattr(pourcheck, "check", check)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    return calls, res


def test_pourcheck_unjoined_pad_is_a_problem_and_island_a_warning(tmp_path, monkeypatch):
    unj = {"islands": [], "unjoined_pads": [{"ref": "C3", "name": "1", "x_mm": 1, "y_mm": 2}], "checked": True, "note": "n", "ok": False}
    calls, res = _pour_route(monkeypatch, tmp_path, lambda doc, net=None, layer=None: unj)
    assert any("pad C3-1" in p and "not joined" in p for p in res["problems"]) and res["restored"] and calls["restore"] == 1
    isl = {"islands": [{"layer": 32, "bbox_mm": [1, 1, 2, 2], "area_mm2": 3.0, "polygon": "GND_Bottom", "remove_dead": False}],
           "unjoined_pads": [], "checked": True, "ok": False,
           "note": "1 cut-off copper piece(s) and 0 pad(s) of GND not reached. Remove Dead Copper is off in polygon GND_Bottom; turn it on and repour."}
    calls, res = _pour_route(monkeypatch, tmp_path, lambda doc, net=None, layer=None: isl)
    assert not [p for p in res["problems"] if "open nets" not in p]
    assert len(res["pour_warnings"]) == 1 and "Remove Dead Copper is off" in res["pour_warnings"][0]


def test_pourcheck_not_checked_or_raising_is_never_ok(tmp_path, monkeypatch):
    nc = {"islands": [], "unjoined_pads": [], "checked": False, "note": "No poured copper could be read.", "ok": False}
    _, res = _pour_route(monkeypatch, tmp_path, lambda doc, net=None, layer=None: nc)
    assert not [p for p in res["problems"] if "open nets" not in p] and "pour not checked" in res["pour_warnings"][0]

    def boom(doc, net=None, layer=None):
        raise RuntimeError("surprise")
    _, res = _pour_route(monkeypatch, tmp_path, boom)
    assert not [p for p in res["problems"] if "open nets" not in p] and "pour not checked" in res["pour_warnings"][0] and "surprise" in res["pour_warnings"][0]
    ok = {"islands": [], "unjoined_pads": [], "checked": True, "note": "fine", "ok": True}
    _, res = _pour_route(monkeypatch, tmp_path, lambda doc, net=None, layer=None: ok)
    assert res["pour_warnings"] == [] and not [p for p in res["problems"] if "open nets" not in p]


def test_an_unreadable_drc_report_after_routing_is_unchecked_and_restores(tmp_path, monkeypatch):
    _route_fakes(monkeypatch, tmp_path)
    state = {"n": 0}

    def drc(prj, pcb, report):
        state["n"] += 1
        if state["n"] == 1:
            return {"rules": {"Clearance": 0}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": False, "clean": False}
    monkeypatch.setattr(bridge, "run_drc", drc)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert any("unchecked" in p for p in res["problems"]) and res["restored"] and res["drc_clean"] is False
    assert "unchecked" in res["summary"]


def test_the_summary_lists_every_drc_rule_with_its_count(tmp_path, monkeypatch):
    _route_fakes(monkeypatch, tmp_path)
    full = {"rules": {"Clearance Constraint (Gap=0.127mm)": 0, "Width Constraint (Min=0.1mm)": 0, "Un-Routed Net Constraint": 0},
            "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}
    monkeypatch.setattr(bridge, "run_drc", lambda prj, pcb, report: full)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert "Clearance 0, Width 0, Un-Routed Net 0, total 0 (clean)" in res["summary"] and res["drc_clean"] and res["drc_total"] == 0
    assert res["drc_rules"] == full["rules"]


def _caps(**kw):
    doc = dict({"nets": [], "pads": [], "rules": []}, **kw)
    return route.capability_check(doc, route.rules_from_doc(doc), [0, 0, 50, 40])


def _sp(ref, n, x, y, net, layer=1):
    return pad(ref, str(n), x, y, net, w=0.3, h=0.3, layer=layer)


def test_capability_check_does_not_refuse_the_finished_board_fixtures():
    import pathlib
    from altium import pcbdoc
    fx = pathlib.Path(__file__).parent / "fixtures" / "altium"
    for name in ("finished-board.PcbDoc", "rules-board.PcbDoc"):
        d = pcbdoc.read_pcbdoc(fx / name, geometry=True)
        xs, ys = [p["x_mm"] for p in d["pads"]], [p["y_mm"] for p in d["pads"]]
        box = [min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5]
        assert route.capability_check(d, route.rules_from_doc(d), box) == [], name
    assert _caps(pads=[pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A")]) == []


def test_capability_check_refuses_what_the_router_cannot_do_with_what_to_do_instead():
    inner = _caps(pads=[pad("R1", "1", 5, 5, "A")], tracks=[{"layer": 2, "net": "A", "x1_mm": 0, "y1_mm": 0, "x2_mm": 1, "y2_mm": 1, "width_mm": 0.2}])
    assert len(inner) == 1 and "inner layers" in inner[0] and "Interactive" in inner[0]
    bga = [_sp("U1", f"{r}{c}", 10 + c * 0.8, 10 + r * 0.8, f"N{r}{c}") for r in range(4) for c in range(4)]
    out = _caps(pads=bga)
    assert any("BGA" in m and "by hand" in m for m in out)
    qfp = [_sp("U2", i, 10 + i * 0.5, 10, f"N{i}") for i in range(12)] + [_sp("U2", 20 + i, 10 + i * 0.5, 14, f"M{i}") for i in range(12)]
    assert _caps(pads=qfp) == []                                                  # a dual row is not an area array
    fine = [_sp("U3", i, 10 + i * 0.3, 10, f"N{i}") for i in range(4)]
    assert any("U3" in m and "closer than" in m for m in _caps(pads=fine))
    def ring(ref, n, side=0.5):         # a quad flat package: n pads per side, 0.3 mm pads, plus the exposed pad
        pts = []
        for i in range(n):
            o = (i - (n - 1) / 2) * side
            pts += [(o, -2.0), (o, 2.0), (-2.0, o), (2.0, o)]
        return [pad(ref, str(k), 30 + x, 20 + y, f"N{k}", w=0.3, h=0.3) for k, (x, y) in enumerate(pts)]
    ep = pad("U4", "EP", 30, 20, "GND", w=2.6, h=2.6)
    assert _caps(pads=ring("U4", 5) + [ep]) == []                                  # QFN-20 with exposed pad
    assert _caps(pads=ring("U4", 7) + [ep]) == []                                  # QFN-28
    split = [pad("U4", f"E{i}{j}", 29 + i, 19 + j, "GND", w=0.8, h=0.8) for i in range(3) for j in range(3)]
    assert _caps(pads=ring("U4", 5) + split) == []                                 # exposed pad split into a 3x3 copper grid
    big = [_sp("U1", f"{r}{c}", 10 + c * 0.8, 10 + r * 0.8, f"N{r}{c}") for r in range(5) for c in range(5)]
    assert any("BGA" in m for m in _caps(pads=big))
    cls = []
    assert route.capability_check({"rules": [{"RULEKIND": "MatchedLengths", "NAME": "M", "ENABLED": "TRUE",
                                              "SCOPE1EXPRESSION": "InNetClass('USB')"}], "pads": []}, None, None, 0.1, warnings=cls) == []
    assert len(cls) == 1 and "verify the rule by hand" in cls[0]
    imp = _caps(rules=[{"RULEKIND": "MaxMinImpedance", "NAME": "Imp", "ENABLED": "TRUE", "SCOPE1EXPRESSION": "InNet('CLK')"}])
    assert len(imp) == 1 and "impedance" in imp[0]
    assert _caps(rules=[{"RULEKIND": "MatchedLengths", "NAME": "M", "ENABLED": "FALSE"}]) == []        # disabled: nothing to do
    usb = [pad("J1", "1", 5, 5, "USB_DP"), pad("U1", "1", 15, 5, "USB_DP"), pad("J1", "2", 5, 8, "USB_DM"), pad("U1", "2", 15, 8, "USB_DM")]
    assert _caps(pads=usb, rules=[{"RULEKIND": "MatchedLengths", "NAME": "M", "ENABLED": "TRUE",
                                   "SCOPE1EXPRESSION": "InNet('USB_DP') or InNet('USB_DM')"}]) == []
    big = route.capability_check({"pads": [], "rules": []}, None, [0, 0, 400, 300])
    assert len(big) == 1 and "too large" in big[0]


def test_route_on_refuses_without_drawing_when_the_router_cannot_do_it(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    calls = _route_fakes(monkeypatch, tmp_path)
    doc = {"nets": ["A"], "pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A")], "rules": [{"RULEKIND": "MaxMinImpedance", "ENABLED": "TRUE", "SCOPE1EXPRESSION": "All"}]}
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(bridge, "run_drc", lambda *a: pytest.fail("ran the DRC although the board is refused"))
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert not res["written"] and res["refusals"] and "nothing was drawn" in res["summary"] and res["problems"]
    assert calls["restore"] == 0 and calls["run"] == [["PROJECT", "PCBCHECK"]]


def test_place_warnings_with_a_placement_error_are_not_cut_off_in_the_step_note():
    ws = [f"w{i}" for i in range(6)] + ["placement error: C1 is 5 mm from U1 pin 3"]
    tail = serve.place_summary({"placed": ["U1"], "outline_created": False, "warnings": ws})
    assert "placement error: C1" in tail and "7 warnings" in tail


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


def _plan_log(monkeypatch, pour_model=True):
    """Records the pour_net each plan_routes call gets; pour_model=False plans the ground by tracks whatever route_on asks (a board whose
    ground is drawn by tracks, the pour on top: what the tests of taking a pour off again are about)."""
    from altium import route as route_mod
    real, seen = route_mod.plan_routes, []

    def plan(doc, box, rules=None, **kw):
        seen.append(kw.get("pour_net"))
        return real(doc, box, rules, **dict(kw, pour_net=kw.get("pour_net") if pour_model else None))
    monkeypatch.setattr(route_mod, "plan_routes", plan)
    return seen


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
    _plan_log(monkeypatch, pour_model=False)
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
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}

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
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}

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
    _plan_log(monkeypatch, pour_model=False)
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
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}

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


def _shape_fakes(monkeypatch, tmp_path, stale=True, writes=True):
    """A routed board whose board shape record is stale (or not); set_board_shape is faked and logged in the order of the Altium steps."""
    import altium.pcbdoc as pcbdoc
    from altium import layout
    _route_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(layout, "unrouted", lambda d: [])
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)
    held = {"shape": [25.4, 25.4, 177.8, 127.0] if stale else [0.0, 0.0, 19.99, 19.99]}
    sent = []
    monkeypatch.setattr(pcbdoc, "board_shape_box", lambda path: held["shape"])

    def set_shape(path, box):
        sent.append(["SETSHAPE", [round(v, 2) for v in box]])
        if writes:
            held["shape"] = list(box)
        return writes

    monkeypatch.setattr(pcbdoc, "set_board_shape", set_shape)
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        (["docstate open modified=0"] if cmds[-1][0] == "DOCSTATE" else
                         ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"]))
    return sent


def test_a_stale_board_shape_is_set_to_the_outline_and_the_pour_goes_on(tmp_path, monkeypatch):
    """Blinker 555: the shape of a new board stayed in the file; route sets it (closed board, after the backup) and pours as usual."""
    sent = _shape_fakes(monkeypatch, tmp_path)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    at = lambda name: next(i for i, c in enumerate(sent) if name in c)       # each entry is one call's command names
    assert ["SETSHAPE", [0.0, 0.0, 19.99, 19.99]] in sent
    assert at("REVERT") < at("SETSHAPE") < at("ROUTEBEGIN")
    assert res["pour"] == "GND" and not res["pour_warning"] and res["shape_fixed"] == [0.0, 0.0, 19.99, 19.99] and not res["problems"]


def test_a_matching_board_shape_is_left_alone(tmp_path, monkeypatch):
    sent = _shape_fakes(monkeypatch, tmp_path, stale=False)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert not any(c[0] == "SETSHAPE" for c in sent) and res["pour"] == "GND" and "shape_fixed" not in res


def test_the_warning_stays_only_when_the_shape_cannot_be_set(tmp_path, monkeypatch):
    _shape_fakes(monkeypatch, tmp_path, writes=False)        # the record is not a plain rectangle: nothing written
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert res["pour"] is None and "could not be set" in res["pour_warning"] and "Redefine Board Shape" in res["pour_warning"]
    assert "GND" in res["pour_warning"] and not res["problems"]


def test_set_board_shape_rewrites_the_four_corners_in_place_and_refuses_other_records(monkeypatch):
    import struct
    import olefile
    from altium import pcbdoc
    head = b"\x0b\x86|LAYERSTACKID={ABC}"
    blob = head + b"\x00" + struct.pack("<I", 4) + struct.pack("<8d", 1e7, 1e7, 7e7, 1e7, 7e7, 5e7, 1e7, 5e7) + b"tail"
    written = {}

    class Ole:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Rw:
        def __init__(self, path, write_mode=False): written["mode"] = write_mode
        def write_stream(self, name, data): written[name] = data
        def close(self): pass

    monkeypatch.setattr(pcbdoc, "open_doc", lambda p: Ole())
    monkeypatch.setattr(olefile, "OleFileIO", Rw)
    monkeypatch.setattr(pcbdoc, "_optional_stream", lambda ole, name: blob)
    assert pcbdoc.set_board_shape("x", [0, 0, 30, 20]) is True
    new = written["BoardRegions/Data"]
    assert written["mode"] and len(new) == len(blob) and new.endswith(b"tail")
    monkeypatch.setattr(pcbdoc, "_optional_stream", lambda ole, name: new)
    assert pcbdoc.board_shape_box("x") == [0.0, 0.0, 30.0, 20.0]
    written.clear()
    monkeypatch.setattr(pcbdoc, "_optional_stream", lambda ole, name: head + b"\x00" + struct.pack("<I", 6) + b"\0" * 100)
    assert pcbdoc.set_board_shape("x", [0, 0, 30, 20]) is False and "BoardRegions/Data" not in written


def _poured_board(monkeypatch, tmp_path, copper=4, drc_after=None):
    """_gnd_doc routed with the ground planned as poured (pour model on, the board shape fits); the read-back has no tracks, and unrouted()
    (which does not read pours) says the ground is open, as it does of a ground that the pour joins. Returns (calls, sent, the pour_net of each plan)."""
    import altium.pcbdoc as pcbdoc
    import altium.pourcheck as pourcheck
    from altium import layout
    calls = _route_fakes(monkeypatch, tmp_path)
    seen = _plan_log(monkeypatch)
    doc = _gnd_doc()
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(doc, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: copper)
    monkeypatch.setattr(layout, "unrouted", lambda d: [("GND", ["C1-1", "C2-1"])])
    monkeypatch.setattr(pourcheck, "check", lambda d, net=None, layer=None: {"islands": [], "unjoined_pads": [], "checked": True, "note": "", "ok": True})
    sent = []
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: sent.append([c[0] for c in cmds]) or
                        ["pcbcheck rect=1 objects=0 parts=2 tracks=0 outline_pts=4 box_mil=0,0,787,787"])
    n = []

    def fake_drc(prj, pcb, report):
        n.append(1)
        if len(n) == 2 and drc_after:
            return drc_after
        return {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}
    monkeypatch.setattr(bridge, "run_drc", fake_drc)
    return calls, sent, seen


def test_the_ground_is_planned_for_the_pour_when_the_pour_is_drawn_as_planned(tmp_path, monkeypatch):
    calls, sent, seen = _poured_board(monkeypatch, tmp_path)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert seen == ["GND"] and res["pour"] == "GND" and any("POLY" in run for run in sent)
    assert "GND" in res["routed"] and not res["problems"] and not res["restored"] and calls["restore"] == 0       # the pour is the ground's copper


def test_a_ground_routed_to_the_pour_is_not_routed_when_the_pour_has_no_copper(tmp_path, monkeypatch):
    calls, _, seen = _poured_board(monkeypatch, tmp_path, copper=0)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert seen == ["GND"] and res["pour"] is None
    assert any("GND was routed to the pour" in p and "not connected" in p for p in res["problems"])
    assert res["restored"] and calls["restore"] == 1


def test_a_ground_routed_to_the_pour_is_restored_not_left_open_when_the_pour_breaks_the_rules(tmp_path, monkeypatch):
    bad = {"rules": {"Clearance Constraint (Gap=6mil)": 1}, "violations": ["Clearance Constraint (Gap=6mil): Between Pad J1-1 And Polygon Region"],
           "unrouted": 0, "total": 1}
    calls, sent, _ = _poured_board(monkeypatch, tmp_path, drc_after=bad)
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert not any("POLYDEL" in c for c in sent)         # taking only the pour off would leave the ground pads joined to nothing
    assert res["problems"] and res["restored"] and calls["restore"] == 1


def test_a_board_whose_shape_cannot_be_set_is_planned_with_the_ground_by_tracks(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    from altium import layout
    _, _, seen = _poured_board(monkeypatch, tmp_path)
    monkeypatch.setattr(pcbdoc, "board_shape_box", lambda path: [25.4, 25.4, 177.8, 127.0])
    monkeypatch.setattr(pcbdoc, "set_board_shape", lambda path, box: False)
    monkeypatch.setattr(layout, "unrouted", lambda d: [])
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)
    assert seen == [None] and res["pour"] is None and "could not be set" in res["pour_warning"] and not res["problems"]


def _kiln_partial(monkeypatch, tmp_path, drc_after=None):
    """E5 (kiln LTE run): GND is one of the nets the router left open; the pour then leaves a GND pad unjoined."""
    import altium.pcbdoc as pcbdoc
    import altium.pourcheck as pourcheck
    from altium import route as route_mod
    calls = _route_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda path, geometry=False: dict(_POUR_DOC, tracks=[], vias=[]))
    monkeypatch.setattr(pcbdoc, "poured_copper", lambda path, layer=32: 4)
    unj = {"islands": [], "unjoined_pads": [{"ref": "C3", "name": "1"}], "checked": True, "note": "", "ok": False}
    monkeypatch.setattr(pourcheck, "check", lambda doc, net=None, layer=None: unj)
    real = route_mod.plan_routes

    def plan(doc, box, rules=None, **kw):
        out = real(doc, box, rules, **dict(kw, pour_net=None))
        out["routed"] = [n for n in out["routed"] if n != "GND"]
        out["failed"] = list(out["failed"]) + [("GND", "no way to C3-1")]
        return out
    monkeypatch.setattr(route_mod, "plan_routes", plan)
    if drc_after:
        n = []
        monkeypatch.setattr(bridge, "run_drc", lambda prj, pcb, report: (n.append(1), drc_after if len(n) == 2 else
                            {"rules": {}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True})[1])
    res = bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20, keep_partial=True)
    return calls, res


def test_keep_partial_keeps_the_board_when_the_pour_finding_is_of_a_failed_net(tmp_path, monkeypatch):
    calls, res = _kiln_partial(monkeypatch, tmp_path)
    assert any("pad C3-1 (GND) is not joined" in p for p in res["problems"])
    assert not res["restored"] and calls["restore"] == 0


def test_keep_partial_still_restores_on_a_new_clearance_violation(tmp_path, monkeypatch):
    drc = {"rules": {"Clearance Constraint (Gap=0.2mm)": 2, "Un-Routed Net Constraint": 3}, "violations": ["Clearance Constraint: x"],
           "unrouted": 3, "total": 5, "complete": True, "clean": False}
    calls, res = _kiln_partial(monkeypatch, tmp_path, drc_after=drc)
    assert res["restored"] and calls["restore"] == 1


def test_partial_ok_accepts_only_findings_of_failed_nets():
    gnd = "pad J1-1 (GND) is not joined by the pour or a track"
    assert not bridge._partial_ok(gnd) and bridge._partial_ok(gnd, [("GND", "no way")]) and bridge._partial_ok(gnd, ["GND"])
    assert not bridge._partial_ok(gnd, [("VCC", "no way")])
    dep = "GND was routed to the pour on the bottom layer but the pour is not in the saved board (see the pour warning): the GND pads are not connected"
    assert bridge._partial_ok(dep, [("GND", "x")]) and not bridge._partial_ok(dep, [("A", "x")])
    assert not bridge._partial_ok("Altium's design rule check reports 2 new Short-Circuit violations (GND)", [("GND", "x")])
    assert bridge._partial_ok("Altium's design rule check reports 7 un-routed connections", [("GND", "x")])
