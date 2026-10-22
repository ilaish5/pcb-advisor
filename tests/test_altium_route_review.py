"""Review round for scripts/altium/route.py: vias, clearance the grid rounds, fixed copper of every kind, honest reasons."""
import struct

from altium import pcbdoc, route
from test_altium_route import JLC, pad, rules  # noqa: F401


def _gap_to(items, geo, layers_ok):
    """Smallest copper-to-copper distance between the routed tracks / vias and a fixed shape (independent of the router's own check)."""
    lay = {1: route.TOP, 32: route.BOT}
    best = 1e9
    for it in items:
        if it["kind"] == "track" and lay[it["layer"]] in layers_ok:
            best = min(best, route._dist(geo, (it["x1"], it["y1"]), (it["x2"], it["y2"])) - it["width"] / 2)
        elif it["kind"] == "via":
            best = min(best, route._dist(geo, (it["x"], it["y"]), (it["x"], it["y"])) - it["dia"] / 2)
    return best


def _wall_doc():
    """Net A between two top SMD pads; a tall foreign pad across the whole top layer between them (the bottom layer is free)."""
    return {"pads": [pad("R1", "1", 5, 7, "A"), pad("R2", "1", 15, 7, "A"), pad("W", "1", 10, 7, "WALL", 0.8, 13.0)]}


def test_no_via_inside_or_near_an_smd_pad():
    doc = _wall_doc()
    box = [0, 0, 20, 14]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert res["routed"] == ["A"] and not res["failed"]
    vias = [i for i in res["items"] if i["kind"] == "via"]
    assert len(vias) == 2                                  # down to the bottom layer and back up: the only way past the wall
    for v in vias:
        for p in doc["pads"]:
            gap = route._seg_rect((v["x"], v["y"]), (v["x"], v["y"]), route._pad_rect(p)) - v["dia"] / 2
            assert gap >= rules()["clearance"] - 1e-6, (v, p["ref"], gap)       # not in the pad, not within clearance of its copper
    assert route.violations(doc, res["items"], rules(), box) == []


def test_violations_flags_a_via_in_an_smd_pad_of_its_own_net():
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A")]}
    via = [{"kind": "via", "net": "A", "x": 5, "y": 5, "dia": 0.6, "hole": 0.3}]
    assert route.violations(doc, via, rules(), [0, 0, 20, 14])


def test_through_hole_pad_is_the_layer_change_without_a_via():
    tht = pad("J1", "1", 10, 7, "A", 1.6, 1.6, layer=74)
    doc = {"pads": [pad("R1", "1", 4, 7, "A", layer=1), tht, pad("R2", "1", 16, 7, "A", layer=32)]}
    box = [0, 0, 20, 14]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert res["routed"] == ["A"] and not res["failed"]
    assert not [i for i in res["items"] if i["kind"] == "via"]
    assert route.violations(doc, res["items"], rules(), box) == []


def test_dense_board_on_a_coarse_grid_returns_nothing_too_close():
    """Whatever the grid rounds (here 0.25 mm), no net the router returns is too close to anything: it is routed again or named."""
    pads = [pad("U1", str(i), 10 + i * 1.0, 6, f"S{i}", 0.5, 1.2) for i in range(6)] + [pad("U1", "9", 10, 9, "+5V"), pad("J1", "1", 17, 9, "+5V")]
    pads += [pad("C1", "1", 13, 11, "S1"), pad("C1", "2", 14.5, 11.5, "S2")]
    doc = {"pads": pads}
    box = [0, 0, 24, 16]
    for pitch in (0.1, 0.25):
        res = route.plan_routes(doc, box, rules(), pitch=pitch, seconds=60)
        assert route.violations(doc, res["items"], rules(), box) == [], (pitch, res["failed"])
        assert "+5V" in res["routed"] or dict(res["failed"]).get("+5V")


def test_wide_track_is_checked_beyond_its_centre_cell():
    """A 0.3 mm rail used to be checked at its centre cell only: it hugged a foreign pad."""
    doc = {"pads": [pad("R1", "1", 4, 7, "+5V"), pad("R2", "1", 16, 7, "+5V"), pad("X", "1", 10, 7.9, "X", 3.0, 0.4)]}
    box = [0, 0, 20, 14]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert "+5V" in res["routed"]
    tr = [i for i in res["items"] if i["net"] == "+5V" and i["kind"] == "track"]
    assert max(t["width"] for t in tr) > 0.29                                            # it is a wide rail
    assert _gap_to(res["items"], ("rect", route._pad_rect(doc["pads"][2])), (route.TOP,)) >= rules()["clearance"] - 1e-6


def test_a_net_the_exact_check_finds_too_close_is_routed_again(monkeypatch):
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 8, "A"), pad("R1", "2", 5, 8, "B"), pad("R2", "2", 15, 5, "B")]}
    box = [0, 0, 20, 14]
    real, calls = route._violations, []

    def once(shapes, items, rl, bx):
        calls.append(1)
        out = real(shapes, items, rl, bx)
        return out or ([("pretend: A too close to B", ("A", "B"))] if len(calls) == 1 else [])
    monkeypatch.setattr(route, "_violations", once)
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert sorted(res["routed"]) == ["A", "B"] and not res["failed"] and res["stats"]["repaired"] == 2


def test_a_net_that_cannot_be_made_clean_is_named(monkeypatch):
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 8, "A")]}
    box = [0, 0, 20, 14]
    monkeypatch.setattr(route, "_violations", lambda shapes, items, rl, bx: [("always too close", ("A",))] if items else [])
    res = route.plan_routes(doc, box, rules(), seconds=30)
    assert res["routed"] == [] and res["failed"][0][0] == "A" and "always too close" in res["failed"][0][1]


OBSTACLES = {
    "footprint copper track": ({"tracks": [{"layer": 1, "net": None, "in_component": True, "x1_mm": 10, "y1_mm": 3, "x2_mm": 10, "y2_mm": 11,
                                            "width_mm": 0.3}]}, ("seg", (10, 3), (10, 11), 0.15), (route.TOP,)),
    "footprint copper fill": ({"fills": [{"layer": 1, "net": None, "in_component": True, "x1_mm": 9.5, "y1_mm": 3, "x2_mm": 10.5, "y2_mm": 11,
                                          "rot": 0}]}, ("rect", (9.5, 3, 10.5, 11)), (route.TOP,)),
    "free pad": ({"pads": [pad(None, "1", 10, 7, "FREE", 1.0, 6.0)]}, ("rect", (9.5, 4, 10.5, 10)), (route.TOP,)),
    "unplated hole": ({"drilled_pads": [{"ref": None, "name": "M1", "x_mm": 10, "y_mm": 7, "hole_mm": 2.0, "plated": False}]},
                      ("circ", (10, 7), 1.0), (route.TOP, route.BOT)),
    "copper region": ({"regions": [{"layer": 1, "net": None, "polygon": False, "in_component": False, "kind": 0,
                                    "points_mm": [(9.5, 3), (10.5, 3), (10.5, 11), (9.5, 11)]}]}, ("rect", (9.5, 3, 10.5, 11)), (route.TOP,)),
    "track of another net": ({"tracks": [{"layer": 1, "net": "Z", "in_component": False, "x1_mm": 10, "y1_mm": 3, "x2_mm": 10, "y2_mm": 11,
                                          "width_mm": 0.2}]}, ("seg", (10, 3), (10, 11), 0.1), (route.TOP,)),
}


def test_fixed_copper_of_every_kind_is_kept_clear():
    for name, (extra, geo, layers) in OBSTACLES.items():
        doc = {"pads": [pad("R1", "1", 4, 7, "A"), pad("R2", "1", 16, 7, "A")]}
        for k, v in extra.items():
            doc[k] = doc.get(k, []) + v
        box = [0, 0, 20, 14]
        res = route.plan_routes(doc, box, rules(), seconds=60)
        assert res["routed"] == ["A"], (name, res["failed"])
        need = rules()["clearance"]
        assert _gap_to(res["items"], geo, layers) >= need - 1e-6, name
        assert route.violations(doc, res["items"], rules(), box) == [], name


def test_unplated_hole_keeps_the_hole_to_copper_gap():
    doc = {"pads": [pad("R1", "1", 4, 7, "A"), pad("R2", "1", 16, 7, "A")],
           "drilled_pads": [{"ref": None, "name": "M1", "x_mm": 10, "y_mm": 7, "hole_mm": 2.0, "plated": False}]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(hole_clear=0.4), seconds=60)
    assert res["routed"] == ["A"]
    assert _gap_to(res["items"], ("circ", (10, 7), 1.0), (route.TOP, route.BOT)) >= 0.4 - 1e-6


def test_keepout_layer_blocks_both_layers():
    wall = {"layer": 56, "net": None, "x1_mm": 10, "y1_mm": 0, "x2_mm": 10, "y2_mm": 14, "width_mm": 0.2}
    doc = {"pads": [pad("R1", "1", 4, 7, "A"), pad("R2", "1", 16, 7, "A")], "tracks": [wall]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(), seconds=20, rounds=2)
    assert res["failed"] and res["failed"][0][0] == "A" and not res["items"]


def test_a_pad_inside_the_clearance_of_a_foreign_pad_is_not_claimed_routable():
    """Goal / source cells used to skip the free check: a pad 0.3 mm from a foreign pad at 0.5 mm clearance was 'reached'."""
    doc = {"pads": [pad("R1", "1", 10, 7, "A", 0.2, 0.2), pad("R2", "1", 4, 7, "A"), pad("R3", "1", 10.5, 7, "B", 0.2, 0.2)]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(clearance=0.5, edge=0.5), seconds=20, rounds=1)
    assert dict(res["failed"]).get("A") and "too close" in dict(res["failed"])["A"]


def test_failure_keeps_its_real_reason_and_the_result_does_not_depend_on_the_clock():
    ys = [x * 0.9 for x in range(0, 17)]
    wall = [pad("W", str(i), 10, y, f"W{i}", 0.8, 1.0) for i, y in enumerate(ys)]
    wall += [pad("W", str(i + 20), 10, y, f"V{i}", 0.8, 1.0, layer=32) for i, y in enumerate(ys)]
    doc = {"pads": wall + [pad("A", "1", 4, 7, "ISO"), pad("B", "1", 16, 7, "ISO")]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(), seconds=60, rounds=1)
    why = dict(res["failed"])["ISO"]
    assert "ran out of time" not in why and ("blocked by fixed copper" in why or "no way" in why)
    a = route.plan_routes(_wall_doc(), [0, 0, 20, 14], rules(), seconds=30)
    b = route.plan_routes(_wall_doc(), [0, 0, 20, 14], rules(), seconds=3000)
    assert a["items"] == b["items"]


def test_search_limit_is_not_reported_as_no_way():
    rt = route.Router(_wall_doc(), [0, 0, 20, 14], rules(), 0.1)
    nid = rt.netid["A"]
    src = {(0, c) for c in rt.pads["A"][0]["cells"][0]}
    goals = {(0, c) for c in rt.pads["A"][1]["cells"][0]}
    assert rt.astar(nid, src, goals, 0.127, max_pops=5) is None and rt.status == "limit"
    paths, _, why = rt.route_net("A", 0.127)
    assert paths is not None and why is None


def test_pour_net_needs_three_ground_pads():
    gnd = lambda n: {"pads": [pad("R" + str(i), "1", i, 1, "GND") for i in range(n)]}
    assert route.pour_net_for(gnd(2)) is None and route.pour_net_for(gnd(3)) == "GND"
    cmds = route.route_commands("X.PcbDoc", [], False, pour_net="GND", box=[0, 0, 20, 10], edge=0.3)
    assert cmds[-2][:4] == ("POLY", "X.PcbDoc", "bottom", "GND") and cmds[-1][0] == "PCBSAVE"
    assert route.route_commands("X.PcbDoc", [], False)[-2][0] == "ROUTEBEGIN"


def test_pcbdoc_parsers_read_regions_fills_and_component_flags():
    hdr = lambda layer, net, poly, comp: bytes([layer]) + b"\x0c\x00" + struct.pack("<HHH", net, poly, comp) + b"\xff" * 4 + b"\x00" * 5
    text = b"V7_LAYER=TOP|KIND=0|ISSHAPEBASED=FALSE\x00"
    pts = [(1000000.0, 2000000.0), (3000000.0, 2000000.0), (3000000.0, 4000000.0)]
    body = hdr(1, 0xFFFF, 0xFFFF, 3) + struct.pack("<I", len(text)) + text + struct.pack("<I", 3) + b"".join(struct.pack("<dd", *p) for p in pts)
    reg = pcbdoc.parse_regions(b"\x0b" + struct.pack("<I", len(body)) + body, ["N"])
    assert len(reg) == 1 and reg[0]["in_component"] and not reg[0]["polygon"] and reg[0]["kind"] == 0 and len(reg[0]["points_mm"]) == 3
    fill = hdr(33, 0, 0xFFFF, 0xFFFF)[:13] + struct.pack("<4i", 0, 0, 100000, 200000) + struct.pack("<d", 90.0) + b"\x00" * 4
    fl = pcbdoc.parse_fills(b"\x06" + struct.pack("<I", len(fill)) + fill, ["N"])
    assert fl[0]["net"] == "N" and not fl[0]["in_component"] and fl[0]["rot"] == 90.0 and abs(fl[0]["x2_mm"] - 0.254) < 1e-6
