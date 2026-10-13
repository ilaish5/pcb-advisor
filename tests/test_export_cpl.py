"""The JLC CPL export: positions relative to the board origin, Mid at the centre of the pads."""
import csv
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from skills import export_cpl  # noqa: E402
from altium.pcbdoc import read_pcbdoc  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "altium"


def rows_of(home, res):
    with open(home / res["file"], encoding="utf-8") as fh:
        return {r["Designator"]: r for r in csv.DictReader(fh)}


def mm(s):
    return float(s.removesuffix("mm"))


def test_board_origin_is_read():
    assert export_cpl.board_origin_mm(FIX / "finished-board.PcbDoc") == (25.4, 25.4)
    assert export_cpl.board_origin_mm(FIX / "rules-board.PcbDoc") == (0.0, 0.0)


def test_positions_are_relative_to_the_board_origin(home, empty):
    """Found on a real board on 2026-10-13: every position was 25.4 mm off because the origin
    (1000 mil, 1000 mil) was not subtracted."""
    pcb = FIX / "finished-board.PcbDoc"
    res = export_cpl.export_cpl(empty, pcb_path=pcb)
    rows = rows_of(home, res)
    doc = read_pcbdoc(pcb)
    centres = export_cpl.pad_centres(doc)
    assert res["count"] == len(rows) > 0
    for c in doc["components"]:
        if not c["ref"]:
            continue
        x, y = centres.get(c["ref"], (c["x_mm"], c["y_mm"]))
        assert abs(mm(rows[c["ref"]]["Mid X"]) - (x - 25.4)) < 1e-3
        assert abs(mm(rows[c["ref"]]["Mid Y"]) - (y - 25.4)) < 1e-3
        assert rows[c["ref"]]["Rotation"] == f"{c['rotation']:.1f}"


def test_pad_centre_is_the_middle_of_the_pad_box():
    doc = {"pads": [
        {"ref": "J1", "x_mm": 0.0, "y_mm": 0.0, "sx_mm": 1.0, "sy_mm": 1.0},
        {"ref": "J1", "x_mm": 10.0, "y_mm": 4.0, "sx_mm": 3.0, "sy_mm": 1.0},
        {"ref": None, "x_mm": 99.0, "y_mm": 99.0, "sx_mm": 1.0, "sy_mm": 1.0},
    ]}
    assert export_cpl.pad_centres(doc) == {"J1": ((-0.5 + 11.5) / 2, (-0.5 + 4.5) / 2)}
