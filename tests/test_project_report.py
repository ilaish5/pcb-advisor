"""
The per-project activity report: the zip a tester sends back (zip layout, the merged timeline, the download endpoint) and the
logging hooks added for it (engine tool calls in turns-log, Altium batches with their project and arguments).
"""
import json
import urllib.request
import zipfile

import pytest

import runlog
from test_runlog import call, server, logs  # noqa: F401  (fixtures)


def _write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def story(empty, logs):  # noqa: F811
    """A project with a student message, an agent turn with a failed tool call, a step, an Altium batch and an exception."""
    import workspace
    p = workspace.projects_dir() / empty
    _write(p / "usage-log.jsonl", [
        {"ts": "2026-11-19T10:00:00.000", "kind": "view", "view": "idea"},
        {"ts": "2026-11-19T10:00:05.000", "kind": "message", "text": "add a 3V3 buck", "chat": "s1", "ok": True},
        {"ts": "2026-11-19T10:00:40.000", "kind": "answer", "text": "Done.", "applied": ["bom.add: ok"], "refused": ["altium.route: busy"],
         "warned": {}, "ok": True, "engine": "claude_code", "seconds": 35},
        {"ts": "2026-11-19T10:02:00.000", "kind": "step", "op": "route", "phase": "end", "ok": False, "seconds": 12.0, "shown": "Altium said no",
         "steps": [{"step": "route", "state": "failed", "note": "no room"}]},
        {"ts": "2026-11-19T10:03:00.000", "kind": "ui-error", "message": "x is not defined", "source": "app.js", "line": 3},
    ])
    _write(p / "turns-log.jsonl", [
        {"ts": "2026-11-19T10:00:41", "kind": "chat", "engine": "claude_code", "model": "m", "seconds": 35, "ok": True, "applied": 1, "proposed": 0,
         "refused": 1, "calls": [{"tool": "Bash", "input": {"command": "python scripts/calc.py buck"}, "result": "Exit code 2 boom", "failed": True}]}])
    _write(p / "altium-log.jsonl", [{"ts": "2026-11-19T10:01:00", "by": "altium-bridge", "op": "place", "n": 4}])
    (p / "netlist").mkdir(exist_ok=True)
    (p / "netlist" / "a.json").write_text("{}")
    (p / "notes.md").write_text("hello")
    (p / "sources").mkdir(exist_ok=True)
    (p / "sources" / "x.pdf").write_bytes(b"%PDF")
    (p / "Board.PcbDoc").write_bytes(b"binary")
    (p / "chats").mkdir(exist_ok=True)
    (p / "chats" / "s1.jsonl").write_text('{"role": "user", "text": "add a 3V3 buck"}\n')
    day = logs / "run-2026-11-19.jsonl"
    logs.mkdir(parents=True, exist_ok=True)
    _write(day, [
        {"ts": "2026-11-19T10:01:30.000", "kind": "altium", "commands": ["PLACE"], "args": [["PLACE", "U1"]], "project": empty, "ok": False,
         "seconds": 4.0, "error": "BridgeError: dialog 'Cannot place'"},
        {"ts": "2026-11-19T10:01:31.000", "kind": "exception", "error": "ValueError: bad", "traceback": "Traceback...\nValueError: bad", "where": "step.route"},
        {"ts": "2026-11-19T10:01:32.000", "kind": "op", "op": "step.route", "phase": "end", "project": empty, "ok": False, "seconds": 12, "error": "no room"},
        {"ts": "2026-11-19T10:01:33.000", "kind": "request", "method": "POST", "path": "/api/step", "status": 500, "project": "other"},
        {"ts": "2026-11-20T09:00:00.000", "kind": "exception", "error": "OutsideWindow: nope"},
    ])
    return empty


def test_the_project_zip_layout_has_logs_state_and_chats_but_no_binaries(story, logs):  # noqa: F811
    z = zipfile.ZipFile(runlog.make_report(doctor={"checks": []}, project=story))
    names = z.namelist()
    for want in ("README.txt", "timeline.txt", "about.json", "doctor.json", "config.json", "logs/run-project.jsonl", "project/usage-log.jsonl",
                 "project/turns-log.jsonl", "project/altium-log.jsonl", "project/chats/s1.jsonl", "state/project.json", "state/notes.md",
                 "state/netlist/a.json"):
        assert want in names, want
    assert not any(n.endswith((".pdf", ".PcbDoc")) or n.startswith("projects/") for n in names)
    runs = [json.loads(line) for line in z.read("logs/run-project.jsonl").decode().splitlines()]
    kinds = sorted(r["kind"] for r in runs)
    assert kinds == ["altium", "exception", "op"]          # the other project's request and the exception outside the window are left out
    assert next(r for r in runs if r["kind"] == "exception").get("window") is True
    assert z.filename.rsplit("pcb-advisor-report-", 1)[1].startswith(story)


def test_the_timeline_is_in_time_order_with_errors_marked_and_a_summary(story):
    text = runlog.project_timeline_text(story)
    lines = text.splitlines()
    assert lines[0].startswith("PCB Advisor activity timeline") and "agent turns: 1" in text
    assert "step buttons: 1 ok, 1 failed" not in text and "step buttons: 0 ok, 1 failed" in text
    assert "first record: 2026-11-19 10:00:00.000" in text
    body = [ln for ln in lines if ln[:2] == "20"]
    assert [ln[:23] for ln in body] == sorted(ln[:23] for ln in body)
    pos = {k: text.index(k) for k in ("STUDENT SAYS: add a 3V3 buck", "AGENT ANSWERS", "ALTIUM BRIDGE PLACE", "EXCEPTION step.route", "UI ERROR")}
    assert pos["STUDENT SAYS: add a 3V3 buck"] < pos["AGENT ANSWERS"] < pos["ALTIUM BRIDGE PLACE"] < pos["EXCEPTION step.route"] < pos["UI ERROR"]
    err_lines = [ln for ln in lines if "!! " in ln]
    assert any("ALTIUM BRIDGE PLACE FAILED" in ln and "Cannot place" in ln for ln in err_lines)
    assert any("UI ERROR" in ln for ln in err_lines) and any("STEP route FAILED" in ln for ln in err_lines)
    assert any("tool Bash: python scripts/calc.py buck" in ln and "FAILED" in ln for ln in err_lines)
    assert any("REFUSED" in ln for ln in lines) and "OutsideWindow" not in text
    assert "ALTIUM-LOG" in text.upper() and "view=idea" in text


def test_a_timeline_of_an_empty_project_is_still_made(empty, logs):  # noqa: F811
    z = zipfile.ZipFile(runlog.make_report(doctor={}, project=empty))
    assert "first record: -" in z.read("timeline.txt").decode()


def test_the_download_endpoint_sends_a_zip_with_attachment_headers_and_keeps_a_copy(server, story, logs):  # noqa: F811
    with urllib.request.urlopen(f"{server}/api/report/project?project={story}", timeout=30) as r:
        body = r.read()
        disp = r.headers["Content-Disposition"]
        ctype = r.headers["Content-Type"]
    assert ctype == "application/zip" and body[:2] == b"PK"
    assert disp.startswith('attachment; filename="pcb-advisor-report-' + story) and "filename*=UTF-8''" in disp
    assert len(list(logs.glob(f"pcb-advisor-report-{story}-*.zip"))) == 1
    assert call(server, "GET", "/api/report/project?project=nope")[0] == 404
    assert call(server, "GET", f"/api/report/project?project={story}", headers={"Origin": "http://evil.example"})[0] == 403


def test_cli_report_takes_a_project_name(story, logs, capsys, monkeypatch):  # noqa: F811
    import pcb
    monkeypatch.setattr(runlog, "make_report", lambda doctor=None, project=None: logs / f"x-{project}.zip")
    pcb.cmd_report([story])
    assert f"x-{story}.zip" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        pcb.cmd_report(["no-such-project"])


def test_engine_tool_calls_land_in_the_turns_log_with_results_and_secrets_hidden(empty):
    import introspect
    res = {"provider": "claude_code", "usage": {"calls": [{"tool": "Bash", "input": {"command": "x --token=abcdef123456 y"}, "result": "boom", "failed": True}],
                                                 "denied": [{"tool": "Write", "input": {"file_path": "a"}, "reason": "no"}]}}
    rec = introspect.record(empty, "s", "chat", res, 1.0, reply="")
    row = introspect.turns(empty)[-1]
    assert row["calls"][0]["failed"] is True and row["calls"][0]["result"] == "boom"
    assert "abcdef123456" not in json.dumps(row) and row["denied"][0]["tool"] == "Write" and rec["calls"]


def test_the_stream_reader_keeps_every_call_with_its_result():
    from gateway.claude_code import _Turn
    t = _Turn()
    t.feed(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": "ls"}}]}}))
    t.feed(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "1", "content": "Exit code 1\nnope", "is_error": True}]}}))
    t.feed(json.dumps({"type": "result", "result": "ok", "usage": {}}))
    _, meta, _ = t.final()
    assert meta["calls"][0]["tool"] == "Bash" and meta["calls"][0]["failed"] is True and "nope" in meta["calls"][0]["result"]
    assert "id" not in meta["calls"][0]


def test_bridge_batches_are_logged_with_args_result_and_the_project(logs, monkeypatch):  # noqa: F811
    from altium import bridge
    monkeypatch.setattr(bridge, "_run_commands", lambda *a, **k: ["step 1", "DONE"])
    with runlog.for_project("demo"):
        bridge.run_commands([["PLACE", "U1", "10", "20"]])
    rec = [json.loads(line) for line in next(logs.glob("run-*.jsonl")).read_text(encoding="utf-8").splitlines()][-1]
    assert rec["kind"] == "altium" and rec["project"] == "demo" and rec["args"] == [["PLACE", "U1", "10", "20"]] and rec["result"][-1] == "DONE"

    def boom(*a, **k):
        raise bridge.BridgeError("dialog")
    monkeypatch.setattr(bridge, "_run_commands", boom)
    with pytest.raises(bridge.BridgeError):
        bridge.run_commands([["PLACE", "U1"]])
    rec = [json.loads(line) for line in next(logs.glob("run-*.jsonl")).read_text(encoding="utf-8").splitlines()][-1]
    assert rec["ok"] is False and rec["project"] == "" and "dialog" in rec["error"]


def test_the_ui_has_the_download_button():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "ui" / "js"
    assert "Download activity report (zip)" in (root / "shell.js").read_text(encoding="utf-8")
    assert "/api/report/project" in (root / "views" / "pages.js").read_text(encoding="utf-8")
