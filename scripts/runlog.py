"""
Local diagnostic log: one JSON line per event in <workspace>/logs/run-YYYY-MM-DD.jsonl, and the report zip made from it.

Nothing here is ever sent anywhere. The files stay on this machine; `pcb.py report` (or Settings > Save diagnostic
report) zips them so a person can attach the zip when reporting a problem. Logging must never break the app: every
public function swallows its own failures.

A record is {"ts", "kind", ...fields}. Values of anything named like a token, key, password, secret, cookie or
authorization are never written, and no string is kept past MAX_STR characters. Chat text and answers are never logged.
"""
import contextlib
import datetime as dt
import json
import os
import pathlib
import platform
import re
import sys
import threading
import time
import traceback
import zipfile

KEEP_DAYS = 14                  # run-*.jsonl files kept; older ones go at the first write of a process
MAX_STR = 4000
MAX_BODY = 16000                # the client error endpoint refuses bigger bodies
SECRET_NAME = re.compile(r"token|key|password|passwd|secret|cookie|authorization", re.I)
SECRET_TEXT = re.compile(r"(?i)\b(sk-[a-z0-9_-]{16,}|bearer\s+[a-z0-9._~+/=-]{12,}|"
                         r"(?:token|api[_-]?key|password|passwd|secret)\s*[=:]\s*\S+)")
_lock = threading.Lock()
_state = {"pruned": None}
ctx = threading.local()         # ctx.session: the page-load id of the request being served (the usage log carries it)
USAGE_KINDS = ("view", "click", "shown", "choice", "upload", "submit", "queued", "ui-error")     # what a page may send
USAGE_MAX_EVENTS = 100
USAGE_MAX_BODY = 200000
USAGE_ROLL = 5 * 1024 * 1024    # usage-log.jsonl becomes usage-log.1.jsonl (one kept) past this size
KEEP_REPORTS = 5
NO_PROJECT_FIELDS = ("view", "name", "text", "id", "act", "level", "choice", "ok", "session")      # all a project-less page event may leave in the run log
NO_TEXT_KINDS = ("queued", "message", "answer")      # chat text only ever goes to a project's usage log


def log_dir():
    """<workspace>/logs, beside projects/. PCB_ADVISOR_LOG_DIR moves it (the tests do)."""
    env = os.environ.get("PCB_ADVISOR_LOG_DIR")
    if env:
        return pathlib.Path(env)
    import workspace
    return workspace.home() / "logs"


def _clean(v, depth=0):
    if isinstance(v, str):
        v = SECRET_TEXT.sub("[hidden]", v)
        return v if len(v) <= MAX_STR else v[:MAX_STR] + f"...[+{len(v) - MAX_STR} chars]"
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if depth > 6:
        return str(v)[:200]
    if isinstance(v, dict):
        return {str(k): ("[hidden]" if SECRET_NAME.search(str(k)) else _clean(x, depth + 1)) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x, depth + 1) for x in list(v)[:200]]
    return _clean(str(v), depth + 1)


def redact(obj):
    """A copy of a dict/list with secret-named values hidden and long strings cut (the config in the report)."""
    return _clean(obj)


def _prune(d):
    today = dt.date.today().isoformat()
    if _state["pruned"] == today:
        return
    _state["pruned"] = today
    files = sorted(d.glob("run-*.jsonl"))
    for f in files[:-KEEP_DAYS]:
        try:
            f.unlink()
        except OSError:
            pass


def event(kind, **fields):
    """Append one record. Never raises."""
    try:
        now = dt.datetime.now()
        rec = {"ts": now.isoformat(timespec="milliseconds"), "kind": str(kind), **_clean(fields)}
        rec["kind"] = str(kind)
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with _lock:
            d = log_dir()
            d.mkdir(parents=True, exist_ok=True)
            _prune(d)
            with open(d / f"run-{now.date().isoformat()}.jsonl", "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def project_ok(name):
    """A project name the usage log may write under: a plain folder name that already exists in projects/."""
    import workspace
    try:
        return isinstance(name, str) and workspace.safe_name(name) == name and (workspace.projects_dir() / name).is_dir()
    except Exception:
        return False


def usage(project, kind, **fields):
    """One record in projects/<project>/usage-log.jsonl (what the person saw, did, wrote and was answered), or in the run log when
    no project is open or the name is not a project. Full texts are allowed here, unlike the run log. Never raises."""
    try:
        if not project_ok(project):
            if kind in NO_TEXT_KINDS:
                return event(kind, ok=fields.get("ok"))
            return event(kind, **{k: v for k, v in fields.items() if k in NO_PROJECT_FIELDS})
        if "session" not in fields and getattr(ctx, "session", ""):
            fields["session"] = ctx.session
        now = dt.datetime.now()
        rec = {"ts": now.isoformat(timespec="milliseconds"), "kind": str(kind), **_clean(fields)}
        rec["kind"] = str(kind)
        line = json.dumps(rec, ensure_ascii=False, default=str)
        import workspace
        with _lock:
            target = workspace.projects_dir() / project / "usage-log.jsonl"
            try:
                if target.stat().st_size > USAGE_ROLL:
                    os.replace(target, target.with_name("usage-log.1.jsonl"))
            except OSError:
                pass
            with open(target, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def usage_batch(batch):
    """A page's batch {session, events:[{kind, project, ts, ...}]} -> (status, message). Unknown kinds are dropped; a project name that
    is not a project refuses the whole batch (nothing is written)."""
    if not isinstance(batch, dict) or not isinstance(batch.get("events"), list):
        return 400, "events required"
    session = str(batch.get("session") or "")[:40]
    events = [e for e in batch["events"][:USAGE_MAX_EVENTS] if isinstance(e, dict) and e.get("kind") in USAGE_KINDS]
    for e in events:
        if e.get("project") and not project_ok(e["project"]):
            return 400, "unknown project"
    for e in events:
        f = {k: v for k, v in e.items() if k not in ("kind", "project", "session") and isinstance(k, str)}
        usage(e.get("project") or "", e["kind"], session=session, **f)
    return 200, ""


def tb(exc=None):
    """The traceback text of exc (or of the exception being handled)."""
    try:
        if exc is None:
            return traceback.format_exc()
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        return repr(exc)


def exception(kind, exc=None, **fields):
    event(kind, error=f"{type(exc).__name__}: {exc}" if exc is not None else "", traceback=tb(exc), **fields)


@contextlib.contextmanager
def span(op, **fields):
    """Begin and end records for one operation: the end has seconds, ok and the full error text. Re-raises."""
    t0 = time.time()
    event("op", op=op, phase="begin", **fields)
    if fields.get("project"):
        usage(fields["project"], "step", op=op, phase="begin", ok=True)
    try:
        yield
    except BaseException as exc:
        event("op", op=op, phase="end", ok=False, seconds=round(time.time() - t0, 1),
              error=f"{type(exc).__name__}: {exc}", **fields)
        if fields.get("project"):
            usage(fields["project"], "step", op=op, phase="end", ok=False, seconds=round(time.time() - t0, 1), shown=f"{exc}")
        raise
    event("op", op=op, phase="end", ok=True, seconds=round(time.time() - t0, 1), **fields)
    if fields.get("project"):
        usage(fields["project"], "step", op=op, phase="end", ok=True, seconds=round(time.time() - t0, 1))


# ---------------------------------------------------------------- reading the usage log

def timeline(project, full=False, cut=200):
    """The usage log of a project as readable lines: time, kind, one line each (long texts cut unless full)."""
    import workspace
    base = workspace.projects_dir() / project
    out, last_session = [], None
    rows = []
    for name in ("usage-log.1.jsonl", "usage-log.jsonl"):
        if (base / name).is_file():
            rows += (base / name).read_text(encoding="utf-8", errors="replace").splitlines()
    for raw in rows:
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        if r.get("session") and r.get("session") != last_session:
            last_session = r["session"]
            out.append(f"--- page session {last_session} ---")
        kind = r.get("kind", "?")
        bits = []
        for k in ("op", "phase", "name", "view", "text", "shown", "choice", "error", "answer"):
            v = r.get(k)
            if v not in (None, "", []):
                bits.append(str(v) if k in ("text", "shown", "error", "answer") else f"{k}={v}")
        if "ok" in r:
            bits.append("ok" if r["ok"] else "FAILED")
        for k in ("seconds", "applied", "refused", "warned", "steps"):
            if r.get(k) not in (None, "", [], {}):
                bits.append(f"{k}={json.dumps(r[k], ensure_ascii=False)}")
        line = " | ".join(bits).replace("\n", " ")
        if not full and len(line) > cut:
            line = line[:cut] + "..."
        out.append(f"{str(r.get('ts', ''))[11:19]}  {kind:<9} {line}")
    return out


# ---------------------------------------------------------------- the report

def run_files():
    d = log_dir()
    return sorted(d.glob("run-*.jsonl")) if d.is_dir() else []


def install_files():
    import workspace
    out = {}
    for d in {log_dir(), workspace.REPO / "logs"}:
        if d.is_dir():
            for f in d.glob("install-*.log"):
                out[f.name] = f
    return [out[k] for k in sorted(out)]


def start_info():
    """What a start record and the report both say about this install."""
    info = {"python": sys.version.split()[0], "os": platform.platform(), "launcher": os.environ.get("PCB_ADVISOR_LAUNCHER", "")}
    try:
        import update
        v = update.version()
        info["commit"], info["branch"], info["date"] = v.get("commit", ""), v.get("branch", ""), v.get("date", "")
    except Exception as exc:
        info["commit_error"] = str(exc)
    return info


def make_report(doctor=None):
    """Zip the run logs, install logs, the doctor result, the config without secrets and, per project, its *-log.jsonl files
    (usage-log.jsonl among them) and its chats. Never sources, datasheets or Altium files. Returns the path of the zip."""
    import workspace
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = d / f"pcb-advisor-report-{stamp}.zip"
    n = 1
    while out.exists():
        n += 1
        out = d / f"pcb-advisor-report-{stamp}-{n}.zip"
    if doctor is None:
        try:
            import doctor as doctor_mod
            doctor = doctor_mod.run()
        except Exception as exc:
            doctor = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        cfg = redact(workspace.load())
    except BaseException as exc:         # load() exits on a broken config; the report still gets made
        cfg = {"error": f"{type(exc).__name__}: {exc}"}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.json", json.dumps(start_info(), indent=2))
        z.writestr("doctor.json", json.dumps(redact(doctor), indent=2, ensure_ascii=False, default=str))
        z.writestr("config.json", json.dumps(cfg, indent=2, ensure_ascii=False, default=str))
        for f in run_files() + install_files():
            z.write(f, f"logs/{f.name}")
        try:
            pdir = workspace.projects_dir()
            for p in sorted(pdir.iterdir()) if pdir.is_dir() else []:
                for f in sorted([*p.glob("*-log.jsonl"), *p.glob("usage-log.1.jsonl")]):          # includes usage-log.jsonl
                    z.write(f, f"projects/{p.name}/{f.name}")
                for f in sorted((p / "chats").rglob("*")) if (p / "chats").is_dir() else []:     # the conversation: needed to follow the usage log
                    if f.is_file():
                        z.write(f, f"projects/{p.name}/chats/{f.relative_to(p / 'chats').as_posix()}")
        except OSError as exc:
            z.writestr("projects-error.txt", str(exc))
    event("report", path=str(out))
    for old in sorted(d.glob("pcb-advisor-report-*.zip"), key=lambda f: f.stat().st_mtime)[:-KEEP_REPORTS]:      # only the last few are kept
        try:
            old.unlink()
        except OSError:
            pass
    return out
