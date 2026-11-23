"""Connector routing for the block diagram: the server-side twin of routeConnectors() in ui/diagram.js.

THE SHARED RULES (change both files together; tests/test_diagram_route.py runs the JS and compares):
  * Ports: connectors that leave/enter the same side of a rectangle block get distinct points on that side,
    t = (i+1)/(n+1) along it, ordered by the other end's centre (y for left/right sides, x for top/bottom), then id.
  * Route of an attached connector with side ends: p1 -> stub (20 out of the side) -> middle -> stub -> p2, where
    the middle is an L, or a Z whose bend lane is the mid-point, or a gutter/lane beside any block (+-24, +-40)
    or the whole drawing (+-30, +-46). Candidates are tried in a fixed order.
  * A candidate is valid when no segment enters a non-endpoint block (inflated by 10) and no middle segment
    enters its own end blocks. Cost = length + 40 per bend + 1000 per collinear overlap with an earlier
    connector's segment + 100 per near-parallel (<8) overlap. The cheapest valid candidate wins (first on ties);
    when none is valid the cheapest one is used and the route is flagged not ok.
  * Straight connectors, free ends and self-loops keep the legacy elbow (no obstacle search).
  * Labels (width max(7.5*len+16, 32), height 22) sit at 0.5/0.3/0.7 of the longest segments, first spot that
    touches no block and no earlier label.
"""

STUB = 20.0
CLEAR = 10.0
LANES = (24.0, 40.0)
GLOBAL_LANE = 30.0
BEND = 40.0
OVERLAP = 1000.0
NEAR = 100.0
LABEL_H = 22.0
SIDE_DIR = {"left": (-1.0, 0.0), "right": (1.0, 0.0), "top": (0.0, -1.0), "bottom": (0.0, 1.0)}
_ANCHOR = {"top": (0.5, 0.0), "right": (1.0, 0.5), "bottom": (0.5, 1.0), "left": (0.0, 0.5)}
_ANCHOR8 = {"top-left": (0.0, 0.0), "top-right": (1.0, 0.0), "bottom-right": (1.0, 1.0), "bottom-left": (0.0, 1.0)}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ep(ep):
    """Normalise an endpoint: the str shorthand and dict forms both give a dict."""
    return ep if isinstance(ep, dict) else {"shape": ep} if isinstance(ep, str) else {}


def _rect_type(s):
    return str(s.get("type") or "rectangle").lower() in ("rectangle", "block", "box")


def _side(ep):
    if not ep.get("shape"):
        return None
    p = ep.get("point") or ep.get("side") or "right"
    return p if p in SIDE_DIR else None


def _anchor(s, name):
    """Outline point of a rectangle-like shape; other types use the box (the check is about blocks)."""
    f = _ANCHOR.get(name) or _ANCHOR8.get(name) or _ANCHOR["right"]
    return {"x": _num(s["x"]) + f[0] * _num(s["w"]), "y": _num(s["y"]) + f[1] * _num(s["h"])}


def _centre(ep, by_id):
    s = by_id.get(ep.get("shape"))
    if s:
        return {"x": _num(s["x"]) + _num(s["w"]) / 2, "y": _num(s["y"]) + _num(s["h"]) / 2}
    return {"x": _num(ep.get("x")), "y": _num(ep.get("y"))}


def label_width(label):
    return max(len(label) * 7.5 + 16, 32)


def _ports(connectors, by_id):
    groups = {}
    order = []
    for c in connectors:
        for k, o in (("from", "to"), ("to", "from")):
            ep = _ep(c.get(k))
            side = _side(ep)
            s = by_id.get(ep.get("shape"))
            if not side or not s or not _rect_type(s):
                continue
            key = f"{ep['shape']}|{side}"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((c, k, _centre(_ep(c.get(o)), by_id), side))
    out = {}
    for key in order:
        arr = groups[key]
        n = len(arr)
        if n < 2:
            continue
        horiz = arr[0][3] in ("left", "right")
        arr.sort(key=lambda g: ((g[2]["y"] if horiz else g[2]["x"]), str(g[0].get("id"))))
        s = by_id[key.split("|")[0]]
        for i, (c, k, _o, side) in enumerate(arr):
            base = _anchor(s, side)
            if horiz:
                pt = {"x": base["x"], "y": _num(s["y"]) + _num(s["h"]) * (i + 1) / (n + 1)}
            else:
                pt = {"x": _num(s["x"]) + _num(s["w"]) * (i + 1) / (n + 1), "y": base["y"]}
            out[f"{c.get('id')}|{k}"] = pt
    return out


def _legacy(c, p1, p2):
    if c.get("route") == "straight":
        return [p1, p2]

    def d(ep):
        p = (ep.get("point") or ep.get("side")) if ep.get("shape") else None
        return "v" if p in ("top", "bottom") else "h" if p in ("left", "right") else None
    d1, d2 = d(_ep(c.get("from"))), d(_ep(c.get("to")))
    if d1 and d2 and d1 != d2:
        return [p1, {"x": p2["x"], "y": p1["y"]}, p2] if d1 == "h" else [p1, {"x": p1["x"], "y": p2["y"]}, p2]
    kind = d1 or d2 or ("h" if abs(p2["x"] - p1["x"]) >= abs(p2["y"] - p1["y"]) else "v")
    if kind == "v":
        my = (p1["y"] + p2["y"]) / 2
        return [p1, {"x": p1["x"], "y": my}, {"x": p2["x"], "y": my}, p2]
    mx = (p1["x"] + p2["x"]) / 2
    return [p1, {"x": mx, "y": p1["y"]}, {"x": mx, "y": p2["y"]}, p2]


def _simplify(pts):
    out = []
    for p in pts:
        if out and out[-1]["x"] == p["x"] and out[-1]["y"] == p["y"]:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        if (a["x"] == b["x"] == c["x"]) or (a["y"] == b["y"] == c["y"]):
            del out[i]
        else:
            i += 1
    return out


def _hits(a, b, box):
    """Axis-aligned segment a-b strictly inside the box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    if a["y"] == b["y"]:
        return y0 < a["y"] < y1 and max(a["x"], b["x"]) > x0 and min(a["x"], b["x"]) < x1
    if a["x"] == b["x"]:
        return x0 < a["x"] < x1 and max(a["y"], b["y"]) > y0 and min(a["y"], b["y"]) < y1
    return True  # a diagonal never comes out of the router; treat as a hit


def _segs(poly):
    return [(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]


def _overlap(a, b, tol):
    """Overlap length of two parallel axis segments lying within tol of each other, else 0."""
    if a[0]["y"] == a[1]["y"] and b[0]["y"] == b[1]["y"]:
        if abs(a[0]["y"] - b[0]["y"]) > tol:
            return 0.0
        lo = max(min(a[0]["x"], a[1]["x"]), min(b[0]["x"], b[1]["x"]))
        hi = min(max(a[0]["x"], a[1]["x"]), max(b[0]["x"], b[1]["x"]))
        return max(0.0, hi - lo)
    if a[0]["x"] == a[1]["x"] and b[0]["x"] == b[1]["x"]:
        if abs(a[0]["x"] - b[0]["x"]) > tol:
            return 0.0
        lo = max(min(a[0]["y"], a[1]["y"]), min(b[0]["y"], b[1]["y"]))
        hi = min(max(a[0]["y"], a[1]["y"]), max(b[0]["y"], b[1]["y"]))
        return max(0.0, hi - lo)
    return 0.0


def _uniq(vals):
    seen, out = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _length(poly):
    return sum(abs(b["x"] - a["x"]) + abs(b["y"] - a["y"]) for a, b in _segs(poly))


def _boxes(shapes):
    return [(s["id"], _num(s["x"]), _num(s["y"]), _num(s["x"]) + _num(s["w"]), _num(s["y"]) + _num(s["h"]))
            for s in shapes]


def route_connectors(shapes, connectors):
    """{connector id: {"p1", "p2", "points", "ok", "label": {"x","y","w","h","ok"} | None}} for every connector."""
    by_id = {s["id"]: s for s in shapes}
    ports = _ports(connectors, by_id)
    boxes = _boxes(shapes)
    min_x = min((b[1] for b in boxes), default=0.0)
    max_x = max((b[3] for b in boxes), default=0.0)
    min_y = min((b[2] for b in boxes), default=0.0)
    max_y = max((b[4] for b in boxes), default=0.0)
    routes, used = {}, []

    for c in connectors:
        e1, e2 = _ep(c.get("from")), _ep(c.get("to"))
        cid = c.get("id")

        def end_pt(ep, k):
            if f"{cid}|{k}" in ports:
                return ports[f"{cid}|{k}"]
            s = by_id.get(ep.get("shape"))
            if s:
                return _anchor(s, ep.get("point") or ep.get("side") or "right")
            return {"x": _num(ep.get("x")), "y": _num(ep.get("y"))}
        p1, p2 = end_pt(e1, "from"), end_pt(e2, "to")
        s1 = _side(e1) if e1.get("shape") in by_id else None
        s2 = _side(e2) if e2.get("shape") in by_id else None
        if c.get("route") == "straight" or not s1 or not s2 or e1.get("shape") == e2.get("shape"):
            poly = _legacy(c, p1, p2)
            routes[cid] = {"p1": p1, "p2": p2, "points": poly, "ok": True, "label": None}
            used.extend((cid, sg) for sg in _segs(poly))
            continue

        d1, d2 = SIDE_DIR[s1], SIDE_DIR[s2]
        a = {"x": p1["x"] + d1[0] * STUB, "y": p1["y"] + d1[1] * STUB}
        b = {"x": p2["x"] + d2[0] * STUB, "y": p2["y"] + d2[1] * STUB}
        ends = (e1["shape"], e2["shape"])
        obst = [(x0 - CLEAR, y0 - CLEAR, x1 + CLEAR, y1 + CLEAR) for (i, x0, y0, x1, y1) in boxes if i not in ends]
        own = [(x0, y0, x1, y1) for (i, x0, y0, x1, y1) in boxes if i in ends]

        xs = [(a["x"] + b["x"]) / 2, a["x"], b["x"]]
        ys = [(a["y"] + b["y"]) / 2, a["y"], b["y"]]
        for (_i, x0, y0, x1, y1) in boxes:
            for g in LANES:
                xs += [x0 - g, x1 + g]
                ys += [y0 - g, y1 + g]
        for g in (GLOBAL_LANE, GLOBAL_LANE + 16):
            xs += [min_x - g, max_x + g]
            ys += [min_y - g, max_y + g]
        mids = [[{"x": b["x"], "y": a["y"]}], [{"x": a["x"], "y": b["y"]}]]
        mids += [[{"x": mx, "y": a["y"]}, {"x": mx, "y": b["y"]}] for mx in _uniq(xs)]
        mids += [[{"x": a["x"], "y": ly}, {"x": b["x"], "y": ly}] for ly in _uniq(ys)]

        best = best_any = None
        for mid in mids:
            full = [p1, a] + mid + [b, p2]
            segs = [sg for sg in _segs(full) if not (sg[0]["x"] == sg[1]["x"] and sg[0]["y"] == sg[1]["y"])]
            valid = True
            for j, (u, v) in enumerate(segs):
                if any(_hits(u, v, o) for o in obst) or (0 < j < len(segs) - 1 and any(_hits(u, v, o) for o in own)):
                    valid = False
                    break
            poly = _simplify(full)
            cost = _length(poly) + BEND * (len(poly) - 2)
            for sg in _segs(poly):
                for (oid, os_) in used:
                    if oid == cid:
                        continue
                    if _overlap(sg, os_, 0.5) > 1:
                        cost += OVERLAP
                    elif _overlap(sg, os_, 8) > 1:
                        cost += NEAR
            if best_any is None or cost < best_any[0]:
                best_any = (cost, poly)
            if valid and (best is None or cost < best[0]):
                best = (cost, poly)
        chosen = best or best_any
        routes[cid] = {"p1": p1, "p2": p2, "points": chosen[1], "ok": best is not None, "label": None}
        used.extend((cid, sg) for sg in _segs(chosen[1]))

    rects = [(x0 - 2, y0 - 2, x1 + 2, y1 + 2) for (_i, x0, y0, x1, y1) in boxes]
    placed = []
    for c in connectors:
        r = routes[c.get("id")]
        text = c.get("label")
        if not text:
            continue
        w = label_width(text)
        segs = list(enumerate(_segs(r["points"])))
        segs.sort(key=lambda t: -(abs(t[1][1]["x"] - t[1][0]["x"]) + abs(t[1][1]["y"] - t[1][0]["y"])))
        cands = []
        for _i, (u, v) in segs:
            for f in (0.5, 0.3, 0.7):
                cands.append({"x": u["x"] + (v["x"] - u["x"]) * f, "y": u["y"] + (v["y"] - u["y"]) * f})
        pick = None
        for pt in cands:
            rc = (pt["x"] - w / 2, pt["y"] - LABEL_H / 2, pt["x"] + w / 2, pt["y"] + LABEL_H / 2)
            clash = any(rc[0] < q[2] and rc[2] > q[0] and rc[1] < q[3] and rc[3] > q[1] for q in rects + placed)
            if not clash:
                pick = (pt, rc, True)
                break
        if pick is None:
            pt = cands[0] if cands else r["p1"]
            pick = (pt, (pt["x"] - w / 2, pt["y"] - LABEL_H / 2, pt["x"] + w / 2, pt["y"] + LABEL_H / 2), False)
        placed.append(pick[1])
        r["label"] = {"x": pick[0]["x"], "y": pick[0]["y"], "w": w, "h": LABEL_H, "ok": pick[2]}
    return routes


def route_problems(shapes, connectors):
    """What is still wrong with the drawing, as short strings; [] when every link is clean.
    Re-checks the finished routes independently of how they were chosen (crossings, shared lines, labels)."""
    routes = route_connectors(shapes, connectors)
    problems = []
    boxes = _boxes(shapes)
    for c in connectors:
        r = routes[c.get("id")]
        ends = {_ep(c.get("from")).get("shape"), _ep(c.get("to")).get("shape")}
        for (i, x0, y0, x1, y1) in boxes:
            if i in ends:
                continue
            if any(_hits(u, v, (x0, y0, x1, y1)) for u, v in _segs(r["points"])):
                problems.append(f"{c.get('id')} crosses {i}")
        lab = r["label"]
        if lab and not lab["ok"]:
            problems.append(f"label of {c.get('id')} sits on a block or another label")
    cs = list(connectors)
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            for u in _segs(routes[cs[i]["id"]]["points"]):
                for v in _segs(routes[cs[j]["id"]]["points"]):
                    if _overlap(u, v, 0.5) > 1:
                        problems.append(f"{cs[i]['id']} and {cs[j]['id']} share a line")
    return problems
