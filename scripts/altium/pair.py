"""USB data pair (D+/D-) support for the router: detection and coupled routing (pure Python, used by route.plan_routes).

What it does and does not claim
  * The two nets are routed COUPLED: P is routed by the router's A*, N is its parallel offset at a constant gap on the side of the N
    pads (a centre line plus offset, not a second search: a second A* has no notion of "parallel" on a grid and ends up wandering;
    an offset is parallel by construction, and its result is then checked by exact geometry, so a pair that does not fit is refused,
    never drawn wrong). Pad ends are joined by short straight stubs.
  * It does NOT claim 90 ohm. USB 2.0 full speed (12 Mbit/s) on short traces does not need controlled impedance; what matters is
    coupling, equal length and short routing. zdiff_ipc2141() gives an estimate by the IPC-2141 edge-coupled microstrip formula for
    information only (valid roughly 0.1 < w/h < 2.0; accuracy about +-10..20 %); on a 2 layer 1.6 mm board 90 ohm would need
    traces of several mm, so the pair is reported as "coupled, not impedance-controlled".
  * Length match: the mismatch is reported in mm; TOLERANCE_MM (0.15) is a common layout guideline, not a number of the USB spec.
  * No via: a pair whose P route needs a via is not routed coupled (it falls back to normal routing and says so).

  find_pairs(doc_or_nets)      [(p_net, n_net, kind)]
  zdiff_ipc2141(w, s, h, t, er)
  pre_route(rt, rules, nets, deadline)    routes the coupled pairs first; returns the state for report()
  report(rt, rules, state, items)         the "pairs" list of the plan_routes result, measured on the final items
"""
import math
import re

TOLERANCE_MM = 0.15          # length mismatch guideline (not a spec number)
MIN_WIDTH = 0.2              # preferred track width of the pair (mm) when the rules allow it
MARGINS = (0.0, 0.1, 0.25, 0.4)
TRIMS = tuple(round(0.1 * k, 1) for k in range(0, 26))
MAX_TRIES = 80    # how far from each pad end N may leave its parallel offset line
COUPLED_SHARE = 0.7          # share of N's length that must run at the gap beside P to call the pair coupled
_PRE = r"(?P<pre>|[A-Z0-9_.\-]*?USB[A-Z0-9]*[_.\-]?)"
_SUFFIX = [("D+", "D-"), ("DP", "DM"), ("DP", "DN"), ("DPLUS", "DMINUS")]
_PINROLE = re.compile(r"USB[A-Z0-9]*[_.\-]?D(?P<r>[PMN+\-])(?![A-Z0-9])")
_PINKEYS = ("pin_name", "pin", "func", "function", "label", "signal", "name")


def _norm(n):
    return str(n).strip().upper()


def _nets_of(x):
    if isinstance(x, dict):
        return sorted({p["net"] for p in x.get("pads", []) if p.get("net")})
    return sorted({n for n in x if n})


def find_pairs(x):
    """USB data pairs of a doc (read_pcbdoc dict, also looks at the pin names of its pads) or of an iterable of net names:
    [(p_net, n_net, "usb")]. Net names D+/D-, DP/DM, DP/DN, USB_DP/USB_DN, USB_D+/USB_D-, USBDP/USBDM; a pin named USB_DP / USB_DM
    (e.g. PA12 / PA11) also counts, when it is unambiguous. D+ alone or DP with no DM is not a pair."""
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
    if isinstance(x, dict):                                     # by pin name: PA12 "USB_DP" / PA11 "USB_DM" on nets with any name
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
    Zdiff = 2 Z0 (1 - 0.48 exp(-0.96 s/h)). Information only: rough (+-10..20 %), meant for 0.1 < w/h < 2.0."""
    z0 = 87.0 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))
    return 2 * z0 * (1 - 0.48 * math.exp(-0.96 * s / h))


# ---- geometry
def _tracks(items, net):
    return [i for i in items if i["kind"] == "track" and i["net"] == net]


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
    """The polyline moved by d to its left (negative: right), mitred at the corners."""
    nrm = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        nrm.append((-(b[1] - a[1]) / L, (b[0] - a[0]) / L))
    out = [(pts[0][0] + d * nrm[0][0], pts[0][1] + d * nrm[0][1])]
    for k in range(1, len(pts) - 1):
        n1, n2 = nrm[k - 1], nrm[k]
        f = d / (1 + n1[0] * n2[0] + n1[1] * n2[1])
        out.append((pts[k][0] + f * (n1[0] + n2[0]), pts[k][1] + f * (n1[1] + n2[1])))
    out.append((pts[-1][0] + d * nrm[-1][0], pts[-1][1] + d * nrm[-1][1]))
    return out


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


# ---- routing
def _widths(rules, p, n):
    w = max(rules["width"], rules.get("width_min") or 0, MIN_WIDTH)
    w = min(w, rules["width_max"])
    for net in (p, n):
        if net in rules.get("net_width", {}):
            w = max(w, rules["net_width"][net])
    gap = max(rules["clearance"], w)
    return w, gap


def _try_pair(rt, R, rules, p, n, w, gap, margin, deadline):
    """One attempt: None when P and N are committed, else the reason (rt is as it was before)."""
    paths, stubs, why = rt.route_net(p, w, deadline=deadline, margin=margin)
    if paths is None:
        return f"{p}: {why}"
    rt.commit(p, paths, stubs, w)

    def undo(reason):
        rt.routed.pop(p, None)
        rt.routed.pop(n, None)
        rt.rebuild()
        return reason
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
    for e, at, nxt in ((ends[0], pts[0], 0), (ends[1], pts[-1], -1)):      # P runs to the pad centres, as N does: equal reference for the lengths
        if math.hypot(e[0] - at[0], e[1] - at[1]) > 0.002:
            items.append({"kind": "track", "layer": layer, "x1": round(e[0], 4), "y1": round(e[1], 4), "x2": at[0], "y2": at[1], "width": w, "net": p})
    pts = _chain(_tracks(items, p), ends[0])
    if not pts or len(pts) < 2:
        return undo("the route of " + p + " has an unexpected shape")
    s1 = _side(pts[0], pts[1], (ns[0]["x"], ns[0]["y"]))
    s2 = _side(pts[-2], pts[-1], (ns[1]["x"], ns[1]["y"]))
    if s1 == 0 or s1 != s2:
        return undo(f"the pads of {n} are not on one side of {p} (a crossing would be needed)")
    off = _offset(pts, s1 * (w + gap))
    lidx = 0 if layer == R.LAYER_CODE[R.TOP] else 1
    bad = None
    lp = _length(items, p)
    cands = []                            # near the pads the pair cannot keep the gap: N leaves its offset line early, at each end by its own amount
    for ta in TRIMS:
        for tb in TRIMS:
            poly = _cut(off, ta, tb)
            if poly is not None:
                line = [(ns[0]["x"], ns[0]["y"])] + poly + [(ns[1]["x"], ns[1]["y"])]
                mm = abs(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line, line[1:])) - lp)
                cands.append((mm > TOLERANCE_MM * 0.8, ta + tb if mm <= TOLERANCE_MM * 0.8 else mm, ta, tb, line))
    cands.sort(key=lambda c: c[:4])
    for _, _, ta, tb, line in cands[:MAX_TRIES]:
        nitems = []
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            if math.hypot(x2 - x1, y2 - y1) > 0.002:
                nitems.append({"kind": "track", "layer": layer, "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4),
                               "y2": round(y2, 4), "width": w, "net": n})
        cells = []
        for t in nitems:                                      # its cells, so that later nets keep clear of it
            k = max(1, int(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) / (rt.g / 2)))
            for j in range(k + 1):
                cells.append((lidx, rt.idx(*rt.cell_of(t["x1"] + (t["x2"] - t["x1"]) * j / k, t["y1"] + (t["y2"] - t["y1"]) * j / k))))
        rt.routed[n] = {"cells": cells, "vias": [], "items": nitems, "width": w}
        mine = [i for r in rt.routed.values() for i in r["items"]]
        bad = [m for m, nn in R._violations(rt.shapes, mine, rules, rt.box) if p in nn or n in nn]
        if not bad:
            rt._stamp_net(n)
            return None
    rt.routed.pop(n, None)
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


def pre_route(rt, rules, nets, deadline=None):
    """Find the USB pairs among `nets` (the routable nets) and route each coupled, before the other nets. Returns
    {"pairs": [{"p","n","kind","w","gap","ok","reason"}], "done": {nets routed coupled}}."""
    from . import route as R
    doc_like = {"pads": [dict(p, net=net) for net, ps in rt.pads.items() if net in nets for p in ps]}
    state = {"pairs": [], "done": set()}
    for p, n, kind in find_pairs(doc_like):
        w, gap = _widths(rules, p, n)
        ent = {"p": p, "n": n, "kind": kind, "w": w, "gap": gap, "ok": False, "reason": None}
        state["pairs"].append(ent)
        if len(rt.pads[p]) != 2 or len(rt.pads[n]) != 2:
            ent["reason"] = "a net of the pair does not have exactly 2 pads"
            continue
        reasons = []
        for w_ in dict.fromkeys((w, min(w, max(rules["width"], rules.get("width_min") or 0)))):    # the preferred width, then the rule's own
            g_ = max(rules["clearance"], w_)
            for m in MARGINS:
                r = _try_pair(rt, R, rules, p, n, w_, g_, m, deadline)
                if r is None:
                    ent.update(ok=True, w=w_, gap=g_)
                    state["done"] |= {p, n}
                    break
                if r not in reasons:
                    reasons.append(r)
            if ent["ok"]:
                break
        if not ent["ok"]:
            ent["reason"] = reasons[-1] if reasons else "no way"
    return state


def report(rt, rules, state, items):
    """The "pairs" list, measured on the final items (what was routed, not what was intended)."""
    out = []
    for e in state["pairs"]:
        p, n = e["p"], e["n"]
        lp, ln = _length(items, p), _length(items, n)
        tp = _tracks(items, p)
        w = max((t["width"] for t in tp), default=e["w"])
        vias = [i for i in items if i["kind"] == "via" and i["net"] in (p, n)]
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
            if 0.1 < w / 1.6 < 2.0:
                note += f" (IPC-2141 estimate {zdiff_ipc2141(w, e['gap']):.0f} ohm, rough, information only)"
            if mm > TOLERANCE_MM:
                note += f"; length mismatch {mm:g} mm is above the {TOLERANCE_MM:g} mm guideline"
        else:
            note = "not routed as a coupled pair: " + (reason or "no way")
            if vias:
                note += f" (via(s) on {', '.join(sorted({v['net'] for v in vias}))})"
        out.append({"nets": [p, n], "kind": e["kind"], "coupled": coupled, "length_p": round(lp, 3), "length_n": round(ln, 3),
                    "mismatch_mm": mm, "mismatch_ok": mm <= TOLERANCE_MM, "gap_mm": gap, "width_mm": w, "note": note})
    return out
