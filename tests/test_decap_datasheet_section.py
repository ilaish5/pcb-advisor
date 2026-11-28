"""R2 / W22: the decoupling requirement of a supply pin is read from the part's OWN datasheet text, scoped to its power-supply section (table rows, figure
values under a pin's label, notes that tie a value to a named pin). Outside the section, prose never counts. A missing capacitor of a stated value is
`decap_missing` on that pin; one value stated for a pin is enforced and the pin's other slots are reported as not read. The datasheets below are written
for these tests (a synthetic part in the style of a power-supply table and a decoupling figure)."""
import random

import pytest

import decap_requirements as dr
import schematic_review as sr

TABLE_DS = """Features
The device is supplied through the VDD pins. VDDA is connected to VDD in the simplest case.
5. Power supply
5.1 Power supply scheme
Table 4. Decoupling capacitors per supply pin
Supply pin Capacitor Remark
VDD 100 nF + 4.7 uF each pin
VDDA 10 nF + 1 uF analog
VDDIO 100 nF each pin
6. Electrical characteristics
VBAT 1 uF // 220 nF is mentioned in an unrelated table
"""
FIGURE_DS = """4.2 Power supply decoupling
Figure 9. Power supply and reference decoupling
VREF+
MCUX
VDDA
VSSA/VREF-
1 uF // 10 nF
1 uF // 10 nF
ai0001
1. The 4.7 uF ceramic capacitor must be connected to one of the VDD pins.
6.3 Temperature sensor characteristics
"""
NOTE_DS = """3.3 Power supply scheme
Each VDD pin is decoupled with a 100 nF ceramic capacitor per VDD pin. The VDDA pin is connected to VDD.
7. Package information
"""


def P(ref, pins, **kw):
    return dict({"ref": ref, "section": "A", "pins": [{"num": str(i + 1), "name": n, "net": net} for i, (n, net) in enumerate(pins)]}, **kw)


def cap(ref, net, value):
    return dict(P(ref, [("1", net), ("2", "GND")]), value=value)


def test_sections_are_found_by_heading_and_a_contents_line_is_not_one():
    toc = "3.14 Power supply schemes . . . . . . . . . . . . . . . . 20\n"
    assert dr.sections(toc) == []
    assert [h for h, _ in dr.sections(TABLE_DS)] == [3]


def test_table_rows_figure_values_and_notes_are_read_in_the_section():
    v = dr.requirement("VDDA", "", TABLE_DS)
    assert sorted(s["farads"] for s in v["schemes"][0]["per_pin"]) == [pytest.approx(1e-8), pytest.approx(1e-6)] and not v["partial"]
    vd = dr.requirement("VDD", "", TABLE_DS)["schemes"][0]
    assert sorted(s["farads"] for s in vd["per_pin"]) == [pytest.approx(1e-7), pytest.approx(4.7e-6)]
    f = dr.requirement("VDDA/VREF+", "", FIGURE_DS)
    assert sorted(s["farads"] for s in f["schemes"][0]["per_pin"]) == [pytest.approx(1e-8), pytest.approx(1e-6)]
    n = dr.requirement("VDD_2", "", FIGURE_DS)
    assert n["partial"] and n["schemes"][0]["per_device"][0]["farads"] == pytest.approx(4.7e-6)         # one of the VDD pins: one for the part
    k = dr.requirement("VDD", "", NOTE_DS)
    assert k["partial"] and k["schemes"][0]["per_pin"][0]["farads"] == pytest.approx(1e-7)


@pytest.mark.parametrize("pin, text", [
    ("VDDA", "5. Power supply\nVREF+ is connected to VDDA.\n6. Next\n"),                                       # a pin tied to a pin
    ("VDDA", "5. Power supply\nThough not required, a 0.1 uF capacitor on VDDA may help.\n6. Next\n"),            # optional
    ("VDDA", "5. Power supply\nVDDA: decoupled with a 100 nF capacitor per VDDA pin, not required.\n6. Next\n"),
    ("VBAT", "5. Power supply\nVBAT\nVDD 100 nF + 4.7 uF\n6. Next\n"),                                          # the neighbour's row
    ("VDDA", "1. Features\nVDDA 10 nF + 1 uF\n2. Description\n"),                                               # outside a power-supply section
    ("VDDA", "5. Power supply\nVDDA 0.1 uF - 0.22 uF\n6. Next\n"),                                              # a range
    ("VDDA", "5. Power supply\nVDDA 22 pF\n6. Next\n"),                                                         # a pF value
    ("VDDA", "5. Power supply\nVDDA 10 nF\nVDDA 100 nF\n6. Next\n"),                                            # rows that disagree
    ("VDDA", ""),
])
def test_what_is_not_a_requirement(pin, text):
    assert dr.requirement(pin, "", text) is None


def test_the_found_value_is_enforced_and_the_rest_of_the_pin_is_reported_not_read():
    parts = [P("U1", [("VDD", "+3V3"), ("VSS", "GND")], mpn="X1")]
    r = sr.review("x", parts=parts + [cap("C1", "+3V3", "100nF")], datasheets={"U1": FIGURE_DS})
    assert [f for f in r["findings"] if f["class"] == "decap_missing" and "4.7 uF" in f["text"]]          # no 4.7 uF on the rail
    r2 = sr.review("x", parts=parts + [cap("C1", "+3V3", "100nF"), cap("C2", "+3V3", "4.7uF")], datasheets={"U1": FIGURE_DS})
    assert not [f for f in r2["findings"] if f["class"] == "decap_missing"]
    assert any("states one capacitor value" in x for x in r2["not_checked"])


SUPPLY = [("VDD", "+3V3", [1e-7, 4.7e-6]), ("VDDA", "+3V3A", [1e-8, 1e-6]), ("VDDIO", "+1V8", [1e-7])]


def synthetic(drop=None, style="table"):
    """A part with three supply pins on their own rails, a datasheet that states each pin's capacitors, and the capacitors the datasheet asks for."""
    mcu = P("U1", [(n, net) for n, net, _ in SUPPLY] + [("VSS", "GND")], mpn="SYN-MCU")
    ds = "5. Power supply\nTable 2. Decoupling per supply pin\nSupply pin Capacitors\n" + "\n".join(
        f"{n} " + " + ".join((f"{v * 1e9:g} nF" if v < 1e-6 else f"{v * 1e6:g} uF") for v in vals) for n, _, vals in SUPPLY) + "\n6. Package\n"
    if style == "figure":
        ds = "5. Power supply decoupling\n" + "\n".join(
            f"{n}\nGND\n" + " // ".join((f"{v * 1e9:g} nF" if v < 1e-6 else f"{v * 1e6:g} uF") for v in vals) for n, _, vals in SUPPLY) + "\n6. Package\n"
    caps, k = [], 0
    for n, net, vals in SUPPLY:
        for v in vals:
            k += 1
            caps.append((n, v, cap(f"C{k}", net, f"{v * 1e9:g}nF" if v < 1e-6 else f"{v * 1e6:g}uF")))
    parts = [mcu] + [c for n, v, c in caps if (n, v) != drop]
    return sr.review("x", parts=parts, datasheets={"U1": ds})


@pytest.mark.parametrize("style", ["table", "figure"])
def test_the_clean_twin_has_no_finding_and_every_injected_missing_capacitor_is_found_on_its_pin(style):
    assert not [f for f in synthetic(style=style)["findings"] if f["class"] == "decap_missing"]
    slots = [(n, v) for n, _, vals in SUPPLY for v in vals]
    random.Random(7).shuffle(slots)
    hit = 0
    for n, v in slots:
        found = [f for f in synthetic(drop=(n, v), style=style)["findings"] if f["class"] == "decap_missing"]
        assert len(found) == 1 and f"({n})" in found[0]["text"], (n, v, [f["text"] for f in found])
        hit += 1
    assert hit == len(slots) == 5
