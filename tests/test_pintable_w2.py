"""pintable extensions of W2-B (ledger 13): each has a fixture in the layout text of a real module datasheet's pin table and a
"swapped pins still = mismatch" test. What could not be made reliable is not here (see the stream report)."""
import pintable

# a module-style table (layout text as `pypdf` / `pdftotext -layout` give it): a supply pin named 3V3, a ground pad in a number list
MODULE = """\
ESP32-C3-MINI-1 datasheet
Pin Definitions
Name        No.       Type      Function
GND         1, 2, 11, 14, 36-39   P     Ground
3V3         3         P         Power supply
EN          4         I         High: on; low: off
IO2         5         I/O/T     GPIO2, ADC1_CH2
IO3         6         I/O/T     GPIO3, ADC1_CH3
"""

NUMBER_FIRST = """\
Pin Description
No.  Name  Type  Function
1    GND   P     Ground
2    3V3   P     Power supply, 3.3 V
3    EN    I     Chip enable
4    IO2   I/O   General purpose I/O
"""
PINS = [("1", "GND"), ("2", "3V3"), ("3", "EN"), ("4", "IO2")]


def test_a_supply_pin_named_3v3_is_a_row_in_a_number_first_table():
    r = pintable.check([NUMBER_FIRST], PINS)
    assert r["verify"] == "pass", r["issues"]


def test_a_swapped_3v3_and_enable_is_still_a_mismatch():
    r = pintable.check([NUMBER_FIRST], [("1", "GND"), ("2", "EN"), ("3", "3V3"), ("4", "IO2")])
    assert r["verify"] == "mismatch"


def test_a_name_that_starts_with_a_digit_is_only_a_voltage_not_any_word():
    assert pintable.parse_number_first("2 3V3 P Power supply")["name"] == "3V3"
    assert pintable.parse_number_first("2 1V8 P Core supply")["name"] == "1V8"
    assert pintable.parse_number_first("2 3 inputs are tied together") is None


def test_a_cell_may_mix_numbers_and_ranges():
    row = pintable.parse_name_first("GND         1, 2, 11, 14, 36-39   P     Ground")
    assert row["nums"] == [["1", "2", "11", "14", "36", "37", "38", "39"]] and row["name"] == "GND"
    row = pintable.parse_number_first("1,2,11,14,36-39  GND  P  Ground")
    assert row["nums"] == [["1", "2", "11", "14", "36", "37", "38", "39"]]


def test_a_mixed_cell_ground_table_passes_and_a_swap_with_a_listed_pin_is_a_mismatch():
    pins = [("1", "GND"), ("2", "GND"), ("3", "3V3"), ("4", "EN"), ("5", "IO2"), ("6", "IO3"), ("11", "GND"), ("38", "GND")]
    r = pintable.check([MODULE], pins)
    assert r["verify"] == "pass", r["issues"]
    swapped = [("1", "GND"), ("2", "GND"), ("3", "EN"), ("4", "3V3"), ("5", "IO2"), ("6", "IO3")]
    assert pintable.check([MODULE], swapped)["verify"] == "mismatch"
    wrong_ground = [("1", "GND"), ("2", "GND"), ("3", "3V3"), ("4", "EN"), ("5", "IO2"), ("6", "IO3"), ("12", "GND")]
    assert pintable.check([MODULE], wrong_ground)["verify"] != "pass"      # pin 12 is not in the GND list
