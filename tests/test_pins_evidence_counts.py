"""R2 / W14: the pin evidence record counts what pintable compared against every pin of the symbol; no page is guessed;
a pin named by its number is still verified by its row."""
import store
import verify_part
from test_unverified_pins import _add, _datasheet


def _u1(empty, pins):
    _add(empty, "U1", "ABCD1234")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}],
                                    "parts": [{"ref": "U1", "section": "A", "pins": pins}]})


def _line(empty):
    return {l["key"]: l for l in store.bom(empty)}["U1"]


def test_a_pin_named_by_its_number_is_compared_by_its_row_and_counted(empty):
    _u1(empty, [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}, {"num": "3", "name": "3", "net": "X"}])
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground", "3 OUT Output"])
    store.unverified_parts(empty)
    u1 = _line(empty)
    assert u1["pins_status"] == "verified"
    assert u1["pins_evidence"]["pins_compared"] == u1["pins_evidence"]["symbol_pins"] == 3


def test_a_nameless_symbol_pin_is_in_the_symbol_count_so_the_part_is_not_fully_verified(empty):
    _u1(empty, [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}, {"num": "3", "name": "", "net": "X"}])
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground", "3 OUT Output"])
    store.unverified_parts(empty)
    u1 = _line(empty)
    ev = (store.library_parts(empty).get("U1") or {}).get("pins_evidence")
    assert not ev or ev["symbol_pins"] == 3 and ev["pins_compared"] < 3
    assert u1["pins_status"] != "verified"


def test_a_no_connect_pin_with_no_table_row_is_not_counted_as_compared(empty):
    _u1(empty, [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}, {"num": "3", "name": "NC", "net": "NC"}])
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    store.unverified_parts(empty)
    ev = (store.library_parts(empty).get("U1") or {}).get("pins_evidence")
    assert not ev or ev["pins_compared"] == 2 and ev["symbol_pins"] == 3
    assert _line(empty)["pins_status"] != "verified"


def test_no_compared_row_on_any_page_means_no_record_not_page_one(empty):
    _u1(empty, [{"num": "1", "name": "VCC", "net": "+3V3"}])
    _datasheet(empty, ["1 VCC Supply"])
    assert verify_part._evidence_record(empty, "ABCD1234.pdf", "a page with no pin rows at all", [("1", "VCC")], 1, 1) is None
    rec = verify_part._evidence_record(empty, "ABCD1234.pdf", "intro\f1 VCC Supply", [("1", "VCC")], 1, 1)
    assert rec["page"] == 2
