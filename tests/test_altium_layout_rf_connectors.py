"""Kiln LTE run (docs/E2E-KILN-LTE-DEFECTS-2026-11-24.md): E4 connectors that face inwards, E6 a radio module with no antenna rule."""
from altium import bridge, layout

MIL = 0.0254


def fp(name, pads, extent=None, bodies=None):
    """pads: [(name, x_mm, y_mm, w_mm, h_mm)]; extent {kind: [x0, y0, x1, y1] mm}"""
    out = {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1}
                                  for n, x, y, w, h in pads]}
    out["extent"] = {k: [v / MIL for v in b] for k, b in (extent or {}).items()}
    out["bodies"] = bodies or []
    return out


def part(ref, footprint, nets, names=None, **kw):
    pins = [{"num": str(i + 1), "net": n, "name": (names or [""] * len(nets))[i]} for i, n in enumerate(nets)]
    return dict({"ref": ref, "footprint": footprint, "pins": pins}, **kw)


def row(n, pitch=2.54, y=0.0, size=1.7):
    return [(str(i + 1), (i - (n - 1) / 2) * pitch, y, size, size) for i in range(n)]


R0603 = fp("R0603", [("1", -0.8, 0, 0.8, 0.9), ("2", 0.8, 0, 0.8, 0.9)])


# ---------------------------------------------------------------- E4: which way a connector opens

def test_opening_from_the_3d_body_when_the_outline_is_centred():
    f = fp("TB", row(3), extent={"silk": [-4.5, -3, 4.5, 3], "body": [-4.5, -6, 4.5, 2]})
    assert layout.opening_dir(f) is None
    assert layout.opening_guess(f) == (270, "3d body")


def test_opening_opposite_the_pad_rows_offset():
    f = fp("HDR4", row(4, y=2.0))                  # the row sits 2 mm on +y of the origin (the body centre): the plug side is -y
    assert layout.opening_guess(f) == (270, "pad rows")
    assert layout.opening_guess(fp("HDR4P1", [(n, x + 3.81, y, w, h) for n, x, y, w, h in row(4)]))[1] != "pad rows"   # origin on pin 1


def test_a_screw_terminal_opens_across_its_pad_row():
    f = fp("TB2", row(2, pitch=5.08), extent={"silk": [-5, -4.7, 5, 3.6]})     # 0.55 mm off: the outline does not tell
    assert layout.opening_dir(f) is None
    assert layout.opening_guess(f, {"ref": "J5", "bom_description": "screw terminal block 5.08 mm"}) == (270, "kind")


def test_unknown_opening_is_a_named_guess_with_the_long_side_along_the_edge():
    hdr = fp("HDR", [("1", 0, -1.27, 1.7, 1.7), ("2", 0, 1.27, 1.7, 1.7)])
    deg, src = layout.opening_guess(hdr)
    assert src == "guess" and deg in (0, 180)                  # long side on y: the opening is across it
    fps = {"HDR": hdr, "R0603": R0603}
    plan = layout.plan_placement([part("J5", "HDR", ["A", "GND"]), part("R1", "R0603", ["A", "GND"])], fps, [0, 0, 30, 20])
    assert not plan["errors"], plan
    j = next(p for p in plan["places"] if p["ref"] == "J5")
    b = layout._moved(layout.rot_box(layout.footprint_box(hdr), j["rot"]), j["x"], j["y"])
    on_bottom_or_top = b[1] < 1.5 or b[3] > 18.5
    long_x = b[2] - b[0] > b[3] - b[1]
    assert long_x == on_bottom_or_top                         # the longer side runs along the edge it sits on
    w = [x for x in plan["warnings"] if x.startswith("J5")]
    assert w and "+x" not in w[0].split("(")[0] and "assumed" not in w[0]
    assert "turn J5 180°" in w[0] and "confirm" in w[0].lower() and f"{deg} deg" in w[0]


def test_evidence_based_opening_is_used_by_the_placer():
    f = fp("TB", row(3), extent={"silk": [-4.5, -3, 4.5, 3], "body": [-4.5, -6, 4.5, 2]})
    plan = layout.plan_placement([part("J4", "TB", ["A", "B", "GND"])], {"TB": f}, [0, 0, 40, 30])
    j = next(p for p in plan["places"] if p["ref"] == "J4")
    body = layout._moved(layout.rot_box([v * MIL for v in f["extent"]["body"]], j["rot"]), j["x"], j["y"])
    pads = layout._moved(layout.rot_box(layout.pads_box(f), j["rot"]), j["x"], j["y"])
    gaps = [body[0], body[1], 40 - body[2], 30 - body[3]]
    side = gaps.index(min(gaps))                              # the edge the body is at
    # the body reaches out beyond the pads on that side: the opening faces out of the board
    assert [pads[0] - body[0], pads[1] - body[1], body[2] - pads[2], body[3] - pads[3]][side] > 2
    assert any("3d body" in w for w in plan["warnings"] if w.startswith("J4"))


# ---------------------------------------------------------------- E6: the antenna rule is derived

def _module(n_side=8, pitch=1.0, free=0.0):
    """A square module with pads on all four sides; `free` mm of pad-free outline on +x (an antenna strip)."""
    h = (n_side - 1) * pitch / 2 + 1
    pads, k = [], 1
    for i in range(n_side):
        t = (i - (n_side - 1) / 2) * pitch
        for x, y in ((-h, t), (h, t), (t, -h), (t, h)):
            pads.append((str(k), x, y, 0.6, 0.6))
            k += 1
    return fp("MOD", pads, extent={"silk": [-h - 0.5, -h - 0.5, h + 0.5 + free, h + 0.5]})


def test_a_cellular_module_by_its_bom_text_goes_to_an_edge():
    fps = {"MOD": _module(), "R0603": R0603}
    parts = [part("U6", "MOD", ["X"] * 32, bom_value="A7670G", bom_description="LTE Cat-1 module"),
             part("R1", "R0603", ["X", "GND"])]
    rf = layout.rf_rules(parts, fps)
    assert "U6" in rf["edge"] and not rf["antenna"] and any("U6" in n and "edge" in n for n in rf["notes"])
    plan = layout.plan_placement(parts, fps, [0, 0, 60, 50], rules={"edge": rf["edge"], "antenna": rf["antenna"]})
    u = next(p for p in plan["places"] if p["ref"] == "U6")
    b = layout._moved(layout.rot_box(layout.footprint_box(fps["MOD"]), u["rot"]), u["x"], u["y"])
    assert min(b[0], b[1], 60 - b[2], 50 - b[3]) < 1.0           # at an edge, not the middle of the board


def test_a_module_with_an_antenna_strip_gets_the_antenna_rule_and_a_keepout():
    fps = {"MOD": _module(free=6.0)}
    rf = layout.rf_rules([part("U1", "MOD", ["X"] * 32, bom_value="ESP32-C3-MINI-1")], fps)
    assert rf["antenna"] == {"U1": 0} and rf["keepouts"]["U1"][0] >= 4.0
    plan = layout.plan_placement([part("U1", "MOD", ["X"] * 32)], fps, [0, 0, 50, 40], rules={"antenna": rf["antenna"]})
    u = plan["places"][0]
    ko = layout._moved(layout.rot_box(rf["keepouts"]["U1"], u["rot"]), u["x"], u["y"])
    gaps = [ko[0], ko[1], 50 - ko[2], 40 - ko[3]]
    assert min(gaps) < 1.0                                       # the antenna strip lies at the edge


def test_an_antenna_pin_makes_a_radio_module_and_sets_the_antenna_end():
    mod = _module()
    names = [""] * 32
    names[1] = "ANT"                                              # pad 2 is on the +x side
    rf = layout.rf_rules([part("U2", "MOD", ["RF"] + ["X"] * 31, names=names)], {"MOD": mod})
    assert rf["antenna"] == {"U2": 0} and "antenna pin" in " ".join(rf["notes"])


def test_a_module_reached_by_an_ipex_connector_goes_to_an_edge_and_nothing_tall_crowds_the_connector():
    fps = {"MOD": _module(), "UFL": fp("UFL", [("1", 0, 0, 1, 1), ("2", -1.5, 0, 1, 2), ("3", 1.5, 0, 1, 2)]),
           "R0603": R0603, "CAP": fp("CAP", [("1", -2, 0, 1.5, 1.5), ("2", 2, 0, 1.5, 1.5)], bodies=[{"height": "10mm"}])}
    parts = [part("U6", "MOD", ["RF1"] + ["X"] * 31), part("R9", "R0603", ["RF1", "RF2"]),       # a series part of a matching network
             part("J2", "UFL", ["RF2", "GND", "GND"], bom_value="U.FL IPEX"), part("C9", "CAP", ["X", "GND"])]
    rf = layout.rf_rules(parts, fps)
    assert "U6" in rf["edge"] and ("J2", "C9", layout.RF_TALL_MM) in rf["apart"]
    assert not any(a[1] in ("U6", "R9") for a in rf["apart"])
    assert any("J2" in n and "3 mm" in n for n in rf["notes"])


def test_no_radio_no_rule():
    fps = {"MOD": _module(), "R0603": R0603}
    rf = layout.rf_rules([part("U1", "MOD", ["X"] * 32, bom_value="STM32F103"), part("R1", "R0603", ["X", "GND"])], fps)
    assert rf == {"antenna": {}, "edge": {}, "keepouts": {}, "apart": [], "notes": []}


def test_place_on_gives_the_planner_the_derived_antenna_rule(tmp_path, monkeypatch):
    import altium.pcbdoc as pcbdoc
    lib = tmp_path / "L.PcbLib"
    lib.write_bytes(b"x")
    pcb = tmp_path / "B.PcbDoc"
    pcb.write_bytes(b"pcb")
    mod = _module(free=6.0)
    monkeypatch.setattr(bridge, "read_pcblib", lambda p: {"footprints": [mod]})
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {})
    monkeypatch.setattr(bridge, "_backup", lambda prj, files: None)
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", lambda p, geometry=False: {"pads": [1], "tracks": []})
    monkeypatch.setattr(layout, "verify_layout", lambda *a, **k: [])
    seen = {}

    def spy(parts, footprints, outline, **kw):
        seen.update(kw)
        raise RuntimeError("stop")
    monkeypatch.setattr(layout, "plan_placement", spy)
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, **kw: ["pcbcheck rect=1 objects=2 parts=2 tracks=0 outline_pts=4 box_mil=0,0,1969,1575"])
    parts = [{"ref": "U6", "footprint": "MOD", "lib_ref": "U", "pins": [], "bom_value": "SIM7600E-H LTE"}]
    try:
        bridge.place_on(tmp_path / "P.PrjPcb", pcb, lib, parts, size=(50, 40))
    except RuntimeError:
        pass
    assert seen["rules"]["antenna"] == {"U6": 0}


def test_library_rf_keywords_cover_cellular_modules():
    import partlib_mech
    for t in ("A7670G LTE Cat-1", "SIM7600E-H", "WH-LTE-7S1", "nRF52840 module", "ESP32-S3"):
        assert partlib_mech.RF_RE.search(t), t
    assert not partlib_mech.RF_RE.search("LM1117 regulator SOT-223")


# ---------------------------------------------------------------- review fixes

def test_a_body_offset_along_the_pad_row_does_not_turn_a_screw_terminal():
    """Kiln PcbLib CONN-TH_2P-P5.00_WJ500V-5.08-2P: pads at x=+-2.54, body box x -8.22..2.54: the body offset is along the row."""
    f = fp("CONN-TH_2P-P5.00_WJ500V-5.08-2P", [("1", -2.54, 0, 1.8, 1.8), ("2", 2.54, 0, 1.8, 1.8)],
           extent={"body": [-8.22, -4.0, 2.54, 4.0]})
    deg, src = layout.opening_guess(f, {"ref": "J3", "bom_description": "screw terminal block"})
    assert deg in (90, 270), (deg, src)
    # a body that reaches across the rows still counts
    g = fp("TB", [("1", -2.54, 0, 1.8, 1.8), ("2", 2.54, 0, 1.8, 1.8)], extent={"body": [-8.22, -6.0, 2.54, 2.0]})
    assert layout.opening_guess(g) == (270, "3d body")


def test_text_that_names_a_radio_module_does_not_make_a_support_part_one():
    fps = {"R0603": R0603, "MOD": _module()}
    for role in ("100nF decoupling for LTE module", "bulk cap for SIM7600 VBAT", "ferrite bead WiFi supply",
                 "level shifter for ESP32 UART", "BLE antenna matching inductor"):
        rf = layout.rf_rules([part("C1", "R0603", ["X", "GND"], bom_role=role, role=role)], fps)
        assert not rf["edge"] and not rf["antenna"], role
        # a real module with that text still counts, a many-pad part named by its role only does not
    rf = layout.rf_rules([part("U1", "MOD", ["X"] * 32, bom_role="level shifter for ESP32 UART")], fps)
    assert not rf["edge"] and not rf["antenna"]
    rf = layout.rf_rules([part("U1", "MOD", ["X"] * 32, bom_value="SIM7600E")], fps)
    assert "U1" in rf["edge"] or "U1" in rf["antenna"]


def test_a_2x5_idc_header_with_silk_noise_is_a_confirmed_guess():
    pads = [(str(i * 2 + j + 1), (i - 2) * 2.54, (j - 0.5) * 2.54, 1.7, 1.7) for i in range(5) for j in range(2)]
    f = fp("IDC2x5", pads, extent={"silk": [-7, -3.2, 7, 3.2], "body": [-7, -3.2, 7, 3.2]})
    f["extent"]["silk"][1] += 0.3                                  # 0.15 mm of silk offset: noise
    deg, src = layout.opening_guess(f, {"ref": "J1", "bom_description": "IDC header 2x5"})
    assert src == "guess"
