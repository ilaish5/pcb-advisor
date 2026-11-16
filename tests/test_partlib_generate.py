"""Pins the nominal land-pattern dimensions of scripts/partlib_generate.py and its no-guessing symbol rules."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import partlib_generate as gen  # noqa: E402

MM = 1 / 0.0254


def pads(key):
    out = {}
    for ln in (key if isinstance(key, list) else gen.footprint_for(key)["lines"]):
        if ln.startswith("PAD|"):
            f = ln.split("|")
            out[f[1]] = (float(f[2]) / MM, float(f[3]) / MM, float(f[11]) / MM, float(f[12]) / MM)   # x, y, w, h in mm
    return out


def test_sot23_3_pins_1_and_2_are_two_pitches_apart_pin_3_centred_opposite():
    p = pads("SOT-23-3")                                  # JEDEC TO-236: 0.95 mm pitch, pins 1-2 1.90 mm apart
    assert p["1"][1] - p["2"][1] == pytest.approx(1.90, abs=0.01)
    assert p["1"][0] == p["2"][0] < 0 < p["3"][0] and p["3"][1] == 0
    assert p["1"][1] > 0                                  # pin 1 top left


@pytest.mark.parametrize("key,left,right", [
    ("SOT-23-5", [0.95, 0, -0.95], [-0.95, 0.95]),
    ("SOT-23-6", [0.95, 0, -0.95], [-0.95, 0, 0.95]),
])
def test_sot23_5_6_rows_and_ccw_numbering(key, left, right):
    p = pads(key)
    n = len(left) + len(right)
    assert len(p) == n
    assert [p[str(i + 1)][1] for i in range(len(left))] == pytest.approx(left, abs=0.005)
    assert [p[str(len(left) + i + 1)][1] for i in range(len(right))] == pytest.approx(right, abs=0.005)
    assert all(p[str(i + 1)][0] < 0 for i in range(len(left))) and all(p[str(i + 1)][0] > 0 for i in range(len(left), n))


@pytest.mark.parametrize("key,pitch,rowx,n", [("SOIC-8", 1.27, 2.475, 8), ("SOIC-14", 1.27, 2.475, 14), ("SOIC-16", 1.27, 2.475, 16),
                                              ("TSSOP-8", 0.65, 2.8625, 8), ("TSSOP-14", 0.65, 2.875, 14),
                                              ("TSSOP-16", 0.65, 2.8625, 16), ("TSSOP-20", 0.65, 2.8625, 20)])
def test_dual_row_pitch_spacing_and_counter_clockwise_numbering(key, pitch, rowx, n):
    p = pads(key)
    h = n // 2
    assert len(p) == n
    for i in range(h):
        l, r = p[str(i + 1)], p[str(n - i)]
        assert l[0] == pytest.approx(-rowx, abs=0.005) and r[0] == pytest.approx(rowx, abs=0.005)
        assert l[1] == pytest.approx(r[1], abs=0.005)               # pin i+1 faces pin n-i
        if i:
            assert p[str(i)][1] - l[1] == pytest.approx(pitch, abs=0.005)
    assert p["1"][1] > 0 and p[str(n)][1] > 0                         # pin 1 top left, last pin top right


def test_sot223_pitch_pin1_and_the_tab_is_pad_2():
    # as KiCad's SOT-223-3_TabPin2: three pins and a tab on pin 2's net
    lines = [ln.split("|") for ln in gen.footprint_for("SOT-223")["lines"] if ln.startswith("PAD|")]
    got = sorted((f[1], round(float(f[2]) / MM, 3), round(float(f[3]) / MM, 3), round(float(f[12]) / MM, 3)) for f in lines)
    assert got == [("1", -3.15, 2.3, 1.5), ("2", -3.15, 0.0, 1.5), ("2", 3.15, 0.0, 3.8), ("3", -3.15, -2.3, 1.5)]


# KiCad's official footprints (kicad-footprints master, read 2026-11-16): file, |pad x|, pad w, pad h of pad 1
KICAD = [("0402", "R", "R_0402_1005Metric", 0.51, 0.54, 0.64), ("0603", "R", "R_0603_1608Metric", 0.825, 0.80, 0.95),
         ("0805", "R", "R_0805_2012Metric", 0.9125, 1.025, 1.4), ("1206", "R", "R_1206_3216Metric", 1.4625, 1.125, 1.75),
         ("0402", "C", "C_0402_1005Metric", 0.48, 0.56, 0.62), ("0603", "C", "C_0603_1608Metric", 0.775, 0.90, 0.95),
         ("0805", "C", "C_0805_2012Metric", 0.95, 1.00, 1.45), ("1206", "C", "C_1206_3216Metric", 1.475, 1.15, 1.80),
         ("0805", "L", "L_0805_2012Metric", 1.0625, 0.875, 1.2), ("1206", "FB", "L_1206_3216Metric", 1.575, 1.05, 1.9),
         ("0603", "LED", "LED_0603_1608Metric", 0.7875, 0.875, 0.95), ("0805", "LED", "LED_0805_2012Metric", 0.9375, 0.975, 1.4),
         ("1206", "D", "D_1206_3216Metric", 1.4, 1.25, 1.75), ("0805", "F", "Fuse_0805_2012Metric", 0.9375, 0.975, 1.4),
         ("SOD-123", None, "D_SOD-123", 1.65, 0.90, 1.20), ("SOD-323", None, "D_SOD-323", 1.05, 0.60, 0.45)]


@pytest.mark.parametrize("key,prefix,kicad,cx,pw,ph", KICAD)
def test_two_pad_parts_have_kicads_pads(key, prefix, kicad, cx, pw, ph):
    p = pads(gen.footprint_for(key, prefix)["lines"])
    assert set(p) == {"1", "2"}
    assert p["1"][0] == pytest.approx(-cx, abs=0.005) and p["2"][0] == pytest.approx(cx, abs=0.005)
    assert p["1"][1] == p["2"][1] == 0 and p["1"][2:] == pytest.approx((pw, ph), abs=0.005)


@pytest.mark.parametrize("key,cx,pw,ph", [("SOT-23-3", 0.9375, 1.475, 0.60), ("SOT-23-5", 1.1375, 1.325, 0.60),
                                          ("SOIC-8", 2.475, 1.95, 0.60), ("TSSOP-14", 2.875, 1.55, 0.40),
                                          ("TSSOP-20", 2.8625, 1.475, 0.40)])
def test_ic_pads_are_kicads(key, cx, pw, ph):
    # SOT-23, SOT-23-5, SOIC-8_3.9x4.9mm_P1.27mm, TSSOP-14_4.4x5mm_P0.65mm, TSSOP-20_4.4x6.5mm_P0.65mm
    p = pads(key)
    assert p["1"][0] == pytest.approx(-cx, abs=0.005) and p["1"][2:] == pytest.approx((pw, ph), abs=0.005)


def test_pin_header_numbering_row_by_row_from_the_top_left():
    p = pads("PinHeader-2x03_P2.54mm")
    assert len(p) == 6
    assert (p["1"][0], p["2"][0]) == pytest.approx((-1.27, 1.27), abs=0.005) and p["1"][1] == p["2"][1] > p["3"][1]
    assert p["1"][1] - p["3"][1] == pytest.approx(2.54, abs=0.005)


# ------------------------------------------------------------ symbols never invent a pinout
def test_transistor_without_pins_is_not_generated():
    assert gen.symbol_for("Q", "2N7002", [], 3) is None
    assert gen.symbol_for("Q", "BC847 NPN", [], 3) is None


def pin_by_name(sym, name):
    return next(p for p in sym[0] if p["name"] == name)


def test_transistor_shape_follows_the_part_type():
    bjt = gen.symbol_for("Q", "BC847 NPN", [{"num": "1", "name": "B"}, {"num": "2", "name": "E"}, {"num": "3", "name": "C"}], 3)
    mos = gen.symbol_for("Q", "AO3400 N-channel", [{"num": "1", "name": "G"}, {"num": "2", "name": "S"}, {"num": "3", "name": "D"}], 3)
    assert bjt and mos and bjt[1] != mos[1]
    assert not any(i for i in bjt[2] if "polarity" in i) and not any(i for i in mos[2] if "polarity" in i)
    pnp = gen.symbol_for("Q", "BC857 PNP", [{"num": "1", "name": "B"}, {"num": "2", "name": "E"}, {"num": "3", "name": "C"}], 3)
    assert pnp[1] != bjt[1]                                           # arrow direction differs
    assert pin_by_name(bjt, "C")["num"] == "3" and pin_by_name(bjt, "E")["num"] == "2"      # pin functions come from the caller


def test_transistor_with_unknown_polarity_is_neutral_and_flagged():
    sym = gen.symbol_for("Q", "2N7002", [{"num": "1", "name": "G"}, {"num": "2", "name": "S"}, {"num": "3", "name": "D"}], 3)
    assert sym and any("polarity" in i for i in sym[2])
    assert not any(g[0] == "polygon" for g in sym[1])                 # no arrow head when the type is unknown


def test_diode_polarity_is_flagged_unverified_unless_the_sheet_names_a_and_k():
    guessed = gen.symbol_for("D", "BAT54", [], 2)
    assert any("unverified" in i and "cathode" in i for i in guessed[2])
    named = gen.symbol_for("D", "BAT54", [{"num": "1", "name": "K"}, {"num": "2", "name": "A"}], 2)
    assert named[2] == []


def test_diode_symbol_and_sod_footprint_agree_pad_1_is_the_cathode():
    pins, _, _ = gen.symbol_for("D", "BAT54", [], 2)
    cathode = next(p for p in pins if p["orient"] == "eRotate0")      # the bar side of the symbol is on the right
    assert cathode["num"] == "1"
    marks = [ln for ln in gen.footprint_for("SOD-123")["lines"] if ln.startswith("TRACK|") and ln.endswith("|Top Overlay")]
    p1 = pads("SOD-123")["1"]
    assert any(f[1] == f[3] and float(f[1]) / MM < p1[0] - p1[2] / 2 for f in (ln.split("|") for ln in marks))   # a bar beyond pad 1


ALL_KEYS = (list(gen.CHIPS) + list(gen.DIODES) + list(gen.SOT) + ["SOT-223", "SOIC-8", "SOIC-16", "TSSOP-8", "TSSOP-20",
            "PinHeader-1x02_P2.54mm", "PinHeader-2x05_P2.54mm"])


def _silk_to_pad(lines):
    """Smallest copper-to-silk edge distance in mm, sampling each silk line (and the pin-1 dot)."""
    pads, silk = [], []
    for f in (ln.split("|") for ln in lines):
        if f[0] == "PAD":
            x, y, w, h = (float(f[i]) / MM for i in (2, 3, 11, 12))
            pads.append((x - w / 2, x + w / 2, y - h / 2, y + h / 2))
        elif f[0] == "TRACK" and f[-1] == "Top Overlay":
            silk.append((*(float(f[i]) / MM for i in (1, 2, 3, 4)), float(f[5]) / MM / 2))
        elif f[0] == "ARC" and f[-1] == "Top Overlay":
            x, y = float(f[1]) / MM, float(f[2]) / MM
            silk.append((x, y, x, y, float(f[3]) / MM + float(f[6]) / MM / 2))
    best = 9.0
    for x1, y1, x2, y2, r in silk:
        for t in (i / 100 for i in range(101)):
            px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            for a, b, c, d in pads:
                best = min(best, (max(a - px, 0, px - b) ** 2 + max(c - py, 0, py - d) ** 2) ** 0.5 - r)
    return best


@pytest.mark.parametrize("key,prefix", [(k, None) for k in ALL_KEYS] + [(k, "LED") for k in gen.CHIPS])
def test_silk_keeps_jlc_clearance_from_the_pads(key, prefix):
    # JLC flags silkscreen closer than 0.15 mm to a pad (and clips it at fabrication)
    assert _silk_to_pad(gen.footprint_for(key, prefix)["lines"]) >= gen.SILK_TO_PAD


@pytest.mark.parametrize("prefix", ["LED", "D", "TVS", "ZD"])
def test_a_chip_led_or_diode_marks_pad_1_as_the_cathode_and_does_not_share_the_resistor_footprint(prefix):
    fp, plain = gen.footprint_for("0805", prefix), gen.footprint_for("0805", "R")
    assert fp["name"] != plain["name"] == "CHIP-0805" and fp["name"].endswith("-CHIP-0805")
    p1 = {ln.split("|")[1]: float(ln.split("|")[2]) / MM - float(ln.split("|")[11]) / MM / 2
          for ln in fp["lines"] if ln.startswith("PAD|")}["1"]
    bars = [f for f in (ln.split("|") for ln in fp["lines"] if ln.startswith("TRACK|") and ln.endswith("|Top Overlay"))
            if f[1] == f[3]]
    assert bars and all(float(f[1]) / MM < p1 for f in bars)                  # the bar is beyond pad 1, not pad 2
    assert not [ln for ln in plain["lines"] if ln.startswith("TRACK|") and ln.endswith("|Top Overlay")
                and ln.split("|")[1] == ln.split("|")[3]]


def test_silk_and_the_pin_1_dot_lie_inside_the_courtyard():
    for key in ALL_KEYS[:-2] + ["0805"]:
        lines = gen.footprint_for(key, "LED")["lines"]
        court = [(float(f[i]) / MM, float(f[i + 1]) / MM) for f in (ln.split("|") for ln in lines
                 if ln.endswith("|Mechanical Layer 15")) for i in (1, 3)]
        lo = [min(c[a] for c in court) - 1e-6 for a in (0, 1)]
        hi = [max(c[a] for c in court) + 1e-6 for a in (0, 1)]
        for f in (ln.split("|") for ln in lines if ln.endswith("|Top Overlay")):
            arc = f[0] == "ARC"
            r = (float(f[3]) / MM if arc else 0) + float(f[6 if arc else 5]) / MM / 2
            for pt in ([(f[1], f[2])] if arc else [(f[1], f[2]), (f[3], f[4])]):
                for a in (0, 1):
                    v = float(pt[a]) / MM
                    assert lo[a] <= v - r and v + r <= hi[a], key


def test_diode_with_cathode_on_pin_2_is_not_generated():
    # the generated SOD footprint marks pad 1 as the cathode, so 1=A 2=K would put silk and circuit in disagreement
    assert gen.symbol_for("D", "BAT54", [{"num": "1", "name": "A"}, {"num": "2", "name": "K"}], 2) is None
    assert gen.symbol_for("D", "BAT54", [{"num": "1", "name": "K"}, {"num": "2", "name": "A"}], 2) is not None


def test_sod_cathode_bar_stays_inside_the_courtyard():
    for key in ("SOD-123", "SOD-323"):
        lines = gen.footprint_for(key)["lines"]
        xs = [float(f[i]) for f in (ln.split("|") for ln in lines if ln.endswith("|Top Overlay") and ln.startswith("TRACK|"))
              for i in (1, 3)]
        court = [float(f[i]) for f in (ln.split("|") for ln in lines if ln.endswith("|Mechanical Layer 15")) for i in (1, 3)]
        assert min(xs) - gen.MIN_SILK / 2 >= min(court) and max(xs) + gen.MIN_SILK / 2 <= max(court)


def _hint_symbol(hint, names):
    pins = [{"num": str(i + 1), "name": n} for i, n in enumerate(names)]
    return gen.symbol_for("Q", hint, pins, 3)


@pytest.mark.parametrize("hint,arrow", [("AO3400 N-channel", True), ("SI2301 P-ch", True), ("X NMOS", True),
                                        ("X PMOS", True), ("SI2300 TrenchFET", False), ("2N7002", False)])
def test_mosfet_polarity_hints_are_word_bounded(hint, arrow):
    sym = _hint_symbol(hint, ["G", "S", "D"])
    assert any(g[0] == "polygon" for g in sym[1]) == arrow
    assert any("polarity" in i for i in sym[2]) == (not arrow)


def test_mosfet_polarity_direction_from_hint():
    n = next(g for g in _hint_symbol("X NMOS", ["G", "S", "D"])[1] if g[0] == "polygon")
    p = next(g for g in _hint_symbol("X PMOS", ["G", "S", "D"])[1] if g[0] == "polygon")
    assert n[4] < n[6] and p[4] > p[6]                                # tip into the channel for N, out of it for P


def test_mosfet_is_drawn_with_a_split_channel_and_the_arrow_on_the_body_line():
    gfx = _hint_symbol("X NMOS", ["G", "S", "D"])[1]
    lines = [g[3:] for g in gfx if g[0] == "polyline"]
    channel = [l for l in lines if len(l) == 4 and l[0] == l[2] == -30]
    assert len(channel) == 3                                          # enhancement mode: three segments, not one line
    gate = next(l for l in lines if len(l) == 4 and l[0] == l[2] and l[0] < -30)
    arrow = next(g for g in gfx if g[0] == "polygon")
    xs, ys = arrow[4::2], arrow[5::2]
    assert gate[0] < -30 < min(xs) and set(ys) == {0, 10, -10}        # beside the channel on the body line, not in the gap
    assert [0, 0, 0, -55] == next(l for l in lines if l[:2] == [-30, 0])[2:]     # the body is tied to the source
    assert [-30, -55, 0, -55, 0, -100] in lines                       # ... whose lead ends at the source pin
    src = next(p for p in _hint_symbol("X NMOS", ["G", "S", "D"])[0] if p["name"] == "S")
    assert (src["x"], src["y"]) == (0, -100)
    pa = next(g for g in _hint_symbol("X PMOS", ["G", "S", "D"])[1] if g[0] == "polygon")
    assert -30 < min(pa[4::2]) and max(pa[4::2]) < -5 and set(pa[5::2]) == {0, 10, -10}   # on the body line, clear of the source


def test_bjt_hint_is_word_bounded():
    sym = _hint_symbol("BC847 NPNX", ["B", "E", "C"])
    assert any("polarity" in i for i in sym[2])


def test_bjt_arrow_tip_points_away_from_base_for_npn_and_toward_it_for_pnp():
    def tip(hint):
        poly = next(g for g in _hint_symbol(hint, ["B", "E", "C"])[1] if g[0] == "polygon")
        return poly[4], poly[5]                                       # first vertex is the arrow tip
    emitter_end, base = (0, -100), (-40, 0)
    d = lambda a, b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    npn, pnp = tip("BC847 NPN"), tip("BC857 PNP")
    assert d(npn, emitter_end) < d(npn, base)
    assert d(pnp, base) < d(pnp, emitter_end)


def test_mixed_bjt_and_fet_pin_names_give_no_transistor_symbol():
    # the pins stay as the sheet names them (plain box); no transistor shape is drawn from a mixed pin set
    assert gen.transistor_symbol("BC847 NPN", [("1", "B"), ("2", "S"), ("3", "D")]) is None
    assert gen.transistor_symbol("AO3400 N-channel", [("1", "G"), ("2", "E"), ("3", "C")]) is None

def test_diode_pin_names_spelled_out_are_read_as_anode_and_cathode():
    # "Anode"/"Cathode" on pins 1/2 is the same disagreement as A/K: never drawn with pin 1 as the cathode
    assert gen.symbol_for("D", "1N4148W", [{"num": "1", "name": "Anode"}, {"num": "2", "name": "Cathode"}], 2) is None
    ok = gen.symbol_for("LED", "red", [{"num": "1", "name": "C"}, {"num": "2", "name": "A"}], 2)
    assert ok is not None and not any("unverified" in i for i in ok[2])
