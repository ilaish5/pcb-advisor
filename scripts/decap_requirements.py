"""What a part's own datasheet asks for at a supply pin, read from its text (R2 / W22).

    requirement(text, pin_name) -> {"values": [farads, ...], "why": "where it was read"} | None

None means the text gives no readable requirement for that pin (an empty or scanned datasheet, a figure the text lost): the caller says "not
checked" with that reason, it never guesses a template for the part family. Two forms are read, both generic:
  * a list of capacitors next to the pin name: "1 uF // 10 nF", "1 x 100 nF + 1 x 4.7 uF" (a parallel or additive chain within a few lines of
    a line that names the pin);
  * a note that a capacitor of a value goes on a named pin: "The 4.7 uF ceramic capacitor must be connected to one of the VDD pin".
"""
import re

_UNIT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6}
_VAL = r"(?:(\d+)\s*[x×]\s*)?(\d+(?:\.\d+)?)\s*([nuµμ])\s*F\b"          # nF and uF: a pF is a parasitic or a crystal load, not a decoupling capacitor
_JOIN = r"\s*(?://|\|\||\+|,|and|&)\s*"          # a dash is a range (0.1-0.22 uF: any in between), not a second capacitor
_CHAIN = re.compile(r"(?:" + _VAL + r")(?:" + _JOIN + _VAL + r")*", re.I)
_ONE = re.compile(_VAL, re.I)
_NOTE = re.compile(r"(\d+(?:\.\d+)?)\s*([pnuµμ])\s*F\s+(?:ceramic\s+)?(?:capacitor\s+)?(?:must|should)\s+be\s+(?:connected|placed|fitted)\s+"
                   r"(?:to|on)\s+(?:one\s+of\s+)?(?:the\s+)?([A-Za-z][\w+\-]*)\s+pin", re.I)
WINDOW = 6                     # lines between the pin name and the list of capacitors


def _norm(text):
    """The text as the pin names are written: the PDF kerning gap in 'V DD', 'V DDA' and 'V REF+' is removed."""
    t = re.sub(r"\bV\s+(DD|SS|REF|CAP|BAT|CC)", r"V\1", str(text or ""))
    return re.sub(r"[ \t]*\n[ \t]*(?=[+/|]|and\b)|(?<=[+/|])[ \t]*\n[ \t]*", " ", t)          # a list broken over two lines is one list


def _values(chain):
    out = []
    for m in _ONE.finditer(chain):
        out += [float(m.group(2)) * _UNIT[m.group(3).lower()]] * int(m.group(1) or 1)
    return out


def _tokens(name):
    return [t.strip() for t in str(name or "").split("/") if t.strip()]


def requirement(text, pin_name):
    lines = _norm(text).splitlines()
    if not any(lines):
        return None
    toks = _tokens(pin_name)
    for m in _NOTE.finditer(_norm(text)):          # a note that names this very pin outranks a list that merely sits near its name
        if m.group(3).upper() in {t.upper() for t in toks}:
            return {"values": [float(m.group(1)) * _UNIT[m.group(2).lower()]], "why": f"the datasheet's note on {m.group(3)}: {m.group(0)[:90]}"}
    best = None                  # (distance, line number, values)
    for tok in toks:
        rx = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(tok) + r"(?![A-Za-z0-9_])", re.I)
        for i, ln in enumerate(lines):
            if not rx.search(ln):
                continue
            for j in range(max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)):
                m = _CHAIN.search(lines[j])
                vals = _values(m.group(0)) if m else []
                key = (-len(vals), abs(i - j))              # the longest list near the name, then the nearest
                if len(vals) >= 2 and (best is None or key < best[0]):          # one value near a name is prose, not a requirement
                    best = (key, j, vals)
        for i, ln in enumerate(lines):          # one value is a requirement only in a sentence about the capacitor ON that pin
            vals = _values(ln)
            if best is None and len(vals) == 1 and rx.search(ln) and re.search(r"decoupl|bypass|capacitor", ln, re.I) \
                    and re.search(r"(?:on|at|to|for|each)\s+(?:each\s+|every\s+)?(?:the\s+)?" + re.escape(tok) + r"\b", ln, re.I):
                best = ((-1, 0), i, vals)
    if best:
        return {"values": best[2], "why": f"the datasheet's capacitor list next to {pin_name} (line {best[1] + 1} of its text)"}
    return None
