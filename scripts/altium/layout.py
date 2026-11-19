"""PCB placement for the agent's `altium.place_pcb` action (pure Python: no Altium here, so it can be tested).

Same pattern as draw.py: plan here, keep the Pascal side to dumb object creation, verify from the saved file.
Units are mm, rotation is degrees counter-clockwise like Altium, y grows upwards.

  board_size(idea)                  (width, height) mm from idea["board"] or from the requirements text, else None
  footprint_box(fp)                 courtyard box of a PcbLib footprint (pads + margin), relative to its origin
  plan_outline(size)                the outline to create when the PcbDoc has none
  plan_placement(...)               {"places": [{ref, footprint, x, y, rot}], "warnings", "errors"}
  plan_commands(...)                the script lines for the bridge (PCBBEGIN, OUTLINE, PLACEFP, PADNET, PCBSAVE)
  unrouted(doc)                     nets whose pads are not all joined by tracks, vias and pads in a read_pcbdoc dict
  verify_layout(...)                saved PcbDoc against the netlist: parts, footprints, pad nets, overlaps, edges
"""
import math
import re

EDGE_MM = 1.0           # parts keep this far from the board edge (connectors may touch it: see CONNECTOR_OVERHANG)
GAP_MM = 0.6            # clearance between two courtyards (never below the JLC clearance rule passed in)
COURT_MM = 0.25         # courtyard margin around pads
STEP_MM = 0.5           # search grid
FINE_STEP_MM = 0.25     # the search grid beside a supply pin: two caps side by side only fit (0.6 mm between courtyards) on a quarter-mm grid
CAP_SHARE_MM = 10.0     # a decoupling cap's score grows by this for every cap its IC already has (one cap per IC first)
HALO_MM = 2.5          # the room kept round an IC with supply pins for its decoupling caps while the other ICs are placed
FANOUT_PITCH_MM = 0.8    # an IC whose pads are this close (centre to centre) or closer is fine pitch: its pins need a fan-out band
FANOUT_PITCHES = 2.0     # the fan-out band of a fine-pitch IC, for its decoupling caps and crystal: this many pitches beyond its pads (courtyards included),
                        # room for a via and a track at 0.127 mm rules; their own tracks cross it
FANOUT_FREE_PITCHES = 6.0   # the same band for every other part: wide enough for the tracks of a pin row to run along it to the gaps between parts
CSP_TRIES = 5000        # choices the search for the places beside an IC makes before it gives up
CSP_DOMAIN = 400        # candidate places kept for one part
IC_TRIES = 10           # places (turns, designator sides) tried for an IC whose crystal or caps did not all find a place beside it
IC_TRY_APART_MM = 0.75   # a place tried again with the same turn and designator side is this far from every place tried before
DECAP_NEAR_MM = 3.0      # this tool's threshold (datasheets only say "as close as possible"): pad to pad, a decoupling cap's rail pad to its supply pin pad
DECAP_TOL_MM = 0.05      # a cap this much over DECAP_NEAR_MM still passes (so '3.0 mm, limit 3 mm' is never reported)
DECAP_WINDOW_MM = 3.0   # the search for a place around a supply pin reaches this much beyond DECAP_NEAR_MM
PIN_SHARE_MM = 100.0     # score added for every cap a supply pin already has: each pin gets its own cap while caps are left
BULK_F = 10e-6           # a cap above this is bulk, not decoupling: placed near a pin but not held to DECAP_NEAR_MM
XTAL_NEAR_MM = 5.0       # a crystal farther than this from the MCU oscillator pins gets a finding (placement guideline, ST AN2867)
MAX_FILL = 0.55         # courtyard area / board area above which we refuse: nothing is left for routing
MIL = 0.0254
_CELL = 2.0             # mm: the cell of the obstacle index of the placement search
LABEL_H = 1.0          # designator text height, mm
LABEL_LINE = 0.16       # stroke, mm: JLC's minimum is 0.15, but JLCDFM warns below 6 mil (0.1524), so 0.15 gave 45 warnings (16/11)
LABEL_W = 0.65         # width of one designator character at LABEL_H
LABEL_GAP = 0.25       # between a part and its designator
EDGE_COPPER_MM = 0.3   # copper (pads) stays this far from the board edge (JLC)
SILK_EDGE_MM = 0.2     # a connector's silkscreen outline stays EDGE_COPPER_MM + this from the board edge: the outline clearance rule (12 mil) is
                       # measured to the edge of the silkscreen line (0.25 mm wide), and Altium's DRC reports a connector flush with the edge
OPEN_MIN_MM = 0.8
CONNECTOR_OVERHANG_MM = 1.0   # a connector's body may stick out of the outline this far, on its mating side only
_GND = re.compile(r"^(?:[ADPSEC]?GND\w*|VSS\w*|GROUND)$", re.I)
_RAIL = re.compile(r"^[+-]\d|^\d+V\d*$|^(?:VCC|VDD|VBUS|VBAT|VIN|VSYS|VDDA|VCCA|AVDD|DVDD)\w*$", re.I)
_Q = "[\"״”“'׳]{1,2}"
_UNIT = rf"(?:mm|cm|ממ|מ{_Q}מ|ס{_Q}מ|סמ)"      # mm cm מ"מ ממ ס"מ סמ
_NUM = r"(\d+(?:[.,]\d+)?)"
# "30x25", "30 X 25 mm", "30mm × 25mm", "30 על 25 מ\"מ", "3,5 by 2 cm": two numbers with a separator between them
_SIZE = re.compile(rf"(?<![\w.,]){_NUM}\s*({_UNIT})?\s*(?:[xX×*]|\bby\b|על)\s*{_NUM}\s*({_UNIT})?(?![\w])", re.I)
_HE = "א-ת"
# English words; Hebrew words whole (one prefix letter allowed: הכרטיס, בלוח), "לוח זמנים" (a schedule) is not a board
_BOARD_WORD = re.compile(r"\b(?:board|pcb|outline|dimensions?)\b|(?<![" + _HE + r"])[והבלמשכ]?"
                         r"(?:גודל|מידות|כרטיס|לוח(?!\s+זמנים))"
                         r"(?![" + _HE + "])", re.I)       # board pcb outline dimensions | גודל מידות כרטיס לוח


def is_gnd(net):
    return bool(_GND.match(str(net or "").strip()))


def is_rail(net):
    return bool(_RAIL.match(str(net or "").strip())) and not is_gnd(net)


def is_connector(ref):
    return bool(re.match(r"^(?:J|P|CON|TERM|USB)\d", ref, re.I))



_UNIT_F = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3}


def cap_farads(value):
    """Capacitance in farads from a BOM value like '100nF', '0.1uF', '4.7 uF 16V', '10u', or None when it cannot be read."""
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:([pnuµμm])\s*F?|F)(?![A-Za-z])", str(value or ""), re.I)
    return float(m.group(1).replace(",", ".")) * _UNIT_F[(m.group(2) or "").lower()] if m else None


# Oscillator pin names of an MCU: OSC_IN/OSC_OUT, OSC1/OSC2, OSC32_IN/OUT, XTAL1/2, XTAL_IN/OUT, XIN/XOUT, XI/XO, CLKIN, PH0-OSC_IN, PC14-OSC32_IN
_OSC_PIN = re.compile(r"(?<![A-Z0-9])(?:OSC\d*_?(?:IN|OUT|I|O)?|XTAL\d?(?:_?(?:IN|OUT))?|X(?:IN|OUT|I|O)\d*|CLK_?IN)(?![A-Z0-9]|_?(?:IN|OUT))", re.I)
_XTAL_TEXT = re.compile(r"crystal|xtal|resonator|\d\s*[kM]Hz", re.I)
# Supply pins by NAME (a RESET/EN/CE pin tied to the rail is not one): VDD VDDA AVDD DVDD VDDIO VCC VCCA VBAT VCAP V+ (also VDD_1, VDD/VDDA...)
_SUPPLY_PIN = re.compile(r"^(?:[AD]?VDD\w*|[AD]?VCC\w*|VBAT\w*|VCAP\w*|V\+)(?:[/\-][\w+\-]+)*$", re.I)
_REG_PIN = re.compile(r"^(?:V?OUT\d*|V?IN\d*|VO|VI|VOUT\w*|VIN\w*|OUTPUT|INPUT|TAB)$", re.I)       # a regulator's input/output pins
_REG_TEXT = re.compile(r"regulator|\bldo\b|dc-?dc|\bbuck\b|\bboost\b|converter|switcher", re.I)
_REG_FP = re.compile(r"SOT-?223|SOT-?23-?5|SOT-?89|TO-?252|DPAK|TO-?220|TO-?263", re.I)


def is_osc_pin(name):
    return bool(_OSC_PIN.search(str(name or "")))


def is_supply_pin_name(name):
    return bool(_SUPPLY_PIN.match(str(name or "").strip()))


def part_value(part):
    """The BOM value of a netlist part (bridge passes it as bom_value so that PLACEFP's own value argument stays as it was)."""
    return part.get("bom_value") or part.get("value") or ""


def part_text(part):
    return " ".join(str(part.get(k) or "") for k in ("bom_value", "value", "bom_description", "description", "bom_role", "role",
                                                      "lib_ref", "symbol", "comment"))


def is_regulator(part, footprint=""):
    """A voltage regulator: its role or BOM text says so, or its footprint is a regulator package (SOT-223, SOT-23-5, ...)."""
    return bool(_REG_TEXT.search(part_text(part)) or _REG_FP.search(str(footprint or part.get("footprint") or "")))


def is_ic_ref(ref):
    return bool(re.match(r"^(?:U|IC)\d", str(ref), re.I))


def is_crystal(part, npads):
    """A crystal or resonator: a Y or X reference with 2 to 4 pads (a resonator has 3), or crystal/xtal/resonator/MHz in the BOM text
    with 2 or 4 pads. (The caller still requires a link to an MCU oscillator pin.)"""
    ref = str(part.get("ref") or "")
    if re.match(r"^[YX]\d", ref, re.I):
        return 2 <= npads <= 4
    if re.match(r"^[CRLDQUJP]\d", ref, re.I) or npads not in (2, 4):
        return False
    return bool(_XTAL_TEXT.search(part_text(part)))


_TOKEN = re.compile(r"[^\W\d_]+|\d+(?:[.,]\d+)?|[,;:()\[\]|]")
_ARTICLE = re.compile(r"(?:a|an|the)$", re.I)
# the words that may stand right before a board size: size words, "about", "of", "be" ("the PCB must be 50x40"), Hebrew alike
_PRE_OK = re.compile(r"(?:size[sd]?|dimensions?|outline|approx|approximately|about|around|roughly|max|maximum|of|is|be|at|most|"
                     r"to|under|within|גודל|בגודל|מידות|במידות|מוערך|מוערכות|בערך|כ|של|עד|הוא|מקסימום|כמעט)$", re.I)
# the words that may follow it: "30x25 mm board", "100 x 80 mm with 4 M3 holes"
_POST_OK = re.compile(r"(?:with|and|or|max|maximum|approx|approximately|total|overall|outline|עם|או|מקסימום|בערך|בלבד|לכל|סה)$", re.I)


def _tied_to_board(before, after):
    """True when a W x H found in a sentence is a board size by the words beside it: the word before it (articles skipped) is a board
    or size word or a list break (",", start), and the word after it (its unit already read) is none, a board word or a joining word.
    "board shows a 128x64 OLED", "OLED 128x64", "LCD 16x2", "8x8 matrix" are not."""
    nxt = _TOKEN.findall(after)[:1]
    if nxt and _BOARD_WORD.fullmatch(nxt[0]):
        return True                                    # "a 40x30 board", "on a 40 x 30 mm PCB"
    toks = _TOKEN.findall(before)
    while toks and _ARTICLE.match(toks[-1]):
        toks.pop()
    if toks and not re.match(r"[,;:()\[\]|]$", toks[-1]):
        w = toks[-1]
        if w[0].isdigit() or not (_BOARD_WORD.fullmatch(w) or _PRE_OK.match(w)):
            return False
    if nxt and not re.match(r"[,;:()\[\]|]$", nxt[0]):
        w = nxt[0]
        if w[0].isdigit() or not _POST_OK.match(w):
            return False
    return True


def _sizes_in(text, topic=""):
    """(w, h) mm candidates in one piece of text. The sentence (or the topic) must talk about the board, the unit (mm, cm, מ"מ, ס"מ; none = mm)
    is converted, and both sides must be 10..500 mm."""
    out = []
    for sentence in re.split(r"[;\n]|\.\s|׃", str(text or "")):
        talks = bool(_BOARD_WORD.search(f"{topic} {sentence}"))
        for m in _SIZE.finditer(sentence):
            if not _tied_to_board(sentence[:m.start()], sentence[m.end():]):
                continue                               # "a board with a 128x64 OLED": the size of another thing
            w, h = float(m.group(1).replace(",", ".")), float(m.group(3).replace(",", "."))
            u1, u2 = (m.group(2) or "").lower(), (m.group(4) or "").lower()
            u1, u2 = u1 or u2, u2 or u1                # a unit written once covers both sides, two units may differ
            w, h = w * (10 if u1 == "cm" or u1.startswith("ס") else 1), h * (10 if u2 == "cm" or u2.startswith("ס") else 1)
            if talks and 10 <= w <= 500 and 10 <= h <= 500:
                out.append((w, h))
    return out


def board_size(idea):
    """(width_mm, height_mm) from idea["board"] = {"width_mm", "height_mm"}, else the first 'W x H' in the agreed list, the
    requirements or the goal/description (English or Hebrew, mm or cm), else None. Never a guess."""
    idea = idea or {}
    b = idea.get("board")
    if isinstance(b, dict) and b.get("width_mm") and b.get("height_mm"):
        return float(b["width_mm"]), float(b["height_mm"])
    for key in ("requirements", "agreed"):
        for r in idea.get(key, []) or []:
            if isinstance(r, dict):
                found = _sizes_in(r.get("text"), r.get("topic", ""))
            else:
                found = _sizes_in(r)
            if found:
                return found[0]
    for key in ("goal", "describe", "description", "brief"):
        found = _sizes_in(idea.get(key))
        if found:
            return found[0]
    return None


def plan_outline(size, origin=(0.0, 0.0)):
    """Rectangle outline [x0, y0, x1, y1] mm for a (w, h) board. A board must be at least 10 x 10 and at most 500 x 500 mm."""
    if not size:
        return None
    w, h = size
    if not (10 <= w <= 500 and 10 <= h <= 500):
        return None
    return [origin[0], origin[1], origin[0] + w, origin[1] + h]


# ---- board size against the parts (an early estimate: the student is told before Place, the size is never changed here) ----
TIGHT_FILL = 0.5          # part area / board area (one side) above which the board is called clearly too tight (Place refuses above MAX_FILL)
TARGET_FILL = 0.4         # the board size suggested leaves this share covered by parts
_PASSIVE_MM2 = (("0201", 1.6), ("0402", 3.0), ("0603", 5.0), ("0805", 7.5), ("1206", 12.0), ("1210", 17.0), ("2512", 40.0))
_REF_MM2 = {"R": 5.0, "C": 5.0, "L": 8.0, "FB": 5.0, "F": 8.0, "D": 6.0, "LED": 5.0, "Q": 9.0, "U": 40.0, "IC": 40.0, "J": 40.0, "P": 30.0,
            "CN": 40.0, "USB": 40.0, "SW": 30.0, "S": 30.0, "Y": 20.0, "X": 20.0, "TP": 4.0, "BT": 80.0, "K": 60.0}


def package_area_mm2(text="", ref=""):
    """Typical courtyard area (mm2) of a part from its footprint/package name (or, with no name, from its designator letters). A rough
    figure for the time before the library is built; the real footprint is used once it exists."""
    t = str(text or "").lower()
    n = [int(m) for m in re.findall(r"(\d+)", t)]
    for key, a in _PASSIVE_MM2:
        if key in t:
            return a
    if re.search(r"sot-?223", t):
        return 45.0
    if re.search(r"sot-?23|sot-?323|sot-?363|sc-?70|sod-?323", t):
        return 9.0
    pins = max([v for v in n if 3 <= v <= 400] or [0])
    if pins:
        if re.search(r"qfn|dfn|son|wson", t):
            return 1.1 * pins + 8
        if re.search(r"lqfp|tqfp|qfp", t):
            return 2.0 * pins + 20
        if re.search(r"tssop|ssop|msop|vssop", t):
            return 3.5 * pins + 6
        if re.search(r"soic|sop|so-?\d", t):
            return 5.5 * pins + 6
        if "bga" in t:
            return 0.9 * pins + 10
        if re.search(r"header|pin|jst|conn|socket|terminal", t):
            return 7.0 * pins + 10
    if re.search(r"usb", t):
        return 60.0
    letters = re.match(r"[A-Za-z]+", str(ref or ""))
    return _REF_MM2.get(letters.group(0).upper(), 20.0) if letters else 20.0


def board_fit(parts, size, footprints=None, sides=1):
    """The courtyard area the parts need against the board, per side. parts: [{ref, footprint (name), package/description (optional)}];
    size: (w, h) mm; footprints: {name: footprint} of the built library (the real courtyard is used for the parts it has; the others
    are estimated from their package). Returns {"area", "board", "fill", "tight", "from_library", "estimated", "parts", "suggest"}
    (suggest: a (w, h) in whole 5 mm steps with the same proportions, or None when the board is not too tight) or None (no size or no parts)."""
    if not size or not parts or not (size[0] > 0 and size[1] > 0):
        return None
    sides = max(1, int(sides or 1))
    area, lib, est = 0.0, 0, 0
    for p in parts:
        fp = (footprints or {}).get(p.get("footprint"))
        box = footprint_box(fp) if fp else None
        if box is not None:
            area += (box[2] - box[0]) * (box[3] - box[1])
            lib += 1
        else:
            area += package_area_mm2(" ".join(str(p.get(k) or "") for k in ("footprint", "package", "description")), p.get("ref") or "")
            est += 1
    area /= sides
    board = float(size[0]) * float(size[1])
    fill = area / board
    tight = fill > TIGHT_FILL
    suggest = None
    if tight:
        k = math.sqrt(area / TARGET_FILL / board)
        suggest = (5 * math.ceil(size[0] * k / 5), 5 * math.ceil(size[1] * k / 5))
    return {"area": area, "board": board, "fill": fill, "tight": tight, "from_library": lib, "estimated": est, "parts": len(parts),
            "suggest": suggest}


def fit_text(fit, size):
    """One plain sentence for a board_fit result that is tight (the figures and a size to try); '' when the board is fine."""
    if not fit or not fit["tight"]:
        return ""
    how = ("from the library footprints" if not fit["estimated"] else
           "estimated from typical package sizes" if not fit["from_library"] else "from the library footprints and typical package sizes")
    sw, sh = fit["suggest"]
    return (f"The {fit['parts']} parts need about {fit['area']:.0f} mm2 of board on one side ({how}); the {size[0]:g} x {size[1]:g} mm board "
            f"has {fit['board']:.0f} mm2, so {100 * fit['fill']:.0f}% would be covered and little is left for tracks. Try about "
            f"{sw:g} x {sh:g} mm ({sw * sh:.0f} mm2). The board size was not changed.")


def _pad_rect(p):
    """[x0, y0, x1, y1] of a read_pcblib pad (mil units in, mm out), relative to the footprint origin; a pad turned 90 or 270
    degrees swaps its sides, any other angle takes the square that holds it."""
    x, y = p["x"] * MIL, p["y"] * MIL
    sx, sy = p.get("xsize", 0) * MIL, p.get("ysize", 0) * MIL
    rot = float(p.get("rotation") or 0) % 180
    if abs(rot - 90) < 0.5:
        sx, sy = sy, sx
    elif min(rot, 180 - rot) > 0.5:
        sx = sy = math.hypot(sx, sy)
    return [x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2]


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def pads_box(fp):
    """The box of the copper of a read_pcblib footprint, mm, relative to its origin (None without sized pads)."""
    return _union([_pad_rect(p) for p in fp.get("pads", []) if "x" in p])


def footprint_extent(fp):
    """The real extent of a read_pcblib footprint, mm, relative to its origin: the union of its pads (turned as they are), its
    silkscreen, its mechanical layers (courtyard, assembly) and the outline of its 3D body. A part is as big as the biggest of them,
    not as its pads: a connector's shell and plug end are far outside its pads. None when there is nothing."""
    ext = fp.get("extent") or {}
    return _union([pads_box(fp)] + [[v * MIL for v in ext[k]] for k in ("silk", "mech", "body") if ext.get(k)])


def _silk_box(fp):
    """The box of the silkscreen of a read_pcblib footprint, mm, relative to its origin (None when it has none)."""
    silk = (fp.get("extent") or {}).get("silk")
    return [v * MIL for v in silk] if silk else None


def footprint_box(fp, margin=COURT_MM):
    """footprint_extent grown by `margin`: the box other parts keep out of. None when the footprint has no pads with a size."""
    e = footprint_extent(fp)
    if e is None or pads_box(fp) is None:
        return None
    return [e[0] - margin, e[1] - margin, e[2] + margin, e[3] + margin]


def opening_dir(fp):
    """The way a connector footprint opens (degrees, 0 = +x, 90 = +y, rotation 0), from where the part reaches out from its pads:
    the silkscreen and mechanical outline (the plug side) against the centre of the copper. None when it cannot be told (the outline
    is centred on the pads, less than OPEN_MIN_MM off)."""
    pb, ext = pads_box(fp), fp.get("extent") or {}
    outline = _union([[v * MIL for v in ext[k]] for k in ("silk", "mech") if ext.get(k)])
    if pb is None or outline is None:
        return None
    pads = [_pad_rect(p) for p in fp.get("pads", []) if "x" in p]
    px = sum((b[0] + b[2]) / 2 for b in pads) / len(pads)
    py = sum((b[1] + b[3]) / 2 for b in pads) / len(pads)
    dx, dy = (outline[0] + outline[2]) / 2 - px, (outline[1] + outline[3]) / 2 - py
    if math.hypot(dx, dy) < OPEN_MIN_MM:
        return None
    return int(round(math.degrees(math.atan2(dy, dx)) / 90.0)) % 4 * 90


def label_size(ref):
    """(width, height) mm of a designator drawn at LABEL_H."""
    return max(len(ref), 1) * LABEL_W, LABEL_H


def label_rotation(part_rot, vertical=False):
    """Text rotation of a designator, degrees: 0 (horizontal) or 90 (vertical), never 180 or 270 (upside down, or reading the wrong
    way). The part's own rotation must not carry over: Altium turns a component's designator with it, so a part at 180 came out
    upside down (C6, C9, U2, J2 of the Live-STM32 board). The label boxes this module reserves are horizontal, so 0 unless asked."""
    return (90 if vertical else 0) % 180


def rot_point(x, y, rot):
    r = int(rot) % 360
    return {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[r]


def rot_box(box, rot):
    pts = [rot_point(x, y, rot) for x in (box[0], box[2]) for y in (box[1], box[3])]
    return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]


def _hit(a, b, gap):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def _inside(box, outline, edge):
    return box[0] >= outline[0] + edge and box[1] >= outline[1] + edge and box[2] <= outline[2] - edge and box[3] <= outline[3] - edge


def _moved(box, x, y):
    return [box[0] + x, box[1] + y, box[2] + x, box[3] + y]


def _pads_of(part, fp):
    """{pad name: (x, y, net)} relative to the footprint origin, mm."""
    nets = {str(p.get("num", p.get("number", ""))): str(p.get("net") or "") for p in part.get("pins", [])}
    out = {}
    for p in fp.get("pads", []):
        if "x" in p:
            out[p["name"]] = (p["x"] * MIL, p["y"] * MIL, nets.get(p["name"], ""))
    return out


def _label_rect(box, ref, side):
    """The designator's box above ("top") or below the part box, centred on it, or (when neither fits) left or right of it, centred
    on it (the text is drawn upright, whatever the part's turn)."""
    w, h = label_size(ref)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if side == "top":
        return [cx - w / 2, box[3] + LABEL_GAP, cx + w / 2, box[3] + LABEL_GAP + h]
    if side == "left":
        return [box[0] - LABEL_GAP - w, cy - h / 2, box[0] - LABEL_GAP, cy + h / 2]
    if side == "right":
        return [box[2] + LABEL_GAP, cy - h / 2, box[2] + LABEL_GAP + w, cy + h / 2]
    return [cx - w / 2, box[1] - LABEL_GAP - h, cx + w / 2, box[1] - LABEL_GAP]


def plan_placement(parts, footprints, outline, clearance_mm=0.0, keep=None, connector_dirs=None, edge_copper_mm=EDGE_COPPER_MM):
    """The placement (see _plan_placement). Connectors go to the edges first and a big one can take the room a regulator needs for its
    caps: when a decoupling cap does not get next to its supply pin, the crystal is farther than XTAL_NEAR_MM from the oscillator pins
    (or a part finds no place), the plan is made again, with the connectors starting on another side of the board (up to three more)
    and, on a board with a crystal, with the crystal placed before the decoupling caps instead of after them (the two compete for the
    room beside the MCU). When no plan is free of findings, the same plans are made once more with the MCU (any IC with a crystal or
    caps to place beside it) tried at other places and turns: where the board edge leaves room for them beside its pins (a first place
    that leaves a crystal or a supply pin without room is the usual reason for a finding). The best plan is returned: fewest errors,
    then caps too far, then crystals too far, then findings; the first one on a tie."""
    best, best_key = None, None
    for trials in (False, True):
        for shift in range(4 if any(is_connector(p["ref"]) for p in parts) else 1):
            plan = _plan_placement(parts, footprints, outline, clearance_mm, keep, connector_dirs, edge_copper_mm, shift, best_key, trials)
            if plan is None:                        # cannot beat the best so far
                continue
            far = sum(1 for f in plan.get("findings", []) if f["level"] == "error")
            xfar = sum(1 for c in plan.get("crystals", []) if c["max_mm"] > XTAL_NEAR_MM)
            key = (len(plan["errors"]), far, xfar, len(plan.get("findings", [])))
            if best is None or key < best_key:
                best, best_key = plan, key
            if key == (0, 0, 0, 0):
                break                               # nothing left to improve
        if best_key == (0, 0, 0, 0):
            break
    best.setdefault("findings", [])
    best.setdefault("crystals", [])
    return best


def _plan_placement(parts, footprints, outline, clearance_mm, keep, connector_dirs, edge_copper_mm, shift, bound=None, trials=False):
    """Places every part inside the outline, by its real extent (pads, silkscreen, courtyard, 3D body) plus the strip its designator
    needs, so no two parts and no designator overlap.
    parts: netlist parts [{ref, footprint, pins: [{num, net}]}]; footprints: {footprint name: read_pcblib footprint};
    outline: [x0, y0, x1, y1] mm; clearance_mm: the board's copper clearance rule (parts keep at least this far apart);
    keep: {ref: (x, y, rot)} parts that are already placed and must not move (their boxes are obstacles);
    connector_dirs: {ref: degrees} which way the opening faces at rotation 0 (0 = +x); else read from the footprint (opening_dir).
    Order: connectors flush with an edge (centred along it, turned so the opening faces out, their pads edge_copper_mm inside the
    outline), ICs largest first, then decoupling caps beside the supply pin they serve, then every other part beside the parts it
    shares signal nets with, pulled towards the middle of the board while the board is roomy. Readable, not optimal.
    Crystals (a Y part, or crystal/xtal/resonator/MHz in its BOM text, whose nets reach MCU oscillator pins by pin name) are placed
    right after the ICs as close as possible to those pins, their load caps (crystal net to GND) next to them; the crystal-to-pin
    distance is reported in "crystals" and a finding says so above XTAL_NEAR_MM (ST AN2867; the threshold is this tool's).
    Every supply pin of an IC gets its own nearest decoupling cap while caps are left (smallest value first, so 100 nF is nearest);
    the target is DECAP_NEAR_MM (this tool's threshold) pad to pad, for supply pins by NAME of U parts with more than 4 pads; a regulator only gets a soft warning. "findings" [{level, ref, text}]: level "error" = a cap that is farther than that (also
    copied into "warnings" as 'placement error: ...', since "errors" stops the placement), "warning" = a supply pin without a cap.
    Returns {"places": [{ref, footprint, x, y, rot, label: [x, y], label_h}], "warnings": [...], "errors": [...], "findings": [...],
    "crystals": [{ref, pins: [{pad, ic, pin, name, mm}], max_mm}]}"""
    errors, warnings, places = [], [], []
    gap = max(GAP_MM, clearance_mm)
    keep = keep or {}
    info = {}
    for p in parts:
        fpname = p.get("footprint") or ""
        fp = footprints.get(fpname)
        if fp is None:
            errors.append(f"{p['ref']}: footprint {fpname or '(none)'} is not in the project library")
            continue
        box = footprint_box(fp)
        if box is None:
            errors.append(f"{p['ref']}: footprint {fpname} has no pads")
            continue
        info[p["ref"]] = {"part": p, "fp": fpname, "box": box, "padbox": pads_box(fp), "silk": _silk_box(fp), "pads": _pads_of(p, fp), "open": opening_dir(fp),
                          "names": {str(q.get("num", q.get("number", ""))): str(q.get("name") or "") for q in p.get("pins", [])},
                          "reg": is_regulator(p, fpname)}
    if errors:
        return {"places": [], "warnings": warnings, "errors": errors}
    area = sum((i["box"][2] - i["box"][0]) * (i["box"][3] - i["box"][1]) for i in info.values())
    board = (outline[2] - outline[0]) * (outline[3] - outline[1])
    k = math.sqrt(area / TARGET_FILL / board) if board > 0 else 1.0
    figures = (f" (the {len(info)} parts need about {area:.0f} mm2 of the {board:.0f} mm2 board, {100 * area / board:.0f}%; try about "
               f"{5 * math.ceil((outline[2] - outline[0]) * k / 5):g} x {5 * math.ceil((outline[3] - outline[1]) * k / 5):g} mm)")
    if area > MAX_FILL * board:
        return {"places": [], "warnings": warnings, "errors": [
            f"the parts need {area:.0f} mm2 (pads, silkscreen, 3D body) and the board is {board:.0f} mm2 ({100 * area / board:.0f}%): "
            f"no room left for tracks; make the board bigger (more than {area / MAX_FILL:.0f} mm2) or use fewer parts"]}

    placed = {}
    grid = {}                           # obstacle boxes by 2 mm cell: a candidate is only compared with the boxes near it
    rboxes = {}                         # (ref, rot) -> the part box turned

    def cells(b, pad):
        return [(i, j) for i in range(math.floor((b[0] - pad) / _CELL), math.floor((b[2] + pad) / _CELL) + 1)
                for j in range(math.floor((b[1] - pad) / _CELL), math.floor((b[3] + pad) / _CELL) + 1)]

    def add_obstacle(b):
        for c in cells(b, 0.0):
            grid.setdefault(c, []).append(b)

    def drop_obstacle(b):
        for c in cells(b, 0.0):
            grid[c] = [o for o in grid[c] if o is not b]

    def blocked(x0, y0, x1, y1):
        """True when the box is closer than `gap` to an obstacle (the same test as _hit(box, o, gap) for every obstacle)."""
        for i in range(math.floor((x0 - gap) / _CELL), math.floor((x1 + gap) / _CELL) + 1):
            for j in range(math.floor((y0 - gap) / _CELL), math.floor((y1 + gap) / _CELL) + 1):
                for o in grid.get((i, j), ()):
                    if x0 < o[2] + gap and o[0] < x1 + gap and y0 < o[3] + gap and o[1] < y1 + gap:
                        return True
        return False

    def full_box(ref, rot, x, y, side):
        rb = rboxes.get((ref, rot))
        if rb is None:
            rb = rboxes[ref, rot] = rot_box(info[ref]["box"], rot)
        b = _moved(rb, x, y)
        return b, _label_rect(b, ref, side)

    def commit(ref, x, y, rot, side="top"):
        b, lab = full_box(ref, rot, x, y, side)
        add_obstacle(b)                 # two boxes, not their union: a designator strip over an IC's width must not wall off its pins
        add_obstacle(lab)
        placed[ref] = {"x": x, "y": y, "rot": rot, "box": b, "label": lab}

    for ref, (x, y, rot) in keep.items():
        if ref in info:
            commit(ref, x, y, rot)

    def fit_sides(ref, rot, x, y, edge):
        """The sides of the designator that fit at this place (top, bottom, left, right: a generator; none: the part does not fit).
        Same arithmetic as _moved / _label_rect / _union / _inside."""
        rb = rboxes.get((ref, rot))
        if rb is None:
            rb = rboxes[ref, rot] = rot_box(info[ref]["box"], rot)
        bx0, by0, bx1, by1 = rb[0] + x, rb[1] + y, rb[2] + x, rb[3] + y
        w, h = label_size(ref)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        ox0, oy0, ox1, oy1 = outline[0] + edge, outline[1] + edge, outline[2] - edge, outline[3] - edge
        if bx0 < ox0 or bx1 > ox1 or by0 < oy0 or by1 > oy1 or blocked(bx0, by0, bx1, by1):
            return
        for side in ("top", "bottom", "left", "right"):
            if side == "top":
                lx0, ly0, lx1, ly1 = cx - w / 2, by1 + LABEL_GAP, cx + w / 2, by1 + LABEL_GAP + h
            elif side == "bottom":
                lx0, ly0, lx1, ly1 = cx - w / 2, by0 - LABEL_GAP - h, cx + w / 2, by0 - LABEL_GAP
            elif side == "left":
                lx0, ly0, lx1, ly1 = bx0 - LABEL_GAP - w, cy - h / 2, bx0 - LABEL_GAP, cy + h / 2
            else:
                lx0, ly0, lx1, ly1 = bx1 + LABEL_GAP, cy - h / 2, bx1 + LABEL_GAP + w, cy + h / 2
            if lx0 >= ox0 and lx1 <= ox1 and ly0 >= oy0 and ly1 <= oy1 and not blocked(lx0, ly0, lx1, ly1):
                yield side

    def free(ref, rot, x, y, edge):
        """The first side of the designator that fits (top first), or None."""
        return next(fit_sides(ref, rot, x, y, edge), None)

    def find(ref, tx, ty, edge=EDGE_MM, rots=(0, 90, 180, 270), rmax=None):
        rmax = rmax or max(outline[2] - outline[0], outline[3] - outline[1])
        n = int(rmax / STEP_MM)
        best = None
        for k in range(0, n + 1):                       # rings of growing radius, so the first hit is the nearest
            r = k * STEP_MM
            cands = [(tx, ty)] if k == 0 else _ring(tx, ty, r)
            for x, y in cands:
                x, y = round(x / STEP_MM) * STEP_MM, round(y / STEP_MM) * STEP_MM
                for rot in rots:
                    side = free(ref, rot, x, y, edge)
                    if side:
                        d = math.hypot(x - tx, y - ty)
                        if best is None or d < best[0]:
                            best = (d, x, y, rot, side)
            if best and best[0] <= r:
                return best[1:]
        return best[1:] if best else None

    def centre(ref):
        b = placed[ref]["box"]
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    def pad_xy(ref, pad):
        px, py, _ = info[ref]["pads"][pad]
        rx, ry = rot_point(px, py, placed[ref]["rot"])
        return placed[ref]["x"] + rx, placed[ref]["y"] + ry

    todo = [r for r in info if r not in placed]
    conns = sorted([r for r in todo if is_connector(r)], key=lambda r: -_area(info[r]))
    ics = sorted([r for r in todo if r not in conns and re.match(r"^(?:U|IC|Q|M|MOD)\d", r, re.I)], key=lambda r: -_area(info[r]))
    rest = [r for r in todo if r not in conns and r not in ics]
    cx, cy = (outline[0] + outline[2]) / 2, (outline[1] + outline[3]) / 2
    roomy = area < 0.25 * board

    def toward_middle(tgt):
        """While the board is roomy the cluster is drawn towards its middle instead of crowding the connector."""
        return ((tgt[0] + cx) / 2, (tgt[1] + cy) / 2) if roomy else tgt

    # 1. connectors: flush with an edge, centred along it, opening turned outwards, pads kept edge_copper_mm from the edge
    sides = [("B", 270), ("L", 180), ("R", 0), ("T", 90)]
    cursor = {}
    for n, ref in enumerate(conns):
        done = False
        face0 = (connector_dirs or {}).get(ref, info[ref]["open"])
        for s, face in sides[(n + shift) % 4:] + sides[:(n + shift) % 4]:
            rot = (face - (face0 or 0)) % 360
            b = rot_box(info[ref]["box"], rot)
            pb = rot_box(info[ref]["padbox"], rot)
            eb = rot_box(info[ref]["silk"], rot) if info[ref]["silk"] else pb                # no silkscreen: the copper again, nothing more is asked
            silk = edge_copper_mm + SILK_EDGE_MM if info[ref]["silk"] else edge_copper_mm
            w, h = b[2] - b[0], b[3] - b[1]
            lw = max(w, label_size(ref)[0])
            horizontal = s in "LR"
            span = (outline[3] - outline[1]) if horizontal else (outline[2] - outline[0])
            size = (h if horizontal else lw) if horizontal else lw
            first = max(0.0, (span - size) / 2)
            starts = [first] if s not in cursor else []
            starts += _slide(cursor.get(s, 0.0), span - size)
            for c in starts:
                along = round(c / STEP_MM) * STEP_MM
                if horizontal:
                    x = outline[0] - b[0] if s == "L" else outline[2] - b[2]
                    y = outline[1] + along - b[1]
                    pbx, ebx = _moved(pb, x, y), _moved(eb, x, y)
                    d = (max(0.0, outline[0] + edge_copper_mm - pbx[0], outline[0] + silk - ebx[0]) if s == "L"
                         else -max(0.0, pbx[2] - (outline[2] - edge_copper_mm), ebx[2] - (outline[2] - silk)))
                    x += d
                else:
                    y = outline[1] - b[1] if s == "B" else outline[3] - b[3]
                    x = outline[0] + along - b[0] - (lw - w) / 2
                    pbx, ebx = _moved(pb, x, y), _moved(eb, x, y)
                    d = (max(0.0, outline[1] + edge_copper_mm - pbx[1], outline[1] + silk - ebx[1]) if s == "B"
                         else -max(0.0, pbx[3] - (outline[3] - edge_copper_mm), ebx[3] - (outline[3] - silk)))
                    y += d
                side = free(ref, rot, x, y, -1e-6)
                if side:
                    commit(ref, x, y, rot, side)
                    whole = _union([placed[ref]["box"], placed[ref]["label"]])
                    cursor[s] = ((whole[1] if horizontal else whole[0]) - (outline[1] if horizontal else outline[0])
                                 + (whole[3] - whole[1] if horizontal else whole[2] - whole[0]) + gap)
                    done = True
                    break
            if done:
                break
        if not done:
            errors.append(f"{ref}: no room for the connector on an edge of the board")

    caps = [r for r in rest if _decap_rail(info[r])]
    caps.sort(key=lambda r: _farads_or_inf(info[r]))     # smallest value first: the 100 nF gets the pin's nearest place (stable: BOM order on a tie)
    findings = []
    crystals = []
    all_ics = [r for r in info if is_ic_ref(r)]          # kept ones too; Q parts are not ICs here

    def checked_ic(o):
        """The per-pin rule applies to U/IC parts with more than 4 pads that are not regulators (regulators get a softer warning)."""
        return len(info[o]["pads"]) > 4 and not info[o]["reg"]

    def pin_ok(o, pad):
        """A pin a decoupling cap may be placed for: a supply pin by NAME (VDD, VCC, VBAT, VCAP...; a regulator's in/out pins too). A pin
        tied to the rail but named RESET/EN/CE is not one. Pins without a name (a hand-made netlist) all count, as they always did."""
        name = info[o]["names"].get(pad, "").strip()
        return not name or is_supply_pin_name(name) or (info[o]["reg"] and bool(_REG_PIN.match(name)))

    # crystals: a crystal part whose nets reach MCU oscillator pins (by pin name), directly or through a series resistor (Rext); its load
    # caps are the caps between the crystal-side nets and GND
    xtals, loads = {}, {}
    two_pads = {r: i for r, i in info.items() if re.match(r"^R\d", r, re.I) and len(i["pads"]) == 2}

    def osc_pins(net):
        return [(o, opad) for o in all_ics for opad, (_, _, onet) in info[o]["pads"].items()
                if onet == net and is_osc_pin(info[o]["names"].get(opad))]

    def series_osc(net):
        """Oscillator pins reached from `net` through a series resistor (Rext): the crystal still belongs to that pin."""
        out = []
        for ri in two_pads.values():
            ps = list(ri["pads"].values())
            for a, b in (ps, ps[::-1]):
                if a[2] == net and b[2] and not is_gnd(b[2]):
                    out += osc_pins(b[2])
        return out

    for r in rest:
        if r in caps or not is_crystal(info[r]["part"], len(info[r]["pads"])):
            continue
        links = []
        for pad, (_, _, net) in info[r]["pads"].items():
            if not net or is_gnd(net):
                continue
            direct = osc_pins(net)
            via = [] if direct else series_osc(net)
            links += [(pad, o, opad, net) for o, opad in direct + via]
        if links:
            xtals[r] = links
    for c in rest:
        if c in caps or c in xtals or not re.match(r"^C\d", c, re.I) or len(info[c]["pads"]) != 2:
            continue
        pads = info[c]["pads"]
        for yref, links in xtals.items():
            for lnet in {l[3] for l in links}:
                sig = [p for p, (_, _, n) in pads.items() if n == lnet]
                gnd = [p for p, (_, _, n) in pads.items() if is_gnd(n)]
                if len(sig) == 1 and len(gnd) == 1 and c not in loads:
                    loads[c] = (yref, sig[0], lnet)
    others = [r for r in rest if r not in caps and r not in xtals and r not in loads]

    assigned = {}       # (IC, supply net) -> decoupling caps already given to it: caps spread one per IC before a second one goes to the same IC
    pin_caps = {}       # (IC, pad) -> decoupling caps already given to that supply pin
    cap_pin = {}        # decoupling cap -> (IC, pad) it was placed for
    ROTS = (0, 90, 180, 270)

    def pad_abs(ref, pad, x, y, rot):
        px, py, _ = info[ref]["pads"][pad]
        rx, ry = rot_point(px, py, rot)
        return x + rx, y + ry

    def near_places(ref, targets, cost_cap, step=STEP_MM, all_sides=False):
        """The free places by pad distance, cheapest first (a generator): targets [(pad of ref, (x, y) it should be next to)]; every grid
        point and turn around them is costed (sum of pad-to-target distances), those that cost at most cost_cap are tried in order of
        cost. Yields (x, y, rot, side, cost); all_sides: one for every side of the designator that fits, not the first only."""
        tx = sum(t[1][0] for t in targets) / len(targets)
        ty = sum(t[1][1] for t in targets) / len(targets)
        gx, gy = round(tx / step) * step, round(ty / step) * step
        n = int((cost_cap + 3.0) / len(targets) / step) + 1
        offs = [[rot_point(info[ref]["pads"][pad][0], info[ref]["pads"][pad][1], rot) for pad, _ in targets] for rot in ROTS]
        cands = []
        if len(targets) == 1:                   # one target: only the rows and columns that can be within cost_cap are costed
            t = targets[0][1]
            for k, rot in enumerate(ROTS):
                ox, oy = offs[k][0]
                for i in range(-n, n + 1):
                    x = gx + i * step
                    dx = x + ox - t[0]
                    if abs(dx) > cost_cap + 1e-6:
                        continue
                    h = math.sqrt(max(0.0, cost_cap * cost_cap - dx * dx)) + 1e-6
                    for j in range(max(-n, math.floor((t[1] - oy - h - gy) / step)), min(n, math.ceil((t[1] - oy + h - gy) / step)) + 1):
                        y = gy + j * step
                        cost = math.hypot(dx, y + oy - t[1])
                        if cost <= cost_cap:
                            cands.append((cost, x, y, rot))
        else:
            for i in range(-n, n + 1):
                for j in range(-n, n + 1):
                    x, y = gx + i * step, gy + j * step
                    for k, rot in enumerate(ROTS):
                        cost = 0.0
                        for (ox, oy), (_, t) in zip(offs[k], targets):
                            cost += math.hypot(x + ox - t[0], y + oy - t[1])
                        if cost <= cost_cap:
                            cands.append((cost, x, y, rot))
        cands.sort()
        for cost, x, y, rot in cands:
            for side in fit_sides(ref, rot, x, y, EDGE_MM):
                yield x, y, rot, side, cost
                if not all_sides:
                    break

    def find_near(ref, targets, cost_cap, step=STEP_MM):
        """The cheapest free place of near_places, or None."""
        return next(near_places(ref, targets, cost_cap, step), None)

    def place_cap(ref, only=None):
        """(target (IC, pad) or None, free place) of a decoupling cap. With `only` = (IC, pad) the cap is for that pin alone (pad None:
        for any pin of that IC) and only the places within DECAP_NEAR_MM of it are accepted: none gives (None, None) and nothing is recorded. The candidates are the supply pins of its net (pin_ok); the cap's
        rail pad is put as near the pin pad as it goes (find_near: the places next to the pin come first, within DECAP_NEAR_MM +
        DECAP_WINDOW_MM). Pins that have no cap yet are tried first (every pin gets its own cap while caps are left; PIN_SHARE_MM),
        the pin with the lowest score wins: pad distance + CAP_SHARE_MM for each cap its IC already has. Only when no pin has a place
        within the window does the old ring search run, for one pin. No IC pin on the rail: the middle of what it shares nets with."""
        rail = _decap_rail(info[ref])
        rp = next(p for p, (_, _, n) in info[ref]["pads"].items() if n == rail)
        pins = _decap_pins(ref, info, placed, pad_xy, pin_ok)
        if only:
            pins = [p for p in pins if p[2] == only[0] and only[1] in (None, p[3])]
        if not pins:
            return None, (None if only else find(ref, *toward_middle(_target(ref, info, placed, centre, (cx, cy)))))
        best, best_far = None, None
        for cnt in sorted({pin_caps.get((ic, pad), 0) for _, _, ic, pad in pins}):
            for x, y, ic, pad in pins:
                if pin_caps.get((ic, pad), 0) != cnt:
                    continue
                h = find_near(ref, [(rp, (x, y))], DECAP_NEAR_MM + DECAP_WINDOW_MM, step=FINE_STEP_MM)
                if h is None:
                    continue
                score = h[4] + CAP_SHARE_MM * assigned.get((ic, rail), 0)
                if h[4] <= DECAP_NEAR_MM + DECAP_TOL_MM:
                    if best is None or score < best[0] - 1e-9:
                        best = (score, h, ic, pad)
                elif best_far is None or score < best_far[0] - 1e-9:
                    best_far = (score, h, ic, pad)         # a place, but farther than DECAP_NEAR_MM: only when no pin has a better one
            if best:
                break
        if best is None and only:
            return None, None
        best = best or best_far
        if best is None:                 # nothing within the window: the nearest free place by the ring search, for the first free pin only
            x, y, ic, pad = min(pins, key=lambda p: (pin_caps.get((p[2], p[3]), 0), assigned.get((p[2], rail), 0)))
            h = find(ref, x, y)
            if h is None:
                return None, None
            ax, ay = pad_abs(ref, rp, h[0], h[1], h[2])
            best = (0.0, (*h, math.hypot(ax - x, ay - y)), ic, pad)
        _, h, ic, pad = best
        assigned[ic, rail] = assigned.get((ic, rail), 0) + 1
        pin_caps[ic, pad] = pin_caps.get((ic, pad), 0) + 1
        return (ic, pad), h[:4]

    done_x = set()
    todo_loads = []

    def record_crystal(yref, links):
        """The distance of a placed crystal to the oscillator pins it connects to (a finding above XTAL_NEAR_MM), its load caps to do."""
        pins = []
        for pad, o, opad, _ in links:
            if o in placed:
                (ax, ay), (bx, by) = pad_xy(yref, pad), pad_xy(o, opad)
                pins.append({"pad": pad, "ic": o, "pin": opad, "name": info[o]["names"].get(opad, ""), "mm": round(math.hypot(ax - bx, ay - by), 2)})
        far = max(pins, key=lambda q: q["mm"])
        crystals.append({"ref": yref, "pins": pins, "max_mm": far["mm"]})
        if far["mm"] > XTAL_NEAR_MM:
            text = (f"{yref} is {far['mm']:.1f} mm from {far['ic']} pin {far['pin']} {far['name']}; place the crystal as close as possible "
                    f"(ST AN2867, Oscillator design guide); {XTAL_NEAR_MM:g} mm is this tool's check threshold")
            findings.append({"level": "warning", "ref": yref, "text": text})
            warnings.append(text)
        todo_loads.append((yref, links))

    def place_crystals(force=False):
        """Crystals that have no place yet, as close as possible to the MCU oscillator pins they connect to (the cheapest free place,
        or the nearest by the ring search), once every IC they connect to is placed (force: with the ones that are placed)."""
        for yref, links in xtals.items():
            if yref in done_x or (not force and any(o not in placed for _, o, _, _ in links)):
                continue
            done_x.add(yref)
            targets = [(pad, pad_xy(o, opad)) for pad, o, opad, _ in links if o in placed]
            if not targets:
                continue
            hit = find_near(yref, targets, len(targets) * (XTAL_NEAR_MM + 3.0))     # bounded: farther than this the ring search below runs once
            if hit is None:
                tgt = (sum(t[1][0] for t in targets) / len(targets), sum(t[1][1] for t in targets) / len(targets))
                hit = find(yref, *tgt)
            if hit is None:
                errors.append(f"{yref}: no free place inside the board; make the board bigger{figures}")
                continue
            commit(yref, *hit[:3], side=hit[3])
            record_crystal(yref, links)

    def entry(ref, x, y, rot, side, cost):
        """A candidate place for solve(): (cost, x, y, rot, side, part box, designator box, the two together)."""
        b, lab = full_box(ref, rot, x, y, side)
        return cost, x, y, rot, side, b, lab, _union([b, lab])

    def solve(doms):
        """Places for a set of parts that must not touch each other: doms [domain]; a domain is the candidate places of one part
        [entry(...)], best first. Depth first with forward checking (a choice that leaves another part no candidate is dropped at once)
        and the part with the fewest candidates left first, within a budget of CSP_TRIES choices (so it gives the same answer every
        time). When no place is found for every part, the part that most often was left without a candidate is left out and the search
        starts again. Returns {index of the part: its entry} for as many parts as it found places for."""
        def clash(e, f):
            u, v = e[7], f[7]
            if u[0] >= v[2] + gap or v[0] >= u[2] + gap or u[1] >= v[3] + gap or v[1] >= u[3] + gap:
                return False
            return _hit(e[5], f[5], gap) or _hit(e[5], f[6], gap) or _hit(e[6], f[5], gap) or _hit(e[6], f[6], gap)

        skipped, best_all = set(), {}
        for _ in range(len(doms) + 1):
            tries, chosen, best, wipes = [CSP_TRIES], {}, {}, {}

            def rec(cur):
                if not cur:
                    return True
                i = min(cur, key=lambda k: (len(cur[k]), k))
                rest = {k: v for k, v in cur.items() if k != i}
                for e in cur[i]:
                    tries[0] -= 1
                    if tries[0] < 0:
                        return False
                    nxt = {}
                    for k, v in rest.items():
                        nd = [f for f in v if not clash(e, f)]
                        if not nd:
                            wipes[k] = wipes.get(k, 0) + 1
                            break
                        nxt[k] = nd
                    else:
                        chosen[i] = e
                        if len(chosen) > len(best):
                            best.clear()
                            best.update(chosen)
                        if rec(nxt):
                            return True
                        del chosen[i]
                return False

            full = rec({i: d for i, d in enumerate(doms) if i not in skipped})
            if len(best) > len(best_all):
                best_all = dict(best)
            if full or len(skipped) >= len(doms):
                break
            hard = [k for k in wipes if k not in skipped]
            if not hard:
                break
            skipped.add(max(hard, key=lambda k: (wipes[k], -k)))
        return best_all

    def fan_bands(pitches=FANOUT_PITCHES):
        """The fan-out band of every placed fine-pitch IC: the box of its pads, grown by `pitches` pitches. A pin of such an IC needs room
        to leave its pad (a via, a track beside it, and a channel along the row to the gaps between parts): a part in the band walls the
        neighbouring pins off. The decoupling caps and the crystal keep out of the narrow one, every other part out of the wide one
        (unless the board is too full)."""
        out = []
        for o in placed:
            if o not in ics or o in band_cache and band_cache[o] is None:
                continue
            if o not in band_cache:
                pts = sorted(set((round(x, 3), round(y, 3)) for x, y, _ in info[o]["pads"].values()))
                pitch = min((math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1:]), default=None)
                band_cache[o] = pitch if pitch is not None and pitch <= FANOUT_PITCH_MM else None
            if band_cache[o] is None:
                continue
            pb = _moved(rot_box(info[o]["padbox"], placed[o]["rot"]), placed[o]["x"], placed[o]["y"])
            d = pitches * band_cache[o]
            out.append([pb[0] - d, pb[1] - d, pb[2] + d, pb[3] + d])
        return out

    band_cache = {}

    def neighbourhood(ic):
        """Right after an IC is placed: the crystal (and the decoupling caps of its supply pins) beside it, all at once, before anything
        else can take the room there. Every named supply pin gets a cap, the smallest values first, and then each rail's caps in proportion
        to this IC's share of the rail's supply pins (a rail with one pin here and two caps gives both to it). Candidates: the crystal
        within XTAL_NEAR_MM of every oscillator pin, a cap within DECAP_NEAR_MM of its pin (pad to pad), every free place and turn on
        the grid; solve() finds places that do not touch. What it cannot place is left to the later steps. Returns how many of the
        crystals and caps it wanted to place it found no place for."""
        parts_, doms = [], []
        bands = fan_bands()
        wanted = 0
        for yref, links in xtals.items():
            if yref in done_x or any(o not in placed for _, o, _, _ in links):
                continue
            wanted += 1
            targets = [(pad, pad_xy(o, opad)) for pad, o, opad, _ in links]
            dom = []
            for x, y, rot, side, cost in near_places(yref, targets, len(targets) * XTAL_NEAR_MM, all_sides=True):
                if all(math.hypot(pad_abs(yref, pad, x, y, rot)[0] - t[0], pad_abs(yref, pad, x, y, rot)[1] - t[1]) <= XTAL_NEAR_MM
                       for pad, t in targets):
                    e = entry(yref, x, y, rot, side, cost)
                    if not any(_hit(e[5], r, 0) for r in bands):
                        dom.append(e)
                        if len(dom) >= CSP_DOMAIN:
                            break
            if dom:
                parts_.append(("x", yref, links))
                doms.append(dom)
        for net in sorted({n for _, _, n in info[ic]["pads"].values() if is_rail(n)}):
            mine = [p for p, (_, _, n) in info[ic]["pads"].items() if n == net and info[ic]["names"].get(p, "").strip() and pin_ok(ic, p)]
            allpins = sum(1 for o, i in info.items() if re.match(r"^(?:U|IC|M|MOD)\d", o, re.I)
                          for p, (_, _, n) in i["pads"].items() if n == net and i["names"].get(p, "").strip() and pin_ok(o, p))
            rail_caps = [c for c in caps if _decap_rail(info[c]) == net and (cap_farads(part_value(info[c]["part"])) is None
                                                                             or cap_farads(part_value(info[c]["part"])) <= BULK_F)]
            todo = [c for c in rail_caps if c not in placed]
            if not mine or not todo:
                continue
            allpins = max(allpins, len(mine))                                       # an IC that is not a U/IC/M/MOD (a Q...) counts too
            quota = max(len(mine), -(-len(rail_caps) * len(mine) // allpins))        # ceil(caps * my pins / all pins), one per pin at least
            for k, c in enumerate(todo[:quota]):
                wanted += 1
                pad = mine[k % len(mine)]
                rp = next(p for p, (_, _, n) in info[c]["pads"].items() if n == net)
                dom = []
                for x, y, rot, side, cost in near_places(c, [(rp, pad_xy(ic, pad))], DECAP_NEAR_MM + DECAP_TOL_MM, step=FINE_STEP_MM, all_sides=True):
                    e = entry(c, x, y, rot, side, cost)
                    if not any(_hit(e[5], r, 0) for r in bands):
                        dom.append(e)
                        if len(dom) >= CSP_DOMAIN:
                            break
                if dom:
                    parts_.append(("c", c, (ic, pad)))
                    doms.append(dom)
        sol = solve(doms)
        for i, e in sorted(sol.items()):
            kind, ref, extra = parts_[i]
            commit(ref, e[1], e[2], e[3], side=e[4])
            if kind == "c":
                cap_pin[ref] = extra
                assigned[extra[0], net_of(ref)] = assigned.get((extra[0], net_of(ref)), 0) + 1
                pin_caps[extra] = pin_caps.get(extra, 0) + 1
            else:
                done_x.add(ref)
                record_crystal(ref, extra)
        return wanted - len(sol)

    def net_of(c):
        return _decap_rail(info[c])

    def place_loads():
        """The load caps of the crystals placed so far, beside their crystal pad."""
        while todo_loads:
            yref, links = todo_loads.pop(0)
            for c, (cy_ref, sig, lnet) in loads.items():
                if cy_ref != yref:
                    continue
                ypad = next((p for p, _, _, n in links if n == lnet), None)
                if ypad is None:
                    continue
                h = find_near(c, [(sig, pad_xy(yref, ypad))], 6.0)
                if h is None:
                    h = find(c, *pad_xy(yref, ypad))
                if h is None:
                    errors.append(f"{c}: no free place inside the board; make the board bigger{figures}")
                    continue
                commit(c, *h[:3], side=h[3])

    # 2. ICs: nearest the middle, then around what they share nets with. Right after each one, before the next IC or any other part
    # can take the room beside its pins: a decoupling cap at each supply pin, then the crystal (and its load caps) at its oscillator pins
    halos = []      # while the ICs are placed, the room round an IC that has supply pins is kept for its caps: the next IC is put outside it

    def snapshot():
        return (dict(placed), {k: list(v) for k, v in grid.items()}, dict(assigned), dict(pin_caps), dict(cap_pin), set(done_x),
                list(crystals), list(findings), list(warnings), list(todo_loads), dict(band_cache), list(errors), list(halos))

    def restore(saved):
        for target, was in zip((placed, grid, assigned, pin_caps, cap_pin, done_x, crystals, findings, warnings, todo_loads, band_cache,
                                errors, halos), saved):
            if isinstance(target, dict):
                target.clear()
                target.update({k: list(v) for k, v in was.items()} if target is grid else was)
            elif isinstance(target, set):
                target.clear()
                target.update(was)
            else:
                target[:] = was

    def min_dim(r):
        b = info[r]["box"]
        return min(b[2] - b[0], b[3] - b[1])

    def pitch_of(o):
        """The smallest centre to centre distance between two pads of an IC (None for one pad)."""
        pts = sorted(set((round(x, 3), round(y, 3)) for x, y, _ in info[o]["pads"].values()))
        return min((math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1:]), default=None)

    def ic_needs(ic):
        """{pad of the IC: the room (mm, across) a part needs beside it} for the parts the neighbourhood puts beside this IC: the
        crystal beside each oscillator pin, the smallest decoupling cap beside each supply pin (only when there are caps for every
        pin: with fewer, which pins get one is not known yet)."""
        out = {}
        for yref, links in xtals.items():
            if yref not in done_x:
                for _, o, opad, _ in links:
                    if o == ic:
                        out[opad] = max(out.get(opad, 0.0), min_dim(yref))
        for net in {n for _, _, n in info[ic]["pads"].values() if is_rail(n)}:
            mine = [p for p, (_, _, n) in info[ic]["pads"].items() if n == net and info[ic]["names"].get(p, "").strip() and pin_ok(ic, p)]
            todo_c = [c for c in caps if c not in placed and _decap_rail(info[c]) == net
                      and (cap_farads(part_value(info[c]["part"])) is None or cap_farads(part_value(info[c]["part"])) <= BULK_F)]
            if mine and len(todo_c) >= len(mine):
                d = min(min_dim(c) for c in todo_c)
                for p in mine:
                    out[p] = max(out.get(p, 0.0), d)
        return out

    def room_ok(ic, needs, x, y, rot, band):
        """True when, at this place and turn, the board edge leaves room beside every pad that has a need: on the side of the pad row the
        pad is on, from the pads' box to the keep-out line of the edge there must be the fan-out band and the part."""
        pb = _moved(rot_box(info[ic]["padbox"], rot), x, y)
        room = (pb[0] - outline[0] - EDGE_MM, outline[2] - EDGE_MM - pb[2], pb[1] - outline[1] - EDGE_MM, outline[3] - EDGE_MM - pb[3])
        for pad, d in needs.items():
            px, py = pad_abs(ic, pad, x, y, rot)
            gaps = (px - pb[0], pb[2] - px, py - pb[1], pb[3] - py)
            if room[gaps.index(min(gaps))] < band + d - 1e-6:
                return False
        return True

    def ic_poses(ic, tx, ty, edge, needs, band):
        """Places and turns for an IC, nearest to (tx, ty) first, that leave room beside its pads (room_ok): (x, y, rot, side of the
        designator), one for every side of the designator that fits."""
        n = int(max(outline[2] - outline[0], outline[3] - outline[1]) / STEP_MM)
        for k in range(n + 1):
            pts = {(round(x / STEP_MM) * STEP_MM, round(y / STEP_MM) * STEP_MM) for x, y in ([(tx, ty)] if k == 0 else _ring(tx, ty, k * STEP_MM))}
            for x, y in sorted(pts, key=lambda q: (math.hypot(q[0] - tx, q[1] - ty), q)):
                for rot in ROTS:
                    if room_ok(ic, needs, x, y, rot, band):
                        for side in fit_sides(ic, rot, x, y, edge):
                            yield x, y, rot, side

    def settle(ic, pose):
        """Put the IC at `pose`, then its crystal and caps beside it. -> how many of them did not get a place within reach."""
        commit(ic, *pose[:3], side=pose[3])
        short = neighbourhood(ic)
        place_crystals()                # a crystal with no place within XTAL_NEAR_MM of its pins: the cheapest free one
        place_loads()                   # after the caps at the supply pins: a load cap is not held to a distance from the MCU
        for yref, links in xtals.items():
            if any(o == ic for _, o, _, _ in links) and all(o in placed for _, o, _, _ in links):
                rec = next((c for c in crystals if c["ref"] == yref), None)
                short += rec is None or rec["max_mm"] > XTAL_NEAR_MM
        return short

    def settle_best(ic, tgt, hit):
        """The IC at the first free place (`hit`) when its crystal and caps all get a place beside it; else the first of up to IC_TRIES
        other places and turns, nearest to the target first, where they do (the designator may go to another side too), else the one
        that left the fewest without. A place where the edge leaves no room beside the pads for them is not tried."""
        base = snapshot()
        needs = ic_needs(ic) if trials else None
        short = settle(ic, hit)
        if not short or not needs:
            return
        pitch = pitch_of(ic)
        band = FANOUT_PITCHES * pitch if pitch is not None and pitch <= FANOUT_PITCH_MM else COURT_MM + gap
        best, last, tried = (short, hit), hit, [hit]
        for pose in ic_poses(ic, *tgt, EDGE_MM + 0.5, needs, band):
            if len(tried) >= IC_TRIES:
                break
            if any(q[2] == pose[2] and q[3] == pose[3] and math.hypot(q[0] - pose[0], q[1] - pose[1]) < IC_TRY_APART_MM for q in tried):
                continue
            tried.append(pose)
            restore(base)
            short, last = settle(ic, pose), pose
            if short < best[0]:
                best = (short, pose)
            if not short:
                return
        if last != best[1]:
            restore(base)
            settle(ic, best[1])

    for ref in ics:
        tgt = toward_middle(_target(ref, info, placed, centre, (cx, cy)))
        hit = find(ref, *tgt, edge=EDGE_MM + 0.5)
        if hit is None and halos:                       # no room outside the halos: the caps will have to make do
            for h in halos:
                drop_obstacle(h)
            halos.clear()
            hit = find(ref, *tgt, edge=EDGE_MM + 0.5)
        if hit is None:
            errors.append(f"{ref}: no free place inside the board; make the board bigger{figures}")
            continue
        settle_best(ref, tgt, hit)
        if checked_ic(ref) and any(is_rail(n) and pin_ok(ref, pad) and info[ref]["names"].get(pad, "").strip()
                                   for pad, (_, _, n) in info[ref]["pads"].items()):
            b = placed[ref]["box"]
            halos.append([b[0] - HALO_MM, b[1] - HALO_MM, b[2] + HALO_MM, b[3] + HALO_MM])
            add_obstacle(halos[-1])
    place_crystals(force=True)
    place_loads()
    for h in halos:
        drop_obstacle(h)

    # 3. decoupling caps first (beside the supply pin), then the others by how tied they are to placed parts
    others.sort(key=lambda r: -len(_shared(r, info, placed)))
    for ref in caps:
        if ref in placed:
            continue
        owner, hit = place_cap(ref)
        if hit is None:
            errors.append(f"{ref}: no free place inside the board; make the board bigger{figures}")
            continue
        commit(ref, *hit[:3], side=hit[3])
        if owner:
            cap_pin[ref] = owner

    # decoupling findings from the final positions: a cap too far from its supply pin (error; a regulator: warning), a supply pin without a cap
    for ref in caps:
        if ref not in cap_pin or ref not in placed:
            continue
        ic, pad = cap_pin[ref]
        name = info[ic]["names"].get(pad, "").strip()
        if not name or not (checked_ic(ic) or info[ic]["reg"]) or not pin_ok(ic, pad):
            continue                     # unnamed pins cannot be told from RESET/EN: no finding
        rail = _decap_rail(info[ref])
        rp = next(p for p, (_, _, n) in info[ref]["pads"].items() if n == rail)
        (ax, ay), (bx, by) = pad_xy(ref, rp), pad_xy(ic, pad)
        d = math.hypot(ax - bx, ay - by)
        f = cap_farads(part_value(info[ref]["part"]))
        if d > DECAP_NEAR_MM + DECAP_TOL_MM and (f is None or f <= BULK_F):
            level, text = decap_text(ref, d, ic, pad, name, info[ic]["reg"])
            findings.append({"level": level, "ref": ref, "text": text})
            warnings.append(("placement error: " if level == "error" else "") + text)
    for ic in all_ics:
        if ic not in placed or not checked_ic(ic):
            continue
        for rail in sorted({n for _, _, n in info[ic]["pads"].values() if is_rail(n)}):
            pins = [p for p, (_, _, n) in info[ic]["pads"].items() if n == rail and is_supply_pin_name(info[ic]["names"].get(p))]
            mine = [c for c in caps if c in placed and _decap_rail(info[c]) == rail and (cap_farads(part_value(info[c]["part"])) or 0) <= BULK_F]
            bare = []
            for p in pins:
                px, py = pad_xy(ic, p)
                if not any(math.hypot(pad_xy(c, q)[0] - px, pad_xy(c, q)[1] - py) <= DECAP_NEAR_MM + DECAP_TOL_MM
                           for c in mine for q, (_, _, n) in info[c]["pads"].items() if n == rail):
                    bare.append(p)
            if bare:
                names = ", ".join(f"{p} {info[ic]['names'].get(p, '')}".strip() for p in bare)
                text = (f"{ic}: {len(bare)} of {len(pins)} supply pin(s) on {rail} have no decoupling cap within {DECAP_NEAR_MM:g} mm "
                        f"(pin {names}); datasheets ask for one close to each supply pin, {DECAP_NEAR_MM:g} mm is this tool's threshold")
                findings.append({"level": "warning", "ref": ic, "text": text})
                warnings.append(text)
    # the plan is judged by the crystal and the caps, which nothing placed after them can change: a variant that cannot beat `bound`
    # (the key of the best so far, see plan_placement) is dropped here, before the other parts take their time
    if bound is not None and (len(errors), sum(1 for f in findings if f["level"] == "error"),
                              sum(1 for c in crystals if c["max_mm"] > XTAL_NEAR_MM), len(findings)) >= bound:
        return None
    # 4. every other part, by how tied it is to the placed parts, outside the fan-out bands of the fine-pitch ICs (inside them only when
    # there is no other place: a part there walls off the pins beside it)
    bands = [[r[0] + gap, r[1] + gap, r[2] - gap, r[3] - gap] for r in fan_bands(FANOUT_FREE_PITCHES)]    # an obstacle is kept `gap` away: so the band is
    for r in bands:                                                                                  # FANOUT_FREE_PITCHES from the pads
        add_obstacle(r)
    for ref in others:
        if ref in placed:
            continue
        tgt = toward_middle(_target(ref, info, placed, centre, (cx, cy)))
        hit = find(ref, *tgt)
        if hit is None and bands:
            for r in bands:
                drop_obstacle(r)
            bands = []
            hit = find(ref, *tgt)
        if hit is None:
            errors.append(f"{ref}: no free place inside the board; make the board bigger{figures}")
            continue
        commit(ref, *hit[:3], side=hit[3])
    for ref in placed:
        if ref in keep:
            continue
        i = info[ref]
        lab = placed[ref]["label"]
        places.append({"ref": ref, "footprint": i["fp"], "x": round(placed[ref]["x"], 3), "y": round(placed[ref]["y"], 3),
                       "rot": placed[ref]["rot"], "label": [round((lab[0] + lab[2]) / 2, 3), round((lab[1] + lab[3]) / 2, 3)],
                       "label_h": LABEL_H, "label_rot": label_rotation(placed[ref]["rot"])})
    for ref in conns:
        if ref in placed and ref not in (connector_dirs or {}):
            if info[ref]["open"] is None:
                warnings.append(f"{ref}: cannot tell from its footprint which way the connector opens; it was assumed to open towards +x: "
                                "check the mating face in 3D")
            else:
                warnings.append(f"{ref}: connector turned to open out of the board edge (opening read from the footprint outline, "
                                f"{info[ref]['open']} deg): check the mating face in 3D")
    return {"places": places, "warnings": warnings, "errors": errors, "findings": findings, "crystals": crystals}


def _area(i):
    return (i["box"][2] - i["box"][0]) * (i["box"][3] - i["box"][1])


def _ring(cx, cy, r):
    pts = []
    n = max(8, int(2 * math.pi * r / STEP_MM))
    for k in range(n):
        a = 2 * math.pi * k / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _slide(start, room):
    """Offsets along an edge to try, from `start` on in half-mm steps."""
    out, c = [], max(0.0, start)
    while c <= room + 1e-9:
        out.append(c)
        c += STEP_MM
    return out


def _signal_nets(i):
    return {n for _, _, n in i["pads"].values() if n and not is_gnd(n) and not is_rail(n) and n.upper() not in ("NC", "N/C")}


def _shared(ref, info, placed):
    mine = _signal_nets(info[ref])
    return [o for o in placed if o != ref and mine & _signal_nets(info[o])]


def _target(ref, info, placed, centre, fallback):
    others = _shared(ref, info, placed)
    if not others:
        mine = {n for _, _, n in info[ref]["pads"].values() if is_rail(n)}
        others = [o for o in placed if mine & {n for _, _, n in info[o]["pads"].values() if is_rail(n)}]
    if not others:
        return fallback
    pts = [centre(o) for o in others]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _decap_rail(i):
    """The supply net of a small two-pad part that sits between a supply rail and ground (a decoupling cap), else None."""
    if not re.match(r"^C\d", i["part"]["ref"], re.I) or len(i["pads"]) != 2:
        return None
    nets = [n for _, _, n in i["pads"].values()]
    if any(is_gnd(n) for n in nets):
        rails = [n for n in nets if is_rail(n)]
        return rails[0] if rails else None
    return None


def _decap_pins(ref, info, placed, pad_xy, ok=None):
    """The supply pins a decoupling cap can sit beside, as (x, y, IC ref, pad): every pin on its rail net of every placed IC that
    `ok(ic, pad)` accepts (a RESET/EN pin tied to the rail is not a supply pin). Q parts are not ICs."""
    rail = _decap_rail(info[ref])
    found = []
    for o, i in info.items():
        if o not in placed or o == ref or not re.match(r"^(?:U|IC|M|MOD)\d", o, re.I):
            continue
        for name, (_, _, net) in i["pads"].items():
            if net == rail and (ok is None or ok(o, name)):
                x, y = pad_xy(o, name)
                found.append((x, y, o, name))
    return found


def _farads_or_inf(i):
    f = cap_farads(part_value(i["part"]))
    return float("inf") if f is None else f


def decap_text(cap, d, ic, pad, name, regulator):
    """(level, text) of a decoupling cap that is `d` mm from its supply pin. A regulator's cap: a warning, as close as possible (see the
    regulator datasheet's layout section). Any other IC: an error at DECAP_NEAR_MM, this tool's own threshold (datasheets only ask for
    'as close as possible')."""
    pin = f"{ic} pin {pad} {name or ''}".rstrip()
    if regulator:
        return "warning", f"{cap} is {d:.1f} mm from {pin}: place it as close as possible (see the regulator datasheet's layout section)"
    return "error", (f"{cap} is {d:.1f} mm from {pin}; limit {DECAP_NEAR_MM:g} mm (datasheets ask for decoupling caps as close as possible "
                     f"to each supply pin; {DECAP_NEAR_MM:g} mm is this tool's threshold)")


OUTLINE_LAYER = 57          # Mechanical 1: the layer the shipped OutJob plots as the board outline (.GM1; layer id 16908289)
OUTLINE_WIDTH_MM = 0.15     # JLC: draw the outline 0.15 mm wide (same as scripts/jlc_testboard.py)


def outline_layer_free(doc):
    """(tracks, arcs) a PcbDoc holds on the outline layer that are not part of a footprint: somebody's outline drawing."""
    tracks = [t for t in doc.get("tracks", []) if t.get("layer") == OUTLINE_LAYER and not t.get("in_component")]
    arcs = [a for a in doc.get("arcs", []) if a.get("layer") == OUTLINE_LAYER and not a.get("in_component")]
    return tracks, arcs


def outline_drawing_problems(doc, outline, tol=0.05):
    """What is wrong with the outline layer (Mechanical 1) of a read-back PcbDoc against the board shape `outline` [x0, y0, x1, y1] mm:
    nothing drawn, drawn but not closed, or not the board shape (box off by more than tol mm). [] when it is a closed drawing of it."""
    tracks, arcs = outline_layer_free(doc)
    if not tracks and not arcs:
        return ["the outline layer (Mechanical 1) has no drawing: the board shape is set but nothing is drawn, so the outline Gerber "
                "(.GM1) comes out empty"]
    xs = [v for t in tracks for v in (t["x1_mm"], t["x2_mm"])]
    ys = [v for t in tracks for v in (t["y1_mm"], t["y2_mm"])]
    for a in arcs:       # an arc on the outline: its circle box is a safe outer bound for the extent check
        r = a.get("r_mm") or 0
        xs += [a.get("cx_mm", 0) - r, a.get("cx_mm", 0) + r]
        ys += [a.get("cy_mm", 0) - r, a.get("cy_mm", 0) + r]
    box = [min(xs), min(ys), max(xs), max(ys)]
    probs = []
    if any(abs(a - b) > tol for a, b in zip(box, outline)):
        probs.append(f"the outline drawn on Mechanical 1 is {[round(v, 2) for v in box]} mm, the board shape is {[round(v, 2) for v in outline]} mm")
    if not arcs:
        ends = {}
        for t in tracks:
            for p in ((round(t["x1_mm"] / tol), round(t["y1_mm"] / tol)), (round(t["x2_mm"] / tol), round(t["y2_mm"] / tol))):
                ends[p] = ends.get(p, 0) + 1
        if not tracks or any(n % 2 for n in ends.values()):
            probs.append("the outline drawn on Mechanical 1 is not a closed shape (loose line ends)")
    return probs


def plan_commands(doc, outline, create_outline, places, footprints, parts, pcblib, replace=False, draw_outline=False):
    """Script lines for the bridge. PCBBEGIN doc replace; OUTLINE doc x0 y0 x1 y1 (mm); PLACEFP doc ref footprint pcblib x y rot
    libref sourceid; PADNET doc ref pad net; PCBSAVE doc. A footprint is placed from the project PcbLib and linked like ECO does
    (designator, source designator, library reference, footprint library) and each pad gets its net from the netlist so a later
    Update PCB matches the part instead of adding a duplicate."""
    by_ref = {p["ref"]: p for p in parts}
    d = str(doc)
    cmds = [("PCBBEGIN", d, "1" if replace else "0")]
    if create_outline and outline:
        cmds.append(("OUTLINE", d) + tuple(f"{v:g}" for v in outline))
    if draw_outline and outline:         # the bridge draws nothing when the layer already holds a drawing
        cmds.append(("OUTLINEDRAW", d) + tuple(f"{v:g}" for v in outline) + (f"{OUTLINE_WIDTH_MM:g}",))
    for pl in places:
        p = by_ref[pl["ref"]]
        cmds.append(("PLACEFP", d, pl["ref"], pl["footprint"], str(pcblib), f"{pl['x']:g}", f"{pl['y']:g}", f"{pl['rot']:g}",
                     str(p.get("lib_ref") or p.get("symbol") or ""), str(p.get("value") or ""),
                     f"{(pl.get('label') or [pl['x'], pl['y']])[0]:g}", f"{(pl.get('label') or [pl['x'], pl['y']])[1]:g}",
                     f"{pl.get('label_h', LABEL_H):g}", f"{LABEL_LINE:g}",
                     ("\\" + p["uid"]) if p.get("uid") else "", str(p.get("sheet") or ""),
                     f"{pl.get('label_rot', label_rotation(pl['rot'])):g}"))
        for pin in p.get("pins", []):
            net = str(pin.get("net") or "").strip()
            if net and net.upper() not in ("NC", "N/C"):
                cmds.append(("PADNET", d, pl["ref"], str(pin.get("num", pin.get("number", ""))), net))
    cmds.append(("PCBSAVE", d))
    return cmds


def text_problems(parts):
    bad = []
    for p in parts:
        names = [p["ref"], p.get("footprint") or ""] + [str(x.get("net") or "") for x in p.get("pins", [])]
        for t in names:
            if not all(32 <= ord(c) < 127 for c in t):
                bad.append(f"{p['ref']}: name {t!r} has a non-ASCII character, a tab or a line break: rename it")
    return sorted(set(bad))


def occupied(doc):
    """What a PcbDoc already holds that placing over would destroy: ({placed refs}, track+via+arc count)."""
    refs = [c["ref"] for c in doc.get("components", []) if c.get("ref")]
    n = len(doc.get("tracks", [])) + len(doc.get("vias", [])) + len(doc.get("arcs", []))
    return refs, n


def _seg_touches_pad(a, b, rect, hw, rounded=False):
    """The track (a, b, half width hw) touches the pad: its box, or for a round / oval pad the ellipse inscribed in the box (the
    corners of the box are not copper)."""
    from altium import route as rt
    if not rounded:
        return rt._seg_rect(a, b, rect) <= hw
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    ha, hb = (rect[2] - rect[0]) / 2 + hw, (rect[3] - rect[1]) / 2 + hw
    if ha <= 0 or hb <= 0:
        return False
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.02) + 1)
    for i in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        if ((x - cx) / ha) ** 2 + ((y - cy) / hb) ** 2 <= 1.0:
            return True
    return False


def unrouted(doc, tol=0.02):
    """[(net, [pad tags])]: for every net with two or more pads, the groups of pads that tracks and vias do not join (copper
    pours and polygons are not read, so a net meant to be poured shows as unrouted: the caller says so). Same rule as Altium: a
    track joins what its body (not only its ends) touches on its layer, a via joins every layer, a through-hole pad joins both."""
    from altium import route as rt
    pads = [p for p in doc.get("pads", []) if p.get("net") and p.get("ref")]
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    rects = [rt._pad_rect(p) for p in pads]
    lay_of = [set(1 if l == rt.TOP else 32 for l in rt._pad_layers(p)) for p in pads]
    tracks = [t for t in doc.get("tracks", []) if t.get("net")]
    vias = [v for v in doc.get("vias", []) if v.get("net")]
    seg = lambda t: ((t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"]))
    for k, t in enumerate(tracks):
        a, b = seg(t)
        hw = t.get("width_mm", 0) / 2 + tol
        for j, p in enumerate(pads):
            if p["net"] == t["net"] and t["layer"] in lay_of[j] and _seg_touches_pad(a, b, rects[j], hw, rt._round_pad(p)):
                union(("track", k), ("pad", j))
        for m, u in enumerate(tracks[k + 1:], k + 1):
            if u["net"] == t["net"] and u["layer"] == t["layer"]:
                c, d = seg(u)
                if rt._seg_seg(a, b, c, d) <= hw + u.get("width_mm", 0) / 2:
                    union(("track", k), ("track", m))
        for m, v in enumerate(vias):
            if v["net"] == t["net"] and rt._pt_seg(v["x_mm"], v["y_mm"], a[0], a[1], b[0], b[1]) <= hw + max(v.get("dia_mm", 0) / 2, tol):
                union(("track", k), ("via", m))
    for m, v in enumerate(vias):
        r = max(v.get("dia_mm", 0) / 2, tol)
        for j, p in enumerate(pads):
            if p["net"] == v["net"] and rt._seg_rect((v["x_mm"], v["y_mm"]), (v["x_mm"], v["y_mm"]), rects[j]) <= r:
                union(("via", m), ("pad", j))
        for n2, w in enumerate(vias[m + 1:], m + 1):
            if w["net"] == v["net"] and math.hypot(v["x_mm"] - w["x_mm"], v["y_mm"] - w["y_mm"]) <= r + max(w.get("dia_mm", 0) / 2, tol):
                union(("via", m), ("via", n2))
    groups = {}
    for k, p in enumerate(pads):
        groups.setdefault(p["net"], {}).setdefault(find(("pad", k)), []).append(f"{p['ref']}-{p['name']}")
    return [(net, sorted(sum(g.values(), []))) for net, g in sorted(groups.items()) if len(g) > 1]
def _abs_pad_rect(p):
    """[x0, y0, x1, y1] of a read_pcbdoc pad (board mm, with its own turn)."""
    sx, sy = p.get("sx_mm", 0), p.get("sy_mm", 0)
    rot = float(p.get("rot") or 0) % 180
    if abs(rot - 90) < 0.5:
        sx, sy = sy, sx
    elif min(rot, 180 - rot) > 0.5:
        sx = sy = math.hypot(sx, sy)
    return [p["x_mm"] - sx / 2, p["y_mm"] - sy / 2, p["x_mm"] + sx / 2, p["y_mm"] + sy / 2]


def real_boxes(doc, footprints=None):
    """{ref: [x0, y0, x1, y1]} the real extent of every part of a saved board (read_pcbdoc with geometry=True gives the body and the
    silkscreen box): pads (turned as they are), 3D body, silkscreen / mechanical outline, and, when `footprints` ({name: read_pcblib
    footprint}) is given, the library's own extent moved and turned to where the part sits."""
    out = {}
    for c in doc.get("components", []):
        ref = c.get("ref")
        boxes = [_abs_pad_rect(p) for p in doc.get("pads", []) if p.get("ref") == ref and "x_mm" in p]
        boxes += [c.get("body_bbox_mm"), c.get("outline_bbox_mm")]
        fp = (footprints or {}).get(c.get("pattern"))
        if fp is not None and footprint_extent(fp):
            rot = round(float(c.get("rotation") or 0)) % 360
            if rot % 90 == 0:
                boxes.append(_moved(rot_box(footprint_extent(fp), rot), c.get("x_mm", 0), c.get("y_mm", 0)))
        out[ref] = _union(boxes)
    return {r: b for r, b in out.items() if b}


def _designators(doc):
    """{ref: [x0, y0, x1, y1]} the drawn designators of a saved board (the text origin is its lower left corner)."""
    out = {}
    for t in doc.get("texts", []):
        if t.get("kind") != "designator":
            continue
        h = t.get("height_mm") or 0
        w = len(t.get("text", "")) * h * 0.6
        if round(t.get("rotation") or 0) % 180 == 90:
            w, h = h, w
        out[t["text"]] = [t["x_mm"], t["y_mm"], t["x_mm"] + w, t["y_mm"] + h]
    return out


def decap_distance_warnings(doc, plan_parts, limit=DECAP_NEAR_MM):
    """Read-back check of the decoupling rule, WARNINGS only (a far cap never undoes a placement): every decoupling cap (a 2-pad C
    between a supply rail and ground, not bulk above BULK_F) whose rail pad is more than `limit` mm (pad centre to pad centre, +
    DECAP_TOL_MM) from the nearest supply pin of a U/IC part on the same rail. Supply pins are told by NAME (VDD, VCC, VBAT, VCAP...: a
    RESET/EN pin is not one), so pins without names are never checked; an IC with 4 pads or fewer is skipped. A regulator
    gets the softer 'as close as possible' text. Texts are decap_text's."""
    at = {(p.get("ref"), str(p.get("name"))): (p["x_mm"], p["y_mm"]) for p in doc.get("pads", []) if isinstance(p, dict) and "x_mm" in p and p.get("ref")}
    pins = {}                                        # rail -> [(ic, num, name, (x, y), regulator)]
    for part in plan_parts:
        if not is_ic_ref(part["ref"]):
            continue
        reg = is_regulator(part)
        if len(part.get("pins", [])) <= 4 and not reg:
            continue
        for pin in part.get("pins", []):
            num, net, name = str(pin.get("num", pin.get("number", ""))), str(pin.get("net") or "").strip(), str(pin.get("name") or "").strip()
            if is_rail(net) and (part["ref"], num) in at and (is_supply_pin_name(name) or (reg and _REG_PIN.match(name))):
                pins.setdefault(net, []).append((part["ref"], num, name, at[part["ref"], num], reg))
    out = []
    for part in plan_parts:
        nets = [str(p.get("net") or "").strip() for p in part.get("pins", [])]
        if not re.match(r"^C\d", part["ref"], re.I) or len(nets) != 2 or not any(is_gnd(n) for n in nets):
            continue
        rail = next((n for n in nets if is_rail(n)), None)
        f = cap_farads(part_value(part))
        if rail is None or rail not in pins or (f is not None and f > BULK_F):
            continue
        pin = next(p for p in part["pins"] if str(p.get("net") or "").strip() == rail)
        xy = at.get((part["ref"], str(pin.get("num", pin.get("number", "")))))
        if xy is None:
            continue
        d, ic, num, name, _, reg = min(((math.hypot(xy[0] - q[3][0], xy[1] - q[3][1]), *q) for q in pins[rail]), key=lambda t: t[0])
        if d > limit + DECAP_TOL_MM:
            out.append(decap_text(part["ref"], d, ic, num, name, reg)[1])
    return out


def verify_layout(doc, plan_parts, outline=None, clearance_mm=0.0, places=None, footprints=None, edge_copper_mm=EDGE_COPPER_MM):
    """Saved PcbDoc (read_pcbdoc dict, ideally geometry=True) against the netlist parts [{ref, footprint, pins}]. Problem strings,
    empty = it matches. Checks: every part there on the right footprint; every pad (every pad of a shared number too) on the net
    the netlist gives it; no stray parts; no two parts whose REAL extents (pads, 3D body, silkscreen) come closer than the clearance;
    every part inside the outline (a connector's body may stick out CONNECTOR_OVERHANG_MM on one side, its mating face) and every pad
    edge_copper_mm inside it; no designator over a pad or over another designator; parts where the plan put them (`places`)."""
    problems = []
    comps = {c["ref"]: c for c in doc.get("components", [])}
    pad_nets = {}
    for p in doc.get("pads", []):
        pad_nets.setdefault((p.get("ref"), str(p.get("name"))), []).append(p.get("net") or "")
    for part in plan_parts:
        c = comps.get(part["ref"])
        if c is None:
            problems.append(f"{part['ref']} is not on the saved board")
            continue
        if part.get("footprint") and c.get("pattern") != part["footprint"]:
            problems.append(f"{part['ref']} has footprint {c.get('pattern')!r}, the netlist says {part['footprint']!r}")
        for pin in part.get("pins", []):
            want = str(pin.get("net") or "").strip()
            if want.upper() in ("NC", "N/C"):
                want = ""
            num = str(pin.get("num", pin.get("number", "")))
            if (part["ref"], num) not in pad_nets:
                problems.append(f"{part['ref']}: footprint has no pad {num} (netlist pin {pin.get('name') or ''})")
                continue
            for got in pad_nets[(part["ref"], num)]:
                if got != want:
                    problems.append(f"{part['ref']}-{num} is on net {got or 'none'}, the netlist says {want or 'none'}")
    extra = sorted(set(comps) - {p["ref"] for p in plan_parts})
    if extra:
        problems.append(f"parts on the board that are not in the netlist: {', '.join(extra)}")
    boxes = real_boxes(doc, footprints)
    refs = sorted(boxes)
    gap = clearance_mm if clearance_mm > 0 else 0.0
    for a in range(len(refs)):
        for b in range(a + 1, len(refs)):
            if _hit(boxes[refs[a]], boxes[refs[b]], gap - 1e-6):
                problems.append(f"{refs[a]} and {refs[b]} overlap on the board (pads, 3D body or silkscreen" + (f", closer than {gap:g} mm" if gap else "") + ")")
    if outline:
        for r, b in boxes.items():
            if _inside(b, outline, -1e-6):
                continue
            sides = [(b[0] < outline[0] - 1e-6, outline[0] - b[0]), (b[2] > outline[2] + 1e-6, b[2] - outline[2]),
                     (b[1] < outline[1] - 1e-6, outline[1] - b[1]), (b[3] > outline[3] + 1e-6, b[3] - outline[3])]
            out_sides = [d for hit, d in sides if hit]
            if is_connector(r) and len(out_sides) == 1 and out_sides[0] <= CONNECTOR_OVERHANG_MM + 1e-6:
                continue
            problems.append(f"{r} sticks out of the board outline by {max(out_sides):.2f} mm (3D body, silkscreen or pads)")
        for p in doc.get("pads", []):
            if "x_mm" not in p or not p.get("ref"):
                continue
            pb = _abs_pad_rect(p)
            d = min(pb[0] - outline[0], pb[1] - outline[1], outline[2] - pb[2], outline[3] - pb[3])
            if d < edge_copper_mm - 0.01:
                problems.append(f"{p['ref']}-{p['name']} is {d:.2f} mm from the board edge (copper must keep {edge_copper_mm:g} mm)")
    labels = _designators(doc)
    for ref in [p["ref"] for p in plan_parts] if "texts" in doc else []:
        if ref in comps and ref not in labels:
            problems.append(f"{ref}: designator is not shown on the board")
    pad_boxes = [(f"{p['ref']}-{p['name']}", _abs_pad_rect(p)) for p in doc.get("pads", []) if "x_mm" in p and p.get("ref")]
    for ref, lb in sorted(labels.items()):
        for who, pb in pad_boxes:
            if _hit(lb, pb, -1e-6):
                problems.append(f"designator {ref} is over pad {who}")
                break
        if outline and not _inside(lb, outline, -1e-6):
            problems.append(f"designator {ref} is outside the board outline")
    lrefs = sorted(labels)
    for a in range(len(lrefs)):
        for b in range(a + 1, len(lrefs)):
            if _hit(labels[lrefs[a]], labels[lrefs[b]], -1e-6):
                problems.append(f"designators {lrefs[a]} and {lrefs[b]} overlap")
    for t in doc.get("texts", []):
        if t.get("kind") == "designator" and (t.get("height_mm") or 0) > LABEL_H * 1.6:
            problems.append(f"designator {t['text']} is {t['height_mm']:g} mm high (more than {LABEL_H * 1.6:g} mm)")
    for pl in places or []:
        c = comps.get(pl["ref"])
        if c is None:
            continue
        dr = abs(((float(c.get("rotation") or 0) - pl["rot"] + 180) % 360) - 180)
        if abs(c.get("x_mm", 0) - pl["x"]) > 0.02 or abs(c.get("y_mm", 0) - pl["y"]) > 0.02 or dr > 0.5:
            problems.append(f"{pl['ref']} sits at ({c.get('x_mm')}, {c.get('y_mm')}) turned {c.get('rotation')}, the plan says "
                            f"({pl['x']}, {pl['y']}) turned {pl['rot']}")
    return problems
