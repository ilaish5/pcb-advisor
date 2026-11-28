"""What a part asks for at a supply pin, from a SOURCE that says it (R2 / W22). It fails closed: no source, no requirement, never a guess from prose.

    requirement(pin_name, mpn="", text="") -> {"schemes": [{"per_pin": [slot], "per_device": [slot], "why": "..."}]} | None

A slot is {"role": "hf" | "bulk", "farads": f}. Two sources, in this order:
  1. the cited family table (shared/reference/decap-families.json): the family of the part (its MPN) and the pin group name the scheme, with the
     document and place that says it. The table is general data; no board or project is named in it;
  2. the part's own datasheet text, scoped to its power-supply section (found by heading: "Power supply scheme", "Decoupling", "Typical application"...).
     Inside that section only: a table row that starts with the pin name and carries values ("VDDA  10 nF + 1 uF"), the values of a figure under the
     pin's label, and a note or sentence that ties a value to the named pin ("a 4.7 uF ceramic capacitor must be connected to one of the VDD pins",
     "decoupled with a 100 nF capacitor per VDD pin"). Outside the section prose never counts, nor optional wording ("not required", "though"), a pin
     tied to a pin ("connected to VDDA"), a range, a pF value, VBAT taking a neighbour's list, or two statements of one kind that disagree. One value
     found is enforced; the result says "partial" so the caller reports the pin's other slots as not read.
None means "not checked": the caller says so with the reason.
"""
import json
import pathlib
import re

TABLE = pathlib.Path(__file__).resolve().parent.parent / "shared" / "reference" / "decap-families.json"
HF_WINDOW = (0.8, 3.0)        # a ceramic of 0.8x to 3x the value fills a slot (the next standard values either side); a 100 nF never fills a 10 nF slot, a 4.7 uF never a 1 uF one
BULK_WINDOW = (0.5, 2.0)
BULK_FROM = 2.2e-6             # a value of a table row from here up is a bulk capacitor, below it a high-frequency one

_UNIT = {"n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6}
_VAL = r"(?:(\d+)\s*[x×]\s*)?(\d+(?:\.\d+)?)\s*([nuµμ])\s*F\b"          # nF and uF: a pF is a parasitic or a crystal load, not a decoupling capacitor
_JOIN = r"\s*(?://|\|\||\+|,|and|&)\s*"          # a dash is a range (0.1-0.22 uF: any in between), not a second capacitor
_CHAIN = re.compile(r"^(?:" + _VAL + r")(?:" + _JOIN + _VAL + r")*$", re.I)
_ONE = re.compile(_VAL, re.I)
_FILLER = re.compile(r"\b(?:decoupling|bypass|capacitors?|ceramic|per|each|every|pin|pins)\b|[:=|]", re.I)
_cache = {}


def _table():
    if "t" not in _cache:
        try:
            _cache["t"] = json.loads(TABLE.read_text(encoding="utf-8")).get("families", [])
        except (OSError, ValueError):
            _cache["t"] = []
    return _cache["t"]


def _tokens(name):
    return [t.strip() for t in str(name or "").split("/") if t.strip()]


def cite_text(cite):
    return f"{cite['file']}, page {cite['page']}" + (f", {cite['figure']}" if cite.get("figure") else "")


def page_text(cite, root=None):
    """The text of the page a table entry cites, or None when the file or the page is not there (tests/test_decap_families.py checks every entry)."""
    f = (root or TABLE.parent) / cite["file"]
    try:
        if f.suffix.lower() == ".pdf":
            import pypdf
            pages = [pg.extract_text() or "" for pg in pypdf.PdfReader(str(f)).pages]
        else:
            pages = f.read_text(encoding="utf-8").split("")
    except Exception:       # noqa: BLE001 - a file that cannot be read confirms nothing
        return None
    n = int(cite["page"])
    return pages[n - 1] if 1 <= n <= len(pages) else None


def _from_table(pin_name, mpn):
    mpn = str(mpn or "").strip()
    if not mpn:
        return None
    for fam in _table():
        if not re.search(fam["match"], mpn, re.I):
            continue
        for grp in fam.get("groups", []):
            if any(re.match(grp["pin"], t, re.I) for t in _tokens(pin_name)):
                return {"group": fam["id"] + ":" + grp["pin"], "schemes": [{"per_pin": s.get("per_pin", []), "per_device": s.get("per_device", []),
                                     "why": cite_text(s["cite"])} for s in grp["schemes"]]}
    return None


def _norm(text):
    """The text as the pin names are written: the PDF kerning gap in 'V DD', 'V DDA' and 'V REF+' is removed, dashes are plain."""
    t = re.sub(r"\bV\s+(DD|SS|REF|CAP|BAT|CC)", r"V\1", str(text or ""))
    return t.replace("–", "-").replace("−", "-")


# ---- the part's own datasheet, scoped to its power-supply section -------------------------------------------------------------------
_HEAD = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+|(?:Figure|Table)\s+\d+\.?\s+)?(?:power\s+supply(?:\s+(?:scheme|schemes|decoupling|and\s+reference\s+decoupling))?"
                   r"|supply\s+decoupling|decoupling|power\s+decoupling|typical\s+application|recommended\s+operating)\b", re.I)
_NUM_HEAD = re.compile(r"^\s*\d+(?:\.\d+){1,3}\.?\s+[A-Z]")
_TOC = re.compile(r"(?:\.\s*){4,}\s*\d+\s*$")
SECTION_LINES = 60
_OPTIONAL = re.compile(r"not\s+(?:required|necessary|mandatory)|optional|though|although|if\s+desired|may\s+be\s+(?:omitted|removed)|recommended\s+but|can\s+be\s+omitted", re.I)
_UNITS_ONLY = re.compile(r"\b(?:decoupling|bypass|capacitors?|ceramic|per|each|every|pins?|x|and|of|one)\b|[:=|()]|\d+(?![\d.]*\s*[nuµμp]F)", re.I)
_CHAIN_ANY = re.compile(r"(?:" + _VAL + r")(?:" + _JOIN + _VAL + r")*", re.I)
_GROUND = re.compile(r"^(?:VSS\w*|GND\w*|VREF-|AGND|PGND)$", re.I)
_NO_LABEL = re.compile(r"^(?:VBAT|VBUS)$", re.I)


def sections(text):
    """[(heading line number, [lines])]: the power-supply sections of a datasheet text, by heading: a numbered heading, a figure or table caption, or
    a line that opens with the words; a table-of-contents line is not one. A section runs to the next numbered heading or SECTION_LINES lines."""
    lines = _norm(text).splitlines()
    out, i = [], 0
    while i < len(lines):
        if _HEAD.match(lines[i]) and not _TOC.search(lines[i]):
            j = i + 1
            while j < len(lines) and j - i < SECTION_LINES and not (_NUM_HEAD.match(lines[j]) and not _HEAD.match(lines[j])):
                j += 1
            out.append((i + 1, lines[i:j]))
            i = j
        else:
            i += 1
    return out


def _vals(chain):
    out = []
    for v in _ONE.finditer(chain):
        out += [float(v.group(2)) * _UNIT[v.group(3).lower()]] * int(v.group(1) or 1)
    return out


def _is_name(tok, name):
    t = tok.strip().upper()
    base = re.sub(r"[_-]?\d+$", "", name.upper())
    return t in (name.upper(), base)


def _label_tokens(line):
    s = line.strip()
    if not s or len(s.split()) > 3 or len(s) > 24 or _ONE.search(s) or s.endswith("."):
        return None
    return [t for t in re.split(r"[/\s]+", s) if t]


def _statements(lines, names):
    """[(kind, values)] for a pin whose name tokens are `names`, read inside one section: table rows, figure labels with a value line, and notes."""
    out = []
    pat = "|".join(re.escape(n) for n in names)
    base = "|".join(sorted({re.escape(re.sub(r"[_-]?\d+$", "", n)) for n in names} | {re.escape(n) for n in names}, key=len, reverse=True))
    pat = base            # a pin named VDD_1 is a VDD pin of the datasheet's notes
    # (a) a table row: the line starts with the pin name; what is left of it is only values and filler words
    row = re.compile(r"^\s*(?:\d{1,3}\s+)?(?:" + base + r")(?![A-Za-z0-9_+/-])\s*[:=|]?\s+(.+?)\s*$", re.I)
    for ln in lines:
        m = row.match(ln)
        if not m or _OPTIONAL.search(ln):
            continue
        c = _CHAIN_ANY.search(m.group(1))
        if c and re.match(r"\s*(?:-|to)\s*\d", m.group(1)[c.end():]):          # a range: any value in between, not a capacitor
            continue
        if c and not _UNITS_ONLY.sub(" ", m.group(1)[:c.start()]).strip(" ,;/+"):          # only filler before the values; a remark column may follow
            out.append(("pin", tuple(_vals(c.group(0)))))
    # (a2) a figure: the labels of the pins, then a line that is only the values; they belong to the nearest supply label above them
    for j, ln in enumerate(lines):
        if not _CHAIN.match(ln.strip().rstrip(".")) or _OPTIONAL.search(ln):
            continue
        k = j - 1
        while k >= 0 and j - k <= 5:
            toks = _label_tokens(lines[k])
            if toks is None:
                if _CHAIN.match(lines[k].strip()):
                    k -= 1
                    continue
                break
            supply = [t for t in toks if not _GROUND.match(t) and re.match(r"^[AD]?V", t, re.I) and not _NO_LABEL.match(t)]
            if any(_is_name(t, n) for t in supply for n in names):
                out.append(("pin", tuple(_vals(ln))))
                break
            if supply:
                break           # the labels of another supply pin stand between: the values are not this pin's
            k -= 1
    # (b) notes and sentences that tie a value to this pin
    text = " ".join(x.strip() for x in lines)
    for sent in re.split(r"(?<!\d)\.(?=\s|$)|;", text):
        if _OPTIONAL.search(sent):
            continue
        for m in re.finditer(r"(" + _CHAIN_ANY.pattern + r")\s*(?:ceramic\s+|tantalum\s+)?(?:decoupling\s+)?capacitors?\s+(?:must|should|shall)\s+be\s+"
                             r"(?:connected|placed|fitted|used)\s+(?:to|on|at)\s+(?P<one>one\s+of\s+)?(?:the\s+|each\s+)?(?:" + pat + r")\s+pins?\b", sent, re.I):
            out.append(("device" if m.group("one") else "pin", tuple(_vals(m.group(1)))))
        for m in re.finditer(r"(?:decoupl|bypass)\w*\s+(?:with|by|using)\s+(?:a|an|one)?\s*(" + _CHAIN_ANY.pattern + r")(?:\s+ceramic)?(?:\s+capacitors?)?\s+"
                             r"(?:per|on|at|for|each|every)\s+(?:each\s+|every\s+)?(?:" + pat + r")\s+pins?\b", sent, re.I):
            out.append(("pin", tuple(_vals(m.group(1)))))
        for m in re.finditer(r"(?<![A-Za-z0-9_])(?:" + pat + r")\b[^.]{0,40}?(?:decoupl|bypass)\w*\s+(?:with|by|using)\s+(?:a|an)?\s*(" + _CHAIN_ANY.pattern + r")", sent, re.I):
            out.append(("pin", tuple(_vals(m.group(1)))))
    return [s for s in out if s[1]]


def _from_text(pin_name, text):
    names = _tokens(pin_name)
    stmts = []
    for _n, lines in sections(text):
        stmts += _statements(lines, names)
    if not stmts:
        return None
    per_pin = {s[1] for s in stmts if s[0] == "pin"}
    per_dev = {s[1] for s in stmts if s[0] == "device"}
    if len(per_pin) > 1 or len(per_dev) > 1:          # two statements of one kind that disagree: not a requirement
        return None
    pin_vals = sorted(next(iter(per_pin))) if per_pin else []
    dev_vals = [v for v in (sorted(next(iter(per_dev))) if per_dev else []) if not any(abs(v - p) < 1e-12 for p in pin_vals)]

    def role(v):
        return "bulk" if v >= BULK_FROM else "hf"
    scheme = {"per_pin": [{"role": role(v), "farads": v} for v in pin_vals], "per_device": [{"role": role(v), "farads": v} for v in dev_vals],
              "why": f"the power-supply section of the part's own datasheet text names {pin_name}"}
    n = len(pin_vals) + len(dev_vals)
    return {"group": "text:" + str(pin_name), "schemes": [scheme], "partial": n == 1}


def requirement(pin_name, mpn="", text=""):
    """The requirement of a supply pin, or None. A requirement with "partial": True states one value only: that value is enforced and the caller says
    the pin's other slots are not read."""
    return _from_table(pin_name, mpn) or (_from_text(pin_name, text) if text else None)


def fits(role, want, have):
    """Does a capacitor of `have` farads fill a slot of `want` farads of this role?"""
    lo, hi = HF_WINDOW if role == "hf" else BULK_WINDOW
    return have is not None and want > 0 and lo * 0.999 <= have / want <= hi * 1.001
