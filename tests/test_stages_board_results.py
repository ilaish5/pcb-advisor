"""Stream A slice 1: the board log. Altium's answers (place, route, DRC, outputs) are recorded; the Check board step runs the existing
bridge.run_drc; a changed PcbDoc makes the record stale. The bridge is faked."""
import board_results
import lineage
import pytest
import serve
import store
from altium import bridge
from test_chat_turns import call, server  # noqa: F401

DRC = {"rules": {"Clearance Constraint (Gap=0.127mm) (All),(All)": 21, "Un-Routed Net Constraint": 0}, "violations": ["Clearance: a"], "unrouted": 0,
       "total": 21, "complete": True, "clean": False}
CLEAN = {"rules": {"Clearance Constraint": 0}, "violations": [], "unrouted": 0, "total": 0, "complete": True, "clean": True}
ROUTED = {"summary": "4 nets routed", "warnings": ["w"], "routed": ["A", "B"], "failed": [], "tracks": 9, "vias": 1,
          "drc_rules": {"Clearance Constraint": 0, "Un-Routed Net Constraint": 2}, "drc_total": 2, "drc_clean": False}


@pytest.fixture
def pcb(tmp_path, monkeypatch):
    f = tmp_path / "B.PcbDoc"
    f.write_bytes(b"v1")
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: f)
    monkeypatch.setattr(bridge, "_linked", lambda p: tmp_path / "P.PrjPcb")
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: f)
    return f


def test_record_round_trip_and_stale_when_the_pcb_changes(empty, pcb):
    board_results.record(empty, "route", ROUTED)
    board_results.record(empty, "place", {"placed": ["R1", "C1"], "warnings": []})
    rows = store.read_jsonl(store.pdir(empty) / "board-log.jsonl")
    assert [r["op"] for r in rows] == ["route", "place"]
    r = rows[0]
    assert r["ok"] and r["pcb_sha256"] and r["drc"]["total"] == 2 and r["drc"]["unrouted"] == 2 and r["summary"]["routed"] == 2 and r["warnings"] == ["w"]
    assert rows[1]["summary"] == {"placed": 2} and rows[1]["drc"] is None
    lt = board_results.latest(empty)
    assert lt["route"]["stale"] is False and lt["board_check"]["op"] == "route"
    pcb.write_bytes(b"v2 edited")
    assert board_results.latest(empty)["board_check"]["stale"] is True


def test_a_failed_or_foreign_step_is_not_a_board_check(empty, pcb):
    board_results.record(empty, "route", {}, ok=False, error="boom")
    assert board_results.record(empty, "draw", {}) is None
    lt = board_results.latest(empty)
    assert lt["route"]["ok"] is False and lt["route"]["error"] == "boom" and lt["board_check"] is None


def test_the_check_board_step_runs_the_existing_drc_and_records_the_violations(server, empty, pcb, monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "run_drc", lambda prj, pcb_, report: seen.append((prj.name, pcb_.name, report.name)) or dict(DRC))
    code, body = call(server, "POST", "/api/altium/drc", empty, {})
    assert code == 200 and seen == [("P.PrjPcb", "B.PcbDoc", "drc.txt")]
    assert "21" in body["summary"] and body["total"] == 21
    chk = board_results.latest(empty)["board_check"]
    assert chk["op"] == "drc" and chk["drc"]["violations"] == ["Clearance: a"] and chk["drc"]["total"] == 21 and not chk["drc"]["clean"]
    monkeypatch.setattr(bridge, "run_drc", lambda *a: dict(CLEAN))
    assert call(server, "POST", "/api/altium/drc", empty, {})[0] == 200
    assert board_results.latest(empty)["board_check"]["drc"]["clean"] is True


def test_a_drc_error_is_an_answer_and_logged(server, empty, pcb, monkeypatch):
    def boom(*a):
        raise bridge.BridgeError("Altium did not write the design rule check report.")
    monkeypatch.setattr(bridge, "run_drc", boom)
    code, body = call(server, "POST", "/api/altium/drc", empty, {})
    assert code == 400 and "report" in body["error"]
    assert board_results.latest(empty)["drc"]["ok"] is False and board_results.latest(empty)["board_check"] is None
    assert not serve.STEP_LOCK.locked()


def test_the_chat_path_records_through_the_same_helper(empty, pcb, monkeypatch):
    monkeypatch.setattr(bridge, "route_pcb", lambda p, replace=False, keep_partial=False: dict(ROUTED))
    said = "תנתב אתה את הלוח באלטיום"
    serve.apply_actions(empty, [{"type": "altium.route_pcb", "student_said": said}], last_user=said, chat=[{"role": "user", "text": said}])
    assert board_results.latest(empty)["route"]["drc"]["total"] == 2


def test_the_page_has_the_check_board_button():
    from ui_source import ui_js
    js = ui_js()
    assert "url: '/api/altium/drc'" in js and "pvStepBtn('drc')" in js and "'Check board'" in js
