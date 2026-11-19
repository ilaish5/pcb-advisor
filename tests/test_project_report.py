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
        {"ts": "2026-11-18T10:00:00.000", "kind": "view", "view": "idea"},
        {"ts": "2026-11-18T10:00:05.000", "kind": "message", "text": "add a 3V3 buck", "chat": "s1", "ok": True},
        {"ts": "2026-11-18T10:00:40.000", "kind": "answer", "text": "Done.", "applied": ["bom.add: ok"], "refused": ["altium.route: busy"],
         "warned": {}, "ok": True, "engine": "claude_code", "seconds": 35},
        {"ts": "2026-11-18T10:02:00.000", "kind": "step", "op": "route", "phase": "end", "ok": False, "seconds": 12.0, "shown": "Altium said no",
         "steps": [{"step": "route", "state": "failed", "note": "no room"}]},
        {"ts": "2026-11-18T10:03:00.000", "kind": "ui-error", "message": "x is not defined", "source": "app.js", "line": 3},
    ])
    _write(p / "turns-log.jsonl", [
        {"ts": "2026-11-18T10:00:41", "kind": "chat", "engine": "claude_code", "model": "m", "seconds": 35, "ok": True, "applied": 1, "proposed": 0,
         "refused": 1, "calls": [{"tool": "Bash", "input": {"command": "python scripts/calc.py buck"}, "result": "Exit code 2 boom", "failed": True, "error": True}]}])
    _write(p / "altium-log.jsonl", [{"ts": "2026-11-18T10:01:00", "by": "altium-bridge", "op": "place", "n": 4}])
    (p / "netlist").mkdir(exist_ok=True)
    (p / "netlist" / "a.json").write_text("{}")
    (p / "notes.md").write_text("hello")
    (p / "sources").mkdir(exist_ok=True)
    (p / "sources" / "x.pdf").write_bytes(b"%PDF")
    (p / "Board.PcbDoc").write_bytes(b"binary")
    (p / "chats").mkdir(exist_ok=True)
    (p / "chats" / "s1.jsonl").write_text('{"role": "user", "text": "add a 3V3 buck"}\n')
    day = logs / "run-2026-11-18.jsonl"
    logs.mkdir(parents=True, exist_ok=True)
    _write(day, [
        {"ts": "2026-11-18T10:01:30.000", "kind": "altium", "commands": ["PLACE"], "args": [["PLACE", "U1"]], "project": empty, "ok": False,
         "seconds": 4.0, "error": "BridgeError: dialog 'Cannot place'"},
        {"ts": "2026-11-18T10:01:31.000", "kind": "exception", "error": "ValueError: bad", "traceback": "Traceback...\nValueError: bad", "where": "step.route"},
        {"ts": "2026-11-18T10:01:32.000", "kind": "op", "op": "step.route", "phase": "end", "project": empty, "ok": False, "seconds": 12, "error": "no room"},
        {"ts": "2026-11-18T10:01:33.000", "kind": "request", "method": "POST", "path": "/api/step", "status": 500, "project": "other"},
        {"ts": "2026-11-18T09:00:00.000", "kind": "exception", "error": "OutsideWindow: nope"},
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
    assert kinds == ["altium", "exception", "op"]          # the other project's request and the exception before the window are left out
    assert next(r for r in runs if r["kind"] == "exception").get("window") is True
    assert z.filename.rsplit("pcb-advisor-report-", 1)[1].startswith(story)


def test_the_timeline_is_in_time_order_with_errors_marked_and_a_summary(story):
    text = runlog.project_timeline_text(story)
    lines = text.splitlines()
    assert lines[0].startswith("PCB Advisor activity timeline") and "agent turns: 1" in text
    assert "step buttons: 1 ok, 1 failed" not in text and "step buttons: 0 ok, 1 failed" in text
    assert "first record: 2026-11-18 10:00:00.000" in text
    body = [ln for ln in lines if ln[:2] == "20"]
    assert [ln[:23] for ln in body] == sorted(ln[:23] for ln in body)
    pos = {k: text.index(k) for k in ("STUDENT SAYS: add a 3V3 buck", "AGENT ANSWERS", "ALTIUM BRIDGE PLACE", "EXCEPTION step.route", "UI ERROR")}
    assert pos["STUDENT SAYS: add a 3V3 buck"] < pos["AGENT ANSWERS"] < pos["ALTIUM BRIDGE PLACE"] < pos["EXCEPTION step.route"] < pos["UI ERROR"]
    err_lines = [ln for ln in lines if "!! " in ln]
    assert any("ALTIUM BRIDGE PLACE FAILED" in ln and "Cannot place" in ln for ln in err_lines)
    assert any("UI ERROR" in ln for ln in err_lines) and any("STEP route FAILED" in ln for ln in err_lines)
    assert any("tool Bash: python scripts/calc.py buck" in ln and "ERROR" in ln for ln in err_lines)
    assert any("REFUSED" in ln for ln in lines) and "OutsideWindow" not in text
    assert "ALTIUM-LOG" in text.upper() and "view=idea" in text


def test_a_timeline_of_an_empty_project_is_still_made(empty, logs):  # noqa: F811
    z = zipfile.ZipFile(runlog.make_report(doctor={}, project=empty))
    assert "first record: -" in z.read("timeline.txt").decode()


def test_the_download_endpoint_sends_a_zip_with_attachment_headers_and_keeps_a_copy(server, story, logs):  # noqa: F811
    req = urllib.request.Request(f"{server}/api/report/project?project={story}", headers={"X-PCB-Report": "1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        disp = r.headers["Content-Disposition"]
        ctype = r.headers["Content-Type"]
    assert ctype == "application/zip" and body[:2] == b"PK"
    assert disp.startswith('attachment; filename="pcb-advisor-report-' + story) and "filename*=UTF-8''" in disp
    assert len(list(logs.glob(f"pcb-advisor-report-{story}-*.zip"))) == 1
    assert call(server, "GET", "/api/report/project?project=nope", headers={"X-PCB-Report": "1"})[0] == 404
    assert call(server, "GET", f"/api/report/project?project={story}", headers={"Origin": "http://evil.example", "X-PCB-Report": "1"})[0] == 403
    assert call(server, "GET", f"/api/report/project?project={story}", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert call(server, "GET", f"/api/report/project?project={story}")[0] == 403          # no same-origin signal at all
    assert call(server, "GET", f"/api/report/project?project={story}", headers={"Sec-Fetch-Site": "same-origin"})[0] == 200
    name = sorted(logs.glob(f"pcb-advisor-report-{story}-*.zip"))[0].name
    code, data = call(server, "GET", f"/api/report?file={name}")          # a project zip is served by its strict file name too
    assert code == 200 and data[:2] == b"PK"


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


# ---------------------------------------------------------------- review round

@pytest.mark.parametrize("text", [
    "GEMINI_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrstu12",
    "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    '$env:OPENAI_API_KEY="sk-proj-aaaaaaaaaaaaaaaaaaaa"',
    '{"api_key": "xyz-secret-value"}',
    "token = 'quoted secret'",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "xoxb-123456789012-abcdefghij",
    "sk-ant-api03-abcdefghijklmnop",
    "AIzaSyA1234567890abcdefghijklmnopqrstu12",
    "my_password: hunter2hunter2",
])
def test_secret_shapes_are_hidden(text, logs):  # noqa: F811
    out = runlog.redact({"x": text})["x"]
    for bad in ("AIza", "ghp_", "sk-", "xyz-secret", "quoted secret", "xoxb", "github_pat", "hunter2"):
        assert bad not in out, out
    assert "[hidden]" in out
    assert runlog.redact({"x": "tokens_in: 5 and max_tokens 100"})["x"] == "tokens_in: 5 and max_tokens 100"      # no false hit


def test_denied_inputs_in_the_turns_log_are_redacted(empty):
    import introspect
    introspect.record(empty, "s", "chat", {"provider": "e", "usage": {"denied": [{"tool": "Bash", "input": {"command": "x GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789"},
                                                                       "reason": "no"}]}}, 1.0)
    assert "ghp_" not in json.dumps(introspect.turns(empty)[-1])


def test_agy_tool_events_become_calls_and_unknown_events_are_kept_raw():
    from gateway.antigravity import AntigravityProvider as A
    lines = [json.dumps(x) for x in (
        {"event": "assistant", "text": "let me look"},
        {"event": "tool_call", "tool": {"name": "RunCommand", "args": {"command": "python scripts/calc.py buck --token=abcdef0123456789"}}},
        {"event": "tool_result", "name": "RunCommand", "output": "exit 1: boom", "exit_code": 1},
        {"event": "tool_call", "name": "ReadFile", "input": {"path": "a.md"}},
        {"event": "tool_result", "name": "ReadFile", "result": "contents"},
        {"event": "result", "result": {"status": "SUCCESS", "response": "ok"}})]
    calls, raw = A._calls(lines, ["2026-11-18T10:00:0%d.000" % i for i in range(len(lines))])
    assert [c["tool"] for c in calls] == ["RunCommand", "ReadFile"] and raw == []
    assert calls[0]["failed"] is True and "boom" in calls[0]["result"] and calls[0]["ts"].endswith("01.000")
    assert calls[1]["failed"] is False and calls[1]["result"] == "contents"
    calls, raw = A._calls([json.dumps({"event": "mystery", "payload": {"a": 1}})], ["t"])
    assert calls == [] and raw and "mystery" in raw[0]["event"]


def test_agy_complete_puts_calls_in_meta(home, monkeypatch):
    import shutil
    import gateway
    out = "\n".join(json.dumps(x) for x in (
        {"event": "tool_call", "name": "RunCommand", "input": {"command": "ls"}},
        {"event": "tool_result", "name": "RunCommand", "output": "a b"},
        {"event": "result", "result": {"status": "SUCCESS", "response": "ok"}}))

    def fake_run(argv, stdin_text="", cwd=None, env=None, total_timeout=None, idle_timeout=None, cancel=None, on_line=None):
        for ln in out.splitlines():
            on_line(ln)
        return 0, "", "done"
    monkeypatch.setattr(shutil, "which", lambda cmd: "/bin/" + cmd)
    monkeypatch.setattr(gateway.stream, "run", fake_run)
    res = gateway.route(gateway.Request(prompt="hi", timeout=5, options={}), name="antigravity")
    assert res.meta["calls"][0]["tool"] == "RunCommand" and res.meta["calls"][0]["result"] == "a b"


def test_nested_inputs_are_clipped_and_calls_over_the_cap_are_counted():
    from gateway import events
    from gateway.claude_code import _Turn
    big = events.clip_input({"edits": [{"old": "x" * 5000, "new": ["y" * 5000] * 50}] * 50})
    assert len(json.dumps(big)) <= events.CALL_BYTES + 100
    t = _Turn()
    for i in range(events.MAX_CALLS + 5):
        t.feed(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": str(i), "name": "Read", "input": {"file_path": "a"}}]}}))
    t.feed(json.dumps({"type": "result", "result": "ok", "usage": {}}))
    _, meta, _ = t.final()
    assert len(meta["calls"]) == events.MAX_CALLS and meta["calls_dropped"] == 5 and meta["calls"][0]["ts"]


def test_turns_log_rolls_over_five_megabytes_and_the_rolled_file_is_in_the_zip(empty, logs, monkeypatch):  # noqa: F811
    import introspect
    import workspace
    monkeypatch.setattr(introspect, "ROLL", 10)
    introspect.record(empty, "s", "chat", {"provider": "e"}, 1.0)
    introspect.record(empty, "s", "chat", {"provider": "e"}, 1.0)
    p = workspace.projects_dir() / empty
    assert (p / "turns-log.1.jsonl").is_file() and (p / "turns-log.jsonl").is_file()
    z = zipfile.ZipFile(runlog.make_report(doctor={}, project=empty))
    assert "project/turns-log.1.jsonl" in z.namelist()
    assert z.read("timeline.txt").decode().count("AGENT TURN") == 2


def test_timeline_marks_stopped_not_failed_and_exit_codes_are_not_errors(empty, logs):  # noqa: F811
    import workspace
    p = workspace.projects_dir() / empty
    _write(p / "usage-log.jsonl", [{"ts": "2026-11-18T10:00:00.000", "kind": "step", "op": "route", "phase": "end", "ok": False, "stopped": True, "shown": "stopped"}])
    _write(p / "turns-log.jsonl", [{"ts": "2026-11-18T10:00:20", "started": "2026-11-18T10:00:10.000", "kind": "chat", "ok": True, "seconds": 10, "calls": [
        {"tool": "Bash", "ts": "2026-11-18T10:00:12.000", "input": {"command": "grep x"}, "result": "Exit code 1\n", "failed": True, "error": False},
        {"tool": "Bash", "ts": "2026-11-18T10:00:13.000", "input": {"command": "boom"}, "result": "bad", "failed": True, "error": True}]}])
    logs.mkdir(parents=True, exist_ok=True)
    _write(logs / "run-2026-11-18.jsonl", [{"ts": "2026-11-18T10:00:01.000", "kind": "op", "op": "step.route", "phase": "end", "project": empty, "ok": False, "stopped": True, "seconds": 1}])
    lines = runlog.project_timeline_text(empty).splitlines()
    stop = next(ln for ln in lines if "STEP route" in ln)
    assert "STOPPED" in stop and "!!" not in stop
    grep = next(ln for ln in lines if "grep x" in ln)
    assert "exit 1" in grep and "!!" not in grep
    assert "!!" in next(ln for ln in lines if "tool Bash: boom" in ln) and "ERROR" in next(ln for ln in lines if "tool Bash: boom" in ln)
    assert "0 ok, 0 failed, 1 stopped" in "\n".join(lines)


def test_a_turns_calls_sort_between_its_start_and_the_bridge_lines_they_caused(empty, logs):  # noqa: F811
    import workspace
    p = workspace.projects_dir() / empty
    _write(p / "turns-log.jsonl", [{"ts": "2026-11-18T10:00:30", "started": "2026-11-18T10:00:00.000", "kind": "chat", "ok": True, "seconds": 30, "calls": [
        {"tool": "Bash", "ts": "2026-11-18T10:00:05.000", "input": {"command": "first"}, "result": "ok"},
        {"tool": "Bash", "input": {"command": "second"}, "result": "ok"}]}])
    logs.mkdir(parents=True, exist_ok=True)
    _write(logs / "run-2026-11-18.jsonl", [{"ts": "2026-11-18T10:00:10.000", "kind": "altium", "commands": ["PLACE"], "project": empty, "ok": True, "seconds": 1}])
    text = runlog.project_timeline_text(empty)
    assert text.index("AGENT TURN") < text.index("tool Bash: second") < text.index("tool Bash: first") or text.index("AGENT TURN") < text.index("tool Bash: first")
    assert text.index("tool Bash: first") < text.index("ALTIUM BRIDGE PLACE")


def test_window_includes_projectless_http_errors_and_skips_other_projects_exceptions(story, logs):  # noqa: F811
    import datetime
    now = datetime.datetime.now().isoformat(timespec="milliseconds")
    with open(logs / "run-2026-11-18.jsonl", "a", encoding="utf-8") as fh:
        for r in ({"ts": "2026-11-18T10:01:40.000", "kind": "request", "method": "GET", "path": "/api/x", "status": 500, "error": "boom"},
                  {"ts": "2026-11-18T10:01:41.000", "kind": "exception", "error": "OtherProject: no", "project": "other"},
                  {"ts": now, "kind": "exception", "error": "LateOne: after the last record"}):
            fh.write(json.dumps(r) + "\n")
    text = runlog.project_timeline_text(story)
    assert "HTTP GET /api/x -> 500" in text and "OtherProject" not in text and "LateOne" in text


def test_a_broken_timeline_still_gives_a_zip_with_an_error_file(story, logs, monkeypatch):  # noqa: F811
    monkeypatch.setattr(runlog, "_timeline_rows", lambda project: 1 / 0)
    names = zipfile.ZipFile(runlog.make_report(doctor={}, project=story)).namelist()
    assert "timeline-error.txt" in names and "project/usage-log.jsonl" in names


def test_two_reports_at_once_get_different_files_and_each_kind_prunes_by_itself(story, logs, monkeypatch):  # noqa: F811
    import threading
    got = []
    ts = [threading.Thread(target=lambda: got.append(runlog.make_report(doctor={}, project=story))) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len({str(g) for g in got}) == 4 and all(g.is_file() for g in got)
    for _ in range(7):
        runlog.make_report(doctor={})
        runlog.make_report(doctor={}, project=story)
    assert len(list(logs.glob("pcb-advisor-report-[0-9]*.zip"))) == runlog.KEEP_REPORTS
    assert len(list(logs.glob(f"pcb-advisor-report-{story}-*.zip"))) == runlog.KEEP_REPORTS


def test_output_is_teed_into_a_capped_file_and_about_has_cli_versions(logs, monkeypatch, capsys):  # noqa: F811
    import sys
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    runlog.tee_output()
    print("[guard] the agent edited system files: restored x GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789", file=sys.stderr)
    f = runlog.output_files()[0].read_text(encoding="utf-8")
    assert "[guard] the agent edited system files" in f and "ghp_" not in f and " err " in f
    monkeypatch.setattr(runlog, "_cli_cache", {})
    monkeypatch.setattr("shutil.which", lambda n: None)
    assert runlog.cli_versions() == {"claude": "not on PATH", "agy": "not on PATH"}


def test_a_crashing_turn_still_records_its_turn_with_the_error(server, empty, monkeypatch):
    import introspect
    import serve

    def boom(*a, **k):
        raise RuntimeError("engine fell over")
    monkeypatch.setattr(serve.agent, "respond", boom)
    try:
        call(server, "POST", f"/api/chat?project={empty}", {"text": "hello"})
    except Exception:
        pass
    row = introspect.turns(empty)[-1]
    assert row["ok"] is False and "engine fell over" in row["error"]


def test_the_page_download_uses_fetch_with_the_header_and_checks_the_answer():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "pages.js").read_text(encoding="utf-8")
    assert "X-PCB-Report" in src and "r.ok" in src and "createObjectURL" in src and "PG_PROJ_REPORT_BUSY" in src


def test_agy_real_step_update_stream_becomes_calls():
    """The shape a real `agy -p= --output-format stream-json` run printed (19/11, trimmed)."""
    from gateway.antigravity import AntigravityProvider
    ev = lambda d: json.dumps({"event": "step_update", "step_update": d})
    lines = [
        json.dumps({"event": "init", "init": {"tools": ["run_command"]}}),
        ev({"step_index": 0, "state": "DONE", "step_type": "user_input"}),
        ev({"step_index": 2, "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command",
            "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}}}),
        ev({"step_index": 2, "state": "DONE", "step_type": "tool", "tool_name": "run_command", "duration_seconds": 2.0,
            "tool_info": {"name": "run_command", "parameters": {"CommandLine": "dir"}, "output": "Command exited with code 0."}}),
        ev({"step_index": 4, "state": "DONE", "step_type": "tool", "tool_name": "read_file",
            "tool_info": {"name": "read_file", "parameters": {"Path": "a.txt"}, "output": "1 lines, 6 bytes"}}),
        ev({"step_index": 5, "state": "DONE", "step_type": "agent_response", "text_delta": "hello"}),
        json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "hello\n"}}),
    ]
    calls, raw = AntigravityProvider._calls(lines, list(range(len(lines))))
    assert [c["tool"] for c in calls] == ["run_command", "read_file"]
    assert calls[0]["input"] == {"CommandLine": "dir"} and "exited with code 0" in calls[0]["result"]
    assert calls[0]["seconds"] == 2.0 and calls[0]["ts"] == 2 and not calls[0]["failed"]
    assert raw == []
