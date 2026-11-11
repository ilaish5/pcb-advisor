"""Verify later, don't block now: an IC without a datasheet is placed and marked unverified; the Final checks list it."""
import sources
import store
import verify_part


def _add(empty, key, mpn):
    store.propose_bom(empty, key, {"mpn": mpn, "refs": [key]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")


def _sheet(empty):
    _add(empty, "U1", "ABCD1234")
    _add(empty, "R1", "RC0603")
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}]},
        {"ref": "R1", "section": "A", "pins": [{"num": "1", "name": "1", "net": "+3V3"}, {"num": "2", "name": "2", "net": "X"}]}]}
    return store.write_sheet(empty, "01", sheet)


def _datasheet(empty, text):
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 x")
    (folder / "ABCD1234.pdf.txt").write_text(text, encoding="utf-8")


def test_ic_without_datasheet_is_written_and_marked_passives_are_not(empty):
    assert _sheet(empty)["ok"]
    parts = {p["ref"]: p for p in store.load_sheet(empty, "01")["parts"]}
    assert parts["U1"]["pins_source"] == "agent"
    assert "pins_source" not in parts["R1"]
    lines = {l["key"]: l for l in store.bom(empty)}
    assert lines["U1"]["pins_status"] == "unverified" and lines["R1"]["pins_status"] == ""


def test_datasheet_then_verify_clears_the_mark(empty):
    _sheet(empty)
    _datasheet(empty, "1 VCC 2 GND")
    assert [u["line"] for u in store.unverified_parts(empty)] == []     # found the datasheet and verified
    assert store.load_sheet(empty, "01")["parts"][0]["pins_source"] == "datasheet"
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "verified"


def test_conflicting_datasheet_raises_a_finding_and_accept_resolves_it(empty):
    _sheet(empty)
    _datasheet(empty, "1 VDD 2 GND")
    item = store.unverified_parts(empty)[0]
    assert item["status"] == "mismatch" and "VCC" in item["issues"]
    store.accept_pins(empty, "U1")
    assert store.unverified_parts(empty) == []
    assert store.load_sheet(empty, "01")["parts"][0]["pins_source"] == "student"


def test_final_checks_list_unverified_parts(empty):
    _sheet(empty)
    out = store.unverified_parts(empty)
    assert [(u["line"], u["status"]) for u in out] == [("U1", "unverified")]
    store.accept_pins(empty, "U1")
    assert store.unverified_parts(empty) == []


def test_unverified_badge_in_the_schematic(empty):
    import render_sheet
    _sheet(empty)
    svg = render_sheet.render_sheet(store.load_sheet(empty, "01"), store.bom_lines(empty))
    assert svg.count("add the datasheet to verify") == 1


def _jd_sheet(empty, d_names=("A", "K")):
    _add(empty, "J1", "USB-C-16P")
    _add(empty, "D1", "LED0603")
    _add(empty, "R1", "RC0603")
    pins = lambda a, b: [{"num": "1", "name": a, "net": "N1"}, {"num": "2", "name": b, "net": "GND"}]
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "J1", "section": "A", "pins": pins("VBUS", "GND")},
        {"ref": "D1", "section": "A", "pins": pins(*d_names)},
        {"ref": "R1", "section": "A", "pins": pins("1", "2")}]}
    assert store.write_sheet(empty, "01", sheet)["ok"]


def _symbol(empty, names):
    import partlib
    lib = partlib.library_dir(empty)
    (lib / "build").mkdir(parents=True, exist_ok=True)
    (lib / "manifest.json").write_text('{"D1": {"symbol": "LED-SYM"}}', encoding="utf-8")
    pins = "".join(f"PIN|{i}|{n}|eElectricPassive|0|0|0|1|100\n" for i, n in enumerate(names, 1))
    (lib / "build" / "symbols_spec.txt").write_text(f"SYMBOL|LED-SYM|x|1\n{pins}", encoding="cp1252")


def test_connector_and_led_without_datasheet_are_listed_resistor_is_not(empty):
    _jd_sheet(empty)
    out = {u["line"]: u for u in store.unverified_parts(empty)}
    assert set(out) == {"J1", "D1"} and out["J1"]["status"] == out["D1"]["status"] == "unverified"
    assert "no datasheet" in out["J1"]["issues"] and "polarity" in out["D1"]["issues"]
    assert "library symbol" not in out["D1"]["issues"]


def test_led_polarity_matching_the_library_symbol_is_worded_precisely(empty):
    _jd_sheet(empty)
    _symbol(empty, ["A", "K"])
    d1 = {u["line"]: u for u in store.unverified_parts(empty)}["D1"]
    assert "match the library symbol LED-SYM" in d1["issues"] and "no datasheet" in d1["issues"]
    _symbol(empty, ["K", "A"])                     # swapped numbers: no claim of a match
    assert "match the library symbol" not in {u["line"]: u for u in store.unverified_parts(empty)}["D1"]["issues"]


def test_accepting_clears_connector_and_led(empty):
    _jd_sheet(empty)
    store.accept_pins(empty, "J1")
    store.accept_pins(empty, "D1")
    assert store.unverified_parts(empty) == []


def test_diode_never_runs_the_datasheet_text_check(empty):
    import verify_part
    store.propose_bom(empty, "D1", {"mpn": "LED-RED", "refs": ["D1"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    before = len(store.library_log(empty)) if hasattr(store, "library_log") else None
    r = verify_part.verify(empty, "D1")
    assert r["verify"] == "unchecked"
    assert (store.library_parts(empty).get("D1") or {}).get("verify") is None


def test_connector_with_datasheet_stays_unverified_until_verified():
    line = {"refs": ["J1"], "key": "J1", "datasheet": "usb.pdf"}
    assert store.pins_status(line, {"verify": "unchecked"})[0] == "unverified"
    assert store.pins_status(line, {"verify": "pass"})[0] == ""
    assert store.pins_status(line, {"pins_accepted": True})[0] == ""
