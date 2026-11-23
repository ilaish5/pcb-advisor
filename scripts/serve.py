"""
Renderer + the single writer.

State is derived in model.py/store.py from append-only logs; knowledge lives in
sources/. This file reads state, appends to it, and applies agent actions.
Keeping one writer is what stops the two-sources-of-truth failure.

Nothing here is hardcoded: ports, paths, the default project and which LLM
engine to route to all come from config.json (see scripts/workspace.py).

    python3 pcb.py serve [--project NAME] [--port N] [--engine ID]
"""
import argparse
import base64
import datetime as dt
import itertools
import json
import mimetypes
import os
import pathlib
import re
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "skills"))
import agent             # noqa: E402
import ext               # noqa: E402
import gateway           # noqa: E402
import model             # noqa: E402
import project as project_mod  # noqa: E402
import runlog            # noqa: E402
import session as session_mod  # noqa: E402
import sources           # noqa: E402
import tool_guard        # noqa: E402
import project_guard     # noqa: E402
import store             # noqa: E402
import workspace         # noqa: E402

ext.load()               # the extension modules register their routes, actions and model keys (import errors surface here)

BACKEND = None            # set at startup; None means "whatever config says"
DEFAULT_PROJECT = None


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def say(project, sess, record):
    """One conversation's log."""
    session_mod.append(project, sess, record)
    project_mod.touch(project)


def compact_if_due(project, sess):
    """Rewrite this session's memory when enough has happened. A separate call,
    so it never competes with answering the student."""
    due, _ = session_mod.due_for_compaction(project, sess)
    if not due:
        return None
    res = agent.compact(model.build(project=project, session=sess), project, sess,
                        backend=BACKEND)
    if not res.get("ok"):
        print(f"(memory not rewritten: {res.get('reason')})")
    return res


# One entry per chat turn in flight, keyed (project, session). The HTTP server is threaded: every access holds
# TURNS_LOCK. "cancel" is the Event the engine watches; the entry exists only while agent.respond runs.
TURNS = {}
TURNS_LOCK = threading.Lock()
COMPACTING = {}                       # (project, session) -> Lock; one memory rewrite at a time per conversation
COMPACTING_LOCK = threading.Lock()
ALLOW_LOCK = threading.Lock()


def _new_turn():
    t = time.time()
    return {"started": t, "last": t, "steps": [], "current": None, "cancel": threading.Event()}


def _turn_start(key):
    turn = _new_turn()
    with TURNS_LOCK:
        TURNS[key] = turn
    return turn


def _turn_event(key, ev):
    """The engine's on_event, called from its reader thread."""
    if not isinstance(ev, dict):
        return
    now_t = time.time()
    with TURNS_LOCK:
        turn = TURNS.get(key)
        if not turn:
            return
        turn["last"] = now_t
        label = str(ev.get("label") or ev.get("tool") or ev.get("kind") or "")
        turn["current"] = label or turn["current"]
        if ev.get("kind") != "text" and label:
            turn["steps"].append({"label": label, "ts": ev.get("ts") or now_t})
            del turn["steps"][:-50]


def _turn_end(key, turn=None):
    """Drop the turn of this conversation. With `turn`, only that very turn: a follow-up that ends late never removes the entry of the
    student's next turn."""
    with TURNS_LOCK:
        if turn is None or TURNS.get(key) is turn:
            TURNS.pop(key, None)


def cancel_followups(match, wait=3.0):
    """Stop every follow-up turn whose key `match`es and wait (bounded) until its entry is gone: a student message or a step button
    comes before a correction of an earlier reply. The engine dies within some 50 ms of the cancel. True when none is left."""
    with TURNS_LOCK:
        mine = [(k, t) for k, t in TURNS.items() if t.get("followup") and match(k)]
        for _, t in mine:
            t["cancel"].set()
    end = time.time() + wait
    while time.time() < end:
        with TURNS_LOCK:
            if not any(TURNS.get(k) is t for k, t in mine):
                return True
        time.sleep(0.02)
    return False


def followup_running(project, sess):
    with TURNS_LOCK:
        t = TURNS.get((project, sess))
        return bool(t and t.get("followup") and not t["cancel"].is_set())


def turn_progress(key):
    with TURNS_LOCK:
        turn = TURNS.get(key)
        if not turn:
            return {"running": False, "seconds": 0, "idle_seconds": 0, "steps": [], "current": None}
        t = time.time()
        return {"running": True, "seconds": round(t - turn["started"]), "idle_seconds": round(t - turn["last"]),
                "steps": [dict(x) for x in turn["steps"][-12:]], "current": turn["current"]}


def compact_async(project, sess):
    """compact_if_due after the reply, off the request thread. Never raises, never runs twice at once."""
    with COMPACTING_LOCK:
        lock = COMPACTING.setdefault((project, sess), threading.Lock())

    def work():
        if not lock.acquire(blocking=False):
            return                       # a rewrite is already running for this conversation
        try:
            compact_if_due(project, sess)
        except BaseException as exc:    # a background rewrite must not take the server down
            print(f"(memory rewrite failed: {exc})")
        finally:
            lock.release()

    t = threading.Thread(target=work, name="memory-rewrite", daemon=True)
    t.start()
    return t


PROTECTED_RE = re.compile(r"(\.jsonl|(^|[/\\])(idea|bom)\.json|(^|[/\\])netlist[/\\][^/\\]*\.json"
                          r"|(^|[/\\])(library|lib)[^/\\]*(manifest|index)[^/\\]*\.json"
                          r"|manifest[^/\\]*\.json)", re.I)
SHELL_OPS = ("&&", "||", ";", "|", "`", "$(", "\n", ">", "<", "&")


def unique_denials(denied):
    """One card per command: an engine that retries a refused command reports it twice. The ids are the
    positions in the stored list, which is what /api/chat/allow indexes."""
    out, seen = [], set()
    for d in denied:
        if not isinstance(d, dict):
            continue
        inp = {k: v for k, v in (d.get("input") or {}).items() if k != "description"}
        key = (d.get("tool"), json.dumps(inp, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        out.append({**d, "id": len(out)})
    return out


def allow_rule(denial):
    """The permission rule for one RECORDED denial, or raise ValueError saying why not."""
    tool = str((denial or {}).get("tool") or "")
    inp = (denial or {}).get("input") or {}
    if not tool:
        raise ValueError("this denial has no tool")
    if denial.get("compound"):
        raise ValueError("a combined command cannot be allowed; retry asks it to run them one by one")
    if tool == "Bash":
        cmd = str(inp.get("command") or "").strip()
        if not cmd:
            raise ValueError("this denial has no command")
        if any(op in cmd for op in SHELL_OPS):
            raise ValueError("a combined command cannot be allowed; retry asks it to run them one by one")
        if PROTECTED_RE.search(cmd):
            raise ValueError("a command touching a protected file cannot be allowed")
        return f"Bash({cmd})"
    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or "").strip()
        if not path:
            raise ValueError("this denial has no path")
        if tool != "Read" and PROTECTED_RE.search(path):
            raise ValueError("this file is written by the server only")
        return f"{tool}({path})"
    if tool == "WebFetch":
        host = urlparse(str(inp.get("url") or "")).hostname
        if not host:
            raise ValueError("this denial has no web address")
        return f"WebFetch(domain:{host})"
    return tool


def allow_denial(project, sess, turn_ts, index):
    """Persist the rule for the denial at `index` of the agent record stamped `turn_ts`. Returns the rule."""
    rec = next((r for r in session_mod.load_chat(project, sess)
                if r.get("role") == "agent" and r.get("ts") == turn_ts), None)
    if rec is None:
        raise KeyError("no such turn in this conversation")
    denied = rec.get("denied") or []
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(denied):
        raise KeyError("no such denial")
    rule = allow_rule(denied[index])
    key = "agent.providers.claude_code.tools.allowed_extra"
    with ALLOW_LOCK:
        cur = workspace.load(reload=True)
        extra = list((((cur.get("agent") or {}).get("providers") or {}).get("claude_code") or {})
                     .get("tools", {}).get("allowed_extra") or [])
        if rule not in extra:
            workspace.set_value(key, extra + [rule])    # save() reloads the cache: the next turn sees it
    return rule


# What the browser may see and set. The rest of the config belongs to whoever
# runs the tool, not to the student sitting in front of it.
SETTABLE = (
    "user.language", "user.units", "user.name",
    "user.theme", "agent.provider", "agent.model", "agent.memory_every",
    "agent.memory_max_chars", "agent.history_messages", "agent.autonomy",
    "server.default_project", "altium.install_path", "altium.projects_dir",
)


def _public_config():
    cfg = workspace.load(reload=True)
    agent_cfg = cfg.get("agent", {})
    return {
        "user": cfg.get("user", {}),
        "engineering_defaults": cfg.get("engineering_defaults", {}),
        "altium": cfg.get("altium", {"install_path": "", "projects_dir": ""}),
        "agent": {**{k: v for k, v in agent_cfg.items() if k != "providers"},
                  "model": (agent_cfg.get("providers", {})
                            .get(gateway.resolve(BACKEND), {}).get("model", ""))},
        "server": {"default_project": DEFAULT_PROJECT or workspace.default_project()},
        "engine": gateway.resolve(BACKEND),
        "engines": gateway.describe_all(),
        "home": str(workspace.home()),
        "config_file": str(workspace.config_path()),
        "settable": list(SETTABLE),
    }


def _altium_state(proj):
    from altium import registry
    installs = registry.find_installs()
    recent = registry.recent_projects()
    install_path = workspace.get("altium.install_path", "")
    if install_path:
        active = next((i for i in installs if i.get("path") == install_path), None)
        if active:
            active_install = active
        else:
            exe = ""
            try:
                candidate = pathlib.Path(install_path) / "X2.EXE"
                if candidate.is_file():
                    exe = str(candidate)
            except OSError:
                pass
            active_install = {
                "build": "",
                "version": "",
                "path": install_path,
                "exe": exe,
            }
    elif installs:
        active_install = installs[0]
    else:
        active_install = None

    link = project_mod.altium_link(proj)
    project_file = link.get("project_file", "")
    if not project_file:
        linked = None
    else:
        p = pathlib.Path(project_file)
        exists = p.is_file()
        if exists:
            try:
                from altium.prjpcb import read_prjpcb
                summary = read_prjpcb(p)
            except Exception as exc:
                summary = {"error": str(exc)}
        else:
            summary = {"error": "file not found"}

        if isinstance(summary, dict) and "sheets" in summary:
            sheets = [str((p.parent / pathlib.Path(s.replace("\\", "/"))).resolve()) for s in summary["sheets"]]
        else:
            sheets = []

        linked = {
            "project_file": project_file,
            "exists": exists,
            "summary": summary,
            "pcb_file": link.get("pcb_file", ""),
            "outputs_dir": link.get("outputs_dir", ""),
            "sheets": sheets,
        }

    return {
        "installs": installs,
        "recent": recent,
        "install_path": install_path,
        "active_install": active_install,
        "linked": linked,
    }


def redraw(project):
    """Sheet pictures are derived; a bad picture must never lose a change."""
    try:
        import render_sheet
        for sid in store.sheet_ids(project):
            render_sheet.render(project, sid)
    except Exception as exc:
        print(f"render failed: {exc}")


def _agent_may_set_library(changes):
    """The agent can say what exists. It cannot say a part is verified or accepted:
    verification is a skill's result, acceptance is the student's."""
    allowed = {"symbol", "footprint", "step", "model_source", "issues"}
    return {k: v for k, v in (changes or {}).items() if k in allowed}


def board_fit_note(project, sess):
    """After a BOM approval: when the parts clearly do not fit the board size (the idea's size; altium.bridge.board_fit_check), tell the
    student once per (tight or may be tight, suggested size), with a size to try. What was said is kept in the project folder
    (fit-said.json), so a restart or one more approval does not say it again; a board that fits again forgets it. The size is never
    changed here."""
    try:
        from altium import bridge
        fit = bridge.board_fit_check(project)
        mark = fit_mark = None
        if fit and fit["text"]:
            fit_mark = [bool(fit["tight"]), list(fit["suggest"] or [])]
        path = store.pdir(project) / "fit-said.json"
        try:
            mark = json.loads(path.read_text(encoding="utf-8")).get("said")
        except (OSError, ValueError, AttributeError):
            mark = None
        if fit_mark is None:
            if mark is not None:
                path.unlink(missing_ok=True)
            return
        if mark == fit_mark:
            return
        path.write_text(json.dumps({"said": fit_mark}), encoding="utf-8")
    except Exception:                                  # an estimate must never stop an approval
        return
    say(project, sess, {"ts": now(), "role": "agent", "text": fit["text"] + " Change it on the Idea page if you agree."})


def decide_and_note(project, sess, pid, decision, by="student", note=True, redraw_now=True):
    """Approve or reject one proposal and do what follows (supply re-check, sheet labels, a note the engine
    reads). The click, the batch endpoint and the autonomy setting all come through here, so the logs are
    the same whoever decided; only `by` differs."""
    if store.decide(project, pid, decision, by=by).get("already"):
        return next(p for p in store.proposals(project) if p["id"] == pid)      # decided that way before: nothing more to do
    project_mod.touch(project)
    prop = next(p for p in store.proposals(project) if p["id"] == pid)
    if decision == "approved" and prop.get("kind") != "idea_diagram":
        if "mpn" in prop.get("changes", {}):
            recheck_async(project, prop["line"])
        recheck_missing(project)           # a new line, or one whose MPN came with a library change
        if redraw_now:
            redraw(project)
    if not note:
        return prop
    decided = {"decision": decision, "proposal": pid}
    if decision != "approved":
        say(project, sess, {"ts": now(), "role": "agent", "text": f"Rejected. {pid} changes nothing.", **decided})
    elif prop.get("kind") == "idea_diagram":
        say(project, sess, {"ts": now(), "role": "agent",
                            "text": "Approved diagram changes. The block diagram has been updated.", **decided})
    else:
        ref = next((l["refs"][0] for l in store.bom_lines(project) if l["key"] == prop["line"] and l.get("refs")),
                   prop["line"])
        what = "added to the BOM" if prop.get("new") else "updated in the BOM, on the schematic label and in the library"
        say(project, sess, {"ts": now(), "role": "agent", "text": "Approved. {{ref:" + ref + "}} is " + what + ".", **decided})
        board_fit_note(project, sess)
    return prop


ALTIUM_ACTIONS = ("altium.create_project", "altium.add_sheet", "altium.skeleton", "altium.add_pcb", "altium.open",
                  "altium.import_rules", "altium.run_outjob")      # (+ altium.draw_schematic, altium.place_pcb, altium.route_pcb: each has its own consent guard)


def library_issue_count(project):
    """How many lines of the part library manifest still carry an issue."""
    return sum(1 for e in store.library_manifest(project).values() if e.get("issues") or e.get("built_issues"))


def _truthy(v):
    """A flag from JSON or a model: true, 1, "true", "yes" are on; "false", "0", "", None are off."""
    return v is True or v == 1 or str(v).strip().lower() in ("1", "true", "yes", "on")


def _pending(project, ids):
    """How many of these proposals still wait for the student (one approved at once by the autonomy setting is done, not pending)."""
    try:
        status = {p["id"]: p.get("status") for p in store.proposals(project)}
        return sum(1 for i in ids if status.get(i) == "pending")
    except Exception:
        return len(ids)


def _usage_applied(applied):
    """The applied list for the usage log's answer: proposals are logged under the proposals, not as applied work."""
    return [x for x in applied if not str(x).startswith("bom.propose:")]


def _bridge_done(project, op, since):
    """The newest altium-log.jsonl entry of `op` that succeeded at or after `since` (epoch seconds), else None: a model
    that ran bridge.py itself in its shell has already done what the action would do."""
    if not since:
        return None
    floor = dt.datetime.fromtimestamp(since).isoformat(timespec="seconds")
    ok = [r for r in store.read_jsonl(store.pdir(project) / "altium-log.jsonl")
          if r.get("op") == op and store.log_ok(r) and str(r.get("ts", "")) >= floor]
    return ok[-1] if ok else None


def _quote_holds(said, last_user) -> bool:
    """idea.confirm's quote must be words the student wrote: the whole of a short message ("מאשר", "yes"), otherwise at
    least 2 words or 8 characters matched as whole words, so "y" or "es" inside a longer message does not count."""
    edge = " .,!?;:()-" + chr(34) + chr(39) + chr(9) + chr(10)
    q = re.sub(r"\s+", " ", str(said or "").lower()).strip(edge)
    u = re.sub(r"\s+", " ", str(last_user or "").lower()).strip(edge)
    if len(q) < 2:
        return False
    if q == u:
        return True
    return (len(q) >= 8 or " " in q) and re.search(r"(?<!\w)" + re.escape(q) + r"(?!\w)", u) is not None


SELF_DRAW = re.compile(r"myself|\bi[\u2019']?ll draw|i will draw|\bi draw|בעצמי|אני אשרטט|אני אצייר|אשרטט אני"
                       r"|\bdon[’']?t draw|\bdo not draw|אל תשרטט|אל תצייר|לא לשרטט|לא תשרטט|אני לא רוצה ש", re.I)
REDRAW_WORD = re.compile(
    r"(?<![\w-])(?:replace|re-?draw|re-?do|overwrite|start\s+over)\b"
    r"|(?<!\w)(?:[וש])?(?:מחדש|תחליף|תחליפי|החלף|להחליף|תמחק|תמחקי|תדרוס|תדרוסי|דרוס|לדרוס)(?!\w)",
    re.I,
)
QUOTE_MISSING = ("student_said must be a verbatim quote (most of it) of ONE student message of this conversation since the last time "
                 "this ran, and that message must tell you to {verb}; no such quote was found. If they already said so, send the quote; ")
ASK_FIRST = QUOTE_MISSING.format(verb="draw the schematic") + "only if they never said who draws: Ask the student first, draw it themselves in Altium or should you draw it? Run this only after their answer."


SELF_PLACE = re.compile(r"myself|\bi[\u2019']?ll place|i will place|\bi place|\bi[\u2019']?ll do the placement|בעצמי|אני אמקם|אמקם אני"
                        r"|\bdon[\u2019']?t place|\bdo not place|אל תמקם|לא למקם|לא תמקם|אני לא רוצה ש", re.I)
SELF_ROUTE = re.compile(r"myself|\bi[\u2019']?ll route|i will route|\bi route|\bi[\u2019']?ll do the routing|בעצמי|אני אנתב|אנתב אני"
                        r"|\bdon[\u2019']?t route|\bdo not route|אל תנתב|לא לנתב|לא תנתב|אני לא רוצה ש", re.I)
REPLACE_WORD = re.compile(
    r"(?<![\w-])(?:re-?place|re-?do|re-?route|overwrite|start\s+over)\b"
    r"|(?<!\w)(?:[וש])?(?:מחדש|תחליף|תחליפי|החלף|להחליף|תמחק|תמחקי|תדרוס|תדרוסי|דרוס|לדרוס|תמקם מחדש|תנתב מחדש)(?!\w)",
    re.I,
)
ASK_PLACE = (QUOTE_MISSING.format(verb="place the parts (the message needs a place word)") + "only if they never said who places: Ask the student first, place the parts "
             "on the board themselves in Altium or should you place them? Run this only after their answer.")
ASK_ROUTE = (QUOTE_MISSING.format(verb="route the board (the message needs a route word)") + "only if they never said who routes: Ask the student first, route the board "
             "themselves in Altium or should you route it? A separate question from placing. Run this only after their answer.")
DRAW_WORD = re.compile(r"draw|sketch|schematic|תצייר|תשרטט|צייר|שרטט|לצייר|לשרטט|אצייר|אשרטט|סכמה|סכימה", re.I)
EARLIER_NEED = {"draw": DRAW_WORD}      # a message from an earlier turn must name the action: a bare "yes" there answered something else
PLACE_WORD = re.compile(r"\bplac(?:e|ing|ement)\b|\bposition|lay ?out|מקם|תמקם|למקם|אמקם|מיקום|השמה|פלייסמנט", re.I)
ROUTE_WORD = re.compile(r"\brout(?:e|ing)\b|auto-?rout|נתב|תנתב|לנתב|אנתב|ניתוב|ראוט", re.I)
SELF_NC = re.compile(r"myself|\bi[\u2019']?ll mark|\bi will mark|בעצמי|אני אסמן|\bdon[\u2019']?t mark|\bdo not mark|אל תסמן|לא לסמן|אני לא רוצה ש", re.I)
NC_WORD = re.compile(r"\bN/?C\b|no[- ]?connect|not connected|unconnected|לא מחובר|ללא חיבור", re.I)
ASK_NC = ("The student's message is the only way to mark an open pin NC without their approval: student_said must be a verbatim quote of their "
          "message telling you to mark pins NC. No such quote: the NC marks wait as ONE proposal the student approves with one click.")
CONSENT = {   # kind -> (they do it themselves, they say replace, ask text, what replace wipes, what it is, a word their message must have)
    "draw": (SELF_DRAW, REDRAW_WORD, ASK_FIRST, "sheet", "draw it", None),
    "place": (SELF_PLACE, REPLACE_WORD, ASK_PLACE, "board's parts and copper", "place them", PLACE_WORD),
    "route": (SELF_ROUTE, REPLACE_WORD, ASK_ROUTE, "board's tracks", "route it", ROUTE_WORD),
    "nc": (SELF_NC, re.compile(r"(?!x)x"), ASK_NC, "pins", "mark them NC", NC_WORD),
}


PARTIAL_WORD = re.compile(r"partial|חלקי|מה שאפשר|what you can", re.I)       # a yes to "keep a half-routed board" says so in the words


def _partial_consent(a, last_user):
    """Keeping a half-routed board needs partial: true and partial_said = the student's own words, and those words say partial."""
    said = a.get("partial_said")
    return (_truthy(a.get("partial")) and bool(said) and _quote_holds(said, last_user)
            and PARTIAL_WORD.search(str(said)) is not None)


SELF_START = "The student said they will"
_WHO = {"draw": "draws", "place": "places", "route": "routes", "nc": "marks the pins"}
_ACTION_ANY = {"draw": DRAW_WORD, "place": PLACE_WORD, "route": ROUTE_WORD, "nc": NC_WORD}
_BOARD_WORD = re.compile(r"\bpcb\b|\bboard\b|לוח|\blayout\b", re.I)
_OTHER_ACTION = {      # words that name ANOTHER action: a self-do clause with only these leaves this one alone
    "draw": re.compile(PLACE_WORD.pattern + "|" + ROUTE_WORD.pattern + "|" + _BOARD_WORD.pattern, re.I),
    "place": re.compile(DRAW_WORD.pattern + "|" + ROUTE_WORD.pattern, re.I),
    "route": re.compile(DRAW_WORD.pattern + "|" + PLACE_WORD.pattern, re.I),
    "nc": re.compile(DRAW_WORD.pattern + "|" + PLACE_WORD.pattern + "|" + ROUTE_WORD.pattern, re.I)}
_CLAUSE = re.compile(r"[,;.!?\n]+|\s+(?=ו)|\s+(?:and|but|while|אבל)\s+", re.I)
_STOP = re.compile(r"\bnot yet\b|\bwait\b|\bstop\b|\bhold (?:on|off)\b|\bnever ?mind\b|\bcancel\b|\bdon[’']?t\b|\bdo not\b"
                   r"|(?<!\w)(?:חכה|חכי|תחכה|עצור|תעצור|עצרי|בטל|ביטול|עזוב)(?!\w)|אל ת\S+", re.I)
_STOP_BARE = re.compile(r"^(?:no|nope|לא)(?!\w)", re.I)      # "no" is a stop only as a short reply or at the start of a clause


_OTHER_VERB = re.compile(r"(?<!\w)(?:delet\w*|remov\w*|renam\w*|erase\w*)|(?<!\w)(?:ת?מחק\w*|ת?מחוק|ת?סיר\w*|למחוק|להסיר)(?!\w)", re.I)
_SHEET_REMOVE = _OTHER_VERB            # the words that remove a sheet
_SHEET_RENAME = re.compile(r"renam\w*|chang\w*\s+(?:the\s+)?(?:name|id)|(?<!\w)(?:ת?שנה|ת?שני|לשנות|שינוי)(?!\w)", re.I)
_NEG = r"(?:don[’']?t|do not|never|אל)"
_NEG_OTHER = re.compile(_NEG + r"\s+(?:\S+\s+){0,2}?(?:" + _OTHER_VERB.pattern + ")", re.I)


class _Stops:
    """The student's words that say no, wait or stop. The unambiguous words (stop, wait, don't, עצור ...) count anywhere; a bare
    "no"/"לא" only as a short reply (the clause is at most three words: "no", "no thanks", "לא עכשיו"), never inside a sentence
    such as "so that no signal net runs between the sheets". With `kind` (draw / place / route) a negation that directly governs a
    delete / remove / rename verb ("don't delete Main", "אל תמחק את Main") is cut out of its clause first: it forbids ANOTHER action,
    so it is no stop for this one. The rest of the clause is still read ("wait until I delete the old parts" stops)."""
    @staticmethod
    def search(text, kind=None):
        text = str(text or "")
        for clause in _CLAUSE.split(text):
            if kind:
                clause = _NEG_OTHER.sub(lambda m: m.group(0) if _ACTION_ANY[kind].search(m.group(0)) else " ", clause)
            if _STOP.search(clause):
                return True
            words = clause.strip().split()
            if words and len(words) <= 3 and _STOP_BARE.match(words[0]):
                return True
        return False


_STOP_ANY = _Stops()
_SENT = re.compile(r"[^.!?\n]+[.!?]*")
_FILLER = re.compile(r"^(?:(?:ok|okay|yes|yeah|sure|so|well|fine|כן|בסדר|אוקיי|טוב)[,\s]+)+", re.I)
_QUESTION = re.compile(r"^(?:how|what|why|can|could|should|would|is|are|do|does|when|where|which|who|איך|מה|למה|האם|אפשר|כיצד|מתי|איפה)(?!\w)", re.I)
_INSTR_HE = {"draw": "תצייר|תשרטט|צייר|שרטט", "place": "תמקם|מקם|תניח|הנח", "route": "תנתב|נתב"}
_VERB_EN = {"draw": "draw", "place": "place", "route": "route"}
_OBJECT = {"draw": re.compile(r"\bschematics?\b|\bsheet\b|סכמה|סכימה", re.I),
           "place": re.compile(r"\bparts\b|\bcomponents\b|\bboard\b|\bpcb\b|רכיבים|לוח|חלקים", re.I),
           "route": re.compile(r"\bboard\b|\bpcb\b|\btracks\b|\btraces\b|לוח|מסלולים", re.I)}
_INSTR = {k: re.compile(r"(?<!\w)(?:" + _INSTR_HE[k] + r")(?!\w)|(?:^|\b(?:you|please|then|now|just|ahead and|and)\s+(?:\w+\s+)?)" + _VERB_EN[k] + r"\b", re.I)
          for k in _VERB_EN}
_BLOCK_DIAGRAM = re.compile(r"block diagram|דיאגרמ", re.I)


def _is_question(sentence):
    s = _FILLER.sub("", sentence.strip().lower()).strip(" -\"'")
    return "?" in sentence or _QUESTION.match(s) is not None


def _instruction(kind, text):
    """True when a sentence of `text` that is no question tells the agent to do `kind` and names its object (an earlier message:
    "how do I route this?", "explain the schematic", "you draw the block diagram" are no instruction)."""
    for sent in _SENT.findall(str(text or "")):
        if _is_question(sent):
            continue
        s = _FILLER.sub("", sent.strip().lower())
        if _INSTR[kind].search(s) and _OBJECT[kind].search(s):
            return True
    return False


def _self_verdict(kind, text):
    """'self' when a clause that names this action says the student does it (or does not want the agent to), 'unsure' when such a
    clause names no action at all or only the board ("I'll do the PCB myself"), '' when none: a self-do about another action does not count."""
    self_re = CONSENT[kind][0]
    for clause in _CLAUSE.split(str(text or "")):
        if not self_re.search(clause):
            continue
        if _ACTION_ANY[kind].search(clause):
            return "self"
        if _OTHER_ACTION[kind].search(clause):
            continue
        return "unsure"
    return ""


def _self_text(kind, verdict):
    verb = CONSENT[kind][4].split()[0]
    if verdict == "self":
        return f"{SELF_START} do it themselves. Do not {verb}; help them with the manual steps."
    return (f"{SELF_START} do something themselves and it is not clear that it is not this action. Do not {verb}; "
            f"ask the student who {_WHO[kind]}: they themselves in Altium or should you? Run this only after their answer.")


def _norm_quote(t):
    return re.sub(r"\s+", " ", str(t or "").lower()).strip(" .,!?;:()-\"'")


def _bad_replace_earlier(kind, text):
    """True when an earlier student message refuses, stops, negates, or self-does a replace of `kind`."""
    return bool(_self_verdict(kind, text) or _REPLACE_SELF.search(text)
                or _STOP_ANY.search(text) or _NEGATED.search(text) or _REPLACE_NEG.search(text))


def _valid_replace_quote(kind, said, last_user, earlier):
    """True when `said` verbatim-quotes (>=50%) `last_user` (validated by `_replace_consent`), or an `earlier` non-question
    message for `kind` with no intervening or in-message self-do, stop, or negation."""
    q = _norm_quote(said)
    u = _norm_quote(last_user)
    if u and _quote_holds(said, last_user) and len(q) >= 0.5 * len(u):
        return True
    for src in earlier:
        if _bad_replace_earlier(kind, src):
            return False
        su = _norm_quote(src)
        if not (su and _quote_holds(said, src) and len(q) >= 0.5 * len(su)):
            continue
        if kind == "draw" and _BLOCK_DIAGRAM.search(src) and not _OBJECT["draw"].search(src):
            continue
        other_kind = (not _REPLACE_SPECIFIC[kind].search(src)
                      and any(_REPLACE_SPECIFIC[k].search(src) for k in _REPLACE_SPECIFIC if k != kind))
        if other_kind:
            continue
        sents = [s for s in _SENT.findall(str(src or "")) if s.strip()]
        if any(not _is_question(s) and not _REPLACE_INDIRECT_Q.search(s)
               and (_ACTION_ANY[kind].search(s) or CONSENT[kind][1].search(s)) for s in sents):
            return True
    return False


def _consent(kind, a, last_user, earlier=(), prev_agent=""):
    """The action's consent (`_consent_base`); then, for replace, `_replace_consent`: only a short, unambiguous replace or yes of the
    CURRENT message grants it (never a longer message, never an earlier one)."""
    why = _consent_base(kind, a, last_user, earlier)
    if not _truthy(a.get("replace")):
        return why
    if why:
        if not (_asked_replace(kind, prev_agent)
                and not _self_verdict(kind, last_user)
                and not _STOP_ANY.search(last_user)
                and _valid_replace_quote(kind, a.get("student_said"), last_user, earlier)):
            return why
    return _replace_consent(kind, a, last_user, prev_agent)


def _consent_base(kind, a, last_user, earlier=()):
    """'' when a student message really asked the agent to do `kind` ("draw" the schematic, "place" the parts, "route" the board) or,
    for replace, to do it over what is there, else why not. The quote is checked against the last message first, then against
    `earlier` (the student's messages of this conversation since `kind` last ran, newest first): a clear instruction given one
    turn before (a library build in between) still counts, but such a message must be an instruction to the agent for this action
    (no question, an imperative, the right object). The current message, and every message newer than the quote, cancels with a
    do-it-myself (about this action) or a no / wait / stop."""
    why = _consent_one(kind, a, last_user, False)
    if not why:
        return ""
    if why.startswith(SELF_START):
        return why
    verb = CONSENT[kind][4].split()[0]
    verdict = _self_verdict(kind, last_user)
    if verdict:
        return _self_text(kind, verdict)
    if _STOP_ANY.search(last_user, kind):
        return f"The student's last message says no, wait or stop. Do not {verb}; ask the student what they want first."
    for u in earlier:
        w = _consent_one(kind, a, u, True)
        if not w:
            return ""
        if w.startswith(SELF_START):
            return w
        verdict = _self_verdict(kind, u)
        if verdict:
            return _self_text(kind, verdict)
        if _STOP_ANY.search(u, kind):
            return f"The student said no, wait or stop after that. Do not {verb}; ask the student what they want first."
    return why


def _consent_one(kind, a, last_user, earlier_turn):
    self_re, replace_re, ask, wipes, verb, need = CONSENT[kind]
    if earlier_turn:
        need = need or EARLIER_NEED[kind]
    norm = lambda t: re.sub(r"\s+", " ", str(t or "").lower()).strip(" .,!?;:()-\"'")
    q, u = norm(a.get("student_said")), norm(last_user)
    if not _quote_holds(a.get("student_said"), last_user):
        return ask
    if len(q) < 0.5 * len(u):
        return ask + (" The quote was too short (it must be most of their message): re-send this action with student_said = the student's "
                      "WHOLE message, copied verbatim, not only the sentence that tells you to " + verb.split()[0] + ".")
    if need is not None and not need.search(u):        # "yes" to the schematic question is not a yes to placing or routing
        return ask
    if earlier_turn and not _instruction(kind, last_user):
        return ask
    word = need or _ACTION_ANY[kind]
    sents = [x for x in _SENT.findall(str(last_user or "")) if word.search(x)]
    if sents and all(_is_question(x) for x in sents):      # "how do I route this?" asks, it does not tell
        return ask
    if kind == "draw" and _BLOCK_DIAGRAM.search(u) and not _OBJECT["draw"].search(u):
        return ask
    verdict = _self_verdict(kind, last_user)
    if verdict:
        return _self_text(kind, verdict)
    return ""


_NEGATED = re.compile(r"(?<!\w)(?:never|shouldn[’']?t|should not|no need|not|without|don[’']?t|do not|אסור|אל|לא)(?!\w)", re.I)
_HARD_STOP = re.compile(r"(?<!\w)(?:not yet|wait|stop|hold (?:on|off)|never ?mind|cancel|no|nope)(?!\w)"
                        r"|(?<!\w)(?:חכה|חכי|תחכה|עצור|תעצור|עצרי|בטל|ביטול|עזוב|רגע|עוד לא|לא)(?!\w)", re.I)
_REPLACE_NEG = re.compile(
    r"\b\w+n[’']t\b"
    r"|\b(?:cannot|dont|cant|wont|shouldnt|wouldnt|couldnt|didnt|doesnt|isnt|arent|mustnt|neednt|hasnt|havent|wasnt|werent"
    r"|nah|naw|negative|nothing|none|neither|nor|no\s+reason|avoid|never|refus(?:e|ing)|declin(?:e|ing)|object(?:ing)?)\b"
    r"|(?<!\w)(?:וש|ו|ש)?(?:לא|אל|אין|אינ(?:י|ני|ו|ה|ם|ן|נו)|בלי|מבלי|ללא|אסור|תי?מנעי?|מ?להי?מנע|הי?מנעי?|נמנע(?:ת|ים|ות)?"
    r"|מיותר(?:ת|ים|ות)?|חבל|בשום|מתנגד|מתנגדת|מסרב|מסרבת|כלום)(?!\w)",
    re.I,
)
_REPLACE_REVERSAL = re.compile(
    r"\b(?:keep(?:ing)?|leav(?:e|ing)|preserv(?:e|ing)|retain(?:ing)?|sav(?:e|ing)|back\s*up|scratch\s+that|forget(?:ting)?|ignor(?:e|ing)"
    r"|skip(?:ping)?|abort(?:ing)?|paus(?:e|ing)|hang\s+on|hold\s+(?:up|it)|drop\s+it|undo|disregard(?:ing)?|nvm"
    r"|second\s+thoughts?|chang(?:ed|ing)\s+my\s+mind|change\s+of\s+mind"
    r"|actually|instead|rather|but|however|though|although|except|bad\s+idea|unnecessary)\b"
    r"|(?<!\w)(?:וש|ו|ש)?(?:תשאיר|תשאירי|להשאיר|השאר|השאירי|נשאיר|אשאיר|שמור|שמרי|תשמור|תשמרי|לשמור|אשמור|נשמור|גיבוי|לגבות|תגבה"
    r"|תוותר|תוותרי|וותר|וותרי|לוותר|נוותר|אוותר|שכח|שכחי|תשכח|תשכחי|לשכוח|בעצם|במקום|עדיף|אבל|אך|חוץ|מלבד"
    r"|הפסק|הפסיקי|תפסיק|תפסיקי|להפסיק|חכה|חכי|תחכה|תחכי|לחכות|תמתין|תמתיני|המתן|המתיני|להמתין|עצור|עצרי|תעצור|תעצרי|לעצור"
    r"|בטל|בטלי|תבטל|תבטלי|ביטול|לבטל|עזוב|עזבי|תעזוב|תעזבי|לעזוב|דלג|תדלג|תדלגי|לדלג|התחרטתי|מתחרט|מתחרטת|רד\s+מזה|רדי\s+מזה|רגע|עוד\s+לא)(?!\w)",
    re.I,
)
_REPLACE_HEDGE_COND = re.compile(
    r"\b(?:first|when|whenever|while|later|soon|tomorrow|next\s+time|eventually|might|may|could|would|should|shall|unsure|uncertain"
    r"|guess|suppose|wonder(?:ing)?|possibly|potentially|likely|pending|assuming|provided|if|unless|only)\b"
    r"|(?<!\w)(?:וש|ו|ש)?(?:כדאי|אפשר|אפשרי|אז|כאשר|בהמשך|בינתיים|עדיין|כרגע|שנייה|שניה|מאוחר\s+יותר|אחר[\s\-–]+כך|אח[\"״]כ"
    r"|עוד\s+מעט|מחר|בתנאי|תלוי|תלויה|ב?ספק|כנראה|יי?תכן|לדעתי|מתלבט|מתלבטת|מתלבטים|אם|אלא|רק|אולי|אחרי|קודם|לפני|לאחר|במידה|במקרה|עד\s+ש)(?!\w)"
    r"|(?<!\w)ו?כש",
    re.I,
)
_REPLACE_SELF = re.compile(
    r"\b(?:myself|on\s+my\s+own|by\s+hand|manually|i[’']?ll|i\s+will|let\s+me"
    r"|(?:i[’']?m|i\s+am)(?:\s+(?:just|really|also|simply))?\s+(?:going\s+to|gonna)"
    r"|i(?:\s+(?:just|really|also|simply))?\s+(?:(?:want|need|plan|prefer|intend|have)\s+to|gonna|wanna)"
    r"|i[’']?d(?:\s+(?:just|really|also|simply))?\s+like\s+to|i\s+would(?:\s+(?:just|really|also|simply))?\s+like\s+to)\b"
    r"|\bi\s+(?:re-?place|re-?draw|re-?do|re-?route|overwrit\w*|start\s+over)\b"
    r"|(?<!\w)(?:ו)?(?:בעצמי|ביד|ידנית|א(?:חליף|דרוס|מחק|מחוק|שרטט|צייר|מקם|נתב|עשה|תחיל|נסה))(?!\w)"
    r"|(?<!\w)(?:אני\s+)?(?:רוצה|צריך|צריכה|מעדיף|מעדיפה|מתכוון|מתכוונת|הולך|הולכת)\s+ל\S+"
    r"|(?<!\w)אני\s+(?:מחליף|מחליפה|דורס|דורסת|מוחק|מוחקת|משרטט|משרטטת|מצייר|מציירת|ממקם|ממקמת|מנתב|מנתבת|עושה|מתחיל|מתחילה|לבד)(?!\w)",
    re.I,
)
_REPLACE_INDIRECT_Q = re.compile(
    r"\b(?:how|why|whether|explain(?:ing)?)\b"
    r"|(?<!\w)(?:וש|ו|ש)?(?:איך|למה|מדוע|האם|כיצד|מתי|איפה|להסביר|תסביר|תסבירי|הסבר)(?!\w)",
    re.I,
)
_YES = re.compile(r"(?<!\w)(?:yes|yeah|yep|yup|sure|ok|okay|go ahead|כן|אוקיי|אוקי|בסדר|סבבה|מאשר|מאשרת|בהחלט)(?!\w)", re.I)
_YES_TOKEN = (
    r"(?:yes|yeah|yep|yup|sure|ok|okay|alright|all\s+right|fine|go\s+ahead|do\s+it|proceed|confirm(?:ed)?|approv(?:e|ed)|please|thanks|thank\s+you"
    r"|כן|אוקיי|אוקי|בסדר|טוב|סבבה|יאללה|קדימה|תמשיך|המשך|בבקשה|תודה|מאשר|מאשרת|מאושר|בהחלט|לגמרי|תעשה\s+את\s+זה|לך\s+על\s+זה)"
)
_BARE_YES = re.compile(r"^[\s,.!]*?" + _YES_TOKEN + r"(?:[\s,.!]+" + _YES_TOKEN + r")*[\s,.!]*$", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
_NOT_APPLIED_TAIL = re.compile(r"(?:^|\n\n)\(Not applied:.*$", re.S)
_REPLACE_ASKED_MANUAL = re.compile(
    r"\b(?:by\s+hand|yourself|yourselves|manually|on\s+your\s+own|or\s+should\s+i|or\s+will\s+you|or\s+do\s+you"
    r"|will\s+you\s+(?:re-?draw|re-?place|re-?do|re-?route|draw|place|route|overwrite))\b"
    r"|(?<!\w)(?:ו)?(?:ביד|בעצמך|בעצמכם|ידנית|לבדך)(?!\w)"
    r"|(?<!\w)או\s+ש?(?:אני|אנחנו|אתה|את)(?!\w)"
    r"|(?<!\w)(?:אתה|את)\s+(?:תשרטט|תשרטטי|תצייר|תציירי|תמקם|תמקמי|תנתב|תנתבי|תחליף|תחליפי)(?!\w)",
    re.I,
)
_REPLACE_ASKED_PART = re.compile(
    r"(?i:\bbom\b)|(?i:\breplac(?:e|ing)\s+(?:the\s+)?|(?:להחליף|תחליף|אחליף)\s+(?:את\s+)?)(?:\{\{ref:)?[A-Z]{1,3}\d{1,3}(?!\w)"
)
_REPLACE_ASKED_VERB = re.compile(
    r"(?<![\w-])(?:replac(?:e|ing)|overwrit(?:e|ing)|re-?draw(?:ing)?|re-?do(?:ing)?|re-?plac(?:e|ing)|re-?rout(?:e|ing)|wip(?:e|ing)|start\s+over)\b"
    r"|(?<!\w)(?:[ולש])?(?:מחדש|להחליף|תחליף|אחליף|לדרוס|תדרוס|אדרוס)(?!\w)",
    re.I,
)
_REPLACE_ASKED_DEL = re.compile(r"(?<!\w)(?:[ולש])?(?:למחוק|תמחק|אמחק)(?!\w)", re.I)
_REPLACE_ASKED_DEL_CTX = re.compile(
    r"(?<!\w)(?:ו?[בלמהש]|ו)?(?:ציור|שרטוט|לשרטט|לצייר|קיים|קיימ(?:ת|ים|ות)|הישן|הישנה|הישנים|נחושת|מסלולים)(?!\w)|מה שיש",
    re.I,
)
_REPLACE_SPECIFIC = {
    "draw": re.compile(
        r"(?<![\w-])(?:sheets?|schematics?|draw(?:ing)?|re-?draw(?:ing)?)\b"
        r"|(?<!\w)(?:ו?[בלמהש]|ו)?(?:גיליון|גליון|סכמה|סכימה|ציור|שרטוט|לשרטט|לצייר|תשרטט|תשרטטי|תצייר|תציירי|שרטט|צייר|אשרטט|אצייר)(?!\w)",
        re.I,
    ),
    "place": re.compile(
        r"(?<![\w-])(?:re-plac(?:e|ing)|plac(?:e|ing|ement)|parts|components|copper)\b"
        r"|(?<!\w)(?:ו?[בלמהש]|ו)?(?:רכיבים|השמה|מיקום|נחושת|למקם|תמקם|תמקמי|מקם|אמקם)(?!\w)",
        re.I,
    ),
    "route": re.compile(
        r"(?<![\w-])(?:re-?rout(?:e|ing)|rout(?:e|ing)|tracks|traces)\b"
        r"|(?<!\w)(?:ו?[בלמהש]|ו)?(?:מסלולים|ניתוב|לנתב|תנתב|תנתבי|נתב|אנתב)(?!\w)",
        re.I,
    ),
}
_REPLACE_SHARED = {
    "draw": re.compile(r"\bexisting\b|(?<!\w)(?:ו?[בלמהש]|ו)?(?:קיים|קיימ(?:ת|ים|ות))(?!\w)|מה שיש", re.I),
    "place": re.compile(r"\b(?:board|pcb)\b|(?<!\w)(?:ו?[בלמהש]|ו)?לוח(?!\w)|מה שיש", re.I),
    "route": re.compile(r"\b(?:board|pcb)\b|(?<!\w)(?:ו?[בלמהש]|ו)?לוח(?!\w)|מה שיש", re.I),
}
REPLACE_MAX_WORDS = 8


def previous_agent_text(chat, last_user=""):
    """The agent's message right before the student's current one ('' when there is none)."""
    recs = list(chat or [])
    if recs and recs[-1].get("role") == "user" and str(recs[-1].get("text") or "").strip() == str(last_user or "").strip():
        recs = recs[:-1]
    for r in reversed(recs):
        if r.get("role") == "agent":
            if r.get("error"):
                continue
            return _NOT_APPLIED_TAIL.sub("", str(r.get("text") or "")).strip()
        if r.get("role") == "user":
            return ""
    return ""


def _asked_replace(kind, prev_agent):
    """True when a question sentence of `prev_agent` asked whether the agent may replace the existing work of `kind`."""
    cleaned = _URL_RE.sub("", str(prev_agent or ""))
    for sent in _SENT.findall(cleaned):
        if "?" not in sent or _REPLACE_ASKED_MANUAL.search(sent) or _REPLACE_ASKED_PART.search(sent):
            continue
        has_verb = bool(_REPLACE_ASKED_VERB.search(sent)) or (
            bool(_REPLACE_ASKED_DEL.search(sent)) and bool(_REPLACE_ASKED_DEL_CTX.search(sent))
        )
        if not has_verb:
            continue
        spec = bool(_REPLACE_SPECIFIC[kind].search(sent))
        if not spec and not _REPLACE_SHARED[kind].search(sent):
            continue
        if not spec and any(_REPLACE_SPECIFIC[k].search(sent) for k in _REPLACE_SPECIFIC if k != kind):
            continue
        return True
    return False


def _replace_consent(kind, a, last_user, prev_agent=""):
    """'' when the student's last message is a short, unambiguous replace or yes, else why not. Simple by construction: at most 8 words,
    a replace word (or a bare yes right after the agent asked about replacing), and no negation, reversal, hedge, condition, question,
    self-do or stop word anywhere in it. A longer message never grants replace, however it is worded: the agent asks a yes/no question instead."""
    wipes, replace_re = CONSENT[kind][3], CONSENT[kind][1]
    text = str(last_user or "")
    words = re.findall(r"[\w’'\-]+", text)
    asked_yes = bool(_YES.search(text)) and bool(_BARE_YES.match(text.strip())) and _asked_replace(kind, prev_agent)
    has_q = ("?" in text or bool(_REPLACE_INDIRECT_Q.search(text))
             or (not asked_yes and (any(_is_question(s) for s in _SENT.findall(text))
                                    or any(_is_question(c) for c in _CLAUSE.split(text) if c.strip()))))
    other_kind = (not _REPLACE_SPECIFIC[kind].search(text)
                  and any(_REPLACE_SPECIFIC[k].search(text) for k in _REPLACE_SPECIFIC if k != kind))
    clean = (len(words) <= REPLACE_MAX_WORDS and not has_q and not other_kind
             and not _NEGATED.search(text) and not _REPLACE_NEG.search(text)
             and not _REPLACE_REVERSAL.search(text)
             and not _HEDGE.search(text) and not _CONDITION.search(text) and not _REPLACE_HEDGE_COND.search(text)
             and not _REPLACE_SELF.search(text)
             and not _STOP_ANY.search(text) and not _HARD_STOP.search(text))
    if clean and (replace_re.search(text) or asked_yes):
        return ""
    sheet = str(a.get("sheet") or "").strip()
    what = f"the drawing on sheet {sheet}" if kind == "draw" and sheet else f"the {wipes}"
    be = "is" if wipes == "sheet" else "are"
    return (f"The {wipes} {be} only wiped on a short, clear yes from the student (a long message never grants replace). Ask a yes/no "
            f"question: \"Replace {what}? This wipes what is there (a backup is kept). Answer yes/no.\" Run this again only after their "
            "short answer (such as \"yes, replace\").")


_ME = re.compile(r"myself|\bi[’']?ll\b|\bi will\b|בעצמי|(?<!\w)א(?:מחק|סיר|שנה|מחוק)\w*", re.I)
_CONDITION = re.compile(r"(?<!\w)(?:after|then|before|until|once)(?!\w)|(?<!\w)(?:אחרי|קודם|לפני|אחר כך)(?!\w)|(?<!\w)עד ש", re.I)
_FILL = r"(?:please|now|just|quickly|entirely|completely|נא|בבקשה|עכשיו|מהר|כבר|גם|לגמרי)"
_GAP = r"(?:the|sheet|page|schematic|את|ה|ה-|הגיליון|גיליון|הדף|דף|השם|שם|של)"
_TAILWORD = r"(?:sheet|page|גיליון|דף|from the project|מהפרויקט|" + _FILL + ")"
_LEADIN = (r"(?:i[’']?d like you to|i would like you to|i want you to|i need you to|you can|you should|can you|could you|would you|"
           r"ok|okay|yes|כן|תוכל|תוכלי)")
_POLITE = re.compile(r"^(?:(?:ok|okay|yes|כן)[,\s]+)*(?:(?:can|could|would) you\b|תוכל)", re.I)      # a polite request, when nothing in the message asks or hedges
_HEDGE = re.compile(r"not sure|should i|maybe|perhaps|do you think|or should|i think|i guess|probably|נראה לי|(?<!\w)חושב\w*|(?<!\w)or\b|לא בטוח|אולי|(?<!\w)או ש|(?<!\w)או(?!\w)", re.I)
_WANT_THAT = re.compile(r"(?<!\w)(אני רוצה|רוצה|אני מבקש|מבקש) ש(?=\S)")          # "אני רוצה שתמחק": the ש is "that", not part of the verb


def _unthat(clause):
    """A leading Hebrew "ו" and the "אני רוצה ש" of "אני רוצה שתמחק" (want that you delete) turned into "please": only that form is a request; "אני רוצה למחוק"
    (I want to delete) is the student's own wish and has no lead-in."""
    return _WANT_THAT.sub("please ", re.sub(r"^\s*ו(?=\S)", "", clause))
_AFTER = re.compile(r"\s+(?:since|because|כי|מפני ש)\s+.*$", re.I)       # the reason is no part of the instruction


def _name_pat(name):
    """The sheet name (any case: the rest of the clause is strict, so "the power LED" fails on "LED"), with one Hebrew prefix letter
    (ל ב ה ו, optional hyphen) allowed."""
    return r"(?:[לבהו]-?)?(?i:" + re.escape(name) + r")(?!\w)"


def _clause_ok(kind, clause, name, to=""):
    """True when the whole `clause` has the shape  [filler]* VERB [filler / article / sheet words]* NAME [tail]  with nothing else: the
    tail is nothing, sheet / page / גיליון, filler, "from the project" (for a rename: "to <new id>" / "ל<new id>" first). The passive
    "NAME should/must be deleted / renamed (to X)" also fits. A "'s", a part, a title, a preposition, a second noun anywhere in the clause
    is about something else than the sheet: refused. A leading Hebrew "ו" (and) and a polite lead-in ("I'd like you to", "can you") are fine."""
    clause = _AFTER.sub("", clause.strip(" .!?\"'\t")).strip()
    clause = _unthat(clause)
    rename = kind == "netlist.rename"
    verb = (r"(?:renam\w*(?:\s+the\s+name\s+of)?|chang\w*\s+(?:the\s+)?(?:name|id)(?:\s+of)?|(?<!\w)(?:ת?שנה|ת?שני|לשנות|שינוי)(?!\w))"
            if rename else "(?:" + _SHEET_REMOVE.pattern + ")")
    nm = _name_pat(name)
    to_pat = r"(?:to\s+|ל-?)" + _name_pat(to).replace("(?:[לבהו]-?)?", "", 1) if rename and to else None
    tail = r"(?:\s+" + _TAILWORD + ")*"
    if rename:
        if not to_pat:
            return False
        tail = tail + r"\s+" + to_pat + tail
    lead = r"(?:(?:" + _FILL + "|" + _LEADIN + r")\s+)*"
    act = re.compile("^" + lead + verb + r"\s+(?:(?:" + _FILL + "|" + _GAP + r")\s+)*" + nm + tail + "$", re.I)
    passive = re.compile(r"^(?:the\s+)?(?:(?:sheet|page)\s+)?" + nm + r"\s+(?:should|must)\s+be\s+(?:" + _FILL + r"\s+)*(?:" +
                         (r"renam\w*" if rename else _SHEET_REMOVE.pattern) + ")" + tail + "$", re.I)
    return bool(act.match(clause) or passive.match(clause))


def _sheet_edit_consent(kind, a, last_user):
    """'' when the student's own words ask to remove (delete) or rename a netlist sheet, else why not. The quote has the remove / rename
    word with the sheet as its object (and for a rename the new id); a question, a negation before the verb ("don't", "never",
    "shouldn't be", "no need", "אסור"), a do-it-myself ("I'll delete Main myself"), or a no / wait / stop anywhere in the message is no
    instruction."""
    said, sheet = str(a.get("student_said") or ""), str(a.get("sheet") or "")
    word = _SHEET_REMOVE if kind == "netlist.remove" else _SHEET_RENAME
    what = "remove" if kind == "netlist.remove" else "rename"
    if not _quote_holds(said, last_user):
        return f"student_said must be a verbatim quote of the student's message that tells you to {what} the sheet. Ask the student first."
    to = str(a.get("to") or "")
    names = [sheet] + ([to] if kind == "netlist.rename" else [])
    # the student's whole clauses (not only the quote of them: "delete the Main" is part of "delete the Main LED"); punctuation splits,
    # "and" does not, and a dot between digits ("01.5") is no split
    verb_clauses = [c for c in re.split(r"[,;!?\n]+|(?<!\d)\.|\.(?!\d)", str(last_user or "")) if word.search(_unthat(c))]
    ok = bool(verb_clauses) and all(n.strip() for n in names) and all(_clause_ok(kind, c, sheet, to) for c in verb_clauses)
    if not ok:
        return f"the quote must ask to {what} the sheet {sheet}" + (f" to {to}" if kind == "netlist.rename" else "") + " (the sheet itself, named). Ask the student first."
    if _STOP_ANY.search(last_user):
        return "the student's message says no, wait or stop. Do not change the sheet; ask what they want."
    if _HEDGE.search(str(last_user or "")):
        return "the student's message hedges (not sure, maybe, or ...). Do not change the sheet; confirm with them first."
    if _CONDITION.search(str(last_user or "")):
        return "the student's message makes it conditional (after, first, then ...). Do not change the sheet yet; ask what they want."
    for sent in _SENT.findall(str(last_user or "")):
        if word.search(_unthat(sent)) and ("?" in sent or (_is_question(sent) and not (_POLITE.match(sent.strip().lower())
                                                                                   and "?" not in str(last_user) and not _HEDGE.search(str(last_user))))):
            return "the student asked a question about it; it is no instruction. Answer it and ask."
    for clause in _CLAUSE.split(str(last_user or "")):
        m = word.search(clause)
        if m and _ME.search(clause):
            return "the student said they will do it themselves. Do not change the sheet; help them with the manual steps."
        if m and _NEGATED.search(clause[:m.start()]):
            return "the student's message is a refusal or a worry about this, not an instruction. Do not change the sheet; ask what they want."
    return ""


def _draw_consent(a, last_user, earlier=(), prev_agent=""):
    return _consent("draw", a, last_user, earlier, prev_agent)


_CONSENT_ACTION = {"draw": "altium.draw_schematic", "place": "altium.place_pcb", "route": "altium.route_pcb",
                   "rules": "altium.import_rules", "outputs": "altium.run_outjob",
                   "drc": "altium.run_drc"}      # rules / outputs / drc: buttons only, the chat asks no words for them


def consent_words(chat, last_user):
    """The current message as consent evidence: '' when a button wrote it (flagged generated in the stored chat)."""
    recs = list(chat or [])
    if recs and recs[-1].get("role") == "user" and recs[-1].get("text") == last_user and recs[-1].get("generated"):
        return ""
    return last_user


def earlier_student_messages(chat, kind, last_user=""):
    """The student's messages of this conversation before the current one (newest first), back to the last time the action of `kind`
    was applied (that run used up what they said). `chat` = the stored records; the current message may be the last of them."""
    recs = list(chat or [])
    if recs and recs[-1].get("role") == "user" and recs[-1].get("text") == last_user:
        recs = recs[:-1]
    out = []
    for r in reversed(recs):
        if r.get("role") == "agent" and any(str(x).startswith(_CONSENT_ACTION[kind]) for x in r.get("applied") or []):
            break
        if r.get("role") == "user" and r.get("text") and not r.get("generated"):      # a button's text is not the student's words
            out.append(str(r["text"]))
    return out


_DESIG = r"[A-Z]{1,3}\d{1,3}(?!\w)(?!\.\d)"
# two or more designators written together: "R1, R2", "C2/C3", "R1-R4", "R1–R4", "R1..R4"
_REF_GROUP = re.compile(rf"(?<![\w.+-]){_DESIG}(?:\s*(?:,|/|-|–|\.\.)\s*{_DESIG})+")
_REF_TOKEN = re.compile(rf"([A-Z]{{1,3}})(\d{{1,3}})(?!\w)(?!\.\d)|(-|–|\.\.)")
_LISTED_LINE = re.compile(r"^\s*(?:\||[-*•]\s|\d{1,2}[.)]\s)")        # a table row or a list item: where a reply names its parts


def _ref_groups(reply):
    """[[designator, ...]] for each group of designators a table row or list item of the reply writes together, ranges expanded
    ("R1-R3" -> R1, R2, R3; same letters, at most 32 apart). {{ref:R1}} tokens, bold and code marks are read as plain text."""
    text = re.sub(r"\{\{ref:([^}|]+)\}\}", r"\1", str(reply or "")).replace("**", "").replace("`", "")
    groups = []
    for line in text.splitlines():
        if not _LISTED_LINE.match(line):
            continue
        for m in _REF_GROUP.finditer(line):
            refs, dash = [], False
            for pre, num, sep in _REF_TOKEN.findall(m.group(0)):
                if sep:
                    dash = True
                    continue
                if dash and refs:
                    p0, n0 = re.match(r"([A-Z]+)(\d+)", refs[-1]).groups()
                    if p0 == pre and 0 < int(num) - int(n0) <= 32:
                        refs += [f"{pre}{n}" for n in range(int(n0) + 1, int(num))]
                refs.append(pre + num)
                dash = False
            groups.append(list(dict.fromkeys(refs)))
    return groups


def refs_missing_from_bom(project, reply):
    """Designators that a table row or list item of the reply names together with others ("| C1, C2 | 100nF |", "- R1, R2: 5.1k",
    "R1-R4") but that no BOM line (nor a pending BOM proposal) holds, while another designator of the same group is held: one line
    proposed for several identical parts with only the first ref (AGENTS.md: every part named in the reply table is in some line's
    refs). A group none of whose names is in the BOM is left alone (pin names "PA9, PA10", "CC1/CC2"). [] when all are covered."""
    groups = _ref_groups(reply)
    if not groups:
        return []
    held = {r for l in store.bom_lines(project) for r in [l["key"], *(l.get("refs") or [])]}
    for p in store.proposals(project):
        if p.get("kind") == "bom" and p.get("status") == "pending":
            held |= {p.get("line"), *((p.get("changes") or {}).get("refs") or [])}
    letters = lambda r: re.match(r"[A-Z]+", r).group(0)
    # one line holds identical parts: only a name with the letters of a held one in its group counts ("U1, NE555" is a part and its MPN)
    return list(dict.fromkeys(r for g in groups for r in g if r not in held
                              and any(h in held and letters(h) == letters(r) for h in g)))


_WARN_RE = re.compile(r"\(\s*(?:\d+\s+)?warnings?:\s*(.*)\)\s*$|WARNING:\s*(.*)$|(\(\d+ with issues\))|(missing [^()]*)|(Could not[^;]*)", re.I | re.S)


def warning_of(item):
    """The warning an applied action's result carries ('' when none): '(2 warnings: ...)', 'WARNING: ...', 'missing <layer>',
    'Could not ...', 'with issues'. The chat shows such a result as an amber chip, never as a plain green 'done'."""
    m = _WARN_RE.search(item or "")
    if not m:
        return ""
    return next((g for g in m.groups() if g), "").strip() or "see the result"


def warned_map(applied):
    """{applied result: warning text} for the results that carry one (stored on the chat record as 'warned')."""
    return {a: w for a in applied for w in [warning_of(a)] if w}


def bom_value_warning(project, a):
    """' (warning: ...)' when a bom.propose line for a resistor, capacitor or inductor has no value ('5.1k'), else ''.
    The student sees the value, not the MPN; the proposal still goes through."""
    ch = a.get("changes") or {}
    refs = ch.get("refs") if isinstance(ch.get("refs"), list) and ch.get("refs") else [a["line"]]
    if not re.match(r"[RCL]\d", str(refs[0]).upper()):
        return ""
    have = next((l.get("value") for l in store.bom_lines(project) if l["key"] == a["line"]), "")
    if str(ch.get("value") or have or "").strip():
        return ""
    return f' (warning: {a["line"]} has no value such as "5.1k" or "100nF"; the student sees only the MPN)'


def _renumber_by_name(part, symbol, why=None):
    """Rewrite the netlist pin numbers of a part from the symbol when every pin NAME matches the symbol's pins (case-insensitive:
    by the exact name, else by another spelling of it (RESET for RST, ~RST, and on a two-pin part K for "-"), see pinnames.py).
    A name the symbol has on several pins (USB-C: GND, VBUS, SHELL) is one electrical node: the net given to it (once, or on every
    listing of that name, all alike) is connected to every pin of that name, so the part gets one netlist pin per symbol pin. Never
    guessed: a name listed more than once with DIFFERENT nets, a name the symbol lacks, an alias that fits several pins, or one
    symbol pin claimed by two names leave the part untouched. True when done; False otherwise, and the cause goes into the list
    `why` when one is given."""
    import pinnames
    pins = part["pins"]

    def fail(msg):
        if why is not None:
            why.append(f"{part.get('ref')}: {msg}")
        return False
    wanted = [str(p.get("name") or "").strip() for p in pins]
    if not pins or not all(wanted):
        return fail("a netlist pin has no name and no number, so it cannot be matched to a pin of the library symbol")
    two = len(pins) == 2 and len(symbol["pins"]) == 2
    groups = {}
    for p, w in zip(pins, wanted):
        groups.setdefault(w.upper(), []).append(p)
    names = [lp.get("name") for lp in symbol["pins"]]
    claimed, plan = set(), []
    for key, group in groups.items():
        w = str(group[0].get("name")).strip()
        hit = [lp for lp in symbol["pins"] if str(lp.get("name") or "").strip().upper() == key]
        if not hit:
            mine = pinnames.forms_among(w, wanted, two)
            hit = [lp for lp in symbol["pins"] if mine & pinnames.forms_among(lp.get("name"), names, two)]
            if len(hit) > 1:
                return fail(f"pin name {w} fits several pins of library symbol {symbol['name']} "
                            f"({', '.join(str(h['number']) for h in hit)}): give the pin number")
        if not hit:
            return fail(f"pin name {w} is not a pin of library symbol {symbol['name']}: give the pin number")
        nets = {str(p.get("net") or "").strip().upper() for p in group}
        if len(nets) > 1:
            return fail(f"pin name {w} is listed {len(group)} times with different nets ({', '.join(sorted(nets))}), "
                        f"and library symbol {symbol['name']} has {len(hit)} pins of that name: give the pin numbers")
        if len(group) > len(hit):
            return fail(f"pin name {w} is listed {len(group)} times, but library symbol {symbol['name']} has only {len(hit)} pin(s) of that name: give the pin numbers")
        nums = [str(h["number"]) for h in hit]
        if claimed & set(nums):
            return fail(f"two pin names fit the same pin of library symbol {symbol['name']}: give the pin numbers")
        claimed |= set(nums)
        plan.append((group[0], nums))
    new_pins = []
    for p, nums in plan:
        for num in nums:
            q = dict(p)
            q["number" if "number" in q and "num" not in q else "num"] = num
            new_pins.append(q)
    pins[:] = new_pins
    return True


def netlist_symbol_errors(project, data, notes=None):
    """Errors for parts of a netlist sheet whose BOM line already has a built library symbol and whose pins do not fit it
    (a pin number the symbol lacks, a swapped pin name): the draw step's own comparison (draw.pin_nets), run at write time,
    each error listing the symbol's real number/name pairs. [] when there is no built library or no symbol for a part.
    A part whose numbers the symbol lacks but whose pin names each match one symbol pin is renumbered in data from the symbol
    (a note goes to `notes`). A symbol built for an older MPN/LCSC of the line is skipped."""
    import partlib
    from altium import draw
    spec = partlib._spec_symbols(partlib.library_dir(project) / "build" / "symbols_spec.txt")
    if not spec:
        return []
    man = store.library_manifest(project)
    lines = {r: l for l in store.bom_lines(project) for r in (l.get("refs") or [l["key"]])}
    key = {r: l["key"] for r, l in lines.items()}
    out = []
    for part in data.get("parts") or []:
        if not isinstance(part, dict) or not isinstance(part.get("pins"), list):
            continue
        entry = man.get(key.get(part.get("ref"))) or {}
        name = entry.get("symbol")
        if not name or name not in spec:
            continue
        line = lines.get(part.get("ref")) or {}
        if any(entry.get(f) and line.get(f) and str(entry[f]).strip().lower() != str(line[f]).strip().lower() for f in ("mpn", "lcsc")):
            continue                  # the part changed since the build: the symbol is stale, library.build comes first
        symbol = {"name": name, "pins": [{"number": p["num"], "name": p["name"]} for p in spec[name]["pins"]]}
        try:
            errs = draw.pin_nets(part, symbol)[2]
            cause = []
            if errs and any("has no pin in library symbol" in e or "has no pin number" in e for e in errs) \
                    and _renumber_by_name(part, symbol, cause):
                errs = draw.pin_nets(part, symbol)[2]
                if not errs and notes is not None:
                    notes.append(f"{part['ref']}: pin numbers taken from the library symbol {name} (matched by pin name)")
            elif cause:
                errs = [*cause, *errs]
        except (KeyError, TypeError, AttributeError):
            continue
        if errs:
            real = ", ".join(f"{p['number']}={p['name']}" for p in symbol["pins"])
            out.append("; ".join(errs[:3]) + f". Pins of {part['ref']} in the library symbol {name}: {real}. "
                       "Use these numbers (run library.build again if the part changed)")
    return out


def fit_sheets_to_library(project, sheet=None):
    """Before a draw: give the stored netlist sheets the pin numbers of the library symbols built since they were written
    (a part approved and built after netlist.write has pins named but not numbered, or numbered differently). Only the
    renumbering by pin name that netlist.write itself does; a sheet that changed is saved (undoable, in sheet-log.jsonl).
    Returns the refs renumbered. A part that still does not fit is left for the draw step to refuse, in its own words."""
    fitted = []
    for sid in store.sheet_ids(project):
        if sheet is not None and str(sid) != str(sheet):
            continue
        data, notes = store.load_sheet(project, sid), []
        if not data:
            continue
        try:
            netlist_symbol_errors(project, data, notes)
        except (OSError, ValueError, KeyError):
            continue
        try:                        # a sheet file that cannot be written now (open elsewhere) is no reason to stop the draw
            if notes and store.write_sheet_logged(project, sid, data, by="advisor").get("ok"):
                fitted += [n.split(":")[0] for n in notes]
        except OSError:
            pass
    return fitted


def _drawn(bridge, project, sheet, replace):
    """The draw, after the stored sheets were fitted to the library; what was renumbered is said in the result's summary."""
    fitted = fit_sheets_to_library(project, sheet)
    res = bridge.draw_schematic(project, sheet, replace=replace)
    if fitted and isinstance(res, dict):
        res["fitted"] = fitted
    return res


# what the progress line says while a slow action runs (the engine's turn is already over by then)
STEP_LABELS = {"altium.create_project": "Creating the Altium project", "altium.skeleton": "Drawing the sheet frames",
               "library.build": "Building the project library in Altium", "altium.draw_schematic": "Drawing the schematic in Altium",
               "altium.place_pcb": "Placing the parts on the board", "altium.import_rules": "Importing the JLC rules",
               "altium.route_pcb": "Routing the board", "netlist.write": "Writing the netlist", "altium.add_pcb": "Adding the PcbDoc",
               "outjob.generate": "Adding the OutJob to the project", "altium.run_outjob": "Generating the outputs in Altium",
               "altium.run_drc": "Checking the board in Altium"}


def _warn_tail(res):
    """" (N warnings: first four)" when the bridge result has warnings, else "": the same words in the chat and on the step buttons."""
    w = res.get("warnings") or []
    w = [x for x in w if str(x).startswith("placement error")] + [x for x in w if not str(x).startswith("placement error")]   # a cap too far is never cut off by the first four
    return f" ({len(w)} warnings: {'; '.join(w[:4])})" if w else ""


def draw_summary(res):
    fitted = res.get("fitted") or []
    return (f"{res['parts']} parts and {len(res['nets'])} nets drawn on {len(res['sheets'])} sheet(s), saved and checked against the netlist"
            + (f", pin numbers of {', '.join(fitted[:12])}{' ...' if len(fitted) > 12 else ''} matched by pin name to the library symbols" if fitted else "")
            + _warn_tail(res))


def place_summary(res):
    return (f"{len(res['placed'])} parts placed" + (", outline created" if res["outline_created"] else ", outline kept")
            + ", saved and checked against the netlist" + _warn_tail(res))


def route_summary(res):
    """The route's own summary, which carries Altium's DRC line with every rule and its count (not only the watched six in
    drc_after); when a summary lacks it (a result from elsewhere), the line is added here."""
    line = str(res.get("drc_line") or "")
    s = str(res["summary"])
    if line and line not in s:
        s += f"; Altium DRC, every rule: {line}"
    return s + _warn_tail(res)


def library_build_summary(project, res):
    """What library.build says it did: the same words in the chat and in a button's preparation."""
    issues = library_issue_count(project)
    return (f"{res['built']} of {res['lines']} lines built, IntLib installed" + (f" ({issues} with issues)" if issues else "")
            + "".join(" " + n for n in res.get("notices", [])))


def import_rules_summary(res):
    """What altium.import_rules says it did (chat and button preparation)."""
    return (f"{len(res['created'])} added, {len(res['updated'])} updated"
            + (f", {len(res['skipped'])} skipped ({', '.join(x['name'] for x in res['skipped'])})" if res["skipped"] else "")
            + (f", not confirmed: {', '.join(res['unconfirmed'])}" if res["unconfirmed"] else "")
            + (f". {res['message']}" if res.get("message") else ""))


def rules_warnings(res):
    """What an import_rules result says that the student must read (amber on the button's note)."""
    out = []
    if res.get("skipped"):
        out.append(f"Skipped {len(res['skipped'])}: {', '.join(x['name'] for x in res['skipped'])} ({res['skipped'][0].get('why', '')}).")
    if res.get("message"):
        out.append(res["message"])
    elif res.get("unconfirmed"):
        out.append(f"Altium did not keep: {', '.join(res['unconfirmed'])}.")
    return out


def outputs_summary(res):
    return f"Altium wrote {len(res.get('files') or [])} files" + (" (OutJob added to the project)" if res.get("added") else "")


def drc_summary(res):
    import board_results
    return board_results.drc_summary(res)


STEP_SUMMARY = {"draw": draw_summary, "place": place_summary, "route": route_summary, "rules": import_rules_summary, "outputs": outputs_summary,
                "drc": drc_summary}
NEEDS_REPLACE = re.compile(r"already has \d+ objects \(parts, wires, labels\)"                 # draw: bridge.draw_schematic / DRAWCHECK
                           r"|the board already has \d+ (?:parts or copper objects|tracks, vias or pours)")   # place / route: PCBCHECK


def needs_replace(exc):
    """True when the bridge refused only because the drawing / placement / copper is already there and replace was off. The refusal
    is a plain BridgeError (no code): this one function is the only place that knows its wording (pinned by a test)."""
    return NEEDS_REPLACE.search(str(exc)) is not None


# Altium runs one script at a time and every operation shares one exchange folder: a second operation started while a draw / place /
# route is running stops it or reads its files half written. The bridge's own lock only covers a single command batch, so whoever
# starts an operation (a step button, another Altium button, a chat turn applying its actions) holds this for all of it.
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")     # the only Host names a request may carry (DNS rebinding)
STEP_LOCK = threading.Lock()
ALTIUM_BUSY = "Altium is still working on another step; wait for it to finish and try again."
STEP_NAMES = {"draw": "Drew the schematic", "place": "Placed the parts", "route": "Routed the board",
              "rules": "Imported the JLC rules", "outputs": "Generated the outputs", "drc": "Checked the board"}


def altium_start(project):
    """A button is about to drive Altium: '' with STEP_LOCK held (the caller releases it), or why it cannot start now. The agent may
    look at Altium while it answers, and that stops a running script, so no button starts while the chat answers for this project."""
    cancel_followups(lambda k: k[0] == project)       # a correction of an earlier reply never blocks a button
    with TURNS_LOCK:              # with the checks in /api/chat under the same lock: a turn and a button operation never start together
        if any(k[0] == project for k in TURNS):
            return "The chat is still answering for this project and may be using Altium; wait for it to finish."
        return "" if STEP_LOCK.acquire(blocking=False) else ALTIUM_BUSY


# What a step button prepares by itself (design principle 4): only these three routine actions, the ones the chat runs without asking
# (they add new files or back up what they change). Drawing is not a preparation for Place, nor placing for Route: those are the student's steps.
PREP_WORDS = {"library.build": ("building the library", "The library was built", "Building the library"),
              "altium.add_pcb": ("adding a PcbDoc", "A PcbDoc was added", "Adding the PcbDoc"),
              "altium.import_rules": ("importing the JLC rules", "The JLC rules were imported", "Importing the JLC rules"),
              "outjob.generate": ("adding the OutJob", "The OutJob was added to the project", "Adding the OutJob")}
STEP_NOT_DONE = {"draw": "The schematic was not drawn.", "place": "The parts were not placed.", "route": "The board was not routed.",
                 "rules": "The rules were not imported.", "outputs": "The outputs were not generated.",
                 "drc": "The board was not checked."}
STEP_RUNS = {}                # project -> the live list of a button run (see step_plan); kept after the run until the page has the answer
RUNS_LOCK = threading.Lock()


def _and(items):
    return "".join(items) if len(items) < 2 else ", ".join(items[:-1]) + " and " + items[-1]


def step_plan(project, step):
    """The preparations a step button runs before its step, from file checks only (no Altium call). Each is planned only when the
    step cannot run without it and nothing of the student's can be touched by it:
    - library.build (draw, place) when the project has no library file yet. A library that is merely older than the BOM or the
      netlist (library_stale: true after almost every edit) is NOT rebuilt here: that takes minutes, replaces symbols under a sheet
      that is already drawn, and the step says so itself when a part is really missing from the library;
    - altium.add_pcb (place) when the Altium project lists no PcbDoc at all (one the student added by hand is theirs to link);
    - altium.import_rules (route) when the board has none of the advisor rules. A board that has some was imported before: what
      differs there is the student's edit, and the Rules page shows it and applies it on their click.
    A check that itself fails (no linked project) plans nothing: the step then gives its own error."""
    from altium import bridge
    plan = []
    if step in ("draw", "place"):
        try:
            lp = bridge.library_paths(project)
            if not lp["schlib"].is_file() or (step == "place" and not lp["pcblib"].is_file()):
                plan.append("library.build")
        except Exception:
            pass
    if step in ("place", "rules"):          # rules: the import writes into a PcbDoc, so one is added first when the project has none
        try:
            if not bridge.read_prjpcb(bridge._linked(project))["pcbs"]:
                plan.append("altium.add_pcb")
        except Exception:
            pass
    if step == "outputs":                   # ours is made and added to the project when it lists no OutJob (a visible step of the run)
        try:
            if not bridge.read_prjpcb(bridge._linked(project))["outjobs"]:
                plan.append("outjob.generate")
        except Exception:
            pass
    if step == "route":
        try:
            if bridge.rules_never_imported(project):
                plan.append("altium.import_rules")
        except Exception:
            pass
    return plan


def step_refusal(project, step):
    """Why a step must not start at all (checked at plan time, before anything runs), or "". Outputs: unverified pins block the files."""
    return button_words(store.manufacturing_warning(project)) if step == "outputs" else ""


_RUN_SEQ = itertools.count(1)


def _run_begin(project, step, keys):
    """-> the id of the new run (step_ack takes it: an answer only ever clears its own run's record)."""
    with RUNS_LOCK:
        run_id = f"{time.time():.6f}-{next(_RUN_SEQ)}"        # the counter: two runs inside one clock tick (15 ms on Windows) never share an id
        STEP_RUNS[project] = {"id": run_id, "step": step, "started": time.time(), "running": True, "stopping": False,
                              "steps": [{"key": k, "label": STEP_LABELS[k], "state": "waiting", "note": ""} for k in keys]}
    return run_id


NEEDS_LIBRARY = re.compile(r"run library\.build first")       # draw / place refusing before they change anything: a part is not in the library


def _run_insert(project, key, before):
    """A preparation that turned out to be needed only when the step looked: it joins the live list just before the step, running."""
    with RUNS_LOCK:
        steps = (STEP_RUNS.get(project) or {}).get("steps")
        if steps is not None and not any(st["key"] == key for st in steps):
            at = next((i for i, st in enumerate(steps) if st["key"] == before), len(steps))
            steps.insert(at, {"key": key, "label": STEP_LABELS[key], "state": "running", "note": ""})
            for st in steps[at + 1:]:
                st["state"] = "waiting"


def _run_mark(project, key, state, note=""):
    with RUNS_LOCK:
        for st in (STEP_RUNS.get(project) or {}).get("steps", []):
            if st["key"] == key:
                st["state"], st["note"] = state, note


def _run_end(project, **final):
    with RUNS_LOCK:
        run = STEP_RUNS.get(project)
        if run:
            for st in run["steps"]:
                if st["state"] in ("waiting", "running"):
                    st["state"] = "stopped" if final.get("stopped") else "skipped" if final.get("error") else "done"
            run.update(final, running=False, stopping=False)


class BadField(Exception):
    """A body field that must be text was something else (a list, a number, an object): the answer is 400, not a dropped connection."""


def _text_field(data, key, default=""):
    """The one place a name / project / text is read from a request body: a string (or absent -> default), stripped.
    A list or number is refused with BadField instead of being turned into "['a']" or crashing on .strip()."""
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise BadField(f"\"{key}\" must be text")
    return value.strip()


class StepStopped(Exception):
    """The student pressed Stop. Raised only between steps, never inside one: a step in Altium runs to its end, so no file is left
    half written (each bridge operation is one batch of commands that saves and checks its file before it reports)."""


def step_stop(project):
    """The Stop button of a button run: True when a running run was told to end before its next step, False when none is running."""
    with RUNS_LOCK:
        run = STEP_RUNS.get(project)
        if run and run.get("running"):
            run["stopping"] = True
            return True
    return False


def _stop_check(project):
    with RUNS_LOCK:
        if (STEP_RUNS.get(project) or {}).get("stopping"):
            raise StepStopped()


def _stopped_body(project, done):
    """The answer of a stopped run: what ran last, and that nothing after it did."""
    with RUNS_LOCK:
        ran = [st["label"] for st in (STEP_RUNS.get(project) or {}).get("steps", []) if st["state"] == "done"]
    msg = f"Stopped after {ran[-1]}; nothing after it ran." if ran else "Stopped before the first step; nothing ran."
    body = {"stopped": True, "message": msg, "warnings": []}
    if done:
        body["prepared"] = [f"{k}: {t}" if t else k for k, t in done]
    return body


def step_status(project, take=False):
    """The live state of the last button run, or {"running": False}. A finished run is kept until the next run replaces it, or until
    it is read with take (the page that was reloaded mid-run reads it once) or its own POST answer was delivered (step_ack): a result
    is never shown twice and never outlives the next run."""
    with RUNS_LOCK:
        run = STEP_RUNS.get(project)
        if not run:
            return {"running": False}
        out = json.loads(json.dumps(run))
        if take and not run["running"]:
            STEP_RUNS.pop(project, None)
        return out


def step_ack(project, run_id):
    """The answer of the button's POST reached the page: that run's finished record is not needed any more."""
    with RUNS_LOCK:
        run = STEP_RUNS.get(project)
        if run and run_id and run.get("id") == run_id and not run["running"]:
            STEP_RUNS.pop(project, None)


def _step_note(project, sess, step, done, summary=None, failure=""):
    """The note the agent reads next turn. `done` = [(kind, sentence)] of the preparations that ran; they changed the project, so they are
    noted even when the step itself failed. Nothing is written when nothing ran and nothing succeeded."""
    if not done and summary is None:
        return
    try:
        applied = [f"{k}: {t}" if t else k for k, t in done]
        names = _and([PREP_WORDS[k][0] for k, _ in done])
        if summary is not None:
            applied.append(f"{_CONSENT_ACTION[step]}: {summary}")
            text = f"{STEP_NAMES[step]} in Altium{' after ' + names if done else ''} because the student pressed the button: {summary}"
        else:
            text = f"The student pressed the {step} button. Altium did {names} first; {failure}"
        if step == "rules" and any(k == "altium.add_pcb" for k, _ in done):
            text += " The PcbDoc did not exist: an empty one was added for the rules, so the parts are not placed yet."
        note = {"ts": now(), "role": "agent", "by": "button", "applied": applied, "text": text}
        if warned_map(applied):       # the chip in the chat is amber, as for the same result from a chat turn
            note["warned"] = warned_map(applied)
        say(project, sess, note)
    except Exception as exc:      # Altium did the work: a note that could not be written must not turn that into a failure
        print(f"(the note about the {step} button step was not written: {exc})")


# Altium's refusals are written for the agent (action names, "ask the student"); the button page shows them to the student
BUTTON_WORDS = [
    (r"write the netlist first \(netlist\.write\)", "ask the agent in the chat to write the schematic first"),
    (r"run library\.build (first|again)", r"build the library \1: Library page, Build library"),
    (r"draw it first \(altium\.draw_schematic, with the student's agreement\)", "draw it first (Schematic, Draw in Altium)"),
    (r"place the parts first \(altium\.place_pcb\)", "place the parts first (Layout, Place parts)"),
    (r"Import the JLC rules first \(altium\.import_rules\)", "Import the JLC rules first (Rules, Apply rules in Altium)"),
    (r"Ask the student whether it is the real board outline\.", "Tell the agent in the chat whether it is the real board outline."),
    (r"Ask the student for the board width and height in mm \(do not guess\), record it with idea\.update, or draw the outline "
     r"in Altium first\.", "Tell the agent in the chat the board width and height in mm, or draw the outline in Altium first."),
    (r" \(altium\.install_path\)", ""),
]


def button_words(text, built=False):
    """A refusal as the student reads it on a step button's page; the chat note keeps the agent's wording. built: the button
    already rebuilt the library in this run, so building again would not help: the part's own library line is the place to look."""
    if built:
        text = re.sub(r"run library\.build (first|again)", "the library was just built without it: open the part on the Library page", text)
    for pat, rep in BUTTON_WORDS:
        text = re.sub(pat, rep, text)
    return text


def _step_failed(project, sess, step, done, current, exc, unexpected):
    """(status, body) for a step or preparation that stopped; the later steps do not run. needs_replace only for the step's own refusal."""
    final = current == _CONSENT_ACTION[step]
    prepared = [f"{k}: {t}" if t else k for k, t in done]
    reason = (f"it stopped on an unexpected error ({type(exc).__name__}: {exc}). Look at the file in Altium before trying again; whatever "
              "it changed was copied to .advisor-backup first" if unexpected else str(exc)).rstrip(". ")
    if final:
        err = (f"The step stopped on an unexpected error ({type(exc).__name__}: {exc}). Look at the file in Altium before "
               "trying again; whatever it changed was copied to .advisor-backup first.") if unexpected else str(exc)
    else:
        before = f"{_and([PREP_WORDS[k][1] for k, _ in done])}. " if done else ""
        err = f"{before}{PREP_WORDS[current][2]} failed: {reason}. {STEP_NOT_DONE[step]}"
    body = {"error": button_words(err, built=any(k == "library.build" for k, _ in done))}
    if prepared:
        body["prepared"] = prepared
    if final and done:
        body["done_first"] = f"{_and([PREP_WORDS[k][1] for k, _ in done])}."       # the page puts it before the step's own error
    if final and not unexpected and step == "route" and getattr(exc, "open_nets", None):
        body["partial_offer"] = list(exc.open_nets)       # nets the router could not do: the page offers a partial route (the click is the consent)
    if final and not unexpected and needs_replace(exc):
        body["needs_replace"] = True       # the caller drops it when replace was on
    _run_mark(project, current, "failed", reason)
    _step_note(project, sess, step, done, failure=("the step itself then stopped: " if final else f"then {PREP_WORDS[current][0]} stopped: ") + reason + ".")
    return (500 if unexpected else 400), body


def run_step_button(project, sess, step, data):
    """The Draw / Place / Route buttons: the click is the consent, so no wording check. Runs by itself what the step needs first
    (step_plan), all under one hold of STEP_LOCK. Returns (status, body, run id for step_ack)."""
    from altium import bridge
    data = data if isinstance(data, dict) else {}       # a body that is not an object asks for nothing special
    busy = altium_start(project)
    if busy:
        return 409, {"error": busy}, ""
    t0 = time.time()
    runlog.event("op", op=f"step.{step}", phase="begin", project=project)
    runlog.usage(project, "step", op=step, phase="begin", ok=True)
    try:
        try:
            with runlog.for_project(project):
                code, body = _run_step(project, sess, step, data, bridge)
        except Exception as exc:      # after the step itself (its result could not be put into words): still an answer, and the page reads the files again
            code, body = 500, {"error": f"Altium ran the step but its result could not be read ({type(exc).__name__}: {exc}). Look at the file in Altium before trying again."}
            _run_end(project, **body)
            runlog.exception("exception", exc, where=f"step.{step}", project=project)
        _log_step_end(project, step, code, body, t0)
        _record_board(project, step, body if code == 200 and not body.get("stopped") else None, code, body)
        return code, body, _run_id(project)
    finally:
        with RUNS_LOCK:               # whatever happened above, no record is left saying "running" once the lock is free
            run = STEP_RUNS.get(project)
            if run and run.get("running"):
                run.update(running=False, error="The step stopped without an answer; look at the file in Altium and at the chat before trying again.")
        STEP_LOCK.release()


def _record_board(project, step, res, code=200, body=None):
    """The one place a step's answer from Altium goes into board-log.jsonl (button steps and the chat's altium.* actions): res is the
    bridge result of a step that ran, None for one that stopped or failed (then an error record, unless it only refused)."""
    try:
        import board_results
        if res is not None:
            board_results.record(project, step, res)
        elif isinstance(body, dict) and body.get("error") and not body.get("needs_replace") and code >= 400 and step in ("place", "route", "drc", "outputs") and code != 409:
            board_results.record(project, step, {}, ok=False, error=body["error"])
    except Exception:           # noqa: BLE001 - the log never turns a done step into a failure
        pass


def _log_step_end(project, step, code, body, t0):
    """The end record of a step button: the steps that ran (preparations included), seconds, the summary or the full error."""
    try:
        with RUNS_LOCK:
            steps = [{"step": s["key"], "state": s["state"]} for s in (STEP_RUNS.get(project) or {}).get("steps", [])]
        runlog.event("op", op=f"step.{step}", phase="end", project=project, ok=code == 200 and not body.get("stopped"), stopped=bool(body.get("stopped")), status=code, steps=steps,
                     seconds=round(time.time() - t0, 1), summary=body.get("summary", ""), error=body.get("error", ""),
                     warnings=body.get("warnings") or [])
        with RUNS_LOCK:         # the usage log keeps what the person was shown: each step's note, then the summary or the refusal
            shown = [{"step": s["key"], "state": s["state"], "note": s.get("note", "")} for s in (STEP_RUNS.get(project) or {}).get("steps", [])]
        runlog.usage(project, "step", op=step, phase="end", ok=code == 200 and not body.get("stopped"), stopped=bool(body.get("stopped")), seconds=round(time.time() - t0, 1), steps=shown,
                     shown=body.get("summary") or body.get("error") or "", warnings=body.get("warnings") or [])
    except Exception:
        pass


def _run_id(project):
    with RUNS_LOCK:
        return (STEP_RUNS.get(project) or {}).get("id", "")


def _prep_said(project, kind, res):
    """The sentence for a preparation that ran. Never raises: the preparation worked, a sentence that cannot be made is no failure."""
    try:
        return library_build_summary(project, res) if kind == "library.build" else import_rules_summary(res) if kind == "altium.import_rules" else ""
    except Exception:
        return ""


def _run_step(project, sess, step, data, bridge):
    final, done, current = _CONSENT_ACTION[step], [], _CONSENT_ACTION[step]
    replace = _truthy(data.get("replace"))        # for the step itself: a preparation never replaces anything
    why = step_refusal(project, step)         # a refusal at plan time: nothing runs, and it is an answer, not a crash
    if why:
        _run_begin(project, step, [final])
        body = {"error": why}
        _run_mark(project, final, "failed", why)
        _run_end(project, **body)
        return 400, body
    plan = step_plan(project, step)
    _run_begin(project, step, [*plan, final])
    try:
        for current in plan:
            _stop_check(project)              # Stop is read between steps only: a step in Altium is never cut in the middle
            _run_mark(project, current, "running")
            if current == "library.build":
                res = bridge.build_library(project)
            elif current == "altium.add_pcb":
                res = bridge.add_pcb(project)
            elif current == "outjob.generate":
                res = bridge.add_outjob(project)
            else:
                res = bridge.import_rules(project)
            said = _prep_said(project, current, res)
            done.append((current, said))
            _run_mark(project, current, "done", said or pathlib.Path(str((res or {}).get("file") or "")).name)
        def the_step():
            if step == "draw":
                return _drawn(bridge, project, data.get("sheet") or None, replace)
            if step == "place":
                return bridge.place_pcb(project, replace=replace)
            if step == "rules":
                return bridge.import_rules(project)
            if step == "outputs":
                return bridge.run_outjob(project)
            if step == "drc":
                import board_results
                return board_results.run_drc(project, bridge)
            # keep_partial only from the "Route the rest and leave X open" button (its click is the consent; the agent's chat path asks for words instead)
            return bridge.route_pcb(project, replace=replace, keep_partial=_truthy(data.get("keep_partial")))
        current = final
        _stop_check(project)
        _run_mark(project, final, "running")
        try:
            res = the_step()
        except bridge.BridgeError as exc:
            # the library exists but lacks a part of this sheet (a line approved after the last build): the step says so before it
            # touches anything. That is the one case where a rebuild is needed, so build and try the step once more
            if not NEEDS_LIBRARY.search(str(exc)) or any(k == "library.build" for k, _ in done):
                raise
            current = "library.build"
            _run_insert(project, current, final)
            res = bridge.build_library(project)
            said = _prep_said(project, current, res)
            done.append((current, said))
            _run_mark(project, current, "done", said)
            current = final
            _stop_check(project)
            _run_mark(project, final, "running")
            res = the_step()
    except StepStopped:           # nothing is running in Altium now; what ran before stays done and is told to the agent
        body = _stopped_body(project, done)
        _step_note(project, sess, step, done, failure=f"then the student pressed Stop: {body['message']}")
        _run_end(project, **body)
        return 200, body
    except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
        code, body = _step_failed(project, sess, step, done, current, exc, False)
        if body.get("needs_replace") and replace:
            del body["needs_replace"]
        _run_end(project, **body)
        return code, body
    except Exception as exc:      # a bug in the planning code is an answer too, not a dropped connection; the page reads the files again
        code, body = _step_failed(project, sess, step, done, current, exc, True)
        _run_end(project, **body)
        return code, body
    if step == "outputs" and any(k == "outjob.generate" for k, _ in done):
        res = {**res, "added": True}          # the same answer as when the bridge adds the OutJob itself
    summary = STEP_SUMMARY[step](res)
    # the agent reads this conversation on its next turn: a note there says the step is done, so it does not offer it again.
    # "applied" makes it an applied action like the chat's: consent given in words before it is used up (earlier_student_messages)
    _step_note(project, sess, step, done, summary=summary)
    body = {**res, "summary": summary, "warnings": list(res.get("warnings") or []) + (rules_warnings(res) if step == "rules" else [])}
    if done:
        body["prepared"] = [f"{k}: {t}" if t else k for k, t in done]
    _run_end(project, summary=summary, warnings=body["warnings"], **({"prepared": body["prepared"]} if done else {}))
    return 200, body


def _uses_altium(kind):
    return isinstance(kind, str) and (kind.startswith("altium.") or kind == "library.build")


def apply_actions(project, actions, sess=None, last_user="", meta=None, turn_start=None, on_step=None, cancel=None, chat=None, allow_auto=True):
    """The server is the only writer: see _apply_actions. A turn whose actions drive Altium holds STEP_LOCK while they run; when
    something else holds it, those actions are refused and the rest still applies."""
    wants = any(_uses_altium(a.get("type")) for a in actions or [] if isinstance(a, dict))
    held = wants and STEP_LOCK.acquire(blocking=False)
    try:
        with runlog.for_project(project):
            return _apply_actions_held(project, actions, sess, last_user, meta, turn_start, on_step, cancel, chat, held, allow_auto)
    finally:
        if held:
            STEP_LOCK.release()


def _apply_actions_held(project, actions, sess, last_user, meta, turn_start, on_step, cancel, chat, held, allow_auto):
    if not held:
        return _apply_actions(project, actions, sess, last_user, meta, turn_start, on_step, cancel, chat, altium_free=held, allow_auto=allow_auto)
    kinds = [a.get("type") for a in actions if isinstance(a, dict) and _uses_altium(a.get("type"))]
    with runlog.span("chat.altium-actions", project=project, actions=kinds):
        res = _apply_actions(project, actions, sess, last_user, meta, turn_start, on_step, cancel, chat, altium_free=held, allow_auto=allow_auto)
        runlog.event("op", op="chat.altium-actions", phase="result", project=project, refused=res[2])
        return res


def _apply_actions(project, actions, sess=None, last_user="", meta=None, turn_start=None, on_step=None, cancel=None, chat=None, altium_free=True, allow_auto=True):
    """The server is the only writer. Agents propose; this applies.
    Returns (applied, proposal_ids, refused). Proposals the autonomy setting lets through are
    approved here, by "auto", right after they are recorded (so later actions in the same turn see them)."""
    applied, proposals, refused = [], [], []
    auto_done = []
    # refs this turn names, so a line that gets extra refs for its qty does not take one a later line uses
    reserved = {r for a in actions or [] if isinstance(a, dict) and a.get("type") == "bom.propose"
                for r in [a.get("line"), *(((a.get("changes") or {}).get("refs") or []) if isinstance(a.get("changes"), dict) else [])]
                if isinstance(r, str)}

    def maybe_auto(rec):
        if not allow_auto or not store.may_auto_apply(rec):       # allow_auto=False (the follow-up turn): a proposal always waits for the student
            return
        try:
            decide_and_note(project, sess, rec["id"], "approved", by="auto", note=False, redraw_now=False)
            auto_done.append(rec)
        except (ValueError, KeyError) as exc:
            refused.append(f"auto-apply of {rec['id']} failed, it waits for you: {exc}")

    for a in actions or []:             # in the listed order: library.build, then netlist.write, then altium.draw_schematic
        if not isinstance(a, dict):
            continue
        kind = a.get("type")
        if cancel is not None and cancel.is_set():      # Stop: what has not started does not run (a running Altium step is not interrupted)
            refused.append(f"{kind}: stopped by the student before it ran")
            continue
        if _uses_altium(kind) and not altium_free:
            refused.append(f"{kind}: not run. Another step is still running in Altium (started with a button); try again when it has finished")
            continue                                # two Altium operations at once would write the same files
        if on_step and kind in STEP_LABELS:        # the slow steps show in the chat's progress line
            on_step(STEP_LABELS[kind])
        try:
            if kind == "idea.propose" and a.get("topic") and a.get("text"):
                store.propose_idea(project, a["topic"], a["text"], by="agent")
                applied.append(f"idea.propose:{a['topic']}")
            elif kind == "idea.describe" and isinstance(a.get("text"), str):
                store.set_idea_goal(project, a["text"], by="agent")
                applied.append("idea.describe")
            elif kind == "idea.confirm":
                # only after the student said yes: the quote must be in what they just wrote
                if _quote_holds(a.get("student_said"), last_user):
                    if store.load_idea_working(project).get("agreed"):
                        store.confirm_idea(project)
                        applied.append("idea.confirm")
                    else:
                        applied.append("idea.ready")
                else:
                    # no quote that holds up: not an error, the reply just offers the Confirm idea button
                    applied.append("idea.ready")
            elif kind == "idea.ready":
                applied.append("idea.ready")
            elif kind == "bom.propose" and a.get("line") and isinstance(a.get("changes"), dict):
                rec = store.propose_bom(project, a["line"], a["changes"], a.get("reason", ""),
                                        a.get("sources", []), _agent_may_set_library(a.get("library")) or None,
                                        sess, new=bool(a.get("new")), reserved=reserved)
                proposals.append(rec["id"])
                applied.append(f"bom.propose:{a['line']}" + bom_value_warning(project, a))
                maybe_auto(rec)
            elif kind == "net.set_current" and a.get("net"):      # a proposal like a BOM change: the student's click in ask / important mode
                if "amps" not in a:             # a missing amount is a mistake; clearing needs an explicit "amps": null
                    refused.append("net.set_current: amps is missing (use \"amps\": null to clear the current)")
                    continue
                try:
                    rec = store.propose_net_current(project, a["net"], a["amps"], a.get("reason", ""), a.get("sources", []), sess)
                except ValueError as exc:
                    refused.append(f"net.set_current: {exc}")
                    continue
                proposals.append(rec["id"])
                applied.append(f"net.set_current:{a['net']}")
                maybe_auto(rec)
            elif kind == "idea.diagram" and isinstance(a.get("changes"), dict):
                rec = store.propose_idea_diagram(project, a["changes"], a.get("reason", "Diagram update proposed"),
                                                sources=a.get("sources", []), session=sess)
                proposals.append(rec["id"])
                applied.append("idea.diagram")
                maybe_auto(rec)
            elif kind == "idea.diagram.edit":
                ops = a.get("ops")
                if not isinstance(ops, list):
                    raise ValueError("ops list required")
                res = store.apply_diagram_edit(project, ops)
                applied.append("idea.diagram.edit")
                if meta is not None and isinstance(res, dict) and res.get("touched"):
                    meta.setdefault("diagram_touched", []).extend(res["touched"])
            elif kind == "netlist.write" and a.get("sheet") and isinstance(a.get("data"), dict):
                notes = []
                data, held = a["data"], []
                if _consent_base("nc", a, consent_words(chat, last_user)):
                    # NC on an open / unlisted pin of the netlist as it stands clears the manufacturing gate: only the student's own
                    # words do that directly; otherwise those marks wait as one proposal (one click), the rest of the sheet is written
                    data, held = store.hold_nc_marks(project, a["sheet"], data)
                sym_errors = netlist_symbol_errors(project, data, notes)
                res = {"ok": False, "errors": sym_errors} if sym_errors else store.write_sheet_logged(project, a["sheet"], data)
                if res["ok"] and held:
                    store.propose_nc(project, held)
                    notes.append(f"{len(held)} {'pin' if len(held) == 1 else 'pins'} left open: the NC marks wait as one proposal for the student to approve "
                                 f"with one click ({', '.join(i['ref'] + ' pin ' + (i['num'] or i['name']) for i in held[:10])}{' ...' if len(held) > 10 else ''})")
                if res["ok"]:
                    # pin numbers filled from the library symbol are how it is meant to work, not a warning: one short remark, no amber chip
                    filled = [n.split(":")[0] for n in notes if "matched by pin name" in n]
                    warns = [*(n for n in notes if "matched by pin name" not in n), *(res.get("warnings") or [])]
                    note = (f", pin numbers of {', '.join(filled[:12])}{' ...' if len(filled) > 12 else ''} matched by pin name to the library symbols" if filled else "") + (f" (warnings: {'; '.join(warns[:8])})" if warns else "")
                    applied.append(f"netlist.write:{res['sheet']}{note}")
                else:
                    refused.append(f"netlist.write:{a['sheet']} refused: " + "; ".join(res["errors"][:8]))
            elif kind in ("netlist.remove", "netlist.rename") and a.get("sheet"):
                why = _sheet_edit_consent(kind, a, last_user)
                if why:
                    refused.append(f"{kind}:{a['sheet']} refused: {why}")
                else:
                    if kind == "netlist.remove":
                        res = store.remove_sheet_logged(project, a["sheet"])
                    else:
                        res = store.rename_sheet_logged(project, a["sheet"], a.get("to") or "")
                    if res["ok"]:
                        applied.append(f"{kind}:{a['sheet']}" + (f" -> {res['sheet']}" if kind == "netlist.rename" else "")
                                       + " (the SchDoc in Altium is not touched: remove or keep it there)")
                    else:
                        refused.append(f"{kind}:{a['sheet']} refused: " + "; ".join(res["errors"][:4]))
            elif kind == "library.add" and a.get("line"):
                if a["line"] not in {l["key"] for l in store.bom_lines(project)}:
                    refused.append(f"library.add: no BOM line {a['line']}")
                else:
                    store.add_library(project, a["line"], _agent_may_set_library(a.get("changes")))
                    applied.append(f"library.add:{a['line']}")
            elif kind == "library.build":
                # routine: the build backs up the library files and restores them when it fails
                from altium import bridge
                try:
                    res = bridge.build_library(project)
                except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
                    refused.append(f"{kind}: {exc}")
                    continue
                applied.append(f"{kind}: " + library_build_summary(project, res))
            elif kind == "part.attach_datasheet" and a.get("ref") and a.get("name"):
                # routine: applies at once; detach (the Unverified panel, /api/parts/detach_datasheet) is the undo
                res = store.attach_datasheet(project, a["ref"], a["name"], by="agent")
                applied.append(f"part.attach_datasheet:{a['ref']} <- {res['name']}: {res['status']}"
                               + (f" ({res['issues']})" if res["issues"] else ""))
            elif kind == "thread.open" and a.get("anchor"):
                if open_part_session(project, a["anchor"]):
                    applied.append(f"thread.open:{a['anchor']}")
                else:
                    refused.append(f"thread.open: nothing to anchor to at {a['anchor']}")
            elif kind == "altium.draw_schematic":
                # the agent draws the sheet in Altium only when the student said so, in their own words (asked first: draw it
                # yourself or should I?). replace needs that too, and never happens by default: a drawing is never wiped.
                from altium import bridge
                why = _draw_consent(a, consent_words(chat, last_user), earlier_student_messages(chat, "draw", last_user), previous_agent_text(chat, last_user))
                if why:
                    refused.append(f"{kind}: not run. {why}")
                    continue
                try:
                    res = _drawn(bridge, project, a.get("sheet") or None, _truthy(a.get("replace")))
                except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
                    refused.append(f"{kind}: {exc}")
                    continue
                applied.append(f"{kind}: " + draw_summary(res))
            elif kind in ("altium.place_pcb", "altium.route_pcb"):
                # the agent places / routes the board in Altium only when the student said so in their own words, separately for
                # each (asked first: do it yourself or should I?). replace needs that too and never happens by default.
                from altium import bridge
                step = "place" if kind == "altium.place_pcb" else "route"
                why = _consent(step, a, consent_words(chat, last_user), earlier_student_messages(chat, step, last_user), previous_agent_text(chat, last_user))
                if why:
                    refused.append(f"{kind}: not run. {why}")
                    continue
                try:
                    if step == "place":
                        res = bridge.place_pcb(project, replace=_truthy(a.get("replace")))
                    else:
                        keep = _partial_consent(a, consent_words(chat, last_user))
                        res = bridge.route_pcb(project, replace=_truthy(a.get("replace")), keep_partial=keep)
                except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
                    refused.append(f"{kind}: {exc}")
                    continue
                _record_board(project, step, res)
                applied.append(f"{kind}: " + STEP_SUMMARY[step](res))
            elif kind in ALTIUM_ACTIONS:
                from altium import bridge
                # routine: new files only, and whatever it modifies is copied to .advisor-backup first
                if kind == "altium.create_project":
                    res = bridge.create(project)
                    if res.get("skeleton_error"):
                        applied.append(kind)
                        refused.append(f"altium.skeleton: {res['skeleton_error']}")
                        continue
                elif kind == "altium.add_sheet":
                    bridge.add_sheet(project, str(a.get("name") or ""))
                elif kind == "altium.skeleton":
                    bridge.skeleton(project, a.get("sheet"))
                elif kind == "altium.add_pcb":
                    bridge.add_pcb(project)
                elif kind == "altium.import_rules":
                    # the PcbDoc is copied to .advisor-backup first; the student's own rules are never deleted
                    done = _bridge_done(project, "import-rules", turn_start)
                    if done:
                        applied.append(f"{kind}: already done earlier in this turn ({len(done.get('created', []))} added, "
                                       f"{len(done.get('updated', []))} updated)")
                        continue
                    try:
                        res = bridge.import_rules(project)
                    except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                        refused.append(f"{kind}: {exc}")
                        continue
                    applied.append(f"{kind}: " + import_rules_summary(res))
                    continue
                elif kind == "altium.run_outjob":
                    unv = store.manufacturing_warning(project)     # unverified pins block the files
                    if unv:
                        refused.append(f"{kind}: {unv}")
                        continue
                    done = _bridge_done(project, "run-outjob", turn_start)
                    if done:
                        applied.append(f"{kind}: already done earlier in this turn ({done.get('files', 0)} files)")
                        continue
                    try:
                        res = bridge.run_outjob(project)
                    except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                        refused.append(f"{kind}: {exc}")
                        continue
                    _record_board(project, "outputs", res)
                    applied.append(f"{kind}: {len(res['files'])} files" + (" (OutJob added to the project)" if res["added"] else "")
                                   + "".join(f". WARNING: {w}" for w in res.get("warnings", [])))
                    continue
                else:
                    bridge.open_project(project)
                applied.append(kind + (f":{a['name']}" if kind == "altium.add_sheet" else ""))
            elif kind == "jlc.gerber_zip":
                import jlc_upload
                unv = store.manufacturing_warning(project)         # unverified pins block the zip
                try:
                    if unv:
                        refused.append(f"jlc.gerber_zip: {unv}")
                        continue
                    res = jlc_upload.gerber_zip(project)
                except jlc_upload.UploadError as exc:
                    refused.append(f"jlc.gerber_zip: {exc}")
                else:
                    gaps = [m["layer"] for m in res["missing"] if m["level"] == "problem"]
                    applied.append(f"jlc.gerber_zip:{res['zip']} ({len(res['files'])} files" + (f", missing {', '.join(gaps)}" if gaps else "") + ")"
                                   + "".join(f" {m['layer']}: {m['why']}" for m in res["missing"]
                                             if m["level"] == "problem" and m["why"].startswith("The outline layer"))
                                   + "".join(f". WARNING: {w}" for w in res.get("warnings", [])[:4]))
            elif kind == "order.check":
                import order_check
                try:
                    applied.append("order.check: " + order_check.summary(order_check.order_check(project, recheck=_truthy(a.get("recheck")))))
                except Exception as exc:        # a supplier being down must not stop the turn
                    refused.append(f"order.check: {exc}")
            elif kind == "jlc.pickup":
                import jlc_upload
                res = jlc_upload.pickup(project, kind=a.get("kind") or None, name=a.get("name") or None)
                for f in res["found"]:
                    applied.append(f"jlc.pickup:{f['stem']} ({f['kind']})")
                for f in res["pending"]:
                    refused.append(f"jlc.pickup: {f['name']} is not added yet; say pcb, smt or both with kind")
                if not (res["found"] or res["pending"]):
                    refused.append(f"jlc.pickup: no new JLCDFM report in {res['folder']}")
            elif kind == "dfm.triage" and a.get("stem") and isinstance(a.get("rows"), list):
                import dfm
                try:
                    res = dfm.merge_triage(project, a["stem"], a["rows"])
                except FileNotFoundError:
                    refused.append(f"dfm.triage: no report {a['stem']} in this project")
                else:
                    applied.append(f"dfm.triage:{a['stem']} ({res['added']} added, {res['updated']} updated)")
            else:
                res = ext.dispatch_action(project, a, {"sess": sess, "last_user": last_user, "meta": meta, "allow_auto": allow_auto})
                if res is None:
                    refused.append(f"{kind}: not a known action, or fields missing")
                elif isinstance(res, tuple):
                    applied.extend(res[0])
                    refused.extend(res[1])
                else:
                    applied.append(res)
        except StepStopped:
            raise
        except (ValueError, KeyError) as exc:
            refused.append(f"{kind}: {exc}")
        except Exception as exc:        # noqa: BLE001 - one action's bug must not lose the other actions of the turn
            runlog.event("op", op="chat.action", phase="error", project=project, action=str(kind), error=f"{type(exc).__name__}: {exc}")
            refused.append(f"{kind}: could not be applied ({type(exc).__name__}: {exc}). The other actions of this turn were not affected")
    if any(x.startswith("netlist") for x in applied) or any(r.get("kind") != "idea_diagram" for r in auto_done):
        redraw(project)
    if auto_done and sess:
        say(project, sess, {"ts": now(), "role": "agent", "decision": "approved", "proposal": auto_done[0]["id"],
                            "text": f"Applied without asking ({store.autonomy()} mode, the student can undo): "
                                    + ", ".join(r["id"] for r in auto_done)})
    return applied, proposals, refused


FOLLOWUP_WAIT = ("Results of your actions: {applied}; refused: {refused}; warnings: {warned}. Correct anything in your previous "
                 "reply that claimed otherwise, in one or two short sentences, and do not repeat actions that need the student's approval. "
                 "This is a text-only reply: no actions will run")
# refusals / warnings whose action the agent's text probably reported as done; value-only warnings, stops, a busy Altium and the
# guards' notes are not worth a second turn
_FU_REFUSED = re.compile(r"^(netlist\.write|altium\.|library\.|jlc\.|order\.check|bom\.(?!check)|the reply's actions block)")
_FU_WARNED = re.compile(r"^(netlist\.write|altium\.|library\.|jlc\.|order\.check)")
_FU_SKIP = ("stopped by the student", "Another step is still running")


FOLLOWUP_SPLIT = ("These commands were denied because each joined several actions: {cmds}. Run every part again as its own plain "
                  "command, one per tool call (no cd, &&, ;, pipe, 2>&1), then answer the student's question from the results, "
                  "briefly. Do not tell the student to allow anything")
FOLLOWUP_TOOLS = ". You may run scripts with tool calls in this reply, one plain command per call; only the ```json actions block is ignored"
_QUOTED = re.compile(r'"(?:[^"`]|`.)*"|' + r"'[^']*'")
_SCRIPT_IN_CMD = re.compile(r"scripts[/\\](?:[\w.-]+[/\\])*([\w.-]+\.py)")


def _outside_quotes(cmd):
    return _QUOTED.sub(" ", cmd)


def _norm_run(text):
    return " ".join(str(text).replace('"', " ").replace("'", " ").split())


def _command_parts(cmd):
    """The `script.py args` of each scripted part of a (compound) command, split on shell operators outside quotes."""
    masked = _QUOTED.sub(lambda m: "x" * len(m.group(0)), cmd)
    cuts, last, out = [], 0, []
    for m in re.finditer(r"&&|\|\||[;|&\n]", masked):
        cuts.append((last, m.start()))
        last = m.end()
    cuts.append((last, len(cmd)))
    for lo, hi in cuts:
        m = _SCRIPT_IN_CMD.search(cmd[lo:hi])
        if m:
            out.append(_norm_run(m.group(1).split("/")[-1].split("\\")[-1] + " " + cmd[lo:hi][m.end():]))
    return out


def _recovered(cmd, tools):
    """True when the same turn later ran every scripted part of the denied command (script and arguments) successfully."""
    parts = _command_parts(cmd)
    ok = [_norm_run(str(t.get("t") or "")[len("Running "):] if str(t.get("t") or "").startswith("Running ") else str(t.get("t") or ""))
          for t in tools or [] if isinstance(t, dict) and t.get("st") == "ok"]
    return bool(parts) and all(any(c == p or (c.endswith("…") and p.startswith(c[:-1])) for c in ok) for p in parts)


def compound_denials(denied, tools=None):
    """The commands the engine refused because they joined several actions (flagged by the engine, or shell operators OUTSIDE quotes in a
    Bash/PowerShell command), minus those whose scripts the same turn ran successfully afterwards."""
    out = []
    for d in denied or []:
        if not isinstance(d, dict):
            continue
        cmd = str((d.get("input") or {}).get("command") or "").strip()
        if (d.get("compound") or (d.get("tool") in ("Bash", "PowerShell")
                                  and any(op in _outside_quotes(cmd) for op in SHELL_OPS))) and not _recovered(cmd, tools):
            out.append(cmd or str(d.get("tool") or "a command"))
    return out


def followup_message(applied, refused, warned, denied=None, tools=None):
    """The server's message to the agent after a turn whose actions were refused or came back with warnings: what really happened.
    A combined command that was denied adds the retry hint: the agent splits it itself, the student does nothing."""
    j = lambda xs: "; ".join(str(x) for x in xs) or "none"
    split = compound_denials(denied, tools)
    if split and not (applied or refused or warned):
        return FOLLOWUP_SPLIT.format(cmds=j(c[:200] for c in split)) + FOLLOWUP_TOOLS
    msg = FOLLOWUP_WAIT.format(applied=j(applied), refused=j(refused), warned=j(f"{k}: {v}" for k, v in (warned or {}).items()))
    if split:
        msg = msg.replace("This is a text-only reply: no actions will run", "Only the ```json actions block is ignored in this reply")
    return msg + ("\n" + FOLLOWUP_SPLIT.format(cmds=j(c[:200] for c in split)) + FOLLOWUP_TOOLS if split else "")


def followup_worthy(applied, refused, denied=None, tools=None):
    """True when a refusal or warning is of a kind whose action the reply may have claimed as done, or a combined command was denied."""
    if compound_denials(denied, tools):
        return True
    for r in refused:
        r = str(r)
        if not any(x in r for x in _FU_SKIP) and _FU_REFUSED.match(r):
            return True
    return any(_FU_WARNED.match(a) for a in warned_map(applied))


def followup_expected(rec, applied, refused, cancelled):
    """The conditions for a follow-up turn, apart from a busy server."""
    return not (cancelled or rec.get("error") or rec.get("partial")
                or not followup_worthy(applied, refused, rec.get("denied"), rec.get("tools"))
                or not workspace.get("chat.followup_on_refusal", True))


def start_followup(proj, sess, tkey, user_text, orig_rec, applied, refused, cancelled):
    """After the reply is stored: ONE more agent turn, TEXT ONLY (its actions are dropped), when a worthwhile action was refused or came
    back with a warning (the reply's text often says "done" before the server's answer is known). True when it started; it runs in
    its own thread and the page shows it from /api/state. Not started: setting off, Stop in between, a failed first turn. It never
    chains, and a new student message or a step button cancels it."""
    if not followup_expected(orig_rec, applied, refused, cancelled):
        return False
    with TURNS_LOCK:          # atomic with a new student message: whoever registers first wins
        if tkey in TURNS or STEP_LOCK.locked():
            return False
        fturn = TURNS[tkey] = _new_turn()
        fturn["followup"] = True
    threading.Thread(target=_run_followup, args=(proj, sess, tkey, fturn, user_text, orig_rec, applied, refused, warned_map(applied)),
                     daemon=True, name="chat-followup").start()
    return True


def _followup_guard_note(proj, sess, notes):
    """A discarded follow-up that still edited files: the student hears of it (a record that carries only that refusal)."""
    if notes:
        say(proj, sess, {"ts": now(), "role": "agent", "followup": True, "applied": [], "refused": notes,
                         "text": "(Not applied: " + "; ".join(notes) + ")"})


def _run_followup(proj, sess, tkey, fturn, user_text, orig_rec, applied, refused, warned):
    t0 = time.time()
    notes = []
    try:
        tail = session_mod.load_chat(proj, sess)
        if not tail or tail[-1].get("ts") != orig_rec["ts"] or tail[-1].get("role") != "agent" or fturn["cancel"].is_set():
            return                                  # the student wrote again, or pressed Stop, before it began
        runlog.event("chat", phase="followup-begin", project=proj, refused=len(refused), warned=len(warned))
        m = model.build(project=proj, session=sess)
        guard = tool_guard.begin()
        pguard = project_guard.begin(proj)
        BUSY["chat"] += 1
        try:
            res = agent.respond(m, followup_message(applied, refused, warned, orig_rec.get("denied"), orig_rec.get("tools")), m["chat"], backend=BACKEND, cancel=fturn["cancel"],
                                typed=user_text, generated=False, on_event=lambda ev, k=tkey: _turn_event(k, ev))
        finally:
            BUSY["chat"] -= 1
            edited, unrestored = tool_guard.end(guard)
            data_edited, data_unrestored = project_guard.end(pguard)
        if edited or unrestored:
            print(f"[guard] the follow-up edited system files: restored {edited}, not restorable {unrestored}", file=sys.stderr, flush=True)
            notes.append(tool_guard.refusal(edited, unrestored))
        if data_edited or data_unrestored:
            print(f"[guard] the follow-up edited project files: restored {data_edited}, not restorable {data_unrestored}", file=sys.stderr, flush=True)
            notes.append(project_guard.refusal(data_edited, data_unrestored))
        dropped = [str(a.get("type")) for a in res.get("actions") or [] if isinstance(a, dict)]
        if dropped:
            runlog.event("chat", phase="followup-actions-dropped", project=proj, kinds=dropped)
            print(f"[followup] follow-up actions dropped: {', '.join(dropped)}", file=sys.stderr, flush=True)
        reply = (res.get("reply") or "").strip()
        if reply == "(no reply)":                   # agent.respond's placeholder for an empty answer
            reply = ""
        tail = session_mod.load_chat(proj, sess)    # a message sent while it answered: the follow-up would land under the wrong question
        if (res.get("error") or res.get("partial") or fturn["cancel"].is_set() or not reply
                or not tail or tail[-1].get("ts") != orig_rec["ts"]):
            runlog.event("chat", phase="followup-end", ok=False, project=proj, seconds=round(time.time() - t0, 1),
                         error=str(res.get("error_kind") or ("cancelled" if fturn["cancel"].is_set() else "") or res.get("reply") or "no reply")[:300])
            _followup_guard_note(proj, sess, notes)  # nothing else is stored; the first reply and its red refusals stay
            notes = []
            return
        f_refused = list(notes)                     # only the guards' notes: a broken actions block of a text-only reply means nothing
        notes = []
        rec = {"ts": now(), "role": "agent", "followup": True, "text": reply, "applied": []}
        if f_refused:
            rec["refused"] = f_refused
            rec["text"] += "\n\n(Not applied: " + "; ".join(f_refused) + ")"
        if dropped:                                 # its text must not pass as a claim that something ran
            rec["text"] += "\n\n(Not run: follow-up replies do not run actions: " + ", ".join(dict.fromkeys(dropped)) + ")"
        for k in ("tools", "steps"):
            if res.get(k):
                rec[k] = res[k]
        if res.get("denied"):
            rec["denied"] = unique_denials(res["denied"])
        if compound_denials(orig_rec.get("denied"), orig_rec.get("tools")) and not any(
                isinstance(t, dict) and t.get("st") in ("ok", "bad") for t in rec.get("tools") or []):
            rec["text"] += "\n\n(Not run: the denied command was not run again; no script ran in this reply)"
        if res.get("seconds") is not None:
            rec["seconds"] = round(float(res["seconds"]), 1)
        if fturn["cancel"].is_set():                # a cancel at any point before the record is stored: nothing is stored
            _followup_guard_note(proj, sess, f_refused)
            return
        say(proj, sess, rec)
        if res.get("provider") != "external":
            import introspect
            introspect.record(proj, sess, "chat", res, res.get("seconds") or 0, reply=res.get("reply") or "",
                              applied=0, proposed=0, refused=len(f_refused))
        runlog.usage(proj, "answer", text=rec["text"], chat=sess, engine=res.get("provider") or "", model=res.get("model") or "",
                     seconds=rec.get("seconds"), applied=[], refused=f_refused, ok=True, words=len(rec["text"].split()), followup=True)
        runlog.event("chat", phase="followup-end", ok=True, project=proj, seconds=round(time.time() - t0, 1), refused=len(f_refused))
        import background
        background.verify_record_async(proj, sess, rec["ts"], rec["text"])    # citations: checked after the reply, never before
    except BaseException as exc:                    # a failed follow-up shows nothing: log it, the first turn stays
        try:
            runlog.event("chat", phase="followup-end", ok=False, project=proj, seconds=round(time.time() - t0, 1), error=f"{type(exc).__name__}: {exc}")
            _followup_guard_note(proj, sess, notes)
        except Exception:
            pass
    finally:
        _turn_end(tkey, fturn)


def open_part_session(project, ref_or_key):
    """Find or create the conversation anchored to a BOM line, net, or DFM check."""
    if not ref_or_key:
        return None
    info = model.anchors(project).get(ref_or_key)
    key = info["line"] if info and info.get("line") else ref_or_key
    line = next((l for l in store.bom_lines(project) if l["key"] == key), None)
    
    # Check if a session already has this anchor
    for row in session_mod.list_all(project):
        if row.get("anchor") == key or row.get("anchor") == ref_or_key:
            return row["id"]

    safe_sid_key = re.sub(r"[^\w-]", "_", str(ref_or_key))[:30]
    if line:
        sid = session_mod.create(project, title=line.get("mpn") or key, anchor=key, sid=f"part-{key}")
        ctx = model.part_context(project, line["refs"][0])
        session_mod.append(project, sid, {"ts": store.now(), "role": "ctx", "part": ctx})
        session_mod.append(project, sid, {
            "ts": store.now(), "role": "agent",
            "text": "What do you want to know about {{ref:" + line["refs"][0] + "}}? I can see its datasheet, "
                    "the nets it connects to and its stock."})
        return sid

    if str(ref_or_key).startswith("dfm:"):
        check_name = ref_or_key.split(":", 2)[-1]
        sid = session_mod.create(project, title=f"DFM: {check_name}", anchor=ref_or_key, sid=f"dfm-{safe_sid_key}")
        session_mod.append(project, sid, {
            "ts": store.now(), "role": "agent",
            "text": f"Let's discuss DFM check **{check_name}**. We can review the slice crop, check if it's a real issue or model artifact, and decide on a fix."
        })
        return sid

    # Net anchor or generic part anchor
    clean_anchor = str(ref_or_key).replace("net:", "")
    sid = session_mod.create(project, title=f"Net {clean_anchor}", anchor=ref_or_key, sid=f"net-{safe_sid_key}")
    session_mod.append(project, sid, {
        "ts": store.now(), "role": "agent",
        "text": f"What would you like to discuss about net or part **{clean_anchor}**? I can help check connectivity and design rules."
    })
    return sid


ABOUT_KINDS = ("part", "net", "dfm", "rule", "zone")     # what an "Ask" chip in the chat can point at (a file has its own field)


def chat_about(raw):
    """The chip the student sent with a message, cleaned: {kind, id, label} or None. It is stored on the user's
    message (the chat draws it) and turned into context for the engine by about_context."""
    if not isinstance(raw, dict) or raw.get("kind") not in ABOUT_KINDS:
        return None
    ident = str(raw.get("id") or "").strip()[:200]
    if not ident:
        return None
    return {"kind": raw["kind"], "id": ident, "label": str(raw.get("label") or ident).strip()[:200]}


def about_context(project, about):
    """What the engine is told about the thing the student pointed at, in front of their question.
    A part gets the same context card a part conversation starts with."""
    if about["kind"] == "part":
        line = next((l for l in store.bom_lines(project)
                     if about["id"] in l.get("refs", []) or l["key"] == about["id"]), None)
        ref = about["id"] if line and about["id"] in line.get("refs", []) else (line["refs"][0] if line and line.get("refs") else None)
        ctx = model.part_context(project, ref) if ref else None
        if ctx:
            return "[this question is about one part; its context]\n" + json.dumps(ctx, ensure_ascii=False, indent=2) + "\n\n"
    return f"[this question is about the {about['kind']} '{about['label']}' ({about['id']})]\n\n"


def export_library(project):
    """The Altium library package: manifest + whatever part files exist. Compiling the
    IntLib itself needs Altium (Windows); this is the hand-over, and it says what is unverified."""
    import zipfile
    rows = store.library_view(project)
    warnings = [f"{r['refs'][0] if r['refs'] else r['line']} ({r['mpn']}): {r['status']}"
                + (f" - {r['issues']}" if r["issues"] else "") for r in rows if r["status"] != "ok"]
    out_dir = store.pdir(project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{project}_library.zip"
    manifest = {"project": project, "exported": store.now(), "parts": rows, "unverified": warnings}
    readme = ("Altium library package\n======================\n"
              "manifest.json lists every non-standard part: symbol, footprint, 3D, where the model came from\n"
              "and whether it was checked against its datasheet and accepted.\n\n"
              "To build the IntLib: put the SchLib/PcbLib/STEP files from library/ in a Library Package project in\n"
              "Altium, compile it, then Components panel > menu > File-based Libraries Preferences > Installed > Install.\n"
              "Parts listed under 'unverified' must be checked by hand before you trust them.\n")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("README.txt", readme)
        lib = store.pdir(project) / "library"
        if lib.exists():
            for f in lib.rglob("*"):
                if f.is_file():
                    z.write(f, "library/" + f.relative_to(lib).as_posix())
    import lineage
    lineage.note(project, path, lambda: [lineage.state_input(project, "library")], "export_library")
    return {"file": path.name, "parts": len(rows), "warnings": warnings}


def recheck_async(project, key):
    """An MPN or LCSC code changed, or a line was added: a stock check answers for it, in the background queue
    (one job per line; background.py)."""
    import background
    return background.stock_line_async(project, key)


def recheck_missing(project):
    """After any BOM change (edit, import, applied proposal, agent action): every line that wants a stock check and
    has none is queued. Cheap: it reads files, never the network."""
    import background
    try:
        for key in background.lines_missing_stock(project):
            recheck_async(project, key)
    except Exception as exc:
        print(f"(stock sweep failed: {exc})")


def run_skill(name, project, *args):
    """The BOM page's buttons call a skill directly, the same code the agent runs."""
    if name == "compare":
        import compare_prices
        return compare_prices.compare(project)
    if name == "export_bom":
        import export_bom
        return export_bom.export(project, *args)
    if name == "check":
        import check_availability
        return {"results": check_availability.check(project, set(args) or None)}
    if name == "verify":
        import verify_part
        return verify_part.verify(project, args[0])
    raise ValueError(f"unknown skill {name}")


QUIET = False

# ---------------------------------------------------------------- self-update
# Checked once in the background at every start; the UI offers the Update button from what this holds.
UPDATE = {"state": "idle", "result": None}      # idle | checking | done | applying
UPDATE_LOCK = threading.Lock()
BUSY = {"chat": 0}                              # engine turns in flight: an update waits for them
HTTPD = None
RESTART_EXIT = 75                                  # start.bat starts the server again on this exit code
RESTART = {"go": False, "args": []}             # set by an applied update: main() starts the new code after shutdown


def check_updates(fetch=True):
    import update
    with UPDATE_LOCK:
        if UPDATE["state"] in ("checking", "applying"):
            return UPDATE["result"]
        UPDATE["state"] = "checking"
    try:
        res = update.check(fetch=fetch)
    except Exception as exc:                    # never take the server down over an update check
        res = {"kind": "?", "behind": 0, "can_update": False, "error": str(exc), "reason": ""}
    UPDATE.update(state="done", result=res)
    try:
        import introspect
        (workspace.home() / introspect.UPDATE_STATUS).write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                                                  encoding="utf-8")
    except OSError:
        pass
    return res


def update_state():
    import update
    return {"state": UPDATE["state"], **(UPDATE["result"] or {}), "version": update.version()}


def apply_update():
    """Apply, then restart into the new code. Refused while the agent is answering: the restart would cut it off."""
    import update
    if BUSY["chat"]:
        why = "The agent is answering. Update when it is done."
        return 409, {"ok": False, "reason": why, "error": why}
    if STEP_LOCK.locked():              # the restart would kill the script that is driving Altium
        why = "Altium is running a step. Update when it has finished."
        return 409, {"ok": False, "reason": why, "error": why}
    with UPDATE_LOCK:
        if UPDATE["state"] in ("checking", "applying"):
            why = "An update check is running. Try again in a moment."
            return 409, {"ok": False, "reason": why, "error": why}
        UPDATE["state"] = "applying"
    try:
        res = update.apply()
    except Exception as exc:                    # apply() reports its own failures; this is the unforeseen one
        res = {"ok": False, "reason": f"The update failed: {exc}"}
    finally:
        UPDATE["state"] = "done"
    if res["ok"]:
        UPDATE["result"] = {**(UPDATE["result"] or {}), "behind": 0, "can_update": False, "current": res["to"],
                            "commits": [], "reason": "Updated; restarting."}
        res["restarting"] = HTTPD is not None
        if HTTPD is not None:
            threading.Timer(0.5, restart).start()
    else:
        res["error"] = res.get("reason") or "The update failed."     # the UI's toast shows `error`
    return (200 if res["ok"] else 400), res


def restart():
    """Stop serving; main() then starts the server again on the updated code."""
    RESTART["go"] = True
    HTTPD.shutdown()


def _start_again(args):
    """The same command line, without opening another browser tab: the open page reloads itself."""
    argv = [sys.executable, str(workspace.REPO / "pcb.py"), "serve", *[a for a in args if a != "--no-browser"],
            "--no-browser"]
    if os.name == "nt":
        if os.environ.get("PCB_ADVISOR_LAUNCHER") == "start.bat":
            raise SystemExit(RESTART_EXIT)      # start.bat runs the server again in a fresh process
        # Started by hand: os.execv on Windows starts a detached process and the console window would close under
        # it; waiting for the child keeps that window (and its Ctrl+C) attached to the running server.
        import subprocess
        raise SystemExit(subprocess.call(argv))
    os.execv(sys.executable, argv)

# What GET /ui/<path> may serve from ui_dir, by file extension (anything else is a 404).
UI_STATIC_TYPES = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".json": "application/json",
}


def _extra_rules_load(rules_file):
    """The project's extra rules (rules.json), [] when there are none or the file is unreadable."""
    if rules_file.is_file():
        try:
            val = json.loads(rules_file.read_text(encoding="utf-8"))
            return val if isinstance(val, list) else []
        except Exception:
            return []
    return []


def _preset_off(proj):
    """Names of the JLC preset rules this project turned off (rules-off.json)."""
    f = model.project_dir(proj) / "rules-off.json"
    try:
        val = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else []
        return [n for n in val if isinstance(n, str)] if isinstance(val, list) else []
    except Exception:
        return []


def _extra_rules_save(rules_file, new_rules):
    """Add rules to the store; a rule with the same name replaces the old one."""
    extra = _extra_rules_load(rules_file)
    for rule in new_rules:
        idx = next((i for i, r in enumerate(extra) if r.get("name") == rule["name"]), None)
        if idx is None:
            extra.append(rule)
        else:
            extra[idx] = rule
    rules_file.parent.mkdir(parents=True, exist_ok=True)
    rules_file.write_text(json.dumps(extra, indent=2), encoding="utf-8")
    return extra


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        """One line per request, unless --quiet. A rejected write used to leave no
        trace anywhere; now it shows up here."""
        if QUIET:
            return
        line = (fmt % args) if args else str(fmt)
        # the UI polls /api/state every few seconds; logging that would bury everything else
        if "/api/state" in line and " 200 " in line:
            return
        sys.stderr.write(f"  {dt.datetime.now().strftime('%H:%M:%S')}  {line}\n")

    def project(self):
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("project") or [DEFAULT_PROJECT or workspace.default_project()])[0]
        return workspace.safe_name(name)

    def session(self, project):
        q = parse_qs(urlparse(self.path).query)
        return session_mod.current(project, (q.get("session") or [None])[0])

    def query(self, key):
        return (parse_qs(urlparse(self.path).query).get(key) or [None])[0]

    def queries(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self._status = code
        if code >= 400:             # for the run log: what the answer said, and where a 5xx came from
            try:
                self._err = str((json.loads(body) if ctype.startswith("application/json") else {}).get("error", ""))
            except Exception:
                self._err = ""
            if code >= 500 and sys.exc_info()[0]:
                self._tb = runlog.tb()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        try:
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            self._client_gone = True        # the browser tab went away before the answer: not a fault of the server
            raise

    def _cross_origin(self):
        """True when the request must be refused as not from this machine's own page. Three checks: the Host is a local name (a
        DNS-rebound page arrives with its own Host; Origin == Host alone would pass it), an Origin if sent is this very server, and
        Sec-Fetch-Site if sent says same-origin or none. No Origin (CLI, tests, our own callers) is fine on a local Host."""
        host = (self.headers.get("Host") or "").strip().lower()
        name = host[:host.index("]") + 1] if host.startswith("[") and "]" in host else host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        if name not in LOCAL_HOSTS:
            return True
        origin = self.headers.get("Origin")
        if origin is not None and urlparse(origin).netloc.lower() != host:
            return True
        site = self.headers.get("Sec-Fetch-Site")
        return site is not None and site not in ("same-origin", "none")

    def _report(self, make):
        """POST: make the diagnostic zip (local only) and say where it is. GET ?file=<name>: send one made earlier (strict file name)."""
        name = self.query("file")
        if not make and not name:
            return self._send(405, {"error": "use POST to make a report"})
        if name:
            if not re.fullmatch(r"pcb-advisor-report-[\w-]+\.zip", name) or not (runlog.log_dir() / name).is_file():
                return self._send(404, {"error": "no such report"})
            zpath = runlog.log_dir() / name
        else:
            try:
                zpath = runlog.make_report(doctor=_cached_doctor())
            except Exception as exc:
                runlog.exception("exception", exc, where="report")
                return self._send(500, {"error": f"The report could not be made ({type(exc).__name__}: {exc})"})
        if not make:
            return self._send(200, zpath.read_bytes(), "application/zip",
                              {"Content-Disposition": f'attachment; filename="{zpath.name}"'})
        return self._send(200, {"path": str(zpath), "name": zpath.name, "size": zpath.stat().st_size})

    def _report_project(self):
        """GET /api/report/project?project=<name>: make that project's activity zip now (a copy stays in logs/) and send it as a download."""
        name = self.query("project")
        site = self.headers.get("Sec-Fetch-Site") or ""
        if self._cross_origin() or not (site in ("same-origin", "none") or self.headers.get("X-PCB-Report") == "1"):
            return self._send(403, {"error": "forbidden"})        # a page of another site must not make zips; the page's own fetch sets the header
        if not runlog.project_ok(name):
            return self._send(404, {"error": "no such project"})
        try:
            zpath = runlog.make_report(project=name, doctor=_cached_doctor())
            data = zpath.read_bytes()
        except Exception as exc:
            runlog.exception("exception", exc, where="report.project", project=name)
            return self._send(500, {"error": f"The report could not be made ({type(exc).__name__}: {exc})"})
        found = re.search(r"(\d{8}-\d{6}(?:-\d+)?)$", zpath.stem)
        stamp = found.group(1) if found else "now"
        ascii_name = "pcb-advisor-report-" + (re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "project") + "-" + stamp + ".zip"
        return self._send(200, data, "application/zip", {
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(zpath.name)}"})

    def _send_ui_static(self, rel):
        """GET /ui/<rel>: any file under ui_dir with an allowed extension (scripts, styles, images, fonts, json).
        Anything that resolves outside ui_dir is refused (403); unknown extensions and missing files are 404."""
        rel = unquote(rel)
        ctype = UI_STATIC_TYPES.get(pathlib.PurePosixPath(rel.replace("\\", "/")).suffix.lower())
        try:
            ui_dir = workspace.ui_dir().resolve()
            target = (ui_dir / rel).resolve()
        except (OSError, ValueError):       # NUL byte, invalid characters
            return self._send(404, {"error": "not found"})
        if ui_dir not in target.parents:
            return self._send(403, {"error": "forbidden"})
        if ctype is None or not target.is_file():
            return self._send(404, {"error": "not found"})
        return self._send(200, target.read_bytes(), ctype)

    # ---------------------------------------------------------------- read
    def do_GET(self):
        self._guarded(self._get)

    def do_POST(self):
        self._guarded(self._post)

    def _guarded(self, fn):
        """The run log around every request; the work itself is _guarded_run."""
        t0 = time.time()
        self._status, self._err, self._tb = 0, "", ""
        runlog.ctx.session = (self.headers.get("X-Usage-Session") or "")[:40]       # the page load this request belongs to
        try:
            return self._guarded_run(fn)
        except BaseException as exc:
            if getattr(self, "_client_gone", False):
                self._err = self._err or f"client gone ({type(exc).__name__})"
                raise
            runlog.exception("exception", exc, method=self.command, path=self.path.split("?")[0], project=self._log_project())
            raise
        finally:
            self._log_request(t0)
            runlog.ctx.session = ""

    def _log_project(self):
        try:
            return (parse_qs(urlparse(self.path).query).get("project") or [""])[0]
        except Exception:
            return ""

    def _log_request(self, t0):
        path = self.path.split("?")[0]
        if 0 < self._status < 400 and not self._err and (path in QUIET_PATHS or path == "/" or path.startswith("/ui/")):
            return                  # polled or logging endpoints and the page's own files: only their errors are worth a line
        rec = {"method": self.command, "path": path, "status": self._status, "ms": round((time.time() - t0) * 1000)}
        project = self._log_project()
        if project:
            rec["project"] = project
        if self._err:
            rec["error"] = self._err
        if self._tb:
            rec["traceback"] = self._tb
        runlog.event("request", **rec)

    def _guarded_run(self, fn):
        """A project file another program holds open (Windows: an editor) is an answer, not a dropped connection."""
        try:
            return fn()
        except BadField as exc:
            return self._send(400, {"error": str(exc)})
        except PermissionError as exc:              # a Windows sharing violation; a missing file or a socket error is not
            if not exc.filename:
                raise
            name = pathlib.Path(exc.filename).name
            return self._send(423, {"error": f"{name} is open in another program ({exc.filename}); close it and try again"})

    def _get(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/") and self._cross_origin():      # some GETs write logs (e.g. /api/final/unverified); none is for another site
            return self._send(403, {"error": "forbidden"})
        if path in ("/", "/index.html"):
            return self._send(200, (workspace.ui_dir() / "index.html").read_text(encoding="utf-8"),
                              "text/html; charset=utf-8")
        if path == "/diagram.js":          # old alias for /ui/diagram.js
            path = "/ui/diagram.js"
        if path.startswith("/ui/"):
            return self._send_ui_static(path[len("/ui/"):])
        if path == "/api/projects":
            return self._send(200, {"projects": model.list_projects(),
                                    "default": DEFAULT_PROJECT or workspace.default_project()})
        if path == "/api/state":
            proj = self.project()
            m = model.build(project=proj, session=self.session(proj))
            m["backend"] = m["engine"] = gateway.resolve(BACKEND)
            m["followup_running"] = followup_running(proj, self.session(proj))
            return self._send(200, m)
        if path == "/api/sessions":
            proj = self.project()
            return self._send(200, {"sessions": session_mod.list_all(proj),
                                    "current": self.session(proj)})
        if path == "/api/config":
            return self._send(200, _public_config())
        if path == "/api/chat/progress":
            proj = self.project()
            return self._send(200, turn_progress((proj, self.session(proj))))
        if path == "/api/altium":
            return self._send(200, _altium_state(self.project()))
        if path == "/api/bom/import/candidates":
            proj = self.project()
            if not project_mod.exists(proj):
                return self._send(404, {"error": f"no such project: {proj}"})
            import bom_import
            linked = bool(project_mod.altium_link(proj).get("project_file"))
            return self._send(200, {"linked": linked, "bom_empty": not store.bom_lines(proj),
                                    "candidates": bom_import.candidates(proj) if linked else []})
        if path == "/api/altium/file":
            req_path = self.query("path")
            if not req_path:
                return self._send(403, {"error": "forbidden"})
            link = project_mod.altium_link(self.project())
            project_file = link.get("project_file", "")
            if not project_file:
                return self._send(403, {"error": "no Altium project linked"})

            prj_path = pathlib.Path(project_file).resolve()
            allowed = {os.path.normcase(str(prj_path))}
            if link.get("pcb_file"):
                try:
                    allowed.add(os.path.normcase(str(pathlib.Path(link["pcb_file"]).resolve())))
                except Exception:
                    pass
            try:
                from altium.prjpcb import read_prjpcb
                prj_info = read_prjpcb(prj_path)
                for doc in prj_info.get("documents", []):
                    doc_p = pathlib.Path(doc.replace("\\", "/"))
                    doc_target = doc_p.resolve() if doc_p.is_absolute() else (prj_path.parent / doc_p).resolve()
                    allowed.add(os.path.normcase(str(doc_target)))
                for sheet in prj_info.get("sheets", []):
                    s_p = pathlib.Path(sheet.replace("\\", "/"))
                    s_target = s_p.resolve() if s_p.is_absolute() else (prj_path.parent / s_p).resolve()
                    allowed.add(os.path.normcase(str(s_target)))
                for pcb in prj_info.get("pcbs", []):
                    pcb_p = pathlib.Path(pcb.replace("\\", "/"))
                    pcb_target = pcb_p.resolve() if pcb_p.is_absolute() else (prj_path.parent / pcb_p).resolve()
                    allowed.add(os.path.normcase(str(pcb_target)))
            except Exception:
                pass

            try:
                target = pathlib.Path(req_path).resolve()
            except Exception:
                return self._send(403, {"error": "forbidden"})

            if os.path.normcase(str(target)) not in allowed:
                return self._send(403, {"error": "forbidden"})

            try:
                from altium import AltiumReadError, read_any
                from altium.dump import summarize
                doc = read_any(target)
                res = summarize(target, doc)
                return self._send(200, res)
            except AltiumReadError as exc:
                return self._send(422, {"error": str(exc)})
            except Exception as exc:
                return self._send(422, {"error": str(exc)})
        if path == "/api/report/project":      # the tester's one button: this project's activity zip, as a download
            return self._report_project()
        if path == "/api/report":              # downloads one report made earlier; making one is POST only
            return self._report(make=False)
        if path == "/api/doctor":                  # the same list as `pcb.py doctor --json`; ?refresh=1 runs it again
            import doctor
            return self._send(200, doctor.cached(refresh=bool(self.query("refresh"))))
        if path == "/api/readiness":               # what is not ready yet (the banner on open); never runs a subprocess
            return self._send(200, readiness(self.project()))
        if path == "/api/update":                  # the check made at start; ?refresh=1 checks again now
            if self.query("refresh"):
                check_updates(fetch=True)
            return self._send(200, update_state())
        if path == "/api/introspect":              # what the agent did in this project, what it cost, which version
            import introspect
            proj = self.project()
            return self._send(200, {"summary": introspect.summary(proj), "outputs": introspect.outputs(proj),
                                    "version": introspect.version()})
        if path == "/api/skills":
            from skills import registry
            return self._send(200, {"skills": registry.listing()})
        if path in ("/api/sheet.svg", "/api/preview/sch.svg"):
            proj = self.project()
            sheet = self.query("sheet") or (store.sheet_ids(proj) or [""])[0]
            if not store.load_sheet(proj, sheet):
                import preview_sch
                try:
                    svg = preview_sch.render_project_sch(proj, sheet=sheet)
                except (Exception, SystemExit):
                    svg = None
                if svg and not svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">'):
                    return self._send(200, svg, "image/svg+xml; charset=utf-8")
                return self._send(404, {"error": f"no sheet {sheet!r}"})
            import render_sheet
            try:
                return self._send(200, render_sheet.render(proj, sheet, write=False),
                                  "image/svg+xml; charset=utf-8")
            except (Exception, SystemExit):
                return self._send(404, {"error": f"no sheet {sheet!r}"})
        if path == "/api/sch/component":
            ref = self.query("ref")
            if not ref:
                return self._send(400, {"error": "ref required"})
            sheet = self.query("sheet")
            proj = self.project()
            import preview_sch
            comp = preview_sch.get_component_details(proj, ref, sheet=sheet)
            if not comp:
                return self._send(404, {"error": f"component {ref!r} not found"})
            return self._send(200, comp)
        if path == "/api/preview/pcb.svg":
            proj = self.project()
            layer = self.query("layer") or "all"
            import preview_pcb
            svg = preview_pcb.render_project_pcb(proj, layer=layer)
            return self._send(200, svg, "image/svg+xml; charset=utf-8")
        if path == "/api/placement/plan":
            proj = self.project()
            import preview_pcb
            return self._send(200, preview_pcb.load_placement_plan(proj))
        if path == "/api/keeping/decisions":
            proj = self.project()
            import keeping
            return self._send(200, {"decisions": keeping.list_decisions(proj)})
        if path == "/api/keeping/impact":
            proj = self.project()
            item = self.query("item") or ""
            import keeping
            return self._send(200, {"impacts": keeping.change_impact(proj, item)})
        if path == "/api/keeping/report":
            proj = self.project()
            import keeping
            return self._send(200, keeping.file_organization(proj))
        if path.startswith("/api/source/"):
            name = unquote(path.split("/api/source/", 1)[1])
            # a plain name is a project or shared document; a name with a folder ('jlc/pcb-capabilities.en.md') is a
            # reference document and only resolves through the reference listing, so a path can never leave the library
            if "/" in name or "\\" in name:
                found = [sources.reference_path(name)]
            else:
                found = [base / pathlib.Path(name).name for base in (model.project_dir(self.project()) / "sources", workspace.datasheets_dir())]
                found.append(sources.reference_path(name))
            for f in found:
                if f is not None and f.exists() and f.is_file():
                    ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
                    if ctype.startswith("text/") or "xml" in ctype or "html" in ctype:
                        ctype = "text/plain; charset=utf-8"  # never let an uploaded .html run in the UI origin
                    extra = {}
                    if self.query("download") == "1":
                        extra["Content-Disposition"] = f'attachment; filename="{f.name}"'
                    return self._send(200, f.read_bytes(), ctype, extra=extra)
            return self._send(404, {"error": "not in the library"})
        if path.startswith("/api/export/"):
            name = pathlib.Path(unquote(path.split("/api/export/", 1)[1])).name
            f = model.project_dir(self.project()) / "exports" / name
            if f.exists():
                return self._send(200, f.read_bytes(), "application/octet-stream",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, {"error": "no such export"})
        if path == "/api/parts/alternatives":
            proj = self.project()
            key = self.query("line")
            if not key:
                return self._send(400, {"error": "line required"})
            lines = store.bom(proj, write=False)
            target_line = next((l for l in lines if l["key"] == key), None)
            if not target_line:
                return self._send(404, {"error": f"no BOM line {key!r}"})
            try:
                import jlc
                alts = jlc.alternatives(target_line)
                return self._send(200, alts)
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if path == "/api/order/check":
            import order_check
            try:
                return self._send(200, order_check.order_check(self.project()))      # read only: a recheck is a POST
            except Exception as exc:
                return self._send(500, {"error": str(exc)})
        if path == "/api/final/unverified":
            return self._send(200, store.recheck_pins(self.project()))
        if path == "/api/final/incomplete":
            return self._send(200, store.sheet_gaps(self.project()))
        if path == "/api/checks":
            import dfm
            kind = self.query("kind")
            return self._send(200, {"checks": dfm.list_checks(self.project(), kind=kind)})
        if path == "/api/checks/slice":
            stem = self.query("stem")
            slice_file = self.query("slice")
            if not stem or not slice_file:
                return self._send(400, {"error": "stem and slice query params required"})
            import dfm
            p = dfm.get_slice_path(self.project(), stem, slice_file)
            if not p:
                return self._send(404, {"error": "slice not found"})
            return self._send(200, p.read_bytes(), "image/jpeg")
        if path == "/api/checks/triage":
            stem = self.query("stem")
            if not stem:
                return self._send(400, {"error": "stem query param required"})
            import dfm
            rows = dfm.load_triage(self.project(), stem)
            return self._send(200, {"stem": stem, "triage": rows, "sig": dfm.triage_sig(rows)})
        if path == "/api/checks/index":
            stem = self.query("stem")
            if not stem:
                return self._send(400, {"error": "stem query param required"})
            import dfm
            try:
                return self._send(200, dfm.load_index(self.project(), stem))
            except Exception as exc:
                return self._send(404, {"error": str(exc)})
        if path == "/api/exports":
            proj = self.project()
            out_dir = model.project_dir(proj) / "exports"
            files = []
            if out_dir.is_dir():
                for f in sorted(out_dir.iterdir()):
                    if f.is_file():
                        files.append({
                            "name": f.name,
                            "bytes": f.stat().st_size,
                            "modified": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                            "url": f"/api/export/{f.name}",
                        })
            return self._send(200, {"exports": files})
        if path == "/api/altium/step-status":        # the live list of the button run for this project (see step_status); take=1 reads a finished run once
            return self._send(200, step_status(self.project(), take=self.query("take") == "1"))
        if path == "/api/altium/outputs":            # what Altium's outputs folder holds now (folders, file counts, newest time)
            import jlc_upload
            return self._send(200, jlc_upload.outputs_summary(self.project()))
        if path == "/api/jlc/gerber-zip":            # the zip made last time (files, when written, what is missing); nothing is built
            import jlc_upload
            return self._send(200, jlc_upload.zip_info(self.project()))
        if path == "/api/net-currents":             # supply nets with their current, where it came from and the track width it gives
            from altium import bridge
            return self._send(200, bridge.net_current_rows(self.project()))
        if path == "/api/rules":
            proj = self.project()
            import rules as rules_mod
            import rule_kinds, ipc_standards
            from checks import board as board_checks
            preset = rules_mod.get_jlc_preset(project_mod.board(proj))   # 2 or multilayer, copper weight, mask colour
            rules_file = model.project_dir(proj) / "rules.json"
            extra = _extra_rules_load(rules_file)
            linked_pcb = None
            board_rules = []
            doc = None
            try:
                link = project_mod.altium_link(proj)
                pcb_name = link.get("pcb_file")
                prj_file = link.get("project_file")
                if pcb_name:
                    pcb_path = pathlib.Path(pcb_name)
                    if not pcb_path.is_file() and prj_file:
                        pcb_path = pathlib.Path(prj_file).parent / pcb_name
                    if pcb_path.is_file():
                        from altium import read_pcbdoc
                        doc = read_pcbdoc(pcb_path)
                        board_rules = doc.get("rules", [])
                        linked_pcb = pcb_path.name
            except Exception:
                pass
            off = _preset_off(proj)
            missing_in_pcb = []
            if linked_pcb:
                from altium import bridge
                try:
                    missing_in_pcb = bridge.rules_missing(proj)      # what Import would write that the PcbDoc file lacks
                except bridge.AliasError:
                    missing_in_pcb = []                              # design_check below carries the same clash message
            diff = rules_mod.diff_rules(board_rules, [r for r in preset.get("rules", []) if r.get("name") not in off], board_geom=doc)
            design_check = []
            if linked_pcb:
                from altium import bridge
                design_check = bridge.design_problems(proj)    # the board against the design (netlist and SchDocs)
            return self._send(200, {
                "preset": preset,
                "extra": extra,
                "preset_off": off,
                "kinds": rule_kinds.kinds_info(),
                "standards": ipc_standards.info(),
                "diff": diff,
                "linked_pcb": linked_pcb,
                "missing_in_pcb": missing_in_pcb,
                "drill_check": board_checks.check_drills(doc) if doc else [],
                "design_check": design_check,
            })
        if path == "/api/rules/standard":           # what a standard preset would add (nothing is stored)
            import ipc_standards
            q = self.queries()
            try:
                return self._send(200, ipc_standards.preview(q.get("standard", ""), q, project_mod.board(self.project())))
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
        if path == "/api/rules/export":
            proj = self.project()
            import rules as rules_mod
            off = _preset_off(proj)
            records = [r for r in rules_mod.get_preset_rule_records(project_mod.board(proj)) if r.get("NAME") not in off]
            board_aware = False
            if not self.query("plain"):
                try:
                    link = project_mod.altium_link(proj)
                    pcb_name = link.get("pcb_file")
                    prj_file = link.get("project_file")
                    if pcb_name:
                        pcb_path = pathlib.Path(pcb_name)
                        if not pcb_path.is_file() and prj_file:
                            pcb_path = pathlib.Path(prj_file).parent / pcb_name
                        if pcb_path.is_file():
                            records = rules_mod.board_rul_records(pcb_path, records)
                            board_aware = True
                except Exception:
                    pass
            import rule_kinds
            records = rule_kinds.append_extra_records(records, _extra_rules_load(model.project_dir(proj) / "rules.json"))
            b = rules_mod.format_rul_bytes(records)
            return self._send(200, b, "application/octet-stream",
                              {"Content-Disposition": f'attachment; filename="{proj}-rules{"-board" if board_aware else ""}.RUL"'})
        if path == "/api/calc":
            import calc
            q = self.queries()
            t = q.get("type", "")
            try:
                if t == "trace_width":
                    res = calc.trace_width_ipc2221(
                        float(q.get("current", q.get("amps", 1.0))),
                        float(q.get("rise", 10.0)),
                        float(q.get("oz", 1.0)),
                        q.get("internal", "").lower() in ("true", "1"),
                    )
                elif t == "divider":
                    vin = float(q["vin"])
                    vout = float(q["vout"]) if q.get("vout") else None
                    r1 = float(q["r1"]) if q.get("r1") else None
                    r2 = float(q["r2"]) if q.get("r2") else None
                    res = calc.voltage_divider(vin, vout=vout, r1=r1, r2=r2)
                elif t == "led":
                    res = calc.led_resistor(
                        float(q["v_supply"]),
                        float(q["v_forward"]),
                        float(q.get("i_forward_ma", q.get("i_ma", 20.0))),
                    )
                elif t == "via":
                    res = calc.via_current(
                        float(q.get("drill_mm", q.get("drill", 0.3))),
                        float(q.get("rise", 10.0)),
                        float(q.get("plating_um", calc.PLATING_UM_JLC)),
                    )
                elif t == "microstrip":
                    res = calc.microstrip_impedance(
                        float(q.get("width_mm", q.get("w", 0.3))),
                        float(q.get("height_mm", q.get("h", 0.2))),
                        float(q.get("copper_mm", 0.035)),
                        float(q.get("er", 4.4)),
                    )
                else:
                    return self._send(400, {"error": f"unknown calc type {t!r}"})
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"error": str(exc)})
        if path == "/api/library/search":
            mpn = self.query("mpn")
            if not mpn:
                return self._send(400, {"error": "mpn required"})
            import library as lib_mod
            return self._send(200, lib_mod.model_search_links(mpn))
        if path == "/api/library/check_package":
            bom_pkg = self.query("bom_pkg")
            jlc_pkg = self.query("jlc_pkg")
            import library as lib_mod
            return self._send(200, lib_mod.check_package_variant(bom_pkg, jlc_pkg))
        if path.startswith("/api/"):                    # extensions (ext.py): only a path no route above matched, after the cross-site guard
            hit = ext.dispatch_http(ext.GET, self, path, {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            if hit:
                return self._send(*hit)
        return self._send(404, {"error": "not found"})

    # ---------------------------------------------------------------- write
    def _post(self):
        path = self.path.split("?")[0]
        if self._cross_origin():          # default deny: no state change for a page of another site or a rebound host, whatever the route
            self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1 << 20))     # drained, or the reset hides the answer
            return self._send(403, {"error": "forbidden"})
        proj = self.project()
        sess = self.session(proj)

        n = int(self.headers.get("Content-Length", 0))
        if n > (runlog.USAGE_MAX_BODY if path == "/api/log/usage" else runlog.MAX_BODY if path == "/api/log/client" else n):
            return self._send(413, {"error": "too large"})       # a report from the page is small; refuse the rest unread
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        if not isinstance(data, dict) and path != "/api/log/usage":
            return self._send(400, {"error": "The request body must be a JSON object."})     # every handler below reads data.get(...)

        def state():
            m = model.build(project=proj, session=sess)
            m["followup_running"] = followup_running(proj, sess)
            return m

        if path == "/api/log/client":          # window.onerror / unhandledrejection from the page
            if isinstance(data, dict):
                f = {k: data.get(k) for k in ("message", "source", "line", "column", "stack", "view", "session")}
                runlog.event("ui-error", project=proj, **f)
                runlog.usage(proj, "ui-error", ok=False, **f)
            return self._send(200, {"ok": True})
        if path == "/api/log/usage":           # view / click / shown events, batched by the page
            code, why = runlog.usage_batch(data)
            return self._send(code, {"ok": code == 200} if code == 200 else {"error": why})
        if path == "/api/report":
            return self._report(make=True)

        # ---- the conversation
        if path == "/api/chat":
            text = _text_field(data, "text")
            if not text:
                return self._send(400, {"error": "text required"})
            source_file = data.get("file") or data.get("source")
            about = None if source_file else chat_about(data.get("about"))
            tkey = (proj, sess)
            _chat_t0, _chat_info = time.time(), {"project": proj, "engine": "", "model": ""}       # set before anything can fail
            _answered = []         # the usage log gets exactly one answer (or the refusal) for every message
            _msg = dict(text=text, chat=sess, queued=_truthy(data.get("queued")), generated=_truthy(data.get("generated")), file=source_file or "")
            for _try in range(2):
                with TURNS_LOCK:       # the checks and the registration together: a step button never slips in between them
                    running = tkey in TURNS
                    stepping = STEP_LOCK.locked()
                    if not running and not stepping:
                        turn = TURNS[tkey] = _new_turn()
                if running and _try == 0 and cancel_followups(lambda k, t=tkey: k == t):
                    continue           # only a follow-up was answering: the student's message goes first, no 409
                break
            if running:            # before saving: the client queue resends it when the answer is a 409, so it must not be stored twice
                runlog.usage(proj, "message", ok=False, shown="this conversation is still answering", **_msg)
                return self._send(409, {"error": "this conversation is still answering"})
            if stepping:           # the agent may look at Altium while it answers, and that stops the script that is running there
                runlog.usage(proj, "message", ok=False, shown="Altium is busy with another step; send this again when it has finished", **_msg)
                return self._send(409, {"error": "Altium is busy with another step; send this again when it has finished"})
            runlog.usage(proj, "message", ok=True, **_msg)
            try:
                user_msg = {"ts": now(), "role": "user", "text": text}
                if source_file:
                    user_msg["source"] = source_file
                if about:
                    user_msg["about"] = about
                generated = _truthy(data.get("generated"))      # a button wrote this text: the reply language follows what the student typed
                if generated:
                    user_msg["generated"] = True
                say(proj, sess, user_msg)
                m = model.build(project=proj, session=sess)
                ask = text
                row = next((r for r in m["sessions"] if r["id"] == sess), {})
                if source_file:
                    src_text = ""
                    try:
                        src_text = sources.text_of(source_file, folder=model.project_dir(proj) / "sources")
                    except Exception:
                        pass
                    if src_text:
                        ask = (f"[this conversation is about file '{source_file}'; its content]\n"
                               f"{src_text[:12000]}\n\n{text}")
                    else:
                        ask = f"[this conversation is about file '{source_file}']\n\n{text}"
                elif about:
                    ask = about_context(proj, about) + text
                elif row.get("anchor"):
                    ref = (store.bom_lines(proj) and next(
                        (l["refs"][0] for l in store.bom_lines(proj) if l["key"] == row["anchor"] and l.get("refs")), None))
                    ctx = model.part_context(proj, ref) if ref else None
                    if ctx:
                        ask = ("[this conversation is about one part; its context]\n"
                               f"{json.dumps(ctx, ensure_ascii=False, indent=2)}\n\n{text}")
            except BaseException as exc:
                runlog.usage(proj, "answer", text="", chat=sess, ok=False, error=f"{type(exc).__name__}: {exc}")
                _turn_end(tkey, turn)
                raise
            res = None
            try:             # _turn_end runs exactly once, whatever fails between the start and the end of apply_actions
                _eng = gateway.resolve(BACKEND)       # the run log gets counts and seconds, never the text
                _chat_info = {"project": proj, "engine": _eng, "model": workspace.get(f"agent.providers.{_eng}.model", "")}
                runlog.event("chat", phase="begin", **_chat_info)
                guard = tool_guard.begin()
                pguard = project_guard.begin(proj)
                BUSY["chat"] += 1
                tool_edited, tool_unrestored, data_edited, data_unrestored = [], [], [], []
                try:
                    res = agent.respond(m, ask, m["chat"][:-1], backend=BACKEND, cancel=turn["cancel"], typed=text, generated=generated,
                                        on_event=lambda ev, k=tkey: _turn_event(k, ev))
                finally:
                    BUSY["chat"] -= 1
                    tool_edited, tool_unrestored = tool_guard.end(guard)     # the agent never keeps an edit of the tool's own files
                    data_edited, data_unrestored = project_guard.end(pguard)  # nor a direct edit of the project's server-written data
                if tool_edited or tool_unrestored:
                    print(f"[guard] the agent edited system files: restored {tool_edited}, not restorable {tool_unrestored}", file=sys.stderr, flush=True)
                chat_meta = {}
                partial = bool(res.get("partial"))
                if partial:      # a half-written actions block is not trusted
                    applied, proposals, refused = [], [], []
                else:            # the turn stays open while the actions run, so the chat shows which step is running
                    applied, proposals, refused = apply_actions(
                        proj, res.get("actions"), sess, last_user=text, meta=chat_meta, turn_start=turn["started"],
                        on_step=lambda label, k=tkey: _turn_event(k, {"label": label}), cancel=turn["cancel"],
                        chat=m["chat"])
            except BaseException as exc:
                runlog.usage(proj, "answer", text="", chat=sess, ok=False, error=f"{type(exc).__name__}: {exc}", engine=_chat_info["engine"])
                runlog.exception("chat", exc, phase="end", ok=False, seconds=round(time.time() - _chat_t0, 1), **_chat_info)
                try:        # the turn that crashed is the one a debugger needs: its engine calls so far, and the error
                    import introspect
                    crashed = dict(res) if isinstance(res, dict) else {}
                    crashed.setdefault("provider", _chat_info["engine"])
                    crashed["error"] = f"{type(exc).__name__}: {exc}"
                    introspect.record(proj, sess, "chat", crashed, time.time() - _chat_t0, reply=crashed["error"])
                except Exception:
                    pass
                raise
            finally:
                _turn_end(tkey, turn)
            refused.extend(res.get("parse_refused") or [])
            if tool_edited or tool_unrestored:
                refused.append(tool_guard.refusal(tool_edited, tool_unrestored))
            if data_edited or data_unrestored:
                print(f"[guard] the agent edited project files: restored {data_edited}, not restorable {data_unrestored}", file=sys.stderr, flush=True)
                refused.append(project_guard.refusal(data_edited, data_unrestored))
            runlog.event("chat", phase="end", ok=not res.get("error"), seconds=round(time.time() - _chat_t0, 1), applied=max(0, len(applied) - _pending(proj, proposals)),
                         refused=len(refused), warned=len(warned_map(applied)), proposed=_pending(proj, proposals), partial=partial,
                         actions=[x.get("type") for x in (res.get("actions") or [])[:30] if isinstance(x, dict)], parse_refused=res.get("parse_refused") or [],
                         error_kind=res.get("error_kind") or "", error=("" if partial or not res.get("error") else str(res.get("reply") or "")[:4000]),
                         **_chat_info)
            if proposals and not partial:
                try:
                    gone = refs_missing_from_bom(proj, res.get("reply"))
                except Exception:          # a check of the reply must never lose the reply or the applied marker
                    gone = []
                if gone:
                    applied.append(f"bom.check: WARNING: {', '.join(gone)} named in the reply but in no BOM line (add it to the line's refs)")
            if res.get("provider") != "external":         # an outside driver is not an engine turn
                import introspect
                introspect.record(proj, sess, "chat", res, res.get("seconds") or 0, reply=res.get("reply") or "",
                                  applied=max(0, len(applied) - _pending(proj, proposals)), proposed=_pending(proj, proposals), refused=len(refused))     # a proposal is not "applied": it waits for the student
            if res.get("reply") or refused or partial or applied:       # an action that ran leaves its marker: it uses up the consent
                reply = res.get("reply") or ""
                if refused:
                    reply += "\n\n(Not applied: " + "; ".join(refused) + ")"
                rec = {"ts": now(), "role": "agent", "text": reply.strip(), "applied": applied}
                if warned_map(applied):
                    rec["warned"] = warned_map(applied)
                if refused:
                    rec["refused"] = refused
                if res.get("error"):
                    rec["error"] = True       # the engine did not answer: the chat offers Retry instead of showing this as a reply
                if chat_meta.get("diagram_touched"):
                    rec["diagram_touched"] = chat_meta["diagram_touched"]
                if res.get("tools"):
                    rec["tools"] = res["tools"]
                if proposals:
                    rec["proposals"] = proposals
                kind = res.get("error_kind")
                if res.get("steps"):
                    rec["steps"] = res["steps"]
                if kind:
                    rec["error_kind"] = kind
                if res.get("retry_at"):
                    rec["retry_at"] = res["retry_at"]
                if res.get("seconds") is not None:
                    rec["seconds"] = round(float(res["seconds"]), 1)
                if kind == "idle_timeout":
                    rec["idle_seconds"] = int(workspace.get("agent.idle_timeout_seconds", 180))
                if partial:
                    rec["partial"] = True
                    rec["stopped"] = kind == "stopped"
                    rec["timed_out"] = kind in ("idle_timeout", "total_timeout")
                if res.get("denied"):
                    rec["denied"] = unique_denials(res["denied"])
                    if not partial and compound_denials(rec["denied"], rec.get("tools")) and followup_expected(
                            rec, applied, refused, turn["cancel"].is_set()):
                        rec["split_retry"] = True       # the card says so only when the follow-up is really coming
                say(proj, sess, rec)
                runlog.usage(proj, "answer", text=rec["text"], chat=sess, engine=res.get("provider") or _eng, model=res.get("model") or "",
                             seconds=rec.get("seconds"), applied=_usage_applied(applied), refused=refused, warned=rec.get("warned") or {},
                             error=(rec["text"] if res.get("error") else ""), error_kind=kind or "", ok=not res.get("error"),
                             words=len(rec["text"].split()))
                _answered.append(1)
                import background
                background.verify_record_async(proj, sess, rec["ts"], rec["text"])    # citations: checked after the reply, never before
            if not _answered:      # nothing to say and nothing applied: the usage log still gets its answer
                runlog.usage(proj, "answer", text="", chat=sess, engine=res.get("provider") or _chat_info["engine"], model=res.get("model") or "",
                             seconds=res.get("seconds"), applied=_usage_applied(applied), refused=refused, ok=not res.get("error"), words=0)
            if _answered and not partial:
                try:
                    start_followup(proj, sess, tkey, text, rec, applied, refused, turn["cancel"].is_set())
                except Exception as exc:       # never costs the reply
                    runlog.event("chat", phase="followup-end", ok=False, project=proj, error=f"{type(exc).__name__}: {exc}")
            recheck_missing(proj)
            compact_async(proj, sess)
            out = state()
            out["last_actions"] = applied
            if chat_meta.get("diagram_touched"):
                out["diagram_touched"] = chat_meta["diagram_touched"]
            return self._send(200, out)

        if path == "/api/chat/stop":
            with TURNS_LOCK:
                turn = TURNS.get((proj, sess))
            if not turn:
                return self._send(409, {"error": "nothing is running"})
            turn["cancel"].set()
            return self._send(200, {"ok": True})

        if path == "/api/chat/allow":
            try:
                rule = allow_denial(proj, sess, data.get("turn_ts"), data.get("index"))
            except KeyError as exc:
                return self._send(404, {"error": str(exc.args[0] if exc.args else exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, {"rule": rule})

        # ---- the student decides
        if path == "/api/proposal":
            try:
                decide_and_note(proj, sess, data.get("id"), data.get("decision"))
            except KeyError as exc:
                return self._send(404, {"error": str(exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, state())

        # several proposals at once ("Approve all" / "Reject all"): applied in the order given, each one
        # reported; a refused item does not stop the rest
        if path == "/api/proposals/batch":
            ids, decision = data.get("ids"), data.get("decision")
            if not isinstance(ids, list) or not ids or decision not in ("approved", "rejected"):
                return self._send(400, {"error": "ids (a list) and decision (approved or rejected) required"})
            results = []
            for pid in ids:
                try:
                    prior = next((p["status"] for p in store.proposals(proj) if p["id"] == pid), None)
                    decide_and_note(proj, sess, pid, decision, note=False, redraw_now=False)
                    results.append({"id": pid, "ok": True, **({"already": True} if prior == decision else {})})
                except (KeyError, ValueError) as exc:
                    results.append({"id": pid, "ok": False, "error": str(exc).strip("'\"")})
            done = [r["id"] for r in results if r["ok"] and not r.get("already")]      # a repeat changed nothing: not announced again
            if done:
                if decision == "approved":
                    redraw(proj)
                say(proj, sess, {"ts": now(), "role": "agent", "decision": decision, "proposal": done[0],
                                 "text": f"{'Approved' if decision == 'approved' else 'Rejected'} {len(done)} proposals: "
                                         + ", ".join(done)})
                if decision == "approved":
                    board_fit_note(proj, sess)
            out = state()
            out["results"] = results
            return self._send(200, out)

        # undo one applied change (a proposal "p..." or a sheet write "s..."): a compensating log entry
        if path == "/api/undo":
            try:
                prop = store.undo(proj, data.get("id"))
            except KeyError as exc:
                return self._send(404, {"error": str(exc).strip("'\"")})
            except ValueError as exc:             # includes store.UndoRefused: the message says what to undo first
                return self._send(409, {"error": str(exc)})
            if isinstance(prop, dict) and "mpn" in (prop.get("changes") or {}) and prop.get("line"):
                recheck_async(proj, prop["line"])
            redraw(proj)
            project_mod.touch(proj)
            say(proj, sess, {"ts": now(), "role": "agent", "decision": "undone", "proposal": data.get("id"),
                             "text": f"The student undid change {data.get('id')}; it is back to how it was."})
            return self._send(200, state())

        if path == "/api/bom/edit":
            try:
                rec = store.edit_bom(proj, data.get("line"), data.get("field"), data.get("value"))
            except KeyError as exc:
                return self._send(404, {"error": str(exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            if rec and data.get("field") in ("mpn", "lcsc"):
                recheck_async(proj, data["line"])
            if rec:
                redraw(proj)
                project_mod.touch(proj)
            return self._send(200, state())

        if path == "/api/bom/import":
            import bom_import
            target = workspace.safe_name(_text_field(data, "project")) if data.get("project") else proj
            if not project_mod.exists(target):
                return self._send(404, {"error": f"no such project: {target}"})
            try:
                csv_path = bom_import.resolve_csv(target, data.get("csv"))     # inside the Altium project or ours
                report = (bom_import.apply if data.get("apply") else bom_import.preview)(target, csv_path)
            except bom_import.PathRefused as exc:
                return self._send(403, {"error": str(exc)})
            except bom_import.BomNotEmpty as exc:
                return self._send(409, {"error": str(exc)})
            except bom_import.BomImportError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:
                return self._send(500, {"error": f"import failed: {exc}"})
            if report["applied"]:
                recheck_missing(target)
                redraw(target)
                report["state"] = model.build(project=target, session=self.session(target))
            return self._send(200, report)

        if path == "/api/parts/check":
            target_line = data.get("line")
            try:
                import check_availability
                keys = {target_line} if target_line else None
                check_availability.check(proj, keys)
            except Exception as exc:
                return self._send(500, {"error": f"check failed: {exc}"})
            return self._send(200, state())

        if path == "/api/parts/datasheet":
            target_line = data.get("line")
            if not target_line:
                return self._send(400, {"error": "line required"})
            lines = store.bom(proj, write=False)
            l = next((x for x in lines if x["key"] == target_line), None)
            if not l:
                return self._send(404, {"error": f"no BOM line {target_line!r}"})

            url = l.get("datasheet_url")
            if not url and l.get("supply"):
                url = (l["supply"].get("LCSC") or {}).get("datasheet_url")
            if not url:
                mpn = (l.get("mpn") or "").strip()
                if mpn and mpn not in ("—", "-"):
                    try:
                        import jlc
                        p = jlc.part(mpn)
                        if p and p.get("datasheet_url"):
                            url = p["datasheet_url"]
                    except Exception:
                        pass

            if not url:
                return self._send(200, {"error": "no datasheet URL for this part", "url": None})

            try:
                meta = sources.get(proj, url, name=f"{l.get('mpn') or target_line}.pdf")   # a part's datasheet lives in the project
                store.edit_bom(proj, target_line, "datasheet", meta["name"])
                return self._send(200, {"ok": True, "datasheet": meta["name"], "state": state()})
            except Exception as exc:
                return self._send(200, {"error": str(exc), "url": url})

        if path == "/api/order/check":          # asks the suppliers again: it writes the supply log, so it is not a GET
            import order_check
            try:
                return self._send(200, order_check.order_check(proj, recheck=_truthy(data.get("recheck"))))
            except Exception as exc:
                return self._send(500, {"error": str(exc)})

        if path == "/api/net-currents":             # the student's own edit applies at once; an empty amps clears the current
            from altium import bridge
            if "amps" not in data:
                return self._send(400, {"error": "amps is missing (send an empty value to clear the current)"})
            if _text_field(data, "net") not in bridge.net_current_rows(proj)["all_nets"]:
                return self._send(400, {"error": "that is not a net of this project's netlist"})
            try:
                amps = data["amps"]
                store.set_net_current(proj, _text_field(data, "net"), None if amps is None or amps == "" else amps)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, {"ok": True, **bridge.net_current_rows(proj)})
        if path == "/api/bom/propose":
            line_key = data.get("line")
            changes = data.get("changes") or {}
            reason = data.get("reason") or "Alternative part proposed"
            sources_list = data.get("sources") or []
            try:
                rec = store.propose_bom(proj, line_key, changes, reason=reason, sources=sources_list, session=sess)
                if store.may_auto_apply(rec):
                    decide_and_note(proj, sess, rec["id"], "approved", by="auto")
                say(proj, sess, {
                    "ts": now(), "role": "agent",
                    "text": f"Proposed alternative for {line_key}: {changes.get('mpn') or ''}",
                    "proposals": [rec["id"]]
                })
                return self._send(200, {**state(), "proposed": {"id": rec["id"], "footprint_lock": rec["changes"].get("footprint_lock") or "",
                                                                "lock_note": rec.get("lock_note", "")}})
            except Exception as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/pins/accept":
            if not data.get("line"):
                return self._send(400, {"error": "line required"})
            store.accept_pins(proj, data["line"])
            return self._send(200, state())

        if path == "/api/library/accept":
            entry = store.library_parts(proj).get(data.get("line"))
            if not entry:
                return self._send(404, {"error": "no such library part"})
            if not (store.passed_by_table(entry) or (entry.get("verify") == "pass" and entry.get("accepted"))):
                return self._send(400, {"error": "this part has not passed verification; a student cannot accept past a failed check"})
            store.add_library(proj, data["line"], {"accepted": True}, by="student")
            return self._send(200, state())

        if path == "/api/library/export":
            return self._send(200, export_library(proj))

        if path == "/api/library/prepare":
            import partlib
            try:
                return self._send(200, partlib.prepare(proj))
            except (OSError, ValueError) as exc:
                return self._send(500, {"error": f"the library data could not be prepared: {exc}"})

        if path == "/api/library/build":
            from altium import bridge
            busy = altium_start(proj)
            if busy:
                return self._send(409, {"error": busy})
            try:
                with runlog.span("library.build", project=proj):
                    res = bridge.build_library(proj)
            except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                return self._send(400, {"error": str(exc)})
            except OSError as exc:
                return self._send(500, {"error": f"the library build failed: {exc}"})
            finally:
                STEP_LOCK.release()
            return self._send(200, {**res, "issues_lines": library_issue_count(proj)})

        if path == "/api/skill":
            try:
                name = _text_field(data, "name")
                if name == "export_bom" and not data.get("args"):
                    data["args"] = ["generic"]
                return self._send(200, {"result": run_skill(name, proj, *[str(a) for a in data.get("args", [])]),
                                        "state": state()})
            except (ValueError, SystemExit) as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/diagram/undo":
            try:
                diag = store.undo_diagram(proj)
                out = state()
                out["ok"] = True
                out["diagram"] = diag
                return self._send(200, out)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/diagram":
            diag = data.get("diagram") if "diagram" in data else data
            try:
                valid_diag = store.validate_diagram(diag)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            idea = store.load_idea_working(proj)
            idea["diagram"] = valid_diag
            store.save_idea_draft(proj, idea)
            return self._send(200, state())

        if path == "/api/idea":
            idea = store.load_idea_working(proj)
            if "diagram" in data and isinstance(data["diagram"], dict):
                try:
                    idea["diagram"] = store.validate_diagram(data["diagram"])
                except ValueError as exc:
                    return self._send(400, {"error": str(exc)})
            if "goal" in data:
                try:
                    store.check_idea_goal(data["goal"])
                except ValueError as exc:
                    return self._send(400, {"error": str(exc)})
            for key in ("blocks", "links"):
                if key in data:
                    idea[key] = data[key]
            store.save_idea_draft(proj, idea)
            if "goal" in data:
                store.set_idea_goal(proj, data["goal"], by="student")
            return self._send(200, state())

        if path == "/api/idea/goal":
            try:
                store.set_idea_goal(proj, data.get("text", ""), by="student")
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, state())

        if path in ("/api/idea/goal/confirm", "/api/idea/goal/dismiss"):
            try:
                store.decide_idea_goal(proj, accept=path.endswith("/confirm"))
            except KeyError as exc:
                return self._send(400, {"error": str(exc).strip("'")})
            return self._send(200, state())

        if path == "/api/idea/board":      # the board size typed in directly: no confirmed idea needed (validation in the store)
            try:
                store.set_board_size(proj, data.get("width"), data.get("height"), data.get("unit") or "mm")
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, state())

        if path == "/api/idea/confirm":
            if not store.load_idea_working(proj).get("agreed"):
                return self._send(400, {"error": "add at least one requirement before confirming the idea"})
            store.confirm_idea(proj)
            return self._send(200, state())

        if path == "/api/idea/draft/save":
            store.save_idea_from_draft(proj, by="student")
            return self._send(200, state())

        if path == "/api/idea/draft/revert":
            store.revert_idea_draft(proj)
            return self._send(200, state())

        if path == "/api/idea/version/restore":
            try:
                store.restore_idea_version(proj, int(data.get("n")))
            except (TypeError, ValueError):
                return self._send(400, {"error": "n (a version number) required"})
            except KeyError as exc:
                return self._send(404, {"error": str(exc).strip("'\"")})
            return self._send(200, state())

        if path in ("/api/idea/items/accept-all", "/api/idea/items/dismiss-all"):
            store.accept_all_proposed(proj, accept=path.endswith("/accept-all"))
            return self._send(200, state())

        if path == "/api/idea/item":
            if not data.get("topic") or not data.get("text"):
                return self._send(400, {"error": "topic and text required"})
            try:
                store.propose_idea(proj, data["topic"], data["text"], by="student")
                return self._send(200, state())
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/item/update":
            index = data.get("index")
            if index is not None:
                try:
                    index = int(index)
                except (ValueError, TypeError):
                    return self._send(400, {"error": "invalid index"})
            old_topic = data.get("old_topic")
            topic = data.get("topic")
            text = data.get("text")
            if index is None and not old_topic:
                return self._send(400, {"error": "index or old_topic required"})
            if not topic or not text:
                return self._send(400, {"error": "topic and text required"})
            try:
                store.update_idea_item(proj, index=index, old_topic=old_topic, topic=topic, text=text)
                return self._send(200, state())
            except KeyError as exc:
                return self._send(404, {"error": str(exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/item/delete":
            index = data.get("index")
            if index is not None:
                try:
                    index = int(index)
                except (ValueError, TypeError):
                    return self._send(400, {"error": "invalid index"})
            topic = data.get("topic")
            if index is None and not topic:
                return self._send(400, {"error": "index or topic required"})
            try:
                deleted = store.delete_idea_item(proj, index=index, topic=topic)
                out = state()
                out["deleted"] = deleted
                return self._send(200, out)
            except KeyError as exc:
                return self._send(404, {"error": str(exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/item/confirm":
            index = data.get("index")
            if index is not None:
                try:
                    index = int(index)
                except (ValueError, TypeError):
                    return self._send(400, {"error": "invalid index"})
            topic = data.get("topic")
            try:
                store.confirm_idea_item(proj, index=index, topic=topic)
                return self._send(200, state())
            except KeyError as exc:
                return self._send(404, {"error": str(exc)})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/idea/item/move":
            from_idx = data.get("from") if "from" in data else data.get("from_index")
            to_idx = data.get("to") if "to" in data else data.get("to_index")
            if from_idx is None or to_idx is None:
                return self._send(400, {"error": "from and to required"})
            try:
                from_idx = int(from_idx)
                to_idx = int(to_idx)
                store.move_idea_item(proj, from_idx, to_idx)
                return self._send(200, state())
            except (ValueError, TypeError) as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/placement/plan":
            import preview_pcb
            plan = preview_pcb.save_placement_plan(proj, data)
            return self._send(200, {"ok": True, "plan": plan})

        if path == "/api/keeping/decision":
            dec = data.get("decision")
            if not dec:
                return self._send(400, {"error": "decision required"})
            import keeping
            res = keeping.append_decision(proj, dec, who=data.get("who", "student"),
                                          why=data.get("why", ""), source=data.get("source", ""))
            return self._send(200, {"ok": True, "entry": res})

        if path == "/api/thread/open":
            sid = open_part_session(proj, data.get("anchor") or "")
            if not sid:
                return self._send(404, {"error": "nothing to anchor a conversation to"})
            return self._send(200, {"session": sid, "sessions": session_mod.list_all(proj)})

        if path == "/api/altium/link":
            raw_path = _text_field(data, "path")
            if not raw_path:
                return self._send(400, {"error": "path required"})
            target = pathlib.Path(raw_path)
            if not target.exists():
                return self._send(400, {"error": f"path not found: {raw_path}"})
            if target.is_dir():
                prjs = [f for f in target.iterdir() if f.is_file() and f.suffix.lower() == ".prjpcb"]
                if not prjs:
                    return self._send(400, {"error": f"no .PrjPcb found in folder: {raw_path}"})
                if len(prjs) > 1:
                    return self._send(400, {"error": f"several projects found ({len(prjs)}), pick one"})
                prj_file = prjs[0].resolve()
            elif target.is_file():
                if target.suffix.lower() != ".prjpcb":
                    return self._send(400, {"error": f"not a .PrjPcb file: {target.name}"})
                prj_file = target.resolve()
            else:
                return self._send(400, {"error": f"not a .PrjPcb: {raw_path}"})

            try:
                from altium.prjpcb import read_prjpcb
                summary = read_prjpcb(prj_file)
            except Exception as exc:
                return self._send(400, {"error": f"cannot read project file: {exc}"})

            pcb_docs = summary.get("pcbs", [])
            abs_pcb_map = {}
            for rel_pcb in pcb_docs:
                abs_pcb_map[rel_pcb] = str((prj_file.parent / pathlib.Path(rel_pcb.replace("\\", "/"))).resolve())

            given_pcb = data.get("pcb_file")
            if given_pcb is not None and given_pcb != "":
                matched_pcb = None
                norm_given = os.path.normcase(os.path.normpath(str(given_pcb)))
                for rel_pcb, abs_str in abs_pcb_map.items():
                    if norm_given == os.path.normcase(os.path.normpath(abs_str)):
                        matched_pcb = abs_str
                        break
                    if norm_given == os.path.normcase(os.path.normpath(rel_pcb)):
                        matched_pcb = abs_str
                        break
                    if pathlib.Path(given_pcb).name.lower() == pathlib.Path(rel_pcb).name.lower():
                        matched_pcb = abs_str
                        break
                if not matched_pcb:
                    return self._send(400, {"error": f"'{given_pcb}' is not one of the project's PcbDocs: {pcb_docs}"})
                selected_pcb = matched_pcb
            else:
                if len(pcb_docs) == 1:
                    selected_pcb = list(abs_pcb_map.values())[0]
                else:
                    selected_pcb = ""

            given_out = data.get("outputs_dir")
            if given_out is not None and given_out != "":
                selected_outputs = str(pathlib.Path(given_out).resolve())
            else:
                selected_outputs = str((prj_file.parent / "Outputs").resolve())

            project_mod.set_altium_link(proj, project_file=str(prj_file), pcb_file=selected_pcb, outputs_dir=selected_outputs)
            return self._send(200, _altium_state(proj))

        if path == "/api/altium/unlink":
            project_mod.set_altium_link(proj, project_file="")
            return self._send(200, _altium_state(proj))

        if path == "/api/altium/create":
            from altium import bridge
            busy = altium_start(proj)
            if busy:
                return self._send(409, {"error": busy})
            try:
                with runlog.span("altium.create", project=proj):
                    res = bridge.create(proj)
            except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                return self._send(400, {"error": str(exc)})
            finally:
                STEP_LOCK.release()
            return self._send(200, {**_altium_state(proj), "warning": res.get("skeleton_error", "")})

        if path in ("/api/altium/draw-schematic", "/api/altium/place", "/api/altium/route", "/api/altium/import-rules", "/api/altium/run-outjob", "/api/altium/drc"):
            name = path.rsplit("/", 1)[1]
            step = {"draw-schematic": "draw", "import-rules": "rules", "run-outjob": "outputs"}.get(name, name)
            code, body, run_id = run_step_button(proj, sess, step, data)
            self._send(code, body)
            step_ack(proj, run_id)        # this run's record only; a page that was reloaded mid-run finds "finished" or nothing, and says so
            return

        if path == "/api/altium/step-stop":        # the Stop button of the live list: the run ends before its next step
            if not step_stop(proj):
                return self._send(409, {"error": "no button run is going on"})
            return self._send(200, {"ok": True})

        if path == "/api/update":
            code, res = apply_update()
            return self._send(code, res)

        # ---- settings, sessions, projects
        if path == "/api/config":
            changes = data.get("set") or {}
            bad = [k for k in changes if k not in SETTABLE]
            if bad:
                return self._send(400, {"error": f"not settable from here: {', '.join(bad)}"})
            if changes.get("agent.autonomy", "ask") not in store.AUTONOMY_MODES:
                return self._send(400, {"error": "agent.autonomy must be one of: " + ", ".join(store.AUTONOMY_MODES)})
            # a model name belongs to one engine, so it is stored under whichever engine is
            # current, and the engine is switched first when both arrive together
            for key in sorted(changes, key=lambda k: k != "agent.provider"):
                value = changes[key]
                if key == "agent.model":
                    key = f"agent.providers.{gateway.resolve(BACKEND)}.model"
                workspace.set_value(key, value)
            return self._send(200, {"config": _public_config()})

        if path == "/api/sessions/new":
            created = session_mod.create(proj, title=data.get("title"))
            return self._send(200, {"created": created, "sessions": session_mod.list_all(proj)})

        if path == "/api/sessions/rename":
            if not data.get("title"):
                return self._send(400, {"error": "title required"})
            session_mod.rename(proj, sess, data["title"])
            return self._send(200, {"sessions": session_mod.list_all(proj)})

        if path == "/api/sessions/delete":
            session_mod.delete(proj, data.get("session") or sess)
            return self._send(200, {"sessions": session_mod.list_all(proj),
                                    "current": session_mod.current(proj)})

        if path == "/api/memory":
            if data.get("text") is None:
                res = agent.compact(model.build(project=proj, session=sess), proj, sess, backend=BACKEND)
                return self._send(200, {"rewritten": res, "memory": session_mod.read_memory(proj, sess)})
            text, trimmed = session_mod.fit(data["text"])
            session_mod.write_memory(proj, sess, text)
            return self._send(200, {"memory": text, "trimmed": trimmed})

        if path == "/api/projects/new":
            name = _text_field(data, "name")
            if not name:
                return self._send(400, {"error": "Give the project a name"})
            wanted = workspace.safe_name(name)          # the folder name this text gives
            if project_mod.exists(wanted) and not data.get("allow_copy"):
                # never a silent "name-2": the page asks whether to open the one that is there
                return self._send(409, {"error": f"A project named \"{wanted}\" already exists.", "exists": wanted,
                                        "projects": model.list_projects()})
            created = project_mod.create(name, title=data.get("title") or name, brief=data.get("brief", ""))
            runlog.usage(created, "project", action="create", name=name, ok=True)
            out = {"created": created, "projects": model.list_projects()}
            if created != name:                         # the folder is not the text typed: say what it is
                out["folder"] = created
                spaced = re.sub(r"\s+", "-", name.strip()) == wanted           # only spaces became "-"
                out["note"] = f"The project folder is named \"{created}\"" + ("." if spaced else " (characters a folder cannot hold were changed or dropped).")
            return self._send(200, out)

        if path == "/api/projects/delete":
            name = _text_field(data, "name")
            if not name:
                return self._send(400, {"error": "name required"})
            import shutil
            proj_dir = model.project_dir(name)
            if not proj_dir.is_dir():
                return self._send(404, {"error": f"no such project: {name}"})
            with TURNS_LOCK:
                answering = any(k[0] == name for k in TURNS)
            if answering or STEP_LOCK.locked():       # a turn or an Altium step may be writing into that folder right now
                return self._send(409, {"error": "The project is busy (the agent is answering or Altium is running a step). Delete it when that has finished."})
            trash = proj_dir.parent / ".trash"        # not removed: moved aside (list_all skips dot-folders), so a mistake can be undone by hand
            trash.mkdir(exist_ok=True)
            shutil.move(str(proj_dir), str(trash / f"{proj_dir.name}-{time.strftime('%Y%m%d-%H%M%S')}"))
            projects = model.list_projects()
            default = projects[0]["name"] if projects else "demo"
            return self._send(200, {"deleted": name, "projects": projects, "default": default})

        if path == "/api/project/meta":
            meta = project_mod.load_meta(proj)
            for key in ("title", "brief", "status", "tags", "notes"):
                if key in data:
                    meta[key] = data[key]
            if isinstance(data.get("board"), dict):
                meta["board"] = {**(meta.get("board") or {}), **data["board"]}
            project_mod.save_meta(proj, meta)
            project_mod.touch(proj)
            return self._send(200, state())

        # ---- sources
        if path == "/api/upload":
            # base64 in JSON rather than multipart: the stdlib cgi module was removed in 3.13.
            # also strip what Windows refuses in a file name (: ? * " < > |)
            name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", pathlib.Path(_text_field(data, "name") or "upload.bin").name)
            blob = data.get("data_b64")
            if not blob:
                return self._send(400, {"error": "data_b64 required"})
            try:
                raw = base64.b64decode(blob)
            except Exception as exc:
                return self._send(400, {"error": f"invalid base64: {exc}"})
            if name.lower().endswith(".pdf") and not raw.startswith(b"%PDF-"):
                return self._send(400, {"error": "This file is not a valid PDF (it may be empty or damaged). Upload it again."})
            dest = model.project_dir(proj) / "sources"
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / name
            target.write_bytes(raw)
            import hashlib
            target.with_suffix(target.suffix + ".json").write_text(json.dumps(
                {"name": name, "url": None, "uploaded_at": now(), "origin": "uploaded by the student",
                 "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, indent=2), encoding="utf-8")
            found = store.auto_attach(proj)         # adopts hand-dropped files too; links and verifies the sure ones
            return self._send(200, {**state(), **found})

        if path == "/api/parts/attach_datasheet":
            try:
                res = store.attach_datasheet(proj, data.get("line") or data.get("ref") or "", data.get("name") or "")
            except (KeyError, ValueError) as exc:
                return self._send(400, {"error": str(exc.args[0] if exc.args else exc)})
            return self._send(200, {**state(), "attached": res})

        if path == "/api/parts/detach_datasheet":
            try:
                res = store.detach_datasheet(proj, data.get("line") or data.get("ref") or "")
            except KeyError as exc:
                return self._send(400, {"error": str(exc.args[0])})
            return self._send(200, {**state(), "detached": res})

        if path == "/api/fetch_source":
            url = data.get("url")
            if not url:
                return self._send(400, {"error": "url required"})
            try:
                meta = sources.get(proj, url, data.get("name"))   # added from the UI: the project's own sources
            except Exception as exc:
                return self._send(200, {"error": f"could not fetch: {exc}"})
            return self._send(200, state())

        if path == "/api/delete_source":
            name = _text_field(data, "name")
            if not name:
                return self._send(400, {"error": "name required"})
            sources.unuse(proj, name)
            return self._send(200, state())

        if path == "/api/checks/upload":
            name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", pathlib.Path(data.get("name") or "report.pdf").name)
            blob = data.get("data_b64")
            if not blob:
                return self._send(400, {"error": "data_b64 required"})
            import dfm
            kind = data.get("kind", "pcb")
            if kind not in dfm.KINDS:
                return self._send(400, {"error": f"invalid kind '{kind}': must be 'pcb', 'smt' or 'both'"})
            try:
                raw = base64.b64decode(blob)
            except Exception as exc:
                return self._send(400, {"error": f"invalid base64: {exc}"})
            if name.lower().endswith(".pdf") and not raw.startswith(b"%PDF-"):
                return self._send(400, {"error": "This file is not a valid PDF (it may be empty or damaged). Upload it again."})
            try:
                res = dfm.ingest_pdf(raw, proj, name=name, kind=kind)
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"error": f"could not ingest DFM report: {exc}"})

        if path == "/api/checks/triage":
            stem = data.get("stem")
            rows = data.get("rows")
            if not stem or rows is None:
                return self._send(400, {"error": "stem and rows required"})
            import dfm
            try:
                saved = dfm.save_triage(proj, stem, rows)
                return self._send(200, {"ok": True, "stem": stem, "triage": saved, "sig": dfm.triage_sig(saved)})
            except Exception as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/outjob/generate":
            import outjob
            res = outjob.generate_outjob(proj, filename=data.get("filename"))
            return self._send(200, res)

        if path == "/api/cpl/export":
            from skills.export_cpl import export_cpl
            res = export_cpl(proj)
            return self._send(200, res)

        if path == "/api/jlc/gerber-zip":            # build exports/<p>_gerbers.zip from the linked Altium outputs (read only)
            import jlc_upload
            unv = store.manufacturing_warning(proj)          # unverified pins block the zip
            if unv:
                return self._send(400, {"error": button_words(unv)})
            try:
                res = jlc_upload.gerber_zip(proj)
                return self._send(200, res)
            except jlc_upload.UploadError as exc:
                return self._send(400, {"error": str(exc)})
            except OSError as exc:
                return self._send(500, {"error": f"could not write the Gerber zip: {exc}"})
        if path == "/api/jlc/pickup":                # add the JLCDFM reports that are new in the Downloads folder
            import jlc_upload
            try:
                return self._send(200, jlc_upload.pickup(proj, kind=data.get("kind") or None, name=data.get("name") or None))
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
        if path == "/api/rules/extra":
            import rule_kinds
            try:
                clean_rule = rule_kinds.validate_rule(data.get("rule") or data)
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            rules_file = model.project_dir(proj) / "rules.json"
            extra = _extra_rules_save(rules_file, [clean_rule])
            return self._send(200, {"ok": True, "extra": extra})
        if path == "/api/rules/extra/enabled":      # switch one extra rule on or off (off: kept in the list, not in the .RUL)
            rules_file = model.project_dir(proj) / "rules.json"
            extra = _extra_rules_load(rules_file)
            hit = [r for r in extra if r.get("name") == data.get("name")]
            if not hit:
                return self._send(404, {"error": "no such extra rule"})
            hit[0]["enabled"] = bool(data.get("enabled"))
            rules_file.write_text(json.dumps(extra, indent=2), encoding="utf-8")
            return self._send(200, {"ok": True, "extra": extra})
        if path == "/api/rules/preset/enabled":     # switch one JLC preset rule on or off for this project
            import rules as rules_mod
            name = _text_field(data, "name")
            if name not in {r["name"] for r in rules_mod.get_jlc_preset(project_mod.board(proj)).get("rules", [])}:
                return self._send(404, {"error": "no such preset rule"})
            off = [n for n in _preset_off(proj) if n != name] + ([] if data.get("enabled") else [name])
            (model.project_dir(proj) / "rules-off.json").write_text(json.dumps(off), encoding="utf-8")
            return self._send(200, {"ok": True, "preset_off": off})
        if path == "/api/rules/extra/delete":
            rules_file = model.project_dir(proj) / "rules.json"
            extra = [r for r in _extra_rules_load(rules_file) if r.get("name") != data.get("name")]
            rules_file.write_text(json.dumps(extra, indent=2), encoding="utf-8")
            return self._send(200, {"ok": True, "extra": extra})
        if path == "/api/rules/standard":           # add the rules of a standard preset to the extra rules
            import ipc_standards
            try:
                pre = ipc_standards.preview(data.get("standard", ""), data.get("params") or data, project_mod.board(proj))
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            chosen = data.get("names")                  # the rows ticked in the preview; none given: all of them
            rows = pre["rules"] if chosen is None else [r for r in pre["rules"] if r["name"] in chosen]
            if not rows:
                return self._send(400, {"error": "choose at least one rule to add"})
            rules_file = model.project_dir(proj) / "rules.json"
            extra = _extra_rules_save(rules_file, rows)
            return self._send(200, {"ok": True, "added": [r["name"] for r in rows], "extra": extra})

        if path == "/api/calc":
            import calc
            t = data.get("type", "")
            try:
                if t == "trace_width":
                    res = calc.trace_width_ipc2221(
                        float(data.get("current", data.get("amps", 1.0))),
                        float(data.get("rise", 10.0)),
                        float(data.get("oz", 1.0)),
                        bool(data.get("internal", False)),
                    )
                elif t == "divider":
                    vin = float(data["vin"])
                    vout = float(data["vout"]) if data.get("vout") not in (None, "") else None
                    r1 = float(data["r1"]) if data.get("r1") not in (None, "") else None
                    r2 = float(data["r2"]) if data.get("r2") not in (None, "") else None
                    res = calc.voltage_divider(vin, vout=vout, r1=r1, r2=r2)
                elif t == "led":
                    res = calc.led_resistor(
                        float(data["v_supply"]),
                        float(data["v_forward"]),
                        float(data.get("i_forward_ma", data.get("i_ma", 20.0))),
                    )
                elif t == "via":
                    res = calc.via_current(
                        float(data.get("drill_mm", data.get("drill", 0.3))),
                        float(data.get("rise", 10.0)),
                        float(data.get("plating_um", calc.PLATING_UM_JLC)),
                    )
                elif t == "microstrip":
                    res = calc.microstrip_impedance(
                        float(data.get("width_mm", data.get("w", 0.3))),
                        float(data.get("height_mm", data.get("h", 0.2))),
                        float(data.get("copper_mm", 0.035)),
                        float(data.get("er", 4.4)),
                    )
                else:
                    return self._send(400, {"error": f"unknown calc type {t!r}"})
                return self._send(200, res)
            except Exception as exc:
                return self._send(400, {"error": str(exc)})

        if path == "/api/library/build_script":
            import library as lib_mod
            exports_dir = model.project_dir(proj) / "exports"
            res = lib_mod.write_library_build_package(exports_dir, proj)
            return self._send(200, {"ok": True, "files": res})

        if path == "/api/library/check_package":
            bom_pkg = data.get("bom_pkg", "")
            jlc_pkg = data.get("jlc_pkg")
            ds_text = data.get("datasheet_text")
            import library as lib_mod
            return self._send(200, lib_mod.check_package_variant(bom_pkg, jlc_pkg, ds_text))

        hit = ext.dispatch_http(ext.POST, self, path, data)     # extensions (ext.py): a path no route above matched, after the cross-site guard
        if hit:
            return self._send(*hit)
        return self._send(404, {"error": "not found"})


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port already in use
    allow_reuse_address = os.name != "nt"
    # a page load asks for some 30 files at once; with the default backlog of 5 Windows refused some of them and the page came
    # up without part of its scripts ("initLayout is not defined", seen in a live run)
    request_queue_size = 128


def _server_mode():
    """This process is the server: only it may change Altium (actions and the student's own buttons). The agent's shell,
    the bridge CLI and other processes never get this."""
    from altium import bridge
    bridge.allow_writes()


def _past_idea(project):
    """The project is past the idea stage: the idea is confirmed, or it already has a BOM or a netlist."""
    try:
        return bool(store.load_idea(project).get("confirmed") or store.bom_lines(project) or store.sheet_ids(project))
    except Exception:                           # noqa: BLE001
        return False


def readiness(project):
    """{"problems": [{id, title, fix, page?}]}: what does not work yet and the one step that fixes it. Cheap on purpose
    (a PATH lookup, a registry read, a file read); no subprocess. Altium rows show only once Altium is the next useful
    thing, so a fresh or idea-stage project (and the demo) shows only an engine problem."""
    problems = []
    try:
        ok, why = gateway.provider(gateway.resolve(BACKEND)).available()
    except Exception as exc:                    # noqa: BLE001 - a probe never breaks the page
        ok, why = False, str(exc)
    if not ok:
        problems.append({"id": "engine", "title": "The AI engine is not available" + (f" ({why})" if why else "") + ". Chat and the agent will not answer.",
                         "fix": "Open Settings, then Engine, and follow the setup there.", "page": "settings"})
    try:
        linked = bool(project_mod.altium_link(project).get("project_file"))
    except Exception:                           # noqa: BLE001
        linked = True
    drawn = bool(store.sheet_ids(project)) if hasattr(store, "sheet_ids") else False
    if sys.platform == "win32" and (linked or drawn):          # doctor rates Altium as optional: only when it is in use
        try:
            from altium import bridge
            bridge._exe()
        except Exception:                       # noqa: BLE001 - BridgeError: not found
            problems.append({"id": "altium", "title": "Altium Designer was not found, so the Make in Altium steps cannot run.",
                             "fix": "Open Settings and set the Altium folder (altium.install_path).", "page": "settings"})
    if not linked and _past_idea(project):
        problems.append({"id": "link", "title": "This project is not linked to an Altium project, so nothing can be drawn or read from Altium.",
                         "fix": "Open Altium (Settings) and link the .PrjPcb file.", "page": "settings"})
    import hashlib
    for p in problems:       # a problem that comes back with other words is a new one: a Dismiss is kept per id and instance, not per id for ever
        p["instance"] = hashlib.sha1((p["title"] + "|" + p["fix"]).encode("utf-8")).hexdigest()[:8]
    return {"problems": problems}


def port_holder(host, port, timeout=2.0):
    """Who answers on host:port: "ours" (a pcb-advisor server: /api/update has a version), "other" (answers, but is not
    one) or "silent" (nothing answers within `timeout`). Never raises."""
    import urllib.request
    probe = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    try:
        with urllib.request.urlopen(f"http://{probe}:{port}/api/update", timeout=timeout) as r:
            data = json.loads(r.read(65536).decode("utf-8", "replace"))
        return "ours" if isinstance(data, dict) and "version" in data else "other"
    except Exception as exc:                    # noqa: BLE001
        import socket
        if isinstance(exc, (socket.timeout, TimeoutError)) or isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
            return "silent"
        return "other"


EXIT_PORT_TAKEN = 78      # start.bat: not 75 (restart); it stops with the message already printed


QUIET_PATHS = ("/api/state", "/api/chat/progress", "/api/log/usage", "/api/log/client", "/api/altium/step-status", "/api/readiness")


def _cached_doctor():
    """The setup check for a report: the cached one (a fresh run is several seconds); a failure is a note in the report, not an error."""
    try:
        import doctor
        return doctor.cached()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _log_start(port, engine, available, why):
    """The start record: which version, which machine, what is configured. Looking for Altium only reads the registry; it never starts it."""
    try:
        info = runlog.start_info()
        try:
            from altium import bridge
            altium = bridge._exe()
        except Exception:
            altium = ""
        runlog.event("start", **info, port=port, engine=engine, engine_available=available, engine_problem="" if available else why,
                     model=workspace.get(f"agent.providers.{engine}.model", ""), altium_exe=altium, altium_found=bool(altium),
                     home=str(workspace.home()))
    except Exception:
        pass


def _bind_failed(exc, host, port, url, cfg, no_browser):
    """What to say, and the exit code, when the server cannot bind. Only EADDRINUSE means the port is in use."""
    import errno
    import socket
    py = r".venv\Scripts\python pcb.py" if sys.platform == "win32" else ".venv/bin/python pcb.py"
    code = getattr(exc, "winerror", None) or getattr(exc, "errno", None)
    if isinstance(exc, socket.gaierror):
        print(f"The host {host!r} is not valid ({exc}). Set server.host in the config (normally 127.0.0.1): {py} config server.host 127.0.0.1")
        return EXIT_PORT_TAKEN
    if code in (10013, errno.EACCES):
        print(f"Port {port} is reserved by Windows (Hyper-V/WSL) or not allowed; choose another: {py} serve --port {port + 1}")
        print(f"Or save it: {py} config server.port {port + 1}, then run start.bat.")
        return EXIT_PORT_TAKEN
    if code not in (10048, errno.EADDRINUSE):
        print(f"The server could not listen on {host}:{port} ({exc}).")
        return EXIT_PORT_TAKEN
    who = port_holder(host, port)
    if who == "ours":
        print(f"already running at {url}")
        if cfg["server"].get("open_browser") and not no_browser:
            webbrowser.open(url)
        return 0
    if who == "silent":
        print(f"Port {port} is held by something that does not answer. A previous pcb-advisor window may be stuck: close it, or wait a minute and run start.bat again.")
        print("Do not start a second server on the same workspace.")
        return EXIT_PORT_TAKEN
    print(f"Port {port} is used by another program that is not pcb-advisor.")
    print(f"Choose another port: {py} serve --port {port + 1}   or save it: {py} config server.port {port + 1}, then run start.bat.")
    return EXIT_PORT_TAKEN


def main(argv=None):
    global BACKEND, DEFAULT_PROJECT, QUIET, HTTPD
    RESTART["args"] = list(sys.argv[1:] if argv is None else argv)

    cfg = workspace.load()
    ap = argparse.ArgumentParser(prog="serve", description="pcb-advisor server")
    ap.add_argument("project", nargs="?", help="project to open (default: from config)")
    ap.add_argument("port", nargs="?", type=int, help="port (default: from config)")
    ap.add_argument("engine", nargs="?", help="LLM engine id (default: from config)")
    ap.add_argument("--project", dest="project_opt")
    ap.add_argument("--port", dest="port_opt", type=int)
    ap.add_argument("--engine", "--backend", dest="engine_opt")
    ap.add_argument("--host", dest="host_opt")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="do not log requests")
    a = ap.parse_args(argv)
    QUIET = a.quiet
    _server_mode()

    DEFAULT_PROJECT = workspace.safe_name(a.project_opt or a.project or cfg["server"]["default_project"])
    port = a.port_opt or a.port or int(cfg["server"]["port"])
    host = a.host_opt or cfg["server"]["host"]
    # If the user explicitly asks for an engine, use it. Otherwise None means
    # "read from config dynamically", so settings changes apply without restart.
    BACKEND = a.engine_opt or a.engine

    for key in workspace.unknown_keys():
        print(f"  warning: unknown config key {key}")

    project_mod.ensure(DEFAULT_PROJECT)
    redraw(DEFAULT_PROJECT)

    url = f"http://{host}:{port}"
    _engine = gateway.resolve(BACKEND)
    ok, why = gateway.provider(_engine).available()
    print(f"pcb-advisor  home={workspace.home()}  project={DEFAULT_PROJECT}")
    print(f"             engine={_engine}" + ("" if ok else f"  (unavailable: {why})"))
    print(f"             {url}")
    if not QUIET:
        print("             logging requests; --quiet turns this off")

    try:
        httpd = _Server((host, port), Handler)
    except (OSError, socket.gaierror) as exc:
        return _bind_failed(exc, host, port, url, cfg, a.no_browser)
    if cfg["server"].get("open_browser") and not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    HTTPD = httpd
    runlog.tee_output()           # console output also goes (capped) to logs/server-output-<day>.log for the report
    _log_start(port, _engine, ok, why)
    threading.Thread(target=check_updates, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        runlog.event("stop", reason="ctrl-c")
        return 0
    runlog.event("stop", reason="restart for update" if RESTART["go"] else "shutdown")
    if RESTART["go"]:
        httpd.server_close()
        print("updated - starting again", flush=True)
        _start_again(RESTART["args"])


if __name__ == "__main__":
    main()
