"""The shared Popen runner, step labels, error kinds and the stream-json parse."""
import json
import os
import sys
import threading
import time

import pytest

import gateway
import oscompat
from gateway import events, stream
from gateway.claude_code import ClaudeCodeProvider


def py(code, *args):
    return [sys.executable, "-u", "-c", code, *args]


# ---------------------------------------------------------------- the runner

def test_done_collects_lines_stderr_and_returncode():
    got = []
    rc, err, ended = stream.run(
        py("import sys; print('a'); print('b'); sys.stderr.write('oops\\n'); sys.exit(3)"),
        on_line=got.append, total_timeout=20)
    assert (rc, ended) == (3, "done")
    assert got == ["a", "b"] and "oops" in err


def test_stdin_text_reaches_the_child_and_hebrew_survives_utf8():
    code = "import sys; t=sys.stdin.buffer.read().decode('utf-8'); sys.stdout.buffer.write(('שלום '+t+'\\n').encode('utf-8'))"
    got = []
    rc, _, ended = stream.run(py(code), stdin_text="עולם ✓", on_line=got.append, total_timeout=20,
                              env=oscompat.child_env())
    assert ended == "done" and got == ["שלום עולם ✓"]


def test_idle_timeout_kills_a_silent_child():
    t0 = time.monotonic()
    rc, _, ended = stream.run(py("import time; print('hi'); time.sleep(60)"),
                              idle_timeout=1, total_timeout=30)
    assert ended == "idle_timeout" and rc is None
    assert time.monotonic() - t0 < 10


def test_a_chatty_child_is_not_idle_but_hits_the_total_ceiling():
    code = "import time\nwhile True:\n    print('x'); time.sleep(0.2)"
    rc, _, ended = stream.run(py(code), idle_timeout=1, total_timeout=2)
    assert ended == "total_timeout"


def test_cancel_stops_within_a_second_or_two():
    cancel = threading.Event()
    threading.Timer(0.7, cancel.set).start()
    t0 = time.monotonic()
    _, _, ended = stream.run(py("import time; time.sleep(60)"), cancel=cancel, total_timeout=30)
    assert ended == "stopped"
    assert time.monotonic() - t0 < 5


@pytest.mark.skipif(oscompat.WINDOWS, reason="pid probe uses os.kill(pid, 0)")
def test_cancel_kills_the_whole_tree_not_just_the_child(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    code = ("import subprocess, sys, time\n"
            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"open({str(pidfile)!r}, 'w').write(str(g.pid))\n"
            "time.sleep(60)\n")
    cancel = threading.Event()

    def later():
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text():
                break
            time.sleep(0.05)
        cancel.set()
    threading.Thread(target=later, daemon=True).start()
    _, _, ended = stream.run(py(code), cancel=cancel, total_timeout=30)
    assert ended == "stopped"
    gpid = int(pidfile.read_text())
    for _ in range(40):
        try:
            os.kill(gpid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(gpid, 9)
        pytest.fail("the grandchild survived the cancel")


def test_a_missing_binary_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        stream.run(["/no/such/binary-xyz"], total_timeout=5)


# ---------------------------------------------------------------- labels

def test_labels():
    repo = events.REPO.replace("\\", "/")
    assert events.label("Bash", {"command": f"python3 {repo}/scripts/trace_width.py --amps 2"}) \
        == "Running trace_width.py --amps 2"
    assert events.label("Bash", {"command": "ls /tmp"}) == "Running ls /tmp"
    assert events.label("Read", {"file_path": "/a/b/BOM.md"}) == "Reading BOM.md"
    assert events.label("Grep", {"pattern": "LDO"}) == "Searching for LDO"
    assert events.label("Glob", {"pattern": "*.md"}) == "Searching for *.md"
    assert events.label("WebSearch", {"query": "ams1117 dropout"}) == "Searching the web: ams1117 dropout"
    assert events.label("WebFetch", {"url": "https://www.ti.com/lit/ds/x.pdf"}) == "Opening www.ti.com"
    assert events.label("Skill", {"skill": "parts-and-stock"}) == "Opening skill parts-and-stock"
    assert events.label("Edit", {"file_path": "/p/notes.md"}) == "Editing notes.md"
    assert events.label("Write", {"file_path": "C:\\p\\x.csv"}) == "Editing x.csv"
    assert events.label("TodoWrite", {}) == "TodoWrite"
    assert len(events.label("Bash", {"command": "echo " + "x" * 300})) <= 80


# ---------------------------------------------------------------- error kinds

def test_classification():
    assert events.classify("Not logged in · Please run /login")[0] == "not_logged_in"
    assert events.classify("OAuth session expired and could not be refreshed")[0] == "not_logged_in"
    assert events.classify("Failed to authenticate")[0] == "not_logged_in"
    kind, retry = events.classify("Claude AI usage limit reached|1792000000")
    assert kind == "usage_limit" and retry.startswith("2026-")
    assert events.classify("You hit your usage limit")[:2] == ("usage_limit", None)
    assert events.classify("boom", "segfault", 1) == ("engine_error", None)


# ---------------------------------------------------------------- parse + provider

def _line(**kw):
    return json.dumps(kw, ensure_ascii=False)


STREAM = "\n".join([
    _line(type="system", subtype="init"),
    _line(type="assistant", message={"content": [
        {"type": "thinking", "thinking": "hm"},
        {"type": "tool_use", "id": "t1", "name": "Bash",
         "input": {"command": "ls /tmp && pwd", "description": "d"}}]}),
    _line(type="system", subtype="permission_denied", tool_name="Bash", tool_use_id="t1",
          decision_reason_type="subcommandResults", message="needs approval: ls /tmp"),
    _line(type="user", message={"content": [{"type": "tool_result", "content": "denied", "is_error": True}]}),
    _line(type="assistant", message={"content": [{"type": "text", "text": "Sorry, it needs approval."}]}),
    _line(type="result", result="Sorry, it needs approval.", is_error=False, num_turns=2,
          total_cost_usd=0.01, usage={"input_tokens": 5, "output_tokens": 7},
          permission_denials=[{"tool_name": "Bash", "tool_use_id": "t1",
                               "tool_input": {"command": "ls /tmp && pwd"}},
                              {"tool_name": "Read", "tool_use_id": "t2",
                               "tool_input": {"file_path": "/x/y.jsonl"}}]),
])


def test_parse_stream_json_lines_with_denials_merged_by_id():
    text, meta, err = ClaudeCodeProvider._parse(STREAM)
    assert err == "" and text == "Sorry, it needs approval."
    assert meta["steps"] == ["Running ls /tmp && pwd"]
    assert meta["usage"] == {"input_tokens": 5, "output_tokens": 7} and meta["turns"] == 2
    den = meta["denied"]
    assert len(den) == 2                                      # t1 merged, t2 added from the result
    assert den[0] == {"tool": "Bash", "input": {"command": "ls /tmp && pwd", "description": "d"},
                      "reason": "needs approval: ls /tmp", "compound": True}
    assert den[1] == {"tool": "Read", "input": {"file_path": "/x/y.jsonl"}, "reason": "", "compound": False}


def test_parse_still_takes_the_old_single_object_and_plain_text():
    one = json.dumps({"type": "result", "result": "hi", "is_error": False, "num_turns": 1})
    assert ClaudeCodeProvider._parse(one)[:1] == ("hi",)
    assert ClaudeCodeProvider._parse("just words\n") == ("just words\n", {}, "")
    text, meta, err = ClaudeCodeProvider._parse(_line(type="result", result="Not logged in · Please run /login",
                                                      is_error=True))
    assert text == "" and "Not logged in" in err


def _fake(monkeypatch, stdout="", rc=0, stderr="", ended="done", pause=None):
    def run(argv, stdin_text="", cwd=None, env=None, total_timeout=None, idle_timeout=None,
            cancel=None, on_line=None):
        for ln in stdout.splitlines():
            on_line(ln)
        return rc, stderr, ended
    monkeypatch.setattr(stream, "run", run)


def test_provider_emits_events_and_sets_meta(home, monkeypatch):
    _fake(monkeypatch, STREAM)
    evs = []
    res = gateway.route(gateway.Request(prompt="p", timeout=5, options={"on_event": evs.append}),
                        name="claude_code")
    assert res.ok and res.text == "Sorry, it needs approval."
    kinds = [e["kind"] for e in evs]
    assert kinds[:2] == ["thinking", "tool"] and "denied" in kinds and "text" in kinds
    tool = next(e for e in evs if e["kind"] == "tool")
    assert tool["tool"] == "Bash" and tool["label"].startswith("Running ls") and isinstance(tool["ts"], float)
    assert "error_kind" not in res.meta and "partial" not in res.meta


def test_text_events_are_throttled(home, monkeypatch):
    many = "\n".join(_line(type="assistant", message={"content": [{"type": "text", "text": f"t{i}"}]})
                     for i in range(20))
    _fake(monkeypatch, many, rc=0)
    evs = []
    res = gateway.route(gateway.Request(prompt="p", timeout=5, options={"on_event": evs.append}),
                        name="claude_code")
    assert [e["kind"] for e in evs] == ["text"]
    assert res.error                                          # no result line: reported, text kept
    assert res.text.startswith("t0") and "t19" in res.text


@pytest.mark.parametrize("ended,kind,idle", [("stopped", "stopped", 7), ("idle_timeout", "idle_timeout", 7),
                                             ("total_timeout", "total_timeout", 7)])
def test_stop_and_timeouts_keep_the_partial_text(home, monkeypatch, ended, kind, idle):
    part = "\n".join(STREAM.splitlines()[:5])                 # no result line yet
    _fake(monkeypatch, part, ended=ended, rc=None)
    res = gateway.route(gateway.Request(prompt="p", timeout=9, options={"idle_timeout": idle}),
                        name="claude_code")
    assert not res.ok and res.text == "Sorry, it needs approval."
    assert res.meta["partial"] is True and res.meta["error_kind"] == kind
    assert res.meta["steps"] == ["Running ls /tmp && pwd"] and res.meta["denied"]


def test_not_logged_in_and_usage_limit_kinds(home, monkeypatch):
    _fake(monkeypatch, _line(type="result", result="Not logged in · Please run /login", is_error=True,
                             terminal_reason="api_error"), rc=1)
    res = gateway.route(gateway.Request(prompt="p", timeout=5), name="claude_code")
    assert not res.ok and res.meta["error_kind"] == "not_logged_in"
    _fake(monkeypatch, _line(type="result", result="Claude AI usage limit reached|1792000000", is_error=True), rc=1)
    res = gateway.route(gateway.Request(prompt="p", timeout=5), name="claude_code")
    assert res.meta["error_kind"] == "usage_limit" and res.meta["retry_at"].startswith("2026-")
    _fake(monkeypatch, "", rc=1, stderr="Failed to authenticate")
    assert gateway.route(gateway.Request(prompt="p", timeout=5), name="claude_code").meta["error_kind"] \
        == "not_logged_in"


def test_not_installed_kind(home, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(stream, "run", boom)
    import shutil
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: "/fake/" + cmd)
    res = gateway.route(gateway.Request(prompt="p", timeout=5), name="claude_code")
    assert res.meta["error_kind"] == "not_installed"
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None)
    res = gateway.provider("claude_code").complete(gateway.Request(prompt="p", timeout=5))
    assert not res.ok and res.meta.get("error_kind") == "not_installed"


def test_options_reach_the_runner(home, monkeypatch):
    seen = {}

    def run(argv, **kw):
        seen.update(kw)
        return 0, "", "done"
    monkeypatch.setattr(stream, "run", run)
    ev = threading.Event()
    gateway.route(gateway.Request(prompt="p", timeout=33, options={"cancel": ev, "idle_timeout": 11}),
                  name="claude_code")
    assert seen["cancel"] is ev and seen["idle_timeout"] == 11 and seen["total_timeout"] == 33
