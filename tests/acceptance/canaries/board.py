"""Control and canary builders for the board metrics (metrics/board.py).

A control is a corrected copy of the artifact on which the check must pass; a canary is a random seeded defect injected into that
control on which the check must fail, naming the injected object (ACCEPTANCE.md A4, A5). Controls here are sparse roots (only the
files a metric reads), built with the minimal OLE writer in oracle/olewrite.py, so the 438 MB fixture is never copied.
Output files are for this oracle only; they are not meant to be opened in Altium.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import struct

from lib import Ctx
from oracle import olewrite, pcbdoc as P


# ------------------------------------------------------------------------------------------------------------ sparse roots
def sparse_root(ctx: Ctx, name: str, copy: tuple = ()) -> Ctx:
    """A new writable fixture-shaped root under ctx.work holding only `copy` (paths relative to ctx.root)."""
    dst = ctx.work / name
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "project").mkdir(parents=True)
    (dst / "altium").mkdir(parents=True)
    for rel in copy:
        src = ctx.root / rel
        if not src.exists():
            raise FileNotFoundError(src)
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / rel)
    return Ctx(dst, ctx.seed, ctx.work, ctx.live, frozen=False, label=name)


def rewrite_pcbdoc(ctx: Ctx, name: str, replace: dict, header_counts: dict | None = None, copy: tuple = ()) -> Ctx:
    """Sparse root whose altium/ holds the fixture PcbDoc rewritten with `replace` streams (name -> bytes)."""
    c = sparse_root(ctx, name, copy)
    src = ctx.pcbdoc()
    olewrite.rewrite(src, c.altium / src.name, replace=replace, header_counts=header_counts)
    return c


# ------------------------------------------------------------------------------------------------------------ text records
def split_records(blob: bytes, skip: int = 0) -> list[bytes]:
    """Raw records `[skip bytes][uint32 len][body]` of a text stream (verbatim slices, so a record can be copied or dropped)."""
    out, i = [], 0
    while i + skip + 4 <= len(blob):
        n = struct.unpack("<I", blob[i + skip:i + skip + 4])[0] & 0xFFFFFF
        out.append(blob[i:i + skip + 4 + n])
        i += skip + 4 + n
    if i != len(blob):
        raise ValueError(f"trailing {len(blob) - i} bytes after the last record")
    return out


def patch_text(raw: bytes, updates: dict, skip: int = 0) -> bytes:
    """Set `KEY=value` pairs inside one raw record (`|KEY=value`; a value ends at `|` or CR). A missing key raises."""
    n = struct.unpack("<I", raw[skip:skip + 4])[0]
    flag, n = n >> 24, n & 0xFFFFFF
    text = raw[skip + 4:skip + 4 + n].decode("latin-1")
    for k, v in updates.items():
        pat = re.compile(r"(\|" + re.escape(k) + r"=)([^|\r\x00]*)")
        if not pat.search(text):
            raise KeyError(k)
        text = pat.sub(lambda m: m.group(1) + v, text, count=1)
    b = text.encode("latin-1")
    return raw[:skip] + struct.pack("<I", len(b) | flag << 24) + b


def mil_text(mm: float) -> str:
    return f"{mm / P.MIL_MM:.4f}mil"


# ------------------------------------------------------------------------------------------------------------ W27: the stack
def stack_updates(rows_v9: list, rows_v8: list, want: list) -> dict:
    """Board6 key updates that give the stack the `want` rows: [{"kind": "copper"|"dielectric", "cu_mm"/"diel_mm"/"er"}] in order."""
    upd: dict = {}
    for rows, key in ((rows_v9, lambda n, f: f"V9_STACK_LAYER{n}_{f}"), (rows_v8, lambda n, f: f"LAYER_V8_{n}{f}")):
        if len(rows) != len(want):
            raise ValueError(f"stack has {len(rows)} rows, wanted {len(want)}")
        for r, w in zip(rows, want):
            if r["kind"] != w["kind"]:
                raise ValueError(f"row {r['n']}: kind {r['kind']} != {w['kind']}")
            if w["kind"] == "copper":
                upd[key(r["n"], "COPTHICK")] = mil_text(w["cu_mm"])
            else:
                upd[key(r["n"], "DIELHEIGHT")] = mil_text(w["diel_mm"])
                upd[key(r["n"], "DIELCONST")] = f"{w['er']}"
    return upd


def with_board_updates(ctx: Ctx, name: str, updates: dict, copy: tuple = ()) -> Ctx:
    streams = olewrite.read_all(ctx.pcbdoc())
    return rewrite_pcbdoc(ctx, name, {"Board6/Data": patch_text(streams["Board6/Data"], updates)}, copy=copy)


# ------------------------------------------------------------------------------------------------------------ W32(a): Rules6
def rules6_append(blob: bytes, attrs: dict) -> bytes:
    """Append one rule record built from `attrs` (the RULEKIND, NAME, ... pairs) with the 2-byte kind prefix of the last record."""
    recs = split_records(blob, skip=2)
    text = ("|" + "|".join(f"{k}={v}" for k, v in attrs.items())).encode("latin-1") + b"\0"
    return blob + recs[-1][:2] + struct.pack("<I", len(text)) + text


def with_rules(ctx: Ctx, name: str, extra: list, copy: tuple = ()) -> Ctx:
    """Sparse root whose PcbDoc has `extra` (attribute dicts) added to Rules6 and the header count raised."""
    streams = olewrite.read_all(ctx.pcbdoc())
    blob, n = streams["Rules6/Data"], len(split_records(streams["Rules6/Data"], skip=2))
    for a in extra:
        blob = rules6_append(blob, a)
    return rewrite_pcbdoc(ctx, name, {"Rules6/Data": blob}, header_counts={"Rules6": n + len(extra)}, copy=copy)


# ------------------------------------------------------------------------------------------------------------ W17: PcbLib courtyard
def footprint_objects(d: bytes) -> tuple[bytes, list[tuple[int, bytes]]]:
    """Split a footprint Data stream into its name block and its objects [(kind, raw bytes incl. the kind byte)]."""
    n0 = struct.unpack("<I", d[:4])[0] & 0xFFFFFF
    head, i, out = d[:4 + n0], 4 + n0, []
    while i < len(d):
        kind, j = d[i], i + 1
        blocks = 6 if kind == 2 else 2 if kind == 5 else 1
        for _ in range(blocks):
            j += 4 + (struct.unpack("<I", d[j:j + 4])[0] & 0xFFFFFF)
        out.append((kind, d[i:j]))
        i = j
    return head, out


def _payload(raw: bytes) -> bytes:
    """Payload of a single-block object (type 1/3/4/6/11/12)."""
    n = struct.unpack("<I", raw[1:5])[0] & 0xFFFFFF
    return raw[5:5 + n]


def _track_raw(template_raw: bytes, layer: int, x1: float, y1: float, x2: float, y2: float) -> bytes:
    p = bytearray(_payload(template_raw))
    p[0] = layer
    struct.pack_into("<4i", p, 13, *(round(v / P.UNIT_MM) for v in (x1, y1, x2, y2)))
    return bytes([4]) + struct.pack("<I", len(p)) + bytes(p)


def courtyard_footprint_data(d: bytes, layer: int, margin_mm: float, shrink_mm: float = 0.0) -> bytes:
    """Footprint Data with every object on `layer` (tracks, arcs, regions) replaced by one rectangle that encloses all pad copper and
    all 3D bodies by `margin_mm` - `shrink_mm`. A footprint with no plated pad (a mechanical hole, a keep-out) is returned unchanged."""
    fp = P._footprint_from_data("x", "", d)
    if not any(p.plated for p in fp.pads):
        return d
    head, objs = footprint_objects(d)
    template = next((raw for k, raw in objs if k == 4), None)
    if template is None:
        raise ValueError("footprint has no track to copy a record from")
    keep = [raw for k, raw in objs if not (k in (1, 4, 11) and _payload(raw)[0] == layer)]
    pts: list[tuple[float, float]] = []
    for p in fp.pads:
        x0, y0, x1, y1 = p.extent()
        pts += [(x0, y0), (x1, y1)]
    for b in fp.bodies:
        bb = b.bbox()
        if bb:
            pts += [(bb[0], bb[1]), (bb[2], bb[3])]
    m = margin_mm - shrink_mm
    x0, x1 = min(p[0] for p in pts) - m, max(p[0] for p in pts) + m
    y0, y1 = min(p[1] for p in pts) - m, max(p[1] for p in pts) + m
    rect = [_track_raw(template, layer, x0, y0, x1, y0), _track_raw(template, layer, x1, y0, x1, y1),
            _track_raw(template, layer, x1, y1, x0, y1), _track_raw(template, layer, x0, y1, x0, y0)]
    return head + b"".join(keep) + b"".join(rect)


def rewrite_courtyards(src: pathlib.Path, dst: pathlib.Path, layer: int, margin_mm: float, shrink_names: dict | None = None) -> pathlib.Path:
    """Copy a PcbLib to `dst` with a rectangular courtyard on `layer` in every footprint that has plated pads. `shrink_names`
    {footprint name: mm} makes those courtyards smaller by that amount (a canary)."""
    streams = olewrite.read_all(src)
    shrink_names = shrink_names or {}
    for key in list(streams):
        parts = key.split("/")
        if len(parts) == 2 and parts[1] == "Parameters":
            par = P.kv(streams[key].decode("cp1252", "replace"))
            dkey = parts[0] + "/Data"
            if "PATTERN" in par and dkey in streams and streams[dkey]:
                streams[dkey] = courtyard_footprint_data(streams[dkey], layer, margin_mm, shrink_names.get(par["PATTERN"], 0.0))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(olewrite.build(streams))
    return dst


# ------------------------------------------------------------------------------------------------------------ routing edits (W31, W28)
def prim_records(blob: bytes) -> list[bytes]:
    """Raw primitive records `[type][uint32 len][payload]` of Tracks6 / Vias6 / Arcs6 data."""
    out, i = [], 0
    while i < len(blob):
        n = struct.unpack("<I", blob[i + 1:i + 5])[0]
        out.append(blob[i:i + 5 + n])
        i += 5 + n
    if i != len(blob):
        raise ValueError("truncated primitive stream")
    return out


def new_track(template: bytes, layer: int, net_idx: int, x1: float, y1: float, x2: float, y2: float, width: float) -> bytes:
    """A free copper track record: the template record with layer, net, owner and geometry replaced (mm)."""
    p = bytearray(template[5:])
    p[0] = layer
    struct.pack_into("<H", p, 3, net_idx)
    struct.pack_into("<H", p, 5, 0xFFFF)      # no polygon
    struct.pack_into("<H", p, 7, 0xFFFF)      # no owning component
    struct.pack_into("<5i", p, 13, *(round(v / P.UNIT_MM) for v in (x1, y1, x2, y2, width)))
    return template[:1] + struct.pack("<I", len(p)) + bytes(p)


def routing_streams(src, keep_track=None, keep_via=None, add_tracks: list | None = None, set_width: dict | None = None,
                    template_from=None):
    """({stream: bytes}, {name: count}) for a PcbDoc whose tracks / vias are filtered by `keep_track(Track)` / `keep_via(Via)`, whose
    tracks on `set_width` {net: mm} nets are redrawn at that width, and which gains `add_tracks`
    [(layer, net name, x1, y1, x2, y2, width_mm)]. A new net name is not allowed (the net table is not edited). New tracks copy a
    free copper track record of `template_from` (default `src`; a placement-stage PcbDoc may have none)."""
    doc = P.PcbDoc(src)
    nets, tracks, vias = doc.nets(), doc.tracks(), doc.vias()
    streams = olewrite.read_all(src)
    doc.close()
    traw, vraw = prim_records(streams["Tracks6/Data"]), prim_records(streams["Vias6/Data"])
    if len(traw) != len(tracks) or len(vraw) != len(vias):
        raise ValueError("record count differs from the parsed objects")
    template = None
    if add_tracks:
        tsrc = template_from or src
        td = P.PcbDoc(tsrc)
        trecs, tobjs = prim_records(olewrite.read_all(tsrc)["Tracks6/Data"]), td.tracks()
        td.close()
        template = next((r for r, t in zip(trecs, tobjs) if t.comp is None and P.is_copper(t.layer)), None)
        if template is None:
            raise ValueError(f"no free copper track in {tsrc} to copy a record from")

    def widened(r, t):
        if set_width and t.net in set_width and P.is_copper(t.layer):
            p = bytearray(r[5:])
            struct.pack_into("<i", p, 29, round(set_width[t.net] / P.UNIT_MM))
            return r[:5] + bytes(p)
        return r
    ktr = [widened(r, t) for r, t in zip(traw, tracks) if keep_track is None or keep_track(t)]
    kvi = [r for r, v in zip(vraw, vias) if keep_via is None or keep_via(v)]
    ktr += [new_track(template, layer, nets.index(net), x1, y1, x2, y2, w) for layer, net, x1, y1, x2, y2, w in (add_tracks or [])]
    return {"Tracks6/Data": b"".join(ktr), "Vias6/Data": b"".join(kvi)}, {"Tracks6": len(ktr), "Vias6": len(kvi)}


def rewrite_routing(ctx: Ctx, name: str, keep_track=None, keep_via=None, add_tracks: list | None = None, copy: tuple = (),
                    set_width: dict | None = None) -> Ctx:
    """Sparse root whose PcbDoc is the fixture PcbDoc edited by routing_streams()."""
    replace, counts = routing_streams(ctx.pcbdoc(), keep_track, keep_via, add_tracks, set_width)
    return rewrite_pcbdoc(ctx, name, replace, header_counts=counts, copy=copy)


def regions_to_keepout(src, dst, rects: list, add_tracks: list | None = None, template_from=None) -> pathlib.Path:
    """Copy PcbDoc `src` to `dst` with every non-pour region whose bounding-box centre lies in one of `rects` [(x0, y0, x1, y1) mm]
    moved to the Keep-Out layer (layer byte 56, V7_LAYER=KEEPOUT); `add_tracks` as in routing_streams (canary copper)."""
    doc = P.PcbDoc(src)
    nets = doc.nets()
    streams = olewrite.read_all(src)
    doc.close()
    out = {}
    for sname in ("Regions6", "ShapeBasedRegions6"):
        recs = []
        for raw in prim_records(streams[sname + "/Data"]):
            p = raw[5:]
            r = P._parse_region(p, nets, shape=sname.startswith("Shape"))
            cx = sum(x for x, _ in r.points) / max(len(r.points), 1)
            cy = sum(y for _, y in r.points) / max(len(r.points), 1)
            if r.points and not r.poured and any(a <= cx <= c and b <= cy <= d for a, b, c, d in rects):
                tl = struct.unpack("<I", p[18:22])[0]
                text = p[22:22 + tl].decode("latin-1")
                text = re.sub(r"V7_LAYER=[^|\r\x00]*", "V7_LAYER=KEEPOUT", text)
                p = bytes([P.L_KEEPOUT]) + p[1:18] + struct.pack("<I", len(text)) + text.encode("latin-1") + p[22 + tl:]
                raw = raw[:1] + struct.pack("<I", len(p)) + p
            recs.append(raw)
        out[sname + "/Data"] = b"".join(recs)
    counts = {}
    if add_tracks:
        rep, counts = routing_streams(src, add_tracks=add_tracks, template_from=template_from)
        out["Tracks6/Data"] = rep["Tracks6/Data"]
        counts = {"Tracks6": counts["Tracks6"]}
    return olewrite.rewrite(src, dst, replace=out, header_counts=counts)


# ------------------------------------------------------------------------------------------------------------ moving a component
def move_components(src, dst, shifts: dict) -> pathlib.Path:
    """Copy PcbDoc `src` to `dst` with components moved: `shifts` {component index: (dx_mm, dy_mm)}. Moves the component record (X, Y)
    and its pads; tracks, text and bodies owned by it stay (enough for a distance canary)."""
    streams = olewrite.read_all(src)
    recs = split_records(streams["Components6/Data"])
    d = P.PcbDoc(src)
    cl = d.components()
    d.close()
    for idx, (dx, dy) in shifts.items():
        c = cl[idx]
        recs[idx] = patch_text(recs[idx], {"X": mil_text(c.x + dx), "Y": mil_text(c.y + dy)})
    blob, out, i = streams["Pads6/Data"], bytearray(), 0
    while i < len(blob):
        if blob[i] != 2:
            raise ValueError("unexpected record in Pads6")
        j, starts = i + 1, []
        for _ in range(6):
            n = struct.unpack("<I", blob[j:j + 4])[0] & 0xFFFFFF
            starts.append((j + 4, n))
            j += 4 + n
        g0, gn = starts[4]
        comp = struct.unpack("<H", blob[g0 + 7:g0 + 9])[0]
        rec = bytearray(blob[i:j])
        if comp in shifts:
            off = g0 - i
            x, y = struct.unpack("<2i", bytes(rec[off + 13:off + 21]))
            struct.pack_into("<2i", rec, off + 13, x + round(shifts[comp][0] / P.UNIT_MM), y + round(shifts[comp][1] / P.UNIT_MM))
        out += rec
        i = j
    return olewrite.rewrite(src, dst, replace={"Components6/Data": b"".join(recs), "Pads6/Data": bytes(out)})
