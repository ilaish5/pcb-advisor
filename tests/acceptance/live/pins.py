"""The oracle's own W14 pin status of a BOM line (ACCEPTANCE W14/U1), computed from the line's data and the files on
disk, never taken from the product's pins_status label.

  verified        only with an evidence record {sha256 of the datasheet file = file on disk now, page, pins compared =
                  the symbol's pin count}
  accepted        a student decision on that line (the pin decision record), whatever the product calls it
  not_applicable  only unpolarised 2-terminal passives: R, C (not electrolytic / tantalum / polarised), L, FB
  not_checked     everything else
"""
from __future__ import annotations

import hashlib
import pathlib
import re

PASSIVE_PREFIX = re.compile(r"^(R|C|L|FB)\d", re.I)
POLARISED = re.compile(r"electrolytic|tantalum|polari[sz]ed|\bE-?cap\b", re.I)


def is_unpolarised_passive(line: dict) -> bool:
    refs = line.get("refs") or [line.get("key", "")]
    if not refs or not all(PASSIVE_PREFIX.match(str(r)) for r in refs):
        return False
    text = " ".join(str(line.get(k) or "") for k in ("value", "mpn", "description", "role", "footprint", "package"))
    return not POLARISED.search(text)


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def evidence_ok(line: dict, project_dir: pathlib.Path) -> tuple[bool, str]:
    ev = line.get("pins_evidence") or line.get("evidence")
    if isinstance(ev, list):
        ev = ev[0] if ev else None
    if not isinstance(ev, dict):
        return False, "no evidence record"
    doc = ev.get("doc") or ev.get("datasheet") or line.get("datasheet")
    f = project_dir / "sources" / str(doc or "")
    if not doc or not f.is_file():
        return False, "evidence names no datasheet file on disk"
    if ev.get("sha256") != _sha(f):
        return False, "evidence sha256 is not the file on disk (stale)"
    if not isinstance(ev.get("page"), int):
        return False, "evidence has no page"
    n, sym = ev.get("pins_compared"), ev.get("symbol_pins")
    if not isinstance(n, int) or not isinstance(sym, int) or n != sym or n < 1:
        return False, "pins compared != symbol pin count"
    return True, ""


def oracle_status(line: dict, project_dir: pathlib.Path) -> tuple[str, str]:
    dec = line.get("pin_decision")
    if isinstance(dec, dict) and dec.get("basis"):
        return "accepted", f"student decision ({dec.get('basis')})"
    ok, why = evidence_ok(line, project_dir)
    if ok:
        return "verified", "evidence record matches the file"
    if is_unpolarised_passive(line):
        return "not_applicable", "unpolarised 2-terminal passive"
    return "not_checked", why
