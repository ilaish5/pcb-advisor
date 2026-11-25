"""One decision per identical part, the waiting summary the Library / DFM / Outputs pages read, the datasheet fetch the system does by
itself, and the per-project count script. Grouping never changes what is recorded: each line keeps its own fingerprint and decision."""
import json
import pathlib
import sys

import pin_decisions
import pin_model
import sources
import store
from test_pin_model import _bom, _draw, _library
from test_unverified_pins import _datasheet, _sheet

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI = ROOT / "ui" / "js" / "views"


def _led(empty, key, mpn="LED0805", package="0805"):
    store.propose_bom(empty, key, {"mpn": mpn, "refs": [key], "package": package}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")


def _leds(empty, nets, **kw):
    """D1.. each an LED on its own net, pins named A / K: `nets` = {ref: anode net}."""
    for ref in nets:
        _led(empty, ref, **kw)
    _draw(empty, {ref: [("1", "A", net), ("2", "K", "GND")] for ref, net in nets.items()})


def _decisions(empty):
    log = [json.loads(l) for l in (store.pdir(empty) / "library-log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return {e["line"]: e["changes"]["pin_decision"] for e in log if "pin_decision" in (e.get("changes") or {})}


# ---------------------------------------------------------------- grouping

def test_identical_leds_on_different_nets_are_one_question(empty):
    _leds(empty, {"D1": "N1", "D2": "N2", "D3": "N3"})
    qs = pin_decisions.questions(empty)
    assert len(qs) == 1 and qs[0]["count"] == 3 and sorted(qs[0]["refs"]) == ["D1", "D2", "D3"]
    assert qs[0]["kind"] == "polarised" and not qs[0]["own_look"] and not qs[0]["blind"]
    assert pin_decisions.group_lines(empty, "D2")[0] == "D2" and sorted(pin_decisions.group_lines(empty, "D2")) == ["D1", "D2", "D3"]


def test_a_copy_wired_differently_or_with_another_mpn_gets_its_own_question(empty):
    _leds(empty, {"D1": "N1", "D2": "N2"})
    _led(empty, "D3", mpn="OTHER")
    _led(empty, "D4")
    sheet = store.load_sheet(empty, "01")
    sheet["parts"] += [{"ref": "D3", "section": "A", "pins": [{"num": "1", "name": "A", "net": "N3"}, {"num": "2", "name": "K", "net": "GND"}]},
                       {"ref": "D4", "section": "A", "pins": [{"num": "1", "name": "A", "net": "N4"}, {"num": "2", "name": "K", "net": ""}]}]
    assert store.write_sheet(empty, "01", sheet)["ok"]
    qs = {tuple(sorted(q["refs"])) for q in pin_decisions.questions(empty)}
    assert qs == {("D1", "D2"), ("D3",), ("D4",)}


def test_a_part_with_no_mpn_or_footprint_is_never_grouped(empty):
    for ref in ("D1", "D2"):
        store.propose_bom(empty, ref, {"mpn": "", "refs": [ref]}, new=True)
        store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    _draw(empty, {"D1": [("1", "A", "N1"), ("2", "K", "GND")], "D2": [("1", "A", "N2"), ("2", "K", "GND")]})
    assert all(pin_decisions.group_key(empty, k) is None for k in ("D1", "D2"))
    assert len(pin_decisions.questions(empty)) == 2


def test_a_mismatch_is_never_grouped_and_never_in_the_bulk(empty):
    _library(empty, {"D1": "C34499", "D2": "C34499"})
    _bom(empty, "D1", "C34499")
    _bom(empty, "D2", "C34499")
    _draw(empty, {"D1": [("1", "K", "GND"), ("2", "A", "N1")],            # swapped against the library: 1 = A there
                  "D2": [("1", "A", "N2"), ("2", "K", "GND")]})           # as the library has it: verified by it
    w = pin_decisions.waiting(empty)
    assert w["own_look"] == 1 and w["questions"] == 1 and w["bulk"] == [] and w["auto_verified"] == 1
    assert w["groups"][0]["refs"] == ["D1"] and w["groups"][0]["own_look"]


def test_accepting_one_of_a_group_records_a_decision_for_each_with_its_own_fingerprint(empty):
    _leds(empty, {"D1": "N1", "D2": "N2", "D3": "N3"})
    r = pin_decisions.accept(empty, "D1", group=True)
    assert r["ok"] and store.unverified_parts(empty) == []
    dec = _decisions(empty)
    assert set(dec) == {"D1", "D2", "D3"}
    assert all(d["basis"] == "polarity" for d in dec.values())
    assert len({d["fingerprint"] for d in dec.values()}) == 3              # the polarity nets differ: one record each, never one shared
    # a later change of one copy lapses only that copy's decision
    sheet = store.load_sheet(empty, "01")
    for p in sheet["parts"]:
        if p["ref"] == "D2":
            p["pins"][0]["name"], p["pins"][1]["name"] = "K", "A"
    store.write_sheet(empty, "01", sheet)
    assert [u["line"] for u in store.unverified_parts(empty)] == ["D2"]


def test_accepting_without_group_decides_only_that_line(empty):
    _leds(empty, {"D1": "N1", "D2": "N2"})
    pin_decisions.accept(empty, "D1")
    assert [u["line"] for u in store.unverified_parts(empty)] == ["D2"]


# ---------------------------------------------------------------- the waiting summary and the bulk

def test_waiting_summary_counts_groups_names_blind_ics_and_leaves_no_mismatch_in_the_bulk(empty):
    _sheet(empty)                                                      # U1 (an IC, no datasheet) and R1
    for ref in ("D1", "D2"):
        _led(empty, ref)
    sheet = store.load_sheet(empty, "01")
    sheet["parts"] += [{"ref": r, "section": "A", "pins": [{"num": "1", "name": "A", "net": n}, {"num": "2", "name": "K", "net": "GND"}]}
                       for r, n in (("D1", "N1"), ("D2", "N2"))]
    assert store.write_sheet(empty, "01", sheet)["ok"]
    w = pin_decisions.waiting(empty)
    assert w["questions"] == 2 and w["lines"] == 3 and w["own_look"] == 0
    assert sorted(w["bulk"]) == ["D1", "D2", "U1"] and w["blind"] == ["U1"]
    model = pin_decisions._model(empty, {})["pin_decisions"]["waiting"]
    assert model["questions"] == 2


def test_confirm_all_settles_every_question_that_is_not_a_mismatch(empty):
    _leds(empty, {"D1": "N1", "D2": "N2"})
    w = pin_decisions.waiting(empty)
    r = pin_decisions.accept_all(empty, w["bulk"])
    assert sorted(r["accepted"]) == ["D1", "D2"] and store.unverified_parts(empty) == []
    assert pin_decisions.waiting(empty)["questions"] == 0
    assert set(_decisions(empty)) == {"D1", "D2"}


def test_a_part_the_library_verified_is_not_waiting_and_is_listed_in_the_order_manifest(empty):
    _library(empty, {"D1": "C84256"})
    _bom(empty, "D1", "C84256")
    _draw(empty, {"D1": [("2", "+", "N1"), ("1", "-", "GND")]})
    w = pin_decisions.waiting(empty)
    assert w["questions"] == 0 and w["auto_verified"] == 1 and w["bulk"] == []
    pin_decisions.write_manifest(empty)
    doc = json.loads((store.pdir(empty) / "exports" / f"{empty}_order_manifest.json").read_text(encoding="utf-8"))
    assert [v["line"] for v in doc["verified_by_library_model"]] == ["D1"]
    assert doc["verified_by_library_model"][0]["basis"] == pin_model.BASIS and doc["unverified"] == []


def test_library_rows_carry_no_pin_button_unless_the_row_needs_its_own_look(empty):
    ok = {"verify": "unchecked", "symbol": "S"}
    assert pin_decisions.row_buttons(ok, {"refs": ["D1"], "pins_status": "unverified", "datasheet": ""}) == 0
    assert pin_decisions.row_buttons(ok, {"refs": ["J1"], "pins_status": "unverified", "datasheet": "x.pdf"}) == 0
    assert pin_decisions.row_buttons(ok, {"refs": ["U1"], "pins_status": "unverified", "datasheet": "x.pdf"}) == 1      # Verify can decide
    assert pin_decisions.row_buttons(ok, {"refs": ["D1"], "pins_status": "mismatch", "datasheet": ""}) == 1             # its own button
    assert pin_decisions.row_buttons({"verify": "pass", "accepted": False, "symbol": "S"}, {}) == 1                      # Accept after a pass


def test_the_waiting_line_is_on_the_bom_dfm_and_outputs_pages():
    bom, pages, checks, outputs, pins = [(UI / f).read_text(encoding="utf-8") for f in ("bom.js", "pages.js", "checks.js", "outputs.js", "pins.js")]
    # the Library page's waiting line moved with its table onto the BOM page, above the table
    top = bom[bom.index("function bomTop"):]
    assert "pinsWaitingBar()" in top[:top.index("\n}")] and "title: 'Library'" not in pages
    assert "dfmWaitingHTML" in checks and "pinsWaitingBar()" in checks
    assert "pinsConfirmAllBtn" in outputs
    assert "Confirm all" in pins and "pins-bar" in pins and "own look" in pins


# ---------------------------------------------------------------- the system fetches datasheets itself

def _with_url(empty, url):
    store.propose_bom(empty, "U1", {"datasheet_url": url}, new=False)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")


def test_a_datasheet_the_supplier_links_is_fetched_linked_and_checked_by_the_system(empty):
    _sheet(empty)
    _with_url(empty, "https://example.test/abcd1234.pdf")
    calls = []

    def getter(project, url, name):
        calls.append((url, name))
        _datasheet(project, ["1 VCC Supply", "2 GND Ground"])
        return {"name": name}

    out = store.fetch_datasheets(empty, getter=getter)
    assert calls == [("https://example.test/abcd1234.pdf", "ABCD1234.pdf")]
    assert [f["line"] for f in out["fetched"]] == ["U1"] and out["fetched"][0]["status"] == "verified" and out["failed"] == []
    line = {l["key"]: l for l in store.bom(empty)}["U1"]
    assert line["datasheet"] == "ABCD1234.pdf" and line["pins_status"] == "verified"


def test_a_failed_download_is_reported_and_the_part_waits_as_before(empty):
    _sheet(empty)
    _with_url(empty, "https://example.test/abcd1234.pdf")

    def getter(project, url, name):
        raise sources.SourceError("the site sent a bot page")

    out = store.fetch_datasheets(empty, getter=getter)
    assert out["fetched"] == [] and out["failed"][0]["refs"] == ["U1"] and "bot page" in out["failed"][0]["why"]
    assert {l["key"]: l for l in store.bom(empty)}["U1"]["pins_status"] == "unverified"


def test_nothing_is_fetched_for_a_passive_a_linked_part_or_a_part_with_no_link(empty):
    _sheet(empty)                                      # U1 has no datasheet_url, R1 is a passive
    calls = []
    out = store.fetch_datasheets(empty, getter=lambda *a: calls.append(a))
    assert calls == [] and out == {"fetched": [], "failed": []}


# ---------------------------------------------------------------- the count script

def test_the_count_script_counts_a_project_the_way_the_page_shows_it(empty, tmp_path, monkeypatch):
    _leds(empty, {"D1": "N1", "D2": "N2", "D3": "N3"})
    sys.path.insert(0, str(ROOT / "tools"))
    import friction_count
    res = friction_count.measure(empty)
    assert res["pin_rows"] == 3 and res["pin_questions"] == 1 and res["pin_own_look"] == 0
    assert res["asks"] <= res["pin_rows"] and res["ui"] == "new"
    out = tmp_path / "counts.json"
    assert friction_count.main(["--home", str(tmp_path / "nowhere"), "--out", str(out)]) == 0      # no projects folder: nothing to count
    assert not out.exists()


# ---------------------------------------------------------------- a part with no wired pin has nothing to decide

def _ics(empty, wired):
    """U1 wired to nets, U7 placed with no pins drawn at all, U8 with its pins listed but on no net, U9 with its pins on NC only."""
    for ref, mpn in (("U1", "ABCD1234"), ("U7", "TPS3823-33DBVR"), ("U8", "EFGH5678"), ("U9", "IJKL9012")):
        store.propose_bom(empty, ref, {"mpn": mpn, "refs": [ref]}, new=True)
        store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    pins = lambda *nets: [{"num": str(i + 1), "name": f"P{i + 1}", "net": n} for i, n in enumerate(nets)]
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": pins("+3V3", "GND") if wired else []},
        {"ref": "U7", "section": "A", "pins": []},
        {"ref": "U8", "section": "A", "pins": pins("", "")},
        {"ref": "U9", "section": "A", "pins": pins("NC", "N/C")}]}
    _put(empty, sheet)


def _put(empty, sheet):
    """The sheet file as an importer writes it: write_sheet refuses a part with no pins, a sheet read from Altium can hold one."""
    path = store.netlist_dir(empty) / "01.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**sheet, "id": "01"}), encoding="utf-8")
    store.refresh_pins_source(empty)


def test_a_part_with_no_wired_pin_is_not_waiting_and_blocks_nothing(empty):
    _ics(empty, wired=True)
    lines = {l["key"]: l for l in store.bom(empty)}
    assert lines["U1"]["pins_status"] == "unverified"
    for key in ("U7", "U8", "U9"):
        assert lines[key]["pins_status"] == "" and lines[key]["on_sheet"]       # on a sheet, but nothing wired: nothing to decide
    assert [r["line"] for r in store.pins_to_resolve(empty)] == ["U1"]
    w = pin_decisions.waiting(empty)
    assert w["questions"] == 1 and w["groups"][0]["refs"] == ["U1"] and w["bulk"] == ["U1"] and w["blind"] == ["U1"]
    assert [r["line"] for r in pin_decisions.remaining(empty)] == ["U1"]
    assert all(w["lib_buttons"].get(k, 0) == 0 for k in ("U7", "U8", "U9"))
    warn = store.pins_warning(empty)
    assert "pins nobody checked against a datasheet: U1" in warn and "U7" not in warn and "U9" not in warn      # a warning, never a block
    msg = store.manufacturing_warning(empty)
    assert "pins nobody checked" not in msg and "U8 pin 1" in msg      # its listed pins are open (no net, no NC): that is the open-pin gate, which stays


def test_only_empty_parts_leave_the_gate_open_and_nothing_to_confirm(empty):
    _ics(empty, wired=False)
    assert store.pins_to_resolve(empty) == [] and pin_decisions.waiting(empty)["questions"] == 0
    assert store.pins_warning(empty) == "" and "pins nobody checked" not in store.manufacturing_warning(empty)
    assert pin_decisions.accept_all(empty)["accepted"] == []


def test_an_empty_part_can_not_be_confirmed_and_wiring_it_later_asks_like_any_other(empty):
    _ics(empty, wired=True)
    r = pin_decisions.accept(empty, "U7", group=True)
    assert r["ok"] is False and r["decision"] is None and "nothing to confirm" in r["why"]
    assert pin_decisions.accept(empty, "U8", wrong=["1"])["ok"] is False
    assert "U7" not in _decisions(empty) and "U8" not in _decisions(empty)
    assert pin_decisions.confirm_data(empty, "U7")["wired"] is False and pin_decisions.confirm_data(empty, "U1")["wired"] is True
    sheet = store.load_sheet(empty, "01")                              # U7 gets wired afterwards
    for p in sheet["parts"]:
        if p["ref"] == "U7":
            p["pins"] = [{"num": "1", "name": "VDD", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}]
    assert store.write_sheet(empty, "01", sheet)["ok"]            # the agent draws the sheet again, now with U7's pins
    assert sorted(r["line"] for r in store.pins_to_resolve(empty)) == ["U1", "U7"]       # asked, with nothing recorded about the empty past
    assert store.load_sheet(empty, "01")["parts"][1]["pins_source"] == "agent"


def test_a_decision_made_with_wired_pins_lapses_when_the_pins_change_and_an_unwired_part_is_not_a_risk(empty):
    _ics(empty, wired=True)
    assert pin_decisions.accept(empty, "U1")["ok"]
    assert [r["line"] for r in pin_decisions.risks(empty)] == ["U1"]
    sheet = store.load_sheet(empty, "01")
    sheet["parts"][0]["pins"] = [{"num": "1", "name": "P1", "net": ""}, {"num": "2", "name": "P2", "net": ""}]    # all unwired now
    _put(empty, sheet)
    assert pin_decisions.risks(empty) == [] and store.pins_to_resolve(empty) == []
    sheet["parts"][0]["pins"] = [{"num": "1", "name": "P1", "net": "+3V3"}, {"num": "2", "name": "P2", "net": "X"}]  # the same pins wired again
    _put(empty, sheet)
    assert [r["line"] for r in pin_decisions.risks(empty)] == ["U1"]       # the decision was about these pins: it stands, as for any net change
    sheet["parts"][0]["pins"] = [{"num": "1", "name": "Q1", "net": "+3V3"}, {"num": "2", "name": "Q2", "net": "X"}]  # other pins
    _put(empty, sheet)
    assert [r["line"] for r in store.pins_to_resolve(empty)] == ["U1"] and pin_decisions.risks(empty) == []


def test_the_confirm_dialog_is_not_opened_for_a_part_with_nothing_wired():
    src = (UI / "pins.js").read_text(encoding="utf-8")
    assert "if (!d.wired)" in src and src.index("if (!d.wired)") < src.index("showModal()")
