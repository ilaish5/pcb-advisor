"""Check the ground pour after routing: poured copper pieces cut off from every pad (islands), and pads of the pour net the pour
does not reach. Works on the dict read_pcbdoc returns (regions, polygons, pads, vias, tracks, arcs, fills).

What counts as copper of the net: its pads, vias, tracks (also those inside footprints), arcs, fills and fixed (non-pour) regions,
and the poured pieces of its polygons. Two pieces of copper on a common layer that overlap are joined; a through-hole pad and a via
are on every layer.

Approximated: a rectangular or octagonal pad is its bounding rectangle (quarter-turn rotation only), a round pad a circle, an oval
pad a capsule; a via is a circle; a track a segment with its width; an arc a chain of 8 segments; a fill a rectangle (rotated). The
holes inside a poured piece (clearances around other nets) are respected: a shape wholly inside a hole does not touch the piece, one
partly inside does. Contact tolerance 0.01 mm. Pads on a copper layer with no pour of the net are not required to touch it."""
import math

MULTILAYER = 74
_EPS = 0.01          # mm, contact tolerance (coordinates are rounded to 0.1 um)
_ALL = None          # layers value of copper that is on every layer


def _is_gnd(name):
    n = (name or "").upper()
    return n.startswith("GND") or n.endswith("GND") or n in ("VSS", "0V")


def _default_net(doc):
    """Same choice as route.pour_net_for: the ground net with the most pads, at least 3."""
    cnt = {}
    for p in doc.get("pads", []):
        if p.get("net"):
            cnt[p["net"]] = cnt.get(p["net"], 0) + 1
    g = sorted((n for n in cnt if _is_gnd(n) and cnt[n] >= 3), key=lambda n: (-cnt[n], n))
    return g[0] if g else None


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _cross(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _seg_inter(a, b, c, d):
    return _cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _seg_seg(a, b, c, d):
    if _seg_inter(a, b, c, d):
        return 0.0
    return min(_pt_seg(a, c, d), _pt_seg(b, c, d), _pt_seg(c, a, b), _pt_seg(d, a, b))


def _seg_rect(a, b, rect):
    """Segment a-b touches the axis rectangle (x0, y0, x1, y1)."""
    for p in (a, b):
        if rect[0] <= p[0] <= rect[2] and rect[1] <= p[1] <= rect[3]:
            return True
    c = [(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])]
    return any(_seg_inter(a, b, c[k], c[(k + 1) % 4]) for k in range(4))


# A primitive is ("rect", (x0, y0, x1, y1)) or ("seg", a, b, r): a segment widened by r (a == b is a circle).

def _prim_box(pr):
    if pr[0] == "rect":
        return pr[1]
    _, a, b, r = pr
    return min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r


def _rect_corners(rect):
    return [(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])]


def _prim_touch(p, q):
    if p[0] == "rect" and q[0] == "rect":
        return not (p[1][0] > q[1][2] or p[1][2] < q[1][0] or p[1][1] > q[1][3] or p[1][3] < q[1][1])
    if p[0] == "rect":
        p, q = q, p
    if q[0] == "rect":
        _, a, b, r = p
        x0, y0, x1, y1 = q[1]
        return _seg_rect(a, b, (x0 - r, y0 - r, x1 + r, y1 + r))
    return _seg_seg(p[1], p[2], q[1], q[2]) <= p[3] + q[3]


def _poly_hits(poly, pbox, pr):
    """Does the polygon outline overlap the primitive?"""
    b = _prim_box(pr)
    if pbox[0] > b[2] or pbox[2] < b[0] or pbox[1] > b[3] or pbox[3] < b[1]:
        return False
    n = len(poly)
    if pr[0] == "rect":
        rect = pr[1]
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        corners = _rect_corners(rect)
        if _in_poly(cx, cy, poly) or any(_in_poly(x, y, poly) for x, y in corners):
            return True
        if any(rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3] for x, y in poly):
            return True
        return any(_seg_inter(poly[i], poly[(i + 1) % n], corners[k], corners[(k + 1) % 4]) for i in range(n) for k in range(4))
    _, a, c, r = pr
    if _in_poly(a[0], a[1], poly) or _in_poly(c[0], c[1], poly):
        return True
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        if _seg_seg(a, c, p, q) <= r:
            return True
    return False


def _inside_hole(hole, pr):
    """Is the primitive wholly inside the hole polygon (touching no edge of it)?"""
    n = len(hole)
    if pr[0] == "rect":
        corners = _rect_corners(pr[1])
        if not all(_in_poly(x, y, hole) for x, y in corners):
            return False
        return not any(_seg_inter(hole[i], hole[(i + 1) % n], corners[k], corners[(k + 1) % 4]) for i in range(n) for k in range(4))
    _, a, c, r = pr
    if not (_in_poly(a[0], a[1], hole) and _in_poly(c[0], c[1], hole)):
        return False
    return all(_seg_seg(a, c, hole[i], hole[(i + 1) % n]) > r for i in range(n))


def _shape_hits(shape, pr):
    """Does a copper shape (outline with holes) touch the primitive? Wholly inside a hole is no contact."""
    if not _poly_hits(shape["poly"], shape["box"], pr):
        return False
    return not any(_inside_hole(h, pr) for h in shape["holes"] if len(h) >= 3)


def _poly_overlap(p, q):
    bp, bq = _bbox(p), _bbox(q)
    if bp[0] > bq[2] or bp[2] < bq[0] or bp[1] > bq[3] or bp[3] < bq[1]:
        return False
    if _in_poly(p[0][0], p[0][1], q) or _in_poly(q[0][0], q[0][1], p):
        return True
    n, m = len(p), len(q)
    return any(_seg_inter(p[i], p[(i + 1) % n], q[j], q[(j + 1) % m]) for i in range(n) for j in range(m))


def _poly_in_hole(poly, hole):
    n = len(hole)
    return (all(_in_poly(x, y, hole) for x, y in poly)
            and not any(_seg_inter(hole[i], hole[(i + 1) % n], poly[k], poly[(k + 1) % len(poly)])
                        for i in range(n) for k in range(len(poly))))


def _shapes_touch(a, b):
    """Two copper shapes on one layer touch when their outlines overlap, unless one lies wholly in a hole of the other. Pieces of
    poured polygons never touch each other (Altium keeps them apart: what looks like overlap is one piece sitting in a hole)."""
    if a["pour"] and b["pour"]:
        return False
    if not _poly_overlap(a["poly"], b["poly"]):
        return False
    return not (any(_poly_in_hole(b["poly"], h) for h in a["holes"] if len(h) >= 3)
                or any(_poly_in_hole(a["poly"], h) for h in b["holes"] if len(h) >= 3))


def _area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _pad_prim(p):
    sx, sy = max(p.get("sx_mm") or 0.0, 0.05), max(p.get("sy_mm") or 0.0, 0.05)
    if round((p.get("rot") or 0) / 90.0) % 2 == 1:
        sx, sy = sy, sx
    x, y = p["x_mm"], p["y_mm"]
    if p.get("shape") == 1:                       # round or oval: circle or capsule along the long side
        r = min(sx, sy) / 2 + _EPS
        d = (max(sx, sy) - min(sx, sy)) / 2
        a, b = ((x - d, y), (x + d, y)) if sx >= sy else ((x, y - d), (x, y + d))
        return ("seg", a, b, r)
    return ("rect", (x - sx / 2 - _EPS, y - sy / 2 - _EPS, x + sx / 2 + _EPS, y + sy / 2 + _EPS))


def _arc_prims(a):
    r = a["r_mm"]
    a1, a2 = a["a1"], a["a2"]
    if a2 <= a1:
        a2 += 360.0
    pts = [(a["cx_mm"] + r * math.cos(math.radians(a1 + (a2 - a1) * k / 8)),
            a["cy_mm"] + r * math.sin(math.radians(a1 + (a2 - a1) * k / 8))) for k in range(9)]
    w = a["width_mm"] / 2 + _EPS
    return [("seg", pts[k], pts[k + 1], w) for k in range(8)]


def _fill_poly(f):
    x1, y1, x2, y2 = f["x1_mm"], f["y1_mm"], f["x2_mm"], f["y2_mm"]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    c, s = math.cos(math.radians(f.get("rot") or 0)), math.sin(math.radians(f.get("rot") or 0))
    return [(cx + (px - cx) * c - (py - cy) * s, cy + (px - cx) * s + (py - cy) * c)
            for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]


def _layer_name(n):
    return {1: "Top", 32: "Bottom"}.get(n, f"layer {n}")


def check(doc, net=None, layer=None):
    """Check the pour of `net` (default: the ground net with the most pads, at least 3, as route.pour_net_for) on `layer` (default:
    every copper layer that holds pieces of that net's polygons) in `doc`, the dict read_pcbdoc returns (call it after reading the
    saved board back). Returns {"islands": [{"layer", "bbox_mm", "points", "area_mm2"}], "unjoined_pads": [{"ref", "name", "x_mm",
    "y_mm"}], "ok", "checked", "note"}. ok is True only when checked is True and nothing is reported."""
    def out(checked, note, islands=(), unjoined=()):
        return {"islands": list(islands), "unjoined_pads": list(unjoined), "checked": checked, "note": note,
                "ok": bool(checked and not islands and not unjoined)}
    try:
        return _check(doc, net, layer, out)
    except Exception as e:  # geometry comes from a binary file: never claim ok on a surprise
        return out(False, f"The pour could not be checked ({type(e).__name__}: {e}).")


def _check(doc, net, layer, out):
    if not isinstance(doc, dict) or "regions" not in doc or "pads" not in doc:
        return out(False, "The board file holds no readable copper regions, so the pour was not checked.")
    net = net or _default_net(doc)
    if not net:
        return out(False, "No ground net with at least 3 pads, so there is no pour to check.")
    regions = doc["regions"]
    pieces = []
    for r in regions:
        if (layer is not None and r.get("layer") != layer) or not r.get("polygon") or r.get("in_component") or r.get("kind", 0) != 0:
            continue
        if r.get("polygon_net") != net:          # a piece whose polygon is unknown is not taken to be the pour net
            continue
        pts = [tuple(p) for p in r.get("points_mm") or []]
        if len(pts) >= 3:
            pieces.append({"poly": pts, "box": _bbox(pts), "layer": r.get("layer"), "pour": True,
                           "holes": [[tuple(p) for p in h] for h in r.get("holes") or []],
                           "remove_dead": r.get("polygon_remove_dead")})
    if not pieces:
        if any(r.get("polygon") and not r.get("polygon_net") for r in regions):
            return out(False, "The polygons of the board could not be read from the file (their nets are unknown), so the pour "
                              "was not checked.")
        return out(False, "No poured copper of this net could be read (the polygon may be unfilled or stored in a form this "
                          "reader does not decode), so the pour was not checked.")
    pour_layers = {pc["layer"] for pc in pieces}

    # shapes (outline with holes): the pieces, then the net's fixed regions and fills
    shapes = list(pieces)
    for r in regions:
        if r.get("net") == net and not r.get("polygon") and r.get("kind", 0) == 0 and 1 <= (r.get("layer") or 0) <= 32:
            pts = [tuple(p) for p in r.get("points_mm") or []]
            if len(pts) >= 3:
                shapes.append({"poly": pts, "box": _bbox(pts), "layer": r["layer"], "pour": False,
                               "holes": [[tuple(p) for p in h] for h in r.get("holes") or []]})
    for f in doc.get("fills", []):
        if f.get("net") == net and 1 <= (f.get("layer") or 0) <= 32:
            pts = _fill_poly(f)
            shapes.append({"poly": pts, "box": _bbox(pts), "layer": f["layer"], "pour": False, "holes": []})

    # nodes: (kind, data, layers (None = every layer), primitive)
    nodes = []
    for p in doc["pads"]:
        if p.get("net") == net and p.get("x_mm") is not None:
            tht = p.get("layer") == MULTILAYER or (p.get("hole_mm") or 0) > 0
            nodes.append(("pad", p, _ALL if tht else {p.get("layer")}, _pad_prim(p)))
    for v in doc.get("vias", []):
        if v.get("net") == net:
            nodes.append(("via", v, _ALL, ("seg", (v["x_mm"], v["y_mm"]), (v["x_mm"], v["y_mm"]), v["dia_mm"] / 2 + _EPS)))
    for t in doc.get("tracks", []):
        if t.get("net") == net:
            nodes.append(("track", t, {t["layer"]}, ("seg", (t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"]),
                                                     t["width_mm"] / 2 + _EPS)))
    for a in doc.get("arcs", []):
        if a.get("net") == net:
            nodes.extend(("track", a, {a["layer"]}, pr) for pr in _arc_prims(a))
    n = len(nodes)
    parent = list(range(n + len(shapes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    def same_layer(la, lb):
        return la is _ALL or lb is _ALL or bool(la & lb)

    boxes = [_prim_box(nd[3]) for nd in nodes]
    for i in range(n):
        bi = boxes[i]
        for j in range(i + 1, n):
            bj = boxes[j]
            if bi[0] > bj[2] or bi[2] < bj[0] or bi[1] > bj[3] or bi[3] < bj[1]:
                continue
            if nodes[i][0] == "pad" and nodes[j][0] == "pad":
                continue                          # pads touching each other are not joined by anything drawn
            if same_layer(nodes[i][2], nodes[j][2]) and _prim_touch(nodes[i][3], nodes[j][3]):
                union(i, j)
    for k, sh in enumerate(shapes):
        for i, nd in enumerate(nodes):
            if sh["layer"] in (nd[2] if nd[2] is not _ALL else (sh["layer"],)) and _shape_hits(sh, nd[3]):
                union(i, n + k)
        for k2 in range(k):
            if shapes[k2]["layer"] == sh["layer"] and _shapes_touch(sh, shapes[k2]):
                union(n + k, n + k2)

    members, shapes_in = {}, {}
    for i, nd in enumerate(nodes):
        members.setdefault(find(i), []).append(nd[0])
    for k, sh in enumerate(shapes):
        shapes_in.setdefault(find(n + k), []).append(k)
    islands = []
    for root, ks in shapes_in.items():
        if any(m in ("pad", "via") for m in members.get(root, [])):
            continue
        for k in ks:
            if shapes[k]["pour"]:
                sh = shapes[k]
                area = _area(sh["poly"]) - sum(_area(h) for h in sh["holes"] if len(h) >= 3)
                islands.append({"layer": sh["layer"], "bbox_mm": [round(v, 3) for v in sh["box"]], "points": len(sh["poly"]),
                                "area_mm2": round(max(area, 0.0), 3)})
    unjoined = []
    for i, (kind, d, layers, _pr) in enumerate(nodes):
        if kind != "pad" or not (layers is _ALL or layers & pour_layers):
            continue
        root = find(i)
        if root in shapes_in and any(shapes[k]["pour"] for k in shapes_in[root]):
            continue                              # reached by the pour
        if sum(1 for m in members[root] if m in ("pad", "via")) > 1:
            continue                              # tied by copper to the rest of the net
        unjoined.append({"ref": d.get("ref"), "name": d.get("name"), "x_mm": d["x_mm"], "y_mm": d["y_mm"]})
    if islands or unjoined:
        note = f"{len(islands)} cut-off copper piece(s) and {len(unjoined)} pad(s) of {net} not reached by the pour or a track."
        if islands:
            il = {i["layer"] for i in islands}
            off = sorted({f"{net}_{'Bot' if pc['layer'] == 32 else _layer_name(pc['layer'])}" for pc in pieces
                          if pc["remove_dead"] is False and pc["layer"] in il})
            if off:
                note += f" Remove Dead Copper is off in polygon {', '.join(off)}; turn it on and repour."
    else:
        note = f"The {net} pour touches every pad that needs it and has no cut-off piece."
    return out(True, note, islands, unjoined)
