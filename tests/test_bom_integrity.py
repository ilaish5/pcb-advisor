"""R2 / W10, W12: a card never duplicates a designator; an MPN change moves the datasheet binding in the same write."""
import pytest

import sources
import store


def _line(project, key):
    return {l["key"]: l for l in store.bom(project)}[key]


def _approve(project, key, changes, **kw):
    store.propose_bom(project, key, changes, **kw)
    return store.decide(project, store.proposals(project)[-1]["id"], "approved")


def test_a_card_that_reuses_a_designator_is_refused_naming_both_lines_and_writes_nothing(empty):
    _approve(empty, "R3", {"mpn": "RC0603-10K", "refs": ["R3"]}, new=True)
    store.propose_bom(empty, "R4", {"mpn": "RC0603-1K", "refs": ["R3"]}, new=True)
    pid = store.proposals(empty)[-1]["id"]
    with pytest.raises(ValueError) as e:
        store.decide(empty, pid, "approved")
    msg = str(e.value)
    assert "R3" in msg and "line R3" in msg and "R4" in msg
    assert [p for p in store.proposals(empty) if p["id"] == pid][0]["status"] == "pending"      # nothing was decided or written
    refs = [r for l in store.bom(empty) for r in l.get("refs", [])]
    assert len(refs) == len(set(refs))


def test_a_student_edit_cannot_duplicate_a_designator_either(empty):
    _approve(empty, "R3", {"mpn": "RC0603-10K", "refs": ["R3"]}, new=True)
    _approve(empty, "R5", {"mpn": "RC0603-1K", "refs": ["R5"]}, new=True)
    with pytest.raises(ValueError, match="R3 is already on line R3"):
        store.edit_bom(empty, "R5", "refs", ["R5", "R3"])


def _with_datasheets(empty, names):
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    for n, text in names.items():
        (folder / n).write_bytes(b"%PDF-1.4 x")
        (folder / (n + ".txt")).write_text(text, encoding="utf-8")


def test_an_mpn_change_rebinds_the_datasheet_to_a_file_that_names_the_new_part(empty):
    _with_datasheets(empty, {"AMS1117-3.3.pdf": "AMS1117-3.3 regulator", "ME6211C33M5G-N.pdf": "ME6211C33M5G-N LDO"})
    _approve(empty, "U5", {"mpn": "AMS1117-3.3", "refs": ["U5"], "datasheet": "AMS1117-3.3.pdf"}, new=True)
    _approve(empty, "U5", {"mpn": "ME6211C33M5G-N"})
    u5 = _line(empty, "U5")
    assert u5["datasheet"] == "ME6211C33M5G-N.pdf"                 # same write: never a window with the old datasheet
    assert "rebound" in store.library_parts(empty)["U5"]["issues"]
    assert u5["pins_status"] != "verified" and u5.get("pins_evidence") is None


def test_an_mpn_change_with_no_matching_file_unbinds_and_pins_are_not_checked(empty):
    _with_datasheets(empty, {"AMS1117-3.3.pdf": "AMS1117-3.3 regulator"})
    _approve(empty, "U5", {"mpn": "AMS1117-3.3", "refs": ["U5"], "datasheet": "AMS1117-3.3.pdf"}, new=True)
    store.edit_bom(empty, "U5", "mpn", "ME6211A33PG-N")
    u5 = _line(empty, "U5")
    assert not u5.get("datasheet")
    assert store.library_parts(empty)["U5"]["verify"] == "unchecked" and "unbound" in store.library_parts(empty)["U5"]["issues"]
    assert u5["pins_status"] != "verified"


def test_a_datasheet_that_already_names_the_new_mpn_is_kept(empty):
    _with_datasheets(empty, {"family.pdf": "ME6211C33M5G-N and ME6211A33PG-N regulators"})
    _approve(empty, "U5", {"mpn": "ME6211C33M5G-N", "refs": ["U5"], "datasheet": "family.pdf"}, new=True)
    store.edit_bom(empty, "U5", "mpn", "ME6211A33PG-N")
    assert _line(empty, "U5")["datasheet"] == "family.pdf"
