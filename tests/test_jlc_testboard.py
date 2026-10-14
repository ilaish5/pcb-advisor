"""Offline tests for the synthetic JLC test board (scripts/jlc_testboard.py). No network: the live
check (scripts/jlc_live.py) is not collected by pytest."""
import json
import pathlib
import re
import zipfile

import pytest

import jlc_testboard as tb

REPO = pathlib.Path(__file__).resolve().parent.parent
FORMATS = ("jlc-altium26", "outjob", "jlc-altium26-mixed")
# drawn-value tolerance: mm 4:4 is exact to 0.1 um; inch 2:4 rounds coordinates to 2.54 um
TOL = {"jlc-altium26": 0.0003, "outjob": 0.0035, "jlc-altium26-mixed": 0.0003}


@pytest.fixture(scope="module")
def board(tmp_path_factory):
    out = tmp_path_factory.mktemp("tb")
    return out, tb.generate(out, FORMATS)


def test_coupon_set_covers_the_brief(board):
    _, m = board
    by_kind = {}
    for c in m["coupons"]:
        by_kind.setdefault(c["kind"], []).append(c["nominal"])
    assert sorted(n["width_mm"] for n in by_kind["track_space"]) == [0.075, 0.09, 0.10, 0.127, 0.15]
    assert all(n["width_mm"] == n["space_mm"] for n in by_kind["track_space"])
    assert sorted(n["ring_mm"] for n in by_kind["annular_ring"]) == [0.10, 0.13, 0.15, 0.18, 0.25]
    assert sorted((n["drill_mm"], n["dia_mm"]) for n in by_kind["via"]) == [(0.15, 0.25), (0.2, 0.35), (0.3, 0.6)]
    assert sorted(n["edge_mm"] for n in by_kind["copper_to_edge"]) == [0.15, 0.2, 0.3, 0.4]
    assert sorted(n["silk_to_mask_mm"] for n in by_kind["silk_to_pad"]) == [0.05, 0.10, 0.15]
    assert sorted(n["dam_mm"] for n in by_kind["mask_dam"]) == [0.08, 0.10, 0.13]
    assert sorted(n["width_mm"] for n in by_kind["silk_width"]) == [0.10, 0.15]
    assert len(by_kind["hole_to_hole"]) >= 1
    assert sorted(n["drill_mm"] for n in by_kind["drill"]) == [0.15, 0.2]
    assert len({c["id"] for c in m["coupons"]}) == len(m["coupons"])


def test_zips_are_flat_and_complete(board):
    out, m = board
    for fmt in FORMATS:
        info = m["formats"][fmt]
        with zipfile.ZipFile(out / info["zip"]) as z:
            names = z.namelist()
        assert sorted(names) == sorted(info["files"])
        assert all("/" not in n and "\\" not in n for n in names)
        exts = {n.rsplit(".", 1)[1] for n in names}
        assert {"GTL", "GBL", "GTO", "GTS", "GBS", "GTP", "GM1", "TXT"} <= exts
        assert "TB1-Plated.TXT" in names and "TB1-NonPlated.TXT" in names


def test_gerber_syntax(board):
    out, m = board
    for fmt in FORMATS:
        for name in m["formats"][fmt]["files"]:
            if name.endswith(".TXT"):
                continue
            text = (out / fmt / name).read_text(encoding="ascii")
            assert text.rstrip().endswith("M02*")
            assert re.search(r"^%FSLAX\d\dY\d\d\*%$", text, re.M) and re.search(r"^%MO(MM|IN)\*%$", text, re.M)
            for line in text.splitlines():
                assert line.endswith("*") or line.endswith("*%"), line
            # plain RS-274X: no X2 attributes, not even as G04 comments (JLC reads them before file names)
            assert "%TF" not in text and "%TA" not in text and "#@!" not in text
            used = set(re.findall(r"^D(\d+)\*$", text, re.M))
            defined = set(re.findall(r"^%ADD(\d+)[CR],", text, re.M))
            assert used and used <= defined
            g = tb.parse_gerber(text)          # raises on anything unexpected
            assert g["prims"]


def test_excellon_syntax(board):
    out, m = board
    for fmt in FORMATS:
        for name in ("TB1-Plated.TXT", "TB1-NonPlated.TXT"):
            text = (out / fmt / name).read_text(encoding="ascii")
            lines = text.split()
            assert lines[0] == "M48" and lines[-1] == "M30" and "%" in lines
            e = tb.parse_excellon(text)
            assert e["hits"] and e["tools"]
            assert e["plated"] is (name == "TB1-Plated.TXT")


def test_formats_follow_their_recipes(board):
    out, m = board
    a = (out / "jlc-altium26" / "TB1.GTL").read_text(encoding="ascii")
    assert "%FSLAX44Y44*%" in a and "%MOMM*%" in a
    da = (out / "jlc-altium26" / "TB1-Plated.TXT").read_text(encoding="ascii")
    assert ";FILE_FORMAT=2:5" in da and "INCH,LZ" in da
    # leading and trailing zeros kept: every coordinate has 2 + 5 digits
    assert all(len(x) == 7 and len(y) == 7 for x, y in re.findall(r"^X(-?\d+)Y(-?\d+)$", da, re.M))
    b = (out / "outjob" / "TB1.GTL").read_text(encoding="ascii")
    assert "%FSLAX24Y24*%" in b and "%MOIN*%" in b
    db = (out / "outjob" / "TB1-Plated.TXT").read_text(encoding="ascii")
    assert ";FILE_FORMAT=2:4" in db and "INCH,TZ" in db
    coords = re.findall(r"^X(-?\d+)Y(-?\d+)$", db, re.M)
    assert coords and all(not c.startswith("0") for xy in coords for c in xy)


def test_outjob_format_matches_outjob_py():
    """The 'outjob' export format must stay what scripts/outjob.py configures."""
    import outjob
    t = outjob.OUTJOB_TEMPLATE
    ger = re.search(r"Configuration3_Item1=(.*)", t).group(1)
    drl = re.search(r"Configuration4_Item1=(.*)", t).group(1)
    kv = lambda s: dict(p.split("=", 1) for p in s.split("|") if "=" in p)
    g, d = kv(ger), kv(drl)
    f = tb.FORMATS["outjob"]
    assert (g["GerberUnit"], int(g["NumberOfDecimals"])) == ("Imperial", f["gerber"]["dec"]) and f["gerber"]["units"] == "inch"
    assert g["LeadingAndTrailingZeroesMode"] == "SuppressLeadingZeroes" and f["gerber"]["zeros"] == "suppress_leading"
    assert g["OriginPosition"] == "Relative" and f["gerber_origin"] == "relative"
    assert (d["Units"], int(d["NumberOfUnits"]), int(d["NumberOfDecimals"])) == ("Imperial", f["drill"]["int"], f["drill"]["dec"])
    assert d["LeadingAndTrailingZeroesMode"] == "SuppressLeadingZeroes" and f["drill"]["zeros"] == "suppress_leading"
    assert d["OriginPosition"] == "Relative" and f["drill_origin"] == "relative"


def test_jlc_format_matches_reference_recipe():
    text = (REPO / "shared" / "reference" / "jlc" / "files-and-formats.en.md").read_text(encoding="utf-8")
    assert "Units Millimeters; Decimal 0.0001 mm (4:4)" in text
    assert "Units Inches; Format 2:5; keep leading and trailing zeroes" in text
    f = tb.FORMATS["jlc-altium26"]
    assert (f["gerber"]["units"], f["gerber"]["int"], f["gerber"]["dec"]) == ("mm", 4, 4)
    assert (f["drill"]["units"], f["drill"]["int"], f["drill"]["dec"], f["drill"]["zeros"]) == ("inch", 2, 5, "keep")
    assert f["drill_origin"] == "absolute"


def test_manifest_values_match_drawn_geometry(board):
    out, m = board
    for fmt in FORMATS:
        geo = tb.load(out, fmt)
        for c in m["coupons"]:
            drawn = tb.measure(geo, c)
            assert drawn == m["formats"][fmt]["measured"][c["id"]]
            for key, nominal in c["nominal"].items():
                if isinstance(nominal, float) and key in drawn:
                    assert abs(drawn[key] - nominal) <= TOL[fmt], (fmt, c["id"], key, drawn[key], nominal)


def test_both_formats_describe_the_same_geometry(board):
    out, _ = board
    ga, gb = tb.load(out, "jlc-altium26"), tb.load(out, "outjob")
    # both formats are written from the same feature list in the same order, so compare item by item
    for layer in tb.LAYERS:
        pa, pb = ga[layer], gb[layer]
        assert len(pa) == len(pb), layer
        for p, q in zip(pa, pb):
            assert p["kind"] == q["kind"]
            for k in ("x", "y", "x1", "y1", "x2", "y2", "w", "h"):
                if k in p:
                    assert abs(p[k] - q[k]) <= 0.003, (layer, k, p, q)
    ha, hb = ga["holes"], gb["holes"]
    assert len(ha) == len(hb) == 15
    for p, q in zip(ha, hb):
        assert abs(p["x"] - q["x"]) <= 0.003 and abs(p["y"] - q["y"]) <= 0.003
        assert abs(p["d"] - q["d"]) <= 0.002 and p["plated"] == q["plated"]


def test_origins(board):
    out, _ = board
    ox, oy = tb.ABSOLUTE_ORIGIN_MM

    def raw_min_x_mm(fmt, name):
        text = (out / fmt / name).read_text(encoding="ascii")
        if name.endswith(".TXT"):
            e = tb.parse_excellon(text)
            return min(h["x"] for h in e["hits"]) * 25.4
        g = tb.parse_gerber(text)
        k = 25.4 if g["units"] == "inch" else 1.0
        return min(min(p.get("x", 1e9), p.get("x1", 1e9), p.get("x2", 1e9)) for p in g["prims"]) * k

    # absolute origin: the board corner sits at ABSOLUTE_ORIGIN_MM in both Gerber and drill
    assert abs(raw_min_x_mm("jlc-altium26", "TB1.GM1") - (ox - tb.OUTLINE_W / 2) - tb.OUTLINE_W / 2) < 0.001
    assert abs(raw_min_x_mm("jlc-altium26", "TB1-Plated.TXT") - (4.0 + ox)) < 0.001
    # relative origin: the board corner is 0, 0
    assert abs(raw_min_x_mm("outjob", "TB1.GM1")) < 0.001
    assert abs(raw_min_x_mm("outjob", "TB1-Plated.TXT") - 4.0) < 0.003
    # the mixed experiment: copper relative, drill absolute, so the raw files disagree by the offset
    assert abs(raw_min_x_mm("jlc-altium26-mixed", "TB1.GM1")) < 0.001
    assert abs(raw_min_x_mm("jlc-altium26-mixed", "TB1-Plated.TXT") - (4.0 + ox)) < 0.001


def test_board_outline_and_parts(board):
    out, m = board
    geo = tb.load(out, "jlc-altium26")
    xs = [v for p in geo["outline"] for v in (p["x1"], p["x2"])]
    ys = [v for p in geo["outline"] for v in (p["y1"], p["y2"])]
    assert (min(xs), max(xs), min(ys), max(ys)) == (0.0, tb.BOARD_W, 0.0, tb.BOARD_H)
    assert all(abs(p["w"] - tb.OUTLINE_W) < 1e-9 for p in geo["outline"])
    # nothing on the outline layer but the outline; every part sits on two paste pads
    assert len(geo["outline"]) == 4
    pastes = geo["top_paste"]
    for part in m["parts"]:
        near = [p for p in pastes if abs(p["y"] - part["y"]) < 0.01 and abs(abs(p["x"] - part["x"]) - tb.PAD_0603[2]) < 0.01]
        assert len(near) == 2, part["ref"]
    assert {p["lcsc"] for p in m["parts"]} == {"C25804", "C14663", "C2286"}


def test_jlcdfm_level_rule():
    """The level mapping jlc_live.py applies to JLCDFM's served ranges (mil)."""
    import jlc_live
    rng = [4, 6, 8]
    assert jlc_live.dfm_level(0.10, rng) == "Danger"          # 3.94 mil
    assert jlc_live.dfm_level(0.1016, rng) == "Warning"       # 4.0 mil
    assert jlc_live.dfm_level(0.15, rng) == "Warning"         # 5.9 mil
    assert jlc_live.dfm_level(0.16, rng) == "Good"
    assert jlc_live.dfm_level(0.25, rng) == "not reported"
    assert jlc_live.dfm_level(0.3, [8, 6, 3]) == "Danger"      # reversed range: larger is worse


def test_live_script_is_not_collected():
    cfg = (REPO / "pytest.ini").read_text(encoding="utf-8")
    assert "testpaths = tests" in cfg
    assert not (REPO / "tests" / "test_jlc_live.py").exists()
    src = (REPO / "scripts" / "jlc_live.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in src
