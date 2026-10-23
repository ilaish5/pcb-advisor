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
import oscompat    # noqa: E402
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
        if l.get("dnp") or l.get("nobuy"):
            row["not_bought"] = True
        sup = l.get("supply")
        row["stock"] = ("not checked" if sup is None else
                        {k: v.get("stock") for k, v in sup.items()})
        # a check runs in the background after every BOM change: run the script yourself only when this says
        # missing, or stale (older than 24 h); "checking" means wait, do not start another
        import background
        row["stock_check"] = background.stock_state(model.get("project") or "", l["key"], sup)
        bom.append(row)
    diag_summary = _compact_diagram(model.get("diagram") or (model.get("idea") or {}).get("diagram"))
    idea_summary = {k: v for k, v in (model.get("idea") or {}).items() if k in ("goal", "goal_status", "agreed", "confirmed")}
    idea_summary["diagram"] = diag_summary
    s = {
        "idea": idea_summary,
        "diagram": diag_summary,
        "totals": model.get("totals"),
        "bom": bom,
        "sheets": [{"id": sh["id"], "title": sh["title"], "parts": len(sh["parts"])} for sh in model.get("sheets", [])],
        "pending_proposals": [{"id": p["id"], "line": p["line"], "changes": p["changes"]}
                              for p in model.get("proposals", []) if p["status"] == "pending"],
        "sources": [x["name"] for x in model.get("sources", [])],
    }
    checks_summary = []
    for c in model.get("checks", []):
        stem = c.get("stem")
        if stem:
            c_dir = workspace.project_dir(model.get("project")) / "checks" / stem
            slice_paths = [f.as_posix() for f in sorted(c_dir.glob("slice_*.jpg"))]
            checks_summary.append({"stem": stem, "slices": slice_paths, "triage_count": c.get("triage_count", 0)})
    if checks_summary:
        s["dfm_checks"] = checks_summary
    return json.dumps(s, ensure_ascii=False, indent=1)


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
    lines += ["", "Scripts. Prefer these over reasoning it out yourself:"]
    for sc in w["scripts"]:
        lines.append(f"  {sc['run']}")
        lines.append(f"      {sc['what']}")
    lines += ["",
              "Reading is free: open a datasheet, grep the sources, check a value. "
              "Writing is not yours. Never edit the .jsonl logs - they are "
              "append-only and carry who decided what, and the server appends to "
              "them when you emit an action. To add a document, "
              "run " + oscompat.py("python3 {repo}/scripts/sources.py") + " so its sha256 is recorded. To view available "
              "sources, read the files in the project's sources/ directory. To delete a "
              "document, run '" + oscompat.py("python3 {repo}/scripts/sources.py unuse <project_name> <document_name>") + "'."]
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


def _parse(text):
    """Pull the actions block out; tolerate a model that forgets it."""
    blocks = re.findall(r"```json\s*(.*?)```", text, re.S)
    actions, tools = [], []
    for b in blocks:
        try:
            obj = json.loads(b)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            actions.extend(obj.get("actions", []))
            tools.extend(t for t in obj.get("tools", []) if isinstance(t, dict) and t.get("t"))
        elif isinstance(obj, list):
            actions.extend(obj)
    reply = re.sub(r"```json\s*.*?```", "", text, flags=re.S).strip()
    return reply, actions, tools


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


def respond(model, message, history, backend=None, timeout=None, on_event=None, cancel=None):
    """(state, message) -> {reply, actions}. `backend` names an engine; None
    means whatever `agent.provider` is set to."""
    name = gateway.resolve(backend)
    if name == "external":
        return {"reply": None, "actions": [], "backend": name, "provider": name}

    keep = int(workspace.get("agent.history_messages", 8))
    # a context card (role "ctx") has no text; the agent gets that context in the message itself
    history = [m for m in history if m.get("text")]
    convo = "\n".join(f"{m['role']}: {m['text']}" for m in history[-keep:])

    parts = [rules()]
    memory = (model.get("memory") or "").strip()
    if memory:
        parts.append("--- MEMORY (this conversation, kept small on purpose) ---\n"
                     + memory)
    try:
        engine_home = runtime_pack.sync()
    except runtime_pack.RuntimePackError as exc:
        return {"reply": f"[{name}] {exc}", "actions": [], "backend": name, "provider": name,
                "error": True}
    if gateway.provider(name).has_workspace():
        parts.append("--- WORKSPACE ---\n" + _workspace_section(model.get("project"), engine_home))
    parts.append("--- CURRENT STATE ---\n" + _summary(model))
    parts.append("--- CONVERSATION SO FAR ---\n" + convo)
    parts.append("--- STUDENT SAYS ---\n" + message + "\n")
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
        system=parts[0],
        history=[{"role": m.get("role"), "text": m.get("text")} for m in history[-keep:]],
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

    reply, actions, tools = _parse(res.text)
    return {"reply": reply or "(no reply)", "actions": actions, "tools": tools,
            "backend": res.provider, "provider": res.provider, "model": res.model, **turn, **took}
