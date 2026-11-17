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


def test_cli_writes_the_csv_into_exports(home, empty, capsys):
    export_cpl.main([empty, str(FIX / "finished-board.PcbDoc")])
    out = capsys.readouterr().out
    assert f"{empty}_cpl.csv" in out
    assert (home / "projects" / empty / "exports" / f"{empty}_cpl.csv").is_file()


# ---- CPL rotation offset (BOM line field `cpl_rotation`)

def _export_with(monkeypatch, empty, comps, bom):
    import store
    doc = {"components": comps, "pads": []}
    monkeypatch.setattr(export_cpl, "read_pcbdoc", lambda _p: doc)
    monkeypatch.setattr(export_cpl, "board_origin_mm", lambda _p: (0.0, 0.0))
    for line, refs, extra in bom:
        store.append(empty, "bom-log.jsonl", {"ts": "t", "by": "student", "line": line, "changes": {"refs": refs, **extra}})
    return export_cpl.export_cpl(empty, pcb_path=FIX / "finished-board.PcbDoc")


def _comp(ref, rot, layer="Top Layer"):
    return {"ref": ref, "x_mm": 1.0, "y_mm": 2.0, "rotation": rot, "layer": layer}


def test_no_offset_leaves_rotation_unchanged(home, empty, monkeypatch):
    res = _export_with(monkeypatch, empty, [_comp("U1", 90.0)], [("U1", ["U1"], {})])
    assert rows_of(home, res)["U1"]["Rotation"] == "90.0"
    assert res["rotation_offsets"] == [] and res["warnings"] == []


def test_offset_is_added_to_every_ref_of_the_line_mod_360(home, empty, monkeypatch):
    res = _export_with(monkeypatch, empty, [_comp("C1", 270.0), _comp("C2", 0.0), _comp("C3", 10.0)],
                       [("C1", ["C1", "C2"], {"cpl_rotation": 180})])
    rows = rows_of(home, res)
    assert rows["C1"]["Rotation"] == "90.0" and rows["C2"]["Rotation"] == "180.0" and rows["C3"]["Rotation"] == "10.0"
    assert [o["ref"] for o in res["rotation_offsets"]] == ["C1", "C2"] and res["warnings"] == []


def test_bottom_part_keeps_its_rotation_and_is_named_in_a_warning(home, empty, monkeypatch):
    res = _export_with(monkeypatch, empty, [_comp("U2", 30.0, "Bottom Layer"), _comp("U3", 0.0)],
                       [("U2", ["U2", "U3"], {"cpl_rotation": 90})])
    rows = rows_of(home, res)
    assert rows["U2"]["Rotation"] == "30.0" and rows["U3"]["Rotation"] == "90.0"
    assert [o["ref"] for o in res["rotation_offsets"]] == ["U3"]
    assert res["warnings"] == ["U2: CPL rotation offset not applied on the bottom side (JLC does not document its "
                               "direction); check these parts in JLC's placement preview and rotate them there"]


def test_offset_must_be_a_multiple_of_90():
    import pytest
    import store
    assert store.cpl_rotation_value(-90) == 270 and store.cpl_rotation_value("180") == 180
    assert store.cpl_rotation_value("") is None and store.cpl_rotation_value(None) is None
    for bad in (45, "x", True, 90.5, float("nan")):
        with pytest.raises(ValueError):
            store.cpl_rotation_value(bad)


def test_offset_needs_the_students_approval(empty):
    import pytest
    import store
    store.append(empty, "bom-log.jsonl", {"ts": "t", "by": "student", "line": "U1", "changes": {"refs": ["U1"]}})
    rec = store.propose_bom(empty, "U1", {"cpl_rotation": "90"}, "preview shows U1 turned")
    assert rec["changes"] == {"cpl_rotation": 90} and store.classify_proposal(rec) == "critical"
    assert not store.may_auto_apply(rec, "important")
    assert "cpl_rotation" not in next(l for l in store.bom_lines(empty) if l["key"] == "U1")
    with pytest.raises(ValueError):
        store.propose_bom(empty, "U1", {"cpl_rotation": 45})


def _line(store, empty, **ch):
    store.append(empty, "bom-log.jsonl", {"ts": "t", "by": "student", "line": "U1", "changes": {"refs": ["U1"], **ch}})
    return next(l for l in store.bom_lines(empty) if l["key"] == "U1")


def test_offset_is_cleared_when_the_part_changes(empty):
    import store
    assert _line(store, empty, mpn="A", cpl_rotation=90)["cpl_rotation"] == 90
    assert "cpl_rotation" not in _line(store, empty, mpn="B")
    assert _line(store, empty, cpl_rotation=180, package="X")["cpl_rotation"] == 180      # set explicitly in the same change
    assert "cpl_rotation" not in _line(store, empty, lcsc="C1")
    assert _line(store, empty, cpl_rotation=90, note="n")["cpl_rotation"] == 90          # a note does not clear it


def test_offset_can_be_cleared(empty):
    import store
    _line(store, empty, cpl_rotation=90)
    rec = store.propose_bom(empty, "U1", {"cpl_rotation": ""})
    assert rec["changes"] == {"cpl_rotation": None}
    assert store.edit_bom(empty, "U1", "cpl_rotation", "")["changes"] == {"cpl_rotation": None}
    assert not export_cpl.rotation_offsets(empty)


def test_offset_always_asks_even_in_auto_mode(empty):
    import store
    _line(store, empty)
    rec = store.propose_bom(empty, "U1", {"cpl_rotation": 90})
    assert store.classify_proposal(rec) == "critical"
    for mode in ("ask", "important", "auto"):
        assert not store.may_auto_apply(rec, mode)


def test_approval_card_labels_the_offset():
    ui = REPO / "ui" / "js"
    assert "cpl_rotation: 'CPL rotation (added in pick and place)'" in (ui / "chat.js").read_text(encoding="utf-8")
    assert "cpl_rotation: 'CPL rotation (added in pick and place)'" in (ui / "core.js").read_text(encoding="utf-8")
    chat = (ui / "chat.js").read_text(encoding="utf-8")
    assert "'none'" in chat and "'+'" in chat and "°" in chat
    assert "(r.warnings || []).forEach" in (ui / "views" / "outputs.js").read_text(encoding="utf-8").split("onAct('gen-cpl'")[1][:300]
