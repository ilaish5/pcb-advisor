import pytest
"""E3 (the JLC BOM leaves out DNP lines and designators on no drawn sheet, and says so) and E12 (a part checked against a datasheet
page is not listed as "not verified by a datasheet table"). E1 (pins warn, an unrouted board blocks): test_manufacturing_block.py."""
import csv
import pathlib

import export_bom
import store
from test_unverified_pins import _add, _sheet

REPO = pathlib.Path(__file__).resolve().parent.parent


def _csv(empty):
    path = store.pdir(empty) / "exports" / f"{empty}_BOM_jlc.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def _draw(empty):
    """Record sheet 01 as drawn in Altium (the record the bridge writes), so "on a drawn sheet" is a fact."""
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"01": "Main.SchDoc"}})


def test_the_jlc_bom_leaves_out_parts_on_no_drawn_sheet_and_says_which(empty):
    _sheet(empty)                          # U1, R1 on sheet 01
    _add(empty, "J2", "USB-C")             # in the BOM, on no sheet
    _add(empty, "R22", "RC0603")
    _draw(empty)
    res = export_bom.export(empty, "jlc")
    refs = [r[1] for r in _csv(empty)[1:]]
    assert sorted(refs) == ["R1", "U1"]
    assert sorted(x["refs"][0] for x in res["off_sheet"]) == ["J2", "R22"]
    assert res["left_out_text"].startswith("Left out of the JLC BOM: ") and "J2" in res["left_out_text"] and "R22" in res["left_out_text"]
    assert "no drawn sheet" in res["left_out_text"]


def test_a_line_keeps_its_refs_that_are_on_the_sheet(empty):
    _sheet(empty)
    store.propose_bom(empty, "R1", {"refs": ["R1", "R9"]})
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    _draw(empty)
    res = export_bom.export(empty, "jlc")
    row = next(r for r in _csv(empty)[1:] if "R1" in r[1])
    assert row[1] == "R1" and res["off_sheet"] == [{"line": "R1", "refs": ["R9"]}]


def test_dnp_lines_are_left_out_of_the_jlc_bom_by_flag_or_by_text_and_named(empty):
    _sheet(empty)
    _add(empty, "C29", "DNP")              # the MPN says DNP
    store.edit_bom(empty, "R1", "dnp", True)
    sh = store.load_sheet(empty, "01")
    sh["parts"] += [{"ref": "C29", "section": "A", "pins": []}]
    store.write_sheet(empty, "01", sh)
    _draw(empty)
    res = export_bom.export(empty, "jlc")
    assert [r[1] for r in _csv(empty)[1:]] == ["U1"]
    assert sorted(res["dnp"]) == ["C29", "R1"] and "2 DNP line(s)" in res["left_out_text"]


def test_a_bom_only_project_drops_nothing_for_want_of_a_sheet(empty):
    _add(empty, "U1", "ABCD1234")
    res = export_bom.export(empty, "jlc")
    assert [r[1] for r in _csv(empty)[1:]] == ["U1"] and res["off_sheet"] == [] and res["left_out_text"] == ""


def test_the_other_formats_keep_every_line(empty):
    _sheet(empty)
    _add(empty, "J2", "USB-C")
    _draw(empty)
    res = export_bom.export(empty, "generic")
    assert res["lines"] == 3 and res["off_sheet"] == []


def test_the_bom_page_toast_and_the_altium_fallback_say_what_was_left_out():
    js = (REPO / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")
    assert "res.left_out_text" in js
    bridge = (REPO / "scripts" / "altium" / "bridge.py").read_text(encoding="utf-8")
    assert 'res["left_out_text"]' in bridge


# ---- E12

def test_a_part_checked_against_a_datasheet_page_is_not_listed_as_not_verified_by_a_datasheet():
    pins = (REPO / "ui" / "js" / "views" / "pins.js").read_text(encoding="utf-8")
    body = pins[pins.index("function pinRisksHTML"):][:700]
    assert "r.basis === 'datasheet_page'" in pins and "Checked by you" in body
    assert "pins you checked against a datasheet page" in body
    risks = body[body.index("'Accepted risks'"):]
    assert "!PIN_PAGE_CHECKED(r)" in body and "without checking a datasheet page" in risks


def test_the_design_report_splits_page_checked_from_blind_accepts():
    src = (REPO / "scripts" / "design_report.py").read_text(encoding="utf-8")
    assert "Pins checked by the student against a datasheet page" in src and "without a datasheet page" in src



@pytest.mark.route_gate
def test_drc_without_the_unrouted_rule_is_not_ready(monkeypatch):
    """A design rule check that did not run Un-Routed Net cannot say the copper is complete (review 24/11/2026)."""
    import board_results
    import store
    drc = {"rules": {"Clearance Constraint": 0}, "unrouted": 0, "complete": True, "violations": []}
    monkeypatch.setattr(board_results, "latest", lambda p: {"board_check": {"drc": drc}})
    st = store.route_state("x")
    assert not st["ready"] and "Un-Routed Net rule" in st["why"]
    drc["rules"]["Un-Routed Net Constraint ( (All) )"] = 0
    assert store.route_state("x")["ready"]
