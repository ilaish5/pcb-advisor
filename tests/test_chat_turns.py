"""
The chat turn as the server runs it: progress while it works, Stop, the denial allow-list,
and memory rewrites that never delay the reply. The engine is faked at agent.respond / gateway.route.
"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

import session as session_mod
import workspace


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


def call(base, method, path, project, body=None):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"{base}{path}{sep}project={project}", method=method,
                                 data=json.dumps(body if body is not None else {}).encode() if method == "POST" else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait_for(cond, secs=5):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def chat_in_thread(base, project, text="hello"):
    out = {}

    def run():
        out["r"] = call(base, "POST", "/api/chat", project, {"text": text})

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, out


def fake_blocking_respond(monkeypatch, partial_text="half an answer"):
    """A turn that emits two steps and then waits for Stop, like an engine killed mid-run."""
    import serve
    started = threading.Event()

    def respond(model, message, history, backend=None, timeout=None, on_event=None, cancel=None):
        on_event({"kind": "tool", "label": "Running calc.py a", "tool": "Bash", "ts": time.time()})
        on_event({"kind": "tool", "label": "Reading datasheet.pdf", "tool": "Read", "ts": time.time()})
        started.set()
        assert cancel.wait(10), "Stop never arrived"
        return {"reply": partial_text, "actions": [{"type": "note.add", "text": "must not apply"}], "partial": True,
                "error_kind": "stopped", "steps": ["Running calc.py a", "Reading datasheet.pdf"],
                "provider": "fake", "seconds": 1, "usage": {}}

    monkeypatch.setattr(serve.agent, "respond", respond)
    return started


def test_progress_while_a_turn_runs_then_idle(server, empty, monkeypatch):
    started = fake_blocking_respond(monkeypatch)
    assert call(server, "GET", "/api/chat/progress", empty)[1]["running"] is False
    t, out = chat_in_thread(server, empty)
    assert started.wait(5)
    code, p = call(server, "GET", "/api/chat/progress", empty)
    assert code == 200 and p["running"] is True
    assert [s["label"] for s in p["steps"]] == ["Running calc.py a", "Reading datasheet.pdf"]
    assert p["current"] == "Reading datasheet.pdf" and p["seconds"] >= 0 and "idle_seconds" in p
    assert call(server, "POST", "/api/chat/stop", empty)[0] == 200
    t.join(10)
    assert call(server, "GET", "/api/chat/progress", empty)[1]["running"] is False


def test_stop_returns_the_partial_record_and_applies_no_actions(server, empty, monkeypatch):
    started = fake_blocking_respond(monkeypatch)
    t, out = chat_in_thread(server, empty)
    assert started.wait(5)
    assert call(server, "POST", "/api/chat/stop", empty) == (200, {"ok": True})
    t.join(10)
    code, state = out["r"]
    assert code == 200 and state["last_actions"] == []
    sess = session_mod.current(empty, None)
    rec = [r for r in session_mod.load_chat(empty, sess) if r["role"] == "agent"][-1]
    assert rec["text"] == "half an answer" and rec["partial"] is True and rec["stopped"] is True
    assert rec["timed_out"] is False and rec["error_kind"] == "stopped"
    assert rec["steps"] == ["Running calc.py a", "Reading datasheet.pdf"]
    assert not rec.get("error")
    assert rec["seconds"] == 1.0 and "idle_seconds" not in rec


def test_idle_timeout_record_carries_the_limit_that_fired(server, empty, monkeypatch):
    import serve
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {
        "reply": "so far", "actions": [], "partial": True, "error_kind": "idle_timeout", "provider": "fake",
        "seconds": 183.26, "usage": {}})
    assert call(server, "POST", "/api/chat", empty, {"text": "x"})[0] == 200
    rec = [r for r in session_mod.load_chat(empty, session_mod.current(empty, None)) if r["role"] == "agent"][-1]
    assert rec["timed_out"] is True and rec["seconds"] == 183.3 and rec["idle_seconds"] == 180


def test_stop_when_nothing_runs_is_409(server, empty):
    code, body = call(server, "POST", "/api/chat/stop", empty)
    assert code == 409 and "error" in body


def seed_denial(project, denial, ts="2026-10-20T10:00:00"):
    sess = session_mod.current(project, None)
    session_mod.append(project, sess, {"ts": ts, "role": "agent", "text": "needs approval",
                                       "denied": [{**denial, "id": 0}]})
    return ts


def allowed_extra():
    return workspace.load(reload=True)["agent"]["providers"]["claude_code"]["tools"].get("allowed_extra", [])


def test_allow_writes_the_rule_once_from_the_recorded_denial(server, empty):
    ts = seed_denial(empty, {"tool": "Bash", "input": {"command": "ls /tmp"}, "reason": "r", "compound": False})
    for _ in range(2):    # deduped
        code, body = call(server, "POST", "/api/chat/allow", empty, {"turn_ts": ts, "index": 0})
        assert code == 200 and body == {"rule": "Bash(ls /tmp)"}
    assert allowed_extra() == ["Bash(ls /tmp)"]


def test_allow_builds_each_tool_kind(server, empty):
    cases = [({"tool": "Read", "input": {"file_path": "/x/a.pdf"}}, "Read(/x/a.pdf)"),
             ({"tool": "WebFetch", "input": {"url": "https://example.com/p?q=1"}}, "WebFetch(domain:example.com)"),
             ({"tool": "Glob", "input": {"pattern": "*"}}, "Glob")]
    for i, (d, rule) in enumerate(cases):
        ts = seed_denial(empty, {**d, "reason": "", "compound": False}, ts=f"2026-10-20T10:00:0{i}")
        assert call(server, "POST", "/api/chat/allow", empty, {"turn_ts": ts, "index": 0})[1]["rule"] == rule


def test_allow_refuses_compound_and_protected_and_unknown(server, empty):
    ts = seed_denial(empty, {"tool": "Bash", "input": {"command": "ls /tmp"}, "reason": "", "compound": True})
    assert call(server, "POST", "/api/chat/allow", empty, {"turn_ts": ts, "index": 0})[0] == 400
    ts2 = seed_denial(empty, {"tool": "Bash", "input": {"command": "cd x && ls"}, "reason": "", "compound": False}, "t2")
    assert call(server, "POST", "/api/chat/allow", empty, {"turn_ts": ts2, "index": 0})[0] == 400
    for i, path in enumerate(["/p/chat/s1.jsonl", "/p/idea.json", "/p/bom.json", "/p/netlist/main.json",
                              "C:\\p\\netlist\\main.json"]):
        t = seed_denial(empty, {"tool": "Write", "input": {"file_path": path}, "reason": "", "compound": False}, f"p{i}")
        code, _ = call(server, "POST", "/api/chat/allow", empty, {"turn_ts": t, "index": 0})
        assert code == 400, path
    # the client names a turn and an index, nothing else; unknown ones are 404
    assert call(server, "POST", "/api/chat/allow", empty, {"turn_ts": "nope", "index": 0})[0] == 404
    assert call(server, "POST", "/api/chat/allow", empty, {"turn_ts": ts, "index": 5})[0] == 404
    assert allowed_extra() == []


def test_the_reply_does_not_wait_for_the_memory_rewrite(server, empty, monkeypatch):
    import serve
    monkeypatch.undo()          # restore the real compact_async; the fixture patched compact_if_due
    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    release, ran, calls = threading.Event(), threading.Event(), []

    def slow_compact(p, s):
        calls.append((p, s))
        ran.set()
        release.wait(10)

    monkeypatch.setattr(serve, "compact_if_due", slow_compact)
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {"reply": "hi", "actions": [], "provider": "fake",
                                                                  "seconds": 0, "usage": {}})
    t0 = time.time()
    code, _ = call(server, "POST", "/api/chat", empty, {"text": "hello"})
    assert code == 200 and time.time() - t0 < 5 and not release.is_set()
    assert ran.wait(5)
    # a second turn while the rewrite still runs does not start another one
    call(server, "POST", "/api/chat", empty, {"text": "again"})
    time.sleep(0.2)
    assert len(calls) == 1
    release.set()


def test_compact_async_never_raises(home, monkeypatch, capsys):
    import serve

    def boom(p, s):
        raise RuntimeError("engine down")

    monkeypatch.setattr(serve, "compact_if_due", boom)
    serve.compact_async("p", "s").join(5)
    assert "engine down" in capsys.readouterr().out


def test_write_memory_is_atomic(empty):
    sess = session_mod.current(empty, None)
    path = session_mod.write_memory(empty, sess, "one")
    assert path.read_text(encoding="utf-8") == "one\n"
    session_mod.write_memory(empty, sess, "two")
    assert path.read_text(encoding="utf-8") == "two\n"
    assert not list(path.parent.glob("*.tmp"))


def test_respond_forwards_options_and_returns_the_turn_meta(empty, monkeypatch):
    import agent
    import gateway
    import model
    seen = {}

    def route(req, name=None):
        seen["req"] = req
        return gateway.Result(text="partial words ```json {\"actions\": [", provider="claude_code", model="m",
                              error="stopped", meta={"partial": True, "error_kind": "idle_timeout",
                                                     "steps": ["Reading a.md"], "denied": [{"tool": "Bash"}],
                                                     "retry_at": "2026-10-20T12:00:00"})

    monkeypatch.setattr(agent.gateway, "route", route)
    monkeypatch.setattr(agent.runtime_pack, "sync", lambda: empty)
    cancel, events = threading.Event(), []
    res = agent.respond(model.build(project=empty), "hi", [], on_event=events.append, cancel=cancel)
    opts = seen["req"].options
    assert opts["cancel"] is cancel and opts["on_event"] == events.append and opts["idle_timeout"] == 180
    assert seen["req"].timeout == 900
    assert res["partial"] is True and res["reply"].startswith("partial words") and res["error"] is True and res["actions"] == []
    assert res["steps"] == ["Reading a.md"] and res["error_kind"] == "idle_timeout"
    assert res["denied"] == [{"tool": "Bash"}] and res["retry_at"].startswith("2026")


def test_a_command_refused_twice_is_one_card():
    import serve
    d = {"tool": "Bash", "input": {"command": "git --version", "description": "a"}, "reason": "", "compound": False}
    out = serve.unique_denials([d, {**d, "input": {"command": "git --version", "description": "b"}},
                                {**d, "input": {"command": "git status"}}])
    assert [x["input"]["command"] for x in out] == ["git --version", "git status"]
    assert [x["id"] for x in out] == [0, 1]
