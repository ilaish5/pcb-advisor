"""Physical constraints slice (W2-C): constraints.py, partlib_mech.py, layout rules, pour keep-outs, requirement rows, DRC origin.
Pure Python over fakes: nothing here ran in Altium."""
import json

import pytest

import constraints
import partlib_generate as gen
import partlib_mech
import store
from altium import layout, route
from checks import drc_origin, requirements

MIL = 0.0254


def fp(name, pads):
    return {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1} for n, x, y, w, h in pads]}


FPS = {"R0603": fp("R0603", [("1", -0.8, 0, 0.8, 0.9), ("2", 0.8, 0, 0.8, 0.9)]),
       "QFN": fp("QFN", [(str(i + 1), -2 + i, -2, 0.3, 0.8) for i in range(5)] + [("6", 2, 2, 0.3, 0.8)]),
       "MECH_HOLE_3p2": fp("MECH_HOLE_3p2", [("", 0, 0, 3.2, 3.2)])}


def part(ref, footprint, nets):
    return {"ref": ref, "footprint": footprint, "pins": [{"num": str(i + 1), "net": n} for i, n in enumerate(nets)]}


OUT = [0.0, 0.0, 40.0, 30.0]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "pdir", lambda p: tmp_path)
    (tmp_path / "idea.json").write_text(json.dumps({"goal": "x", "agreed": []}), encoding="utf-8")
    return "P"


# ------------------------------------------------------------------ items, defaults, confirmation

def test_hole_defaults_and_validation():
    it = constraints.validate_item({"kind": "mounting_hole"})
    assert it["diameter_mm"] == 3.2 and it["inset_mm"] == 3.5 and it["corners"] == ["BL", "BR", "TL", "TR"]
    assert it["status"] == "proposed"
    with pytest.raises(ValueError):
        constraints.validate_item({"kind": "mounting_hole", "diameter_mm": 99})
    with pytest.raises(ValueError):
        constraints.validate_item({"kind": "keep_apart", "a": "U1", "b": "U1"})
    with pytest.raises(ValueError):
        constraints.validate_item({"kind": "nope"})


def test_save_confirms_and_counts_as_a_change(proj):
    idea = store.load_idea_working(proj)
    idea["constraints"] = constraints.validate({"items": [{"kind": "mounting_hole", "by": "agent"}]})
    store.save_idea_draft(proj, idea)          # a draft that holds only a constraint is a draft
    assert store.idea_draft_info(proj)
    assert constraints.confirmed(store.load_idea(proj)) == []
    store.save_idea_from_draft(proj)
    saved = store.load_idea(proj)
    assert [i["status"] for i in constraints.of(saved)] == ["confirmed"]
    assert len(constraints.confirmed(saved)) == 1


def test_agent_action_writes_proposed_item_into_the_draft(proj):
    constraints._idea_constrain(proj, {"type": "idea.constrain", "op": "add", "item": {"kind": "edge", "target": "U1", "side": "top"}}, {})
    draft = store.load_idea_working(proj)
    assert [i["status"] for i in constraints.of(draft)] == ["proposed"]
    assert constraints.confirmed(store.load_idea(proj)) == []          # not yet in the saved idea: nothing downstream sees it
    with pytest.raises(ValueError):
        constraints._idea_constrain(proj, {"type": "idea.constrain", "op": "remove", "item": {"id": "zzz"}}, {})


# ------------------------------------------------------------------ library footprints and the board plan

def test_mechanical_footprint_specs():
    h = gen.mounting_hole(3.2)
    name = h["name"]
    assert name == "MECH_HOLE_3p2" and gen.is_mech_footprint(name)
    pad = next(ln for ln in h["lines"] if ln.startswith("PAD|"))
    assert pad.startswith("PAD||0.0|0.0|0|Multi-Layer|0|")          # blank name, unplated
    ko = gen.keepout_lines(-1, -1, 1, 1)
    assert sum(ln.startswith("TRACK|") for ln in ko) == 4 and sum(ln.startswith("REGION|") for ln in ko) == 1
    assert all("Keep-Out Layer" in ln for ln in ko) and not any(ln.startswith("PAD|") for ln in ko)


def test_plan_for_board_holes_in_corners():
    items = constraints.validate({"items": [{"kind": "mounting_hole", "status": "confirmed"}]})["items"]
    pl = constraints.plan_for_board(items, OUT)
    assert [h["ref"] for h in pl["holes"]] == ["H1", "H2", "H3", "H4"]
    assert {(h["x"], h["y"]) for h in pl["holes"]} == {(3.5, 3.5), (36.5, 3.5), (3.5, 26.5), (36.5, 26.5)}
    assert constraints.is_mech_ref("H3") and constraints.is_mech_ref("KO1") and not constraints.is_mech_ref("U1")
    small = constraints.plan_for_board(items, [0, 0, 6, 6])
    assert not small["holes"] and small["findings"]          # outside the board: a finding, never a hole off the board


def test_unknown_target_is_a_finding():
    items = constraints.validate({"items": [{"kind": "edge", "target": "U9", "status": "confirmed"}]})["items"]
    pl = constraints.plan_for_board(items, OUT, refs=["U1"], lines={})
    assert pl["findings"] and not pl["edge"]


# ------------------------------------------------------------------ placement

def test_placer_keeps_holes_and_puts_edge_part_at_edge():
    parts = [part("U1", "QFN", ["a", "b", "c", "d", "e", "f"]), part("R1", "R0603", ["a", "b"]), part("R2", "R0603", ["c", "d"]),
             {"ref": "H1", "footprint": "MECH_HOLE_3p2", "pins": [], "mech": "hole"}]
    rules = {"fixed": {"H1": (3.5, 3.5, 0)}, "edge": {"R1": "L"}, "apart": [("R1", "R2", 10.0)]}
    plan = layout.plan_placement(parts, FPS, OUT, rules=rules)
    assert not plan.get("errors"), plan
    at = {p["ref"]: p for p in plan["places"]}
    assert (at["H1"]["x"], at["H1"]["y"]) == (3.5, 3.5)
    r1 = layout._moved(layout.rot_box(layout.footprint_box(FPS["R0603"]), at["R1"]["rot"]), at["R1"]["x"], at["R1"]["y"])
    assert r1[0] < 3.0                                         # on the left edge side
    r2 = layout._moved(layout.rot_box(layout.footprint_box(FPS["R0603"]), at["R2"]["rot"]), at["R2"]["x"], at["R2"]["y"])
    gap = max(r2[0] - r1[2], r1[0] - r2[2], r2[1] - r1[3], r1[1] - r2[3])
    assert gap >= 10.0 - 1e-6
    for p in plan["places"]:
        if p["ref"] != "H1":
            b = layout._moved(layout.rot_box(layout.footprint_box(FPS[p["footprint"]]), p["rot"]), p["x"], p["y"])
            hb = layout._moved(layout.footprint_box(FPS["MECH_HOLE_3p2"]), 3.5, 3.5)
            assert b[2] <= hb[0] or b[0] >= hb[2] or b[3] <= hb[1] or b[1] >= hb[3]          # nothing on the hole


def test_placer_avoids_keepout():
    parts = [part("R%d" % i, "R0603", ["a", "b"]) for i in range(1, 6)]
    ko = [0, 0, 40, 10]
    plan = layout.plan_placement(parts, FPS, OUT, rules={"keepouts": [ko]})
    assert not plan.get("errors"), plan
    for p in plan["places"]:
        b = layout._moved(layout.rot_box(layout.footprint_box(FPS["R0603"]), p["rot"]), p["x"], p["y"])
        assert b[1] >= 10 - 1e-6 or b[3] <= 0 + 1e-6 or b[0] >= 40 or b[2] <= 0


# ------------------------------------------------------------------ pour and router obstacles

def _area(rects):
    return sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)


def test_pour_has_no_copper_in_keepout():
    ko = [10.0, 10.0, 20.0, 20.0]
    rects = route.pour_rects([0, 0, 40, 30], [ko])
    assert len(rects) > 1
    for r in rects:
        assert r[2] <= ko[0] or r[0] >= ko[2] or r[3] <= ko[1] or r[1] >= ko[3], r
    assert _area(rects) < _area(route.pour_rects([0, 0, 40, 30]))
    assert len(route.pour_rects([0, 0, 40, 30])) == 1
    polys = [c for c in route.route_commands("x.PcbDoc", [], pour_net="GND", box=[0, 0, 40, 30], keepouts=[ko]) if c[0] == "POLY"]
    assert len(polys) == len(rects)


def test_router_sees_component_keepout_as_obstacle():
    doc = {"pads": [], "tracks": [{"layer": 56, "x1_mm": 0, "y1_mm": 0, "x2_mm": 5, "y2_mm": 0, "width_mm": 0.2, "in_component": True}],
           "vias": [], "fills": [], "regions": [], "arcs": []}
    shapes = route.fixed_shapes(doc, {"clearance": 0.127})
    assert any(s["kind"] == "keepout" for s in shapes)


# ------------------------------------------------------------------ requirement rows (measured board)

class _Doc(dict):
    pass


def _board(monkeypatch, boxes, holes=()):
    monkeypatch.setattr(layout, "real_boxes", lambda doc: boxes)
    return {"components": [{"ref": r} for r in boxes], "drilled_pads": list(holes), "tracks": [], "vias": [], "fills": [], "regions": [],
            "pads": [], "polygons": []}


def test_every_confirmed_constraint_has_a_row(monkeypatch):
    items = constraints.validate({"items": [
        {"kind": "mounting_hole", "status": "confirmed"},
        {"kind": "edge", "target": "J1", "side": "left", "status": "confirmed"},
        {"kind": "keep_apart", "a": "U1", "b": "U2", "min_mm": 10, "status": "confirmed"},
        {"kind": "attr", "target": "U1", "attr": "heat_source", "status": "confirmed"},
        {"kind": "keepout", "rect_mm": [30, 0, 40, 10], "status": "confirmed"}]})["items"]
    holes = [{"ref": "H%d" % i, "x_mm": x, "y_mm": y, "hole_mm": 3.2, "plated": False}
             for i, (x, y) in enumerate([(3.5, 3.5), (36.5, 3.5), (3.5, 26.5), (36.5, 26.5)])]
    doc = _board(monkeypatch, {"J1": [0.5, 10, 3, 14], "U1": [10, 10, 14, 14], "U2": [18, 10, 22, 14]}, holes)
    m = requirements.measure(doc, OUT, items)
    by = {r["id"]: r for r in m["requirements"] if not str(r["id"]).startswith("auto:")}
    assert set(by) == {i["id"] for i in items}
    kinds = {r["kind"]: r["status"] for r in by.values()}
    assert kinds["mounting_hole"] == "met" and kinds["edge"] == "met"
    assert kinds["keep_apart"] == "violated"          # 4 mm apart, 10 asked
    assert kinds["attr"] == "unverifiable"            # a board file does not show a heat source
    assert kinds["keepout"] == "met"


def test_hole_missing_is_violated(monkeypatch):
    items = constraints.validate({"items": [{"kind": "mounting_hole", "status": "confirmed"}]})["items"]
    m = requirements.measure(_board(monkeypatch, {"U1": [10, 10, 14, 14]}), OUT, items)
    assert m["requirements"][0]["status"] == "violated"


def test_copper_under_keepout_is_violated(monkeypatch):
    items = constraints.validate({"items": [{"kind": "keepout", "rect_mm": [30, 0, 40, 10], "status": "confirmed"}]})["items"]
    doc = _board(monkeypatch, {"U1": [10, 10, 14, 14]})
    doc["tracks"] = [{"layer": 1, "x1_mm": 31, "y1_mm": 5, "x2_mm": 38, "y2_mm": 5, "width_mm": 0.25}]
    m = requirements.measure(doc, OUT, items)
    assert m["requirements"][0]["status"] == "violated"


def test_facts_recorded_stale_and_in_model(proj, monkeypatch, tmp_path):
    pcb = tmp_path / "b.PcbDoc"
    pcb.write_bytes(b"1")
    assert constraints.load_facts(proj) is None
    constraints.record_facts(proj, _board(monkeypatch, {"U1": [10, 10, 14, 14]}), OUT, pcb=str(pcb))
    f = constraints.load_facts(proj)
    assert f and not f.get("stale") and f["size"] == [40.0, 30.0]
    pcb.write_bytes(b"22")
    assert constraints.load_facts(proj)["stale"]
    s = constraints._summary(proj, {})
    assert s["board_facts"]["stale"] is True and s["board_facts"]["note"]
    pcb.unlink()
    constraints.record_facts(proj, _board(monkeypatch, {}), OUT, pcb="")
    assert constraints.load_facts(proj)["stale"]                    # no board file: never presented as current
    (tmp_path / "board-facts.json").unlink()
    assert "none measured" in constraints._summary(proj, {})["board_facts"]


# ------------------------------------------------------------------ DRC explained

def test_drc_origin_classes_and_unwatched():
    v = ["Silk To Solder Mask Clearance (Clearance=0.05mm) Between Pad U1-1(1mm,1mm) on Top Layer And Track (1mm,1mm)",
         "Minimum Annular Ring (Minimum=0.15mm) (Pad J1-1(2mm,2mm) Multi-Layer)",
         "Minimum Solder Mask Sliver (Gap=0.05mm) Between Pad U1-1(1mm,1mm) And Pad U1-2(1mm,2mm)",
         "Minimum Solder Mask Sliver (Gap=0.05mm) Between Pad U1-1(1mm,1mm) And Pad R1-1(1mm,2mm)"]
    assert drc_origin.origin(v[2]) == "footprint"
    assert drc_origin.origin(v[3]) == "placement"
    t = drc_origin.table({"rules": {"Minimum Solder Mask Sliver (Gap=0.05mm)": 21}, "violations": v[2:]})
    assert t and t[0]["n"] == 21 and t[0]["by_origin"].get("unlisted") == 19 and not t[0]["explained"]
    got = drc_origin.new_unwatched({"Minimum Solder Mask Sliver (Gap=0.05mm)": 7}, {"Minimum Solder Mask Sliver (Gap=0.05mm)": 21}, ("Clearance",))
    assert got and "7 -> 21" in got[0]
    assert drc_origin.new_unwatched({"Clearance Constraint": 1}, {"Clearance Constraint": 5}, ("Clearance",)) == []


# ------------------------------------------------------------------ radio module heuristic and 3D offset

def _spec(pads, other=()):
    lines = [f"PAD|{n}|{x}|{y}|0|Top Layer|1|0|0|0|0|40|40|1|" for n, x, y in pads]
    lines += [f"TRACK|{a}|{b}|{c}|{d}|10|Top Overlay" for a, b, c, d in other]
    return lines


def test_rf_module_antenna_side():
    pads = [(str(i), -300 + 60 * i, -400) for i in range(10)]
    lines = _spec(pads, other=[(-400, -450, 400, -450), (400, -450, 400, 500), (400, 500, -400, 500), (-400, 500, -400, -450)])
    rf = partlib_mech.rf_module({"mpn": "ESP32-C3-MINI-1", "description": "WiFi module"}, {"name": "MOD", "lines": lines})
    assert rf and rf["antenna_side"] == "T" and rf["keepout_box"] and rf["keepout_mm"] > 2
    assert partlib_mech.rf_module({"mpn": "LM1117", "description": "regulator"}, {"name": "SOT223", "lines": lines}) is None


def test_body_offset_issue():
    lines = _spec([("1", -50, 0), ("2", 50, 0)])
    assert partlib_mech.body_offset_issue("X", [-1, -1, 0, 1, 1, 1], {"rz": 0, "dx": 0, "dy": 0}, lines) == ""
    assert "offset" in partlib_mech.body_offset_issue("X", [4, 4, 0, 6, 6, 1], {"rz": 0, "dx": 0, "dy": 0}, lines)


# ------------------------------------------------------------------ bridge: connector direction, CPL, capabilities

def test_cpl_skips_mechanical_parts(tmp_path, monkeypatch):
    from skills import export_cpl
    doc = {"components": [{"ref": "R1", "pattern": "R0603", "layer": "Top", "x_mm": 1, "y_mm": 1},
                          {"ref": "H1", "pattern": "MECH_HOLE_3p2", "layer": "Top", "x_mm": 3, "y_mm": 3}]}
    pcb = tmp_path / "b.PcbDoc"
    pcb.write_bytes(b"x")
    monkeypatch.setattr(export_cpl, "read_pcbdoc", lambda p: doc)
    monkeypatch.setattr(export_cpl, "board_origin_mm", lambda p: (0.0, 0.0))
    monkeypatch.setattr(export_cpl, "pad_centres", lambda d: {})
    assert [r["Designator"] for r in export_cpl._raw_rows("P", pcb)] == ["R1"]


def test_capabilities_probe_with_fake_altium(tmp_path, monkeypatch):
    from altium import bridge
    monkeypatch.setattr(bridge, "TEMPLATES", tmp_path)
    (tmp_path / "Template.PcbLib").write_bytes(b"t")
    ran = []

    def reader(lib):
        return {"footprints": [{"name": "CAPS_TEST", "layers": {56: 5}, "pads": [{"hole": 3.2, "plated": False}]}]}
    monkeypatch.setattr(bridge, "read_pcblib", reader)
    cache = tmp_path / "caps.json"
    res = bridge.capabilities(runner=lambda cmds, **kw: ran.append(cmds), cache=cache)
    assert ran and ran[0][0][0] == "FPBATCH" and ran[0][1][0] == "SAVELIB"
    assert res["keepout_layer"] and res["npth"] and res["slot"] is None and not res["problems"] and not res["cached"]
    again = bridge.capabilities(runner=lambda *a, **k: pytest.fail("cached"), cache=cache)
    assert again["cached"]
    monkeypatch.setattr(bridge, "read_pcblib", lambda lib: {"footprints": [{"name": "CAPS_TEST", "layers": {}, "pads": []}]})
    bad = bridge.capabilities(force=True, runner=lambda *a, **k: None, cache=cache)
    assert not bad["keepout_layer"] and bad["problems"]

