"""Generated parts: IPC-7351 nominal footprints for standard packages, and symbols (standard shapes or a box).

Used when a BOM line has no LCSC number or EasyEDA has no model. A package that is not in the table is
never guessed: package_key() returns None and the caller reports the line as missing.
Footprints are built in mm with y up (Altium axes) and written in mil, relative to the library origin.
"""
import math
import re

from partlib_convert import MM, MIN_SILK, snap_symbol

# chip: pad centre offset, pad width (x), pad height (y), body width, body height -- all mm
CHIPS = {"0402": (0.48, 0.56, 0.62, 1.0, 0.5), "0603": (0.825, 0.80, 0.95, 1.6, 0.8),
         "0805": (0.95, 1.00, 1.45, 2.0, 1.25), "1206": (1.50, 1.15, 1.80, 3.2, 1.6)}
# two-pad diodes: pad centre offset, pad w, pad h, body w, body h
DIODES = {"SOD-123": (1.635, 0.91, 1.22, 2.7, 1.6), "SOD-323": (1.05, 0.60, 0.45, 1.7, 1.25)}
# dual-row ICs: pitch, row centre offset, pad length (x), pad width (y), body width, body length
DUAL = {"SOIC": (1.27, 2.70, 1.55, 0.60, 3.9, None), "TSSOP": (0.65, 2.85, 1.50, 0.40, 4.4, None)}
BODY_LEN = {("SOIC", 8): 4.9, ("SOIC", 14): 8.7, ("SOIC", 16): 9.9, ("TSSOP", 8): 3.0, ("TSSOP", 14): 5.0,
            ("TSSOP", 16): 5.0, ("TSSOP", 20): 6.5}
SOT = {"SOT-23-3": (0.95, 1.00, 0.90, 0.80, 1.3, 2.9), "SOT-23-5": (0.95, 1.10, 1.06, 0.65, 1.6, 2.9),
       "SOT-23-6": (0.95, 1.10, 1.06, 0.65, 1.6, 2.9)}


def package_key(pkg):
    """Canonical package name from a BOM package string, or None when it is not one we generate."""
    raw = (pkg or "").strip()
    m = re.search(r"header", raw, re.I) and re.search(r"([12])\s*x\s*(\d{1,2})", raw, re.I)
    if m:
        pitch = re.search(r"(\d\.\d+)\s*mm", raw)
        if pitch and pitch.group(1) != "2.54":
            return None
        return f"PinHeader-{m.group(1)}x{int(m.group(2)):02d}_P2.54mm"
    from library import _normalize_pkg
    s = _normalize_pkg(re.sub(r"[_\s]*\d+(\.\d+)?\s*x\s*\d+(\.\d+)?\s*mm", "", raw, flags=re.I))
    s = re.sub(r"^(c|r|l|led|d)(?=\d{4}$)", "", s)           # c0603, r0805, led0603
    if s in CHIPS:
        return s
    if s in ("sod123", "sod323"):
        return f"SOD-{s[3:]}"
    if s in ("sot23", "sot233"):
        return "SOT-23-3"
    if s in ("sot235", "sot236"):
        return f"SOT-23-{s[-1]}"
    if s == "sot223":
        return "SOT-223"
    m = re.fullmatch(r"(soic|tssop)(\d+)", s)
    if m and (m.group(1).upper(), int(m.group(2))) in BODY_LEN:
        return f"{m.group(1).upper()}-{m.group(2)}"
    return None


def _pad(num, x, y, w, h, shape=2, hole=0):
    layer, plated = ("Multi-Layer", 1) if hole else ("Top Layer", 1)
    return (f"PAD|{num}|{_m(x)}|{_m(y)}|0|{layer}|{plated}|{_m(hole) if hole else 0}|0|0|0|{_m(w)}|{_m(h)}|{shape}|")


def _m(v):
    return round(v * MM, 3) + 0.0


def _track(x1, y1, x2, y2, layer, w=MIN_SILK):
    return f"TRACK|{_m(x1)}|{_m(y1)}|{_m(x2)}|{_m(y2)}|{w}|{layer}"


def _rect(x1, y1, x2, y2, layer, w):
    return [_track(x1, y1, x2, y1, layer, w), _track(x2, y1, x2, y2, layer, w),
            _track(x2, y2, x1, y2, layer, w), _track(x1, y2, x1, y1, layer, w)]


def _finish(name, desc, pads, body, silk, pin1=None, tht=False):
    """pads: [(num,x,y,w,h[,shape,hole])] in mm; body (w,h) mm; silk: extra TRACK lines."""
    xs = [p[1] + s * p[3] / 2 for p in pads for s in (-1, 1)] + [-body[0] / 2, body[0] / 2]
    ys = [p[2] + s * p[4] / 2 for p in pads for s in (-1, 1)] + [-body[1] / 2, body[1] / 2]
    c = 0.25                                            # courtyard margin
    lines = [_pad(p[0], p[1], p[2], p[3], p[4], *p[5:7]) for p in pads]
    lines += silk
    if pin1:
        lines.append(f"ARC|{_m(pin1[0])}|{_m(pin1[1])}|{_m(0.12)}|0|360|{MIN_SILK}|Top Overlay")
    lines += [_track(-body[0] / 2, -body[1] / 2, body[0] / 2, -body[1] / 2, "Mechanical Layer 13", 4),
              _track(body[0] / 2, -body[1] / 2, body[0] / 2, body[1] / 2, "Mechanical Layer 13", 4),
              _track(body[0] / 2, body[1] / 2, -body[0] / 2, body[1] / 2, "Mechanical Layer 13", 4),
              _track(-body[0] / 2, body[1] / 2, -body[0] / 2, -body[1] / 2, "Mechanical Layer 13", 4)]
    x1, x2, y1, y2 = min(xs) - c, max(xs) + c, min(ys) - c, max(ys) + c
    lines += [_track(x1, y1, x2, y1, "Mechanical Layer 15", 2), _track(x2, y1, x2, y2, "Mechanical Layer 15", 2),
              _track(x2, y2, x1, y2, "Mechanical Layer 15", 2), _track(x1, y2, x1, y1, "Mechanical Layer 15", 2)]
    return {"name": name, "desc": desc, "lines": lines, "tht": tht, "model": None}


def footprint_for(key):
    """The generated footprint dict {name, lines, tht, model} for a canonical package key."""
    desc = f"{key} IPC-7351 nominal (generated)"
    if key in CHIPS:
        cx, pw, ph, bw, bh = CHIPS[key]
        y = ph / 2 + 0.2
        silk = [_track(-cx, y, cx, y, "Top Overlay"), _track(-cx, -y, cx, -y, "Top Overlay")]
        return _finish(f"CHIP-{key}", desc, [(1, -cx, 0, pw, ph), (2, cx, 0, pw, ph)], (bw, bh), silk)
    if key in DIODES:
        cx, pw, ph, bw, bh = DIODES[key]
        y = max(ph, bh) / 2 + 0.2
        silk = [_track(-cx, y, cx, y, "Top Overlay"), _track(-cx, -y, cx, -y, "Top Overlay")]
        return _finish(key, desc, [(1, -cx, 0, pw, ph), (2, cx, 0, pw, ph)], (bw, bh), silk)
    if key in SOT:
        pitch, cx, pw, ph, bw, bl = SOT[key]
        n = int(key[-1])
        if n == 3:
            pads = [(1, -cx, pitch / 2, pw, ph), (2, -cx, -pitch / 2, pw, ph), (3, cx, 0, pw, ph)]
        else:
            rows = [pitch, 0, -pitch]
            pads = [(i + 1, -cx, rows[i], pw, ph) for i in range(3)]
            right = [4, 5, 6] if n == 6 else [4, 5]
            ys = [-pitch, 0, pitch] if n == 6 else [-pitch, pitch]
            pads += [(num, cx, y, pw, ph) for num, y in zip(right, ys)]
            pads.sort(key=lambda p: p[0])
        ye = max(p[2] + p[4] / 2 for p in pads) + 0.2
        silk = [_track(-bw / 2, ye, bw / 2, ye, "Top Overlay"), _track(-bw / 2, -ye, bw / 2, -ye, "Top Overlay")]
        return _finish(key, desc, pads, (bw, bl), silk, pin1=(-cx - pw / 2 - 0.3, pads[0][2]))
    if key == "SOT-223":
        pads = [(1, -3.15, 2.3, 2.0, 1.5), (2, -3.15, 0, 2.0, 1.5), (3, -3.15, -2.3, 2.0, 1.5), (4, 3.15, 0, 2.0, 3.8)]
        silk = [_track(-1.8, 3.35, 1.8, 3.35, "Top Overlay"), _track(-1.8, -3.35, 1.8, -3.35, "Top Overlay")]
        return _finish(key, desc, pads, (3.5, 6.5), silk, pin1=(-4.5, 2.3))
    m = re.fullmatch(r"(SOIC|TSSOP)-(\d+)", key)
    if m:
        pitch, rx, pl, pw, bw, _ = DUAL[m.group(1)]
        n = int(m.group(2))
        bl = BODY_LEN[(m.group(1), n)]
        top = (n / 2 - 1) * pitch / 2
        half = n // 2
        pads = [(i + 1, -rx, top - i * pitch, pl, pw) for i in range(half)]
        pads += [(half + i + 1, rx, -top + i * pitch, pl, pw) for i in range(half)]
        ye = bl / 2
        xe = min(bw / 2, rx - pl / 2 - 0.2)
        silk = [_track(-xe, ye, xe, ye, "Top Overlay"), _track(-xe, -ye, xe, -ye, "Top Overlay")]
        return _finish(key, desc, pads, (bw, bl), silk, pin1=(-rx - pl / 2 - 0.3, top))
    m = re.fullmatch(r"PinHeader-(\d)x(\d+)_P2\.54mm", key)
    if m:
        rows, n = int(m.group(1)), int(m.group(2))
        pads = []
        for i in range(n):
            for r in range(rows):
                pads.append((i * rows + r + 1, r * 2.54, -i * 2.54, 1.7, 1.7, 2 if i == 0 and r == 0 else 1, 1.0))
        bw, bh = rows * 2.54, n * 2.54
        cx, cy = (rows - 1) * 2.54 / 2, -(n - 1) * 2.54 / 2
        for p in range(len(pads)):                                  # centre the part on the library origin
            q = list(pads[p])
            q[1] -= cx
            q[2] -= cy
            pads[p] = tuple(q)
        silk = []
        for ln in _rect(-bw / 2, -bh / 2, bw / 2, bh / 2, "Top Overlay", MIN_SILK):
            silk.append(ln)
        return _finish(key, desc, pads, (bw, bh), silk, tht=True)
    raise KeyError(key)


# ------------------------------------------------------------------ symbols
POWER_NAME = re.compile(r"^(\+?\d+V\d*|[AD]?GND\w*|VSS\w*|VCC\w*|VDD\w*|VBAT\w*|VIN\w*|VBUS\w*|VREF\w*|PGND\w*|"
                        r"\+\w+)$", re.I)
GROUND_NAME = re.compile(r"^([AD]?GND\w*|VSS\w*|PGND\w*|EP|PAD)$", re.I)
OUT_NAME = re.compile(r"(^|_)(OUT|TX|TXD|DO|SO|MOSI|Q)\d*($|_)", re.I)
IN_NAME = re.compile(r"(^|_)(IN|RX|RXD|DI|SI|MISO|EN|CLK|CS|NRST|RESET)\d*($|_)", re.I)
PASSIVE_PREFIX = {"R", "C", "L", "FB", "D", "LED", "F", "TVS", "ZD", "Y", "X", "SW", "TP", "J", "P", "JP", "RN"}


def pin_type(name, prefix):
    if prefix in PASSIVE_PREFIX:
        return "Passive"
    if POWER_NAME.match(name or ""):
        return "Power"
    if OUT_NAME.search(name or ""):
        return "Output"
    if IN_NAME.search(name or ""):
        return "Input"
    return "IO"


def _pin(num, name, ptype, orient, x, y, length):
    return {"num": str(num), "name": name, "type": ptype, "orient": orient, "x": x, "y": y, "len": length}


def two_pin_symbol(prefix, hint, pins):
    """R / C / L / diode / generic two-pin shapes. pins: [(num,name)] in order; returns (pins, gfx, issues)."""
    (n1, nm1), (n2, nm2) = (list(pins) + [("1", "1"), ("2", "2")])[:2]
    issues = []
    left, right = (n1, nm1), (n2, nm2)
    shape = "box"
    if prefix in ("D", "LED", "TVS", "ZD"):
        shape = "diode"
        # SOD/chip diode pad 1 is the cathode; sheet pin names A/K override
        names = {nm1.upper(): (n1, nm1), nm2.upper(): (n2, nm2)}
        if {"A", "K"} <= set(names):
            left, right = names["A"], names["K"]
        else:
            left, right = (n2, nm2), (n1, nm1)
            issues.append("diode: pin 1 drawn as cathode, check the datasheet")
    elif prefix in ("C",):
        shape = "cap"
    elif prefix in ("L", "FB"):
        shape = "ind"
    elif prefix == "R" or not prefix:
        shape = "box"
    pt = lambda: "Passive"
    if shape in ("box", "ind"):
        half, ln = 100, 100
    else:
        half, ln = 20, 180
    p = [_pin(left[0], left[1], pt(), "eRotate180", -half, 0, ln),
         _pin(right[0], right[1], pt(), "eRotate0", half, 0, ln)]
    if shape == "box":
        g = [["rectangle", "1", "1", "0", -100, -40, 100, 40]]
    elif shape == "cap":
        g = [["polyline", "1", "1", -20, -60, -20, 60], ["polyline", "1", "1", 20, -60, 20, 60]]
    elif shape == "ind":
        g = [["arc", "1", "1", -75 + 50 * i, 0, 25, 0, 180] for i in range(4)]
    else:
        g = [["polygon", "1", "1", "1", -20, 70, -20, -70, 20, 0], ["polyline", "1", "1", 20, -70, 20, 70]]
    return p, g, issues


def transistor_symbol(name_hint, pins):
    """3-pin Q: gate/base left, drain/collector top, source/emitter bottom. pins: [(num,name)] or []."""
    issues = []
    if not pins:
        pins = [("1", "G"), ("2", "S"), ("3", "D")]
        issues.append("transistor pins assumed 1=G 2=S 3=D, check the datasheet")
    role = {}
    for num, nm in pins:
        u = (nm or "").upper()
        role["g" if u in ("G", "B", "GATE", "BASE") else "d" if u in ("D", "C", "DRAIN", "COLLECTOR")
             else "s" if u in ("S", "E", "SOURCE", "EMITTER") else "?"] = (num, nm)
    if set(role) != {"g", "d", "s"}:
        return None
    pch = bool(re.search(r"p[-_ ]?ch|pnp|p-?mos|\bp\b", name_hint or "", re.I))
    p = [_pin(role["g"][0], role["g"][1], "Passive", "eRotate180", -100, 0, 200),
         _pin(role["d"][0], role["d"][1], "Passive", "eRotate90", 0, 100, 200),
         _pin(role["s"][0], role["s"][1], "Passive", "eRotate270", 0, -100, 200)]
    g = [["polyline", "1", "1", -100, 0, -40, 0], ["polyline", "1", "1", -40, -80, -40, 80],
         ["polyline", "1", "1", 0, -100, 0, 100]]
    g.append(["polygon", "1", "1", "1", -5, 0, -35, 20, -35, -20] if pch else
             ["polygon", "1", "1", "1", -35, 0, -5, 20, -5, -20])
    return p, g, issues


def box_symbol(prefix, pins, issues):
    """A rectangle with the part's pins: power top, ground bottom, outputs right, the rest left.

    pins: [{"num","name","side"?}] from the netlist sheet. Names the sheet marks left/right keep that side."""
    left, right, top, bottom = [], [], [], []
    for pn in pins:
        name = pn.get("name") or ""
        side = pn.get("side")
        if GROUND_NAME.match(name):
            bottom.append(pn)
        elif POWER_NAME.match(name) and prefix not in PASSIVE_PREFIX and side not in ("left", "right"):
            top.append(pn)
        elif side == "right" or (not side and OUT_NAME.search(name)):
            right.append(pn)
        else:
            left.append(pn)
    ndots = max(len(left), len(right), 1)
    maxl = max([len(p["name"]) for p in left] or [0])
    maxr = max([len(p["name"]) for p in right] or [0])
    width = max(600, math.ceil(((maxl + maxr) * 60 + 200) / 100) * 100)
    half = max(math.ceil(width / 200) * 100, 100 * (max(len(top), len(bottom)) // 2 + 1))
    ymax, ymin = 100, -100 * ndots
    out = []

    def pin(pn, orient, x, y):
        out.append(_pin(pn["num"], pn["name"], pin_type(pn["name"], prefix), orient, x, y, 200))
    for i, pn in enumerate(left):
        pin(pn, "eRotate180", -half, -100 * i)
    for i, pn in enumerate(right):
        pin(pn, "eRotate0", half, -100 * i)
    for grp, orient, y in ((top, "eRotate90", ymax), (bottom, "eRotate270", ymin)):
        start = -100 * ((len(grp) - 1) // 2)
        for i, pn in enumerate(grp):
            pin(pn, orient, start + 100 * i, y)
    gfx = [["rectangle", "1", "1", "0", -half, ymin, half, ymax]]
    return out, gfx, issues


def symbol_for(prefix, hint, sheet_pins, npads):
    """(pins, gfx, issues) for a part, or None when its pins cannot be known (never invented).

    sheet_pins: [{"num","name","side"?}] from the project's netlist sheets (may be empty);
    npads: pad count of the footprint, used when the sheet has no pins for the part."""
    sp = [p for p in sheet_pins if re.fullmatch(r"[A-Za-z0-9]{1,6}", str(p.get("num", "")))]
    issues = [f"{len(sheet_pins) - len(sp)} netlist pin(s) without a pin number left out"] if len(sp) < len(sheet_pins) else []
    n = len(sp) or npads
    pairs = [(p["num"], p["name"]) for p in sp]
    if n == 2:
        a, b, c = two_pin_symbol(prefix, hint, pairs)
        return a, b, c + issues
    if prefix == "Q" and n == 3:
        t = transistor_symbol(hint, pairs)
        if t:
            return t[0], t[1], t[2] + issues
    if not sp and prefix in ("J", "P", "JP", "H") and n:         # a header: its pins are just numbered
        sp = [{"num": str(i), "name": str(i)} for i in range(1, n + 1)]
    return box_symbol(prefix, sp, issues) if sp else None
