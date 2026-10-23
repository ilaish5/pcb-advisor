"""Guard for the tool's own files during an agent turn.

The runtime agent may change projects through actions, never the tool's code. When the last running agent turn ends,
anything under the install that changed during the turns (modified, added, deleted) is put back.

  git clone   judged with `git status`; files are restored from the commit (or the bytes they had before the turn when
              the owner had already edited them).
  ZIP install no git and no manifest: a snapshot of size + mtime for every file, plus the bytes of code files (about
              3 MB), taken when the first turn starts. Code files are restored from those bytes. A file that has no
              copy (large or binary) is only reported, never invented.

Off for developers: PCB_ADVISOR_DEV=1, or `agent.protect_tool_files: false` in config.json. Data folders (the workspace
projects folder, whatever it is called), config.json, caches and logs are not the tool. A guard that cannot look (git
fails) does nothing for that turn: it never restores from a bad snapshot.
"""
import os
import pathlib
import subprocess
import sys
import threading

REPO = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", "projects", "workspace", "local"}
SKIP_PREFIX = ("shared/cache/", "shared/datasheets/")
SKIP_FILES = {"config.json"}
SKIP_SUFFIX = (".pyc", ".log", ".jsonl")
CODE_SUFFIX = (".py", ".pas", ".md", ".js", ".html", ".css", ".json", ".txt", ".bat", ".sh", ".ps1", ".yml", ".yaml", ".toml")
MAX_KEEP = 512_000            # a ZIP-install code file bigger than this is only reported


def enabled():
    if os.environ.get("PCB_ADVISOR_DEV") == "1":
        return False
    try:
        import workspace
        return bool(workspace.get("agent.protect_tool_files", True))
    except Exception:
        return True


def _data_prefixes(root):
    """Folders of the workspace that sit inside the install (the projects folder under its configured name)."""
    out = []
    try:
        import workspace
        for p in (workspace.projects_dir(), workspace.home()):
            try:
                rel = pathlib.Path(p).resolve().relative_to(pathlib.Path(root).resolve()).as_posix()
            except (ValueError, OSError):
                continue
            if rel not in ("", "."):
                out.append(rel.rstrip("/") + "/")
    except Exception:
        pass
    return tuple(out)


def _skip(rel, extra=()):
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    return (any(p in SKIP_DIRS for p in parts[:-1]) or rel.startswith(SKIP_PREFIX + tuple(extra)) or rel in SKIP_FILES
            or rel.endswith(SKIP_SUFFIX))


def _git(root, *args):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
                          timeout=60, env=env)


def _is_git(root):
    if not (pathlib.Path(root) / ".git").exists():
        return False
    try:
        return _git(root, "rev-parse", "--git-dir").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _read(p):
    try:
        return p.read_bytes()
    except OSError:
        return None


def _git_state(root, extra):
    """{rel: (status, bytes|None)} of every watched file that differs from the commit. Raises when git cannot answer."""
    p = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200] or "git status failed")
    out, recs, i = {}, p.stdout.split("\0"), 0
    while i < len(recs):
        rec = recs[i]
        i += 1
        if len(rec) < 4:
            continue
        st, rel = rec[:2], rec[3:]
        if st[0] in "RC" and i < len(recs):
            i += 1                                      # the old name of a rename
        if not _skip(rel, extra):
            out[rel] = (st, _read(root / rel))
    return out


def _zip_state(root, extra):
    """{rel: (size, mtime_ns, bytes|None)}: bytes only for code files up to MAX_KEEP."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            f = pathlib.Path(dirpath) / fn
            rel = f.relative_to(root).as_posix()
            if _skip(rel, extra):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            keep = _read(f) if fn.endswith(CODE_SUFFIX) and st.st_size <= MAX_KEEP else None
            out[rel] = (st.st_size, st.st_mtime_ns, keep)
    return out


def snapshot(root=None):
    """The state to compare with later; state is None (guard off for this turn) when it cannot be taken."""
    root = pathlib.Path(root or REPO)
    snap = {"root": root, "git": False, "state": None, "extra": ()}
    try:
        snap["extra"] = _data_prefixes(root)
        snap["git"] = _is_git(root)
        snap["state"] = _git_state(root, snap["extra"]) if snap["git"] else _zip_state(root, snap["extra"])
    except Exception as exc:
        print(f"[guard] cannot look at the tool's files, guard off for this turn: {exc}", file=sys.stderr, flush=True)
        snap["state"] = None
    return snap


def restore(snap):
    """Put the tool's files back to what they were at snapshot(). Returns (restored, unrestored) lists of relative paths.
    Never raises."""
    try:
        return _restore(snap)
    except Exception as exc:
        print(f"[guard] restore failed: {exc}", file=sys.stderr, flush=True)
        return [], []


def _restore(snap):
    if not snap or snap.get("state") is None:
        return [], []
    root, before = snap["root"], snap["state"]
    restored, unrestored = [], []
    if snap["git"]:
        after = _git_state(root, snap["extra"])
        for rel in sorted(set(before) | set(after)):
            if before.get(rel) == after.get(rel):
                continue
            path, was = root / rel, before.get(rel)
            if was is not None:                 # already edited (or present) before the turn: back to those bytes
                if was[1] is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(was[1])
            else:                               # clean before: back to the commit, or gone when new
                if _git(root, "cat-file", "-e", f"HEAD:{rel}").returncode == 0:
                    _git(root, "reset", "-q", "HEAD", "--", rel)
                    _git(root, "checkout", "--", rel)
                else:
                    _git(root, "rm", "-f", "-q", "--cached", "--", rel)
                    path.unlink(missing_ok=True)
            restored.append(rel)
        return restored, unrestored
    after = _zip_state(root, snap["extra"])
    for rel in sorted(set(before) | set(after)):
        b, a = before.get(rel), after.get(rel)
        if b is not None and a is not None and b[:2] == a[:2]:
            continue
        path = root / rel
        if b is None:                           # new file: remove only code, the tool may write other files by itself
            if rel.endswith(CODE_SUFFIX):
                path.unlink(missing_ok=True)
                restored.append(rel)
            else:
                unrestored.append(rel)
        elif b[2] is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b[2])
            restored.append(rel)
        else:
            unrestored.append(rel)              # no copy and no source of truth in a ZIP install
    return restored, unrestored


# One snapshot for all running turns: the first turn takes it, the last one to end restores.
_lock = threading.Lock()
_active = 0
_snap = None


def begin():
    """Call when an agent turn starts. Returns True when the guard watches this turn."""
    global _active, _snap
    if not enabled():
        return False
    with _lock:
        if _active == 0:
            _snap = snapshot()
        _active += 1
    return True


def end(watched):
    """Call when the turn ended (pass begin()'s result). The last active turn restores; the others get ([], [])."""
    global _active, _snap
    if not watched:
        return [], []
    with _lock:
        _active -= 1
        if _active > 0:
            return [], []
        snap, _snap = _snap, None
        return restore(snap)


def refusal(restored, unrestored=()):
    files = ", ".join((list(restored) + list(unrestored))[:6])
    if unrestored and restored:
        how = "; some were restored, the rest could NOT be"
    elif unrestored:
        how = "; they could NOT be restored (install a fresh copy)"
    else:
        how = "; they were restored"
    return f"the agent edited system files: {files}{how}. System bugs go to the student as a report, not a patch"
