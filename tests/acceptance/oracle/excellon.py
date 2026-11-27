"""Excellon drill reader (A2: independent of the product). Altium style: M48 header, `;TYPE=PLATED|NON_PLATED`, `;FILE_FORMAT=i:d`,
INCH|METRIC with LZ|TZ, T-codes with C diameter, X/Y hits, routed slots (G00 ... M15 / G01 ... M16) and G85 slots. Units -> mm.

A drill file with no ;TYPE comment is classified by its file name ("NonPlated"/"NPTH" -> non-plated, otherwise plated).
"""
from __future__ import annotations

import dataclasses
import pathlib
import re

IN = 25.4


@dataclasses.dataclass
class Hole:
    x: float
    y: float
    d: float                 # mm
    plated: bool
    slot_to: tuple | None = None   # (x1, y1) when a routed slot, else None
    file: str = ""

    @property
    def core(self) -> tuple:
        p0 = (self.x, self.y)
        return (p0, self.slot_to or p0)


def parse(name: str, data: bytes | str) -> list[Hole]:
    text = data.decode("latin1") if isinstance(data, bytes) else data
    unit, zero, intd, decd = IN, "L", 2, 4
    plated = None
    tools: dict[int, float] = {}
    in_header = False
    seen_header = False
    cur: int | None = None
    x = y = 0.0
    routing = False          # M15 pressed: G01 moves cut a slot
    mode = "drill"
    slot_start: tuple | None = None
    holes: list[Hole] = []

    def conv(s: str) -> float:
        sign = -1 if s.startswith("-") else 1
        s = s.lstrip("+-")
        if "." in s:
            return sign * float(s) * unit
        total = intd + decd
        s = s.ljust(total, "0") if zero == "L" else s.rjust(total, "0")
        return sign * int(s) / (10 ** decd) * unit

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            m = re.match(r";\s*TYPE\s*=\s*(\w+)", line, re.I)
            if m:
                plated = m.group(1).upper().startswith("PLATED")
            m = re.match(r";\s*FILE_FORMAT\s*=\s*(\d+):(\d+)", line, re.I)
            if m:
                intd, decd = int(m.group(1)), int(m.group(2))
            continue
        if line == "M48":
            in_header = seen_header = True
            continue
        if line == "%":
            in_header = False
            continue
        if in_header:
            m = re.match(r"(INCH|METRIC)(?:,\s*(LZ|TZ))?", line)
            if m:
                unit = IN if m.group(1) == "INCH" else 1.0
                zero = (m.group(2) or "LZ")[0]
                if m.group(1) == "METRIC" and "FILE_FORMAT" not in text:
                    intd, decd = 3, 3
                continue
            m = re.match(r"T(\d+)(?:F\d+)?(?:S\d+)?C([0-9.]+)", line)
            if m:
                tools[int(m.group(1))] = float(m.group(2)) * unit
            continue
        if line in ("M30", "M00"):
            break
        if line in ("M17", "G90", "G05"):
            continue
        if line == "M15":
            routing = True
            slot_start = (x, y)
            continue
        if line == "M16":
            routing = False
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = int(m.group(1))
            if cur not in tools:
                raise ValueError(f"{name}: tool T{cur} not defined")
            continue
        m = re.match(r"(G0[01]|G85)?(?:X([-+]?[0-9.]+))?(?:Y([-+]?[0-9.]+))?(?:G85X([-+]?[0-9.]+)Y([-+]?[0-9.]+))?$", line)
        if not m or not (m.group(2) or m.group(3)):
            raise ValueError(f"{name}: cannot parse line {line!r}")
        g = m.group(1)
        nx = conv(m.group(2)) if m.group(2) else x
        ny = conv(m.group(3)) if m.group(3) else y
        if cur is None:
            raise ValueError(f"{name}: coordinate before a tool")
        if m.group(4):                                   # X..Y..G85X..Y.. slot
            holes.append(Hole(nx, ny, tools[cur], bool(plated), (conv(m.group(4)), conv(m.group(5)))))
        elif routing and g == "G01":
            holes.append(Hole(x, y, tools[cur], bool(plated), (nx, ny)))
        elif g is None:                                  # a bare X/Y line is a drill hit; G00 is a routing move
            holes.append(Hole(nx, ny, tools[cur], bool(plated)))
        x, y = nx, ny
    if not seen_header:
        raise ValueError(f"{name}: no M48 header")
    if plated is None:
        plated = not re.search(r"non.?plated|npth", name, re.I)
        for h in holes:
            h.plated = plated
    for h in holes:
        h.file = name
    return holes


def is_drill_name(name: str) -> bool:
    p = pathlib.PurePath(name)
    return p.suffix.lower() in (".txt", ".drl", ".xln", ".nc") and not re.search(r"pick|place|status", p.stem, re.I)
