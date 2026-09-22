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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gateway     # noqa: E402
import session     # noqa: E402
import workspace   # noqa: E402

RULES = """You are the PCB design advisor. You walk a student down a decision cascade.

HARD RULES
- Never invent a design constraint. Constraints come only from the authored
  cascade; the server attaches them automatically when a decision is recorded.
- You may explain, compare options, and recommend. You must never choose for
  the student.
- If something is outside the design questions you have, say so plainly instead
  of improvising a rule - and say it in the student's terms: "this has no cited
  source, it is my engineering judgement." Never by naming a file, a line number
  or an option id.
- Do not recall part numbers, pinouts or stock levels from memory. `documents`
  in CURRENT STATE lists what is already on disk; if what you need is not there,
  say so rather than remembering it.
- A quote counts only if you have seen it in the document. Say which document
  and where, so the student can check you.

VOCABULARY
The student sees a chat and a block diagram. They do not see this prompt, the
YAML, or the ids in it. Never say "cascade", "corpus", "stage", "node", "option
id", "locks", or a path like cascade/power.yaml to them. Say "the design
questions", "the sources I have", "the diagram", "your answer". Options are
named by their label, never by their id.

STAGE 1 - SKETCH
If stage is "sketch", the student is describing what they want to build. Propose
a block diagram as your interpretation and ASK whether it matches. Refine it
until they confirm. The block `kind` is what decides which design questions get
asked, so choose it by what the signal IS, not by what the part is called:
  power_in    where power enters: battery, wall adapter, USB, upstream rail
  regulation  anything that converts or regulates a rail
  mcu         the microcontroller or processor
  digital     an on/off signal: a contact closure, a reed switch, a button, a
              limit switch, a relay coil, an LED, a buzzer, a logic-level line
  sensor      a sensor with a CONTINUOUS output that must be measured
  analog      amplification, filtering, references
  adc         an explicit analog-to-digital conversion stage
A reed switch or a push button is `digital`, not `sensor` - it closes or it does
not. Calling it `sensor` asks the student about ADC references they do not have.
Emit: {"type":"sketch","blocks":[{"id":"PWR","kind":"regulation","label":"5V buck"}],
       "links":[["PWR","MCU"]],"confirmed":false}
Set confirmed true only once the student agrees.

STAGE 2 - CASCADE
Ask ONE open question at a time, in plain English, including its "why".
Record an answer the student gives in chat with
  {"type":"answer","node":"<id>","value":"<option id>"}

ANCHORING - do this without being asked
A question or an explanation about ONE named element belongs on that element,
not in the chat stream, because the chat scrolls away and the element does not.
Whenever you explain why a constraint holds, challenge one, or ask something
about a specific decision, also anchor it:
  {"type":"ask","anchor":"<node or constraint id>","text":"..."}
The anchor must be an id that exists - a node id from open_questions/answered,
or a constraint id from active_constraints. An invented id is dropped.
Anything waiting on you appears under OPEN THREADS below; answer those first,
anchored on the same id.

LANGUAGE
Answer in whatever language the student writes in. Two rules if that is Hebrew:
- Block LABELS in the sketch stay short. Hebrew is fine, but prefer keeping part
  numbers, units and signal names in Latin script inside them.
- Write flow arrows as ← in Hebrew prose, not →. The sentence reads right to left.

REPLY FORMAT
Prose for the student, then a fenced json block:
```json
{"actions":[ ... ]}
```
Omit the block if there is nothing to record."""


def _summary(model):
    s = {
        "stage": model["stage"],
        "sketch": model["sketch"],
        "domains": model["domains"],
        "open_questions": [
            {"id": n["id"], "question": n["question"], "why": n.get("why", ""),
             "options": [{"id": o["id"], "label": o["label"],
                          "costs": o.get("costs", []),
                          "note": o.get("note", ""),
                          # an option's real price is often here, not in costs
                          "locks_in": [lk.get("text", "") for lk in (o.get("locks") or [])],
                          "adds_parts": [b.get("label", b["id"]).replace("\n", " ")
                                         for b in (o.get("blocks") or [])]}
                         for o in n.get("options", [])]}
            for n in model["open"]
        ],
        "answered": [{"id": n["id"], "chosen": n["chosen"]} for n in model["answered"]],
        # provenance travels WITH the constraint. Without it the agent is asked
        # to explain how we know a rule while holding only the rule.
        "active_constraints": [
            {"id": c["id"], "text": c["text"], "provenance": c["provenance"],
             "verified": c["verified"], "source": c.get("source") or {}}
            for c in model["constraints"]
        ],
        # the index of what is already on disk. Cheap, and it is the difference
        # between "I need a datasheet" and "the datasheet is right here".
        "documents": [
            {k: v for k, v in
             {"name": d.get("name"), "scope": d.get("scope"), "url": d.get("url")}.items()
             if v} for d in model.get("sources", [])
        ],
        "board": model.get("board", {}),
        # threads waiting on the agent go in full - they are what the student
        # asked and nobody answered. The rest are a count; the engine can read
        # threads.jsonl if it wants them.
        "open_threads": [
            {"anchor": t["anchor"], "about": t["label"],
             "messages": [{"role": m["role"], "text": m["text"]}
                          for m in t["messages"] if m.get("role") in ("user", "agent")]}
            for t in (model.get("threads") or {}).values() if t.get("waiting_on") == "agent"
        ],
        "threads_waiting_on_student": model.get("progress", {}).get("waiting_on_student", 0),
        "conflicts": model["conflicts"],
    }
    return json.dumps(s, ensure_ascii=False, indent=2)


def _workspace_section(project):
    """Only for an engine that can actually open a file. Telling a text-only
    engine to go and read something does not fail loudly - it invents."""
    w = workspace.describe(project)
    lines = [f"You are running in {w['home']}, and the current project is "
             f"{w['project']}. You may open these yourself.", ""]
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
              "Reading is free: open a datasheet, grep the corpus, check a value. "
              "Writing is not yours. Never edit the .jsonl logs - they are "
              "append-only and carry who decided what, and the server appends to "
              "them when you emit an action. Never add a constraint to the "
              "cascade; propose it to the student instead. To add a document, "
              "run scripts/sources.py so its sha256 is recorded."]
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
- Never put a design constraint here. Those come only from the authored cascade.
  A layout or electrical rule in this file is a bug.
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

    text, attempts = "", 0
    for attempts in (1, 2):
        res = gateway.route(gateway.Request(
            prompt=prompt,
            timeout=int(workspace.get("agent.timeout_seconds", 180)),
        ), name=name)
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
    actions = []
    for b in blocks:
        try:
            obj = json.loads(b)
            actions.extend(obj.get("actions", []) if isinstance(obj, dict) else obj)
        except json.JSONDecodeError:
            pass
    reply = re.sub(r"```json\s*.*?```", "", text, flags=re.S).strip()
    return reply, actions


def respond(model, message, history, backend=None, timeout=None):
    """(state, message) -> {reply, actions}. `backend` names an engine; None
    means whatever `agent.provider` is set to."""
    name = gateway.resolve(backend)
    if name == "external":
        return {"reply": None, "actions": [], "backend": name, "provider": name}

    keep = int(workspace.get("agent.history_messages", 8))
    convo = "\n".join(f"{m['role']}: {m['text']}" for m in history[-keep:])

    parts = [RULES]
    memory = (model.get("memory") or "").strip()
    if memory:
        parts.append("--- MEMORY (this conversation, kept small on purpose) ---\n"
                     + memory)
    if gateway.provider(name).has_workspace():
        parts.append("--- WORKSPACE ---\n" + _workspace_section(model.get("project")))
    parts.append("--- CURRENT STATE ---\n" + _summary(model))
    parts.append("--- CONVERSATION SO FAR ---\n" + convo)
    parts.append("--- STUDENT SAYS ---\n" + message + "\n")
    prompt = "\n\n".join(parts)

    res = gateway.route(gateway.Request(
        prompt=prompt,
        system=RULES,
        history=[{"role": m.get("role"), "text": m.get("text")} for m in history[-keep:]],
        timeout=int(timeout or workspace.get("agent.timeout_seconds", 180)),
    ), name=name)

    if not res.ok:
        return {"reply": f"[{res.provider or name}] {res.error}", "actions": [],
                "backend": res.provider or name, "provider": res.provider or name,
                "error": True}

    reply, actions = _parse(res.text)
    return {"reply": reply or "(no reply)", "actions": actions,
            "backend": res.provider, "provider": res.provider, "model": res.model}
