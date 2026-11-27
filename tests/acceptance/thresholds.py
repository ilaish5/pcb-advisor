"""Frozen thresholds (ACCEPTANCE.md A7). Every value names its source. Only the owner changes this file (new tag).

A builder adding a value must cite a `shared/reference` file + heading, a part datasheet page, or an owner decision (OD-n).
A value with no source does not belong here.
"""
from __future__ import annotations

MM_PER_MIL = 0.0254


def T(value, unit: str, source: str, note: str = "") -> dict:
    return {"value": value, "unit": unit, "source": source, "note": note}


# Owner decisions 27/11 (ACCEPTANCE.md "Owner decisions")
DECAP_FALLBACK_MM = T(3.0, "mm", "OD-1", "used only when the IC datasheet/app note gives no number; label: general knowledge")
XTAL_MAX_TRACK_MM = T(10.0, "mm", "OD-2", "general knowledge; AN2867 gives no number")
XTAL_VIAS_ON_PATH = T(0, "count", "OD-2", "general knowledge; AN2867 has no via rule")
COURTYARD_EXCESS_MM = T(0.25, "mm", "OD-3; shared/reference/standards/ipc-7351b-courtyard.en.md (Level B)")
EP_PASTE_COVERAGE = T((0.50, 0.80), "fraction", "OD-4", "fallback when the part datasheet has no stencil recommendation; IPC-7525 range")
CPL_FLAG_MM = T(0.25, "mm", "OD-5; shared/reference/jlc/cpl-reference-point.en.md", "our choice: JLC states no tolerance")
CHAT_MAX_LINES = T(10, "lines per message", "OD-6")

# JLCPCB (shared/reference/jlc/pcb-capabilities.en.md). Builders: fill the numbers from the cited heading, with the [P#] tag.
JLC04161H_7628 = T({
    "prepreg_mm": 0.2104, "prepreg_er": 4.4,
    "core_mm": 1.065, "core_er": 4.6,
    "outer_cu_mil": 1.6, "inner_cu_mil": 0.6,
}, "mixed", "jlc/pcb-capabilities.en.md § Impedance control and stack-ups")
STACK_TOL_MM = T(0.001, "mm", "Altium stores 0.0001 mil; ±0.001 mm covers mil rounding (ACCEPTANCE.md W27)")

# Measurement resolution (not design limits): how close an oracle value must be to a displayed value.
DISPLAY_TOL_MM = T(0.01, "mm", "display rounding (ACCEPTANCE.md W15, W34)")
OFFSET_TOL_MM = T(0.05, "mm", "measurement resolution (ACCEPTANCE.md W18)")
