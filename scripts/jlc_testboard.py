"""
A synthetic 2-layer test board for checking JLC's live tools (JLCDFM, the quote page) against the
advisor's JLC claims. Nothing here reads a real design: every feature is generated from the table below.

    python scripts/jlc_testboard.py OUT_DIR [--formats jlc-altium26,outjob]

writes, for each export format,
    OUT_DIR/<format>/TB1.GTL ... TB1-Plated.TXT   RS-274X Gerbers and Excellon drill files
    OUT_DIR/TB1_<format>.zip                       the same files, flat, as JLC wants the upload
and OUT_DIR/manifest.json: every coupon with its nominal value, its box on the board (mm from the
board's lower-left corner) and the value measured back from the files that were written.

Board: 50 x 50 mm, 2 layers, outline on its own layer (.GM1, 0.15 mm line). Coupons (top side):
track/space, PTH annular ring, vias, copper to board edge, silkscreen to pad / mask opening,
mask dams, silkscreen line width, hole-to-hole pairs, smallest drills, plus three 0603 parts for
an assembly (BOM/CPL) test and one non-plated hole.

Export formats:
  jlc-altium26  JLC's Altium 26 recipe (shared/reference/jlc/files-and-formats.en.md, F1): Gerber mm 4:4,
                leading zeros suppressed; NC drill inch 2:5, leading and trailing zeros kept, absolute
                origin. F1 does not state the Gerber origin, so the Gerber uses the absolute origin too.
  outjob        what scripts/outjob.py configures today: Gerber inch 2:4, leading zeros suppressed,
                relative origin; NC drill inch 2:4, leading zeros suppressed, relative origin.
  jlc-altium26-mixed  (experiment, not in the default set) the F1 recipe with Altium's default
                Gerber origin (relative) next to the absolute drill origin: drill and copper are offset.
"""
import argparse
import json
import math
import pathlib
import zipfile

BOARD_NAME = "TB1"
BOARD_W = 50.0
BOARD_H = 50.0
OUTLINE_W = 0.15            # JLC: draw the outline 0.15 mm wide [P2 #7]
MASK_EXP = 0.05             # mask expansion per side (the advisor's JLC preset: 2 mil)
TEXT_H = 1.0                # JLC min text height 1.0 mm
TEXT_W = 0.15               # JLC min silk line width
# Where the board's lower-left corner sits in Altium's absolute coordinates (an arbitrary, non-round
# offset so that a mix-up of origins shows): 1250 x 900 mil.
ABSOLUTE_ORIGIN_MM = (31.75, 22.86)

LAYERS = {   # layer -> Altium (Protel) file extension
    "top_copper": "GTL", "bottom_copper": "GBL", "top_silk": "GTO", "top_mask": "GTS",
    "bottom_mask": "GBS", "top_paste": "GTP", "outline": "GM1",
}

FORMATS = {
    "jlc-altium26": {
        "title": "JLC's Altium 26 recipe",
        "source": "shared/reference/jlc/files-and-formats.en.md § JLC's Altium Gerber and drill recipe [F1]",
        "gerber": {"units": "mm", "int": 4, "dec": 4, "zeros": "suppress_leading"},
        "drill": {"units": "inch", "int": 2, "dec": 5, "zeros": "keep"},
        "gerber_origin": "absolute", "drill_origin": "absolute",
    },
    "outjob": {
        "title": "pcb-advisor OutJob (scripts/outjob.py)",
        "source": "scripts/outjob.py: Gerber GerberUnit=Imperial, NumberOfDecimals=4, SuppressLeadingZeroes, "
                  "OriginPosition=Relative; NC Drill Units=Imperial, NumberOfUnits=2, NumberOfDecimals=4, "
                  "SuppressLeadingZeroes, OriginPosition=Relative",
        "gerber": {"units": "inch", "int": 2, "dec": 4, "zeros": "suppress_leading"},
        "drill": {"units": "inch", "int": 2, "dec": 4, "zeros": "suppress_leading"},
        "gerber_origin": "relative", "drill_origin": "relative",
    },
    "jlc-altium26-mixed": {
        "title": "JLC's Altium 26 recipe with Altium's default (relative) Gerber origin",
        "source": "experiment: F1 sets the drill to the absolute origin and does not say where the Gerber goes",
        "gerber": {"units": "mm", "int": 4, "dec": 4, "zeros": "suppress_leading"},
        "drill": {"units": "inch", "int": 2, "dec": 5, "zeros": "keep"},
        "gerber_origin": "relative", "drill_origin": "absolute",
        "experimental": True,
    },
}
DEFAULT_FORMATS = ("jlc-altium26", "outjob")

# Parts for the assembly test: real JLC Basic parts (codes checked live by scripts/jlc_live.py).
PARTS = [
    {"ref": "R1", "value": "10k", "footprint": "0603", "lcsc": "C25804", "x": 22.0, "y": 10.0, "rotation": 0},
    {"ref": "C1", "value": "100nF", "footprint": "0603", "lcsc": "C14663", "x": 28.0, "y": 10.0, "rotation": 0},
    {"ref": "D1", "value": "Red LED", "footprint": "0603", "lcsc": "C2286", "x": 34.0, "y": 10.0, "rotation": 0},
]
PAD_0603 = (0.8, 0.95, 0.8)   # pad width, height, centre offset from the part centre

# --------------------------------------------------------------------------- stroke font
# Each glyph is a list of polylines in a 0.6 (wide) x 1.0 (high) box; advance 0.9 x height.
_F = {
    "0": [[(0, 0), (.6, 0), (.6, 1), (0, 1), (0, 0)]],
    "1": [[(.15, .85), (.3, 1), (.3, 0)]],
    "2": [[(0, 1), (.6, 1), (.6, .5), (0, .5), (0, 0), (.6, 0)]],
    "3": [[(0, 1), (.6, 1), (.6, 0), (0, 0)], [(0, .5), (.6, .5)]],
    "4": [[(0, 1), (0, .5), (.6, .5)], [(.6, 1), (.6, 0)]],
    "5": [[(.6, 1), (0, 1), (0, .5), (.6, .5), (.6, 0), (0, 0)]],
    "6": [[(.6, 1), (0, 1), (0, 0), (.6, 0), (.6, .5), (0, .5)]],
    "7": [[(0, 1), (.6, 1), (.6, 0)]],
    "8": [[(0, 0), (.6, 0), (.6, 1), (0, 1), (0, 0)], [(0, .5), (.6, .5)]],
    "9": [[(.6, .5), (0, .5), (0, 1), (.6, 1), (.6, 0), (0, 0)]],
    "A": [[(0, 0), (0, 1), (.6, 1), (.6, 0)], [(0, .5), (.6, .5)]],
    "C": [[(.6, 1), (0, 1), (0, 0), (.6, 0)]],
    "D": [[(0, 0), (0, 1), (.4, 1), (.6, .8), (.6, .2), (.4, 0), (0, 0)]],
    "E": [[(.6, 1), (0, 1), (0, 0), (.6, 0)], [(0, .5), (.45, .5)]],
    "H": [[(0, 0), (0, 1)], [(.6, 0), (.6, 1)], [(0, .5), (.6, .5)]],
    "M": [[(0, 0), (0, 1), (.3, .5), (.6, 1), (.6, 0)]],
    "P": [[(0, 0), (0, 1), (.6, 1), (.6, .5), (0, .5)]],
    "R": [[(0, 0), (0, 1), (.6, 1), (.6, .5), (0, .5)], [(.3, .5), (.6, 0)]],
    "S": [[(.6, 1), (0, 1), (0, .5), (.6, .5), (.6, 0), (0, 0)]],
    "T": [[(0, 1), (.6, 1)], [(.3, 1), (.3, 0)]],
    "V": [[(0, 1), (.3, 0), (.6, 1)]],
    "W": [[(0, 1), (.15, 0), (.3, .5), (.45, 0), (.6, 1)]],
    "B": [[(0, 0), (0, 1), (.6, 1), (.6, 0), (0, 0)], [(0, .5), (.6, .5)]],
}


# --------------------------------------------------------------------------- board model
class Board:
    """Features in mm, board coordinates (lower-left corner of the outline = 0, 0)."""

    def __init__(self):
        self.feats = {name: [] for name in LAYERS}
        self.holes = []          # {"x", "y", "d", "plated"}
        self.coupons = []
        self.parts = []

    def line(self, layer, x1, y1, x2, y2, w):
        self.feats[layer].append({"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "w": w})

    def circle(self, layer, x, y, d):
        self.feats[layer].append({"kind": "flash", "shape": "C", "x": x, "y": y, "w": d, "h": d})

    def rect(self, layer, x, y, w, h):
        self.feats[layer].append({"kind": "flash", "shape": "R", "x": x, "y": y, "w": w, "h": h})

    def hole(self, x, y, d, plated=True):
        self.holes.append({"x": x, "y": y, "d": d, "plated": plated})

    def text(self, x, y, s, h=TEXT_H, w=TEXT_W, layer="top_silk"):
        for i, ch in enumerate(s):
            ox = x + i * 0.9 * h
            for poly in _F[ch]:
                for (ax, ay), (bx, by) in zip(poly, poly[1:]):
                    self.line(layer, ox + ax * h, y + ay * h, ox + bx * h, y + by * h, w)

    def coupon(self, cid, kind, nominal, bbox, what, label_xy):
        self.text(label_xy[0], label_xy[1], cid)
        self.coupons.append({"id": cid, "kind": kind, "nominal": nominal, "what": what,
                             "bbox": [round(v, 4) for v in bbox], "label_at": list(label_xy)})

    # pads ------------------------------------------------------------------
    def pth(self, x, y, drill, pad, mask=True):
        for side in ("top", "bottom"):
            self.circle(f"{side}_copper", x, y, pad)
            if mask:
                self.circle(f"{side}_mask", x, y, pad + 2 * MASK_EXP)
        self.hole(x, y, drill, True)

    def via(self, x, y, drill, dia):          # tented: no mask opening
        for side in ("top", "bottom"):
            self.circle(f"{side}_copper", x, y, dia)
        self.hole(x, y, drill, True)

    def smd(self, x, y, w, h, paste=True):
        self.rect("top_copper", x, y, w, h)
        self.rect("top_mask", x, y, w + 2 * MASK_EXP, h + 2 * MASK_EXP)
        if paste:
            self.rect("top_paste", x, y, w, h)


def build() -> Board:
    b = Board()
    # outline: one closed rectangle on its own layer
    pts = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H), (0, 0)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        b.line("outline", ax, ay, bx, by, OUTLINE_W)

    # A. track and space (width = space), three parallel 6 mm tracks
    for x0, v in zip((2.0, 11.5, 21.0, 30.5, 40.0), (0.075, 0.09, 0.10, 0.127, 0.15)):
        y0, p = 43.5, 2 * v
        for k in range(3):
            b.line("top_copper", x0, y0 + k * p, x0 + 6.0, y0 + k * p, v)
        b.coupon(f"TS{round(v * 1000):03d}", "track_space", {"width_mm": v, "space_mm": v},
                 (x0 - v, y0 - v, x0 + 6.0 + v, y0 + 2 * p + v),
                 f"3 top tracks {v} mm wide, {v} mm apart", (x0, 45.3))

    # B. PTH annular ring: 0.8 mm drill, pad = drill + 2 x ring, mask opening both sides
    for xc, r in zip((5.0, 14.5, 24.0, 33.5, 43.0), (0.10, 0.13, 0.15, 0.18, 0.25)):
        pad = 0.8 + 2 * r
        b.pth(xc, 38.0, 0.8, pad)
        b.coupon(f"AR{round(r * 100):02d}", "annular_ring", {"ring_mm": r, "drill_mm": 0.8, "pad_mm": round(pad, 4)},
                 (xc - 1.0, 37.0, xc + 1.0, 39.0), f"PTH pad, drill 0.8 mm, pad {pad:.2f} mm (ring {r} mm), top and bottom",
                 (xc - 1.8, 39.5))

    # C. vias (tented) and smallest drills
    vias = (("V15", 0.15, 0.25), ("V20", 0.20, 0.35), ("V30", 0.30, 0.60), ("DR15", 0.15, 0.45), ("DR20", 0.20, 0.50))
    for xc, (cid, drill, dia) in zip((5.0, 14.5, 24.0, 33.5, 43.0), vias):
        b.via(xc, 31.5, drill, dia)
        kind = "via" if cid.startswith("V") else "drill"
        b.coupon(cid, kind, {"drill_mm": drill, "dia_mm": dia, "ring_mm": round((dia - drill) / 2, 4)},
                 (xc - 0.6, 30.9, xc + 0.6, 32.1), f"tented via, drill {drill} mm, diameter {dia} mm", (xc - 1.8, 32.8))

    # D. silkscreen to mask opening: 1.5 mm square pad, 1.6 mm opening, 0.15 mm silk line at gap s
    for xc, s in zip((4.0, 12.0, 20.0), (0.05, 0.10, 0.15)):
        b.smd(xc, 25.0, 1.5, 1.5)
        sx = xc + 0.8 + s + TEXT_W / 2
        b.line("top_silk", sx, 24.0, sx, 26.0, TEXT_W)
        b.coupon(f"SP{round(s * 100):02d}", "silk_to_pad", {"silk_to_mask_mm": s, "silk_to_pad_mm": round(s + MASK_EXP, 4)},
                 (xc - 0.9, 23.85, sx + 0.2, 26.15),
                 f"silk line {s} mm from the mask opening ({s + MASK_EXP:.2f} mm from the copper)", (xc - 0.75, 26.6))
    # silkscreen line width
    for x0, w in ((30.0, 0.10), (40.0, 0.15)):
        b.line("top_silk", x0, 25.0, x0 + 5.0, 25.0, w)
        b.coupon(f"SW{round(w * 100):02d}", "silk_width", {"width_mm": w}, (x0 - 0.2, 24.8, x0 + 5.2, 25.2),
                 f"5 mm silk line {w} mm wide", (x0, 26.6))

    # E. mask dams: 4 pads 0.3 x 1.2 mm, gap g = dam + 2 x expansion
    for x0, dam in zip((3.0, 14.0, 25.0), (0.08, 0.10, 0.13)):
        g = dam + 2 * MASK_EXP
        pitch = 0.3 + g
        for k in range(4):
            b.smd(x0 + k * pitch, 18.0, 0.3, 1.2)
        b.coupon(f"MD{round(dam * 100):02d}", "mask_dam", {"dam_mm": dam, "pad_gap_mm": round(g, 4)},
                 (x0 - 0.3, 17.25, x0 + 3 * pitch + 0.3, 18.75),
                 f"4 pads 0.3 x 1.2 mm, gap {g:.2f} mm, mask dam {dam} mm", (x0, 19.4))

    # G. hole-to-hole pairs (copper merged, so only the hole gap is new) and a non-plated hole
    gap = 0.25
    x1, x2 = 4.0, 4.0 + 0.3 + gap
    for xc in (x1, x2):
        b.via(xc, 10.0, 0.3, 0.5)
    for side in ("top", "bottom"):
        b.line(f"{side}_copper", x1, 10.0, x2, 10.0, 0.5)
    b.coupon("HV25", "hole_to_hole", {"gap_mm": gap, "drill_mm": 0.3, "what": "via-via"},
             (x1 - 0.4, 9.6, x2 + 0.4, 10.4), "two tented vias 0.3/0.5 mm, holes 0.25 mm apart (edge to edge)",
             (3.0, 11.4))
    gap = 0.40
    x1, x2 = 11.0, 11.0 + 0.8 + gap
    for xc in (x1, x2):
        b.pth(xc, 10.0, 0.8, 1.3)
    for side in ("top", "bottom"):
        b.line(f"{side}_copper", x1, 10.0, x2, 10.0, 1.3)
    b.coupon("HP40", "hole_to_hole", {"gap_mm": gap, "drill_mm": 0.8, "what": "PTH-PTH"},
             (x1 - 0.8, 9.2, x2 + 0.8, 10.8), "two PTH pads 0.8/1.3 mm, holes 0.40 mm apart (edge to edge)",
             (10.5, 11.4))
    b.hole(44.0, 10.0, 2.0, plated=False)
    for side in ("top", "bottom"):
        b.circle(f"{side}_mask", 44.0, 10.0, 2.0 + 2 * MASK_EXP)
    b.coupon("MH", "npth", {"drill_mm": 2.0}, (42.9, 8.9, 45.1, 11.1), "non-plated hole 2.0 mm, no copper", (43.4, 11.6))

    # F. copper to board edge: 0.25 mm tracks along the bottom edge, d = copper edge to outline centre
    for x0, d in zip((3.0, 13.0, 23.0, 33.0), (0.15, 0.20, 0.30, 0.40)):
        y = d + 0.125
        b.line("top_copper", x0, y, x0 + 4.0, y, 0.25)
        b.coupon(f"E{round(d * 100):02d}", "copper_to_edge",
                 {"edge_mm": d, "to_outline_line_edge_mm": round(d - OUTLINE_W / 2, 4)},
                 (x0 - 0.2, -0.1, x0 + 4.2, d + 0.35),
                 f"0.25 mm track {d} mm from the board edge (outline centre line)", (x0, 2.0))

    # parts for the assembly test
    pw, ph, off = PAD_0603
    for p in PARTS:
        for sx in (-1, 1):
            b.smd(p["x"] + sx * off, p["y"], pw, ph)
        b.text(p["x"] - 0.75, 11.4, p["ref"])
        if p["ref"].startswith("D"):     # cathode bar next to pad 1 (left)
            b.line("top_silk", p["x"] - 1.65, p["y"] - 0.6, p["x"] - 1.65, p["y"] + 0.6, TEXT_W)
        b.parts.append(dict(p, layer="Top"))
    return b


# --------------------------------------------------------------------------- writers
def _origin(fmt, which):
    return ABSOLUTE_ORIGIN_MM if FORMATS[fmt][f"{which}_origin"] == "absolute" else (0.0, 0.0)


def _scale(units):
    return 1.0 if units == "mm" else 1 / 25.4


def _coord(v_mm, spec, off_mm):
    """A Gerber/Excellon coordinate string for v_mm in the given number format."""
    n = round((v_mm + off_mm) * _scale(spec["units"]) * 10 ** spec["dec"])
    if spec["zeros"] == "keep":
        digits = spec["int"] + spec["dec"]
        return ("-" if n < 0 else "") + f"{abs(n):0{digits}d}"
    return str(n)


def _ap_val(v_mm, units):
    return f"{v_mm * _scale(units):.4f}" if units == "mm" else f"{v_mm * _scale(units):.5f}"


def write_gerber(feats, layer, fmt) -> str:
    spec = FORMATS[fmt]["gerber"]
    ox, oy = _origin(fmt, "gerber")
    u = spec["units"]
    aps, order = {}, []
    for f in feats:
        key = ("C", _ap_val(f["w"], u), None) if f["kind"] == "line" or f["shape"] == "C" else \
              ("R", _ap_val(f["w"], u), _ap_val(f["h"], u))
        if key not in aps:
            aps[key] = 10 + len(aps)
            order.append(key)
        f["_ap"] = aps[key]
    out = [f"G04 Synthetic test board {BOARD_NAME}, layer {layer}, written by pcb-advisor scripts/jlc_testboard.py*",
           f"G04 {fmt}: {u} {spec['int']}:{spec['dec']}, leading zeros suppressed, "
           f"{FORMATS[fmt]['gerber_origin']} origin*",
           f"%FSLAX{spec['int']}{spec['dec']}Y{spec['int']}{spec['dec']}*%",
           "%MOMM*%" if u == "mm" else "%MOIN*%"]
    for key in order:
        shape, w, h = key
        out.append(f"%ADD{aps[key]}C,{w}*%" if shape == "C" else f"%ADD{aps[key]}R,{w}X{h}*%")
    out += ["%LPD*%", "G01*"]
    cur_ap, pos = None, None
    for f in feats:
        if f["_ap"] != cur_ap:
            out.append(f"D{f['_ap']}*")
            cur_ap = f["_ap"]
        if f["kind"] == "line":
            a = (_coord(f["x1"], spec, ox), _coord(f["y1"], spec, oy))
            e = (_coord(f["x2"], spec, ox), _coord(f["y2"], spec, oy))
            if pos != a:
                out.append(f"X{a[0]}Y{a[1]}D02*")
            out.append(f"X{e[0]}Y{e[1]}D01*")
            pos = e
        else:
            c = (_coord(f["x"], spec, ox), _coord(f["y"], spec, oy))
            out.append(f"X{c[0]}Y{c[1]}D03*")
            pos = c
    out.append("M02*")
    for f in feats:
        f.pop("_ap", None)
    return "\n".join(out) + "\n"


def write_excellon(holes, plated, fmt) -> str:
    spec = FORMATS[fmt]["drill"]
    ox, oy = _origin(fmt, "drill")
    sizes = sorted({round(h["d"], 4) for h in holes})
    zeros = {"keep": "LZ", "suppress_leading": "TZ", "suppress_trailing": "LZ"}[spec["zeros"]]
    units = "INCH" if spec["units"] == "inch" else "METRIC"
    out = ["M48", f";Synthetic test board {BOARD_NAME}, written by pcb-advisor scripts/jlc_testboard.py",
           f";FILE_FORMAT={spec['int']}:{spec['dec']}", f"{units},{zeros}",
           ";TYPE=PLATED" if plated else ";TYPE=NON_PLATED"]
    for i, d in enumerate(sizes, 1):
        size = d / 25.4 if spec["units"] == "inch" else d
        out.append(f"T{i}F00S00C{size:.5f}" if spec["units"] == "inch" else f"T{i}F00S00C{size:.3f}")
    out.append("%")
    for i, d in enumerate(sizes, 1):
        out.append(f"T{i:02d}")
        for h in holes:
            if round(h["d"], 4) == d:
                out.append(f"X{_coord(h['x'], spec, ox)}Y{_coord(h['y'], spec, oy)}")
    out.append("M30")
    return "\n".join(out) + "\n"


def file_names():
    names = {layer: f"{BOARD_NAME}.{ext}" for layer, ext in LAYERS.items()}
    names["drill_plated"] = f"{BOARD_NAME}-Plated.TXT"
    names["drill_nonplated"] = f"{BOARD_NAME}-NonPlated.TXT"
    return names


def write_format(board: Board, fmt: str, out_dir: pathlib.Path) -> dict:
    d = out_dir / fmt
    d.mkdir(parents=True, exist_ok=True)
    names = file_names()
    files = []
    for layer in LAYERS:
        (d / names[layer]).write_text(write_gerber(board.feats[layer], layer, fmt), encoding="ascii", newline="\n")
        files.append(names[layer])
    for plated, key in ((True, "drill_plated"), (False, "drill_nonplated")):
        holes = [h for h in board.holes if h["plated"] == plated]
        if holes:
            (d / names[key]).write_text(write_excellon(holes, plated, fmt), encoding="ascii", newline="\n")
            files.append(names[key])
    zpath = out_dir / f"{BOARD_NAME}_{fmt}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(d / name, arcname=name)          # flat: no folder inside the archive
    return {"dir": fmt, "zip": zpath.name, "files": files}


# --------------------------------------------------------------------------- readers (own output only)
def parse_gerber(text: str) -> dict:
    """RS-274X subset this module writes: FS (leading zeros suppressed), MO, ADD C/R, D01/D02/D03.
    Returns {"units", "fs": (int, dec), "apertures", "prims": [...] in file units}."""
    import re
    fs = units = None
    aps, prims = {}, []
    cur, x, y = None, 0, 0
    for raw in re.findall(r"%[^%]*%|[^%*\n]+\*", text):
        s = raw.strip()
        if s.startswith("%"):
            body = s.strip("%").rstrip("*")
            if body.startswith("FS"):
                m = re.fullmatch(r"FSLAX(\d)(\d)Y(\d)(\d)", body)
                if not m:
                    raise ValueError(f"unsupported FS {body}")
                fs = (int(m.group(1)), int(m.group(2)))
            elif body.startswith("MO"):
                units = {"MOMM": "mm", "MOIN": "inch"}[body]
            elif body.startswith("ADD"):
                m = re.fullmatch(r"ADD(\d+)([CR]),([\d.]+)(?:X([\d.]+))?", body)
                if not m:
                    raise ValueError(f"unsupported aperture {body}")
                w = float(m.group(3))
                aps[int(m.group(1))] = (m.group(2), w, float(m.group(4)) if m.group(4) else w)
            continue
        s = s.rstrip("*")
        if s.startswith("G04") or s in ("G01", "G75", "M02") or not s:
            continue
        m = re.fullmatch(r"D(\d+)", s)
        if m and int(m.group(1)) >= 10:
            cur = int(m.group(1))
            if cur not in aps:
                raise ValueError(f"D{cur} used before it is defined")
            continue
        m = re.fullmatch(r"(?:X(-?\d+))?(?:Y(-?\d+))?D0([123])", s)
        if not m:
            raise ValueError(f"unsupported Gerber statement {s!r}")
        if fs is None or units is None:
            raise ValueError("coordinates before FS/MO")
        nx = int(m.group(1)) / 10 ** fs[1] if m.group(1) is not None else x
        ny = int(m.group(2)) / 10 ** fs[1] if m.group(2) is not None else y
        op = m.group(3)
        if cur is None:
            raise ValueError("draw without an aperture")
        shape, w, h = aps[cur]
        if op == "1":
            prims.append({"kind": "line", "x1": x, "y1": y, "x2": nx, "y2": ny, "w": w, "ap": cur})
        elif op == "3":
            prims.append({"kind": "flash", "shape": shape, "x": nx, "y": ny, "w": w, "h": h, "ap": cur})
        x, y = nx, ny
    if not text.rstrip().endswith("M02*"):
        raise ValueError("no M02 at the end")
    return {"units": units, "fs": fs, "apertures": aps, "prims": prims}


def parse_excellon(text: str) -> dict:
    """Excellon subset this module writes. Returns {"units", "format", "zeros", "plated", "tools", "hits"}
    with tool sizes and hits in file units."""
    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines or lines[0] != "M48":
        raise ValueError("no M48 header")
    units = zeros = fmt = plated = None
    tools, hits, cur, in_header = {}, [], None, True
    for l in lines[1:]:
        if in_header:
            if l == "%":
                in_header = False
            elif l.startswith(";FILE_FORMAT="):
                a, b = l.split("=")[1].split(":")
                fmt = (int(a), int(b))
            elif l.startswith(";TYPE="):
                plated = l == ";TYPE=PLATED"
            elif re.fullmatch(r"(INCH|METRIC),(LZ|TZ)", l):
                units, zeros = l.split(",")
            elif re.fullmatch(r"T\d+(F\d+)?(S\d+)?C[\d.]+", l):
                n = int(re.match(r"T(\d+)", l).group(1))
                tools[n] = float(l.split("C")[-1])
            elif not l.startswith(";"):
                raise ValueError(f"unexpected header line {l!r}")
            continue
        if l == "M30":
            break
        m = re.fullmatch(r"T(\d+)", l)
        if m:
            cur = int(m.group(1))
            if cur not in tools:
                raise ValueError(f"T{cur} not in the tool list")
            continue
        m = re.fullmatch(r"X(-?\d+)Y(-?\d+)", l)
        if not m:
            raise ValueError(f"unsupported drill statement {l!r}")
        if None in (units, zeros, fmt, cur):
            raise ValueError("hit before units, zero mode, format or tool")
        vals = []
        for g in m.groups():
            neg, digits = g.startswith("-"), g.lstrip("-")
            if zeros == "LZ":                   # leading zeros present, trailing may be missing
                digits = digits.ljust(fmt[0] + fmt[1], "0")
            v = int(digits) / 10 ** fmt[1]
            vals.append(-v if neg else v)
        hits.append({"x": vals[0], "y": vals[1], "d": tools[cur]})
    else:
        raise ValueError("no M30 at the end")
    return {"units": "inch" if units == "INCH" else "mm", "format": fmt, "zeros": zeros,
            "plated": plated, "tools": tools, "hits": hits}


def load(out_dir, fmt) -> dict:
    """Read a written format back into board coordinates (mm): {layer: prims, "holes": [...]}."""
    d = pathlib.Path(out_dir) / fmt
    names = file_names()
    res = {}
    gx, gy = _origin(fmt, "gerber")
    for layer in LAYERS:
        g = parse_gerber((d / names[layer]).read_text(encoding="ascii"))
        k = 25.4 if g["units"] == "inch" else 1.0
        prims = []
        for p in g["prims"]:
            q = dict(p)
            for key in ("x", "x1", "x2"):
                if key in q:
                    q[key] = q[key] * k - gx
            for key in ("y", "y1", "y2"):
                if key in q:
                    q[key] = q[key] * k - gy
            q["w"], q["h"] = p["w"] * k, p.get("h", p["w"]) * k
            prims.append(q)
        res[layer] = prims
    hx, hy = _origin(fmt, "drill")
    res["holes"] = []
    for key, plated in (("drill_plated", True), ("drill_nonplated", False)):
        f = d / names[key]
        if f.exists():
            e = parse_excellon(f.read_text(encoding="ascii"))
            k = 25.4 if e["units"] == "inch" else 1.0
            res["holes"] += [{"x": h["x"] * k - hx, "y": h["y"] * k - hy, "d": h["d"] * k, "plated": plated}
                             for h in e["hits"]]
    return res


# --------------------------------------------------------------------------- measuring
def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _seg_seg(a, b, c, d):
    if _seg_cross(a, b, c, d):
        return 0.0
    return min(_pt_seg(*a, *c, *d), _pt_seg(*b, *c, *d), _pt_seg(*c, *a, *b), _pt_seg(*d, *a, *b))


def _shape(p):
    """('stadium', a, b, r) or ('rect', x0, y0, x1, y1)."""
    if p["kind"] == "line":
        return ("stadium", (p["x1"], p["y1"]), (p["x2"], p["y2"]), p["w"] / 2)
    if p["shape"] == "C":
        return ("stadium", (p["x"], p["y"]), (p["x"], p["y"]), p["w"] / 2)
    return ("rect", p["x"] - p["w"] / 2, p["y"] - p["h"] / 2, p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)


def _pt_rect(px, py, r):
    dx = max(r[1] - px, 0.0, px - r[3])
    dy = max(r[2] - py, 0.0, py - r[4])
    return math.hypot(dx, dy)


def gap(p, q) -> float:
    """Edge-to-edge distance between two primitives (0 when they touch or overlap)."""
    s, t = _shape(p), _shape(q)
    if s[0] == "rect" and t[0] == "rect":
        dx = max(0.0, max(s[1], t[1]) - min(s[3], t[3]))
        dy = max(0.0, max(s[2], t[2]) - min(s[4], t[4]))
        return math.hypot(dx, dy)
    if s[0] == "rect":
        s, t = t, s
    if t[0] == "stadium":
        return max(0.0, _seg_seg(s[1], s[2], t[1], t[2]) - s[3] - t[3])
    r = t
    a, b = s[1], s[2]
    corners = [(r[1], r[2]), (r[3], r[2]), (r[3], r[4]), (r[1], r[4])]
    inside = any(r[1] <= x <= r[3] and r[2] <= y <= r[4] for x, y in (a, b))
    crosses = any(_seg_cross(a, b, c, d) for c, d in zip(corners, corners[1:] + corners[:1]))
    if inside or crosses:
        return 0.0
    dist = min([_pt_rect(*a, r), _pt_rect(*b, r)] + [_pt_seg(*c, *a, *b) for c in corners])
    return max(0.0, dist - s[3])


def _in(p, box):
    xs = [p[k] for k in ("x", "x1", "x2") if k in p]
    ys = [p[k] for k in ("y", "y1", "y2") if k in p]
    return all(box[0] <= x <= box[2] for x in xs) and all(box[1] <= y <= box[3] for y in ys)


def measure(geo: dict, coupon: dict) -> dict:
    """The coupon's values as drawn in `geo` (from load()), in mm, rounded to 0.1 um."""
    box = coupon["bbox"]
    cu = [p for p in geo["top_copper"] if _in(p, box)]
    holes = [h for h in geo["holes"] if box[0] <= h["x"] <= box[2] and box[1] <= h["y"] <= box[3]]
    k = coupon["kind"]
    out = {}
    if k == "track_space":
        out["width_mm"] = min(p["w"] for p in cu)
        out["space_mm"] = min(gap(p, q) for i, p in enumerate(cu) for q in cu[i + 1:])
    elif k in ("annular_ring", "via", "drill"):
        h = holes[0]
        rings = []
        for layer in ("top_copper", "bottom_copper"):
            pad = min((p for p in geo[layer] if p["kind"] == "flash" and math.hypot(p["x"] - h["x"], p["y"] - h["y"]) < 0.01),
                      key=lambda p: p["w"])
            rings.append((pad["w"] - h["d"]) / 2)
        out.update(drill_mm=h["d"], ring_mm=min(rings))
        out["dia_mm" if k != "annular_ring" else "pad_mm"] = h["d"] + 2 * min(rings)
    elif k == "copper_to_edge":
        edges = geo["outline"]
        p = cu[0]
        to_centre = min(_seg_seg((p["x1"], p["y1"]), (p["x2"], p["y2"]), (e["x1"], e["y1"]), (e["x2"], e["y2"]))
                        for e in edges) - p["w"] / 2
        out["edge_mm"] = to_centre
        out["to_outline_line_edge_mm"] = to_centre - min(e["w"] for e in edges) / 2
    elif k == "silk_to_pad":
        silk = [p for p in geo["top_silk"] if _in(p, box)]
        mask = [p for p in geo["top_mask"] if _in(p, box)]
        out["silk_to_mask_mm"] = min(gap(s, m) for s in silk for m in mask)
        out["silk_to_pad_mm"] = min(gap(s, c) for s in silk for c in cu)
    elif k == "silk_width":
        out["width_mm"] = min(p["w"] for p in geo["top_silk"] if _in(p, box))
    elif k == "mask_dam":
        mask = sorted((p for p in geo["top_mask"] if _in(p, box)), key=lambda p: p["x"])
        cu = sorted(cu, key=lambda p: p["x"])
        out["dam_mm"] = min(gap(a, b) for a, b in zip(mask, mask[1:]))
        out["pad_gap_mm"] = min(gap(a, b) for a, b in zip(cu, cu[1:]))
    elif k == "hole_to_hole":
        a, b = holes[:2]
        out["gap_mm"] = math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - (a["d"] + b["d"]) / 2
        out["drill_mm"] = a["d"]
    elif k == "npth":
        out["drill_mm"] = holes[0]["d"]
    return {key: round(v, 4) for key, v in out.items()}


# --------------------------------------------------------------------------- main
def generate(out_dir, formats=DEFAULT_FORMATS) -> dict:
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    board = build()
    manifest = {
        "board": {"name": BOARD_NAME, "size_mm": [BOARD_W, BOARD_H], "layers": 2, "outline_layer": "GM1",
                  "outline_width_mm": OUTLINE_W, "mask_expansion_mm": MASK_EXP,
                  "absolute_origin_mm": list(ABSOLUTE_ORIGIN_MM),
                  "coordinates": "mm from the board's lower-left corner (outline centre line)"},
        "generator": "scripts/jlc_testboard.py",
        "coupons": board.coupons,
        "parts": board.parts,
        "formats": {},
    }
    for fmt in formats:
        info = write_format(board, fmt, out_dir)
        geo = load(out_dir, fmt)
        info.update({k: v for k, v in FORMATS[fmt].items()})
        info["origin_offset_mm"] = {"gerber": list(_origin(fmt, "gerber")), "drill": list(_origin(fmt, "drill"))}
        info["measured"] = {c["id"]: measure(geo, c) for c in board.coupons}
        manifest["formats"][fmt] = info
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the synthetic JLC test board (Gerber + drill, zipped)")
    ap.add_argument("out", help="output folder")
    ap.add_argument("--formats", default=",".join(DEFAULT_FORMATS),
                    help=f"comma list of {', '.join(FORMATS)} (default {','.join(DEFAULT_FORMATS)})")
    a = ap.parse_args(argv)
    fmts = [f for f in a.formats.split(",") if f]
    bad = [f for f in fmts if f not in FORMATS]
    if bad:
        raise SystemExit(f"unknown format(s): {', '.join(bad)}")
    m = generate(a.out, fmts)
    print(json.dumps({"out": str(pathlib.Path(a.out).resolve()), "coupons": len(m["coupons"]),
                      "zips": [m["formats"][f]["zip"] for f in fmts]}, indent=2))


if __name__ == "__main__":
    main()
