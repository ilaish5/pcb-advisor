"""RS-274X reader for the subset Altium emits (A2: written here, independent of scripts/gerber_check.py).

Supported: %FS (absolute, L/T zero omission), %MOIN/%MOMM, G70/G71, G01/G02/G03, G74 rejected, G75, G36/G37 regions (lines and arcs),
%LPD/%LPC polarity, %ADD with C/R/O/P apertures, D01/D02/D03, X2 attributes (%TF/%TA/%TO/%TD kept as text), comments.
NOT supported and therefore REFUSED (ValueError, never skipped): %AM macros used by an aperture, %AB blocks, %SR step-repeat,
%LM/%LR/%LS transforms, G74 single-quadrant arcs, rectangular-aperture arcs, rotated rectangle flashes (none occur in Altium output).
All coordinates are converted to mm.

Layer role comes from the file extension (JLC / Altium names), see `role_of`.
"""
from __future__ import annotations

import dataclasses
import math
import pathlib
import re
import zipfile

from . import gerber_geom as geom

IN = 25.4
EXT_ROLE = {
    ".gtl": ("copper", "top"), ".gbl": ("copper", "bottom"),
    ".gts": ("mask", "top"), ".gbs": ("mask", "bottom"),
    ".gtp": ("paste", "top"), ".gbp": ("paste", "bottom"),
    ".gto": ("silk", "top"), ".gbo": ("silk", "bottom"),
    ".gko": ("outline", None), ".gd1": ("drilldrawing", None), ".gg1": ("guide", None),
    ".gpt": ("padmaster", "top"), ".gpb": ("padmaster", "bottom"),
}


def role_of(name: str) -> tuple[str, str | None] | None:
    """(role, side) from a JLC/Altium file name: .GTL/.GBL top/bottom copper, .G1.. inner copper, .GTS/.GBS mask,
    .GTP/.GBP paste, .GTO/.GBO silk, .GM1.. / .GKO outline-mechanical. None if the extension is not a Gerber layer."""
    ext = pathlib.PurePath(name).suffix.lower()
    if ext in EXT_ROLE:
        return EXT_ROLE[ext]
    m = re.fullmatch(r"\.g(\d{1,2})", ext)
    if m:
        return ("copper", f"inner{int(m.group(1))}")
    m = re.fullmatch(r"\.gm(\d{1,2})", ext)
    if m:
        return ("outline" if int(m.group(1)) == 1 else "mechanical", None)
    return None


@dataclasses.dataclass
class Aperture:
    code: int
    shape: str                     # C R O P
    params: tuple                  # mm

    def poly(self, cx: float, cy: float) -> list:
        s, p = self.shape, self.params
        if s == "C":
            return geom.circle_poly(cx, cy, p[0] / 2)
        if s == "R":
            return geom.rect_poly(cx, cy, p[0], p[1])
        if s == "O":
            w, h = p[0], p[1]
            if abs(w - h) < 1e-9:
                return geom.circle_poly(cx, cy, w / 2)
            if w > h:
                return geom.stadium_poly(cx - (w - h) / 2, cy, cx + (w - h) / 2, cy, h / 2)
            return geom.stadium_poly(cx, cy - (h - w) / 2, cx, cy + (h - w) / 2, w / 2)
        if s == "P":
            d, n = p[0], int(p[1])
            rot = math.radians(p[2]) if len(p) > 2 else 0.0
            r = d / 2
            return [(cx + r * math.cos(rot + 2 * math.pi * i / n), cy + r * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)]
        raise ValueError(f"aperture shape {s}")

    def extent(self) -> tuple[float, float]:
        s, p = self.shape, self.params
        if s == "C":
            return p[0], p[0]
        if s in ("R", "O"):
            return p[0], p[1]
        return p[0], p[0]


class Prim:
    """One drawing object. kind: flash | draw | region. dark=False is clear polarity (erases earlier objects)."""
    __slots__ = ("kind", "dark", "ap", "pts", "polys", "bbox", "idx", "x", "y", "width")

    def __init__(self, kind, dark, ap, pts, polys, idx):
        self.kind, self.dark, self.ap, self.pts, self.polys, self.idx = kind, dark, ap, pts, polys, idx
        allp = [p for poly in polys for p in poly]
        self.bbox = geom.bbox(allp) if allp else (0, 0, 0, 0)
        self.x = self.y = None
        if kind == "flash":
            self.x, self.y = pts[0]
        self.width = None

    def contains(self, p) -> bool:
        return any(geom.point_in_poly(p, poly) for poly in self.polys)

    def dist(self, other: "Prim", limit: float = float("inf")) -> float:
        best = limit
        for a in self.polys:
            for b in other.polys:
                best = min(best, geom.poly_poly_dist(a, b, best))
                if best == 0.0:
                    return 0.0
        return best

    def area(self) -> float:
        return sum(geom.area(p) for p in self.polys)

    @property
    def size(self) -> tuple[float, float]:
        """(w, h) of the bounding box in mm."""
        return self.bbox[2] - self.bbox[0], self.bbox[3] - self.bbox[1]


class Layer:
    def __init__(self, name: str, role: tuple | None) -> None:
        self.name = name
        self.role = role[0] if role else None
        self.side = role[1] if role else None
        self.prims: list[Prim] = []
        self.attrs: list[str] = []
        self.apertures: dict[int, Aperture] = {}
        self._grid: geom.Grid | None = None
        self.step = 0.00254      # coordinate resolution in mm, set from %FS / %MO

    # -- indexing / painter model
    def grid(self) -> geom.Grid:
        if self._grid is None:
            self._grid = geom.Grid(1.0)
            for pr in self.prims:
                self._grid.add(pr.idx, pr.bbox)
        return self._grid

    def covered(self, p, skip=frozenset()) -> bool:
        """Painter model: the last object (in file order) that covers p decides (dark = material, clear = none)."""
        for i in reversed(self.grid().near((p[0], p[1], p[0], p[1]))):
            if i in skip:
                continue
            pr = self.prims[i]
            if pr.contains(p):
                return pr.dark
        return False

    def flashes(self, dark_only: bool = True) -> list[Prim]:
        return [p for p in self.prims if p.kind == "flash" and (p.dark or not dark_only)]

    def dark(self) -> list[Prim]:
        return [p for p in self.prims if p.dark]

    def extent(self) -> tuple[float, float, float, float]:
        boxes = [p.bbox for p in self.prims]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def nearest_material(self, shape_core: tuple, r: float, reach: float, eps: float = 0.002):
        """Distance from the wall of a round hole / slot (core segment p0-p1, radius r) to the nearest material boundary on this
        layer, using the painter model (a clear object's edge is a boundary only where material is on the other side).
        A dark flash lying entirely inside the hole (within own_tol of its wall) is the hole's own pad shape, which the drill removes:
        it is ignored. Returns (distance_mm, (x, y)) or (None, None) when no material lies within reach. Negative = overlaps."""
        p0, p1 = shape_core
        box = (min(p0[0], p1[0]) - r, min(p0[1], p1[1]) - r, max(p0[0], p1[0]) + r, max(p0[1], p1[1]) + r)
        near = self.grid().near(box, reach)
        own_tol = 2 * self.step + 0.002 * r          # coordinate rounding + the circumscribed-polygon error (measurement resolution)
        skip = set()
        for i in near:
            pr = self.prims[i]
            if pr.kind == "flash" and pr.dark and all(geom.pt_seg_closest(v, p0, p1)[0] <= r + own_tol for v in pr.polys[0]):
                skip.add(i)
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        if self.covered(mid, skip):
            return -r, mid
        cands = []
        for i in near:
            if i in skip:
                continue
            pr = self.prims[i]
            for poly in pr.polys:
                n = len(poly)
                if n < 2:
                    continue
                for k in range(n):
                    a, b = poly[k], poly[(k + 1) % n]
                    d, qa, qb = geom.seg_seg_closest(p0, p1, a, b)
                    if d - r < reach:
                        cands.append((d, qb, a, b))
        cands.sort(key=lambda c: c[0])
        for d, q, a, b in cands:
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L == 0:
                continue
            nx, ny = -dy / L, dx / L
            s1 = self.covered((q[0] + nx * eps, q[1] + ny * eps), skip)
            s2 = self.covered((q[0] - nx * eps, q[1] - ny * eps), skip)
            if s1 != s2:
                return d - r, q
        return None, None


class _Parser:
    def __init__(self, name: str, text: str) -> None:
        self.layer = Layer(name, role_of(name))
        self.text = text
        self.unit = IN
        self.int_d = self.dec_d = None
        self.zero = "L"
        self.dark = True
        self.ap: Aperture | None = None
        self.x = self.y = 0.0
        self.interp = "G01"
        self.quad = None
        self.region: list | None = None
        self.region_cur: list | None = None
        self.ap_defs: dict[int, tuple] = {}

    # coordinates
    def conv(self, digits: str) -> float:
        if self.int_d is None:
            raise ValueError("coordinate before %FS")
        sign = -1 if digits.startswith("-") else 1
        d = digits.lstrip("+-")
        total = self.int_d + self.dec_d
        if "." in d:
            return sign * float(d) * self.unit
        if self.zero == "T":
            d = d.ljust(total, "0")
        return sign * int(d) / (10 ** self.dec_d) * self.unit

    def add(self, kind, ap, pts, polys) -> Prim:
        pr = Prim(kind, self.dark, ap, pts, polys, len(self.layer.prims))
        self.layer.prims.append(pr)
        return pr

    def arc_points(self, x0, y0, x1, y1, i, j, cw) -> list:
        cx, cy = x0 + i, y0 + j
        r0 = math.hypot(x0 - cx, y0 - cy)
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        if cw:
            if a1 >= a0:
                a1 -= 2 * math.pi
        else:
            if a1 <= a0:
                a1 += 2 * math.pi
        if (x0, y0) == (x1, y1):
            a1 = a0 + (-2 * math.pi if cw else 2 * math.pi)
        n = max(4, int(abs(a1 - a0) / (2 * math.pi) * 128) + 1)
        return [(cx + r0 * math.cos(a0 + (a1 - a0) * k / n), cy + r0 * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    def draw_poly(self, pts: list) -> list:
        ap = self.ap
        if ap is None:
            raise ValueError("draw without aperture")
        polys = []
        if ap.shape == "C":
            for a, b in zip(pts, pts[1:]):
                polys.append(geom.stadium_poly(a[0], a[1], b[0], b[1], ap.params[0] / 2))
        elif ap.shape == "R":
            w, h = ap.params[0] / 2, ap.params[1] / 2
            for a, b in zip(pts, pts[1:]):
                corners = [(px + sx * w, py + sy * h) for px, py in (a, b) for sx in (-1, 1) for sy in (-1, 1)]
                polys.append(geom.hull(corners))
        else:
            raise ValueError(f"draw with {ap.shape} aperture is not supported")
        return polys

    def run(self) -> Layer:
        L = self.layer
        for chunk in re.finditer(r"%([^%]*)%|([^%*]*)\*", self.text, re.S):
            ext, word = chunk.group(1), chunk.group(2)
            if ext is not None:
                for cmd in ext.replace("\n", "").replace("\r", "").split("*"):
                    if cmd:
                        self.ext_cmd(cmd)
                continue
            w = word.strip().replace("\n", "").replace("\r", "")
            if w:
                self.word(w)
        if self.region is not None:
            raise ValueError("unterminated G36 region")
        L.apertures = dict(self.ap_defs_obj) if hasattr(self, "ap_defs_obj") else {}
        return L

    ap_defs_obj: dict

    def ext_cmd(self, cmd: str) -> None:
        if not hasattr(self, "ap_defs_obj"):
            self.ap_defs_obj = {}
        if cmd.startswith("FS"):
            m = re.fullmatch(r"FS([LT])([AI])X(\d)(\d)Y(\d)(\d)", cmd)
            if not m or m.group(2) != "A":
                raise ValueError(f"unsupported format spec {cmd}")
            self.zero = m.group(1)
            self.int_d, self.dec_d = int(m.group(3)), int(m.group(4))
            self.layer.step = 10 ** -self.dec_d * self.unit
        elif cmd == "MOIN":
            self.unit = IN
            if self.dec_d is not None:
                self.layer.step = 10 ** -self.dec_d * self.unit
        elif cmd == "MOMM":
            self.unit = 1.0
        elif cmd == "LPD":
            self.dark = True
        elif cmd == "LPC":
            self.dark = False
        elif cmd.startswith("ADD"):
            m = re.fullmatch(r"ADD(\d+)([A-Za-z_][A-Za-z0-9_.$]*),?([-0-9.Xx]*)", cmd)
            if not m:
                raise ValueError(f"bad aperture definition {cmd}")
            code, shape, par = int(m.group(1)), m.group(2), m.group(3)
            if shape not in ("C", "R", "O", "P"):
                raise ValueError(f"aperture {code}: macro/standard shape {shape!r} not supported")
            nums = [float(v) for v in par.split("X") if v != ""]
            if shape == "C":
                vals = (nums[0] * self.unit,)
            elif shape in ("R", "O"):
                vals = (nums[0] * self.unit, nums[1] * self.unit)
            else:
                vals = (nums[0] * self.unit, nums[1], nums[2] if len(nums) > 2 else 0.0)
            ap = Aperture(code, shape, vals)
            self.ap_defs_obj[code] = ap
        elif cmd.startswith(("AM", "AB", "SR", "LM", "LR", "LS")):
            raise ValueError(f"unsupported extended command {cmd[:12]}")
        elif cmd.startswith(("TF", "TA", "TO", "TD", "IP", "OF", "IN", "LN", "SF", "AS", "MI", "IR")):
            self.layer.attrs.append(cmd)
        # other parameters are ignored only if purely informational; unknown commands are recorded
        else:
            self.layer.attrs.append(cmd)

    def word(self, w: str) -> None:
        if w.startswith("G04"):
            return
        if w in ("M02", "M00"):
            return
        # split off G codes preceding coordinates (e.g. G01X..Y..D01)
        m = re.fullmatch(r"(?:G(\d+))?(.*)", w)
        g, rest = m.group(1), m.group(2)
        if g is not None:
            g = "G" + g.lstrip("0").rjust(2, "0") if g.strip("0") else "G00"
            gi = int(g[1:])
            if gi in (1, 2, 3):
                self.interp = g
            elif gi == 36:
                self.region = []
                self.region_cur = None
            elif gi == 37:
                self.end_region()
            elif gi == 75:
                self.quad = "multi"
            elif gi == 74:
                raise ValueError("G74 single-quadrant arcs not supported")
            elif gi == 54:
                pass
            elif gi in (70, 71):
                self.unit = IN if gi == 70 else 1.0
            elif gi in (90, 91):
                if gi == 91:
                    raise ValueError("incremental coordinates not supported")
            else:
                raise ValueError(f"unsupported G{gi}")
            if not rest:
                return
        if not rest:
            return
        if re.fullmatch(r"D\d+", rest) and int(rest[1:]) >= 10:
            code = int(rest[1:])
            if code not in self.ap_defs_obj:
                raise ValueError(f"aperture D{code} not defined")
            self.ap = self.ap_defs_obj[code]
            return
        coords = dict(re.findall(r"([XYIJ])([-+]?[0-9.]+)", rest))
        dm = re.search(r"D0?([123])$", rest)
        if not coords and not dm:
            raise ValueError(f"cannot parse word {w!r}")
        x0, y0 = self.x, self.y
        x1 = self.conv(coords["X"]) if "X" in coords else x0
        y1 = self.conv(coords["Y"]) if "Y" in coords else y0
        ij = (self.conv(coords.get("I", "0")), self.conv(coords.get("J", "0")))
        d = int(dm.group(1)) if dm else getattr(self, "last_d", 1)
        self.last_d = d
        self.x, self.y = x1, y1
        if self.region is not None:
            self.region_op(d, x0, y0, x1, y1, ij)
            return
        if d == 2:
            return
        if d == 3:
            if self.ap is None:
                raise ValueError("flash without aperture")
            self.add("flash", self.ap, [(x1, y1)], [self.ap.poly(x1, y1)])
            return
        if self.interp == "G01":
            pts = [(x0, y0), (x1, y1)]
        else:
            if self.quad != "multi":
                raise ValueError("arc without G75")
            pts = self.arc_points(x0, y0, x1, y1, ij[0], ij[1], self.interp == "G02")
        pr = self.add("draw", self.ap, pts, self.draw_poly(pts))
        pr.width = self.ap.params[0] if self.ap.shape == "C" else None

    def region_op(self, d, x0, y0, x1, y1, ij) -> None:
        if d == 2:
            if self.region_cur and len(self.region_cur) >= 3:
                self.close_contour()
            self.region_cur = [(x1, y1)]
            return
        if self.region_cur is None:
            self.region_cur = [(x0, y0)]
        if self.interp == "G01":
            self.region_cur.append((x1, y1))
        else:
            self.region_cur.extend(self.arc_points(x0, y0, x1, y1, ij[0], ij[1], self.interp == "G02")[1:])

    def close_contour(self) -> None:
        pts = self.region_cur
        if pts and pts[0] == pts[-1]:
            pts = pts[:-1]
        if pts and len(pts) >= 3:
            self.region.append(pts)
        self.region_cur = None

    def end_region(self) -> None:
        if self.region_cur:
            self.close_contour()
        for contour in self.region or []:
            self.add("region", None, contour, [contour])
        self.region = None
        self.region_cur = None


def parse(name: str, data: bytes | str) -> Layer:
    text = data.decode("latin1") if isinstance(data, bytes) else data
    return _Parser(name, text).run()


def attr_value(layer: Layer, key: str) -> str | None:
    for a in layer.attrs:
        m = re.match(r"TF\." + re.escape(key) + r",(.*)", a)
        if m:
            return m.group(1)
    return None


def load_zip(path: pathlib.Path) -> tuple[dict[str, Layer], dict[str, bytes]]:
    """Parse every Gerber layer of a zip (by extension); returns ({name: Layer}, {name: raw bytes of non-Gerber members})."""
    layers: dict[str, Layer] = {}
    others: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            nm = pathlib.PurePath(info.filename).name
            if role_of(nm):
                layers[nm] = parse(nm, z.read(info))
            else:
                others[nm] = z.read(info)
    return layers, others


def load_dir(path: pathlib.Path) -> tuple[dict[str, Layer], dict[str, bytes]]:
    layers: dict[str, Layer] = {}
    others: dict[str, bytes] = {}
    for f in sorted(pathlib.Path(path).iterdir()):
        if f.is_file():
            if role_of(f.name):
                layers[f.name] = parse(f.name, f.read_bytes())
            else:
                others[f.name] = f.read_bytes()
    return layers, others


class Board:
    """The Gerber set of one board: layers keyed by (role, side)."""

    def __init__(self, layers: dict[str, Layer]) -> None:
        self.layers = layers
        self.by = {}
        for nm, ly in layers.items():
            self.by.setdefault((ly.role, ly.side), ly)

    def get(self, role: str, side: str | None) -> Layer | None:
        return self.by.get((role, side))

    def copper(self) -> list[Layer]:
        out = [l for l in self.layers.values() if l.role == "copper"]
        order = lambda l: (0 if l.side == "top" else 2 if l.side == "bottom" else 1, int(re.sub(r"\D", "", l.side or "0") or 0))
        return sorted(out, key=order)


class Nets:
    """Copper connectivity rebuilt from the Gerbers alone (no netlist in a Gerber set): same-layer touching copper is one object,
    a plated hole joins the copper under its centre on every layer, a plane region joins the pads/tracks that touch it where the
    painter model shows copper. `net(layer, prim)` returns an id; equal ids = connected as far as the Gerbers show.
    Limits (stated, not hidden): split planes drawn as two regions are two nets; copper joined only through a component body is not
    joined; a plane island with no hole in it is a net of its own."""


    def __init__(self, board: "Board", holes: list) -> None:
        self.parent: dict = {}
        # two copper objects closer than 1.2 coordinate steps are one object (a gap below the file's resolution is a rounding step)
        self.TOUCH = 1.2 * max(l.step for l in board.layers.values())
        for ly in board.copper():
            self._layer(ly)
        for h in holes:
            if not h.plated:
                continue
            nodes = []
            for ly in board.copper():
                n = self._node_at(ly, (h.x, h.y))
                if n is not None:
                    nodes.append(n)
            for a, b in zip(nodes, nodes[1:]):
                self._union(a, b)

    def _find(self, a):
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def _union(self, a, b) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self.parent[ra] = rb

    def _node_at(self, ly: Layer, p):
        for i in reversed(ly.grid().near((p[0], p[1], p[0], p[1]))):
            pr = ly.prims[i]
            if pr.contains(p):
                return (ly.name, i) if pr.dark else None
        return None

    def _layer(self, ly: Layer) -> None:
        darks = [p for p in ly.prims if p.dark]
        for p in darks:
            self._find((ly.name, p.idx))
        for p in darks:
            if p.kind == "region":
                continue
            for j in ly.grid().near(p.bbox, self.TOUCH):
                q = ly.prims[j]
                if j <= p.idx or not q.dark or q.kind == "region":
                    continue
                if p.dist(q, self.TOUCH) < self.TOUCH:
                    self._union((ly.name, p.idx), (ly.name, j))
            # joins with visible region copper
            for poly in p.polys:
                for v in poly:
                    cx, cy = (p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2
                    dx, dy = v[0] - cx, v[1] - cy
                    L = math.hypot(dx, dy) or 1.0
                    probe = (v[0] + dx / L * 0.01, v[1] + dy / L * 0.01)
                    for i in reversed(ly.grid().near((probe[0], probe[1], probe[0], probe[1]))):
                        q = ly.prims[i]
                        if i == p.idx:
                            continue
                        if q.contains(probe):
                            if q.dark and q.kind == "region":
                                self._union((ly.name, p.idx), (ly.name, i))
                            break

    def net(self, ly: Layer, prim: Prim):
        return self._find((ly.name, prim.idx))


def group_pads(pads: list[Prim], anchors: dict[str, tuple[float, float]]) -> tuple[dict[str, list[int]], list[int]]:
    """Heuristic: split copper pad flashes between components. A Gerber set carries no pad ownership, so this is a best effort, used
    where an approximate part outline is enough (finding an exposed pad); it is NOT used to decide a CPL point.
    anchors = {designator: (x, y)} from a CPL. Method: every part starts as a point at its CPL position; repeatedly the unassigned pad
    nearest (box to box) to any part box is absorbed, unless the grown box would contain another part's anchor or overlap another
    part's box. Pads that no part can absorb stay unassigned (e.g. mounting-hole pads). Returns ({ref: [pad index]}, [unassigned])."""
    box = {d: [x, y, x, y] for d, (x, y) in anchors.items()}
    members: dict[str, list[int]] = {d: [] for d in anchors}
    left = set(range(len(pads)))

    def gap(b, pb):
        return math.hypot(max(pb[0] - b[2], b[0] - pb[2], 0.0), max(pb[1] - b[3], b[1] - pb[3], 0.0))

    def union(b, pb):
        return [min(b[0], pb[0]), min(b[1], pb[1]), max(b[2], pb[2]), max(b[3], pb[3])]

    def overlap(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    while left:
        best = None
        for i in left:
            pb = pads[i].bbox
            for d, b in box.items():
                g = gap(b, pb)
                if best is not None and g >= best[0]:
                    continue
                nb = union(b, pb) if members[d] else list(pb)
                if any(d2 != d and nb[0] <= ax <= nb[2] and nb[1] <= ay <= nb[3] for d2, (ax, ay) in anchors.items()):
                    continue
                if any(d2 != d and members[d2] and overlap(nb, b2) for d2, b2 in box.items()):
                    continue
                best = (g, i, d)
        if best is None:
            break
        _, i, d = best
        box[d] = union(box[d], pads[i].bbox) if members[d] else list(pads[i].bbox)
        members[d].append(i)
        left.discard(i)
    return members, sorted(left)
