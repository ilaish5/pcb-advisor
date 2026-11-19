"""KiCad library (as written by easyeda2kicad) -> symbol and footprint dicts for the Altium batch specs.

Ported from the kiln board's kicad2spec.py. Conventions (each one was learned the hard way):
  * batch PAD/TRACK coordinates are relative to the library origin, never +50000 mil
  * KiCad footprint y points down, Altium y up: footprint y is negated (symbols are y up in both)
  * KiCad pin 'at' is the connection end; the Altium pin location is the body end
  * pin connection points sit on a 100 mil grid: the symbol is shifted, a stray pin gets longer
  * silk is at least 0.15 mm wide; '|' is the spec delimiter, so it never appears in text
The files are untrusted data: everything is parsed defensively and a bad file raises (ValueError and friends).
"""
import math
import re

MM = 1 / 0.0254                     # mm -> mil
MIN_SILK = 6.0                      # mil, just over 0.15 mm
MAX_FILE = 2_000_000
DIRS = {"eRotate0": (1, 0), "eRotate180": (-1, 0), "eRotate90": (0, 1), "eRotate270": (0, -1)}
KICAD_PIN_TYPES = {"input": "Input", "output": "Output", "bidirectional": "IO", "power_in": "Power",
                   "power_out": "Power"}
LAYERS = {"F.SilkS": "Top Overlay", "F.Fab": "Mechanical Layer 13", "F.CrtYd": "Mechanical Layer 15",
          "F.Cu": "Top Layer"}


def clean(text, limit=200):
    """Text for a spec line: no '|' or line breaks, cp1252-safe."""
    s = str(text or "").replace("Ω", "ohm").replace("Ω", "ohm")
    s = re.sub(r"[|\r\n\t]+", " ", s).strip()[:limit]
    return s.encode("cp1252", "replace").decode("cp1252")


def safe_name(text):
    """A symbol/footprint name: letters, digits and . _ + - only."""
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", str(text or "")).strip("_")[:60]


def parse(text):
    """KiCad s-expression -> nested lists."""
    if len(text) > MAX_FILE:
        raise ValueError("file too large")
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack = [[]]
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            if len(stack) < 2:
                raise ValueError("unbalanced parentheses")
            e = stack.pop()
            stack[-1].append(e)
        else:
            stack[-1].append(t[1:-1] if t.startswith('"') else t)
    if len(stack) != 1 or not stack[0]:
        raise ValueError("unbalanced parentheses")
    return stack[0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def one(node, key):
    r = find(node, key)
    return r[0] if r else None


def mil(v):
    return round(float(v) * MM, 3)


def conn(p):
    """Connection point of a pin dict."""
    dx, dy = DIRS[p["orient"]]
    return p["x"] + dx * p["len"], p["y"] + dy * p["len"]


def snap_symbol(pins, gfx, grid=100):
    """Shift the symbol so pin 1 is on the grid, then lengthen any pin that still misses it."""
    if not pins:
        return
    cx, cy = conn(pins[0])
    ox, oy = -(cx % grid), -(cy % grid)
    if ox < -grid / 2:
        ox += grid
    if oy < -grid / 2:
        oy += grid
    if ox or oy:
        for p in pins:
            p["x"] += ox
            p["y"] += oy
        for g in gfx:
            start = {"polyline": 3, "polygon": 4, "rectangle": 4, "arc": 3}[g[0]]
            n = 2 if g[0] == "arc" else len(g) - start
            for i in range(start, start + n):
                g[i] = round(float(g[i]) + (ox if (i - start) % 2 == 0 else oy), 3)
    for p in pins:
        cx, cy = conn(p)
        dx, dy = DIRS[p["orient"]]
        rem = (cx % grid) if dx else (cy % grid)
        if rem:
            p["len"] += (grid - rem) if (dx + dy) > 0 else rem
    _slide_pins_onto_grid(pins, gfx, grid)


def _slide_pins_onto_grid(pins, gfx, grid):
    """A pin still off the grid ACROSS its axis (EasyEDA's NE555: DISCH at y=150) cannot be fixed by its length.
    When its base sits on an edge of the symbol's rectangle, slide it along that edge to the nearest grid line,
    outward from the box centre first, if that point is still on the edge and no other pin ends there. Anything
    else (a pin on a drawn shape, no free point) is left alone: the draw step warns about it."""
    rects = []
    for g in gfx:
        if g[0] == "rectangle":
            x1, y1, x2, y2 = (float(v) for v in g[4:8])
            rects.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    ends = {conn(p) for p in pins}
    bases = {(p["x"], p["y"]) for p in pins}
    for p in pins:
        dx, dy = DIRS[p["orient"]]
        axis = "y" if dx else "x"                   # the coordinate across the pin
        v = p[axis]
        if not v % grid:
            continue
        for x1, y1, x2, y2 in rects:
            if dx and min(abs(p["x"] - x1), abs(p["x"] - x2)) <= 1:
                lo, hi = y1, y2
            elif dy and min(abs(p["y"] - y1), abs(p["y"] - y2)) <= 1:
                lo, hi = x1, x2
            else:
                continue
            if not lo - 1 <= v <= hi + 1:           # on the edge's line, but beyond this box (another unit's box)
                continue
            down = v - v % grid
            for nv in ((down + grid, down) if v >= (lo + hi) / 2 else (down, down + grid)):
                moved = {**p, axis: nv}
                end, base = conn(moved), (moved["x"], moved["y"])
                if lo <= nv <= hi and end not in ends and base not in bases:
                    ends.discard(conn(p))
                    bases.discard((p["x"], p["y"]))
                    p[axis] = nv
                    ends.add(end)
                    bases.add(base)
                    break
            break


def _graphic(it):
    k = it[0]
    if k == "rectangle":
        st, en = one(it, "start"), one(it, "end")
        return ["rectangle", "1", "1", "0", mil(st[1]), mil(st[2]), mil(en[1]), mil(en[2])]
    if k == "polyline":
        pts = one(it, "pts")[1:]
        xy = [v for p in pts for v in (mil(p[1]), mil(p[2]))]
        fill = one(it, "fill")
        ftype = one(fill, "type") if fill else None
        if ftype and ftype[1] in ("background", "outline") and len(pts) >= 3:
            return ["polygon", "1", "1", "1"] + xy
        return ["polyline", "1", "1"] + xy
    if k == "circle":
        c, r = one(it, "center"), float(one(it, "radius")[1])
        return ["arc", "1", "1", mil(c[1]), mil(c[2]), round(r * MM, 3), 0, 360]
    if k == "arc":
        (x1, y1), (x2, y2), (x3, y3) = [(float(p[1]), float(p[2])) for p in
                                        (one(it, "start"), one(it, "mid"), one(it, "end"))]
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if not d:
            return None
        ux = ((x1*x1 + y1*y1) * (y2 - y3) + (x2*x2 + y2*y2) * (y3 - y1) + (x3*x3 + y3*y3) * (y1 - y2)) / d
        uy = ((x1*x1 + y1*y1) * (x3 - x2) + (x2*x2 + y2*y2) * (x1 - x3) + (x3*x3 + y3*y3) * (x2 - x1)) / d
        a1 = math.degrees(math.atan2(y1 - uy, x1 - ux)) % 360
        a3 = math.degrees(math.atan2(y3 - uy, x3 - ux)) % 360
        am = math.degrees(math.atan2(y2 - uy, x2 - ux)) % 360
        if not (am - a1) % 360 < (a3 - a1) % 360:
            a1, a3 = a3, a1
        return ["arc", "1", "1", round(ux * MM, 3), round(uy * MM, 3),
                round(math.hypot(x1 - ux, y1 - uy) * MM, 3), round(a1, 2), round(a3, 2)]
    return None


def convert_symbols(text):
    """Every symbol of a lib.kicad_sym as {name, props, footprint, pins, gfx}; pins/graphics in mil, grid-snapped."""
    root = parse(text)[0]
    out = []
    for s in find(root, "symbol"):
        props = {p[1]: p[2] for p in find(s, "property") if len(p) > 2}
        pins, gfx = [], []
        for unit in [s] + find(s, "symbol"):
            for it in unit[1:]:
                if not isinstance(it, list) or not it:
                    continue
                if it[0] == "pin":
                    at = one(it, "at")
                    x, y = float(at[1]), float(at[2])
                    ang = float(at[3]) if len(at) > 3 else 0
                    ln = float(one(it, "length")[1])
                    bx = x + ln * math.cos(math.radians(ang))
                    by = y + ln * math.sin(math.radians(ang))
                    orient = {0: "eRotate180", 90: "eRotate270", 180: "eRotate0", 270: "eRotate90"}[int(ang) % 360]
                    pins.append({"num": one(it, "number")[1], "name": one(it, "name")[1],
                                 "type": KICAD_PIN_TYPES.get(it[1], "Passive"), "orient": orient,
                                 "x": round(bx * MM / 10) * 10, "y": round(by * MM / 10) * 10,
                                 "len": round(ln * MM)})
                else:
                    g = _graphic(it)
                    if g:
                        gfx.append(g)
        snap_symbol(pins, gfx)
        out.append({"name": s[1], "props": props, "footprint": props.get("Footprint", "").split(":")[-1],
                    "pins": pins, "gfx": gfx})
    return out


def convert_footprint(text):
    """One kicad_mod -> {name, lines, tht, model}; lines are the spec lines after FOOTPRINT, in mil, y up."""
    m = parse(text)[0]
    X = lambda v: round(float(v) * MM, 3) + 0.0      # + 0.0 turns -0.0 into 0.0
    Y = lambda v: round(-float(v) * MM, 3) + 0.0
    lines, tht, notes = [], False, []
    for it in m[2:]:
        if not isinstance(it, list) or not it:
            continue
        k = it[0]
        lay = LAYERS.get((one(it, "layer") or [None, None])[1])
        width = one(it, "width") or one(one(it, "stroke") or [], "width")
        w = mil(width[1]) if width else 5
        if lay == "Top Overlay":
            w = max(w, MIN_SILK)
        if k == "pad":
            cu = one(it, "layers")
            if cu is not None and not any(".Cu" in str(v) for v in cu[1:]):
                continue                                        # paste or mask only: no copper
            at, size = one(it, "at"), one(it, "size")
            rot = float(at[3]) if len(at) > 3 else 0
            shape = {"rect": 2, "circle": 1, "oval": 1, "roundrect": 9}.get(it[3], 2)
            pct = str(round(float(one(it, "roundrect_rratio")[1]) * 200)) if it[3] == "roundrect" else ""
            drill = one(it, "drill")
            if it[2] in ("thru_hole", "np_thru_hole") and drill:
                nums = [float(v) for v in drill[1:] if re.fullmatch(r"[-\d.]+", str(v))]
                hole, htype, hw, hrot = mil(max(nums)), 0, 0, 0
                if len(nums) > 1 and nums[0] != nums[1]:        # drill oval X Y: a slot, long axis along the larger
                    hole, htype, hw, hrot = mil(min(nums[:2])), 2, mil(max(nums[:2])), 90 if nums[1] > nums[0] else 0
                layer, plated = "Multi-Layer", 1 if it[2] == "thru_hole" else 0
                if plated and size and float(size[1]) <= nums[0] and float(size[2]) <= nums[-1]:
                    plated = 0                                  # no annular ring: a mechanical hole
                tht = True
            else:
                hole, htype, hw, hrot, layer, plated = 0, 0, 0, 0, "Top Layer", 1
            lines.append(f"PAD|{clean(it[1], 20)}|{X(at[1])}|{Y(at[2])}|{rot}|{layer}|{plated}|{hole}|{htype}|{hw}|{hrot}|"
                         f"{mil(size[1])}|{mil(size[2])}|{shape}|{pct}")
        elif k == "fp_line" and lay:
            s, e = one(it, "start"), one(it, "end")
            lines.append(f"TRACK|{X(s[1])}|{Y(s[2])}|{X(e[1])}|{Y(e[2])}|{w}|{lay}")
        elif k == "fp_rect" and lay:
            s, e = one(it, "start"), one(it, "end")
            x1, y1, x2, y2 = X(s[1]), Y(s[2]), X(e[1]), Y(e[2])
            for a, b, c, d in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
                lines.append(f"TRACK|{a}|{b}|{c}|{d}|{w}|{lay}")
        elif k == "fp_circle" and lay:
            c, e = one(it, "center"), one(it, "end")
            r = math.hypot(float(e[1]) - float(c[1]), float(e[2]) - float(c[2]))
            lines.append(f"ARC|{X(c[1])}|{Y(c[2])}|{round(r * MM, 3)}|0|360|{w}|{lay}")
        elif k == "fp_arc" and lay and one(it, "angle"):
            c, e = one(it, "start"), one(it, "end")     # legacy: start = centre, end = arc start
            ang = float(one(it, "angle")[1])
            r = math.hypot(float(e[1]) - float(c[1]), float(e[2]) - float(c[2]))
            a0 = math.degrees(math.atan2(-(float(e[2]) - float(c[2])), float(e[1]) - float(c[1])))
            lo, hi = sorted((a0, a0 - ang))
            lines.append(f"ARC|{X(c[1])}|{Y(c[2])}|{round(r * MM, 3)}|{round(lo % 360, 2)}|"
                         f"{round(lo % 360 + hi - lo, 2)}|{w}|{lay}")
        elif k == "fp_poly" and lay:
            pts = one(it, "pts")[1:]
            lines.append(f"REGION|{lay}|0|" + "|".join(f"{X(p[1])}|{Y(p[2])}" for p in pts))
    return {"name": m[1], "lines": clip_silk(lines), "tht": tht, "notes": sorted(set(notes)), "model": kicad_model(text, tht)}


SILK_TO_PAD = 0.15                     # mm, JLC's silkscreen-to-pad clearance (pcb-capabilities: "Pad to silkscreen")
SILK_DANGER = 5.0                      # mil: JLCDFM rates silk closer than this to a pad Danger (pcb-capabilities, 14/10)
MIN_PIECE = 5.0                        # mil: a silk piece shorter than this after clipping is dropped
# Altium measures silk to the MASK OPENING, not to the copper: the JLC preset's rules are a mask expansion of 2 mil per side and a
# silk-to-solder-mask clearance of 6 mil (jlc_preset.py; a test keeps these two numbers equal to the preset's), so silk must stay
# 8 mil from the copper edge or the board's own design rule check fails (218 violations on the first live STM32 board, silk 5 mil
# from the mask). SILK_TO_PAD (JLC's fab limit, 0.15 mm = 5.9 mil) alone is not enough.
MASK_EXPANSION_MIL = 2.0
SILK_TO_MASK_MIL = 6.0
SILK_TO_COPPER_MIL = max(SILK_TO_PAD / MM * 1000, MASK_EXPANSION_MIL + SILK_TO_MASK_MIL)    # silk edge to copper edge, mil


def _pad_boxes(lines):
    """(x, y, rot, half x, half y, round) of every copper pad, in mil; a hole bigger than its copper (an NPTH) counts."""
    out = []
    for ln in lines:
        f = ln.split("|")
        if f[0] == "PAD":
            sx, sy, hole, slot = float(f[11]), float(f[12]), float(f[7] or 0), float(f[9] or 0)
            along = slot if f[8] == "2" else hole                 # a slot's length runs along x, or y when turned 90
            sx, sy = (max(sx, along), max(sy, hole)) if float(f[10] or 0) % 180 == 0 else (max(sx, hole), max(sy, along))
            out.append((float(f[2]), float(f[3]), float(f[4]), sx / 2, sy / 2, f[13] == "1" and sx == sy))
    return out


def _gap(px, py, box, grow=0.0):
    """Distance in mil from a point to a pad's copper grown by `grow` on every side (a rectangle in the pad's own frame, grown
    square at the corners the way Altium's mask opening is; a round pad as a circle)."""
    x, y, rot, hx, hy, round_ = box
    hx, hy = hx + grow, hy + grow
    dx, dy = px - x, py - y
    if round_:
        return max(math.hypot(dx, dy) - hx, 0.0)
    a = math.radians(-rot)
    u, v = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    return math.hypot(max(abs(u) - hx, 0.0), max(abs(v) - hy, 0.0))


def _runs(points, ok):
    """Index ranges [i, j] of consecutive points that are all clear."""
    out, start = [], None
    for i, good in enumerate(ok):
        if good and start is None:
            start = i
        if not good and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(points) - 1))
    return out


def clip_silk(lines):
    """Cut the top silkscreen of a vendor footprint (EasyEDA's USB-C and LED outlines run over their pads: JLC DFM flagged
    them, 16/11) so no silk line is closer to the copper than SILK_TO_COPPER_MIL: the mask expansion plus the silk-to-solder-mask
    rule (SILK_DANGER, JLCDFM's Danger limit, is looser and would leave silk the board's own design rule check flags). The
    mask opening is the copper grown SQUARE (a rectangle pad's corner stays a corner), so near a pad's corner the silk must be
    SILK_TO_MASK_MIL from that grown rectangle, not just SILK_TO_COPPER_MIL from the copper: a silk end 12.6 mil sideways and
    3 mil beyond a pad corner is 8 mil from the copper but only 5.7 mil from its opening (the LED of the Live-STM32 board: 0.140 mm). The generated
    footprints keep the same distance (partlib_generate.CLEAR). Lines and arcs are cut into the pieces that stay clear; pieces under
    MIN_PIECE are dropped. Text, regions and other layers are left as they are."""
    boxes = _pad_boxes(lines)
    if not boxes:
        return lines
    out = []
    for ln in lines:
        f = ln.split("|")
        if f[0] not in ("TRACK", "ARC") or f[-1] != "Top Overlay":
            out.append(ln)
            continue
        w = float(f[5] if f[0] == "TRACK" else f[6])
        need = max(SILK_DANGER, SILK_TO_PAD / MM * 1000) + w / 2             # from the copper (JLC's fab limit)
        need_mask = SILK_TO_MASK_MIL + w / 2                                # from the mask opening
        if f[0] == "TRACK":
            x1, y1, x2, y2 = (float(v) for v in f[1:5])
            n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1)))            # a point per mil
            pts = [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]
        else:
            cx, cy, r, a0, a1 = (float(v) for v in f[1:6])
            a1 += 360 if a1 < a0 else 0                             # counter-clockwise from a0 to a1
            n = max(1, math.ceil(math.radians(a1 - a0) * r))
            angs = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
            pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in angs]
        ok = [all(_gap(px, py, b) >= need and _gap(px, py, b, MASK_EXPANSION_MIL) >= need_mask for b in boxes) for px, py in pts]
        if all(ok):
            out.append(ln)
            continue
        for i, j in _runs(pts, ok):
            (ax, ay), (bx, by) = pts[i], pts[j]
            if f[0] == "TRACK":
                if math.hypot(bx - ax, by - ay) >= MIN_PIECE:
                    out.append(f"TRACK|{round(ax, 3)}|{round(ay, 3)}|{round(bx, 3)}|{round(by, 3)}|{f[5]}|{f[6]}")
            elif math.radians(angs[j] - angs[i]) * r >= MIN_PIECE:
                lo = angs[i] - 360 * (angs[i] // 360)                # start in 0..360, the end follows it
                out.append(f"ARC|{f[1]}|{f[2]}|{f[3]}|{round(lo, 2)}|{round(lo + angs[j] - angs[i], 2)}|{f[6]}|{f[7]}")
    return out


def kicad_model(text, tht):
    """The 3D model line of a kicad_mod: {file, rx, ry, rz, dx, dy, seat} in Altium terms, or None.

    Rotations have the opposite sign to Altium's, the offset maps straight on x/y (no y flip); legacy
    (at (xyz)) is in inches, (offset (xyz)) in mm. seat=1 lifts an SMD body onto the board."""
    t = text.replace("\n", " ")
    mm = re.search(r'\(model\s+"?([^"\s)]+)"?', t)
    if not mm:
        return None
    rot = re.search(r"\(rotate\s*\(xyz\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", t)
    off = re.search(r"\(offset\s*\(xyz\s+([-\d.]+)\s+([-\d.]+)", t)
    at = re.search(r"\(model[^()]*\(at\s*\(xyz\s+([-\d.]+)\s+([-\d.]+)", t)
    if off:
        dx, dy = float(off.group(1)) * MM, float(off.group(2)) * MM
    elif at:
        dx, dy = float(at.group(1)) * 1000, float(at.group(2)) * 1000
    else:
        dx = dy = 0.0
    k = [float(rot.group(i)) for i in (1, 2, 3)] if rot else [0.0, 0.0, 0.0]
    return {"file": mm.group(1), "rx": (-k[0]) % 360, "ry": (-k[1]) % 360, "rz": (-k[2]) % 360,
            "dx": round(dx, 3), "dy": round(dy, 3), "seat": 0 if tht else 1}


# ---------------------------------------------------------------- pin names that do not fit the symbol body

NAME_CHAR = 60                      # mil per character of a pin name or number (Altium default 10 pt, a little generous)
NAME_MARGIN = 50                    # mil between the body edge and the first letter of a pin name (Altium draws it a little in)
NAME_HEIGHT = 80                    # mil: the part of a text line that is ink (pins 100 mil apart do not touch)
NUMBER_RAISE = 45                   # mil: a pin number sits this far above its pin line
OVERLAP_OK = 30                     # mil two turned (top or bottom) names may overlap before they count as on top of each other
INK_SLACK = 5                       # mil: a drawing line may graze a name box this much


def _text_box(p, text, inside):
    """Rectangle (x0, y0, x1, y1) in mil that a pin's name (inside the body, a margin in from the pin's body end) or number (along
    the pin, from the body edge outwards, beside it) takes. On a pin at the top or bottom the text is turned to run along the pin."""
    dx, dy = DIRS.get(p.get("orient"), (1, 0))
    w = max(1, len(str(text))) * NAME_CHAR
    x, y = float(p["x"]), float(p["y"])
    h = NAME_HEIGHT / 2
    a, b = (-NAME_MARGIN, -NAME_MARGIN - w) if inside else (0.0, w)       # the name runs into the body, the number out along the pin
    if dy == 0:
        lo, hi = sorted((x + dx * a, x + dx * b))
        return (lo, y - h, hi, y + h) if inside else (lo, y + NUMBER_RAISE, hi, y + NUMBER_RAISE + NAME_HEIGHT)
    lo, hi = sorted((y + dy * a, y + dy * b))
    return (x - h, lo, x + h, hi) if inside else (x - NUMBER_RAISE - NAME_HEIGHT, lo, x - NUMBER_RAISE, hi)


def _segment_hits(box, x1, y1, x2, y2):
    """Does the segment cross the rectangle (Liang-Barsky)?"""
    t0, t1 = 0.0, 1.0
    for d, lo, hi, o in ((x2 - x1, box[0], box[2], x1), (y2 - y1, box[1], box[3], y1)):
        if d == 0:
            if o < lo or o > hi:
                return False
            continue
        ta, tb = (lo - o) / d, (hi - o) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return True


def _obstacles(gfx):
    """Segments and boxes of the drawing inside the body that a pin name must not be drawn over: polylines, polygons and every
    rectangle but the body outline (the biggest one). gfx lines are as the spec has them (numbers may be text)."""
    segs, boxes, rects = [], [], []
    for g in gfx or []:
        try:
            if g[0] == "rectangle":
                x0, y0, x1, y1 = (float(v) for v in g[4:8])
                rects.append((abs((x1 - x0) * (y1 - y0)), (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))))
            elif g[0] in ("polyline", "polygon"):
                xy = [float(v) for v in g[4:]] if g[0] == "polygon" else [float(v) for v in g[3:]]
                pts = list(zip(xy[0::2], xy[1::2]))
                segs += [(*a, *b) for a, b in zip(pts, pts[1:])]
                if g[0] == "polygon" and pts:
                    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                    boxes.append((min(xs), min(ys), max(xs), max(ys)))
        except (ValueError, IndexError):
            continue
    for _, (x0, y0, x1, y1) in sorted(rects, key=lambda r: -r[0])[1:]:
        segs += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
    return segs, boxes


def names_fit(pins, gfx=None):
    """False when pin names would be drawn on top of each other inside the body (a small body whose pins face each other: a 4-pin
    crystal), on top of the symbol's own drawing (gfx: lines, polygons, inner rectangles), or two pin numbers on top of each other
    outside it. A name is never compared with a number: the name is inside the body, the number outside it, along the pin. Such a
    symbol gets its pin names hidden; the numbers stay."""
    for kind in (True, False):
        boxes = [(_text_box(p, p.get("name") if kind else p.get("num"), kind), DIRS.get(p.get("orient"), (1, 0))[1] != 0) for p in pins
                 if (p.get("name") if kind else p.get("num")) not in (None, "", "~")]
        for i, (a, va) in enumerate(boxes):
            for b, vb in boxes[i + 1:]:
                # parallel texts only (a top pin's name crossing a side name is not judged). Names that run along the same row, facing
                # each other (a crystal's two sides), are judged strictly; two turned names on pins 200 mil apart may touch a little
                ok = OVERLAP_OK if va else 0
                if va == vb and a[0] + ok < b[2] and b[0] + ok < a[2] and a[1] + ok < b[3] and b[1] + ok < a[3]:
                    return False
    segs, solid = _obstacles(gfx)
    if segs or solid:
        for p in pins:
            if p.get("name") in (None, "", "~"):
                continue
            x0, y0, x1, y1 = _text_box(p, p["name"], True)
            box = (x0 + INK_SLACK, y0 + INK_SLACK, x1 - INK_SLACK, y1 - INK_SLACK)
            if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in solid) or \
                    any(_segment_hits(box, *sg) for sg in segs):
                return False
    return True
