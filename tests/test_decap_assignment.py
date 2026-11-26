"""Which decoupling cap goes to which part (scripts/altium/layout.py): a cap whose BOM role names a part sits beside that part; without a
hint a small cap goes to an IC supply pin before a regulator pin and a bulk cap to the regulator; the read-back warns when that fails.
The board is a regulator + a sensor on one 3V3 rail (the E2E run that swapped the two caps). Pure Python, offline."""
import math

import pytest

from altium import layout

MIL = 0.0254


def fp(name, pads):
    return {"name": name, "pads": [{"name": n, "x": x / MIL, "y": y / MIL, "xsize": w / MIL, "ysize": h / MIL, "layer": 1}
                                   for n, x, y, w, h in pads]}


FPS = {"SOT223": fp("SOT223", [("1", -2.3, -3.1, 1.2, 1.8), ("2", 0, -3.1, 1.2, 1.8), ("3", 2.3, -3.1, 1.2, 1.8), ("4", 0, 3.1, 3.6, 1.8)]),
       "DFN8": fp("DFN8", [(str(1 + i), -1.2, 0.75 - 0.5 * i, 0.5, 0.3) for i in range(4)] +
                  [(str(5 + i), 1.2, -0.75 + 0.5 * i, 0.5, 0.3) for i in range(4)]),
       "C0402": fp("C0402", [("1", -0.5, 0, 0.6, 0.6), ("2", 0.5, 0, 0.6, 0.6)]),
       "WALL": fp("WALL", [("1", -6, -6, 1, 1), ("2", 6, 6, 1, 1)])}
OUT = [0, 0, 60, 40]


def part(ref, footprint, nets, names=None, **bom):
    return {"ref": ref, "footprint": footprint, **bom,
            "pins": [{"num": str(i + 1), "net": n, **({"name": names[i]} if names else {})} for i, n in enumerate(nets)]}


def regulator(ref="U1"):
    return part(ref, "SOT223", ["GND", "+3V3", "VBUS", "+3V3"], ["GND", "VOUT", "VIN", "TAB"],
                bom_value="AMS1117-3.3", bom_mpn="AMS1117-3.3", bom_role="3.3 V LDO regulator")


def sensor(ref="U2"):
    return part(ref, "DFN8", ["SDA", "ADDR", "ALERT", "SCL", "+3V3", "NRST", "NC", "GND"],
                ["SDA", "ADDR", "ALERT", "SCL", "VDD", "nRESET", "R", "VSS"],
                bom_value="SHT31-DIS", bom_mpn="SHT31-DIS-B2.5kS", bom_role="humidity sensor")


def cap(ref, net, value, role="", **bom):
    return part(ref, "C0402", [net, "GND"], bom_value=value, bom_role=role, **bom)


def board(c2_role="LDO output cap", c3_role="SHT31 decoupling", c2="10uF", c3="100nF"):
    return [regulator(), sensor(), cap("C1", "VBUS", "10uF", "LDO input cap"), cap("C2", "+3V3", c2, c2_role), cap("C3", "+3V3", c3, c3_role)]


def pad_xy(plan, parts, ref, pad):
    p = next((q for q in plan["places"] if q["ref"] == ref), None) or dict(zip(("x", "y", "rot"), plan["keep"][ref]))   # a kept part is not in "places"
    q = next(q for q in FPS[next(x for x in parts if x["ref"] == ref)["footprint"]]["pads"] if q["name"] == pad)
    rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, p["rot"])
    return p["x"] + rx, p["y"] + ry


def dist(plan, parts, c, ic, *pins):
    """The cap's rail pad to the nearest of these pins."""
    a = pad_xy(plan, parts, c, "1")
    return min(math.dist(a, pad_xy(plan, parts, ic, p)) for p in pins)


NEAR = layout.DECAP_NEAR_MM + layout.DECAP_TOL_MM
OUT_PINS, VDD, VIN = ("2", "4"), "5", "3"


def assert_each_cap_is_where_it_belongs(plan, parts):
    assert not plan["errors"], plan
    assert dist(plan, parts, "C3", "U2", VDD) <= NEAR
    assert dist(plan, parts, "C2", "U1", *OUT_PINS) <= NEAR
    assert dist(plan, parts, "C1", "U1", VIN) <= NEAR
    assert not plan["findings"], plan["findings"]


def saved(plan, parts):
    """The read-back of the plan, as read_pcbdoc gives its pads."""
    return {"pads": [{"ref": p["ref"], "name": q["num"], "x_mm": pad_xy(plan, parts, p["ref"], q["num"])[0],
                      "y_mm": pad_xy(plan, parts, p["ref"], q["num"])[1]} for p in parts for q in p["pins"]]}


@pytest.mark.parametrize("c2_role, c3_role", [
    ("LDO output cap", "SHT31 decoupling"),           # the part's name, and the regulator by what it is
    ("AMS1117 output capacitor", "U2 bypass"),        # MPN without its option, designator
    ("Output capacitor for the regulator", "decoupling for SHT31-DIS"),
    ("", ""),                                         # no hint at all
    ("decoupling", "decoupling"),
])
def test_each_cap_goes_to_its_own_part(c2_role, c3_role):
    parts = board(c2_role, c3_role)
    plan = layout.plan_placement(parts, FPS, OUT)
    assert_each_cap_is_where_it_belongs(plan, parts)
    assert layout.decap_distance_warnings(saved(plan, parts), parts) == []


def test_role_hint_beats_the_value_order():
    """The role decides even against the no-hint rule: a 100 nF named as the LDO's output cap stays at the LDO."""
    parts = board("SHT31 bulk", "LDO output cap")
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"], plan
    assert dist(plan, parts, "C2", "U2", VDD) <= NEAR and dist(plan, parts, "C3", "U1", *OUT_PINS) <= NEAR


def test_bulk_cap_without_a_hint_prefers_the_regulator():
    parts = board("", "", c2="22uF")
    plan = layout.plan_placement(parts, FPS, OUT)
    assert dist(plan, parts, "C2", "U1", *OUT_PINS) <= NEAR and dist(plan, parts, "C3", "U2", VDD) <= NEAR


def test_a_single_small_cap_goes_to_the_sensor_and_the_regulator_is_warned():
    parts = [p for p in board("", "") if p["ref"] != "C2"]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert dist(plan, parts, "C3", "U2", VDD) <= NEAR
    warns = [f for f in plan["findings"] if f["ref"] == "U1"]
    assert len(warns) == 1 and warns[0]["level"] == "warning", plan["findings"]
    assert "C3 is " in warns[0]["text"] and " mm" in warns[0]["text"] and "VOUT" in warns[0]["text"]
    assert warns[0]["text"] in plan["warnings"] and warns[0]["text"] in layout.decap_distance_warnings(saved(plan, parts), parts)


def test_a_regulator_pin_with_no_cap_at_all_is_warned():
    parts = [p for p in board() if p["ref"] != "C1"]
    plan = layout.plan_placement(parts, FPS, OUT)
    texts = [f["text"] for f in plan["findings"]]
    assert len(texts) == 1 and "U1" in texts[0] and "VIN" in texts[0] and "no capacitor" in texts[0], texts


def test_saved_board_with_the_two_caps_swapped_is_warned():
    """The E2E board: the 100 nF named for the sensor sits at the regulator and the 10 uF at the sensor. Some cap is near every supply
    pin, so only the roles show it."""
    parts = board()
    plan = layout.plan_placement(parts, FPS, OUT)
    doc = saved(plan, parts)
    at = {(p["ref"], p["name"]): p for p in doc["pads"]}
    for n in ("1", "2"):
        a, b = at["C2", n], at["C3", n]
        a["x_mm"], b["x_mm"], a["y_mm"], b["y_mm"] = b["x_mm"], a["x_mm"], b["y_mm"], a["y_mm"]
    warns = layout.decap_distance_warnings(doc, parts)
    c3 = [w for w in warns if w.startswith("C3 is ")]
    c2 = [w for w in warns if w.startswith("C2 is ")]
    assert len(c3) == 1 and "U2" in c3[0] and "SHT31" in c3[0] and " mm" in c3[0], warns
    assert len(c2) == 1 and "U1" in c2[0] and "AMS1117" in c2[0], warns


def test_warning_when_the_named_part_has_no_room_for_its_cap():
    """The sensor is walled in: its cap cannot get within reach, and the finding names the cap, the part and the distance."""
    parts = board() + [part("R9", "WALL", ["W1", "W2"])]
    keep = {"U2": (45, 20, 0), "R9": (45, 20, 0)}
    plan = dict(layout.plan_placement(parts, FPS, OUT, keep=keep), keep=keep)
    assert not plan["errors"], plan
    errs = [f for f in plan["findings"] if f["ref"] == "C3"]
    assert len(errs) == 1 and errs[0]["level"] == "error", plan["findings"]
    assert errs[0]["text"].startswith("C3 is ") and " mm from U2 " in errs[0]["text"] and "SHT31" in errs[0]["text"], errs
    assert errs[0]["text"] in layout.decap_distance_warnings(saved(plan, parts), parts)


def test_one_role_naming_two_parts_spreads_the_caps():
    role = "Decoupling, one per IC (U2, U3)"
    parts = [regulator(), sensor("U2"), sensor("U3"), cap("C1", "VBUS", "10uF"), cap("C2", "+3V3", "10uF", "LDO output cap"),
             cap("C3", "+3V3", "100nF", role), cap("C4", "+3V3", "100nF", role)]
    plan = layout.plan_placement(parts, FPS, OUT)
    assert not plan["errors"] and not plan["findings"], plan
    near = {c: next((u for u in ("U2", "U3") if dist(plan, parts, c, u, VDD) <= NEAR), None) for c in ("C3", "C4")}
    assert set(near.values()) == {"U2", "U3"}, near


def hints_for(role, parts=None, description=""):
    parts = parts or [regulator(), sensor(), sensor("U21")]
    return {ic for ic, _ in layout.decap_hints(parts + [cap("C9", "+3V3", "100nF", role, bom_description=description)]).get("C9", [])}


def test_role_matching():
    assert hints_for("SHT31 decoupling") == {"U2", "U21"}
    assert hints_for("U2 bypass") == {"U2"}                                       # not U21
    assert hints_for("SHT31 decoupling (U2)") == {"U2", "U21"} and hints_for("decoupling (U2)") == {"U2"}   # an IC in brackets is no note
    assert hints_for("AMS1117 output cap") == {"U1"}
    assert hints_for("LDO output cap") == {"U1"}
    assert hints_for("100nF decoupling") == set()
    assert hints_for("humidity sensor decoupling") == set()                       # a part's own role text is not its name
    assert hints_for("decoupling on the rail from the LDO") == set()              # where the rail comes from, not whose cap it is
    assert hints_for("decoupling for U21, powered by the LDO") == {"U21"}         # a named part before a kind of part
    assert hints_for("", description="Decoupling for U2") == {"U2"}
    assert hints_for("U7 bypass") == set()
    # a part with no pin on the cap's rail is not its owner
    assert {ic for ic, _ in layout.decap_hints([regulator(), sensor(), cap("C9", "VBUS", "100nF", "SHT31 decoupling")]).get("C9", [])} == set()


_QFN16 = [(str(1 + i), -2.0 + 1.0 * i, -3.0, 0.3, 0.8) for i in range(4)] + [(str(5 + i), 3.0, -2.0 + 1.0 * i, 0.8, 0.3) for i in range(4)] + \
         [(str(9 + i), 2.0 - 1.0 * i, 3.0, 0.3, 0.8) for i in range(4)] + [(str(13 + i), -3.0, 2.0 - 1.0 * i, 0.8, 0.3) for i in range(4)]


def test_a_part_that_only_says_converter_is_not_the_regulator():
    """A USB-UART bridge (its text says "converter") has VCC on the 3V3 rail: "LDO output cap" is still the AMS1117's, and the plain
    100 nF goes to the bridge's VCC, not to the regulator."""
    fps = dict(FPS, QFN16=fp("QFN16", _QFN16))
    names = ["VCC"] + [f"P{i}" for i in range(2, 9)] + ["GND"] + [f"P{i}" for i in range(10, 17)]
    nets = ["+3V3"] + [f"S{i}" for i in range(2, 9)] + ["GND"] + [f"S{i}" for i in range(10, 17)]
    bridge = part("U3", "QFN16", nets, names, bom_value="CH340C", bom_mpn="CH340C", bom_description="USB to UART converter")
    parts = [regulator(), sensor(), bridge, cap("C1", "VBUS", "10uF", "LDO input cap"), cap("C2", "+3V3", "10uF", "LDO output cap"),
             cap("C3", "+3V3", "100nF", "SHT31 decoupling"), cap("C4", "+3V3", "100nF")]
    assert {ic for ic, _ in layout.decap_hints(parts)["C2"]} == {"U1"}
    assert layout.decap_owners(parts, layout.decap_hints(parts))["C4"] == {"U2", "U3"}                  # never the regulator
    plan = layout.plan_placement(parts, fps, OUT)
    assert not plan["errors"] and not plan["findings"], plan
    fps_of = dict(FPS, QFN16=fps["QFN16"])

    def d(c, ic, pin):
        p = next(q for q in plan["places"] if q["ref"] == ic)
        q = next(q for q in fps_of[next(x for x in parts if x["ref"] == ic)["footprint"]]["pads"] if q["name"] == pin)
        rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, p["rot"])
        a = next(q for q in plan["places"] if q["ref"] == c)
        b = next(q for q in fps_of["C0402"]["pads"] if q["name"] == "1")
        cx, cy = layout.rot_point(b["x"] * MIL, b["y"] * MIL, a["rot"])
        return math.hypot(a["x"] + cx - p["x"] - rx, a["y"] + cy - p["y"] - ry)

    assert min(d("C2", "U1", p) for p in OUT_PINS) <= NEAR and d("C3", "U2", VDD) <= NEAR


def test_input_and_output_words_pick_the_regulator_pins():
    parts = board("LDO output cap", "LDO input cap")        # C3 is on 3V3 (the output), the word "input" finds no input pin there
    assert {n for _, n in layout.decap_hints(parts)["C3"]} == {"2", "4"}      # no IN pin on the rail: every regulator pin on it
    parts = board() + [cap("C5", "VBUS", "100nF", "regulator input")]
    assert {n for _, n in layout.decap_hints(parts)["C5"]} == {"3"}


def mcu(ref="U3"):
    names = [("VDD" if i % 4 == 1 else "VSS" if i % 4 == 3 else f"PA{i}") for i in range(1, 17)]
    nets = [("+3V3" if n == "VDD" else "GND" if n == "VSS" else f"S{i}") for i, n in enumerate(names)]
    return part(ref, "QFN16", nets, names, bom_value="STM32F411", bom_mpn="STM32F411RET6", bom_role="main controller")


def test_a_line_shared_by_more_caps_than_the_named_pins_does_not_lock_them_all():
    """One BOM line "SHT31 decoupling" for five caps: the sensor has one supply pin, so one cap is its; the unnamed MCU keeps the rest."""
    parts = [sensor(), mcu()] + [cap(f"C{i}", "+3V3", "100nF", "SHT31 decoupling") for i in range(1, 6)]
    hints = layout.decap_hints(parts)
    assert set(hints) == {"C1"} and {ic for ic, _ in hints["C1"]} == {"U2"}
    fps = dict(FPS, QFN16=fp("QFN16", _QFN16))
    plan = layout.plan_placement(parts, fps, OUT)
    assert not plan["errors"] and not plan["findings"], plan

    def xy(ref, num):
        p = next(q for q in plan["places"] if q["ref"] == ref)
        q = next(q for q in fps[next(x for x in parts if x["ref"] == ref)["footprint"]]["pads"] if q["name"] == num)
        rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, p["rot"])
        return p["x"] + rx, p["y"] + ry

    for ic, pin in [("U2", VDD)] + [("U3", str(n)) for n in (1, 5, 9, 13)]:
        assert min(math.dist(xy(f"C{i}", "1"), xy(ic, pin)) for i in range(1, 6)) <= NEAR, (ic, pin)


def test_designator_notes_in_a_shared_line_speak_for_their_caps():
    parts = [regulator(), sensor(), sensor("U21")]
    line = "Decoupling: U2, U21 (C9 on VDD), LDO in/out (C7, C8)"
    caps = [cap("C6", "+3V3", "100nF", line), cap("C9", "+3V3", "100nF", line), cap("C7", "VBUS", "1uF", line),
            cap("C8", "+3V3", "1uF", line)]
    hints = layout.decap_hints(parts + caps)
    assert {ic for ic, _ in hints["C9"]} == {"U21"} and {ic for ic, _ in hints["C6"]} == {"U2"}
    assert {n for _, n in hints["C7"]} == {"3"} and {n for _, n in hints["C8"]} == {"2", "4"}       # "in/out": both sides


def test_a_kind_word_binds_only_to_a_regulator_of_that_kind():
    buck = part("U4", "DFN8", ["VBUS2", "SW", "BST", "EN", "FB", "VCC", "NC", "GND"], ["IN", "SW", "BST", "EN", "FB", "VCC", "NC", "GND"],
                bom_value="MP2315", bom_mpn="MP2315GJ-Z", bom_role="buck 12 V to 3.8 V")
    parts = [regulator(), buck]
    assert hints_for("buck output cap", parts) == set()                       # the buck has no pin on +3V3, the LDO is not a buck
    assert hints_for("LDO output cap", parts) == {"U1"}
    assert hints_for("regulator output cap", parts) == {"U1"}
    fed = dict(regulator(), bom_role="LDO fed by the buck")                    # says both kinds: any kind word fits
    assert hints_for("LDO output cap", [fed, buck]) == {"U1"}


def test_a_supervisor_in_a_regulator_package_gets_plain_caps():
    sup = part("U5", "SOT-23-5", ["RST", "GND", "MR", "WDI", "+3V3"], ["RESET", "GND", "MR", "WDI", "VDD"],
               bom_value="TPS3823-33", bom_mpn="TPS3823-33DBVR", bom_role="supervisor")
    parts = [regulator(), sensor(), sup, cap("C4", "+3V3", "100nF"), cap("C5", "+3V3", "100nF")]
    assert layout.decap_owners(parts, layout.decap_hints(parts))["C4"] == {"U2", "U5"}


def test_a_regulator_gets_its_microfarad_cap_before_the_small_ones_go_out():
    parts = [regulator(), sensor(), cap("C4", "+3V3", "100nF"), cap("C5", "+3V3", "1uF")]
    owners = layout.decap_owners(parts, {})
    assert owners["C5"] == {"U1"} and owners["C4"] == {"U2"}
