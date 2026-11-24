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
import itertools
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
POUR_NECK = 0.25          # a poured net's copper must be joined to the pour through at least this wide a corridor, mm
POWER_WIDTH = 0.3          # rail nets are routed at least this wide when the board has room and no rule says otherwise
NECK_MAX = 1.0             # a neck-down (a narrower track into a pad that cannot take the wanted width) is at most this long outside the pad, mm
DEFAULT_EXPANSIONS = 4_000_000   # the cells all searches of one plan_routes together may expand (deterministic; the clock is a safety cap only)
EXPANSIONS_PER_CELL = 20         # ... or this many per grid cell of the board, whichever is more
MAX_RIPS = 5               # a net is ripped up at most this many times for the benefit of others
ROUNDS = 8                 # rip-up rounds, at least; or this many per net that failed in the first pass
ROUNDS_PER_FAILED = 2
GRADED_TRIES = 10          # tries of taking up one or two blocking nets only, per failed net and round, before taking up all of them
SECOND_SHARE = 0.3         # the share of a plan's search budget the second pass of rip-up rounds (graded_rip first) may spend
GRADED_SHARE = 0.2         # ... and the share of the second pass's search cap (cells) all those tries together may spend (a failed try searches the whole board)
VIA_COST = 30.0
CROSS_COST = 25.0          # relaxed search: entering a cell that holds another net's track (the nets to rip up are those crossed)
CHECK_POPS = 5000          # a search that has expanded this many cells asks once whether a goal can be reached at all
POUR_TIES = 3                 # times the pads that the pour does not reach are tied by tracks to the pads it does (each may move other nets)
THRU_COST = 2.0            # a change of layer inside a through hole pad: no via, only the cost of leaving the layer
TURN_45, TURN_90 = 0.3, 0.7
_TO01 = bytes([48] + [49] * 255)                  # byte 0 -> '0', any other -> '1' (a cell array as a binary string)
MARGINS = (0.05, 0.1, 0.2, 0.3, 0.45, 0.6)        # extra distance asked of a net that the exact check found too close to something
# How far the grid search keeps off an obstacle beyond the rule, as a share of the grid pitch: (obstacles grown by q, wide tracks and vias
# looked at by reach). The track centre sits on a grid point and the obstacle is sampled on the same grid, so some margin is needed so
# that a diagonal run does not clip a corner; the exact check (violations) repairs what is left. The wide setting is the first try; the
# tight one leaves a fine pitch fan-out (0.5 mm pitch, 0.2 mm clearance) room that the wide one takes away, and is tried when nets are open.
SAMPLING = (0.8, 0.71)
SAMPLING_TIGHT = (0.3, 0.3)
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
    for k in rules.get("keepout_rects") or ():      # keep-outs the program holds itself (the Altium keep-out layer did not take them)
        out.append({"kind": "keepout", "tag": "keep-out", "net": None, "layers": (TOP, BOT), "smd": False,
                    "geo": ("rect", tuple(float(v) for v in k))})
    return out


class Router:
    def __init__(self, doc, box, rules, pitch=0.1, sampling=SAMPLING):
        self.g = g = pitch
        self.rules = rules
        self.x0, self.y0 = box[0], box[1]
        self.box = box
        self.nx, self.ny = int((box[2] - box[0]) / g) + 1, int((box[3] - box[1]) / g) + 1
        self.n = self.nx * self.ny
        self.wb = rules["width"]
        self.clear = rules["clearance"]
        # The track centre sits on a grid point, an obstacle is sampled on the same grid: half a cell diagonal (0.71 g) plus what a
        # diagonal segment dips between two cells is the most the sampling can miss. Every obstacle is grown by it.
        self.q = sampling[0] * g
        self.reach_q = sampling[1] * g
        self.S = [[-1] * self.n, [-1] * self.n]        # fixed copper and the board edge: -1 free, net id, -2 blocks everything
        self.D = [[-1] * self.n, [-1] * self.n]        # tracks and vias routed so far
        # the same two as bitmaps (1 where the cell holds anything) and the cells each net id owns alone, so that "blocked for this net"
        # is a copy of the bitmap minus the net's own cells instead of a pass over every cell
        self.Socc = [bytearray(self.n), bytearray(self.n)]
        self.Docc = [bytearray(self.n), bytearray(self.n)]
        self.Sown = [{}, {}]
        self.Down = [{}, {}]
        self.netid = {}
        self.pads = {}                                  # net -> [pad dict with cells]
        self.routed = {}                                # net -> {"cells": [(l, i)], "vias": [i], "items": [...], "width": w}
        self.novia = bytearray(self.n)                  # cells where a via would sit in or too close to an SMD pad
        self.tht = {}                                   # net id -> cells of its through hole pads (a change of layer there needs no via)
        self.status = "none"                            # why the last astar() found nothing: none | limit | budget | time
        self._cols = None                               # bit masks of the grid's columns (see _connected)
        self.planes = set()                             # nets that lie on an inner plane (4 layers): joined to it by a stub and a via per pad
        self.pour_lenient = False                       # a poured net: a pad that cannot be joined is left out and named (pour_unjoined), not a failure
        self.pour_unjoined = []                         # [(pad tag, why)] of the last pour routing
        self.pour_tree = {}                             # {(layer, cell): pad tag} of the copper the last pour routing drew or found (see _route_pour)
        self.tie = {}                                   # net -> {"items", "cells", "vias", "pads": (tag, tag)}: copper that joins two pads of the net
        self.spent = 0                                  # cells expanded by all searches so far
        self.cap = float("inf")                         # the most cells all searches together may expand (the deterministic limit)
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

    def _stamp(self, fixed, l, ix, iy, offs, owner):
        ny, nx = self.ny, self.nx
        for dx, dy in offs:
            a, b = ix + dx, iy + dy
            if 0 <= a < nx and 0 <= b < ny:
                self._mark(fixed, l, a * ny + b, owner)

    def _mark(self, fixed, l, j, owner):
        """Cell j of layer l (fixed copper if `fixed`, else the routed tracks) is touched by net id `owner`: free -> owned, owned by
        another -> shared (-2, blocks everyone)."""
        arr, occ, own = (self.S[l], self.Socc[l], self.Sown[l]) if fixed else (self.D[l], self.Docc[l], self.Down[l])
        c = arr[j]
        if c == -1:
            arr[j] = owner
            occ[j] = 1
            if owner != -2:
                own.setdefault(owner, set()).add(j)
        elif c != owner and c != -2:
            arr[j] = -2
            own[c].discard(j)

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
                        self.Socc[l][ix * self.ny + iy] = 1

    def _owner(self, net):
        return -2 if not net else self.netid.setdefault(net, len(self.netid))

    def _add_shape(self, s):
        owner = self._owner(s["net"])
        r = self.clear + self.wb / 2 + self.q
        for l in s["layers"]:
            for j in self._cells_within(s["geo"], r):
                self._mark(True, l, j, owner)

    def _add_pad(self, p, shape):
        net = shape["net"]
        rect = shape["geo"][1]
        r = self.clear + self.wb / 2 + self.q
        layers = shape["layers"]
        owner = self._owner(net)
        for l in layers:
            for j in self._cells_within(shape["geo"], r):
                self._mark(True, l, j, owner)
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
            b = bytearray(self.Socc[l])
            for j in self.Sown[l].get(net, ()):
                b[j] = 0
            if not relaxed:
                d = bytearray(self.Docc[l])
                for j in self.Down[l].get(net, ()):
                    d[j] = 0
                b = bytearray((int.from_bytes(b, "little") | int.from_bytes(d, "little")).to_bytes(self.n, "little"))
            out.append(b)
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

    def astar(self, net, sources, goals, width, relaxed=False, deadline=None, max_pops=None, margin=0.0, goal_bot=None, goal_layer=BOT):
        """Cheapest path (list of (layer, cell)) from any source cell to any goal cell, or None (self.status says why: "none" there is
        no way, "limit" the search limit was reached, "time" the time given ran out). relaxed: tracks routed so far are passable (used
        to find which nets are in the way). margin: extra distance kept from everything (used to re-route a net the exact check found
        too close to something). goal_bot: a mask over the grid; a cell of layer goal_layer (the bottom layer unless said) it marks is a goal too (a net that
        is poured on that layer or lies on an inner plane: a via to it ends the search). The expansions are counted in self.spent; at self.cap the search
        stops with status "budget"; that is the deterministic limit, the clock is only a safety cap."""
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
            vblock = (int.from_bytes(d0, "little") | int.from_bytes(d1, "little") | int.from_bytes(novia, "little")).to_bytes(n, "little")
        # which cells hold another net's routed track (relaxed search only: crossing it is allowed, at a price)
        foreign = [None, None]
        if relaxed:
            for l in (TOP, BOT):
                f = bytearray(self.Docc[l])
                for j in self.Down[l].get(net, ()):
                    f[j] = 0
                foreign[l] = f
        checked = False                                         # is any goal reachable at all? asked only when the search is long
        if goal_bot is None:
            gx = [g[1] // ny for g in goals]
            gy = [g[1] % ny for g in goals]
            gx0, gx1, gy0, gy1 = min(gx), max(gx), min(gy), max(gy)

            def h(i):
                ix, iy = i // ny, i % ny
                dx = max(gx0 - ix, 0, ix - gx1)
                dy = max(gy0 - iy, 0, iy - gy1)
                return (dx + dy) + (SQ2 - 2) * (dx if dx < dy else dy)
        else:
            def h(i):
                return 0.0

        heap, best, parent, came = [], {}, {}, {}
        goalset = set(goals)
        for (l, i) in sorted(sources):
            k = l * n + i
            best[k] = 0.0
            came[k] = 8
            heapq.heappush(heap, (h(i), 0.0, k))
        pops = 0
        dirs = [(nd, dx, dy, SQ2 if dx and dy else 1.0) for nd, (dx, dy) in enumerate(DIRS)]
        push, pop, bget = heapq.heappush, heapq.heappop, best.get
        while heap:
            f, gc, k = pop(heap)
            if gc > bget(k, 1e18) + 1e-9:
                continue
            pops += 1
            self.spent += 1
            if pops > max_pops:
                self.status = "limit"
                return None
            if self.spent > self.cap:
                self.status = "budget"
                return None
            if pops == CHECK_POPS and not checked:
                checked = True
                if not self._connected(net, sources, goals, base, wide, vblock, tht, relaxed, goal_bot, goal_layer):
                    return None
            if deadline and pops % 2000 == 0 and time.time() > deadline:
                self.status = "time"
                return None
            l, i = divmod(k, n)
            if (l, i) in goalset or (goal_bot is not None and l == goal_layer and goal_bot[i]):
                path = [(l, i)]
                while k in parent:
                    k = parent[k]
                    path.append((k // n, k % n))
                return path[::-1]
            ix, iy = i // ny, i % ny
            bl, wl = base[l], wide[l]
            d = came[k]
            fl = foreign[l]
            for nd, dx, dy, step in dirs:
                a, b = ix + dx, iy + dy
                if not (0 <= a < nx and 0 <= b < ny):
                    continue
                j = a * ny + b
                if wl[j]:                                        # the goal cells too: a pad cell too close to a neighbour is no goal
                    continue
                if dx and dy:                                    # a diagonal must not cut between two blocked cells
                    if bl[ix * ny + b] or bl[a * ny + iy]:
                        continue
                cost = gc + step
                if d != 8 and d != nd:
                    t = min((d - nd) % 8, (nd - d) % 8)
                    if t > 2:
                        continue
                    cost += TURN_45 if t == 1 else TURN_90
                if fl is not None and fl[j]:
                    cost += CROSS_COST
                nk = l * n + j
                if cost < bget(nk, 1e18) - 1e-9:
                    best[nk] = cost
                    parent[nk] = k
                    came[nk] = nd
                    push(heap, (cost + h(j), cost, nk))
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

    def _bits(self, arr):
        """A per cell bytearray (0 / nonzero) as one big integer with bit i set when cell i is."""
        return int(bytes(arr).translate(_TO01)[::-1], 2)

    def _connected(self, net, sources, goals, base, wide, vblock, tht, relaxed, goal_bot=None, goal_layer=BOT):
        """A cheap flood fill (4 neighbours, vias where they could be) from the sources: is any goal reachable at all? A search that
        has no way would otherwise try every cell of the board before saying so. Done on bit sets (one big integer per layer, a bit
        per cell): a step of the fill is a few shifts of the whole grid instead of a visit of each cell."""
        ny, n = self.ny, self.n
        if self._cols is None:
            self._cols = (self._bits(bytes(([0] + [1] * (ny - 1)) * self.nx)),        # cells that are not in the first row of their column
                          self._bits(bytes(([1] * (ny - 1) + [0]) * self.nx)))        # ... not in the last
        not_first, not_last = self._cols
        full = (1 << n) - 1
        free = [full ^ self._bits(wide[l]) for l in (TOP, BOT)]
        nv = full ^ self._bits(self.novia if relaxed else vblock)
        t = 0
        for i in tht:
            t |= 1 << i
        jump = [(full ^ self._bits(base[l])) & (t | nv) for l in (TOP, BOT)]         # where a change of layer may land
        r, goal = [0, 0], [0, 0]
        for l, i in sources:
            r[l] |= 1 << i
        for l, i in goals:
            goal[l] |= 1 << i
        if goal_bot is not None:
            goal[goal_layer] |= self._bits(goal_bot)
        r0, r1 = r
        while True:
            if (r0 & goal[0]) | (r1 & goal[1]):
                return True
            a0 = (r0 << ny) | (r0 >> ny) | ((r0 & not_last) << 1) | ((r0 & not_first) >> 1)
            a1 = (r1 << ny) | (r1 >> ny) | ((r1 & not_last) << 1) | ((r1 & not_first) >> 1)
            n0 = r0 | (a0 & free[0]) | (r1 & jump[0])
            n1 = r1 | (a1 & free[1]) | (r0 & jump[1])
            if n0 == r0 and n1 == r1:
                break
            r0, r1 = n0, n1
        self.status = "none"
        return False

    # ---- fine pitch pads
    def _clean(self, net, l, pts, width, margin, relaxed):
        """The polyline `pts` as a track of this width on layer l keeps clearance (+ margin) from all other copper and the board edge,
        by exact geometry (not the grid)."""
        hw, clear, edge, box = width / 2, self.clear + margin + 2e-4, self.rules["edge"], self.box
        for x, y in pts:
            if x - hw < box[0] + edge or x + hw > box[2] - edge or y - hw < box[1] + edge or y + hw > box[3] - edge:
                return False
        for a, b in zip(pts, pts[1:]) if len(pts) > 1 else [(pts[0], pts[0])]:
            reach = hw + clear                                  # a shape whose box is farther than this from the segment's box cannot be too close
            sx0, sx1, sy0, sy1 = min(a[0], b[0]) - reach, max(a[0], b[0]) + reach, min(a[1], b[1]) - reach, max(a[1], b[1]) + reach
            for s in self.shapes:
                if s["net"] != net and l in s["layers"]:
                    bb = s.get("bb")
                    if bb is None:
                        bb = s["bb"] = _bbox(s["geo"])
                    if bb[2] < sx0 or bb[0] > sx1 or bb[3] < sy0 or bb[1] > sy1:
                        continue
                    if _dist(s["geo"], a, b) - hw < clear:
                        return False
            if relaxed:
                continue
            for other, r in self.routed.items():
                if other == net:
                    continue
                for it in r["items"]:
                    if it["kind"] == "track" and it["layer"] == LAYER_CODE[l]:
                        if _seg_seg(a, b, (it["x1"], it["y1"]), (it["x2"], it["y2"])) - (it["width"] + width) / 2 < clear:
                            return False
                    elif it["kind"] == "via" and _pt_seg(it["x"], it["y"], a[0], a[1], b[0], b[1]) - it["dia"] / 2 - hw < clear:
                        return False
        return True

    def _escape(self, net, nid, pad, width, margin, relaxed, stub_w=None, max_len=None):
        """A fine pitch SMD pad has no grid cell the grid search may use (the neighbours' keep-off is wider than the pitch leaves), yet a
        straight track along the pad's long axis, centred on the pad, can be legal. Try one: from the pad centre along the axis (either
        way) to the first grid row/column where the cell is usable, then sideways to that cell; kept only when the exact geometry keeps
        the clearance. {"escape": points, "layer", "cell"} for the shortest legal one, else None (the pad stays unroutable).
        stub_w (a neck-down): the stub itself is drawn and checked at this narrower width, at most max_len long; the cell it ends in must
        still take `width`, the width of the rest of the net."""
        if len(pad["layers"]) != 1:
            return None
        r, l = pad["rect"], pad["layers"][0]
        w, h = r[2] - r[0], r[3] - r[1]
        if abs(w - h) < 1e-6:
            return None                                      # no long axis
        px, py = pad["x"], pad["y"]
        fx, fy = math.floor((px - self.x0) / self.g + 1e-9), math.floor((py - self.y0) / self.g + 1e-9)
        cx, cy = self.cell_of(px, py)
        best = None
        for sign in (1, -1):
            for k in range(0, 31):
                done = False
                for side in (0, 1):                              # the two grid lines either side of the axis
                    if h > w:
                        ix, iy = fx + side, cy + sign * k
                        e = (px, self.y0 + iy * self.g)
                        dist = (e[1] - py) * sign
                    else:
                        ix, iy = cx + sign * k, fy + side
                        e = (self.x0 + ix * self.g, py)
                        dist = (e[0] - px) * sign
                    if dist <= 1e-9 or not (0 <= ix < self.nx and 0 <= iy < self.ny):
                        continue
                    i = self.idx(ix, iy)
                    if not self.usable(nid, l, i, width, margin, relaxed):
                        continue
                    pts = [(px, py)]
                    for q in (e, self.xy(i)):
                        q = (round(q[0], 4), round(q[1], 4))
                        if math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 1e-9:
                            pts.append(q)
                    if max_len is not None and sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) > max_len + 1e-9:
                        continue
                    if self._clean(net, l, pts, stub_w or width, margin, relaxed):
                        if best is None or dist < best[0] - 1e-9:
                            best = (dist, {"escape": pts, "layer": l, "cell": i})
                        done = True
                        break
                if done:
                    break
        return best[1] if best else None

    # ---- one net
    def why_stopped(self):
        return {"limit": "search limit reached", "time": "ran out of time",
                "budget": "ran out of search budget"}.get(self.status, "no way")

    def route_net(self, net, width, relaxed=False, deadline=None, margin=0.0, stub_width=None, pour_mask=None, pour_tie=None):
        """Join every pad of `net`. Returns (path list of segments-as-cell-paths, pad stubs, None) or (None, None, reason).
        stub_width: a neck-down, the narrower width allowed for the escape stub of a pad that cannot take `width`.
        pour_mask: the net is poured on the bottom layer (pour_region): its pads are not joined to each other by tracks but each
        top layer pad to the pour, by a short stub and a via (or by a short track to a pad that is in the pour already).
        pour_tie: (tree, tags): the pads `tags` of the poured net are joined by tracks to the copper `tree` ({(layer, cell): tag}) of its
        pads that the pour does reach (a pad whose drop the pour does not reach is tied to another pad's copper instead)."""
        pads = self.pads[net]
        nid = self.netid[net]
        use = lambda pad: {(l, c) for l, cs in pad["cells"].items() for c in cs if self.usable(nid, l, c, width, margin, relaxed)}
        paths, stubs, escaped = [], [], set()

        def start(pad):
            cells = use(pad)
            if cells:
                return cells
            esc = self._escape(net, nid, pad, width, margin, relaxed)
            if not esc and stub_width:
                r_ = pad["rect"]
                half = max(r_[2] - r_[0], r_[3] - r_[1]) / 2          # the stub starts at the pad centre: the length inside the pad is no neck
                esc = self._escape(net, nid, pad, width, margin, relaxed, stub_w=stub_width, max_len=half + NECK_MAX)
                if esc:
                    esc["neck"], esc["inside"] = stub_width, half
            if esc:
                esc["tag"] = pad["tag"]
                stubs.append(esc)
                escaped.add(id(pad))
                return {(esc["layer"], esc["cell"])}
            return cells
        if pour_mask is not None or pour_tie is not None:
            return self._route_pour(nid, pads, width, margin, deadline, start, stubs, escaped, pour_mask, relaxed, pour_tie)
        tree = start(pads[0])
        if not tree:
            return None, None, f"pad {pads[0]['tag']} is too close to other copper for a {width:g} mm track"
        joined, todo = [pads[0]], pads[1:]
        if pads[0]["stub"] and id(pads[0]) not in escaped:     # an escape replaces the unchecked cell-to-centre stub
            stubs.append(pads[0])
        tie = self.tie.get(net)
        mate = {}
        if tie:
            by_tag = {q["tag"]: q for q in pads}
            a, b = tie["pads"]
            if a in by_tag and b in by_tag:
                mate = {a: by_tag[b], b: by_tag[a]}

        def absorb(pad):
            """A pad joined: the pad its tie leads to is joined with it (the tie copper and that pad are part of the tree)."""
            m = mate.get(pad["tag"])
            if m is not None and m in todo:
                todo.remove(m)
                tree.update(tie["cells"])
                tree.update(use(m))
                joined.append(m)
        absorb(pads[0])
        while todo:
            todo.sort(key=lambda p: (min(abs(p["x"] - q["x"]) + abs(p["y"] - q["y"]) for q in joined), p["tag"]))
            tgt = todo.pop(0)
            goals = start(tgt)
            if not goals:
                return None, None, f"pad {tgt['tag']} is too close to other copper for a {width:g} mm track"
            path = self.astar(nid, tree, goals, width, relaxed=relaxed, deadline=deadline, margin=margin)
            if path is None:
                return None, None, f"{self.why_stopped()} from {joined[0]['tag']} to {tgt['tag']}"
            paths.append(path)
            tree |= set(path)
            tree |= goals
            joined.append(tgt)
            if tgt["stub"] and id(tgt) not in escaped:
                stubs.append(tgt)
            absorb(tgt)
        return paths, stubs, None

    def _route_pour(self, nid, pads, width, margin, deadline, start, stubs, escaped, pour_mask, relaxed=False, tie=None):
        """Each pad of a poured net that is on the top layer only is joined to the pour: a path from the pad to a via that lands in
        the pour (pour_mask, bottom layer) or to a pad already in the pour (a through hole pad or a bottom layer pad: the pour covers
        the whole bottom layer, so the pad is in it) or to copper already drawn for another pad. Returns like route_net, and sets
        self.pour_links: {pad tag: ("pour", cell) | ("pad", other tag)} for the check that the pour really reaches each of them, and
        self.pour_tree. tie = (tree, tags): only those pads, each joined by a track to the copper in tree (no drop to the pour)."""
        paths = []
        self.pour_links = links = {}
        self.pour_unjoined = unjoined = []
        plane = any(self.netid.get(n) == nid for n in self.planes)      # the net lies on an inner plane: a pad of either outer layer drops to it
        if tie is not None:
            tree = dict(tie[0])
            only = set(tie[1])
            todo = sorted((q for q in pads if q["tag"] in only), key=lambda q: q["tag"])
        else:
            tree = {}
            for pad in pads:
                if len(pad["layers"]) == 2 or (pad["layers"][0] == BOT and not plane):      # in the pour by itself (an inner plane: a through hole pad only)
                    for l, cs in pad["cells"].items():
                        for c in cs:
                            tree[(l, c)] = pad["tag"]
                    links[pad["tag"]] = ("pour", None)
            todo = sorted((q for q in pads if q["tag"] not in links), key=lambda q: q["tag"])
        self.pour_tree = tree
        for pad in todo:
            src = start(pad)
            to = BOT if not plane else 1 - pad["layers"][0]            # the layer a via lands on: the pour's, or the other outer layer for a plane
            path = (self.astar(nid, src, set(tree), width, relaxed=relaxed, deadline=deadline, margin=margin, goal_bot=pour_mask, goal_layer=to)
                    if src else None)
            if not src:
                self.status = "none"
            if path is None and pour_mask is not None and not relaxed and self.status not in ("time", "budget"):
                drop = self._drop_exact(nid, pad, width, margin, pour_mask)      # the grid keeps off more than the rules ask: look by exact geometry
                if drop is not None:
                    path, esc = drop
                    stubs[:] = [q for q in stubs if q.get("tag") != pad["tag"]] + [esc]
                    escaped.add(id(pad))
            if path is None and not src:
                why_ = f"pad {pad['tag']} is too close to other copper for a {width:g} mm track"
                if self.pour_lenient:
                    unjoined.append((pad["tag"], why_))
                    continue
                return None, None, why_
            if path is None:
                why_ = (f"{self.why_stopped()} from {pad['tag']} to the pour (a via into the bottom layer or a pad in the pour)" if tie is None
                        else f"{self.why_stopped()} from {pad['tag']} to other copper of the net that the pour reaches")
                if self.pour_lenient and self.status not in ("time", "budget"):
                    unjoined.append((pad["tag"], why_))
                    continue
                return None, None, why_
            end = path[-1]
            links[pad["tag"]] = ("pad", tree[end]) if end in tree else ("pour", end[1])
            paths.append(path)
            for c in path:
                tree.setdefault(c, pad["tag"])
            for l, cs in pad["cells"].items():
                for c in cs:
                    tree.setdefault((l, c), pad["tag"])
            if pad["stub"] and id(pad) not in escaped:
                stubs.append(pad)
        return paths, stubs, None

    def _via_clean(self, net, x, y, margin=0.0):
        """A via of `net` at (x, y) keeps the clearance (+ margin) from all other copper and the board edge, by exact geometry: the same
        tests as _violations (a via is never in or near an SMD pad, whatever its net; copper of other nets on either layer)."""
        r, clear, edge, box = self.rules["via_dia"] / 2, self.clear + margin + 2e-4, self.rules["edge"], self.box
        if x - r < box[0] + edge or x + r > box[2] - edge or y - r < box[1] + edge or y + r > box[3] - edge:
            return False
        reach = r + clear
        for s in self.shapes:
            bb = s.get("bb")
            if bb is None:
                bb = s["bb"] = _bbox(s["geo"])
            if bb[2] < x - reach or bb[0] > x + reach or bb[3] < y - reach or bb[1] > y + reach:
                continue
            if (s["smd"] or s["net"] != net) and _dist(s["geo"], (x, y), (x, y)) - r < clear:
                return False
        for other, rr in self.routed.items():
            if other == net:
                continue
            for it in rr["items"]:
                if it["kind"] == "track":
                    if _pt_seg(x, y, it["x1"], it["y1"], it["x2"], it["y2"]) - r - it["width"] / 2 < clear:
                        return False
                elif math.hypot(it["x"] - x, it["y"] - y) - r - it["dia"] / 2 < clear:
                    return False
        return True

    def _drop_exact(self, nid, pad, width, margin, pour_mask, radius=2.5):
        """A poured net's top layer pad that the grid search could not join to the pour: look for a stub (from the pad centre, along the
        pad's long axis or straight) and a via in the pour by exact geometry instead of the grid's keep-off, which is wider than the rules
        ask (it grows every obstacle by the sampling error). Nearest via first; kept only when the stub and the via keep the clearance
        from everything routed so far. Returns (path [(top, cell), (bottom, cell)], stub dict) or None."""
        if len(pad["layers"]) != 1 or (pad["layers"][0] != TOP and not any(self.netid.get(n) == nid for n in self.planes)):
            return None
        net = next(k for k, v in self.netid.items() if v == nid)
        l, px, py = pad["layers"][0], pad["x"], pad["y"]
        r = pad["rect"]
        vert = (r[3] - r[1]) >= (r[2] - r[0])
        half = ((r[3] - r[1]) if vert else (r[2] - r[0])) / 2
        ix0, iy0 = self.cell_of(px - radius, py - radius)
        ix1, iy1 = self.cell_of(px + radius, py + radius)
        cands = []
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                i = self.idx(ix, iy)
                x, y = self.xy(i)
                d = math.hypot(x - px, y - py)
                if d <= radius and pour_mask[i] and not self.novia[i]:
                    cands.append((round(d, 3), ix, iy, i))
        cands.sort()
        for _d, _ix, _iy, i in cands[:400]:
            x, y = self.xy(i)
            if not self._via_clean(net, x, y, margin):
                continue
            along, across = ((y - py), (x - px)) if vert else ((x - px), (y - py))
            sgn = 1 if along >= 0 else -1
            routes = [[(px, py), (round(x, 4), round(y, 4))]]                      # straight
            if abs(across) > 1e-6:
                axis = (lambda t: (px, round(py + t, 4))) if vert else (lambda t: (round(px + t, 4), py))
                for t in (along, sgn * (abs(along) - abs(across)), sgn * (half + 0.05)):      # along the axis, then to the via
                    if abs(t) > 1e-6 and t * sgn > 0 and abs(t) <= abs(along) + 1e-9:
                        routes.append([(px, py), axis(t), (round(x, 4), round(y, 4))])
            for pts in routes:
                if self._clean(net, l, pts, width, margin, False):
                    return [(l, i), (1 - l, i)], {"escape": pts, "layer": l, "cell": i, "tag": pad["tag"]}
        return None

    def pour_region(self, nid, neck=POUR_NECK):
        """(mask, labels, sizes): the bottom layer cells where copper of net nid can be (not blocked by the fixed copper or the tracks
        of other nets, and room for a `neck` wide corridor), the connected piece each belongs to (4 neighbours) and the sizes of the
        pieces. mask is 1 on the biggest piece: what a pour of the net fills as one body; a via in a smaller piece would sit in an
        island that is cut off from it."""
        base = self._blocked(nid, False)[BOT]
        extra = max(0.0, (neck - self.wb) / 2)
        blocked = self._dilate(base, self.reach(extra)) if extra > 1e-9 else base
        ny, nx, n = self.ny, self.nx, self.n
        labels = [0] * n
        sizes = [0]
        for s0 in range(n):
            if blocked[s0] or labels[s0]:
                continue
            lab = len(sizes)
            labels[s0] = lab
            stack, cnt = [s0], 0
            while stack:
                i = stack.pop()
                cnt += 1
                ix, iy = divmod(i, ny)
                if ix + 1 < nx and not labels[i + ny] and not blocked[i + ny]:
                    labels[i + ny] = lab
                    stack.append(i + ny)
                if ix > 0 and not labels[i - ny] and not blocked[i - ny]:
                    labels[i - ny] = lab
                    stack.append(i - ny)
                if iy + 1 < ny and not labels[i + 1] and not blocked[i + 1]:
                    labels[i + 1] = lab
                    stack.append(i + 1)
                if iy > 0 and not labels[i - 1] and not blocked[i - 1]:
                    labels[i - 1] = lab
                    stack.append(i - 1)
            sizes.append(cnt)
        best = max(range(1, len(sizes)), key=lambda k: (sizes[k], -k), default=0)
        mask = bytearray(1 if (best and lab_ == best) else 0 for lab_ in labels)
        return mask, labels, sizes

    def commit(self, net, paths, stubs, width, extend=False):
        """Draw `paths` (and the stubs) as the copper of net; extend: add it to what the net has drawn already."""
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
        necks = []
        for pad in stubs:
            if "escape" in pad:                                    # a fine pitch pad: out along its axis, checked exactly
                pts = pad["escape"]
                if pad.get("neck"):                                # a neck-down: this stub is narrower than the rest of the net
                    necks.append({"pad": pad.get("tag"), "width_mm": pad["neck"],
                                  "len_mm": round(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) - pad.get("inside", 0), 2)})
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    items.append({"kind": "track", "layer": LAYER_CODE[pad["layer"]], "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                  "width": pad.get("neck") or width, "net": net})
                    steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / (self.g / 2)))
                    for k in range(steps + 1):                     # its cells, so that later nets keep clear of it
                        cells.append((pad["layer"], self.idx(*self.cell_of(x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps))))
                continue
            # a tiny pad: the last cell is not on its centre
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
        t = self.tie.get(net)
        if extend and net in self.routed:
            r0 = self.routed[net]
            self.routed[net] = {"cells": r0["cells"] + cells, "vias": r0["vias"] + vias, "items": r0["items"] + items, "width": r0["width"],
                                "necks": r0["necks"] + necks}
            self._stamp_net(net)
            return
        if t:                                                      # the copper that joined two pads before routing is part of the net
            items += t["items"]
            cells += t["cells"]
            vias += t["vias"]
        self.routed[net] = {"cells": cells, "vias": vias, "items": items, "width": width, "necks": necks}
        self._stamp_net(net)

    def add_tie(self, net, items, tags):
        """Copper that joins two pads of one net before any routing (the two pads of one net at a connector that has a pad of another net
        between them): it is fixed for the other nets, free for this one, and is drawn with the net whenever the net is routed. tags:
        (tag, tag) of the two pads it joins. Returns False when a tie of the net exists already."""
        if net in self.tie:
            return False
        from . import pair as _pair
        cells, vias = _pair._cells(self, items)
        nid = self.netid[net]
        w = max(i["width"] for i in items if i["kind"] == "track")
        r_dyn = self.clear + w / 2 + self.wb / 2 + self.q
        r_via = self.clear + self.rules["via_dia"] / 2 + self.wb / 2 + self.q
        for l, i in cells:
            self._stamp(True, l, i // self.ny, i % self.ny, self.offsets(r_dyn), nid)
        for i in vias:
            for l in (TOP, BOT):
                self._stamp(True, l, i // self.ny, i % self.ny, self.offsets(r_via), nid)
        self.tie[net] = {"items": list(items), "cells": list(cells), "vias": list(vias), "pads": tuple(tags)}
        return True

    def _stamp_net(self, net):
        r = self.routed[net]
        nid = self.netid[net]
        r_dyn = self.clear + r["width"] / 2 + self.wb / 2 + self.q
        r_via = self.clear + self.rules["via_dia"] / 2 + self.wb / 2 + self.q
        for l, i in r["cells"]:
            self._stamp(False, l, i // self.ny, i % self.ny, self.offsets(r_dyn), nid)
        for i in r["vias"]:
            for l in (TOP, BOT):
                self._stamp(False, l, i // self.ny, i % self.ny, self.offsets(r_via), nid)

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
        self.Docc = [bytearray(self.n), bytearray(self.n)]
        self.Down = [{}, {}]
        for net in self.routed:
            self._stamp_net(net)

    def escape_blockers(self, net, stubs, width):
        """The routed nets whose tracks or vias an escape (fine pitch pad stub, found while ignoring routed tracks) would be too close to,
        by the same exact geometry as _clean."""
        hit, clear = set(), self.clear + 2e-4
        hw = width / 2
        for st in stubs or []:
            if "escape" not in st:
                continue
            pts, code = st["escape"], LAYER_CODE[st["layer"]]
            for a, b in zip(pts, pts[1:]):
                for other, r in self.routed.items():
                    if other == net:
                        continue
                    for it in r["items"]:
                        if it["kind"] == "track" and it["layer"] == code:
                            if _seg_seg(a, b, (it["x1"], it["y1"]), (it["x2"], it["y2"])) - (it["width"] + width) / 2 < clear:
                                hit.add(other)
                        elif it["kind"] == "via" and _pt_seg(it["x"], it["y"], a[0], a[1], b[0], b[1]) - it["dia"] / 2 - hw < clear:
                            hit.add(other)
        return hit

    def blockers(self, net, path):
        """The routed nets whose copper is within clearance of a path found while ignoring routed tracks."""
        where = {}
        for other, r in self.routed.items():
            for l, i in r["cells"]:
                where.setdefault((l, i), set()).add(other)
        hit = set()
        via_r = self.rules["via_dia"] / 2
        reach = self.offsets(self.clear + via_r + self.wb)
        # a via of the path (a change of layer) keeps a via's distance from the track cells of both layers: what a strict search asks
        # (vblock) is the stamp of a routed track or via plus the via's own radius, so a net that is only that far is in the way too
        r_via = self.clear + via_r + self.wb / 2 + self.q + (via_r - self.wb / 2) + self.reach_q
        reach_via = self.offsets(r_via)
        for (l, i), nxt in zip(path, list(path[1:]) + [None]):
            ix, iy = i // self.ny, i % self.ny
            is_via = nxt is not None and nxt[0] != l and nxt[1] == i
            layers = (TOP, BOT) if is_via else (l,)
            for dx, dy in (reach_via if is_via else reach):
                a, b = ix + dx, iy + dy
                if 0 <= a < self.nx and 0 <= b < self.ny:
                    for ll in layers:
                        s = where.get((ll, a * self.ny + b))
                        if s:
                            hit |= s
        hit.discard(net)
        return hit


def _pour_cut_off(rt, net, links, skip=()):
    """The pads of a poured net (routed by drops, `links` from Router._route_pour) that the pour does not reach now that all the
    tracks are drawn: the copper a pour of the net can fill (Router.pour_region) is split by the bottom layer tracks and vias of
    other nets, and a pad whose via or own bottom copper is not in the biggest piece is cut off. Returns the pad tags (not those in
    `skip`: pads that were left out of the pour routing, and are reported as such)."""
    nid = rt.netid[net]
    mask, labels, sizes = rt.pour_region(nid)
    best = max(range(1, len(sizes)), key=lambda k: (sizes[k], -k), default=0)
    by_tag = {p["tag"]: p for p in rt.pads[net]}
    memo = {}

    def joined(tag, seen=()):
        if tag in memo:
            return memo[tag]
        kind, ref = links.get(tag, ("pour", None))
        if tag in seen:
            ok = False
        elif kind == "pad":
            ok = joined(ref, seen + (tag,))
        elif ref is not None:
            ok = best != 0 and labels[ref] == best
        else:
            ok = best != 0 and any(labels[c] == best for c in by_tag[tag]["cells"].get(BOT, ()))
        memo[tag] = ok
        return ok
    return sorted(t for t in by_tag if t not in skip and not joined(t))


def _spanning_nets(pads):
    """Nets with two pads on one part that have a pad of another net between them (+5V at the two ends of a USB-C pad row): their way
    from one pad to the other runs along the row, in front of the pads of the nets in between, whose way out it can close."""
    out = set()
    items = [(net, q) for net, ps in pads.items() for q in ps]
    for net, ps in pads.items():
        for k, a in enumerate(ps):
            for b in ps[k + 1:]:
                if a["tag"].split("-")[0] != b["tag"].split("-")[0]:
                    continue
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                L2 = dx * dx + dy * dy
                if L2 < 1e-9:
                    continue
                for other, q in items:
                    if other == net or q["tag"].split("-")[0] != a["tag"].split("-")[0]:
                        continue
                    t = ((q["x"] - a["x"]) * dx + (q["y"] - a["y"]) * dy) / L2
                    if 0.0 < t < 1.0 and math.hypot(q["x"] - (a["x"] + t * dx), q["y"] - (a["y"] + t * dy)) < 1.0:
                        out.add(net)
    return out


def _hpwl(pads):
    xs, ys = [p["x"] for p in pads], [p["y"] for p in pads]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def _is_gnd(net):
    return bool(re.match(r"^(?:[ADPSEC]?GND\w*|VSS\w*|GROUND)$", str(net), re.I))


def _width_report(nets, plan_w, routed):
    """{net: {"width_mm" (drawn; None if not routed), "wanted_mm", "current_a", "source", "note"}}; a net drawn narrower than wanted
    (the board had no room for more) says so in its note."""
    out = {}
    for n in nets:
        p = plan_w[n]
        got = routed[n]["width"] if n in routed else None
        necks = routed[n].get("necks") or [] if n in routed else []
        note = p["note"]
        for k in necks:
            note += ("; " if note else "") + f"necked to {k['width_mm']:g} mm for {k['len_mm']:g} mm at {k['pad']}"
        if got is not None and p["width_mm"] is not None and got < p["width_mm"] - 1e-9:
            note += ("; " if note else "") + f"drawn {got:g} mm: no room for the wanted {p['width_mm']:g} mm"
        out[n] = {"width_mm": got, "wanted_mm": p["width_mm"], "current_a": p["current_a"], "source": p["source"], "note": note,
                  "necks": necks}
    return out


def _plan_routes_once(doc, box, rules=None, pitch=0.1, seconds=120.0, only=None, rounds=None, pour_net=None, max_expansions=None,
                      first=(), t0=None, info=None, sampling=SAMPLING, spans_last=False, ground_early=False, second_pass=False, planes=None):
    """Route every net of a placed board (read_pcbdoc dict) inside `box` [x0, y0, x1, y1].
    Returns {"items", "routed", "failed": [(net, reason)], "stats"}. Nets with one pad are not routed. Order: rails (wide) first, then
    signals shortest first, ground last. A net that is blocked rips up the nets in its way and everything is retried (`rounds`: 8 or twice the nets that failed first, whichever is more).
    What was routed is then checked again by exact geometry (violations): a net found too close to something is ripped up and routed
    again with more distance (and, if need be, a narrower track) instead of refusing the board; a net that cannot be made clean
    comes back as failed, named. The result does not depend on the clock: the searches have a budget of cells they may expand
    (`max_expansions`, the same for the same board); `seconds` is only a safety cap and, when it really runs out, it says so.
    pour_net: a net that will be poured on the bottom layer (the caller draws the pour): its top layer pads are joined to the pour
    by a short stub and a via each instead of by tracks to each other; where that cannot be done the net is routed by tracks as
    usual. The result's "pour" says which.
    planes: {net: inner layer name} of a 4 layer board (see plane_nets_for): those nets are not routed by tracks: each of their pads
    is joined to the plane by a short stub and a via (a through hole pad is in the plane by itself), laid before every other net.
    The result's "planes" lists them."""
    rules = rules or rules_from_doc(doc)
    t0 = t0 or time.time()
    deadline = t0 + seconds
    rt = Router(doc, box, rules, pitch, sampling)
    rt.cap = max_expansions or max(DEFAULT_EXPANSIONS, EXPANSIONS_PER_CELL * rt.n)
    nets = sorted(n for n, ps in rt.pads.items() if len(ps) >= 2 and (only is None or n in only))
    rt.planes = {n for n in (planes or {}) if n in nets}
    plane_mask = bytearray(b"") * rt.n                  # a plane is under the whole board: a via may land wherever the rules let one stand
    pour = pour_net if pour_net in nets and not rt.planes else None
    pour_state = {"net": pour, "mode": None, "note": "", "links": {}}
    region = [None]

    spanning = _spanning_nets(rt.pads) if spans_last else set()

    def key(n):
        if ground_early and _is_gnd(n):
            return (0.5, _hpwl(rt.pads[n]), n)                 # after the rails, before the signals (see STRATEGIES)
        return (2 if _is_gnd(n) else 0 if _RAIL.match(n) and n not in spanning else 1, _hpwl(rt.pads[n]), n)
    order = sorted(nets, key=key)
    # --- coupled USB pair hook (logic in pair.py): D+/D- are routed together first and leave the normal order
    from . import pair as _pair
    pair_state = _pair.pre_route(rt, rules, nets, deadline, doc)
    _pair.fallback_ties(rt, rules, pair_state)       # an uncoupled pair: the pads of a net at the connector are tied first
    order = [n for n in order if n not in pair_state["done"] and n != pour and n not in rt.planes]
    # --- end hook
    rank = {n: k for k, n in enumerate(first)}                 # nets that failed in an earlier attempt are laid first (see plan_routes)
    order = sorted(order, key=lambda n: rank.get(n, len(rank)))        # a stable sort: the rest keeps its order
    order = sorted(rt.planes, key=lambda n: (planes[n], n)) + order      # the plane nets' stubs and vias first: they are short and the signals go round them

    from altium import netcurrent
    plan_w = netcurrent.net_widths(nets, rules, rules.get("net_current"), rules.get("net_estimate"), rules.get("copper_oz") or 1.0,
                                   rules.get("temp_rise_c") or 10.0, is_rail=lambda n: bool(_RAIL.match(n)))
    mn = rules.get("width_min") or rules["width"]

    def width_for(n):
        w = plan_w[n]["width_mm"]
        if w is None:           # a current outside the IPC-2221 range: no invented width, the rail default or the board's width
            w = min(max(rules["width"], POWER_WIDTH), rules["width_max"]) if _RAIL.match(n) else rules["width"]
        if plan_w[n]["current_a"] is not None and not rules.get("allow_narrow"):
            return [w]           # a net with a current is drawn at its width or not at all (allow_narrow: a partial route the student agreed to)
        ws = [w, rules["width"]] if w > rules["width"] + 1e-9 else [w]
        if mn < ws[-1] - 1e-9:
            ws.append(mn)                                    # the narrowest the width rule allows, as a last resort
        return ws

    def necks(w):
        """The narrower stub widths to try for a pad that cannot take width w, widest first."""
        cand = [rules["width"], mn] + [round(w * f, 3) for f in (0.75, 0.5, 0.35, 0.25)]
        return sorted({x for x in cand if mn - 1e-9 <= x < w - 1e-9}, reverse=True)

    def stopped():
        return rt.status in ("time", "budget")

    def try_route(n, margin=0.0):
        if n in rt.planes:
            return _try_widths(n, margin, plane_mask)
        if n == pour and pour_state["mode"] != "tracks":
            region[0] = rt.pour_region(rt.netid[pour])[0]                  # the pour as it is with the tracks drawn so far
            r = _try_widths(n, margin, region[0])
            if r is None:
                pour_state["mode"], pour_state["links"], pour_state["tree"] = "drops", dict(rt.pour_links), dict(rt.pour_tree)
            return r
        return _try_widths(n, margin, None)

    def _try_widths(n, margin, mask):
        last = None
        for w in width_for(n):
            # the wanted width first; then, when a pad cannot take it (a fine pitch pad), only the short stub at that pad narrower
            for sw in [None] + (necks(w) if w > mn + 1e-9 else []):
                paths, stubs, why_ = rt.route_net(n, w, deadline=deadline, margin=margin, stub_width=sw, pour_mask=mask)
                if paths is not None:
                    rt.commit(n, paths, stubs, w)
                    return None
                last = why_ or "no way"
                if stopped() or (sw is None and not last.startswith("pad ")):
                    break              # a neck-down only helps when a pad is the problem
            if stopped():
                break
        return last or "no way"

    def explain(n, reason):
        """A net with a current is never drawn narrower than it needs (unless a partial route was agreed): when it does not fit, say so
        and name the ways forward."""
        p = plan_w[n]
        if p["current_a"] is None or rules.get("allow_narrow") or p["width_mm"] is None:
            return reason
        return (f"{p['current_a']:g} A needs {p['width_mm']:g} mm and there is no room for it, even narrowed at the pads ({reason}); "
                "move parts to give it room, add a wider copper pour or polygon for this rail, or lower its current if that was an estimate")

    def all_items():
        return [it for r in rt.routed.values() for it in r["items"]]

    if pour and pour not in rank and ground_early:               # the poured net's drops are laid after the rails, before the signals: a ground pin
        k = 0
        while k < len(order) and (order[k] in rank or (_RAIL.match(order[k]) and order[k] not in spanning)):
            k += 1                                              # in the middle of a fine pitch row gets its stub and via before the
        order = order[:k] + [pour] + order[k:]                  # signals' fan-out closes the way
    else:
        order = ([pour] if pour in rank else []) + order + ([pour] if pour and pour not in rank else [])   # a poured net last: its vias go where the signals left the pour whole
    failed, why = [], {}
    for n in order:
        r = try_route(n)
        if r:
            failed.append(n)
            why[n] = r
        if stopped():
            break
    ripped = {}
    graded = [0]                  # cells expanded by the graded tries so far
    graded_cap = [0]              # the search cap of the second pass the tries share is taken from

    def graded_rip(n, blockers):
        """The least disturbance first: of the nets whose tracks a way for `n` crosses, one (then two) is taken up and laid again after
        `n`, instead of all together (which lets the greedy search close other nets' ways in turn; the rounds above do that and
        can go round in circles). The first try with every net routed is kept (True); else everything is as it was (False)."""
        cands = sorted(blockers, key=key)
        for sub in ([(b,) for b in cands] + list(itertools.combinations(cands, 2)))[:GRADED_TRIES]:
            if graded[0] > GRADED_SHARE * graded_cap[0]:
                break
            spent0 = rt.spent
            snap = (dict(rt.routed), list(failed), dict(why), dict(pour_state["links"]), pour_state["mode"], pour_state.get("tree"))
            for b in sub:
                rt.routed.pop(b)
            rt.rebuild()
            done = all(not try_route(m) for m in [n] + sorted(sub, key=lambda m: (m != pour, key(m)))) and not stopped()
            graded[0] += rt.spent - spent0
            if done:
                for b in sub:
                    ripped[b] = ripped.get(b, 0) + 1
                return True
            rt.routed = dict(snap[0])                                            # plan that stays open is as the rounds left it (later plans start from it)
            failed[:] = snap[1]                                                  # rounds left it, so the plans after it start from the same open nets
            why.clear()
            why.update(snap[2])
            pour_state["links"], pour_state["mode"], pour_state["tree"] = snap[3], snap[4], snap[5]
            rt.rebuild()
            if stopped():
                break
        return False
    hard = set()                  # nets whose search is blocked by fixed copper even with every track passable: ripping up cannot help
    best = [None]                 # the state with the fewest nets failed so far: a round that makes it worse is not kept

    def keep_best():
        k = len(set(failed))
        if best[0] is None or k < best[0][0]:
            best[0] = (k, dict(rt.routed), list(failed), dict(why), dict(pour_state["links"]), pour_state["mode"], pour_state.get("tree"))
    keep_best()

    def run_rounds(gentle):
        for rnd in range(rounds if rounds is not None else max(ROUNDS, ROUNDS_PER_FAILED * len(failed))):
            cand = [m for m in failed if m not in hard and not (gentle and m == pour)]
            if not cand or stopped() or time.time() > deadline:
                break
            n = cand[0]
            failed.remove(n)
            paths, esc_stubs, reason = rt.route_net(n, rules["width"], relaxed=True, deadline=deadline,
                                                    pour_mask=(plane_mask if n in rt.planes else rt.pour_region(rt.netid[n])[0] if n == pour and pour_state["mode"] != "tracks" else None))
            if paths is None:
                why[n] = reason + (": blocked by fixed copper (pads, board edge), not by other tracks" if not stopped() else "")
                if not stopped():
                    hard.add(n)
                failed.append(n)
                continue
            blockers = set()
            for p in paths:
                blockers |= rt.blockers(n, p)
            blockers |= rt.escape_blockers(n, esc_stubs, rules["width"])      # a fine pitch pad's escape can be what a track blocks
            blockers = {b for b in blockers if ripped.get(b, 0) < MAX_RIPS and b not in pair_state["done"]}   # a coupled pair is not ripped up
            if not blockers:
                if "(no track of another net to move)" not in (why.get(n) or ""):
                    why[n] = (why.get(n) or "no way") + " (no track of another net to move)"
                failed.append(n)
                continue
            if gentle and len(blockers) > 1 and graded_rip(n, blockers):
                keep_best()
                continue
            for b in sorted(blockers):
                ripped[b] = ripped.get(b, 0) + 1
                rt.routed.pop(b)
            rt.rebuild()
            again = [n] + sorted(blockers, key=lambda m: (m != pour, key(m)))      # the poured net's drops come before the others are laid again
            for m in again:
                r = try_route(m)
                if r:
                    failed.append(m)
                    why[m] = r + (f" (after moving {', '.join(sorted(blockers - {m}))})" if m != n else "")
            keep_best()
        if best[0] is not None and len(set(failed)) > best[0][0]:     # the rounds ended worse than the best state they passed (also when out of time: final_check runs after)
            _, routed_, failed[:], why_, pour_state["links"], pour_state["mode"], pour_state["tree"] = best[0]
            rt.routed = dict(routed_)
            why.clear()
            why.update(why_)
            rt.rebuild()

    run_rounds(False)
    if second_pass and any(m not in hard and m != pour for m in failed) and not stopped():   # still open, in a later plan: the same again,
        snap = (dict(rt.routed), list(failed), dict(why), dict(pour_state["links"]), pour_state["mode"], pour_state.get("tree"), dict(ripped))
        cap0 = rt.cap                                                            # taking up one or two nets first (see graded_rip); it may
        rt.cap = min(cap0, rt.spent + int(SECOND_SHARE * cap0))                  # spend only a share of the plan's budget
        graded_cap[0] = cap0
        run_rounds(True)
        rt.cap = cap0
        if rt.status == "budget" and rt.spent < cap0:
            rt.status = "none"                                                   # the share ran out, not the plan's budget
        if len(set(failed)) >= len(set(snap[1])) or any(m != pour for m in failed):   # kept only when it leaves no net but the poured one open: a
            rt.routed = dict(snap[0])
            failed[:] = snap[1]
            why.clear()
            why.update(snap[2])
            pour_state["links"], pour_state["mode"], pour_state["tree"] = snap[3], snap[4], snap[5]
            ripped.clear()
            ripped.update(snap[6])
            rt.rebuild()
    partial = {}                  # a poured net some of whose pads could not be joined: {net: why}; its other pads are drawn
    if pour and pour in failed and not stopped():          # no way to the pour for some pad, even moving the nets in the way
        # 1. every pad that can be dropped to the pour is, and the pad that cannot is named; 2. tracks for the whole net, which is
        # better if they join every pad; else 1. stands (the net is reported as not complete, naming the pad)
        keep = None
        if pour_state["mode"] != "tracks":
            region[0] = rt.pour_region(rt.netid[pour])[0]
            rt.pour_lenient = True
            r = _try_widths(pour, 0.0, region[0])
            rt.pour_lenient = False
            if r is None:
                if rt.pour_unjoined:
                    if len(rt.pour_unjoined) < sum(1 for q in rt.pads[pour] if q["layers"][0] == TOP and len(q["layers"]) == 1):
                        keep = (rt.routed.pop(pour), dict(rt.pour_links), list(rt.pour_unjoined))
                        rt.rebuild()
                    else:
                        rt.routed.pop(pour)
                        rt.rebuild()
                else:
                    pour_state["mode"], pour_state["links"] = "drops", dict(rt.pour_links)
                    failed.remove(pour)
        if pour in failed:
            pour_state["mode"], pour_state["note"] = "tracks", why.get(pour, "")
            failed.remove(pour)
            r = try_route(pour)
            if r:
                if keep:
                    rt.routed[pour] = keep[0]
                    rt.rebuild()
                    pour_state["mode"], pour_state["links"] = "drops", keep[1]
                    names = ", ".join(t for t, _ in keep[2])
                    partial[pour] = (f"pad(s) {names} cannot be joined to the pour or to other {pour} copper ({keep[2][0][1]}); "
                                     f"the other {pour} pads are dropped to the pour")
                    pour_state["note"] = partial[pour]
                    pour_state["unjoined"] = [t for t, _ in keep[2]]
                else:
                    failed.append(pour)
                    why[pour] = r
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
        hit = sorted(set(hit) | set(_pair.release(pair_state, hit, last_msg, key)), key=key)      # pair.py hook: a released pair is reported
        for n in hit:
            rt.routed.pop(n)
        rt.rebuild()
        _pair.fallback_ties(rt, rules, pair_state)          # a pair released just now is routed as two nets: their connector ties first
        repaired += len(hit)
        for n in hit:
            r = try_route(n, margin=MARGINS[attempt])
            if r:
                failed.append(n)
                why[n] = r
    def final_check():
        """What is left is checked by exact geometry once more: a net found too close to something is taken off and reported."""
        vs = _violations(rt.shapes, all_items(), rules, box)
        for n in sorted({n for _, ns in vs for n in ns if n in rt.routed}):
            rt.routed.pop(n)
            partial.pop(n, None)
            for msg, ns in vs:
                if n in ns:
                    failed.append(n)
                    why[n] = "the track would break the rules and no other way was found: " + msg
                    break
        rt.rebuild()
    final_check()

    def cut_now():
        return _pour_cut_off(rt, pour, pour_state["links"], pour_state.get("unjoined", ()) if pour in partial else ())

    def tie_cut(cut):
        """The pads the pour does not reach (`cut`) are joined by tracks to the copper of the pads it does reach: only those pads get
        tracks, the others stay dropped to the pour. When the tracks of other nets are in the way those nets are taken up and laid
        again after (as in the rounds above). Kept only when every net is still routed and the exact check still passes; else
        nothing is changed. True when kept."""
        tree = pour_state.get("tree")
        if not tree or pour in partial:
            return False
        goal = {c: t for c, t in tree.items() if t not in cut}
        w = width_for(pour)[0]
        snap = (dict(rt.routed), list(failed), dict(why), dict(pour_state["links"]), dict(tree), dict(ripped))
        moved = []
        paths, stubs, why_ = rt.route_net(pour, w, deadline=deadline, pour_tie=(goal, sorted(cut)))
        if paths is None and not stopped():                # what is in the way: the nets whose tracks a way through crosses
            paths_r, st_r, why_r = rt.route_net(pour, w, relaxed=True, deadline=deadline, pour_tie=(goal, sorted(cut)))
            if paths_r is not None:
                bl = set()
                for p_ in paths_r:
                    bl |= rt.blockers(pour, p_)
                bl |= rt.escape_blockers(pour, st_r, w)
                moved = sorted((b for b in bl if ripped.get(b, 0) < MAX_RIPS + 2 and b not in pair_state["done"]), key=key)
                if moved:
                    for b in moved:
                        ripped[b] = ripped.get(b, 0) + 1
                        rt.routed.pop(b)
                    rt.rebuild()
                    paths, stubs, why_ = rt.route_net(pour, w, deadline=deadline, pour_tie=(goal, sorted(cut)))
        ok = paths is not None
        if ok:
            links = dict(pour_state["links"])
            links.update(rt.pour_links)
            rt.commit(pour, paths, stubs, w, extend=True)
            pour_state["links"], pour_state["tree"] = links, dict(rt.pour_tree)
            for m in moved:                                 # the nets that were in the way, laid again round the new copper
                r = try_route(m)
                if r:
                    ok = False
                    break
        if ok:
            before = set(snap[1])
            final_check()
            ok = pour in rt.routed and set(failed) <= before
        if ok:
            return True
        rt.routed = dict(snap[0])                          # not accepted: as it was
        failed[:] = snap[1]
        why.clear()
        why.update(snap[2])
        pour_state["links"], pour_state["tree"] = snap[3], snap[4]
        ripped.clear()
        ripped.update(snap[5])
        rt.rebuild()
        return False

    if pour and pour in rt.routed and pour_state["mode"] == "drops":       # the pour must really reach every pad: no track of another net may cut it off
        cut = cut_now()
        for _ in range(POUR_TIES):
            if not cut or not tie_cut(cut):
                break
            cut = cut_now() if pour in rt.routed else []
        if cut:
            rt.routed.pop(pour)
            partial.pop(pour, None)
            rt.rebuild()
            pour_state["mode"], pour_state["note"] = "tracks", ("the bottom layer tracks of other nets cut the pour off from " + ", ".join(cut[:4])
                                                                  + (" ..." if len(cut) > 4 else "") + ": the net is routed by tracks")
            r = _try_widths(pour, 0.0, None)
            if r:
                failed.append(pour)
                why[pour] = r
            else:
                final_check()                                   # the tracks that replace the pour are checked like all others
    for n in nets:                      # never leave a net unaccounted for: not routed means failed, with a reason
        if n not in rt.routed and n not in failed:
            failed.append(n)
            why[n] = ("not routed (ran out of time)" if time.time() > deadline else
                      "not routed (ran out of search budget)" if rt.status == "budget" else "not routed")
    failed = list(dict.fromkeys(n for n in failed if n not in rt.routed))
    for n in partial:                   # drawn in part: it is not a routed net, its failure says which pad is left
        if n in rt.routed:
            failed.append(n)
            why[n] = partial[n]
    items = all_items()
    if info is not None:
        info["hard"] = set(hard)
    return {"pairs": _pair.report(rt, rules, pair_state, items),     # pair.py hook
            "items": items, "routed": sorted(n for n in rt.routed if n not in partial), "failed": [(n, explain(n, why.get(n) or last_msg.get(n) or "no path")) for n in failed],
            "widths": (rep := _width_report(nets, plan_w, rt.routed)), "width_problems": netcurrent.width_problems(rep),
            "planes": {n: planes[n] for n in sorted(rt.planes)},
            "pour": {"net": pour, "mode": pour_state["mode"] if pour in rt.routed else None, "note": pour_state["note"]} if pour else None,
            "stats": {"nets": len(nets), "tracks": sum(1 for i in items if i["kind"] == "track"), "vias": sum(1 for i in items if i["kind"] == "via"),
                      "seconds": round(time.time() - t0, 1), "ripped": sum(ripped.values()), "repaired": repaired, "pitch": pitch,
                      "expansions": rt.spent}}


# The plans tried, in order, until every net is routed: (sampling, the nets left open by the earlier plans are laid first, a rail that
# spans other nets' pads on a connector is laid after them, the ground (the poured net, or a ground net routed by tracks) is laid after
# the rails and before the signals).
STRATEGIES = ((SAMPLING, False, False, False), (SAMPLING_TIGHT, False, True, True), (SAMPLING_TIGHT, True, True, False),
              (SAMPLING_TIGHT, True, False, False))

def plan_routes(doc, box, rules=None, pitch=0.1, seconds=120.0, only=None, rounds=None, pour_net=None, max_expansions=None, planes=None):
    """Route every net of a placed board (read_pcbdoc dict) inside `box` [x0, y0, x1, y1]; the arguments and the result are those of
    _plan_routes_once. A net left open that is not blocked by fixed copper alone is a search that went wrong, not a board that cannot be
    routed (the search is greedy: one net's track can close a fine pitch pad's only way out): the whole plan is then made again, by the
    next of STRATEGIES (the open nets laid first; a tighter keep-off), and the plan with the fewest nets open is returned (ties: the
    earlier). Every plan passes the same exact checks, so a later plan can only complete the route, never weaken it. Each plan has its own
    budget of cells, so the result is the same for the same board; `seconds` (all plans together) is the safety cap."""
    t0 = time.time()
    rules = rules or rules_from_doc(doc)
    best, info, first, tried, took = None, {}, [], 0, 0.0
    for sampling, promote, spans_last, ground_early in STRATEGIES:
        if best is not None:
            open_ = [n for n, _ in best["failed"]]
            if not open_ or time.time() - t0 + took > seconds or not [n for n in open_ if n not in info.get("hard", ())]:
                break                                  # done, out of time, or only fixed copper is in the way: another plan cannot help
            if promote:
                first = open_ + [n for n in first if n not in open_]
        info = {}
        t1 = time.time()
        res = _plan_routes_once(doc, box, rules, pitch, seconds, only, rounds, pour_net, max_expansions, first=first, t0=t0, info=info,
                                sampling=sampling, spans_last=spans_last, ground_early=ground_early, second_pass=tried > 0, planes=planes)
        tried += 1
        took = time.time() - t1
        if best is None or len(res["failed"]) < len(best["failed"]):
            best = res
    best["stats"]["attempts"] = tried
    return best


POUR_KEEPOUT_MARGIN_MM = 0.2      # the pour stays this far from a keep-out (the polygon clearance rule adds its own)
POUR_MIN_PIECE_MM = 1.0           # a leftover piece of the pour smaller than this in either direction is not drawn


def _rect_minus(r, k):
    """[rect] pieces of rect r outside rect k (all [x0, y0, x1, y1])."""
    if k[0] >= r[2] or k[2] <= r[0] or k[1] >= r[3] or k[3] <= r[1]:
        return [r]
    out = []
    if k[0] > r[0]:
        out.append([r[0], r[1], k[0], r[3]])
    if k[2] < r[2]:
        out.append([k[2], r[1], r[2], r[3]])
    x0, x1 = max(r[0], k[0]), min(r[2], k[2])
    if k[1] > r[1]:
        out.append([x0, r[1], x1, k[1]])
    if k[3] < r[3]:
        out.append([x0, k[3], x1, r[3]])
    return out


def pour_rects(box, keepouts=(), edge=0.3):
    """The rectangles the ground pour is drawn as: the board box less `edge` on each side, less every keep-out rectangle (plus
    POUR_KEEPOUT_MARGIN_MM): so no pour copper lies in a keep-out (an antenna area). One rectangle when there is no keep-out."""
    rects = [[box[0] + edge, box[1] + edge, box[2] - edge, box[3] - edge]]
    for k in keepouts or ():
        k = [k[0] - POUR_KEEPOUT_MARGIN_MM, k[1] - POUR_KEEPOUT_MARGIN_MM, k[2] + POUR_KEEPOUT_MARGIN_MM, k[3] + POUR_KEEPOUT_MARGIN_MM]
        rects = [p for r in rects for p in _rect_minus(r, k)]
    return [r for r in rects if r[2] - r[0] >= POUR_MIN_PIECE_MM and r[3] - r[1] >= POUR_MIN_PIECE_MM]


def route_commands(pcb, items, replace=False, pour_net=None, box=None, edge=0.3, keepouts=None, planes=None):
    """Script lines: ROUTEBEGIN doc replace, TRACK doc layer x1 y1 x2 y2 width net, VIA doc x y dia hole net, then, for pour_net, POLY
    doc layer net x0 y0 x1 y1 (a pour on the bottom layer over the box; one POLY per rectangle of the box less the `keepouts`,
    see pour_rects), PCBSAVE doc. planes ({net: "mid1" | "mid2"}, a 4 layer board): one POLY per net on its inner layer, over the whole box
    less the keep-outs of the same kind (a plane has no copper in an antenna keep-out either), after the tracks and vias."""
    d = str(pcb)
    cmds = [("ROUTEBEGIN", d, "1" if replace else "0")]
    for it in items:
        if it["kind"] == "track":
            cmds.append(("TRACK", d, "top" if it["layer"] == 1 else "bottom", f"{it['x1']:.4f}", f"{it['y1']:.4f}", f"{it['x2']:.4f}",
                         f"{it['y2']:.4f}", f"{it['width']:g}", it["net"]))
        else:
            cmds.append(("VIA", d, f"{it['x']:.4f}", f"{it['y']:.4f}", f"{it['dia']:g}", f"{it['hole']:g}", it["net"]))
    if pour_net and box:
        for r in (pour_rects(box, keepouts, edge) if keepouts else [[box[0] + edge, box[1] + edge, box[2] - edge, box[3] - edge]]):
            cmds.append(("POLY", d, "bottom", pour_net, f"{r[0]:.4f}", f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:.4f}"))
    if planes and box:
        for net, layer in sorted(planes.items(), key=lambda kv: (kv[1], kv[0])):
            for r in pour_rects(box, keepouts, edge) if keepouts else [[box[0] + edge, box[1] + edge, box[2] - edge, box[3] - edge]]:
                cmds.append(("POLY", d, layer, net, f"{r[0]:.4f}", f"{r[1]:.4f}", f"{r[2]:.4f}", f"{r[3]:.4f}"))
    cmds.append(("PCBSAVE", d))
    return cmds


PLANE_LAYERS = ("mid1", "mid2")        # the inner copper layers of the 4 layer stack: Mid-Layer 1 (ground) and Mid-Layer 2 (the main supply)
PLANE_CODES = {"mid1": 2, "mid2": 3}   # their Altium layer codes


def plane_nets_for(doc, rules=None):
    """{net: "mid1" | "mid2"} for a 4 layer board: the ground net (pour_net_for: a ground-named net of at least 3 pads) is the plane on
    the first inner layer, the main supply (the rail-named net, not ground, with the most pads, at least 3) the plane on the second.
    A board with no such net gets the planes it has; none is invented."""
    cnt = {}
    for p in doc.get("pads", []):
        if p.get("net") and p.get("ref"):
            cnt[p["net"]] = cnt.get(p["net"], 0) + 1
    out = {}
    g = pour_net_for(doc, rules)
    if g:
        out[g] = PLANE_LAYERS[0]
    rails = sorted((n for n in cnt if _RAIL.match(n) and not _is_gnd(n) and cnt[n] >= 3 and n != g), key=lambda n: (-cnt[n], n))
    if rails:
        out[rails[0]] = PLANE_LAYERS[1]
    return out


def pour_net_for(doc, rules=None):
    """The ground net to pour on the bottom layer: a ground-named net with at least 3 pads, else None."""
    cnt = {}
    for p in doc.get("pads", []):
        if p.get("net") and p.get("ref"):
            cnt[p["net"]] = cnt.get(p["net"], 0) + 1
    gnds = sorted((n for n in cnt if _is_gnd(n) and cnt[n] >= 3), key=lambda n: (-cnt[n], n))
    return gnds[0] if gnds else None


# ---- an independent check of what the router drew (exact geometry, not the grid it searched on)

class _Index:
    """A uniform grid over boxes (x0, y0, x1, y1): which of them can be within reach of a query box. Only a way to skip the exact
    distance test for what is far away; the test itself is unchanged."""
    CELL = 2.0

    def __init__(self, boxes):
        self.boxes = boxes
        self.cells = {}
        c = self.CELL
        for k, bx in enumerate(boxes):
            for ix in range(int(bx[0] // c), int(bx[2] // c) + 1):
                for iy in range(int(bx[1] // c), int(bx[3] // c) + 1):
                    self.cells.setdefault((ix, iy), []).append(k)

    def near(self, q):
        """Indices (ascending) of the boxes that overlap the query box q."""
        c = self.CELL
        seen = set()
        for ix in range(int(q[0] // c), int(q[2] // c) + 1):
            for iy in range(int(q[1] // c), int(q[3] // c) + 1):
                seen.update(self.cells.get((ix, iy), ()))
        out = []
        for k in sorted(seen):
            bx = self.boxes[k]
            if bx[0] <= q[2] and bx[2] >= q[0] and bx[1] <= q[3] and bx[3] >= q[1]:
                out.append(k)
        return out


def _violations(shapes, items, rules, box, nets=None):
    """[(message, (nets involved))] of the clearance, edge and via-in-pad problems of `items` against the fixed copper `shapes` and
    each other, by exact geometry. Same net copper may touch. nets: only the problems that involve one of these nets are looked for
    (the answer is the same as filtering the full list, found faster)."""
    out = []
    clear, edge = rules["clearance"], rules["edge"]
    via_r = rules["via_dia"] / 2
    tracks = [i for i in items if i["kind"] == "track"]
    vias = [i for i in items if i["kind"] == "via"]
    lay = {1: TOP, 32: BOT}
    want = (lambda a, b: True) if nets is None else (lambda a, b: a in nets or b in nets)
    sh_idx = _Index([_bbox(sh["geo"]) for sh in shapes])
    pad = clear + 0.01                                           # the reach of a clearance test beyond the copper itself
    tb = [(min(t["x1"], t["x2"]) - t["width"] / 2, min(t["y1"], t["y2"]) - t["width"] / 2,
           max(t["x1"], t["x2"]) + t["width"] / 2, max(t["y1"], t["y2"]) + t["width"] / 2) for t in tracks]
    tr_idx = _Index(tb)
    for t, bb in zip(tracks, tb):
        a, b, hw = (t["x1"], t["y1"]), (t["x2"], t["y2"]), t["width"] / 2
        for x, y in (a, b):
            if x - hw < box[0] + edge - 1e-3 or x + hw > box[2] - edge + 1e-3 or y - hw < box[1] + edge - 1e-3 or y + hw > box[3] - edge + 1e-3:
                if want(t["net"], t["net"]):
                    out.append((f"track of {t['net']} at ({x:.2f}, {y:.2f}) is closer than {edge:g} mm to the board edge", (t["net"],)))
        for k in sh_idx.near((bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad)):
            sh = shapes[k]
            if sh["net"] != t["net"] and lay[t["layer"]] in sh["layers"] and want(t["net"], sh["net"]):
                d = _dist(sh["geo"], a, b) - hw
                if d < clear - 1e-3:
                    out.append((f"track of {t['net']} near {sh['kind']} {sh['tag']} ({sh['net'] or 'no net'}): {d:.3f} mm < {clear:g} mm",
                                (t["net"], sh["net"])))
    for i, (t, bb) in enumerate(zip(tracks, tb)):
        for j in tr_idx.near((bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad)):
            if j <= i:
                continue
            u = tracks[j]
            if t["net"] != u["net"] and t["layer"] == u["layer"] and want(t["net"], u["net"]):
                d = _seg_seg((t["x1"], t["y1"]), (t["x2"], t["y2"]), (u["x1"], u["y1"]), (u["x2"], u["y2"])) - (t["width"] + u["width"]) / 2
                if d < clear - 1e-3:
                    out.append((f"tracks of {t['net']} and {u['net']} are {d:.3f} mm apart (< {clear:g} mm)", (t["net"], u["net"])))
    for v in vias:
        r = v["dia"] / 2
        p = (v["x"], v["y"])
        if v["x"] - r < box[0] + edge - 1e-3 or v["x"] + r > box[2] - edge + 1e-3 or v["y"] - r < box[1] + edge - 1e-3 or v["y"] + r > box[3] - edge + 1e-3:
            if want(v["net"], v["net"]):
                out.append((f"via of {v['net']} at ({v['x']:.2f}, {v['y']:.2f}) is closer than {edge:g} mm to the board edge", (v["net"],)))
        q = (p[0] - r - pad, p[1] - r - pad, p[0] + r + pad, p[1] + r + pad)
        for k in sh_idx.near(q):
            sh = shapes[k]
            d = _dist(sh["geo"], p, p) - r
            if sh["smd"] and d < clear - 1e-3:                       # via-in-pad is never allowed, whatever the net
                if want(v["net"], sh["net"]):
                    out.append((f"via of {v['net']} at ({v['x']:.2f}, {v['y']:.2f}) is in or too near SMD pad {sh['tag']}", (v["net"], sh["net"])))
            elif sh["net"] != v["net"] and d < clear - 1e-3 and want(v["net"], sh["net"]):
                out.append((f"via of {v['net']} near {sh['kind']} {sh['tag']} ({sh['net'] or 'no net'})", (v["net"], sh["net"])))
        for j in tr_idx.near(q):
            t = tracks[j]
            if t["net"] != v["net"] and want(v["net"], t["net"]) and \
                    _pt_seg(v["x"], v["y"], t["x1"], t["y1"], t["x2"], t["y2"]) < clear + r + t["width"] / 2 - 1e-3:
                out.append((f"via of {v['net']} near a track of {t['net']}", (v["net"], t["net"])))
        for u in vias:
            if u is not v and u["net"] != v["net"] and want(v["net"], u["net"]) and \
                    math.hypot(u["x"] - v["x"], u["y"] - v["y"]) < clear + r + u["dia"] / 2 - 1e-3:
                out.append((f"vias of {v['net']} and {u['net']} are too close", (v["net"], u["net"])))
    return out


def violations(doc, items, rules, box):
    """Clearance, edge and via-in-pad problems of `items` (as plan_routes returns them) against the fixed copper of `doc` (pads,
    footprint copper, fills, regions, tracks, unplated holes, keep-out) and each other, by exact geometry. Strings; empty = the copper
    keeps the rules. Same net copper may touch."""
    return [m for m, _ in _violations(fixed_shapes(doc, rules), items, rules, box)]


# ---------------------------------------------------------------- what this router does not do: said before anything is drawn

FINE_PITCH_MM = 0.4          # nearest pad of another net, centre to centre, below which the escape is not supported (grid 0.1 mm)
MAX_CELLS = 4_000_000        # grid cells per layer the search can hold in the time it gets (about 200 x 200 mm at 0.1 mm)
_INNER_COPPER = set(range(2, 32)) | set(range(39, 55))      # Altium layer codes: mid layers and internal planes
_NOT_SUPPORTED_RULES = {"MaxMinImpedance": "impedance control", "MatchedLengths": "length matching", "Length": "a length limit",
                        "MaxMinLength": "a length limit"}
HAND = "route these by hand or with Altium's interactive router (Route > Interactive Routing), then check with the design rule check"


def _is_bga(pads):
    """True when the SMD pads of one part form an area array. Only pads of the part's most common pad size count (a QFN's exposed pad,
    also one split into a grid of copper pads, is another size): a pad of that size with a same-size neighbour at the pitch on all
    four sides is an interior ball, and at least 2 such pads are needed. A dual or quad row, or a QFN, has none."""
    sized = [(round(p.get("sx_mm") or 0, 2), round(p.get("sy_mm") or 0, 2), p["x_mm"], p["y_mm"]) for p in pads
             if p.get("x_mm") is not None and p.get("y_mm") is not None]
    if len(sized) < 9:
        return False
    sizes = {}
    for sx, sy, _, _ in sized:
        sizes[(sx, sy)] = sizes.get((sx, sy), 0) + 1
    common = max(sizes, key=lambda k: (sizes[k], k))
    pts = [(x, y) for sx, sy, x, y in sized if (sx, sy) == common]
    if len(pts) < 9:
        return False
    d = min((math.hypot(a - x, b - y) for i, (x, y) in enumerate(pts) for a, b in pts[i + 1:]), default=0)
    if d < 0.2:
        return False
    tol = 0.15 * d

    def has(x, y, dx, dy):
        return any(abs(a - (x + dx)) < tol and abs(b - (y + dy)) < tol for a, b in pts)
    interior = sum(1 for x, y in pts if has(x, y, d, 0) and has(x, y, -d, 0) and has(x, y, 0, d) and has(x, y, 0, -d))
    return interior >= 2


def capability_check(doc, rules=None, box=None, pitch=0.1, warnings=None, layers=2):
    """What the router cannot do on this board, said BEFORE routing: a list of plain texts (empty = nothing found that it cannot do;
    it never means the board is routable). Each text says what to do instead. Only what is certain from the file is refused:
    copper on an inner layer (more than 2 layers), an area array (BGA), pads closer than FINE_PITCH_MM between nets, an enabled
    impedance / length-matching / length rule on nets other than the USB pair, and a board of more than MAX_CELLS grid cells.
    A rule whose scope cannot be resolved to nets (a net class, a differential pair, any other expression) is no refusal: a text
    "not checked, verify the rule by hand" is appended to `warnings` (a list, when given). layers=4: the pours on the two inner layers
    (what this tool drew before) are no refusal; any other copper there is."""
    out = []
    doc = doc or {}
    plane_codes = set(PLANE_CODES.values()) if layers == 4 else set()
    inner = sorted({o.get("layer") for k in ("pads", "tracks", "arcs", "vias", "fills", "regions") for o in doc.get(k, [])
                    if isinstance(o, dict) and o.get("layer") in _INNER_COPPER and not o.get("in_component")
                    and not (o.get("layer") in plane_codes and k == "regions" and o.get("polygon"))})
    if inner:
        out.append(f"the board has copper on inner layers (layer codes {', '.join(map(str, inner))}): this router draws two copper layers only; {HAND}")
    by_ref = {}
    for p in doc.get("pads", []):
        if p.get("layer") in (1, 32) and not (p.get("hole_mm") or 0) and p.get("ref"):
            by_ref.setdefault(p["ref"], []).append(p)
    bga = sorted(r for r, ps in by_ref.items() if _is_bga(ps))
    if bga:
        out.append(f"{', '.join(bga[:6])} is a BGA (a ball grid): the inner balls cannot be reached on two layers without microvias or "
                   f"a fan-out this router does not do; {HAND}")
    fine = []
    for r, ps in by_ref.items():
        if r in bga:
            continue
        nets = [p for p in ps if p.get("net") and p.get("x_mm") is not None]
        for i, a in enumerate(nets):
            if any(a["net"] != b["net"] and math.hypot(a["x_mm"] - b["x_mm"], a["y_mm"] - b["y_mm"]) < FINE_PITCH_MM - 1e-4
                   for b in nets[i + 1:]):
                fine.append(r)
                break
    if fine:
        out.append(f"{', '.join(sorted(fine)[:6])} has pads closer than {FINE_PITCH_MM:g} mm between different nets: that is finer than the "
                   f"{pitch:g} mm grid of this router can escape; {HAND}")
    usb = set()
    try:
        from . import pair as _pair
        usb = {n for p, m, _ in _pair.find_pairs(doc) for n in (p, m)}
    except Exception:                                    # no pair knowledge: every rule net counts as not the pair (stricter)
        pass
    for r in doc.get("rules", []):
        what = _NOT_SUPPORTED_RULES.get(r.get("RULEKIND"))
        if not what or str(r.get("ENABLED", "TRUE")).upper() != "TRUE":
            continue
        scope = str(r.get("SCOPE1EXPRESSION", "")).strip()
        nets = set(_INNET.findall(scope))
        if nets and nets <= usb:
            continue
        if not nets and scope.lower() != "all":      # a net class, a differential pair, ...: which nets it covers is not known here
            if warnings is not None:
                warnings.append(f"rule '{r.get('NAME') or r.get('RULEKIND')}' ({what}) has a scope this tool cannot resolve to nets "
                                f"({scope or 'empty'}): not checked, verify the rule by hand (the router does not control {what} except on the USB pair)")
            continue
        out.append(f"the board has an enabled rule '{r.get('NAME') or r.get('RULEKIND')}' for {what}: the router only couples and length-matches the "
                   f"USB D+/D- pair and does not control impedance or length elsewhere; {HAND}, or disable the rule if it is not needed")
    if box is not None and pitch > 0:
        cells = (int((box[2] - box[0]) / pitch) + 1) * (int((box[3] - box[1]) / pitch) + 1)
        if cells > MAX_CELLS:
            out.append(f"the board is {box[2] - box[0]:.0f} x {box[3] - box[1]:.0f} mm: too large for the time this router gets "
                       f"({cells / 1e6:.1f} million grid cells per layer, the limit is {MAX_CELLS / 1e6:.0f} million); {HAND}")
    return out
