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

# Session default for the run log's folder: a request thread that finishes after its test (and its monkeypatch) is over still writes
# here, never to the real logs/ folder.
import tempfile  # noqa: E402
os.environ["PCB_ADVISOR_LOG_DIR"] = tempfile.mkdtemp(prefix="pcb-runlog-")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach the internet. Background jobs (stock checks after a chat turn or a BOM change) would
    otherwise ask JLC from any test that forgot to stub them. Loopback stays open for the test servers."""
    import socket
    real = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
            raise OSError(f"test tried to reach the network: {address!r}")
        return real(self, address)
    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture(autouse=True)
def altium_host_ok(monkeypatch, request):
    """The bridge refuses a host that is not Windows before it writes anything (bridge._host_check). The stubbed-Altium tests run on any
    machine, so the check is off for them; a test that asks for the `real_host_check` fixture gets the real one."""
    if "real_host_check" in request.fixturenames:
        return
    from altium import bridge
    monkeypatch.setattr(bridge, "_host_check", lambda: None)


@pytest.fixture
def real_host_check():
    return True


@pytest.fixture(autouse=True)
def routed_board(request, monkeypatch):
    """The board gate (store.route_state: unrouted nets, a board never routed or checked) reads board-log.jsonl, which a test
    project has none of. Tests about anything else stand on a routed, clean board; a test of the gate itself is marked route_gate
    and reads the real record."""
    if request.node.get_closest_marker("route_gate"):
        return
    import store
    monkeypatch.setattr(store, "route_state", lambda project: {"ready": True, "why": "", "unrouted": 0, "open_nets": []})


@pytest.fixture(autouse=True)
def engine_home(tmp_path_factory, monkeypatch):
    """The engine's folder, never the real one in the user's app data. It must sit
    outside any git tree (the pack refuses otherwise); pytest's temp dir does."""
    path = tmp_path_factory.mktemp("engine")
    monkeypatch.setenv("PCB_ADVISOR_ENGINE_HOME", str(path))
    return path


@pytest.fixture(autouse=True)
def run_log_dir(tmp_path_factory, monkeypatch):
    """The run log never goes to the real logs/ folder. A test that checks the log points PCB_ADVISOR_LOG_DIR at its own."""
    monkeypatch.setenv("PCB_ADVISOR_LOG_DIR", str(tmp_path_factory.mktemp("runlog")))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A workspace of our own, with the config reloaded to match."""
    monkeypatch.setenv("PCB_ADVISOR_HOME", str(tmp_path))
    monkeypatch.setenv("PCB_ADVISOR_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path / "userhome"))   # no test reads the real Downloads
    import workspace
    workspace.load(reload=True)
    monkeypatch.setattr(workspace, "_shell_downloads", lambda: None)      # nor the real folder Windows points to
    (tmp_path / "projects").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    # A chat follow-up or retry runs in its own thread and may outlive its test: stop it while the test's fakes are still in place,
    # so it never calls the real engine or writes into the next test's project.
    serve = sys.modules.get("serve")
    if serve is not None:
        serve.cancel_followups(lambda k: True, wait=5.0)
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


# ------------------------------------------------------------------ platform tests
# `windows`: needs Windows itself; `altium`: needs a live Altium Designer. Off those machines they are skipped with the reason,
# never failed. CI runs -m "not windows and not altium"; the Windows PC runs -m "windows or altium" (docs/TESTING.md).

def pytest_collection_modifyitems(config, items):
    on_windows = os.name == "nt"
    with_altium = os.environ.get("PCB_ADVISOR_ALTIUM") == "1"
    skip_windows = pytest.mark.skip(reason="needs Windows (marked `windows`; runs on the Windows PC, os.name == 'nt')")
    skip_altium = pytest.mark.skip(reason="needs a live Altium Designer (marked `altium`; set PCB_ADVISOR_ALTIUM=1 on the Altium PC)")
    for item in items:
        if not on_windows and item.get_closest_marker("windows"):
            item.add_marker(skip_windows)
        if not with_altium and item.get_closest_marker("altium"):
            item.add_marker(skip_altium)
