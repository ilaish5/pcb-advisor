"""Start the product server from a git worktree of a given commit, on a free port, with its own PCB_ADVISOR_HOME.

    python -I tests/acceptance/live/server.py up [--commit 2dcd691] [--project fixture]   # prints URL and project, stays up
    python -I tests/acceptance/live/server.py check --url URL                            # what runs here (CAPABILITIES.md)

A2: the product is a child process; nothing here imports it. The engine the server uses is the oracle's fake engine
(live/fake_engine.py) unless engine="real" is asked for: agent behaviour is then scripted, free and repeatable.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ACC = HERE.parent
REPO = ACC.parent.parent
PRE_FIX = "2dcd691"
WORKTREES = REPO / "local" / "acceptance-worktrees"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def resolve_commit(commit: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", commit + "^{commit}"],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def worktree(commit: str) -> pathlib.Path:
    """A detached worktree of `commit` (reused when it already exists at that commit)."""
    sha = resolve_commit(commit)
    wt = WORKTREES / sha[:12]
    if (wt / "pcb.py").is_file():
        head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head == sha:
            return wt
        subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)], capture_output=True)
    WORKTREES.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), sha], check=True, capture_output=True)
    return wt


def http_json(url: str, body=None, timeout: float = 30.0):
    """GET (body None) or POST JSON. Returns (status, parsed-or-text)."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return status, raw.decode("utf-8", "replace")


class LiveServer:
    """One product server. `home` is its PCB_ADVISOR_HOME; projects are seeded into home/projects before start (or after,
    through the page's own project list)."""

    def __init__(self, commit: str = PRE_FIX, home: pathlib.Path | None = None, port: int | None = None,
                 engine: str = "fake", env: dict | None = None, project: str = "demo") -> None:
        self.commit = commit
        self.sha = resolve_commit(commit)
        self.wt = worktree(commit)
        self.home = pathlib.Path(home or tempfile.mkdtemp(prefix="acc-home-"))
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "projects").mkdir(exist_ok=True)
        self.port = port or free_port()
        self.engine = engine
        self.extra_env = dict(env or {})
        self.project = project
        self.proc: subprocess.Popen | None = None
        self.log = self.home / "server-output.log"
        self.started_at = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def projects(self) -> pathlib.Path:
        return self.home / "projects"

    # -- the engine: the fake one is a two-line wrapper the product finds as its `command`
    def _config(self) -> pathlib.Path:
        cfg = {"server": {"open_browser": False}}
        if self.engine == "fake":
            bindir = self.home / "bin"
            bindir.mkdir(exist_ok=True)
            wrapper = bindir / "fake-claude"
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{HERE / "fake_engine.py"}" "$@"\n', encoding="utf-8")
            wrapper.chmod(0o755)
            cfg["agent"] = {"providers": {"claude_code": {"command": str(wrapper)}}}
            (self.home / "fake-engine").mkdir(exist_ok=True)
        path = self.home / "config.json"
        path.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
        return path

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ACCEPTANCE_")}
        env.update({"PCB_ADVISOR_HOME": str(self.home), "PCB_ADVISOR_CONFIG": str(self._config()),
                    "ACC_FAKE_ENGINE_DIR": str(self.home / "fake-engine"), "PYTHONUTF8": "1"})
        env.update(self.extra_env)
        return env

    def start(self, timeout: float = 60.0) -> "LiveServer":
        py = self.wt / ".venv" / "bin" / "python"
        py = str(py) if py.is_file() else sys.executable
        logf = open(self.log, "a", encoding="utf-8")
        logf.write(f"\n=== start {time.strftime('%H:%M:%S')} commit={self.sha[:12]} port={self.port}\n")
        logf.flush()
        self.proc = subprocess.Popen([py, "pcb.py", "serve", "--port", str(self.port), "--no-browser",
                                      "--project", self.project],
                                     cwd=self.wt, env=self.env(), stdout=logf, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        self.started_at = time.time()
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited {self.proc.returncode}; see {self.log}")
            try:
                st, _ = http_json(self.url + "/api/projects", timeout=2)
                if st == 200:
                    return self
            except OSError:
                pass
            time.sleep(0.3)
        raise TimeoutError(f"server did not answer within {timeout}s; see {self.log}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(5)
        self.proc = None

    def restart(self) -> "LiveServer":
        self.stop()
        return self.start()

    def get(self, path: str, **q):
        from urllib.parse import urlencode
        q.setdefault("project", self.project)
        return http_json(f"{self.url}{path}?{urlencode(q)}")

    def post(self, path: str, body: dict, **q):
        from urllib.parse import urlencode
        q.setdefault("project", self.project)
        return http_json(f"{self.url}{path}?{urlencode(q)}", body, timeout=120)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def commit_of(live: dict | None) -> str:
    """The commit a metric's private server runs: --live-commit, else the pre-fix commit (the red proof)."""
    return (live or {}).get("commit") or os.environ.get("ACCEPTANCE_LIVE_COMMIT") or PRE_FIX


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["up"])
    ap.add_argument("--commit", default=PRE_FIX)
    ap.add_argument("--project", default="fixture", help="'fixture' seeds the frozen 27/11 project")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--engine", default="fake", choices=["fake", "real"])
    a = ap.parse_args(argv)
    sys.path.insert(0, str(ACC))
    from live import seed
    srv = LiveServer(a.commit, port=a.port, engine=a.engine)
    name = seed.seed_fixture(srv.projects) if a.project == "fixture" else a.project
    srv.project = name
    srv.start()
    info = {"url": srv.url, "project": name, "home": str(srv.home), "commit": srv.sha, "pid": srv.proc.pid}
    reg = REPO / "local" / "acceptance-live"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{srv.port}.json").write_text(json.dumps(info), encoding="utf-8")      # metrics find the server's home by port
    print(json.dumps(info), flush=True)
    try:
        while srv.proc and srv.proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
        (reg / f"{srv.port}.json").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
