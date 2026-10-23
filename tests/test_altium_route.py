"""The agent's own router (scripts/altium/route.py): rules, routing small and denser synthetic boards, the independent check, commands."""
from altium import layout, route
from altium.bridge import _drc_counts


def pad(ref, name, x, y, net, w=0.8, h=0.9, layer=1):
    return {"ref": ref, "name": name, "x_mm": x, "y_mm": y, "sx_mm": w, "sy_mm": h, "rot": 0, "net": net, "layer": layer}


JLC = dict(clearance=0.127, width=0.127, width_min=0.127, width_max=10, via_dia=0.6, via_hole=0.3, edge=0.3)


def rules(**kw):
    r = dict(route.rules_from_doc({}), **JLC)
    r.update(kw)
    return r


def as_board(doc, items):
    return dict(doc, tracks=[{"layer": i["layer"], "net": i["net"], "x1_mm": i["x1"], "y1_mm": i["y1"], "x2_mm": i["x2"], "y2_mm": i["y2"],
                              "width_mm": i["width"]} for i in items if i["kind"] == "track"],
                vias=[{"net": i["net"], "x_mm": i["x"], "y_mm": i["y"], "dia_mm": i["dia"], "hole_mm": i["hole"]} for i in items if i["kind"] == "via"])


def test_rules_from_doc_and_fallbacks():
    d = route.rules_from_doc({})
    assert d["clearance"] == 0.127 and d["width"] == 0.127 and d["via_dia"] == 0.6 and d["via_hole"] == 0.3
    doc = {"rules": [{"RULEKIND": "Clearance", "GAP": "10mil", "ENABLED": "TRUE"},
                     {"RULEKIND": "Clearance", "GAP": "20mil", "ENABLED": "FALSE"},
                     {"RULEKIND": "Width", "SCOPE1EXPRESSION": "All", "MINLIMIT": "8mil", "MAXLIMIT": "20mil", "PREFEREDWIDTH": "10mil", "ENABLED": "TRUE"},
                     {"RULEKIND": "Width", "SCOPE1EXPRESSION": "InNet('+5V')", "MINLIMIT": "20mil", "MAXLIMIT": "40mil", "PREFEREDWIDTH": "30mil",
                      "ENABLED": "TRUE"},
                     {"RULEKIND": "RoutingVias", "WIDTH": "20mil", "HOLEWIDTH": "10mil", "ENABLED": "TRUE"}]}
    r = route.rules_from_doc(doc)
    assert abs(r["clearance"] - 0.254) < 1e-6 and abs(r["width"] - 0.254) < 1e-6      # the disabled 20 mil gap is ignored
    assert abs(r["net_width"]["+5V"] - 0.762) < 1e-6
    assert abs(r["via_dia"] - 0.508) < 1e-6 and r["edge"] >= r["clearance"]


def test_two_pads_routed_clean():
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 8, "A"), pad("R1", "2", 5, 8, "B"), pad("R2", "2", 15, 5, "B")]}
    box = [0, 0, 20, 14]
    res = route.plan_routes(doc, box, rules(), seconds=30)
    assert sorted(res["routed"]) == ["A", "B"] and not res["failed"]
    assert route.violations(doc, res["items"], rules(), box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []


def test_dense_board_with_an_ic_routes_and_checks():
    """Not tuned to a handful of parts: a 16-pin SOIC-like IC with 8 decoupling-style resistors, two layers."""
    pads = []
    for i in range(8):
        pads.append(pad("U1", str(i + 1), 12 + i * 1.27, 14, f"S{i}", 0.6, 1.6))
        pads.append(pad("U1", str(16 - i), 12 + i * 1.27, 20, f"T{i}" if i % 2 else "GND", 0.6, 1.6))
    for i in range(8):
        pads.append(pad(f"R{i}", "1", 8 + i * 3, 8, f"S{i}"))
        pads.append(pad(f"R{i}", "2", 8 + i * 3, 10.5, "GND"))
    doc = {"pads": pads}
    box = [0, 0, 40, 30]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert not res["failed"], res["failed"]
    assert route.violations(doc, res["items"], rules(), box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []
    gnd = [i for i in res["items"] if i["net"] == "GND" and i["kind"] == "track"]
    assert gnd                                             # ground gets copper tracks, not only a pour


def test_failure_is_reported_with_a_reason():
    """A net walled in by a foreign net across the whole board has no path on either layer: reported, never claimed."""
    wall = [pad("W", str(i), 10, y, f"W{i}", 0.8, 1.0) for i, y in enumerate([x * 0.9 for x in range(0, 17)])]
    wall += [pad("W", str(i + 20), 10, y, f"V{i}", 0.8, 1.0, layer=32) for i, y in enumerate([x * 0.9 for x in range(0, 17)])]
    doc = {"pads": wall + [pad("A", "1", 4, 7, "ISO"), pad("B", "1", 16, 7, "ISO")]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(), seconds=3, rounds=1)
    assert dict(res["failed"]).get("ISO")


def test_violations_catches_a_bad_track():
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A"), pad("R3", "1", 10, 5.5, "B"), pad("R4", "1", 10, 9, "B")]}
    bad = [{"kind": "track", "layer": 1, "net": "A", "x1": 5, "y1": 5, "x2": 15, "y2": 5, "width": 0.127}]
    assert route.violations(doc, bad, rules(), [0, 0, 20, 14])                      # runs through R3's pad
    edge = [{"kind": "track", "layer": 1, "net": "A", "x1": 0.05, "y1": 5, "x2": 5, "y2": 5, "width": 0.127}]
    assert route.violations({"pads": []}, edge, rules(), [0, 0, 20, 14])           # on the board edge


def test_unrouted_sees_open_and_closed_nets():
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 5, "A")]}
    assert layout.unrouted(as_board(doc, []))[0][0] == "A"
    t = [{"kind": "track", "layer": 1, "net": "A", "x1": 5, "y1": 5, "x2": 15, "y2": 5, "width": 0.2}]
    assert layout.unrouted(as_board(doc, t)) == []
    gap = [{"kind": "track", "layer": 1, "net": "A", "x1": 5, "y1": 5, "x2": 9, "y2": 5, "width": 0.2},
           {"kind": "track", "layer": 1, "net": "A", "x1": 10, "y1": 5, "x2": 15, "y2": 5, "width": 0.2}]
    assert layout.unrouted(as_board(doc, gap))                                      # a 1 mm gap in the middle
    other_layer = [{"kind": "track", "layer": 32, "net": "A", "x1": 5, "y1": 5, "x2": 15, "y2": 5, "width": 0.2}]
    assert layout.unrouted(as_board(doc, other_layer))                              # bottom copper does not touch SMD pads without vias


def test_route_commands():
    items = [{"kind": "track", "layer": 1, "net": "A", "x1": 1, "y1": 2, "x2": 3, "y2": 2, "width": 0.2},
             {"kind": "via", "net": "A", "x": 3, "y": 2, "dia": 0.6, "hole": 0.3}]
    c = route.route_commands("X.PcbDoc", items, replace=True)
    assert c[0] == ("ROUTEBEGIN", "X.PcbDoc", "1") and c[1][0] == "TRACK" and c[1][2] == "top" and c[2][0] == "VIA" and c[-1][0] == "PCBSAVE"
    assert route.route_commands("X", [], False)[0][2] == "0"


def test_drc_counts_prefix_match():
    r = {"rules": {"Clearance Constraint (Gap=0.254mm) (All),(All)": 2, "Un-Routed Net Constraint ( (All) )": 3, "Other": 9}}
    assert _drc_counts(r) == {"Clearance Constraint": 2, "Un-Routed Net": 3}


def test_round_pad_is_not_joined_at_its_box_corner():
    """Altium: a track ending at the corner of an oval pad's box does not touch the pad (the live DRC said so)."""
    oval = dict(pad("J1", "1", 10, 10, "G", 1.2, 2.0), shape=1)
    rect = dict(oval, shape=2)
    other = pad("R1", "1", 4, 10, "G")
    t = [{"kind": "track", "layer": 1, "net": "G", "x1": 4, "y1": 10, "x2": 9.42, "y2": 9.02, "width": 0.127}]      # ends at the box corner
    assert layout.unrouted(as_board({"pads": [oval, other]}, t))
    assert layout.unrouted(as_board({"pads": [rect, other]}, t)) == []
    t2 = [{"kind": "track", "layer": 1, "net": "G", "x1": 4, "y1": 10, "x2": 10, "y2": 10, "width": 0.127}]
    assert layout.unrouted(as_board({"pads": [oval, other]}, t2)) == []


def test_router_ends_tracks_inside_an_oval_pad():
    oval = dict(pad("J1", "1", 10, 7, "G", 1.2, 2.0), shape=1)
    doc = {"pads": [oval, pad("R1", "1", 4, 12, "G")]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(), seconds=20)
    assert res["routed"] == ["G"]
    assert layout.unrouted(as_board(doc, res["items"])) == []


def _soic8(ref, cx, cy, nets):
    """SOIC-8 (1.27 mm pitch, 5.4 mm between the pad rows): pins 1-4 along the bottom row, 5-8 back along the top."""
    out = []
    for k in range(4):
        out.append(pad(ref, str(k + 1), cx - 1.905 + k * 1.27, cy - 2.7, nets[k], 0.6, 1.6))
        out.append(pad(ref, str(8 - k), cx - 1.905 + k * 1.27, cy + 2.7, nets[7 - k], 0.6, 1.6))
    return out


def dense_board():
    """Two SOIC-8 and 15 0603 passives on 40 x 30 mm, with the roomy numbers of a student's project (0.254 clearance, 1.27 via)."""
    u1 = ["GND", "N1", "N2", "N3", "N4", "N5", "N6", "+5V"]
    u2 = ["GND", "N4", "N7", "N2", "N8", "N9", "N5", "+5V"]
    pads = _soic8("U1", 12, 15, u1) + _soic8("U2", 28, 15, u2)
    parts = [("N1", "GND"), ("N3", "+5V"), ("N6", "GND"), ("N7", "+5V"), ("N8", "GND"), ("N9", "+5V"), ("N1", "N6"), ("N3", "N7"),
             ("N2", "GND"), ("N4", "+5V"), ("N5", "GND"), ("N8", "N9"), ("N7", "GND"), ("N6", "+5V"), ("N9", "GND")]
    for k, (a, b) in enumerate(parts):
        x, y = 5 + (k % 5) * 7.5, 5 if k < 5 else 25 if k < 10 else 9.5
        if k >= 10:
            x = 8 + (k - 10) * 6
        pads += [pad(f"R{k}", "1", x, y, a, 0.8, 0.95), pad(f"R{k}", "2", x + 1.6, y, b, 0.8, 0.95)]
    return {"pads": pads}


def test_dense_two_soic_and_fifteen_passives_routes_within_budget():
    """The class of board a student draws (it ran out of time at the old router): all nets, rule-clean, in seconds not minutes."""
    import time
    doc, box = dense_board(), [0, 0, 40, 30]
    r = rules(clearance=0.254, width=0.254, width_min=0.254, via_dia=1.27, via_hole=0.71)
    t0 = time.time()
    res = route.plan_routes(doc, box, r, seconds=60)
    assert not res["failed"], res["failed"]
    assert time.time() - t0 < 30
    assert route.violations(doc, res["items"], r, box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []
