"""
Self-awareness: one line per engine turn, a summary the agent and the UI read, the engine's own accounting parsed,
and the update endpoints the UI's Update button drives.
"""
import json

import introspect
import serve
import update
from gateway.antigravity import AntigravityProvider
from gateway.claude_code import ClaudeCodeProvider

from test_server import get, post, server  # noqa: F401  (the fixture)

CC_RESULT = {"type": "result", "subtype": "success", "is_error": False, "result": "C1 is 100 nF {{src:a.pdf|p. 3}}",
             "num_turns": 3, "duration_ms": 4200, "total_cost_usd": 0.0123,
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 900, "output_tokens": 55},
             "modelUsage": {"claude-sonnet-5-5": {}}}


def _res(**meta):
    return {"provider": "claude_code", "usage": {"usage": {"input_tokens": 10, "output_tokens": 5}, **meta}, "tools": []}


def test_claude_code_json_is_parsed_into_text_and_cost():
    text, meta, err = ClaudeCodeProvider._parse(json.dumps(CC_RESULT))
    assert text.startswith("C1 is 100 nF") and not err
    assert meta["cost_usd"] == 0.0123 and meta["turns"] == 3 and meta["models"] == ["claude-sonnet-5-5"]
    assert meta["usage"] == {"input_tokens": 10, "cache_read_input_tokens": 900, "output_tokens": 55}


def test_claude_code_plain_text_and_errors_pass_through():
    assert ClaudeCodeProvider._parse("just text") == ("just text", {}, "")
    text, meta, err = ClaudeCodeProvider._parse(json.dumps({**CC_RESULT, "is_error": True, "result": "rate limited"}))
    assert text == "" and err == "rate limited" and meta["cost_usd"] == 0.0123


def test_agy_usage_is_read_when_reported():
    out = 'noise\n{"event":"result","result":{"status":"SUCCESS","response":"hi","usage":{"promptTokenCount":7,"candidatesTokenCount":3}}}\n'
    assert AntigravityProvider._usage(out) == {"input_tokens": 7, "output_tokens": 3}
    assert AntigravityProvider._usage("no json") == {}


def test_turns_are_recorded_and_summarised(empty):
    introspect.record(empty, "s1", "chat", {**_res(cost_usd=0.02), "tools": [{"t": "check_availability.py"}]}, 3.0,
                      reply="R1 is 10 kΩ", applied=1)
    introspect.record(empty, "s1", "chat", _res(), 2.0, reply="Use 0.2 mm traces")          # a number, no source
    introspect.record(empty, "s1", "chat", {"provider": "claude_code", "error": True, "reply": "timed out"}, 180.0)
    introspect.record(empty, "s1", "memory", _res(cost_usd=0.01), 1.0)
    rows = introspect.turns(empty)
    assert [r["kind"] for r in rows] == ["chat", "chat", "chat", "memory"]
    assert rows[0]["tokens_in"] == 10 and rows[0]["sourced"] and not rows[1]["sourced"]
    assert rows[2]["ok"] is False and rows[2]["error"] == "timed out"
    s = introspect.summary(empty)
    assert s["turns"] == 4 and s["failed"] == 1 and s["cost_usd"] == 0.03 and s["uncosted_turns"] == 2
    assert s["with_numbers"] == 2 and s["sourced"] == 1 and s["sourced_pct"] == 50
    assert s["scripts"] == {"check_availability.py": 1} and s["applied"] == 1
    assert s["last_error"]["error"] == "timed out"


def test_cli_answers_about_itself(empty, capsys):
    introspect.record(empty, "s", "chat", _res(cost_usd=0.5), 2.0, reply="ok")
    assert introspect.main([empty]) == 0
    out = capsys.readouterr().out
    assert "pcb-advisor" in out and "1 engine turns" in out and "$0.50" in out
    assert introspect.main([empty, "errors"]) == 0 and "none" in capsys.readouterr().out


def test_the_update_check_is_served_and_saved_for_the_agent(server, empty, home, monkeypatch):  # noqa: F811
    fake = {"kind": "git", "behind": 2, "can_update": True, "commits": [{"sha": "abc", "date": "", "subject": "x"}],
            "reason": "", "error": "", "latest": "abc"}
    monkeypatch.setattr(update, "check", lambda fetch=True: dict(fake))
    monkeypatch.setitem(serve.UPDATE, "state", "idle")
    code, st = get(server, "/api/update?refresh=1", empty)
    assert code == 200 and st["state"] == "done" and st["behind"] == 2 and st["can_update"] and "commit" in st["version"]
    assert introspect.update_status()["behind"] == 2          # what introspect.py version tells the agent


def test_update_is_refused_while_the_agent_answers(server, empty, monkeypatch):  # noqa: F811
    monkeypatch.setitem(serve.BUSY, "chat", 1)
    code, res = post(server, "/api/update", {}, empty)
    assert code == 409 and "answering" in res["error"]


def test_a_failed_update_says_why_and_does_not_restart(server, empty, monkeypatch):  # noqa: F811
    monkeypatch.setitem(serve.UPDATE, "state", "done")
    monkeypatch.setattr(update, "apply", lambda: {"ok": False, "from": "a", "to": "a", "commits": [],
                                                  "rolled_back": True, "reason": "The new version did not start (x)."})
    restarted = []
    monkeypatch.setattr(serve, "restart", lambda: restarted.append(1))
    code, res = post(server, "/api/update", {}, empty)
    assert code == 400 and res["error"].startswith("The new version did not start") and not restarted


def test_a_good_update_schedules_the_restart(server, empty, monkeypatch):  # noqa: F811
    monkeypatch.setitem(serve.UPDATE, "state", "done")
    monkeypatch.setattr(update, "apply", lambda: {"ok": True, "from": "a", "to": "b", "commits": [],
                                                  "rolled_back": False, "reason": ""})
    monkeypatch.setattr(serve, "HTTPD", object())
    fired = []
    monkeypatch.setattr(serve, "restart", lambda: fired.append(1))
    code, res = post(server, "/api/update", {}, empty)
    assert code == 200 and res["restarting"] and res["to"] == "b"
    import time
    time.sleep(0.8)
    assert fired == [1]


def test_restart_exits_75_for_start_bat_on_windows(monkeypatch):
    import os
    import pytest
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("PCB_ADVISOR_LAUNCHER", "start.bat")
    with pytest.raises(SystemExit) as e:
        serve._start_again(["--project", "x"])
    assert e.value.code == serve.RESTART_EXIT == 75


def test_introspect_endpoint(server, lte):  # noqa: F811
    code, r = get(server, "/api/introspect", lte)
    assert code == 200 and r["summary"]["project"] == lte and "counts" in r["outputs"] and "commit" in r["version"]


def test_the_ui_loads_the_update_button_before_boot():
    import pathlib
    ui = pathlib.Path(__file__).resolve().parent.parent / "ui"
    html = (ui / "index.html").read_text(encoding="utf-8")
    assert html.index("/ui/js/update.js") < html.index("/ui/js/boot.js")
    assert "updLoad(false)" in (ui / "js" / "boot.js").read_text(encoding="utf-8")
    shell = (ui / "js" / "shell.js").read_text(encoding="utf-8")
    assert "typeof updNavBtn === 'function' ? updNavBtn() : ''" in shell


def test_start_bat_starts_the_server_again_on_the_restart_code():
    import pathlib
    bat = (pathlib.Path(__file__).resolve().parent.parent / "start.bat").read_text(encoding="utf-8")
    assert f"if %ERRORLEVEL% EQU {serve.RESTART_EXIT} (set PCB_ARGS=--no-browser & goto run)" in bat
    assert "set PCB_ADVISOR_LAUNCHER=start.bat" in bat
