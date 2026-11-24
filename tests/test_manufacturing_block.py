"""The manufacturing gate (owner decisions 16/11 and 24/11/2026): unverified or conflicting pins are a WARNING that names the parts
(never a block); a board with unrouted nets, or never routed or checked, IS blocked, with the open nets, the DRC Un-Routed count and one
next step. The bridge and the zip are faked: nothing here touches Altium."""
import json
import pathlib
import re

import pytest

import jlc_upload
import serve
import store
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _datasheet, _jd_sheet, _sheet

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def made(monkeypatch):
    """What the faked outputs were asked to make."""
    seen = []
    monkeypatch.setattr(bridge, "run_outjob", lambda p: seen.append("outjob") or {"files": ["a.GTL"], "added": False, "warnings": []})
    monkeypatch.setattr(jlc_upload, "gerber_zip", lambda p: seen.append("zip") or {"zip": "x.zip", "files": ["a.GTL"], "missing": [], "warnings": []})
    return seen


def _both(server, empty):
    return [call(server, "POST", "/api/altium/run-outjob", empty, {}), call(server, "POST", "/api/jlc/gerber-zip", empty, {})]


def test_outjob_and_zip_are_not_refused_for_unverified_pins_they_warn_and_name_the_part(server, empty, made):
    _sheet(empty)
    assert store.manufacturing_block(empty) == ""
    for code, body in _both(server, empty):
        assert code == 200
        assert "U1" in body["pins_warning"] and body["warnings"][0] == body["pins_warning"]
        assert "the outputs are still made" in body["pins_warning"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.run_outjob"}, {"type": "jlc.gerber_zip"}])
    assert len(applied) == 2 and not refused and all("WARNING: Warning" in a and "U1" in a for a in applied)
    assert made == ["outjob", "zip", "outjob", "zip"]


def test_the_warning_lists_every_part_and_splits_unverified_from_conflicting(empty, monkeypatch):
    _jd_sheet(empty)
    msg = store.pins_warning(empty)
    assert msg.startswith("Warning (the outputs are still made): 2 parts have pins nobody checked against a datasheet: ") and "J1" in msg and "D1" in msg
    rows = [{"line": "U1", "refs": ["U1"], "mpn": "", "status": "unverified", "issues": ""},
            {"line": "U2", "refs": ["U2"], "mpn": "", "status": "mismatch", "issues": "x"}]
    monkeypatch.setattr(store, "unverified_parts", lambda project, verify_new=True: rows)
    msg = store.pins_warning(empty)
    assert "1 part has pins nobody checked against a datasheet: U1; 1 part has pins that differ from the datasheet: U2." in msg
    assert store.manufacturing_warning(empty) == "" and store.manufacturing_block(empty) == ""


def test_the_warning_goes_into_the_order_manifest(empty):
    import json

    import pin_decisions
    _sheet(empty)
    path = pathlib.Path(pin_decisions.write_manifest(empty))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "U1" in doc["warning"] and [r["line"] for r in doc["unverified"]] == ["U1"]
    store.accept_pins(empty, "U1")
    assert json.loads(pathlib.Path(pin_decisions.write_manifest(empty)).read_text(encoding="utf-8"))["warning"] == ""


def test_accepting_clears_the_warning_and_the_endpoint_resolves_a_part(server, empty, made):
    _jd_sheet(empty)                 # D1 is polarised: only the student's accept clears it
    assert store.pins_warning(empty)
    assert call(server, "POST", "/api/altium/run-outjob", empty, {})[0] == 200
    for key in ("J1", "D1"):
        assert call(server, "POST", "/api/pins/accept", empty, {"line": key})[0] == 200
    assert store.pins_warning(empty) == ""


def test_dnp_lines_are_left_out_of_the_warning(server, empty, made):
    _sheet(empty)
    store.edit_bom(empty, "U1", "dnp", True)
    assert store.pins_warning(empty) == ""
    assert call(server, "POST", "/api/altium/run-outjob", empty, {})[0] == 200


def test_the_agent_cannot_accept_on_the_students_behalf(empty):
    _sheet(empty)
    assert serve._agent_may_set_library({"pins_accepted": True, "accepted": True, "verify": "pass", "footprint": "F"}) == {"footprint": "F"}
    serve.apply_actions(empty, [{"type": "library.add", "line": "U1", "changes": {"pins_accepted": True, "accepted": True, "verify": "pass"}}])
    assert not store.library_parts(empty).get("U1", {}).get("pins_accepted")
    assert "U1" in store.pins_warning(empty)


# ---- E1: the board gate (unrouted nets), read from board-log.jsonl

def _log(empty, op, drc=None, summary=None, ok=True):
    """A board-log record, as board_results.record writes it (the PcbDoc hash left empty: then lineage finds no linked PcbDoc)."""
    store.append(empty, "board-log.jsonl", {"ts": store.now_ms(), "op": op, "ok": ok, "pcb": "", "pcb_sha256": "", "drc": drc,
                                            "summary": summary or {}, "warnings": []})


def _fresh(monkeypatch):
    import board_results
    monkeypatch.setattr(board_results, "_stale", lambda project, rec: False)


@pytest.mark.route_gate
def test_a_board_never_routed_or_checked_is_not_ready(server, empty, made):
    msg = store.route_block(empty)
    assert msg.startswith("Not made yet: the board was never checked") and "Route board" in msg and "Check board" in msg
    for code, body in _both(server, empty):
        assert code == 400 and "Route board" in body["error"] and "never checked" in body["error"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.run_outjob"}, {"type": "jlc.gerber_zip"}])
    assert not applied and len(refused) == 2 and all("never checked" in r for r in refused)
    assert made == []


@pytest.mark.route_gate
def test_unrouted_nets_block_with_the_open_nets_the_drc_count_and_one_next_step(server, empty, made, monkeypatch):
    _fresh(monkeypatch)
    _log(empty, "route", summary={"routed": 3, "failed": 4, "tracks": 0, "vias": 0, "open_nets": ["NET1", "NET2", "NET3", "NET4", "NET5", "NET6", "NET7"]})
    _log(empty, "drc", drc={"rules": {"Un-Routed Net Constraint": 234}, "total": 370, "unrouted": 234, "clean": False, "complete": True, "violations": []})
    msg = store.manufacturing_block(empty)
    assert "DRC Un-Routed 234" in msg and "NET1, NET2, NET3, NET4, NET5, NET6 ..." in msg and "7 open" in msg
    assert msg.count("Next:") == 1 and "Route board" in msg and "Check board" in msg
    for code, body in _both(server, empty):
        assert code == 400 and "DRC Un-Routed 234" in body["error"]
    assert made == []


@pytest.mark.route_gate
def test_a_routed_and_clean_board_is_ready_and_a_stale_check_is_not(server, empty, made, monkeypatch):
    import board_results
    _fresh(monkeypatch)
    _log(empty, "route", summary={"routed": 9, "failed": 0, "tracks": 80, "vias": 4, "open_nets": []})
    _log(empty, "drc", drc={"rules": {"Clearance Constraint": 0}, "total": 0, "unrouted": 0, "clean": True, "complete": True, "violations": []})
    assert store.route_block(empty) == ""
    assert [c for c, _ in _both(server, empty)] == [200, 200]
    monkeypatch.setattr(board_results, "_stale", lambda project, rec: True)          # the PcbDoc changed since the check
    assert "changed since its last check" in store.route_block(empty)


@pytest.mark.route_gate
def test_an_incomplete_check_is_not_ready(empty, monkeypatch):
    _fresh(monkeypatch)
    _log(empty, "drc", drc={"rules": {"Clearance Constraint": 0}, "total": 0, "unrouted": 0, "clean": False, "complete": False, "violations": []})
    assert "not read in full" in store.route_block(empty)


@pytest.mark.route_gate
def test_the_agent_context_carries_the_same_reason_as_the_banner(empty, monkeypatch):
    import agent
    import model
    _fresh(monkeypatch)
    _log(empty, "drc", drc={"rules": {"Un-Routed Net Constraint": 5}, "total": 5, "unrouted": 5, "clean": False, "complete": True, "violations": []})
    m = model.build(project=empty)
    outputs = next(x for x in m["stages"] if x["id"] == "outputs")
    assert outputs["gate"]["blocked"] and outputs["gate"]["page"] == "pcb" and "DRC Un-Routed 5" in outputs["gate"]["why"]
    state = json.loads(agent._summary(m))
    assert state["outputs_blocked"] == outputs["gate"]["why"] == store.manufacturing_block(empty)


def test_the_unverified_list_has_a_confirm_button_per_part():
    js = (REPO / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    pins = (REPO / "ui" / "js" / "views" / "pins.js").read_text(encoding="utf-8")
    assert "act: 'confirm-pins', line: l.key" in js and "'/api/pins/confirm', {line: key" in pins
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", pins, flags=re.S).lower()   # comments may describe the record shape
    # low friction: no reason input and no length rule anywhere in the flow (showing an old note is fine)
    assert not re.search(r"<(input|textarea)[^>]*reason|reason[^\n]{0,40}\.length|reason\s*\.\s*trim", code)
    assert "rows.map(item)" in js     # every row, a mismatch included, comes from the one template that holds the button


def test_a_block_never_runs_the_verification(empty, monkeypatch):
    import verify_part
    _sheet(empty)
    _datasheet(empty, ["1 VCC Supply", "2 GND Ground"])
    monkeypatch.setattr(verify_part, "verify", lambda *a, **k: pytest.fail("a click on an output must not verify"))
    monkeypatch.setattr(store, "auto_attach", lambda *a, **k: pytest.fail("a click on an output must not attach"))
    assert "U1" in store.pins_warning(empty)
