"""R2 / F-F: Confirm-pins opens the page that holds the part's pin table; a symbol-vs-pad count difference is explained per pad."""
import pin_decisions
import partlib_order


PINS = [{"ref": "J1", "num": str(n), "name": nm, "net": ""} for n, nm in ((1, "VBUS"), (2, "CC1"), (3, "DP"), (4, "DN"))]
HEAD = "Pin Configuration and Functions\n"
TABLE = "Pin No. Pin Name I/O\n1 VBUS Power\n2 CC1 I/O\n3 DP I/O\n4 DN I/O\n"


def test_the_page_with_the_parts_own_pin_rows_comes_first_not_a_blank_or_heading_page():
    pages = ["Cover", HEAD + "Pin Description\n" + "SOIC-8 top view\n", "blank " * 3, HEAD + TABLE]
    text = "\f".join(pages)
    got = pin_decisions.candidate_pages(text, "SOIC-8", PINS)
    assert got[0] == 4, got                       # the page whose text holds the table rows of THIS part


def test_a_page_with_no_rows_of_this_part_is_still_a_candidate_by_heading():
    text = "\f".join(["Cover", HEAD + "Pin Description\n"])
    assert pin_decisions.candidate_pages(text, "", PINS) == [2]


def test_rows_are_counted_by_number_and_name_on_one_line():
    assert pin_decisions.pin_rows_on_page(TABLE, PINS) == 4
    assert pin_decisions.pin_rows_on_page("1 other\n2 text\nVBUS alone\n", PINS) == 0


def _fp(lines, symbol_pins):
    return {"lines": lines, "symbol_pins": [{"num": n} for n in symbol_pins]}


def test_every_extra_pad_is_explained_and_npth_pegs_are_listed(monkeypatch):
    pad = lambda num, plated, hole: f"PAD|{num}|0|0|0|Top Layer|{plated}|{hole}|0|0|0|10|10|1|"
    lines = [pad("1", 1, 0), pad("2", 1, 0), pad("3", 1, 0), pad("3", 1, 0), pad("5", 1, 0), pad("", 0, 80), pad("", 0, 80)]
    monkeypatch.setattr(partlib_order, "footprint_of", lambda project, key: _fp(lines, ["1", "2", "3", "4"]))
    c = pin_decisions.pad_check("p", {"key": "J1"})
    assert c["pads"] == 7 and c["symbol_pins"] == 4
    kinds = sorted(r["kind"] for r in c["rows"])
    assert kinds == ["no_pad", "no_symbol_pin", "npth_peg", "npth_peg", "second_pad"]
    assert len(c["rows"]) == 5 and "5 difference" in c["note"]
    assert all(r["why"] for r in c["rows"])


def test_equal_counts_say_every_pad_is_one_pin(monkeypatch):
    pad = lambda num: f"PAD|{num}|0|0|0|Top Layer|1|0|0|0|0|10|10|1|"
    monkeypatch.setattr(partlib_order, "footprint_of", lambda project, key: _fp([pad("1"), pad("2")], ["1", "2"]))
    c = pin_decisions.pad_check("p", {"key": "R"})
    assert c["rows"] == [] and "every pad is one pin" in c["note"]


def test_no_footprint_is_no_claim(monkeypatch):
    monkeypatch.setattr(partlib_order, "footprint_of", lambda project, key: None)
    assert pin_decisions.pad_check("p", {"key": "J1"}) is None
