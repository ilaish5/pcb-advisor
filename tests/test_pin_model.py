"""The pin check against the part's library model (scripts/pin_model.py): a diode, an LED or a connector whose sheet pins agree with the
EasyEDA model it is drawn from is verified by it; one that disagrees is a mismatch with a reason; one the model cannot decide stays
unverified. The fixtures under tests/fixtures/pin_model/<LCSC>/ are the real library files of five parts (the raw kicad_sym and
kicad_mod, the manifest entry, and the pins / pads of the built symbol and footprint): Blinker-555 D1 (C84256, pins "+" 2 and "-" 1),
Dark-sensor-LED D1 (C34499, 2 = K and 1 = A) and J1 (C393939, a USB-C with named pins), Live-STM32 D1 (C99289) and J2 (C32713270, a
1x4 header whose pins are named by number)."""
import json
import pathlib
import shutil

import pin_model
import store

FIX = pathlib.Path(__file__).parent / "fixtures" / "pin_model"


def _library(project, parts, source="easyeda"):
    """Builds library/ of the project from the fixtures: parts = {line key: LCSC}. The manifest, the EasyEDA folder and the built specs."""
    import partlib
    lib = partlib.library_dir(project)
    (lib / "build").mkdir(parents=True, exist_ok=True)
    man, syms, fps = {}, [], ["FPLIB|<PCBLIB>"]
    for key, lcsc in parts.items():
        src = FIX / lcsc
        entry = json.loads((src / "manifest_entry.json").read_text(encoding="utf-8"))
        entry["source"] = source
        man[key] = entry
        dst = lib / "easyeda" / lcsc
        if not dst.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*_spec.txt", "manifest_entry.json"))
        syms += (src / "symbols_spec.txt").read_text(encoding="cp1252").splitlines()
        fps += (src / "footprints_spec.txt").read_text(encoding="cp1252").splitlines()[1:]
    (lib / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (lib / "build" / "symbols_spec.txt").write_text("\n".join(syms) + "\n", encoding="cp1252")
    (lib / "build" / "footprints_spec.txt").write_text("\n".join(fps) + "\n", encoding="cp1252")
    return man


def _bom(project, key, lcsc, refs=None):
    entry = json.loads((FIX / lcsc / "manifest_entry.json").read_text(encoding="utf-8"))
    store.propose_bom(project, key, {"mpn": entry["mpn"], "lcsc": lcsc, "refs": refs or [key]}, new=True)
    store.decide(project, store.proposals(project)[-1]["id"], "approved")


def _pins(*rows):
    return [{"num": n, "name": nm, "net": net} for n, nm, net in rows]


def _draw(project, parts, sheet="01"):
    """parts = {ref: [(num, name, net), ...]}"""
    sh = {"sections": [{"id": "A", "title": "T"}],
          "parts": [{"ref": r, "section": "A", "pins": _pins(*p)} for r, p in parts.items()]}
    assert store.write_sheet(project, sheet, sh)["ok"]


def _verdict(project, key):
    return pin_model.check(project, store._line_of(project, key))


# ---------------------------------------------------------------- parsing the real files

def test_parse_the_real_symbol_and_footprint():
    sym = pin_model.parse_symbol((FIX / "C84256" / "lib.kicad_sym").read_text(encoding="utf-8"))
    assert sym["symbols"] == ["FC-2012HRK-620D"] and sym["lcsc"] == "C84256"
    assert {p["num"]: p["name"] for p in sym["pins"]} == {"2": "+", "1": "-"}
    fp = pin_model.parse_footprint((FIX / "C84256" / "lib.pretty" / "LED0805-RD.kicad_mod").read_text(encoding="utf-8"))
    assert fp["name"] == "LED0805-RD" and fp["lcsc"] == "C84256" and sorted(fp["pads"]) == ["1", "2"]


def test_parse_a_connector_with_named_pins():
    sym = pin_model.parse_symbol((FIX / "C393939" / "lib.kicad_sym").read_text(encoding="utf-8"))
    names = {p["num"]: p["name"] for p in sym["pins"]}
    assert names["A1B12"] == "GND" and names["A4B9"] == "VBUS" and names["1"] == "SHELL"


# ---------------------------------------------------------------- agree

def test_led_drawn_as_the_library_numbers_it_is_verified(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    chk = _verdict(empty, "D1")
    assert chk["result"] == "agree" and "C84256" in chk["reason"]
    assert chk["evidence"]["basis"] == "library_model" and chk["evidence"]["symbol"] == "NCD0805R1"
    assert "not a datasheet reading" in chk["evidence"]["note"]
    line = {l["key"]: l for l in store.bom(empty)}["D1"]
    assert line["pins_status"] == "verified" and line["pins_basis"] == "library_model"
    assert store.unverified_parts(empty) == []


def test_anode_cathode_names_in_other_case_still_agree(empty):
    _library(empty, {"D1": "C34499"})
    _bom(empty, "D1", "C34499")
    _draw(empty, {"D1": [("1", "a", "N1"), ("2", "k", "GND")]})
    assert _verdict(empty, "D1")["result"] == "agree"


def test_connector_with_the_models_pin_names_is_verified(empty):
    _library(empty, {"J1": "C393939"})
    _bom(empty, "J1", "C393939")
    _draw(empty, {"J1": [("A1B12", "GND", "GND"), ("A4B9", "VBUS", "+5V"), ("A5", "CC1", "CC1"), ("A6", "DP1", "DP"), ("A7", "DN1", "DN")]})
    chk = _verdict(empty, "J1")
    assert chk["result"] == "agree", chk
    assert {l["key"]: l for l in store.bom(empty)}["J1"]["pins_basis"] == "library_model"


# ---------------------------------------------------------------- disagree

def test_led_with_anode_and_cathode_swapped_is_a_mismatch_with_a_reason(empty):
    _library(empty, {"D1": "C34499"})
    _bom(empty, "D1", "C34499")
    _draw(empty, {"D1": [("1", "K", "GND"), ("2", "A", "N1")]})          # the library has 1 = A and 2 = K
    chk = _verdict(empty, "D1")
    assert chk["result"] == "disagree"
    assert "pin 1" in chk["reason"] and "cathode" in chk["reason"] and "anode" in chk["reason"] and "C34499" in chk["reason"]
    row = next(u for u in store.unverified_parts(empty) if u["line"] == "D1")
    assert row["status"] == "mismatch" and "library" in row["issues"]


def test_a_pin_number_the_model_does_not_have_disagrees(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("3", "-", "GND")]})
    chk = _verdict(empty, "D1")
    assert chk["result"] == "disagree" and "pin 3" in chk["reason"]


def test_connector_pin_named_otherwise_than_the_model_disagrees(empty):
    _library(empty, {"J1": "C393939"})
    _bom(empty, "J1", "C393939")
    _draw(empty, {"J1": [("A1B12", "GND", "GND"), ("A4B9", "VBUS", "+5V"), ("A5", "CC2", "CC1")]})
    chk = _verdict(empty, "J1")
    assert chk["result"] == "disagree" and "CC2" in chk["reason"] and "CC1" in chk["reason"]


# ---------------------------------------------------------------- undecided: never verified without real evidence

def test_header_named_by_numbers_stays_for_the_student(empty):
    _library(empty, {"J2": "C32713270"})
    _bom(empty, "J2", "C32713270")
    _draw(empty, {"J2": [("1", "1", "+3V3"), ("2", "2", "GND"), ("3", "3", "SDA"), ("4", "4", "SCL")]})
    chk = _verdict(empty, "J2")
    assert chk["result"] == "undecided" and "number" in chk["reason"]
    assert {l["key"]: l for l in store.bom(empty)}["J2"]["pins_status"] == "unverified"


def test_a_symbol_that_was_generated_from_the_sheet_decides_nothing(empty):
    _library(empty, {"D1": "C84256"}, source="generated")
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    chk = _verdict(empty, "D1")
    assert chk["result"] == "undecided" and "sheet itself" in chk["reason"]
    assert {l["key"]: l for l in store.bom(empty)}["D1"]["pins_status"] == "unverified"


def test_no_library_built_yet_decides_nothing(empty):
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    chk = _verdict(empty, "D1")
    assert chk["result"] == "undecided" and "no library model" in chk["reason"]


def test_a_library_built_for_another_lcsc_code_decides_nothing(empty):
    _library(empty, {"D1": "C84256"})
    store.propose_bom(empty, "D1", {"mpn": "NCD0805R1", "lcsc": "C99999", "refs": ["D1"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    assert _verdict(empty, "D1")["result"] == "undecided"


def test_a_model_file_changed_after_the_build_is_noticed(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    assert _verdict(empty, "D1")["result"] == "agree"
    import partlib
    sym = partlib.library_dir(empty) / "easyeda" / "C84256" / "lib.kicad_sym"
    sym.write_text(sym.read_text(encoding="utf-8").replace('"+"', '"A"', 1), encoding="utf-8")
    chk = pin_model.check(empty, dict(store._line_of(empty, "D1"), key="D1"))
    assert chk["result"] == "undecided" and "do not have the same pins" in chk["reason"]


def test_a_resistor_or_an_ic_is_not_checked(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "R1", "C84256")
    _draw(empty, {"R1": [("1", "1", "A"), ("2", "2", "B")]})
    assert _verdict(empty, "R1")["result"] == "undecided"


# ---------------------------------------------------------------- never overrides a decision

def test_the_model_never_overrides_a_flagged_or_accepted_part(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    store.accept_pins(empty, "D1")
    line = {l["key"]: l for l in store.bom(empty)}["D1"]
    assert line["pins_status"] == "accepted" and line.get("pins_basis") != "library_model"     # the student's word stays the basis


def test_an_audit_record_is_written_once_and_the_order_manifest_lists_the_part(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    store.bom(empty)
    store.bom(empty)
    rec = store.library_manifest(empty)
    log = (store.pdir(empty) / "library-log.jsonl").read_text(encoding="utf-8").splitlines() if (store.pdir(empty) / "library-log.jsonl").exists() else []
    assert sum('"pin_model_check"' in ln for ln in log) == 1
    assert [v["line"] for v in pin_model.verified_lines(empty)] == ["D1"]
    del rec
