"""Pin verification against a datasheet's pin TABLE (scripts/pintable.py, skills/verify_part.py): a number near a name in prose,
or in another row, proves nothing; the package decides the numbering column; a datasheet of another part, a pin count that
differs from the footprint and a symbol generated from the netlist itself are never "verified"."""
import json

import pintable
import store
import verify_part
from altium import bridge

NE = """\
LM1117 low dropout regulator
Pin Functions
PIN NAME TYPE DESCRIPTION
1 GND G Ground
2 VOUT O Output voltage
3 VIN I Input voltage
"""
PINS = [("1", "GND"), ("2", "VOUT"), ("3", "VIN")]


def test_a_correct_table_passes_and_notes_nothing():
    r = pintable.check([NE], PINS)
    assert r["verify"] == "pass" and not r["issues"]


def test_a_number_in_prose_does_not_pass():
    prose = ("The part has three pins. Pin 1 is connected to ground (GND) and pin 2 is the output (VOUT); "
             "tie pin 3 to VIN through a capacitor.\nThe GND pin 1 must see a solid plane.\n")
    r = pintable.check([prose], PINS)
    assert r["verify"] == "unchecked" and "no pin table" in r["issues"][0]


def test_a_neighbouring_row_does_not_pass():
    # the old check passed pin 3 GND: "3" is within 40 characters of GND in the row above/below
    r = pintable.check([NE], [("1", "GND"), ("2", "VOUT"), ("3", "GND")])
    assert r["verify"] == "mismatch" and "pin 3 GND" in r["issues"][0] and "VIN" in r["issues"][0]


def test_a_swapped_pair_names_both_pins():
    r = pintable.check([NE], [("1", "VIN"), ("2", "VOUT"), ("3", "GND")])
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2 and "puts VIN on pin 3" in r["issues"][0]


def test_a_short_name_is_the_tables_long_one():
    t = "NE555\nPin Functions\nPIN NAME\n1 GND Ground\n4 RESET Reset input\n8 VCC Supply\n"
    assert pintable.check([t], [("1", "GND"), ("4", "RST"), ("8", "VCC")])["verify"] == "pass"
    assert pintable.check([t], [("1", "GND"), ("4", "OUT"), ("8", "VCC")])["verify"] == "mismatch"


def test_a_pin_without_a_row_is_unchecked_not_wrong():
    t = "X\nPin Functions\nPIN NAME\n1 GND Ground\n2 VIN Supply\n5 OUT Output\n"      # 3 and 4 not read
    r = pintable.check([t], [("1", "GND"), ("4", "EN")])
    assert r["verify"] == "unchecked" and "pin 4 EN" in r["issues"][0]


def test_a_type_that_disagrees_is_a_note_not_a_mismatch():
    t = "X\nPin Functions\nPIN NAME TYPE\n1 GPIO3 I/O Signal\n2 VDD P Supply\n3 GND G Ground\n"
    r = pintable.check([t], [("1", "GPIO3"), ("2", "VDD"), ("3", "GND")])
    assert r["verify"] == "pass" and not r["notes"]
    r = pintable.check([t], [("1", "GND"), ("2", "VDD"), ("3", "GND")])
    assert r["verify"] == "mismatch"                        # GND on a GPIO3 row is a real conflict
    t2 = "X\nPin Functions\nPIN NAME TYPE\n1 GND I/O Signal\n2 VDD P Supply\n3 OUT O Output\n"
    r = pintable.check([t2], [("1", "GND"), ("2", "VDD"), ("3", "OUT")])
    assert r["verify"] == "pass" and "ground name" in r["notes"][0]


MULTI = """\
TPS7A47 regulator
Pin Description
Pin Number
SOIC DIP QFN
1 1 3 VIN Input
2 2 4 GND Ground
3 3 5 OUT Output
4 4 6 EN Enable
"""


def test_the_numbering_column_of_the_parts_package_is_used():
    assert pintable.check([MULTI], [("1", "VIN"), ("2", "GND"), ("3", "OUT"), ("4", "EN")], "SOIC-8")["verify"] == "pass"
    assert pintable.check([MULTI], [("3", "VIN"), ("4", "GND"), ("5", "OUT"), ("6", "EN")], "QFN-16")["verify"] == "pass"
    r = pintable.check([MULTI], [("1", "VIN"), ("2", "GND"), ("3", "OUT"), ("4", "EN")], "QFN-16")      # SOIC numbers on a QFN
    assert r["verify"] == "mismatch" and "VIN" in r["issues"][0]


def test_an_unknown_package_with_differing_columns_is_unchecked_never_pass():
    for pkg in ("", "0603", "MYSTERY"):
        r = pintable.check([MULTI], [("1", "VIN"), ("2", "GND"), ("3", "OUT"), ("4", "EN")], pkg)
        assert r["verify"] == "unchecked", pkg
        assert "different numbers" in r["issues"][0]


def test_an_unknown_package_is_fine_when_the_columns_agree():
    same = MULTI.replace("1 1 3 VIN", "1 1 1 VIN").replace("2 2 4 GND", "2 2 2 GND").replace("3 3 5 OUT", "3 3 3 OUT") \
        .replace("4 4 6 EN", "4 4 4 EN")
    assert pintable.check([same], [("1", "VIN"), ("2", "GND"), ("3", "OUT"), ("4", "EN")])["verify"] == "pass"


def test_the_footprints_pads_decide_the_column_when_the_package_text_does_not():
    # an IPC footprint name says nothing about SOIC/DIP/QFN, but its pads 3..6 are the QFN column
    r = pintable.check([MULTI], [("3", "VIN"), ("4", "GND"), ("5", "OUT"), ("6", "EN")], "QFN50P300X300X80-16N", pads=list("3456"))
    assert r["verify"] == "pass"


def test_the_pin_count_is_compared_with_the_footprint():
    t = "X\nPin Configuration SOIC-8\nPIN NAME\n" + "".join(f"{i} P{i} I/O sig\n" for i in range(1, 9))
    pins = [(str(i), f"P{i}") for i in range(1, 9)]
    assert pintable.check([t], pins, "SOIC-8", pads=[str(i) for i in range(1, 9)])["verify"] == "pass"
    r = pintable.check([t], pins, "SOIC-8", pads=[str(i) for i in range(1, 7)])
    assert r["verify"] == "mismatch" and "SOIC-8 lists 8 pins, the footprint has 6 pads" in r["issues"][0]
    assert pintable.check([t], pins, "SOIC-8", pads=[str(i) for i in range(1, 10)])["verify"] == "pass"   # 9th = exposed pad
    r = pintable.check([t], pins, "SOIC-8", pads=[str(i) for i in range(1, 9)] + ["10", "11"])
    assert r["verify"] == "mismatch"


def test_the_tables_of_other_packages_only_are_unchecked():
    t = "X\nPin Configuration QFN-16\nPIN NAME\n" + "".join(f"{i} P{i} I/O sig\n" for i in range(1, 5))
    r = pintable.check([t], [("1", "P1")], "SOIC-8")
    assert r["verify"] == "unchecked" and "QFN-16" in r["issues"][0]


def test_a_dot_leader_contents_line_is_not_a_table():
    toc = "Contents\n5 Pin Configuration and Functions........4\n6 Specifications...........5\n7 Detailed Description.....9\n"
    assert pintable.check([toc], [("5", "Pin")])["verify"] == "unchecked"


def test_a_name_first_table_reads_and_ignores_a_dash_type():
    t = ("TPS\nTable 5-1. Pin Functions\nPIN\nNAME NO. TYPE DESCRIPTION\n"
         "GND 7 — Ground\nOE 8 I Enable\nVCCA 1 — Supply\nVCCB 14 — Supply\nA1 2 I/O Signal\n")
    assert pintable.check([t], [("7", "GND"), ("8", "OE"), ("1", "VCCA")])["verify"] == "pass"
    assert pintable.check([t], [("7", "OE"), ("8", "GND")])["verify"] == "mismatch"


# ---------------------------------------------------------------- verify_part on a project

def _ic(empty, mpn="LM1117IMPX", pins=PINS, package="SOT-223"):
    store.propose_bom(empty, "U1", {"mpn": mpn, "refs": ["U1"], "package": package}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": n, "name": nm, "net": "N" + n} for n, nm in pins]}]}
    assert store.write_sheet(empty, "01", sheet)["ok"]


def _doc(empty, name, text):
    folder = store.pdir(empty) / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"%PDF-1.4 x")
    (folder / (name + ".txt")).write_text(text, encoding="utf-8")


def test_the_datasheet_of_another_part_is_unchecked(empty):
    _ic(empty)
    _doc(empty, "LM1117IMPX.pdf", NE.replace("LM1117", "TPS7A47"))       # named after the part, but about another one
    r = verify_part.verify(empty, "U1")
    assert r["verify"] == "unchecked" and "does not mention LM1117IMPX" in r["issues"]
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "unverified"


def test_the_family_name_on_the_front_page_is_enough(empty):
    _ic(empty)
    _doc(empty, "LM1117IMPX.pdf", NE)                                     # says LM1117, the MPN is LM1117IMPX
    r = verify_part.verify(empty, "U1")
    assert r["verify"] == "pass" and {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "verified"


def test_a_wrong_pin_is_a_mismatch_with_the_row_text(empty):
    _ic(empty, pins=[("1", "VIN"), ("2", "VOUT"), ("3", "GND")])
    _doc(empty, "LM1117IMPX.pdf", NE)
    r = verify_part.verify(empty, "U1")
    assert r["verify"] == "mismatch" and "pin 1 VIN" in r["issues"]
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "mismatch"


def test_the_pads_of_the_built_footprint_are_compared(empty):
    import partlib
    _ic(empty)
    _doc(empty, "LM1117IMPX.pdf", NE)
    lib = partlib.library_dir(empty)
    (lib / "build").mkdir(parents=True)
    (lib / "manifest.json").write_text(json.dumps({"U1": {"symbol": "S", "footprint": "FP", "source": "easyeda"}}), encoding="utf-8")
    (lib / "build" / "footprints_spec.txt").write_text("FOOTPRINT|FP|x\nPAD|1|0|0|0\nPAD|2|0|0|0\nTRACK|0|0|1|1\n", encoding="cp1252")
    r = verify_part.verify(empty, "U1")
    assert r["verify"] == "mismatch" and "lists 3 pins, the footprint has 2 pads" in r["issues"]


# ---------------------------------------------------------------- a generated symbol is no evidence

def _manifest(empty, source):
    import partlib
    lib = partlib.library_dir(empty)
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.json").write_text(json.dumps({"U1": {"symbol": "S", "footprint": "FP", "source": source}}), encoding="utf-8")


def test_a_generated_symbol_is_never_counted_as_verification(empty):
    _ic(empty)
    _manifest(empty, "generated")
    line = {l["key"]: l for l in store.bom(empty)}["U1"]
    assert line["pins_status"] == "unverified"               # symbol and netlist agree by construction: still unverified
    w = bridge.circular_pin_warnings(empty, ["U1"])
    assert len(w) == 1 and "UNVERIFIED" in w[0] and "proves nothing" in w[0]
    _manifest(empty, "easyeda")                              # an EasyEDA symbol is not built from the netlist
    assert bridge.circular_pin_warnings(empty, ["U1"]) == []
    _manifest(empty, "generated")
    _doc(empty, "LM1117IMPX.pdf", NE)
    assert verify_part.verify(empty, "U1")["verify"] == "pass"           # only the datasheet's table verifies it
    assert bridge.circular_pin_warnings(empty, ["U1"]) == []


def test_the_symbol_of_a_generated_part_is_marked_as_made_from_the_netlist():
    import partlib
    assert partlib.symbol_from_netlist({"source": "kicad"}) and partlib.symbol_from_netlist({"symbol_from": "netlist"})
    assert not partlib.symbol_from_netlist({"source": "easyeda"}) and not partlib.symbol_from_netlist(None)
