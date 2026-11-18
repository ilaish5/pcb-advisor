"""U5 readiness banner and U8 install/port: the readiness answer per case, the banner source, the port probe on real
sockets, and the install.ps1 / start.bat text."""
import json
import pathlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


import project as project_mod
import serve
from ui_source import UI

REPO = pathlib.Path(__file__).resolve().parent.parent
PS1 = (REPO / "install.ps1").read_text(encoding="utf-8")
BAT = (REPO / "start.bat").read_text(encoding="utf-8")


# ------------------------------------------------------------------ readiness

def _patch(monkeypatch, engine_ok=True, altium_ok=True, linked=True, past=True, sheets=False):
    class Prov:
        def available(self):
            return (True, "") if engine_ok else (False, "`claude` is not on PATH")
    monkeypatch.setattr(serve.gateway, "provider", lambda name=None: Prov())
    monkeypatch.setattr(serve.gateway, "resolve", lambda b=None: "claude_code")
    monkeypatch.setattr(sys, "platform", "win32")
    from altium import bridge

    def exe():
        if not altium_ok:
            raise bridge.BridgeError("Altium Designer was not found.")
        return "X2.EXE"
    monkeypatch.setattr(bridge, "_exe", exe)
    monkeypatch.setattr(project_mod, "altium_link", lambda n: {"project_file": "a.PrjPcb" if linked else ""})
    monkeypatch.setattr(serve, "_past_idea", lambda n: past)
    monkeypatch.setattr(serve.store, "sheet_ids", lambda n: ["s1"] if sheets else [])


def ids(res):
    return [p["id"] for p in res["problems"]]


def test_everything_ready_is_empty(monkeypatch):
    _patch(monkeypatch)
    assert serve.readiness("demo") == {"problems": []}


def test_engine_missing(monkeypatch):
    _patch(monkeypatch, engine_ok=False)
    res = serve.readiness("demo")
    assert ids(res) == ["engine"]
    assert "not on PATH" in res["problems"][0]["title"] and res["problems"][0]["fix"]


def test_altium_missing(monkeypatch):
    _patch(monkeypatch, altium_ok=False)
    assert ids(serve.readiness("demo")) == ["altium"]


def test_project_not_linked(monkeypatch):
    _patch(monkeypatch, linked=False)
    assert ids(serve.readiness("demo")) == ["link"]


def test_all_three(monkeypatch):
    _patch(monkeypatch, False, False, False)
    assert ids(serve.readiness("demo")) == ["engine", "link"]      # not linked and no drawing: Altium is not needed yet
    _patch(monkeypatch, False, False, True)
    assert ids(serve.readiness("demo")) == ["engine", "altium"]


def test_idea_stage_project_shows_no_link_row(monkeypatch):
    _patch(monkeypatch, linked=False, past=False)
    assert serve.readiness("demo") == {"problems": []}


def test_altium_missing_is_silent_without_link_or_drawing(monkeypatch):
    _patch(monkeypatch, altium_ok=False, linked=False, past=False)
    assert serve.readiness("demo") == {"problems": []}
    _patch(monkeypatch, altium_ok=False, linked=False, past=False, sheets=True)
    assert ids(serve.readiness("demo")) == ["altium"]


def test_no_doctor_merge():
    import inspect
    assert "import doctor" not in inspect.getsource(serve.readiness)


def test_probe_that_raises_does_not_break(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(serve.gateway, "provider", lambda name=None: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ids(serve.readiness("demo")) == ["engine"]


def test_banner_source():
    js = (UI / "js" / "ready.js").read_text(encoding="utf-8")
    assert "/api/readiness" in js and "data-ready-x" in js and "problems.length" in js
    assert "localStorage" in js and "try {" in js and "readyDismiss" in js
    assert "readyLoad()" in (UI / "js" / "boot.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert 'id="ready"' in html and html.index("/ui/js/ready.js") < html.index("/ui/js/boot.js")
    assert ".ready-bar" in (UI / "styles" / "shell.css").read_text(encoding="utf-8")


# ------------------------------------------------------------------ port probe

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _serve(body):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_port_holder_ours():
    srv = _serve(json.dumps({"version": "abc"}))
    try:
        assert serve.port_holder("127.0.0.1", srv.server_port) == "ours"
    finally:
        srv.shutdown()


def test_port_holder_foreign():
    srv = _serve("<html>hello</html>")
    try:
        assert serve.port_holder("127.0.0.1", srv.server_port) == "other"
    finally:
        srv.shutdown()


def test_port_holder_silent_socket():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)                         # accepts the connection in the backlog, never answers
    try:
        assert serve.port_holder("127.0.0.1", s.getsockname()[1], timeout=0.5) == "silent"
    finally:
        s.close()


def test_serve_on_a_foreign_port_exits_nonzero_without_the_browser(monkeypatch, capsys):
    srv = _serve("nope")
    opened = []
    monkeypatch.setattr(serve.webbrowser, "open", lambda u: opened.append(u))
    try:
        rc = serve.main(["--port", str(srv.server_port), "--host", "127.0.0.1"])
    finally:
        srv.shutdown()
    out = capsys.readouterr().out
    assert rc == serve.EXIT_PORT_TAKEN and rc not in (0, 75)
    assert not opened and str(srv.server_port) in out and "--port" in out and "pcb.py serve --port" in out


def _bind(monkeypatch, capsys, exc, who="other"):
    opened = []
    monkeypatch.setattr(serve.webbrowser, "open", lambda u: opened.append(u))
    monkeypatch.setattr(serve, "port_holder", lambda h, p, timeout=2.0: who)
    rc = serve._bind_failed(exc, "127.0.0.1", 8931, "http://127.0.0.1:8931", {"server": {"open_browser": True}}, False)
    return rc, capsys.readouterr().out, opened


def test_silent_holder_does_not_suggest_another_port(monkeypatch, capsys):
    import errno
    rc, out, opened = _bind(monkeypatch, capsys, OSError(errno.EADDRINUSE, "in use"), who="silent")
    assert rc == 78 and not opened
    assert "--port" not in out and "stuck" in out and "close it" in out


def test_reserved_port_and_bad_host_messages(monkeypatch, capsys):
    e = OSError(13, "denied")
    e.winerror = 10013
    rc, out, _ = _bind(monkeypatch, capsys, e)
    assert rc == 78 and "reserved by Windows" in out and "another program" not in out
    rc, out, _ = _bind(monkeypatch, capsys, socket.gaierror(11001, "no host"))
    assert rc == 78 and "not valid" in out and "another program" not in out


def test_in_use_and_ours_opens_browser(monkeypatch, capsys):
    import errno
    rc, out, opened = _bind(monkeypatch, capsys, OSError(errno.EADDRINUSE, "in use"), who="ours")
    assert rc == 0 and opened and "already running" in out


# ------------------------------------------------------------------ install

def test_installer_starts_the_server_in_its_own_window():
    assert "Start-Process" in PS1 and "start.bat" in PS1
    assert "cmd /c .\\start.bat" not in PS1


def test_installer_says_something_before_every_wait():
    lines = PS1.splitlines()

    def before(needle, window=3):
        idx = [i for i, l in enumerate(lines) if needle in l and not l.lstrip().startswith("#")]
        assert idx, needle
        for i in idx:
            assert any("Write-Host" in l or "Say " in l for l in lines[max(0, i - window):i]), (needle, lines[i])
    before("winget install -e")
    before("Pcb-Run git clone")
    before("Invoke-WebRequest")
    before("-m pip install --quiet --upgrade pip")
    before("-m pip install --quiet -r requirements.txt", window=2)
    before("claude.ai/install.ps1")
    before("antigravity.google")
    before("doctor --exit-start")


def test_start_bat_never_loops_on_the_port_code():
    assert "EQU 75" in BAT and "EQU 78" in BAT
    assert BAT.index("EQU 78") < BAT.index("NEQ 0") and "exit /b 78" in BAT
    assert serve.EXIT_PORT_TAKEN == 78
