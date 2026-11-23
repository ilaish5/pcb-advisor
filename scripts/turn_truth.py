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
_VERB = re.compile(r"propos|add(?:ed|ing)?\b|creat|queue|sent\b|wrote|put\b|updat|הצעתי|הוספתי|יצרתי|שלחתי|עדכנתי", re.I)
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


def card_correction(reply, applied, proposals):
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
                return (f"(Correction: this turn created {real} BOM card{'s' if real != 1 else ''}, not {m.group(1)}; "
                        "the cards below are the truth)" if real else
                        f"(Correction: this turn created no BOM cards, not {m.group(1)})")
    return ""


def promises_work(reply, applied, proposals):
    """True when the reply promises work it did not do: a deferral to a later reply (always), or "I will now / I'm drawing" with
    nothing applied this turn."""
    text = str(reply or "")
    if _DEFER.search(text):
        return True
    return bool(_NOW.search(text)) and not (applied or proposals)


def stopped_line(refused):
    """The one line that replaces a promise nothing keeps: why the turn stopped, from the server's own refusal."""
    why = str(refused[0]).strip() if refused else "no action was sent with this reply, so nothing ran; write again or press the button"
    return "(Stopped: " + why[:200].rstrip() + ")"


def closing_lines(reply, applied, proposals, refused, retry_follows=False):
    """The correction lines to append to a stored reply ([] when the text and the records agree). A promise is left alone while a
    retry round is about to do the work (its own record tells the outcome)."""
    out = []
    fix = card_correction(reply, applied, proposals)
    if fix:
        out.append(fix)
    if not retry_follows and promises_work(reply, applied, proposals):
        out.append(stopped_line(refused))
    return out
