"""R2 / W22: the tool's own schematic review: five rule classes, each with a defect and a clean twin; the scope is always stated."""
import schematic_review as sr


def P(ref, pins, kind=""):
    return {"ref": ref, "kind": kind, "pins": [{"num": str(i + 1), "name": n, "net": net} for i, (n, net) in enumerate(pins)]}


def cap(ref, net):
    return P(ref, [("1", net), ("2", "GND")])


def classes(parts):
    return {f["class"] for f in sr.review("x", parts=parts)["findings"]}


def test_decap_missing_and_clean():
    ic = P("U1", [("VDD", "3V3"), ("VDD", "3V3"), ("GND", "GND")])
    assert "decap_missing" in classes([ic])                          # a supply rail with no capacitor to ground at all
    assert "decap_missing" not in classes([ic, cap("C1", "3V3")])
    r = sr.review("x", parts=[ic, cap("C1", "3V3")])               # no datasheet text: what the pin asks is not known, so it is not checked
    assert r["not_checked"] and "datasheet" in r["not_checked"][0]


def test_i3c_device_on_shared_spi_bus():
    imu = P("U2", [("SCL", "CLK"), ("SDA", "SDI"), ("CS", "CS1")])
    flash = P("U3", [("SCK", "CLK"), ("DI", "SDI")])
    r = sr.review("x", parts=[imu, flash])
    f = [x for x in r["findings"] if x["class"] == "i3c_shared_spi"]
    assert f and f[0]["ref"] == "U2" and "U2" in f[0]["text"]
    assert "i3c_shared_spi" not in classes([P("U2", [("SCL", "SCL1"), ("SDA", "SDA1"), ("CS", "CS1")]), flash])


def test_open_drain_without_pullup():
    mcu = P("U1", [("SCL", "I2C_SCL")])
    assert "od_no_pullup" in classes([mcu])
    assert "od_no_pullup" not in classes([mcu, P("R1", [("1", "I2C_SCL"), ("2", "3V3")])])


def test_exposed_pad_not_ground():
    assert "ep_not_gnd" in classes([P("U1", [("EP", "3V3")])])
    assert "ep_not_gnd" not in classes([P("U1", [("EP", "GND")])])


def test_crystal_load_caps():
    y = P("Y1", [("1", "XI"), ("2", "XO")], kind="xtal")
    assert "xtal_no_caps" in classes([y, cap("C1", "XI")])
    assert "xtal_no_caps" not in classes([y, cap("C1", "XI"), cap("C2", "XO")])


def test_a_clean_sheet_never_says_zero_errors_and_always_states_scope():
    r = sr.review("x", parts=[P("U1", [("GND", "GND")])])
    assert not r["findings"] and "Scope:" in r["text"] and "0 errors" not in r["text"] and "Not checked" in r["text"]


def test_request_detection():
    assert sr.is_review_request("Review this sheet") and not sr.is_review_request("what is a decoupling cap")
