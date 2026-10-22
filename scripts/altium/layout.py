"""PCB placement for the agent's `altium.place_pcb` action (pure Python: no Altium here, so it can be tested).

Same pattern as draw.py: plan here, keep the Pascal side to dumb object creation, verify from the saved file.
Units are mm, rotation is degrees counter-clockwise like Altium, y grows upwards.

  board_size(idea)                  (width, height) mm from idea["board"] or from the requirements text, else None
  footprint_box(fp)                 courtyard box of a PcbLib footprint (pads + margin), relative to its origin
  plan_outline(size)                the outline to create when the PcbDoc has none
  plan_placement(...)               {"places": [{ref, footprint, x, y, rot}], "warnings", "errors"}
  plan_commands(...)                the script lines for the bridge (PCBBEGIN, OUTLINE, PLACEFP, PADNET, PCBSAVE)
  unrouted(doc)                     nets whose pads are not all joined by tracks, vias and pads in a read_pcbdoc dict
  verify_layout(...)                saved PcbDoc against the netlist: parts, footprints, pad nets, overlaps, edges
"""
import math
import re

EDGE_MM = 1.0           # parts keep this far from the board edge (connectors may touch it: see CONNECTOR_OVERHANG)
GAP_MM = 0.6            # clearance between two courtyards (never below the JLC clearance rule passed in)
COURT_MM = 0.25         # courtyard margin around pads
STEP_MM = 0.5           # search grid
MAX_FILL = 0.55         # courtyard area / board area above which we refuse: nothing is left for routing
MIL = 0.0254
LABEL_H = 1.0          # designator text height, mm (line 0.15 mm)
LABEL_LINE = 0.15
LABEL_W = 0.65         # width of one designator character at LABEL_H
LABEL_GAP = 0.25       # between a part and its designator
EDGE_COPPER_MM = 0.3   # copper (pads) stays this far from the board edge (JLC)
OPEN_MIN_MM = 0.8
CONNECTOR_OVERHANG_MM = 1.0   # a connector's body may stick out of the outline this far, on its mating side only
_GND = re.compile(r"^(?:[ADPSEC]?GND\w*|VSS\w*|GROUND)$", re.I)
_RAIL = re.compile(r"^[+-]\d|^\d+V\d*$|^(?:VCC|VDD|VBUS|VBAT|VIN|VSYS|VDDA|VCCA|AVDD|DVDD)\w*$", re.I)
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:x|X|×|by)\s*(\d+(?:[.,]\d+)?)\s*mm")


def is_gnd(net):
    return bool(_GND.match(str(net or "").strip()))


def is_rail(net):
    return bool(_RAIL.match(str(net or "").strip())) and not is_gnd(net)


def is_connector(ref):
    return bool(re.match(r"^(?:J|P|CON|TERM|USB)\d", ref, re.I))


def board_size(idea):
    """(width_mm, height_mm) from idea["board"] = {"width_mm", "height_mm"}, else the first 'W x H mm' in a requirement whose
    topic or text mentions the board size, else None. Never a guess."""
    idea = idea or {}
    b = idea.get("board")
    if isinstance(b, dict) and b.get("width_mm") and b.get("height_mm"):
        return float(b["width_mm"]), float(b["height_mm"])
    for r in idea.get("requirements", []) or []:
        text = str(r.get("text", ""))
        if not re.search(r"board|pcb|size|outline", f"{r.get('topic', '')} {text}", re.I):
            continue
        m = _SIZE.search(text)
        if m:
            return float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    return None


def plan_outline(size, origin=(0.0, 0.0)):
    """Rectangle outline [x0, y0, x1, y1] mm for a (w, h) board. A board must be at least 10 x 10 and at most 500 x 500 mm."""
    if not size:
        return None
    w, h = size
    if not (10 <= w <= 500 and 10 <= h <= 500):
        return None
    return [origin[0], origin[1], origin[0] + w, origin[1] + h]


def _pad_rect(p):
    """[x0, y0, x1, y1] of a read_pcblib pad (mil units in, mm out), relative to the footprint origin; a pad turned 90 or 270
    degrees swaps its sides, any other angle takes the square that holds it."""
    x, y = p["x"] * MIL, p["y"] * MIL
    sx, sy = p.get("xsize", 0) * MIL, p.get("ysize", 0) * MIL
    rot = float(p.get("rotation") or 0) % 180
    if abs(rot - 90) < 0.5:
        sx, sy = sy, sx
    elif min(rot, 180 - rot) > 0.5:
        sx = sy = math.hypot(sx, sy)
    return [x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2]


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def pads_box(fp):
    """The box of the copper of a read_pcblib footprint, mm, relative to its origin (None without sized pads)."""
    return _union([_pad_rect(p) for p in fp.get("pads", []) if "x" in p])


def footprint_extent(fp):
    """The real extent of a read_pcblib footprint, mm, relative to its origin: the union of its pads (turned as they are), its
    silkscreen, its mechanical layers (courtyard, assembly) and the outline of its 3D body. A part is as big as the biggest of them,
    not as its pads: a connector's shell and plug end are far outside its pads. None when there is nothing."""
    ext = fp.get("extent") or {}
    return _union([pads_box(fp)] + [[v * MIL for v in ext[k]] for k in ("silk", "mech", "body") if ext.get(k)])


def footprint_box(fp, margin=COURT_MM):
    """footprint_extent grown by `margin`: the box other parts keep out of. None when the footprint has no pads with a size."""
    e = footprint_extent(fp)
    if e is None or pads_box(fp) is None:
        return None
    return [e[0] - margin, e[1] - margin, e[2] + margin, e[3] + margin]


def opening_dir(fp):
    """The way a connector footprint opens (degrees, 0 = +x, 90 = +y, rotation 0), from where the part reaches out from its pads:
    the silkscreen and mechanical outline (the plug side) against the centre of the copper. None when it cannot be told (the outline
    is centred on the pads, less than OPEN_MIN_MM off)."""
    pb, ext = pads_box(fp), fp.get("extent") or {}
    outline = _union([[v * MIL for v in ext[k]] for k in ("silk", "mech") if ext.get(k)])
    if pb is None or outline is None:
        return None
    pads = [_pad_rect(p) for p in fp.get("pads", []) if "x" in p]
    px = sum((b[0] + b[2]) / 2 for b in pads) / len(pads)
    py = sum((b[1] + b[3]) / 2 for b in pads) / len(pads)
    dx, dy = (outline[0] + outline[2]) / 2 - px, (outline[1] + outline[3]) / 2 - py
    if math.hypot(dx, dy) < OPEN_MIN_MM:
        return None
    return int(round(math.degrees(math.atan2(dy, dx)) / 90.0)) % 4 * 90


def label_size(ref):
    """(width, height) mm of a designator drawn at LABEL_H."""
    return max(len(ref), 1) * LABEL_W, LABEL_H


def rot_point(x, y, rot):
    r = int(rot) % 360
    return {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[r]


def rot_box(box, rot):
    pts = [rot_point(x, y, rot) for x in (box[0], box[2]) for y in (box[1], box[3])]
    return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]


def _hit(a, b, gap):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def _inside(box, outline, edge):
    return box[0] >= outline[0] + edge and box[1] >= outline[1] + edge and box[2] <= outline[2] - edge and box[3] <= outline[3] - edge


def _moved(box, x, y):
    return [box[0] + x, box[1] + y, box[2] + x, box[3] + y]


def _pads_of(part, fp):
    """{pad name: (x, y, net)} relative to the footprint origin, mm."""
    nets = {str(p.get("num", p.get("number", ""))): str(p.get("net") or "") for p in part.get("pins", [])}
    out = {}
    for p in fp.get("pads", []):
        if "x" in p:
            out[p["name"]] = (p["x"] * MIL, p["y"] * MIL, nets.get(p["name"], ""))
    return out


def _label_rect(box, ref, side):
    """The designator's box above ("top") or below the part box, centred on it (the text is drawn upright, whatever the part's turn)."""
    w, h = label_size(ref)
    cx = (box[0] + box[2]) / 2
    if side == "top":
        return [cx - w / 2, box[3] + LABEL_GAP, cx + w / 2, box[3] + LABEL_GAP + h]
    return [cx - w / 2, box[1] - LABEL_GAP - h, cx + w / 2, box[1] - LABEL_GAP]


def plan_placement(parts, footprints, outline, clearance_mm=0.0, keep=None, connector_dirs=None, edge_copper_mm=EDGE_COPPER_MM):
    """Places every part inside the outline, by its real extent (pads, silkscreen, courtyard, 3D body) plus the strip its designator
    needs, so no two parts and no designator overlap.
    parts: netlist parts [{ref, footprint, pins: [{num, net}]}]; footprints: {footprint name: read_pcblib footprint};
    outline: [x0, y0, x1, y1] mm; clearance_mm: the board's copper clearance rule (parts keep at least this far apart);
    keep: {ref: (x, y, rot)} parts that are already placed and must not move (their boxes are obstacles);
    connector_dirs: {ref: degrees} which way the opening faces at rotation 0 (0 = +x); else read from the footprint (opening_dir).
    Order: connectors flush with an edge (centred along it, turned so the opening faces out, their pads edge_copper_mm inside the
    outline), ICs largest first, then decoupling caps beside the supply pin they serve, then every other part beside the parts it
    shares signal nets with, pulled towards the middle of the board while the board is roomy. Readable, not optimal.
    Returns {"places": [{ref, footprint, x, y, rot, label: [x, y], label_h}], "warnings": [...], "errors": [...]}"""
    errors, warnings, places = [], [], []
    gap = max(GAP_MM, clearance_mm)
    keep = keep or {}
    info = {}
    for p in parts:
        fpname = p.get("footprint") or ""
        fp = footprints.get(fpname)
        if fp is None:
            errors.append(f"{p['ref']}: footprint {fpname or '(none)'} is not in the project library")
            continue
        box = footprint_box(fp)
        if box is None:
            errors.append(f"{p['ref']}: footprint {fpname} has no pads")
            continue
        info[p["ref"]] = {"part": p, "fp": fpname, "box": box, "padbox": pads_box(fp), "pads": _pads_of(p, fp), "open": opening_dir(fp)}
    if errors:
        return {"places": [], "warnings": warnings, "errors": errors}
    area = sum((i["box"][2] - i["box"][0]) * (i["box"][3] - i["box"][1]) for i in info.values())
    board = (outline[2] - outline[0]) * (outline[3] - outline[1])
    if area > MAX_FILL * board:
        return {"places": [], "warnings": warnings, "errors": [
            f"the parts need {area:.0f} mm2 (pads, silkscreen, 3D body) and the board is {board:.0f} mm2 ({100 * area / board:.0f}%): "
            f"no room left for tracks; make the board bigger (more than {area / MAX_FILL:.0f} mm2) or use fewer parts"]}

    obstacles, placed = [], {}

    def full_box(ref, rot, x, y, side):
        b = _moved(rot_box(info[ref]["box"], rot), x, y)
        return b, _label_rect(b, ref, side)

    def commit(ref, x, y, rot, side="top"):
        b, lab = full_box(ref, rot, x, y, side)
        obstacles.append(_union([b, lab]))
        placed[ref] = {"x": x, "y": y, "rot": rot, "box": b, "label": lab}

    for ref, (x, y, rot) in keep.items():
        if ref in info:
            commit(ref, x, y, rot)

    def free(ref, rot, x, y, edge):
        """The side of the designator strip that fits (top first), or None."""
        for side in ("top", "bottom"):
            b, lab = full_box(ref, rot, x, y, side)
            whole = _union([b, lab])
            if _inside(whole, outline, edge) and not any(_hit(whole, o, gap) for o in obstacles):
                return side
        return None

    def find(ref, tx, ty, edge=EDGE_MM, rots=(0, 90, 180, 270), rmax=None):
        rmax = rmax or max(outline[2] - outline[0], outline[3] - outline[1])
        n = int(rmax / STEP_MM)
        best = None
        for k in range(0, n + 1):                       # rings of growing radius, so the first hit is the nearest
            r = k * STEP_MM
            cands = [(tx, ty)] if k == 0 else _ring(tx, ty, r)
            for x, y in cands:
                x, y = round(x / STEP_MM) * STEP_MM, round(y / STEP_MM) * STEP_MM
                for rot in rots:
                    side = free(ref, rot, x, y, edge)
                    if side:
                        d = math.hypot(x - tx, y - ty)
                        if best is None or d < best[0]:
                            best = (d, x, y, rot, side)
            if best and best[0] <= r:
                return best[1:]
        return best[1:] if best else None

    def centre(ref):
        b = placed[ref]["box"]
        return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

    def pad_xy(ref, pad):
        px, py, _ = info[ref]["pads"][pad]
        rx, ry = rot_point(px, py, placed[ref]["rot"])
        return placed[ref]["x"] + rx, placed[ref]["y"] + ry

    todo = [r for r in info if r not in placed]
    conns = sorted([r for r in todo if is_connector(r)], key=lambda r: -_area(info[r]))
    ics = sorted([r for r in todo if r not in conns and re.match(r"^(?:U|IC|Q|M|MOD)\d", r, re.I)], key=lambda r: -_area(info[r]))
    rest = [r for r in todo if r not in conns and r not in ics]
    cx, cy = (outline[0] + outline[2]) / 2, (outline[1] + outline[3]) / 2
    roomy = area < 0.25 * board

    def toward_middle(tgt):
        """While the board is roomy the cluster is drawn towards its middle instead of crowding the connector."""
        return ((tgt[0] + cx) / 2, (tgt[1] + cy) / 2) if roomy else tgt

    # 1. connectors: flush with an edge, centred along it, opening turned outwards, pads kept edge_copper_mm from the edge
    sides = [("B", 270), ("L", 180), ("R", 0), ("T", 90)]
    cursor = {}
    for n, ref in enumerate(conns):
        done = False
        face0 = (connector_dirs or {}).get(ref, info[ref]["open"])
        for s, face in sides[n % 4:] + sides[:n % 4]:
            rot = (face - (face0 or 0)) % 360
            b = rot_box(info[ref]["box"], rot)
            pb = rot_box(info[ref]["padbox"], rot)
            w, h = b[2] - b[0], b[3] - b[1]
            lw = max(w, label_size(ref)[0])
            horizontal = s in "LR"
            span = (outline[3] - outline[1]) if horizontal else (outline[2] - outline[0])
            size = (h if horizontal else lw) if horizontal else lw
            first = max(0.0, (span - size) / 2)
            starts = [first] if s not in cursor else []
            starts += _slide(cursor.get(s, 0.0), span - size)
            for c in starts:
                along = round(c / STEP_MM) * STEP_MM
                if horizontal:
                    x = outline[0] - b[0] if s == "L" else outline[2] - b[2]
                    y = outline[1] + along - b[1]
                    pbx = _moved(pb, x, y)
                    d = max(0.0, outline[0] + edge_copper_mm - pbx[0]) if s == "L" else -max(0.0, pbx[2] - (outline[2] - edge_copper_mm))
                    x += d
                else:
                    y = outline[1] - b[1] if s == "B" else outline[3] - b[3]
                    x = outline[0] + along - b[0] - (lw - w) / 2
                    pbx = _moved(pb, x, y)
                    d = max(0.0, outline[1] + edge_copper_mm - pbx[1]) if s == "B" else -max(0.0, pbx[3] - (outline[3] - edge_copper_mm))
                    y += d
                side = free(ref, rot, x, y, -1e-6)
                if side:
                    commit(ref, x, y, rot, side)
                    whole = obstacles[-1]
                    cursor[s] = ((whole[1] if horizontal else whole[0]) - (outline[1] if horizontal else outline[0])
                                 + (whole[3] - whole[1] if horizontal else whole[2] - whole[0]) + gap)
                    done = True
                    break
            if done:
                break
        if not done:
            errors.append(f"{ref}: no room for the connector on an edge of the board")

    # 2. ICs: nearest the middle, then around what they share nets with
    for ref in ics:
        tgt = toward_middle(_target(ref, info, placed, centre, (cx, cy)))
        hit = find(ref, *tgt, edge=EDGE_MM + 0.5)
        if hit is None:
            errors.append(f"{ref}: no free place inside the board")
            continue
        commit(ref, *hit[:3], side=hit[3])

    # 3. decoupling caps first (beside the supply pin), then the others by how tied they are to placed parts
    caps = [r for r in rest if _decap_rail(info[r])]
    others = [r for r in rest if r not in caps]
    others.sort(key=lambda r: -len(_shared(r, info, placed)))
    for ref in caps + others:
        if ref in caps:
            tgt = _decap_target(ref, info, placed, pad_xy) or toward_middle(_target(ref, info, placed, centre, (cx, cy)))
        else:
            tgt = toward_middle(_target(ref, info, placed, centre, (cx, cy)))
        hit = find(ref, *tgt)
        if hit is None:
            errors.append(f"{ref}: no free place inside the board; make the board bigger")
            continue
        commit(ref, *hit[:3], side=hit[3])
        if ref in caps:
            hx, hy = tgt
            d = math.hypot(hit[0] - hx, hit[1] - hy)
            if d > 5.0:
                warnings.append(f"{ref}: decoupling cap is {d:.1f} mm from its supply pin (no closer room)")
    for ref in placed:
        if ref in keep:
            continue
        i = info[ref]
        lab = placed[ref]["label"]
        places.append({"ref": ref, "footprint": i["fp"], "x": round(placed[ref]["x"], 3), "y": round(placed[ref]["y"], 3),
                       "rot": placed[ref]["rot"], "label": [round((lab[0] + lab[2]) / 2, 3), round((lab[1] + lab[3]) / 2, 3)],
                       "label_h": LABEL_H})
    for ref in conns:
        if ref in placed and ref not in (connector_dirs or {}):
            if info[ref]["open"] is None:
                warnings.append(f"{ref}: cannot tell from its footprint which way the connector opens; it was assumed to open towards +x: "
                                "check the mating face in 3D")
            else:
                warnings.append(f"{ref}: connector turned to open out of the board edge (opening read from the footprint outline, "
                                f"{info[ref]['open']} deg): check the mating face in 3D")
    return {"places": places, "warnings": warnings, "errors": errors}


def _area(i):
    return (i["box"][2] - i["box"][0]) * (i["box"][3] - i["box"][1])


def _ring(cx, cy, r):
    pts = []
    n = max(8, int(2 * math.pi * r / STEP_MM))
    for k in range(n):
        a = 2 * math.pi * k / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _slide(start, room):
    """Offsets along an edge to try, from `start` on in half-mm steps."""
    out, c = [], max(0.0, start)
    while c <= room + 1e-9:
        out.append(c)
        c += STEP_MM
    return out


def _signal_nets(i):
    return {n for _, _, n in i["pads"].values() if n and not is_gnd(n) and not is_rail(n) and n.upper() not in ("NC", "N/C")}


def _shared(ref, info, placed):
    mine = _signal_nets(info[ref])
    return [o for o in placed if o != ref and mine & _signal_nets(info[o])]


def _target(ref, info, placed, centre, fallback):
    others = _shared(ref, info, placed)
    if not others:
        mine = {n for _, _, n in info[ref]["pads"].values() if is_rail(n)}
        others = [o for o in placed if mine & {n for _, _, n in info[o]["pads"].values() if is_rail(n)}]
    if not others:
        return fallback
    pts = [centre(o) for o in others]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _decap_rail(i):
    """The supply net of a small two-pad part that sits between a supply rail and ground (a decoupling cap), else None."""
    if not re.match(r"^C\d", i["part"]["ref"], re.I) or len(i["pads"]) != 2:
        return None
    nets = [n for _, _, n in i["pads"].values()]
    if any(is_gnd(n) for n in nets):
        rails = [n for n in nets if is_rail(n)]
        return rails[0] if rails else None
    return None


def _decap_target(ref, info, placed, pad_xy):
    rail = _decap_rail(info[ref])
    best = None
    for o, i in info.items():
        if o not in placed or o == ref or not re.match(r"^(?:U|IC|Q|M|MOD)\d", o, re.I):
            continue
        for name, (_, _, net) in i["pads"].items():
            if net == rail:
                x, y = pad_xy(o, name)
                taken = sum(1 for r2, pl in placed.items() if r2 != o and abs(pl["x"] - x) < 4 and abs(pl["y"] - y) < 4 and r2.startswith("C"))
                key = (taken, 0)
                if best is None or key < best[0]:
                    best = (key, (x, y))
    return best[1] if best else None


def plan_commands(doc, outline, create_outline, places, footprints, parts, pcblib, replace=False):
    """Script lines for the bridge. PCBBEGIN doc replace; OUTLINE doc x0 y0 x1 y1 (mm); PLACEFP doc ref footprint pcblib x y rot
    libref sourceid; PADNET doc ref pad net; PCBSAVE doc. A footprint is placed from the project PcbLib and linked like ECO does
    (designator, source designator, library reference, footprint library) and each pad gets its net from the netlist so a later
    Update PCB matches the part instead of adding a duplicate."""
    by_ref = {p["ref"]: p for p in parts}
    d = str(doc)
    cmds = [("PCBBEGIN", d, "1" if replace else "0")]
    if create_outline and outline:
        cmds.append(("OUTLINE", d) + tuple(f"{v:g}" for v in outline))
    for pl in places:
        p = by_ref[pl["ref"]]
        cmds.append(("PLACEFP", d, pl["ref"], pl["footprint"], str(pcblib), f"{pl['x']:g}", f"{pl['y']:g}", f"{pl['rot']:g}",
                     str(p.get("lib_ref") or p.get("symbol") or ""), str(p.get("value") or ""),
                     f"{(pl.get('label') or [pl['x'], pl['y']])[0]:g}", f"{(pl.get('label') or [pl['x'], pl['y']])[1]:g}",
                     f"{pl.get('label_h', LABEL_H):g}", f"{LABEL_LINE:g}",
                     ("\\" + p["uid"]) if p.get("uid") else "", str(p.get("sheet") or "")))
        for pin in p.get("pins", []):
            net = str(pin.get("net") or "").strip()
            if net and net.upper() not in ("NC", "N/C"):
                cmds.append(("PADNET", d, pl["ref"], str(pin.get("num", pin.get("number", ""))), net))
    cmds.append(("PCBSAVE", d))
    return cmds


def text_problems(parts):
    bad = []
    for p in parts:
        names = [p["ref"], p.get("footprint") or ""] + [str(x.get("net") or "") for x in p.get("pins", [])]
        for t in names:
            if not all(32 <= ord(c) < 127 for c in t):
                bad.append(f"{p['ref']}: name {t!r} has a non-ASCII character, a tab or a line break: rename it")
    return sorted(set(bad))


def occupied(doc):
    """What a PcbDoc already holds that placing over would destroy: ({placed refs}, track+via+arc count)."""
    refs = [c["ref"] for c in doc.get("components", []) if c.get("ref")]
    n = len(doc.get("tracks", [])) + len(doc.get("vias", [])) + len(doc.get("arcs", []))
    return refs, n


def _seg_touches_pad(a, b, rect, hw, rounded=False):
    """The track (a, b, half width hw) touches the pad: its box, or for a round / oval pad the ellipse inscribed in the box (the
    corners of the box are not copper)."""
    from altium import route as rt
    if not rounded:
        return rt._seg_rect(a, b, rect) <= hw
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    ha, hb = (rect[2] - rect[0]) / 2 + hw, (rect[3] - rect[1]) / 2 + hw
    if ha <= 0 or hb <= 0:
        return False
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.02) + 1)
    for i in range(n + 1):
        x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
        if ((x - cx) / ha) ** 2 + ((y - cy) / hb) ** 2 <= 1.0:
            return True
    return False


def unrouted(doc, tol=0.02):
    """[(net, [pad tags])]: for every net with two or more pads, the groups of pads that tracks and vias do not join (copper
    pours and polygons are not read, so a net meant to be poured shows as unrouted: the caller says so). Same rule as Altium: a
    track joins what its body (not only its ends) touches on its layer, a via joins every layer, a through-hole pad joins both."""
    from altium import route as rt
    pads = [p for p in doc.get("pads", []) if p.get("net") and p.get("ref")]
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    rects = [rt._pad_rect(p) for p in pads]
    lay_of = [set(1 if l == rt.TOP else 32 for l in rt._pad_layers(p)) for p in pads]
    tracks = [t for t in doc.get("tracks", []) if t.get("net")]
    vias = [v for v in doc.get("vias", []) if v.get("net")]
    seg = lambda t: ((t["x1_mm"], t["y1_mm"]), (t["x2_mm"], t["y2_mm"]))
    for k, t in enumerate(tracks):
        a, b = seg(t)
        hw = t.get("width_mm", 0) / 2 + tol
        for j, p in enumerate(pads):
            if p["net"] == t["net"] and t["layer"] in lay_of[j] and _seg_touches_pad(a, b, rects[j], hw, rt._round_pad(p)):
                union(("track", k), ("pad", j))
        for m, u in enumerate(tracks[k + 1:], k + 1):
            if u["net"] == t["net"] and u["layer"] == t["layer"]:
                c, d = seg(u)
                if rt._seg_seg(a, b, c, d) <= hw + u.get("width_mm", 0) / 2:
                    union(("track", k), ("track", m))
        for m, v in enumerate(vias):
            if v["net"] == t["net"] and rt._pt_seg(v["x_mm"], v["y_mm"], a[0], a[1], b[0], b[1]) <= hw + max(v.get("dia_mm", 0) / 2, tol):
                union(("track", k), ("via", m))
    for m, v in enumerate(vias):
        r = max(v.get("dia_mm", 0) / 2, tol)
        for j, p in enumerate(pads):
            if p["net"] == v["net"] and rt._seg_rect((v["x_mm"], v["y_mm"]), (v["x_mm"], v["y_mm"]), rects[j]) <= r:
                union(("via", m), ("pad", j))
        for n2, w in enumerate(vias[m + 1:], m + 1):
            if w["net"] == v["net"] and math.hypot(v["x_mm"] - w["x_mm"], v["y_mm"] - w["y_mm"]) <= r + max(w.get("dia_mm", 0) / 2, tol):
                union(("via", m), ("via", n2))
    groups = {}
    for k, p in enumerate(pads):
        groups.setdefault(p["net"], {}).setdefault(find(("pad", k)), []).append(f"{p['ref']}-{p['name']}")
    return [(net, sorted(sum(g.values(), []))) for net, g in sorted(groups.items()) if len(g) > 1]
def _abs_pad_rect(p):
    """[x0, y0, x1, y1] of a read_pcbdoc pad (board mm, with its own turn)."""
    sx, sy = p.get("sx_mm", 0), p.get("sy_mm", 0)
    rot = float(p.get("rot") or 0) % 180
    if abs(rot - 90) < 0.5:
        sx, sy = sy, sx
    elif min(rot, 180 - rot) > 0.5:
        sx = sy = math.hypot(sx, sy)
    return [p["x_mm"] - sx / 2, p["y_mm"] - sy / 2, p["x_mm"] + sx / 2, p["y_mm"] + sy / 2]


def real_boxes(doc, footprints=None):
    """{ref: [x0, y0, x1, y1]} the real extent of every part of a saved board (read_pcbdoc with geometry=True gives the body and the
    silkscreen box): pads (turned as they are), 3D body, silkscreen / mechanical outline, and, when `footprints` ({name: read_pcblib
    footprint}) is given, the library's own extent moved and turned to where the part sits."""
    out = {}
    for c in doc.get("components", []):
        ref = c.get("ref")
        boxes = [_abs_pad_rect(p) for p in doc.get("pads", []) if p.get("ref") == ref and "x_mm" in p]
        boxes += [c.get("body_bbox_mm"), c.get("outline_bbox_mm")]
        fp = (footprints or {}).get(c.get("pattern"))
        if fp is not None and footprint_extent(fp):
            rot = round(float(c.get("rotation") or 0)) % 360
            if rot % 90 == 0:
                boxes.append(_moved(rot_box(footprint_extent(fp), rot), c.get("x_mm", 0), c.get("y_mm", 0)))
        out[ref] = _union(boxes)
    return {r: b for r, b in out.items() if b}


def _designators(doc):
    """{ref: [x0, y0, x1, y1]} the drawn designators of a saved board (the text origin is its lower left corner)."""
    out = {}
    for t in doc.get("texts", []):
        if t.get("kind") != "designator":
            continue
        h = t.get("height_mm") or 0
        w = len(t.get("text", "")) * h * 0.6
        if round(t.get("rotation") or 0) % 180 == 90:
            w, h = h, w
        out[t["text"]] = [t["x_mm"], t["y_mm"], t["x_mm"] + w, t["y_mm"] + h]
    return out


def verify_layout(doc, plan_parts, outline=None, clearance_mm=0.0, places=None, footprints=None, edge_copper_mm=EDGE_COPPER_MM):
    """Saved PcbDoc (read_pcbdoc dict, ideally geometry=True) against the netlist parts [{ref, footprint, pins}]. Problem strings,
    empty = it matches. Checks: every part there on the right footprint; every pad (every pad of a shared number too) on the net
    the netlist gives it; no stray parts; no two parts whose REAL extents (pads, 3D body, silkscreen) come closer than the clearance;
    every part inside the outline (a connector's body may stick out CONNECTOR_OVERHANG_MM on one side, its mating face) and every pad
    edge_copper_mm inside it; no designator over a pad or over another designator; parts where the plan put them (`places`)."""
    problems = []
    comps = {c["ref"]: c for c in doc.get("components", [])}
    pad_nets = {}
    for p in doc.get("pads", []):
        pad_nets.setdefault((p.get("ref"), str(p.get("name"))), []).append(p.get("net") or "")
    for part in plan_parts:
        c = comps.get(part["ref"])
        if c is None:
            problems.append(f"{part['ref']} is not on the saved board")
            continue
        if part.get("footprint") and c.get("pattern") != part["footprint"]:
            problems.append(f"{part['ref']} has footprint {c.get('pattern')!r}, the netlist says {part['footprint']!r}")
        for pin in part.get("pins", []):
            want = str(pin.get("net") or "").strip()
            if want.upper() in ("NC", "N/C"):
                want = ""
            num = str(pin.get("num", pin.get("number", "")))
            if (part["ref"], num) not in pad_nets:
                problems.append(f"{part['ref']}: footprint has no pad {num} (netlist pin {pin.get('name') or ''})")
                continue
            for got in pad_nets[(part["ref"], num)]:
                if got != want:
                    problems.append(f"{part['ref']}-{num} is on net {got or 'none'}, the netlist says {want or 'none'}")
    extra = sorted(set(comps) - {p["ref"] for p in plan_parts})
    if extra:
        problems.append(f"parts on the board that are not in the netlist: {', '.join(extra)}")
    boxes = real_boxes(doc, footprints)
    refs = sorted(boxes)
    gap = clearance_mm if clearance_mm > 0 else 0.0
    for a in range(len(refs)):
        for b in range(a + 1, len(refs)):
            if _hit(boxes[refs[a]], boxes[refs[b]], gap - 1e-6):
                problems.append(f"{refs[a]} and {refs[b]} overlap on the board (pads, 3D body or silkscreen" + (f", closer than {gap:g} mm" if gap else "") + ")")
    if outline:
        for r, b in boxes.items():
            if _inside(b, outline, -1e-6):
                continue
            sides = [(b[0] < outline[0] - 1e-6, outline[0] - b[0]), (b[2] > outline[2] + 1e-6, b[2] - outline[2]),
                     (b[1] < outline[1] - 1e-6, outline[1] - b[1]), (b[3] > outline[3] + 1e-6, b[3] - outline[3])]
            out_sides = [d for hit, d in sides if hit]
            if is_connector(r) and len(out_sides) == 1 and out_sides[0] <= CONNECTOR_OVERHANG_MM + 1e-6:
                continue
            problems.append(f"{r} sticks out of the board outline by {max(out_sides):.2f} mm (3D body, silkscreen or pads)")
        for p in doc.get("pads", []):
            if "x_mm" not in p or not p.get("ref"):
                continue
            pb = _abs_pad_rect(p)
            d = min(pb[0] - outline[0], pb[1] - outline[1], outline[2] - pb[2], outline[3] - pb[3])
            if d < edge_copper_mm - 0.01:
                problems.append(f"{p['ref']}-{p['name']} is {d:.2f} mm from the board edge (copper must keep {edge_copper_mm:g} mm)")
    labels = _designators(doc)
    for ref in [p["ref"] for p in plan_parts] if "texts" in doc else []:
        if ref in comps and ref not in labels:
            problems.append(f"{ref}: designator is not shown on the board")
    pad_boxes = [(f"{p['ref']}-{p['name']}", _abs_pad_rect(p)) for p in doc.get("pads", []) if "x_mm" in p and p.get("ref")]
    for ref, lb in sorted(labels.items()):
        for who, pb in pad_boxes:
            if _hit(lb, pb, -1e-6):
                problems.append(f"designator {ref} is over pad {who}")
                break
        if outline and not _inside(lb, outline, -1e-6):
            problems.append(f"designator {ref} is outside the board outline")
    lrefs = sorted(labels)
    for a in range(len(lrefs)):
        for b in range(a + 1, len(lrefs)):
            if _hit(labels[lrefs[a]], labels[lrefs[b]], -1e-6):
                problems.append(f"designators {lrefs[a]} and {lrefs[b]} overlap")
    for t in doc.get("texts", []):
        if t.get("kind") == "designator" and (t.get("height_mm") or 0) > LABEL_H * 1.6:
            problems.append(f"designator {t['text']} is {t['height_mm']:g} mm high (more than {LABEL_H * 1.6:g} mm)")
    for pl in places or []:
        c = comps.get(pl["ref"])
        if c is None:
            continue
        dr = abs(((float(c.get("rotation") or 0) - pl["rot"] + 180) % 360) - 180)
        if abs(c.get("x_mm", 0) - pl["x"]) > 0.02 or abs(c.get("y_mm", 0) - pl["y"]) > 0.02 or dr > 0.5:
            problems.append(f"{pl['ref']} sits at ({c.get('x_mm')}, {c.get('y_mm')}) turned {c.get('rotation')}, the plan says "
                            f"({pl['x']}, {pl['y']}) turned {pl['rot']}")
    return problems
