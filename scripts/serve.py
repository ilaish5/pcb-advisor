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
import json
import mimetypes
import os
import pathlib
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "skills"))
import agent             # noqa: E402
import gateway           # noqa: E402
import model             # noqa: E402
import project as project_mod  # noqa: E402
import session as session_mod  # noqa: E402
import sources           # noqa: E402
import tool_guard        # noqa: E402
import store             # noqa: E402
import workspace         # noqa: E402

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


def _turn_start(key):
    t = time.time()
    turn = {"started": t, "last": t, "steps": [], "current": None, "cancel": threading.Event()}
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


def _turn_end(key):
    with TURNS_LOCK:
        TURNS.pop(key, None)


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


def decide_and_note(project, sess, pid, decision, by="student", note=True, redraw_now=True):
    """Approve or reject one proposal and do what follows (supply re-check, sheet labels, a note the engine
    reads). The click, the batch endpoint and the autonomy setting all come through here, so the logs are
    the same whoever decided; only `by` differs."""
    store.decide(project, pid, decision, by=by)
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
    return prop


ALTIUM_ACTIONS = ("altium.create_project", "altium.add_sheet", "altium.skeleton", "altium.add_pcb", "altium.open",
                  "altium.import_rules", "altium.run_outjob")      # (+ altium.draw_schematic, altium.place_pcb, altium.route_pcb: each has its own consent guard)


def library_issue_count(project):
    """How many lines of the part library manifest still carry an issue."""
    return sum(1 for e in store.library_manifest(project).values() if e.get("issues") or e.get("built_issues"))


def _truthy(v):
    """A flag from JSON or a model: true, 1, "true", "yes" are on; "false", "0", "", None are off."""
    return v is True or v == 1 or str(v).strip().lower() in ("1", "true", "yes", "on")


def _bridge_done(project, op, since):
    """The newest altium-log.jsonl entry of `op` that succeeded at or after `since` (epoch seconds), else None: a model
    that ran bridge.py itself in its shell has already done what the action would do."""
    if not since:
        return None
    floor = dt.datetime.fromtimestamp(since).isoformat(timespec="seconds")
    ok = [r for r in store.read_jsonl(store.pdir(project) / "altium-log.jsonl")
          if r.get("op") == op and "error" not in r and str(r.get("ts", "")) >= floor]
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
REDRAW_WORD = re.compile(r"replace|redraw|re-draw|overwrite|start over|מחדש|תחליף|תמחק|להחליף", re.I)
ASK_FIRST = "Ask the student first: draw the schematic themselves in Altium, or should you draw it? Run this only after their answer, with student_said = a quote of it."


SELF_PLACE = re.compile(r"myself|\bi[\u2019']?ll place|i will place|\bi place|\bi[\u2019']?ll do the placement|בעצמי|אני אמקם|אמקם אני"
                        r"|\bdon[\u2019']?t place|\bdo not place|אל תמקם|לא למקם|לא תמקם|אני לא רוצה ש", re.I)
SELF_ROUTE = re.compile(r"myself|\bi[\u2019']?ll route|i will route|\bi route|\bi[\u2019']?ll do the routing|בעצמי|אני אנתב|אנתב אני"
                        r"|\bdon[\u2019']?t route|\bdo not route|אל תנתב|לא לנתב|לא תנתב|אני לא רוצה ש", re.I)
REPLACE_WORD = re.compile(r"replace|redo|overwrite|start over|re-?place|re-?route|מחדש|תחליף|תמחק|להחליף|תמקם מחדש|תנתב מחדש", re.I)
ASK_PLACE = ("Ask the student first: place the parts on the board themselves in Altium, or should you place them? "
             "Run this only after their answer, with student_said = a quote of it.")
ASK_ROUTE = ("Ask the student first: route the board themselves in Altium, or should you route it? This is a separate question from "
             "placing the parts. Run this only after their answer, with student_said = a quote of it.")
PLACE_WORD = re.compile(r"\bplac(?:e|ing|ement)\b|\bposition|lay ?out|מקם|תמקם|למקם|אמקם|מיקום|השמה|פלייסמנט", re.I)
ROUTE_WORD = re.compile(r"\brout(?:e|ing)\b|auto-?rout|נתב|תנתב|לנתב|אנתב|ניתוב|ראוט", re.I)
CONSENT = {   # kind -> (they do it themselves, they say replace, ask text, what replace wipes, what it is, a word their message must have)
    "draw": (SELF_DRAW, REDRAW_WORD, ASK_FIRST, "sheet", "draw it", None),
    "place": (SELF_PLACE, REPLACE_WORD, ASK_PLACE, "board's parts and copper", "place them", PLACE_WORD),
    "route": (SELF_ROUTE, REPLACE_WORD, ASK_ROUTE, "board's tracks", "route it", ROUTE_WORD),
}


PARTIAL_WORD = re.compile(r"partial|חלקי|מה שאפשר|what you can", re.I)       # a yes to "keep a half-routed board" says so in the words


def _partial_consent(a, last_user):
    """Keeping a half-routed board needs partial: true and partial_said = the student's own words, and those words say partial."""
    said = a.get("partial_said")
    return (_truthy(a.get("partial")) and bool(said) and _quote_holds(said, last_user)
            and PARTIAL_WORD.search(str(said)) is not None)


def _consent(kind, a, last_user):
    """'' when the student's last message really asked the agent to do `kind` ("draw" the schematic, "place" the parts, "route" the
    board) or, for replace, to do it over what is there, else why not. The quote must be most of their message (a fragment of "I'll
    draw it myself" is not a yes), and a message that says they do it themselves is never one. "לבד" is not a negation: "תשרטט לבד"
    = you draw it. Placing and routing are separate questions: each action needs its own answer."""
    self_re, replace_re, ask, wipes, verb, need = CONSENT[kind]
    norm = lambda t: re.sub(r"\s+", " ", str(t or "").lower()).strip(" .,!?;:()-\"'")
    q, u = norm(a.get("student_said")), norm(last_user)
    if not _quote_holds(a.get("student_said"), last_user) or len(q) < 0.5 * len(u):
        return ask
    if need is not None and not need.search(u):        # "yes" to the schematic question is not a yes to placing or routing
        return ask
    if self_re.search(u):
        return f"The student said they will do it themselves. Do not {verb.split()[0]}; help them with the manual steps."
    if _truthy(a.get("replace")):
        r = norm(a.get("replace_said"))
        # the replace word itself is a short quote ("מחדש"): whole words of their message are enough here
        if not r or not replace_re.search(r) or re.search(r"(?<!\w)" + re.escape(r) + r"(?!\w)", u) is None:
            return (f"The {wipes} are only wiped when the student says so: ask whether what is there may be replaced, then run this with "
                    "replace_said = a quote of their words (replace, redo, overwrite, start over / מחדש, תחליף, תמחק).")
    return ""


def _draw_consent(a, last_user):
    return _consent("draw", a, last_user)


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


def apply_actions(project, actions, sess=None, last_user="", meta=None, turn_start=None):
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
        if not store.may_auto_apply(rec):
            return
        try:
            decide_and_note(project, sess, rec["id"], "approved", by="auto", note=False, redraw_now=False)
            auto_done.append(rec)
        except (ValueError, KeyError) as exc:
            refused.append(f"auto-apply of {rec['id']} failed, it waits for you: {exc}")

    for a in actions or []:
        if not isinstance(a, dict):
            continue
        kind = a.get("type")
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
                applied.append(f"bom.propose:{a['line']}")
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
                res = store.write_sheet_logged(project, a["sheet"], a["data"])
                if res["ok"]:
                    note = f" (warnings: {'; '.join(res['warnings'][:8])})" if res.get("warnings") else ""
                    applied.append(f"netlist.write:{res['sheet']}{note}")
                else:
                    refused.append(f"netlist.write:{a['sheet']} refused: " + "; ".join(res["errors"][:8]))
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
                issues = library_issue_count(project)
                applied.append(f"{kind}: {res['built']} of {res['lines']} lines built, IntLib installed"
                               + (f" ({issues} with issues)" if issues else "") + "".join(" " + n for n in res.get("notices", [])))
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
                why = _draw_consent(a, last_user)
                if why:
                    refused.append(f"{kind}: not run. {why}")
                    continue
                try:
                    res = bridge.draw_schematic(project, a.get("sheet") or None, replace=_truthy(a.get("replace")))
                except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
                    refused.append(f"{kind}: {exc}")
                    continue
                applied.append(f"{kind}: {res['parts']} parts and {len(res['nets'])} nets drawn on {len(res['sheets'])} sheet(s), "
                               "saved and checked against the netlist"
                               + (f" ({len(res['warnings'])} warnings: {'; '.join(res['warnings'][:4])})" if res["warnings"] else ""))
            elif kind in ("altium.place_pcb", "altium.route_pcb"):
                # the agent places / routes the board in Altium only when the student said so in their own words, separately for
                # each (asked first: do it yourself or should I?). replace needs that too and never happens by default.
                from altium import bridge
                step = "place" if kind == "altium.place_pcb" else "route"
                why = _consent(step, a, last_user)
                if why:
                    refused.append(f"{kind}: not run. {why}")
                    continue
                try:
                    if step == "place":
                        res = bridge.place_pcb(project, replace=_truthy(a.get("replace")))
                    else:
                        keep = _partial_consent(a, last_user)
                        res = bridge.route_pcb(project, replace=_truthy(a.get("replace")), keep_partial=keep)
                except (bridge.BridgeError, bridge.AltiumReadError, OSError) as exc:
                    refused.append(f"{kind}: {exc}")
                    continue
                if step == "place":
                    applied.append(f"{kind}: {len(res['placed'])} parts placed" + (", outline created" if res["outline_created"] else ", outline kept")
                                   + ", saved and checked against the netlist"
                                   + (f" ({len(res['warnings'])} warnings: {'; '.join(res['warnings'][:4])})" if res["warnings"] else ""))
                else:
                    applied.append(f"{kind}: {res['summary']}"
                                   + (f" ({len(res['warnings'])} warnings: {'; '.join(res['warnings'][:4])})" if res.get("warnings") else ""))
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
                    applied.append(f"{kind}: {len(res['created'])} added, {len(res['updated'])} updated"
                                   + (f", {len(res['skipped'])} skipped ({', '.join(x['name'] for x in res['skipped'])})" if res["skipped"] else "")
                                   + (f", not confirmed: {', '.join(res['unconfirmed'])}" if res["unconfirmed"] else "")
                                   + (f". {res['message']}" if res.get("message") else ""))
                    continue
                elif kind == "altium.run_outjob":
                    done = _bridge_done(project, "run-outjob", turn_start)
                    if done:
                        applied.append(f"{kind}: already done earlier in this turn ({done.get('files', 0)} files)")
                        continue
                    try:
                        res = bridge.run_outjob(project)
                    except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                        refused.append(f"{kind}: {exc}")
                        continue
                    applied.append(f"{kind}: {len(res['files'])} files" + (" (OutJob added to the project)" if res["added"] else "")
                                   + "".join(f". WARNING: {w}" for w in res.get("warnings", [])))
                    continue
                else:
                    bridge.open_project(project)
                applied.append(kind + (f":{a['name']}" if kind == "altium.add_sheet" else ""))
            elif kind == "jlc.gerber_zip":
                import jlc_upload
                try:
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
                refused.append(f"{kind}: not a known action, or fields missing")
        except (ValueError, KeyError) as exc:
            refused.append(f"{kind}: {exc}")
    if any(x.startswith("netlist") for x in applied) or any(r.get("kind") != "idea_diagram" for r in auto_done):
        redraw(project)
    if auto_done and sess:
        say(project, sess, {"ts": now(), "role": "agent", "decision": "approved", "proposal": auto_done[0]["id"],
                            "text": f"Applied without asking ({store.autonomy()} mode, the student can undo): "
                                    + ", ".join(r["id"] for r in auto_done)})
    return applied, proposals, refused


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
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

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
        """A project file another program holds open (Windows: an editor) is an answer, not a dropped connection."""
        try:
            return fn()
        except PermissionError as exc:              # a Windows sharing violation; a missing file or a socket error is not
            if not exc.filename:
                raise
            name = pathlib.Path(exc.filename).name
            return self._send(423, {"error": f"{name} is open in another program ({exc.filename}); close it and try again"})

    def _get(self):
        path = self.path.split("?")[0]
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
        if path == "/api/doctor":                  # the same list as `pcb.py doctor --json`; ?refresh=1 runs it again
            import doctor
            return self._send(200, doctor.cached(refresh=bool(self.query("refresh"))))
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
            return self._send(200, {"unverified": store.unverified_parts(self.project())})
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
        if path == "/api/jlc/gerber-zip":            # the zip made last time (files, when written, what is missing); nothing is built
            import jlc_upload
            return self._send(200, jlc_upload.zip_info(self.project()))
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
                missing_in_pcb = bridge.rules_missing(proj)      # what Import would write that the PcbDoc file lacks
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
                    res = calc.trace_width_ipc2152(
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
                        float(q.get("plating_um", 25.0)),
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
        return self._send(404, {"error": "not found"})

    # ---------------------------------------------------------------- write
    def _post(self):
        path = self.path.split("?")[0]
        proj = self.project()
        sess = self.session(proj)

        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})

        def state():
            return model.build(project=proj, session=sess)

        # ---- the conversation
        if path == "/api/chat":
            text = (data.get("text") or "").strip()
            if not text:
                return self._send(400, {"error": "text required"})
            source_file = data.get("file") or data.get("source")
            about = None if source_file else chat_about(data.get("about"))
            tkey = (proj, sess)
            with TURNS_LOCK:
                running = tkey in TURNS
            if running:            # before saving: the client queue resends it, so it must not be stored twice
                return self._send(409, {"error": "this conversation is still answering"})
            user_msg = {"ts": now(), "role": "user", "text": text}
            if source_file:
                user_msg["source"] = source_file
            if about:
                user_msg["about"] = about
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
            turn = _turn_start(tkey)
            guard = tool_guard.begin()
            BUSY["chat"] += 1
            tool_edited, tool_unrestored = [], []
            try:
                res = agent.respond(m, ask, m["chat"][:-1], backend=BACKEND, cancel=turn["cancel"],
                                    on_event=lambda ev, k=tkey: _turn_event(k, ev))
            finally:
                BUSY["chat"] -= 1
                _turn_end(tkey)
                tool_edited, tool_unrestored = tool_guard.end(guard)     # the agent never keeps an edit of the tool's own files
            if tool_edited or tool_unrestored:
                print(f"[guard] the agent edited system files: restored {tool_edited}, not restorable {tool_unrestored}", file=sys.stderr, flush=True)
            chat_meta = {}
            partial = bool(res.get("partial"))
            if partial:      # a half-written actions block is not trusted
                applied, proposals, refused = [], [], []
            else:
                applied, proposals, refused = apply_actions(proj, res.get("actions"), sess, last_user=text, meta=chat_meta,
                                                           turn_start=turn["started"])
            if tool_edited or tool_unrestored:
                refused.append(tool_guard.refusal(tool_edited, tool_unrestored))
            if res.get("provider") != "external":         # an outside driver is not an engine turn
                import introspect
                introspect.record(proj, sess, "chat", res, res.get("seconds") or 0, reply=res.get("reply") or "",
                                  applied=len(applied), proposed=len(proposals), refused=len(refused))
            if res.get("reply") or refused or partial:
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
                say(proj, sess, rec)
                import background
                background.verify_record_async(proj, sess, rec["ts"], rec["text"])    # citations: checked after the reply, never before
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
                    decide_and_note(proj, sess, pid, decision, note=False, redraw_now=False)
                    results.append({"id": pid, "ok": True})
                except (KeyError, ValueError) as exc:
                    results.append({"id": pid, "ok": False, "error": str(exc).strip("'\"")})
            done = [r["id"] for r in results if r["ok"]]
            if done:
                if decision == "approved":
                    redraw(proj)
                say(proj, sess, {"ts": now(), "role": "agent", "decision": decision, "proposal": done[0],
                                 "text": f"{'Approved' if decision == 'approved' else 'Rejected'} {len(done)} proposals: "
                                         + ", ".join(done)})
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
            target = workspace.safe_name(data["project"]) if data.get("project") else proj
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
            if entry.get("verify") != "pass":
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
            try:
                res = bridge.build_library(proj)
            except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                return self._send(400, {"error": str(exc)})
            except OSError as exc:
                return self._send(500, {"error": f"the library build failed: {exc}"})
            return self._send(200, {**res, "issues_lines": library_issue_count(proj)})

        if path == "/api/skill":
            try:
                name = data.get("name")
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
            raw_path = (data.get("path") or "").strip()
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
            try:
                res = bridge.create(proj)
            except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, {**_altium_state(proj), "warning": res.get("skeleton_error", "")})

        if path in ("/api/altium/import-rules", "/api/altium/run-outjob"):
            from altium import bridge
            try:
                res = bridge.import_rules(proj) if path.endswith("rules") else bridge.run_outjob(proj)
            except (bridge.BridgeError, bridge.AltiumReadError) as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(200, res)

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
            name = (data.get("name") or "").strip() or "untitled"
            created = project_mod.create(name, title=data.get("title") or name, brief=data.get("brief", ""))
            return self._send(200, {"created": created, "projects": model.list_projects()})

        if path == "/api/projects/delete":
            name = (data.get("name") or "").strip()
            if not name:
                return self._send(400, {"error": "name required"})
            import shutil
            proj_dir = model.project_dir(name)
            if proj_dir.exists():
                shutil.rmtree(proj_dir)
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
            name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", pathlib.Path(data.get("name") or "upload.bin").name)
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
            name = data.get("name")
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
            try:
                return self._send(200, jlc_upload.gerber_zip(proj))
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
            name = data.get("name")
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
                    res = calc.trace_width_ipc2152(
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
                        float(data.get("plating_um", 25.0)),
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

        return self._send(404, {"error": "not found"})


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port already in use
    allow_reuse_address = os.name != "nt"


def _server_mode():
    """This process is the server: only it may change Altium (actions and the student's own buttons). The agent's shell,
    the bridge CLI and other processes never get this."""
    from altium import bridge
    bridge.allow_writes()


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
    except OSError:
        print(f"already running at {url}")
        if cfg["server"].get("open_browser") and not a.no_browser:
            webbrowser.open(url)
        return 0
    if cfg["server"].get("open_browser") and not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    HTTPD = httpd
    threading.Thread(target=check_updates, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    if RESTART["go"]:
        httpd.server_close()
        print("updated - starting again", flush=True)
        _start_again(RESTART["args"])


if __name__ == "__main__":
    main()
