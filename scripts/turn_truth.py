"""
The closing text of a reply checked against what the server really did (W3, ledger rows 31 and 39).

The agent writes its text BEFORE its actions run, so the text can say a number or a promise the server then contradicts. The server's
applied / refused records are the truth; this module only appends ONE short correction line to the stored text, never rewrites it:
  - a count of BOM cards / lines that differs from the cards this turn really created (row 39);
  - a promise of work "in the next reply" (or "I will now ...") when nothing ran: the student is told it stopped and why (row 31).
"""
import re

_SENT = re.compile(r"[^.!?\n]+[.!?]?")
_CARD_NOUN = r"(?:cards?|proposals?|כרטיסים|כרטיס|הצעות)"
_LINE_NOUN = r"(?:lines?|rows?|שורות|שורה)"
_CLAIM = re.compile(rf"(?<![\w.])(\d{{1,3}})\s+(?:new\s+|BOM\s+|more\s+)*({_CARD_NOUN}|{_LINE_NOUN})(?!\w)", re.I)
# verb forms only, on word boundaries: "You have 3 proposals waiting" / "3 updates" are nouns, not a claim of work done
_VERB = re.compile(r"\b(?:propos(?:e|ed|es|ing)|add(?:ed|ing|s)?|creat(?:e|ed|es|ing)|queue[ds]?|queuing|sent|wrote|put|updat(?:e|ed|ing))\b"
                   r"|הצעתי|הוספתי|יצרתי|שלחתי|עדכנתי", re.I)
_LINE_CTX = re.compile(r"\bBOM\b|propos|cards?|כרטיס|הצע", re.I)

# a deferral the agent cannot keep (its next turn only happens when the student writes again) ...
_DEFER = re.compile(r"\b(?:next|following)\s+(?:reply|message|turn|answer)\b|\bin\s+my\s+next\b|\bonce\s+you\s+(?:write|say|reply)\b"
                    r"|בתשובה הבאה|בהודעה הבאה|בתור הבא|בתגובה הבאה", re.I)
# ... or work announced as under way / about to start
_NOW = re.compile(r"\bI(?:'ll|\s+will|\s+am\s+going\s+to)\s+(?:now\s+)?(?:draw|place|route|build|write|send|run|create|generate|import)\b"
                  r"|\bI(?:'m|\s+am)\s+(?:now\s+)?(?:drawing|placing|routing|building|writing|sending|running|creating|generating|importing)\b"
                  r"|\bnow\s+(?:drawing|placing|routing|building)\b|מצייר עכשיו|אצייר עכשיו|אשלח עכשיו|אבנה עכשיו|אמקם עכשיו|אנתב עכשיו", re.I)


def n_cards(applied, proposals):
    """How many BOM cards the turn really created: bom.propose records, else all proposals."""
    n = sum(1 for x in applied or [] if str(x).startswith("bom.propose:"))
    return n or len(proposals or [])


def card_correction(reply, applied, proposals, lang="en"):
    """'' or one line when the reply says it created N cards / BOM lines and the server created another number."""
    real = n_cards(applied, proposals)
    for sent in _SENT.findall(str(reply or "")):
        if not _VERB.search(sent):
            continue
        for m in _CLAIM.finditer(sent):
            noun = m.group(2).lower()
            is_card = re.fullmatch(_CARD_NOUN, noun, re.I) is not None
            if not is_card and not _LINE_CTX.search(sent):
                continue                    # "40 lines of text", "the 12 rows": not about this turn's cards
            if int(m.group(1)) != real:
                return (msg("fix_n", lang, real=real, s="s" if real != 1 else "", said=m.group(1)) if real
                        else msg("fix_0", lang, said=m.group(1)))
    return ""


def promises_work(reply, applied, proposals):
    """True when the reply promises work it did not do: a deferral to a later reply (always), or "I will now / I'm drawing" with
    nothing applied this turn."""
    text = str(reply or "")
    if _DEFER.search(text):
        return True
    return bool(_NOW.search(text)) and not (applied or proposals)


# the server's own lines, in the student's language (one small table: key -> {lang: text})
MSG = {
    "fix_n": {"en": "(Correction: this turn created {real} BOM card{s}, not {said}; the cards below are the truth)",
              "he": "(תיקון: בתור הזה נוצרו {real} כרטיסי BOM, לא {said}; הכרטיסים למטה הם האמת)"},
    "fix_0": {"en": "(Correction: this turn created no BOM cards, not {said})",
              "he": "(תיקון: בתור הזה לא נוצרו כרטיסי BOM, לא {said})"},
    "nothing": {"en": "no action was sent with this reply, so nothing ran; write again or press the button",
                "he": "לא נשלחה פעולה עם התשובה הזו, אז שום דבר לא רץ; כתוב שוב או לחץ על הכפתור"},
    "stopped": {"en": "(Stopped: {why})", "he": "(נעצר: {why})"},
    "partial": {"en": "(Done: {done}. Not done: {todo}; {hint})", "he": "(בוצע: {done}. לא בוצע: {todo}; {hint})"},
    "hint_verb": {"en": "say '{verb} it'", "he": "כתוב לי להמשיך"},
    "hint": {"en": "say 'go on'", "he": "כתוב לי להמשיך"},
    "todo_any": {"en": "what the reply promised next", "he": "מה שהתשובה הבטיחה לאחר מכן"},
    "not_applied": {"en": "(Not applied: {what})", "he": "(לא הוחל: {what})"},
    "not_run": {"en": "(Not run: {what})", "he": "(לא הורץ: {what})"},
    "followup_no_actions": {"en": "follow-up replies do not run actions: {what}", "he": "תשובות המשך לא מריצות פעולות: {what}"},
    "denied_not_rerun": {"en": "the denied command was not run again; no script ran in this reply",
                         "he": "הפקודה שנדחתה לא הורצה שוב; אף סקריפט לא רץ בתשובה הזו"},
    "no_followup": {"en": "the follow-up that was to fix this could not start", "he": "תשובת ההמשך שהייתה אמורה לתקן את זה לא יכלה להתחיל"},
}
# what an applied record means in words, by its kind (the part before ":")
_DONE = {
    "library.build": ("library built", "הספרייה נבנתה"), "netlist.write": ("sheet {n} written", "גיליון {n} נכתב"),
    "altium.create_project": ("project created", "הפרויקט נוצר"), "altium.import_rules": ("rules imported", "הכללים יובאו"),
    "altium.draw_schematic": ("sheet drawn", "הגיליון צויר"), "altium.place_pcb": ("parts placed", "החלקים הונחו"),
    "altium.route_pcb": ("routed", "הניתוב בוצע"), "altium.run_outjob": ("outputs generated", "הפלטים נוצרו"),
    "altium.run_drc": ("DRC run", "ה-DRC רץ"),
}
# a promised verb -> (gerund, imperative, Hebrew gerund)
_PROMISE_VERB = re.compile(r"\b(draw|place|route|build|writ|send|run|creat|generat|import)\w*|(?:מצייר|אצייר)|(?:אשלח)|(?:אבנה)|(?:אמקם)|(?:אנתב)", re.I)
_PROMISE_WORDS = {"draw": ("drawing", "draw", "ציור"), "place": ("placing", "place", "מיקום"), "rout": ("routing", "route", "ניתוב"),
                  "build": ("building", "build", "בנייה"), "writ": ("writing", "write", "כתיבה"), "send": ("sending", "send", "שליחה"),
                  "run": ("running", "run", "הרצה"), "creat": ("creating", "create", "יצירה"),
                  "generat": ("generating", "generate", "יצירה"), "import": ("importing", "import", "ייבוא")}
_HE_VERB = {"מצייר": "draw", "אצייר": "draw", "אשלח": "send", "אבנה": "build", "אמקם": "place", "אנתב": "rout"}


def msg(key, lang="en", **kw):
    row = MSG[key]
    return row.get(lang if lang in row else "en").format(**kw)


def _ran(applied, lang):
    """Short labels of what really ran this turn (dedup, in order); pending proposals and checks do not count."""
    out = []
    for x in applied or []:
        x = str(x)
        kind, _, rest = x.partition(":")
        kind = kind.strip()
        if kind in ("bom.check", "bom.propose") or not kind:
            continue
        en, he = _DONE.get(kind, (kind, kind))
        label = (he if lang == "he" else en).replace("{n}", (rest.strip().split()[0] if rest.strip() else "?"))
        if label not in out:
            out.append(label)
    return out


def _promised(reply):
    m = None
    for sent in _SENT.findall(str(reply or "")):
        if _DEFER.search(sent) or _NOW.search(sent):          # the verb of the promise, not of what was already done
            m = _PROMISE_VERB.search(sent)
            if m:
                break
    if not m:
        return None
    word = m.group(0).lower()
    key = _HE_VERB.get(word) or next((k for k in _PROMISE_WORDS if word.startswith(k)), None)
    return key


def stopped_line(refused, applied=None, reply="", lang="en", proposals=None):
    """The one line that replaces a promise nothing keeps. Nothing ran: why the turn stopped, from the server's own refusal.
    Something ran: what did (Done) and what did not (Not done), so 'nothing ran' is never claimed falsely."""
    done = _ran(applied, lang)
    if done:
        key = _promised(reply)
        words = _PROMISE_WORDS.get(key)
        todo = words[2 if lang == "he" else 0] if words else msg("todo_any", lang)
        hint = msg("hint_verb", lang, verb=words[1]) if words else msg("hint", lang)
        return msg("partial", lang, done=", ".join(done), todo=todo, hint=hint)
    why = str(refused[0]).strip() if refused else msg("nothing", lang)
    return msg("stopped", lang, why=why[:200].rstrip())


def closing_lines(reply, applied, proposals, refused, retry_follows=False, lang="en"):
    """The correction lines to append to a stored reply ([] when the text and the records agree). A promise is left alone while a
    retry round is about to do the work (its own record tells the outcome)."""
    out = []
    fix = card_correction(reply, applied, proposals, lang)
    if fix:
        out.append(fix)
    if not retry_follows and promises_work(reply, applied, proposals):
        out.append(stopped_line(refused, applied, reply, lang, proposals))
    return out
