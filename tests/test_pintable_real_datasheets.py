"""The pin check on text cut from real datasheets (tests/fixtures/datasheet_text, extracted by scripts/sources.py from the LCSC
PDFs of an RP2040 sensor board). Each case was a false answer once: a GPIO function-select table read as the RP2040 pinout
(pin 1 IOVDD "is" SPI0), a status-register truth table taken as the W25Q16JV pin table with pins 2..8 called an exposed pad,
SOT-25-5 not taken for SOT25, and "Connect to" read as a TO package. Any doubt is "unchecked", never a conflict; a real swap
still is one."""
import pathlib

import pintable

FX = pathlib.Path(__file__).resolve().parent / "fixtures" / "datasheet_text"


def _text(name):
    return (FX / name).read_text(encoding="utf-8")


RP2040 = [("1", "IOVDD"), ("10", "IOVDD"), ("22", "IOVDD"), ("33", "IOVDD"), ("42", "IOVDD"), ("49", "IOVDD"), ("23", "DVDD"),
          ("50", "DVDD"), ("45", "VREG_VOUT"), ("44", "VREG_IN"), ("48", "USB_VDD"), ("43", "ADC_AVDD"), ("57", "GND"),
          ("19", "TESTEN"), ("26", "RUN"), ("47", "USB_DP"), ("46", "USB_DM"), ("20", "XIN"), ("21", "XOUT"), ("24", "SWCLK"),
          ("25", "SWD"), ("56", "QSPI_SS"), ("55", "QSPI_SD1"), ("54", "QSPI_SD2"), ("53", "QSPI_SD0"), ("52", "QSPI_SCLK"),
          ("51", "QSPI_SD3"), ("6", "GPIO4"), ("7", "GPIO5"), ("37", "GPIO25")]
W25Q = [("1", "~{CS}"), ("2", "DO/IO1"), ("3", "~{WP}/IO2"), ("4", "GND"), ("5", "DI/IO0"), ("6", "CLK"),
        ("7", "~{HOLD}/~{RESET}/IO3"), ("8", "VCC")]
AP2112 = [("1", "VIN"), ("2", "GND"), ("3", "EN"), ("4", "NC"), ("5", "VOUT")]
BME280 = [("1", "GND"), ("2", "CSB"), ("3", "SDI"), ("4", "SCK"), ("5", "SDO"), ("6", "VDDIO"), ("7", "GND"), ("8", "VDD")]
PADS8 = [str(i) for i in range(1, 9)]


def _swap(pins, a, b):
    return [(n, {a: b, b: a}.get(m, m)) for n, m in pins]


# ---------------------------------------------------------------- RP2040: a function-select table is not the pinout

def test_the_gpio_function_select_table_is_never_the_pinout():
    layout = _text("rp2040_gpio_functions.layout.txt")
    assert pintable.find_tables(layout) == []               # GPIO F1..F9: GPIO numbers and peripheral functions
    r = pintable.check([layout], RP2040, "LQFN-56(7x7)", pads=[str(i) for i in range(1, 58)])
    assert r["verify"] == "unchecked" and not any("SPI0" in i for i in r["issues"])


def test_the_rp2040_pin_list_never_conflicts_on_a_spelling():
    # the real pin list (Tables 620..626) is in the plain text only; the netlist spells two names its own way
    r = pintable.check([_text("rp2040_gpio_functions.layout.txt"), _text("rp2040_pin_list.txt")], RP2040, "LQFN-56(7x7)")
    assert r["verify"] == "unchecked"
    assert "pin 44 VREG_IN: the datasheet calls pin 44 VREG_VIN, which may be another spelling" in r["issues"][0]
    assert "QSPI_CSn" in r["issues"][0] and "split over several tables" in r["issues"][0]


def test_a_spelling_is_not_a_different_pin_but_a_different_name_is():
    assert pintable._near("VREG_IN", "VREG_VIN") and pintable._near("QSPI_SS", "QSPI_CSn")
    assert not pintable._near("GPIO3", "GPIO4") and not pintable._near("OUT", "RESET") and not pintable._near("GND", "VIN")
    assert not pintable._near("QSPI_SD1", "QSPI_SD2")


# ---------------------------------------------------------------- W25Q16JV: SOIC 150/208-mil, a truth table, an exposed pad

def test_a_size_in_mils_shared_by_two_bodies_is_no_pin_count():
    assert pintable.package_labels("Pin Description SOIC 150/208-mil, WSON 6x5-mm") == ["SOIC", "WSON"]


def test_the_w25q16jv_pin_table_passes_with_altium_overbars_and_alternatives():
    text = _text("w25q16jv_pin_description.layout.txt") + "\n" + _text("w25q16jv_status_protect.layout.txt")
    r = pintable.check([text], W25Q, "SOIC-8", pads=PADS8)
    assert r["verify"] == "pass", r
    assert pintable.check([text], W25Q, "SOIC-8")["verify"] == "pass"


def test_a_swapped_flash_pin_pair_is_still_a_mismatch():
    text = _text("w25q16jv_pin_description.layout.txt")
    r = pintable.check([text], _swap(W25Q, "CLK", "GND"), "SOIC-8", pads=PADS8)
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2 and "puts CLK on pin 6" in r["issues"][0]


def test_a_status_register_truth_table_is_not_a_pin_table():
    status = _text("w25q16jv_status_protect.layout.txt")
    assert pintable.find_tables(status) == []                # SRL/SRP columns give 0 and 1 to several rows
    r = pintable.check([status], W25Q, "SOIC-8", pads=PADS8)
    assert r["verify"] == "unchecked" and not any("exposed pad" in i for i in r["issues"])


def test_a_short_table_never_makes_most_pins_an_exposed_pad():
    t = "X\nPin Functions\nPIN NAME\n1 CS Chip select\n2 DO Data out\n"
    col = pintable._columns(pintable.find_tables(t)[0])[0]
    out = pintable._evaluate(col, [("1", "CS"), ("2", "DO"), ("3", "WP"), ("4", "GND"), ("5", "DI")], None)
    assert not any("exposed pad" in a for a in out["absent"] + out["notes"]) and out["conflict"] == []


def test_more_pins_than_a_short_complete_table_is_unchecked_not_a_conflict():
    t = "X\nPin Functions\nPIN NAME\n1 A In\n2 B In\n3 C In\n4 D In\n"
    r = pintable.check([t], [(str(i), n) for i, n in enumerate("ABCDEFGH", 1)])
    assert r["verify"] == "unchecked" and "cut short" in r["issues"][0]


def test_a_table_of_another_package_is_not_read_again_from_the_plain_text():
    rows = "1 VIN Supply\n2 GND Ground\n3 OUT Output\n4 EN Enable\n"
    layout = "X\nPin Configuration QFN-16\nPIN NAME\n" + rows
    plain = "X\nPin Functions\nPIN NAME\n" + rows
    r = pintable.check([layout, plain], [("1", "GND"), ("2", "VIN"), ("3", "OUT"), ("4", "EN")], "SOIC-8")
    assert r["verify"] == "unchecked" and "QFN-16" in r["issues"][0]


def test_a_netlist_name_with_functions_matches_only_by_its_first():
    t = "X\nPin Functions\nPIN NAME\n10 PA0 (TIM2_CH1) I/O\n15 PA5 (TIM2_CH1) I/O\n16 GND Ground\n"
    assert pintable.check([t], [("10", "PA0/TIM2_CH1"), ("15", "PA5/TIM2_CH1"), ("16", "GND")])["verify"] == "pass"
    assert pintable.check([t], [("10", "PA5/TIM2_CH1"), ("15", "PA0/TIM2_CH1"), ("16", "GND")])["verify"] == "mismatch"


# ---------------------------------------------------------------- AP2112: SOT-25-5 is SOT25; untied columns stay unchecked

def test_sot_25_5_is_sot25_but_not_any_five_pin_package():
    assert pintable.package_relation("SOT25", "SOT-25-5") == "exact"
    assert pintable.package_relation("SOT-23-5", "SOT-25-5") == "exact"
    assert pintable.package_relation("SOT-89-5", "SOT-25-5") == ""
    assert pintable.package_relation("SOT-26", "SOT-25-5") == ""


def test_the_ap2112_table_is_unchecked_not_a_package_mismatch():
    text = _text("ap2112_pin_descriptions.layout.txt")
    for pads in (None, list("12345")):
        r = pintable.check([text], AP2112, "SOT-25-5", pads=pads)
        assert r["verify"] == "unchecked", r
        assert "the package of this part is" not in r["issues"][0] and "SOT-25" in r["issues"][0]


def test_the_sot89_column_is_never_used_for_a_sot25_part():
    text = _text("ap2112_pin_descriptions.layout.txt")
    r = pintable.check([text], [("4", "VIN"), ("2", "GND"), ("5", "VOUT")], "SOT-25-5")     # SOT89-5 numbering
    assert r["verify"] != "pass"


# ---------------------------------------------------------------- BME280: "Connect to" is not a TO package

def test_words_of_a_sentence_are_not_packages():
    assert pintable.package_labels("Pin Name I/O Type Description Connect to") == []
    assert pintable.package_labels("so that the pins") == []
    assert pintable.package_labels("TO-220") == ["TO-220"] and pintable.package_labels("SC-70") == ["SC-70"]


def test_the_bme280_pin_table_passes_and_a_swap_conflicts():
    text = _text("bme280_pin_description.layout.txt")
    assert pintable.check([text], BME280, "LGA-8(2.5x2.5)", pads=PADS8)["verify"] == "pass"
    r = pintable.check([text], _swap(BME280, "SDI", "SDO"), "LGA-8(2.5x2.5)")
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2
