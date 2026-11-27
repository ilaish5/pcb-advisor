"""R2 / W22: the review's matching is by token and per supply pin; a 4-pin crystal is read, not skipped; the scope never claims more than ran."""
import schematic_review as sr


def P(ref, pins, kind=""):
    return {"ref": ref, "kind": kind, "pins": [{"num": str(i + 1), "name": n, "net": net} for i, (n, net) in enumerate(pins)]}


def cap(ref, net):
    return P(ref, [("1", net), ("2", "GND")])


def run(parts):
    return sr.review("x", parts=parts)


def classes(parts):
    return {f["class"] for f in run(parts)["findings"]}


def test_spi_sclk_is_not_an_i2c_scl_pin():
    spi_dev = P("U2", [("SPI_SCLK", "CLK"), ("SDA", "SDI"), ("CS", "CS1")])
    other = P("U3", [("SCK", "CLK"), ("DI", "SDI")])
    assert "i3c_shared_spi" not in classes([spi_dev, other])
    assert "i3c_shared_spi" in classes([P("U2", [("I2C_SCL", "CLK"), ("SDA", "SDI"), ("CS", "CS1")]), other])


def test_a_four_pin_crystal_without_load_caps_is_found_and_with_caps_is_clean():
    y = P("Y1", [("1", "XI"), ("2", "GND"), ("3", "XO"), ("4", "GND")], kind="xtal")
    f = [x for x in run([y])["findings"] if x["class"] == "xtal_no_caps"]
    assert f and "XI" in f[0]["text"] and "XO" in f[0]["text"]
    assert "xtal_no_caps" not in classes([y, cap("C1", "XI"), cap("C2", "XO")])


def test_a_crystal_it_cannot_read_is_named_in_the_scope_not_claimed():
    y = P("Y2", [("1", "XI"), ("2", "XO"), ("3", "VDD")], kind="xtal")
    r = run([y])
    assert "Y2" in r["scope"] and "could not read" in r["scope"]


def test_decap_count_is_per_supply_pin_across_all_ics_on_the_rail():
    a = P("U1", [("VDD", "3V3"), ("GND", "GND")])
    b = P("U2", [("VDD", "3V3"), ("GND", "GND")])
    assert "decap_missing" in classes([a, b, cap("C1", "3V3")])             # one cap for two supply pins
    assert "decap_missing" not in classes([a, b, cap("C1", "3V3"), cap("C2", "3V3")])


def test_vdda_vref_shared_pin_needs_its_decap():
    u = P("U1", [("VDD", "+3V3"), ("VDDA/VREF+", "+3V3"), ("VSS", "GND")])
    assert "decap_missing" in classes([u, cap("C1", "+3V3")])
    assert "decap_missing" in classes([u, cap("C1", "+3V3"), cap("C2", "+3V3")])      # the analog pin asks two, the digital pin one
    assert "decap_missing" not in classes([u, cap("C1", "+3V3"), cap("C2", "+3V3"), cap("C3", "+3V3")])


def vcap(ref, net, value, section="B"):
    return dict(cap(ref, net), value=value, section=section)


def _mcu():
    return dict(P("U1", [("VDD", "+3V3"), ("VDD", "+3V3"), ("VDDA/VREF+", "+3V3"), ("VSS", "GND")]), section="B")


def test_the_analog_pin_asks_a_10nf_and_a_1uf_of_its_own_and_a_spare_bulk_cap_does_not_stand_in():
    ok = [_mcu(), vcap("C1", "+3V3", "100nF"), vcap("C2", "+3V3", "100nF"), vcap("C3", "+3V3", "10nF"), vcap("C4", "+3V3", "1uF")]
    assert "decap_missing" not in classes(ok)
    assert "decap_missing" in classes([c for c in ok if c["ref"] != "C3"] + [vcap("C9", "+3V3", "470uF")])
    assert "decap_missing" in classes([c for c in ok if c["ref"] not in ("C3", "C4")])


def test_caps_of_another_sheet_area_do_not_serve_the_pin():
    parts = [_mcu(), vcap("C1", "+3V3", "100nF"), vcap("C2", "+3V3", "100nF"), vcap("C3", "+3V3", "10nF", "E"), vcap("C4", "+3V3", "1uF", "E")]
    assert "decap_missing" in classes(parts)
