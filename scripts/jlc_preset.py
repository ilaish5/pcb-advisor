"""The JLC design-rule preset: the numbers, chosen by the board's layer count, copper weight and mask colour.

Two kinds of number live here, and they are not the same thing:
  * the fab floor (`fab_min_mm`): JLC's own absolute minimum from its capabilities page. The verdicts of
    scripts/rules.py call a board value below it "below_fab_min".
  * the preset value: what the advisor tells the student to set in Altium. It sits above the floor so that
    JLCDFM (JLC's design check) rates it Good. JLCDFM's limits are whole mils, so a drawn 0.10 mm (3.94 mil)
    is Danger against its 4 mil limit even though JLC's page accepts it; the preset is written in whole mils.

Evidence, all read 2026-10-14:
  * shared/reference/jlc/pcb-capabilities.en.md: JLC's capabilities page [P1] and help pages, by number.
  * docs/bench-runs/jlc-live-2026-10-14/jlcdfm_rules.json: JLCDFM's 38 checks with their Danger / Warning /
    Good limits in mil, fetched from jlcdfm.com (copied into DFM below; a test compares the two).
JLC changes these pages: re-read them before quoting a number as current.
"""
import re

MIL = 0.0254                      # mm per mil
CAPABILITIES_URL = "https://jlcpcb.com/capabilities/pcb-capabilities"
REFERENCE = "shared/reference/jlc/pcb-capabilities.en.md"
CHECKED = "2026-10-14"

# JLCDFM check -> [r0, r1, r2] in mil: below r0 Danger, below r1 Warning, below r2 Good, else not reported.
DFM = {
    "Trace width": [4, 5, 8],
    "Trace spacing": [4, 6, 8],
    "Annular ring": [4, 6, 8],
    "Trace to board edge": [6, 8, 10],
    "Pad to board edge": [5, 8, 16],
    "Soldermask bridge": [4, 6, 8],
    "Plated through-hole spacing": [7, 8, 10],
    "Silkscreen to pad": [5, 7, 10],
}

# JLC's absolute minimum track and space (mm) by copper weight [P1, P3], as the page states them: 1-2 layer 1 oz 0.10 mm
# (4 mil), multilayer 1 oz 0.09 mm (3.5 mil; 3.0-3.5 mil there costs +20 % [P13]). 2 oz is 0.16 mm on any layer count (P3;
# P1 says 0.15 mm on multilayer, the page conflict is listed in the reference). JLCDFM is stricter than the page here (see DFM).
TRACK_FLOOR_MM = {
    "2L": {1: 0.10, 2: 0.16, 2.5: 0.20, 3.5: 0.25, 4.5: 0.30},
    "ML": {1: 0.09, 2: 0.16},
}
# Preset values (mil): the least that JLCDFM rates Good at 1 oz (spacing 6, width 5), then about 25 % above the floor.
SPACE_MIL = {1: 6, 2: 8, 2.5: 10, 3.5: 13, 4.5: 15}
WIDTH_MIN_MIL = {1: 5, 2: 8, 2.5: 10, 3.5: 13, 4.5: 15}

# PTH annular ring [P1]: (absolute minimum mm, preset mil). The preset is JLC's "recommended" (2-layer 0.25 mm, multilayer
# 0.20 mm) in whole mils; 2 oz and heavier copper: JLC asks >= 0.254 mm (10 mil).
PTH_RING = {("2L", 1): (0.18, 10), ("ML", 1): (0.15, 8)}
PTH_RING_2OZ = (0.254, 10)

# Mask bridge (dam) floor [P1], mm: 1 oz green/red/yellow/blue/purple 0.10, black/white 0.13; 2 oz 0.20 any colour.
SLIVER_FLOOR_MM = {"standard": 0.10, "dark_light": 0.13}
SLIVER_2OZ_MM = 0.20


def _num(v, default):
    m = re.search(r"\d+(?:\.\d+)?", str(v)) if v is not None and not isinstance(v, bool) else None
    return float(m.group()) if m else default


def copper_tier(oz, multilayer):
    """The copper weight column JLC's tables have for this board: 1, 2, or (2-layer only) 2.5 / 3.5 / 4.5 oz."""
    if oz <= 1.0:
        return 1
    if oz <= 2.0 or multilayer:      # multilayer is offered in 1 and 2 oz outer copper only
        return 2
    return next((t for t in (2.5, 3.5, 4.5) if oz <= t), 4.5)


def variant(board=None) -> dict:
    """{layers, multilayer, copper_oz, mask_colour, colour_class, name} for a project.json `board` block.
    Unknown or missing values mean 2 layers, 1 oz, green."""
    b = board if isinstance(board, dict) else {}
    layers = int(_num(b.get("layers"), 2)) or 2
    multilayer = layers >= 3
    tier = copper_tier(_num(b.get("copper_oz"), 1.0), multilayer)
    colour = str(b.get("mask_colour") or "green").strip().lower() or "green"
    dark_light = "black" in colour or "white" in colour
    return {"layers": layers, "multilayer": multilayer, "copper_oz": tier, "mask_colour": colour,
            "colour_class": "dark_light" if dark_light else "standard",
            "name": f"JLC {layers}-layer {tier:g} oz"}


def mil_text(mil) -> str:
    return (f"{mil:.4f}".rstrip("0").rstrip(".") or "0") + "mil"


def mm_to_mil_text(mm) -> str:
    return mil_text(mm / MIL)


def dfm_level(value_mm, range_mil) -> str:
    """JLCDFM's level for a value: Danger / Warning / Good / Not reported (its limits are whole mils)."""
    v = round(value_mm / MIL, 3)
    r0, r1, r2 = range_mil
    return "Danger" if v < r0 else "Warning" if v < r1 else "Good" if v < r2 else "Not reported"


def _g(x) -> str:
    return f"{x:.4g}"


def build_preset(board=None) -> dict:
    """The preset for a board: {name, variant, capabilities_url, reference, checked, rules: [...]}.
    Each rule has `attributes` (the .RUL record), the numbers in mm (`value_mm`, `min_mm` ...), `fab_min_mm`
    (JLC's floor), `jlcdfm` (the JLCDFM checks that look at it) and a `description` that says where it comes from."""
    v = variant(board)
    cls = "ML" if v["multilayer"] else "2L"
    where = "multilayer" if v["multilayer"] else "1-2 layer"
    tier = v["copper_oz"]
    oz = f"{tier:g} oz"
    floor = TRACK_FLOOR_MM[cls][tier]
    rules = []

    def add(kind, name, value, description, *, attrs, mm, scope1="All", scope2="All", priority=1,
            fab_min=None, fab_basis=None, dfm=None):
        rec = {"NAME": name, "RULEKIND": kind, "SCOPE1EXPRESSION": scope1, "SCOPE2EXPRESSION": scope2,
               **attrs, "ENABLED": "TRUE", "PRIORITY": str(priority)}
        r = {"name": name, "kind": kind, "scope1": scope1, "scope2": scope2, "value": value, **mm,
             "description": description, "fab_min_mm": fab_min}
        if fab_min is not None:
            r["fab_min_source"] = CAPABILITIES_URL
            r["fab_min_basis"] = fab_basis
        if dfm:
            r["jlcdfm"] = [{"check": c, "range_mil": DFM[c]} for c in dfm]
        r["attributes"] = rec
        rules.append(r)

    # -- clearance and track width
    space = SPACE_MIL[tier]
    r0, r1, _ = DFM["Trace spacing"]
    add("Clearance", "Clearance", mil_text(space),
        f"Copper to copper. JLC absolute minimum {_g(floor)} mm ({where}, {oz}) [P1, P3] is the fab floor; JLCDFM flags "
        f"Danger below {r0} mil and Warning below {r1} mil, so the preset is {space} mil.",
        attrs={"GAP": mil_text(space), "GENERICCLEARANCE": mil_text(space)},
        mm={"value_mm": round(space * MIL, 4)}, fab_min=floor,
        fab_basis=f"JLC absolute minimum track/space, {where}, {oz} [P1, P3]", dfm=["Trace spacing"])
    wmin = WIDTH_MIN_MIL[tier]
    wpref = max(8, wmin + 2)
    r0, r1, _ = DFM["Trace width"]
    add("Width", "Width", f"Min: {mil_text(wmin)}, Pref: {mil_text(wpref)}, Max: 40mil",
        f"Track width. JLC absolute minimum {_g(floor)} mm ({where}, {oz}) [P1, P3] is the fab floor; JLCDFM flags Danger below "
        f"{r0} mil and Warning below {r1} mil, so the minimum is {wmin} mil. Width tolerance is +/-20 % [P1].",
        attrs={"MINLIMIT": mil_text(wmin), "PREFEREDWIDTH": mil_text(wpref), "MAXLIMIT": "40mil"},
        mm={"min_mm": round(wmin * MIL, 4), "pref_mm": round(wpref * MIL, 4), "max_mm": round(40 * MIL, 4)},
        fab_min=floor, fab_basis=f"JLC absolute minimum track/space, {where}, {oz} [P1, P3]", dfm=["Trace width"])

    # -- vias, holes, annular ring
    vh, vd = (0.3, 0.5) if v["layers"] == 1 else (0.15, 0.25)
    add("RoutingVias", "RoutingVias", "Hole: 12mil, Dia: 24mil",
        f"Routing via. JLC's smallest via is {_g(vh)} / {_g(vd)} mm hole / diameter, diameter >= hole + 0.1 mm, hole 0.2 mm or more "
        "preferred [P1]. 0.3 / 0.6 mm avoids JLC's via price steps [P1]; as 12 / 24 mil its ring is 6 mil, the least JLCDFM rates Good.",
        attrs={"MINHOLEWIDTH": "12mil", "HOLEWIDTH": "12mil", "MAXHOLEWIDTH": "40mil",
               "MINWIDTH": "24mil", "WIDTH": "24mil", "MAXWIDTH": "60mil"},
        mm={"hole_mm": round(12 * MIL, 4), "dia_mm": round(24 * MIL, 4)},
        fab_min={"hole": vh, "dia": vd}, fab_basis="JLC minimum via hole / diameter [P1]")
    if tier >= 2:
        pth_floor, pth_mil = PTH_RING_2OZ
    else:
        pth_floor, pth_mil = PTH_RING[(cls, 1)]
    r0, r1, _ = DFM["Annular ring"]
    add("MinimumAnnularRing", "MinimumAnnularRing_PTH", mil_text(pth_mil),
        f"Annular ring of plated component holes (pads). JLC {where}, {oz}: absolute minimum {_g(pth_floor)} mm [P1]; "
        f"the preset is JLC's recommended ring in whole mils. JLCDFM flags Danger below {r0} mil and Warning below {r1} mil.",
        attrs={"MINIMUMRING": mil_text(pth_mil)}, mm={"value_mm": round(pth_mil * MIL, 4)},
        scope1="IsPad", priority=1, fab_min=pth_floor,
        fab_basis=f"JLC PTH annular ring, {where}, {oz} [P1]", dfm=["Annular ring"])
    add("MinimumAnnularRing", "MinimumAnnularRing_Via", mil_text(6),
        f"Annular ring of vias. A via at JLC's minimum ({_g(vh)} / {_g(vd)} mm) has a {_g((vd - vh) / 2)} mm ring: via rings follow the "
        f"via diameter rule, not the PTH rule [P1]. JLCDFM rates a ring below {r0} mil Danger and below {r1} mil Warning, so the preset is 6 mil.",
        attrs={"MINIMUMRING": mil_text(6)}, mm={"value_mm": round(6 * MIL, 4)},
        scope1="IsVia", priority=2, fab_min=round((vd - vh) / 2, 4),
        fab_basis="JLC minimum via: (diameter - hole) / 2 [P1]", dfm=["Annular ring"])
    add("HoleSize", "HoleSize", "Min: 12mil, Max: 248.0315mil",
        f"Drill range. JLC drills {_g(0.3 if v['layers'] == 1 else 0.15)} to 6.3 mm; larger holes are CNC-routed from a smaller drill [P1]. "
        "The preset minimum is the standard 0.3 mm drill: holes below it can add a surcharge [P13].",
        attrs={"MINLIMIT": "12mil", "MAXLIMIT": "248.0315mil"},
        mm={"min_mm": round(12 * MIL, 4), "max_mm": 6.3},
        fab_min={"min": 0.3 if v["layers"] == 1 else 0.15}, fab_basis="JLC smallest drill [P1]")

    # -- solder mask and silkscreen
    add("SilkToSolderMaskClearance", "SilkToSolderMaskClearance", "6mil",
        "Silkscreen to mask opening. JLC: pad to silkscreen 0.15 mm, silk line >= 0.15 mm [P1]. Altium measures to the mask "
        "opening, so silk to pad is this plus the mask expansion; JLCDFM flags silk to pad Danger below 5 mil, Warning below 7 mil.",
        attrs={"MINSILKSCREENTOMASKGAP": "6mil", "CLEARANCETOEXPOSEDCOPPER": "TRUE"},
        mm={"value_mm": round(6 * MIL, 4)}, fab_min=0.15, fab_basis="JLC pad to silkscreen [P1]")
    add("SolderMaskExpansion", "SolderMaskExpansion", "2mil",
        "Mask opening beyond the pad, per side. JLC accepts 1:1 openings (zero expansion) since the June 2025 LDI upgrade, calls 0.1 mm "
        "generally recommended and asks >= 0.09 mm between an opening and a neighbouring trace; a negative expansion covers the pad "
        "[P1, P7]. 2 mil (0.05 mm) is the advisor's start value inside that range, not a JLC standard.",
        attrs={"EXPANSION": "2mil"}, mm={"value_mm": round(2 * MIL, 4)})
    if tier >= 2:
        sliver_floor, sliver_mil, colour_txt = SLIVER_2OZ_MM, 8, "2 oz, any colour"
    else:
        sliver_floor, sliver_mil = SLIVER_FLOOR_MM[v["colour_class"]], 6
        colour_txt = f"1 oz, {v['mask_colour']} mask"
    r0, r1, _ = DFM["Soldermask bridge"]
    add("MinimumSolderMaskSliver", "MinimumSolderMaskSliver", mil_text(sliver_mil),
        f"Mask dam between two openings. JLC minimum bridge {_g(sliver_floor)} mm ({colour_txt}; green, red, yellow, blue, purple 0.10 mm, "
        f"black, white 0.13 mm at 1 oz; 2 oz 0.20 mm) [P1]. JLCDFM flags Danger below {r0} mil and Warning below {r1} mil, "
        f"so the preset is {sliver_mil} mil.",
        attrs={"MINSOLDERMASKWIDTH": mil_text(sliver_mil)}, mm={"value_mm": round(sliver_mil * MIL, 4)},
        fab_min=sliver_floor, fab_basis=f"JLC mask bridge, {colour_txt} [P1]", dfm=["Soldermask bridge"])

    # -- board edge and hole to hole
    r0, r1, _ = DFM["Trace to board edge"]
    add("BoardOutlineClearance", "BoardOutlineClearance", "12mil",
        "Copper to board edge. JLC: routed edge >= 0.2 mm, V-cut edge >= 0.4 mm [P1]; Economic assembly asks > 0.3 mm [P24 #14]. "
        f"JLCDFM flags trace to edge Danger below {r0} mil, Warning below {r1} mil (0.2 mm is a Warning) and pad to edge Warning "
        "below 8 mil, so the preset is 12 mil (0.3 mm). Use 16 mil on V-cut edges.",
        attrs={"GAP": "12mil", "GENERICCLEARANCE": "12mil"}, mm={"value_mm": round(12 * MIL, 4)},
        fab_min=0.2, fab_basis="JLC copper to routed edge [P1]", dfm=["Trace to board edge", "Pad to board edge"])
    r0, r1, _ = DFM["Plated through-hole spacing"]
    add("HoleToHoleClearance", "HoleToHoleClearance_PTH", "18mil",
        "Hole edge to hole edge, component hole to component hole. JLC pad to pad 0.45 mm [P1]. JLCDFM only flags plated holes "
        "closer than 10 mil, so it does not catch a 0.40 mm gap that JLC's page forbids.",
        attrs={"GAP": "18mil"}, mm={"value_mm": round(18 * MIL, 4)}, scope1="IsPad", scope2="IsPad", priority=1,
        fab_min=0.45, fab_basis="JLC hole to hole, pad to pad [P1]", dfm=["Plated through-hole spacing"])
    add("HoleToHoleClearance", "HoleToHoleClearance", "8mil",
        f"Hole edge to hole edge, every other pair (via to via). JLC via to via 0.2 mm [P1]. JLCDFM flags plated hole spacing Danger "
        f"below {r0} mil and Warning below {r1} mil, so the preset is 8 mil.",
        attrs={"GAP": "8mil"}, mm={"value_mm": round(8 * MIL, 4)}, priority=2,
        fab_min=0.2, fab_basis="JLC hole to hole, via to via [P1]", dfm=["Plated through-hole spacing"])
    add("ViasUnderSMD", "ViasUnderSMD", "Not allowed",
        "No via in an SMD pad. JLC makes via-in-pad only as epoxy- or copper-filled and plated-over vias, which cost extra on boards "
        "under 6 layers [P1, P5]; JLCDFM warns about a via placed within a pad.",
        attrs={"ALLOWED": "FALSE"}, mm={})

    return {
        "name": v["name"],
        "variant": {k: v[k] for k in ("layers", "multilayer", "copper_oz", "mask_colour")},
        "_comment": f"JLC preset for {v['name']}. Fab floors are JLC's own minimums; values are chosen so JLCDFM rates them Good. "
                    f"Checked {CHECKED}, see {REFERENCE}.",
        "capabilities_url": CAPABILITIES_URL,
        "reference": REFERENCE,
        "checked": CHECKED,
        "rules": rules,
    }
