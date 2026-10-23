"""A small router for the agent's `altium.route_pcb` action (pure Python: no Altium here, so it can be tested).

Altium's autorouter (Situs) cannot be run from a script (it opens its strategy dialog and waits for a click), so small two layer
boards are routed here and the result is sent to Altium as tracks and vias. It is a grid router: A* on a 0.1 mm grid with 8
directions (45 and 90 degree segments), two layers, vias with a cost, per-net track width, clearance and edge keep-off from the
board's rules, rip-up and retry when a net is blocked by nets routed before it. It never claims more than it did: every net it
could not route comes back with the reason.

What is fixed copper for it (it keeps clear of all of it, by the board's clearance): pads (also the pads of no part), copper that
belongs to a footprint (tracks, arcs, fills, regions), copper regions and fills on the board, existing tracks and vias, unplated
holes (with a hole-to-copper gap) and everything on the keep-out layer. A via is never placed in or within clearance of an SMD pad;
a through hole pad serves as the change of layer without a via.

  rules_from_doc(doc)                                  clearance, width, via and edge numbers from the PcbDoc's rules (JLC defaults)
  plan_routes(doc, box, rules, ...)                    {"items": [track/via], "routed": [net], "failed": [(net, reason)], "stats": {...}}
  route_commands(doc, items)                           the script lines for the bridge (ROUTEBEGIN, TRACK, VIA, PCBSAVE)
  violations(doc, items, rules, box)                   an independent exact check of items against the fixed copper

Units are mm, y grows upwards, layer codes are Altium's (1 top, 32 bottom, 56 keep-out, 74 multi layer).
"""
import heapq
import math
import re
import time

try:
    from .pcbdoc import _arc_extent_points
except ImportError:                                      # pragma: no cover - run outside the package
    _arc_extent_points = None

TOP, BOT = 0, 1
LAYER_CODE = {TOP: 1, BOT: 32}
KEEPOUT_LAYER = 56
SQ2 = math.sqrt(2)
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
DEFAULTS = {"clearance": 0.127, "width": 0.127, "width_min": 0.127, "width_max": 10.0, "via_dia": 0.6, "via_hole": 0.3, "edge": 0.3,
            "hole_clear": 0.25}
POWER_WIDTH = 0.3          # rail nets are routed at least this wide when the board has room and no rule says otherwise
VIA_COST = 30.0
CROSS_COST = 25.0          # relaxed search: entering a cell that holds another net's track (the nets to rip up are those crossed)
THRU_COST = 2.0            # a change of layer inside a through hole pad: no via, only the cost of leaving the layer
TURN_45, TURN_90 = 0.3, 0.7
MARGINS = (0.05, 0.1, 0.2, 0.3, 0.45, 0.6)        # extra distance asked of a net that the exact check found too close to something
_LEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(mil|mm)?\s*$", re.I)
_INNET = re.compile(r"InNet\s*\(\s*'([^']+)'\s*\)", re.I)
_RAIL = re.compile(r"^[+-]\d|^\d+V\d*$|^(?:VCC|VDD|VBUS|VBAT|VIN|VSYS|VDDA|VCCA|AVDD|DVDD)\w*$", re.I)


def _len(text):
    m = _LEN.match(str(text or ""))
    if not m:
        return None
    v = float(m.group(1))
    return v * 0.0254 if (m.group(2) or "mil").lower() == "mil" else v


def rules_from_doc(doc):
    """Routing numbers (mm) from a read_pcbdoc dict's rules: the biggest enabled Clearance gap, the Width rule on All (and per-net
    Width rules written as InNet('X')), the routing via sizes and the board-edge clearance. Missing ones: the JLC numbers."""
    out = dict(DEFAULTS, net_width={})
    clear = []
    for r in doc.get("rules", []):
        if str(r.get("ENABLED", "TRUE")).upper() != "TRUE":
            continue
        kind = r.get("RULEKIND")
        if kind == "Clearance" and _len(r.get("GAP")) is not None:
            clear.append(_len(r["GAP"]))
        elif kind == "BoardOutlineClearance" and _len(r.get("GAP")) is not None:
            out["edge"] = max(out["edge"], _len(r["GAP"]))
        elif kind == "RoutingVias":
            d, h = _len(r.get("WIDTH")), _len(r.get("HOLEWIDTH"))
            if d and h:
                out["via_dia"], out["via_hole"] = d, h
        elif kind == "Width":
            mn, mx, pf = _len(r.get("MINLIMIT")), _len(r.get("MAXLIMIT")), _len(r.get("PREFEREDWIDTH"))
            nets = _INNET.findall(r.get("SCOPE1EXPRESSION", ""))
            w = pf or mn or DEFAULTS["width"]
            if mn is not None and mx is not None:
                w = min(max(w, mn), mx)
            if nets:
                for n in nets:
                    out["net_width"][n] = w
            elif str(r.get("SCOPE1EXPRESSION", "All")).strip().lower() == "all":
                out["width"], out["width_min"], out["width_max"] = w, mn if mn is not None else w, mx if mx is not None else 10.0
    if clear:
        out["clearance"] = max(clear)
    out["edge"] = max(out["edge"], out["clearance"])
    return out


def _pad_rect(p):
    sx, sy = p.get("sx_mm", 0) or 0, p.get("sy_mm", 0) or 0
    rot = float(p.get("rot") or 0) % 180
    if abs(rot - 90) < 0.5:
        sx, sy = sy, sx
    elif min(rot, 180 - rot) > 0.5:
        sx = sy = math.hypot(sx, sy)
    return p["x_mm"] - sx / 2, p["y_mm"] - sy / 2, p["x_mm"] + sx / 2, p["y_mm"] + sy / 2


def _round_pad(p):
    """Round / oval / octagonal / rounded-rectangle pads (the corners of their bounding box are not copper); a pad of unknown shape
    counts as rectangular, as the SMD pads of a footprint are."""
    return p.get("shape") in (1, 3, 9)


def _pad_layers(p):
    return {1: (TOP,), 32: (BOT,)}.get(p.get("layer"), (TOP, BOT))


# ---- exact geometry (the router searches on a grid, the check does not)

def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _seg_seg(a, b, c, d):
    if _ccw(a, c, d) != _ccw(b, c, d) and _ccw(a, b, c) != _ccw(a, b, d):
        return 0.0
    return min(_pt_seg(a[0], a[1], c[0], c[1], d[0], d[1]), _pt_seg(b[0], b[1], c[0], c[1], d[0], d[1]),
               _pt_seg(c[0], c[1], a[0], a[1], b[0], b[1]), _pt_seg(d[0], d[1], a[0], a[1], b[0], b[1]))


def _seg_rect(a, b, r):
    """Distance from segment a-b to the rectangle r = (x0, y0, x1, y1) (0 when they touch)."""
    inside = lambda p: r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]
    if inside(a) or inside(b):
        return 0.0
    c = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    return min(_seg_seg(a, b, c[k], c[(k + 1) % 4]) for k in range(4))


def _dist(geo, a, b):
    """Distance from the segment a-b (a point when a == b) to the edge of a fixed copper shape (0 when they overlap)."""
    kind = geo[0]
    if kind == "rect":
        return _seg_rect(a, b, geo[1])
    if kind == "seg":
        return max(0.0, _seg_seg(a, b, geo[1], geo[2]) - geo[3])
    return max(0.0, _pt_seg(geo[1][0], geo[1][1], a[0], a[1], b[0], b[1]) - geo[2])          # circ


def _bbox(geo):
    kind = geo[0]
    if kind == "rect":
        return geo[1]
    if kind == "seg":
        (ax, ay), (bx, by), hw = geo[1], geo[2], geo[3]
        return min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw
    (cx, cy), r = geo[1], geo[2]
    return cx - r, cy - r, cx + r, cy + r


def _pts_rect(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _both(layer):
    return (TOP,) if layer == 1 else (BOT,) if layer == 32 else (TOP, BOT) if layer == KEEPOUT_LAYER else ()


def fixed_shapes(doc, rules):
    """Every piece of copper (and keep-out) that is on the board before routing, as
    {"kind": pad|copper|hole|keepout, "tag", "net", "layers", "geo", "smd"}; geo is ("rect", box), ("seg", a, b, half width) or
    ("circ", centre, radius). Copper of a poured polygon is not fixed (it is poured again around the tracks)."""
    out = []
    for p in doc.get("pads", []):
        if "x_mm" not in p:
            continue
        net = p.get("net")
        net = None if (not net or str(net).upper() in ("NC", "N/C")) else net
        lay = _pad_layers(p)
        out.append({"kind": "pad", "tag": f"{p.get('ref') or 'free'}-{p.get('name')}", "net": net, "layers": lay,
                    "geo": ("rect", _pad_rect(p)), "smd": len(lay) == 1, "pad": p})
    extra = max(0.0, rules.get("hole_clear", DEFAULTS["hole_clear"]) - rules["clearance"])
    for h in doc.get("drilled_pads", []):
        if not h.get("plated", True) and h.get("hole_mm", 0) > 0:
            out.append({"kind": "hole", "tag": f"hole {h.get('ref') or 'free'}-{h.get('name')}", "net": None, "layers": (TOP, BOT),
                        "geo": ("circ", (h["x_mm"], h["y_mm"]), h["hole_mm"] / 2 + extra), "smd": False})
    for t in doc.get("tracks", []):
        lay = _both(t.get("layer"))
        if lay:
            k = "keepout" if t["layer"] == KEEPOUT_LAYER else "copper"
            out.append({"kind": k, "tag": "track", "net": t.get("net") if k == "copper" else None, "layers": lay, "smd": False,
                        "geo": ("seg", (t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"]), (t.get("width_mm") or 0) / 2)})
    for a in doc.get("arcs", []):
        lay = _both(a.get("layer"))
        if lay and _arc_extent_points:
            pts = _arc_extent_points(a["cx_mm"], a["cy_mm"], a["r_mm"], a["a1"], a["a2"])
            hw = (a.get("width_mm") or 0) / 2
            x0, y0, x1, y1 = _pts_rect(pts)
            k = "keepout" if a["layer"] == KEEPOUT_LAYER else "copper"
            out.append({"kind": k, "tag": "arc", "net": a.get("net") if k == "copper" else None, "layers": lay, "smd": False,
                        "geo": ("rect", (x0 - hw, y0 - hw, x1 + hw, y1 + hw))})
    for f in doc.get("fills", []):
        lay = _both(f.get("layer"))
        if lay:
            cx, cy = (f["x1_mm"] + f["x2_mm"]) / 2, (f["y1_mm"] + f["y2_mm"]) / 2
            w, h = abs(f["x2_mm"] - f["x1_mm"]), abs(f["y2_mm"] - f["y1_mm"])
            rot = float(f.get("rot") or 0) % 180
            if abs(rot - 90) < 0.5:
                w, h = h, w
            elif min(rot, 180 - rot) > 0.5:
                w = h = math.hypot(w, h)
            k = "keepout" if f["layer"] == KEEPOUT_LAYER else "copper"
            out.append({"kind": k, "tag": "fill", "net": f.get("net") if k == "copper" else None, "layers": lay, "smd": False,
                        "geo": ("rect", (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))})
    for g in doc.get("regions", []):
        lay = _both(g.get("layer"))
        if lay and not g.get("polygon") and g.get("points_mm") and (g.get("kind", 0) == 0 or g["layer"] == KEEPOUT_LAYER):
            k = "keepout" if g["layer"] == KEEPOUT_LAYER else "copper"
            out.append({"kind": k, "tag": "region", "net": g.get("net") if k == "copper" else None, "layers": lay, "smd": False,
                        "geo": ("rect", _pts_rect(g["points_mm"]))})
    for v in doc.get("vias", []):
        out.append({"kind": "copper", "tag": "via", "net": v.get("net"), "layers": (TOP, BOT), "smd": False,
                    "geo": ("circ", (v["x_mm"], v["y_mm"]), (v.get("dia_mm") or 0) / 2)})
    return out


class Router:
    def __init__(self, doc, box, rules, pitch=0.1):
        self.g = g = pitch
        self.rules = rules
        self.x0, self.y0 = box[0], box[1]
        self.nx, self.ny = int((box[2] - box[0]) / g) + 1, int((box[3] - box[1]) / g) + 1
        self.n = self.nx * self.ny
        self.wb = rules["width"]
        self.clear = rules["clearance"]
        # The track centre sits on a grid point, an obstacle is sampled on the same grid: half a cell diagonal (0.71 g) plus what a
        # diagonal segment dips between two cells is the most the sampling can miss. Every obstacle is grown by it.
        self.q = 0.8 * g
        self.reach_q = 0.71 * g
        self.S = [[-1] * self.n, [-1] * self.n]        # fixed copper and the board edge: -1 free, net id, -2 blocks everything
        self.D = [[-1] * self.n, [-1] * self.n]        # tracks and vias routed so far
        self.netid = {}
        self.pads = {}                                  # net -> [pad dict with cells]
        self.routed = {}                                # net -> {"cells": [(l, i)], "vias": [i], "items": [...], "width": w}
        self.novia = bytearray(self.n)                  # cells where a via would sit in or too close to an SMD pad
        self.tht = {}                                   # net id -> cells of its through hole pads (a change of layer there needs no via)
        self.status = "none"                            # why the last astar() found nothing: none | limit | time
        self._offsets = {}
        self.shapes = fixed_shapes(doc, rules)
        self._edge(box)
        for s in self.shapes:
            if s["kind"] == "pad":
                self._add_pad(s["pad"], s)
            else:
                self._add_shape(s)

    # ---- grid
    def idx(self, ix, iy):
        return ix * self.ny + iy

    def xy(self, i):
        return self.x0 + (i // self.ny) * self.g, self.y0 + (i % self.ny) * self.g

    def cell_of(self, x, y):
        ix, iy = round((x - self.x0) / self.g), round((y - self.y0) / self.g)
        return max(0, min(self.nx - 1, ix)), max(0, min(self.ny - 1, iy))

    def offsets(self, r):
        """Cell offsets (dx, dy) whose distance is below r mm."""
        k = round(r * 1000)
        if k not in self._offsets:
            m = int(r / self.g) + 1
            self._offsets[k] = [(dx, dy) for dx in range(-m, m + 1) for dy in range(-m, m + 1) if math.hypot(dx, dy) * self.g < r]
        return self._offsets[k]

    def reach(self, extra):
        """The cells to look at around a track centre whose copper reaches `extra` mm beyond what the stamps already allow for: the
        radius is rounded UP to the grid (all cells the copper can touch, and the half cell the sampling can miss)."""
        return self.offsets(extra + self.reach_q + 1e-9)

    def _stamp(self, arr, ix, iy, offs, owner):
        ny, nx = self.ny, self.nx
        for dx, dy in offs:
            a, b = ix + dx, iy + dy
            if 0 <= a < nx and 0 <= b < ny:
                self._mark(arr, a * ny + b, owner)

    @staticmethod
    def _mark(arr, j, owner):
        c = arr[j]
        if c == -1:
            arr[j] = owner
        elif c != owner and c != -2:
            arr[j] = -2

    def _cells_within(self, geo, r):
        """Cell indices whose centre is nearer than r mm to the shape."""
        g = self.g
        b = _bbox(geo)
        ix0, ix1 = int((b[0] - r - self.x0) / g) - 1, int((b[2] + r - self.x0) / g) + 2
        iy0, iy1 = int((b[1] - r - self.y0) / g) - 1, int((b[3] + r - self.y0) / g) + 2
        rect = geo[0] == "rect"
        for ix in range(max(ix0, 0), min(ix1, self.nx - 1) + 1):
            x = self.x0 + ix * g
            for iy in range(max(iy0, 0), min(iy1, self.ny - 1) + 1):
                y = self.y0 + iy * g
                if rect:
                    dx = max(geo[1][0] - x, 0, x - geo[1][2])
                    dy = max(geo[1][1] - y, 0, y - geo[1][3])
                    d = math.hypot(dx, dy)
                else:
                    d = _dist(geo, (x, y), (x, y))
                if d < r:
                    yield ix * self.ny + iy

    def _edge(self, box):
        e = self.rules["edge"] + self.wb / 2 + 0.02
        for l in (TOP, BOT):
            arr = self.S[l]
            for ix in range(self.nx):
                x = self.x0 + ix * self.g
                for iy in range(self.ny):
                    y = self.y0 + iy * self.g
                    if x < box[0] + e - 1e-9 or x > box[2] - e + 1e-9 or y < box[1] + e - 1e-9 or y > box[3] - e + 1e-9:
                        arr[ix * self.ny + iy] = -2

    def _owner(self, net):
        return -2 if not net else self.netid.setdefault(net, len(self.netid))

    def _add_shape(self, s):
        owner = self._owner(s["net"])
        r = self.clear + self.wb / 2 + self.q
        for l in s["layers"]:
            for j in self._cells_within(s["geo"], r):
                self._mark(self.S[l], j, owner)

    def _add_pad(self, p, shape):
        net = shape["net"]
        rect = shape["geo"][1]
        r = self.clear + self.wb / 2 + self.q
        layers = shape["layers"]
        owner = self._owner(net)
        for l in layers:
            for j in self._cells_within(shape["geo"], r):
                self._mark(self.S[l], j, owner)
        if shape["smd"]:                                  # no via in an SMD pad nor within clearance of its copper
            for j in self._cells_within(shape["geo"], self.rules["via_dia"] / 2 + self.clear + 0.005):
                self.novia[j] = 1
        if owner == -2:
            return
        ix0, iy0 = self.cell_of(rect[0], rect[1])
        ix1, iy1 = self.cell_of(rect[2], rect[3])
        # a round or oval pad is joined only where the track is inside the ellipse inscribed in its box (80%), not at the box corners
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        ha, hb = max((rect[2] - rect[0]) / 2, 1e-6), max((rect[3] - rect[1]) / 2, 1e-6)
        inside = [(ix, iy) for ix in range(ix0, ix1 + 1) for iy in range(iy0, iy1 + 1)
                  if rect[0] - 1e-9 <= self.x0 + ix * self.g <= rect[2] + 1e-9 and rect[1] - 1e-9 <= self.y0 + iy * self.g <= rect[3] + 1e-9
                  and (not _round_pad(p) or ((self.x0 + ix * self.g - cx) / ha) ** 2 + ((self.y0 + iy * self.g - cy) / hb) ** 2 <= 0.64 + 1e-9)]
        stub = False
        if not inside:
            inside, stub = [self.cell_of(p["x_mm"], p["y_mm"])], True
        cells = {l: {self.idx(ix, iy) for ix, iy in inside} for l in layers}
        if len(layers) == 2:
            self.tht.setdefault(owner, set()).update(cells[TOP])
        self.pads.setdefault(net, []).append({"tag": shape["tag"], "x": p["x_mm"], "y": p["y_mm"], "rect": rect, "cells": cells,
                                              "stub": stub, "layers": layers})

    # ---- passability
    def ok(self, net, l, i):
        s, d = self.S[l][i], self.D[l][i]
        return (s == -1 or s == net) and (d == -1 or d == net)

    def ring_ok(self, net, l, ix, iy, offs):
        ny, nx = self.ny, self.nx
        for dx, dy in offs:
            a, b = ix + dx, iy + dy
            if not (0 <= a < nx and 0 <= b < ny) or not self.ok(net, l, a * ny + b):
                return False
        return True

    def usable(self, net, l, i, width, margin=0.0, relaxed=False):
        """A track of this width can have its centre on the cell: the cell and the cells its copper reaches are free for the net."""
        s = self.S[l][i]
        if s != -1 and s != net:
            return False
        if not relaxed:
            d = self.D[l][i]
            if d != -1 and d != net:
                return False
        extra = max(0.0, (width - self.wb) / 2) + margin
        if extra > 1e-9:
            ix, iy = i // self.ny, i % self.ny
            for dx, dy in self.reach(extra):
                a, b = ix + dx, iy + dy
                if not (0 <= a < self.nx and 0 <= b < self.ny):
                    return False
                j = a * self.ny + b
                sj = self.S[l][j]
                if sj != -1 and sj != net:
                    return False
                if not relaxed:
                    dj = self.D[l][j]
                    if dj != -1 and dj != net:
                        return False
        return True

    # ---- search
    def _blocked(self, net, relaxed):
        """Per layer, a bytearray over the grid: 1 where a track centre of this net cannot be (fixed copper of another net, and tracks
        routed so far unless relaxed)."""
        out = []
        for l in (TOP, BOT):
            S = self.S[l]
            if relaxed:
                out.append(bytearray([1 if (v != -1 and v != net) else 0 for v in S]))
            else:
                D = self.D[l]
                out.append(bytearray([1 if ((v != -1 and v != net) or (d != -1 and d != net)) else 0 for v, d in zip(S, D)]))
        return out

    def _dilate(self, arr, offs):
        """arr (1 = blocked, grid order) grown by the cell offsets: a cell is 1 when any cell at one of the offsets is 1, or when that
        cell is off the board. Done on one big integer (a byte per cell, the grid padded with blocked cells) so that it is a few dozen
        shifts instead of millions of lookups."""
        nx, ny = self.nx, self.ny
        m = max(max(abs(dx), abs(dy)) for dx, dy in offs)
        w = ny + 2 * m
        pad = bytearray(b"") * ((nx + 2 * m) * w)
        for ix in range(nx):
            o = (ix + m) * w + m
            pad[o:o + ny] = arr[ix * ny:(ix + 1) * ny]
        big = int.from_bytes(pad, "little")
        acc = 0
        for dx, dy in offs:
            k = 8 * (dx * w + dy)
            acc |= (big << k) if k >= 0 else (big >> -k)
        raw = (acc & ((1 << (8 * len(pad))) - 1)).to_bytes(len(pad), "little")
        out = bytearray(nx * ny)
        for ix in range(nx):
            o = (ix + m) * w + m
            out[ix * ny:(ix + 1) * ny] = raw[o:o + ny]
        return out

    def astar(self, net, sources, goals, width, relaxed=False, deadline=None, max_pops=None, margin=0.0):
        """Cheapest path (list of (layer, cell)) from any source cell to any goal cell, or None (self.status says why: "none" there is
        no way, "limit" the search limit was reached, "time" the time given ran out). relaxed: tracks routed so far are passable (used
        to find which nets are in the way). margin: extra distance kept from everything (used to re-route a net the exact check found
        too close to something)."""
        ny, nx, n = self.ny, self.nx, self.n
        max_pops = max_pops or max(300000, 4 * n)
        extra = max(0.0, (width - self.wb) / 2) + margin
        via_r = self.rules["via_dia"] / 2
        tht = self.tht.get(net, ())
        novia = self.novia
        self.status = "none"
        base = self._blocked(net, relaxed)                    # base[l][i]: 1 = a track centre cannot be there
        wide = [self._dilate(base[l], self.reach(extra)) for l in (TOP, BOT)] if extra > 1e-9 else base
        if relaxed:
            vblock = [None, None]
        else:
            vo = self.reach(max(0.0, via_r - self.wb / 2) + margin)
            d0, d1 = self._dilate(base[TOP], vo), self._dilate(base[BOT], vo)
            vblock = bytes(a | b | c for a, b, c in zip(d0, d1, novia))
        # which cells hold another net's routed track (relaxed search only: crossing it is allowed, at a price)
        foreign = [None, None]
        if relaxed:
            for l in (TOP, BOT):
                foreign[l] = bytearray([1 if (v != -1 and v != net) else 0 for v in self.D[l]])
        if not self._connected(net, sources, goals, base, wide, vblock, tht, relaxed):
            return None
        gx = [g[1] // ny for g in goals]
        gy = [g[1] % ny for g in goals]
        gx0, gx1, gy0, gy1 = min(gx), max(gx), min(gy), max(gy)

        def h(i):
            ix, iy = i // ny, i % ny
            dx = max(gx0 - ix, 0, ix - gx1)
            dy = max(gy0 - iy, 0, iy - gy1)
            return (dx + dy) + (SQ2 - 2) * (dx if dx < dy else dy)

        heap, best, parent, came = [], {}, {}, {}
        goalset = set(goals)
        for (l, i) in sorted(sources):
            k = l * n + i
            best[k] = 0.0
            came[k] = 8
            heapq.heappush(heap, (h(i), 0.0, k))
        pops = 0
        dirs = list(enumerate(DIRS))
        while heap:
            f, gc, k = heapq.heappop(heap)
            if gc > best.get(k, 1e18) + 1e-9:
                continue
            pops += 1
            if pops > max_pops:
                self.status = "limit"
                return None
            if deadline and pops % 2000 == 0 and time.time() > deadline:
                self.status = "time"
                return None
            l, i = divmod(k, n)
            if (l, i) in goalset:
                path = [(l, i)]
                while k in parent:
                    k = parent[k]
                    path.append((k // n, k % n))
                return path[::-1]
            ix, iy = i // ny, i % ny
            bl, wl = base[l], wide[l]
            d = came[k]
            fl = foreign[l]
            for nd, (dx, dy) in dirs:
                a, b = ix + dx, iy + dy
                if not (0 <= a < nx and 0 <= b < ny):
                    continue
                j = a * ny + b
                if wl[j]:                                        # the goal cells too: a pad cell too close to a neighbour is no goal
                    continue
                if dx and dy:                                    # a diagonal must not cut between two blocked cells
                    if bl[ix * ny + b] or bl[a * ny + iy]:
                        continue
                cost = gc + (SQ2 if dx and dy else 1.0)
                if d != 8 and d != nd:
                    t = min((d - nd) % 8, (nd - d) % 8)
                    if t > 2:
                        continue
                    cost += TURN_45 if t == 1 else TURN_90
                if fl is not None and fl[j]:
                    cost += CROSS_COST
                nk = l * n + j
                if cost < best.get(nk, 1e18) - 1e-9:
                    best[nk] = cost
                    parent[nk] = k
                    came[nk] = nd
                    heapq.heappush(heap, (cost + h(j), cost, nk))
            o = 1 - l
            if not base[o][i]:
                if i in tht:                                     # inside a through hole pad of the net: the pad is the change of layer
                    cost = gc + THRU_COST
                elif relaxed:
                    cost = gc + VIA_COST if not novia[i] else None
                elif not vblock[i]:
                    cost = gc + VIA_COST
                else:
                    cost = None
                if cost is not None:
                    nk = o * n + i
                    if cost < best.get(nk, 1e18) - 1e-9:
                        best[nk] = cost
                        parent[nk] = k
                        came[nk] = 8
                        heapq.heappush(heap, (cost + h(i), cost, nk))
        return None

    def _connected(self, net, sources, goals, base, wide, vblock, tht, relaxed):
        """A cheap flood fill (4 neighbours, vias where they could be) from the sources: is any goal reachable at all? A search that
        has no way would otherwise try every cell of the board before saying so."""
        ny, nx, n = self.ny, self.nx, self.n
        novia = self.novia
        seen = [bytearray(n), bytearray(n)]
        stack = []
        for l, i in sources:
            if not seen[l][i]:
                seen[l][i] = 1
                stack.append((l, i))
        goalset = set(goals)
        while stack:
            l, i = stack.pop()
            if (l, i) in goalset:
                return True
            wl, sl = wide[l], seen[l]
            ix, iy = divmod(i, ny)
            for j, ok in ((i + ny, ix + 1 < nx), (i - ny, ix > 0), (i + 1, iy + 1 < ny), (i - 1, iy > 0)):
                if ok and not sl[j] and not wl[j]:
                    sl[j] = 1
                    stack.append((l, j))
            o = 1 - l
            if not seen[o][i] and not base[o][i] and (i in tht or (not novia[i] if relaxed else not vblock[i])):
                seen[o][i] = 1
                stack.append((o, i))
        self.status = "none"
        return False

    # ---- one net
    def route_net(self, net, width, relaxed=False, deadline=None, margin=0.0):
        """Join every pad of `net`. Returns (path list of segments-as-cell-paths, pad stubs, None) or (None, None, reason)."""
        pads = self.pads[net]
        nid = self.netid[net]
        use = lambda pad: {(l, c) for l, cs in pad["cells"].items() for c in cs if self.usable(nid, l, c, width, margin, relaxed)}
        tree = use(pads[0])
        if not tree:
            return None, None, f"pad {pads[0]['tag']} is too close to other copper for a {width:g} mm track"
        joined, todo = [pads[0]], pads[1:]
        paths, stubs = [], []
        if pads[0]["stub"]:
            stubs.append(pads[0])
        while todo:
            todo.sort(key=lambda p: (min(abs(p["x"] - q["x"]) + abs(p["y"] - q["y"]) for q in joined), p["tag"]))
            tgt = todo.pop(0)
            goals = use(tgt)
            if not goals:
                return None, None, f"pad {tgt['tag']} is too close to other copper for a {width:g} mm track"
            path = self.astar(nid, tree, goals, width, relaxed=relaxed, deadline=deadline, margin=margin)
            if path is None:
                what = {"limit": "search limit reached", "time": "ran out of time"}.get(self.status, "no way")
                return None, None, f"{what} from {joined[0]['tag']} to {tgt['tag']}"
            paths.append(path)
            tree |= set(path)
            tree |= goals
            joined.append(tgt)
            if tgt["stub"]:
                stubs.append(tgt)
        return paths, stubs, None

    def commit(self, net, paths, stubs, width):
        nid = self.netid[net]
        cells, vias, items = [], [], []
        tht = self.tht.get(nid, ())
        for path in paths:
            run = [path[0]]
            for a, b in zip(path, path[1:]):
                if a[0] != b[0]:
                    self._emit(net, run, width, items)
                    if b[1] not in tht:
                        vias.append(b[1])
                    run = [b]
                else:
                    run.append(b)
            self._emit(net, run, width, items)
            cells += path
        for pad in stubs:                                          # a tiny pad: the last cell is not on its centre
            c = next(iter(pad["cells"][pad["layers"][0]]))
            ls = [l for (l, q) in cells if q == c]
            l = ls[0] if ls else pad["layers"][0]
            cx, cy = self.xy(c)
            if math.hypot(cx - pad["x"], cy - pad["y"]) > 0.002:
                items.append({"kind": "track", "layer": LAYER_CODE[l], "x1": round(cx, 4), "y1": round(cy, 4), "x2": pad["x"],
                              "y2": pad["y"], "width": width, "net": net})
        for i in vias:
            x, y = self.xy(i)
            items.append({"kind": "via", "x": x, "y": y, "dia": self.rules["via_dia"], "hole": self.rules["via_hole"], "net": net})
        self.routed[net] = {"cells": cells, "vias": vias, "items": items, "width": width}
        self._stamp_net(net)

    def _stamp_net(self, net):
        r = self.routed[net]
        nid = self.netid[net]
        r_dyn = self.clear + r["width"] / 2 + self.wb / 2 + self.q
        r_via = self.clear + self.rules["via_dia"] / 2 + self.wb / 2 + self.q
        for l, i in r["cells"]:
            self._stamp(self.D[l], i // self.ny, i % self.ny, self.offsets(r_dyn), nid)
        for i in r["vias"]:
            for l in (TOP, BOT):
                self._stamp(self.D[l], i // self.ny, i % self.ny, self.offsets(r_via), nid)

    def _emit(self, net, run, width, items):
        """Collinear cells of a layer run become one track."""
        if len(run) < 2:
            return
        l = run[0][0]
        pts = [self.xy(c[1]) for c in run]
        seg = [pts[0]]
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-9:
                seg.append(b)
        seg.append(pts[-1])
        for (x1, y1), (x2, y2) in zip(seg, seg[1:]):
            items.append({"kind": "track", "layer": LAYER_CODE[l], "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4),
                          "y2": round(y2, 4), "width": width, "net": net})

    def rebuild(self):
        self.D = [[-1] * self.n, [-1] * self.n]
        for net in self.routed:
            self._stamp_net(net)

    def blockers(self, net, path):
        """The routed nets whose copper is within clearance of a path found while ignoring routed tracks."""
        where = {}
        for other, r in self.routed.items():
            for l, i in r["cells"]:
                where.setdefault((l, i), set()).add(other)
        hit = set()
        reach = self.offsets(self.clear + self.rules["via_dia"] / 2 + self.wb)
        for l, i in path:
            ix, iy = i // self.ny, i % self.ny
            for dx, dy in reach:
                a, b = ix + dx, iy + dy
                if 0 <= a < self.nx and 0 <= b < self.ny:
                    s = where.get((l, a * self.ny + b))
                    if s:
                        hit |= s
        hit.discard(net)
        return hit


def _hpwl(pads):
    xs, ys = [p["x"] for p in pads], [p["y"] for p in pads]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def _is_gnd(net):
    return bool(re.match(r"^(?:[ADPSEC]?GND\w*|VSS\w*|GROUND)$", str(net), re.I))


def plan_routes(doc, box, rules=None, pitch=0.1, seconds=120.0, only=None, rounds=8):
    """Route every net of a placed board (read_pcbdoc dict) inside `box` [x0, y0, x1, y1].
    Returns {"items", "routed", "failed": [(net, reason)], "stats"}. Nets with one pad are not routed. Order: rails (wide) first, then
    signals shortest first, ground last. A net that is blocked rips up the nets in its way and everything is retried (`rounds`).
    What was routed is then checked again by exact geometry (violations): a net found too close to something is ripped up and routed
    again with more distance (and, if need be, a narrower track) instead of refusing the board; a net that cannot be made clean
    comes back as failed, named. The result does not depend on the clock unless `seconds` really runs out (then it says so)."""
    rules = rules or rules_from_doc(doc)
    t0 = time.time()
    deadline = t0 + seconds
    rt = Router(doc, box, rules, pitch)
    nets = sorted(n for n, ps in rt.pads.items() if len(ps) >= 2 and (only is None or n in only))

    def key(n):
        return (2 if _is_gnd(n) else 0 if _RAIL.match(n) else 1, _hpwl(rt.pads[n]), n)
    order = sorted(nets, key=key)

    def width_for(n):
        if n in rules["net_width"]:
            ws = [rules["net_width"][n]]
        elif _RAIL.match(n):
            w = min(max(rules["width"], POWER_WIDTH), rules["width_max"])
            ws = [w, rules["width"]] if w > rules["width"] else [rules["width"]]
        else:
            ws = [rules["width"]]
        mn = rules.get("width_min") or rules["width"]
        if mn < ws[-1] - 1e-9:
            ws.append(mn)                                    # the narrowest the width rule allows, as a last resort
        return ws

    def try_route(n, margin=0.0):
        last = None
        for w in width_for(n):
            paths, stubs, why_ = rt.route_net(n, w, deadline=deadline, margin=margin)
            if paths is not None:
                rt.commit(n, paths, stubs, w)
                return None
            last = why_ or "no way"
            if rt.status == "time":
                break
        return last or "no way"

    def all_items():
        return [it for r in rt.routed.values() for it in r["items"]]

    failed, why = [], {}
    for n in order:
        r = try_route(n)
        if r:
            failed.append(n)
            why[n] = r
    ripped = {}
    for rnd in range(rounds):
        if not failed or time.time() > deadline:
            break
        n = failed.pop(0)
        paths, _, reason = rt.route_net(n, rules["width"], relaxed=True, deadline=deadline)
        if paths is None:
            why[n] = reason + ": blocked by fixed copper (pads, board edge), not by other tracks"
            failed.append(n)
            continue
        blockers = set()
        for p in paths:
            blockers |= rt.blockers(n, p)
        blockers = {b for b in blockers if ripped.get(b, 0) < 3}
        if not blockers:
            why[n] = (why.get(n) or "no way") + " (no track of another net to move)"
            failed.append(n)
            continue
        for b in blockers:
            ripped[b] = ripped.get(b, 0) + 1
            rt.routed.pop(b)
        rt.rebuild()
        again = [n] + sorted(blockers, key=key)
        for m in again:
            r = try_route(m)
            if r:
                failed.append(m)
                why[m] = r + (f" (after moving {', '.join(sorted(blockers))})" if m != n else "")
    # the exact check of what the grid produced: rip up and route again what it finds too close, with more distance each time
    repaired = 0
    last_msg = {}
    for attempt in range(len(MARGINS)):
        vs = _violations(rt.shapes, all_items(), rules, box)
        hit = sorted({n for _, ns in vs for n in ns if n in rt.routed}, key=key)
        if not hit:
            break
        for msg, ns in vs:
            for n in ns:
                last_msg.setdefault(n, msg)
        for n in hit:
            rt.routed.pop(n)
        rt.rebuild()
        repaired += len(hit)
        for n in hit:
            r = try_route(n, margin=MARGINS[attempt])
            if r:
                failed.append(n)
                why[n] = r
    vs = _violations(rt.shapes, all_items(), rules, box)
    for n in sorted({n for _, ns in vs for n in ns if n in rt.routed}):
        rt.routed.pop(n)
        for msg, ns in vs:
            if n in ns:
                failed.append(n)
                why[n] = "the track would break the rules and no other way was found: " + msg
                break
    rt.rebuild()
    for n in nets:                      # never leave a net unaccounted for: not routed means failed, with a reason
        if n not in rt.routed and n not in failed:
            failed.append(n)
            why[n] = "not routed (ran out of time)" if time.time() > deadline else "not routed"
    failed = list(dict.fromkeys(n for n in failed if n not in rt.routed))
    items = all_items()
    return {"items": items, "routed": sorted(rt.routed), "failed": [(n, why.get(n) or last_msg.get(n) or "no path") for n in failed],
            "stats": {"nets": len(nets), "tracks": sum(1 for i in items if i["kind"] == "track"), "vias": sum(1 for i in items if i["kind"] == "via"),
                      "seconds": round(time.time() - t0, 1), "ripped": sum(ripped.values()), "repaired": repaired, "pitch": pitch}}


def route_commands(pcb, items, replace=False, pour_net=None, box=None, edge=0.3):
    """Script lines: ROUTEBEGIN doc replace, TRACK doc layer x1 y1 x2 y2 width net, VIA doc x y dia hole net, then, for pour_net, POLY
    doc layer net x0 y0 x1 y1 (a pour on the bottom layer over the box), PCBSAVE doc."""
    d = str(pcb)
    cmds = [("ROUTEBEGIN", d, "1" if replace else "0")]
    for it in items:
        if it["kind"] == "track":
            cmds.append(("TRACK", d, "top" if it["layer"] == 1 else "bottom", f"{it['x1']:.4f}", f"{it['y1']:.4f}", f"{it['x2']:.4f}",
                         f"{it['y2']:.4f}", f"{it['width']:g}", it["net"]))
        else:
            cmds.append(("VIA", d, f"{it['x']:.4f}", f"{it['y']:.4f}", f"{it['dia']:g}", f"{it['hole']:g}", it["net"]))
    if pour_net and box:
        cmds.append(("POLY", d, "bottom", pour_net, f"{box[0] + edge:.4f}", f"{box[1] + edge:.4f}", f"{box[2] - edge:.4f}",
                     f"{box[3] - edge:.4f}"))
    cmds.append(("PCBSAVE", d))
    return cmds


def pour_net_for(doc, rules=None):
    """The ground net to pour on the bottom layer: a ground-named net with at least 3 pads, else None."""
    cnt = {}
    for p in doc.get("pads", []):
        if p.get("net") and p.get("ref"):
            cnt[p["net"]] = cnt.get(p["net"], 0) + 1
    gnds = sorted((n for n in cnt if _is_gnd(n) and cnt[n] >= 3), key=lambda n: (-cnt[n], n))
    return gnds[0] if gnds else None


# ---- an independent check of what the router drew (exact geometry, not the grid it searched on)

def _violations(shapes, items, rules, box):
    """[(message, (nets involved))] of the clearance, edge and via-in-pad problems of `items` against the fixed copper `shapes` and
    each other, by exact geometry. Same net copper may touch."""
    out = []
    clear, edge = rules["clearance"], rules["edge"]
    via_r = rules["via_dia"] / 2
    tracks = [i for i in items if i["kind"] == "track"]
    vias = [i for i in items if i["kind"] == "via"]
    lay = {1: TOP, 32: BOT}
    for t in tracks:
        a, b, hw = (t["x1"], t["y1"]), (t["x2"], t["y2"]), t["width"] / 2
        for x, y in (a, b):
            if x - hw < box[0] + edge - 1e-3 or x + hw > box[2] - edge + 1e-3 or y - hw < box[1] + edge - 1e-3 or y + hw > box[3] - edge + 1e-3:
                out.append((f"track of {t['net']} at ({x:.2f}, {y:.2f}) is closer than {edge:g} mm to the board edge", (t["net"],)))
        for s in shapes:
            if s["net"] != t["net"] and lay[t["layer"]] in s["layers"]:
                d = _dist(s["geo"], a, b) - hw
                if d < clear - 1e-3:
                    out.append((f"track of {t['net']} near {s['kind']} {s['tag']} ({s['net'] or 'no net'}): {d:.3f} mm < {clear:g} mm",
                                (t["net"], s["net"])))
    for i, t in enumerate(tracks):
        for u in tracks[i + 1:]:
            if t["net"] != u["net"] and t["layer"] == u["layer"]:
                d = _seg_seg((t["x1"], t["y1"]), (t["x2"], t["y2"]), (u["x1"], u["y1"]), (u["x2"], u["y2"])) - (t["width"] + u["width"]) / 2
                if d < clear - 1e-3:
                    out.append((f"tracks of {t['net']} and {u['net']} are {d:.3f} mm apart (< {clear:g} mm)", (t["net"], u["net"])))
    for v in vias:
        r = v["dia"] / 2
        p = (v["x"], v["y"])
        if v["x"] - r < box[0] + edge - 1e-3 or v["x"] + r > box[2] - edge + 1e-3 or v["y"] - r < box[1] + edge - 1e-3 or v["y"] + r > box[3] - edge + 1e-3:
            out.append((f"via of {v['net']} at ({v['x']:.2f}, {v['y']:.2f}) is closer than {edge:g} mm to the board edge", (v["net"],)))
        for s in shapes:
            d = _dist(s["geo"], p, p) - r
            if s["smd"] and d < clear - 1e-3:                       # via-in-pad is never allowed, whatever the net
                out.append((f"via of {v['net']} at ({v['x']:.2f}, {v['y']:.2f}) is in or too near SMD pad {s['tag']}", (v["net"], s["net"])))
            elif s["net"] != v["net"] and d < clear - 1e-3:
                out.append((f"via of {v['net']} near {s['kind']} {s['tag']} ({s['net'] or 'no net'})", (v["net"], s["net"])))
        for t in tracks:
            if t["net"] != v["net"] and _pt_seg(v["x"], v["y"], t["x1"], t["y1"], t["x2"], t["y2"]) < clear + r + t["width"] / 2 - 1e-3:
                out.append((f"via of {v['net']} near a track of {t['net']}", (v["net"], t["net"])))
        for u in vias:
            if u is not v and u["net"] != v["net"] and math.hypot(u["x"] - v["x"], u["y"] - v["y"]) < clear + r + u["dia"] / 2 - 1e-3:
                out.append((f"vias of {v['net']} and {u['net']} are too close", (v["net"], u["net"])))
    return out


def violations(doc, items, rules, box):
    """Clearance, edge and via-in-pad problems of `items` (as plan_routes returns them) against the fixed copper of `doc` (pads,
    footprint copper, fills, regions, tracks, unplated holes, keep-out) and each other, by exact geometry. Strings; empty = the copper
    keeps the rules. Same net copper may touch."""
    return [m for m, _ in _violations(fixed_shapes(doc, rules), items, rules, box)]
