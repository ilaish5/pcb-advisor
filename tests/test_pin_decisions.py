"""Pin decisions (stream W2-B): "Accept as is" is a record with a basis and a fingerprint, it can be revoked, it lapses when the
pins change, and a legacy accept is grandfathered. Ledger rows 13-18, 20, 21."""
import json

import pytest

import pin_decisions
import serve
import sources
import store
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _add, _datasheet, _jd_sheet, _sheet


def _log(empty):
    return [json.loads(l) for l in (store.pdir(empty) / "library-log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _decisions(empty, key="U1"):
    return [e for e in _log(empty) if e.get("line") == key and "pin_decision" in (e.get("changes") or {})]


def _redraw(empty, name="VCC", net=None):
    """Rename U1's pin 1 (a pin change), or with net= only rewire it (not a pin change)."""
    sheet = store.load_sheet(empty, "01")
    for p in sheet["parts"]:
        if p["ref"] == "U1":
            if net is None:
                p["pins"][0]["name"] = name
            else:
                p["pins"][0]["net"] = net
    store.write_sheet(empty, "01", sheet)


def test_accept_records_basis_evidence_and_needs_no_reason(empty):
    _sheet(empty)
    r = pin_decisions.accept(empty, "U1")
    assert r["changed"] and r["decision"]["basis"] == "blind" and r["decision"]["reason"] == ""
    assert store.unverified_parts(empty) == [] and not store.manufacturing_warning(empty)
    assert store.bom(empty)[0]["pin_decision"]["basis"] == "blind" or any(l["pin_decision"] for l in store.bom(empty))
    pin_decisions.revoke(empty, "U1")
    r = pin_decisions.accept(empty, "U1", evidence=[{"doc": "x.pdf", "sha256": "ab", "page": 4}])
    assert r["decision"]["basis"] == "datasheet_page" and r["decision"]["evidence"][0]["page"] == 4


def test_polarity_basis_for_a_diode_without_a_page(empty):
    _jd_sheet(empty)
    assert pin_decisions.accept(empty, "D1")["decision"]["basis"] == "polarity"


def test_double_accept_is_idempotent(empty):
    _sheet(empty)
    pin_decisions.accept(empty, "U1")
    again = pin_decisions.accept(empty, "U1")
    assert again["changed"] is False
    assert len(_decisions(empty)) == 1


def test_rewiring_or_marking_nc_keeps_the_decision(empty):
    _sheet(empty)
    sheet = store.load_sheet(empty, "01")
    sheet["parts"][0]["pins"].append({"num": "3", "name": "EN", "net": ""})   # an open pin
    store.write_sheet(empty, "01", sheet)
    pin_decisions.accept(empty, "U1")
    _redraw(empty, net="+5V")                                                # moved to another net
    assert store.unverified_parts(empty) == []
    store.mark_pins_nc(empty)                                                # the open pin becomes NC
    sheet = store.load_sheet(empty, "01")
    sheet["parts"][0]["pins"].append({"num": "4", "name": "IO9", "net": "NC"})  # an unlisted pin added as NC
    store.write_sheet(empty, "01", sheet)
    assert store.unverified_parts(empty) == []
    sheet["parts"][0]["pins"][-1]["net"] = "+3V3"                              # wiring it is a pin change
    store.write_sheet(empty, "01", sheet)
    assert [u["line"] for u in store.unverified_parts(empty)] == ["U1"]


def test_a_changed_pin_or_mpn_ends_the_decision(empty):
    _sheet(empty)
    pin_decisions.accept(empty, "U1")
    assert store.unverified_parts(empty) == []
    _redraw(empty, "VDD")
    row = store.unverified_parts(empty)[0]
    assert row["status"] == "unverified" and "accepted on" in row["issues"] and "pins changed since" in row["issues"]
    assert store.manufacturing_warning(empty)
    pin_decisions.accept(empty, "U1")                       # decided again against the new pins
    assert store.unverified_parts(empty) == []
    store.propose_bom(empty, "U1", {"mpn": "OTHER9999"})
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    assert [u["line"] for u in store.unverified_parts(empty)] == ["U1"]


def test_revoke_closes_the_gate_again_and_is_idempotent(empty):
    _sheet(empty)
    pin_decisions.accept(empty, "U1")
    assert pin_decisions.revoke(empty, "U1")["changed"] is True
    assert pin_decisions.revoke(empty, "U1")["changed"] is False
    assert store.manufacturing_warning(empty)
    assert store.load_sheet(empty, "01")["parts"][0]["pins_source"] == "agent"


def test_a_legacy_accept_is_grandfathered_until_the_pins_change(empty):
    _sheet(empty)
    store.add_library(empty, "U1", {"pins_accepted": True}, by="student")
    assert store.unverified_parts(empty) == []              # no forced re-confirm
    store.bom(empty)                                        # the read stamps the fingerprint once
    assert _decisions(empty)[0]["changes"]["pin_decision"]["basis"] == "legacy"
    store.bom(empty)
    assert len(_decisions(empty)) == 1
    assert store.bom(empty)[0]["pin_decision"]["basis"] == "legacy"
    _redraw(empty, "VDD")
    assert [u["line"] for u in store.unverified_parts(empty)] == ["U1"]
    assert pin_decisions.revoke(empty, "U1")["changed"] is True


def test_no_decision_survives_a_pin_change_property(empty):
    _sheet(empty)
    seen = {pin_decisions.fingerprint(empty, "U1")}
    for i, name in enumerate(["V5", "VX", "VCC"]):          # VCC is the first one again: same pins, same fingerprint
        _redraw(empty, name)
        seen.add(pin_decisions.fingerprint(empty, "U1"))
    assert len(seen) == 3
    sheet = store.load_sheet(empty, "01")
    sheet["parts"][0]["pins"][0]["name"] = "VDD"
    store.write_sheet(empty, "01", sheet)
    assert pin_decisions.fingerprint(empty, "U1") not in seen


def test_the_agent_cannot_write_a_decision(empty):
    _sheet(empty)
    dec = {"status": "accepted", "basis": "blind", "fingerprint": pin_decisions.fingerprint(empty, "U1")}
    serve.apply_actions(empty, [{"type": "library.add", "line": "U1", "changes": {"pin_decision": dec, "pins_accepted": True}}])
    assert "pin_decision" not in store.library_parts(empty).get("U1", {})
    assert store.manufacturing_warning(empty)


def test_simple_passives_are_never_asked(empty):
    _sheet(empty)
    assert all(r["line"] != "R1" for r in pin_decisions.remaining(empty))
    assert pin_decisions.confirm_data(empty, "R1")["status"] == ""


def test_accept_all_remaining_is_one_call_and_skips_conflicts(empty):
    _jd_sheet(empty)
    _add(empty, "U1", "ABCD1234")
    sheet = store.load_sheet(empty, "01")
    sheet["parts"].append({"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}]})
    store.write_sheet(empty, "01", sheet)
    _datasheet(empty, ["1 VIN Supply", "2 GND Ground"])
    store.unverified_parts(empty)                           # U1 now conflicts with its datasheet
    todo = {r["line"] for r in pin_decisions.remaining(empty)}
    assert todo == {"J1", "D1"}
    assert set(pin_decisions.accept_all(empty)["accepted"]) == {"J1", "D1"}
    assert [u["line"] for u in store.unverified_parts(empty)] == ["U1"]
    assert pin_decisions.remaining(empty) == []


def test_flagging_a_pin_wrong_is_a_conflict_not_an_accept(empty):
    _sheet(empty)
    r = pin_decisions.accept(empty, "U1", wrong=["2"])
    assert r["decision"] is None
    row = store.unverified_parts(empty)[0]
    assert row["status"] == "mismatch" and "pin 2" in row["issues"]


def test_confirm_data_offers_the_pin_table_pages(empty):
    _sheet(empty)
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 x")
    (folder / "ABCD1234.pdf.txt").write_text("ABCD1234 features\fblock diagram\fPin Configuration and Functions\n1 VCC\n2 GND\n", encoding="utf-8")
    d = pin_decisions.confirm_data(empty, "U1")
    assert d["docs"][0]["candidate_pages"] == [3] and d["docs"][0]["url"] == "/api/source/ABCD1234.pdf"
    assert [(p["num"], p["name"]) for p in d["pins"]] == [("1", "VCC"), ("2", "GND")]


def test_a_linked_datasheet_with_no_file_is_not_offered_as_a_page(empty):
    """A sidecar-only record (the BOM names a datasheet whose file never came) must not give the dialog an iframe that 404s,
    and a page of it is never evidence."""
    _sheet(empty)
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "gone.pdf.json").write_text('{"name": "gone.pdf", "note": "sidecar only"}', encoding="utf-8")
    store.edit_bom(empty, "U1", "datasheet", "gone.pdf")
    d = pin_decisions.confirm_data(empty, "U1")
    assert d["docs"] == [] and d["missing_doc"] == "gone.pdf"
    (folder / "ABCD1234_datasheet.pdf").write_bytes(b"%PDF-1.4 x")                     # the same part's document is here: it stands in
    (folder / "ABCD1234_datasheet.pdf.txt").write_text("ABCD1234 datasheet\fPin Functions\n1 VCC\n", encoding="utf-8")   # its text is cached: no PDF extraction in the test
    d = pin_decisions.confirm_data(empty, "U1")
    assert d["docs"][0]["name"] == "ABCD1234_datasheet.pdf" and d["missing_doc"] == ""
    r = pin_decisions.accept(empty, "U1", evidence=[{"doc": "gone.pdf", "sha256": "", "page": 3}])
    assert r["decision"]["evidence"] == [] and r["decision"]["basis"] != "datasheet_page"


def test_routes_confirm_revoke_and_accept_all(server, empty):
    _sheet(empty)
    code, body = call(server, "GET", "/api/pins/confirm-data?line=U1", empty)
    assert code == 200 and body["line"] == "U1"
    assert call(server, "GET", "/api/pins/confirm-data?line=NOPE", empty)[0] == 404
    assert call(server, "POST", "/api/pins/confirm", empty, {})[0] == 400
    assert call(server, "POST", "/api/pins/confirm", empty, {"line": "NOPE"})[0] == 404
    code, body = call(server, "POST", "/api/pins/confirm", empty, {"line": "U1"})      # no reason, no ticks
    assert code == 200 and body["decision"]["basis"] == "blind"
    assert call(server, "POST", "/api/pins/revoke", empty, {"line": "U1"})[1]["changed"] is True
    assert call(server, "POST", "/api/pins/accept-all", empty, {})[0] == 400           # one explicit confirm
    code, body = call(server, "POST", "/api/pins/accept-all", empty, {"confirm": True})
    assert code == 200 and body["accepted"] == ["U1"]
    assert store.unverified_parts(empty) == []


def test_the_model_lists_accepted_risks_and_what_remains(empty):
    import model
    _sheet(empty)
    assert [r["line"] for r in model.build(empty)["pin_decisions"]["remaining"]] == ["U1"]
    pin_decisions.accept(empty, "U1")
    out = model.build(empty)["pin_decisions"]
    assert out["remaining"] == [] and out["accepted"][0]["line"] == "U1" and out["accepted"][0]["basis"] == "blind"


@pytest.mark.parametrize("text,state", [("", "none"), ("The device pin table 引脚 功能 说明 " * 40, "poor"),
                                         ("ABCD1234 pin configuration. " * 20, "good")])
def test_source_quality_states(text, state):
    assert sources.quality(text)["state"] == state


def test_a_chinese_datasheet_is_never_a_verification(empty):
    _sheet(empty)
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 x")
    (folder / "ABCD1234.pdf.txt").write_text("ABCD1234 数据手册 引脚 说明 电源 地 " * 30 + "\n1 VCC\n2 GND\n", encoding="utf-8")
    row = store.unverified_parts(empty)[0]
    assert row["status"] == "unverified" and "mostly Chinese" in row["issues"]


def test_an_empty_extraction_is_not_cached_and_the_list_says_not_read(empty, tmp_path, monkeypatch):
    import subprocess
    # pypdf cannot read this file; pdftotext (when installed) reads a scan as no text. Stubbed, so the test does not depend on
    # poppler being on the machine (a missing pdftotext raises instead: tests/test_sources.py)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""))
    folder = sources.folder_of(empty)
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 not really")
    assert sources.text_state(pdf) == "not_read"
    assert sources.text_of("scan.pdf", folder) == "" and not (folder / "scan.pdf.txt").exists()
    (folder / "scan.pdf.txt").write_text("", encoding="utf-8")
    assert sources.text_state(pdf) == "none"


def test_accepted_connector_and_led_show_as_accepted_risk_never_datasheet(empty):
    _jd_sheet(empty)
    pin_decisions.accept_all(empty)
    lines = {l["key"]: l for l in store.bom(empty)}
    for k in ("J1", "D1"):
        assert lines[k]["pins_status"] == "accepted" and lines[k]["pin_decision"]
    assert {r["line"] for r in pin_decisions.risks(empty)} == {"J1", "D1"}
    src = {p["ref"]: p.get("pins_source") for p in store.load_sheet(empty, "01")["parts"]}
    assert src["J1"] == src["D1"] == "student" and src["R1"] is None
    assert json.loads(open(pin_decisions.write_manifest(empty), encoding="utf-8").read())["accepted_risks"]
    pin_decisions.revoke(empty, "J1")
    assert [r["line"] for r in pin_decisions.risks(empty)] == ["D1"]


def test_order_manifest_follows_accept_revoke_and_the_board_check(empty, monkeypatch):
    import board_results
    _jd_sheet(empty)
    path = store.pdir(empty) / "exports" / "empty_order_manifest.json"
    read = lambda: json.loads(path.read_text(encoding="utf-8"))
    pin_decisions.accept(empty, "J1")
    assert [r["line"] for r in read()["accepted_risks"]] == ["J1"] and [u["line"] for u in read()["unverified"]] == ["D1"]
    pin_decisions.revoke(empty, "J1")
    assert read()["accepted_risks"] == [] and {u["line"] for u in read()["unverified"]} == {"J1", "D1"}
    monkeypatch.setattr(board_results, "latest", lambda p: {"board_check": {"total": 3, "stale": False}})
    pin_decisions.write_manifest(empty)
    assert read()["board_check"]["board_check"]["total"] == 3
    monkeypatch.setattr(board_results, "latest", lambda p: {"board_check": {"total": 0, "stale": False}})
    pin_decisions.write_manifest(empty)
    assert read()["board_check"]["board_check"]["total"] == 0              # only the board check changed: still rewritten
