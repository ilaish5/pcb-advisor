"""Negotiated-congestion routing for dense boards (PathFinder style), used by route.plan_routes. Pure Python, no Altium.

Every net is first routed as if it were alone; tracks may then overlap those of other nets at a price. Each round the nets that overlap
are routed again while the price of an overlap rises and the cells that were fought over keep a history cost, until no two nets are
closer than the clearance. What is still contested when the budget ends is taken off, tried once more around what is left, and
reported with the nets it would have to cross. It differs from the greedy router (route.Router) in three ways that matter on a dense
board: obstacles are measured exactly from the grid points (no sampling growth, so a fine pitch row can be escaped), a pad that cannot
take its net's width is entered by a short narrower neck, and a 4 layer board has a third routing layer, Mid-Layer 2, used after the
outer two, with the supply poured around the tracks there (Mid-Layer 1 stays a solid ground plane).

  plan(doc, box, rules, ...)      the same result dict as route.plan_routes
"""
import heapq
import math
import time

from . import route as R

SQ2 = math.sqrt(2)
M = 12                    # cells of blocked border round the grid: no stamp or step leaves the arrays
EPS = 0.008               # mm: the most a 45 degree run between two grid points dips under the distance measured at the points
MID = 2                   # layer index of Mid-Layer 2 (a 4 layer board)
LAYER_CODE = {R.TOP: 1, R.BOT: 32, MID: 3}
LAYER_MULT = {R.TOP: 1.0, R.BOT: 1.02, MID: 1.8}        # cost of a step per layer: Mid-Layer 2 only after top and bottom
POUR_BOT_MULT = 1.25      # ... and the bottom layer when it carries the ground pour: tracks there cut the pour
VIA_COST = 12.0           # grid steps
THT_COST = 2.0
TURN_45, TURN_90 = 0.3, 0.7
GREED = 1.2               # weight of the heuristic: a slightly longer track for far fewer cells searched
PRES_FIRST, PRES_GROW, PRES_MAX = 0.6, 1.5, 400.0
HIST_STEP = 0.8
ROUNDS_MAX = 90           # negotiation rounds at most
EXPANSIONS = 120_000_000  # cells all searches together may expand: the deterministic limit (the clock is a safety cap)
STALL = 25                # rounds without fewer overlapping nets before giving up on negotiation
NECK_MIN = 0.127          # JLC's narrowest track, mm; a neck is never narrower than this nor than the board's width rule allows
WINDOW_MM = 7.0           # a search is first held to this far round its ends
NECK_COST = 1.3           # cost factor of a necked step: the full width wherever it fits


class _Net:
    def __init__(self, name, nid):
        self.name, self.nid = name, nid
        self.pads = []
        self.width = self.neck = None
        self.zone = None                # per layer bytearray: cells where the neck width may be used
        self.kind = "tracks"            # tracks | drop (each pad to a plane or pour by a via)
        self.paths = []                 # [[(l, i)]]
        self.vias = []                  # cells
        self.stamp = None               # [(array, set)] added to the congestion counts
        self.joined = ""                # "a to b" of the connection that failed
        self.why = None
        self.hist_key = 0
        self.tied = []                  # [(cells set, (tag, tag))] copper laid before routing that joins two pads
        self.plane_layer = None         # drop nets: the layer of the pour (None: a solid inner plane that no track enters)
        self.options = []               # [(width, neck width or None)] to try, in order


class Negotiator:
    def __init__(self, doc, box, rules, pitch, layers, widths, deadline, fixed_items=()):
        """widths: every full width a net may be drawn at, mm; fixed_items: copper laid before routing (a coupled pair, connector
        ties), as route items."""
        self.g, self.box, self.rules = pitch, box, rules
        self.x0, self.y0 = box[0], box[1]
        self.nx, self.ny = int((box[2] - box[0]) / pitch) + 1, int((box[3] - box[1]) / pitch) + 1
        self.L = layers
        self.clear = rules["clearance"]
        self.via_r = rules["via_dia"] / 2
        self.deadline = deadline
        self.spent = 0
        self._work = None
        self.cap = EXPANSIONS
        mn = max(NECK_MIN, rules.get("width_min") or rules["width"])
        self.neck_widths = sorted({w for w in (rules["width"], mn) if w >= mn - 1e-9}, reverse=True)
        self.shapes = R.fixed_shapes(doc, rules)
        self.nets = {}
        names = sorted({s["net"] for s in self.shapes if s["net"]})
        self.nid = {n: k for k, n in enumerate(names)}
        classes = {round(w, 4) for w in widths} | {round(w, 4) for w in self.neck_widths} | {round(R.POUR_NECK, 4)}
        self.halves = {w: w / 2 for w in sorted(classes)}
        self.halves["via"] = self.via_r
        self.M = max(M, int((self.clear + 2 * max(self.halves.values()) + EPS) / pitch) + 2)      # no stamp reaches past the border
        self.H = self.ny + 2 * self.M
        self.N = (self.nx + 2 * self.M) * self.H
        self._offs = {}
        self.fixed_items = list(fixed_items)
        self._build_fixed()
        self._build_pads()
        size = self.N
        self.cnt = {c: [bytearray(size) for _ in range(1 if c == "via" else layers)] for c in self.halves}
        self.hist = [[0.0] * size for _ in range(layers)]
        self.vhist = [0.0] * size

    # ---- grid
    def idx(self, ix, iy):
        return (ix + self.M) * self.H + iy + self.M

    def xy(self, i):
        a, b = divmod(i, self.H)
        return self.x0 + (a - self.M) * self.g, self.y0 + (b - self.M) * self.g

    def cell_of(self, x, y):
        ix, iy = round((x - self.x0) / self.g), round((y - self.y0) / self.g)
        return self.idx(max(0, min(self.nx - 1, ix)), max(0, min(self.ny - 1, iy)))

    def offs(self, r):
        """Flat index offsets of the cells nearer than r mm."""
        k = round(r * 10000)
        o = self._offs.get(k)
        if o is None:
            m = min(self.M - 1, int(r / self.g) + 1)
            o = self._offs[k] = [dx * self.H + dy for dx in range(-m, m + 1) for dy in range(-m, m + 1) if math.hypot(dx, dy) * self.g < r]
        return o

    def _cells_near(self, geo, r):
        """(cell, distance) of the grid points nearer than r to the shape."""
        g = self.g
        b = R._bbox(geo)
        ix0, ix1 = max(int((b[0] - r - self.x0) / g) - 1, 0), min(int((b[2] + r - self.x0) / g) + 2, self.nx - 1)
        iy0, iy1 = max(int((b[1] - r - self.y0) / g) - 1, 0), min(int((b[3] + r - self.y0) / g) + 2, self.ny - 1)
        kind = geo[0]
        for ix in range(ix0, ix1 + 1):
            x = self.x0 + ix * g
            base = (ix + self.M) * self.H + self.M
            for iy in range(iy0, iy1 + 1):
                y = self.y0 + iy * g
                if kind == "rect":
                    q = geo[1]
                    d = math.hypot(max(q[0] - x, 0, x - q[2]), max(q[1] - y, 0, y - q[3]))
                else:
                    d = R._dist(geo, (x, y), (x, y))
                if d < r:
                    yield base + iy, d

    # ---- fixed copper
    def _layers_of(self, s):
        return tuple(range(self.L)) if len(s["layers"]) == 2 else s["layers"]

    def _build_fixed(self):
        """fix[class][layer] = (occupied bytearray, {net id: cells only that net may use}); fix["via"] has one layer."""
        own = {c: [dict() for _ in range(1 if c == "via" else self.L)] for c in self.halves}
        rmax = self.clear + max(self.halves.values()) + EPS

        def mark(d, j, owner):
            cur = d.get(j)
            if cur is None:
                d[j] = owner
            elif cur != owner:
                d[j] = -2

        shapes = list(self.shapes)
        for it in self.fixed_items:
            if it["kind"] == "via":
                shapes.append({"net": it["net"], "layers": (R.TOP, R.BOT), "geo": ("circ", (it["x"], it["y"]), it["dia"] / 2), "smd": False,
                               "kind": "copper"})
            else:
                lay = {1: (R.TOP,), 32: (R.BOT,), 3: (MID,)}[it["layer"]]
                shapes.append({"net": it["net"], "layers": lay, "smd": False, "kind": "copper",
                               "geo": ("seg", (it["x1"], it["y1"]), (it["x2"], it["y2"]), it["width"] / 2)})
        classes = [(c, self.clear + h + EPS) for c, h in self.halves.items() if c != "via"]
        vr = self.clear + self.via_r + EPS
        for s in shapes:
            owner = -2 if not s["net"] else self.nid.setdefault(s["net"], len(self.nid))
            layers = self._layers_of(s)
            smd = s["kind"] == "pad" and s["smd"]
            tht = s["kind"] == "pad" and not s["smd"]
            for j, d in self._cells_near(s["geo"], rmax):
                for c, r in classes:
                    if d < r:
                        for l in layers:
                            mark(own[c][l], j, owner)
                if d < vr:      # never a via in or near an SMD pad, and no second hole at a through hole pad, whatever the net
                    mark(own["via"][0], j, -2 if (smd or tht) else owner)
        # board edge
        for c, h in self.halves.items():
            e = self.rules["edge"] + h + 1e-4
            xs = [ix for ix in range(self.nx) if ix * self.g < e - 1e-9 or ix * self.g > self.box[2] - self.box[0] - e + 1e-9]
            ys = [iy for iy in range(self.ny) if iy * self.g < e - 1e-9 or iy * self.g > self.box[3] - self.box[1] - e + 1e-9]
            for d in own[c]:
                for ix in xs:
                    for iy in range(self.ny):
                        d[self.idx(ix, iy)] = -2
                for iy in ys:
                    for ix in range(self.nx):
                        d[self.idx(ix, iy)] = -2
        border = bytearray(b"\x01") * self.N
        for ix in range(self.nx):
            o = self.idx(ix, 0)
            border[o:o + self.ny] = bytes(self.ny)
        self.fix = {}
        for c, per_layer in own.items():
            self.fix[c] = []
            for d in per_layer:
                occ = bytearray(border)
                mine = {}
                for j, o in d.items():
                    occ[j] = 1
                    if o != -2:
                        mine.setdefault(o, []).append(j)
                self.fix[c].append((occ, mine))

    def blocked(self, c, l, nid):
        occ, mine = self.fix[c][l]
        b = bytearray(occ)
        for j in mine.get(nid, ()):
            b[j] = 0
        return b

    # ---- pads
    def _build_pads(self):
        self.pads = {}
        for s in self.shapes:
            if s["kind"] != "pad" or not s["net"]:
                continue
            p, rect = s["pad"], s["geo"][1]
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            ha, hb = max((rect[2] - rect[0]) / 2, 1e-6), max((rect[3] - rect[1]) / 2, 1e-6)
            ix0, iy0 = math.ceil((rect[0] - self.x0) / self.g - 1e-6), math.ceil((rect[1] - self.y0) / self.g - 1e-6)
            ix1, iy1 = math.floor((rect[2] - self.x0) / self.g + 1e-6), math.floor((rect[3] - self.y0) / self.g + 1e-6)
            inside = []
            for ix in range(max(ix0, 0), min(ix1, self.nx - 1) + 1):
                for iy in range(max(iy0, 0), min(iy1, self.ny - 1) + 1):
                    x, y = self.x0 + ix * self.g, self.y0 + iy * self.g
                    if R._round_pad(p) and ((x - cx) / ha) ** 2 + ((y - cy) / hb) ** 2 > 0.64 + 1e-9:
                        continue
                    inside.append(self.idx(ix, iy))
            if min(float(p.get("rot") or 0) % 90, 90 - float(p.get("rot") or 0) % 90) > 0.5:
                # a pad at an angle: the rectangle round it is mostly not copper, so a track ends only near the centre
                r = 0.4 * min(p.get("sx_mm") or 0, p.get("sy_mm") or 0)
                inside = [i for i in inside if math.hypot(self.xy(i)[0] - p["x_mm"], self.xy(i)[1] - p["y_mm"]) <= r]
            stub = not inside
            if stub:
                inside = [self.cell_of(p["x_mm"], p["y_mm"])]
            layers = self._layers_of(s)
            self.pads.setdefault(s["net"], []).append({"tag": s["tag"], "x": p["x_mm"], "y": p["y_mm"], "rect": rect, "cells": inside,
                                                       "layers": layers, "stub": stub, "tht": len(s["layers"]) == 2})

    # ---- the cells one net holds
    def zone_for(self, net, pads):
        """Per layer, the cells round the SMD pads where this net may be narrower: within NECK_MAX of the pad."""
        zone = [bytearray(self.N) for _ in range(self.L)]
        for p in pads:
            if p["tht"]:
                continue
            for j, _d in self._cells_near(("rect", p["rect"]), R.NECK_MAX):
                zone[p["layers"][0]][j] = 1
        return zone

    def width_at(self, net, blk_wide, l, i):
        """The width the net has at the cell: necked only inside its zone and only where fixed copper leaves no room for the full one."""
        return net.neck if net.zone is not None and net.zone[l][i] and blk_wide[l][i] else net.width

    def masks(self, net, margin=0.0):
        """(wide, use): per layer the cells blocked at the full width and the cells blocked for the search (neck width in the zone)."""
        c = round(net.width, 4)
        wide = [self.blocked(c, l, net.nid) for l in range(self.L)]
        if net.zone is None:
            return wide, wide
        n = round(net.neck, 4)
        use = []
        for l in range(self.L):
            narrow = self.blocked(n, l, net.nid)
            u = bytearray(wide[l])
            z = net.zone[l]
            j = z.find(1)
            while j >= 0:
                u[j] = narrow[j]
                j = z.find(1, j + 1)
            use.append(u)
        return wide, use

    # ---- congestion bookkeeping
    def occupy(self, net, wide):
        """Add the net's copper to the congestion counts: for every class c the cells a centre of class c may not use because of it."""
        sets = {c: [set() for _ in range(len(a))] for c, a in self.cnt.items()}
        for path in net.paths:
            for l, i in path:
                h = self.width_at(net, wide, l, i) / 2
                for c, hc in self.halves.items():
                    o = self.offs(self.clear + h + hc + EPS)
                    sets[c][0 if c == "via" else l].update(map(i.__add__, o))
        for i in net.vias:
            for c, hc in self.halves.items():
                o = self.offs(self.clear + self.via_r + hc + EPS)
                cells = list(map(i.__add__, o))
                for s in sets[c]:
                    s.update(cells)
        net.stamp = [(self.cnt[c][l], s) for c, per in sets.items() for l, s in enumerate(per) if s]
        for arr, s in net.stamp:
            for j in s:
                arr[j] += 1

    def release(self, net):
        if net.stamp:
            for arr, s in net.stamp:
                for j in s:
                    arr[j] -= 1
        net.stamp = None

    def clashes(self, net, wide):
        """The cells of the net's own copper that another net's copper is too close to: [(layer, cell)], vias as ("v", cell)."""
        out = []
        cw = self.cnt[round(net.width, 4)]
        cn = self.cnt[round(net.neck, 4)] if net.zone is not None else cw
        for path in net.paths:
            for l, i in path:
                a = cn if net.zone is not None and net.zone[l][i] and wide[l][i] else cw
                if a[l][i] > 1:
                    out.append((l, i))
        v = self.cnt["via"][0]
        out += [("v", i) for i in net.vias if v[i] > 1]
        return out

    # ---- search
    def search(self, net, wide, use, sources, goals, pres, hard=False, via_goal=False, window=True):
        """Cheapest path from the source states to a goal state. States are layer * N + cell. via_goal: a cell where a via may stand
        ends the search (the path then has the via there). Returns the [(layer, cell)] path or None (self.status says why). The search
        is first held to a window round the sources and goals, and only when that has no way is the whole board searched."""
        if window:
            N, H = self.N, self.H
            ks = list(goals) if goals else []
            ks += list(sources) if not goals or len(sources) < 64 else []
            if ks:
                if goals and len(sources) >= 64:             # a big tree: the part of it nearest the goal is what matters
                    ga, gb = divmod(next(iter(goals)) % N, H)
                    near = min(sources, key=lambda k: (abs((k % N) // H - ga) + abs((k % N) % H - gb), k))
                    ks.append(near)
                a = [(k % N) // H for k in ks]
                b = [(k % N) % H for k in ks]
                m = int(WINDOW_MM / self.g) + (max(a) - min(a) + max(b) - min(b)) // 5
                a0, a1, b0, b1 = max(min(a) - m, 0), max(a) + m + 1, max(min(b) - m, 0), min(max(b) + m + 1, H)
                if (a1 - a0) * (b1 - b0) < 0.7 * self.nx * self.ny:
                    shut = []
                    for u in use:
                        w = bytearray(b"\x01") * N
                        for x in range(a0, min(a1, N // H)):
                            o = x * H
                            w[o + b0:o + b1] = u[o + b0:o + b1]
                        shut.append(w)
                    path = self._astar(net, wide, shut, sources, goals, pres, hard, via_goal)
                    if path is not None or self.status in ("time", "budget"):
                        return path
        return self._astar(net, wide, use, sources, goals, pres, hard, via_goal)

    def _astar(self, net, wide, use, sources, goals, pres, hard, via_goal):
        N, H = self.N, self.H
        L = self.L
        vblk = self.blocked("via", 0, net.nid)
        vcnt = self.cnt["via"][0]
        vhist = self.vhist
        c = round(net.width, 4)
        cw = self.cnt[c]
        cn = self.cnt[round(net.neck, 4)] if net.zone is not None else cw
        zone = net.zone
        mult = self.mult
        hist = self.hist
        tht = set()
        for p in self.pads.get(net.name, ()):
            if p["tht"]:
                tht.update(p["cells"])
        own_vias = set(net.vias)
        gap = int(math.ceil((self.rules["via_dia"] + 0.02) / self.g))
        gap2 = (self.rules["via_dia"] + 0.02) ** 2 / self.g ** 2
        for v in own_vias:                    # a second via of the same net stands on the first one or clear of it (hole to hole)
            for dx in range(-gap, gap + 1):
                for dy in range(-gap, gap + 1):
                    if (dx or dy) and dx * dx + dy * dy < gap2:
                        j = v + dx * H + dy
                        if j not in own_vias:
                            vblk[j] = 1

        if goals:
            gxs = [(k % N) // H for k in goals]
            gys = [(k % N) % H for k in goals]
            gx0, gx1, gy0, gy1 = min(gxs), max(gxs), min(gys), max(gys)
        else:
            gx0, gx1, gy0, gy1 = 0, N, 0, H                  # no goal cells: the heuristic is zero everywhere
        wd, wg = GREED, GREED * (SQ2 - 2)
        dirs = [(d, dx * H + dy, SQ2 if dx and dy else 1.0) for d, (dx, dy) in enumerate(R.DIRS)]
        turns = []                                            # turns[came][dir]: the cost of the turn, None when sharper than 90 degrees
        for came_ in range(9):
            row = []
            for nd in range(8):
                t = 0 if came_ == 8 else min((came_ - nd) % 8, (nd - came_) % 8)
                row.append(0.0 if t == 0 else TURN_45 if t == 1 else TURN_90 if t == 2 else None)
            turns.append([(row[nd], nd, dj, step) for nd, dj, step in dirs if row[nd] is not None])
        SINK = L * N
        best, par, came, lastv = self._arrays()
        touched = []
        heap = []
        for k in sources:
            best[k] = 0.0
            came[k] = 8
            par[k] = -1
            lastv[k] = -1
            touched.append(k)
            heap.append((0.0, 0.0, k))
        heapq.heapify(heap)
        push, pop = heapq.heappush, heapq.heappop
        pops = 0
        limit = L * self.nx * self.ny
        self.status = "none"
        sink_cost, sink_cell = 1e18, None
        found = None

        while heap:
            _f, gc, k = pop(heap)
            if k == SINK:
                found = sink_cell
                break
            if gc > best[k] + 1e-9:
                continue
            if k in goals:
                found = k
                break
            pops += 1
            if not pops & 4095:
                if self.spent + pops > self.cap:
                    self.status = "budget"
                    break
                if R.late(self.deadline):
                    self.status = "time"
                    break
                if pops > limit:
                    self.status = "limit"
                    break
            l = k // N
            base = l * N
            i = k - base
            bl = use[l]
            hl = hist[l]
            ow = cw[l]
            nw = cn[l]
            z = zone[l] if zone is not None else None
            wl = wide[l]
            ml = mult[l]
            lv = lastv[k]
            for tc, nd, dj, step in turns[came[k]]:
                j = i + dj
                if bl[j]:
                    continue
                cost = step * ml * (1.0 + hl[j])
                if z is not None and z[j] and wl[j]:
                    o = nw[j]
                    cost *= NECK_COST
                else:
                    o = ow[j]
                if o:
                    if hard:
                        continue
                    cost *= 1.0 + pres * o
                cost += gc + tc
                nk = base + j
                if cost < best[nk]:
                    if best[nk] >= 1e18:
                        touched.append(nk)
                    best[nk] = cost - 1e-9
                    par[nk] = k
                    came[nk] = nd
                    lastv[nk] = lv
                    a = j // H
                    b = j % H
                    dx = gx0 - a if a < gx0 else a - gx1 if a > gx1 else 0
                    dy = gy0 - b if b < gy0 else b - gy1 if b > gy1 else 0
                    push(heap, (cost + wd * (dx + dy) + wg * (dx if dx < dy else dy), cost, nk))
            # a change of layer
            via = i not in tht
            if via:
                if vblk[i]:
                    continue
                if lv >= 0 and lv != i:
                    ax, ay = divmod(lv, H)
                    bx, by = divmod(i, H)
                    if (ax - bx) * (ax - bx) + (ay - by) * (ay - by) < gap2:
                        continue
                o = vcnt[i]
                if o and hard:
                    continue
                cost = gc + (THT_COST if i in own_vias else VIA_COST * (1.0 + vhist[i]) * (1.0 + pres * o))
                if via_goal:
                    if cost < sink_cost:
                        sink_cost, sink_cell = cost, k
                        push(heap, (cost, cost, SINK))
                    continue
            else:
                cost = gc + THT_COST
            a = i // H
            b = i % H
            dx = gx0 - a if a < gx0 else a - gx1 if a > gx1 else 0
            dy = gy0 - b if b < gy0 else b - gy1 if b > gy1 else 0
            f = cost + wd * (dx + dy) + wg * (dx if dx < dy else dy)
            for m in range(L):
                if m == l or use[m][i]:
                    continue
                if hard and cw[m][i]:
                    continue
                nk = m * N + i
                if cost < best[nk]:
                    if best[nk] >= 1e18:
                        touched.append(nk)
                    best[nk] = cost - 1e-9
                    par[nk] = k
                    came[nk] = 8
                    lastv[nk] = i if via else lv
                    push(heap, (f, cost, nk))
        self.spent += pops
        path = None
        if found is not None:
            k = found
            path = [(k // N, k % N)]
            while par[k] >= 0:
                k = par[k]
                path.append((k // N, k % N))
            path.reverse()
        for k in touched:
            best[k] = 1e18
        return path

    def _arrays(self):
        if self._work is None:
            n = self.L * self.N
            self._work = ([1e18] * n, [-1] * n, bytearray(n), [-1] * n)
        return self._work

    # ---- one net
    def pad_states(self, use, pad):
        N = self.N
        return [l * N + i for l in pad["layers"] for i in pad["cells"] if not use[l][i]]

    def route(self, net, pres, hard=False, keep=((), ())):
        """Route every connection of the net with the others' copper as it is counted now. Sets net.paths / net.vias; returns None or
        the reason. keep: (plane nets only) (paths, vias) of an earlier route: those paths stay as they are."""
        net.paths, net.vias = [], []
        self.status = "none"                 # why the last search stopped; a pad with no free cell stops before any search
        wide, use = self.masks(net)
        N = self.N
        pads = self.pads[net.name]
        if net.kind == "drop":
            return self._route_drops(net, wide, use, pres, hard, keep)
        first = pads[0]
        tree = set(self.pad_states(use, first))
        if not tree:
            return f"pad {first['tag']} is too close to other copper for a {net.neck or net.width:g} mm track"
        joined, todo = [first], pads[1:]
        by_tag = {p["tag"]: p for p in pads}

        def absorb(pad):
            for cells, tags in net.tied:
                if pad["tag"] in tags:
                    other = by_tag.get(tags[1] if tags[0] == pad["tag"] else tags[0])
                    if other in todo:
                        todo.remove(other)
                        tree.update(cells)
                        tree.update(self.pad_states(use, other))
                        joined.append(other)
        absorb(first)
        while todo:
            tgt = min(todo, key=lambda p: (min(abs(p["x"] - q["x"]) + abs(p["y"] - q["y"]) for q in joined), p["tag"]))
            todo.remove(tgt)
            goals = set(self.pad_states(use, tgt))
            net.joined = f"{joined[0]['tag']} to {tgt['tag']}"
            if not goals:
                return f"pad {tgt['tag']} is too close to other copper for a {net.neck or net.width:g} mm track"
            path = self.search(net, wide, use, tree, goals, pres, hard=hard)
            if path is None:
                return f"{self.why_stopped()} from {net.joined}"
            self._take(net, path)
            tree.update(l * N + i for l, i in path)
            tree.update(goals)
            joined.append(tgt)
            absorb(tgt)
        return None

    def _take(self, net, path):
        net.paths.append(path)
        tht = set()
        for p in self.pads[net.name]:
            if p["tht"]:
                tht.update(p["cells"])
        for a, b in zip(path, path[1:]):
            if a[0] != b[0] and b[1] not in tht and b[1] not in net.vias:
                net.vias.append(b[1])

    def why_stopped(self):
        return {"time": "ran out of time", "budget": "ran out of search budget", "limit": "search limit reached"}.get(self.status, "no way")

    def _route_drops(self, net, wide, use, pres, hard, keep=((), ())):
        """A plane net: every SMD pad that is not on the plane's own layer gets a short stub and a via."""
        N = self.N
        plane = net.plane_layer
        reached = set()                    # states of copper that is in the plane already: through hole pads, and (bottom pour) bottom pads
        for p in self.pads[net.name]:
            if p["tht"] or (plane is not None and p["layers"] == (plane,)):
                reached.update(l * N + i for l in p["layers"] for i in p["cells"])
        paths, old_vias = keep
        old_vias = set(old_vias)
        for path in paths:                       # a drop that stays: its path, and the via it ends on (its own or a shared one)
            self._take(net, path)
            end = path[-1][1]
            if end in old_vias:
                if end not in net.vias:
                    net.vias.append(end)
                reached.update(m * N + end for m in range(self.L))
        held = {path[0] for path in paths}
        for p in sorted(self.pads[net.name], key=lambda p: p["tag"]):
            if p["tht"] or (plane is not None and p["layers"] == (plane,)):
                continue
            if any((l, i) in held for l in p["layers"] for i in p["cells"]):
                continue
            src = self.pad_states(use, p)
            net.joined = f"{p['tag']} to the plane"
            if not src:
                return f"pad {p['tag']} is too close to other copper for a {net.neck or net.width:g} mm track"
            l = p["layers"][0]
            goals = {k for k in reached if k // N == l}
            path = self.search(net, wide, use, src, goals, pres, hard=hard, via_goal=True)
            if path is None:
                return f"{self.why_stopped()} from {p['tag']} to a via into the plane"
            end = path[-1]
            net.paths.append(path)
            if end[0] * N + end[1] not in reached:
                if end[1] not in net.vias:
                    net.vias.append(end[1])
                reached.update(m * N + end[1] for m in range(self.L))
        return None

    # ---- the negotiation
    def negotiate(self, nets, log=None):
        """nets: [_Net] in routing order. Routes them, resolves the overlaps; returns the number of rounds. Every net ends either with
        copper that overlaps no other net's, or with net.why."""
        live, wides = [], {}
        for net in nets:
            why = self._first(net, wides)
            if why:
                net.why = why
            else:
                live.append(net)
        pres = PRES_FIRST
        best, stall, rounds = None, 0, 0
        while rounds < ROUNDS_MAX:
            bad = [(n, self.clashes(n, wides[n.name])) for n in live]
            bad = [(n, c) for n, c in bad if c]
            score = (len(bad), sum(len(c) for _, c in bad))
            if log:
                log(rounds, score, self.spent)
            if best is None or score < best[0]:
                best = (score, {n.name: (list(n.paths), list(n.vias)) for n in live})
                stall = 0
            else:
                stall += 1
            if isinstance(self.deadline, R.Clock):
                self.deadline.note(self.done0 + len(live) - len(bad), phase=f"negotiated routing, round {rounds + 1}", fine=-score[1], work=self.spent)
            if not bad or stall > STALL or self.spent > self.cap or R.late(self.deadline):
                break
            rounds += 1
            for _n, cells in bad:
                for l, i in set(cells):
                    if l == "v":
                        self.vhist[i] += HIST_STEP
                    else:
                        self.hist[l][i] += HIST_STEP
            for net, _c in bad:
                if self.spent > self.cap or R.late(self.deadline):
                    break
                if not self.clashes(net, wides[net.name]):
                    continue
                old = (net.paths, net.vias)
                keep = ((), ())
                if net.kind == "drop":
                    bad_cells = set(self.clashes(net, wides[net.name]))
                    keep = ([p for p in net.paths if not any(c in bad_cells or ("v", c[1]) in bad_cells for c in p)], list(net.vias))
                self.release(net)
                if self.route(net, pres, keep=keep):
                    net.paths, net.vias = old
                self.occupy(net, wides[net.name])
            pres = min(PRES_MAX, pres * PRES_GROW)
        self._legalise(live, wides, best, rounds)
        return rounds

    def _first(self, net, wides):
        """The net routed with the others' copper only as a light price: finds the width (and neck) it can be drawn at at all."""
        why = None
        for width, neck in net.options:
            net.width, net.neck = width, neck
            net.zone = self.zone_for(net, self.pads[net.name]) if neck else None
            why = self.route(net, PRES_FIRST * 0.25)
            if why is None:
                wides[net.name] = self.masks(net)[0]
                self.occupy(net, wides[net.name])
                return None
            if self.status in ("time", "budget"):
                break
        net.paths, net.vias = [], []
        if self.status in ("time", "budget"):
            return why
        return why + ": blocked by fixed copper (pads, board edge, keep-out), not by other tracks"

    def _legalise(self, live, wides, best, rounds):
        def bad_now():
            return {n.name: c for n in live if n.stamp for c in [self.clashes(n, wides[n.name])] if c}

        bad = bad_now()
        if bad and best is not None and (len(bad), sum(map(len, bad.values()))) > best[0]:
            for n in live:
                self.release(n)
                n.paths, n.vias = list(best[1][n.name][0]), list(best[1][n.name][1])
                self.occupy(n, wides[n.name])
            bad = bad_now()
        off = []
        by_name = {n.name: n for n in live}
        while bad:                                   # take off the most contested net until nothing is too close to anything
            worst = max(bad, key=lambda m: (len(bad[m]), m))
            net = by_name[worst]
            self.release(net)
            net.paths, net.vias = [], []
            off.append(net)
            bad = bad_now()
        for net in sorted(off, key=lambda n: (len(self.pads[n.name]), R._hpwl(self.pads[n.name]), n.name)):
            why = self.route(net, 0.0, hard=True)
            if why is None:
                self.occupy(net, wides[net.name])
                continue
            joined = net.joined
            status = self.status
            net.paths, net.vias = [], []
            names = []
            if status not in ("time", "budget") and self.route(net, 2.0) is None:       # what would it have to cross?
                names = self._crossed(net, wides, live)
            net.paths, net.vias = [], []
            net.why = (f"{why}" if status in ("time", "budget") else
                       f"no way from {joined} without crossing the tracks of {', '.join(names[:6]) or 'other nets'}"
                       f" ({rounds} rounds of rip-up and reroute did not make room)")

    def _crossed(self, net, wides, live):
        """Names of the nets whose copper the net's (relaxed) paths are too close to."""
        mine = {}
        for path in net.paths:
            for l, i in path:
                mine.setdefault(l, set()).add(i)
        c = round(net.width, 4)
        out = []
        for other in live:
            if other is net or not other.stamp:
                continue
            for arr, s in other.stamp:
                hit = False
                for l in range(self.L):
                    if arr is self.cnt[c][l] and not s.isdisjoint(mine.get(l, ())):
                        hit = True
                if arr is self.cnt["via"][0] and not s.isdisjoint(net.vias):
                    hit = True
                if hit:
                    out.append(other.name)
                    break
        return sorted(out)

    # ---- items
    def items(self, net):
        """The net's copper as route items: runs per layer and width, collinear points merged; vias; stubs to pads too small to hold a
        grid point. Returns (items, necks)."""
        out = []
        wide = self.masks(net)[0]
        r4 = lambda v: round(v, 4)
        ends = {}
        for path in net.paths:
            pts = [(l, i, self.width_at(net, wide, l, i)) for l, i in path]
            for l, i, w in (pts[0], pts[-1]):
                ends.setdefault(i, (l, w))
            run = []
            for (al, ai, aw), (bl, bi, bw) in zip(pts, pts[1:]):
                if al != bl:
                    self._flush(net, run, out)
                    run = []
                    continue
                run.append((al, ai, bi, min(aw, bw)))
            self._flush(net, run, out)
        necks = self._necks(net, out)
        for p in self.pads[net.name]:
            if p["stub"] and p["cells"][0] in ends:
                l, w = ends[p["cells"][0]]
                x, y = self.xy(p["cells"][0])
                if math.hypot(x - p["x"], y - p["y"]) > 0.002:
                    out.append({"kind": "track", "layer": LAYER_CODE[l], "x1": r4(x), "y1": r4(y), "x2": p["x"], "y2": p["y"],
                                "width": w, "net": net.name})
        for i in net.vias:
            x, y = self.xy(i)
            out.append({"kind": "via", "x": r4(x), "y": r4(y), "dia": self.rules["via_dia"], "hole": self.rules["via_hole"], "net": net.name})
        return out, necks

    def _necks(self, net, tracks):
        """[{pad, width_mm, len_mm}]: the length of track drawn narrower than the net's width outside the pads, per nearest pad."""
        found = {}
        for t in tracks:
            if t["width"] >= net.width - 1e-9:
                continue
            length = math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"])
            n = max(1, int(length / (self.g / 2)))
            for k in range(n):
                f = (k + 0.5) / n
                q = (t["x1"] + (t["x2"] - t["x1"]) * f, t["y1"] + (t["y2"] - t["y1"]) * f)
                d, tag = min((R._dist(("rect", p["rect"]), q, q), p["tag"]) for p in self.pads[net.name])
                e = found.setdefault(tag, [t["width"], 0.0])
                e[0] = min(e[0], t["width"])
                if d > 0:
                    e[1] += length / n
        return [{"pad": tag, "width_mm": w, "len_mm": round(length, 2)} for tag, (w, length) in sorted(found.items())]

    def _flush(self, net, run, out):
        if not run:
            return
        l, start, prev, w = run[0]
        d = prev - start
        for _l, a, b, ww in run[1:]:
            if b - a != d or ww != w:
                self._segment(net, l, start, a, w, out)
                start, d, w = a, b - a, ww
            prev = b
        self._segment(net, l, start, prev, w, out)

    def _segment(self, net, l, a, b, w, out):
        (x1, y1), (x2, y2) = self.xy(a), self.xy(b)
        out.append({"kind": "track", "layer": LAYER_CODE[l], "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4),
                    "y2": round(y2, 4), "width": w, "net": net.name})

    # ---- does the pour reach every pad of its net?
    def pour_cut(self, net, layer):
        """The pads of the poured net that the pour on `layer` does not reach: copper of other nets there (and their vias) cuts the
        pour into pieces, and a pad whose via (or own copper on that layer) is not in the biggest piece is cut off. Returns
        (cut pad tags, tags reached)."""
        c = round(R.POUR_NECK, 4)
        occ = self.blocked(c, layer, net.nid)
        busy = self.cnt[c][layer]
        mine = next((s for a, s in (net.stamp or ()) if a is busy), set())
        blocked = bytearray(occ)
        for j in range(self.N):
            if busy[j] > (1 if j in mine else 0):
                blocked[j] = 1
        return self._joined(net, layer, blocked)

    def solid_cut(self, net, vias):
        """The same for the plane on Mid-Layer 1, which has no tracks: only holes of other nets (through pads, vias: [(cell, net)])
        and keep-outs cut it."""
        h = round(R.POUR_NECK, 4) / 2
        blocked = bytearray(b"\x01") * self.N
        e = self.rules["edge"] + h
        for ix in range(self.nx):
            if e <= ix * self.g <= self.box[2] - self.box[0] - e:
                for iy in range(self.ny):
                    if e <= iy * self.g <= self.box[3] - self.box[1] - e:
                        blocked[self.idx(ix, iy)] = 0
        for s in self.shapes:
            if len(s["layers"]) == 2 and s["net"] != net.name:
                for j, _d in self._cells_near(s["geo"], self.clear + h + EPS):
                    blocked[j] = 1
        offs = self.offs(self.clear + self.via_r + h + EPS)
        for v, other in vias:
            if other != net.name:
                for o in offs:
                    blocked[v + o] = 1
        return self._joined(net, None, blocked)

    def _joined(self, net, layer, blocked):
        """(cut pad tags, reached tags): which pads of the net are joined to the biggest piece of the pour whose obstacles are
        `blocked`, directly (a through pad, a pad on `layer`), by a via or by a track. layer None: an inner plane with no pads on it."""
        label = [0] * self.N
        sizes = [0]
        H = self.H
        j0 = blocked.find(0)
        while j0 >= 0:
            if not label[j0]:
                lab = len(sizes)
                label[j0] = lab
                stack, count = [j0], 0
                while stack:
                    i = stack.pop()
                    count += 1
                    for j in (i + 1, i - 1, i + H, i - H):
                        if not label[j] and not blocked[j]:
                            label[j] = lab
                            stack.append(j)
                sizes.append(count)
            j0 = blocked.find(0, j0 + 1)
        big = max(range(1, len(sizes)), key=lambda k: (sizes[k], -k), default=0)
        in_pour = lambda i: big and label[i] == big
        # the pads joined: by the pour itself, by a via in the pour, or by a track to such copper
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        N = self.N
        for p in self.pads[net.name]:
            for l in p["layers"]:
                for i in p["cells"]:
                    union(("pad", p["tag"]), l * N + i)
            if (p["tht"] or p["layers"] == (layer,)) and any(in_pour(i) for i in self._ring(p)):
                union(("pad", p["tag"]), "pour")
        for path in net.paths:
            for a, b in zip(path, path[1:]):
                union(a[0] * N + a[1], b[0] * N + b[1])
        for v in net.vias:
            for l in range(self.L):
                union(("via", v), l * N + v)
            if in_pour(v):
                union(("via", v), "pour")
        reached = [p["tag"] for p in self.pads[net.name] if find(("pad", p["tag"])) == find("pour")]
        return sorted(p["tag"] for p in self.pads[net.name] if p["tag"] not in reached), reached

    def _ring(self, pad):
        return [j for j, _d in self._cells_near(("rect", pad["rect"]), self.clear + 0.3)]

    def tie_cut(self, net, wide, cut, reached):
        """Tracks from each cut pad to a pad the pour does reach, around everything already drawn. Returns the pads still cut."""
        _w, use = self.masks(net)
        N = self.N
        by = {p["tag"]: p for p in self.pads[net.name]}
        goals = set()
        for t in reached:
            goals.update(self.pad_states(use, by[t]))
        left = []
        self.release(net)
        for t in cut:
            src = self.pad_states(use, by[t])
            path = self.search(net, wide, use, src, goals, 0.0, hard=True) if src and goals else None
            if path is None:
                left.append(t)
                continue
            self._take(net, path)
            goals.update(l * N + i for l, i in path)
        self.occupy(net, wide)
        return left


def plan(doc, box, rules=None, pitch=0.1, seconds=600.0, only=None, pour_net=None, planes=None, layers=2, log=None, expansions=None, clock=None):
    """Route a placed board; the arguments and the result are those of route.plan_routes. layers=4: Mid-Layer 2 is a third routing
    layer (the plane on it is poured around the tracks); Mid-Layer 1 is never used."""
    from altium import netcurrent, pair as _pair
    t0 = time.time()
    rules = rules or R.rules_from_doc(doc)
    deadline = clock or R.Clock(seconds, t0=t0)
    rt = R.Router(doc, box, rules, pitch, R.SAMPLING_TIGHT)
    rt.cap = R.DEFAULT_EXPANSIONS
    nets = sorted(n for n, ps in rt.pads.items() if len(ps) >= 2 and (only is None or n in only))
    planes = {n: v for n, v in (planes or {}).items() if n in nets}
    pour = pour_net if pour_net in nets and not planes else None
    nl = 3 if layers == 4 else 2

    pair_state = _pair.pre_route(rt, rules, nets, t0 + min(30.0, seconds), doc)
    _pair.fallback_ties(rt, rules, pair_state)
    fixed_items = [it for n in sorted(rt.routed) for it in rt.routed[n]["items"]] + [it for n in sorted(rt.tie) for it in rt.tie[n]["items"]]
    done = set(pair_state["done"])

    plan_w = netcurrent.net_widths(nets, rules, rules.get("net_current"), rules.get("net_estimate"), rules.get("copper_oz") or 1.0,
                                   rules.get("temp_rise_c") or 10.0, is_rail=lambda n: bool(R._RAIL.match(n)))
    mn = max(NECK_MIN, rules.get("width_min") or rules["width"])
    widths, options = {}, {}
    for n in nets:
        floor = max(mn, (rules.get("net_min") or {}).get(n, 0.0))      # the board's own Width rule for this net
        w = plan_w[n]["width_mm"]
        if w is None:
            w = min(max(rules["width"], R.POWER_WIDTH), rules["width_max"]) if R._RAIL.match(n) else rules["width"]
        ws = [w]
        if plan_w[n]["current_a"] is None or rules.get("allow_narrow"):
            ws += [x for x in (rules["width"], floor) if floor - 1e-9 <= x < ws[-1] - 1e-9]
        necks = [x for x in (rules["width"], floor) if x < w - 1e-9 and x >= floor - 1e-9]
        opts = [(w, None)] + [(w, x) for x in dict.fromkeys(necks)]
        for x in ws[1:]:
            opts.append((x, None))
            if floor < x - 1e-9:
                opts.append((x, floor))
        widths[n], options[n] = w, opts

    plane_layer = {}
    for n, name in planes.items():
        plane_layer[n] = MID if name == "mid2" and nl == 3 else None
    if pour:
        plane_layer[pour] = R.BOT
    ng = Negotiator(doc, box, rules, pitch, nl, {v for opts in options.values() for pair_ in opts for v in pair_ if v}, deadline,
                    fixed_items)
    ng.cap = expansions or EXPANSIONS
    ng.done0 = len(done)
    deadline.note(len(done), total=len(nets))
    ng.mult = [LAYER_MULT[l] for l in range(nl)]
    if pour:
        ng.mult[R.BOT] = POUR_BOT_MULT

    objs = []
    for n in nets:
        if n in done:
            continue
        o = _Net(n, ng.nid[n])
        o.options = options[n]
        o.width = widths[n]
        if n in plane_layer:
            o.kind = "drop"
            o.plane_layer = plane_layer[n]
        if n in rt.tie:
            t = rt.tie[n]
            cells = set()
            for it in t["items"]:
                if it["kind"] == "via":
                    cells.update(l * ng.N + ng.cell_of(it["x"], it["y"]) for l in range(nl))
                else:
                    l = 0 if it["layer"] == 1 else 1
                    k = max(1, int(math.hypot(it["x2"] - it["x1"], it["y2"] - it["y1"]) / (pitch / 2)))
                    cells.update(l * ng.N + ng.cell_of(it["x1"] + (it["x2"] - it["x1"]) * j / k, it["y1"] + (it["y2"] - it["y1"]) * j / k)
                                 for j in range(k + 1))
            o.tied = [(cells, t["pads"])]
        objs.append(o)

    def order(o):
        pads = ng.pads[o.name]
        return (0 if o.kind == "drop" else 1, R._hpwl(pads), o.name)
    objs.sort(key=order)
    rounds = ng.negotiate(objs, log=log)

    pour_cuts = {}
    drops = [o for o in objs if o.kind == "drop" and not o.why]
    for o in sorted(drops, key=lambda o: o.plane_layer is None):      # every pour must reach every pad of its net; the solid one last
        if o.plane_layer is not None or planes.get(o.name) == "mid1":
            if o.plane_layer is not None:
                cut, reached = ng.pour_cut(o, o.plane_layer)
            else:
                holes = [(v, other.name) for other in objs if not other.why for v in other.vias]
                holes += [(ng.cell_of(it["x"], it["y"]), it["net"]) for it in fixed_items if it["kind"] == "via"]
                cut, reached = ng.solid_cut(o, holes)
            if cut:
                cut = ng.tie_cut(o, ng.masks(o)[0], cut, reached)
            if cut:
                pour_cuts[o.name] = cut

    routed, failed, items = {}, [], []
    for o in objs:
        if o.why:
            failed.append((o.name, o.why))
            continue
        its, necks = ng.items(o)
        if o.name in rt.tie:
            its = its + rt.tie[o.name]["items"]
        items += its
        routed[o.name] = {"items": its, "width": o.width, "necks": necks}
        if o.name in pour_cuts:
            names = ", ".join(pour_cuts[o.name][:6])
            failed.append((o.name, f"pad(s) {names} cannot be joined to the pour or to other {o.name} copper; the other pads are dropped"))
    for n in sorted(done):
        its = rt.routed[n]["items"]
        items += its
        routed[n] = {"items": its, "width": rt.routed[n]["width"], "necks": rt.routed[n].get("necks") or []}

    # the exact check of what is about to be drawn: whatever it finds too close is taken off and named
    repaired = 0
    shapes = ng.shapes
    while True:
        vs = R._violations(shapes, items, rules, box)
        hit = sorted({n for _m, ns in vs for n in ns if n in routed})
        if not hit:
            break
        worst = max(hit, key=lambda n: (sum(1 for _m, ns in vs if n in ns), n not in done, n))
        msg = next(m for m, ns in vs if worst in ns)
        items = [it for it in items if it["net"] != worst]
        routed.pop(worst)
        failed = [f for f in failed if f[0] != worst]
        failed.append((worst, "the track would break the rules and no other way was found: " + msg))
        repaired += 1
    partial = {n for n, _ in failed}
    for n in nets:
        if n not in routed and n not in partial:
            failed.append((n, "not routed"))

    pour_info = None
    if pour:
        pour_info = {"net": pour, "mode": "drops" if pour in routed else None, "note": dict(failed).get(pour, "")}
    rep = R._width_report(nets, plan_w, routed)
    return {"pairs": _pair.report(rt, rules, pair_state, items), "items": items, "routed": sorted(n for n in routed if n not in partial),
            "failed": failed, "widths": rep, "width_problems": netcurrent.width_problems(rep),
            "planes": {n: planes[n] for n in sorted(planes)}, "pour": pour_info,
            "stats": {"nets": len(nets), "tracks": sum(1 for i in items if i["kind"] == "track"),
                      "vias": sum(1 for i in items if i["kind"] == "via"), "seconds": round(time.time() - t0, 1), "ripped": rounds,
                      "rounds": rounds, "repaired": repaired, "pitch": pitch, "expansions": ng.spent, "attempts": 1, "engine": "negotiated"}}
