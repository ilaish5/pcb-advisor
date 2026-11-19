"""Review round on the verify fixes: altium_ok counts only good runs, one sheet is one tab, report redaction and filtering."""
import json

import pytest  # noqa: F401

import runlog
import workspace
from test_chat_turns import call, server  # noqa: F401
from test_runlog import logs  # noqa: F401


def _rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_altium_ok_ignores_failed_records_and_tracks_drawn_sheets(empty):
    import model
    import store
    log = workspace.projects_dir() / empty / "altium-log.jsonl"
    _rows(log, [
        {"ts": "2026-11-18T10:00:00.100", "op": "draw-schematic", "sheets": ["C:\\p\\01 Power.SchDoc"], "problems": ["x"]},
        {"ts": "2026-11-18T10:00:01.100", "op": "route-pcb", "failed": ["+3V3"], "problems": []},
        {"ts": "2026-11-18T10:00:02.100", "op": "place-pcb", "restored": True},
        {"ts": "2026-11-18T10:00:03.100", "op": "draw-schematic", "sheets": ["C:\\p\\02 RP2040.SchDoc"], "problems": []},
    ])
    ok = model.altium_ok(empty)
    assert ok["draw-schematic"] == "2026-11-18T10:00:03.100" and "route-pcb" not in ok and "place-pcb" not in ok
    assert ok["draw_sheets"] == [{"ts": "2026-11-18T10:00:03.100", "sheets": ["02 RP2040"]}]      # sheet 01 was not drawn by a good run
    assert store.log_ok({"op": "x"}) and not store.log_ok({"op": "x", "error": "e"})


def test_plan_sheet_and_its_altium_file_are_one_sheet(empty, monkeypatch):
    import model
    import project as project_mod
    import store
    import altium.prjpcb as prjpcb
    monkeypatch.setattr(store, "sheet_ids", lambda p: ["01", "02"])
    monkeypatch.setattr(store, "load_sheet", lambda p, sid: {"title": "t" + sid, "sections": [], "parts": []})
    monkeypatch.setattr(project_mod, "altium_link", lambda p: {"project_file": __file__})
    monkeypatch.setattr(prjpcb, "read_prjpcb", lambda f: {"sheets": ["01 USB-C.SchDoc", "02 RP2040.SchDoc", "Main.SchDoc"]})
    ids = [(s["id"], bool(s.get("altium"))) for s in model.sheets(empty)]
    assert ids == [("01", False), ("02", False), ("Main", True)]


def test_pending_count_leaves_out_proposals_approved_at_once(empty, monkeypatch):
    import serve
    import store
    monkeypatch.setattr(store, "proposals", lambda p: [{"id": "a", "status": "pending"}, {"id": "b", "status": "approved"}])
    assert serve._pending(empty, ["a", "b"]) == 1
    assert serve._usage_applied(["bom.propose:R1", "library.add:R1"]) == ["library.add:R1"]


def test_link_path_must_be_text(server, empty):
    assert call(server, "POST", "/api/altium/link", empty, {"path": ["x"]})[0] == 400


def test_report_hides_profile_names_with_spaces_and_in_tracebacks():
    t = runlog.home_paths('File "C:\\Users\\Jo Smith\\AppData\\x.py", line 3 and C:\\Users\\bob is here')
    assert "Jo Smith" not in t and "bob" not in t and t.count("%USERPROFILE%") == 2


def test_filter_output_matches_whole_project_names(empty, logs):  # noqa: F811
    (workspace.projects_dir() / "Verify-RP2040").mkdir(exist_ok=True)
    (workspace.projects_dir() / "guard").mkdir(exist_ok=True)
    lines = ["2026-11-18T10:00:00.500 out [guard] line one", "2026-11-18T10:00:01.000 out edit in projects/Verify-RP2040/x restored",
             "2026-11-18T10:00:02.000 out edit in projects/Verify/x restored"]
    out = runlog.filter_output(lines, "Verify", "2026-11-18 10:00:00.999", "2026-11-18 11:00:00.000")
    assert "[guard] line one" in out and "Verify-RP2040" not in out and "projects/Verify/x" in out


def test_step_counts_do_not_overlap(empty, logs):  # noqa: F811
    runs = [{"ts": "2026-11-18T10:00:00", "kind": "op", "op": "step.route", "phase": "end", "ok": True, "summary": "x; PARTIAL ROUTE, left open: A"},
            {"ts": "2026-11-18T10:00:01", "kind": "op", "op": "step.place", "phase": "end", "ok": True, "summary": "placed"}]
    text = runlog.project_timeline_text(empty, run_events=runs)
    assert "step buttons: 1 ok, 1 partial, 0 failed" in text and "RUN step.route PARTIAL" in text
