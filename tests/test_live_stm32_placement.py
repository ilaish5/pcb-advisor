"""Regression for a live Altium run: a 26-part STM32F103 (LQFP-48) board, 45 x 40 mm, was placed with the crystal 11.7 mm from the OSC pins,
supply pins without a cap within 3 mm, and the silk of the edge connectors closer than the board-outline rule (6 DRC items).
The board is tests/live_stm32_fixture.py (the library footprints and nets of that run, frozen; nothing under projects/ is read).
The checks are measured from the placed geometry, not from the tool's own findings, and the tool's findings must stay truthful."""
import math

import pytest

import live_stm32_fixture as fx
from altium import layout

MIL = 0.0254
SILK_LINE_MM = 0.25            # the silk lines of the library footprints are 10 mil wide
EDGE_RULE_MM = 0.3048          # Altium board-outline clearance, 12 mil


@pytest.fixture(scope="module")
def board():
    plan = layout.plan_placement(fx.PARTS, fx.FPS, fx.OUTLINE, clearance_mm=0.0, edge_copper_mm=fx.EDGE_COPPER_MM)
    return dict(plan=plan, doc=_doc(plan), at={p["ref"]: p for p in plan["places"]})


def _doc(plan):
    """The saved-board dict (what read_pcbdoc gives) of a placement plan: pads at absolute positions."""
    byref = {p["ref"]: p for p in fx.PARTS}
    doc = {"components": [], "pads": [], "tracks": [], "vias": []}
    for pl in plan["places"]:
        part, fp = byref[pl["ref"]], fx.FPS[pl["footprint"]]
        nets = {str(p["num"]): p["net"] for p in part["pins"]}
        names = {str(p["num"]): p.get("name", "") for p in part["pins"]}
        doc["components"].append({"ref": pl["ref"], "pattern": pl["footprint"], "x_mm": pl["x"], "y_mm": pl["y"], "rotation": pl["rot"],
                                  "body_bbox_mm": None, "outline_bbox_mm": None})
        for q in fp["pads"]:
            rx, ry = layout.rot_point(q["x"] * MIL, q["y"] * MIL, pl["rot"])
            w, h = q["xsize"] * MIL, q["ysize"] * MIL
            if int(pl["rot"]) % 180 == 90:
                w, h = h, w
            net = nets.get(q["name"], "")
            doc["pads"].append({"ref": pl["ref"], "name": q["name"], "pin_name": names.get(q["name"], ""),
                                "x_mm": round(pl["x"] + rx, 4), "y_mm": round(pl["y"] + ry, 4), "sx_mm": w, "sy_mm": h, "rot": 0,
                                "net": "" if net.upper() in ("NC", "N/C") else net, "layer": 1})
    return doc


def _pad(doc, ref, name):
    return next(p for p in doc["pads"] if p["ref"] == ref and p["name"] == name)


def _dist(a, b):
    return math.hypot(a["x_mm"] - b["x_mm"], a["y_mm"] - b["y_mm"])


def test_fixture_is_the_live_board():
    """26 parts, 45 x 40 mm, the LQFP-48 with 0.5 mm pitch and the real pin names (OSC on pins 5-6, VDDA on 9)."""
    assert len(fx.PARTS) == 26 and fx.OUTLINE == [0.0, 0.0, 45.0, 40.0]
    u1 = next(p for p in fx.PARTS if p["ref"] == "U1")
    names = {p["num"]: p["name"] for p in u1["pins"]}
    assert names["5"] == "PD0-OSC_IN" and names["6"] == "PD1-OSC_OUT" and names["9"] == "VDDA" and names["7"] == "NRST"
    pads = {p["name"]: p for p in fx.FPS[u1["footprint"]]["pads"]}
    assert len(pads) == 48 and abs(abs(pads["47"]["y"] - pads["48"]["y"]) * MIL - 0.5) < 0.01


def test_everything_is_placed_without_errors(board):
    plan = board["plan"]
    assert len(plan["places"]) == 26 and not plan["errors"]
    assert not [f for f in plan["findings"] if f["level"] == "error"], plan["findings"]
    assert layout.verify_layout(board["doc"], fx.PARTS, fx.OUTLINE, places=plan["places"], footprints=fx.FPS) == []


def test_crystal_is_beside_the_osc_pins(board):
    """Was 11.7 mm (the MCU filled the middle and the crystal went to the far side). Measured here from the pads, not from the finding."""
    doc = board["doc"]
    for pad, pin in (("1", "5"), ("3", "6")):
        d = _dist(_pad(doc, "Y1", pad), _pad(doc, "U1", pin))
        assert d <= layout.XTAL_NEAR_MM, f"Y1 pad {pad} is {d:.1f} mm from U1 pin {pin}"
    assert board["plan"]["crystals"][0]["max_mm"] <= layout.XTAL_NEAR_MM
    assert not [f for f in board["plan"]["findings"] if "Y1" in f["text"]], board["plan"]["findings"]


def test_supply_pins_have_their_cap_and_a_bare_pin_is_reported_truthfully(board):
    """Was 2 of 5 supply pins within 3 mm. The VDDA pin (9) sits between the crystal and the 0.5 mm fan-out band and may stay bare,
    but then the tool must say so, naming that pin, and no other pin may be bare."""
    doc, plan = board["doc"], board["plan"]
    supply = [p["name"] for p in fx.FPS["LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL"]["pads"] if _pad(doc, "U1", p["name"])["net"] == "+3V3"]
    assert sorted(supply, key=int) == ["1", "9", "24", "36", "48"]
    caps = [r["ref"] for r in doc["components"] if r["ref"].startswith("C") and r["ref"] not in ("C1", "C2", "C3", "C4")]
    bare = []
    for pin in supply:
        near = [c for c in caps for q in doc["pads"] if q["ref"] == c and q["net"] == "+3V3" and _dist(q, _pad(doc, "U1", pin)) <= layout.DECAP_NEAR_MM]
        if not near:
            bare.append(pin)
    assert len(supply) - len(bare) >= 4, f"bare supply pins {bare}"
    said = [f["text"] for f in plan["findings"] if f["text"].startswith("U1:") and "supply pin" in f["text"]]
    if bare:
        assert len(said) == 1 and all(f"pin {p} " in said[0] for p in bare), (bare, said)
    else:
        assert not said


def test_oscillator_and_supply_sides_keep_room_around_the_mcu(board):
    """The MCU may not be pushed so close to an edge that nothing fits beside its OSC pins (5, 6) or its supply pins."""
    doc = board["doc"]
    x0, y0, x1, y1 = fx.OUTLINE
    for pin in ("5", "6", "9", "24", "36", "48", "1"):
        p = _pad(doc, "U1", pin)
        assert min(p["x_mm"] - x0, x1 - p["x_mm"], p["y_mm"] - y0, y1 - p["y_mm"]) > 2.0, f"U1 pin {pin} at {p['x_mm']:.1f}, {p['y_mm']:.1f}"


def test_copper_keeps_the_edge_clearance(board):
    x0, y0, x1, y1 = fx.OUTLINE
    for p in board["doc"]["pads"]:
        gap = min(p["x_mm"] - p["sx_mm"] / 2 - x0, x1 - p["x_mm"] - p["sx_mm"] / 2, p["y_mm"] - p["sy_mm"] / 2 - y0, y1 - p["y_mm"] - p["sy_mm"] / 2)
        assert gap >= fx.EDGE_COPPER_MM - 1e-6, f"{p['ref']}-{p['name']} is {gap:.2f} mm from the edge"


@pytest.mark.parametrize("ref", ["J1", "J2"])
def test_connector_silk_clears_the_outline_rule(board, ref):
    """The 6 DRC items of the live run: the 10 mil silk lines of the edge connectors were 0.26 mm from the outline (rule 0.3048 mm to the line's edge)."""
    pl = board["at"][ref]
    sx0, sy0, sx1, sy1 = (v * MIL for v in fx.FPS[pl["footprint"]]["extent"]["silk"])
    pts = [layout.rot_point(x, y, pl["rot"]) for x in (sx0, sx1) for y in (sy0, sy1)]
    xs, ys = [pl["x"] + p[0] for p in pts], [pl["y"] + p[1] for p in pts]
    x0, y0, x1, y1 = fx.OUTLINE
    gap = min(min(xs) - x0, x1 - max(xs), min(ys) - y0, y1 - max(ys))
    assert gap - SILK_LINE_MM / 2 >= EDGE_RULE_MM, f"{ref} silk is {gap:.2f} mm from the outline"
