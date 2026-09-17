"""
Agent adapter.

The agent is treated as a pure function:  (state, message) -> {reply, actions}.
It gets no file access and no tools.  The SERVER applies the actions, which
keeps one writer and means any model or runtime can be dropped in behind this
interface without touching the rest of the tool.

Backends:
  claude    spawn `claude -p`, parse a JSON block off stdout
  external  do nothing; an agent attached elsewhere is driving the folder
"""
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent

RULES = """You are the PCB design advisor. You walk a student down a decision cascade.

HARD RULES
- Never invent a design constraint. Constraints come only from the authored
  cascade; the server attaches them automatically when a decision is recorded.
- You may explain, compare options, and recommend. You must never choose for
  the student.
- If something is outside the cascades loaded, say so plainly instead of
  improvising a rule.
- Do not recall part numbers, pinouts or stock levels from memory. Say you need
  a datasheet.

STAGE 1 - SKETCH
If stage is "sketch", the student is describing what they want to build. Propose
a block diagram as your interpretation and ASK whether it matches. Refine it
until they confirm. Use these block kinds so the right knowledge loads:
  power_in, regulation, mcu, digital, sensor, analog, adc
Emit: {"type":"sketch","blocks":[{"id":"PWR","kind":"regulation","label":"5V buck"}],
       "links":[["PWR","MCU"]],"confirmed":false}
Set confirmed true only once the student agrees.

STAGE 2 - CASCADE
Ask ONE open question at a time, in plain English, including its "why".
Record an answer the student gives in chat with
  {"type":"answer","node":"<id>","value":"<option id>"}
Anchor a question on a node or a constraint with
  {"type":"ask","anchor":"<id>","text":"..."}

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
             "options": [{"id": o["id"], "label": o["label"], "costs": o.get("costs", [])}
                         for o in n.get("options", [])]}
            for n in model["open"]
        ],
        "answered": [{"id": n["id"], "chosen": n["chosen"]} for n in model["answered"]],
        "active_constraints": [{"id": c["id"], "text": c["text"]} for c in model["constraints"]],
        "conflicts": model["conflicts"],
    }
    return json.dumps(s, ensure_ascii=False, indent=2)


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


def respond(model, message, history, backend="claude", timeout=180):
    if backend == "external":
        return {"reply": None, "actions": [], "backend": "external"}

    convo = "\n".join(f"{m['role']}: {m['text']}" for m in history[-8:])
    prompt = (f"{RULES}\n\n--- CURRENT STATE ---\n{_summary(model)}\n\n"
              f"--- CONVERSATION SO FAR ---\n{convo}\n\n"
              f"--- STUDENT SAYS ---\n{message}\n")
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"reply": "No `claude` CLI on PATH. Set backend=external and drive the "
                         "project folder from your own agent.", "actions": [], "error": True}
    except subprocess.TimeoutExpired:
        return {"reply": "The agent timed out.", "actions": [], "error": True}

    if proc.returncode != 0:
        return {"reply": f"Agent failed: {(proc.stderr or '').strip()[:400]}",
                "actions": [], "error": True}

    reply, actions = _parse(proc.stdout)
    return {"reply": reply or "(no reply)", "actions": actions, "backend": "claude"}
