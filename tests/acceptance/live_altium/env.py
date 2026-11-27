"""Harness for the Altium-judged behaviour metrics: a pre-fix server on its own port and home, a scratch copy of the Altium project.

Nothing here imports product code (A2). The product runs as a separate process from a `git worktree` of the pre-fix commit.

Layout (all under SCRATCH, outside the repo; nothing here ever goes to git):
    SCRATCH/pre-2dcd691/        git worktree of the pre-fix commit (the code under test for everything but B1(b))
    SCRATCH/pre-dbf3635p/       git worktree of dbf3635^ (B1(b): the build before the modal-detection fix)
    SCRATCH/home-<tag>/         PCB_ADVISOR_HOME of one server: config.json + projects/<NAME>/
    SCRATCH/altium-<tag>/       the scratch copy of the Altium project the advisor project points at (own project name, so the
                                library names never collide with the owner's installed libraries)
    SCRATCH/server-<port>.json  how the server on that port was started (so a metric can restart it)

The owner's open Altium documents are never touched: every Altium path the server is told about is under SCRATCH.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
SCRATCH = pathlib.Path(os.environ.get("ACC_SCRATCH") or r"C:\Users\Public\Documents\Altium\acc-scratch")
PRE_FIX = "2dcd691"
PRE_B1B = "dbf3635^"
TREES = {"pre": SCRATCH / "pre-2dcd691", "b1b": SCRATCH / "pre-dbf3635p"}
NAME = "Acc-A"                       # advisor project name AND Altium project name in the scratch copy
OLD = "Final-E2E-4L"                 # the name inside the frozen fixture; renamed in the copy (see make_altium_copy)
PORT_DEFAULT = 8941
OWNER_PORT = 8931                    # the owner's live server: never touched


def fixture() -> pathlib.Path:
    p = os.environ.get("ACCEPTANCE_FIXTURE")
    if not p:
        raise RuntimeError("set ACCEPTANCE_FIXTURE to the frozen fixture folder")
    return pathlib.Path(p)


# ----------------------------------------------------------------------------------------------- trees and copies
def ensure_tree(which: str = "pre") -> pathlib.Path:
    """The pre-fix checkout, created once with `git worktree add --detach` (from the main repo that holds the fixture)."""
    tree = TREES[which]
    if (tree / "pcb.py").is_file():
        return tree
    ref = PRE_FIX if which == "pre" else PRE_B1B
    gitdir = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    main = pathlib.Path(gitdir).resolve().parent if pathlib.Path(gitdir).name == ".git" else REPO
    tree.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "--detach", str(tree), ref], check=True, capture_output=True)
    return tree


def _replace_in(path: pathlib.Path, old: str, new: str) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", errors="replace") if not path.suffix.lower() in (".pcbdoc", ".schdoc") else None
    if text is None:
        return
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.replace(old, new).encode("utf-8"))


def make_altium_copy(dst: pathlib.Path, name: str = NAME) -> pathlib.Path:
    """Copy the fixture's Altium folder to dst, renamed to `name` (Prj/Pcb/OutJob/Lib files), without .advisor-backup."""
    src = fixture() / "altium"
    if dst.exists():                 # Altium has the scratch project open: a file it holds (the installed IntLib) cannot be removed, the rest is
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".advisor-backup", "History", "__Previews"), dirs_exist_ok=True)
    for p in sorted(dst.rglob("*"), key=lambda q: -len(q.parts)):
        if OLD in p.name:
            target = p.with_name(p.name.replace(OLD, name))
            if target.is_file():
                target.unlink()
            if target.is_dir():          # the folder is already there (a re-seed): merge into it; a file Altium holds stays as it is
                try:
                    shutil.copytree(p, target, dirs_exist_ok=True)
                except (shutil.Error, OSError):
                    pass
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.rename(target)
    for p in dst.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".prjpcb", ".outjob", ".libpkg"):
            _replace_in(p, OLD, name)
    return dst


_SEP = r"(?P<s>\\{1,4}|/)"
_ROOT = r"C:" + _SEP + r"Users(?P=s)Public(?P=s)Documents(?P=s)Altium(?P=s)"
_OWNER_ALT = re.compile(_ROOT + OLD, re.I)
_OWNER_HOME = re.compile(_ROOT + r"pcb-advisor(?P=s)projects(?P=s)" + OLD, re.I)
_TEXT = (".json", ".jsonl", ".txt", ".md", ".csv", ".log")


def _as_style(path: pathlib.Path, sep: str) -> str:
    return str(path).replace("\\", "/").replace("/", sep)


def rewrite_owner_paths(pdir: pathlib.Path, alt: pathlib.Path) -> int:
    """Every path in the copied project data that names the owner's Altium folder or the owner's project folder is pointed at the
    scratch copies (any slash style or JSON escaping), so no product step can write to the owner's files."""
    n = 0
    for f in pdir.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in _TEXT:
            continue
        try:
            text = f.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = _OWNER_HOME.sub(lambda m: _as_style(pdir, m.group("s")), text)
        new = _OWNER_ALT.sub(lambda m: _as_style(alt, m.group("s")), new)
        if new != text:
            f.write_bytes(new.encode("utf-8"))
            n += 1
    return n


def owner_path_hits(pdir: pathlib.Path) -> list[str]:
    """Files under pdir that still name the owner's folders (must be empty before a server starts)."""
    bad = []
    for f in pdir.rglob("*"):
        if f.is_file() and f.suffix.lower() in _TEXT:
            try:
                t = f.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue
            if _OWNER_ALT.search(t) or _OWNER_HOME.search(t):
                bad.append(str(f))
    return bad


OWNER_PROJECT_DIRS = (pathlib.Path(r"C:\Users\Public\Documents\Altium\Final-E2E-4L"),
                      pathlib.Path(r"C:\Users\Public\Documents\Altium\pcb-advisor\projects\Final-E2E-4L"))


def owner_snapshot() -> dict:
    """(size, mtime) of the owner's own documents. A change during a run is reported (Altium autosave can cause one), never repaired."""
    snap = {}
    for d in OWNER_PROJECT_DIRS:
        for ext in ("*.PcbDoc", "*.SchDoc", "*.PrjPcb"):
            for f in d.glob(ext):
                st = f.stat()
                snap[str(f)] = (st.st_size, int(st.st_mtime))
    return snap


def make_home(tag: str = "a", name: str = NAME, port: int = PORT_DEFAULT, extra_config: dict | None = None) -> dict:
    """A fresh home with the fixture's advisor project, pointing at a fresh scratch Altium copy. Returns the paths."""
    home = SCRATCH / f"home-{tag}"
    alt = SCRATCH / f"altium-{tag}"
    if home.exists():
        shutil.rmtree(home)
    (home / "projects").mkdir(parents=True)
    pdir = home / "projects" / name
    shutil.copytree(fixture() / "project", pdir)
    make_altium_copy(alt, name)
    rewrite_owner_paths(pdir, alt)
    left = owner_path_hits(pdir)
    if left:
        raise RuntimeError(f"owner paths remain in {len(left)} files, e.g. {left[0]}")
    meta = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    meta["name"] = meta["title"] = name
    meta["altium"] = {"project_file": str(alt / f"{name}.PrjPcb"), "pcb_file": str(alt / f"{name}.PcbDoc"),
                      "outputs_dir": str(alt / "Outputs")}
    (pdir / "project.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for f in ("outputs-check.json", "board-facts.json", "library/build/parts.json", "README.md", "notes.md"):
        p = pdir / f
        if p.is_file():
            _replace_in(p, OLD, name)
    cfg = {"server": {"port": port, "open_browser": False, "default_project": name}}
    for k, v in (extra_config or {}).items():
        cfg[k] = v
    (home / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return {"home": home, "altium": alt, "project_dir": pdir, "name": name, "port": port}


# ----------------------------------------------------------------------------------------------- the server process
def _free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def http(url: str, data=None, timeout: float = 30, method: str | None = None):
    """(status, parsed json or text). Never raises on an HTTP error status."""
    req = urllib.request.Request(url, method=method or ("POST" if data is not None else "GET"))
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read().decode("utf-8", "replace"), e.code
    except (urllib.error.URLError, OSError) as e:
        return 0, f"{type(e).__name__}: {e}"
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, raw


class Server:
    """One product server process. `start()` refuses the owner's port. Its stdout goes to SCRATCH/server-<port>.log."""

    def __init__(self, tree: str = "pre", tag: str = "a", port: int = PORT_DEFAULT, env: dict | None = None):
        if port == OWNER_PORT:
            raise RuntimeError("port 8931 is the owner's live server")
        self.tree, self.tag, self.port, self.extra = tree, tag, port, dict(env or {})
        self.proc: subprocess.Popen | None = None
        self.home = SCRATCH / f"home-{tag}"
        self.log = SCRATCH / f"server-{port}.log"

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, wait: float = 60) -> "Server":
        tree = ensure_tree(self.tree)
        if not _free(self.port):
            raise RuntimeError(f"port {self.port} is in use")
        env = dict(os.environ, PCB_ADVISOR_HOME=str(self.home), PYTHONIOENCODING="utf-8", PYTHONUTF8="1", **self.extra)
        env.pop("PCB_ADVISOR_CONFIG", None)
        out = open(self.log, "ab")
        self.proc = subprocess.Popen([sys.executable, "-u", str(tree / "pcb.py"), "serve", "--no-browser", "--port", str(self.port)],
                                     cwd=str(tree), env=env, stdout=out, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        (SCRATCH / f"server-{self.port}.json").write_text(json.dumps(
            {"pid": self.proc.pid, "tree": self.tree, "tag": self.tag, "port": self.port, "env": self.extra}), encoding="utf-8")
        t0 = time.time()
        while time.time() - t0 < wait:
            code, _ = http(self.url + "/api/projects", timeout=3)
            if code == 200:
                return self
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited early (code {self.proc.returncode}); see {self.log}")
            time.sleep(0.5)
        raise RuntimeError(f"server did not answer within {wait}s; see {self.log}")

    def stop(self) -> None:
        pid = self.proc.pid if self.proc else self._pid_from_state()
        if pid:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        self.proc = None
        t0 = time.time()
        while not _free(self.port) and time.time() - t0 < 15:
            time.sleep(0.3)

    def _pid_from_state(self) -> int:
        try:
            return int(json.loads((SCRATCH / f"server-{self.port}.json").read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError):
            return 0

    def restart(self) -> "Server":
        self.stop()
        return self.start()


def attach(live: dict) -> Server:
    """The managed server behind ctx.live['base_url'] (started by live_altium/serve.py); a restart-capable handle."""
    port = int(re.search(r":(\d+)", live["base_url"]).group(1))
    st = SCRATCH / f"server-{port}.json"
    if not st.is_file():
        raise RuntimeError(f"no harness state for port {port}: start the server with live_altium/serve.py")
    d = json.loads(st.read_text(encoding="utf-8"))
    return Server(tree=d["tree"], tag=d["tag"], port=port, env=d.get("env"))


def project_dir(srv: Server, name: str = NAME) -> pathlib.Path:
    return srv.home / "projects" / name


def altium_dir(srv: Server) -> pathlib.Path:
    return SCRATCH / f"altium-{srv.tag}"


def jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out
