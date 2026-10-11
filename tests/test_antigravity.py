"""The Antigravity provider: what reaches the `agy` command line."""
import json
import shutil
import subprocess

import gateway
from gateway import antigravity


def _stream(response="ok", status="SUCCESS", noise=True):
    lines = ["logging before google.Init"] if noise else []
    lines.append(json.dumps({"event": "assistant", "text": "thinking"}))
    lines.append(json.dumps({"event": "result",
                             "result": {"status": status, "response": response}},
                            ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _run(monkeypatch, prompt="hello", stdout=None, returncode=0, stderr="",
         options=None):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["kw"] = list(argv), kw

        class R:
            pass
        r = R()
        r.returncode, r.stdout, r.stderr = returncode,             _stream() if stdout is None else stdout, stderr
        return r

    monkeypatch.setattr(shutil, "which", lambda cmd: "/bin/" + cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = gateway.route(gateway.Request(prompt=prompt, timeout=5,
                                        options=options or {}),
                        name="antigravity")
    return res, seen


def test_the_prompt_goes_on_stdin_as_stream_json(home, monkeypatch):
    res, seen = _run(monkeypatch)
    assert res.ok and res.text == "ok"
    # the full path which() found: on Windows the CLI may be agy.cmd, which
    # subprocess cannot start by its bare name
    assert seen["argv"][0] == "/bin/agy"
    assert "hello" not in seen["argv"] and "-" not in seen["argv"]
    assert seen["argv"][1:7] == ["-p=", "--input-format", "stream-json",
                                 "--output-format", "stream-json",
                                 "--dangerously-skip-permissions"]
    assert seen["kw"]["encoding"] == "utf-8"
    assert json.loads(seen["kw"]["input"]) == {
        "event": "user", "message": {"role": "user", "content": "hello"}}


def test_a_huge_hebrew_prompt_arrives_intact_on_stdin(home, monkeypatch):
    prompt = ("שלום עולם, מעגל מודפס\n" * 6000)[:100_000]
    assert len(prompt) == 100_000
    res, seen = _run(monkeypatch, prompt=prompt, stdout=_stream("תשובה בעברית"))
    assert res.text == "תשובה בעברית"
    assert all(len(a) < 200 and "שלום" not in a for a in seen["argv"])
    sent = seen["kw"]["input"]
    assert sent.endswith("\n") and sent.count("\n") == 1   # one NDJSON line
    assert json.loads(sent)["message"]["content"] == prompt


def test_noise_lines_are_skipped(home, monkeypatch):
    out = "logging before google.Init\n{broken json\n" + _stream("fine", noise=False)
    res, _ = _run(monkeypatch, stdout=out)
    assert res.ok and res.text == "fine"


def test_a_missing_result_event_is_an_error_with_a_tail(home, monkeypatch):
    res, _ = _run(monkeypatch, stdout="logging before google.Init\nsome tail text\n",
                  stderr="boom detail")
    assert not res.ok
    assert "no result event" in res.error and "some tail text" in res.error
    assert "boom detail" in res.error


def test_a_non_success_status_is_an_error(home, monkeypatch):
    res, _ = _run(monkeypatch, stdout=_stream("partial", status="ERROR"))
    assert not res.ok and "ERROR" in res.error


def test_an_error_field_in_the_result_is_surfaced(home, monkeypatch):
    out = json.dumps({"event": "result", "result": {"status": "SUCCESS",
                                                    "error": "quota exceeded"}})
    res, _ = _run(monkeypatch, stdout=out)
    assert not res.ok and "quota exceeded" in res.error


def test_nonzero_exit_reports_stderr(home, monkeypatch):
    res, _ = _run(monkeypatch, stdout="", returncode=2, stderr="not signed in")
    assert not res.ok and "not signed in" in res.error


def test_user_args_keep_extra_flags_and_lose_the_old_print_mode(home, monkeypatch):
    import workspace
    workspace.set_value("agent.providers.antigravity.args",
                        ["-p", "-", "--output-format", "text", "--mode", "accept-edits"])
    _, seen = _run(monkeypatch)
    argv = seen["argv"]
    assert argv.count("-p=") == 1 and "-" not in argv and "-p" not in argv
    assert argv.count("--output-format") == 1
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--mode" in argv and "accept-edits" in argv


def test_model_wins_over_effort_and_the_drop_is_reported(home, monkeypatch):
    import workspace
    workspace.set_value("agent.providers.antigravity.effort", "low")
    workspace.set_value("agent.providers.antigravity.model", "gemini-3.8-flash-high")
    res, seen = _run(monkeypatch)
    assert "--effort" not in seen["argv"]
    assert seen["argv"][seen["argv"].index("--model") + 1] == "gemini-3.8-flash-high"
    assert res.meta["dropped"] == ["effort"]


def test_effort_reaches_the_cli_only_when_set(home, monkeypatch):
    import workspace
    _, seen = _run(monkeypatch)
    assert "--effort" not in seen["argv"]
    workspace.set_value("agent.providers.antigravity.effort", "high")
    res, seen = _run(monkeypatch)
    i = seen["argv"].index("--effort")
    assert seen["argv"][i + 1] == "high"
    assert "--model" not in seen["argv"] and "dropped" not in res.meta


def test_add_dirs_become_add_dir_flags(home, monkeypatch):
    _, seen = _run(monkeypatch, options={"add_dirs": ["C:/a b", "C:/c"]})
    argv = seen["argv"]
    assert argv[-4:] == ["--add-dir", "C:/a b", "--add-dir", "C:/c"]
    _, seen = _run(monkeypatch, options={"add_dirs": []})
    assert "--add-dir" not in seen["argv"]


def test_an_unknown_effort_is_reported_not_passed(home, monkeypatch):
    import workspace
    workspace.set_value("agent.providers.antigravity.effort", "extreme")
    res, seen = _run(monkeypatch)
    assert not res.ok and "effort" in res.error
    assert "argv" not in seen


def test_a_hanging_model_list_does_not_hang_describe(home, monkeypatch):
    seen = {}

    def hang(argv, **kw):
        # describe() swallows exceptions, so record rather than assert in here
        seen["timeout"] = kw.get("timeout")
        raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)

    monkeypatch.setattr(antigravity, "_AGY_MODELS_CACHE", None)
    monkeypatch.setattr(shutil, "which", lambda cmd: "/bin/" + cmd)
    monkeypatch.setattr(subprocess, "check_output", hang)
    assert gateway.provider("antigravity").describe()["models"] == []
    assert seen["timeout"], "agy models must run with a timeout"


def test_agy_never_waits_on_the_terminal(home, monkeypatch):
    _, seen = _run(monkeypatch)
    # stdin is a pipe fed with the prompt (input=), never the inherited terminal
    assert seen["kw"].get("input") and "stdin" not in seen["kw"]
