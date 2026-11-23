"""Which JLCDFM item an Altium design rule corresponds to, and at what level JLC flags it: the answer to "Altium says 21, JLC says 7".

Static, from jlc_preset.DFM (the thresholds the preset documents: [Danger below mil, Warning below mil, Good from mil]). A rule that
has no JLCDFM item is listed with jlc=None: Altium counts it, JLC's check does not look at it. Nothing here measures a board.
"""
import re

# Altium rule (short name, as bridge._drc_short writes it) -> JLCDFM item. Hedged on purpose: the item names are JLCDFM's.
RULE_TO_JLC = {
    "Minimum Solder Mask Sliver": "Soldermask bridge",
    "Minimum Solder Mask Sliver (Gap)": "Soldermask bridge",
    "Clearance": "Trace spacing",
    "Width": "Trace width",
    "Minimum Annular Ring": "Annular ring",
    "Hole To Hole Clearance": "Plated through-hole spacing",
    "Board Outline Clearance": "Trace to board edge",
    "Silk To Solder Mask Clearance": "Silkscreen to pad",
}


def short(rule):
    """"Minimum Solder Mask Sliver Constraint (Gap=0.1mm) (All)" -> "Minimum Solder Mask Sliver"."""
    return re.split(r" \(|:", str(rule), maxsplit=1)[0].replace(" Constraint", "").strip()


def jlc_item(rule):
    s = short(rule)
    for key, item in RULE_TO_JLC.items():
        if s.lower() == key.lower():
            return item
    return None


def thresholds(item):
    """{"danger_below_mil", "warning_below_mil"} of a JLCDFM item, or None."""
    try:
        import jlc_preset
        t = jlc_preset.DFM.get(item)
    except ImportError:
        t = None
    return {"danger_below_mil": t[0], "warning_below_mil": t[1]} if t else None


def level(rule, measured_mil=None):
    """"danger" | "warning" | "ok" | "unknown" | "not_checked" for an Altium rule: not_checked = JLCDFM has no such item; unknown =
    the rule maps to an item but the violation's measured size is not known (Altium's report gives the count, not always the size)."""
    item = jlc_item(rule)
    if item is None:
        return "not_checked"
    t = thresholds(item)
    if t is None or measured_mil is None:
        return "unknown"
    return "danger" if measured_mil < t["danger_below_mil"] else "warning" if measured_mil < t["warning_below_mil"] else "ok"
