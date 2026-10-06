"""The Antigravity provider: what reaches the `agy` command line."""
import shutil
import subprocess

import gateway
from gateway import antigravity


def _run(monkeypatch, **request):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["kw"] = list(argv), kw

        class R:
            returncode, stdout, stderr = 0, "ok", ""
        return R()

    monkeypatch.setattr(shutil, "which", lambda cmd: "/bin/" + cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = gateway.route(gateway.Request(prompt="hello", timeout=5, **request),
                        name="antigravity")
    return res, seen


def test_the_prompt_takes_the_place_of_the_dash(home, monkeypatch):
    res, seen = _run(monkeypatch)
    assert res.ok and res.text == "ok"
    assert seen["argv"][0] == "agy"
    assert "hello" in seen["argv"] and "-" not in seen["argv"]


def test_effort_reaches_the_cli_only_when_set(home, monkeypatch):
    import workspace
    _, seen = _run(monkeypatch)
    assert "--effort" not in seen["argv"]
    workspace.set_value("agent.providers.antigravity.effort", "high")
    _, seen = _run(monkeypatch)
    i = seen["argv"].index("--effort")
    assert seen["argv"][i + 1] == "high"


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
