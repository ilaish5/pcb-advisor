"""Non-regression: every real sheet our own test boards drew before must still fit one A4 sheet with the designator and comment text
reserved (tests/fixtures/real_sheets: netlists and symbol specs of Live-STM32 01-03, Blinker-555, Dark-sensor-LED, Regulator-3V3,
Live-T29b/c; generic test boards, no paths or names). Symbols are matched to parts by reference prefix and pin numbers."""
import json
import pathlib

import pytest

from altium import draw
from test_altium_draw_text import symbols_from

ROOT = pathlib.Path(__file__).parent / "fixtures" / "real_sheets"
SHEETS = sorted((d.name, f.name) for d in ROOT.iterdir() if d.is_dir() for f in d.glob("*.json"))


def _props(proj):
    out = {}
    for line in (ROOT / proj / "props.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line and "|" in line:
            name, rest = line.split("=", 1)
            pre, com = rest.split("|", 1)
            out[name] = (pre, com)
    return out


def lib_for(proj, sheet):
    syms, props = symbols_from(ROOT / proj / "symbols_spec.txt"), _props(proj)
    out = {}
    for p in sheet["parts"]:
        nums = {str(q.get("num", "")) for q in p["pins"]}
        pre = p["ref"].rstrip("0123456789")
        cand = [s for n, s in syms.items() if {q["number"] for q in s["pins"]} == nums] or                [s for n, s in syms.items() if nums <= {q["number"] for q in s["pins"]}]
        cand = [s for s in cand if props.get(s["name"], ("", ""))[0] == pre] or cand
        assert cand, (proj, p["ref"], nums)
        out[p["ref"]] = {**cand[0], "comment": props.get(cand[0]["name"], ("", cand[0]["name"]))[1]}
    return out


@pytest.mark.parametrize("proj,name", SHEETS)
def test_every_real_sheet_still_fits_one_sheet(proj, name):
    sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
    plan = draw.plan_sheet(sheet, lib_for(proj, sheet), "l", "d")
    assert plan["errors"] == [], plan["errors"][0][:300]
    frames = [c for c in plan["commands"] if c[0] == "FRAME"]
    for c in frames:                                           # frames stay inside the area and on the grid
        x, y, w, h = (int(v) for v in c[2:6])
        assert all(v % draw.GRID == 0 for v in (x, y, w, h)), c
        assert y >= draw.AREA[1] and y + h <= draw.AREA[3] and x + w <= draw.AREA[2] + draw.FRAME_PAD


def test_a_two_pin_part_grows_little_for_its_texts():
    # a resistor cell was 400 mil high before the texts: now both texts sit on one row, so it stays well under double
    sheet = json.loads((ROOT / "Live-STM32" / "03.json").read_text(encoding="utf-8"))
    lib = lib_for("Live-STM32", sheet)
    for p in sheet["parts"]:
        if p["ref"].startswith(("R", "C")) and len(p["pins"]) == 2:
            b = draw.part_cell(p, lib[p["ref"]])["box"]
            assert b[3] - b[1] <= 600, (p["ref"], b)


def test_a_long_comment_is_cut_for_display_and_the_cell_stays_narrow():
    found = None
    for proj, name in SHEETS:
        sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
        lib = lib_for(proj, sheet)
        for p in sheet["parts"]:
            if len(lib[p["ref"]]["comment"]) > draw.MAX_COMMENT:
                found = found or (sheet, lib, p)
    assert found, "the fixtures hold no long comment"
    sheet, lib, part = found
    c = draw.part_cell(part, lib[part["ref"]])
    assert len(c["comment"]) <= draw.MAX_COMMENT and c["comment"].endswith("...") and c["comment_cut"]
    plan = draw.plan_sheet(sheet, lib, "l", "d")
    place = next(x for x in plan["commands"] if x[0] == "PLACE" and x[2] == part["ref"])
    assert place[12] == c["comment"]                         # the shortened text is sent; an uncut comment sends nothing
    assert all(x[12] == "" for x in plan["commands"] if x[0] == "PLACE" and len(lib[x[2]]["comment"]) <= draw.MAX_COMMENT)
