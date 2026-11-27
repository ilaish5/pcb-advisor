"""W11: what a chat turn did to the project, said item by item at its end, and which actions a review turn may run.

A turn that came from a review chip (a suggestion the page offers: "What is wrong in ... and how do I fix it?") only answers or
proposes. `review_refusal` is the one place that decides it, so the chat path and the follow-up rounds read the same rule.
"""
import re

# what a review turn may do: say something, ask a question, add a step to the student's list. A proposal (a card the student decides on)
# is allowed too, but never applied by itself (the caller turns auto-apply off).
ANSWER_ONLY = {"chat.ask", "ledger.track", "idea.ready"}
PROPOSE_ONLY = {"bom.propose", "bom.delete", "net.set_current", "idea.diagram"}

# a typed question that asks nothing to be done. "Can you route the board?" is a request; "how do I fix it?" is a question.
_ASKS = re.compile(r"\?\s*$|^(?:what|why|how|which|where|when|who|explain|show me|tell me|list)\b", re.I)
_DOES = re.compile(r"\b(?:please|go ahead|do it|just do|build|draw|place|route|create|make|add|run|generate|apply|import|replace|delete|remove|"
                   r"write|confirm|approve|start|send|order|export|rebuild|redraw|fix it for me|you fix|fix (?:it|this|them) now)\b|"
                   r"(?:^|\s)(?:בנה|צייר|מקם|נתב|צור|הוסף|הרץ|מחק|הסר|אשר|שלח)\b", re.I)


def is_review(text, chip=False):
    """True for a message that asks and orders nothing: every suggestion chip, and a typed question with no order in it."""
    if chip:
        return True
    t = str(text or "").strip()
    return bool(_ASKS.search(t)) and not _DOES.search(t)


def review_refusal(kind):
    """None when a review turn may run this action, else the sentence for the refusal (it names the action)."""
    if kind in ANSWER_ONLY or kind in PROPOSE_ONLY:
        return None
    return f"{kind}: not run. You asked a question, so nothing was changed; say what you want done and it will be done then"


_WORDS = {
    "library.build": "built the library", "altium.create_project": "created the Altium project", "altium.skeleton": "drew the sheet frames",
    "altium.add_sheet": "added a sheet", "altium.add_pcb": "added the PcbDoc", "netlist.write": "wrote the netlist",
    "altium.draw_schematic": "drew the schematic", "altium.place_pcb": "placed the parts", "altium.route_pcb": "routed the board",
    "altium.import_rules": "imported the rules", "altium.run_outjob": "generated the outputs", "altium.run_drc": "checked the board",
    "idea.propose": "added a requirement", "idea.describe": "changed the description", "idea.confirm": "confirmed the idea",
    "bom.propose": "proposed a BOM change", "net.set_current": "proposed a net current", "idea.diagram": "proposed a diagram change",
    "idea.diagram.edit": "edited the diagram", "outjob.generate": "added the OutJob", "ledger.track": "added a step to your list",
}
_WORDS_HE = {
    "library.build": "נבנתה הספרייה", "altium.create_project": "נוצר פרויקט Altium", "altium.draw_schematic": "נשרטטה הסכמה",
    "altium.place_pcb": "מוקמו החלקים", "altium.route_pcb": "נותב הלוח", "netlist.write": "נכתבה רשימת החיבורים",
}


# What did NOT run is named as the thing, never as the done verb ("routed the board" would read as if it had happened).
_NOT_RUN = {"altium.route_pcb": "routing the board", "altium.place_pcb": "placing the parts", "altium.draw_schematic": "drawing the schematic",
            "altium.run_outjob": "generating the outputs", "altium.run_drc": "checking the board", "library.build": "building the library"}


def _label(kind, lang):
    if lang == "he" and kind in _WORDS_HE:
        return _WORDS_HE[kind]
    return _WORDS.get(kind, kind)


def items(applied):
    """[(kind, detail)] of what the applied list records, in order: the server's own records, not the agent's text."""
    out = []
    for x in applied or []:
        kind, _, rest = str(x).partition(":")
        kind = kind.strip()
        if not kind or kind in ("bom.check", "chat.ask", "idea.ready"):
            continue
        out.append((kind, rest.strip()))
    return out


def text(applied, refused, lang="en", stopped=False, review=False):
    """The end line of a turn: every change by name, every action that did not run by name and reason. "" when nothing was done and
    nothing refused (a plain answer needs no such line)."""
    did = items(applied)
    parts = []
    if did:
        names = "; ".join(f"{_label(k, lang)}" + (f" ({d.split(chr(10))[0][:60]})" if d and k.startswith("bom.propose") else "") for k, d in did)
        parts.append(("Changed in this turn: " if lang != "he" else "השתנה בתור הזה: ") + names + ".")
    elif stopped or review or refused:
        parts.append("Nothing was changed in this turn." if lang != "he" else "לא השתנה דבר בתור הזה.")
    if refused:
        nm = "; ".join(((_NOT_RUN.get(str(r).partition(":")[0].strip()) if lang != "he" else None) or _label(str(r).partition(":")[0].strip(), lang)) + " (" + (str(r).partition(":")[2].strip().split(".")[0][:70] or "not run") + ")" for r in refused[:12])
        parts.append(("Did not run: " if lang != "he" else "לא רץ: ") + nm + ("" if len(refused) <= 12 else f" and {len(refused) - 12} more") + ".")
    if stopped:
        parts.append("You pressed Stop: nothing started after it." if lang != "he" else "לחצת עצור: שום דבר לא התחיל אחרי זה.")
    return " ".join(parts)
