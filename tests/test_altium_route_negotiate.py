"""The negotiated-congestion engine (altium.negotiate): rip-up and reroute, fine pitch necks, Mid-Layer 2 and the plumbing round it.
Offline: no Altium."""
import math

import dense_board
from altium import layout, negotiate, route

CLEAR, W = 0.1524, 0.2032
TWO_LAYER_BUDGET, TWO_LAYER_OPEN = 100_000_000, 3       # measured: 1 net (some GND pads) after 62.5 million cells


def pad(ref, name, x, y, net, sx=0.6, sy=0.6, layer=1, hole=0.0):
    return {"ref": ref, "name": name, "net": net, "layer": layer, "x_mm": x, "y_mm": y, "sx_mm": sx, "sy_mm": sy, "rot": 0.0, "shape": 2,
            "hole_mm": hole, "plated": True}


def rules(**kw):
    return dict(route.DEFAULTS, clearance=CLEAR, width=W, width_min=0.127, net_width={}, net_current={}, net_estimate={},
                allow_narrow=False, **kw)


def saved(doc, res):
    return dict(doc, tracks=[{"net": i["net"], "layer": i["layer"], "x1_mm": i["x1"], "y1_mm": i["y1"], "x2_mm": i["x2"],
                              "y2_mm": i["y2"], "width_mm": i["width"]} for i in res["items"] if i["kind"] == "track"],
                vias=[{"net": i["net"], "x_mm": i["x"], "y_mm": i["y"], "dia_mm": i["dia"]} for i in res["items"] if i["kind"] == "via"])


def two_nets_one_gap():
    """A wall with a gap that takes one track near both nets and a second gap far away; nothing on the bottom layer. Both nets' shortest
    way is the near gap."""
    walls = [(0.0, 4.2), (4.85, 11.5), (12.15, 14.0)]          # gaps of 0.65 mm at y 4.2..4.85 and 11.5..12.15
    pads = [pad("W", str(k), 10.0, (a + b) / 2, None, 0.6, b - a) for k, (a, b) in enumerate(walls)]
    pads.append(pad("B", "1", 10.0, 7.0, None, 20.0, 14.0, layer=32))
    pads += [pad("R1", "1", 6.0, 5.0, "A"), pad("R2", "1", 14.0, 5.0, "A"),
             pad("R3", "1", 6.0, 3.8, "B"), pad("R4", "1", 14.0, 3.8, "B")]
    return {"pads": pads, "nets": ["A", "B"]}


def test_two_nets_that_want_the_same_gap_are_negotiated_apart():
    doc, box, r = two_nets_one_gap(), [0.0, 0.0, 20.0, 14.0], rules()
    rounds = []
    res = negotiate.plan(doc, box, r, seconds=120, log=lambda n, score, _spent: rounds.append(score))
    assert res["failed"] == [], res["failed"]
    assert rounds[0][0] == 2 and rounds[-1][0] == 0, rounds        # both overlapped at first, none at the end
    assert route.violations(doc, res["items"], r, box) == []
    assert layout.unrouted(saved(doc, res)) == []
    assert res["stats"]["vias"] == 0


def test_a_net_that_cannot_fit_says_which_tracks_it_would_cross():
    doc = two_nets_one_gap()
    doc["pads"] = [p for p in doc["pads"] if p["ref"] != "W" or p["name"] != "1"]
    doc["pads"].append(pad("W", "1", 10.0, 9.425, None, 0.6, 9.15))      # the far gap is closed: one gap, two nets
    box, r = [0.0, 0.0, 20.0, 14.0], rules()
    res = negotiate.plan(doc, box, r, seconds=60)
    assert len(res["failed"]) == 1 and len(res["routed"]) == 1, res["failed"]
    name, why = res["failed"][0]
    assert "without crossing the tracks of " + res["routed"][0] in why, why
    assert route.violations(doc, res["items"], r, box) == []


def fine_pitch_row():
    """Five 0.3 mm pads at 0.5 mm pitch; the middle one belongs to a 0.6 mm wide net, its neighbours to others."""
    pads = [pad("U1", str(k + 1), 5.0 + 0.5 * k, 3.0, n, 0.3, 1.5) for k, n in enumerate(("N1", "N2", "PWR", "N3", "N4"))]
    pads.append(pad("C1", "1", 6.0, 9.0, "PWR", 1.0, 1.0))
    return {"pads": pads, "nets": ["N1", "N2", "PWR", "N3", "N4"]}


def test_a_pad_too_narrow_for_its_net_gets_a_short_neck_and_it_is_reported():
    doc, box = fine_pitch_row(), [0.0, 0.0, 12.0, 12.0]
    r = rules()
    r["net_width"] = {"PWR": 0.6}
    res = negotiate.plan(doc, box, r, seconds=60)
    assert res["failed"] == [] and "PWR" in res["routed"], res["failed"]
    assert route.violations(doc, res["items"], r, box) == []
    assert layout.unrouted(saved(doc, res)) == []
    widths = {t["width"] for t in res["items"] if t["kind"] == "track" and t["net"] == "PWR"}
    assert max(widths) == 0.6 and min(widths) >= 0.127
    necks = res["widths"]["PWR"]["necks"]
    assert [k["pad"] for k in necks] == ["U1-3"] and necks[0]["width_mm"] < 0.6
    assert 0 < necks[0]["len_mm"] <= route.NECK_MAX + 0.1
    assert "necked to" in res["widths"]["PWR"]["note"]
    thin = [t for t in res["items"] if t["kind"] == "track" and t["net"] == "PWR" and t["width"] < 0.6]
    assert all(math.hypot(t["x1"] - 6.0, t["y1"] - 3.0) <= 0.75 + route.NECK_MAX + 0.2 for t in thin)


def test_a_mid_layer_2_track_is_drawn_checked_and_counted_as_a_connection():
    items = [{"kind": "track", "layer": 3, "x1": 1.0, "y1": 1.0, "x2": 5.0, "y2": 1.0, "width": W, "net": "A"}]
    cmds = route.route_commands("B.PcbDoc", items)
    assert ("TRACK", "B.PcbDoc", "mid2", "1.0000", "1.0000", "5.0000", "1.0000", "0.2032", "A") in cmds
    tht = {"pads": [pad("J1", "1", 1.0, 1.0, "A", 1.5, 1.5, layer=74, hole=0.8), pad("J2", "1", 5.0, 1.0, "A", 1.5, 1.5, layer=74, hole=0.8),
                    pad("J3", "1", 3.0, 1.0, "B", 1.5, 1.5, layer=74, hole=0.8)], "nets": ["A", "B"]}
    box, r = [0.0, 0.0, 8.0, 4.0], rules()
    assert any("J3-1" in v for v in route.violations(tht, items, r, box))        # a through hole pad of another net is there too
    clean = dict(tht, pads=tht["pads"][:2])
    assert layout.unrouted(saved(clean, {"items": items})) == []
    assert layout.unrouted(saved(dict(clean, pads=[dict(p, layer=1, hole_mm=0) for p in clean["pads"]]), {"items": items}))


def test_four_layers_use_mid_layer_2_only_where_top_and_bottom_are_closed():
    """Walls across the whole board on the top and the bottom layer, nothing on the inner one: the only way is Mid-Layer 2."""
    pads = [pad("W", "1", 10.0, 7.0, None, 0.6, 14.0), pad("W", "2", 10.0, 7.0, None, 0.6, 14.0, layer=32),
            pad("R1", "1", 6.0, 7.0, "A"), pad("R2", "1", 14.0, 7.0, "A")]
    doc, box, r = {"pads": pads, "nets": ["A"]}, [0.0, 0.0, 20.0, 14.0], rules()
    res = negotiate.plan(doc, box, r, seconds=60, layers=4)
    assert res["failed"] == [], res["failed"]
    assert 3 in {t["layer"] for t in res["items"] if t["kind"] == "track"} and res["stats"]["vias"] == 2
    assert route.violations(doc, res["items"], r, box) == []
    two = negotiate.plan(doc, box, r, seconds=60, layers=2)
    assert [n for n, _ in two["failed"]] == ["A"] and "blocked by fixed copper" in two["failed"][0][1]


def test_four_layer_planes_are_reached_by_a_via_from_every_smd_pad():
    pads = [pad("C%d" % k, "1", 4.0 * k, 3.0, "GND") for k in (1, 2, 3)] + [pad("C%d" % k, "2", 4.0 * k, 5.0, "+3V3") for k in (1, 2, 3)]
    pads += [pad("R1", "1", 4.0, 8.0, "SIG"), pad("R2", "1", 12.0, 8.0, "SIG")]
    doc, box, r = {"pads": pads, "nets": ["GND", "+3V3", "SIG"]}, [0.0, 0.0, 16.0, 11.0], rules()
    planes = route.plane_nets_for(doc)
    assert planes == {"GND": "mid1", "+3V3": "mid2"}
    res = negotiate.plan(doc, box, r, seconds=60, planes=planes, layers=4)
    assert res["failed"] == [] and sorted(res["routed"]) == ["+3V3", "GND", "SIG"], res["failed"]
    assert route.violations(doc, res["items"], r, box) == []
    for net in planes:
        vias = [(i["x"], i["y"]) for i in res["items"] if i["kind"] == "via" and i["net"] == net]
        for p in (p for p in pads if p["net"] == net):
            ends = [(t[a], t[b]) for t in res["items"] if t["kind"] == "track" and t["net"] == net for a, b in (("x1", "y1"), ("x2", "y2"))]
            assert vias and min(math.hypot(x - p["x_mm"], y - p["y_mm"]) for x, y in vias) < 3.0 and ends, (net, p["ref"])
    assert all(t["layer"] != 2 for t in res["items"] if t["kind"] == "track")


def test_a_ground_pad_fenced_off_from_the_solid_plane_by_holes_is_reported():
    ring = [(10 + 2 * math.cos(a * math.pi / 12), 8 + 2 * math.sin(a * math.pi / 12)) for a in range(24)]
    pads = [pad("H", str(k), x, y, None, 0.7, 0.7, layer=74, hole=0.4) for k, (x, y) in enumerate(ring)]
    pads += [pad("C1", "1", 10.0, 8.0, "GND"), pad("C2", "1", 3.0, 3.0, "GND"), pad("C3", "1", 17.0, 3.0, "GND")]
    doc, box, r = {"pads": pads, "nets": ["GND"]}, [0.0, 0.0, 20.0, 14.0], rules()
    res = negotiate.plan(doc, box, r, seconds=60, planes={"GND": "mid1"}, layers=4)
    assert [n for n, _ in res["failed"]] == ["GND"] and "C1-1" in res["failed"][0][1], res["failed"]


def test_a_track_into_a_pad_at_45_degrees_ends_on_its_copper():
    pads = [dict(pad("U1", "1", 6.0, 6.0, "A", 2.0, 0.4), rot=45.0, shape=2), pad("R1", "1", 12.0, 8.0, "A")]
    res = negotiate.plan({"pads": pads, "nets": ["A"]}, [0.0, 0.0, 16.0, 12.0], rules(), seconds=60)
    assert res["failed"] == [], res["failed"]
    ends = [(t[a], t[b]) for t in res["items"] if t["kind"] == "track" for a, b in (("x1", "y1"), ("x2", "y2"))]
    assert min(math.hypot(x - 6.0, y - 6.0) for x, y in ends) <= 0.2


def test_a_dense_board_on_four_layers_routes_every_net():
    """A private board with ground and the main supply as planes, on which the greedy plans leave many nets open. Bounded by the
    searches' own budget, not by the clock, so the result does not depend on the machine."""
    doc, box, r = dense_board.load()
    planes = route.plane_nets_for(doc)
    res = route.plan_routes(doc, box, r, seconds=3600, planes=planes, layers=4)
    print(f"4 layers: {len(res['routed'])} routed, {len(res['failed'])} failed, {res['stats']}")
    assert res["failed"] == [], res["failed"]
    assert len(res["routed"]) == len([n for n, ps in route.Router(doc, box, r).pads.items() if len(ps) >= 2])
    assert route.violations(doc, res["items"], r, box) == []
    assert [n for n, _ in layout.unrouted(saved(doc, res)) if n not in planes] == []
    assert 1 not in planes and all(t["layer"] in (1, 3, 32) for t in res["items"] if t["kind"] == "track")


def test_a_dense_board_on_two_layers_routes_nearly_every_net_and_says_why_not():
    doc, box, r = dense_board.load()
    res = route.plan_routes(doc, box, r, seconds=3600, pour_net=route.pour_net_for(doc), layers=2, max_expansions=TWO_LAYER_BUDGET)
    print(f"2 layers: {len(res['routed'])} routed, {len(res['failed'])} failed, {res['stats']}")
    for name, why in res["failed"]:
        print("   ", name, why)
    assert len(res["failed"]) <= TWO_LAYER_OPEN, res["failed"]
    assert all(why.strip() for _n, why in res["failed"])
    assert route.violations(doc, res["items"], r, box) == []


def test_the_routing_time_is_one_segment_a_ceiling_and_a_work_stall_not_a_budget_per_board():
    """time_budget (seconds by pad count) is gone: a bigger board gets the same ceiling and more work, never a different clock."""
    assert not hasattr(route, "time_budget")
    assert route.SEGMENT_S < route.SECONDS_MAX and route.STALL_WORK > 0
