"""Readers for the fab-side files (A2: written here, independent of scripts/): JLC CPL csv, Altium Pick Place txt, JLC BOM csv,
the order manifest json, the order note text (and the statements it makes about the board).

Nothing here decides pass/fail; metrics/outputs.py does.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import json
import pathlib
import re

SKIP_DIRS = (".advisor-backup",)


# ---------------------------------------------------------------------------------------------------------------------- CPL
@dataclasses.dataclass
class CplRow:
    ref: str
    x: float
    y: float
    side: str            # top | bottom
    rot: float


def _mm(s: str) -> float:
    return float(re.sub(r"(?i)\s*mm\s*$", "", s.strip()))


def read_cpl_csv(path: pathlib.Path) -> list[CplRow]:
    """JLC CPL: Designator, Mid X, Mid Y, Layer, Rotation (values may carry a 'mm' suffix)."""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        low = {k.strip().lower(): v for k, v in r.items() if k}
        rows.append(CplRow(low["designator"].strip(), _mm(low["mid x"]), _mm(low["mid y"]),
                           "bottom" if low.get("layer", "top").strip().lower().startswith("b") else "top",
                           float(low.get("rotation", "0") or 0)))
    return rows


def read_altium_pickplace(path: pathlib.Path) -> list[CplRow]:
    """Altium 'Pick Place for X.txt' (whitespace table after the header row 'Designator Comment Layer Footprint Center-X(mm)...')."""
    lines = pathlib.Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    rows, started = [], False
    for ln in lines:
        if ln.startswith("Designator") and "Center-X" in ln:
            started = True
            continue
        if not started or not ln.strip():
            continue
        m = re.match(r"(\S+)\s+.*?\s(TopLayer|BottomLayer)\s+.*?\s(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+(?:\.\d+)?)\s", ln + " ")
        if m:
            rows.append(CplRow(m.group(1), float(m.group(3)), float(m.group(4)),
                               "top" if m.group(2) == "TopLayer" else "bottom", float(m.group(5))))
    return rows


def is_cpl_file(path: pathlib.Path) -> str | None:
    """'jlc' / 'altium' if the file is a pick-and-place list (decided by content, not by name), else None."""
    p = pathlib.Path(path)
    if p.suffix.lower() not in (".csv", ".txt", ".pos"):
        return None
    try:
        head = p.read_bytes()[:4096].decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    if re.search(r"^\s*Designator\s*,.*Mid\s*X", head, re.I | re.M):
        return "jlc"
    if re.search(r"^Designator\s+.*Center-X", head, re.M):
        return "altium"
    return None


def upload_roots(root: pathlib.Path) -> list[pathlib.Path]:
    """Where a student can pick fab files up: the project's exports folder and the Altium output folders."""
    root = pathlib.Path(root)
    out = [root / "project" / "exports"]
    alt = root / "altium"
    if alt.is_dir():
        out += [d for d in sorted(alt.iterdir()) if d.is_dir() and not d.name.startswith(SKIP_DIRS)
                and (d.name == "Outputs" or d.name.startswith("Project Outputs"))]
    return [d for d in out if d.is_dir()]


def find_cpl_files(root: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    found = []
    for d in upload_roots(root):
        for f in sorted(d.rglob("*")):
            if f.is_file() and not any(s in f.parts for s in SKIP_DIRS):
                kind = is_cpl_file(f)
                if kind:
                    found.append((f, kind))
    return found


# ---------------------------------------------------------------------------------------------------------------------- BOM
@dataclasses.dataclass
class BomLine:
    comment: str
    refs: list[str]
    footprint: str
    lcsc: str


def read_bom_jlc(path: pathlib.Path) -> list[BomLine]:
    """JLC BOM: Comment, Designator, Footprint, LCSC Part #."""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig", errors="replace")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        low = {k.strip().lower(): (v or "") for k, v in r.items() if k}
        refs = [x.strip() for x in re.split(r"[,\s]+", low.get("designator", "")) if x.strip()]
        lcsc = next((v for k, v in low.items() if k.startswith("lcsc")), "").strip()
        out.append(BomLine(low.get("comment", "").strip(), refs, low.get("footprint", "").strip(), lcsc))
    return out


def duplicate_lcsc_groups(lines: list[BomLine]) -> list[list[BomLine]]:
    """Groups of 2+ BOM lines with the same LCSC code, comment (value) and footprint: they should be one line."""
    groups: dict[tuple, list[BomLine]] = {}
    for ln in lines:
        if ln.lcsc:
            groups.setdefault((ln.lcsc, ln.comment.lower(), ln.footprint.lower()), []).append(ln)
    return [g for g in groups.values() if len(g) > 1]


# ---------------------------------------------------------------------------------------------------------------------- manifest
def read_json(path: pathlib.Path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))


def manifest_text_outside(manifest: dict, raw_keys=("board_check",)) -> str:
    """All strings of the manifest except the raw tool records (the human-facing part). Keys are included."""
    parts: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                parts.append(str(k))
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif v is not None:
            parts.append(str(v))
    walk({k: v for k, v in manifest.items() if k not in raw_keys})
    return "\n".join(parts)


def drc_violations(manifest: dict) -> list[str] | None:
    """The DRC violation strings Altium reported, as recorded in the manifest; None when the manifest holds no DRC record."""
    for path in (("board_check", "drc", "drc", "violations"), ("drc", "drc", "violations"), ("board_check", "drc", "violations"),
                 ("drc", "violations")):
        v = manifest
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, list):
            return [str(x) for x in v]
    return None


def drc_rule_name(v: str) -> str:
    """'Minimum Annular Ring (Minimum=8mil) (IsPad): ...' -> 'Minimum Annular Ring'."""
    return re.split(r"\s*[\(:]", v, 1)[0].strip()


# ---------------------------------------------------------------------------------------------------------------------- order note
NOTE_NAME = re.compile(r"(order.?note|readme)", re.I)


def exported_order_notes(root: pathlib.Path) -> list[pathlib.Path]:
    d = pathlib.Path(root) / "project" / "exports"
    if not d.is_dir():
        return []
    return [f for f in sorted(d.iterdir())
            if f.is_file() and f.suffix.lower() in (".md", ".txt", ".html") and NOTE_NAME.search(f.stem) and f.stat().st_size > 0]


def notes_md_section(text: str, heading_re: str = r"order\s*note") -> str | None:
    """The body of the '## ... order note' section of notes.md, or None."""
    lines = text.splitlines()
    out, inside = [], False
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            if inside:
                break
            inside = bool(re.search(heading_re, m.group(2), re.I))
            continue
        if inside:
            out.append(ln)
    return "\n".join(out) if inside or out else None


def order_note(root: pathlib.Path) -> tuple[str | None, pathlib.Path | None, str]:
    """(text, path, source) of the order note a student would copy into the JLC order: the exported one, else the section of
    notes.md. source is 'export' | 'notes.md' | 'none'."""
    ex = exported_order_notes(root)
    if ex:
        return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in ex), ex[0], "export"
    nm = pathlib.Path(root) / "project" / "notes.md"
    if nm.is_file():
        sec = notes_md_section(nm.read_text(encoding="utf-8", errors="replace"))
        if sec is not None:
            return sec, nm, "notes.md"
    return None, None, "none"


_UNTENTED = re.compile(r"(un-?tented|not\s+tented|no\s+tent|(?:vias?|them)\s+(?:are\s+|stay\s+|left\s+)?(?:open|bare|exposed)|"
                       r"leave\s+(?:the\s+)?vias?\s+(?:open|untented)|do\s+not\s+tent|don'?t\s+tent)", re.I)
_TENTED = re.compile(r"(tent(?:ed|ing)?\b|plugged|covered\s+with\s+(?:solder\s*)?mask)", re.I)


def tenting_statements(text: str) -> list[tuple[str, str]]:
    """[(line, 'tented'|'untented')] for every line of the note that says something about via tenting."""
    out = []
    for ln in text.splitlines():
        if not re.search(r"tent|plug|via", ln, re.I):
            continue
        if _UNTENTED.search(ln):
            out.append((ln.strip(), "untented"))
        elif _TENTED.search(ln):
            out.append((ln.strip(), "tented"))
    return out


def layer_count_statements(text: str) -> list[tuple[str, int]]:
    out = []
    for ln in text.splitlines():
        for m in re.finditer(r"\b(\d{1,2})\s*[- ]?\s*layers?\b", ln, re.I):
            out.append((ln.strip(), int(m.group(1))))
    return out
