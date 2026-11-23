"""
Agent adapter.

The agent is treated as a pure function:  (state, message) -> {reply, actions}.
Whatever it does while thinking, only those actions change the design, and the
SERVER applies them - one writer, and any model or runtime drops in behind this
interface without touching the rest of the tool.

An engine that lives in the workspace (a CLI agent) also gets a --- WORKSPACE ---
section: the real paths, what it may write, and the scripts worth running. An
engine without hands does not, because telling it to go and read a file does not
fail loudly, it invents.

This file owns the protocol - the rules, the state summary, and pulling the
actions block back out of the reply.  It does not own the engine: which engine
runs is `scripts/gateway/`, configured by `agent.provider`.
"""
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gateway     # noqa: E402
import runtime_pack  # noqa: E402
import session     # noqa: E402
import workspace   # noqa: E402

# The rules live as a file, not as a string in this module, so that every kind of
# agent reaches the same text: a CLI agent loads it from its engine home (see
# runtime_pack.py), and an engine without hands gets it here, in the prompt.
# runtime/AGENTS.md is the source; nothing in runtime/ is auto-loaded by any CLI.
RULES_DIR = runtime_pack.SOURCE
RULES_FILE = RULES_DIR / "AGENTS.md"


def rules():
    return runtime_pack.render("AGENTS.md", RULES_FILE.read_bytes()).decode("utf-8").strip()


RULES_POINTER = ("Your rules are AGENTS.md in your working folder (loaded at start: HARD RULES, HOW TO ANSWER, REPLY FORMAT AND ACTIONS); "
                 "they apply to this turn in full.")


def _compact_diagram(diag):
    if not isinstance(diag, dict):
        return {"shapes": [], "connectors": [], "frames": []}
    shapes_raw = diag.get("shapes", [])
    conns_raw = diag.get("connectors", [])
    frames_raw = diag.get("frames", [])

    shapes = []
    for s in shapes_raw:
        sh = {
            "id": s.get("id"),
            "type": s.get("type", "block"),
            "text": s.get("text", ""),
            "domain": s.get("domain", ""),
            "x": round(float(s.get("x", 0))),
            "y": round(float(s.get("y", 0))),
            "w": round(float(s.get("w", 0))),
            "h": round(float(s.get("h", 0))),
        }
        shapes.append(sh)

    connectors = []
    for c in conns_raw:
        f = c.get("from")
        t = c.get("to")
        f_shape = f.get("shape") if isinstance(f, dict) else str(f or "")
        t_shape = t.get("shape") if isinstance(t, dict) else str(t or "")
        connectors.append({
            "id": c.get("id"),
            "from": f_shape,
            "to": t_shape,
            "label": c.get("label", ""),
        })

    frames = []
    for fr in frames_raw:
        fx = float(fr.get("x", 0))
        fy = float(fr.get("y", 0))
        fw = float(fr.get("w", 0))
        fh = float(fr.get("h", 0))
        members = []
        for s in shapes_raw:
            sx = float(s.get("x", 0)) + float(s.get("w", 0)) / 2
            sy = float(s.get("y", 0)) + float(s.get("h", 0)) / 2
            if fx <= sx <= fx + fw and fy <= sy <= fy + fh:
                members.append(s.get("id"))
        frames.append({
            "id": fr.get("id"),
            "title": fr.get("title", ""),
            "members": members,
            "x": round(fx),
            "y": round(fy),
            "w": round(fw),
            "h": round(fh),
        })

    return {"shapes": shapes, "connectors": connectors, "frames": frames}


def _summary(model):
    """What the agent sees of the project on every turn: small, and enough to not guess."""
    bom = []
    for l in model.get("bom", []):
        row = {"line": l["key"], "refs": l.get("refs"), "value": l.get("value"), "mpn": l.get("mpn"),
               "library": l.get("library")}
        if l.get("role"):
            row["role"] = l["role"]
        if l.get("dnp") or l.get("nobuy"):
            row["not_bought"] = True
        sup = l.get("supply")
        # the JLC type and unit price the cards show, so a reply's count of Extended parts and cost matches them (RCA #39)
        jlc = (sup or {}).get("LCSC") or {}
        if l.get("library_type") or jlc.get("library_type"):
            row["jlc_type"] = l.get("library_type") or jlc.get("library_type")
        if jlc.get("unit_price") is not None:
            row["unit_usd"] = jlc.get("unit_price")
        row["stock"] = ("not checked" if sup is None else
                        {k: v.get("stock") for k, v in sup.items()})
        # a check runs in the background after every BOM change: run the script yourself only when this says
        # missing, or stale (older than 24 h); "checking" means wait, do not start another
        import background
        row["stock_check"] = background.stock_state(model.get("project") or "", l["key"], sup)
        bom.append(row)
    diag_summary = _compact_diagram(model.get("diagram") or (model.get("idea") or {}).get("diagram"))
    idea = model.get("idea") or {}
    idea_summary = {k: v for k, v in idea.items() if k in ("goal", "goal_status", "confirmed")}
    # an agreed item as the agent needs it: what, about what, who wrote it, confirmed or not (its time and earlier text are history)
    idea_summary["agreed"] = [{k: a[k] for k in ("topic", "text", "by", "status") if k in a}
                              for a in idea.get("agreed") or [] if isinstance(a, dict)]
    sources = model.get("sources", [])
    reference = [x for x in sources if x.get("origin") == "Reference library"]
    s = {
        "idea": idea_summary,
        "diagram": diag_summary,          # once: the idea's diagram is this one
        "stages": _stages(model),
        "totals": model.get("totals"),
        "bom": bom,
        "sheets": [{"id": sh["id"], "title": sh["title"], "parts": len(sh["parts"])} for sh in model.get("sheets", [])],
        "pending_proposals": [{"id": p["id"], "line": p["line"], "changes": p["changes"]}
                              for p in model.get("proposals", []) if p["status"] == "pending"],
        # the project's own documents (and shared datasheets) by name; the course/JLC/IPC reference library only as a pointer
        "sources": [x["name"] for x in sources if x.get("origin") != "Reference library"],
    }
    if reference:
        s["reference_library"] = (f"{len(reference)} course, JLC and IPC files in <repo>/shared/reference/, citable by their path "
                                  "there; open its AGENTS.md (the topic index) to find one")
    waiting = _pins_waiting(model)
    if waiting:
        # the DFM page's Unverified parts: the Gerber zip and the OutJob wait until the student resolves each (rule 7, rule 11)
        s["pins_waiting"] = waiting
    checks_summary = []
    for c in model.get("checks", []):
        stem = c.get("stem")
        if stem:
            c_dir = workspace.project_dir(model.get("project")) / "checks" / stem
            slices = sorted(f.name for f in c_dir.glob("slice_*.jpg"))
            checks_summary.append({"stem": stem, "folder": c_dir.as_posix(), "slices": slices, "triage_count": c.get("triage_count", 0)})
    if checks_summary:
        s["dfm_checks"] = checks_summary
    import ext
    ext.load()
    ext.merge(ext.SUMMARY, model.get("project") or "", s)
    return json.dumps(s, ensure_ascii=False, separators=(",", ":"))


STAGE_REASON_CUT = 240


def _pins_waiting(model):
    """The parts the manufacturing gate waits on (store.pins_to_resolve: unverified AND conflicting with the datasheet, DNP left out),
    with their status; without a project, the model's pin_decisions.remaining (unverified only)."""
    rows = None
    if model.get("project"):
        try:
            import store
            rows = store.pins_to_resolve(model["project"])
        except Exception:           # noqa: BLE001 - the state must always build
            rows = None
    if rows is None:
        rows = [dict(r, status="unverified") for r in ((model.get("pin_decisions") or {}).get("remaining") or [])]
    return [{"line": r.get("line"), "refs": r.get("refs"), "status": r.get("status")} for r in rows]


def _stages(model):
    """Where the project stands, one row per stage (stages.ORDER: idea, bom, sch, pcb, rules, outputs, checks): its state, why, and the
    next step the pages offer; a gate that holds the stage says so. Without it the agent could not name the student's next step."""
    out = []
    for st in model.get("stages") or []:
        if not isinstance(st, dict):
            continue
        row = {"id": st.get("id"), "state": st.get("state")}
        reason = str(st.get("reason") or "")
        if reason:
            row["why"] = _clip(reason, STAGE_REASON_CUT)          # head and tail: a gate reason ends with what to do
        nxt = (st.get("next") or {}).get("label")
        if nxt:
            row["next"] = nxt
        if (st.get("gate") or {}).get("blocked"):
            row["blocked"] = True
        if st.get("primary"):
            row["current"] = True          # the stage the student's pages lead with now
        out.append(row)
    return out


def _workspace_section(project, engine_home=None):
    """Only for an engine that can actually open a file. Telling a text-only
    engine to go and read something does not fail loudly - it invents."""
    w = workspace.describe(project, engine_home)
    lines = [f"You are running in {w['cwd']} (your engine home: instructions and skills only, not the repo). "
             f"The repo (the install, with scripts/ and shared/) is {w['repo']}; the workspace is {w['home']}; "
             f"the current project is {w['project']}. Every path below is absolute. "
             "<repo> in your skills means the repo path above. You may open these yourself.", ""]
    for place in w["places"]:
        write = place["write"]
        tag = "write ok" if write is True else ("read only" if write is False else write)
        lines.append(f"  {place['path']}   [{tag}]")
        lines.append(f"      {place['what']}")
    # the script catalog lives once, in AGENTS.md SCRIPTS (with <repo>); listing it here too cost ~1k tokens a turn and drifted
    lines += ["", f"Scripts: the SCRIPTS list of your rules, with <repo> = {w['repo']}; one plain command per call. "
                  "Reading is free; writing is not yours: never edit the .jsonl logs (the server appends when you emit an action); "
                  "add or drop a document only with sources.py get / unuse."]
    return "\n".join(lines)


COMPACT_RULES = """You are maintaining the memory file for one conversation with a
student designing a circuit board. Rewrite it, and return ONLY the file.

WHAT THIS FILE IS FOR
The student's decisions are recorded elsewhere and are given to the advisor in
full on every turn. Do NOT restate them here - that is wasted space. This file
holds only what the transcript would otherwise lose:

  The student's situation   constraints that are not design decisions: enclosure
                            size, budget, deadline, parts they already own, what
                            the assignment requires.
  Ruled out, and why        options considered and rejected, with the reason. This
                            is what stops the advisor proposing them again.
  Open promises             anything either side said they would come back to.
  How they work             language, level, how much detail they want.

HARD RULES
- Never put an electrical or layout rule here as if it were established. Only what
  the student said or agreed to.
- Only what the student actually said or agreed to. If you are unsure, leave it out.
- Keep the four headings exactly as they are, even if a section is empty.
- Every line is a short bullet. No prose paragraphs.

REWRITING
You are given the current memory and the messages since it was last written.
Merge them: add what is new, drop what is no longer true, merge duplicates,
and remove anything a later message overturned. Superseded entries go - this
file is the current picture, not a history.

THE LIMIT IS HARD
The result must be UNDER {limit} characters. Do not get there by cutting a line
in half: compress. Shorten wording, merge related bullets, drop the least useful
entry entirely. A shorter honest file beats a truncated one."""


def compact(model, project, sess, backend=None):
    """Rewrite one session's memory. A separate, focused call - folding this
    into the conversational turn makes it compete with answering the student,
    and it loses."""
    name = gateway.resolve(backend)
    if name == "external":
        return {"ok": False, "reason": "external engine does not write memory"}

    limit = int(workspace.get("agent.memory_max_chars", 2000))
    new = session.messages_since_compaction(project, sess)
    if not new:
        return {"ok": False, "reason": "nothing new since the last rewrite"}

    current = session.read_memory(project, sess)
    convo = "\n".join(f"{m.get('role')}: {m.get('text', '')}" for m in new)
    prompt = (COMPACT_RULES.format(limit=limit) +
              f"\n\n--- CURRENT MEMORY ({len(current)} chars) ---\n{current}\n\n"
              f"--- MESSAGES SINCE ({len(new)}) ---\n{convo}\n\n"
              f"--- RETURN THE NEW MEMORY FILE ---\n")

    import introspect
    text, attempts = "", 0
    for attempts in (1, 2):
        t0 = time.monotonic()
        res = gateway.route(gateway.Request(
            prompt=prompt,
            timeout=int(workspace.get("agent.timeout_seconds", 900)),
        ), name=name)
        introspect.record(project, sess, "memory", {"provider": res.provider or name, "model": res.model,
                                                    "usage": getattr(res, "meta", None) or {}, "error": res.error}, time.monotonic() - t0)
        if not res.ok:
            return {"ok": False, "reason": res.error, "attempts": attempts}
        text = session.normalize(_strip_fence(res.text), title=_title(project, sess))
        if len(text) <= limit:
            break
        # tell it exactly what it did, rather than cutting the text ourselves
        prompt += (f"\nYour previous attempt was {len(text)} characters, over the "
                   f"{limit} limit. Compress it further and return it again.\n")

    text, trimmed = session.fit(text, limit)
    session.write_memory(project, sess, text)
    session.mark_compacted(project, sess)
    return {"ok": True, "chars": len(text), "messages": len(new),
            "attempts": attempts, "sections_dropped": trimmed}


def _title(project, sess):
    row = next((r for r in session.load_index(project) if r["id"] == sess), {})
    return row.get("title") or sess


def _strip_fence(text):
    """Some engines wrap the file in a markdown fence. Take what is inside."""
    body = (text or "").strip()
    fenced = re.match(r"^```(?:markdown|md)?\s*\n(.*?)\n?```\s*$", body, re.S)
    return (fenced.group(1) if fenced else body).strip()


FENCE_OPEN = r"(?m)^[ \t]*```json[ \t]*\r?\n"        # exactly json (not jsonc / json5), at a line start (a list item may indent it)
FENCE_ANY = re.compile(r"```json(?!\w)(.*?)(```|\Z)", re.S)     # a fence anywhere: same line as prose, or the end of the reply


def _meant_as_actions(block):
    return re.search(r'"actions"\s*:', block) is not None


def _take(body, actions, tools):
    """Read one block's body into actions/tools. Returns None when read, else the JSON error."""
    try:
        obj = json.loads(body)
    except json.JSONDecodeError as exc:
        return exc
    if isinstance(obj, dict):
        actions.extend(obj.get("actions", []))
        tools.extend(t for t in obj.get("tools", []) if isinstance(t, dict) and t.get("t"))
    elif isinstance(obj, list):
        actions.extend(obj)
    return None


def _parse(text):
    """Pull the actions block out; tolerate a model that forgets it. Returns (reply, actions, claimed_tools, problems).
    A block with an "actions" key that cannot be read, or that was cut off before its closing fence, is a problem the
    student is told about; any other unreadable json block (an example in the explanation) is just left out."""
    text = text or ""
    pat = re.compile(FENCE_OPEN + r"(.*?)```", re.S)
    actions, tools, problems = [], [], []
    for b in pat.findall(text):
        exc = _take(b, actions, tools)
        if exc and _meant_as_actions(b):
            problems.append(f"the reply's actions block could not be read (JSON error at line {exc.lineno}); nothing in it was applied")
    reply = pat.sub("", text)
    cut = re.search(FENCE_OPEN + r".*\Z", reply, re.S)        # an opening fence that never closes: the reply was cut off
    if cut:
        if _meant_as_actions(cut.group(0)):
            problems.append("the reply's actions block was cut off before its end; nothing in it was applied")
        reply = reply[:cut.start()]
    # a fence still in the text (same line as prose): a block that reads is applied, an actions block that does not is refused,
    # anything else ("put it in a ```json fence") stays as prose
    def leftover(m):
        body = m.group(1).strip()
        exc = _take(body, actions, tools)
        if exc is None:
            return ""
        if _meant_as_actions(body):
            problems.append("the reply's actions block was cut off before its end; nothing in it was applied" if not m.group(2) else
                            f"the reply's actions block could not be read (JSON error at line {exc.lineno}); nothing in it was applied")
            return ""
        return m.group(0)
    reply = FENCE_ANY.sub(leftover, reply)
    return reply.strip(), actions, tools, problems


def _script_stem(s):
    s = str(s).lower()
    return re.sub(r"\.py$", "", s)


def real_tools(meta, claimed=()):
    """Tool chips. An engine that reports its steps (meta["stream"]): the chips are its real runs of the tool's own
    scripts (denied: warn, failed: bad), each keeping the detail `d` of the model's claimed chip for the same script;
    a claim with no real run is dropped. An engine with no step stream: the model's claims, marked "claimed" (unconfirmed)."""
    from gateway import events
    meta = meta or {}
    claimed = [c for c in claimed or [] if isinstance(c, dict) and c.get("t")]
    if not meta.get("stream"):
        return [{**c, "s": "claimed"} for c in claimed]
    denied = {events.label(d.get("tool"), d.get("input")) for d in meta.get("denied") or [] if isinstance(d, dict)}
    free = list(claimed)
    out = []
    for r in meta.get("runs") or []:
        lab = r["label"]
        script = re.search(r"([\w.-]+\.py)", lab)
        st = "warn" if lab in denied else "bad" if r.get("failed") else "ok"       # a denied call also reports an error: denied first
        chip = {"t": events.human(lab), "st": st}      # the student reads "Searching JLC"; the command line stays in "raw", under details
        if chip["t"] != lab:
            chip["raw"] = lab
        if script and st == "ok":
            want = _script_stem(script.group(1))
            for c in free:      # each claim once, in order, on the whole script name (check.py is not check_stock.py)
                names = {_script_stem(w) for w in re.findall(r"[\w.-]+", f"{c.get('t')} {c.get('d', '')}")}
                if want in names:
                    free.remove(c)
                    if c.get("d"):
                        chip["d"] = c["d"]
                    break
        out.append(chip)
    return out


def _add_dirs(project):
    """What the engine may reach outside its own folder: the install (scripts, reference),
    the project, and the workspace when that is somewhere else."""
    dirs = [workspace.REPO, workspace.project_dir(project), workspace.home()]
    out = []
    for d in dirs:
        if str(d) not in out:
            out.append(str(d))
    proj_name = project or workspace.default_project()
    if proj_name:
        import project as project_mod
        link = project_mod.altium_link(proj_name)
        p_file = link.get("project_file")
        if p_file:
            folder = pathlib.Path(p_file).parent
            if folder.is_dir() and str(folder) not in out:
                out.append(str(folder))
    return out


HEBREW = re.compile("[\u0590-\u05ff]")
LATIN = re.compile("[A-Za-z]{2,}")
NOTE_KEEP = 2            # server notes (button steps, approvals) kept as context; they never use up the conversation window
CLIP_USER, CLIP_AGENT, CLIP_NOTE = 600, 900, 220


def _clip(text, n):
    """Cut to n characters keeping the HEAD (40%) and the TAIL (60%): the end of an agent message is its question, the end of a long
    student spec its last requirement; a plain 'keep the start' lost both."""
    text = str(text or "").strip()
    if len(text) <= n:
        return text
    head = int((n - 1) * 0.4)
    return text[:head].rstrip() + "…" + text[len(text) - (n - 1 - head):].lstrip()


def _last_agent(turns):
    return turns[-1] if turns and turns[-1].get("role") == "agent" else None


def _turn_text(m, last_agent):
    """A turn's text for the prompt, clipped; the agent message right before the student's latest message is never clipped (it holds
    the question the student's 'yes' answers)."""
    if m is last_agent:
        return str(m.get("text") or "").strip()
    return _clip(m.get("text"), CLIP_USER if m.get("role") == "user" else CLIP_AGENT)


def _request_history(history, keep):
    turns = [m for m in history if not is_note(m)][-keep:]
    last_agent = _last_agent(turns)
    return [{"role": m.get("role"), "text": _turn_text(m, last_agent)} for m in turns]


def is_note(m):
    """A record the server wrote for the agent's context (a button step, an approval), not a turn of the conversation."""
    return m.get("role") == "agent" and bool(m.get("by") or m.get("decision"))


def history_lines(history, keep):
    """The 'conversation so far': the last `keep` real turns, each clipped, plus at most NOTE_KEEP of the latest server
    notes as one-liners. Notes ("Approved 3 proposals", "Placed the parts ... because the student pressed the button") used to
    fill the window, so the agent saw its own log and little of what the student said."""
    history = [m for m in history if m.get("text")]       # a context card (role "ctx") has no text
    turns = [m for m in history if not is_note(m)]
    turns = turns[-keep:] if keep > 0 else []
    if not turns:
        return ""
    first = history.index(turns[0])
    notes = [m for m in history[first:] if is_note(m)][-NOTE_KEEP:]
    keep_ids = {id(m) for m in turns} | {id(m) for m in notes}
    last_agent = _last_agent(turns)
    out = []
    for m in history[first:]:
        if id(m) not in keep_ids:
            continue
        if is_note(m):
            out.append(f"note: {_clip(m['text'], CLIP_NOTE)}")
        else:
            out.append(f"{m['role']}: {_turn_text(m, last_agent)}")
    return "\n".join(out)


MIN_LETTERS = 3          # a message with fewer letters of either script ("ok", "R5 100k") says nothing about the language


def _message_language(text):
    he = len(re.findall("[֐-׿]", text or ""))
    en = len(re.findall("[A-Za-z]", text or ""))
    if max(he, en) < MIN_LETTERS:
        return ""
    return "he" if he >= en else "en"


def student_language(typed, history=(), generated=False):
    """'he' / 'en' / '' for the student's own words: the last message the student TYPED that has enough letters. A generated message
    (a button, the DFM auto-list) is skipped, and so is a short one. Nothing found: English for a typed message, '' for a generated one.
    One rule for the agent's language line and for the server's own lines (corrections, stop lines)."""
    if not generated:
        found = _message_language(typed)
        if found:
            return found
    for m in reversed(list(history or [])):
        if m.get("role") == "user" and not m.get("generated") and m.get("text"):
            found = _message_language(str(m["text"]))
            if found:
                return found
    return "" if generated else "en"


def language_code(typed, history=(), generated=False):
    """'he' / 'en' / '': Settings > Language when it is set, else student_language()."""
    setting = str(workspace.get("user.language", "auto") or "auto").lower()
    if setting in ("he", "hebrew", "iw"):
        return "he"
    if setting in ("en", "english"):
        return "en"
    return student_language(typed, history, generated)


def reply_language_line(typed, history=(), generated=False):
    """The language the reply must be in, always stated (the model drifted when it was left to infer it).
    Settings > Language: 'he' or 'en' is final. 'auto' (default) follows the student's last TYPED message: Hebrew letters mean
    Hebrew, otherwise English. A button-generated prompt (generated=True) is skipped: the last typed message in `history` counts.
    Hebrew replies address the student in the singular, as one person."""
    lang = {"he": "Hebrew", "en": "English"}.get(language_code(typed, history, generated), "")
    if not lang:
        return ""
    line = f"Reply language: {lang}\n"
    if lang == "Hebrew":
        line += "Address the student in the singular, as one person (never a plural 'you').\n"
    return line


REMINDER = (
    "Before you answer: the answer first, short (40-60 words, 100 at most), to one person. Facts only from <current_state>, a script you "
    "ran this turn or a cited source; otherwise \"unknown\", and \"planned\" for anything on the board that board_facts did not measure. "
    "End with the one next action of the `current` stage. Actions go in ONE closed ```json block at the end; say only what that block "
    "starts, never a promise of a later reply. Draw, place, route and replace only on the student's own words (HARD RULES, REPLY FORMAT).\n")


def _tag(name, body, note=""):
    return f"<{name}{f' note={json.dumps(note)}' if note else ''}>\n{body}\n</{name}>"


def respond(model, message, history, backend=None, timeout=None, on_event=None, cancel=None, typed=None, generated=False,
            from_server=False):
    """(state, message) -> {reply, actions}. `backend` names an engine; None
    means whatever `agent.provider` is set to. `typed` = the student's own text without the context the server adds.
    `from_server`: the message is the server's follow-up or retry note, not the student's words (tagged so)."""
    name = gateway.resolve(backend)
    if name == "external":
        return {"reply": None, "actions": [], "backend": name, "provider": name}

    keep = int(workspace.get("agent.history_messages", 8))
    # a context card (role "ctx") has no text; the agent gets that context in the message itself
    history = [m for m in history if m.get("text")]
    convo = history_lines(history, keep)

    try:
        engine_home = runtime_pack.sync()
    except runtime_pack.RuntimePackError as exc:
        return {"reply": f"[{name}] {exc}", "actions": [], "backend": name, "provider": name,
                "error": True}
    # Stable first, dynamic last, each section in a named tag the rules refer to; the task and a short reminder close the prompt.
    # An engine with a workspace already loaded AGENTS.md from its engine home (CLAUDE.md -> @AGENTS.md, agy: AGENTS.md; proven by
    # `pcb.py probe`), in its cached context: sending it again in the prompt cost ~7.5k tokens a turn. A text-only engine gets it here.
    has_ws = gateway.provider(name).has_workspace()
    parts = [RULES_POINTER if has_ws else rules()]
    if has_ws:
        parts.append(_tag("workspace", _workspace_section(model.get("project"), engine_home)))
    memory = (model.get("memory") or "").strip()
    if memory:
        parts.append(_tag("memory", memory, "this conversation, kept small on purpose"))
    parts.append(_tag("current_state", _summary(model)))
    parts.append(_tag("conversation", convo))
    if from_server:      # a follow-up or retry round: the server reports what really happened; the student did not write this
        parts.append(_tag("server_message", message))
    else:
        parts.append(_tag("student_message", message))
    parts.append(_tag("reminder", REMINDER + reply_language_line(message if typed is None else typed, history, generated).strip()))
    prompt = "\n\n".join(parts)

    # The engine lives in its own folder, where only the instructions and skills are (sync() above).
    # The repo, the project and the workspace are reachable only through add_dirs.
    options = {"cwd": str(engine_home), "add_dirs": _add_dirs(model.get("project")),
               "idle_timeout": int(workspace.get("agent.idle_timeout_seconds", 180))}
    if on_event:
        options["on_event"] = on_event
    if cancel is not None:
        options["cancel"] = cancel
    t0 = time.monotonic()
    res = gateway.route(gateway.Request(
        prompt=prompt,
        system=rules(),
        history=_request_history(history, keep),
        timeout=int(timeout or workspace.get("agent.timeout_seconds", 900)),
        options=options,
    ), name=name)

    meta = getattr(res, "meta", None) or {}
    took = {"seconds": time.monotonic() - t0, "usage": meta}   # introspect.py keeps these per turn
    turn = {k: meta[k] for k in ("steps", "denied", "error_kind", "retry_at") if meta.get(k)}
    if meta.get("partial"):
        # stopped or timed out: keep what was written, trust no half-written actions block
        reply = re.sub(r"```json.*?(```|$)", "", res.text or "", flags=re.S).strip()
        out = {"reply": reply, "actions": [], "tools": [], "partial": True,
               "backend": res.provider or name, "provider": res.provider or name, "model": res.model,
               **turn, **took}
        if meta.get("error_kind") in ("total_timeout", "idle_timeout"):
            # a turn that ran out of time answered nothing: an error with the Retry path, not a quiet success
            why = ("The agent ran out of time (%d s)" % int(timeout or workspace.get("agent.timeout_seconds", 900))
                   if meta["error_kind"] == "total_timeout" else f"The agent stopped answering ({res.error})")
            out["reply"] = (reply + "\n\n" if reply else "") + f"[{res.provider or name}] {why}; no actions were applied (files the agent produced with tools before the timeout may remain)."
            out["error"] = True
        return out
    if not res.ok:
        return {"reply": f"[{res.provider or name}] {res.error}", "actions": [],
                "backend": res.provider or name, "provider": res.provider or name,
                "error": True, **turn, **took}

    reply, actions, claimed, problems = _parse(res.text)
    return {"reply": reply or "(no reply)", "actions": actions, "tools": real_tools(meta, claimed), "parse_refused": problems,
            "backend": res.provider, "provider": res.provider, "model": res.model, **turn, **took}
