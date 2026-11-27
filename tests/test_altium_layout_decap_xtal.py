"""Spec phase 3 placement rules (scripts/altium/layout.py): decoupling caps within 3 mm of their own supply pin, crystal next to the
MCU oscillator pins with its load caps. Pure Python, offline (plan_placement)."""
import math

from pytest import approx

import store
from altium import layout

MIL = 0.0254


def fp(name, pads):
    return {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1}
                                   for n, x, y, w, h in pads]}


# 16-pin MCU, 4 pins a side on a 9 mm square: 1-4 bottom, 5-8 right, 9-12 top, 13-16 left
_MCU_PADS = ([(str(1 + i), -2.25 + 1.5 * i, -4.5, 0.4, 1.0) for i in range(4)] + [(str(5 + i), 4.5, -2.25 + 1.5 * i, 1.0, 0.4) for i in range(4)] +
             [(str(9 + i), 2.25 - 1.5 * i, 4.5, 0.4, 1.0) for i in range(4)] + [(str(13 + i), -4.5, 2.25 - 1.5 * i, 1.0, 0.4) for i in range(4)])
FPS = {"MCU": fp("MCU", _MCU_PADS),
       "C0402": fp("C0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]),
       "XTAL": fp("XTAL", [("1", -1.1, 0, 1.4, 1.9), ("2", 1.1, 0, 1.4, 1.9)]),
       "WALL": fp("WALL", [("1", -10, -10, 1, 1), ("2", 10, 10, 1, 1)])}
OUT = [0, 0, 60, 40]
VDD_PINS = {"1", "6", "11", "16"}


def part(ref, footprint, nets, names=None, value=None):
    p = {"ref": ref, "footprint": footprint,
         "pins": [{"num": str(i + 1), "net": n, **({"name": names[i]} if names else {})} for i, n in enumerate(nets)]}
    if value:
        p["value"] = value
    return p


def mcu(vdd_net="+3V3", osc=None):
    nets, names = [], []
    for i in range(1, 17):
        if str(i) in VDD_PINS:
            nets.append(vdd_net), names.append("VDD")
        elif i in (4, 8, 12, 13):
            nets.append("GND"), names.append("VSS")
        elif osc and i == 14:
            nets.append(osc[0]), names.append("PH0-OSC_IN")
        elif osc and i == 15:
            nets.append(osc[1]), names.append("PH1-OSC_OUT")
        else:
            nets.append(f"IO{i}"), names.append(f"PA{i}")
    return part("U1", "MCU", nets, names)


def at_of(plan):
    return {p["ref"]: p for p in plan["places"]}


def pad_xy(plan, parts, ref, pad):
    p = at_of(plan)[ref]
    fpd = FPS[next(q for q in parts if q["ref"] == ref)["footprint"]]
    q = next(q for q in fpd["pads"] if q["name"] == pad)
    rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, p["rot"])
    return p["x"] + rx, p["y"] + ry


def d(plan, parts, a, pa, b, pb):
    (ax, ay), (bx, by) = pad_xy(plan, parts, a, pa), pad_xy(plan, parts, b, pb)
    return math.hypot(ax - bx, ay - by)


def test_value_and_pin_name_parsing():
    assert layout.cap_farads("100nF") == approx(100e-9) and layout.cap_farads("0.1uF") == approx(100e-9)
    assert layout.cap_farads("4.7 µF 16V") == approx(4.7e-6)
    assert layout.cap_farads("10u") == approx(10e-6) and layout.cap_farads("10") is None and layout.cap_farads("10 mm") is None
    assert all(layout.is_osc_pin(n) for n in ("OSC_IN", "OSC_OUT", "XTAL1", "XTAL2", "XIN", "XOUT", "PH0-OSC_IN", "PC14-OSC32_OUT"))
    assert not any(layout.is_osc_pin(n) for n in ("PA1", "VDD", "XINT", "", None))


def test_mcu_with_four_vdd_pins_and_four_caps_each_pin_gets_a_cap_within_3_mm():
    parts = [mcu()] + [part(f"C{i}", "C0402", ["+3V3", "GND"], value="100nF") for i in range(1, 5)]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"] and not [f for f in plan["findings"] if f["level"] == "error"], plan
    near = {}
    for c in ("C1", "C2", "C3", "C4"):
        pin, dist = min(((p, d(plan, parts, c, "1", "U1", p)) for p in VDD_PINS), key=lambda t: t[1])
        assert dist <= layout.DECAP_NEAR_MM + layout.DECAP_TOL_MM, (c, pin, dist)
        near[c] = pin
    assert set(near.values()) == VDD_PINS, near                       # one cap per pin
    assert not [f for f in plan["findings"] if f["level"] == "warning"], plan["findings"]


def test_smallest_value_is_placed_nearest():
    parts = [mcu(), part("C1", "C0402", ["+3V3", "GND"], value="10uF"), part("C2", "C0402", ["+3V3", "GND"], value="100nF")]
    plan = layout.plan_placement(parts, FPS, OUT)
    order = [p["ref"] for p in plan["places"] if p["ref"].startswith("C")]
    assert order.index("C2") < order.index("C1")                       # the 100 nF is placed (and so gets its pin) first
    assert min(d(plan, parts, "C2", "1", "U1", p) for p in VDD_PINS) <= 3.05


def test_too_few_caps_reports_the_pins_without_one():
    parts = [mcu()] + [part(f"C{i}", "C0402", ["+3V3", "GND"], value="100nF") for i in (1, 2)]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"]
    errs = [f for f in plan["findings"] if f["level"] == "error"]
    warns = [f for f in plan["findings"] if f["level"] == "warning"]
    assert not errs, errs
    assert len(warns) == 1 and warns[0]["ref"] == "U1" and "2 of 4 supply pin(s) on +3V3" in warns[0]["text"], warns
    assert warns[0]["text"] in plan["warnings"]
    none = layout.plan_placement([mcu()], FPS, OUT)                    # no cap at all: all four pins named
    assert "4 of 4 supply pin(s)" in [f for f in none["findings"] if f["level"] == "warning"][0]["text"]


def _walled(extra):
    """The MCU kept in the middle with a kept 20 x 20 mm block over it: nothing is free within 5 mm of any pin."""
    wall = part("R9", "WALL", ["W1", "W2"])
    return [mcu(osc=extra), wall], {"U1": (30, 20, 0), "R9": (30, 20, 0)}


def test_cap_that_cannot_get_close_is_an_error_finding_with_a_clear_text():
    parts, keep = _walled(None)
    parts += [part("C5", "C0402", ["+3V3", "GND"], value="100nF")]
    plan = layout.plan_placement(parts, FPS, OUT, keep=keep)
    assert not plan["errors"], plan
    errs = [f for f in plan["findings"] if f["level"] == "error"]
    assert len(errs) == 1 and errs[0]["ref"] == "C5", plan["findings"]
    assert "C5 is " in errs[0]["text"] and "mm from U1 pin " in errs[0]["text"] and "VDD; limit 3 mm" in errs[0]["text"]
    assert "placement error: " + errs[0]["text"] in plan["warnings"]          # visible to callers that only read warnings


def test_bulk_cap_is_not_held_to_the_3_mm_rule():
    parts, keep = _walled(None)
    parts += [part("C5", "C0402", ["+3V3", "GND"], value="100uF")]
    plan = layout.plan_placement(parts, FPS, OUT, keep=keep)
    assert not [f for f in plan["findings"] if f["level"] == "error"], plan["findings"]


def test_readback_distance_is_a_warning_and_never_a_verify_problem():
    parts = [mcu(), part("C1", "C0402", ["+3V3", "GND"], value="100nF"), part("C2", "C0402", ["+3V3", "GND"], value="100nF")]
    pads = [{"ref": "U1", "name": "1", "x_mm": 10.0, "y_mm": 10.0}, {"ref": "U1", "name": "6", "x_mm": 20.0, "y_mm": 10.0},
            {"ref": "C1", "name": "1", "x_mm": 11.5, "y_mm": 10.0}, {"ref": "C1", "name": "2", "x_mm": 12.5, "y_mm": 10.0},
            {"ref": "C2", "name": "1", "x_mm": 24.2, "y_mm": 10.0}, {"ref": "C2", "name": "2", "x_mm": 25.2, "y_mm": 10.0}]
    doc = {"pads": pads}
    warns = layout.decap_distance_warnings(doc, parts)
    assert len(warns) == 1 and warns[0].startswith("C2 is 4.2 mm from U1 pin 6 VDD; limit 3 mm"), warns
    assert not [p for p in layout.verify_layout(doc, parts) if "limit 3 mm" in p]       # place_on restores the backup on any problem


def test_reset_pin_tied_to_the_rail_is_not_a_supply_pin():
    nets = ["+3V3"] + ["IO%d" % i for i in range(2, 9)]
    names = ["VDD", "NRST", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7"]
    nets[1] = "+3V3"                                           # NRST tied to the rail
    u = part("U1", "MCU", nets + ["GND"] * 8, names + ["VSS"] * 8)
    plan = layout.plan_placement([u, part("C1", "C0402", ["+3V3", "GND"], value="100nF")], FPS, OUT)
    assert not plan["findings"], plan["findings"]              # one VDD pin, one cap; NRST needs no cap
    assert d(plan, [u, part("C1", "C0402", [], value="")], "C1", "1", "U1", "1") <= 3.05


def test_regulator_is_a_soft_warning_and_a_bulk_cap_is_no_missing_cap():
    reg = part("U1", "MCU", ["+5V"] + ["+3V3"] + ["X%d" % i for i in range(14)] + ["GND"], ["VIN", "VOUT"] + ["P"] * 14 + ["GND"])
    reg["bom_description"] = "LDO voltage regulator"
    parts, keep = [reg, part("R9", "WALL", ["W1", "W2"])], {"U1": (30, 20, 0), "R9": (30, 20, 0)}
    parts += [part("C1", "C0402", ["+3V3", "GND"], value="22uF")]
    plan = layout.plan_placement(parts, FPS, OUT, keep=keep)
    assert not [f for f in plan["findings"] if f["level"] == "error"] and not [f for f in plan["findings"] if "no decoupling cap" in f["text"]]
    parts[2]["bom_value"] = "100nF"; parts[2].pop("value")
    plan = layout.plan_placement(parts, FPS, OUT, keep=keep)
    soft = [f for f in plan["findings"] if f["ref"] == "C1"]
    assert len(soft) == 1 and soft[0]["level"] == "warning" and "as close as possible (see the regulator datasheet's layout section)" in soft[0]["text"]
    assert "limit" not in soft[0]["text"]


def test_bom_value_from_the_real_bridge_path_drives_bulk_and_order(empty):
    from altium import bridge
    pins = [{"num": p["num"], "name": p["name"], "net": p["net"]} for p in mcu()["pins"]]
    store.write_sheet(empty, "01", {"id": "01", "title": "T", "sections": [], "parts": [
        {"ref": "U1", "pins": pins}, {"ref": "R9", "pins": [{"num": "1", "net": "W1"}, {"num": "2", "net": "W2"}]},
        {"ref": "C1", "pins": [{"num": "1", "net": "+3V3"}, {"num": "2", "net": "GND"}]},
        {"ref": "C2", "pins": [{"num": "1", "net": "+3V3"}, {"num": "2", "net": "GND"}]}]})
    for ref, value in (("C1", "22uF"), ("C2", "100nF")):
        store.append(empty, "bom-log.jsonl", {"ts": store.now(), "by": "student", "line": ref,
                                              "changes": {"refs": [ref], "value": value, "description": "MLCC capacitor"}})
    parts = {p["ref"]: p for p in bridge._netlist_parts(empty)}
    assert parts["C1"]["bom_value"] == "22uF" and parts["C2"]["bom_description"] == "MLCC capacitor"
    assert "value" not in parts["C1"]                       # PLACEFP's own value argument is untouched
    fp = {"U1": "MCU", "R9": "WALL", "C1": "C0402", "C2": "C0402"}
    plan = layout.plan_placement([dict(p, footprint=fp[r]) for r, p in parts.items()], FPS, OUT,
                                 keep={"U1": (30, 20, 0), "R9": (30, 20, 0)})
    errs = [f["ref"] for f in plan["findings"] if f["level"] == "error"]
    assert errs == ["C2"], plan["findings"]                 # 100 nF is held to 3 mm, the 22 uF is bulk


def test_resonator_x_ref_with_three_pads_and_xi_xo_pins():
    mc = mcu(osc=("XI_N", "XO_N"))
    for p in mc["pins"]:
        p["name"] = {"PH0-OSC_IN": "XI", "PH1-OSC_OUT": "XO"}.get(p["name"], p["name"])
    fps = dict(FPS, RES3=fp("RES3", [("1", -1.2, 0, 0.8, 1.2), ("2", 0, 0, 0.8, 1.2), ("3", 1.2, 0, 0.8, 1.2)]))
    x = part("X1", "RES3", ["XI_N", "GND", "XO_N"])
    plan = layout.plan_placement([mc, x], fps, OUT)
    assert [c["ref"] for c in plan["crystals"]] == ["X1"], plan


def test_series_resistor_on_osc_out_still_finds_the_crystal_and_its_load_cap():
    parts = [mcu(osc=("OSC_IN", "OSC_OUT_R")), part("Y1", "XTAL", ["OSC_IN", "XT_B"], value="8MHz"),
             part("R1", "C0402", ["XT_B", "OSC_OUT_R"]), part("C5", "C0402", ["OSC_IN", "GND"], value="12pF"),
             part("C6", "C0402", ["XT_B", "GND"], value="12pF")]
    for p in parts[0]["pins"]:
        if p["name"] == "PH1-OSC_OUT":
            p["net"] = "OSC_OUT_R"
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"] and [c["ref"] for c in plan["crystals"]] == ["Y1"], plan
    assert {p["pin"] for p in plan["crystals"][0]["pins"]} == {"14", "15"}
    y_pad = {p["pad"] for p in plan["crystals"][0]["pins"] if p["pin"] == "15"}.pop()
    assert d(plan, parts, "C6", "1", "Y1", y_pad) <= 3.0


def test_forty_nine_part_board_places_within_a_cpu_budget():
    """Perf: 2 ICs (32 pins, many supply pins) and 47 passives; the first version spent 27 s on ring searches per pin per cap."""
    import time
    pads = ([(str(1 + i), -4.5 + 1.0 * i, -5.5, 0.4, 1.0) for i in range(10)] + [(str(11 + i), 5.5, -4.5 + 1.0 * i, 1.0, 0.4) for i in range(10)] +
            [(str(21 + i), 4.5 - 1.0 * i, 5.5, 0.4, 1.0) for i in range(10)] + [(str(31 + i), -5.5, 4.5 - 1.0 * i, 1.0, 0.4) for i in range(2)])
    fps = dict(FPS, BIG=fp("BIG", pads), R0402=FPS["C0402"])

    def ic(ref):
        names = ["VDD" if i % 4 == 0 else ("VSS" if i % 4 == 1 else "PA%d" % i) for i in range(32)]
        nets = [("+3V3" if n == "VDD" else "GND" if n == "VSS" else f"{ref}_{i}") for i, n in enumerate(names)]
        return part(ref, "BIG", nets, names)

    parts = [ic("U1"), ic("U2")]
    parts += [part(f"C{i}", "C0402", ["+3V3", "GND"], value="100nF" if i % 3 else "1uF") for i in range(1, 17)]
    parts += [part(f"R{i}", "R0402", [f"U1_{(i * 2) % 32 + 2}", f"U2_{(i * 3) % 32 + 2}"]) for i in range(1, 32)]
    t0 = time.process_time()
    plan = layout.plan_placement(parts, fps, [0, 0, 100, 80])
    assert time.process_time() - t0 < 300, time.process_time() - t0      # a hang guard only: what is asserted is the result below, not the speed
    assert not plan["errors"] and len(plan["places"]) == 49


def test_crystal_next_to_the_oscillator_pins_with_load_caps_beside_it():
    parts = [mcu(osc=("OSC_IN", "OSC_OUT")), part("Y1", "XTAL", ["OSC_IN", "OSC_OUT"], value="8MHz"),
             part("C5", "C0402", ["OSC_IN", "GND"], value="12pF"), part("C6", "C0402", ["OSC_OUT", "GND"], value="12pF")]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"], plan
    assert len(plan["crystals"]) == 1 and plan["crystals"][0]["ref"] == "Y1"
    pins = {p["pin"]: p for p in plan["crystals"][0]["pins"]}
    assert set(pins) == {"14", "15"} and plan["crystals"][0]["max_mm"] <= layout.XTAL_NEAR_MM, plan["crystals"]
    for q in pins.values():                                            # the reported distance is the real pad-to-pin distance
        assert abs(q["mm"] - d(plan, parts, "Y1", q["pad"], "U1", q["pin"])) < 0.02
    assert not [f for f in plan["findings"] if f["ref"] == "Y1"]
    y_in = next(p for p in ("1", "2") if pins["14"]["pad"] == p)
    y_out = "2" if y_in == "1" else "1"
    assert d(plan, parts, "C5", "1", "Y1", y_in) <= 3.0 and d(plan, parts, "C6", "1", "Y1", y_out) <= 3.0     # load caps next to the crystal


def test_crystal_found_by_description_and_xtal_pin_names():
    mc = mcu(osc=("XI", "XO"))
    for p in mc["pins"]:
        p["name"] = {"PH0-OSC_IN": "XTAL1", "PH1-OSC_OUT": "XTAL2"}.get(p["name"], p["name"])
    xt = part("X1", "XTAL", ["XI", "XO"])
    xt["description"] = "Crystal 16 MHz"
    plan = layout.plan_placement([mc, xt], FPS, OUT)
    assert [c["ref"] for c in plan["crystals"]] == ["X1"], plan


def test_crystal_far_from_the_pins_gets_a_finding_citing_the_guideline():
    parts, keep = _walled(("OSC_IN", "OSC_OUT"))
    parts += [part("Y1", "XTAL", ["OSC_IN", "OSC_OUT"], value="8MHz")]
    plan = layout.plan_placement(parts, FPS, OUT, keep=keep)
    assert not plan["errors"], plan
    f = [f for f in plan["findings"] if f["ref"] == "Y1"]
    assert len(f) == 1 and "ST AN2867" in f[0]["text"] and "mm from U1 pin " in f[0]["text"], plan["findings"]
    assert plan["crystals"][0]["max_mm"] > layout.XTAL_NEAR_MM


def test_no_crystal_no_change():
    parts = [mcu()] + [part(f"C{i}", "C0402", ["+3V3", "GND"], value="100nF") for i in range(1, 5)]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert plan["crystals"] == []
    # a crystal-looking part whose nets reach no oscillator pin is an ordinary part
    odd = layout.plan_placement(parts + [part("Y1", "XTAL", ["A", "B"], value="8MHz")], FPS, OUT)
    assert odd["crystals"] == [] and not [f for f in odd["findings"] if f["ref"] == "Y1"]
    assert {p["ref"] for p in odd["places"]} == {p["ref"] for p in parts} | {"Y1"}


def test_transistor_on_a_supply_rail_does_not_break_the_placement():
    """A Q part counts as an IC for the placement order but is no supply-pin IC: its share of a rail's supply pins must not divide by 0."""
    fps = dict(FPS, SOT23=fp("SOT23", [("1", -0.95, 1.0, 0.6, 0.7), ("2", 0.95, 1.0, 0.6, 0.7), ("3", 0.0, -1.0, 0.6, 0.7)]))
    q = part("Q1", "SOT23", ["IO1", "+3V3", "GND"], names=["B", "VDD", "E"])
    parts = [q] + [part(f"C{i}", "C0402", ["+3V3", "GND"], value="100nF") for i in range(1, 3)]
    plan = layout.plan_placement(parts, fps, OUT)
    assert not plan["errors"] and {p["ref"] for p in plan["places"]} == {"Q1", "C1", "C2"}, plan


def test_other_parts_keep_out_of_the_fan_out_band_of_a_fine_pitch_ic():
    """The pins of a 0.5 mm pitch IC need a channel along the row: the decoupling caps may sit beside it, a resistor wired to a pin
    waits outside FANOUT_FREE_PITCHES pitches of its pads."""
    pads = [(str(1 + i), -2.75 + 0.5 * i, 3.0, 0.28, 1.2) for i in range(12)] + [(str(13 + i), -2.75 + 0.5 * i, -3.0, 0.28, 1.2) for i in range(12)]
    fps = dict(FPS, FINE=fp("FINE", pads), R0402=fp("R0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]))
    nets = [f"IO{i}" for i in range(24)]
    names = [f"PA{i}" for i in range(24)]
    nets[0], names[0] = "+3V3", "VDD"
    nets[12], names[12] = "GND", "VSS"
    parts = [part("U1", "FINE", nets, names), part("C1", "C0402", ["+3V3", "GND"], value="100nF")]
    parts += [part(f"R{i}", "R0402", [f"IO{i}", f"S{i}"]) for i in range(1, 6)]
    plan = layout.plan_placement(parts, fps, OUT)
    assert not plan["errors"], plan
    at = at_of(plan)
    u = at["U1"]
    pb = layout.pads_box(fps["FINE"])
    band = layout.FANOUT_FREE_PITCHES * 0.5
    for r in ("R1", "R2", "R3", "R4", "R5"):
        fb = layout.rot_box(layout.footprint_box(fps["R0402"]), at[r]["rot"])
        box = [fb[0] + at[r]["x"], fb[1] + at[r]["y"], fb[2] + at[r]["x"], fb[3] + at[r]["y"]]
        assert not layout._hit(box, [pb[0] + u["x"] - band, pb[1] + u["y"] - band, pb[2] + u["x"] + band, pb[3] + u["y"] + band], -1e-6), r
