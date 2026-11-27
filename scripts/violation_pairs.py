"""Objects named by one line of Altium's design rule check report, as the student reads them ("pad J3-1 and pad J3-2").

A report line is "<rule>: <text>" (bridge.parse_drc). The text names one or two objects ("Between Pad U1-9(10mm,20mm) on Top Layer And
Track (3mm,4mm)(5mm,4mm) on Top Layer"). This module only reads those names; it never measures anything. A line that names no object
returns an empty tuple: the caller says so instead of guessing.
"""
import re

_KINDS = r"Pad|Via|Track|Arc|Text|String|Region|Polygon|Fill|Component|Hole|Room"
_OBJ = re.compile(rf"\b({_KINDS})\b\s*(?:\"([^\"]+)\"|'([^']+)'|([A-Za-z]{{1,4}}\d+(?:-[A-Za-z0-9_.+]+)?))?\s*(\([^)]*\)(?:\([^)]*\))?)?", re.I)
_NET = re.compile(r"\bNet(?:Name)?\s*[:=]?\s*([A-Za-z0-9_+./-]+)", re.I)


def _name(m):
    kind = m.group(1).lower()
    kind = "text" if kind == "string" else kind
    name = m.group(2) or m.group(3) or m.group(4) or ""
    at = m.group(5) or ""
    if name:
        return f"{kind} {name}"
    coords = re.findall(r"\(([-\d.]+)\s*(?:mm|mil)?\s*,\s*([-\d.]+)\s*(?:mm|mil)?\)", at)
    if coords:
        x, y = coords[0]
        return f"{kind} at ({x}, {y})"
    return kind


def objects(line):
    """The objects named by a report line, in the order written: a tuple of 0, 1 or 2 short names ("pad J3-1", "text H3")."""
    text = str(line)
    _, _, rest = text.partition(":")
    rest = rest or text
    parts = re.split(r"\bBetween\b", rest, maxsplit=1, flags=re.I)
    body = parts[1] if len(parts) == 2 else rest
    sides = re.split(r"\bAnd\b", body, maxsplit=1, flags=re.I)
    out = []
    for side in sides[:2]:
        m = _OBJ.search(side)
        if m:
            out.append(_name(m))
    return tuple(out)


def net_of(line):
    m = _NET.search(str(line))
    return m.group(1) if m else ""


def refdes(name):
    """"pad J3-1" -> "J3"; "text H3" -> "H3"; "track at (1, 2)" -> ""."""
    m = re.search(r"\b([A-Za-z]{1,4}\d+)(?:-|\b)", name.split(" at ")[0])
    return m.group(1).upper() if m else ""


def rule_of(line):
    return re.split(r" \(|:", str(line), maxsplit=1)[0].replace(" Constraint", "").strip()


def group(lines):
    """[{"rule", "a", "b", "count", "example"}] one row per (rule, object pair), largest first. A line that names no object is
    counted under a = "" so the total always equals the number of lines (nothing is dropped)."""
    rows = {}
    for ln in lines or []:
        objs = objects(ln)
        a, b = (objs + ("", ""))[:2]
        key = (rule_of(ln), a, b)
        r = rows.setdefault(key, {"rule": key[0], "a": a, "b": b, "count": 0, "example": str(ln)})
        r["count"] += 1
    return sorted(rows.values(), key=lambda r: -r["count"])


def pair_words(row):
    """One row as words: "Clearance: pad J3-1 and pad J3-2 (3)"; one object: "Silk to silk: text H3 (1)"."""
    who = " and ".join(x for x in (row["a"], row["b"]) if x) or "objects the report does not name"
    return f"{row['rule'] or 'rule'}: {who} ({row['count']})"
