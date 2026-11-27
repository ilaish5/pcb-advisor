"""R2 / W14 / U1: a pin status of 'verified' stands on a read-back of the datasheet file, never on a label; the empty status is gone."""
import hashlib

import sources
import store
from test_unverified_pins import _add, _datasheet, _sheet


def _line(empty, key):
    return {l["key"]: l for l in store.bom(empty)}[key]


def test_a_pin_table_pass_carries_an_evidence_record_read_back_from_the_file(empty):
    _sheet(empty)
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    store.unverified_parts(empty)                     # finds the datasheet and verifies
    u1 = _line(empty, "U1")
    ev = u1["pins_evidence"]
    f = sources.folder_of(empty) / "ABCD1234.pdf"
    assert u1["pins_status"] == "verified" and u1["pins_basis"] == "datasheet"
    assert ev["doc"] == "ABCD1234.pdf" and ev["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert ev["pins_compared"] == ev["symbol_pins"] == 2 and isinstance(ev["page"], int)


def test_a_datasheet_that_changed_after_the_check_is_stale_not_verified(empty):
    _sheet(empty)
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    store.unverified_parts(empty)
    assert _line(empty, "U1")["pins_status"] == "verified"
    (sources.folder_of(empty) / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 a different file")
    u1 = _line(empty, "U1")
    assert u1["pins_status"] == "unverified" and u1["pins_evidence"] is None
    assert "changed since" in u1["pins_issues"]


def test_a_pass_without_an_evidence_record_is_not_green():
    line = {"key": "U1", "refs": ["U1"], "datasheet": "x.pdf"}
    st, why = store.pins_status(line, {"verify": "pass", "method": "pin-table"})
    assert st == "unverified" and "evidence" in why


def test_fewer_pins_compared_than_the_symbol_has_is_not_verified(empty):
    _sheet(empty)
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    store.unverified_parts(empty)
    rec = dict(store.library_parts(empty)["U1"]["pins_evidence"], pins_compared=1)
    store.add_library(empty, "U1", {"pins_evidence": rec}, by="test")
    u1 = _line(empty, "U1")
    assert u1["pins_status"] == "unverified" and "1 of 2" in u1["pins_issues"]


def test_the_empty_status_is_never_returned():
    for refs, want in ((["R1"], "not_applicable"), (["C3", "C4"], "not_applicable"), (["FB1"], "not_applicable"),
                       (["TP1"], "not_applicable"), (["FID1"], "not_applicable"),
                       (["Y1"], "not_checked"), (["SW1"], "not_checked"), (["F1"], "not_checked")):
        assert store.pins_status({"key": refs[0], "refs": refs}, {})[0] == want, refs
    # a polarised capacitor is not an unpolarised two-terminal passive
    assert store.pins_status({"key": "C9", "refs": ["C9"], "role": "tantalum bulk"}, {})[0] == "not_checked"
    assert store.pins_status({"key": "U9", "refs": ["U9"]}, {}, check_wired=False)[0] == "unverified"


def test_a_part_with_nothing_wired_is_not_checked_with_the_reason(empty):
    _add(empty, "U1", "ABCD1234")
    assert _line(empty, "U1")["pins_status"] in ("not_checked", "unverified")
    assert _line(empty, "U1")["pins_issues"]
