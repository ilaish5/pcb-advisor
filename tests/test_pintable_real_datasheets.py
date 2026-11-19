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
    # the SRL and SRP columns give 0 and 1 to several rows: they are no pin numbering
    assert all(c["index"] == 2 for t in pintable.find_tables(status) for c in pintable._columns(t))
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


# ---------------------------------------------------------------- review of b0d80c6: no new false pass, no hidden swap

def test_a_function_named_first_never_passes_a_swapped_pin():
    t = "X\nPin Functions\nPIN NAME\n10 PA0 (TIM2_CH1) I/O\n15 PA5 (TIM2_CH1) I/O\n16 GND Ground\n"
    r = pintable.check([t], [("10", "TIM2_CH1/PA5"), ("15", "TIM2_CH1/PA0"), ("16", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2
    t = "X\nPin Functions\nPIN NAME\n1 PA2 (USART2_TX) I/O\n2 PA3 (USART2_RX) I/O\n3 GND Ground\n"
    r = pintable.check([t], [("1", "USART2_TX/PA3"), ("2", "USART2_RX/PA2"), ("3", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2
    assert pintable.check([t], [("1", "USART2_TX/PA2"), ("2", "USART2_RX/PA3"), ("3", "GND")])["verify"] == "pass"


def test_the_two_sides_of_a_pair_are_never_one_spelling():
    for a, b in [("USB_D+", "USB_DM"), ("XTAL_O", "XTAL_IN"), ("LED_R", "LED_G"), ("CS_N", "CS_P"), ("SPI_MISO", "SPI_MOSI"),
                 ("UART_TX", "UART_RX"), ("SEL_A", "SEL_B"), ("LVL_H", "LVL_L")]:
        assert not pintable._near(a, b), (a, b)
    assert pintable._near("VREG_IN", "VREG_VIN") and pintable._near("QSPI_SS", "QSPI_CSn")


def test_a_swapped_usb_pair_or_crystal_pair_is_a_mismatch():
    t = "X\nPin Functions\nPIN NAME\n1 VBUS Supply\n2 USB_DM I/O\n3 USB_DP I/O\n4 GND Ground\n"
    r = pintable.check([t], [("1", "VBUS"), ("2", "USB_D+"), ("3", "USB_D-"), ("4", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2
    t = "X\nPin Functions\nPIN NAME\n1 VDD Supply\n2 XTAL_IN I\n3 XTAL_OUT O\n4 GND Ground\n"
    r = pintable.check([t], [("1", "VDD"), ("2", "XTAL_O"), ("3", "XTAL_I"), ("4", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2


def test_a_name_near_two_rows_is_no_spelling():
    t = "X\nPin Functions\nPIN NAME\n1 VDD Supply\n2 VREG_VIN P\n3 VREG_INX P\n4 GND Ground\n"
    r = pintable.check([t], [("1", "VDD"), ("2", "VREG_IN"), ("4", "GND")])
    assert r["verify"] == "mismatch"


def test_a_column_that_bonds_several_pins_to_one_is_dropped_not_the_table():
    t = ("X\nPin Functions\nPIN NUMBER  NAME\n"
         "1  1  1  VDD Supply\n2  2  1  PA0 I/O\n3  3  1  PA1 I/O\n4  4  2  GND Ground\n5  5  3  PA2 I/O\n6  6  4  PA3 I/O\n")
    tables = pintable.find_tables(t)
    assert tables and [c["index"] for c in pintable._columns(tables[0])] == [0, 1]
    pins = [("1", "VDD"), ("2", "PA0"), ("3", "PA1"), ("4", "GND"), ("5", "PA2"), ("6", "PA3")]
    assert pintable.check([t], pins)["verify"] == "pass"


def test_a_pin_overview_with_io_mux_columns_is_a_pinout():
    t = ("ESP32-C3\nTable 2-1. Pin Overview\n"
         "No.  Name          Type  F0          F1         F2\n"
         "1    LNA_IN        I/O\n"
         "2    VDD3P3        P\n"
         "3    VDD3P3        P\n"
         "4    XTAL_32K_P    I/O   GPIO0       GPIO0\n"
         "5    XTAL_32K_N    I/O   GPIO1       GPIO1\n"
         "6    GPIO2         I/O   GPIO2       FSPIQ\n")
    pins = [("1", "LNA_IN"), ("2", "VDD3P3"), ("3", "VDD3P3"), ("4", "XTAL_32K_P"), ("5", "XTAL_32K_N"), ("6", "GPIO2")]
    assert pintable.check([t], pins)["verify"] == "pass"
    assert pintable.check([t], _swap(pins, "XTAL_32K_P", "XTAL_32K_N"))["verify"] == "mismatch"


def test_a_complete_table_of_the_parts_package_keeps_its_mismatch():
    t = "X\nPin Configuration SOIC-8\nPIN NAME\n" + "".join(f"{i} P{i} I/O sig\n" for i in range(1, 9))
    r = pintable.check([t], [(str(i), f"P{i}") for i in range(1, 15)], "SOIC-8")         # 14 symbol pins, 8-pin table
    assert r["verify"] == "mismatch" and "none is 9" in " ".join(r["issues"])
    r = pintable.check([t], [("1", "VCC"), ("2", "GND"), ("3", "OUT"), ("4", "P4")], "SOIC-8")   # 1 of 4 names in the table
    assert r["verify"] == "mismatch"


def test_package_families_are_read_in_any_case_but_short_words_only_as_printed():
    assert pintable.package_labels("Sot-23") == ["SOT-23"]
    assert pintable.package_labels("sot-23-5 package") == ["SOT-23-5"]
    assert pintable.package_labels("tssop-20") == ["TSSOP-20"]
    assert pintable.package_labels("connect to 3 V") == [] and pintable.package_labels("so 8 pins") == []
    assert pintable.package_labels("SO-8") == ["SO-8"]


# ---------------------------------------------------------------- re-review of 76edae5

def test_a_pair_side_spelt_with_a_sign_or_a_letter_is_one_name():
    assert pintable.name_matches("USB_D-", "USB_DM") and pintable.name_matches("USB_D+", "USB_DP")
    assert pintable.name_matches("USB_DN", "USB_D-") and pintable.name_matches("CLK+", "CLKP") and pintable.name_matches("CLK-", "CLK_N")
    assert not pintable.name_matches("USB_D+", "USB_DM") and not pintable.name_matches("CLK+", "CLKN")
    t = "X\nPin Functions\nPIN NAME\n1 VBUS Supply\n2 USB_DM I/O\n3 USB_DP I/O\n4 GND Ground\n"
    assert pintable.check([t], [("1", "VBUS"), ("2", "USB_D-"), ("3", "USB_D+"), ("4", "GND")])["verify"] == "pass"
    r = pintable.check([t], [("1", "VBUS"), ("2", "USB_D+"), ("3", "USB_D-"), ("4", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2


LDO_VARIANTS = """\
TPS7A
Table 4-1. Pin Functions
PIN
NAME  NO.  I/O  DESCRIPTION
OUT   1    O    Regulated output
GND   2    —    Ground
EN    3    I    Enable input
NR    4    —    Noise-reduction pin, fixed version only
FB    4    I    Feedback input, adjustable version only
IN    5    I    Input supply
"""


def test_variant_rows_of_one_pin_are_a_pinout_and_either_reading_passes():
    fixed = [("1", "OUT"), ("2", "GND"), ("3", "EN"), ("4", "NR"), ("5", "IN")]
    adj = [("1", "OUT"), ("2", "GND"), ("3", "EN"), ("4", "FB"), ("5", "IN")]
    assert pintable.check([LDO_VARIANTS], fixed, pads=list("12345"))["verify"] == "pass"
    assert pintable.check([LDO_VARIANTS], adj, pads=list("12345"))["verify"] == "pass"
    r = pintable.check([LDO_VARIANTS], [("1", "OUT"), ("2", "GND"), ("3", "EN"), ("4", "IN"), ("5", "FB")])
    assert r["verify"] == "mismatch"
    plain = LDO_VARIANTS.replace(", fixed version only", "").replace(", adjustable version only", "")
    assert pintable.check([plain], fixed)["verify"] == "unchecked"            # one number twice without a variant word


def test_a_dropped_package_column_is_named_in_the_reason():
    t = ("STM32G0\nTable 12. Pin definitions\n"
         "PIN NUMBER  PIN NAME\n"
         "LQFP32  TSSOP20  SO8  PIN NAME\n"
         "1  1  1  PB9 I/O\n2  2  1  PC14 I/O\n3  3  2  VDD Supply\n4  4  3  VSS Ground\n5  5  4  NRST I/O\n6  6  5  PA0 I/O\n")
    r = pintable.check([t], [("1", "PB9"), ("2", "VDD"), ("3", "VSS")], "SO-8")
    assert r["verify"] == "unchecked"
    assert "SO-8 column" in r["issues"][0] and "bonded" in r["issues"][0]
