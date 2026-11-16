"""
The local diagnostic logs: the run log (logs/run-*.jsonl), the per-project usage log, the report zip and the timeline.
Everything runs in a temp workspace; conftest points PCB_ADVISOR_LOG_DIR away from the real logs/ folder.
"""
import json
import threading
import urllib.error
import urllib.request
import zipfile

import pytest

import runlog


@pytest.fixture
def logs(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    monkeypatch.setenv("PCB_ADVISOR_LOG_DIR", str(d))
    runlog._state["pruned"] = None
    return d


def records(logs):
    out = []
    for f in sorted(logs.glob("run-*.jsonl")):
        out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def wait_records(logs, pred, secs=5):
    """The request record is written just after the answer is sent, so the test waits for it."""
    import time
    end = time.time() + secs
    while time.time() < end:
        got = [r for r in records(logs) if pred(r)]
        if got:
            return got
        time.sleep(0.02)
    return []


@pytest.fixture
def server(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    import serve
    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    monkeypatch.setattr(serve, "compact_if_due", lambda p, s: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body if body is not None else {}).encode() if method == "POST" else None)
    req = urllib.request.Request(base + path, method=method, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ---------------------------------------------------------------- the writer

def test_a_record_is_written_with_ts_and_kind(logs):
    runlog.event("start", port=1234, note="héllo")
    (rec,) = records(logs)
    assert rec["kind"] == "start" and rec["port"] == 1234 and rec["note"] == "héllo" and rec["ts"]


def test_only_the_last_14_daily_files_are_kept(logs):
    logs.mkdir()
    for day in range(1, 21):
        (logs / f"run-2026-01-{day:02d}.jsonl").write_text("{}\n")
    runlog.event("x")
    names = sorted(p.name for p in logs.glob("run-*.jsonl"))
    assert "run-2026-01-01.jsonl" not in names and "run-2026-01-20.jsonl" in names
    assert len(names) <= 15


def test_secrets_are_hidden_and_long_strings_cut(logs):
    runlog.event("t", api_key="sk-abc", Authorization="Bearer zzz", nested={"password": "p", "ok": 1}, big="x" * 9000,
                 text="token=abc123 and sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa")
    (rec,) = records(logs)
    assert rec["api_key"] == "[hidden]" and rec["Authorization"] == "[hidden]"
    assert rec["nested"] == {"password": "[hidden]", "ok": 1}
    assert len(rec["big"]) < 4100
    assert "abc123" not in rec["text"] and "sk-ant" not in rec["text"]


def test_logging_never_raises(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("PCB_ADVISOR_LOG_DIR", str(blocker / "logs"))      # cannot be created
    runlog.event("x", obj=object())
    runlog.usage("no-such-project", "click", text="a")
    runlog.exception("e", ValueError("boom"))
    with pytest.raises(ZeroDivisionError):                                # span re-raises the caller's error, but logs nothing fatal
        with runlog.span("op"):
            1 / 0


# ---------------------------------------------------------------- the server

def test_an_unhandled_exception_in_a_handler_writes_a_traceback(server, empty, logs, monkeypatch):
    import model
    monkeypatch.setattr(model, "build", lambda **k: (_ for _ in ()).throw(RuntimeError("model exploded")))
    try:
        call(server, "GET", f"/api/state?project={empty}")
    except Exception:
        pass
    exc = wait_records(logs, lambda r: r["kind"] == "request" and r["path"] == "/api/state") and [r for r in records(logs) if r["kind"] == "exception"]
    assert exc and "model exploded" in exc[0]["traceback"] and exc[0]["path"] == "/api/state" and exc[0]["project"] == empty
    assert any(r["kind"] == "request" and r["path"] == "/api/state" and r["status"] == 0 for r in records(logs))


def test_requests_are_logged_but_not_the_state_poll(server, empty, logs):
    call(server, "GET", f"/api/state?project={empty}")
    call(server, "GET", f"/api/nothing?project={empty}")
    wait_records(logs, lambda r: r["kind"] == "request")
    reqs = [r for r in records(logs) if r["kind"] == "request"]
    assert [r["path"] for r in reqs] == ["/api/nothing"] and reqs[0]["status"] in (404, 400) and reqs[0]["project"] == empty


def test_client_errors_land_as_ui_error_and_big_bodies_are_refused(server, empty, logs):
    code, _ = call(server, "POST", f"/api/log/client?project={empty}", {"message": "x is not defined", "source": "a.js", "line": 3, "view": "stage:bom"})
    assert code == 200
    rec = [r for r in records(logs) if r["kind"] == "ui-error"][0]
    assert rec["message"] == "x is not defined" and rec["line"] == 3
    code, _ = call(server, "POST", "/api/log/client", raw=b'{"message":"' + b"a" * 20000 + b'"}')
    assert code == 413


def test_chat_turn_records_have_counts_and_no_text(server, empty, logs, monkeypatch):
    import serve
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {"reply": "The ANSWER-SECRET reply", "actions": [], "provider": "fake",
                                                                 "model": "m1", "seconds": 1, "usage": {}})
    code, _ = call(server, "POST", f"/api/chat?project={empty}", {"text": "MESSAGE-SECRET please"})
    assert code == 200
    chat = [r for r in records(logs) if r["kind"] == "chat"]
    assert [r["phase"] for r in chat] == ["begin", "end"]
    assert chat[1]["ok"] is True and chat[1]["applied"] == 0 and chat[1]["engine"] and "seconds" in chat[1]
    blob = "\n".join(f.read_text(encoding="utf-8") for f in logs.glob("run-*.jsonl"))
    assert "MESSAGE-SECRET" not in blob and "ANSWER-SECRET" not in blob
    # ... while the usage log has the whole conversation
    usage = [json.loads(l) for l in (serve.workspace.projects_dir() / empty / "usage-log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [u["kind"] for u in usage] == ["message", "answer"]
    assert usage[0]["text"] == "MESSAGE-SECRET please" and usage[1]["text"].startswith("The ANSWER-SECRET reply") and usage[1]["ok"] is True


# ---------------------------------------------------------------- the usage log

def test_a_client_batch_is_written_to_the_projects_usage_log(server, empty, logs):
    batch = {"session": "s1", "events": [{"kind": "view", "project": empty, "name": "stage:bom", "ts": "2026-01-01T10:00:00.000"},
                                         {"kind": "click", "project": empty, "text": "Approve", "ts": "2026-01-01T10:00:05.000"},
                                         {"kind": "nonsense", "project": empty}]}
    assert call(server, "POST", "/api/log/usage", batch)[0] == 200
    import workspace
    lines = [json.loads(l) for l in (workspace.projects_dir() / empty / "usage-log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["kind"] for l in lines] == ["view", "click"] and lines[0]["session"] == "s1" and lines[1]["text"] == "Approve"


def test_a_batch_with_an_unsafe_or_unknown_project_is_refused(server, empty, logs, home):
    for bad in ("../../evil", "no-such", "a/b", ".."):
        code, _ = call(server, "POST", "/api/log/usage", {"session": "s", "events": [{"kind": "click", "project": bad, "text": "x"}]})
        assert code == 400, bad
    assert not (home.parent / "evil").exists() and not list(home.rglob("usage-log.jsonl"))


def test_events_without_a_project_go_to_the_run_log(server, logs):
    assert call(server, "POST", "/api/log/usage", {"session": "s", "events": [{"kind": "click", "text": "New project"}]})[0] == 200
    assert [r["text"] for r in records(logs) if r["kind"] == "click"] == ["New project"]


def test_the_timeline_prints_events_in_order(empty):
    runlog.usage(empty, "view", name="stage:bom", session="a")
    runlog.usage(empty, "click", text="Approve", session="a")
    runlog.usage(empty, "answer", text="done " * 100, ok=False, session="a")
    lines = runlog.timeline(empty)
    kinds = [l.split()[0] if not l.startswith("---") else "---" for l in lines]
    assert kinds[0] == "---" and [l.split()[1] for l in lines[1:]] == ["view", "click", "answer"]
    assert lines[-1].endswith("...") and "FAILED" in runlog.timeline(empty, full=True)[-1]
    assert len(runlog.timeline(empty, full=True)[-1]) > len(lines[-1])


# ---------------------------------------------------------------- the report

def test_the_report_holds_logs_and_usage_and_chats_but_no_sources(server, lte, logs, home):
    import workspace
    runlog.event("start", port=1)
    p = workspace.projects_dir() / lte
    (p / "sources").mkdir(exist_ok=True)
    (p / "sources" / "datasheet.pdf").write_bytes(b"%PDF secret")
    (p / "Board.PrjPcb").write_text("altium")
    (p / "chats").mkdir(exist_ok=True)
    (p / "chats" / "main.json").write_text('{"chat": []}')
    (p / "altium-log.jsonl").write_text('{"op": "x"}\n')
    for name in ("Sheet1.SchDoc", "Board.PcbDoc", "datasheet-U1.pdf"):
        (p / name).write_bytes(b"binary")
    (workspace.shared_dir() / "datasheets").mkdir(parents=True, exist_ok=True)
    (workspace.shared_dir() / "datasheets" / "part.pdf").write_bytes(b"%PDF")
    runlog.usage(lte, "click", text="Draw")
    code, body = call(server, "POST", f"/api/report?project={lte}")
    assert code == 200
    res = json.loads(body)
    assert res["path"].endswith(".zip") and res["name"].startswith("pcb-advisor-report-")
    names = zipfile.ZipFile(res["path"]).namelist()
    assert any(n.startswith("logs/run-") for n in names)
    assert f"projects/{lte}/usage-log.jsonl" in names and f"projects/{lte}/altium-log.jsonl" in names
    assert f"projects/{lte}/chats/main.json" in names
    assert "doctor.json" in names and "config.json" in names
    assert not any("sources" in n or n.endswith((".pdf", ".PrjPcb", ".SchDoc", ".PcbDoc")) or "datasheet" in n for n in names)
    code, data = call(server, "GET", f"/api/report?file={res['name']}")
    assert code == 200 and data[:2] == b"PK"
    assert call(server, "GET", "/api/report?file=../../config.json")[0] == 404
    assert call(server, "GET", "/api/report")[0] == 405 and len(list(logs.glob("pcb-advisor-report-*.zip"))) == 1     # a GET never makes a zip
    assert call(server, "POST", "/api/report", headers={"Origin": "http://evil.example"})[0] == 403
    assert call(server, "POST", "/api/log/usage", {"events": []}, headers={"Origin": "http://evil.example"})[0] == 403


def test_the_report_config_and_doctor_have_no_secrets(logs, home, monkeypatch):
    import workspace
    monkeypatch.setattr(workspace, "load", lambda *a, **k: {"user": {"name": "Dana"}, "agent": {"api_key": "SECRET-1", "provider": "claude_code",
                                                              "providers": {"x": {"auth_token": "SECRET-2"}}}})
    z = zipfile.ZipFile(runlog.make_report(doctor={"checks": [{"id": "signin", "detail": "ok", "access_token": "SECRET-3"}]}))
    blob = z.read("config.json").decode() + z.read("doctor.json").decode()
    assert "SECRET" not in blob
    cfg = json.loads(z.read("config.json"))
    assert cfg["user"]["name"] == "Dana" and cfg["agent"]["provider"] == "claude_code"


def test_only_the_last_five_reports_and_one_rolled_usage_file_are_kept(logs, empty, monkeypatch):
    import workspace
    for _ in range(7):
        runlog.make_report(doctor={})
    assert len(list(logs.glob("pcb-advisor-report-*.zip"))) == 5
    monkeypatch.setattr(runlog, "USAGE_ROLL", 200)
    for i in range(30):
        runlog.usage(empty, "click", text="x" * 30)
    d = workspace.projects_dir() / empty
    assert (d / "usage-log.1.jsonl").exists() and (d / "usage-log.jsonl").stat().st_size < 400
    assert len(runlog.timeline(empty)) >= 3


def test_a_log_folder_that_cannot_be_written_does_not_change_the_answer(server, empty, logs, tmp_path, monkeypatch):
    code, before = call(server, "GET", f"/api/projects?project={empty}")
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    monkeypatch.setenv("PCB_ADVISOR_LOG_DIR", str(blocker / "logs"))
    code2, after = call(server, "GET", f"/api/projects?project={empty}")
    assert code == code2 == 200 and json.loads(before) == json.loads(after)
    assert call(server, "POST", "/api/log/usage", {"session": "s", "events": [{"kind": "click", "text": "x"}]})[0] == 200


def test_page_events_without_a_project_leave_only_kind_view_and_label_in_the_run_log(server, logs):
    ev = [{"kind": "click", "text": "New project", "view": "stage:bom", "id": "b1", "stack": "secret trace"},
          {"kind": "queued", "text": "PRIVATE CHAT TEXT"}]
    assert call(server, "POST", "/api/log/usage", {"session": "s", "events": ev})[0] == 200
    recs = [r for r in records(logs) if r["kind"] in ("click", "queued")]
    assert recs[0]["text"] == "New project" and "stack" not in recs[0]
    assert "PRIVATE CHAT TEXT" not in "\n".join(f.read_text(encoding="utf-8") for f in logs.glob("run-*.jsonl"))


# ---------------------------------------------------------------- every message gets one outcome

def usage_of(project):
    import workspace
    f = workspace.projects_dir() / project / "usage-log.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def test_a_refused_message_is_logged_with_the_refusal(server, empty, monkeypatch):
    import serve
    import session as session_mod
    sess = session_mod.current(empty, None)
    monkeypatch.setitem(serve.TURNS, (empty, sess), {})
    assert call(server, "POST", f"/api/chat?project={empty}", {"text": "first"})[0] == 409
    monkeypatch.delitem(serve.TURNS, (empty, sess))
    assert serve.STEP_LOCK.acquire(blocking=False)
    try:
        assert call(server, "POST", f"/api/chat?project={empty}", {"text": "second"})[0] == 409
    finally:
        serve.STEP_LOCK.release()
    msgs = usage_of(empty)
    assert [m["kind"] for m in msgs] == ["message", "message"] and all(m["ok"] is False for m in msgs)
    assert "still answering" in msgs[0]["shown"] and "busy" in msgs[1]["shown"] and msgs[1]["text"] == "second"


def test_a_failing_engine_gives_an_answer_record_with_the_error(server, empty, monkeypatch):
    import serve

    def boom(*a, **k):
        raise RuntimeError("engine fell over")
    monkeypatch.setattr(serve.agent, "respond", boom)
    try:
        call(server, "POST", f"/api/chat?project={empty}", {"text": "hello"})
    except Exception:
        pass
    rows = usage_of(empty)
    assert [r["kind"] for r in rows] == ["message", "answer"] and rows[1]["ok"] is False and "engine fell over" in rows[1]["error"]


def test_a_reply_with_no_text_and_nothing_applied_still_gets_an_answer_record(server, empty, monkeypatch):
    import serve
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {"reply": "", "actions": [], "provider": "fake", "model": "m", "seconds": 1, "usage": {}})
    assert call(server, "POST", f"/api/chat?project={empty}", {"text": "hi"})[0] == 200
    rows = usage_of(empty)
    assert [r["kind"] for r in rows] == ["message", "answer"] and rows[1]["text"] == "" and rows[1]["ok"] is True

