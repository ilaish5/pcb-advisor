"""What a part asks for at a supply pin, from a SOURCE that says it (R2 / W22). It fails closed: no source, no requirement, never a guess from prose.

    requirement(pin_name, mpn="", text="") -> {"schemes": [{"per_pin": [slot], "per_device": [slot], "why": "..."}]} | None

A slot is {"role": "hf" | "bulk", "farads": f}. Two sources, in this order:
  1. the cited family table (shared/reference/decap-families.json): the family of the part (its MPN) and the pin group name the scheme, with the
     document and place that says it. The table is general data; no board or project is named in it;
  2. a strict row of a power-supply table or figure list of the part's own datasheet text: ONE line that starts with the exact pin name and holds
     nothing but capacitor values ("VDDA   10 nF + 1 uF"). A sentence ("connected to VDDA", "though not required ... 0.1 uF"), a list on a
     neighbouring line, a range, a pF value, or two rows that disagree is never a requirement.
None means "not checked": the caller says so with the reason.
"""
import json
import pathlib
import re

TABLE = pathlib.Path(__file__).resolve().parent.parent / "shared" / "reference" / "decap-families.json"
HF_WINDOW = (1.0, 10.0)        # a high-frequency slot takes a ceramic of 1x to 10x the value; the bulk capacitor never stands in for it
BULK_WINDOW = (0.4, 10.0)
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
    """The text as the pin names are written: the PDF kerning gap in 'V DD', 'V DDA' and 'V REF+' is removed."""
    return re.sub(r"\bV\s+(DD|SS|REF|CAP|BAT|CC)", r"V\1", str(text or ""))


def _from_row(pin_name, text):
    rows = set()
    for tok in _tokens(pin_name):
        rx = re.compile(r"^\s*(?:\d{1,3}\s+)?" + re.escape(tok) + r"(?![A-Za-z0-9_+/])\s*[:=|]?\s+(.+?)\s*$", re.I)
        for ln in _norm(text).splitlines():
            m = rx.match(ln)
            if not m:
                continue
            rest = _FILLER.sub(" ", m.group(1)).strip()
            if not _CHAIN.match(rest):
                continue
            vals = []
            for v in _ONE.finditer(rest):
                vals += [float(v.group(2)) * _UNIT[v.group(3).lower()]] * int(v.group(1) or 1)
            rows.add(tuple(vals))
    if len(rows) != 1:          # no row, or rows that disagree: not a requirement
        return None
    vals = sorted(next(iter(rows)))
    slots = [{"role": "bulk" if v >= BULK_FROM else "hf", "farads": v} for v in vals]
    return {"group": "row:" + str(pin_name), "schemes": [{"per_pin": slots, "per_device": [], "why": f"a power-supply row of the part's datasheet text that names {pin_name}"}]}


def requirement(pin_name, mpn="", text=""):
    return _from_table(pin_name, mpn) or (_from_row(pin_name, text) if text else None)


def fits(role, want, have):
    """Does a capacitor of `have` farads fill a slot of `want` farads of this role?"""
    lo, hi = HF_WINDOW if role == "hf" else BULK_WINDOW
    return have is not None and want > 0 and lo * 0.999 <= have / want <= hi * 1.001
