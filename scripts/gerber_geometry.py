"""Pre-order geometry checks on the produced Gerber / Excellon files (R2, ACCEPTANCE W37).

Three checks, each against a limit cited from shared/reference/jlc/pcb-capabilities.en.md:
  - solder mask web: two mask openings of one layer closer than 0.10 mm (1 oz, green; 0.13 mm for black or white) so no dam is made
  - copper to a non-plated hole: copper closer than 0.20 mm to the wall of an NPTH
  - copper to the routed edge: copper closer than 0.20 mm to the board outline (centre line of the outline layer)
Every finding names the position (mm, in the coordinates of the Gerber files) so the student can find it in Altium.
What the check cannot read (an aperture macro, a block aperture, a file over the size limit) is returned in `skipped`, never as green."""
import math
import re

MASK_WEB_MIN_MM = 0.10             # pcb-capabilities.en.md, Solder mask: bridge 0.10 mm green/red/yellow/blue/purple, 1 oz [P1]
MASK_WEB_BLACK_WHITE = 0.13        # the same table for black and white mask; the colour is not known here
NPTH_TO_COPPER_MM = 0.20
EDGE_TO_COPPER_MM = 0.20
MAX_REPORT = 6                      # per kind; the rest is counted


_AMP = re.compile(r"(\w+)=([^|]*)")
_SIZE = re.compile(r"^\s*([-+]?\d*\.?\d+)\s*(mil|mm|in)?\s*$", re.I)


def _mm(s):
    m = _SIZE.match(s or "")
    if not m:
        return None
    v = float(m.group(1))
    return v * {"mil": 0.0254, "mm": 1.0, "in": 25.4, None: 1.0}[(m.group(2) or "").lower() or None]


def _rot_wh(w, h, deg):
    """Width and height of the bounding box of a w x h rectangle turned by deg degrees."""
    a = math.radians(deg % 180)
    return abs(w * math.cos(a)) + abs(h * math.sin(a)), abs(w * math.sin(a)) + abs(h * math.cos(a))


def _flash_shape(ap, x, y):
    """The shape of aperture `ap` flashed at (x, y), or None. ap = ("C", d) | ("R", w, h) | ("O", w, h) | ("A", shape, w, h, rot)
    where "A" is an Altium macro aperture described by its AMPARAMS comment."""
    kind = ap[0]
    if kind == "C":
        return ("seg", x, y, x, y, ap[1] / 2)
    if kind in ("R", "O"):
        w, h = ap[1], ap[2]
    else:
        w, h = _rot_wh(ap[2], ap[3], ap[4])
        kind = {"round": "C", "oval": "O"}.get(ap[1], "R")
        if kind == "C":
            return ("seg", x, y, x, y, max(w, h) / 2)
    if kind == "O":
        if w >= h:
            return ("seg", x - (w - h) / 2, y, x + (w - h) / 2, y, h / 2)
        return ("seg", x, y - (h - w) / 2, x, y + (h - w) / 2, w / 2)
    return ("rect", x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def parse_layer(text):
    """Read one RS-274X file as Altium writes it.
    {"shapes": flashes and strokes (dark only), "boundary": the outlines of regions as zero-width segments,
     "polys": [(dark, [(x, y)...])] the regions with their polarity, "unread": [why]}, or None when it has no readable format header.
    Altium's habits: coordinates are modal (`Y7874D01*` keeps X), a flash is `X..Y..D02*` then a bare `D03*`, round and rectangular pads
    are standard apertures, other pad shapes are macros described by a `G04:AMPARAMS|DCode=..|XSize=..|YSize=..|Rotation=..|Shape=..|` comment,
    and a pour is a dark region with clear (`%LPC*%`) regions cut out of it."""
    fs = re.search(r"%FS([LT])A?X(\d)(\d)Y(\d)(\d)\*%", text)
    mo = re.search(r"%MO(IN|MM)\*%", text)
    if not fs or not mo:
        return None
    zero, dec = fs.group(1), int(fs.group(3))
    digits = int(fs.group(2)) + dec
    unit = 25.4 if mo.group(1) == "IN" else 1.0

    def num(s):
        sign = -1 if s.startswith("-") else 1
        d = s.lstrip("+-")
        if zero == "T":
            d = d.ljust(digits, "0")
        return sign * int(d or "0") / (10 ** dec) * unit

    aps, amp, unread = {}, {}, set()
    shapes, boundary, polys = [], [], []
    clear, region = False, False
    cur = None
    x = y = 0.0
    mode = 1
    last_op = "02"
    contours, pts = [], None

    def arc(x0, y0, x1, y1, st):
        mi, mj = re.search(r"I([-+]?\d+)", st), re.search(r"J([-+]?\d+)", st)
        cx = x0 + (num(mi.group(1)) if mi else 0.0)
        cy = y0 + (num(mj.group(1)) if mj else 0.0)
        rad = math.hypot(x0 - cx, y0 - cy)
        a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
        if mode == 3:
            while a1 <= a0:
                a1 += 2 * math.pi
        else:
            while a1 >= a0:
                a1 -= 2 * math.pi
        out = []
        for k in range(1, 25):
            a = a0 + (a1 - a0) * k / 24
            out.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
        return out

    for m in re.finditer(r"%([^%]*)%|([^*%]*)\*", text):
        if m.group(1) is not None:
            ext = m.group(1)
            if ext.startswith("LP"):
                clear = ext.startswith("LPC")
            elif ext.startswith("ADD"):
                for a in re.finditer(r"ADD(\d+)([A-Za-z_][\w.$]*)(?:,([^*]*))?\*", ext):
                    d, name, args = a.group(1), a.group(2), a.group(3) or ""
                    vals = [float(v) * unit for v in re.findall(r"[-+]?\d*\.?\d+", args.replace("X", " "))]
                    if name == "C" and vals:
                        aps[d] = ("C", vals[0])
                    elif name in ("R", "O") and len(vals) >= 2:
                        aps[d] = (name, vals[0], vals[1])
                    elif d in amp:
                        aps[d] = amp[d]
                    else:
                        unread.add(f"aperture D{d} ({name}) is a macro without a size comment")
            continue
        st = m.group(2).strip()
        if not st:
            continue
        if st.startswith("G04"):
            if "AMPARAMS" in st:
                kv = dict(_AMP.findall(st))
                w, h, rot = _mm(kv.get("XSize")), _mm(kv.get("YSize")), re.sub(r"[^\d.\-]", "", kv.get("Rotation", "0")) or "0"
                if kv.get("DCode") and w and h:
                    amp[kv["DCode"]] = ("A", re.sub(r"[^a-z]", "", kv.get("Shape", "").lower()), w, h, float(rot))
            continue
        if "G36" in st:
            region, contours, pts = True, [], None
            continue
        if "G37" in st:
            if pts and len(pts) > 2:
                contours.append(pts)
            for c in contours:
                polys.append((not clear, c))
                if clear:              # the edge of a cut-out is where copper is NOT: it is no copper edge for the edge check
                    continue
                for p, q in zip(c, c[1:] + c[:1]):
                    boundary.append(("seg", p[0], p[1], q[0], q[1], 0.0))
            region, contours, pts = False, [], None
            continue
        for g, v in (("G01", 1), ("G02", 2), ("G03", 3)):
            if g in st:
                mode = v
        md = re.search(r"D(\d+)$", st)
        mx, my = re.search(r"X([-+]?\d+)", st), re.search(r"Y([-+]?\d+)", st)
        if md and int(md.group(1)) >= 10 and not (mx or my):
            cur = md.group(1).lstrip("0") or "0"
            continue
        if not (mx or my or md):
            continue
        x0, y0 = x, y
        if mx:
            x = num(mx.group(1))
        if my:
            y = num(my.group(1))
        op = md.group(1).lstrip("0") if md else last_op
        op = op or "0"
        last_op = op
        if region:
            if op == "2":
                if pts and len(pts) > 2:
                    contours.append(pts)
                pts = [(x, y)]
            elif op == "1":
                if pts is None:
                    pts = [(x0, y0)]
                if mode in (2, 3) and re.search(r"[IJ]", st):
                    pts += arc(x0, y0, x, y, st)
                else:
                    pts.append((x, y))
            continue
        if clear:
            continue
        ap = aps.get(cur)
        if op == "3" and ap:
            shapes.append(_flash_shape(ap, x, y))
        elif op == "1" and ap:
            r = ap[1] / 2 if ap[0] == "C" else min(ap[1:3]) / 2 if ap[0] in ("R", "O") else min(ap[2], ap[3]) / 2
            if mode in (2, 3) and re.search(r"[IJ]", st):
                px, py = x0, y0
                for qx, qy in arc(x0, y0, x, y, st):
                    shapes.append(("seg", px, py, qx, qy, r))
                    px, py = qx, qy
            else:
                shapes.append(("seg", x0, y0, x, y, r))
    return {"shapes": shapes, "boundary": boundary, "polys": polys, "unread": sorted(unread)}


def parse_npth(text):
    """[(x_mm, y_mm, diameter_mm)] of the hits of one Excellon file as Altium writes it: `INCH,LZ` or `METRIC,TZ`, `;FILE_FORMAT=2:4`,
    tools `T01F00S00C0.0120`, coordinates without a decimal point (zero suppression and format applied), a lone Y after an X (modal).
    A route (M15..M16) or a slot (G85) is not a hole here."""
    metric, tools, cur, out = False, {}, None, []
    zmode, total, decd = "", None, None
    x = y = None
    routing = False
    for raw in text.splitlines():
        line = raw.strip()
        mf = re.match(r";\s*FILE_FORMAT\s*=\s*(\d+):(\d+)", line, re.I)
        if mf:
            total, decd = int(mf.group(1)) + int(mf.group(2)), int(mf.group(2))
            continue
        if line.startswith(";"):
            continue
        if line.startswith(("METRIC", "INCH", "M71", "M72")):
            metric = line.startswith(("METRIC", "M71"))
            zmode = "T" if "TZ" in line else "L" if "LZ" in line else zmode
            continue
        if line.startswith("M15"):
            routing = True
            continue
        if line.startswith("M16") or line.startswith("M17"):
            routing = False
            continue
        m = re.match(r"T(\d+)[A-Z\d.]*?C(\d*\.?\d+)", line)
        if m:
            tools[int(m.group(1))] = float(m.group(2)) * (1.0 if metric else 25.4)
            cur = int(m.group(1))
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        mx, my = re.search(r"X([-+]?[\d.]+)", line), re.search(r"Y([-+]?[\d.]+)", line)
        if (mx or my) and not routing and "G85" not in line and not line.startswith(("G00", "G01", "G02", "G03", "M")):
            def v(s):
                neg = s.startswith("-")
                s = s.lstrip("+-")
                if "." in s:
                    f = float(s)
                else:
                    n, dd = (total, decd) if total else ((6, 3) if metric else (6, 4))
                    s2 = s.ljust(n, "0") if zmode == "L" else s.rjust(n, "0") if zmode == "T" else s
                    f = int(s2) / (10 ** dd)
                return (-f if neg else f) * (1.0 if metric else 25.4)
            if mx:
                x = v(mx.group(1))
            if my:
                y = v(my.group(1))
            if x is not None and y is not None and cur in tools:
                out.append((x, y, tools[cur]))
    return out


def _seg_pt(x1, y1, x2, y2, px, py):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    qx, qy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - qx, py - qy), (qx, qy)


def _rect_pt(r, px, py):
    qx, qy = max(r[1], min(r[3], px)), max(r[2], min(r[4], py))
    return math.hypot(px - qx, py - qy), (qx, qy)


def _bbox(s):
    if s[0] == "rect":
        return s[1], s[2], s[3], s[4]
    r = s[5]
    return min(s[1], s[3]) - r, min(s[2], s[4]) - r, max(s[1], s[3]) + r, max(s[2], s[4]) + r


def _cross(s, t):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    a, b, c, d = (s[1], s[2]), (s[3], s[4]), (t[1], t[2]), (t[3], t[4])
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


def gap(a, b):
    """Edge to edge distance of two shapes (0 when they touch or overlap) and the point on `a` nearest to `b`."""
    if a[0] == "rect" and b[0] == "rect":
        dx = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
        dy = max(0.0, max(a[2], b[2]) - min(a[4], b[4]))
        return math.hypot(dx, dy), ((a[1] + a[3]) / 2, (a[2] + a[4]) / 2)
    if a[0] == "seg" and b[0] == "seg":
        if _cross(a, b):
            return 0.0, ((a[1] + a[3]) / 2, (a[2] + a[4]) / 2)
        cands = []
        for (px, py) in ((a[1], a[2]), (a[3], a[4])):
            d, _ = _seg_pt(b[1], b[2], b[3], b[4], px, py)
            cands.append((d, (px, py)))
        for (px, py) in ((b[1], b[2]), (b[3], b[4])):
            d, q = _seg_pt(a[1], a[2], a[3], a[4], px, py)
            cands.append((d, q))
        dmin = min(c[0] for c in cands)
        near = [c[1] for c in cands if c[0] <= dmin + 1e-6]
        pt = (sum(p[0] for p in near) / len(near), sum(p[1] for p in near) / len(near))
        return max(0.0, dmin - a[5] - b[5]), pt
    r, s = (a, b) if a[0] == "rect" else (b, a)
    cands = [_rect_pt(r, s[1], s[2]), _rect_pt(r, s[3], s[4])]
    for cx, cy in ((r[1], r[2]), (r[3], r[2]), (r[3], r[4]), (r[1], r[4])):
        cands.append((_seg_pt(s[1], s[2], s[3], s[4], cx, cy)[0], (cx, cy)))
    d = min(c[0] for c in cands)
    pt = min(cands, key=lambda c: c[0])[1]
    d = max(0.0, d - s[5])
    return d, (pt if a is s else pt)


def _grid(shapes, cell=2.0):
    g = {}
    for i, s in enumerate(shapes):
        x0, y0, x1, y1 = _bbox(s)
        for gx in range(int(x0 // cell) - 1, int(x1 // cell) + 2):
            for gy in range(int(y0 // cell) - 1, int(y1 // cell) + 2):
                g.setdefault((gx, gy), []).append(i)
    return g


def mask_webs(shapes, limit=MASK_WEB_MIN_MM):
    """[(gap_mm, (x, y))]: pairs of mask openings with a dam between them thinner than the limit (touching ones are one opening)."""
    out, seen = [], set()
    g = _grid(shapes, 1.0)
    for cell, idx in g.items():
        for i in idx:
            for j in idx:
                if i < j and (i, j) not in seen:
                    seen.add((i, j))
                    d, _ = gap(shapes[i], shapes[j])
                    if 1e-6 < d < limit:
                        a, b = _bbox(shapes[i]), _bbox(shapes[j])
                        out.append((d, ((max(a[0], b[0]) + min(a[2], b[2])) / 2 if a[2] < b[0] or b[2] < a[0] else (a[0] + a[2] + b[0] + b[2]) / 4,
                                        (a[1] + a[3] + b[1] + b[3]) / 4)))
    return out


def _inside(poly, px, py):
    n, c = len(poly), False
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            c = not c
    return c


def copper_to_holes(copper, holes, polys=(), limit=NPTH_TO_COPPER_MM):
    """[(gap_mm, (x, y), (hx, hy, dia))]: copper nearer than the limit to the wall of a non-plated hole; (x, y) is the copper's nearest point.
    `copper`: flashes and strokes of one layer; `polys`: its regions [(dark, points)] (a pour is a dark region with clear ones cut out).
    A flash centred on the hole AND of the hole's own size (within a tenth of a mm or a tenth of its diameter) is the hole's own mark in the copper
    file (Altium writes one at the hole size): not a neighbour. A larger or smaller flash on the hole is copper at the hole and is a finding."""
    out = []
    for hx, hy, dia in holes:
        r = dia / 2
        for s in copper:
            x0, y0, x1, y1 = _bbox(s)
            if x0 - limit - r > hx or x1 + limit + r < hx or y0 - limit - r > hy or y1 + limit + r < hy:
                continue
            if (math.hypot((x0 + x1) / 2 - hx, (y0 + y1) / 2 - hy) < 0.1 and s[1] == s[3] and (s[0] == "rect" or s[2] == s[4])
                    and max(abs((x1 - x0) - dia), abs((y1 - y0) - dia)) <= max(0.1, dia / 10)):
                continue
            d, p = (_rect_pt(s, hx, hy) if s[0] == "rect" else _seg_pt(s[1], s[2], s[3], s[4], hx, hy))
            d = d - (s[5] if s[0] == "seg" else 0.0) - r
            if d < limit:
                out.append((max(d, 0.0), p, (hx, hy, dia)))
        if polys:
            covered = False
            for dark, pts in polys:                       # in file order, a later region over an earlier one wins
                if _inside(pts, hx, hy):
                    covered = dark
            best = (0.0, (hx, hy)) if covered else None
            for dark, pts in polys:
                if best and covered:
                    break
                bx0, bx1 = min(q[0] for q in pts), max(q[0] for q in pts)
                by0, by1 = min(q[1] for q in pts), max(q[1] for q in pts)
                if bx0 - limit - r > hx or bx1 + limit + r < hx or by0 - limit - r > hy or by1 + limit + r < hy:
                    continue
                for a, b in zip(pts, pts[1:] + pts[:1]):
                    d, p = _seg_pt(a[0], a[1], b[0], b[1], hx, hy)
                    d -= r
                    if d < limit and (best is None or d < best[0]):
                        best = (max(d, 0.0), p)
            if best:
                out.append((best[0], best[1], (hx, hy, dia)))
    return out


def copper_to_edge(copper, outline, limit=EDGE_TO_COPPER_MM):
    """[(gap_mm, (x, y))]: copper nearer than the limit to the centre line of the outline layer (the routed edge)."""
    out = []
    edges = [s for s in outline if s[0] == "seg" and (s[1], s[2]) != (s[3], s[4])]
    if not edges:
        return out
    g = _grid(edges, 2.0)
    for s in copper:
        x0, y0, x1, y1 = _bbox(s)
        idx = set()
        for gx in range(int(x0 // 2.0) - 1, int(x1 // 2.0) + 2):
            for gy in range(int(y0 // 2.0) - 1, int(y1 // 2.0) + 2):
                idx.update(g.get((gx, gy), ()))
        best = None
        for i in idx:
            e = (edges[i][0], edges[i][1], edges[i][2], edges[i][3], edges[i][4], 0.0)
            d, p = gap(s, e) if s[0] == "seg" else gap(s, e)
            if d < limit and (best is None or d < best[0]):
                best = (d, p)
        if best:
            out.append(best)
    return out


def _dedupe(rows, tol=0.3):
    """One row per place: rows closer than tol (one track drawn as many pieces) are one finding; the smallest gap stays."""
    kept = []
    for r in sorted(rows, key=lambda r: r[0]):
        if all(math.hypot(r[1][0] - k[1][0], r[1][1] - k[1][1]) > tol for k in kept):
            kept.append(r)
    return kept


def problems(files):
    """files: {"mask": [text], "copper": [text], "outline": [text], "npth": [text]} -> (messages, skipped).
    Each file is read on its own (a top and a bottom layer never meet). A message names the kind, the gap and the position;
    `skipped` says what could not be checked, so no file ever turns out green by being unreadable."""
    msgs, skipped = [], []

    def parsed(group):
        out = []
        for t in files.get(group, []):
            p = parse_layer(t)
            if p is None:
                skipped.append(f"a {group} file is not RS-274X: not checked")
                continue
            skipped.extend(f"{group}: {u}; shapes using it are not checked" for u in p["unread"])
            if not p["shapes"] and not p["polys"]:
                skipped.append(f"a {group} file has no readable shape: not checked")
                continue
            out.append(p)
        return out

    def emit(label, rows, fmt):
        rows = _dedupe(rows)
        for r in rows[:MAX_REPORT]:
            msgs.append(fmt(r))
        if len(rows) > MAX_REPORT:
            msgs.append(f"{label}: {len(rows) - MAX_REPORT} more places of the same kind, not listed")

    webs = []
    for p in parsed("mask"):
        webs += mask_webs(p["shapes"])
        if p["polys"]:
            skipped.append("mask: a region opening is not checked for webs")
    if files.get("mask"):
        emit("solder mask web", webs, lambda r: (
            f"solder mask web of {r[0]:.3f} mm between two openings at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm is below the "
            f"{MASK_WEB_MIN_MM:.2f} mm minimum for 1 oz copper, green mask ({MASK_WEB_BLACK_WHITE:.2f} mm for black or white): the dam is "
            f"not made; widen the gap or merge the openings"))
    cu = parsed("copper")
    holes = [h for t in files.get("npth", []) for h in parse_npth(t)]
    if files.get("npth") and not holes:
        skipped.append("an NPTH drill file lists no hole that could be read: copper to NPTH not checked")
    near = []
    for p in cu:
        near += copper_to_holes(p["shapes"], holes, p["polys"]) if holes else []
    if cu and holes:
        emit("copper to NPTH", near, lambda r: (
            f"copper is {r[0]:.2f} mm from a non-plated hole ({r[2][2]:g} mm) at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm, "
            f"less than the {NPTH_TO_COPPER_MM:.2f} mm minimum NPTH to copper clearance"))
    ol = [s for p in parsed("outline") for s in p["shapes"]]
    if cu and ol:
        edge = []
        for p in cu:
            edge += copper_to_edge(p["shapes"] + p["boundary"], ol)
        emit("copper to edge", edge, lambda r: (
            f"copper is {r[0]:.2f} mm from the routed board edge at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm, "
            f"less than the {EDGE_TO_COPPER_MM:.2f} mm minimum copper to edge clearance"))
    return msgs, sorted(set(skipped))
