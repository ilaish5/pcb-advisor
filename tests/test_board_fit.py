"""2026-11-20: an early estimate of the parts' area against the board (BOM approval, Place), and the figures in 'no free place'."""
from altium import layout
from test_altium_layout import FPS, OUT, PARTS


def _parts(n):
    return [{"ref": f"R{i}", "footprint": "", "package": "0603"} for i in range(n)] + \
           [{"ref": "U1", "footprint": "", "package": "QFN-56"}, {"ref": "J1", "footprint": "", "package": "USB-C"}]


def test_package_typical_sizes():
    assert layout.package_area_mm2("0402") < layout.package_area_mm2("0805") < layout.package_area_mm2("SOT-223")
    assert layout.package_area_mm2("QFN-56") > layout.package_area_mm2("QFN-16")
    assert layout.package_area_mm2("", "U3") == 40.0 and layout.package_area_mm2("", "C7") == 5.0


def test_a_loose_board_is_not_flagged():
    fit = layout.board_fit(_parts(10), (100, 80))
    assert fit and not fit["tight"] and fit["suggest"] is None and layout.fit_text(fit, (100, 80)) == ""


def test_a_tight_board_is_flagged_with_the_figures_and_a_bigger_size():
    parts = [{"ref": f"U{i}", "footprint": "", "package": "LQFP-48"} for i in range(8)] + _parts(25)
    fit = layout.board_fit(parts, (40, 30))
    assert fit["tight"] and fit["estimated"] == 35 and fit["from_library"] == 0
    sw, sh = fit["suggest"]
    assert sw > 40 and sh > 30 and abs(sw / sh - 40 / 30) < 0.25
    assert fit["area"] / (sw * sh) <= layout.TARGET_FILL + 0.02          # the suggestion has room
    text = layout.fit_text(fit, (40, 30))
    assert "35 parts" in text and "1200 mm2" in text and "typical package sizes" in text and "not changed" in text and f"{sw:g} x {sh:g}" in text


def test_the_built_footprints_are_used_when_they_exist():
    parts = [{"ref": f"R{i}", "footprint": "R0603"} for i in range(3)] + [{"ref": "X1", "footprint": "Missing", "package": "0402"}]
    fit = layout.board_fit(parts, (5, 5), FPS)
    assert fit["from_library"] == 3 and fit["estimated"] == 1
    box = layout.footprint_box(FPS["R0603"])
    assert abs(fit["area"] - (3 * (box[2] - box[0]) * (box[3] - box[1]) + layout.package_area_mm2("0402"))) < 1e-6


def test_one_side_per_side():
    one = layout.board_fit(_parts(20), (30, 30), sides=1)["area"]
    assert abs(layout.board_fit(_parts(20), (30, 30), sides=2)["area"] - one / 2) < 1e-6
    assert layout.board_fit([], (30, 30)) is None and layout.board_fit(_parts(3), None) is None


def test_no_free_place_states_the_area_and_a_size():
    many = [dict(p) for p in PARTS] + [{"ref": f"HX{i}", "footprint": "HDR", "pins": []} for i in range(6)]
    plan = layout.plan_placement(many, FPS, [0, 0, 12, 12])
    msgs = [e for e in plan["errors"] if "no free place" in e or "need" in e]
    assert msgs
    assert all("mm2" in m and "try" in m.lower() or "make the board bigger" in m for m in msgs)
    assert any("mm2" in m for m in msgs)
    plan = layout.plan_placement(many, FPS, [0, 0, 20, 12])
    if any("no free place" in e for e in plan["errors"]):
        assert all("mm2" in e and " x " in e for e in plan["errors"] if "no free place" in e)
    assert OUT
