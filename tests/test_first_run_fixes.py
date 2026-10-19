"""Regressions from the first real student session (projects/test, 2026-10-14)."""
import json

import pytest

import render_sheet
import sources
import store


def test_new_line_named_like_a_designator_gets_its_ref(empty):
    store.propose_bom(empty, "U1", {"mpn": "X"}, new=True)
    prop = store.proposals(empty)[-1]
    assert prop["changes"]["refs"] == ["U1"]


def test_sheet_writes_a_part_that_is_not_in_the_bom_with_a_warning(empty):
    sheet = {"parts": [{"ref": "R9", "pins": [{"name": "1", "net": "A"}]}]}
    res = store.write_sheet(empty, "01", sheet)
    assert res["ok"] and "R9: not in the BOM yet" in res["warnings"]


def test_diagram_domain_singular_is_accepted():
    assert store.DOMAIN_ALIASES["sensor"] in store.VALID_DOMAINS


def test_render_accepts_plain_string_notes():
    sheet = {"sections": [{"id": "A", "title": "Power"}], "notes": ["plain note"],
             "parts": [{"ref": "R1", "section": "A", "pins": [{"num": "1", "name": "1", "net": "X"}]}]}
    assert "plain note" in render_sheet.render_sheet(sheet, [])


def test_dropped_pdf_is_registered_and_found_by_part_number(empty):
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "PT204-6B.pdf").write_bytes(b"%PDF-1.4 x")
    assert sources.find_for(empty, "PT204-6B") == "PT204-6B.pdf"
    meta = json.loads((folder / "PT204-6B.pdf.json").read_text(encoding="utf-8"))
    assert meta["sha256"] and meta["url"] is None


def test_designator_keyed_line_without_refs_counts_everywhere(empty):
    store.propose_bom(empty, "R5", {"mpn": "RC0603", "refs": []}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    line = next(l for l in store.bom_lines(empty) if l["key"] == "R5")
    assert line["refs"] == ["R5"] and store.qty(line) == 1
    sheet = {"sections": [{"id": "A", "title": "T"}],
             "parts": [{"ref": "R5", "section": "A", "pins": [{"num": "1", "name": "1", "net": "X"}]}]}
    assert store.write_sheet(empty, "01", sheet)["ok"]
    assert next(l for l in store.bom(empty) if l["key"] == "R5")["on_sheet"] == ["01:A"]
    assert "R5" in render_sheet.render_sheet(store.load_sheet(empty, "01"), store.bom_lines(empty))


def test_domain_alias_goes_through_validate_and_edit(empty):
    shape = {"id": "s", "type": "box", "x": 0, "y": 0, "w": 10, "h": 10, "domain": " Sensor "}
    assert store.validate_diagram({"shapes": [shape]})["shapes"][0]["domain"] == "sensors"
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "t", "x": 1, "y": 1, "domain": "Sensor"}])
    assert next(s for s in store.load_idea(empty)["diagram"]["shapes"] if s["id"] == "t")["domain"] == "sensors"


def test_verify_with_find_for_and_no_pins_is_not_a_pass(empty):
    import verify_part
    store.propose_bom(empty, "U7", {"mpn": "ABCD1234", "refs": ["U7"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ABCD1234.PDF").write_bytes(b"%PDF-1.4 x")
    (folder / "ABCD1234.PDF.txt").write_text("1 VCC", encoding="utf-8")
    assert sources.find_for(empty, "ABCD1234") == "ABCD1234.PDF"
    assert verify_part.verify(empty, "U7")["verify"] == "unchecked"


def test_adopt_skips_non_documents(empty):
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    for n in ("Thumbs.db", "desktop.ini", ".hidden", "notes.md", "a.PDF"):
        (folder / n).write_bytes(b"x")
    assert sources.adopt(empty) == ["a.PDF"]
