"""P0-4 collapsed-view judge, shared by every failure path the Altium-judged metrics trigger (library build, route, outputs ...).

The collapsed view is what the page shows without a click (a note's visible innerText, bold elements, <details> states):
  - a bold title on one line, <= 70 characters, that names the action and the object that failed;
  - at most 3 lines of text at 1366 x 768 (title included; the button labels do not count);
  - a "Details" control, collapsed by default;
  - none of: file paths, exception / error-class names, WinError / HRESULT / hex codes, script file names, raw Altium text,
    numbers with float noise (0.299999 mm).
The oracle-run LLM judge of P0-4 ("does the title name the action and the object that were made to fail?") is not built here: the
title is checked for the injected object's own tokens, which is the same question answered by the oracle's own knowledge of what it broke.
"""
from __future__ import annotations

import re

TITLE_MAX = 70
LINES_MAX = 3
FORBIDDEN = [
    ("path", r"[A-Za-z]:\\|\\\\[A-Za-z0-9_.$-]+\\|(?<![\w/])/(?:usr|home|var|tmp|c)/\w"),
    ("error-class", r"\b\w*(?:Error|Exception)\b|Traceback|errno|HRESULT|WinError|OSError|BridgeError"),
    ("hex-code", r"\b0x[0-9A-Fa-f]{3,}\b|\b[0-9A-F]{8}\b"),
    ("script-name", r"\b[\w-]+\.(?:py|pas|js|json|jsonl|PrjScr|txt|log)\b"),
    ("raw-altium", r"\(\s*(?:Clearance|Gap|Minimum|Width|Hole|Min)\s*=\s*[\d.]+\s*(?:mil|mm)|\bBetween\s+(?:Pad|Track|Via|Region|Polygon)|\b\d+(?:\.\d+)?\s*mil\b"),
    ("float-noise", r"\b\d+\.\d{5,}\b"),
    ("internal-id", r"\b(?:altium\.[a-z_]+|library\.build|bom\.propose|student_said|chat\.ask)\b"),
]
_BUTTON_WORDS = re.compile(r"^(dismiss|details?|show details?|hide details?|copy|retry|stop|close|ok|keep it|replace[\w ]*|show \d+ warnings?)$", re.I)


def lines_of(text: str) -> list[str]:
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def hits(text: str) -> list[tuple[str, str]]:
    out = []
    for name, rx in FORBIDDEN:
        for m in re.finditer(rx, text or ""):
            out.append((name, m.group(0)[:60]))
    return out


def collapsed(note: dict) -> dict:
    """What the student sees first, from one snapshot note (browser.snap)."""
    text = note.get("text", "")
    lines = [l for l in lines_of(text) if not _BUTTON_WORDS.match(l)]
    bold = [b for b in (note.get("bold") or []) if b]
    det = note.get("details") or []
    has_details = bool(det) or bool(re.search(r"\bdetails?\b", text, re.I))
    details_closed = all(not d.get("open") for d in det) if det else True
    return {"lines": lines, "bold": bold, "has_details": has_details, "details_closed": details_closed, "n_lines": len(lines),
            "title": bold[0] if bold else "", "hits": hits("\n".join(lines))}


def judge(note: dict | None, object_tokens: list[str]) -> tuple[bool, list[str]]:
    """(ok, reasons). object_tokens: words of the injected action/object, at least one of each group must appear in the title,
    e.g. [["route", "routing"], ["+3V3"]]; a list item is a group of alternatives."""
    if not note:
        return False, ["no end message in the DOM"]
    c = collapsed(note)
    bad: list[str] = []
    if not c["bold"]:
        bad.append("no bold title")
    elif len(c["title"]) > TITLE_MAX:
        bad.append(f"title is {len(c['title'])} characters (limit {TITLE_MAX})")
    else:
        for group in object_tokens:
            if not any(t.lower() in c["title"].lower() for t in group):
                bad.append(f"title does not name {'/'.join(group)}")
    if c["n_lines"] > LINES_MAX:
        bad.append(f"{c['n_lines']} lines in the collapsed view (limit {LINES_MAX})")
    if not c["has_details"]:
        bad.append("no Details control")
    elif not c["details_closed"]:
        bad.append("Details is open by default")
    if c["hits"]:
        bad.append("forbidden in the collapsed view: " + ", ".join(f"{n} '{s}'" for n, s in c["hits"][:4]))
    return (not bad), bad
