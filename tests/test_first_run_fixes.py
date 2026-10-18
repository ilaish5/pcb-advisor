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


def test_sheet_refuses_a_part_that_is_not_in_the_bom(empty):
    sheet = {"parts": [{"ref": "R9", "pins": [{"name": "1", "net": "A"}]}]}
    assert "R9: not in the BOM" in store.write_sheet(empty, "01", sheet)["errors"]


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
