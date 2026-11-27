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

# --- Manufacturing outputs (Gerber / drill / CPL / BOM / order note), added by the outputs oracle ---------------------------------
# Every value cites a heading of shared/reference/jlc/pcb-capabilities.en.md or an owner decision.
_CAP = "jlc/pcb-capabilities.en.md"
MASK_BRIDGE_MIN_MM = T({"green": 0.10, "red": 0.10, "yellow": 0.10, "blue": 0.10, "purple": 0.10, "black": 0.13, "white": 0.13},
                       "mm", f"{_CAP} § Solder mask [P1]", "mask bridge (dam between openings), 1 oz copper; 2 oz would be 0.20 mm any colour")
BARE_VIA_TO_EXPOSED_COPPER_MM = T(0.2, "mm", f"{_CAP} § Via covering options (Untented) [P5, P1]", "with HASL keep bare vias >= 0.2 mm from other exposed copper")
NPTH_TO_COPPER_MM = T(0.2, "mm", f"{_CAP} § Traces and spacing (NPTH to track) [P1]", "applied to copper on every layer, pours included (ACCEPTANCE W32 b)")
VIA_MAX_HOLE_MM = T(0.5, "mm", f"{_CAP} § Via covering options (via holes ideally <= 0.4 mm, max 0.5 mm) [P5]",
                    "classification rule: a plated round hole up to this size is a via; larger plated holes are component holes")
# Measurement resolution (not design limits). Gerber coordinates have a fixed step (read from %FS); the polygon model of a circle is
# circumscribed with 64 sides (error <= 0.12 % of the radius). Both are derived in oracle/gerber.py, not tuned here.
# Oracle resolution (not design limits). Altium stores 1/10000 mil = 2.54e-6 mm; these absorb the rounding of derived values.
GEOM_TOL_MM = T(0.001, "mm", "oracle coordinate resolution (Altium 1/10000 mil); ACCEPTANCE.md A7 measurement resolution")
STACK_ER_TOL = T(0.005, "-", "Altium stores Er as typed (two decimals); half the last stored digit (ACCEPTANCE.md W27)")

# Edge distances (JLCPCB). Used by F-H (c).
EDGE_COPPER_MIN_MM = T(0.2, "mm", "jlc/pcb-capabilities.en.md § Outline, board size and thickness (Copper to edge, routed edge) [P1]",
                       "copper to a routed edge must be >= 0.2 mm")
EDGE_ASSEMBLY_MIN_MM = T(0.3, "mm", "jlc/assembly-capabilities.en.md § Economic vs Standard PCBA (Economic boards ... > 0.3 mm from the edge) [A4 #14]",
                         "JLC asks > 0.3 mm from traces and components to the edge: a gap of 0.3 mm or less is a finding")

# --- Altium-judged live metrics (metrics/altium_*.py) ------------------------------------------------------------------------------
ANNULAR_RING_MIN_MM = T(0.15, "mm", f"{_CAP} § Drills, vias and annular ring (PTH annular ring: multilayer 1 oz, 0.15 mm absolute min) [P1]",
                        "used by the F-H(a) classifier: a pad ring below it is JLC-reject, between it and the rule value JLC-accept")
