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
    assert next(s for s in store.load_idea_working(empty)["diagram"]["shapes"] if s["id"] == "t")["domain"] == "sensors"


def test_an_unknown_domain_is_drawn_neutral_not_refused(empty):
    # Sonnet wrote "debug" and the whole first diagram was dropped
    res = store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "swd", "x": 1, "y": 1, "domain": "debug"},
                                           {"op": "add_shape", "id": "odd", "x": 9, "y": 9, "domain": "quantum"}])
    assert res["ok"]
    shapes = {s["id"]: s for s in store.load_idea_working(empty)["diagram"]["shapes"]}
    assert shapes["swd"]["domain"] == "io" and shapes["odd"].get("domain", "") == ""
    assert store.validate_diagram({"shapes": [{"id": "s", "type": "box", "x": 0, "y": 0, "w": 1, "h": 1,
                                               "domain": "quantum"}]})["shapes"][0]["domain"] == ""


def test_a_whole_diagram_block_takes_its_domain_colours():
    s = store.validate_diagram({"shapes": [{"id": "p", "type": "box", "x": 0, "y": 0, "w": 1, "h": 1,
                                            "domain": "power"}]})["shapes"][0]
    assert s["fill"] == store.DOMAIN_COLORS["power"]["fill"] and s["stroke"] == store.DOMAIN_COLORS["power"]["stroke"]


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


def test_changing_a_line_still_waiting_for_approval_replaces_its_card(empty):
    # Sonnet proposed R1 (1k, new), then 470R for R1 without new: and was refused
    store.propose_bom(empty, "R1", {"mpn": "0603WAF1001T5E", "value": "1k"}, new=True)
    first = store.proposals(empty)[-1]["id"]
    store.propose_bom(empty, "R1", {"mpn": "0603WAF4700T5E", "value": "470"})
    rows = {p["id"]: p for p in store.proposals(empty)}
    assert rows[first]["status"] == "rejected" and rows[first]["decided_by"] == "superseded"
    card = store.proposals(empty)[-1]
    assert card["status"] == "pending" and card["new"] and card["changes"]["mpn"] == "0603WAF4700T5E"
    assert card["changes"]["refs"] == ["R1"]
    store.decide(empty, card["id"], "approved")
    assert next(l for l in store.bom_lines(empty) if l["key"] == "R1")["mpn"] == "0603WAF4700T5E"


def test_a_diagram_op_with_another_verb_is_understood(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "a", "x": 0, "y": 0},
                                     {"op": "add_shape", "id": "b", "x": 9, "y": 0},
                                     {"op": "add_connector", "id": "ab", "from": "a", "to": "b"}])
    assert store.apply_diagram_edit(empty, [{"op": "remove_connector", "id": "ab"}])["ok"]
    assert not store.load_idea_working(empty)["diagram"]["connectors"]
    with pytest.raises(ValueError, match="ops: add_"):
        store.apply_diagram_edit(empty, [{"op": "explode_shape", "id": "a"}])


def test_a_pdf_from_a_link_with_no_extension_is_saved_as_pdf(empty, monkeypatch):
    # JLC's datasheet links end in a bare file id; without .pdf find_for and verify_part never see it
    monkeypatch.setattr(sources, "_download", lambda url, timeout: b"%PDF-1.4 x")
    res = sources.get(empty, "https://jlcpcb.com/api/file/downloadByFileSystemAccessId/8589012691923320832")
    assert res["name"] == "8589012691923320832.pdf"
    assert sources.get(empty, "https://x/y/12345", "ATTINY412-SSNR")["name"] == "ATTINY412-SSNR.pdf"
    assert sources.find_for(empty, "ATTINY412-SSNR") == "ATTINY412-SSNR.pdf"


def _row_of_blocks_around_a_hub():
    ids = ["bat", "mcu", "temp", "door", "buzzer", "led"]
    ops = [{"op": "add_shape", "id": i, "x": 100 + 200 * n, "y": 100, "w": 160, "h": 68} for n, i in enumerate(ids)]
    links = [("bat", "mcu"), ("mcu", "temp"), ("door", "mcu"), ("mcu", "buzzer"), ("mcu", "led")]
    return ops + [{"op": "add_connector", "id": f"c{n}", "from": a, "to": b} for n, (a, b) in enumerate(links)]


def test_a_first_diagram_drawn_as_one_row_around_a_hub_is_laid_out(empty):
    # Sonnet and Flash both put every block in one row: the MCU's links ran through the sensor and looked like a chain
    store.apply_diagram_edit(empty, _row_of_blocks_around_a_hub())
    shapes = store.load_idea_working(empty)["diagram"]["shapes"]
    assert not store._hidden_links(shapes, store.load_idea_working(empty)["diagram"]["connectors"])
    x = {s["id"]: s["x"] for s in shapes}
    assert x["bat"] == x["door"] < x["mcu"] < x["temp"] == x["buzzer"] == x["led"]


def test_blocks_the_student_placed_are_not_moved(empty):
    store.apply_diagram_edit(empty, _row_of_blocks_around_a_hub()[:6])
    before = {s["id"]: (s["x"], s["y"]) for s in store.load_idea_working(empty)["diagram"]["shapes"]}
    store.apply_diagram_edit(empty, [{"op": "add_connector", "id": "c", "from": "mcu", "to": "led"}])
    assert {s["id"]: (s["x"], s["y"]) for s in store.load_idea_working(empty)["diagram"]["shapes"]} == before


def test_a_citation_in_a_chat_table_cell_is_not_split():
    # Flash's review table showed raw {{src:...}}: the citation's own | was taken for a cell border
    import pathlib
    import re
    core = (pathlib.Path(__file__).parents[1] / "ui/js/core.js").read_text(encoding="utf-8")
    split = re.search(r"const cells = l => .*?\.split\(/(.+?)/\)", core).group(1)
    row = "1 | U1.5 | {{src:STM32L011F4P6.pdf|p. 45, Figure 13}}"
    assert [c.strip() for c in re.split(split, row)] == ["1", "U1.5", "{{src:STM32L011F4P6.pdf|p. 45, Figure 13}}"]
