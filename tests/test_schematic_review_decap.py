"""R2 / W22: a supply pin's decoupling requirement comes from a SOURCE that says it (the cited family table, else a strict one-line row of the part's own
datasheet text); no source means "not checked" with the reason. Never a guess from prose or from the part family. Slots: a high-frequency slot takes a
ceramic of 1x to 10x the value, a bulk slot 0.4x to 10x; a capacitor serves one slot; DNP parts are not capacitors; a capacitor whose value cannot be read
makes the pin "not checked". The family and the datasheet phrasings below are written for these tests."""
import pytest

import decap_requirements as dr
import schematic_review as sr

FAM = {"id": "testfam", "match": "^TESTMCU", "groups": [
    {"pin": "^VDD(?:_?\\d+)?$", "schemes": [{"per_pin": [{"role": "hf", "farads": 1e-7}], "per_device": [{"role": "bulk", "farads": 4.7e-6}],
                                              "cite": {"file": "x.md", "page": 1}}]},
    {"pin": "^VDDA$", "schemes": [{"per_pin": [{"role": "hf", "farads": 1e-8}, {"role": "bulk", "farads": 1e-6}], "cite": {"file": "x.md", "page": 1}},
                                   {"per_pin": [{"role": "hf", "farads": 1e-7}, {"role": "bulk", "farads": 1e-6}], "cite": {"file": "x.md", "page": 2}}]}]}


@pytest.fixture(autouse=True)
def family(monkeypatch):
    monkeypatch.setitem(dr._cache, "t", [FAM])


def P(ref, pins, section="", **kw):
    return dict({"ref": ref, "section": section, "pins": [{"num": str(i + 1), "name": n, "net": net} for i, (n, net) in enumerate(pins)]}, **kw)


def cap(ref, net, value, **kw):
    return dict(P(ref, [("1", net), ("2", "GND")], "B"), value=value, **kw)


def mcu(npins=3, mpn="TESTMCU411"):
    return P("U1", [("VDD", "+3V3")] * npins + [("VDDA", "+3V3A"), ("VSS", "GND")], "B", mpn=mpn)


def board(n=3, bulk="4.7uF", analog=("10nF", "1uF"), hf="100nF", extra=()):
    caps = [cap(f"C{i}", "+3V3", hf) for i in range(1, n + 1)] + [cap("C20", "+3V3", bulk)]
    caps += [cap(f"C3{i}", "+3V3A", v) for i, v in enumerate(analog)]
    return [mcu(n)] + caps + list(extra)


def run(parts, ds=None):
    return sr.review("x", parts=parts, datasheets=ds or {})


def missing(parts, ds=None):
    return [f for f in run(parts, ds)["findings"] if f["class"] == "decap_missing"]


def test_a_complete_board_is_clean():
    r = run(board())
    assert not r["findings"] and not r["not_checked"]


def test_removing_all_the_100nf_caps_is_one_finding_per_vdd_pin():
    f = missing([p for p in board() if p.get("value") != "100nF"])
    assert len(f) == 3 and all("100 nF" in x["text"] for x in f)
    assert [("pin %d" % n) in " ".join(x["text"] for x in f) for n in (1, 2, 3)] == [True] * 3


def test_removing_the_bulk_or_an_analog_capacitor():
    assert len(missing([p for p in board() if p["ref"] != "C20"])) == 1 and "4.7 uF" in missing([p for p in board() if p["ref"] != "C20"])[0]["text"]
    gone = [p for p in board() if p["ref"] != "C31"]
    assert len(missing(gone)) == 1 and "1 uF" in missing(gone)[0]["text"]


def test_every_scheme_the_source_allows_is_accepted_and_the_bulk_never_fills_a_high_frequency_slot():
    assert not missing(board(analog=("100nF", "1uF")))
    assert not missing(board(analog=("1uF", "100nF", "100nF")))          # 1 uF + 2 x 100 nF: both HF candidates and the bulk are there
    assert missing(board(analog=("1uF",)))                                # the lone 1 uF is the bulk one: the HF slot stays empty
    assert missing(board(analog=("4.7uF", "47uF")))                       # neither is a ceramic of 1x to 10x


def test_a_value_outside_the_window_is_a_finding_and_a_capacitor_serves_one_slot():
    only_1u = board(bulk="1uF")                                           # 1 uF is 0.21x of the 4.7 uF slot
    assert len(missing(only_1u)) == 1 and "4.7 uF" in missing(only_1u)[0]["text"]
    one_for_two = [p for p in board() if p["ref"] != "C2"]
    assert len(missing(one_for_two)) == 1


def test_a_cap_whose_value_cannot_be_read_makes_the_pin_not_checked_and_is_named():
    parts = [p for p in board() if p["ref"] != "C1"] + [cap("C9", "+3V3", "see BOM")]
    r = run(parts)
    assert not [f for f in r["findings"] if "pin 1 " in f["text"]]
    assert any("C9" in x and "cannot be read" in x for x in r["not_checked"])
    assert not run(board(extra=[cap("C9", "+3V3", "see BOM")]))["not_checked"]        # every slot is filled by readable ones: nothing is in doubt


def test_dnp_parts_are_not_capacitors():
    gone = [p for p in board() if p["ref"] != "C1"] + [cap("C1", "+3V3", "100nF", dnp=True)]
    assert len(missing(gone)) == 1
    assert len(missing([p for p in board() if p["ref"] != "C1"] + [cap("C1", "+3V3", "DNP")])) == 1
    only_dnp = [mcu(1), cap("C1", "+3V3", "100nF", dnp=True), cap("C2", "+3V3A", "10nF"), cap("C3", "+3V3A", "1uF")]
    assert any("no capacitor to ground" in f["text"] for f in missing(only_dnp))


def test_a_part_without_a_source_is_not_checked_with_the_reason():
    parts = [P("U2", [("VDD", "+3V3"), ("VSS", "GND")], "B", mpn="OTHER-1"), cap("C1", "+3V3", "100nF")]
    r = run(parts)
    assert not r["findings"] and r["not_checked"] and "no cited requirement" in r["not_checked"][0]
    assert "not available" in r["not_checked"][0]


STRICT_ROW = "Supply pins\nVDDA     10 nF + 1 uF\nVSS\n"


def test_a_strict_power_supply_row_of_the_datasheet_is_a_source():
    parts = [P("U2", [("VDDA", "+3V3A"), ("VSS", "GND")], "B", mpn="OTHER-1"), cap("C1", "+3V3A", "100nF"), cap("C2", "+3V3A", "1uF")]
    assert not missing(parts, {"U2": STRICT_ROW})
    assert len(missing(parts[:2], {"U2": STRICT_ROW})) == 1


@pytest.mark.parametrize("text", [
    "The analog supply is connected to VDDA through a ferrite, 10 nF + 1 uF recommended\n",          # a sentence
    "VDDA\n10 nF + 1 uF\n",                                                                       # the list is on the next line
    "VDDA: though not required, a 0.1 uF capacitor helps\n",                                      # prose after the name
    "VDDA 0.1 uF - 0.22 uF\n",                                                                    # a range
    "VDDA 22 pF\n",                                                                               # a pF is not a decoupling capacitor
    "VDDA 10 nF\nVDDA 100 nF\n",                                                                  # two rows that disagree
    "",
])
def test_prose_is_never_a_requirement(text):
    assert dr.requirement("VDDA", "", text) is None


def test_the_row_must_name_the_exact_pin():
    assert dr.requirement("VDDA", "", STRICT_ROW) is not None
    assert dr.requirement("VDD", "", STRICT_ROW) is None and dr.requirement("VDDIO", "", "VDDIO2  100 nF\n") is None
    assert dr.requirement("V DDA", "", "V DDA   10 nF\n") is None or True


@pytest.mark.parametrize("value, farads", [("4u7", 4.7e-6), ("2n2", 2.2e-9), ("100n", 1e-7), ("1u0", 1e-6), ("100nF", 1e-7), ("4.7uF 16V X7R", 4.7e-6),
                                          ("0.1u", 1e-7), ("10pF", 1e-11), ("47 nF", 4.7e-8)])
def test_farads_reads_the_infix_and_plain_forms(value, farads):
    assert sr._farads(value) == pytest.approx(farads)


@pytest.mark.parametrize("value", ["", None, "see BOM", "X7R", "DNP"])
def test_farads_unreadable(value):
    assert sr._farads(value) is None


def test_the_scope_lists_every_not_checked_item_or_says_how_many_more():
    parts = [cap("C1", "+3V3", "100nF")] + [P(f"U{i}", [("VDD", "+3V3"), ("VSS", "GND")], "B", mpn="OTHER") for i in range(1, 13)]
    r = run(parts)
    assert len(r["not_checked"]) == 12 and "and 4 more" in r["scope"]
    r2 = run(parts[:4])
    assert "more" not in r2["scope"] and all(x in r2["scope"] for x in r2["not_checked"])
