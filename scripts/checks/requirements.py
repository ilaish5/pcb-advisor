"""Requirements measured on a saved board: does it really hold what the student's confirmed constraints (constraints.py) say?

Pure functions over a read_pcbdoc dict (geometry=True gives the part bodies), an outline [x0, y0, x1, y1] in mm and the confirmed
items; no Altium, no files. measure() answers with the facts the agent may state about the board and one row per constraint:

    {"id", "kind", "status": "met" | "violated" | "unverifiable", "measured": text, "need": text}

unverifiable = this board file cannot show it (the part is not on the board, a heat source is not something a file holds, ...).
Never "met" without a measurement. Rows the checker adds itself have an id that starts with "auto:" (copper under the antenna
keep-out that a module's own footprint carries).
"""
import math

KEEPOUT_LAYER = 56
COPPER_LAYERS = (1, 32)
TOL = 0.01
HOLE_POS_TOL_MM = 0.5
HOLE_DIA_TOL_MM = 0.1
EDGE_GAP_MM = 1.5


def _mech(ref):
    import constraints
    return constraints.is_mech_ref(ref)


def _gap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _rect_hit(a, b, tol=TOL):
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


def _seg_rect_hit(p, q, hw, r):
    """Segment p-q of half width hw against rect r (sampled at 0.05 mm, enough for keep-outs of mm size)."""
    n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 0.05))
    box = [r[0] + TOL, r[1] + TOL, r[2] - TOL, r[3] - TOL]
    for i in range(n + 1):
        t = i / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if box[0] < x + hw and x - hw < box[2] and box[1] < y + hw and y - hw < box[3]:
            return True
    return False


def _in_poly(pt, poly):
    x, y, inside = pt[0], pt[1], False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _segs_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _poly_rect_hit(poly, r, holes=()):
    """A poured region (outline polygon, cut-outs `holes`) has copper inside rect r: false when r lies wholly in a cut-out."""
    if len(poly) < 3:
        return False
    corners = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    for h in holes:
        if len(h) >= 3 and all(_in_poly(c, h) for c in corners):
            return False
    if any(r[0] < x < r[2] and r[1] < y < r[3] for x, y in poly):
        return True
    if any(_in_poly(c, poly) for c in corners):
        return True
    edges = list(zip(corners, corners[1:] + corners[:1]))
    return any(_segs_cross(poly[i], poly[(i + 1) % len(poly)], e0, e1) for i in range(len(poly)) for e0, e1 in edges)


def copper_in(doc, rect, ignore_refs=()):
    """What copper (not in a footprint, pads of the parts listed nowhere) lies inside `rect` on the top or bottom layer:
    ["track", "via", "pad J2-3", "pour", ...] (one entry per object)."""
    found = []
    for t in doc.get("tracks", []):
        if t.get("layer") in COPPER_LAYERS and not t.get("in_component") and \
                _seg_rect_hit((t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"]), (t.get("width_mm") or 0) / 2, rect):
            found.append("track")
    for v in doc.get("vias", []):
        r = (v.get("dia_mm") or 0) / 2
        if _rect_hit([v["x_mm"] - r, v["y_mm"] - r, v["x_mm"] + r, v["y_mm"] + r], rect):
            found.append("via")
    for f in doc.get("fills", []):
        if f.get("layer") in COPPER_LAYERS and not f.get("in_component"):
            box = [min(f["x1_mm"], f["x2_mm"]), min(f["y1_mm"], f["y2_mm"]), max(f["x1_mm"], f["x2_mm"]), max(f["y1_mm"], f["y2_mm"])]
            if _rect_hit(box, rect):
                found.append("fill")
    for g in doc.get("regions", []):
        if g.get("layer") in COPPER_LAYERS and not g.get("in_component") and g.get("kind", 0) == 0 and g.get("points_mm"):
            if g.get("polygon"):
                if _poly_rect_hit(g["points_mm"], rect, g.get("holes") or ()):
                    found.append("pour")
            elif _poly_rect_hit(g["points_mm"], rect):
                found.append("copper region")
    for p in doc.get("pads", []):
        if "x_mm" not in p or p.get("ref") in ignore_refs or _mech(p.get("ref")):
            continue
        sx, sy = p.get("sx_mm", 0) / 2, p.get("sy_mm", 0) / 2
        if _rect_hit([p["x_mm"] - sx, p["y_mm"] - sy, p["x_mm"] + sx, p["y_mm"] + sy], rect):
            found.append(f"pad {p.get('ref')}-{p.get('name')}")
    return found


def component_keepouts(doc):
    """[[x0, y0, x1, y1]] the keep-out layer objects that belong to footprints, merged where they touch (a module's antenna area:
    its region and the four edge tracks come out as one rectangle)."""
    boxes = []
    for g in doc.get("regions", []):
        if g.get("layer") == KEEPOUT_LAYER and g.get("in_component") and g.get("points_mm"):
            xs, ys = [p[0] for p in g["points_mm"]], [p[1] for p in g["points_mm"]]
            boxes.append([min(xs), min(ys), max(xs), max(ys)])
    for t in doc.get("tracks", []):
        if t.get("layer") == KEEPOUT_LAYER and t.get("in_component"):
            hw = (t.get("width_mm") or 0) / 2
            boxes.append([min(t["x1_mm"], t["x2_mm"]) - hw, min(t["y1_mm"], t["y2_mm"]) - hw,
                          max(t["x1_mm"], t["x2_mm"]) + hw, max(t["y1_mm"], t["y2_mm"]) + hw])
    merged = []
    for b in boxes:
        b = list(b)
        for m in [m for m in merged if _gap(m, b) <= 0.05]:
            merged.remove(m)
            b = [min(b[0], m[0]), min(b[1], m[1]), max(b[2], m[2]), max(b[3], m[3])]
        merged.append(b)
    return merged


def _side_gaps(box, outline):
    return {"left": box[0] - outline[0], "right": outline[2] - box[2], "bottom": box[1] - outline[1], "top": outline[3] - box[3]}


def _row(it, status, measured, need):
    return {"id": it["id"], "kind": it["kind"], "status": status, "measured": measured, "need": need}


def measure(doc, outline, items, refs=None, lines=None, size=None):
    """{"size", "on_board", "edge_parts", "holes", "keepouts", "copper_under_keepout", "requirements": [row]} of the saved board."""
    import constraints
    from altium import layout
    boxes = layout.real_boxes(doc)
    real = {r: b for r, b in boxes.items() if not _mech(r)}
    holes = [{"ref": h.get("ref"), "x": h["x_mm"], "y": h["y_mm"], "dia": h["hole_mm"]}
             for h in doc.get("drilled_pads", []) if not h.get("plated", True) and h.get("hole_mm", 0) >= 0.5]
    edge_parts = []
    if outline:
        for r, b in sorted(real.items()):
            gaps = _side_gaps(b, outline)
            side = min(gaps, key=gaps.get)
            if gaps[side] <= EDGE_GAP_MM:
                edge_parts.append({"ref": r, "side": side, "gap_mm": round(gaps[side], 2)})
    facts = {"size": [round(outline[2] - outline[0], 2), round(outline[3] - outline[1], 2)] if outline else None,
             "on_board": sorted(real), "edge_parts": edge_parts, "holes": holes}
    rows, ko_rects = [], []

    def parts(target, it):
        if refs is None:
            return [target]
        return constraints.resolve(target, refs, lines or {})

    for it in items:
        need = constraints.describe(it)
        k = it["kind"]
        if not outline:
            rows.append(_row(it, "unverifiable", "the board has no outline", need))
        elif k == "mounting_hole":
            want = constraints.corner_points(it, outline)
            bad = []
            for x, y in want:
                near = [h for h in holes if math.hypot(h["x"] - x, h["y"] - y) <= HOLE_POS_TOL_MM]
                if not near:
                    bad.append(f"no hole at ({x:.1f}, {y:.1f})")
                elif abs(near[0]["dia"] - it["diameter_mm"]) > HOLE_DIA_TOL_MM:
                    bad.append(f"the hole at ({x:.1f}, {y:.1f}) is {near[0]['dia']:g} mm")
            rows.append(_row(it, "violated" if bad else "met", "; ".join(bad) if bad else
                             f"{len(want)} of {len(want)} holes found, {it['diameter_mm']:g} mm", need))
        elif k in ("edge", "keep_apart", "attr"):
            names = [it["target"]] if k != "keep_apart" else [it["a"], it["b"]]
            got = [parts(n, it) for n in names]
            if any(not g for g in got):
                rows.append(_row(it, "unverifiable", "constraint has no part: " + ", ".join(n for n, g in zip(names, got) if not g), need))
            elif k == "attr":
                rows.append(_row(it, "unverifiable", "a board file does not show this property", need))
            elif k == "edge":
                bad, good = [], []
                for r in got[0]:
                    if r not in real:
                        bad.append(f"{r} is not on the board")
                        continue
                    gaps = _side_gaps(real[r], outline)
                    side = it["side"] if it["side"] != "any" else min(gaps, key=gaps.get)
                    (good if gaps[side] <= EDGE_GAP_MM else bad).append(f"{r} is {gaps[side]:.1f} mm from the {side} edge")
                rows.append(_row(it, "violated" if bad else "met", "; ".join(bad or good), need))
            else:
                worst, txt = None, []
                for a in got[0]:
                    for b in got[1]:
                        if a in real and b in real:
                            d = _gap(real[a], real[b])
                            txt.append(f"{a} to {b} {d:.1f} mm")
                            worst = d if worst is None else min(worst, d)
                if worst is None:
                    rows.append(_row(it, "unverifiable", "a part is not on the board", need))
                else:
                    rows.append(_row(it, "met" if worst >= it["min_mm"] - TOL else "violated", "; ".join(txt), need))
        elif k == "keepout":
            rect = constraints.keepout_rect(it, size, outline)
            if rect is None:
                rows.append(_row(it, "unverifiable", "the keep-out needs the board size", need))
                continue
            box = [outline[0] + rect[0], outline[1] + rect[1], outline[0] + rect[2], outline[1] + rect[3]]
            ko_rects.append(box)
            found = copper_in(doc, box)
            rows.append(_row(it, "violated" if found else "met", f"{len(found)} copper object(s) inside: {', '.join(sorted(set(found)))}"
                             if found else "no copper inside", need))
    keepouts, under = [], 0
    for n, box in enumerate(component_keepouts(doc), 1):
        if any(max(abs(box[i] - kb[i]) for i in range(4)) < 0.6 for kb in ko_rects):
            continue                                    # the box of a constraint's own keep-out footprint: already a row
        found = copper_in(doc, box)
        under += len(found)
        keepouts.append({"box": [round(v, 2) for v in box], "copper": len(found)})
        rows.append({"id": f"auto:keepout-{n}", "kind": "keepout", "status": "violated" if found else "met",
                     "measured": (f"{len(found)} copper object(s) inside: {', '.join(sorted(set(found)))}" if found else "no copper inside"),
                     "need": "no copper under a footprint's keep-out (an antenna area)"})
    for r in rows:
        if r["kind"] == "keepout" and not r["id"].startswith("auto:") and r["status"] == "violated":
            under += 1
    facts.update(keepouts=keepouts, copper_under_keepout=under, requirements=rows)
    return facts
