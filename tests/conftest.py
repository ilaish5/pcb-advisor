"""
Shared fixtures.

Every test runs against a throwaway workspace: PCB_ADVISOR_HOME points at a
temp directory, so `projects/` and `shared/` live there while the templates and
the UI still come from the repo. The worked example (lte-tracker) is seeded
into that workspace by the `lte` fixture.
"""
import os
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "skills"))


@pytest.fixture(autouse=True)
def engine_home(tmp_path_factory, monkeypatch):
    """The engine's folder, never the real one in the user's app data. It must sit
    outside any git tree (the pack refuses otherwise); pytest's temp dir does."""
    path = tmp_path_factory.mktemp("engine")
    monkeypatch.setenv("PCB_ADVISOR_ENGINE_HOME", str(path))
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A workspace of our own, with the config reloaded to match."""
    monkeypatch.setenv("PCB_ADVISOR_HOME", str(tmp_path))
    monkeypatch.setenv("PCB_ADVISOR_CONFIG", str(tmp_path / "config.json"))
    import workspace
    workspace.load(reload=True)
    (tmp_path / "projects").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    # A test may have left a deliberately broken config behind, and reloading it
    # raises. Teardown must still put the module back to a usable state.
    monkeypatch.undo()
    try:
        workspace.load(reload=True)
    except SystemExit:
        workspace._cache = None


@pytest.fixture
def lte(home):
    """The worked example, seeded into the temp workspace. Returns the project name."""
    import seed
    seed.seed()
    return seed.NAME


@pytest.fixture
def empty(home):
    """A project with nothing in it yet."""
    import project
    return project.create("empty", title="Empty")
