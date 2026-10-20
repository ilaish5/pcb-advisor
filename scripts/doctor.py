"""
`python pcb.py doctor` - is this computer ready to run pcb-advisor, and if not, what is the one thing to do.

    python pcb.py doctor            one line per check
    python pcb.py doctor --json     the same as JSON (what GET /api/doctor returns)
    python pcb.py doctor --exit-start   exit 1 only when the server cannot start (used by the installers)
    python pcb.py doctor --engine antigravity   judge another engine than the configured one

Each check has a status:
    ok    fine
    warn  works, but something is limited (no git: Update is off; no JLC network: no stock checks)
    fix   something is missing; `fix.command` is what to run (or `fix.click` is what to press in the UI)
    skip  does not apply here (Altium on macOS)
`blocking` is true for a `fix` that stops the tool being useful (exit code 1); `blocks_start` is the subset that
stops the SERVER from starting (Python, venv, requirements, workspace, port). A missing or signed-out engine does
not block the start: the UI's first-run list shows the fix.

Doctor only looks. It never installs, never writes config, never signs in; the installers do that and call it after.
Every outside fact comes through a Probe, so the tests fake the machine instead of the code.
"""
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import oscompat    # noqa: E402
import workspace   # noqa: E402

MIN_PY = (3, 10)
CLAUDE_INSTALL_WIN = "irm https://claude.ai/install.ps1 | iex"
CLAUDE_INSTALL_UNIX = "curl -fsSL https://claude.ai/install.sh | bash"
REQUIRED_MODULES = "import pypdf, olefile, PIL"
JLC_URL = "https://jlcpcb.com"


class Probe:
    """The machine, as the checks see it. Tests replace the methods they care about."""
    windows = oscompat.WINDOWS
    version_info = tuple(sys.version_info[:3])
    repo = workspace.REPO

    def which(self, cmd):
        return oscompat.which(cmd)

    def run(self, argv, timeout=10):
        """(returncode, stdout+stderr) or (None, reason) when it could not start or timed out."""
        try:
            p = subprocess.run(argv, capture_output=True, timeout=timeout, env=oscompat.child_env(), **oscompat.TEXT)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, str(exc)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def venv_python(self):
        sub = ("Scripts", "python.exe") if self.windows else ("bin", "python")
        return self.repo.joinpath(".venv", *sub)

    def home(self):
        return workspace.home()

    def user_home(self):
        return pathlib.Path.home()

    def config(self, key, default=None):
        return workspace.get(key, default)

    def port_state(self, port):
        """'free' | 'ours' (a pcb-advisor server answers) | 'taken'."""
        s = socket.socket()
        s.settimeout(1)
        try:
            s.bind(("127.0.0.1", port))
            return "free"
        except OSError:
            pass
        finally:
            s.close()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/update", timeout=2) as r:
                return "ours" if "version" in json.loads(r.read().decode("utf-8", "replace")) else "taken"
        except Exception:
            return "taken"

    def reachable(self, url, timeout=3):
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout).close()
            return True
        except Exception as exc:
            return hasattr(exc, "code")         # an HTTP error status still means the network works

    def altium_exe(self):
        try:
            import altium.bridge as bridge
            return bridge._exe()
        except Exception:
            return None


def _check(cid, title, status, detail="", command=None, click=None, blocking=False, blocks_start=False):
    fix = {"command": command, "click": click} if (command or click) else None
    return {"id": cid, "title": title, "status": status, "detail": detail, "fix": fix,
            "blocking": bool(blocking and status == "fix"), "blocks_start": bool(blocks_start and status == "fix")}


def _claude_install_cmd(p):
    return CLAUDE_INSTALL_WIN if p.windows else CLAUDE_INSTALL_UNIX


def check_python(p):
    v = p.version_info
    label = "Python %d.%d.%d" % tuple(v[:3])
    if tuple(v[:2]) >= MIN_PY:
        return _check("python", "Python 3.10 or newer", "ok", label)
    fix = ("winget install -e --id Python.Python.3.12 --scope user" if p.windows
           else ("brew install python@3.12" if p.which("brew") else "https://www.python.org/downloads/"))
    return _check("python", "Python 3.10 or newer", "fix", f"{label} is too old", command=fix,
                  blocking=True, blocks_start=True)


def check_python_alias(p):
    """Windows only: `python` that is the Microsoft Store stub opens the Store instead of running."""
    if not p.windows:
        return None
    path = p.which("python")
    if path and oscompat._is_store_stub(path) and not p.which("py"):
        return _check("python_alias", "`python` command", "warn",
                      "`python` is the Microsoft Store shortcut, not Python. Install Python from python.org or with "
                      "winget, or turn off Settings > Apps > Advanced app settings > App execution aliases > python.exe.",
                      command="winget install -e --id Python.Python.3.12 --scope user")
    return None


def check_venv(p):
    py = p.venv_python()
    if not py.is_file():
        return _check("venv", "Private Python environment (.venv)", "fix", "no .venv in the install folder",
                      command=("install.bat" if p.windows else "./install.sh"), blocking=True, blocks_start=True)
    rc, out = p.run([str(py), "-c", "pass"])
    if rc != 0:
        return _check("venv", "Private Python environment (.venv)", "fix", "the .venv does not run (moved or broken)",
                      command=("install.bat" if p.windows else "./install.sh"), blocking=True, blocks_start=True)
    return _check("venv", "Private Python environment (.venv)", "ok", str(py.parent.parent))


def check_requirements(p):
    py = p.venv_python()
    exe = str(py) if py.is_file() else sys.executable
    rc, out = p.run([exe, "-c", REQUIRED_MODULES], timeout=30)
    if rc == 0:
        return _check("requirements", "Python packages", "ok", "pypdf, olefile, pillow")
    return _check("requirements", "Python packages", "fix", (out or "import failed").strip().splitlines()[-1][:200],
                  command=f'"{exe}" -m pip install -r requirements.txt', blocking=True, blocks_start=True)


def check_git(p):
    if not p.which("git"):
        cmd = "winget install -e --id Git.Git --scope user" if p.windows else "xcode-select --install"
        return _check("git", "git (for Update)", "warn", "git is not installed: everything works, but the in-app "
                      "Update stays off. After installing git, run the installer again.", command=cmd)
    if not (p.repo / ".git").exists():
        return _check("git", "git (for Update)", "warn", "this folder is a ZIP download, not a git clone: Update is off. "
                      "Run the installer again in this folder: it turns it into a clone and keeps your projects.")
    return _check("git", "git (for Update)", "ok", "git clone, Update works")


def _engine_is(p, engine, name):
    return (engine or p.config("agent.provider", "claude_code")) == name


def check_claude(p, engine=None):
    active = _engine_is(p, engine, "claude_code")
    cmd = p.config("agent.providers.claude_code.command", "claude") or "claude"
    path = p.which(cmd)
    title = "Claude Code" + ("" if active else " (not the active engine)")
    if not path:
        return _check("claude", title, "fix" if active else "warn", f"`{cmd}` was not found",
                      command=_claude_install_cmd(p), blocking=active)
    rc, out = p.run([path, "--version"], timeout=10)
    if rc != 0:
        return _check("claude", title, "fix" if active else "warn", "`claude --version` failed: " + (out or "").strip()[:120],
                      command=_claude_install_cmd(p), blocking=active)
    return _check("claude", title, "ok", (out or "").strip().splitlines()[0] if out else path)


def check_signin(p, engine=None, claude=None):
    """`claude auth status --json`: exit 0 + loggedIn means credentials exist. It cannot see an expired token; the
    first chat turn reports that as the not_logged_in card."""
    active = _engine_is(p, engine, "claude_code")
    cmd = p.config("agent.providers.claude_code.command", "claude") or "claude"
    path = p.which(cmd)
    if not path or (claude and claude["status"] != "ok"):
        return None                                 # nothing to sign in to yet; the install check says it all
    rc, out = p.run([path, "auth", "status", "--json"], timeout=15)
    logged = None
    try:
        logged = bool(json.loads(out[out.index("{"):]).get("loggedIn"))
    except (ValueError, AttributeError):
        logged = (rc == 0) if rc is not None else None
    if logged:
        return _check("claude_signin", "Claude sign-in", "ok", "signed in")
    if logged is None:
        return _check("claude_signin", "Claude sign-in", "warn", "could not ask Claude Code: " + str(out)[:120])
    return _check("claude_signin", "Claude sign-in", "fix" if active else "warn", "not signed in",
                  command=f"{cmd if path == oscompat.shutil.which(cmd) else path} auth login", blocking=active)


def check_agy(p, engine=None):
    if not _engine_is(p, engine, "antigravity"):
        return None
    cmd = p.config("agent.providers.antigravity.command", "agy") or "agy"
    if p.which(cmd):
        return _check("agy", "Antigravity (agy)", "ok", p.which(cmd))
    return _check("agy", "Antigravity (agy)", "fix", f"`{cmd}` was not found",
                  command="irm https://antigravity.google/cli/install.ps1 | iex" if p.windows else "see docs/ENGINES.md",
                  blocking=True)


def check_altium(p):
    if not p.windows:
        return _check("altium", "Altium Designer", "skip", "Altium runs on Windows only; reading files and the rest work here")
    exe = p.altium_exe()
    if exe:
        return _check("altium", "Altium Designer", "ok", exe)
    return _check("altium", "Altium Designer", "warn", "not found. Optional: only needed for 'Make in Altium'. "
                  "Set its folder in Settings (altium.install_path).", click="settings")


def check_network(p):
    if p.reachable(JLC_URL):
        return _check("network", "Network to JLCPCB", "ok", "jlcpcb.com reachable")
    return _check("network", "Network to JLCPCB", "warn", "jlcpcb.com is not reachable: part and stock checks will not work "
                  "(check the connection or the proxy settings)")


def check_port(p):
    port = int(p.config("server.port", 8931))
    state = p.port_state(port)
    if state == "free":
        return _check("port", f"Port {port}", "ok", "free")
    if state == "ours":
        return _check("port", f"Port {port}", "ok", "pcb-advisor is already running here")
    return _check("port", f"Port {port}", "fix", f"another program uses port {port}",
                  command=f"python pcb.py serve --port {port + 1}", blocking=True, blocks_start=True)


def check_workspace(p):
    home = p.home()
    try:
        for d in (home, home / "projects"):
            d.mkdir(parents=True, exist_ok=True)
            probe = d / f".doctor-{os.getpid()}.tmp"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
    except OSError as exc:
        return _check("workspace", "Writable workspace", "fix", f"cannot write in {home}: {exc}. Do not install under "
                      "Program Files; use a folder in your user profile.",
                      command="set PCB_ADVISOR_HOME to a folder you own", blocking=True, blocks_start=True)
    return _check("workspace", "Writable workspace", "ok", str(home))


def check_path_chars(p):
    """Warn only: it works for many people (Hebrew user names are common), but some tools trip on it."""
    text = str(p.repo) + str(p.user_home())
    if any(ord(c) > 127 for c in text):
        plain = "C:\\pcb-advisor" if p.windows else "~/pcb-advisor"
        return _check("paths", "Folder names", "warn", "a path contains non-English letters. This usually works; if "
                      f"pip or the engine fails with encoding errors, install in a folder like {plain}.")
    if "OneDrive" in str(p.repo):
        return _check("paths", "Folder names", "warn", "the install is inside OneDrive, which can lock files while syncing.")
    return None


def run(probe=None, engine=None):
    p = probe or Probe()
    checks = [check_python(p), check_python_alias(p), check_venv(p), check_requirements(p), check_git(p)]
    claude = check_claude(p, engine)
    checks += [claude, check_signin(p, engine, claude), check_agy(p, engine), check_altium(p), check_network(p),
               check_port(p), check_workspace(p), check_path_chars(p)]
    checks = [c for c in checks if c]
    return {"checks": checks, "ok": not any(c["blocking"] for c in checks),
            "can_start": not any(c["blocks_start"] for c in checks), "windows": bool(p.windows),
            "engine": engine or p.config("agent.provider", "claude_code")}


_cache = {"at": 0.0, "engine": None, "result": None}


def cached(refresh=False, engine=None, ttl=30):
    """What the server returns: a run is a few seconds (claude --version, auth status, the JLC probe), so keep it 30 s."""
    now = time.time()
    if not refresh and _cache["result"] and _cache["engine"] == engine and now - _cache["at"] < ttl:
        return _cache["result"]
    res = run(engine=engine)
    _cache.update(at=now, engine=engine, result=res)
    return res


def render(res):
    lines = []
    mark = {"ok": "ok  ", "warn": "warn", "fix": "FIX ", "skip": "skip"}
    for c in res["checks"]:
        lines.append(f"{mark[c['status']]}  {c['title']}" + (f": {c['detail']}" if c["detail"] else ""))
        if c["status"] in ("fix", "warn") and c["fix"]:
            what = c["fix"].get("command") or ("in the app: " + c["fix"]["click"])
            lines.append(f"      -> {what}")
    lines.append("")
    if res["ok"]:
        lines.append("Ready." if not any(c["status"] in ("fix", "warn") for c in res["checks"]) else "Ready (see the warnings above).")
    else:
        lines.append("Not ready: fix the FIX lines above, then run `python pcb.py doctor` again.")
    return "\n".join(lines)


def main(args):
    engine = args[args.index("--engine") + 1] if "--engine" in args and args.index("--engine") + 1 < len(args) else None
    res = run(engine=engine)
    if "--json" in args:
        print(json.dumps(res, indent=2))        # ASCII-escaped: safe through any console code page
    else:
        print(render(res))
    if "--exit-start" in args:                  # the installers: only what stops the SERVER starting is an error
        return 0 if res["can_start"] else 1
    return 0 if res["ok"] else 1
