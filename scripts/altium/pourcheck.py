"""Check the ground pour after routing: poured copper pieces cut off from every pad (islands), and pads of the pour net the pour
does not reach. Works on the dict read_pcbdoc returns (regions, pads, vias, tracks).

Approximated: a pad is its bounding rectangle (rotation by quarter turns only, a round or rounded pad counts as its full square);
a via is a circle; a track is a segment (its width widens the contact tolerance); arcs of the pour outline are the vertices Altium
saved (already a polygon); holes inside a poured piece are not read, so a pad inside such a hole would count as touched. Poured
pieces carry no net in the file, so every polygon piece on the checked layer is taken to belong to the pour net. Pads on a copper layer with no
pour of the net are not required to touch the pour (only the pour layer and through-hole pads are)."""
import math

BOTTOM = 32
MULTILAYER = 74
_EPS = 0.01          # mm, contact tolerance (coordinates are rounded to 0.1 um)


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


def _seg_rect(a, b, rect):
    """Segment a-b touches the axis rectangle (x0, y0, x1, y1)."""
    for p in (a, b):
        if rect[0] <= p[0] <= rect[2] and rect[1] <= p[1] <= rect[3]:
            return True
    c = [(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])]
    return any(_seg_inter(a, b, c[k], c[(k + 1) % 4]) for k in range(4))


def _poly_hits_rect(poly, pbox, rect):
    if pbox[0] > rect[2] or pbox[2] < rect[0] or pbox[1] > rect[3] or pbox[3] < rect[1]:
        return False
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    corners = [(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3])]
    if _in_poly(cx, cy, poly) or any(_in_poly(x, y, poly) for x, y in corners):
        return True
    if any(rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3] for x, y in poly):
        return True
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for k in range(4):
            if _seg_inter(a, b, corners[k], corners[(k + 1) % 4]):
                return True
    return False


def _poly_hits_seg(poly, pbox, a, b, r):
    if (max(a[0], b[0]) + r < pbox[0] or min(a[0], b[0]) - r > pbox[2]
            or max(a[1], b[1]) + r < pbox[1] or min(a[1], b[1]) - r > pbox[3]):
        return False
    if _in_poly(a[0], a[1], poly) or _in_poly(b[0], b[1], poly):
        return True
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        if _seg_inter(a, b, p, q) or _pt_seg(p, a, b) <= r:
            return True
    return False


def _pad_rect(p):
    sx, sy = p.get("sx_mm") or 0.0, p.get("sy_mm") or 0.0
    if round((p.get("rot") or 0) / 90.0) % 2 == 1:
        sx, sy = sy, sx
    hx, hy = max(sx, 0.05) / 2 + _EPS, max(sy, 0.05) / 2 + _EPS
    return p["x_mm"] - hx, p["y_mm"] - hy, p["x_mm"] + hx, p["y_mm"] + hy


def _seg(t):
    return (t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"])


def check(doc, net=None, layer=None):
    """Check the pour of `net` (default: the ground net with the most pads, at least 3, as route.pour_net_for) on `layer` (default:
    every copper layer that holds pieces of that net's polygons) in `doc`, the dict read_pcbdoc returns (call it after reading the saved board back). Returns
    {"islands": [{"layer", "bbox_mm", "points"}], "unjoined_pads": [{"ref", "name", "x_mm", "y_mm"}], "ok", "checked", "note"}.
    ok is True only when checked is True and nothing is reported."""
    def out(checked, note, islands=(), unjoined=()):
        return {"islands": list(islands), "unjoined_pads": list(unjoined), "checked": checked, "note": note,
                "ok": bool(checked and not islands and not unjoined)}
    try:
        return _check(doc, net, layer, out)
    except Exception as e:  # geometry comes from a binary file: never claim ok on a surprise
        return out(False, f"The pour could not be checked ({type(e).__name__}: {e}).")


def _touch(a, b):
    """Do two net nodes (kind, data, on_layer, rect) touch? Pad to pad is not a join: only drawn copper joins them."""
    ka, da, _, ra = a
    kb, db, _, rb = b
    if ka == "track" and kb == "track":
        if da["layer"] != db["layer"]:
            return False
        (a1, a2), (b1, b2) = _seg(da), _seg(db)
        r = (da["width_mm"] + db["width_mm"]) / 2 + _EPS
        return _seg_inter(a1, a2, b1, b2) or min(_pt_seg(a1, b1, b2), _pt_seg(a2, b1, b2),
                                                 _pt_seg(b1, a1, a2), _pt_seg(b2, a1, a2)) <= r
    if kb == "track":
        ka, da, ra, kb, db, rb = kb, db, rb, ka, da, ra
    if ka == "track":
        s1, s2 = _seg(da)
        r = da["width_mm"] / 2 + _EPS
        if kb == "pad":
            if db["layer"] not in (da["layer"], MULTILAYER) and not (db.get("hole_mm") or 0) > 0:
                return False
            return _seg_rect(s1, s2, (rb[0] - r, rb[1] - r, rb[2] + r, rb[3] + r))
        return _pt_seg((db["x_mm"], db["y_mm"]), s1, s2) <= db["dia_mm"] / 2 + r
    if ka == "via" and kb == "via":
        return math.hypot(da["x_mm"] - db["x_mm"], da["y_mm"] - db["y_mm"]) <= (da["dia_mm"] + db["dia_mm"]) / 2 + _EPS
    if ka == "via" or kb == "via":
        v, rr = (da, rb) if ka == "via" else (db, ra)
        cx = min(max(v["x_mm"], rr[0]), rr[2])
        cy = min(max(v["y_mm"], rr[1]), rr[3])
        return math.hypot(v["x_mm"] - cx, v["y_mm"] - cy) <= v["dia_mm"] / 2 + _EPS
    return False


def _check(doc, net, layer, out):
    if not isinstance(doc, dict) or "regions" not in doc or "pads" not in doc:
        return out(False, "The board file holds no readable copper regions, so the pour was not checked.")
    net = net or _default_net(doc)
    if not net:
        return out(False, "No ground net with at least 3 pads, so there is no pour to check.")
    pieces = []
    for r in doc["regions"]:
        if (layer is not None and r.get("layer") != layer) or not r.get("polygon") or r.get("in_component") or r.get("kind", 0) != 0:
            continue
        owner = r.get("polygon_net") or r.get("net")     # the polygon's net (Polygons6); poured pieces carry none themselves
        if owner not in (None, net):
            continue
        pts = [tuple(p) for p in r.get("points_mm") or []]
        if len(pts) >= 3:
            pieces.append({"poly": pts, "box": _bbox(pts), "layer": r.get("layer")})
    if not pieces:
        return out(False, "No poured copper of this net could be read (the polygon may be unfilled or stored in a form this "
                          "reader does not decode), so the pour was not checked.")

    pour_layers = {pc["layer"] for pc in pieces}
    nodes = []   # (kind, data, on pour layer, pad rectangle)
    for p in doc["pads"]:
        if p.get("net") == net and p.get("x_mm") is not None:
            on_layer = p.get("layer") in pour_layers or p.get("layer") == MULTILAYER or (p.get("hole_mm") or 0) > 0
            nodes.append(("pad", p, on_layer, _pad_rect(p)))
    for v in doc.get("vias", []):
        if v.get("net") == net:
            nodes.append(("via", v, True, None))
    for t in doc.get("tracks", []):
        if t.get("net") == net and not t.get("in_component"):
            nodes.append(("track", t, False, None))
    n = len(nodes)
    parent = list(range(n + len(pieces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _touch(nodes[i], nodes[j]):
                parent[find(i)] = find(j)
    for k, pc in enumerate(pieces):
        for i, (kind, d, on_layer, rect) in enumerate(nodes):
            if kind == "pad":
                tht = d.get("layer") == MULTILAYER or (d.get("hole_mm") or 0) > 0
                hit = (tht or d.get("layer") == pc["layer"]) and _poly_hits_rect(pc["poly"], pc["box"], rect)
            elif kind == "via":
                r = d["dia_mm"] / 2 + _EPS
                hit = _poly_hits_rect(pc["poly"], pc["box"], (d["x_mm"] - r, d["y_mm"] - r, d["x_mm"] + r, d["y_mm"] + r))
            elif d["layer"] == pc["layer"]:
                s1, s2 = _seg(d)
                hit = _poly_hits_seg(pc["poly"], pc["box"], s1, s2, d["width_mm"] / 2 + _EPS)
            else:
                hit = False
            if hit:
                parent[find(i)] = find(n + k)

    members, pieces_in = {}, {}
    for i, nd in enumerate(nodes):
        members.setdefault(find(i), []).append(nd[0])
    for k in range(len(pieces)):
        pieces_in.setdefault(find(n + k), []).append(k)
    islands = []
    for root, ks in pieces_in.items():
        if not any(m in ("pad", "via") for m in members.get(root, [])):
            for k in ks:
                islands.append({"layer": pieces[k]["layer"], "bbox_mm": [round(v, 3) for v in pieces[k]["box"]],
                                "points": len(pieces[k]["poly"])})
    unjoined = []
    for i, (kind, d, on_layer, rect) in enumerate(nodes):
        if kind != "pad" or not on_layer:
            continue
        root = find(i)
        if root in pieces_in or sum(1 for m in members[root] if m in ("pad", "via")) > 1:
            continue          # reached by the pour, or tied by tracks to the rest of the net
        unjoined.append({"ref": d.get("ref"), "name": d.get("name"), "x_mm": d["x_mm"], "y_mm": d["y_mm"]})
    if islands or unjoined:
        note = f"{len(islands)} cut-off copper piece(s) and {len(unjoined)} pad(s) of {net} not reached by the pour or a track."
    else:
        note = f"The {net} pour touches every pad that needs it and has no cut-off piece."
    return out(True, note, islands, unjoined)
