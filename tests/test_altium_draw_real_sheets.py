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


def test_a_long_comment_is_never_changed_and_its_full_width_is_reserved():
    long_seen = 0
    for proj, name in SHEETS:
        sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
        lib = lib_for(proj, sheet)
        plan = draw.plan_sheet(sheet, lib, "l", "d")
        for p in sheet["parts"]:
            com = lib[p["ref"]]["comment"].strip()
            c = draw.part_cell(p, lib[p["ref"]])
            assert c["comment"] == com                               # whole text, no "..."
            if len(com) > 16:
                long_seen += 1
                x, y, w = c["texts"]["com"]
                assert w == len(com) * draw.TEXT_CHAR and c["box"][0] <= x and x + w <= c["box"][2]
        for x in plan["commands"]:
            if x[0] == "PLACE":
                assert len(x) == 12                                  # no text field: the comment of the instance is never written
    assert long_seen


def test_the_bridge_never_assigns_the_comment_text():
    import re
    src = (pathlib.Path(__file__).parent.parent / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    body = src[src.index("procedure PlacePart("):]
    body = body[:body.index("\nend;")]                    # the placing of an instance: its comment (BOM, PCB) is never assigned
    assert not re.search(r"Comment\s*\.\s*Text\s*:=", body, re.I) and "ComText" not in src
