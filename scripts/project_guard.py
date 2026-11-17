"""Guard for a project's server-written data during an agent turn.

The runtime agent changes a project only through actions the server applies. Claude Code is held to that by its tool
allow-list; Antigravity runs with no per-tool limits and could edit bom.json, idea.json, netlist/*.json or the logs
directly. Around the engine run (agent.respond, never apply_actions) this guard keeps the bytes of those files and, at the
end, puts back whatever changed without the server's knowledge.

A change is legitimate when someone who may write it said so: every write helper of the server (store.append,
store._atomic_write_json, the bom.json and netlist writers, project.save_meta) calls note(path, bytes). That works across
processes: a skill script the agent runs writes through the same helpers, and the registry is a small file under the
workspace's local/ folder, one per project, that exists only while a window is open (so outside a window note() costs one
stat). At the end a file is left alone when its bytes equal what it had at the start, or equal any bytes registered for it
during the window; anything else is restored (a new file removed) and reported. A direct edit AFTER a legitimate write has
other bytes than every registered one, so it is caught. The one blind spot: an append registers the hash of the whole file
as it is right after the append, so a direct edit made in the same instant before it is not told apart.

Never raises, never loses work: a file whose bytes match a registered write is never touched; a restore that fails is
reported as not restored. Off with the tool guard (PCB_ADVISOR_DEV=1, agent.protect_tool_files false).
"""
import hashlib
import json
import pathlib
import sys
import threading

import tool_guard
import workspace

GUARDED = ("idea.json", "bom.json", "project.json", "bom-log.jsonl", "library-log.jsonl", "proposals.jsonl",
           "sheet-log.jsonl", "supply-log.jsonl")
NETLIST = "netlist"

_lock = threading.Lock()
_open = {}            # project -> [turns running, snapshot]


def _digest(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


def _read(path):
    """Bytes, None when absent; raises OSError when it cannot be read."""
    try:
        return pathlib.Path(path).read_bytes()
    except FileNotFoundError:
        return None


def _registry(project):
    return workspace.home() / "local" / "project-guard" / (workspace.safe_name(project) + ".jsonl")


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


def note(path, data=Ellipsis):
    """A legitimate write of `path` just happened. data: the bytes written, None for a deletion, omitted to read the file.
    Free when no window is open. Never raises."""
    try:
        hit = _rel_of(path)
        if not hit:
            return
        reg = _registry(hit[0])
        if not reg.exists():
            return
        if data is Ellipsis:
            data = _read(path)
        elif isinstance(data, str):
            data = data.encode("utf-8")
        with open(reg, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"p": hit[1], "h": _digest(data)}) + "\n")
    except Exception as exc:
        print(f"[project-guard] could not register a write: {exc}", file=sys.stderr, flush=True)


def _files(pdir):
    out = {rel: pdir / rel for rel in GUARDED}
    nd = pdir / NETLIST
    if nd.is_dir():
        for f in nd.iterdir():
            if f.is_file():
                out[f"{NETLIST}/{f.name}"] = f
    return out


def _snapshot(project):
    pdir = workspace.project_dir(project)
    snap = {}
    for rel, f in _files(pdir).items():
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
        with _lock:
            slot = _open.get(project)
            if slot is None:
                reg = _registry(project)
                reg.parent.mkdir(parents=True, exist_ok=True)
                reg.write_text("", encoding="utf-8")
                slot = _open[project] = [0, _snapshot(project)]
            slot[0] += 1
        return project
    except Exception as exc:
        print(f"[project-guard] cannot look at the project, guard off for this turn: {exc}", file=sys.stderr, flush=True)
        return None


def end(token):
    """Call when the agent run ended. The last turn of a project restores; returns (restored, unrestored) file names."""
    if not token:
        return [], []
    try:
        with _lock:
            slot = _open.get(token)
            if slot is None:
                return [], []
            slot[0] -= 1
            if slot[0] > 0:
                return [], []
            del _open[token]
            before = slot[1]
            reg = _registry(token)
            allowed = {}
            try:
                for line in reg.read_text(encoding="utf-8").splitlines():
                    try:
                        rec = json.loads(line)
                        allowed.setdefault(rec["p"], set()).add(rec["h"])
                    except (ValueError, KeyError, TypeError):
                        continue
            except OSError:
                pass
            try:
                reg.unlink(missing_ok=True)
            except OSError:
                pass
            return _restore(token, before, allowed)
    except Exception as exc:
        print(f"[project-guard] end failed: {exc}", file=sys.stderr, flush=True)
        return [], []


def _restore(project, before, allowed):
    pdir = workspace.project_dir(project)
    after_files = _files(pdir)
    restored, unrestored = [], []
    for rel in sorted(set(before) | set(after_files)):
        path = pdir / rel
        try:
            cur = _read(path)
        except OSError:
            continue
        was = before.get(rel)
        h = _digest(cur)
        if h == _digest(was) or h in allowed.get(rel, ()):
            continue                  # untouched, or a write the server (or its scripts) made
        try:
            if was is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(was)
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
