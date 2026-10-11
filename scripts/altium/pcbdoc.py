"""Read Altium PcbDoc printed circuit board files."""
import collections
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


def read_pcbdoc(path) -> dict:
    """Read an Altium .PcbDoc file into a structured dictionary."""
    p = pathlib.Path(path)
    with open_doc(p) as ole:
        raw_comps = text_records(stream(ole, "Components6/Data"), prefix=0)
        raw_nets = text_records(stream(ole, "Nets6/Data"), prefix=0)
        rules = text_records(stream(ole, "Rules6/Data"), prefix=2)
        classes = text_records(stream(ole, "Classes6/Data"), prefix=0)
        pad_blob = stream(ole, "Pads6/Data")

    components = []
    for c in raw_comps:
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
    }


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
