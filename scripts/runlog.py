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
SECRET_TEXT = re.compile(
    r"(?i)(sk-ant-[a-z0-9_-]{10,}|sk-[a-z0-9_-]{16,}|AIza[0-9a-z_-]{30,}|gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|xox[bpa]-[a-z0-9-]{10,}|"
    r"bearer\s+[a-z0-9._~+/=-]{12,}|"
    r"[\w$:.-]*(?:token|api[_-]?key|apikey|password|passwd|secret)[\"']?\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,}]+))")
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
    for pattern in ("run-*.jsonl", "server-output-*.log"):
        for f in sorted(d.glob(pattern))[:-KEEP_DAYS]:
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


OUTPUT_CAP = 5 * 1024 * 1024        # one process writes at most this much of its stdout/stderr into logs/server-output-<day>.log


class _Tee:
    """Wraps sys.stdout / sys.stderr: everything still reaches the console, and a capped copy goes to the server output file
    (the [guard] lines, stock-sweep failures and any other print end up in the report). Never raises."""

    def __init__(self, stream, path, tag, budget):
        self._stream, self._path, self._tag, self._budget = stream, path, tag, budget

    def write(self, text):
        n = self._stream.write(text) if self._stream is not None else len(text or "")    # pythonw has no console
        try:
            if text and self._budget[0] > 0:
                self._budget[0] -= len(text)
                with open(self._path, "a", encoding="utf-8", errors="replace", newline="\n") as fh:
                    for line in str(text).splitlines(True):
                        fh.write(f"{dt.datetime.now().isoformat(timespec='milliseconds')} {self._tag} {_clean(line)}" + ("" if line.endswith("\n") else "\n")
                                 if line.strip() else "")
        except Exception:
            pass
        return n

    def __getattr__(self, name):
        return getattr(self._stream, name)


def tee_output():
    """Called once by the server at start. Idempotent."""
    try:
        if isinstance(sys.stderr, _Tee):
            return
        d = log_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"server-output-{dt.date.today().isoformat()}.log"
        budget = [OUTPUT_CAP]
        sys.stderr = _Tee(sys.stderr, path, "err", budget)
        sys.stdout = _Tee(sys.stdout, path, "out", budget)
    except Exception:
        pass


def output_files():
    d = log_dir()
    return sorted(d.glob("server-output-*.log")) if d.is_dir() else []


_cli_cache = {}


def cli_versions():
    """{"claude": "...", "agy": "..."} for the engine CLIs found on PATH (each `--version` with a 5 s limit; kept for the process)."""
    import shutil
    import subprocess
    out = {}
    for name in ("claude", "agy"):
        if name in _cli_cache:
            out[name] = _cli_cache[name]
            continue
        found = shutil.which(name)
        if not found:
            out[name] = "not on PATH"
        else:
            try:
                r = subprocess.run([found, "--version"], capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace")
                out[name] = (r.stdout or r.stderr or "").strip()[:200] or f"exit {r.returncode}"
            except Exception as exc:
                out[name] = f"{type(exc).__name__}: {exc}"[:200]
        _cli_cache[name] = out[name]
    return out


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
def for_project(project):
    """While inside, run-log records written by lower layers (the Altium bridge) can say which project they belong to (ctx.project)."""
    prev = getattr(ctx, "project", "")
    ctx.project = project or ""
    try:
        yield
    finally:
        ctx.project = prev


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


STATE_FILES = ("project.json", "idea.json", "bom.json", "notes.md", "design-model.json")      # the small state snapshot of a project report
PROJECT_REPORT_MAX_FILE = 8 * 1024 * 1024       # a log or state file bigger than this is cut to its last part


def _read_lines(path):
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _jsonl(path):
    out = []
    for raw in _read_lines(path):
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def _tsnorm(ts):
    """Sortable form of a record's time: 'YYYY-MM-DD HH:MM:SS.mmm' (records have T or a space, with or without milliseconds)."""
    t = str(ts or "").replace("T", " ")
    if not t:
        return ""
    return t[:23] if "." in t else t[:19] + ".999"      # a second-precision record (older logs) sorts after the millisecond records of its second


def _shift(ts, seconds):
    """A normalized ts moved by some (fractional) seconds."""
    try:
        return _tsnorm((dt.datetime.fromisoformat(ts) + dt.timedelta(seconds=seconds)).isoformat(timespec="milliseconds"))
    except ValueError:
        return ts


_PROFILE_RE = re.compile(r"(?i)\b[a-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)(?!(?:Public|Default|All Users)(?:\\|/|\b))[^\\/\s\"'<>|:*?]+")


def home_paths(text):
    """C:\\Users\\<name> (a person's profile folder) written as %USERPROFILE%: the tester's name stays out of a report that is sent on."""
    return _PROFILE_RE.sub("%USERPROFILE%", text) if isinstance(text, str) else text


def _short(v, n=300):
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    t = home_paths(t.replace("\n", " ").strip())
    return t if len(t) <= n else t[:n] + "..."


def _partial_text(shown):
    """'PARTIAL ROUTE, left open: +3V3 (why), +1V1 (why)' out of a step's summary ('' when the step was not partial)."""
    shown = str(shown or "")
    i = shown.find("PARTIAL ROUTE")
    if i < 0:
        return ""
    depth, end = 0, len(shown)
    for j in range(i, len(shown)):                 # up to the next "; " outside brackets
        c = shown[j]
        depth += c == "("
        depth -= (c == ")" and depth > 0)
        if depth == 0 and shown[j:j + 2] == "; ":
            end = j
            break
    return shown[i:end].strip()


def _window(rows):
    """(first, last) record time of a project's rows; the end is moved to now (the report time) so late project-less errors are inside."""
    stamps = [t for t, _, _ in rows if t]
    return (min(stamps) if stamps else ""), max([_tsnorm(dt.datetime.now().isoformat(timespec="milliseconds"))] + stamps)


def _project_run_events(project, since, until):
    """Run-log records of this project, plus project-less failures (exceptions, crashes, UI errors, Altium batches) inside the window of its own records."""
    out = []
    for f in run_files():
        for r in _jsonl(f):
            if r.get("project") == project:
                out.append(r)
            elif not r.get("project") and since <= _tsnorm(r.get("ts")) <= until and (
                    r.get("kind") in ("exception", "crash", "ui-error") or (r.get("kind") == "altium" and r.get("ok") is False)
                    or (r.get("kind") == "request" and (r.get("status") or 0) >= 400)):
                out.append({**r, "window": True})
    return out


def _timeline_rows(project):
    """[(sortable ts, text, is_error)] from every record source of a project."""
    import workspace
    base = workspace.projects_dir() / project
    rows = []

    def add(r, text, err=False):
        rows.append((_tsnorm(r.get("ts")), text, bool(err)))

    for name in ("usage-log.1.jsonl", "usage-log.jsonl"):
        for r in _jsonl(base / name):
            k = r.get("kind", "?")
            bad = r.get("ok") is False or k == "ui-error" or bool(r.get("error"))
            if k == "message":
                add(r, f"STUDENT SAYS: {_short(r.get('text'), 2000)}" + ("  [not accepted: " + _short(r.get("shown")) + "]" if r.get("ok") is False else ""),
                    r.get("ok") is False)
            elif k == "answer":
                bits = [f"AGENT ANSWERS ({r.get('engine', '')} {r.get('model', '')} {r.get('seconds', '')}s)"]
                if r.get("text"):
                    bits.append(_short(r["text"], 2000))
                for key in ("applied", "refused", "warned"):
                    if r.get(key):
                        bits.append(f"{key.upper()}: {_short(r[key], 1500)}")
                if r.get("error"):
                    bits.append("ERROR: " + _short(r["error"], 600))
                add(r, " | ".join(bits), bad)
            elif k == "step":
                if str(r.get("op", "")).startswith("chat.") and r.get("ok") is not False:
                    continue                    # the chat turn's own lines already tell it
                if r.get("phase") == "begin":
                    add(r, f"STEP {r.get('op')} begins")
                else:
                    notes = "; ".join(f"{x.get('step')}={x.get('state')}" + (f" ({_short(x.get('note'), 160)})" if x.get("note") else "")
                                      for x in (r.get("steps") or []) if isinstance(x, dict))
                    word = "ok" if r.get("ok") else "STOPPED by the student" if r.get("stopped") else "FAILED"
                    shown = r.get("shown") or ""
                    left = _partial_text(shown)
                    if r.get("ok") and left:
                        word = "PARTIAL"                # the tracks stay, some nets are still open: not "ok"
                        rest = shown.replace(left, "", 1).strip(" ;")
                        shown = left + (" | " + rest if rest else "")
                    add(r, f"STEP {r.get('op')} {word} in {r.get('seconds', '?')}s: {_short(shown, 700)}"
                           + (f" [{notes}]" if notes else "") + (f" warnings: {_short(r['warnings'], 400)}" if r.get("warnings") else ""),
                        (r.get("ok") is False and not r.get("stopped")) or word == "PARTIAL")
            elif k == "ui-error":
                add(r, f"UI ERROR: {_short(r.get('message'), 400)} ({r.get('source', '')}:{r.get('line', '')}) view={r.get('view', '')}", True)
            else:
                bits = [f"{key}={_short(r[key], 200)}" for key in ("view", "name", "act", "id", "text", "shown", "choice", "action")
                        if r.get(key) not in (None, "", [])]
                if "checked" in r:
                    bits.append("now " + ("ticked" if r["checked"] else "unticked"))
                add(r, f"{k.upper()}: " + " | ".join(bits) + ("  FAILED" if r.get("ok") is False else ""), r.get("ok") is False)
    for r in _jsonl(base / "turns-log.1.jsonl") + _jsonl(base / "turns-log.jsonl"):
        started = r.get("started") or r.get("ts")
        head = (f"AGENT TURN ({r.get('kind')}, {r.get('engine')} {r.get('model', '')}, {r.get('seconds')}s, tokens {r.get('tokens_in')}/{r.get('tokens_out')}, "
                f"done {r.get('applied')}, proposed (waiting for approval) {r.get('proposed')}, refused {r.get('refused')}) "
                + ("ok" if r.get("ok") else "FAILED " + _short(r.get("error"), 300)))
        add({"ts": started}, head, not r.get("ok", True))
        base_ts = _tsnorm(started)
        for i, c in enumerate(r.get("calls") or []):
            if isinstance(c, dict):
                cmd = c.get("input") or {}
                cmd = cmd.get("command") or cmd.get("file_path") or cmd.get("pattern") or cmd
                when = c.get("ts") or _shift(base_ts, (i + 1) * 0.001)         # the stream's own time, else turn start + order
                code = re.match(r"\s*Exit code:?\s*(-?\d+)", str(c.get("result") or ""))
                state = "ERROR" if c.get("error") else (f"exit {code.group(1)}" if c.get("failed") else "ok")
                add({"ts": when}, f"    tool {c.get('tool')}: {_short(cmd, 400)}  ->  {state}: {_short(c.get('result'), 400)}", c.get("error"))
        if r.get("calls_dropped"):
            add({"ts": _shift(base_ts, 0.0005)}, f"    ({r['calls_dropped']} more tool calls in this turn were not recorded)")
        for d in r.get("denied") or []:
            if isinstance(d, dict):
                add({"ts": _shift(base_ts, 0.0007)}, f"    DENIED tool {d.get('tool')}: {_short(d.get('input'), 300)} ({_short(d.get('reason'), 200)})", True)
        for ev in r.get("raw_events") or []:
            add({"ts": ev.get("ts") or started}, f"    engine event: {_short(ev.get('event'), 400)}")
    for f in sorted(base.glob("*-log*.jsonl")) + [base / "proposals.jsonl"]:
        if f.name.startswith(("usage-log", "turns-log")):
            continue
        for r in _jsonl(f):
            bits = [f"{k}={_short(v, 160)}" for k, v in r.items() if k not in ("ts", "by") and v not in (None, "", [], {})][:8]
            add(r, f"{f.stem.upper()}: " + " | ".join(bits), r.get("ok") is False or bool(r.get("error")))
    return rows


def project_timeline_text(project, run_events=None, rows=None):
    """The readable story of one project: a summary on top, then every record in time order, errors marked '!!'."""
    import workspace
    rows = list(rows) if rows is not None else _timeline_rows(project)
    runs = run_events if run_events is not None else _project_run_events(project, *_window(rows))
    steps_ok = steps_bad = steps_stopped = 0
    steps_partial = sum(1 for _, text, _ in rows if text.startswith("STEP ") and " PARTIAL in " in text)
    partial_word = f"{steps_partial} partial, " if steps_partial else ""
    for r in runs:
        ts = _tsnorm(r.get("ts"))
        kind = r.get("kind")
        if kind == "op":
            if r.get("phase") == "end":
                stopped = bool(r.get("stopped"))
                bad = r.get("ok") is False and not stopped
                if str(r.get("op", "")).startswith("step."):
                    steps_bad += bad
                    steps_ok += r.get("ok") is not False
                    steps_stopped += stopped
                rows.append((ts, f"RUN {r.get('op')} {'STOPPED' if stopped else 'FAILED' if bad else 'ok'} in {r.get('seconds', '?')}s"
                                 + (f": {_short(r.get('error'), 800)}" if r.get("error") else "")
                                 + (f" summary: {_short(r.get('summary'), 300)}" if r.get("summary") else ""), bad))
        elif kind == "altium":
            rows.append((ts, f"ALTIUM BRIDGE {','.join(map(str, r.get('commands') or []))} {'ok' if r.get('ok') else 'FAILED'} in {r.get('seconds')}s "
                             f"args={_short(r.get('args'), 500)}" + (f" error: {_short(r.get('error'), 800)}" if r.get("error") else "")
                             + (f" log tail: {_short(r.get('result'), 500)}" if r.get("result") else ""), r.get("ok") is False))
        elif kind in ("exception", "crash"):
            rows.append((ts, f"EXCEPTION {r.get('where') or r.get('path') or ''}: {_short(r.get('error'), 500)}\n{r.get('traceback', '')}".rstrip()
                         + ("  (no project on the record; same time window)" if r.get("window") else ""), True))
        elif kind == "chat" and r.get("phase") in ("end", "followup-end"):
            acts = r.get("actions") or []
            rows.append((ts, f"CHAT TURN {r.get('phase')} ok={r.get('ok')} done={r.get('applied')} refused={r.get('refused')} warned={r.get('warned')} "
                             f"proposed(waiting)={r.get('proposed')} actions asked: {_short([a.get('type') if isinstance(a, dict) else a for a in acts], 300)}"
                             + (f" error: {_short(r.get('error'), 600)}" if r.get("error") else "")
                             + (f"\n{r['traceback']}" if r.get("traceback") else ""), r.get("ok") is False))
        elif kind == "request" and (r.get("status") or 0) >= 400:
            rows.append((ts, f"HTTP {r.get('method')} {r.get('path')} -> {r.get('status')}: {_short(r.get('error'), 400)}"
                             + (f"\n{r['traceback']}" if r.get("traceback") else ""), True))
    rows.sort(key=lambda x: x[0])
    turns = (_jsonl(workspace.projects_dir() / project / "turns-log.1.jsonl") + _jsonl(workspace.projects_dir() / project / "turns-log.jsonl"))
    errs = sum(1 for _, _, e in rows if e)
    head = [f"PCB Advisor activity timeline: project {project}",
            f"first record: {rows[0][0] if rows else '-'}   last record: {rows[-1][0] if rows else '-'}",
            f"agent turns: {len(turns)} (failed: {sum(1 for t in turns if not t.get('ok', True))})   "
            f"step buttons: {steps_ok} ok, {partial_word}{steps_bad} failed, {steps_stopped} stopped   records marked as errors (!!): {errs}",
            "Lines starting with '!!' are failures. Times are local to the tester's computer.", "=" * 78]
    return "\n".join(head + [f"{ts[:23]}  {'!! ' if err else '   '}{text}" for ts, text, err in rows]) + "\n"


README_TEXT = """PCB Advisor activity report for one project (made locally, nothing was sent).

timeline.txt            start here: everything in time order, failures marked '!!', summary on top
about.json              version/commit, OS, python
doctor.json             setup checks as the tester's machine saw them
config.json             settings with secrets hidden
logs/run-project.jsonl  server records of this project (steps, Altium batches with commands/results, exceptions with tracebacks,
                        failed requests) plus project-less exceptions from the same time window
logs/install-*.log      installer logs, if any
logs/server-output-*.log what the server printed to the console: this project's time window only, other projects' lines and PDF parser
                        noise left out, errors and tracebacks marked '!!' (last 1MB per day)
project/*-log*.jsonl    per-project logs: usage (clicks, views, messages, answers, steps), turns (agent tool calls and results),
                        altium, bom, library, sheet, supply, lineage; rotated files too
project/proposals.jsonl proposals the agent made and what was decided
project/chats/          full chat transcripts
state/                  project.json, idea.json, bom.json, netlist/*.json, notes.md, design-model.json (no datasheets, PDFs or Altium files)
"""


def _add_capped(z, path, arcname, cap=PROJECT_REPORT_MAX_FILE):
    try:
        size = path.stat().st_size
        if size <= cap:
            z.write(path, arcname)
        else:
            with open(path, "rb") as fh:
                fh.seek(size - cap)
                z.writestr(arcname, b"[cut: only the last part of this file]\n" + fh.read())
    except OSError as exc:
        z.writestr(arcname + ".error.txt", str(exc))


OUTPUT_NOISE = re.compile(r"Ignoring wrong pointing object|Rotated text discovered|Multiple definitions in dictionary|Xref table not zero-indexed|"
                          r"invalid pdf header|EOF marker not found|incorrect startxref|^-{20,}\s*$")
OUTPUT_ERROR = re.compile(r"Traceback \(most recent|ConnectionAbortedError|ConnectionResetError|BrokenPipeError|Exception occurred during|"
                          r"^\w*(?:Error|Exception)\b|\bFAILED\b")


def filter_output(lines, project, since, until):
    """The lines of the server's console copy that belong in a project's report: inside its time window, and either naming the project
    or naming no other one. PDF parser chatter is dropped; errors and tracebacks are marked '!!'."""
    import workspace
    try:
        others = [p.name for p in workspace.projects_dir().iterdir() if p.is_dir() and p.name != project]
    except OSError:
        others = []
    other = re.compile("|".join(r"(?:projects[\\/]+|project=|\[)" + re.escape(o) + r"(?=[\\/\]\s&\"',]|$)" for o in others), re.I) if others else None
    out = []
    for line in lines:
        m = re.match(r"(\d{4}-\d\d-\d\dT[\d:.]+) (out|err) (.*)$", line)
        if not m:
            continue
        ts, body = _tsnorm(m.group(1)), m.group(3)
        if not (since <= ts <= until) or OUTPUT_NOISE.search(body):
            continue
        if project not in body and other is not None and other.search(body):
            continue                                      # another project's line
        out.append(f"{'!! ' if OUTPUT_ERROR.search(body) else '   '}{m.group(1)} {m.group(2)} {home_paths(body)}")
    return "\n".join(out) + ("\n" if out else "")


def _fill_project_report(z, project):
    import workspace
    base = workspace.projects_dir() / project
    z.writestr("README.txt", README_TEXT)
    runs, rows = [], []
    try:
        rows = _timeline_rows(project)
        runs = _project_run_events(project, *_window(rows))
        z.writestr("timeline.txt", project_timeline_text(project, run_events=runs, rows=rows))
    except Exception as exc:         # the raw files below still tell the story
        z.writestr("timeline-error.txt", f"The timeline could not be built ({type(exc).__name__}: {exc}). Read the raw files.\n{tb(exc)}")
    z.writestr("logs/run-project.jsonl", "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in runs))
    for f in install_files():
        z.write(f, f"logs/{f.name}")
    since, until = _window(rows) if rows else ("", "9")
    for f in output_files():         # what the server printed (the [guard] lines and other console output): this project's window, last part only
        text = filter_output(_read_lines(f), project, since, until)
        if text:
            z.writestr(f"logs/{f.name}", text[-1024 * 1024:])
    if not base.is_dir():
        z.writestr("project-error.txt", f"no project folder named {project}")
        return
    for f in sorted([*base.glob("*-log*.jsonl"), base / "proposals.jsonl"]):
        if f.is_file():
            _add_capped(z, f, f"project/{f.name}")
    if (base / "chats").is_dir():
        for f in sorted((base / "chats").rglob("*")):
            if f.is_file():
                _add_capped(z, f, f"project/chats/{f.relative_to(base / 'chats').as_posix()}")
    for name in STATE_FILES:
        if (base / name).is_file():
            _add_capped(z, base / name, f"state/{name}")
    if (base / "netlist").is_dir():
        for f in sorted((base / "netlist").glob("*.json")):
            _add_capped(z, f, f"state/netlist/{f.name}")


_report_lock = threading.Lock()
STAMP_RE = r"\d{8}-\d{6}(?:-\d+)?"


def make_report(doctor=None, project=None):
    """Zip the run logs, install logs, the doctor result, the config without secrets and, per project, its *-log.jsonl files
    (usage-log.jsonl among them) and its chats. Never sources, datasheets or Altium files. Returns the path of the zip.
    With project=<name>: only that project, with timeline.txt, README.txt, its run-log lines and a small JSON/text state snapshot.
    One report is made at a time; the file is created exclusively, so two clicks never share a name."""
    with _report_lock:
        return _make_report(doctor, project)


def _make_report(doctor, project):
    import workspace
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"pcb-advisor-report-{workspace.safe_name(project)}-" if project else "pcb-advisor-report-"
    n, z = 1, None
    while z is None:
        out = d / (f"{prefix}{stamp}.zip" if n == 1 else f"{prefix}{stamp}-{n}.zip")
        try:
            z = zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED)
        except FileExistsError:
            n += 1
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
    with z:
        z.writestr("about.json", json.dumps({**start_info(), "cli_versions": cli_versions()}, indent=2))
        z.writestr("doctor.json", json.dumps(redact(doctor), indent=2, ensure_ascii=False, default=str))
        z.writestr("config.json", json.dumps(cfg, indent=2, ensure_ascii=False, default=str))
        if project:
            _fill_project_report(z, project)
        else:
            for f in run_files() + install_files() + output_files():
                z.write(f, f"logs/{f.name}")
            try:
                pdir = workspace.projects_dir()
                for p in sorted(pdir.iterdir()) if pdir.is_dir() else []:
                    for f in sorted([*p.glob("*-log.jsonl"), *p.glob("*-log.1.jsonl")]):          # includes usage-log and turns-log, rolled too
                        z.write(f, f"projects/{p.name}/{f.name}")
                    for f in sorted((p / "chats").rglob("*")) if (p / "chats").is_dir() else []:     # the conversation: needed to follow the usage log
                        if f.is_file():
                            z.write(f, f"projects/{p.name}/chats/{f.relative_to(p / 'chats').as_posix()}")
            except OSError as exc:
                z.writestr("projects-error.txt", str(exc))
    event("report", path=str(out), project=project or "")
    mine = re.compile(re.escape(prefix) + STAMP_RE + r"\.zip")        # each kind (the full report, each project) keeps its own last few
    for old in sorted((f for f in d.glob(prefix + "*.zip") if mine.fullmatch(f.name)), key=lambda f: f.stat().st_mtime)[:-KEEP_REPORTS]:
        try:
            old.unlink()
        except OSError:
            pass
    return out
