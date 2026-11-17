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
    wall = [pad("W", str(i), 10, y, f"W{i}", 0.8, 1.5) for i, y in enumerate([x * 0.9 for x in range(0, 17)])]
    wall += [pad("W", str(i + 20), 10, y, f"V{i}", 0.8, 1.5, layer=32) for i, y in enumerate([x * 0.9 for x in range(0, 17)])]
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
    t0 = time.process_time()        # this process's CPU time: other work on the machine does not make the router look slow
    res = route.plan_routes(doc, box, r, seconds=60)
    assert not res["failed"], res["failed"]
    assert time.process_time() - t0 < 30
    assert route.violations(doc, res["items"], r, box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []


def _fine_row(pitch, w=0.3, h=1.0):
    """A row of 8 fine pitch pads (like a USB-C receptacle); the two middle ones are the nets CC1 and CC2, going to parts 4 mm up."""
    nets = ["G", "V", "D1", "CC1", "CC2", "D2", "V", "G"]
    pads = [pad("J1", str(i + 1), 10 + (i - 3.5) * pitch, 5, n, w, h) for i, n in enumerate(nets)]
    pads += [pad("R1", "1", 9.5, 10, "CC1"), pad("R2", "1", 10.5, 10, "CC2")]
    return {"pads": pads}


def test_fine_pitch_pad_escapes_along_its_axis_and_keeps_clearance():
    """0.5 mm pitch, 0.3 mm pads, 0.2 mm clearance: a centred 0.2032 mm track keeps 0.248 mm from the neighbours; the router must find it."""
    doc, box = _fine_row(0.5), [0, 0, 20, 14]
    r = rules(clearance=0.2, width=0.2032, width_min=0.2032)
    res = route.plan_routes(doc, box, r, seconds=30)
    assert "CC1" in res["routed"] and "CC2" in res["routed"], res["failed"]
    assert route.violations(doc, res["items"], r, box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == [] or all(n[0] not in ("CC1", "CC2") for n in layout.unrouted(as_board(doc, res["items"])))
    shapes = route.fixed_shapes(doc, r)
    for it in res["items"]:
        if it["kind"] != "track":
            continue
        for s in shapes:                                   # exact, on our own: no segment is nearer than the clearance to another net
            if s["net"] != it["net"]:
                d = route._dist(s["geo"], (it["x1"], it["y1"]), (it["x2"], it["y2"])) - it["width"] / 2
                assert d >= 0.2 - 1e-3, (it, s["tag"], d)
    cc1 = [i for i in res["items"] if i["net"] == "CC1" and i["kind"] == "track"]
    assert any(abs(i["x1"] - 9.75) < 1e-6 and abs(i["x2"] - 9.75) < 1e-6 for i in cc1)      # leaves the pad straight up along its centre line


def test_fine_pitch_pad_with_no_legal_track_is_refused():
    """0.4 mm pitch, 0.3 mm pads: 0.4 - 0.15 - 0.1016 = 0.148 mm < 0.2 mm, no legal track exists: refused, nothing drawn for those nets."""
    doc, box = _fine_row(0.4), [0, 0, 20, 14]
    r = rules(clearance=0.2, width=0.2032, width_min=0.2032)
    res = route.plan_routes(doc, box, r, seconds=30)
    failed = dict(res["failed"])
    assert "CC1" in failed and "CC2" in failed
    assert not [i for i in res["items"] if i["net"] in ("CC1", "CC2")]
    assert route.violations(doc, res["items"], r, box) == []


# ---- USB data pair (scripts/altium/pair.py)
from altium import pair


def usb_board(extra=()):
    """A USB connector (D+ at y 10, D- at y 11.2) to an MCU (two pads 1.2 mm apart, 2 mm higher)."""
    return {"pads": [pad("J1", "A6", 5, 10, "USB_DP", 0.6, 0.3), pad("J1", "A7", 5, 10.8, "USB_DM", 0.6, 0.3),
                     pad("U1", "21", 25, 12, "USB_DP", 0.6, 0.3), pad("U1", "22", 25, 12.8, "USB_DM", 0.6, 0.3)] + list(extra)}


def test_usb_pair_is_routed_coupled_and_clean():
    doc, box = usb_board(), [0, 0, 30, 24]
    res = route.plan_routes(doc, box, rules(), seconds=30)
    assert not res["failed"] and route.violations(doc, res["items"], rules(), box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []
    (pr,) = res["pairs"]
    assert pr["coupled"] and pr["nets"] == ["USB_DP", "USB_DM"], pr
    assert pr["mismatch_mm"] <= 0.25, pr                                # the fan-out at the pads costs some length; above 0.15 it is flagged
    assert pr["mismatch_ok"] == (pr["mismatch_mm"] <= pair.TOLERANCE_MM) and (pr["mismatch_ok"] or "guideline" in pr["note"]), pr
    assert pr["gap_mm"] >= 0.127 and pr["width_mm"] >= 0.2 and "not impedance-controlled" in pr["note"]
    assert not [i for i in res["items"] if i["kind"] == "via"]
    assert abs(pr["length_p"] - pair._length(res["items"], "USB_DP")) < 1e-3 and pr["length_p"] > 20


def test_usb_pair_with_an_obstacle_falls_back_and_says_so():
    """A foreign pad wall with two gaps, each too narrow for two tracks: both nets are still routed, one by one, and it is reported."""
    ys = [x * 1.0 for x in range(0, 24)]
    wall = [pad("W", str(i), 15, y, f"W{i}", 0.8, 1.5) for i, y in enumerate(ys) if y not in (12.0, 14.0)]
    wall += [pad("W", str(i + 40), 15, y, f"V{i}", 0.8, 1.5, layer=32) for i, y in enumerate(ys)]
    doc, box = usb_board(wall), [0, 0, 30, 24]
    res = route.plan_routes(doc, box, rules(), seconds=30)
    (pr,) = res["pairs"]
    assert not pr["coupled"] and pr["note"].startswith("not routed as a coupled pair: "), pr
    assert route.violations(doc, res["items"], rules(), box) == []


def test_no_usb_nets_leaves_plan_routes_unchanged():
    doc = {"pads": [pad("R1", "1", 5, 5, "A"), pad("R2", "1", 15, 8, "A")]}
    res = route.plan_routes(doc, [0, 0, 20, 14], rules(), seconds=30)
    assert res["pairs"] == [] and res["routed"] == ["A"] and not res["failed"]


def test_find_pairs_names_and_non_pairs():
    for p, n in [("D+", "D-"), ("DP", "DM"), ("USB_DP", "USB_DN"), ("USB_D+", "USB_D-"), ("USBDP", "USBDM"), ("usb_dp", "usb_dm")]:
        assert pair.find_pairs([p, n, "GND"]) == [(p, n, "usb")], (p, n)
    assert pair.find_pairs(["D+", "GND"]) == [] and pair.find_pairs(["DP", "GND", "DATA"]) == []
    assert pair.find_pairs(["USB_DP", "DM"]) == []                      # different prefixes are not one pair
    assert pair.find_pairs(["ADP", "ADM"]) == []


def test_find_pairs_by_pin_names():
    pads = [pad("U1", "21", 0, 0, "N1", 1, 1), pad("U1", "22", 0, 2, "N2", 1, 1), pad("J1", "2", 9, 0, "N1"), pad("J1", "3", 9, 2, "N2")]
    pads[0]["pin_name"], pads[1]["pin_name"] = "PA12 (USB_DP)", "PA11 (USB_DM)"
    assert pair.find_pairs({"pads": pads}) == [("N1", "N2", "usb")]
    pads[1]["pin_name"] = "PA11"                                        # one side only: no pair
    assert pair.find_pairs({"pads": pads}) == []


def usbc_board(extra=(), mcu_x=(12.8, 12.0), mcu_y=6.0):
    """A 16-pin USB-C receptacle (land pattern of the GCT USB4105 / HRO TYPE-C-31-M-12: one row, 0.5 mm pitch, 0.3 x 1.15 signal pads;
    B7 A6 A7 B6 = D- D+ D- D+ interleaved, each net on two pads) at the top, an MCU with two data pins below."""
    cx, cy = 10.0, 20.0
    row = [("A1B12", -3.2, "GND", 0.6), ("A4B9", -2.4, "VBUS", 0.6), ("B8", -1.75, "SBU2", 0.3), ("A5", -1.25, "CC1", 0.3),
           ("B7", -0.75, "USB_DM", 0.3), ("A6", -0.25, "USB_DP", 0.3), ("A7", 0.25, "USB_DM", 0.3), ("B6", 0.75, "USB_DP", 0.3),
           ("A8", 1.25, "SBU1", 0.3), ("B5", 1.75, "CC2", 0.3), ("B4A9", 2.4, "VBUS", 0.6), ("B1A12", 3.2, "GND", 0.6)]
    pads = [pad("J1", nm, cx + dx, cy, net, w, 1.15) for nm, dx, net, w in row]
    pads += [pad("U1", "PA12", mcu_x[0], mcu_y, "USB_DP", 0.4, 0.8), pad("U1", "PA11", mcu_x[1], mcu_y, "USB_DM", 0.4, 0.8)]
    return {"pads": pads + list(extra)}


def test_usb_c_connector_pair_is_tied_and_coupled_or_reported():
    doc, box = usbc_board(), [0, 0, 24, 26]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    assert route.violations(doc, res["items"], rules(), box) == []
    (pr,) = res["pairs"]
    assert not dict(res["failed"]).get("USB_DP") and not dict(res["failed"]).get("USB_DM"), res["failed"]
    if pr["coupled"]:
        assert pr["tie_vias"] in (0, 2, 4) and "not impedance-controlled" in pr["note"]
        assert [i for i in res["items"] if i["kind"] == "via" and i.get("role") != "tie"] == []   # no via in the pair itself
    else:
        assert pr["note"].startswith("not routed as a coupled pair: "), pr


def test_usb_esd_part_in_the_pair_is_a_reported_fallback():
    esd = [pad("D1", "1", 12, 12, "USB_DP", 0.5, 0.5), pad("D1", "3", 12.8, 12, "USB_DM", 0.5, 0.5)]
    doc, box = usbc_board(esd), [0, 0, 24, 26]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    (pr,) = res["pairs"]
    assert not pr["coupled"] and "ESD part in the pair" in pr["note"], pr
    assert route.violations(doc, res["items"], rules(), box) == []


def test_offset_that_reverses_on_a_short_inner_segment_is_refused():
    pts = [(0, 0), (3, 0), (3.2, 0.2), (3.2, 3)]                      # the 0.28 mm diagonal between two left turns, gap 0.4
    assert not pair._offset_ok(pts, pair._offset(pts, 0.4))             # inner side: the diagonal is eaten, a bow tie
    assert pair._offset_ok(pts, pair._offset(pts, -0.4))                # outer side is fine
    assert pair._offset([(0, 0), (1, 0), (0, 0.0001)], 0.2) is None     # a turn of 180 degrees has no mitre


def test_find_pairs_otg_names_and_pin_names_inside_plan_routes():
    assert pair.find_pairs(["USB_OTG_FS_DP", "USB_OTG_FS_DM"]) == [("USB_OTG_FS_DP", "USB_OTG_FS_DM", "usb")]
    assert pair.find_pairs(["USB_OTG_HS_DP", "USB_OTG_HS_DM"]) == [("USB_OTG_HS_DP", "USB_OTG_HS_DM", "usb")]
    pads = [pad("J1", "2", 5, 10, "N1", 0.6, 0.5), pad("J1", "3", 5, 10.8, "N2", 0.6, 0.5),
            pad("U1", "21", 25, 12, "N1", 0.6, 0.5), pad("U1", "22", 25, 12.8, "N2", 0.6, 0.5)]
    pads[2]["pin_name"], pads[3]["pin_name"] = "PA12 (USB_OTG_FS_DP)", "PA11 (USB_OTG_FS_DM)"
    doc = {"pads": pads}
    assert pair.find_pairs(doc) == [("N1", "N2", "usb")]
    res = route.plan_routes(doc, [0, 0, 30, 24], rules(), seconds=30)       # pin names reach pre_route through plan_routes
    assert [pr["nets"] for pr in res["pairs"]] == [["N1", "N2"]]


def test_connector_ties_are_made_when_the_pair_is_not_coupled(monkeypatch):
    """The pair cannot be coupled (forced here): the two pads of one net at the USB-C connector, with a pad of the other net between
    them, are still joined under the connector, so neither net is left unrouted between its own two connector pads."""
    monkeypatch.setattr(pair, "_try_pair", lambda *a, **k: "forced for the test")
    doc, box = usbc_board(), [0, 0, 24, 26]
    res = route.plan_routes(doc, box, rules(), seconds=60)
    (pr,) = res["pairs"]
    assert not pr["coupled"] and "forced for the test" in pr["note"], pr
    assert not res["failed"], res["failed"]
    assert route.violations(doc, res["items"], rules(), box) == []
    assert layout.unrouted(as_board(doc, res["items"])) == []
    ties = [i for i in res["items"] if i.get("role") == "tie"]
    assert {i["net"] for i in ties} == {"USB_DP", "USB_DM"}


def test_pair_pad_choices_cover_either_pad_of_each_net_at_the_connector():
    rt = route.Router(usbc_board(), [0, 0, 24, 26], rules(), 0.1)
    ends, why = pair._ends(rt, "USB_DP", "USB_DM")
    assert why is None
    conn = next(e for e in ends if {q["tag"].split("-")[0] for q in e["P"]} == {"J1"})
    ch = pair._choices(conn)
    assert len(ch) >= 2                                                 # the pair can leave from either side of the pad between
    assert {(c[0]["tag"], c[1]["tag"]) for c in ch} >= {("J1-A6", "J1-A7"), ("J1-B6", "J1-A7")}
    assert all(len(c[2]) == 2 for c in ch)                              # each choice names the tie of both nets


def test_search_budget_is_a_count_of_cells_not_the_clock():
    """The same board with the same budget gives the same result, and a budget that runs out says so."""
    doc, box = dense_board(), [0, 0, 40, 30]
    r = rules(clearance=0.254, width=0.254, width_min=0.254, via_dia=1.27, via_hole=0.71)
    a = route.plan_routes(doc, box, r, seconds=60, max_expansions=3000)
    b = route.plan_routes(doc, box, r, seconds=60, max_expansions=3000)
    assert a["items"] == b["items"] and a["failed"] == b["failed"] and a["stats"]["expansions"] == b["stats"]["expansions"]
    assert a["failed"] and all("budget" in why for _, why in a["failed"]), a["failed"]
    assert a["stats"]["expansions"] <= 3000 + 1


def test_a_poured_net_is_dropped_to_the_pour_by_vias_not_routed_by_tracks_to_each_other():
    doc, box = dense_board(), [0, 0, 40, 30]
    r = rules(clearance=0.254, width=0.254, width_min=0.254, via_dia=1.27, via_hole=0.71)
    res = route.plan_routes(doc, box, r, seconds=60, pour_net="GND")
    assert not res["failed"], res["failed"]
    assert route.violations(doc, res["items"], r, box) == []
    assert res["pour"]["net"] == "GND" and res["pour"]["mode"] in ("drops", "tracks")
    gnd = [i for i in res["items"] if i["net"] == "GND"]
    if res["pour"]["mode"] == "drops":
        assert any(i["kind"] == "via" for i in gnd)
        assert not [i for i in gnd if i["kind"] == "track" and i["layer"] == 32]      # the bottom layer copper of ground is the pour
        assert all(abs(i["x1"] - i["x2"]) + abs(i["y1"] - i["y2"]) < 8 for i in gnd if i["kind"] == "track")   # stubs, not a web
