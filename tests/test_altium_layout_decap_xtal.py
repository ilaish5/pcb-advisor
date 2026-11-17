"""Spec phase 3 placement rules (scripts/altium/layout.py): decoupling caps within 3 mm of their own supply pin, crystal next to the
MCU oscillator pins with its load caps. Pure Python, offline (plan_placement)."""
import math

from pytest import approx

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


def test_verify_reads_the_distance_back_from_the_saved_board():
    parts = [mcu(), part("C1", "C0402", ["+3V3", "GND"], value="100nF"), part("C2", "C0402", ["+3V3", "GND"], value="100nF")]
    pads = [{"ref": "U1", "name": "1", "x_mm": 10.0, "y_mm": 10.0}, {"ref": "U1", "name": "6", "x_mm": 20.0, "y_mm": 10.0},
            {"ref": "C1", "name": "1", "x_mm": 11.5, "y_mm": 10.0}, {"ref": "C1", "name": "2", "x_mm": 12.5, "y_mm": 10.0},
            {"ref": "C2", "name": "1", "x_mm": 24.2, "y_mm": 10.0}, {"ref": "C2", "name": "2", "x_mm": 25.2, "y_mm": 10.0}]
    probs = layout.decap_distance_problems({"pads": pads}, parts)
    assert len(probs) == 1 and probs[0].startswith("C2 is 4.2 mm from U1 pin 6 VDD; limit 3 mm"), probs


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
