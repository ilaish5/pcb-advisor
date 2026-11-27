"""Synthetic fab sets and seeded defect injectors for the output metrics (A5, contract items 4 and 5).

`control_ctx(ctx, name, defect=None)` writes a small but realistic 4-layer fab set (Altium-dialect Gerbers in a zip, Excellon drills,
JLC CPL csv) into a fresh folder shaped like a fixture root and returns a Ctx for it. With `defect=None` it is a CLEAN board: every
output metric must pass on it. With a defect name it injects exactly one defect at a position drawn from `ctx.rng` (never a fixed
coordinate) and records it in `returned_ctx.canary = {"defect", "at": (x, y), ...}`; the metric must then fail and name that place.

Defects: web (two mask openings 0.06 mm apart), via_pad (an untented via 0.15 mm from a pad), npth (plane copper 0.12 mm from a
non-plated hole), ep_full (exposed pad with a full paste opening), cpl_origin (asymmetric part placed in the CPL at its origin),
tent_flip (all vias opened while the note says tented), note_missing, extra_cpl (a second CPL in the Altium output folder),
cpl_check_wrong (outputs-check validated another file), stack_missing, bom_split (one BOM line split in two identical lines),
drc_hidden (a DRC rule class open in the board check but absent from the manifest text).

The writer emits what Altium emits: %FSLAX24Y24*% inches, ADD apertures C/R/O, G36 regions with %LPC clear polygons on plane layers,
Excellon 2:4 LZ with a ;TYPE comment.
"""
from __future__ import annotations

import json
import math
import pathlib
import zipfile

from lib import Ctx

OFF = 20.0            # board origin offset in mm (Altium boards sit away from 0,0)
BOARD = (48.0, 40.0)  # board size mm
STACK_LAYERS = ("GTL", "GBL", "G1", "G2", "GTS", "GBS", "GTP", "GBP", "GM1")


# ------------------------------------------------------------------------------------------------------------ writers
def _c(mm: float) -> int:
    return int(round(mm / 25.4 * 1e4))


class _Layer:
    def __init__(self) -> None:
        self.aps: dict[tuple, int] = {}
        self.ops: list[str] = []
        self.cur = None

    def ap(self, shape: str, *dims: float) -> int:
        key = (shape,) + tuple(round(d / 25.4, 4) for d in dims)
        if key not in self.aps:
            self.aps[key] = 10 + len(self.aps)
        return self.aps[key]

    def flash(self, shape: str, x: float, y: float, *dims: float) -> None:
        a = self.ap(shape, *dims)
        if self.cur != a:
            self.ops.append(f"D{a}*")
            self.cur = a
        self.ops.append(f"X{_c(x)}Y{_c(y)}D03*")

    def draw(self, w: float, x0: float, y0: float, x1: float, y1: float) -> None:
        a = self.ap("C", w)
        if self.cur != a:
            self.ops.append(f"D{a}*")
            self.cur = a
        self.ops.append(f"X{_c(x0)}Y{_c(y0)}D02*")
        self.ops.append(f"X{_c(x1)}Y{_c(y1)}D01*")

    def region(self, pts: list, clear: bool = False) -> None:
        if clear:
            self.ops.append("%LPC*%")
        self.ops.append("G36*")
        self.ops.append(f"X{_c(pts[0][0])}Y{_c(pts[0][1])}D02*")
        for x, y in pts[1:] + [pts[0]]:
            self.ops.append(f"X{_c(x)}Y{_c(y)}D01*")
        self.ops.append("G37*")
        if clear:
            self.ops.append("%LPD*%")

    def text(self, polarity: str = "Positive") -> str:
        head = ["G04*", "G04 #@! TF.GenerationSoftware,synthetic oracle board*", "G04*", "%FSLAX24Y24*%", "%MOIN*%", "G70*", "G04*",
                f"G04 #@! TF.FilePolarity,{polarity}*", "G04*", "G01*", "G75*"]
        for key, code in self.aps.items():
            shape, dims = key[0], key[1:]
            head.append(f"%ADD{code}{shape},{'X'.join(f'{d:.4f}' for d in dims)}*%")
        return "\n".join(head + ["%LPD*%"] + self.ops + ["M02*"]) + "\n"


def _excellon(holes: list[tuple], plated: bool, slots: list | None = None) -> str:
    dias = sorted({round(h[2], 4) for h in holes})
    out = ["M48", ";Layer_Color=9474304", ";FILE_FORMAT=2:4", "INCH,LZ"]
    for i, d in enumerate(dias, 1):
        out.append(f"T{i:02d}F00S00C{d / 25.4:.4f}")
    out.append(";TYPE=PLATED" if plated else ";TYPE=NON_PLATED")
    out.insert(3, out.pop())            # ;TYPE before INCH like Altium's header block
    out.append("%")
    for i, d in enumerate(dias, 1):
        out.append(f"T{i:02d}")
        for x, y, dd in holes:
            if round(dd, 4) == d:
                out.append(f"X{str(_c(x)).zfill(6).rstrip('0') or '0'}Y{str(_c(y)).zfill(6).rstrip('0') or '0'}")
    out.append("M30")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------------------ board model
class Part:
    def __init__(self, ref, kind, x, y, pads, ep=None, cpl_at_origin=False):
        self.ref, self.kind, self.x, self.y, self.pads, self.ep, self.cpl_at_origin = ref, kind, x, y, pads, ep, cpl_at_origin

    def abs_pads(self):
        return [(self.x + dx, self.y + dy, w, h) for dx, dy, w, h in self.pads]

    def padbox_centre(self):
        ps = self.abs_pads() + ([(self.x, self.y, *self.ep)] if self.ep else [])
        x0 = min(p[0] - p[2] / 2 for p in ps)
        x1 = max(p[0] + p[2] / 2 for p in ps)
        y0 = min(p[1] - p[3] / 2 for p in ps)
        y1 = max(p[1] + p[3] / 2 for p in ps)
        return (x0 + x1) / 2, (y0 + y1) / 2


def _passive():
    return [(-0.5, 0, 0.5, 0.6), (0.5, 0, 0.5, 0.6)]


def _soic8():
    return [(sx * 2.7, y, 1.5, 0.6) for sx in (-1, 1) for y in (-1.905, -0.635, 0.635, 1.905)]


def _qfn16():
    pads = []
    for i in range(4):
        o = (i - 1.5) * 0.65
        pads += [(-1.9, o, 0.8, 0.3), (1.9, o, 0.8, 0.3), (o, -1.9, 0.3, 0.8), (o, 1.9, 0.3, 0.8)]
    return pads


def _connector():
    pads = [(x * 0.8, 1.2 + 0.6, 0.4, 1.6) for x in (-2, -1, 0, 1, 2)]       # signal row
    pads += [(-3.6, -0.6 + 0.6, 1.2, 2.4), (3.6, -0.6 + 0.6, 1.2, 2.4)]        # shield pads, lower than the signal row
    pads += [(-3.6, 2.6, 1.2, 0.8)]                                            # one extra lug on the left only
    return pads


class Synth:
    """A clean 4-layer board built from the rng, with optional single defects."""

    def __init__(self, rng, defect: str | None = None, legal_open: bool = False) -> None:
        self.rng = rng
        self.legal_open = legal_open
        self.defect = defect
        self.parts: list[Part] = []
        self.vias: list[tuple] = []          # (x, y, untented)
        self.npth: list[tuple] = []          # (x, y, d, clear_r)
        self.extra_pads: list[tuple] = []
        self.ep_windows = "four"
        self.injected: dict | None = None
        self.open_vias = False
        self.flags: set[str] = set()
        self._build()

    def _build(self) -> None:
        r = self.rng
        cell = 14.0
        kinds = ["qfn", "soic", "conn", "pas", "pas", "pas", "pas", "pas"]
        r.shuffle(kinds)
        n = 0
        for i, k in enumerate(kinds[:6]):
            pass
        spots = [(OFF + 8 + cell * i, OFF + 9 + cell * j) for j in range(2) for i in range(3)]
        order = ["qfn", "conn", "soic", "pas", "pas", "pas"]
        r.shuffle(order)
        for (cx, cy), kind in zip(spots, order):
            x, y = cx + r.uniform(-1.0, 1.0), cy + r.uniform(-1.0, 1.0)
            n += 1
            if kind == "qfn":
                s = round(r.uniform(1.5, 2.4), 2)                                  # another size every run
                self.parts.append(Part(f"U{n}", kind, x, y, _qfn16(), ep=(s, s)))
            elif kind == "soic":
                self.parts.append(Part(f"U{n}", kind, x, y, _soic8()))
            elif kind == "conn":
                self.parts.append(Part(f"J{n}", kind, x, y, _connector()))
            else:
                self.parts.append(Part(f"R{n}", kind, x, y, _passive()))
        for p in self.parts:                 # tented vias well away from every pad (corner offsets of the cell)
            self.vias.append((p.x + 5.6, p.y - 5.0, False))
            self.vias.append((p.x + 5.6, p.y + 5.0, False))
        if self.legal_open:                  # an untented via at a legal distance (pad copper to via copper 0.30 mm) from a passive's pad
            q = next(p for p in self.parts if p.kind == "pas")
            self.vias.append((q.x + 0.75 + 0.30 + 0.30, q.y, True))
        self.npth = [(OFF + 3.0, OFF + 3.0, 3.2, 1.6 + 0.45), (OFF + BOARD[0] - 3.0, OFF + BOARD[1] - 3.0, 3.2, 1.6 + 0.45)]
        d = self.defect
        if d == "web":
            x, y = OFF + r.uniform(8, BOARD[0] - 8), OFF + BOARD[1] - 3.0 - r.uniform(0, 1)
            # two pads 0.5 x 0.6 whose mask openings (pad + 0.05 mm each side) end up 0.06 mm apart: copper gap 0.16
            self.extra_pads += [(x - 0.33, y, 0.5, 0.6), (x + 0.33, y, 0.5, 0.6)]
            self.injected = {"defect": d, "at": (x, y)}
        elif d == "via_pad":
            x, y = OFF + r.uniform(10, BOARD[0] - 10), OFF + r.uniform(1.0, 2.0)
            self.vias.append((x, y, True))                                      # untented via, copper d 0.6
            self.extra_pads.append((x + 0.3 + 0.15 + 0.3, y, 0.6, 0.6))         # pad copper edge 0.15 mm from the via copper
            self.injected = {"defect": d, "at": (x, y)}
        elif d == "npth":
            i = r.randrange(len(self.npth))
            x, y, dia, _ = self.npth[i]
            self.npth[i] = (x, y, dia, 1.6 + 0.12 / math.cos(math.pi / 32))      # plane clear ring: facet gap 0.12 mm
            self.injected = {"defect": d, "at": (x, y)}
        elif d == "ep_full":
            self.ep_windows = "full"
            q = next(p for p in self.parts if p.ep)
            self.injected = {"defect": d, "at": (q.x, q.y)}
        elif d == "tent_flip":
            self.open_vias = True
            self.injected = {"defect": d, "at": None}
        elif d in ("note_missing", "extra_cpl", "cpl_check_wrong", "stack_missing", "bom_split", "drc_hidden"):
            self.flags.add(d)
            self.injected = {"defect": d, "at": None}
        elif d == "cpl_origin":
            c = next(p for p in self.parts if p.kind == "conn")
            c.cpl_at_origin = True
            self.injected = {"defect": d, "at": (c.x, c.y), "ref": c.ref}

    # --- outputs
    def gerbers(self) -> dict[str, str]:
        L = {k: _Layer() for k in STACK_LAYERS}
        exp = 0.05
        for p in self.parts:
            for x, y, w, h in p.abs_pads():
                self._pad(L, x, y, w, h, exp)
            if p.ep:
                x, y = p.x, p.y
                w, h = p.ep
                L["GTL"].flash("R", x, y, w, h)
                L["GTS"].flash("R", x, y, w + 2 * exp, h + 2 * exp)
                if self.ep_windows == "full":
                    L["GTP"].flash("R", x, y, w, h)
                else:
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            L["GTP"].flash("R", x + sx * 0.25 * w, y + sy * 0.25 * h, 0.4 * w, 0.4 * h)   # four windows, 64 % coverage
        for x, y, w, h in self.extra_pads:
            self._pad(L, x, y, w, h, exp)
        for x, y, open_ in self.vias:
            for k in ("GTL", "GBL"):
                L[k].flash("C", x, y, 0.6)
            if open_ or self.open_vias:
                for k in ("GTS", "GBS"):
                    L[k].flash("C", x, y, 0.7)
        for x, y, d, cr in self.npth:
            for k in ("GTL", "GBL"):
                L[k].flash("C", x, y, d)                                       # Altium flashes a pad as large as the hole
            for k in ("GTS", "GBS"):
                L[k].flash("C", x, y, d + 0.1)
        # a couple of tracks so the copper layers are not only flashes
        for p in self.parts[:3]:
            L["GTL"].draw(0.2, p.x + 5.6, p.y - 5.0, p.x + 5.6, p.y - 6.5)
        # planes: outer region, then clear polygons around every hole and via (negative-style antipads)
        for k in ("G1", "G2"):
            outer = [(OFF + 0.2, OFF + 0.2), (OFF + BOARD[0] - 0.2, OFF + 0.2), (OFF + BOARD[0] - 0.2, OFF + BOARD[1] - 0.2),
                     (OFF + 0.2, OFF + BOARD[1] - 0.2)]
            L[k].region(outer)
            for x, y, _o in self.vias:
                L[k].region([(x + 0.55 * math.cos(2 * math.pi * i / 24), y + 0.55 * math.sin(2 * math.pi * i / 24)) for i in range(24)], clear=True)
            for x, y, d, cr in self.npth:
                L[k].region([(x + cr * math.cos(2 * math.pi * i / 32), y + cr * math.sin(2 * math.pi * i / 32)) for i in range(32)], clear=True)
        o = [(OFF, OFF), (OFF + BOARD[0], OFF), (OFF + BOARD[0], OFF + BOARD[1]), (OFF, OFF + BOARD[1]), (OFF, OFF)]
        for a, b in zip(o, o[1:]):
            L["GM1"].draw(0.15, a[0], a[1], b[0], b[1])
        return {k: v.text("Negative" if k in ("GTS", "GBS") else "Positive") for k, v in L.items()}

    def _pad(self, L, x, y, w, h, exp) -> None:
        L["GTL"].flash("R", x, y, w, h)
        L["GTS"].flash("R", x, y, w + 2 * exp, h + 2 * exp)
        L["GTP"].flash("R", x, y, w, h)

    def drills(self) -> dict[str, str]:
        pth = [(x, y, 0.3) for x, y, _o in self.vias]
        for p in self.parts:                                               # the connector's two shield pads are through-hole
            if p.kind == "conn":
                pth += [(p.x + dx, p.y + dy, 0.6) for dx, dy, w, h in p.pads if (w, h) == (1.2, 2.4)]
        npth = [(x, y, d) for x, y, d, _c in self.npth]
        return {"SYN-RoundHoles-Plated.TXT": _excellon(pth, True), "SYN-RoundHoles-NonPlated.TXT": _excellon(npth, False)}

    def cpl(self) -> str:
        rows = ["Designator,Mid X,Mid Y,Layer,Rotation"]
        for p in self.parts:
            cx, cy = (p.x, p.y) if p.cpl_at_origin else p.padbox_centre()
            rows.append(f"{p.ref},{cx:.4f}mm,{cy:.4f}mm,Top,0.0")
        return "\n".join(rows) + "\n"


    def pad_table(self) -> list[tuple]:
        """Pad ownership a PcbDoc would give: (ref, side, x, y) for every pad of every part (the synthetic set has no PcbDoc)."""
        out = []
        for p in self.parts:
            out += [(p.ref, "top", x, y) for x, y, _w, _h in p.abs_pads()]
            if p.ep:
                out.append((p.ref, "top", p.x, p.y))
        return out

    def bom(self) -> str:
        rows = [("100nF", "C1,C2", "C0402", "C1525"), ("10k", "R1,R2", "R0402", "C25744"), ("MCU", "U1", "QFN-16", "C100001")]
        if "bom_split" in self.flags:
            k = self.rng.randrange(len(rows))
            c, refs, fp, lc = rows[k]
            a, b = refs.split(",") if "," in refs else (refs, refs + "x")
            rows[k:k + 1] = [(c, a, fp, lc), (c, b, fp, lc)]
            self.injected = {"defect": "bom_split", "at": None, "lcsc": lc}
        return "Comment,Designator,Footprint,LCSC Part #\n" + "".join(f'{c},"{r}",{f},{l}\n' for c, r, f, l in rows)

    def drc(self) -> dict[str, int]:
        rules = ["Minimum Solder Mask Sliver", "Silk To Solder Mask Clearance", "Un-Routed Net Constraint", "Clearance Constraint"]
        return {r: self.rng.randint(1, 60) for r in rules}


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def write_fab_set(synth: Synth, root: pathlib.Path, ref_name: str = "SYN") -> None:
    exp = root / "project" / "exports"
    exp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(exp / f"{ref_name}_gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for ext, txt in synth.gerbers().items():
            z.writestr(f"{ref_name}.{ext}", txt)
        for nm, txt in synth.drills().items():
            z.writestr(nm, txt)
    cpl_text = synth.cpl()
    (exp / f"{ref_name}_cpl.csv").write_bytes(cpl_text.encode("utf-8"))
    (exp / f"{ref_name}_BOM_jlc.csv").write_text(synth.bom(), encoding="utf-8")
    (root / "project" / "project.json").write_text(json.dumps({"name": ref_name, "board": {"mask_colour": "green"}}), encoding="utf-8")
    alt = root / "altium" / "Project Outputs for SYN" / "Pick Place"
    alt.mkdir(parents=True, exist_ok=True)
    if "extra_cpl" in synth.flags:
        (alt / f"Pick Place for {ref_name}.txt").write_text(
            "Designator Comment Layer Footprint Center-X(mm) Center-Y(mm) Rotation Description\n"
            + "".join(f"{p.ref} x TopLayer FP {p.x:.3f} {p.y:.3f} 0 d\n" for p in synth.parts), encoding="utf-8")
    # manifest: stack, CPL rule statement, DRC classes (counts), raw board_check record
    drc = synth.drc()
    viols = [f"{r} (Constraint): item {i}" for r, n in drc.items() for i in range(n)]
    shown = {r: n for r, n in drc.items()}
    hidden = None
    if "drc_hidden" in synth.flags:
        hidden = synth.rng.choice(sorted(shown))
        del shown[hidden]
        synth.injected = {"defect": "drc_hidden", "at": None, "rule": hidden, "count": drc[hidden]}
    manifest = {"generated": "synthetic",
                "cpl_rule": "CPL point = centre of the bounding box of all pads of the part (JLC: geometric centre).",
                "drc_open_by_rule": shown,
                "board_check": {"drc": {"drc": {"violations": viols}}}}
    if "stack_missing" not in synth.flags:
        manifest["stack"] = "JLC04161H-7628"
    (exp / f"{ref_name}_order_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if "note_missing" not in synth.flags:
        (exp / f"{ref_name}_order_note.md").write_text(
            "# JLC order note\n\n- 4 layers, 1.6 mm, HASL, green mask.\n- Vias are tented: no mask opening over any via.\n", encoding="utf-8")
    found = {"name": f"Pick Place for {ref_name}.txt"} if "cpl_check_wrong" in synth.flags else         {"name": f"{ref_name}_cpl.csv", "sha256": _sha(cpl_text.encode("utf-8"))}
    (root / "project" / "outputs-check.json").write_text(json.dumps(
        {"ok": True, "expected": [{"kind": "cpl", "label": "Pick and place (CPL)", "found": [found]}]}), encoding="utf-8")


def control_ctx(ctx: Ctx, name: str, defect: str | None = None, legal_open: bool = False) -> Ctx:
    """A fixture-shaped folder with a synthetic fab set. Positions come from ctx.rng. `.canary` holds the injected defect, if any;
    `.pad_table` is the pad ownership a PcbDoc would give (the synthetic set has none)."""
    root = ctx.work / name
    if root.exists():
        import shutil
        shutil.rmtree(root)
    synth = Synth(ctx.rng, defect, legal_open)
    write_fab_set(synth, root)
    c = Ctx(root, ctx.seed, ctx.work, ctx.live, frozen=False, label=name)
    c.canary = synth.injected
    c.pad_table = synth.pad_table()
    return c
