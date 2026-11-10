"""Pins the nominal land-pattern dimensions of scripts/partlib_generate.py and its no-guessing symbol rules."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import partlib_generate as gen  # noqa: E402

MM = 1 / 0.0254


def pads(key):
    out = {}
    for ln in gen.footprint_for(key)["lines"]:
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


@pytest.mark.parametrize("key,pitch,rowx,n", [("SOIC-8", 1.27, 2.70, 8), ("SOIC-14", 1.27, 2.70, 14), ("SOIC-16", 1.27, 2.70, 16),
                                              ("TSSOP-8", 0.65, 2.85, 8), ("TSSOP-14", 0.65, 2.85, 14),
                                              ("TSSOP-16", 0.65, 2.85, 16), ("TSSOP-20", 0.65, 2.85, 20)])
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


def test_sot223_pitch_pin1_and_tab():
    p = pads("SOT-223")
    assert len(p) == 4 and p["1"][1] == pytest.approx(2.3, abs=0.005) and p["2"][1] == 0 and p["3"][1] == pytest.approx(-2.3, abs=0.005)
    assert p["1"][0] == p["2"][0] == p["3"][0] == pytest.approx(-3.15, abs=0.005) and p["4"][0] == pytest.approx(3.15, abs=0.005)
    assert p["4"][3] > 3 * p["1"][3] / 2                                # the tab is the wide pad


@pytest.mark.parametrize("key,cx,pw,ph", [("0402", 0.48, 0.56, 0.62), ("0603", 0.825, 0.80, 0.95), ("0805", 0.95, 1.00, 1.45),
                                          ("1206", 1.50, 1.15, 1.80), ("SOD-123", 1.635, 0.91, 1.22),
                                          ("SOD-323", 1.05, 0.60, 0.45)])
def test_two_pad_parts(key, cx, pw, ph):
    p = pads(key)
    assert set(p) == {"1", "2"}
    assert p["1"][0] == pytest.approx(-cx, abs=0.005) and p["2"][0] == pytest.approx(cx, abs=0.005)
    assert p["1"][1] == p["2"][1] == 0 and p["1"][2:] == pytest.approx((pw, ph), abs=0.005)


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
    assert n[4] < n[6] and p[4] > p[6]                                # tip toward the channel for P, away for N


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
