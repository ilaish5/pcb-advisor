"""Verify later, don't block now: an IC without a datasheet is placed and marked unverified; the Final checks list it."""
import sources
import store
import verify_part


def _add(empty, key, mpn):
    store.propose_bom(empty, key, {"mpn": mpn, "refs": [key]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")


def _sheet(empty):
    _add(empty, "U1", "ABCD1234")
    _add(empty, "R1", "RC0603")
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}]},
        {"ref": "R1", "section": "A", "pins": [{"num": "1", "name": "1", "net": "+3V3"}, {"num": "2", "name": "2", "net": "X"}]}]}
    return store.write_sheet(empty, "01", sheet)


def _datasheet(empty, text):
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 x")
    (folder / "ABCD1234.pdf.txt").write_text(text, encoding="utf-8")


def test_ic_without_datasheet_is_written_and_marked_passives_are_not(empty):
    assert _sheet(empty)["ok"]
    parts = {p["ref"]: p for p in store.load_sheet(empty, "01")["parts"]}
    assert parts["U1"]["pins_source"] == "agent"
    assert "pins_source" not in parts["R1"]
    lines = {l["key"]: l for l in store.bom(empty)}
    assert lines["U1"]["pins_status"] == "unverified" and lines["R1"]["pins_status"] == ""


def test_datasheet_then_verify_clears_the_mark(empty):
    _sheet(empty)
    _datasheet(empty, "1 VCC 2 GND")
    assert [u["line"] for u in store.unverified_parts(empty)] == []     # found the datasheet and verified
    assert store.load_sheet(empty, "01")["parts"][0]["pins_source"] == "datasheet"
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "verified"


def test_conflicting_datasheet_raises_a_finding_and_accept_resolves_it(empty):
    _sheet(empty)
    _datasheet(empty, "1 VDD 2 GND")
    item = store.unverified_parts(empty)[0]
    assert item["status"] == "mismatch" and "VCC" in item["issues"]
    store.accept_pins(empty, "U1")
    assert store.unverified_parts(empty) == []
    assert store.load_sheet(empty, "01")["parts"][0]["pins_source"] == "student"


def test_final_checks_list_unverified_parts(empty):
    _sheet(empty)
    out = store.unverified_parts(empty)
    assert [(u["line"], u["status"]) for u in out] == [("U1", "unverified")]
    store.accept_pins(empty, "U1")
    assert store.unverified_parts(empty) == []


def test_unverified_badge_in_the_schematic(empty):
    import render_sheet
    _sheet(empty)
    svg = render_sheet.render_sheet(store.load_sheet(empty, "01"), store.bom_lines(empty))
    assert svg.count("add the datasheet to verify") == 1
