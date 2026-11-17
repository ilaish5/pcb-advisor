"""USB data pair (D+/D-) support for the router: detection and coupled routing (pure Python, used by route.plan_routes).

What it does and does not claim
  * The two nets are routed COUPLED: P is routed by the router's A*, N is its parallel offset at a constant gap on the side of the N
    pads (a centre line plus offset, not a second search: a second A* has no notion of "parallel" on a grid and ends up wandering;
    an offset is parallel by construction, and its result is then checked by exact geometry, so a pair that does not fit is refused,
    never drawn wrong). Pad ends are joined by short straight stubs. An offset that reverses or crosses itself is refused.
  * It does NOT claim 90 ohm. USB 2.0 full speed (12 Mbit/s) on short traces does not need controlled impedance; what matters is
    coupling, equal length and short routing. zdiff_ipc2141() gives an estimate by the IPC-2141 edge-coupled microstrip formula for
    information only (valid roughly 0.1 < w/h < 2.0; accuracy about +-20 %); on a 2 layer 1.6 mm board 90 ohm would need
    traces of several mm, so the pair is reported as "coupled, not impedance-controlled".
  * Length match: the mismatch is reported in mm; TOLERANCE_MM (0.15) is a common layout guideline, not a number of the USB spec.
  * No via in the pair itself: a pair whose P route needs a via is not routed coupled (it falls back to normal routing and says so).
  * A USB-C style connector has D+ and D- on two pads each (A6/B6, A7/B7, interleaved). Same-net pads of one part within 3 mm are
    one group: the pair runs from the two nearest pads, the other pad of each net is tied to its mate under the connector (one net
    by a short top track over the pad row, the other by two vias and a bottom bridge, or both by vias). Tie vias are reported
    separately ("connector tie"), not as pair vias. A third part on a net (an inline ESD part) is a reported fallback.

  find_pairs(doc_or_nets)      [(p_net, n_net, kind)]
  zdiff_ipc2141(w, s, h, t, er)
  pre_route(rt, rules, nets, deadline, doc)    routes the coupled pairs first; returns the state for report()
  release(state, hit, msgs, key)               a repair that has to move a pair net releases the pair (reported, never silent)
  report(rt, rules, state, items)              the "pairs" list of the plan_routes result, measured on the final items
"""
import itertools
import math
import re

TOLERANCE_MM = 0.15          # length mismatch guideline (not a spec number)
MIN_WIDTH = 0.2              # preferred track width of the pair (mm) when the rules allow it
MARGINS = (0.0, 0.1, 0.25, 0.4)
TIE_MARGINS = (0.0, 0.1)
SHORT_END = 0.6              # a first/last segment shorter than this (the hook from a grid cell to the pad centre) is merged into its neighbour
TRIMS = tuple(round(0.1 * k, 1) for k in range(0, 26))    # how far from each pad end N may leave its parallel offset line
MAX_TRIES = 80
COUPLED_SHARE = 0.7          # share of N's length that must run at the gap beside P to call the pair coupled
GROUP_MM = 3.0               # same-net pads of one part this close are one end of the pair (USB-C A6/B6)
MAX_TIE_COMBOS = 6
CHOICE_RATIO = 1.5        # a pad pair at an end is a choice for the pair when it is at most this much farther apart than the nearest pair
MAX_CHOICES = 4
_PRE = r"(?P<pre>|[A-Z0-9_.\-]*?USB[A-Z0-9_.\-]*?)"
_SUFFIX = [("D+", "D-"), ("DP", "DM"), ("DP", "DN"), ("DPLUS", "DMINUS")]
_PINROLE = re.compile(r"USB[A-Z0-9_.\-]*?D(?P<r>[PMN+\-])(?![A-Z0-9])")
_PINKEYS = ("pin_name", "pin", "func", "function", "label", "signal", "name")


def _norm(n):
    return str(n).strip().upper()


def _nets_of(x):
    if isinstance(x, dict):
        return sorted({p["net"] for p in x.get("pads", []) if p.get("net")})
    return sorted({n for n in x if n})


def find_pairs(x):
    """USB data pairs of a doc (read_pcbdoc dict, also looks at the pin names of its pads) or of an iterable of net names:
    [(p_net, n_net, "usb")]. Net names D+/D-, DP/DM, DP/DN, USB_DP/USB_DN, USB_D+/USB_D-, USBDP/USBDM, USB_OTG_FS_DP/DM,
    USB_OTG_HS_DP/DM; a pin named like that (e.g. PA12 "USB_DP" / PA11 "USB_DM", also "USB_OTG_FS_DP") counts too when it is
    unambiguous. D+ alone or DP with no DM is not a pair."""
    nets = _nets_of(x)
    by = {_norm(n): n for n in nets}
    out, seen = [], set()
    for up, n in by.items():
        for sp, sn in _SUFFIX:
            m = re.match("^" + _PRE + re.escape(sp) + "$", up)
            if m and (m.group("pre") + sn) in by:
                key = (n, by[m.group("pre") + sn])
                if key not in seen:
                    seen.add(key)
                    out.append(key + ("usb",))
    if isinstance(x, dict):                                     # by pin name: nets of any name
        roles = {"P": set(), "N": set()}
        for p in x.get("pads", []):
            if not p.get("net"):
                continue
            for k in _PINKEYS:
                m = _PINROLE.search(_norm(p.get(k) or ""))
                if m:
                    roles["P" if m.group("r") in "P+" else "N"].add(p["net"])
                    break
        if len(roles["P"]) == 1 and len(roles["N"]) == 1:
            pn, nn = next(iter(roles["P"])), next(iter(roles["N"]))
            if pn != nn and not any(pn in (a, b) or nn in (a, b) for a, b, _ in out):
                out.append((pn, nn, "usb"))
    return sorted(out)


def zdiff_ipc2141(w, s, h=1.6, t=0.035, er=4.5):
    """Differential impedance estimate (ohm) by IPC-2141 edge-coupled microstrip: Z0 = 87/sqrt(er+1.41) ln(5.98 h/(0.8 w + t)),
    Zdiff = 2 Z0 (1 - 0.48 exp(-0.96 s/h)). Information only: rough (+-20 %), meant for 0.1 < w/h < 2.0."""
    z0 = 87.0 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h))


# ---- geometry
def _tracks(items, net, ties=False):
    return [i for i in items if i["kind"] == "track" and i["net"] == net and (ties or i.get("role") != "tie")]


def _length(items, net):
    return sum(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in _tracks(items, net))


def _chain(tracks, start):
    """The track segments as one polyline [(x, y)] from the end nearest `start`; None if they are not a single open chain."""
    segs = [((round(t["x1"], 3), round(t["y1"], 3)), (round(t["x2"], 3), round(t["y2"], 3))) for t in tracks]
    segs = [s for s in segs if s[0] != s[1]]
    if not segs:
        return None
    deg = {}
    for a, b in segs:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    ends = [p for p, d in deg.items() if d == 1]
    if len(ends) != 2 or any(d > 2 for d in deg.values()):
        return None
    cur = min(ends, key=lambda p: math.hypot(p[0] - start[0], p[1] - start[1]))
    pts, left = [cur], list(segs)
    while left:
        for k, (a, b) in enumerate(left):
            if cur in (a, b):
                cur = b if cur == a else a
                pts.append(cur)
                left.pop(k)
                break
        else:
            return None
    return pts


def _offset(pts, d):
    """The polyline moved by d to its left (negative: right), mitred at the corners. None for a turn of about 180 degrees (no
    mitre exists)."""
    nrm = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-9:
            return None
        nrm.append((-(b[1] - a[1]) / L, (b[0] - a[0]) / L))
    out = [(pts[0][0] + d * nrm[0][0], pts[0][1] + d * nrm[0][1])]
    for k in range(1, len(pts) - 1):
        n1, n2 = nrm[k - 1], nrm[k]
        den = 1 + n1[0] * n2[0] + n1[1] * n2[1]
        if den < 1e-3:
            return None
        f = d / den
        out.append((pts[k][0] + f * (n1[0] + n2[0]), pts[k][1] + f * (n1[1] + n2[1])))
    out.append((pts[-1][0] + d * nrm[-1][0], pts[-1][1] + d * nrm[-1][1]))
    return out


def _offset_ok(pts, off):
    """False when an offset segment runs against its P segment (a short inner segment is eaten by the offset and turns around) or
    when the offset crosses itself (a bow tie): the length and the gap would be wrong and the same-net copper check does not see it."""
    if off is None or len(off) != len(pts):
        return False
    for a, b, c, d in zip(pts, pts[1:], off, off[1:]):
        if (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1]) <= 1e-9:
            return False
    return not _self_crossing(off)


def _self_crossing(line):
    segs = list(zip(line, line[1:]))
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            a, b = segs[i]
            c, d = segs[j]
            if j == i + 1:                                     # neighbours may share their joint, but not fold back on each other
                v1, v2 = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
                l1, l2 = math.hypot(*v1), math.hypot(*v2)
                if l1 > 1e-9 and l2 > 1e-9 and (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2) < -0.99:
                    return True
                continue
            if _seg_dist(a, b, c, d) < 1e-6:
                return True
    return False


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _seg_dist(a, b, c, d):
    if _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d):
        return 0.0
    return min(_pt_seg(a[0], a[1], c[0], c[1], d[0], d[1]), _pt_seg(b[0], b[1], c[0], c[1], d[0], d[1]),
               _pt_seg(c[0], c[1], a[0], a[1], b[0], b[1]), _pt_seg(d[0], d[1], a[0], a[1], b[0], b[1]))


def _side(a, b, q):
    """+1 when q is left of the direction a->b, -1 right, 0 on the line."""
    cross = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])
    return 0 if abs(cross) < 1e-6 else (1 if cross > 0 else -1)


def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _coupling(items, p, n, dist):
    """Share (0..1) of N's length whose centre line lies at `dist` (+-0.02 mm) from P's centre line, on the same layer."""
    tp, tn = _tracks(items, p), _tracks(items, n)
    tot = ok = 0.0
    for t in tn:
        L = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
        k = max(1, int(L / 0.05))
        for i in range(k):
            f = (i + 0.5) / k
            x, y = t["x1"] + (t["x2"] - t["x1"]) * f, t["y1"] + (t["y2"] - t["y1"]) * f
            near = min((_pt_seg(x, y, u["x1"], u["y1"], u["x2"], u["y2"]) for u in tp if u["layer"] == t["layer"]), default=1e9)
            tot += L / k
            if abs(near - dist) <= 0.02:
                ok += L / k
    return ok / tot if tot else 0.0


def _cells(rt, items):
    """Grid cells (layer index, cell) of track items and the cells of via items, so that the grid keeps other nets away."""
    cells, vias = [], []
    for t in items:
        if t["kind"] == "via":
            vias.append(rt.idx(*rt.cell_of(t["x"], t["y"])))
            continue
        lidx = 0 if t["layer"] == 1 else 1
        k = max(1, int(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) / (rt.g / 2)))
        for j in range(k + 1):
            cells.append((lidx, rt.idx(*rt.cell_of(t["x1"] + (t["x2"] - t["x1"]) * j / k, t["y1"] + (t["y2"] - t["y1"]) * j / k))))
    return cells, vias


# ---- the two ends of a pair (a connector with two pads per net has a group at one end)
def _ref(pad):
    return str(pad["tag"]).rsplit("-", 1)[0]


def _clusters(pads):
    out = []
    for pd in pads:
        near = [c for c in out if any(_ref(q) == _ref(pd) and math.hypot(q["x"] - pd["x"], q["y"] - pd["y"]) <= GROUP_MM for q in c)]
        merged = [pd]
        for c in near:
            merged += c
            out.remove(c)
        out.append(merged)
    return out


def _centroid(pads):
    return sum(q["x"] for q in pads) / len(pads), sum(q["y"] for q in pads) / len(pads)


def _ends(rt, p, n):
    """([end, end], None) where end = {"P": [pads], "N": [pads]}, or (None, reason)."""
    cp, cn = _clusters(rt.pads[p]), _clusters(rt.pads[n])
    if len(cp) > 2 or len(cn) > 2:
        return None, "ESD part in the pair (a third part is on the net; a series or ESD part is not routed as a coupled pair)"
    if len(cp) != 2 or len(cn) != 2:
        return None, "both ends of a net are within %g mm (one part): nothing to couple" % GROUP_MM

    def dd(a, b):
        (ax, ay), (bx, by) = _centroid(a), _centroid(b)
        return math.hypot(ax - bx, ay - by)
    if dd(cp[0], cn[0]) + dd(cp[1], cn[1]) <= dd(cp[0], cn[1]) + dd(cp[1], cn[0]):
        pairs = [(cp[0], cn[0]), (cp[1], cn[1])]
    else:
        pairs = [(cp[0], cn[1]), (cp[1], cn[0])]
    return [{"P": a, "N": b} for a, b in pairs], None


def _choices(end):
    """The (P pad, N pad, ties [(net key, tie pad, kept pad)]) the pair can run from at an end, nearest first: with the two pads of
    each net interleaved at a connector either pad of a net can be the one the pair leaves from, and which of them lets the pair
    leave without crossing depends on the other end. [] if more than one extra pad per net."""
    if len(end["P"]) > 2 or len(end["N"]) > 2:
        return []
    d = lambda ab: math.hypot(ab[0]["x"] - ab[1]["x"], ab[0]["y"] - ab[1]["y"])
    combos = sorted(((a, b) for a in end["P"] for b in end["N"]), key=lambda ab: (round(d(ab), 3), ab[0]["tag"], ab[1]["tag"]))
    out = []
    for cP, cN in combos:
        if d((cP, cN)) > CHOICE_RATIO * d(combos[0]) + 1e-6 or len(out) >= MAX_CHOICES:
            break
        out.append((cP, cN, [(k, next(q for q in end[k] if q is not c), c) for k, c in (("P", cP), ("N", cN)) if len(end[k]) == 2]))
    return out


def _choose(end):
    """The nearest P and N pad of an end (the pair runs from these) and the ties [(net key, tie pad, kept pad)]; None if more than
    one extra pad per net."""
    c = _choices(end)
    return c[0] if c else None


# ---- connector ties
def _ext(pad, v):
    r = pad["rect"]
    return abs(v[0]) * (r[2] - r[0]) / 2 + abs(v[1]) * (r[3] - r[1]) / 2


def _tie_item(kind, net, w, layer, pts=None, via=None, rules=None):
    if kind in ("v", "via"):
        return {"kind": "via", "x": round(via[0], 4), "y": round(via[1], 4), "dia": rules["via_dia"], "hole": rules["via_hole"], "net": net,
                "role": "tie"}
    return {"kind": "track", "layer": layer, "x1": round(pts[0][0], 4), "y1": round(pts[0][1], 4), "x2": round(pts[1][0], 4),
            "y2": round(pts[1][1], 4), "width": w, "net": net, "role": "tie"}


def _tie_options(rules, w, net, t, c, row, side_order, kinds, avoid=None):
    """Candidate ties (a list of items) of pad t to pad c of one net, over/under the pads `row` between them: "top" = one top track
    over the pad row, "via" = a via beside each pad and a bottom bridge."""
    ax, ay = c["x"] - t["x"], c["y"] - t["y"]
    L = math.hypot(ax, ay)
    if L < 1e-6:
        return
    ax, ay = ax / L, ay / L
    v = (-ay, ax)
    lead = max(_ext(q, v) for q in row)
    clr = rules["clearance"]
    layer = 1
    for kind in kinds:
        for s in side_order:
            sv = (s * v[0], s * v[1])
            if kind == "top":
                for e in (0.1, 0.3, 0.6):
                    d = lead + clr + w / 2 + e
                    a = (t["x"] + sv[0] * d, t["y"] + sv[1] * d)
                    b = (c["x"] + sv[0] * d, c["y"] + sv[1] * d)
                    yield [_tie_item("t", net, w, layer, ((t["x"], t["y"]), a)), _tie_item("t", net, w, layer, (a, b)),
                           _tie_item("t", net, w, layer, (b, (c["x"], c["y"])))]
            else:
                cand = []
                for e in (0.15, 0.4, 0.8):
                    d = lead + clr + rules["via_dia"] / 2 + e
                    for dxt, dxc in itertools.product((0.0, 0.3, -0.3), repeat=2):
                        a = (t["x"] + sv[0] * d + ax * dxt, t["y"] + sv[1] * d + ay * dxt)
                        b = (c["x"] + sv[0] * d + ax * dxc, c["y"] + sv[1] * d + ay * dxc)
                        far = min(math.hypot(q[0] - avoid[0], q[1] - avoid[1]) for q in (a, b)) if avoid else 0.0
                        cand.append((round(-far / 0.25), e, a, b))
                cand.sort(key=lambda z: z[:2])             # the vias as far as possible from the other net's pad (where the pair leaves)
                for _k, _e, a, b in cand:
                    if True:
                        yield [_tie_item("t", net, w, layer, ((t["x"], t["y"]), a)), _tie_item("t", net, w, layer, ((c["x"], c["y"]), b)),
                               _tie_item("v", net, w, layer, via=a, rules=rules), _tie_item("v", net, w, layer, via=b, rules=rules),
                               _tie_item("t", net, w, 32, (a, b))]


def _tie_combos(rt, R, rules, p, n, w, end, other_c, choice=None, via_first=False):
    """[{net: tie items}] for one end of the pair that has an extra pad: the first clean ties for the nets, best kinds first. [] when
    nothing fits. choice: the (P pad, N pad, ties) the pair leaves from (the nearest pair by default)."""
    cP, cN, ties = choice or _choose(end)
    row = end["P"] + end["N"]
    ax = _centroid(row)
    away = (ax[0] - other_c[0], ax[1] - other_c[1])
    names = {"P": p, "N": n}

    def clean(extra):
        mine = [i for r in rt.routed.values() for i in r["items"]] + extra
        return not [1 for m, nn in R._violations(rt.shapes, mine, rules, rt.box, nets={p, n}) if p in nn or n in nn]

    def sides(t, c):
        ex, ey = c["x"] - t["x"], c["y"] - t["y"]
        L = math.hypot(ex, ey) or 1.0
        v = (-ey / L, ex / L)
        return (1, -1) if (v[0] * away[0] + v[1] * away[1]) >= 0 else (-1, 1)      # the side away from the other end of the pair first

    def first(key, t, c, kinds, base):
        avoid = (cN if key == "P" else cP)
        for opt in _tie_options(rules, w, names[key], t, c, row, sides(t, c), kinds, (avoid["x"], avoid["y"])):
            if clean(base + opt):
                return opt
        return None

    out = []
    if len(ties) == 1:
        k, t, c = ties[0]
        for kinds in (("top", "via"),):
            o = first(k, t, c, kinds, [])
            if o:
                out.append({names[k]: o})
        return out
    (k1, t1, c1), (k2, t2, c2) = ties
    for (ka, ta, ca), (kb, tb, cb) in (((k1, t1, c1), (k2, t2, c2)), ((k2, t2, c2), (k1, t1, c1))):
        for kinds_a, kinds_b in (((("via",), ("via",)), (("top",), ("via",))) if via_first else ((("top",), ("via",)), (("via",), ("via",)))):
            oa = first(ka, ta, ca, kinds_a, [])
            if not oa:
                continue
            ob = first(kb, tb, cb, kinds_b, oa)
            if ob and {names[ka]: oa, names[kb]: ob} not in out:
                out.append({names[ka]: oa, names[kb]: ob})
    return out[:MAX_TIE_COMBOS]


# ---- routing
def _widths(rules, p, n):
    w = max(rules["width"], rules.get("width_min") or 0, MIN_WIDTH)
    w = min(w, rules["width_max"])
    for net in (p, n):
        if net in rules.get("net_width", {}):
            w = max(w, rules["net_width"][net])
    gap = max(rules["clearance"], w)
    return w, gap


def _try_pair(rt, R, rules, p, n, w, gap, margin, deadline, ties=None, pads=None):
    """One attempt: None when P and N are committed, else the reason (rt is as it was before). ties: {net: [tie items]} of the
    connector; pads: {net: [the two pads to route between]} when a net has more pads than the pair runs between."""
    saved = {p: rt.pads[p], n: rt.pads[n]}
    try:
        if pads:
            rt.pads[p], rt.pads[n] = pads[p], pads[n]
        return _attempt(rt, R, rules, p, n, w, gap, margin, deadline, ties or {})
    finally:
        rt.pads.update(saved)


def _attempt(rt, R, rules, p, n, w, gap, margin, deadline, ties):
    def undo(reason):
        rt.routed.pop(p, None)
        rt.routed.pop(n, None)
        rt.rebuild()
        return reason
    tie_cells = {}
    for net in (p, n):
        if net in ties:
            c, v = _cells(rt, ties[net])
            tie_cells[net] = (c, v)
            rt.routed[net] = {"cells": list(c), "vias": list(v), "items": list(ties[net]), "width": w}
    if tie_cells:
        rt.rebuild()                                           # the ties are on the grid before P is routed: nothing crosses them
    paths, stubs, why = rt.route_net(p, w, deadline=deadline, margin=margin)
    if paths is None:
        return undo(f"{p}: {why}")
    rt.commit(p, paths, stubs, w)
    items = rt.routed[p]["items"]
    if any(i["kind"] == "via" for i in items):
        return undo(f"{p} needs a via on this board (the pair is not routed through vias)")
    pa, pb = rt.pads[p][0], rt.pads[p][1]
    ns = rt.pads[n]

    def dd(a, b):
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"])
    if dd(pa, ns[0]) + dd(pb, ns[1]) > dd(pa, ns[1]) + dd(pb, ns[0]):
        ns = [ns[1], ns[0]]
    pts = _chain(_tracks(items, p), (pa["x"], pa["y"]))
    if not pts or len(pts) < 2:
        return undo("the route of " + p + " has an unexpected shape")
    ends = [(pa["x"], pa["y"]), (pb["x"], pb["y"])]
    if math.hypot(pts[0][0] - ends[0][0], pts[0][1] - ends[0][1]) > math.hypot(pts[0][0] - ends[1][0], pts[0][1] - ends[1][1]):
        ends.reverse()
    layer = _tracks(items, p)[0]["layer"]
    lidx = 0 if layer == 1 else 1
    new = []
    for e, at in ((ends[0], pts[0]), (ends[1], pts[-1])):      # P runs to the pad centres, as N does: equal reference for the lengths
        if math.hypot(e[0] - at[0], e[1] - at[1]) > 0.002:
            new.append({"kind": "track", "layer": layer, "x1": round(e[0], 4), "y1": round(e[1], 4), "x2": at[0], "y2": at[1], "width": w,
                        "net": p})
    items += new
    c_new, _ = _cells(rt, new)
    rt.routed[p]["cells"] += c_new                             # the pad stubs are on the grid too
    pts = _chain(_tracks(items, p), ends[0])
    if not pts or len(pts) < 2:
        return undo("the route of " + p + " has an unexpected shape")
    simp = list(pts) if not _offset_ok(pts, _offset(pts, w + gap)) or not _offset_ok(pts, _offset(pts, -(w + gap))) else pts
    for end in ((0, 1) if simp is not pts else ()):            # only when an offset would turn back: the short hook between the pad centre and the first grid cell is not a corner
        q = simp if end == 0 else simp[::-1]
        while len(q) > 2 and math.hypot(q[1][0] - q[0][0], q[1][1] - q[0][1]) < SHORT_END:
            q = [q[0]] + q[2:]
        simp = q if end == 0 else q[::-1]
    if len(simp) != len(pts):
        pts = simp
        items[:] = [i for i in items if i["kind"] != "track"] + [
            {"kind": "track", "layer": layer, "x1": round(a[0], 4), "y1": round(a[1], 4), "x2": round(b[0], 4), "y2": round(b[1], 4),
             "width": w, "net": p} for a, b in zip(pts, pts[1:])]
        rt.routed[p]["cells"] += _cells(rt, items)[0]
    s1 = _side(pts[0], pts[1], (ns[0]["x"], ns[0]["y"]))
    s2 = _side(pts[-2], pts[-1], (ns[1]["x"], ns[1]["y"]))
    if s1 == 0 or s1 != s2:
        return undo(f"the pads of {n} are not on one side of {p} (a crossing would be needed)")
    off = _offset(pts, s1 * (w + gap))
    if not _offset_ok(pts, off):
        return undo(f"the offset of {p} turns back or crosses itself on an inner corner (a segment is shorter than the gap allows)")
    lp = _length(items, p)
    cands = []                            # near the pads the pair cannot keep the gap: N leaves its offset line early, at each end by its own amount
    for ta in TRIMS:
        for tb in TRIMS:
            poly = _cut(off, ta, tb)
            if poly is not None:
                line = [(ns[0]["x"], ns[0]["y"])] + poly + [(ns[1]["x"], ns[1]["y"])]
                if _self_crossing(line):
                    continue
                mm = abs(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:])) - lp)
                cands.append((mm > TOLERANCE_MM * 0.8, ta + tb if mm <= TOLERANCE_MM * 0.8 else mm, ta, tb, line))
    cands.sort(key=lambda c: c[:4])
    # P with its ties, as it will be committed
    if p in ties:
        rt.routed[p]["items"] = items + list(ties[p])
        rt.routed[p]["cells"] += tie_cells[p][0]
        rt.routed[p]["vias"] += tie_cells[p][1]
    bad = None
    for _, _, ta, tb, line in cands[:MAX_TRIES]:
        nitems = []
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            if math.hypot(x2 - x1, y2 - y1) > 0.002:
                nitems.append({"kind": "track", "layer": layer, "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4),
                               "y2": round(y2, 4), "width": w, "net": n})
        cells, _v = _cells(rt, nitems)
        tn = list(ties.get(n, []))
        tc, tv = tie_cells.get(n, ([], []))
        rt.routed[n] = {"cells": cells + list(tc), "vias": list(tv), "items": nitems + tn, "width": w}
        mine = [i for r in rt.routed.values() for i in r["items"]]
        bad = [m for m, nn in R._violations(rt.shapes, mine, rules, rt.box, nets={p, n}) if p in nn or n in nn]
        if not bad:
            rt._stamp_net(p)
            rt._stamp_net(n)
            return None
    return undo("the offset track does not fit: " + (bad[0] if bad else "the pair is too short"))


def _cut(poly, t0, t1):
    """The polyline without its first t0 mm and its last t1 mm (None if nothing is left)."""
    out = list(poly)
    for end, t in ((0, t0), (1, t1)):
        pts = out if end == 0 else out[::-1]
        left = t
        while len(pts) >= 2 and left > 0:
            a, b = pts[0], pts[1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L > left + 1e-9:
                f = left / L
                pts = [(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)] + pts[1:]
                break
            left -= L
            pts = pts[1:]
        if len(pts) < 2:
            return None
        out = pts if end == 0 else pts[::-1]
    return out


def pre_route(rt, rules, nets, deadline=None, doc=None):
    """Find the USB pairs among `nets` (the routable nets; `doc` gives the pin names of the pads) and route each coupled, before the
    other nets. Returns {"pairs": [{"p","n","kind","w","gap","ok","reason","tie_vias"}], "done": {nets routed coupled}}."""
    from . import route as R
    src = (doc or {}).get("pads") or []
    pads = [p for p in src if p.get("net") in nets]
    if not pads:
        pads = [dict(p, net=net) for net, ps in rt.pads.items() if net in nets for p in ps]
    state = {"pairs": [], "done": set()}
    for p, n, kind in find_pairs({"pads": pads}):
        w, gap = _widths(rules, p, n)
        ent = {"p": p, "n": n, "kind": kind, "w": w, "gap": gap, "ok": False, "reason": None, "tie_vias": 0}
        state["pairs"].append(ent)
        ends, why = _ends(rt, p, n)
        if ends is None:
            ent["reason"] = why
            continue
        opts = [_choices(e) for e in ends]
        if any(not o for o in opts):
            ent["reason"] = "more than 2 pads of one net at one end of the pair"
            continue
        reasons = []
        for ch in itertools.product(*opts):
            use = {p: [ch[0][0], ch[1][0]], n: [ch[0][1], ch[1][1]]}
            need = [i for i in (0, 1) if ch[i][2]]
            for w_ in dict.fromkeys((w, min(w, max(rules["width"], rules.get("width_min") or 0)))):    # the preferred width, then the rule's own
                g_ = max(rules["clearance"], w_)
                per_end = []
                for i in need:
                    o = ends[1 - i]
                    combos = _tie_combos(rt, R, rules, p, n, w_, ends[i], _centroid(o["P"] + o["N"]), ch[i])
                    if not combos:
                        per_end = None
                        reasons.append("connector tie does not fit (the pads of one net at the connector cannot be joined under it)")
                        break
                    per_end.append(combos[:3])
                if per_end is None:
                    continue
                tries = [dict()] if not need else [{k: v for d in combo for k, v in d.items()} for combo in itertools.product(*per_end)]
                for ties in tries[:MAX_TIE_COMBOS]:
                    for m in (MARGINS if not ties else TIE_MARGINS):
                        r = _try_pair(rt, R, rules, p, n, w_, g_, m, deadline, ties or None, use)
                        if r is None:
                            ent.update(ok=True, w=w_, gap=g_, tie_vias=sum(1 for t in ties.values() for i in t if i["kind"] == "via"))
                            state["done"] |= {p, n}
                            break
                        if r not in reasons:
                            reasons.append(r)
                    if ent["ok"]:
                        break
                if ent["ok"]:
                    break
            if ent["ok"]:
                break
        if not ent["ok"]:
            ent["reason"] = reasons[-1] if reasons else "no way"
    return state


def fallback_ties(rt, rules, state):
    """The pairs that are not routed coupled (never were, or were released) are routed as ordinary nets: the pads of one net at the
    connector (a pad of the other net sits between them) are joined first by a tie under the connector, as the coupled route would
    have, so that the net is never left unrouted between its own two connector pads. Nets that have a tie already are left alone.
    Nothing is added where no tie fits: the router then reports that net."""
    from . import route as R
    for e in state["pairs"]:
        if e["ok"]:
            continue
        p, n = e["p"], e["n"]
        ends, _why = _ends(rt, p, n)
        if ends is None:
            continue
        for i, end in enumerate(ends):
            ch = _choices(end)
            if not ch or not ch[0][2]:
                continue
            for c in ch:
                if any((p if k == "P" else n) in rt.tie for k, _t, _c in c[2]):
                    break
                o = ends[1 - i]
                combos = _tie_combos(rt, R, rules, p, n, e["w"], end, _centroid(o["P"] + o["N"]), c, via_first=True)
                if not combos:
                    continue
                tags = {(p if k == "P" else n): (t["tag"], kept["tag"]) for k, t, kept in c[2]}
                for net, items in combos[0].items():
                    rt.add_tie(net, items, tags[net])
                break


def release(state, hit, msgs, key=None):
    """The nets in `hit` (found too close by the exact check) are about to be ripped up and routed one by one: a coupled pair among
    them is released, with the reason, and its mate joins them. Returns the nets to add to `hit`."""
    more = set()
    for e in state["pairs"]:
        if e["ok"] and (e["p"] in hit or e["n"] in hit):
            e["ok"] = False
            e["reason"] = "coupling lost: " + (msgs.get(e["p"]) or msgs.get(e["n"]) or "the exact check moved a track of the pair")
            state["done"] -= {e["p"], e["n"]}
            more |= {e["p"], e["n"]}
    return sorted(more - set(hit), key=key) if key else sorted(more - set(hit))


def report(rt, rules, state, items):
    """The "pairs" list, measured on the final items (what was routed, not what was intended)."""
    out = []
    h = rules.get("board_thickness_mm") or 1.6
    for e in state["pairs"]:
        p, n = e["p"], e["n"]
        lp, ln = _length(items, p), _length(items, n)
        tp = _tracks(items, p)
        w = max((t["width"] for t in tp), default=e["w"])
        vias = [i for i in items if i["kind"] == "via" and i["net"] in (p, n) and i.get("role") != "tie"]
        tie_vias = [i for i in items if i["kind"] == "via" and i["net"] in (p, n) and i.get("role") == "tie"]
        coupled, gap, reason = False, None, e["reason"]
        if not tp or not _tracks(items, n):
            reason = reason or "a net of the pair was not routed"
        elif e["ok"]:
            share = _coupling(items, p, n, e["w"] + e["gap"])
            if share >= COUPLED_SHARE and not vias:
                coupled, gap = True, round(e["gap"], 4)
            else:
                reason = "the pair keeps its gap on only %.0f %% of its length (a track of it was moved by another net, or the pads are too far apart)" % (100 * share)
        mm = round(abs(lp - ln), 3)
        if coupled:
            note = "coupled, not impedance-controlled"
            if 0.1 < w / h < 2.0:
                note += (f" (IPC-2141 estimate {zdiff_ipc2141(w, e['gap'], h):.0f} ohm, assuming {h:g} mm FR-4, er 4.5; valid for 0.1 < w/h < 2; "
                         f"rough +-20 %, information only)")
            else:
                note += f" (IPC-2141 estimate not valid here: w/h = {w / h:.2f} is outside 0.1..2)"
            if mm > TOLERANCE_MM:
                note += f"; length mismatch {mm:g} mm is above the {TOLERANCE_MM:g} mm guideline"
            if tie_vias:
                note += f"; connector tie: {len(tie_vias)} via(s), not in the pair"
        else:
            note = "not routed as a coupled pair: " + (reason or "no way")
            if vias:
                note += f" (via(s) on {', '.join(sorted({v['net'] for v in vias}))})"
        out.append({"nets": [p, n], "kind": e["kind"], "coupled": coupled, "length_p": round(lp, 3), "length_n": round(ln, 3),
                    "mismatch_mm": mm, "mismatch_ok": mm <= TOLERANCE_MM, "gap_mm": gap, "width_mm": w,
                    "tie_vias": len(tie_vias) if coupled else 0, "note": note})
    return out
