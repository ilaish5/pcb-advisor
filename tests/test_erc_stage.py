"""The Schematic page shows Altium's own ERC (Compile) messages, marked as coming from Altium: the erc-log record, the model's S.erc, the
"Check in Altium" step button and its endpoint, and the page wiring. The bridge is faked. A count exists only for a report read in full."""
import pathlib

import pytest

import erc_results
import model
import serve
import store
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_js

ROWS = [{"level": "error", "class": "Error", "document": "A.SchDoc", "message": "Duplicate Component Designators C?", "kind": "Duplicate Component Designators",
         "object": "C?", "location": ""},
        {"level": "warning", "class": "Warning", "document": "A.SchDoc", "message": "Net CS has only one pin (Pin J4-24)", "kind": "Net has only one pin",
         "object": "Pin J4-24", "location": ""}]
FOUND = {"complete": True, "clean": False, "rows": ROWS, "n_errors": 1, "n_warnings": 1, "total": 2, "kinds": {"Net has only one pin": 1,
         "Duplicate Component Designators": 1}, "problems": [], "levels_from": "default", "unsaved": [], "line": "1 error, 1 warning",
         "report": "r.html", "warnings": [], "inputs": {"A.SchDoc": "aa", "(ERC settings)": "ss"}}
CLEAN = {**FOUND, "clean": True, "rows": [], "n_errors": 0, "n_warnings": 0, "total": 0, "kinds": {}, "line": "no violations (clean)"}
PARTLY = {**FOUND, "complete": False, "n_errors": None, "n_warnings": None, "total": None, "kinds": None, "line": "unchecked (the report is cut off)",
          "problems": ["the report is cut off (no closing </html>)"], "warnings": ["Altium's ERC report was not read in full"]}


@pytest.fixture
def linked(tmp_path, monkeypatch):
    prj = tmp_path / "P.PrjPcb"
    prj.write_text("[Design]\n", encoding="utf-8")
    state = {"inputs": {"A.SchDoc": "aa", "(ERC settings)": "ss"}}
    monkeypatch.setattr(erc_results, "_prj", lambda p: str(prj))
    monkeypatch.setattr(bridge, "erc_inputs", lambda p: dict(state["inputs"]))
    monkeypatch.setattr(bridge, "_linked", lambda p: prj)
    return state


# ---------------------------------------------------------------- the record

def test_a_complete_result_is_recorded_and_shown_with_its_counts(empty, linked):
    assert erc_results.public(empty) is None, "never run: nothing is shown as a count"
    rec = erc_results.record(empty, "erc", FOUND)
    assert rec["ok"] and rec["inputs"] == FOUND["inputs"]
    assert store.read_jsonl(store.pdir(empty) / "erc-log.jsonl")[0]["erc"]["errors"] == 1
    pub = erc_results.public(empty)
    assert pub["state"] == "violations" and pub["complete"] is True and pub["stale"] is False
    assert pub["counts"] == {"errors": 1, "warnings": 1, "total": 2} and [r["level"] for r in pub["rows"]] == ["error", "warning"]
    assert pub["line"] == "1 error, 1 warning"


def test_a_clean_report_is_clean_and_a_changed_sheet_makes_it_stale(empty, linked):
    erc_results.record(empty, "erc", CLEAN)
    pub = erc_results.public(empty)
    assert pub["state"] == "clean" and pub["counts"]["total"] == 0 and pub["stale"] is False
    linked["inputs"]["A.SchDoc"] = "changed"
    assert erc_results.public(empty)["stale"] is True
    linked["inputs"] = {"A.SchDoc": "aa", "(ERC settings)": "other settings"}
    assert erc_results.public(empty)["stale"] is True, "the project's ERC settings are part of what the result was made from"


def test_a_report_not_read_in_full_has_no_counts_and_is_never_clean(empty, linked):
    erc_results.record(empty, "erc", PARTLY)
    pub = erc_results.public(empty)
    assert pub["state"] == "unchecked" and pub["counts"] is None and pub["kinds"] is None and pub["rows"] == []
    assert "cut off" in pub["error"] and pub["warnings"] == PARTLY["warnings"]
    stored = store.read_jsonl(store.pdir(empty) / "erc-log.jsonl")[0]["erc"]
    assert stored["errors"] is None and stored["total"] is None and stored["clean"] is False


def test_a_failed_run_is_recorded_as_unchecked_with_the_error_and_replaces_an_older_good_one(empty, linked):
    erc_results.record(empty, "erc", CLEAN)
    erc_results.record(empty, "erc", {}, ok=False, error="Altium cannot run scripts right now")
    pub = erc_results.public(empty)
    assert pub["state"] == "unchecked" and pub["ok"] is False and pub["counts"] is None and pub["error"] == "Altium cannot run scripts right now"
    assert pub["stale"] is False


def test_other_steps_are_not_recorded_and_a_result_that_is_no_check_is_unchecked(empty, linked):
    assert erc_results.record(empty, "drc", FOUND) is None and erc_results.records(empty) == []
    erc_results.record(empty, "erc", {"unexpected": 1})
    pub = erc_results.public(empty)
    assert pub["state"] == "unchecked" and pub["counts"] is None


def test_a_project_that_is_no_longer_linked_makes_the_result_stale(empty, monkeypatch):
    monkeypatch.setattr(erc_results, "_prj", lambda p: "")
    erc_results.record(empty, "erc", CLEAN)
    assert erc_results.public(empty)["stale"] is True


def test_the_model_carries_erc_for_the_page(empty, linked):
    assert model.build(empty)["erc"] is None
    erc_results.record(empty, "erc", FOUND)
    m = model.build(empty)
    assert m["erc"]["counts"]["errors"] == 1 and m["erc"]["state"] == "violations"
    assert m["rev"], "the revision digest includes erc-log.jsonl, so the page redraws"


def test_the_revision_changes_when_a_check_is_recorded(empty, linked):
    import stages
    before = stages.rev(empty)
    erc_results.record(empty, "erc", FOUND)
    assert stages.rev(empty) != before


# ---------------------------------------------------------------- the step button

def test_the_check_schematic_endpoint_runs_the_bridge_and_keeps_the_answer(server, empty, linked, monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "run_erc", lambda p: seen.append(p) or dict(FOUND))
    code, body = call(server, "POST", "/api/altium/erc", empty, {})
    assert code == 200 and seen == [empty]
    assert "1 error, 1 warning" in body["summary"] and body["n_errors"] == 1
    assert erc_results.public(empty)["counts"]["errors"] == 1
    assert not serve.STEP_LOCK.locked()
    monkeypatch.setattr(bridge, "run_erc", lambda p: dict(CLEAN))
    assert call(server, "POST", "/api/altium/erc", empty, {})[0] == 200
    assert erc_results.public(empty)["state"] == "clean"


def test_a_failing_check_is_an_error_answer_and_is_kept_as_unchecked(server, empty, linked, monkeypatch):
    def boom(p):
        raise bridge.BridgeError("Altium ran the Electrical Rules Check but wrote no report file. Nothing is counted as checked.")
    monkeypatch.setattr(bridge, "run_erc", boom)
    code, body = call(server, "POST", "/api/altium/erc", empty, {})
    assert code == 400 and "wrote no report" in body["error"]
    pub = erc_results.public(empty)
    assert pub["state"] == "unchecked" and pub["counts"] is None and "wrote no report" in pub["error"]
    assert not serve.STEP_LOCK.locked()


def test_a_partly_read_report_is_an_answer_whose_summary_says_unchecked(server, empty, linked, monkeypatch):
    monkeypatch.setattr(bridge, "run_erc", lambda p: dict(PARTLY))
    code, body = call(server, "POST", "/api/altium/erc", empty, {})
    assert code == 200 and body["summary"].startswith("Electrical rules check: unchecked") and body["warnings"]
    assert erc_results.public(empty)["counts"] is None


def test_the_check_does_not_touch_the_board_log(server, empty, linked, monkeypatch):
    monkeypatch.setattr(bridge, "run_erc", lambda p: dict(FOUND))
    call(server, "POST", "/api/altium/erc", empty, {})
    assert not (store.pdir(empty) / "board-log.jsonl").exists()


def test_the_step_is_known_to_every_table_of_the_step_machinery():
    assert serve._CONSENT_ACTION["erc"] == "altium.run_erc"
    for table in (serve.STEP_SUMMARY, serve.STEP_NAMES, serve.STEP_NOT_DONE):
        assert "erc" in table
    assert "altium.run_erc" in serve.STEP_LABELS
    assert serve.step_plan.__doc__ and serve.step_refusal(None, "erc") == ""


def test_run_erc_logs_and_keeps_the_report_under_the_project(empty, linked, monkeypatch, tmp_path):
    seen = {}

    def fake(prj, keep):
        seen["keep"] = pathlib.Path(keep)
        return dict(FOUND)
    monkeypatch.setattr(bridge, "erc_check", fake)
    res = bridge.run_erc(empty)
    assert seen["keep"] == store.pdir(empty) / "erc" / "report.html" and res["n_errors"] == 1


# ---------------------------------------------------------------- the page

def test_the_schematic_page_has_the_altium_erc_panel_and_button():
    js = ui_js()
    assert "url: '/api/altium/erc'" in js and "pvStepBtn('erc')" in js and "'Check in Altium'" in js
    assert "function ercHTML" in js and "ercHTML()" in js
    assert "From Altium" in js, "the panel says the messages come from Altium"
    assert "S.erc, S.pin_decisions" in js, "a new result redraws the page"


def test_the_panel_shows_a_count_only_when_the_report_was_read_in_full():
    js = ui_js()
    body = js[js.index("function ercHTML"):js.index("const SCH_LIMITS")]
    assert "if (!e.counts)" in body and "could not be read" in body and "not counted as checked" in body
    assert body.index("if (!e.counts)") < body.index("e.counts.errors"), "the unchecked case is decided before any count is used"
    assert "<summary>Details</summary>" in body and "<b>" in body, "bold title, Details expander"
    assert "banner(" in body, "the one message strip of the app"
    assert "e.stale" in body and "check it again" in body
