"""Independent PcbDoc / PcbLib reader on raw `olefile` (ACCEPTANCE.md A2). Reads the record formats directly; shares no code with
scripts/altium/*. Units: mm and degrees. Altium stores coordinates as int32 in 1/10000 mil (1 unit = 2.54e-6 mm).

Layer ids (Altium V6 binary layer byte): 1 Top, 2..31 Mid-Layer 1..30, 32 Bottom, 33 Top Overlay, 34 Bottom Overlay, 35 Top Paste,
36 Bottom Paste, 37 Top Solder, 38 Bottom Solder, 39..54 Internal planes 1..16, 55 Drill Guide, 56 Keep-Out, 57..72 Mechanical 1..16,
73 Drill Drawing, 74 Multi-Layer.
"""
from __future__ import annotations

import dataclasses
import math
import pathlib
import struct
from typing import Iterator

import olefile

UNIT_MM = 0.0254 / 10000          # one stored coordinate unit in mm
MIL_MM = 0.0254

L_TOP, L_BOTTOM, L_KEEPOUT, L_MULTI = 1, 32, 56, 74
L_TOP_OVERLAY, L_BOTTOM_OVERLAY = 33, 34


def is_copper(layer: int) -> bool:
    """Signal layers 1..32 (top, mids, bottom) and internal planes 39..54."""
    return 1 <= layer <= 32 or 39 <= layer <= 54


def layer_name(layer: int) -> str:
    if layer == 1:
        return "Top"
    if layer == 32:
        return "Bottom"
    if 2 <= layer <= 31:
        return f"Mid{layer - 1}"
    if 39 <= layer <= 54:
        return f"Plane{layer - 38}"
    if 57 <= layer <= 72:
        return f"Mech{layer - 56}"
    return {33: "TopOverlay", 34: "BottomOverlay", 35: "TopPaste", 36: "BottomPaste", 37: "TopSolder", 38: "BottomSolder",
            55: "DrillGuide", 56: "KeepOut", 73: "DrillDrawing", 74: "MultiLayer"}.get(layer, f"L{layer}")


# ---------------------------------------------------------------------------------------------------------------- text records
def kv(text: str) -> dict[str, str]:
    """`|KEY=VALUE|KEY=VALUE` -> {KEY: VALUE}. A value ends at `|` or `\\r` (Board6 wraps its record with \\r)."""
    out: dict[str, str] = {}
    for part in text.replace("\r", "|").split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().upper()] = v
    return out


def mil_value(s: str) -> float:
    """'12.6mil' / '0.3mm' / '5' (mil) -> mm."""
    s = (s or "").strip().lower()
    if s.endswith("mil"):
        return float(s[:-3]) * MIL_MM
    if s.endswith("mm"):
        return float(s[:-2])
    return float(s) * MIL_MM


def _text_records(blob: bytes, skip: int = 0) -> list[dict[str, str]]:
    """Records of `[skip bytes][uint32 len (high byte flag)][text]`."""
    out, i = [], 0
    while i + skip + 4 <= len(blob):
        i += skip
        n = struct.unpack("<I", blob[i:i + 4])[0]
        flag, n = n >> 24, n & 0xFFFFFF
        body = blob[i + 4:i + 4 + n]
        i += 4 + n
        if flag:
            continue
        out.append(kv(body.rstrip(b"\0").decode("latin-1", "replace")))
    return out


def _prims(blob: bytes) -> Iterator[bytes]:
    """Primitive streams: [1 byte type][uint32 len][payload]. Yields payloads. A truncated record raises (an oracle that stops
    silently on a short read would report fewer objects, and fewer objects pass more checks)."""
    i = 0
    while i < len(blob):
        if i + 5 > len(blob):
            raise ValueError(f"truncated primitive header at {i} of {len(blob)}")
        n = struct.unpack("<I", blob[i + 1:i + 5])[0]
        if i + 5 + n > len(blob):
            raise ValueError(f"truncated primitive at {i}: {n} bytes of {len(blob) - i - 5}")
        yield blob[i + 5:i + 5 + n]
        i += 5 + n


def _net(idx: int, nets: list[str]) -> str | None:
    return nets[idx] if idx != 0xFFFF and 0 <= idx < len(nets) else None


def _mm(v: int) -> float:
    return v * UNIT_MM


# ---------------------------------------------------------------------------------------------------------------- records
@dataclasses.dataclass
class Pad:
    comp: int | None        # component index, None for a free pad
    ref: str | None         # owning designator
    name: str
    x: float
    y: float
    xs: float               # top-layer size x / y (local frame, before rotation)
    ys: float
    shape: int              # top shape: 1 round, 2 rectangular, 3 octagonal, 9 rounded rectangle
    layer: int
    hole: float
    plated: bool
    rot: float
    net: str | None

    def extent(self) -> tuple[float, float, float, float]:
        """Axis-aligned copper bbox (x0, y0, x1, y1), rotation applied for 90-degree multiples and general angles."""
        t = math.radians(self.rot)
        hw = (abs(self.xs * math.cos(t)) + abs(self.ys * math.sin(t))) / 2
        hh = (abs(self.xs * math.sin(t)) + abs(self.ys * math.cos(t))) / 2
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)


@dataclasses.dataclass
class Track:
    layer: int
    net: str | None
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    comp: int | None


@dataclasses.dataclass
class Arc:
    layer: int
    net: str | None
    cx: float
    cy: float
    r: float
    a1: float
    a2: float
    width: float
    comp: int | None

    def points(self, n: int = 16) -> list[tuple[float, float]]:
        sweep = (self.a2 - self.a1) % 360.0 or 360.0
        return [(self.cx + self.r * math.cos(math.radians(self.a1 + sweep * k / n)),
                 self.cy + self.r * math.sin(math.radians(self.a1 + sweep * k / n))) for k in range(n + 1)]


@dataclasses.dataclass
class Via:
    net: str | None
    x: float
    y: float
    dia: float
    hole: float
    layer_from: int
    layer_to: int


@dataclasses.dataclass
class Region:
    layer: int
    net: str | None
    kind: int                   # 0 copper, 1 polygon cut-out, 2 named, 3 board cut-out
    keepout: bool               # a keep-out region: on the Keep-Out layer or flagged
    poured: bool                # belongs to a polygon pour
    comp: int | None
    points: list[tuple[float, float]]
    holes: list[list[tuple[float, float]]]
    props: dict[str, str]
    polygon: int | None = None


@dataclasses.dataclass
class Component:
    index: int
    ref: str
    pattern: str
    x: float
    y: float
    rotation: float
    layer: str                  # TOP | BOTTOM
    props: dict[str, str]


@dataclasses.dataclass
class Body:
    comp: int | None
    layer: int
    points: list[tuple[float, float]]
    props: dict[str, str]

    def bbox(self):
        if not self.points:
            return None
        xs, ys = [p[0] for p in self.points], [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


def _parse_pad(subs: list[bytes]) -> dict:
    name_len = subs[0][0] if subs[0] else 0
    name = subs[0][1:1 + name_len].decode("latin-1", "replace")
    g = subs[4]
    d = {"name": name, "layer": g[0], "net_idx": struct.unpack("<H", g[3:5])[0], "comp_idx": struct.unpack("<H", g[7:9])[0]}
    x, y, xs, ys = struct.unpack("<4i", g[13:29])
    d.update(x=_mm(x), y=_mm(y), xs=_mm(xs), ys=_mm(ys))
    d["hole"] = _mm(struct.unpack("<i", g[45:49])[0]) if len(g) >= 49 else 0.0
    d["shape"] = g[49] if len(g) > 49 else 2
    d["rot"] = struct.unpack("<d", g[52:60])[0] % 360 if len(g) >= 60 else 0.0
    d["plated"] = bool(g[60]) if len(g) > 60 else True
    return d


def _walk_pads(blob: bytes) -> Iterator[dict]:
    i = 0
    while i < len(blob) and blob[i] == 2:
        i += 1
        subs = []
        for _ in range(6):
            n = struct.unpack("<I", blob[i:i + 4])[0] & 0xFFFFFF
            subs.append(blob[i + 4:i + 4 + n])
            i += 4 + n
        yield _parse_pad(subs)


def _parse_track(p: bytes, nets) -> Track:
    x1, y1, x2, y2, w = struct.unpack("<5i", p[13:33])
    c = struct.unpack("<H", p[7:9])[0]
    return Track(p[0], _net(struct.unpack("<H", p[3:5])[0], nets), _mm(x1), _mm(y1), _mm(x2), _mm(y2), _mm(w), None if c == 0xFFFF else c)


def _parse_arc(p: bytes, nets) -> Arc:
    cx, cy, r = struct.unpack("<3i", p[13:25])
    a1, a2 = struct.unpack("<2d", p[25:41])
    w = struct.unpack("<i", p[41:45])[0]
    c = struct.unpack("<H", p[7:9])[0]
    return Arc(p[0], _net(struct.unpack("<H", p[3:5])[0], nets), _mm(cx), _mm(cy), _mm(r), a1, a2, _mm(w), None if c == 0xFFFF else c)


def _parse_region(p: bytes, nets, shape: bool = False) -> Region:
    tl = struct.unpack("<I", p[18:22])[0]
    props = kv(p[22:22 + tl].decode("latin-1", "replace").strip("\0"))
    n = struct.unpack("<I", p[22 + tl:26 + tl])[0]
    data = p[26 + tl:]
    pts, holes = [], []
    if not shape and len(data) >= 16 * n:
        for k in range(n):
            x, y = struct.unpack("<2d", data[16 * k:16 * k + 16])
            pts.append((x * UNIT_MM, y * UNIT_MM))
        pos = 16 * n
        for _ in range(struct.unpack("<H", p[14:16])[0]):
            if pos + 4 > len(data):
                break
            hn = struct.unpack("<I", data[pos:pos + 4])[0]
            pos += 4
            if pos + 16 * hn > len(data):
                break
            holes.append([(a * UNIT_MM, b * UNIT_MM) for a, b in struct.iter_unpack("<2d", data[pos:pos + 16 * hn])])
            pos += 16 * hn
    elif shape and n and len(data) >= 37 * n:
        for k in range(n):
            x, y = struct.unpack("<ii", data[37 * k + 1:37 * k + 9])
            pts.append((x * UNIT_MM, y * UNIT_MM))
    poly = struct.unpack("<H", p[5:7])[0]
    c = struct.unpack("<H", p[7:9])[0]
    kind = int(props.get("KIND", "0") or 0)
    keepout = p[0] == L_KEEPOUT or props.get("KEEPOUT", "FALSE").upper() == "TRUE" or props.get("ISKEEPOUT", "FALSE").upper() == "TRUE"
    return Region(p[0], _net(struct.unpack("<H", p[3:5])[0], nets), kind, keepout, poly != 0xFFFF, None if c == 0xFFFF else c,
                  pts, holes, props, None if poly == 0xFFFF else poly)


def _parse_body(p: bytes) -> Body:
    tl = struct.unpack("<I", p[18:22])[0]
    props = kv(p[22:22 + tl].decode("latin-1", "replace").strip("\0"))
    rest = p[22 + tl:]
    n = struct.unpack("<I", rest[:4])[0] if len(rest) >= 4 else 0
    data = rest[4:]
    pts = []
    if len(data) >= 16 * n:
        for k in range(n):
            x, y = struct.unpack("<2d", data[16 * k:16 * k + 16])
            pts.append((x * UNIT_MM, y * UNIT_MM))
    c = struct.unpack("<H", p[7:9])[0]
    return Body(None if c == 0xFFFF else c, p[0], pts, props)


# ---------------------------------------------------------------------------------------------------------------- PcbDoc
class PcbDoc:
    def __init__(self, path) -> None:
        self.path = pathlib.Path(path)
        self._ole = olefile.OleFileIO(str(self.path))
        self._c: dict = {}

    def close(self) -> None:
        self._ole.close()

    def __enter__(self):
        return self

    def __exit__(self, *a) -> None:
        self.close()

    def stream(self, name: str) -> bytes:
        parts = name.split("/")
        return self._ole.openstream(parts).read() if self._ole.exists(parts) else b""

    def count(self, name: str) -> int | None:
        """The record count Altium stores in `<name>/Header` (uint32), None when the header is absent."""
        parts = [name, "Header"]
        return struct.unpack("<I", self._ole.openstream(parts).read()[:4])[0] if self._ole.exists(parts) else None

    def checked(self, stream_name: str, records: list) -> list:
        """Return `records` after checking their number against the stream header: a reader that lost records must not pass."""
        want = self.count(stream_name)
        if want is not None and want != len(records):
            raise ValueError(f"{self.path.name}: {stream_name} header says {want} records, the reader found {len(records)}")
        return records

    def _memo(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    # -- Board6
    def board(self) -> dict[str, str]:
        """Board6 key/values (uppercase keys), including the stack families V9_STACK_LAYER<n>_*, LAYER_V8_<n>*, legacy LAYER<n>*."""
        def f():
            b = self.stream("Board6/Data")
            if len(b) < 4:
                return {}
            n = struct.unpack("<I", b[:4])[0] & 0xFFFFFF
            return kv(b[4:4 + n].rstrip(b"\0").decode("latin-1", "replace"))
        return self._memo("board", f)

    def nets(self) -> list[str]:
        return self._memo("nets", lambda: [r.get("NAME", "") for r in self.checked("Nets6", _text_records(self.stream("Nets6/Data")))])

    def components(self) -> list[Component]:
        def f():
            out = []
            for i, r in enumerate(self.checked("Components6", _text_records(self.stream("Components6/Data")))):
                def num(k, default=0.0):
                    try:
                        return mil_value(r.get(k, "")) if k in ("X", "Y") else float(r.get(k, "").strip() or default)
                    except ValueError:
                        return default
                out.append(Component(i, r.get("SOURCEDESIGNATOR") or r.get("DESIGNATOR", ""), r.get("PATTERN", ""), num("X"), num("Y"),
                                     num("ROTATION"), r.get("LAYER", "TOP"), r))
            return out
        return self._memo("components", f)

    def pads(self) -> list[Pad]:
        def f():
            nets, comps = self.nets(), self.components()
            out = []
            for d in self.checked("Pads6", list(_walk_pads(self.stream("Pads6/Data")))):
                ci = d["comp_idx"]
                comp = ci if ci != 0xFFFF and ci < len(comps) else None
                out.append(Pad(comp, comps[comp].ref if comp is not None else None, d["name"], d["x"], d["y"], d["xs"], d["ys"],
                               d["shape"], d["layer"], d["hole"], d["plated"], d["rot"], _net(d["net_idx"], nets)))
            return out
        return self._memo("pads", f)

    def tracks(self) -> list[Track]:
        return self._memo("tracks", lambda: [_parse_track(p, self.nets()) for p in self.checked("Tracks6", list(_prims(self.stream("Tracks6/Data"))))])

    def arcs(self) -> list[Arc]:
        return self._memo("arcs", lambda: [_parse_arc(p, self.nets()) for p in self.checked("Arcs6", list(_prims(self.stream("Arcs6/Data"))))])

    def vias(self) -> list[Via]:
        def f():
            out = []
            for p in self.checked("Vias6", list(_prims(self.stream("Vias6/Data")))):
                x, y, dia, hole = struct.unpack("<4i", p[13:29])
                out.append(Via(_net(struct.unpack("<H", p[3:5])[0], self.nets()), _mm(x), _mm(y), _mm(dia), _mm(hole), p[29], p[30]))
            return out
        return self._memo("vias", f)

    def regions(self) -> list[Region]:
        def f():
            out = []
            seen = set()
            for sname in ("Regions6", "ShapeBasedRegions6"):
                for p in self.checked(sname, list(_prims(self.stream(sname + "/Data")))):
                    r = _parse_region(p, self.nets(), shape=sname.startswith("Shape"))
                    key = (r.layer, r.comp, r.kind, tuple((round(x, 3), round(y, 3)) for x, y in r.points))
                    if key not in seen:
                        seen.add(key)
                        out.append(r)
            return out
        return self._memo("regions", f)

    def polygons(self) -> list[dict]:
        """Polygons6 records (pours): props as parsed key/values plus decoded `net`, `layer`, `name`."""
        def f():
            out = []
            for r in _text_records(self.stream("Polygons6/Data")):
                try:
                    k = int(r.get("NET", ""))
                except ValueError:
                    k = -1
                try:
                    name = "".join(chr(int(c)) for c in r.get("NAME", "").split(",") if c.strip())
                except ValueError:
                    name = r.get("NAME", "")
                out.append({**r, "net": self.nets()[k] if 0 <= k < len(self.nets()) else None, "name": name})
            return out
        return self._memo("polygons", f)

    def fills(self) -> list[dict]:
        out = []
        for p in _prims(self.stream("Fills6/Data")):
            if len(p) >= 37:
                x1, y1, x2, y2 = struct.unpack("<4i", p[13:29])
                out.append({"layer": p[0], "net": _net(struct.unpack("<H", p[3:5])[0], self.nets()), "x1": _mm(x1), "y1": _mm(y1),
                            "x2": _mm(x2), "y2": _mm(y2), "rot": struct.unpack("<d", p[29:37])[0]})
        return out

    def bodies(self) -> list[Body]:
        def f():
            out = []
            for p in self.checked("ComponentBodies6", list(_prims(self.stream("ComponentBodies6/Data")))):
                out.append(_parse_body(p))
            return out
        return self._memo("bodies", f)

    def rules(self) -> list[dict[str, str]]:
        """Rules6 records: every key/value (RULEKIND, NAME, ENABLED, SCOPE1EXPRESSION, GAP, ...), uppercase keys."""
        return self._memo("rules", lambda: self.checked("Rules6", _text_records(self.stream("Rules6/Data"), skip=2)))

    def classes(self) -> list[dict[str, str]]:
        return _text_records(self.stream("Classes6/Data"))

    # -- board outline from Board6 (VX/VY keys), mm
    def outline(self) -> list[tuple[float, float]]:
        b, pts, i = self.board(), [], 0
        while f"KIND{i}" in b or f"VX{i}" in b:
            try:
                pts.append((mil_value(b[f"VX{i}"]), mil_value(b[f"VY{i}"])))
            except (KeyError, ValueError):
                break
            i += 1
        return pts

    # -- stack
    def stack(self) -> list[dict]:
        """The layer stack from the V9_STACK_LAYER<n>_* family (authoritative: Altium reads it, spike 2026-11-27), top to bottom, only
        the layers from the first to the last copper layer: copper rows and the dielectrics between them. Each row:
        {"n", "id", "name", "kind": "copper"|"dielectric", "cop_mm", "diel_mm", "er", "type", "material"}."""
        b = self.board()
        rows = []
        for n in range(1, 200):
            lid = b.get(f"V9_STACK_LAYER{n}_LAYERID")
            if lid is not None:
                rows.append(_stack_row(b, f"V9_STACK_LAYER{n}_", lid, n))
        cu = [i for i, r in enumerate(rows) if r["kind"] == "copper"]
        return rows[cu[0]:cu[-1] + 1] if cu else []

    def stack_v8(self) -> list[dict]:
        """The V8 copy (LAYER_V8_<n>*), same shape as stack()."""
        b = self.board()
        rows = [_stack_row(b, f"LAYER_V8_{n}", b[f"LAYER_V8_{n}LAYERID"], n) for n in range(1, 200) if f"LAYER_V8_{n}LAYERID" in b]
        cu = [i for i, r in enumerate(rows) if r["kind"] == "copper"]
        return rows[cu[0]:cu[-1] + 1] if cu else []

    def close_all(self) -> None:
        self.close()


def _f(b: dict, key: str) -> float | None:
    v = b.get(key)
    if v in (None, ""):
        return None
    try:
        return mil_value(v)
    except ValueError:
        return None


def _stack_row(b: dict, p: str, lid: str, n: int) -> dict:
    er = b.get(p + "DIELCONST")
    try:
        er = float(er) if er not in (None, "") else None
    except ValueError:
        er = None
    cop, diel = _f(b, p + "COPTHICK"), _f(b, p + "DIELHEIGHT")
    kind = "copper" if cop is not None and diel is None else "dielectric" if diel is not None else "other"
    return {"n": n, "id": lid, "name": b.get(p + "NAME", ""), "kind": kind, "cop_mm": cop, "diel_mm": diel, "er": er,
            "type": b.get(p + "DIELTYPE"), "material": b.get(p + "DIELMATERIAL", "")}


# ---------------------------------------------------------------------------------------------------------------- PcbLib
@dataclasses.dataclass
class Footprint:
    name: str
    description: str
    pads: list[Pad]
    tracks: list[Track]
    arcs: list[Arc]
    regions: list[Region]
    bodies: list[Body]
    n_texts: int = 0

    def layer_segments(self, layer: int) -> list:
        return [t for t in self.tracks if t.layer == layer] + [a for a in self.arcs if a.layer == layer]

    def layer_points(self, layer: int) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for t in self.tracks:
            if t.layer == layer:
                pts += [(t.x1, t.y1), (t.x2, t.y2)]
        for a in self.arcs:
            if a.layer == layer:
                pts += a.points()
        for r in self.regions:
            if r.layer == layer:
                pts += r.points
        return pts


def _blocks(d: bytes, i: int, n: int):
    out = []
    for _ in range(n):
        size = struct.unpack("<I", d[i:i + 4])[0] & 0xFFFFFF
        out.append(d[i + 4:i + 4 + size])
        i += 4 + size
    return out, i


def _footprint_from_data(name: str, desc: str, d: bytes) -> Footprint:
    n0 = struct.unpack("<I", d[:4])[0] & 0xFFFFFF
    i = 4 + n0
    fp = Footprint(name, desc, [], [], [], [], [])
    nets: list[str] = []
    while i < len(d):
        kind = d[i]
        i += 1
        if kind == 2:
            subs, i = _blocks(d, i, 6)
            pd = _parse_pad(subs)
            fp.pads.append(Pad(None, None, pd["name"], pd["x"], pd["y"], pd["xs"], pd["ys"], pd["shape"], pd["layer"], pd["hole"],
                               pd["plated"], pd["rot"], None))
        elif kind in (1, 3, 4, 6, 11, 12):
            (blk,), i = _blocks(d, i, 1)
            if kind == 4 and len(blk) >= 33:
                fp.tracks.append(_parse_track(blk, nets))
            elif kind == 1 and len(blk) >= 45:
                fp.arcs.append(_parse_arc(blk, nets))
            elif kind == 11 and len(blk) >= 26:
                try:
                    fp.regions.append(_parse_region(blk, nets))
                except (struct.error, ValueError):
                    pass
            elif kind == 12 and len(blk) >= 26:
                try:
                    fp.bodies.append(_parse_body(blk))
                except (struct.error, ValueError):
                    pass
        elif kind == 5:
            _, i = _blocks(d, i, 2)
            fp.n_texts += 1
        else:
            raise ValueError(f"unknown object type {kind} in footprint {name}")
    return fp


def read_pcblib(path) -> list[Footprint]:
    """Every footprint of a PcbLib (sorted by name). Raises on an unreadable footprint (an oracle that skips is an oracle that passes)."""
    out = []
    ole = olefile.OleFileIO(str(path))
    try:
        for entry in ole.listdir(streams=True, storages=False):
            if len(entry) == 2 and entry[1] == "Parameters":
                par = kv(ole.openstream(entry).read().decode("cp1252", "replace"))
                if "PATTERN" not in par:
                    continue
                data = ole.openstream([entry[0], "Data"]).read() if ole.exists([entry[0], "Data"]) else b""
                out.append(_footprint_from_data(par["PATTERN"], par.get("DESCRIPTION", ""), data) if data
                           else Footprint(par["PATTERN"], "", [], [], [], [], []))
    finally:
        ole.close()
    return sorted(out, key=lambda f: f.name)


# ---------------------------------------------------------------------------------------------------------------- board helpers
import heapq
import re as _re

_GND_NAME = _re.compile(r"^(?:[ADP]?GND\w*|VSS\w*|0V)$", _re.I)


def ground_nets(doc: PcbDoc) -> set[str]:
    """Ground nets by rule: names GND / AGND / DGND / PGND / VSS*, or (no such name) the net with the most pads."""
    names = {n for n in doc.nets() if _GND_NAME.match(n)}
    if names:
        return names
    count: dict[str, int] = {}
    for p in doc.pads():
        if p.net:
            count[p.net] = count.get(p.net, 0) + 1
    return {max(count, key=count.get)} if count else set()


def copper_layer_bytes(doc: PcbDoc) -> list[int]:
    """Track layer bytes of the copper layers in stack order: Top 1, inner 2.., Bottom 32."""
    n = sum(1 for r in doc.stack() if r["kind"] == "copper")
    return [1] + list(range(2, n)) + [32] if n >= 2 else [1]


def adjacent_inner(doc: PcbDoc, side: str) -> int | None:
    """The copper layer next to the outer layer of `side` (TOP | BOTTOM), from the stack order; None on a 2-layer board."""
    ls = copper_layer_bytes(doc)
    if len(ls) < 3:
        return None
    return ls[1] if side.upper().startswith("T") else ls[-2]


def comp_bbox(doc: PcbDoc, idx: int) -> tuple[float, float, float, float]:
    """Bounding box of a placed component's pad copper and 3D bodies."""
    boxes = [p.extent() for p in doc.pads() if p.comp == idx]
    boxes += [b.bbox() for b in doc.bodies() if b.comp == idx and b.bbox()]
    if not boxes:
        raise ValueError(f"component {idx} has no pads or body")
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def seg_hits_rect(x1: float, y1: float, x2: float, y2: float, half: float, rect) -> bool:
    """A track segment of half width `half` touches the rectangle (Liang-Barsky on the rectangle grown by `half`)."""
    x0, y0, xa, ya = rect[0] - half, rect[1] - half, rect[2] + half, rect[3] + half
    t0, t1, dx, dy = 0.0, 1.0, x2 - x1, y2 - y1
    for p, q in ((-dx, x1 - x0), (dx, xa - x1), (-dy, y1 - y0), (dy, ya - y1)):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def route_length(doc: PcbDoc, net: str, a: Pad, b: Pad) -> float | None:
    """Shortest routed copper length (mm) from pad `a` to pad `b` over the tracks, arcs and vias of `net`; None when not connected.
    Track ends inside a pad of the net join that pad; vias join every copper layer they span at the same position."""
    pads = [p for p in doc.pads() if p.net == net]
    snap = lambda x, y: (round(x / 0.01), round(y / 0.01))

    def pad_of(x, y, layer):
        for i, p in enumerate(pads):
            x0, y0, x1, y1 = p.extent()
            if x0 - 0.01 <= x <= x1 + 0.01 and y0 - 0.01 <= y <= y1 + 0.01 and (p.layer in (layer, 74)):
                return ("pad", i)
        return None

    def node(x, y, layer):
        return pad_of(x, y, layer) or (layer, *snap(x, y))

    adj: dict = {}

    def edge(u, v, w):
        adj.setdefault(u, []).append((v, w))
        adj.setdefault(v, []).append((u, w))
    segs = [(t.layer, t.x1, t.y1, t.x2, t.y2) for t in doc.tracks() if t.net == net and is_copper(t.layer)]
    for r in doc.arcs():
        if r.net == net and is_copper(r.layer):
            pts = r.points()
            segs += [(r.layer, p[0], p[1], q[0], q[1]) for p, q in zip(pts, pts[1:])]
    # a track end that lands on the middle of another track of the net splits that track there (T junction)
    cuts: dict[int, list[tuple[float, float]]] = {i: [] for i in range(len(segs))}
    for i, (la, ax, ay, bx, by) in enumerate(segs):
        for j, (lb, cx, cy, dx_, dy_) in enumerate(segs):
            if i == j or la != lb:
                continue
            L2 = (dx_ - cx) ** 2 + (dy_ - cy) ** 2
            for ex, ey in ((ax, ay), (bx, by)):
                s = ((ex - cx) * (dx_ - cx) + (ey - cy) * (dy_ - cy)) / L2 if L2 else 0.0
                if 0.0 < s < 1.0 and math.hypot(cx + s * (dx_ - cx) - ex, cy + s * (dy_ - cy) - ey) <= 0.02:
                    cuts[j].append((ex, ey))
    for j, (lb, cx, cy, dx_, dy_) in enumerate(segs):
        pts = sorted(set(cuts[j]), key=lambda q: (q[0] - cx) ** 2 + (q[1] - cy) ** 2)
        chain = [(cx, cy)] + pts + [(dx_, dy_)]
        for (px, py), (qx, qy) in zip(chain, chain[1:]):
            edge(node(px, py, lb), node(qx, qy, lb), math.hypot(qx - px, qy - py))
    layers = copper_layer_bytes(doc)
    for v in doc.vias():
        if v.net == net:
            span = [l for l in layers if v.layer_from <= l <= v.layer_to] or layers
            for l1, l2 in zip(span, span[1:]):
                edge(node(v.x, v.y, l1), node(v.x, v.y, l2), 0.0)
    src, dst = ("pad", pads.index(a)), ("pad", pads.index(b))
    dist, heap = {src: 0.0}, [(0.0, 0, src)]
    k = 0
    while heap:
        d, _, u = heapq.heappop(heap)
        if u == dst:
            return d
        if d > dist.get(u, 1e18):
            continue
        for v, w in adj.get(u, ()):
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                k += 1
                heapq.heappush(heap, (d + w, k, v))
    return None


# ------------------------------------------------------------------------------------------------------------ board-edge gaps
def _pt_seg(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / n))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _seg_seg(a, b) -> float:
    """Distance between segments a=(x1,y1,x2,y2) and b (0 when they cross)."""
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    p1, p2, p3, p4 = a[:2], a[2:], b[:2], b[2:]
    if ccw(p1, p3, p4) * ccw(p2, p3, p4) < 0 and ccw(p1, p2, p3) * ccw(p1, p2, p4) < 0:
        return 0.0
    return min(_pt_seg(*p1, *b), _pt_seg(*p2, *b), _pt_seg(*p3, *a), _pt_seg(*p4, *a))


def _rect_seg(r, s) -> float:
    if seg_hits_rect(s[0], s[1], s[2], s[3], 0.0, r):
        return 0.0
    cs = ((r[0], r[1]), (r[0], r[3]), (r[2], r[1]), (r[2], r[3]))
    ends = [math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3])) for x, y in ((s[0], s[1]), (s[2], s[3]))]
    return min([_pt_seg(x, y, *s) for x, y in cs] + ends)


def edge_gaps(doc: PcbDoc) -> list[tuple[str, str, float]]:
    """Gap in mm from the board outline (the Board6 vertex polygon) to: each placed component's plated pads and 3D bodies
    ("component", designator), each copper track ("track", net, edge of the copper) and each via ("via", net). Sorted by gap."""
    o = doc.outline()
    if len(o) < 3:
        raise ValueError("board outline has fewer than 3 vertices")
    segs = [(o[i][0], o[i][1], o[(i + 1) % len(o)][0], o[(i + 1) % len(o)][1]) for i in range(len(o))]
    segs = [s for s in segs if (s[0], s[1]) != (s[2], s[3])]
    out = []
    for c in doc.components():
        try:
            boxes = [p.extent() for p in doc.pads() if p.comp == c.index and p.plated]
            boxes += [b.bbox() for b in doc.bodies() if b.comp == c.index and b.bbox()]
            if not boxes:
                continue
            r = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        except ValueError:
            continue
        out.append(("component", c.ref, min(_rect_seg(r, s) for s in segs)))
    for t in doc.tracks():
        if is_copper(t.layer):
            out.append(("track", t.net or "", min(_seg_seg((t.x1, t.y1, t.x2, t.y2), s) for s in segs) - t.width / 2))
    for v in doc.vias():
        out.append(("via", v.net or "", min(_pt_seg(v.x, v.y, *s) for s in segs) - v.dia / 2))
    return sorted(out, key=lambda r: r[2])
