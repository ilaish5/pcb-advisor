"""pcb.py: bad arguments give a usage error (exit 2), read-only commands never create a project."""
import importlib
import sys

import pytest

import workspace


@pytest.fixture
def pcb(monkeypatch):
    monkeypatch.syspath_prepend(str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    return importlib.import_module("pcb")


def run(pcb, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["pcb.py", *argv])
    try:
        return pcb.main()
    except SystemExit as e:
        return e.code


def test_trace_bad_number_is_usage_error(pcb, monkeypatch, capsys):
    assert run(pcb, monkeypatch, "trace", "abc") == 2
    assert "usage: pcb.py trace" in capsys.readouterr().err


def test_trace_bad_option_value(pcb, monkeypatch, capsys):
    assert run(pcb, monkeypatch, "trace", "1.5", "--oz", "x") == 2


def test_bench_bad_only(pcb, monkeypatch, capsys):
    assert run(pcb, monkeypatch, "bench", "--only", "a,b") == 2


@pytest.mark.parametrize("cmd", ["show", "check", "outputs", "usage", "timeline", "chats", "reset"])
def test_unknown_project_not_created(pcb, monkeypatch, capsys, cmd):
    code = run(pcb, monkeypatch, cmd, "nosuchproject")
    assert code not in (0, None)
    assert "no project named nosuchproject" in capsys.readouterr().err
    assert not (workspace.projects_dir() / "nosuchproject").exists()


def test_calc_prog_name(pcb, monkeypatch, capsys):
    run(pcb, monkeypatch, "calc", "led")
    assert "pcb.py calc led" in capsys.readouterr().err
