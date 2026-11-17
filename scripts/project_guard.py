"""Guard for a project's server-written data during an agent turn.

The runtime agent changes a project only through actions the server applies. Claude Code is held to that by its tool
allow-list; Antigravity runs with no per-tool limits and could edit bom.json, idea.json, netlist/*.json or the logs
directly. Around the engine run (agent.respond, never apply_actions) this guard keeps the bytes of those files and, at the
end, puts back whatever changed without the server's knowledge.

A change is legitimate when someone who may write it said so: every write helper of the server (store.append,
store._atomic_write_json, the bom.json and netlist writers, project.save_meta, reset) runs inside `with writing(path):`.
That holds a per-project lock for the write and then registers the file's bytes (sequence number, sha256, and a copy of
the bytes). It works across processes: a skill script the agent runs writes through the same helpers and keeps its own
registry file (<pid>.jsonl) in the project's registry folder under the workspace's local/ folder, which exists only while
a window is open (outside one, writing() costs a stat).

At the end a file is put back to the last LEGITIMATE state, never to the start of the turn when the server wrote since:
  - a log (*.jsonl): untouched when it is the last registered version; when it only grew beyond it, the agent's extra
    lines are cut (the longest legitimate version that is a byte prefix of it stays, so every legitimate append stays);
    when it shrank or was rewritten, the last registered version comes back;
  - any other file: the last registered version (a registered deletion = absent), else the start-of-turn bytes;
  - a new file nobody registered is removed.
The restore is a temp file + os.replace. end() holds the project lock for its whole read-compare-restore, so an in-process
server write cannot land between the check and the restore (subprocess writes finish before the agent run returns).

Never raises, never loses work: a project that is gone (deleted, reset) is left alone and never recreated; a restore that
fails is reported as not restored. Blind spot: an append registers the file as it is right after the append, so a direct
edit made in that same instant before it is not told apart. Off with the tool guard (PCB_ADVISOR_DEV=1,
agent.protect_tool_files false).
"""
import contextlib
import hashlib
import json
import os
import pathlib
import shutil
import sys
import threading
import time

import tool_guard
import workspace

GUARDED = ("idea.json", "bom.json", "project.json", "bom-log.jsonl", "library-log.jsonl", "proposals.jsonl",
           "sheet-log.jsonl", "supply-log.jsonl")
NETLIST = "netlist"

_lock = threading.Lock()
_locks = {}           # project -> RLock: held by writers around write+note and by end() around its whole check
_open = {}            # project -> [turns running, snapshot]


def _plock(project):
    with _lock:
        return _locks.setdefault(project, threading.RLock())


def _digest(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


def _read(path):
    """Bytes, None when absent; raises OSError when it cannot be read."""
    try:
        return pathlib.Path(path).read_bytes()
    except FileNotFoundError:
        return None


def _regdir(project):
    return workspace.home() / "local" / "project-guard" / workspace.safe_name(project)


def _rel_of(path):
    """(project, 'idea.json' | 'netlist/x.json') when path is a guarded file of a project, else None."""
    try:
        rel = pathlib.Path(path).resolve().relative_to(workspace.projects_dir().resolve())
    except (ValueError, OSError):
        return None
    parts = rel.parts
    if len(parts) == 2 and parts[1] in GUARDED:
        return parts[0], parts[1]
    if len(parts) == 3 and parts[1] == NETLIST:
        return parts[0], f"{NETLIST}/{parts[2]}"
    return None


def note(path):
    """Register the file as it is now (absent = a deletion). Call it under writing(). Never raises."""
    try:
        hit = _rel_of(path)
        if not hit:
            return
        reg = _regdir(hit[0])
        if not reg.is_dir():
            return
        data = _read(path)
        h = _digest(data)
        if data is not None and not (reg / f"{h}.bin").exists():
            (reg / f"{h}.bin").write_bytes(data)
        with open(reg / f"{os.getpid()}.jsonl", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"seq": time.time_ns(), "p": hit[1], "h": h}) + "\n")
    except Exception as exc:
        print(f"[project-guard] could not register a write: {exc}", file=sys.stderr, flush=True)


@contextlib.contextmanager
def writing(path):
    """Around a server write of `path`: the project lock is held until the write is registered."""
    try:
        hit = _rel_of(path)
    except Exception:
        hit = None
    if not hit:
        yield
        return
    with _plock(hit[0]):
        try:
            yield
        finally:
            note(path)


def _files(pdir):
    out = {rel: pdir / rel for rel in GUARDED}
    nd = pdir / NETLIST
    if nd.is_dir():
        for f in nd.iterdir():
            if f.is_file():
                out[f"{NETLIST}/{f.name}"] = f
    return out


def _snapshot(project):
    snap = {}
    for rel, f in _files(workspace.project_dir(project)).items():
        try:
            snap[rel] = _read(f)
        except OSError:
            continue                  # cannot look at it: not guarded
    return snap


def begin(project):
    """Call before the agent runs. Returns a token for end(), or None when the guard is off or cannot start."""
    try:
        if not tool_guard.enabled():
            return None
        project = workspace.safe_name(project)
        with _plock(project):
            slot = _open.get(project)
            if slot is None:
                reg = _regdir(project)
                shutil.rmtree(reg, ignore_errors=True)
                reg.mkdir(parents=True, exist_ok=True)
                slot = _open[project] = [0, _snapshot(project)]
            slot[0] += 1
        return project
    except Exception as exc:
        print(f"[project-guard] cannot look at the project, guard off for this turn: {exc}", file=sys.stderr, flush=True)
        return None


def _registered(reg):
    """{rel: [(seq, hash|None), ...] by seq} from the registry file of every process."""
    out = {}
    for f in reg.glob("*.jsonl"):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
                out.setdefault(rec["p"], []).append((int(rec["seq"]), rec["h"]))
            except (ValueError, KeyError, TypeError):
                continue
    for v in out.values():
        v.sort(key=lambda e: e[0])
    return out


def end(token):
    """Call when the agent run ended. The last turn of a project restores; returns (restored, unrestored) file names."""
    if not token:
        return [], []
    try:
        with _plock(token):
            slot = _open.get(token)
            if slot is None:
                return [], []
            slot[0] -= 1
            if slot[0] > 0:
                return [], []
            del _open[token]
            reg = _regdir(token)
            try:
                return _restore(token, slot[1], reg)
            finally:
                shutil.rmtree(reg, ignore_errors=True)
    except Exception as exc:
        print(f"[project-guard] end failed: {exc}", file=sys.stderr, flush=True)
        return [], []


def _versions(rel, before, entries, reg):
    """The legitimate states of a file, oldest first: the start of the turn, then every registered write (bytes|None)."""
    out = [before.get(rel)]
    for _seq, h in entries:
        if h is None:
            out.append(None)
        else:
            try:
                out.append((reg / f"{h}.bin").read_bytes())
            except OSError:
                continue              # no copy of it: it cannot be a target
    return out


def _decide(rel, before, cur, entries, reg):
    """None when the file is fine, else (bytes|None,): what it should hold (None = absent)."""
    vers = _versions(rel, before, entries, reg)
    last = vers[-1]
    if cur == last:
        return None
    if rel.endswith(".jsonl") and last is not None:
        if cur is not None:
            if cur.startswith(last) and cur in vers:
                return None           # appends from two processes that registered out of order: cur is a legit version
            if last.startswith(cur):
                return (last,)        # truncated: every legitimate append comes back
            pre = [v for v in vers if v is not None and cur.startswith(v)]
            if pre:
                return (max(pre, key=len),)      # grown by the agent: its extra lines are cut
        return (last,)
    return (last,)


def _restore(project, before, reg):
    pdir = workspace.project_dir(project)
    if not pdir.is_dir() or (before.get("project.json") is not None and not (pdir / "project.json").exists()
                             and not any(h is None for _s, h in _registered(reg).get("project.json", []))):
        return [], []                 # the project was deleted: nothing to put back, never recreate it
    registered = _registered(reg)
    restored, unrestored = [], []
    for rel in sorted(set(before) | set(_files(pdir)) | set(registered)):
        path = pdir / rel
        try:
            cur = _read(path)
            fix = _decide(rel, before, cur, registered.get(rel, []), reg)
            if fix is None:
                continue
            if fix[0] is None:
                path.unlink(missing_ok=True)
            else:
                tmp = path.with_name(f"{path.name}.guard.{os.getpid()}.tmp")
                try:
                    tmp.write_bytes(fix[0])
                    os.replace(tmp, path)
                finally:
                    tmp.unlink(missing_ok=True)
            restored.append(rel)
        except OSError:
            unrestored.append(rel)
    return restored, unrestored


def refusal(restored, unrestored=()):
    files = ", ".join((list(restored) + list(unrestored))[:6])
    if unrestored and restored:
        how = "; some were restored, the rest could NOT be"
    elif unrestored:
        how = "; they could NOT be restored"
    else:
        how = "; they were restored"
    return f"the agent edited project files directly: {files}{how}. Project changes go through actions"
