"""Read Altium PcbDoc printed circuit board files."""
import collections
import math
import pathlib
import struct

from .ole import AltiumReadError, open_doc, stream, text_records


def mil_to_mm(val: str | float | int) -> float:
    """Convert mil string or float to mm, rounded to 4 decimal places."""
    if isinstance(val, (int, float)):
        return round(float(val) * 0.0254, 4)
    s = str(val).strip()
    if s.lower().endswith("mil"):
        return round(float(s[:-3].strip()) * 0.0254, 4)
    if s.lower().endswith("mm"):
        return round(float(s[:-2].strip()), 4)
    return round(float(s) * 0.0254, 4)


_MIL4_TO_MM = 0.0254 / 10000   # PcbDoc binary coordinates: 1/10000 mil
_SILK_LAYERS = (33, 34)         # Top Overlay, Bottom Overlay
_MECH_LAYERS = range(57, 73)    # Mechanical 1..16 (3D body outline, courtyard, assembly)


def _primitive_records(blob: bytes):
    """Yield the payload of each record in a primitive stream (Tracks6, Arcs6, ComponentBodies6...):
    1 type byte, uint32 length, payload. A truncated tail ends the iteration."""
    i = 0
    while i + 5 <= len(blob):
        n = struct.unpack("<I", blob[i + 1:i + 5])[0]
        if i + 5 + n > len(blob):
            return
        yield blob[i + 5:i + 5 + n]
        i += 5 + n


def _grow(box: list | None, x: float, y: float) -> list:
    if box is None:
        return [x, y, x, y]
    return [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]


def _body_points(rec: bytes, shape_based: bool) -> list[tuple[float, float]]:
    """Outline vertices (mm) of one 3D component body record: 18 header bytes (layer, flags, net, polygon,
    component index...), uint32 text length, text, uint32 vertex count, then the vertices."""
    tl = struct.unpack("<I", rec[18:22])[0]
    rest = rec[22 + tl:]
    n = struct.unpack("<I", rest[:4])[0]
    data = rest[4:]
    pts = []
    if not shape_based and len(data) >= 16 * n:
        for k in range(n):
            x, y = struct.unpack("<dd", data[16 * k:16 * k + 16])
            pts.append((x * _MIL4_TO_MM, y * _MIL4_TO_MM))
    elif shape_based and n and len(data) % 37 == 0:
        # ShapeBasedComponentBodies6: 37 bytes per vertex (round flag, int32 x, y, centre x, y, radius, 2 angles)
        for k in range(len(data) // 37):
            x, y = struct.unpack("<ii", data[37 * k + 1:37 * k + 9])
            pts.append((x * _MIL4_TO_MM, y * _MIL4_TO_MM))
    return pts


def _arc_extent_points(cx: float, cy: float, r: float, a1: float, a2: float) -> list[tuple[float, float]]:
    """End points of an arc plus the axis extremes it sweeps (angles in degrees, counter-clockwise)."""
    sweep = (a2 - a1) % 360.0 or 360.0
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (a1, a2)]
    for k in (0.0, 90.0, 180.0, 270.0):
        if (k - a1) % 360.0 <= sweep:
            pts.append((cx + r * math.cos(math.radians(k)), cy + r * math.sin(math.radians(k))))
    return pts


def _footprint_geometry(ole, n_comps: int) -> tuple[dict[int, list], dict[int, list]]:
    """Per component index: bbox [x1, y1, x2, y2] in mm of its 3D bodies, and of its outline primitives
    (silkscreen tracks/arcs, else the mechanical-layer ones). Missing or unreadable streams give empty dicts."""
    bodies: dict[int, list] = {}
    silk: dict[int, list] = {}
    mech: dict[int, list] = {}

    def idx(rec: bytes):
        i = struct.unpack("<H", rec[7:9])[0]
        return i if i < n_comps else None

    for name, shape_based in (("ComponentBodies6/Data", False), ("ShapeBasedComponentBodies6/Data", True)):
        if bodies or not ole.exists(name.split("/")):
            continue
        try:
            for rec in _primitive_records(stream(ole, name)):
                i = idx(rec)
                if i is None:
                    continue
                for x, y in _body_points(rec, shape_based):
                    bodies[i] = _grow(bodies.get(i), x, y)
        except (struct.error, AltiumReadError):
            bodies = {}

    def layer_box(layer: int):
        return silk if layer in _SILK_LAYERS else mech if layer in _MECH_LAYERS else None

    try:
        if ole.exists(["Tracks6", "Data"]):
            for rec in _primitive_records(stream(ole, "Tracks6/Data")):
                box, i = layer_box(rec[0]), idx(rec)
                if box is None or i is None:
                    continue
                x1, y1, x2, y2 = (v * _MIL4_TO_MM for v in struct.unpack("<4i", rec[13:29]))
                box[i] = _grow(_grow(box.get(i), x1, y1), x2, y2)
        if ole.exists(["Arcs6", "Data"]):
            for rec in _primitive_records(stream(ole, "Arcs6/Data")):
                box, i = layer_box(rec[0]), idx(rec)
                if box is None or i is None:
                    continue
                cx, cy, r = (v * _MIL4_TO_MM for v in struct.unpack("<3i", rec[13:25]))
                a1, a2 = struct.unpack("<2d", rec[25:41])
                for x, y in _arc_extent_points(cx, cy, r, a1, a2):
                    box[i] = _grow(box.get(i), x, y)
    except (struct.error, AltiumReadError):
        silk, mech = {}, {}

    outline = {i: silk.get(i) or mech.get(i) for i in set(silk) | set(mech)}
    return bodies, outline


def read_pcbdoc(path, geometry: bool = False) -> dict:
    """Read an Altium .PcbDoc file into a structured dictionary.

    geometry=True also reads the footprint outlines and adds two keys to every component:
      body_bbox_mm     [x1, y1, x2, y2] of the union of the component's 3D bodies, or None
      outline_bbox_mm  [x1, y1, x2, y2] of its silkscreen (else mechanical-layer) tracks and arcs, or None
    Everything else is unchanged and identical with geometry=False."""
    p = pathlib.Path(path)
    with open_doc(p) as ole:
        raw_comps = text_records(stream(ole, "Components6/Data"), prefix=0)
        raw_nets = text_records(stream(ole, "Nets6/Data"), prefix=0)
        rules = text_records(stream(ole, "Rules6/Data"), prefix=2)
        classes = text_records(stream(ole, "Classes6/Data"), prefix=0)
        pad_blob = stream(ole, "Pads6/Data")
        bodies, outlines = _footprint_geometry(ole, len(raw_comps)) if geometry else ({}, {})
        via_blob = _optional_stream(ole, "Vias6/Data")
        track_blob = _optional_stream(ole, "Tracks6/Data")
        arc_blob = _optional_stream(ole, "Arcs6/Data")
        text_blob = _optional_stream(ole, "Texts6/Data")

    components = []
    for ci, c in enumerate(raw_comps):
        ref = c.get("SOURCEDESIGNATOR") or c.get("DESIGNATOR", "")
        pattern = c.get("PATTERN", "")
        lib_ref = c.get("SOURCELIBREFERENCE") or c.get("LIBREFERENCE", "")
        x_mm = mil_to_mm(c.get("X", "0"))
        y_mm = mil_to_mm(c.get("Y", "0"))
        try:
            rotation = float(c.get("ROTATION", "0").strip())
        except (ValueError, TypeError):
            rotation = 0.0
        layer = c.get("LAYER", "")
        components.append({
            "ref": ref,
            "pattern": pattern,
            "lib_ref": lib_ref,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "rotation": rotation,
            "layer": layer,
        })
        if geometry:
            def rounded(box):
                return [round(v, 4) for v in box] if box else None
            components[-1]["body_bbox_mm"] = rounded(bodies.get(ci))
            components[-1]["outline_bbox_mm"] = rounded(outlines.get(ci))

    nets = [n.get("NAME", "") for n in raw_nets]

    i = 0
    pads = []
    while i < len(pad_blob):
        if pad_blob[i] != 2:
            raise AltiumReadError(str(p), f"invalid pad record type {pad_blob[i]} at offset {i}")
        i += 1
        subs = []
        for _ in range(6):
            if i + 4 > len(pad_blob):
                raise AltiumReadError(str(p), f"unexpected EOF in pad subrecord header at offset {i}")
            n = struct.unpack("<I", pad_blob[i:i + 4])[0]
            subs.append(pad_blob[i + 4:i + 4 + n])
            i += 4 + n

        name_len = subs[0][0] if len(subs[0]) > 0 else 0
        name = subs[0][1:1 + name_len].decode("latin-1", "replace")
        s5 = subs[4]
        layer = s5[0]
        net_idx = struct.unpack("<H", s5[3:5])[0]
        comp_idx = struct.unpack("<H", s5[7:9])[0]
        x, y = struct.unpack("<ii", s5[13:21])
        sx, sy = struct.unpack("<ii", s5[21:29])

        net_name = nets[net_idx] if (net_idx != 0xFFFF and 0 <= net_idx < len(nets)) else None
        comp_ref = components[comp_idx]["ref"] if (comp_idx != 0xFFFF and 0 <= comp_idx < len(components)) else None

        # Units 1/10000 mil: val / 10000 * 0.0254 mm
        x_mm = round(x / 10000 * 0.0254, 4)
        y_mm = round(y / 10000 * 0.0254, 4)
        sx_mm = round(sx / 10000 * 0.0254, 4)
        sy_mm = round(sy / 10000 * 0.0254, 4)

        pads.append({
            "ref": comp_ref,
            "name": name,
            "net": net_name,
            "layer": layer,
            "x_mm": x_mm,
            "y_mm": y_mm,
            "sx_mm": sx_mm,
            "sy_mm": sy_mm,
        })

    return {
        "file": p.name,
        "components": components,
        "nets": nets,
        "pads": pads,
        "rules": rules,
        "classes": classes,
        "vias": parse_vias(via_blob, nets),
        "drilled_pads": parse_drilled_pads(pad_blob, components),
        "tracks": parse_tracks(track_blob, nets),
        "arcs": parse_arcs(arc_blob, nets),
        "texts": parse_texts(text_blob),
        "regions": [],
    }


def _optional_stream(ole, name: str) -> bytes:
    """Read an OLE stream, or b'' when it is absent or unreadable."""
    try:
        return stream(ole, name)
    except AltiumReadError:
        return b""


def parse_vias(blob: bytes, nets: list[str]) -> list[dict]:
    """Read-only list of vias from the Vias6 stream: position, net, hole and
    diameter in mm. Diameter is the via's primary size field (the size on every
    layer in simple mode); per-layer stack sizes are not read."""
    out = []
    i = 0
    while i + 5 <= len(blob):
        if blob[i] != 3:
            break
        n = struct.unpack("<I", blob[i + 1:i + 5])[0]
        d = blob[i + 5:i + 5 + n]
        i += 5 + n
        if len(d) < 31:
            continue
        net_idx = struct.unpack("<H", d[3:5])[0]
        x, y, dia, hole = struct.unpack("<4i", d[13:29])
        out.append({
            "net": nets[net_idx] if (net_idx != 0xFFFF and 0 <= net_idx < len(nets)) else None,
            "x_mm": round(x / 10000 * 0.0254, 4),
            "y_mm": round(y / 10000 * 0.0254, 4),
            "dia_mm": round(dia / 10000 * 0.0254, 4),
            "hole_mm": round(hole / 10000 * 0.0254, 4),
            "from_layer": d[29],
            "to_layer": d[30],
        })
    return out


def parse_drilled_pads(blob: bytes, components: list[dict]) -> list[dict]:
    """Read-only list of pads with a drill (through-hole and mounting holes) from
    the Pads6 stream: hole size, smallest copper dimension over the top, middle
    and bottom sizes, and the plated flag. Mounting holes are unplated."""
    out = []
    M = 0.0254 / 10000
    i = 0
    while i < len(blob) and blob[i] == 2:
        i += 1
        subs = []
        for _ in range(6):
            if i + 4 > len(blob):
                return out
            n = struct.unpack("<I", blob[i:i + 4])[0]
            subs.append(blob[i + 4:i + 4 + n])
            i += 4 + n
        s5 = subs[4]
        if len(s5) < 61:
            continue
        sizes = struct.unpack("<6i", s5[21:45])
        hole = struct.unpack("<i", s5[45:49])[0]
        if hole <= 0:
            continue
        comp_idx = struct.unpack("<H", s5[7:9])[0]
        name_len = subs[0][0] if subs[0] else 0
        copper = [s for s in sizes if s > 0]
        out.append({
            "ref": components[comp_idx]["ref"] if (comp_idx != 0xFFFF and 0 <= comp_idx < len(components)) else None,
            "name": subs[0][1:1 + name_len].decode("latin-1", "replace"),
            "x_mm": round(struct.unpack("<i", s5[13:17])[0] * M, 4),
            "y_mm": round(struct.unpack("<i", s5[17:21])[0] * M, 4),
            "hole_mm": round(hole * M, 4),
            "min_size_mm": round(min(copper) * M, 4) if copper else 0.0,
            "plated": bool(s5[60]),
        })
    return out


def pad_net_map(doc: dict) -> dict[str, list[str]]:
    """Map net names to sorted deduplicated lists of pad identifiers ['REF-PAD', ...]."""
    if not isinstance(doc, dict):
        doc = read_pcbdoc(doc)
    mapping: dict[str, set[str]] = collections.defaultdict(set)
    for p in doc.get("pads", []):
        net = p.get("net")
        if not net:
            continue
        ref = p.get("ref")
        name = p.get("name", "")
        tag = f"{ref}-{name}" if ref else name
        mapping[net].add(tag)
    return {net: sorted(tags) for net, tags in sorted(mapping.items())}


def parse_tracks(blob: bytes, nets: list[str]) -> list[dict]:
    """Read-only list of tracks from the Tracks6 stream: layer, net, endpoints and width in mm."""
    out = []
    if not blob:
        return out
    try:
        for rec in _primitive_records(blob):
            if len(rec) < 33:
                continue
            layer = rec[0]
            net_idx = struct.unpack("<H", rec[3:5])[0]
            x1, y1, x2, y2 = struct.unpack("<4i", rec[13:29])
            w = struct.unpack("<i", rec[29:33])[0]
            net_name = nets[net_idx] if (net_idx != 0xFFFF and 0 <= net_idx < len(nets)) else None
            out.append({
                "layer": layer,
                "net": net_name,
                "x1_mm": round(x1 * _MIL4_TO_MM, 4),
                "y1_mm": round(y1 * _MIL4_TO_MM, 4),
                "x2_mm": round(x2 * _MIL4_TO_MM, 4),
                "y2_mm": round(y2 * _MIL4_TO_MM, 4),
                "width_mm": round(w * _MIL4_TO_MM, 4),
            })
    except Exception:
        pass
    return out


def parse_arcs(blob: bytes, nets: list[str]) -> list[dict]:
    """Read-only list of arcs from the Arcs6 stream: layer, net, center, radius, angles and width in mm."""
    out = []
    if not blob:
        return out
    try:
        for rec in _primitive_records(blob):
            if len(rec) < 45:
                continue
            layer = rec[0]
            net_idx = struct.unpack("<H", rec[3:5])[0]
            cx, cy, r = struct.unpack("<3i", rec[13:25])
            a1, a2 = struct.unpack("<2d", rec[25:41])
            w = struct.unpack("<i", rec[41:45])[0]
            net_name = nets[net_idx] if (net_idx != 0xFFFF and 0 <= net_idx < len(nets)) else None
            out.append({
                "layer": layer,
                "net": net_name,
                "cx_mm": round(cx * _MIL4_TO_MM, 4),
                "cy_mm": round(cy * _MIL4_TO_MM, 4),
                "r_mm": round(r * _MIL4_TO_MM, 4),
                "a1": round(a1, 2),
                "a2": round(a2, 2),
                "width_mm": round(w * _MIL4_TO_MM, 4),
            })
    except Exception:
        pass
    return out


def parse_texts(blob: bytes) -> list[dict]:
    """Read-only list of silkscreen texts from the Texts6 stream: layer, text, position and height in mm."""
    out = []
    if not blob:
        return out
    try:
        i = 0
        while i + 5 <= len(blob):
            rec_type = blob[i]
            if rec_type != 5:
                break
            fl = struct.unpack("<I", blob[i + 1:i + 5])[0]
            if i + 5 + fl > len(blob):
                break
            fd = blob[i + 5:i + 5 + fl]
            pos = i + 5 + fl
            if pos + 4 > len(blob):
                break
            sl = struct.unpack("<I", blob[pos:pos + 4])[0]
            if pos + 4 + sl > len(blob):
                break
            raw_str = blob[pos + 4:pos + 4 + sl]
            i = pos + 4 + sl
            if len(fd) < 25:
                continue
            layer = fd[0]
            if layer not in _SILK_LAYERS:
                continue
            if raw_str and raw_str[0] == len(raw_str) - 1:
                text = raw_str[1:].decode("latin-1", "replace")
            else:
                text = raw_str.decode("latin-1", "replace")
            x, y, h = struct.unpack("<3i", fd[13:25])
            rot = struct.unpack("<d", fd[27:35])[0] if len(fd) >= 35 else 0.0
            x_mm = round(x * _MIL4_TO_MM, 4)
            y_mm = round(y * _MIL4_TO_MM, 4)
            h_mm = round(h * _MIL4_TO_MM, 4)
            out.append({
                "layer": layer,
                "text": text,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "height_mm": h_mm,
                "x": x_mm,
                "y": y_mm,
                "height": h_mm,
                "rotation": round(rot, 2),
            })
    except Exception:
        pass
    return out

