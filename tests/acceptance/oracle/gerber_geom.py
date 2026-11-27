"""Small 2-D geometry kit for the oracle (pure python, mm). Polygons are lists of (x, y); no shapely/numpy needed.

Circles are polygons circumscribed about the true circle (edge tangent to it), so a gap measured on them is never larger than the
true gap (error <= r * 0.0012 for 64 sides, 0.0004 mm on a 0.35 mm radius).
"""
from __future__ import annotations

import math

Pt = tuple[float, float]
CIRCLE_SIDES = 64
CAP_SIDES = 16          # per half circle of a stadium


def circle_poly(cx: float, cy: float, r: float, n: int = CIRCLE_SIDES) -> list[Pt]:
    if r <= 0:
        return [(cx, cy)]
    rr = r / math.cos(math.pi / n)
    return [(cx + rr * math.cos(2 * math.pi * (i + 0.5) / n), cy + rr * math.sin(2 * math.pi * (i + 0.5) / n))
            for i in range(n)]


def rect_poly(cx: float, cy: float, w: float, h: float) -> list[Pt]:
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def stadium_poly(x0: float, y0: float, x1: float, y1: float, r: float) -> list[Pt]:
    """The set of points within r of the segment (x0,y0)-(x1,y1) (a round-ended slot / a round-aperture draw)."""
    if (x0, y0) == (x1, y1):
        return circle_poly(x0, y0, r)
    ang = math.atan2(y1 - y0, x1 - x0)
    rr = r / math.cos(math.pi / (2 * CAP_SIDES))
    pts: list[Pt] = []
    for i in range(CAP_SIDES):          # cap around the end point (x1,y1): from ang-90 to ang+90
        a = ang - math.pi / 2 + math.pi * (i + 0.5) / CAP_SIDES
        pts.append((x1 + rr * math.cos(a), y1 + rr * math.sin(a)))
    for i in range(CAP_SIDES):          # cap around the start point
        a = ang + math.pi / 2 + math.pi * (i + 0.5) / CAP_SIDES
        pts.append((x0 + rr * math.cos(a), y0 + rr * math.sin(a)))
    return pts


def hull(points: list[Pt]) -> list[Pt]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo: list[Pt] = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up: list[Pt] = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def bbox(poly: list[Pt]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def area(poly: list[Pt]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def point_in_poly(p: Pt, poly: list[Pt]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def pt_seg_closest(p: Pt, a: Pt, b: Pt) -> tuple[float, Pt]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), q


def _segs_cross(a: Pt, b: Pt, c: Pt, d: Pt) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
    return ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0


def seg_seg_closest(a: Pt, b: Pt, c: Pt, d: Pt) -> tuple[float, Pt, Pt]:
    """Distance between two segments and the closest point on each (on c-d for the second)."""
    if _segs_cross(a, b, c, d):
        # intersection point
        r = (b[0] - a[0], b[1] - a[1])
        s = (d[0] - c[0], d[1] - c[1])
        den = r[0] * s[1] - r[1] * s[0]
        t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
        q = (a[0] + t * r[0], a[1] + t * r[1])
        return 0.0, q, q
    best = (float("inf"), a, c)
    for p, (s0, s1), first in ((a, (c, d), True), (b, (c, d), True), (c, (a, b), False), (d, (a, b), False)):
        dist, q = pt_seg_closest(p, s0, s1)
        if dist < best[0]:
            best = (dist, p, q) if first else (dist, q, p)
    return best


def _bbox_gap(b1, b2) -> float:
    dx = max(b2[0] - b1[2], b1[0] - b2[2], 0.0)
    dy = max(b2[1] - b1[3], b1[1] - b2[3], 0.0)
    return math.hypot(dx, dy)


def poly_poly_dist(p1: list[Pt], p2: list[Pt], limit: float = float("inf")) -> float:
    """Minimum distance between two filled polygons (0 when they overlap or touch). Returns >= limit early when far apart."""
    if _bbox_gap(bbox(p1), bbox(p2)) >= limit:
        return limit
    if point_in_poly(p1[0], p2) or point_in_poly(p2[0], p1):
        return 0.0
    best = float("inf")
    n1, n2 = len(p1), len(p2)
    for i in range(n1):
        a, b = p1[i], p1[(i + 1) % n1]
        for j in range(n2):
            c, d = p2[j], p2[(j + 1) % n2]
            dist = seg_seg_closest(a, b, c, d)[0]
            if dist < best:
                best = dist
                if best == 0.0:
                    return 0.0
    return best


def clip_convex(subject: list[Pt], clip: list[Pt]) -> list[Pt]:
    """Sutherland-Hodgman: subject clipped by a convex clip polygon (either orientation)."""
    if area(clip) == 0:
        return []
    cw = sum((clip[(i + 1) % len(clip)][0] - clip[i][0]) * (clip[(i + 1) % len(clip)][1] + clip[i][1])
             for i in range(len(clip))) > 0
    out = subject
    n = len(clip)
    for i in range(n):
        a, b = clip[i], clip[(i + 1) % n]
        if not out:
            return []

        def inside(p):
            c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            return c <= 0 if cw else c >= 0

        def inter(p, q):
            x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
            x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        inp, out = out, []
        for k in range(len(inp)):
            cur, prev = inp[k], inp[k - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
    return out


class Grid:
    """Uniform bucket grid over bounding boxes: items are (key, bbox)."""

    def __init__(self, cell: float = 1.0) -> None:
        self.cell = cell
        self.cells: dict[tuple[int, int], list] = {}
        self.boxes: dict = {}

    def add(self, key, box) -> None:
        self.boxes[key] = box
        c = self.cell
        for i in range(int(math.floor(box[0] / c)), int(math.floor(box[2] / c)) + 1):
            for j in range(int(math.floor(box[1] / c)), int(math.floor(box[3] / c)) + 1):
                self.cells.setdefault((i, j), []).append(key)

    def near(self, box, margin: float = 0.0) -> list:
        """Keys whose cell bucket meets box grown by margin, deduplicated, in insertion order of the cells' lists (sorted)."""
        c = self.cell
        x0, y0, x1, y1 = box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin
        seen = set()
        for i in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for j in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
                for k in self.cells.get((i, j), ()):
                    if k not in seen:
                        b = self.boxes[k]
                        if b[0] <= x1 and b[2] >= x0 and b[1] <= y1 and b[3] >= y0:
                            seen.add(k)
        return sorted(seen)
