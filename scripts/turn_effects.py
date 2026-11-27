"""W11: what a chat turn did to the project, said item by item at its end, and which actions a review turn may run.

A turn that came from a review chip (a suggestion the page offers: "What is wrong in ... and how do I fix it?") only answers or
proposes. `review_refusal` is the one place that decides it, so the chat path and the follow-up rounds read the same rule.
"""
import re

# what a review turn may do: say something, ask a question, add a step to the student's list. A proposal (a card the student decides on)
# is allowed too, but never applied by itself (the caller turns auto-apply off).
ANSWER_ONLY = {"chat.ask", "ledger.track", "idea.ready"}
PROPOSE_ONLY = {"bom.propose", "bom.delete", "net.set_current", "idea.diagram"}

# a typed question that asks nothing to be done. "Can you route the board?" is a request; "how do I fix it?" and "How do I move C3?" are questions:
# a question word or a trailing "?" makes it a review turn, unless it also orders (a polite request, "do it", or an order verb that starts the
# message or a later clause).
_ASKS = re.compile(r"\?\s*$|^\s*(?:what|why|how|which|where|when|who|should|is|are|does|do|explain|show me|tell me|list)\b|"
                   r"^\s*(?:איך|למה|מה|איזה|איזו|איפה|מתי|מי|כמה|האם|מדוע|הסבר)(?!\w)", re.I)
_ORDER_EN = (r"build|draw|place|route|create|make|add|run|generate|apply|import|replace|delete|remove|write|confirm|approve|start|send|order|export|"
             r"rebuild|redraw|re-?do|re-?route|re-?place|wipe|overwrite|move|swap|rotate|tidy|finish|update|change|fix|connect|rename")
_ORDER_HE = r"בנה|צייר|מקם|נתב|צור|הוסף|הרץ|מחק|הסר|אשר|שלח|תקן|החלף|הזז|שנה|סדר|חבר|ת(?:נתב|מקם|צייר|בנה|חליף|זיז|מחק|וסיף|ריץ|שנה|סדר|חבר|שלח|צור)"
_DOES = re.compile(r"\b(?:please|go ahead|do it|just do|(?:can|could|would|will) you|why don'?t you|you (?:fix|do|route|place|build)|"
                   r"(?:do|run|route|place|build|make|draw|fix|redo) (?:it|this|that|them) (?:for me|now)|fix (?:it|this|them) now)\b|"
                   r"(?:^|[.!;,\n]|\bthen\b|\band\b)\s*(?:" + _ORDER_EN + r")\b|"
                   r"בבקשה|תוכל|אתה יכול|את יכולה|למה שלא|"
                   r"(?:^|\s|[.!;,])(?:ואז |ו)?(?:" + _ORDER_HE + r")(?!\w)", re.I)


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
            "altium.run_outjob": "generating the outputs", "altium.run_drc": "checking the board", "library.build": "building the library",
            "altium.create_project": "creating the Altium project", "altium.skeleton": "drawing the sheet frames", "altium.add_sheet": "adding a sheet",
            "altium.add_pcb": "adding the PcbDoc", "netlist.write": "writing the netlist", "altium.import_rules": "importing the rules",
            "idea.propose": "adding a requirement", "idea.describe": "changing the description", "idea.confirm": "confirming the idea",
            "bom.propose": "proposing a BOM change", "net.set_current": "proposing a net current", "idea.diagram": "proposing a diagram change",
            "idea.diagram.edit": "editing the diagram", "outjob.generate": "adding the OutJob", "ledger.track": "adding a step to your list"}


_NOT_RUN_HE = {"altium.route_pcb": "ניתוב הלוח", "altium.place_pcb": "מיקום החלקים", "altium.draw_schematic": "שרטוט הסכמה",
               "altium.run_outjob": "הפקת קבצי הפלט", "altium.run_drc": "בדיקת הלוח", "library.build": "בניית הספרייה",
               "altium.create_project": "יצירת פרויקט Altium", "altium.skeleton": "שרטוט מסגרות הדפים", "altium.add_sheet": "הוספת דף",
               "altium.add_pcb": "הוספת קובץ הלוח", "netlist.write": "כתיבת רשימת החיבורים", "altium.import_rules": "ייבוא הכללים",
               "idea.propose": "הוספת דרישה", "idea.describe": "שינוי התיאור", "idea.confirm": "אישור הרעיון", "bom.propose": "הצעת שינוי ב-BOM",
               "net.set_current": "הצעת זרם לרשת", "idea.diagram": "הצעת שינוי בדיאגרמה", "idea.diagram.edit": "עריכת הדיאגרמה",
               "outjob.generate": "הוספת ה-OutJob", "ledger.track": "הוספת צעד לרשימה שלך"}


def _not_run(kind, lang):
    """The name of what did not run: the thing itself ("routing the board" / "ניתוב הלוח"), never the done verb."""
    return (_NOT_RUN_HE.get(kind) if lang == "he" else _NOT_RUN.get(kind)) or _label(kind, lang)


def _why(rest):
    """The reason of a refusal, in the student's words: "not run." is dropped (the line already says it), the rest is kept up to a word
    boundary, never cut to nothing."""
    r = re.sub(r"^\s*not run\.?\s*", "", str(rest or "").strip(), flags=re.I).replace("\n", " ")
    if len(r) > 220:
        r = r[:220].rsplit(" ", 1)[0] + " ..."
    return r.rstrip(". ") or "not run"


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
        nm = "; ".join(_not_run(str(r).partition(":")[0].strip(), lang) + " (" + _why(str(r).partition(":")[2]) + ")" for r in refused[:12])
        parts.append(("Did not run: " if lang != "he" else "לא רץ: ") + nm + ("" if len(refused) <= 12 else (f" and {len(refused) - 12} more" if lang != "he" else f" ועוד {len(refused) - 12}")) + ".")
    if stopped:
        parts.append("You pressed Stop: nothing started after it." if lang != "he" else "לחצת עצור: שום דבר לא התחיל אחרי זה.")
    return " ".join(parts)
