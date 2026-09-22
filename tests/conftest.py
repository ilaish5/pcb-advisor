"""
Shared fixtures.

Every test runs against a throwaway workspace: PCB_ADVISOR_HOME points at a
temp directory, so `projects/` and `shared/` live there while the corpus, the
templates and the UI still come from the repo. That is exactly the split
workspace.py exists to make, so testing it this way tests it too.
"""
import json
import os
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A workspace of our own, with the config reloaded to match."""
    monkeypatch.setenv("PCB_ADVISOR_HOME", str(tmp_path))
    monkeypatch.setenv("PCB_ADVISOR_CONFIG", str(tmp_path / "config.json"))
    import workspace
    workspace.load(reload=True)
    (tmp_path / "projects").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    workspace.load(reload=True)


@pytest.fixture
def board(home):
    """A project builder. Give it blocks, links and decisions; get its name.

    The sketch has to be confirmed for anything to load, which is the rule that
    stops a student being asked cascade questions about a diagram they have not
    agreed to yet.
    """
    import workspace

    def make(name="test", blocks=(), links=(), decisions=(), confirmed=True):
        d = workspace.projects_dir() / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.json").write_text(
            json.dumps({"title": name, "board": {}}), encoding="utf-8")
        (d / "sketch.json").write_text(json.dumps({
            "brief": "", "confirmed": confirmed,
            "blocks": [{"id": b[0], "kind": b[1], "label": b[2] if len(b) > 2 else b[0]}
                       for b in blocks],
            "links": [list(l) for l in links],
        }), encoding="utf-8")
        with open(d / "decisions.jsonl", "w", encoding="utf-8") as fh:
            for ev in decisions:
                fh.write(json.dumps({"ts": "2026-01-01T00:00:00", "by": "user", **ev}) + "\n")
        return name

    return make


@pytest.fixture
def battery_mcu(board):
    """The design the whole review turned on: cells straight into an MCU."""
    return board(
        blocks=(("BAT", "power_in", "2xAA"), ("MCU", "mcu", "MCU")),
        links=(("BAT", "MCU"),),
        decisions=({"node": "req.source", "value": "battery"},
                   {"node": "req.vout", "value": "v3v3"},
                   {"node": "req.iload", "value": "i_low"}),
    )
