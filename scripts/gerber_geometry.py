"""Pre-order geometry checks on the produced Gerber / Excellon files (R2, ACCEPTANCE W37).

Three checks, each against a limit cited from shared/reference/jlc/pcb-capabilities.en.md:
  - solder mask web: two mask openings of one layer closer than 0.10 mm (a dam thinner than that is not made)
  - copper to a non-plated hole: copper closer than 0.20 mm to the wall of an NPTH
  - copper to the routed edge: copper closer than 0.20 mm to the board outline (centre line of the outline layer)
Every finding names the position (mm, in the coordinates of the Gerber files) so the student can find it in Altium.
What the check cannot read (an aperture macro, a block aperture, a file over the size limit) is returned in `skipped`, never as green."""
import math
import re

MASK_WEB_MIN_MM = 0.10
NPTH_TO_COPPER_MM = 0.20
EDGE_TO_COPPER_MM = 0.20
MAX_REPORT = 6                      # per kind; the rest is counted


def parse_layer(text):
    """{"shapes": [shape], "unread": [why]} of one RS-274X file. shape = ("seg", x1, y1, x2, y2, r) or ("rect", x0, y0, x1, y1).
    Dark polarity only; a region (G36..G37) is taken as its boundary line."""
    fs = re.search(r"%FS([LT])A?X(\d)(\d)Y(\d)(\d)\*%", text)
    mo = re.search(r"%MO(IN|MM)\*%", text)
    if not fs or not mo:
        return None
    zero, dec = fs.group(1), int(fs.group(3))
    digits = int(fs.group(2)) + dec
    unit = 25.4 if mo.group(1) == "IN" else 1.0
    aps, unread = {}, []
    for m in re.finditer(r"%ADD(\d+)([A-Za-z_][\w.]*),?([^*%]*)\*%", text):
        kind, args = m.group(2), [float(a) * unit for a in re.findall(r"[-+]?\d*\.?\d+", m.group(3).replace("X", " "))]
        if kind in ("C", "R", "O") and args:
            aps[m.group(1)] = (kind, args)
        else:
            unread.append(f"aperture D{m.group(1)} ({kind}) is a macro or block")
    clear = False
    body = re.sub(r"%LP([DC])\*%", lambda m: "\n#LP" + m.group(1) + "\n", text)
    body = re.sub(r"%(?!#)[^%]*%", "", body)
    body = re.sub(r"G04[^*]*\*", "", body)

    def num(s):
        sign = -1 if s.startswith("-") else 1
        d = s.lstrip("+-")
        if zero == "T":
            d = d.ljust(digits, "0")
        return sign * int(d or "0") / (10 ** dec) * unit

    x = y = 0.0
    cur, mode, shapes, region = None, 1, [], False
    for st in re.split(r"\*|\n", body):
        st = st.strip()
        if st.startswith("#LP"):
            clear = st.endswith("C")
            continue
        if not st:
            continue
        if "G36" in st:
            region = True
        if "G37" in st:
            region = False
        for g, v in (("G01", 1), ("G02", 2), ("G03", 3)):
            if g in st:
                mode = v
        md = re.search(r"D(\d+)$", st)
        mx, my = re.search(r"X([-+]?\d+)", st), re.search(r"Y([-+]?\d+)", st)
        if md and int(md.group(1)) >= 10 and not (mx or my):
            cur = md.group(1)
            continue
        if not (mx or my):
            continue
        x0, y0 = x, y
        if mx:
            x = num(mx.group(1))
        if my:
            y = num(my.group(1))
        op = md.group(1) if md else "01"
        ap = aps.get(cur)
        if clear:
            continue
        if op in ("03", "3") and ap:
            kind, a = ap
            if kind == "C":
                shapes.append(("seg", x, y, x, y, a[0] / 2))
            elif kind == "R" and len(a) >= 2:
                shapes.append(("rect", x - a[0] / 2, y - a[1] / 2, x + a[0] / 2, y + a[1] / 2))
            elif kind == "O" and len(a) >= 2:
                w, h = a[0], a[1]
                if w >= h:
                    shapes.append(("seg", x - (w - h) / 2, y, x + (w - h) / 2, y, h / 2))
                else:
                    shapes.append(("seg", x, y - (h - w) / 2, x, y + (h - w) / 2, w / 2))
        elif op in ("01", "1") and (region or ap):
            r = 0.0 if region else (ap[1][0] / 2 if ap[0] in ("C",) else min(ap[1][:2]) / 2)
            mi, mj = re.search(r"I([-+]?\d+)", st), re.search(r"J([-+]?\d+)", st)
            if mode in (2, 3) and (mi or mj):
                cx = x0 + (num(mi.group(1)) if mi else 0.0)
                cy = y0 + (num(mj.group(1)) if mj else 0.0)
                rad = math.hypot(x0 - cx, y0 - cy)
                a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y - cy, x - cx)
                if mode == 3:
                    while a1 <= a0:
                        a1 += 2 * math.pi
                else:
                    while a1 >= a0:
                        a1 -= 2 * math.pi
                sweep = a1 - a0
                px, py = x0, y0
                for k in range(1, 25):
                    a = a0 + sweep * k / 24
                    qx, qy = cx + rad * math.cos(a), cy + rad * math.sin(a)
                    shapes.append(("seg", px, py, qx, qy, r))
                    px, py = qx, qy
            else:
                shapes.append(("seg", x0, y0, x, y, r))
    return {"shapes": shapes, "unread": sorted(set(unread))}


def parse_npth(text):
    """[(x_mm, y_mm, diameter_mm)] of the hits of one non-plated Excellon file (routs and slots are not holes here)."""
    metric, tools, cur, out = False, {}, None, []
    lead_trail = "L"
    x = y = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("METRIC", "M71")):
            metric = True
            lead_trail = "T" if "TZ" in line else "L"
        elif line.startswith(("INCH", "M72")):
            metric = False
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
        if (mx or my) and cur in tools and not line.startswith(("G00", "G01", "G02", "G03", "M")):
            def v(s):
                f = float(s)
                if "." in s:
                    return f * (1.0 if metric else 25.4)
                return f / (1000.0 if metric else 10000.0) * (1.0 if metric else 25.4)
            if mx:
                x = v(mx.group(1))
            if my:
                y = v(my.group(1))
            if x is not None and y is not None:
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


def copper_to_holes(copper, holes, limit=NPTH_TO_COPPER_MM):
    """[(gap_mm, (x, y), (hx, hy, dia))]: copper nearer than the limit to the wall of a non-plated hole; (x, y) is the copper's nearest point."""
    out = []
    for hx, hy, dia in holes:
        for s in copper:
            x0, y0, x1, y1 = _bbox(s)
            if x0 - limit - dia / 2 > hx or x1 + limit + dia / 2 < hx or y0 - limit - dia / 2 > hy or y1 + limit + dia / 2 < hy:
                continue
            d, p = (_rect_pt(s, hx, hy) if s[0] == "rect" else _seg_pt(s[1], s[2], s[3], s[4], hx, hy))
            d = d - (s[5] if s[0] == "seg" else 0.0) - dia / 2
            if d < limit:
                out.append((max(d, 0.0), p, (hx, hy, dia)))
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
    A message names the kind, the gap and the position; `skipped` says what could not be checked."""
    msgs, skipped = [], []

    def layers(group):
        shapes = []
        for t in files.get(group, []):
            p = parse_layer(t)
            if p is None:
                skipped.append(f"a {group} file is not RS-274X")
                continue
            shapes += p["shapes"]
            skipped.extend(f"{group}: {u}; shapes using it are not checked" for u in p["unread"])
        return shapes

    def emit(label, rows, fmt):
        rows = _dedupe(rows)
        for r in rows[:MAX_REPORT]:
            msgs.append(fmt(r))
        if len(rows) > MAX_REPORT:
            msgs.append(f"{label}: {len(rows) - MAX_REPORT} more places of the same kind, not listed")

    if files.get("mask"):
        mk = layers("mask")
        emit("solder mask web", mask_webs(mk), lambda r: (
            f"solder mask web of {r[0]:.3f} mm between two openings at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm is below the "
            f"{MASK_WEB_MIN_MM:.2f} mm minimum (the dam is not made; widen the gap or merge the openings)"))
    cu = layers("copper") if files.get("copper") else []
    holes = [h for t in files.get("npth", []) for h in parse_npth(t)]
    if cu and holes:
        emit("copper to NPTH", copper_to_holes(cu, holes), lambda r: (
            f"copper is {r[0]:.2f} mm from a non-plated hole ({r[2][2]:g} mm) at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm, "
            f"less than the {NPTH_TO_COPPER_MM:.2f} mm minimum NPTH to copper clearance"))
    ol = layers("outline") if files.get("outline") else []
    if cu and ol:
        emit("copper to edge", copper_to_edge(cu, ol), lambda r: (
            f"copper is {r[0]:.2f} mm from the routed board edge at X {r[1][0]:.2f} mm, Y {r[1][1]:.2f} mm, "
            f"less than the {EDGE_TO_COPPER_MM:.2f} mm minimum copper to edge clearance"))
    return msgs, sorted(set(skipped))
