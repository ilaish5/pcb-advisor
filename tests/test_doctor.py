"""`pcb.py doctor`: each check against a faked machine (a Probe subclass), the JSON contract, the exit codes,
the endpoint, and the CLI lookup that survives a stale PATH."""
import json
import pathlib
import threading
import urllib.request

import pytest

import doctor
import oscompat


class FakeProbe(doctor.Probe):
    """A healthy Mac, with a Claude CLI that is installed and signed in. Tests break one thing at a time."""
    windows = False
    version_info = (3, 12, 1)

    def __init__(self, tmp, **over):
        self.repo = tmp / "repo"
        (self.repo / ".venv" / "bin").mkdir(parents=True)
        (self.repo / ".venv" / "bin" / "python").write_text("")
        (self.repo / ".git").mkdir()
        self._home = tmp / "ws"
        self.cfg = {"agent.provider": "claude_code", "server.port": 8931}
        self.tools = {"git": "/usr/bin/git", "claude": "/u/.local/bin/claude"}
        self.runs = {"--version": (0, "2.1.304 (Claude Code)\n"),
                     "status": (0, '{"loggedIn": true, "authMethod": "claude.ai"}'),
                     "-c": (0, "")}
        self.port = "free"
        self.net = True
        self.altium = None
        self.uhome = tmp / "u"
        self.__dict__.update(over)

    def which(self, cmd):
        return self.tools.get(cmd)

    def run(self, argv, timeout=10):
        for key, val in self.runs.items():
            if key in argv:
                return val
        return 0, ""

    def home(self):
        return self._home

    def user_home(self):
        return self.uhome

    def config(self, key, default=None):
        return self.cfg.get(key, default)

    def port_state(self, port):
        return self.port

    def reachable(self, url, timeout=3):
        return self.net

    def altium_exe(self):
        return self.altium


def by_id(res):
    return {c["id"]: c for c in res["checks"]}


def test_a_healthy_machine_is_ready(tmp_path):
    res = doctor.run(FakeProbe(tmp_path))
    assert res["ok"] and res["can_start"]
    got = by_id(res)
    assert {k: got[k]["status"] for k in ("python", "venv", "requirements", "git", "claude", "claude_signin", "network", "port", "workspace")} == \
        {k: "ok" for k in ("python", "venv", "requirements", "git", "claude", "claude_signin", "network", "port", "workspace")}
    assert got["altium"]["status"] == "skip"           # macOS


def test_every_check_has_the_documented_shape(tmp_path):
    for c in doctor.run(FakeProbe(tmp_path))["checks"]:
        assert set(c) == {"id", "title", "status", "detail", "fix", "blocking", "blocks_start"}
        assert c["status"] in ("ok", "warn", "fix", "skip")


def test_old_python_is_a_blocking_fix_with_a_command(tmp_path):
    res = doctor.run(FakeProbe(tmp_path, version_info=(3, 9, 6), windows=True))
    c = by_id(res)["python"]
    assert c["status"] == "fix" and c["blocking"] and c["blocks_start"]
    assert "winget install -e --id Python.Python.3.12 --scope user" in c["fix"]["command"]
    assert not res["ok"] and not res["can_start"]


def test_the_windows_store_stub_is_explained(tmp_path, monkeypatch):
    p = FakeProbe(tmp_path, windows=True)
    p.tools = {"python": r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe", "claude": "c"}
    c = by_id(doctor.run(p))["python_alias"]
    assert c["status"] == "warn" and "Store" in c["detail"]
    p.tools["py"] = r"C:\Windows\py.exe"
    assert "python_alias" not in by_id(doctor.run(p))


def test_missing_venv_and_packages_block_the_start(tmp_path):
    p = FakeProbe(tmp_path)
    (p.repo / ".venv" / "bin" / "python").unlink()
    c = by_id(doctor.run(p))
    assert c["venv"]["status"] == "fix" and c["venv"]["blocks_start"] and "install.sh" in c["venv"]["fix"]["command"]
    p = FakeProbe(tmp_path / "b")
    p.runs = {"-c": (1, "ModuleNotFoundError: No module named 'pypdf'")}
    c = by_id(doctor.run(p))["requirements"]
    assert c["status"] == "fix" and "pypdf" in c["detail"] and "pip install -r requirements.txt" in c["fix"]["command"]


def test_no_git_and_a_zip_install_are_warnings_not_failures(tmp_path):
    p = FakeProbe(tmp_path)
    p.tools.pop("git")
    c = by_id(doctor.run(p))["git"]
    assert c["status"] == "warn" and "Update" in c["detail"] and doctor.run(p)["ok"]
    p = FakeProbe(tmp_path / "z")
    (p.repo / ".git").rmdir()
    c = by_id(doctor.run(p))["git"]
    assert c["status"] == "warn" and "ZIP" in c["detail"]


def test_missing_claude_is_fix_with_the_official_installer_but_does_not_block_the_start(tmp_path):
    p = FakeProbe(tmp_path)
    p.tools.pop("claude")
    res = doctor.run(p)
    c = by_id(res)
    assert c["claude"]["status"] == "fix" and c["claude"]["blocking"] and not c["claude"]["blocks_start"]
    assert c["claude"]["fix"]["command"] == "curl -fsSL https://claude.ai/install.sh | bash"
    assert "claude_signin" not in c                         # nothing to sign in to yet
    assert not res["ok"] and res["can_start"]
    p.windows = True
    assert by_id(doctor.run(p))["claude"]["fix"]["command"] == "irm https://claude.ai/install.ps1 | iex"


def test_signed_out_claude_offers_the_login_command(tmp_path):
    p = FakeProbe(tmp_path)
    p.runs["status"] = (1, '{"loggedIn": false, "authMethod": "none"}')
    res = doctor.run(p)
    c = by_id(res)["claude_signin"]
    assert c["status"] == "fix" and c["blocking"] and "auth login" in c["fix"]["command"]
    assert res["can_start"]                                 # the UI first-run list shows the fix


def test_another_active_engine_makes_claude_only_a_warning(tmp_path):
    p = FakeProbe(tmp_path)
    p.tools.pop("claude")
    res = doctor.run(p, engine="antigravity")
    assert by_id(res)["claude"]["status"] == "warn"
    assert by_id(res)["agy"]["status"] == "fix"             # agy is not there either
    p.tools["agy"] = "/x/agy"
    assert by_id(doctor.run(p, engine="antigravity"))["agy"]["status"] == "ok"


def test_port_states(tmp_path):
    assert by_id(doctor.run(FakeProbe(tmp_path, port="ours")))["port"]["status"] == "ok"
    res = doctor.run(FakeProbe(tmp_path / "t", port="taken"))
    c = by_id(res)["port"]
    assert c["status"] == "fix" and c["blocks_start"] and "--port 8932" in c["fix"]["command"]


def test_workspace_not_writable(tmp_path):
    p = FakeProbe(tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    p._home = blocker / "ws"                                # a folder cannot be made under a file
    c = by_id(doctor.run(p))["workspace"]
    assert c["status"] == "fix" and c["blocks_start"]


def test_altium_only_asked_on_windows_and_never_blocking(tmp_path):
    c = by_id(doctor.run(FakeProbe(tmp_path, windows=True)))["altium"]
    assert c["status"] == "warn" and not c["blocking"]
    c = by_id(doctor.run(FakeProbe(tmp_path / "a", windows=True, altium=r"C:\A\X2.EXE")))["altium"]
    assert c["status"] == "ok"


def test_hebrew_path_and_no_network_only_warn(tmp_path):
    p = FakeProbe(tmp_path, net=False)
    p.uhome = tmp_path / "\u05d0\u05d9\u05dc\u05d0\u05d9"
    res = doctor.run(p)
    got = by_id(res)
    assert got["paths"]["status"] == "warn" and got["network"]["status"] == "warn"
    assert res["ok"]


def test_cli_text_and_exit_codes(tmp_path, monkeypatch, capsys):
    p = FakeProbe(tmp_path)
    monkeypatch.setattr(doctor, "Probe", lambda: p)
    assert doctor.main([]) == 0
    assert "Ready" in capsys.readouterr().out
    p.tools.pop("claude")
    assert doctor.main([]) == 1
    out = capsys.readouterr().out
    assert "FIX" in out and "claude.ai/install.sh" in out
    assert doctor.main(["--exit-start"]) == 0               # only the engine is missing: the server can start
    capsys.readouterr()
    assert doctor.main(["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["can_start"] is True
    p.port = "taken"
    assert doctor.main(["--exit-start"]) == 1


# ---- the CLI is found where the official installer puts it, with a stale PATH

def test_which_finds_the_installer_folder_when_path_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(oscompat.shutil, "which", lambda c: None)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    assert oscompat.which("claude") is None
    exe = tmp_path / ".local" / "bin" / ("claude.exe" if oscompat.WINDOWS else "claude")
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert oscompat.which("claude") == str(exe)
    assert oscompat.resolve("claude") == str(exe)
    assert oscompat.which("agy") is None                     # only claude has an installer folder
    assert oscompat.resolve("agy") == "agy"


def test_path_wins_over_the_installer_folder(monkeypatch):
    monkeypatch.setattr(oscompat.shutil, "which", lambda c: "/usr/bin/claude")
    assert oscompat.which("claude") == "/usr/bin/claude"


def test_the_engine_sees_claude_through_the_installer_folder(tmp_path, monkeypatch, home):
    import gateway
    monkeypatch.setattr(oscompat.shutil, "which", lambda c: None)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / ".local" / "bin" / ("claude.exe" if oscompat.WINDOWS else "claude")
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    prov = gateway.provider("claude_code")
    ok, why = prov.available()
    assert ok or "not on PATH" not in why


# ---- the endpoint

def test_api_doctor_returns_the_same_json(home, monkeypatch, tmp_path):
    import serve
    from http.server import ThreadingHTTPServer
    p = FakeProbe(tmp_path)
    monkeypatch.setattr(doctor, "Probe", lambda: p)
    monkeypatch.setattr(doctor, "_cache", {"at": 0.0, "engine": None, "result": None})
    monkeypatch.setattr(serve, "QUIET", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urllib.request.urlopen(base + "/api/doctor", timeout=10) as r:
            got = json.loads(r.read())
        assert got["ok"] is True and {c["id"] for c in got["checks"]} >= {"python", "claude", "port"}
        p.tools.pop("claude")                                  # cached for 30 s, until ?refresh=1
        with urllib.request.urlopen(base + "/api/doctor", timeout=10) as r:
            assert json.loads(r.read())["ok"] is True
        with urllib.request.urlopen(base + "/api/doctor?refresh=1", timeout=10) as r:
            assert json.loads(r.read())["ok"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
