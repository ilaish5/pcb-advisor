"""
Import BOM from Altium (scripts/bom_import.py and what it touches):
- reading BOM CSVs the way Altium and a hand-made sheet write them (encodings, delimiters, headers)
- the comparison of CSV, schematic and PcbDoc: what is a finding, and how bad
- apply: one bom-log event per line, into an empty BOM only, the source files never changed
- finding the CSV, and which paths a request from the browser may name
- the declared LCSC code (export, availability check, jlc lookup, a later MPN edit)
- the HTTP endpoints, the command line and the UI wiring
"""
import hashlib
import json
import os
import pathlib
import shutil
import threading
import urllib.error
import urllib.request

import pytest

import bom_import
import check_availability
import export_bom
import jlc
import project
import store
from ui_source import ui_all

REPO = pathlib.Path(__file__).resolve().parent.parent
FX = REPO / "tests" / "fixtures"
DEVICE = FX / "bom" / "device-bom.csv"
DEFAULT = FX / "bom" / "altium-default-bom.csv"


# ---------------------------------------------------------------- helpers

def csv_line(refs, **kw):
    """A line as read_bom_csv returns it."""
    base = {"row": 2, "refs": list(refs), "value": "", "mpn": "", "manufacturer": "", "lcsc": "",
            "footprint": "", "description": "", "qty": None, "broken": []}
    base.update(kw)
    return base


def sch_part(ref, **kw):
    """A component as read_altium_parts returns it."""
    base = {"ref": ref, "sheet": "Main", "comment": "", "description": "", "footprint": "", "lib_ref": "",
            "mpn": "", "manufacturer": "", "urls": {}, "broken": {}, "dnp": False}
    base.update(kw)
    return base


def altium(parts=(), pcb=None, **kw):
    base = {"sch": {p["ref"]: p for p in parts}, "pcb": pcb, "unannotated": [], "duplicates": {},
            "errors": [], "sources": [], "sheets": ["Main"]}
    base.update(kw)
    return base


def board(**patterns):
    return {ref: {"ref": ref, "pattern": pat, "layer": 1} for ref, pat in patterns.items()}


def of(findings, kind):
    return [f for f in findings if f["kind"] == kind]


def refs_of(findings, kind):
    return sorted(r for f in of(findings, kind) for r in f["refs"])


def write_csv(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))
    return path


def altium_copy(tmp_path):
    """The WCTopping fixture in a folder of our own (the repo fixtures are never written to),
    with the finished board next to it and a BOM CSV in Outputs/Assembly, as in a real project."""
    root = tmp_path / "alt"
    shutil.copytree(FX / "altium" / "project", root)
    shutil.copy(FX / "altium" / "finished-board.PcbDoc", root / "finished-board.PcbDoc")
    out = root / "Outputs" / "Assembly"
    out.mkdir(parents=True)
    shutil.copy(DEVICE, out / "BOM-full.csv")
    return root


def link_altium(name, root):
    project.set_altium_link(name, project_file=str(root / "WCTopping.PrjPcb"),
                            pcb_file=str(root / "finished-board.PcbDoc"), outputs_dir=str(root / "Outputs"))


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pathlib.Path(root).rglob("*")) if p.is_file()}


def events(name):
    return store.read_jsonl(store.pdir(name) / "bom-log.jsonl")


# ---------------------------------------------------------------- reading a BOM CSV

def test_a_hand_made_bom_is_read_with_its_quirks():
    info = bom_import.inspect_csv(DEVICE)
    assert info["encoding"] == "utf-8" and info["delimiter"] == "," and info["skipped"] == []
    by_ref = {l["refs"][0]: l for l in info["lines"]}
    assert list(by_ref) == ["C5", "R7", "J9", "U9"]

    c5 = by_ref["C5"]
    assert (c5["mpn"], c5["manufacturer"], c5["lcsc"], c5["footprint"], c5["qty"]) == (
        "CC0603ZRY5V9BB104/TR", "Yageo", "C14663", "C0805", 1)
    assert c5["row"] == 2 and c5["broken"] == []

    r = by_ref["R7"]
    assert r["refs"] == ["R7", "R8"] and r["qty"] == 3          # the Quantity column is kept as written
    assert r["value"] == "10\u00b5F" and r["manufacturer"] == ""

    j9 = by_ref["J9"]                                           # a manufacturer that is the repr of a dict
    assert j9["manufacturer"] == "W\u00fcrth Elektronik"
    assert j9["broken"] == [{"field": "manufacturer", "raw": "{'manufacturer': u'W\\xfcrth Elektronik'}"}]
    assert bom_import.read_bom_csv(DEVICE) == info["lines"]


def test_altiums_own_bom_is_ansi_text_without_an_mpn_column():
    info = bom_import.inspect_csv(DEFAULT)
    assert info["encoding"] == "cp1252"
    assert "mpn" not in info["columns"] and "lcsc" not in info["columns"]
    first, second = info["lines"]
    assert first["refs"] == ["C5", "C6"] and first["qty"] == 2 and first["value"] == "100nF 50V"
    assert first["mpn"] == "" and first["lcsc"] == "" and first["footprint"] == "0603C_L"
    assert second["refs"] == ["C10"] and second["value"] == "10\u00b5F"       # one byte, 0xB5, in the file


def test_headers_delimiters_and_a_preamble_are_flexible(tmp_path):
    text = ("Project;Device\n"
            "Reference;Qty;Part Number;LCSC Part #;Package\n"
            '"C1, C2";2;GRM155R71C104KA88D;c1525;0402\n'
            ";1;ignored;;\n")
    info = bom_import.inspect_csv(write_csv(tmp_path / "bom.csv", text))
    assert info["delimiter"] == ";"
    assert info["lines"] == [csv_line(["C1", "C2"], row=3, mpn="GRM155R71C104KA88D", lcsc="C1525",
                                      footprint="0402", qty=2)]
    assert info["skipped"] == [{"row": 4, "why": "no designators"}]

    tabs = write_csv(tmp_path / "tabs.csv", "Designators\tMPN\nU1\tLM358\n")
    assert bom_import.read_bom_csv(tabs)[0]["mpn"] == "LM358"


def test_a_code_that_is_not_an_lcsc_number_is_not_kept(tmp_path):
    path = write_csv(tmp_path / "bom.csv", "Designator,LCSC\nR1,C25804\nR2,n/a\nR3,12345\nR4,Cx9\n")
    assert [l["lcsc"] for l in bom_import.read_bom_csv(path)] == ["C25804", "", "", ""]


def test_a_csv_without_a_designator_column_is_refused(tmp_path):
    path = write_csv(tmp_path / "bom.csv", "Part,Count\nLM358,2\n")
    with pytest.raises(bom_import.BomImportError, match="Designator"):
        bom_import.read_bom_csv(path)


@pytest.mark.parametrize("raw, expect", [
    ("Yageo", ("Yageo", False)),
    ("", ("", False)),
    ("{'manufacturer': u'GCT'}", ("GCT", True)),
    ("{'manufacturer': u'W\\xfcrth Elektronik'}", ("W\u00fcrth Elektronik", True)),
    ("{'x': }", ("", True)),
])
def test_clean_manufacturer(raw, expect):
    assert bom_import.clean_manufacturer(raw) == expect


def test_designators_are_split_deduplicated_and_naturally_sorted():
    assert bom_import.split_refs("C10, C2;C1  C2") == ["C1", "C2", "C10"]
    assert bom_import.split_refs("") == []


# ---------------------------------------------------------------- the comparison, on the real fixture

def test_the_device_csv_against_the_wctopping_project():
    alt = bom_import.read_altium_parts(FX / "altium" / "project" / "WCTopping.PrjPcb",
                                       FX / "altium" / "finished-board.PcbDoc")
    assert sorted(alt["sch"]) == ["C5", "C6"]                  # the rest of the fixture is not annotated
    assert len(alt["unannotated"]) == 58 and alt["errors"] == [] and len(alt["pcb"]) == 56
    assert alt["sch"]["C5"]["mpn"] == "CC0603ZRY5V9BB104" and alt["sch"]["C5"]["sheet"] == "Processor_Interface"

    found = bom_import.compare(bom_import.read_bom_csv(DEVICE), alt)
    sev = lambda kind: {f["severity"] for f in of(found, kind)}
    assert refs_of(found, "missing_in_schematic") == ["J9", "R7", "R8", "U9"] and sev("missing_in_schematic") == {"error"}
    assert refs_of(found, "missing_in_bom") == ["C6"] and sev("missing_in_bom") == {"warn"}
    assert refs_of(found, "qty_mismatch") == ["R7", "R8"]
    assert refs_of(found, "broken_parameter") == ["J9"]
    assert len(of(found, "board_only")) == len(alt["pcb"]) - 2          # every board part but C5 and C6
    assert of(found, "unannotated")[0]["message"].startswith("58 schematic components")

    [fp] = of(found, "footprint_mismatch")                            # CSV C0805; schematic and board 0603C_L
    assert (fp["refs"], fp["csv"], fp["sch"], fp["pcb"]) == (["C5"], "C0805", "0603C_L", "0603C_L")
    [mp] = of(found, "mpn_mismatch")                                  # a reel suffix only
    assert mp["severity"] == "warn" and "packaging suffix" in mp["message"]
    [vl] = of(found, "value_mismatch")
    assert vl["severity"] == "info" and (vl["csv"], vl["sch"]) == ("100nF", "100nF 50V")
    [stale] = of(found, "stale_link")                                 # two parameters, one generic datasheet link
    assert stale["refs"] == ["C5"] and "ComponentLink1URL" in stale["message"] and "ComponentLink1Description" in stale["message"]
    assert "yageo.com" in stale["sch"]

    order = [bom_import.SEVERITY[f["severity"]] for f in found]
    assert order == sorted(order)                                     # worst first
    assert {f["kind"] for f in found} <= set(bom_import.KINDS)


def test_without_a_linked_project_only_the_csv_itself_is_checked():
    lines = [csv_line(["C1"], qty=2, row=2), csv_line(["C1"], row=3),
             csv_line(["J9"], manufacturer="GCT", broken=[{"field": "manufacturer", "raw": "{'manufacturer': u'GCT'}"}])]
    found = bom_import.compare(lines, None)
    assert {f["kind"] for f in found} == {"qty_mismatch", "duplicate_ref", "broken_parameter"}
    assert "J9" in of(found, "broken_parameter")[0]["message"] and "'GCT'" in of(found, "broken_parameter")[0]["message"]


# ---------------------------------------------------------------- the comparison, rule by rule

@pytest.mark.parametrize("csv_mpn, sch_mpn, grade", [
    ("STM32F411RET6", "stm32f411ret6", "same"),
    ("STM32 F411RET6", "STM32F411RET6", "same"),
    ("CC0603ZRY5V9BB104/TR", "CC0603ZRY5V9BB104", "suffix"),
    ("ABC123+T", "ABC123", "suffix"),
    ("ABC123", "ABC123-TR", "suffix"),
    ("ABC123+", "ABC123", "suffix"),
    ("ABC-123", "ABC123", "suffix"),
    ("W25Q128JVEIQ", "W25N04KVZEIR", "differ"),
])
def test_mpn_grades(csv_mpn, sch_mpn, grade):
    assert bom_import._mpn_match(csv_mpn, sch_mpn) == grade


def test_a_different_mpn_is_an_error_and_the_csv_wins_on_import():
    lines = [csv_line(["U9"], mpn="W25Q128JVEIQ")]
    alt = altium([sch_part("U9", mpn="W25N04KVZEIR")])
    [f] = of(bom_import.compare(lines, alt), "mpn_mismatch")
    assert f["severity"] == "error" and "W25Q128JVEIQ" in f["message"] and "W25N04KVZEIR" in f["message"]
    assert bom_import.build_lines(lines, alt)[0]["changes"]["mpn"] == "W25Q128JVEIQ"


def test_a_schematic_with_several_mpns_matches_any_of_them():
    alt = altium([sch_part("U1", mpn="ABC1, ABC2"), sch_part("U2", mpn="ABC1; ABC2/TR")])
    lines = [csv_line(["U1", "U2"], mpn="ABC2")]
    found = bom_import.compare(lines, alt)
    assert refs_of(found, "mpn_mismatch") == ["U2"] and of(found, "mpn_mismatch")[0]["severity"] == "warn"


def test_mismatches_with_the_same_values_are_one_finding():
    parts = [sch_part(f"R{n}", footprint="0603", comment="10k") for n in (1, 2, 3)]
    lines = [csv_line(["R1", "R2", "R3"], footprint="0805", value="4k7")]
    found = bom_import.compare(lines, altium(parts))
    assert [f["refs"] for f in of(found, "footprint_mismatch")] == [["R1", "R2", "R3"]]
    assert [f["refs"] for f in of(found, "value_mismatch")] == [["R1", "R2", "R3"]]


def test_footprints_that_differ_only_in_spelling_are_the_same_footprint():
    alt = altium([sch_part("C1", footprint="C-0603")], pcb=board(C1="c0603"))
    assert bom_import.compare([csv_line(["C1"], footprint="C0603")], alt) == []
    odd = altium([sch_part("C1", footprint="C-0603")], pcb=board(C1="C0805"))
    [f] = of(bom_import.compare([csv_line(["C1"], footprint="C0603")], odd), "footprint_mismatch")
    assert f["pcb"] == "C0805"


@pytest.mark.parametrize("value, comment, finding", [
    ("10\u00b5F", "10 uF", False),
    ("10\u03bcF", "10uF", False),
    ("100nF", "=Value", False),
    ("100nF", "", False),
    ("100nF", "100nF 50V", True),
])
def test_values_are_compared_by_what_they_say(value, comment, finding):
    found = bom_import.compare([csv_line(["C1"], value=value)], altium([sch_part("C1", comment=comment)]))
    assert bool(of(found, "value_mismatch")) is finding


def test_a_stated_quantity_that_disagrees_with_the_designators():
    lines = [csv_line(["R1", "R2"], qty=2), csv_line(["R3"], qty=2, row=3), csv_line(["R4"], qty=None, row=4)]
    [f] = of(bom_import.compare(lines, None), "qty_mismatch")
    assert f["refs"] == ["R3"] and f["severity"] == "warn" and "Row 3" in f["message"]


def test_a_designator_listed_twice_is_an_error():
    lines = [csv_line(["C1", "C2"], row=2), csv_line(["C1"], row=3)]
    alt = altium([sch_part("C1"), sch_part("C2")], duplicates={"C9": ["Power", "Relay"]})
    found = of(bom_import.compare(lines, alt), "duplicate_ref")
    assert sorted(f["refs"][0] for f in found) == ["C1", "C9"] and {f["severity"] for f in found} == {"error"}
    assert "rows 2, 3" in next(f for f in found if f["refs"] == ["C1"])["message"]
    keys = [e["line"] for e in bom_import.build_lines(lines, alt)]
    assert keys == ["C1", "C1-2"]                                     # the key stays unique, so no line is lost


def test_missing_in_bom_is_calm_for_test_points_and_do_not_fit_parts():
    parts = [sch_part("R1"), sch_part("TP5"), sch_part("C41", dnp=True), sch_part("MH2"), sch_part("FID1")]
    found = bom_import.compare([csv_line(["Z1"])], altium(parts))
    severity = {f["refs"][0]: f["severity"] for f in of(found, "missing_in_bom")}
    assert severity == {"R1": "warn", "TP5": "info", "C41": "info", "MH2": "info", "FID1": "info"}
    assert "do-not-fit" in next(f for f in found if f["refs"] == ["C41"])["message"]


@pytest.mark.parametrize("comp, dnp", [
    ({"comment": "100nF DNP"}, True),
    ({"comment": "100nF", "params": {"DNP": "do not populate"}}, True),
    ({"comment": "100nF", "params": {"Fitted": "No"}}, True),
    ({"comment": "100nF", "params": {"Fitted": "Yes"}}, False),
    ({"comment": "100nF 50V"}, False),
])
def test_a_do_not_fit_mark_is_read_from_the_comment_or_a_parameter(comp, dnp):
    assert bom_import._part("C40", "Main", comp)["dnp"] is dnp


def test_a_schematic_part_the_board_lacks_and_a_board_part_the_schematic_lacks():
    parts = [sch_part("R1"), sch_part("R2")]
    on_board = board(R1="0603", R9="0603", TP1="TP", H1="MH-3.2", MH2="MH")
    found = bom_import.compare([csv_line(["R1", "R2"])], altium(parts, pcb=on_board))
    assert refs_of(found, "missing_on_board") == ["R2"] and of(found, "missing_on_board")[0]["severity"] == "warn"
    severity = {f["refs"][0]: f["severity"] for f in of(found, "board_only")}
    assert severity == {"R9": "warn", "TP1": "info", "H1": "info", "MH2": "info"}
    # no PcbDoc given: nothing is said about the board
    quiet = bom_import.compare([csv_line(["R1", "R2"])], altium(parts, pcb=None))
    assert not of(quiet, "missing_on_board") and not of(quiet, "board_only")


def test_a_datasheet_link_that_names_another_part_is_stale():
    parts = [sch_part("C1", mpn="GRM155R71C104KA88D", urls={"Datasheet": "https://x.com/ds/other-part.pdf"}),
             sch_part("C2", mpn="GRM155R71C104KA88D", urls={"Datasheet": "https://x.com/ds/other-part.pdf"}),
             sch_part("C3", mpn="GRM155R71C104KA88D", urls={"Datasheet": "https://x.com/ds/GRM155R71C104KA88D.pdf"}),
             sch_part("C4", mpn="GRM155R71C104KA88D", urls={"Store": "https://www.lcsc.com/product-detail/C1525.html"}),
             sch_part("C5", mpn="GRM155R71C104KA88D", urls={"Home": "https://www.murata.com/"})]
    lines = [csv_line(["C1", "C2", "C3", "C4", "C5"], mpn="GRM155R71C104KA88D", lcsc="C1525")]
    stale = of(bom_import.compare(lines, altium(parts)), "stale_link")
    assert len(stale) == 1                                            # one finding per link, however many parts carry it
    assert stale[0]["refs"] == ["C1", "C2"] and stale[0]["severity"] == "warn"
    assert stale[0]["sch"] == "https://x.com/ds/other-part.pdf" and "'Datasheet'" in stale[0]["message"]
    assert "LCSC C1525" in stale[0]["message"]


def test_only_web_addresses_are_links():
    part = bom_import._part("C1", "Main", {"params": {"Note": "see the datasheet", "URL": " https://a.com/x.pdf ",
                                                       "File": "file:///C:/x.pdf", "Count": 3}})
    assert part["urls"] == {"URL": "https://a.com/x.pdf"}


def test_a_link_cannot_be_stale_when_there_is_nothing_to_compare_it_with():
    alt = altium([sch_part("C1", urls={"Datasheet": "https://x.com/ds/other-part.pdf"})])
    assert not of(bom_import.compare([csv_line(["C1"], value="100nF")], alt), "stale_link")


def test_unannotated_parts_are_listed_once_and_never_matched():
    alt = altium([sch_part("R1")], unannotated=[{"ref": "R?", "sheet": "Main", "comment": "10k"}] * 3)
    found = bom_import.compare([csv_line(["R1"])], alt)
    [f] = of(found, "unannotated")
    assert f["severity"] == "warn" and f["refs"] == ["R?"] * 3 and f["message"].startswith("3 schematic components")


def test_when_no_sheet_could_be_read_nothing_is_called_missing():
    alt = altium([], errors=["Power.SchDoc: truncated"])
    found = bom_import.compare([csv_line(["R1", "R2"])], alt)
    assert [f["kind"] for f in found] == ["source_error"] and found[0]["severity"] == "error"
    partial = altium([sch_part("R1")], errors=["Power.SchDoc: truncated"])
    kinds = {f["kind"] for f in bom_import.compare([csv_line(["R1", "R2"])], partial)}
    assert {"source_error", "missing_in_schematic"} <= kinds


# ---------------------------------------------------------------- the lines that get imported

def test_build_lines_takes_the_csv_and_fills_the_blanks_from_the_schematic():
    alt = altium([sch_part("U1", comment="LM358", description="Op amp", footprint="SOIC8", mpn="LM358DR, LM358P",
                           manufacturer="TI", sheet="Analog"),
                  sch_part("U2", comment="=Value", footprint="SOIC8")])
    lines = [csv_line(["U1"], row=2),
             csv_line(["U2"], row=3, value="TL072", mpn="TL072CDR", lcsc="C6961", footprint="SOIC-8", description="x")]
    first, second = bom_import.build_lines(lines, alt)
    assert first == {"line": "U1", "changes": {"refs": ["U1"], "value": "LM358", "description": "Op amp",
                                               "mpn": "LM358DR", "manufacturer": "TI", "package": "SOIC8",
                                               "sheet": "Analog"}}
    assert second["changes"]["mpn"] == "TL072CDR" and second["changes"]["package"] == "SOIC-8"
    assert second["changes"]["lcsc"] == "C6961" and second["changes"]["value"] == "TL072"
    bare = bom_import.build_lines([csv_line(["U2"])], alt)[0]["changes"]
    assert bare["value"] == "" and "lcsc" not in bare                 # an expression is not a value; no code, no key


# ---------------------------------------------------------------- apply

def test_preview_writes_the_report_and_nothing_else(empty):
    before = DEVICE.read_bytes()
    report = bom_import.preview(empty, DEVICE)
    assert report["applied"] is False and report["bom_empty"] is True
    assert report["csv"]["lines"] == 4 and report["csv"]["refs"] == 5 and report["altium"] is None
    assert events(empty) == [] and store.bom_lines(empty) == []
    d = store.pdir(empty) / "checks"
    assert json.loads((d / "bom-import.json").read_text(encoding="utf-8"))["by_kind"] == report["by_kind"]
    md = (d / "bom-import.md").read_text(encoding="utf-8")
    assert md.startswith(f"# BOM import - {empty}") and "Preview (nothing imported)" in md and "| bom_csv |" in md
    assert DEVICE.read_bytes() == before


def test_apply_appends_one_event_per_line_and_says_where_they_came_from(empty):
    report = bom_import.apply(empty, DEVICE)
    assert report["applied"] is True and report["imported_lines"] == 4

    evs = events(empty)
    assert [e["line"] for e in evs] == ["C5", "R7", "J9", "U9"]
    assert {e["by"] for e in evs} == {"import"} and len({e["ts"] for e in evs}) == 1
    sha = next(s["sha256"] for s in report["sources"] if s["role"] == "bom_csv")
    assert {e["reason"] for e in evs} == {f"Imported from device-bom.csv (sha256 {sha[:12]})"}

    lines = {l["key"]: l for l in store.bom_lines(empty)}
    assert lines["R7"]["refs"] == ["R7", "R8"] and lines["R7"]["lcsc"] == "C15850"
    assert lines["J9"]["manufacturer"] == "W\u00fcrth Elektronik" and lines["C5"]["package"] == "C0805"
    assert [l["key"] for l in json.loads((store.pdir(empty) / "bom.json").read_text(encoding="utf-8"))] == \
        ["C5", "R7", "J9", "U9"]                                      # bom.json follows the log
    md = (store.pdir(empty) / "checks" / "bom-import.md").read_text(encoding="utf-8")
    assert md.startswith(f"# BOM import - {empty}") and "Imported at" in md
    # no Altium project linked: nothing says which symbol and footprint a line uses
    assert report["library_lines"] == 0 and store.library_parts(empty) == {}


def test_library_entries_take_the_symbol_from_the_schematic_and_the_footprint_from_the_board():
    entries = [{"line": "U9", "changes": {"refs": ["U9"]}},
               {"line": "R7", "changes": {"refs": ["R7", "R8"]}},
               {"line": "J9", "changes": {"refs": ["J9"]}},
               {"line": "C5", "changes": {"refs": ["C5"]}}]
    altium = {"sch": {"U9": {"lib_ref": "W25Q128JVEIQ", "footprint": "WSON-8"},
                      "R8": {"lib_ref": "RES", "footprint": "R0603"},
                      "C5": {"lib_ref": "", "footprint": "C0805"}},
              "pcb": {"U9": {"pattern": "WSON-8_8x6"}, "R7": {"pattern": ""}}}
    got = {e["line"]: e["changes"] for e in bom_import.library_entries(entries, altium)}
    assert got["U9"]["symbol"] == "W25Q128JVEIQ" and got["U9"]["footprint"] == "WSON-8_8x6"   # the board wins
    assert got["R7"]["footprint"] == "R0603"                       # no board pattern: the schematic's
    assert "J9" not in got and "C5" not in got                      # not on the schematic / no symbol
    assert {(c["verify"], c["accepted"], c["model_source"]) for c in got.values()} == \
        {("unchecked", False, "Altium project")}
    assert bom_import.library_entries(entries, None) == []


def test_apply_is_refused_into_a_bom_that_has_lines(empty):
    bom_import.apply(empty, DEVICE)
    n = len(events(empty))
    with pytest.raises(bom_import.BomNotEmpty, match="4 lines"):
        bom_import.apply(empty, DEVICE)
    assert len(events(empty)) == n                                    # refused before anything was written
    assert bom_import.preview(empty, DEVICE)["bom_empty"] is False      # a preview is still allowed


def test_apply_to_a_project_that_does_not_exist():
    with pytest.raises(bom_import.BomImportError, match="no such project"):
        bom_import.apply("ghost", DEVICE)


def test_a_missing_csv_is_an_error_the_caller_can_fix(empty, tmp_path):
    with pytest.raises(bom_import.BomImportError, match="not found"):
        bom_import.preview(empty, tmp_path / "nope.csv")


def test_the_source_files_are_never_changed(empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    before = tree_hashes(root)
    bom_import.preview(empty, root / "Outputs" / "Assembly" / "BOM-full.csv")
    bom_import.apply(empty, root / "Outputs" / "Assembly" / "BOM-full.csv")
    assert tree_hashes(root) == before


def test_apply_with_a_linked_project_compares_and_records_the_sheet(empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    report = bom_import.apply(empty, root / "Outputs" / "Assembly" / "BOM-full.csv")
    roles = [s["role"] for s in report["sources"]]
    assert roles[0] == "bom_csv" and "prjpcb" in roles and roles.count("schdoc") == 5 and "pcbdoc" in roles
    assert report["altium"]["sch_components"] == 2 and report["altium"]["pcb_components"] == 56
    assert report["by_kind"]["missing_in_schematic"] == 4 and report["by_severity"]["error"] >= 4
    lines = {l["key"]: l for l in store.bom_lines(empty)}
    assert lines["C5"]["sheet"] == "Processor_Interface" and "sheet" not in lines["U9"]
    # a line the schematic and the board name is in the library, to review - not missing
    lib = store.library_parts(empty)
    assert report["library_lines"] == len(lib) >= 1 and "C5" in lib and "U9" not in lib
    status = {l["key"]: l["library"] for l in store.bom(empty, write=False)}
    assert status["C5"] == "review" and status["U9"] == "missing"


def test_a_broken_pcbdoc_is_a_finding_not_a_crash(empty, tmp_path):
    root = altium_copy(tmp_path)
    (root / "finished-board.PcbDoc").write_bytes(b"this is not an OLE file")
    link_altium(empty, root)
    report = bom_import.preview(empty, root / "Outputs" / "Assembly" / "BOM-full.csv")
    assert report["by_kind"]["source_error"] == 1 and report["altium"]["pcb_components"] is None
    assert "board_only" not in report["by_kind"]


# ---------------------------------------------------------------- finding the CSV

def test_candidates_are_bom_csvs_newest_first_and_skip_what_is_not_a_bom(empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    old = root / "Outputs" / "Assembly" / "BOM-full.csv"
    new = write_csv(root / "Outputs" / "Assembly" / "bom-newer.csv", DEFAULT.read_bytes().decode("cp1252"), "cp1252")
    for name in ("History/old-bom.csv", "_Legacy/bom.csv", ".venv/x/bom.csv", "__previews/bom.csv",
                 "Outputs/notes.csv", "Outputs/readme-bom.txt", "Outputs/broken-bom.csv"):
        write_csv(root / name, "Part,Count\nLM358,2\n" if name.endswith("broken-bom.csv") else "Designator\nR1\n")
    os.utime(old, (1_700_000_000, 1_700_000_000))
    os.utime(new, (1_700_100_000, 1_700_100_000))

    found = bom_import.candidates(empty)
    assert [c["name"] for c in found] == ["bom-newer.csv", "BOM-full.csv"]       # the outputs folder is under the project folder: once
    assert found[0]["rows"] == 2 and found[0]["has_lcsc"] is False and found[0]["has_mpn"] is False
    assert found[1]["rows"] == 4 and found[1]["has_lcsc"] is True and found[1]["has_mpn"] is True
    assert pathlib.Path(found[1]["path"]) == old and found[1]["mtime"] < found[0]["mtime"]
    assert len(bom_import.candidates(empty, limit=1)) == 1


def test_candidates_of_a_project_without_a_link_are_none(empty):
    assert bom_import.altium_dirs(empty) == [] and bom_import.candidates(empty) == []


def test_which_paths_a_request_from_the_browser_may_name(empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    inside = root / "Outputs" / "Assembly" / "BOM-full.csv"
    secret = write_csv(tmp_path / "secret.csv", "Designator\nR1\n")
    ours = write_csv(store.pdir(empty) / "sources" / "mine.csv", "Designator\nR1\n")
    write_csv(root / "Outputs" / "notes.txt", "x")

    assert bom_import.resolve_csv(empty, str(inside)) == inside.resolve()
    assert bom_import.resolve_csv(empty, "Outputs/Assembly/BOM-full.csv") == inside.resolve()     # relative to the project
    assert bom_import.resolve_csv(empty, str(ours)) == ours.resolve()                           # the project's own folder
    for bad in (str(secret), "Outputs/../../secret.csv", str(FX / "bom" / "device-bom.csv"), "C:/Windows/win.ini"):
        with pytest.raises(bom_import.PathRefused):
            bom_import.resolve_csv(empty, bad)
    assert bom_import.resolve_csv(empty, str(secret), restrict=False) == secret.resolve()     # the command line may

    with pytest.raises(bom_import.BomImportError, match=r"\.csv") as e:
        bom_import.resolve_csv(empty, str(root / "Outputs" / "notes.txt"))
    assert not isinstance(e.value, bom_import.PathRefused)
    for bad in ("", "   ", None):
        with pytest.raises(bom_import.BomImportError, match="required"):
            bom_import.resolve_csv(empty, bad)
    with pytest.raises(bom_import.BomImportError, match="not found"):
        bom_import.resolve_csv(empty, str(root / "Outputs" / "gone.csv"))


# ---------------------------------------------------------------- the declared LCSC code

def test_a_jlc_export_uses_the_declared_code_and_the_stock_check_wins(lte):
    assert "U5" in export_bom.export(lte, "jlc")["needs_lcsc"]
    store.edit_bom(lte, "U5", "lcsc", "C44955")
    res = export_bom.export(lte, "jlc")
    assert "U5" not in res["needs_lcsc"]
    path = store.pdir(lte) / "exports" / f"{lte}_BOM_jlc.csv"
    assert "C44955" in path.read_text(encoding="utf-8")

    store.add_supply(lte, "U5", "LCSC", 10, 0.4, "TXS0104EPWR", source="LCSC C99999")
    export_bom.export(lte, "jlc")
    text = path.read_text(encoding="utf-8")
    assert "C99999" in text and "C44955" not in text                  # what was last looked up beats what was declared


def test_a_new_mpn_voids_the_declared_code(empty):
    bom_import.apply(empty, DEVICE)
    assert {l["key"]: l for l in store.bom_lines(empty)}["C5"]["lcsc"] == "C14663"

    assert store.edit_bom(empty, "C5", "mpn", "CC0603ZRY5V9BB104/TR") is None        # not a change: the code stays
    assert {l["key"]: l for l in store.bom_lines(empty)}["C5"]["lcsc"] == "C14663"

    store.edit_bom(empty, "C5", "lcsc", "C1525")                      # the student may set the code by hand
    assert {l["key"]: l for l in store.bom_lines(empty)}["C5"]["lcsc"] == "C1525"
    store.edit_bom(empty, "C5", "mpn", "CL10A104KB8NNNC")
    assert {l["key"]: l for l in store.bom_lines(empty)}["C5"]["lcsc"] == ""         # it was for the old part

    last = events(empty)[-1]
    assert last["changes"]["lcsc"] == "" and last["changes"]["mpn"] == "CL10A104KB8NNNC"


def test_a_new_mpn_on_a_line_without_a_code_adds_no_lcsc_key(empty):
    store.append(empty, "bom-log.jsonl", {"ts": store.now(), "by": "import", "line": "R1",
                                          "changes": {"refs": ["R1"], "mpn": "OLD"}})
    store.edit_bom(empty, "R1", "mpn", "NEW")
    assert "lcsc" not in events(empty)[-1]["changes"]


def test_an_approved_proposal_with_a_new_mpn_voids_the_declared_code_too(empty):
    bom_import.apply(empty, DEVICE)
    pid = store.propose_bom(empty, "U9", {"mpn": "W25Q64JVSSIQ"}, reason="smaller flash")["id"]
    store.decide(empty, pid, "approved")
    u9 = {l["key"]: l for l in store.bom_lines(empty)}["U9"]
    assert u9["mpn"] == "W25Q64JVSSIQ" and u9["lcsc"] == ""


# ---------------------------------------------------------------- the availability check starts from the code

def _raw(mpn, code, stock=10):
    return {"componentModelEn": mpn, "componentCode": code, "stockCount": stock,
            "componentPrices": [{"startNumber": 1, "endNumber": -1, "productPrice": 0.5}]}


def test_availability_looks_the_declared_code_up_first(lte, monkeypatch):
    asked = []

    def fake(keyword, n=10):
        asked.append(keyword)
        return [_raw("MIC94355", "C111111"), _raw("TXS0104EPWR", "C44955", stock=777)]
    monkeypatch.setattr(check_availability, "jlc_search", fake)
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    store.edit_bom(lte, "U5", "lcsc", "C44955")

    [out] = check_availability.check(lte, {"U5"})
    assert asked == ["C44955"]                                        # the code alone found it; the MPN was not searched
    assert (out["code"], out["stock"], out["exact"]) == ("C44955", 777, True)   # a look-alike with another code is not taken


def test_availability_falls_back_to_the_mpn_when_the_code_finds_nothing(lte, monkeypatch):
    asked = []

    def fake(keyword, n=10):
        asked.append(keyword)
        return [] if keyword == "C44955" else [_raw("TXS0104EPWR", "C12345", stock=5)]
    monkeypatch.setattr(check_availability, "jlc_search", fake)
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    store.edit_bom(lte, "U5", "lcsc", "C44955")

    [out] = check_availability.check(lte, {"U5"})
    assert asked == ["C44955", "TXS0104EPWR"] and out["code"] == "C12345" and out["exact"] is True


def test_a_line_with_a_code_and_no_mpn_is_checked_at_lcsc_only(empty, monkeypatch):
    store.append(empty, "bom-log.jsonl", {"ts": store.now(), "by": "import", "line": "J9",
                                          "changes": {"refs": ["J9"], "mpn": "", "lcsc": "C5184785"}})
    store.append(empty, "bom-log.jsonl", {"ts": store.now(), "by": "import", "line": "R1",
                                          "changes": {"refs": ["R1"], "mpn": "\u2014"}})           # no MPN, no code: skipped
    asked = []
    monkeypatch.setattr(check_availability, "jlc_search", lambda kw, n=10: asked.append(kw) or [_raw("61300411121", "C5184785")])
    monkeypatch.setenv("MOUSER_API_KEY", "key")
    monkeypatch.setattr(check_availability, "mouser", lambda mpn: pytest.fail("Mouser needs an MPN"))

    out = check_availability.check(empty)
    assert asked == ["C5184785"]
    assert [(o["line"], o["supplier"], o["code"]) for o in out] == [("J9", "LCSC", "C5184785")]
    assert store.supply_for(empty)["J9"]["LCSC"]["stock"] == 10


def test_lcsc_without_an_mpn_or_a_code_asks_nobody(monkeypatch):
    monkeypatch.setattr(check_availability, "jlc_search", lambda kw, n=10: pytest.fail("no question to ask"))
    assert check_availability.lcsc("") is None and check_availability.lcsc("", None) is None


# ---------------------------------------------------------------- a declared code that is another part

@pytest.mark.parametrize("mpn, model, same", [
    ("STM32F411RET6", "stm32f411ret6", True),
    ("STM32 F411RET6", "STM32F411RET6", True),
    ("1812L260/16MR", "1812L260-16MR", True),
    ("ABC_123", "ABC123", True),
    ("ABC123 (reel)", "ABC123", True),
    ("CC0603ZRY5V9BB104/TR", "CC0603ZRY5V9BB104", True),          # a reel suffix on one side
    ("MAX31856MUD+", "MAX31856MUD+T", True),                      # Maxim: lead-free, then reel
    ("1812L260/16MR", "SMD1812P260TF/16", False),                 # the real case: another maker's fuse
    ("STM32F411RE", "STM32F411RET6", False),                      # a longer orderable code is another variant
    ("", "ANYTHING", True),                                       # nothing to compare
    ("ANYTHING", None, True),
])
def test_the_mpn_a_declared_code_resolves_to(mpn, model, same):
    assert check_availability.mpn_matches(mpn, model) is same


def _fuse_search(asked, alt=True):
    """C20814 is a RUILON fuse; the Littelfuse part the BOM names is C207075."""
    def fake(keyword, n=10):
        asked.append(keyword)
        if keyword == "C20814":
            return [_raw("SMD1812P260TF/16", "C20814", stock=4000) | {"componentBrandEn": "RUILON(耐普罗)"}]
        if keyword == "1812L260/16MR" and alt:
            return [_raw("1812L260/16MR", "C207075", stock=900) | {"componentBrandEn": "Littelfuse"}]
        return []
    return fake


def _line(project_name, key, **changes):
    store.append(project_name, "bom-log.jsonl", {"ts": store.now(), "by": "import", "line": key,
                                                  "changes": {"refs": [key], **changes}})


def test_a_code_that_names_another_part_still_gives_stock_but_says_so(empty, monkeypatch):
    asked = []
    monkeypatch.setattr(check_availability, "jlc_search", _fuse_search(asked))
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    _line(empty, "F1", mpn="1812L260/16MR", lcsc="C20814", value="2.6A fuse")

    [out] = check_availability.check(empty)
    msg = ("LCSC C20814 is RUILON SMD1812P260TF/16, not 1812L260/16MR: JLC will place the RUILON part. "
           "Check it is equivalent, or use C207075.")
    assert asked == ["C20814", "1812L260/16MR"]                       # the code first; the MPN only to find a better code
    assert (out["code"], out["stock"], out["exact"]) == ("C20814", 4000, True)       # stock and price are of the code's part
    assert out["warning"] == "code_mpn_mismatch" and out["message"] == msg

    f1 = {l["key"]: l for l in store.bom(empty, write=False)}["F1"]
    assert f1["supply"]["LCSC"]["code_mismatch"] == msg and f1["supply"]["LCSC"]["code"] == "C20814"
    assert store.CODE_RISK in f1["risk"]
    assert store.supply_for(empty)["F1"]["LCSC"]["stock"] == 4000


@pytest.mark.parametrize("alt_search", [
    lambda keyword, n=10: [_raw("1812L260/16MR-OTHER-REEL", "C555555")],        # near, not exact
    lambda keyword, n=10: (_ for _ in ()).throw(OSError("offline")),            # the suggestion is lost, nothing else
])
def test_no_other_code_is_named_unless_the_mpn_search_finds_it_exactly(empty, monkeypatch, alt_search):
    base = _fuse_search([], alt=False)
    monkeypatch.setattr(check_availability, "jlc_search", lambda kw, n=10: base(kw, n) if kw == "C20814" else alt_search(kw, n))
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    _line(empty, "F1", mpn="1812L260/16MR", lcsc="C20814")

    [out] = check_availability.check(empty)
    assert out["message"] == ("LCSC C20814 is RUILON SMD1812P260TF/16, not 1812L260/16MR: JLC will place the RUILON part. "
                              "Check it is equivalent.")
    assert out["stock"] == 4000


def test_a_code_that_names_the_mpns_part_is_not_a_warning_and_costs_one_search(empty, monkeypatch):
    asked = []

    def fake(keyword, n=10):
        asked.append(keyword)
        return [_raw("CC0603ZRY5V9BB104", "C14663")]
    monkeypatch.setattr(check_availability, "jlc_search", fake)
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    _line(empty, "C5", mpn="CC0603ZRY5V9BB104/TR", lcsc="C14663")

    [out] = check_availability.check(empty)
    assert asked == ["C14663"] and "warning" not in out
    c5 = {l["key"]: l for l in store.bom(empty, write=False)}["C5"]
    assert "code_mismatch" not in c5["supply"]["LCSC"] and store.CODE_RISK not in c5["risk"]


def test_a_line_with_a_code_and_no_mpn_has_nothing_to_disagree_with(empty, monkeypatch):
    monkeypatch.setattr(check_availability, "jlc_search", _fuse_search([]))
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    _line(empty, "F1", mpn="", lcsc="C20814")
    [out] = check_availability.check(empty)
    assert out["code"] == "C20814" and "warning" not in out


def test_setting_the_right_code_and_checking_again_clears_the_warning(empty, monkeypatch):
    monkeypatch.setattr(check_availability, "jlc_search", _fuse_search([]))
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)
    _line(empty, "F1", mpn="1812L260/16MR", lcsc="C20814")
    check_availability.check(empty)
    assert store.CODE_RISK in {l["key"]: l for l in store.bom(empty, write=False)}["F1"]["risk"]

    store.edit_bom(empty, "F1", "lcsc", "C207075")
    [out] = check_availability.check(empty)
    assert out["code"] == "C207075" and "warning" not in out
    assert store.CODE_RISK not in {l["key"]: l for l in store.bom(empty, write=False)}["F1"]["risk"]


def test_an_lcsc_edit_over_http_rechecks_the_line_like_an_mpn_edit(server, empty, monkeypatch):
    import serve
    rechecked = []
    monkeypatch.setattr(serve, "recheck_async", lambda p, k: rechecked.append((p, k)))
    _line(empty, "F1", mpn="1812L260/16MR", lcsc="C20814")
    assert call(server, "/api/bom/edit", empty, {"line": "F1", "field": "lcsc", "value": "C207075"})[0] == 200
    assert call(server, "/api/bom/edit", empty, {"line": "F1", "field": "note", "value": "x"})[0] == 200
    assert rechecked == [(empty, "F1")]


# ---------------------------------------------------------------- jlc.part_by_code

def _envelope(items):
    return {"code": 200, "msg": "success", "data": {"componentPageInfo": {"list": items}}}


def _item(code, mpn):
    return {"componentCode": code, "componentModelEn": mpn, "componentBrandEn": "Acme",
            "componentSpecificationEn": "0603", "stockCount": 9, "componentPrices": [],
            "componentLibraryType": "base", "preferredComponentFlag": False}


def test_part_by_code_takes_only_the_hit_with_that_code(home):
    seen = []

    def transport(url, body, **kw):
        seen.append(body)
        return _envelope([_item("C9435500", "MIC94355-LOOKALIKE"), _item("C94355", "STM32F411RET6")])

    p = jlc.part_by_code("c94355", transport=transport)
    assert p["code"] == "C94355" and p["mpn"] == "STM32F411RET6" and p["exact"] is True
    assert len(seen) == 1 and "C94355" in json.dumps(seen[0])


def test_part_by_code_is_none_when_no_hit_has_the_code(home):
    assert jlc.part_by_code("C77777", transport=lambda url, body, **kw: _envelope([_item("C1", "X")])) is None


@pytest.mark.parametrize("code", ["", None, "STM32", "C", "12345", "C12x"])
def test_part_by_code_does_not_search_for_what_is_not_a_code(home, code):
    def transport(url, body, **kw):
        raise AssertionError("must not search")
    assert jlc.part_by_code(code, transport=transport) is None


# ---------------------------------------------------------------- the command line

def test_the_command_line_lists_candidates_and_does_a_dry_run(empty, tmp_path, capsys):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    assert bom_import.main([empty]) == 0
    listing = capsys.readouterr().out
    assert "BOM-full.csv" in listing and "4 rows" in listing and "LCSC" in listing

    csv_path = str(root / "Outputs" / "Assembly" / "BOM-full.csv")
    assert bom_import.main([empty, csv_path]) == 0
    out = capsys.readouterr().out
    assert "dry run, nothing written to the BOM" in out and "Add --apply to import." in out
    assert "missing_in_schematic" in out and "[error] missing_in_schematic" in out
    assert "WCTopping.PrjPcb: 5 sheets" in out and "PcbDoc 56 components" in out
    assert events(empty) == []

    assert bom_import.main([empty, csv_path, "--apply"]) == 0
    assert "IMPORTED" in capsys.readouterr().out
    assert len(events(empty)) == 4

    assert bom_import.main([empty, csv_path]) == 0
    assert "import works into an empty BOM only" in capsys.readouterr().out


def test_the_command_line_says_what_is_wrong(empty, tmp_path):
    with pytest.raises(SystemExit, match="no such project"):
        bom_import.main(["ghost", str(DEVICE)])
    with pytest.raises(SystemExit, match="not found"):
        bom_import.main([empty, str(tmp_path / "nope.csv")])
    bom_import.apply(empty, DEVICE)
    with pytest.raises(SystemExit, match="empty BOM"):
        bom_import.main([empty, str(DEVICE), "--apply"])


# ---------------------------------------------------------------- over HTTP

@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)   # no network
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, path, project_name, body=None):
    url = f"{base}{path}{'&' if '?' in path else '?'}project={project_name}"
    req = urllib.request.Request(url, method="GET" if body is None else "POST",
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_the_candidates_endpoint(server, empty, tmp_path):
    code, body = call(server, "/api/bom/import/candidates", empty)
    assert code == 200 and body == {"linked": False, "bom_empty": True, "candidates": []}

    root = altium_copy(tmp_path)
    link_altium(empty, root)
    code, body = call(server, "/api/bom/import/candidates", empty)
    assert code == 200 and body["linked"] is True and body["bom_empty"] is True
    assert [c["name"] for c in body["candidates"]] == ["BOM-full.csv"]
    assert body["candidates"][0]["rows"] == 4 and body["candidates"][0]["has_lcsc"] is True

    assert call(server, "/api/bom/import/candidates", "ghost")[0] == 404


def test_preview_then_import_over_http(server, empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    csv_path = str(root / "Outputs" / "Assembly" / "BOM-full.csv")

    code, rep = call(server, "/api/bom/import", empty, {"csv": csv_path})
    assert code == 200 and rep["applied"] is False and "state" not in rep
    assert rep["by_kind"]["missing_in_schematic"] == 4 and rep["csv"]["lines"] == 4
    assert events(empty) == [] and (store.pdir(empty) / "checks" / "bom-import.json").is_file()

    code, rep = call(server, "/api/bom/import", empty, {"csv": csv_path, "apply": True})
    assert code == 200 and rep["applied"] is True and rep["imported_lines"] == 4
    assert [l["key"] for l in rep["state"]["bom"]] == ["C5", "R7", "J9", "U9"]    # the page redraws from this
    assert rep["state"]["bom"][0]["lcsc"] == "C14663"
    assert len(events(empty)) == 4

    code, err = call(server, "/api/bom/import", empty, {"csv": csv_path, "apply": True})
    assert code == 409 and "empty BOM" in err["error"] and len(events(empty)) == 4
    assert call(server, "/api/bom/import/candidates", empty)[1]["bom_empty"] is False


def test_the_endpoint_works_without_a_linked_altium_project(server, empty):
    mine = write_csv(store.pdir(empty) / "sources" / "bom.csv", DEVICE.read_bytes().decode("utf-8-sig"))
    code, rep = call(server, "/api/bom/import", empty, {"csv": str(mine)})
    assert code == 200 and rep["altium"] is None and rep["csv"]["lines"] == 4
    code, rep = call(server, "/api/bom/import", empty, {"csv": "sources/bom.csv", "apply": True})
    assert code == 200 and rep["imported_lines"] == 4


def test_the_endpoint_refuses_paths_outside_the_project(server, empty, tmp_path):
    root = altium_copy(tmp_path)
    link_altium(empty, root)
    secret = write_csv(tmp_path / "secret.csv", "Designator\nR1\n")
    write_csv(root / "Outputs" / "notes.txt", "x")
    for bad in (str(secret), "Outputs/../../secret.csv", str(DEVICE), "C:/Windows/win.ini"):
        code, err = call(server, "/api/bom/import", empty, {"csv": bad})
        assert code == 403, bad
        assert "must be inside" in err["error"]
    assert not (store.pdir(empty) / "checks" / "bom-import.json").exists()      # nothing was read, nothing was written

    assert call(server, "/api/bom/import", empty, {"csv": str(root / "Outputs" / "notes.txt")})[0] == 400
    assert call(server, "/api/bom/import", empty, {"csv": str(root / "Outputs" / "gone.csv")})[0] == 400
    assert call(server, "/api/bom/import", empty, {})[0] == 400
    assert call(server, "/api/bom/import", empty, {"csv": "  "})[0] == 400
    bad_csv = write_csv(root / "Outputs" / "bad-bom.csv", "Part,Count\nLM358,2\n")
    code, err = call(server, "/api/bom/import", empty, {"csv": str(bad_csv)})
    assert code == 400 and "Designator" in err["error"]
    assert events(empty) == []
    assert call(server, "/api/bom/import", empty, {"project": "ghost", "csv": str(DEVICE)})[0] == 404


# ---------------------------------------------------------------- the page

def test_the_bom_tab_offers_the_import():
    html = ui_all()
    for needle in ("Import BOM from Altium", "/api/bom/import/candidates", "'/api/bom/import'",
                   'data-act="imp-preview"', 'data-act="imp-apply"', 'data-act="imp-scan"',
                   "function importHTML()", "function importReportHTML(", "${importHTML()}",
                   "Import works into an empty BOM", "onAct('imp-apply'"):
        assert needle in html, needle
    # a finding is text from a file: it goes through esc()
    assert "esc(f.message)" in html and "esc(f.kind)" in html and "esc(c.path)" in html
