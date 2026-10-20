"""Background checks: work the student must never wait for.

One daemon worker thread per process runs a FIFO queue of small jobs. A job has a key; a key that is already queued
or running is not added again (a stock check for a line that is still running asks for ONE more run afterwards, so
an MPN edited during a check is not lost). A job never raises out of the worker: the traceback is printed and the
worker goes on. Results are written into the project's files atomically (store._atomic_write_json).

Two kinds of job:
- citations: after an agent reply is stored, every `{{src:file|locator}}` in it is checked against the file. The
  result sits beside the chat, in `chats/<session>.cites.json`, keyed by the record's `ts`:
      {"<ts>": {"state": "done", "at": ISO, "items": {"<file>|<locator>": {"status": "ok" | "not_found" |
                                                                        "missing_file", "reason": "..."}}}}
  model.build() attaches it to the chat record as `cites`; while the job is queued or running `cites` is
  {"state": "checking"}. The chat UI redraws its chips from that (a normal state poll carries it).
- stock: a BOM line added, or its MPN/LCSC changed -> check_availability for that line (key stock:<project>:<line>).
  The jobs run one after another and `STOCK_GAP` seconds apart; check_availability and jlc.py keep their own cache.

Windows: only threads and os.replace (retried by store._atomic_write_json); no signals, no subprocess.
"""
import collections
import datetime as dt
import pathlib
import re
import sys
import threading
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "skills"))

CITE = re.compile(r"\{\{src:([^|}]+)(?:\|([^}]*))?\}\}")
QUOTED = re.compile(r'"([^"]{3,})"|“([^”]{3,})”|«([^»]{3,})»')
NOT_A_FILE = re.compile(r"^\s*(jlc|lcsc|check_availability)\b", re.I)   # a script run, cited by its query and time
STOCK_GAP = 1.0                  # seconds between two stock checks: the JLC endpoint is not ours to hammer
RETRY_AFTER = 3600               # a line JLC could not answer for is not asked again for an hour (unless it changed)
STALE_HOURS = 24

_cv = threading.Condition()
_queue = collections.deque()     # (key, fn)
_queued = set()
_dirty = set()                   # keys submitted again while running: run once more after
_state = {"running": None, "thread": None}
_tried = {}                      # (project, line, mpn, lcsc) -> time of the last attempt


# ---------------------------------------------------------------- the queue

def submit(key, fn, rerun=False):
    """Queue fn under key. False when the key is already queued or running (rerun=True: once more after the
    running one finishes). Never blocks."""
    with _cv:
        if key in _queued:
            return False
        if _state["running"] == key:
            if rerun:
                _dirty.add(key)
            return False
        _queued.add(key)
        _queue.append((key, fn))
        if _state["thread"] is None or not _state["thread"].is_alive():
            t = threading.Thread(target=_worker, name="background-checks", daemon=True)
            _state["thread"] = t
            t.start()
        _cv.notify_all()
        return True


def _worker():
    while True:
        with _cv:
            while not _queue:
                _cv.wait()
            key, fn = _queue.popleft()
            _queued.discard(key)
            _state["running"] = key
        try:
            fn()
        except BaseException:                       # a check must never take the worker (or the server) down
            print(f"(background job {key} failed)")
            traceback.print_exc()
        with _cv:
            _state["running"] = None
            if key in _dirty:
                _dirty.discard(key)
                _queued.add(key)
                _queue.append((key, fn))
            _cv.notify_all()


def is_active(key):
    with _cv:
        return key in _queued or _state["running"] == key


def wait_idle(timeout=10.0):
    """Block until nothing is queued or running (tests). True if it got idle in time."""
    end = time.time() + timeout
    with _cv:
        while _queue or _state["running"] is not None:
            left = end - time.time()
            if left <= 0:
                return False
            _cv.wait(left)
    return True


# ---------------------------------------------------------------- citations

def cites_path(project, session):
    import session as session_mod
    return session_mod.chats_dir(project) / f"{session_mod._safe(session)}.cites.json"


def read_cites(project, session):
    import json
    path = cites_path(project, session)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cite_key(project, session, ts):
    return f"cite:{project}:{session}:{ts}"


def citations_in(text):
    """[(file, locator)] in the order written, without duplicates; script runs are not files and are left out."""
    out, seen = [], set()
    for name, loc in CITE.findall(text or ""):
        name, loc = name.strip(), (loc or "").strip()
        if not name or NOT_A_FILE.match(name) or (name, loc) in seen:
            continue
        seen.add((name, loc))
        out.append((name, loc))
    return out


def check_one(project, name, locator):
    """One citation: the file must exist; a quoted sentence in the locator must be in it. A locator without a
    quote ("p. 2, Pin configuration") names a place: the file existing is all that can be checked."""
    import sources
    try:
        sources.text_of(name, folder=sources.folder_of(project))
    except FileNotFoundError:
        return {"status": "missing_file", "reason": f"{name} is not in Sources"}
    except Exception as exc:                        # an unreadable file is not a fabricated quote, but it is not confirmed
        return {"status": "not_found", "reason": f"could not read {name}: {exc}"}
    quotes = [next(g for g in m if g) for m in QUOTED.findall(locator or "")]
    for q in quotes:
        res = sources.verify(name, q, project)
        if not res.get("ok"):
            return {"status": "not_found", "reason": res.get("reason") or "quote not found in file"}
    if not quotes and _reads_as_sentence(locator) and sources.verify(name, locator.strip(), project).get("ok"):
        return {"status": "ok", "reason": "quote found in file"}       # a quote written without quotation marks
    return {"status": "ok", "reason": "quote found in file" if quotes else "file found"}


def _reads_as_sentence(locator):
    """Agents sometimes put the quote itself where the place goes. A miss proves nothing (it may be a long
    heading), so this can only upgrade "file found" to "quote found", never mark a citation wrong."""
    text = (locator or "").strip()
    return len(text.split()) >= 6 and not re.match(r"(p\.|pp\.|page|§|\d)", text, re.I)


def verify_record(project, session, ts):
    """The job: check every citation of the agent record `ts` and store the result beside the chat."""
    import session as session_mod
    import store
    rec = next((m for m in session_mod.load_chat(project, session) if m.get("ts") == ts and m.get("role") == "agent"), None)
    if not rec:
        return None
    items = {}
    for name, loc in citations_in(rec.get("text", "")):
        items[f"{name}|{loc}"] = check_one(project, name, loc)
    if not items:
        return None
    data = read_cites(project, session)
    data[ts] = {"state": "done", "at": dt.datetime.now().isoformat(timespec="seconds"), "items": items}
    store._atomic_write_json(cites_path(project, session), data)
    return data[ts]


def verify_record_async(project, session, ts, text=None):
    """Called after an agent record is stored. Queues one check; returns False when there is nothing to check."""
    if text is not None and not citations_in(text):
        return False
    return submit(cite_key(project, session, ts), lambda: verify_record(project, session, ts))


def cites_for(project, session, record):
    """What model.build() puts on a chat record as `cites`: {"state": "checking"} while the job is queued or
    running, the stored result when done, None when never checked (an older record: its chips stay plain)."""
    if record.get("role") != "agent" or "{{src:" not in (record.get("text") or ""):
        return None
    ts = record.get("ts")
    if is_active(cite_key(project, session, ts)):
        return {"state": "checking"}
    return read_cites(project, session).get(ts)


# ---------------------------------------------------------------- stock

def stock_key(project, line):
    return f"stock:{project}:{line}"


def _check(project, keys):
    import check_availability
    return check_availability.check(project, keys)


def _line_wants_stock(line):
    import store
    mpn = (line.get("mpn") or "").strip()
    declared = (line.get("lcsc") or "").strip()
    return bool(store.qty(line)) and (mpn not in ("", "—", "-") or bool(declared))


def stock_job(project, line, force=False):
    import store
    row = next((l for l in store.bom_lines(project) if l["key"] == line), None)
    if not row or not _line_wants_stock(row):
        return None
    tried = (project, line, (row.get("mpn") or "").strip(), (row.get("lcsc") or "").strip())
    _tried[tried] = time.time()
    out = _check(project, {line})
    if STOCK_GAP:
        time.sleep(STOCK_GAP)
    return out


def stock_line_async(project, line, force=True):
    """A line was added or its MPN/LCSC changed: check it in the background (once; once more if one is running)."""
    return submit(stock_key(project, line), lambda: stock_job(project, line, force), rerun=force)


def lines_missing_stock(project, retry_after=RETRY_AFTER):
    """BOM lines that want a stock check and have none for their current MPN (a changed MPN drops the old answer),
    minus the ones asked for recently with no answer: JLC does not know them, asking again each turn is noise."""
    import store
    have = store.supply_for(project)
    out = []
    for l in store.bom_lines(project):
        if not _line_wants_stock(l) or have.get(l["key"]):
            continue
        t = _tried.get((project, l["key"], (l.get("mpn") or "").strip(), (l.get("lcsc") or "").strip()))
        if t and time.time() - t < retry_after:
            continue
        out.append(l["key"])
    return out


def stock_state(project, line_key, supply, now=None):
    """What the agent is told about one line's stock: `checking` | `missing` | `stale` | `fresh`, and when."""
    if is_active(stock_key(project, line_key)):
        return {"state": "checking"}
    if not supply:
        return {"state": "missing"}
    at = max((v.get("checked_at") or "" for v in supply.values()), default="")
    try:
        age = ((now or dt.datetime.now()) - dt.datetime.fromisoformat(at)).total_seconds() / 3600
    except ValueError:
        return {"state": "missing"}
    return {"state": "stale" if age > STALE_HOURS else "fresh", "checked_at": at}
