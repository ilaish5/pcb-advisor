"""Idea-stage checks on requirements text (pure functions, no I/O except the facts table loader).

check_flashing_plan(text): finds a requirement that firmware is flashed/programmed over USB, finds the
MCUs named in the text, and looks them up in references/mcu-bootloaders.json (ROM bootloader interfaces
per family, each row with a source). An MCU whose row says "no USB DFU in ROM" is a finding; unknown
MCUs and unknown rows give no finding.
"""
import json
import pathlib
import re
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
TABLE = REPO / "runtime" / "skills" / "idea-and-requirements" / "references" / "mcu-bootloaders.json"

_USB = re.compile(r"\busb\b", re.I)
_FLASH = re.compile(r"\b(flash\w*|program\w*|firmware|dfu|bootload\w*|burn\w*|upload\w*)\b", re.I)
_REF = re.compile(r"^[A-Z]{1,3}\d+[A-Z]?$")


def load_table(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    rows = json.loads((path or TABLE).read_text(encoding="utf-8"))["rows"]
    for r in rows:
        r["_re"] = re.compile(r["match"], re.I)
    return rows


def usb_flash_requirements(text: str) -> list[str]:
    """Requirement lines that tie USB to flashing/programming/firmware."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith(("#", "|")):
            continue
        if _USB.search(line) and _FLASH.search(line):
            out.append(line.strip().lstrip("-* ").replace("**", ""))
    return out


def mcus_in_text(text: str, table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{ref, part, row}] for each line (usually a parts-table row) that names a known MCU family.
    ref is the first table cell when it looks like a designator, else ''."""
    found = []
    for line in text.splitlines():
        for row in table:
            m = row["_re"].search(line)
            if not m:
                continue
            ref = ""
            if line.lstrip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells and _REF.match(cells[0]):
                    ref = cells[0]
            part = re.search(r"[A-Za-z0-9\-]*(?:" + row["match"] + r")[A-Za-z0-9\-]*", line, re.I)
            found.append({"ref": ref, "part": part.group(0) if part else m.group(0), "row": row})
            break
    return found


def check_flashing_plan(text: str, table: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    table = table if table is not None else load_table()
    reqs = usb_flash_requirements(text)
    if not reqs:
        return []
    findings = []
    for m in mcus_in_text(text, table):
        row = m["row"]
        if row["usb_dfu_rom"] != "no":
            continue
        alts = row.get("alternatives") or []
        who = (m["ref"] + " ") if m["ref"] else ""
        findings.append({
            "id": "mcu_no_usb_dfu", "severity": "error", "refs": [m["ref"]] if m["ref"] else [],
            "message": (f"{who}{m['part']}: requirement \"{reqs[0][:110]}\" needs USB flashing, "
                        f"but the {row['family']} ROM bootloader has no USB DFU (ROM interfaces: "
                        f"{', '.join(row['rom_interfaces']) or 'none'}). "
                        + (f"Alternatives: {'; '.join(alts)}. " if alts else "")
                        + f"Source: {row['source']}."),
            "evidence": reqs[0]})
    return findings
