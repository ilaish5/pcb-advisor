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
SOIC   DIP   QFN
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


# ---------------------------------------------------------------- review fixes: wrong passes and false mismatches

TWO = """\
{caption}
Pin Configuration and Functions
Table 1. Pin Functions
SOIC  VSSOP  NAME  DESCRIPTION
1     3      VIN   Input
2     4      GND   Ground
3     5      OUT   Output
4     6      EN    Enable
"""
SOIC_PINS = [("1", "VIN"), ("2", "GND"), ("3", "OUT"), ("4", "EN")]
VSSOP_PINS = [("3", "VIN"), ("4", "GND"), ("5", "OUT"), ("6", "EN")]


def test_a_figure_caption_above_the_heading_does_not_order_the_package_columns():
    # the caption names VSSOP first, the header row SOIC first: the old reading tied SOIC to VSSOP's column
    t = TWO.format(caption="DGK Package 8-lead VSSOP Top View")
    assert pintable.check([t], SOIC_PINS, "SOIC-8")["verify"] == "pass"
    assert pintable.check([t], VSSOP_PINS, "VSSOP-8")["verify"] == "pass"
    r = pintable.check([t], VSSOP_PINS, "SOIC-8")               # the VSSOP pinout on a SOIC part
    assert r["verify"] == "mismatch"


def test_package_names_in_a_caption_with_the_pin_word_leave_the_columns_untied():
    # "DGK Package 8-Pin VSSOP Top View" is itself taken for a heading: two lines name packages, nothing is tied to a column
    t = TWO.format(caption="DGK Package 8-Pin VSSOP Top View")
    for pins, pkg in ((VSSOP_PINS, "SOIC-8"), (SOIC_PINS, "SOIC-8"), (VSSOP_PINS, "VSSOP-8")):
        r = pintable.check([t], pins, pkg)
        assert r["verify"] != "pass" or pins is not VSSOP_PINS or pkg == "VSSOP-8", (pins, pkg)
    assert pintable.check([t], VSSOP_PINS, "SOIC-8")["verify"] != "pass"          # the exact wrong pass of the review
    t2 = TWO.replace("Table 1. Pin Functions", "DGK Package 8-Pin VSSOP Top View").format(caption="")
    assert pintable.check([t2], VSSOP_PINS, "SOIC-8")["verify"] != "pass"


def test_a_k1_tables_scope_is_not_taken_from_a_caption_above_the_heading():
    t = "D Package 8-lead SOIC Top View\nPin Functions\nPIN NAME TYPE\n1 VIN P Input\n2 GND G Ground\n3 OUT O Output\n"
    assert pintable.find_tables(t)[0]["labels"] == []
    assert pintable.check([t], [("1", "VIN"), ("2", "GND")], "VSSOP-8")["verify"] == "pass"   # not dropped for a caption


def test_the_description_never_names_a_pin():
    # "IN  Input from the VCC rail": VCC is in the description, not the name
    t = "X\nPin Functions\nPIN NAME DESCRIPTION\n1 IN Input from the VCC rail\n2 GND Ground\n3 OUT Output\n"
    assert not pintable.name_matches("VCC", "IN Input from the VCC rail")
    r = pintable.check([t], [("1", "VCC"), ("2", "GND"), ("3", "OUT")])
    assert r["verify"] == "unchecked" and "name cell" in r["issues"][0]
    assert pintable.check([t], [("1", "IN"), ("2", "GND"), ("3", "OUT")])["verify"] == "pass"
    cols = "X\nPin Functions\nPIN   NAME   DESCRIPTION\n1     IN     Input from the VCC rail\n2     GND    Ground\n3     OUT    Output\n"
    assert pintable.check([cols], [("1", "VCC"), ("2", "GND"), ("3", "OUT")])["verify"] == "mismatch"    # a column break isolates it


def test_joined_alternatives_and_a_parenthesised_name_still_match():
    assert pintable.name_matches("IO3", "/HOLD or /RESET (IO3)") and pintable.name_matches("HOLD", "/HOLD or /RESET (IO3)")
    assert pintable.name_matches("SWDIO", "PA13 (SWDIO)") and pintable.name_matches("SDA", "SDA / SDI")
    t = "W\nPin Functions\nPIN NAME I/O\n1 /CS I Chip select\n2 DO (IO1) I/O Data out\n7 /HOLD or /RESET (IO3) I/O Hold\n"
    assert pintable.check([t], [("1", "CS"), ("2", "IO1"), ("7", "IO3")])["verify"] == "pass"


EP8 = """\
X
Pin Functions
PIN NAME TYPE DESCRIPTION
1 VIN P Input
2 EN I Enable
3 FB I Feedback
4 GND G Ground
5 SW O Switch
6 PG O Power good
7 BOOT I Boot
8 OUT O Output
{ep}"""
EP_PINS = [("1", "VIN"), ("2", "EN"), ("3", "FB"), ("4", "GND"), ("5", "SW"), ("6", "PG"), ("7", "BOOT"), ("8", "OUT")]


def test_an_exposed_pad_in_the_netlist_is_the_thermal_pad_not_a_missing_pin():
    ep = EP8.format(ep="Thermal pad: connect to GND\n")
    for pad in ("9", "0", "EP"):
        assert pintable.check([ep], EP_PINS + [(pad, "GND")])["verify"] == "pass", pad
    assert pintable.check([ep], EP_PINS + [("9", "GND"), ("10", "GND")])["verify"] == "pass"       # EP split into 9 and 10
    assert pintable.check([ep], EP_PINS + [("9", "VSS")])["verify"] == "pass"
    r = pintable.check([ep], EP_PINS + [("9", "VIN")])          # a supply on the pad: not what the table allows, not a "none is 9"
    assert r["verify"] == "unchecked" and "none is" not in " ".join(r["issues"])


def test_an_exposed_pad_with_no_evidence_is_unchecked_never_a_mismatch():
    r = pintable.check([EP8.format(ep="")], EP_PINS + [("9", "GND")])
    assert r["verify"] == "unchecked" and "none is" not in " ".join(r["issues"]) and "exposed pad" in r["issues"][0]
    # the footprint's extra pad is the evidence
    r = pintable.check([EP8.format(ep="")], EP_PINS + [("9", "GND")], pads=[str(i) for i in range(1, 10)])
    assert r["verify"] == "pass"
    r = pintable.check([EP8.format(ep="")], EP_PINS + [("12", "GND")])                       # pin 12 of 8 is no exposed pad
    assert r["verify"] == "mismatch" and "none is 12" in r["issues"][0]


def test_a_numbered_exposed_pad_row_takes_ground_and_needs_no_footprint_pad():
    t = EP8.format(ep="9 EP Thermal pad, connect to GND\n")
    assert pintable.check([t], EP_PINS + [("9", "GND")], pads=[str(i) for i in range(1, 9)])["verify"] == "pass"
    assert pintable.check([t], EP_PINS + [("9", "VSS")])["verify"] == "pass"


def test_only_vcc_vdd_and_gnd_vss_are_taken_for_one_another():
    assert pintable.name_matches("VCC", "VDD") and pintable.name_matches("VDD", "VCC")
    assert pintable.name_matches("GND", "VSS") and pintable.name_matches("VSS", "GND") and pintable.name_matches("GND", "Ground")
    assert not pintable.name_matches("VIN", "VCC") and not pintable.name_matches("VIN", "VDD") and not pintable.name_matches("VCC", "VIN")
    assert not pintable.name_matches("AGND", "VSS") and not pintable.name_matches("VOUT", "VDD")


def test_clk_n_is_not_a_plain_clk_but_reset_n_is_a_reset():
    assert not pintable.name_matches("CLK_N", "CLK") and pintable.name_matches("CLK_N", "CLK_N") and pintable.name_matches("CLK_N", "CLK#")
    assert pintable.name_matches("RESET_N", "RESET") and pintable.name_matches("CS_N", "CS")
    t = "X\nPin Functions\nPIN NAME TYPE\n1 CLK I Clock\n2 GND G Ground\n3 OUT O Output\n"
    r = pintable.check([t], [("1", "CLK_N"), ("2", "GND"), ("3", "OUT")])
    assert r["verify"] == "unchecked" and "active-low mark" in r["issues"][0]


def test_a_matches_a_slash_pair_only_as_a_whole_alternative():
    # "A/B" is one pin with two functions: A is one of them; AB, A1 and B/C are not
    assert pintable.name_matches("A", "A/B") and pintable.name_matches("B", "A/B")
    assert not pintable.name_matches("A", "AB") and not pintable.name_matches("A", "A1") and not pintable.name_matches("A", "B/C")


def test_the_part_number_with_a_voltage_is_found_in_the_datasheet_of_its_base():
    import sources
    head = "AMS1117 1A LOW DROPOUT VOLTAGE REGULATOR  Fixed 1.5V 1.8V 2.5V 3.3V 5.0V"
    assert sources.mentions_part(head, "AMS1117-3.3") and sources.mentions_part(head, "AMS1117-5.0")
    assert not sources.mentions_part("AMS11175 regulator", "AMS1117-3.3")        # the cut would fall inside a digit run
    assert not sources.mentions_part("AMS1118 regulator", "AMS1117-3.3")
    assert not sources.mentions_part("74HC04 hex inverter", "74HC-595")          # a short family is not a base
    assert sources.mentions_part("NE555 timer", "NE555DR")


def test_a_pass_without_the_pin_table_method_is_not_verified_but_never_revokes_an_accept():
    line = {"refs": ["U1"], "key": "U1"}
    assert store.pins_status(line, {"verify": "pass", "method": "pin-table"})[0] == "verified"
    assert store.pins_status(line, {"verify": "pass"})[0] == "unverified"
    assert store.pins_status(line, {"verify": "pass", "accepted": True})[0] == "accepted"
    assert store.pins_status(line, {"verify": "pass", "pins_accepted": True})[0] == "accepted"
    assert store.ui_entry({"verify": "pass"})["verify"] == "unchecked"                  # the page offers Verify, not Accept
    assert store.ui_entry({"verify": "pass", "accepted": True})["verify"] == "pass"
    assert store.ui_entry({"verify": "pass", "method": "pin-table"})["verify"] == "pass"


def test_a_later_failed_verify_clears_the_old_method_and_evidence(empty):
    _ic(empty)
    _doc(empty, "LM1117IMPX.pdf", NE)
    assert verify_part.verify(empty, "U1")["verify"] == "pass"
    e = store.library_parts(empty)["U1"]
    assert e["method"] == "pin-table" and e["evidence"]
    _doc(empty, "LM1117IMPX.pdf", NE.replace("GND G Ground", "VIN I Input"))
    assert verify_part.verify(empty, "U1")["verify"] == "mismatch"
    e = store.library_parts(empty)["U1"]
    assert e["verify"] == "mismatch" and not e.get("method") and not e.get("evidence")
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "mismatch"


def test_the_library_page_offers_verify_for_a_legacy_pass(empty):
    _ic(empty)
    store.add_library(empty, "U1", {"symbol": True, "footprint": True, "verify": "pass"}, by="verify_part")      # an older pass
    row = {r["line"]: r for r in store.library_view(empty)}["U1"]
    assert row["verify"] == "unchecked" and not row["accepted"]
    store.add_library(empty, "U1", {"accepted": True}, by="student")
    row = {r["line"]: r for r in store.library_view(empty)}["U1"]
    assert row["verify"] == "pass" and row["accepted"]                  # the student's accept stays


# ---------------------------------------------------------------- second review: doubt is "unchecked", never pass

CODES = """\
{above}Pin Functions
{between}D    DGK   NAME   DESCRIPTION
1    3     VIN    Input
2    4     GND    Ground
3    5     OUT    Output
4    6     EN     Enable
"""
CAPTION = "Figure 3. DGK (VSSOP) and D (SOIC) Packages, Top View\n"


def test_a_caption_never_ties_the_columns_and_codes_in_the_header_tie_nothing():
    for t in (CODES.format(above=CAPTION, between=""), CODES.format(above="", between=CAPTION)):
        for pins in (VSSOP_PINS, SOIC_PINS):
            for pkg in ("SOIC-8", "VSSOP-8", ""):
                assert pintable.check([t], pins, pkg)["verify"] == "unchecked", (pins, pkg)      # D / DGK cannot be mapped for certain
    same = CODES.format(above=CAPTION, between="").replace("1    3 ", "1    1 ").replace("2    4 ", "2    2 ") \
        .replace("3    5 ", "3    3 ").replace("4    6 ", "4    4 ")
    assert pintable.check([same], SOIC_PINS, "SOIC-8")["verify"] == "pass"                    # the columns agree: no choice to make


def test_a_title_line_naming_packages_does_not_tie_the_columns():
    t = ("Pin Functions\nPin Functions for VSSOP and SOIC\nD    DGK   NAME   DESCRIPTION\n1    3     VIN    Input\n"
         "2    4     GND    Ground\n3    5     OUT    Output\n")
    assert pintable.check([t], [("1", "VIN"), ("2", "GND"), ("3", "OUT")], "VSSOP-8")["verify"] == "unchecked"
    assert pintable.check([t], [("3", "VIN"), ("4", "GND"), ("5", "OUT")], "VSSOP-8")["verify"] == "unchecked"


def test_only_the_pad_rows_own_name_cell_may_name_the_net_of_the_exposed_pad():
    t = EP8.format(ep="Thermal Pad — — Connect to GND. Do not connect to VIN or SW.\n")
    assert pintable.check([t], EP_PINS + [("9", "VIN")])["verify"] == "unchecked"     # a mention in the text beside the table does not count
    assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] == "unchecked"     # another net is named there: even a ground is not shown
    t = EP8.format(ep="9 EP Thermal pad, do not connect to VIN\n")                     # the description of the row neither
    assert pintable.check([t], EP_PINS + [("9", "VIN")])["verify"] != "pass"
    assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] != "pass"          # no "connect to GND" in the row
    t = EP8.format(ep="9 EP Thermal pad. Connect to GND.\n")
    assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] == "pass"
    for cell in ("PAD (VIN)", "EP/VIN"):                                              # the name cell itself names the net
        t = EP8.format(ep=f"9 {cell} P Pad\n")
        assert pintable.check([t], EP_PINS + [("9", "VIN")])["verify"] == "pass", cell
        assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] != "pass", cell      # the name cell names another net
    for cell in ("PAD (GND)", "PAD (VSS)", "EP/GND"):
        t = EP8.format(ep=f"9 {cell} P Pad\n")
        assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] == "pass", cell


def test_an_op_amps_pad_v_minus_is_no_ground():
    t = EP8.format(ep="9 PAD (V-) P Exposed pad\n")
    assert pintable.check([t], EP_PINS + [("9", "GND")])["verify"] != "pass"
    assert pintable.check([t], EP_PINS + [("9", "GND")], pads=[str(i) for i in range(1, 10)])["verify"] != "pass"
    assert pintable.check([t], EP_PINS + [("9", "V-")])["verify"] == "pass"
    t = EP8.format(ep="Thermal pad must be connected to V-\n")                         # a line of text about the pad
    for pins in (EP_PINS + [("9", "GND")], EP_PINS + [("0", "GND")]):
        assert pintable.check([t], pins)["verify"] != "pass"
        assert pintable.check([t], pins, pads=[str(i) for i in range(1, 10)] + ["0"])["verify"] != "pass"


def test_a_sot_223_tab_is_never_taken_for_ground():
    t = "LM1117\nPin Functions\nPIN NAME DESCRIPTION\n1 GND Ground\n2 VOUT Output\n3 VIN Input\n4 TAB Connected to VOUT\n"
    pins = [("1", "GND"), ("2", "VOUT"), ("3", "VIN")]
    assert pintable.check([t], pins + [("4", "GND")])["verify"] != "pass"
    assert pintable.check([t], pins + [("4", "VOUT")])["verify"] != "pass"           # named only in the description
    assert pintable.check([t], pins + [("4", "TAB")])["verify"] == "pass"
    named = t.replace("4 TAB Connected to VOUT", "4 TAB (VOUT) Heat sink")
    assert pintable.check([named], pins + [("4", "VOUT")])["verify"] == "pass"
    assert pintable.check([named], pins + [("4", "GND")])["verify"] != "pass"


def test_a_footprint_pad_alone_takes_a_ground_with_a_note_and_no_other_net():
    t = EP8.format(ep="")
    pads = [str(i) for i in range(1, 10)]
    r = pintable.check([t], EP_PINS + [("9", "GND")], pads=pads)
    assert r["verify"] == "pass" and "exposed pad" in r["notes"][0]
    assert pintable.check([t], EP_PINS + [("9", "VIN")], pads=pads)["verify"] == "unchecked"
    assert pintable.check([t], EP_PINS + [("9", "EP")], pads=pads)["verify"] == "unchecked"
    text = EP8.format(ep="Thermal pad: the pad is not electrically connected.\n")      # text about the pad that gives no net
    assert pintable.check([text], EP_PINS + [("9", "GND")], pads=pads)["verify"] != "pass"


def test_a_header_row_is_tabular_and_a_sentence_never_ties_the_columns():
    for between, under in (("The VSSOP and SOIC packages have no exposed pad.\n", ""), ("", "Numbering of VSSOP and SOIC\n")):
        t = f"Pin Functions\n{between}D    DGK   NAME   I/O\n{under}1    3     VIN    I\n2    4     GND    G\n3    5     OUT    O\n"
        for pins in ([("1", "VIN"), ("2", "GND"), ("3", "OUT")], [("3", "VIN"), ("4", "GND"), ("5", "OUT")]):
            for pkg in ("SOIC-8", "VSSOP-8"):
                assert pintable.check([t], pins, pkg)["verify"] != "pass", (between, under, pkg)
    # single-space plain text has no cells: the labels tie nothing
    plain = "Pin Functions\nPIN SOIC VSSOP NAME\n1 3 VIN\n2 4 GND\n3 5 OUT\n"
    assert pintable.check([plain], [("1", "VIN"), ("2", "GND"), ("3", "OUT")], "SOIC-8")["verify"] == "unchecked"
    assert pintable._header_labels("PIN   SOIC   VSSOP   NAME") == ["SOIC", "VSSOP"]
    assert pintable._header_labels("D    DGK   NAME   I/O") == []
    assert pintable._header_labels("Pin numbers of the SOIC and VSSOP") is None
    assert pintable._header_labels("name   no.") is None                              # printed in upper case
    # a column line directly above the rows that names nothing ties nothing; one that names the packages does
    t = "Pin Functions\nSOIC   VSSOP\n1   3   VIN\n2   4   GND\n3   5   OUT\n"
    assert pintable.check([t], [("1", "VIN"), ("2", "GND"), ("3", "OUT")], "SOIC-8")["verify"] == "pass"


SSD = """\
SSD1306 OLED driver
Pin Functions
PIN NAME TYPE DESCRIPTION
1 GND G Ground
2 VDD P Logic supply
3 VCC P Panel supply
4 SDA I/O Data
"""


def test_vcc_and_vdd_are_one_name_only_when_the_table_does_not_use_both():
    ok = [("1", "GND"), ("2", "VDD"), ("3", "VCC"), ("4", "SDA")]
    assert pintable.check([SSD], ok)["verify"] == "pass"
    r = pintable.check([SSD], [("1", "GND"), ("2", "VCC"), ("3", "VDD"), ("4", "SDA")])        # swapped: two different pins
    assert r["verify"] == "mismatch" and len(r["issues"]) == 2
    only_vdd = SSD.replace("3 VCC P Panel supply", "3 OUT O Output")
    assert pintable.check([only_vdd], [("1", "GND"), ("2", "VCC"), ("3", "OUT")])["verify"] == "pass"       # VDD on the table, VCC on the net
    only_vss = "X\nPin Functions\nPIN NAME\n1 VSS Ground\n2 VDD Supply\n3 OUT Output\n"
    assert pintable.check([only_vss], [("1", "GND"), ("2", "VCC"), ("3", "OUT")])["verify"] == "pass"
    both = only_vss.replace("3 OUT Output", "3 GND Ground")
    assert pintable.check([both], [("1", "GND"), ("2", "VCC"), ("3", "VSS")])["verify"] == "mismatch"


def test_a_leading_or_trailing_sign_is_one_form_but_plus_and_minus_stay_apart():
    assert pintable.name_matches("IN+", "+IN") and pintable.name_matches("+IN", "IN+")
    assert pintable.name_matches("IN-", "-IN") and pintable.name_matches("-IN", "IN-")
    assert not pintable.name_matches("IN+", "IN-") and not pintable.name_matches("IN+", "-IN") and not pintable.name_matches("IN-", "+IN")
    assert not pintable.name_matches("IN+", "IN") and not pintable.name_matches("IN-", "IN")
    t = "X\nPin Functions\nPIN NAME TYPE\n1 +IN I Non-inverting\n2 -IN I Inverting\n3 OUT O Output\n"
    assert pintable.check([t], [("1", "IN+"), ("2", "IN-"), ("3", "OUT")])["verify"] == "pass"
    assert pintable.check([t], [("1", "IN-"), ("2", "IN+"), ("3", "OUT")])["verify"] == "mismatch"


def test_a_footprint_pad_0_is_the_exposed_pad_in_the_pad_count():
    t = EP8.format(ep="Thermal pad: connect to GND\n")
    pads = [str(i) for i in range(1, 9)] + ["0"]
    assert pintable.check([t], EP_PINS, pads=pads)["verify"] == "pass"
    assert pintable.check([t], EP_PINS + [("0", "GND")], pads=pads)["verify"] == "pass"
    bare = EP8.format(ep="")                                              # no EP text: the footprint's pad 0 is the evidence
    assert pintable.check([bare], EP_PINS + [("0", "GND")], pads=pads)["verify"] == "pass"
    assert pintable.check([bare], EP_PINS + [("0", "GND")])["verify"] == "unchecked"
    assert pintable.check([bare], EP_PINS, pads=pads + ["10", "11"])["verify"] == "mismatch"
