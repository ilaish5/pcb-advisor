"""Review fixes: pin counts from the package family, no smaller-board suggestion, soft band, ADDDOC listed check, scrub details."""
import json
import pathlib
import zipfile

import pytest

import runlog
from altium import layout
from test_altium_layout import FPS, PARTS

PAS = (pathlib.Path(__file__).parent.parent / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")


@pytest.mark.parametrize("name,low,high", [
    ("SOP-8_150mil", 40, 60), ("SOP-8_L4.9-W3.9-P1.27-LS6.0-BL", 35, 50), ("MSOP-10_P0.50", 30, 50), ("TSSOP-20_P0.65", 60, 90),
    ("SOIC-8", 40, 60), ("QFN-56", 60, 80), ("LGA-8", 10, 14), ("PinHeader_1x05_P2.54mm", 40, 55)])
def test_pin_count_is_the_number_of_the_family_not_a_dimension(name, low, high):
    assert low <= layout.package_area_mm2(name) <= high, (name, layout.package_area_mm2(name))


def test_per_part_defaults():
    assert layout.package_area_mm2("", "SW1") == 42.0 and layout.package_area_mm2("", "J2") == 26.0


def test_no_smaller_board_is_suggested_and_a_low_fill_blames_the_shape():
    many = [dict(p) for p in PARTS] + [{"ref": f"HX{i}", "footprint": "HDR", "pins": []} for i in range(2)]
    plan = layout.plan_placement(many, FPS, [0, 0, 6, 60])           # a long thin board: plenty of area, no room
    msgs = [e for e in plan["errors"] if "no free place" in e]
    assert msgs and all("shape" in m and "try about" not in m for m in msgs)
    fit = layout.board_fit([{"ref": "R1", "footprint": "", "package": "0603"}] * 3, (100, 100))
    assert fit["suggest"] is None


def test_the_soft_band_warns_only_for_estimated_sizes():
    parts = [{"ref": f"R{i}", "footprint": "", "package": "0603"} for i in range(100)]         # 100 x 5 = 500 mm2
    fit = layout.board_fit(parts, (35, 35))                                                    # 41%
    assert fit["soft"] and not fit["tight"] and "may be tight" in layout.fit_text(fit, (35, 35)) and fit["suggest"][0] >= 35
    box = layout.footprint_box(FPS["R0603"])
    real = layout.board_fit([{"ref": "R1", "footprint": "R0603"}] * 100, (box[2] - box[0] and 35, 35), FPS)
    assert not real["soft"]                                                                    # sizes from the library: no soft warning
    assert not layout.board_fit(parts, (50, 50))["soft"] and layout.board_fit(parts, (20, 20))["tight"]


def test_a_board_like_the_e2e_one_is_soft_flagged_on_40x30_and_quiet_on_45x35():
    """The E2E parts (43; packages from its BOM): 44% of 40 x 30 (the board that failed in Place), 34% of 45 x 35 (it placed), and
    small boards of the other projects stay quiet."""
    items = [("U", "LQFN-56(7x7)", 1), ("U", "SOIC-8", 1), ("U", "SOT-223", 1), ("U", "LGA-8(2.5x2.5)", 1), ("U", "SOT-23-6L", 1),
             ("Y", "SMD3225-4P", 1), ("J", "SMD", 1), ("J", "Plugin,P=2.54mm", 1), ("SW", "SMD-4P,5.1x5.1mm", 2),
             ("C", "0603", 20), ("R", "0603", 9), ("D", "0603", 2), ("C", "0805", 2)]
    parts = [{"ref": f"{r}{i}", "footprint": "", "package": pkg} for r, pkg, n in items for i in range(n)]
    assert len(parts) == 43
    fit = layout.board_fit(parts, (40, 30))
    assert fit["soft"] and not fit["tight"] and 0.40 < fit["fill"] < 0.50 and fit["suggest"] == (45, 35)
    assert not layout.board_fit(parts, (45, 35))["soft"] and layout.fit_text(layout.board_fit(parts, (45, 35)), (45, 35)) == ""
    small = [{"ref": f"{r}{i}", "footprint": "", "package": pkg} for r, pkg, n in (("U", "LQFP-48", 1), ("C", "0603", 12), ("R", "0603", 8),
                                                                                   ("J", "", 3), ("Y", "", 1), ("D", "0603", 1)) for i in range(n)]
    assert not layout.board_fit(small, (45, 40))["soft"]                                      # a Live-STM32 sized design (about 20%)


def test_adddoc_checks_the_listed_documents_like_newdocument():
    body = PAS[PAS.index("procedure AddDocument"):PAS.index("{ ====")]
    assert "DM_LogicalDocuments" in body and "Listed" in body and "SameFile" in body


def test_scrub_json_escaped_newline_before_a_path_and_names_stop_at_the_next_word():
    raw = json.dumps("first line\nC:\\Users\\zebulon_q\\AppData\\x")
    assert "zebulon_q" not in runlog.home_paths(raw) and "\\n%USERPROFILE%" in runlog.home_paths(raw)
    assert runlog.home_paths("C:\\Users\\zebulon_q and the rest of the line") == "%USERPROFILE% and the rest of the line"
    assert runlog.home_paths(json.dumps("C:\\Users\\zebulon_q\nnext")) == json.dumps("%USERPROFILE%\nnext")
    assert runlog.home_paths("C:\\Users\\John Smith\\AppData") == "%USERPROFILE%\\AppData"


def test_scrubbed_zip_stores_a_non_utf8_file_as_it_is(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"\xff\xfe\x00C:\\Users\\zebulon_q" + bytes(range(128, 140)))
    t = tmp_path / "t.txt"
    t.write_text("C:\\Users\\zebulon_q\\x", encoding="utf-8")
    with runlog._ScrubbedZip(tmp_path / "o.zip", "x") as z:
        z.write(f, "x.bin")
        z.write(t, "t.txt")
    z = zipfile.ZipFile(tmp_path / "o.zip")
    assert z.read("x.bin") == f.read_bytes() and z.read("t.txt") == b"%USERPROFILE%\\x"
