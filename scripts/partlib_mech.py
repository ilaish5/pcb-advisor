"""Library additions for the physical constraints (stream C): an RF module's antenna keep-out, the mechanical footprints (holes,
keep-outs) of the confirmed constraints, and a check that a 3D body sits where its pads are. Called from partlib.prepare / _write;
kept in its own module so those functions only gain small call sites.
"""
import math
import re

import partlib_generate as gen

RF_RE = re.compile(r"wroom|wrover|mini-?1\b|esp32|esp8266|wi-?fi|\bwlan\b|\bble\b|bluetooth|\blora\b|sx12\d\d|\bantenna\b|"
                   # cellular modules (kiln LTE run, E6: an A7670 sat in the middle of the board with no keep-out); layout.RF_MODULE is the placer's twin
                   r"\blte\b|\bgsm\b|\bgprs\b|\b[45]g\b|cat-?1\b|cat-?m|nb-?iot|cellular|a76\d\d|sim7\d{3}|sim8\d\d|sim900|wh-?lte|"
                   r"\bec2\d|\bbg9\d|\bsara-|quectel|\bnrf\d|zigbee|radio module|rf module", re.I)
MIL = 0.0254
ANTENNA_MIN_MM = 2.0            # the pad-free strip must be at least this deep to be called an antenna side
KEEPOUT_DEFAULT_MM = 15.0       # Espressif asks for this much free board beyond the antenna end of a module: recorded, not enforced
BODY_OFFSET_MM = 0.5            # a 3D body whose centre is farther than this from the pads' centre is reported
SIDE_DEG = {"R": 0, "T": 90, "L": 180, "B": 270}


def _fields(line):
    return line.split("|")


def _geometry(lines):
    """(pad_box, outline_box) in mm from footprint spec lines (mil): the pads, and every other drawn point (silkscreen, mechanical)."""
    pads, other = [], []
    for ln in lines:
        f = _fields(ln)
        try:
            if f[0] == "PAD":
                x, y, w, h = float(f[2]) * MIL, float(f[3]) * MIL, float(f[11]) * MIL, float(f[12]) * MIL
                pads.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
            elif f[0] == "TRACK" and f[6] != gen.KEEPOUT_LAYER_NAME:
                other += [(float(f[1]) * MIL, float(f[2]) * MIL), (float(f[3]) * MIL, float(f[4]) * MIL)]
            elif f[0] == "ARC":
                cx, cy, r = float(f[1]) * MIL, float(f[2]) * MIL, float(f[3]) * MIL
                other += [(cx - r, cy - r), (cx + r, cy + r)]
        except (IndexError, ValueError):
            continue
    if not pads:
        return None, None
    pb = [min(p[0] for p in pads), min(p[1] for p in pads), max(p[2] for p in pads), max(p[3] for p in pads)]
    ob = list(pb)
    for x, y in other:
        ob = [min(ob[0], x), min(ob[1], y), max(ob[2], x), max(ob[3], y)]
    return pb, ob


def rf_module(line, fp):
    """The RF facts of a BOM line's footprint, or None when the part is not a radio module. `line` is the BOM line (mpn, value,
    description, package), `fp` the build footprint ({"name", "lines": [spec lines in mil]}).
    {"antenna_side": "L|R|T|B" or None, "keepout_mm": depth of the pad-free strip, "keepout_box": [x0, y0, x1, y1] mm in footprint
    coordinates, "source": "heuristic"}. The side is the one on which the outline reaches farthest beyond the pads (a module's antenna
    area has no pads); None when no side reaches 2 mm. A guess by name and shape: the Library shows it and the student can override."""
    text = " ".join(str(line.get(k) or "") for k in ("mpn", "value", "description", "package", "role")) + " " + str(fp.get("name") or "")
    if not RF_RE.search(text):
        return None
    pb, ob = _geometry(fp.get("lines", []))
    if pb is None:
        return None
    gaps = {"L": pb[0] - ob[0], "R": ob[2] - pb[2], "B": pb[1] - ob[1], "T": ob[3] - pb[3]}
    side = max(gaps, key=gaps.get)
    if gaps[side] < ANTENNA_MIN_MM:
        return {"antenna_side": None, "keepout_mm": 0.0, "keepout_box": None, "source": "heuristic",
                "note": "radio module, but no side of its outline is free of pads by 2 mm or more: the antenna side is not known"}
    box = {"L": [ob[0], ob[1], pb[0], ob[3]], "R": [pb[2], ob[1], ob[2], ob[3]],
           "B": [ob[0], ob[1], ob[2], pb[1]], "T": [ob[0], pb[3], ob[2], ob[3]]}[side]
    return {"antenna_side": side, "keepout_mm": round(gaps[side], 2), "keepout_box": [round(v, 3) for v in box], "source": "heuristic"}


def apply_rf(fp, rf):
    """Add the antenna keep-out of `rf` (rf_module's answer) to the footprint's spec lines, once. True when lines were added."""
    if not rf or not rf.get("keepout_box"):
        return False
    if any(ln.startswith("REGION|" + gen.KEEPOUT_LAYER_NAME) for ln in fp["lines"]):
        return False
    fp["lines"] += gen.keepout_lines(*rf["keepout_box"])
    return True


def rf_side_degrees(rf):
    """The direction (degrees, 0 = +x, 90 = +y at rotation 0) the antenna faces, or None."""
    return SIDE_DEG.get((rf or {}).get("antenna_side"))


# ---- the 3D body against the pads

def step_bbox(text):
    """[x0, y0, z0, x1, y1, z1] of the CARTESIAN_POINTs of STEP text (mm), or None. A rough box (placement points of the file's
    own axes are in it too), good enough to tell a body that is 2.7 mm off its pads."""
    pts = re.findall(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)", text)
    if not pts:
        return None
    v = [(float(a), float(b), float(c)) for a, b, c in pts]
    return [min(p[i] for p in v) for i in range(3)] + [max(p[i] for p in v) for i in range(3)]


def body_offset_mm(bbox, model, lines):
    """Distance (mm) between the 3D body's centre (its box turned by the model's rz and moved by its dx, dy mil) and the centre of
    the footprint's pads; None when either is unknown."""
    pb, _ = _geometry(lines)
    if bbox is None or pb is None:
        return None
    cx, cy = (bbox[0] + bbox[3]) / 2, (bbox[1] + bbox[4]) / 2
    a = math.radians(float((model or {}).get("rz") or 0))
    x, y = cx * math.cos(a) - cy * math.sin(a), cx * math.sin(a) + cy * math.cos(a)
    x, y = x + float((model or {}).get("dx") or 0) * MIL, y + float((model or {}).get("dy") or 0) * MIL
    return math.hypot(x - (pb[0] + pb[2]) / 2, y - (pb[1] + pb[3]) / 2)


def body_offset_issue(name, bbox, model, lines):
    """"" or a message when the body is farther than BODY_OFFSET_MM from the pads' centre. A centred body is the rule for chips;
    a connector whose body really overhangs its pads is told to look, not condemned."""
    d = body_offset_mm(bbox, model, lines)
    if d is None or d <= BODY_OFFSET_MM:
        return ""
    return (f"the 3D body of footprint {name} is centred {d:.1f} mm from its pads (limit {BODY_OFFSET_MM:g} mm): the model may be "
            "offset (the converter writes a 3D offset of 0, 0, 0), look at it in the 3D view")


def annotate(fpentry, e, line):
    """Called by partlib.prepare for each built footprint (`fpentry` = Build.footprints[name], `e` = the manifest entry, `line` = the
    BOM line): a radio module gets its antenna keep-out in the footprint and `e["rf"]`; a 3D body that sits off its pads is an issue."""
    fp = fpentry["fp"]
    rf = rf_module(line, fp)
    if rf:
        apply_rf(fp, rf)
        e["rf"] = rf
        if rf.get("note"):
            e["issues"].append(rf["note"])
    for step in fpentry.get("steps", [])[:1]:
        try:
            with open(step, "r", encoding="latin-1") as fh:
                text = fh.read(40_000_000)
        except OSError:
            continue
        msg = body_offset_issue(fp.get("name") or e.get("footprint") or "?", step_bbox(text), fpentry.get("model"), fp.get("lines", []))
        if msg:
            e["issues"].append(msg)


# ---- the mechanical footprints of the confirmed constraints

def mech_specs(project):
    """[{name, desc, lines}] for the project's saved, confirmed constraints (constraints.library_specs)."""
    import constraints
    import store
    return constraints.library_specs(store.load_idea(project))


def mech_signature(project):
    """A short text that changes when the mechanical footprints the library should hold change (the library is stale then)."""
    import hashlib
    h = hashlib.sha256()
    for sp in mech_specs(project):
        h.update(sp["name"].encode() + b"\n" + "\n".join(sp["lines"]).encode() + b"\n")
    return h.hexdigest()[:16]
