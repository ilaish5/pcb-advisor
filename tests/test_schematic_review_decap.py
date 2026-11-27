"""R2 / W22: decoupling is read per supply pin from the part's OWN datasheet, matched by net, one capacitor per wanted slot; a requirement that cannot
be read is "not checked" with the reason, never a missing capacitor and never a family template."""
import pytest

import decap_requirements as dr
import schematic_review as sr

# the datasheet phrasings are written for these tests (not copied from any datasheet)
DS_ANALOG_PAIR = "Power supply\nVDDA\n1 uF // 10 nF\nThe 4.7 uF ceramic capacitor must be connected to one of the VDD pin.\n"
DS_TOTAL_LIST = "Supply VDD/VDDA\n1 x 100 nF\n+ 1 x 4.7 uF\nVSS\n"
DS_RANGE_ONLY = "VCC: decouple with a 0.1 uF - 0.22 uF capacitor\n"


def P(ref, pins, section=""):
    return {"ref": ref, "section": section, "pins": [{"num": str(i + 1), "name": n, "net": net} for i, (n, net) in enumerate(pins)]}


def cap(ref, net, value, section="B"):
    return dict(P(ref, [("1", net), ("2", "GND")], section), value=value)


MCU = P("U1", [("VBAT", "+3V3"), ("VDD", "+3V3"), ("VDD", "+3V3"), ("VDDA/VREF+", "+3V3"), ("VSS", "GND")], "B")
GOOD = [MCU, cap("C1", "+3V3", "10nF"), cap("C2", "+3V3", "1uF"), cap("C3", "+3V3", "4.7uF"), cap("C4", "+3V3", "100nF")]


def run(parts, ds=DS_ANALOG_PAIR):
    return sr.review("x", parts=parts, datasheets={"U1": ds})


def missing(parts, ds=DS_ANALOG_PAIR):
    return [f for f in run(parts, ds)["findings"] if f["class"] == "decap_missing"]


def test_the_requirement_is_read_from_the_datasheet_text():
    assert dr.requirement(DS_ANALOG_PAIR, "VDDA/VREF+")["values"] == [1e-6, 1e-8]
    assert dr.requirement(DS_ANALOG_PAIR, "VDD")["values"] == [4.7e-6]
    assert dr.requirement(DS_TOTAL_LIST, "VDD/VDDA")["values"] == [pytest.approx(1e-7), pytest.approx(4.7e-6)]
    assert dr.requirement("", "VDD") is None and dr.requirement(DS_RANGE_ONLY, "VCC") is None
    assert dr.requirement("a 10 nF capacitor is shown\nVDDA\n", "VDDA") is None          # one value near a name is prose


def test_a_board_with_every_slot_filled_is_clean_and_the_pins_it_cannot_read_are_listed_not_flagged():
    r = run(GOOD)
    assert not [f for f in r["findings"] if f["class"] == "decap_missing"]
    assert any("VBAT" in x for x in r["not_checked"])


def test_removing_the_10nf_or_the_1uf_of_the_analog_pin_is_found_and_the_vdd_bulk_never_stands_in():
    without = lambda ref: [p for p in GOOD if p["ref"] != ref]
    assert len(missing(without("C1"))) == 1 and "10 nF" in missing(without("C1"))[0]["text"]
    assert len(missing(without("C2"))) == 1 and "1 uF" in missing(without("C2"))[0]["text"]      # the 4.7 uF (C3) is the VDD pin's
    assert len(missing(without("C3"))) == 1 and "4.7 uF" in missing(without("C3"))[0]["text"]
    assert len(missing([p for p in GOOD if p["ref"] not in ("C1", "C2")])) == 2


def test_a_capacitor_serves_one_slot_only():
    two_pins = [MCU, P("U9", [("VDDA", "+3V3"), ("VSS", "GND")], "C"), cap("C1", "+3V3", "10nF"), cap("C2", "+3V3", "1uF"), cap("C3", "+3V3", "4.7uF")]
    r = sr.review("x", parts=two_pins, datasheets={"U1": DS_ANALOG_PAIR, "U9": DS_ANALOG_PAIR})
    assert len([f for f in r["findings"] if f["class"] == "decap_missing" and f["ref"] in ("U1", "U9")]) >= 2


def test_a_capacitor_in_another_sheet_section_serves_the_pin_because_the_net_is_the_same():
    far = [MCU] + [dict(c, section="E") for c in GOOD[1:]]
    assert missing(far) == []


def test_an_unreadable_requirement_is_not_checked_with_the_reason_never_missing():
    for ds in ("", DS_RANGE_ONLY, None):
        r = run(GOOD, ds)
        assert not [f for f in r["findings"] if f["class"] == "decap_missing"], ds
        assert r["not_checked"] and "datasheet" in r["not_checked"][0]
        assert "not checked" in r["scope"]


def test_a_rail_with_no_capacitor_to_ground_at_all_is_missing_without_any_datasheet():
    r = sr.review("x", parts=[MCU], datasheets={})
    assert [f["class"] for f in r["findings"]].count("decap_missing") >= 1


def test_the_requirement_is_the_parts_own_not_a_family_template():
    # a G030-style datasheet asks 100 nF + 4.7 uF at VDD/VDDA; no 10 nF is wanted, so a board that has those two is clean
    mcu = P("U1", [("VDD/VDDA", "+3V3"), ("VSS", "GND")], "B")
    parts = [mcu, cap("C1", "+3V3", "100nF"), cap("C2", "+3V3", "4.7uF")]
    assert missing(parts, DS_TOTAL_LIST) == []
    assert len(missing([parts[0], parts[1]], DS_TOTAL_LIST)) == 1
