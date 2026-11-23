"""Quick previews of a library line's models, as plain data the UI draws: a symbol, a footprint, the 3D file.

Generic: nothing here knows a project or a board. Everything is read from the project's library/ folder and its
manifest.json entry (see partlib.prepare); the client sends only a line key, never a path.

Where the geometry comes from, in this order:
  1. the part's own KiCad files (easyeda/<C..>/lib.kicad_sym and lib.pretty/*.kicad_mod, a vendor zip's files, KiCad's
     official footprint under kicad/<lib>/): the source geometry, with the courtyard and fab drawing kept;
  2. the build spec (library/build/symbols_spec.txt, footprints_spec.txt): what Altium was given. Generated parts and the
     KiCad passives have their symbol only here (their symbol is drawn from the netlist, there is no kicad_sym).
`source` in the answer says which one was used. Both are parsed into the same shape, so one drawing serves both.

Units in the answers: a symbol in mil (y up, a pin's `x`,`y` is its body end and `cx`,`cy` its connection end), a footprint in
mm (y up). Every file is untrusted data: a file that cannot be read is an answer (error), never an exception.
Every path starts at the manifest and must resolve inside library/ (resolve() follows links, so a link cannot escape).
"""
import math
import pathlib
import re

import partlib_convert as pc

MM_PER_MIL = 0.0254
MAX_MODEL_BYTES = 40 * 1024 * 1024
LCSC_RE = re.compile(r"^C\d{2,9}$")
LAYER_KIND = {"Top Overlay": "silk", "Mechanical Layer 15": "courtyard", "Mechanical Layer 13": "fab"}
SHAPES = {1: "round", 2: "rect", 3: "octagon", 9: "roundrect"}


class PreviewError(Exception):
    """A refusal or a missing piece, with the sentence the student reads and the HTTP code to send."""

    def __init__(self, message, code=404):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ paths

def inside(lib, path):
    """The resolved path when it is an existing file inside lib (links followed), else None."""
    try:
        root, p = pathlib.Path(lib).resolve(), pathlib.Path(path).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    return p if root in p.parents and p.is_file() else None


def manifest_path(lib, rel):
    """A path written in the manifest (relative to library/) as an existing file inside library/, or None."""
    if not isinstance(rel, str) or not rel.strip() or "\0" in rel:
        return None
    return inside(lib, pathlib.Path(lib) / rel)


def part_root(lib, entry):
    """The folder the part's own files live in: the first two components of its STEP path (easyeda/<C..>, vendor/<mpn>,
    kicad/<lib>), else easyeda/<LCSC> for an EasyEDA part with no STEP. None when the manifest names nothing usable."""
    step = entry.get("step")
    if isinstance(step, str) and step.strip() and "\0" not in step:
        parts = pathlib.PurePosixPath(step.replace("\\", "/")).parts
        if len(parts) >= 3 and ".." not in parts and not pathlib.PurePosixPath(step.replace("\\", "/")).is_absolute() and parts[0] in ("easyeda", "vendor", "kicad"):
            root = pathlib.Path(lib).joinpath(*parts[:2])
            return root if _dir_inside(lib, root) else None
    lcsc = entry.get("lcsc")
    if entry.get("source") == "easyeda" and isinstance(lcsc, str) and LCSC_RE.match(lcsc):
        root = pathlib.Path(lib) / "easyeda" / lcsc
        return root if _dir_inside(lib, root) else None
    return None


def _dir_inside(lib, path):
    try:
        root, p = pathlib.Path(lib).resolve(), pathlib.Path(path).resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    return root in p.parents and p.is_dir()


def _first(lib, root, pattern, prefer=None, any_ok=True):
    """A file under root matching pattern and inside library/: the one whose stem is `prefer` (or its safe form), else the first."""
    if root is None:
        return None
    found = [f for f in sorted(root.rglob(pattern))[:200] if inside(lib, f)]
    for f in found:
        if prefer and (f.stem == prefer or pc.safe_name(f.stem) == prefer):
            return inside(lib, f)
    return inside(lib, found[0]) if found and any_ok else None


def part_files(lib, entry):
    """{root, sym, mod, step, wrl}: each an existing file inside library/ or None."""
    root = part_root(lib, entry)
    own = entry.get("source") in ("easyeda", "vendor")      # KiCad's footprint folder is shared: only the exact name counts there
    step = manifest_path(lib, entry.get("step"))
    if step is not None and step.suffix.lower() not in (".step", ".stp"):
        step = None
    wrl = inside(lib, step.with_suffix(".wrl")) if step is not None else None
    if wrl is None and not str(entry.get("step") or "").strip() and root is not None:      # no STEP named at all: a .wrl may still sit in the part's folder
        wrl = _first(lib, root, "*.wrl")
    return {"root": root, "step": step, "wrl": wrl,
            "sym": _first(lib, root, "*.kicad_sym") if own else None,
            "mod": _first(lib, root, "*.kicad_mod", prefer=entry.get("footprint"), any_ok=own)}


# ------------------------------------------------------------------ the build spec

def _spec_lines(path):
    try:
        return pathlib.Path(path).read_text(encoding="cp1252", errors="replace").splitlines()
    except OSError:
        return []


def spec_symbol(lib, name):
    """build/symbols_spec.txt -> (pins, gfx) of the symbol `name`, or None."""
    pins, gfx, cur = [], [], False
    for ln in _spec_lines(pathlib.Path(lib) / "build" / "symbols_spec.txt"):
        f = ln.split("|")
        if f[0] == "SYMBOL":
            if cur:
                break
            cur = len(f) > 1 and f[1] == name
        elif cur and f[0] == "GRAPHIC":
            gfx.append(f[1:])
        elif cur and f[0] == "PIN" and len(f) >= 9:
            pins.append({"num": f[1], "name": f[2], "type": f[3].replace("eElectric", ""), "orient": f[4],
                         "x": float(f[5]), "y": float(f[6]), "len": float(f[8])})
    return (pins, gfx) if cur else None


def spec_footprint(lib, name):
    """build/footprints_spec.txt -> the spec lines of footprint `name`, or None."""
    out, cur = [], False
    for ln in _spec_lines(pathlib.Path(lib) / "build" / "footprints_spec.txt"):
        if ln.startswith("FOOTPRINT|"):
            if cur:
                break
            cur = ln.split("|")[1:2] == [name]
        elif cur and ln and not ln.startswith("FPLIB|"):
            out.append(ln)
    return out if cur else None


# ------------------------------------------------------------------ symbol

def _num(v):
    return float(v)


def _gfx(g):
    """One spec graphic (list of strings or numbers) -> a drawing item, or None."""
    k = g[0]
    c = [_num(v) for v in g[{"rectangle": 4, "polygon": 4, "polyline": 3, "arc": 3}.get(k, 99):]]
    if k == "rectangle" and len(c) >= 4:
        return {"k": "rect", "x1": c[0], "y1": c[1], "x2": c[2], "y2": c[3]}
    if k in ("polygon", "polyline") and len(c) >= 4:
        return {"k": "poly", "fill": k == "polygon", "pts": [[c[i], c[i + 1]] for i in range(0, len(c) - 1, 2)]}
    if k == "arc" and len(c) >= 5:
        return {"k": "arc", "cx": c[0], "cy": c[1], "r": c[2], "a0": c[3], "a1": c[4]}
    return None


def _symbol_dict(name, pins, gfx, source):
    out_pins = []
    for p in pins:
        dx, dy = pc.DIRS.get(p["orient"], (1, 0))
        ln = _num(p["len"])
        out_pins.append({"num": str(p["num"]), "name": str(p["name"]), "type": str(p.get("type", "")), "x": _num(p["x"]), "y": _num(p["y"]),
                         "cx": _num(p["x"]) + dx * ln, "cy": _num(p["y"]) + dy * ln, "dx": dx, "dy": dy, "len": ln})
    items = [i for i in (_gfx(g) for g in gfx) if i]
    xs, ys = [], []
    for p in out_pins:
        xs += [p["x"], p["cx"]]
        ys += [p["y"], p["cy"]]
    for i in items:
        for x, y in ([(i["x1"], i["y1"]), (i["x2"], i["y2"])] if i["k"] == "rect" else i["pts"] if i["k"] == "poly"
                     else [(i["cx"] - i["r"], i["cy"] - i["r"]), (i["cx"] + i["r"], i["cy"] + i["r"])]):
            xs.append(x)
            ys.append(y)
    bounds = [min(xs), min(ys), max(xs), max(ys)] if xs else [-100, -100, 100, 100]
    return {"name": name, "source": source, "unit": "mil", "pins": out_pins, "gfx": items, "bounds": bounds}


def symbol_preview(lib, entry):
    files = part_files(lib, entry)
    name = entry.get("symbol") or ""
    notes = []
    if files["sym"] is not None:
        try:
            syms = pc.convert_symbols(files["sym"].read_text(encoding="utf-8", errors="replace"))
            sym = next((s for s in syms if s["name"] == name), syms[0] if syms else None)
            if sym and sym["pins"]:
                return _symbol_dict(sym["name"], sym["pins"], sym["gfx"], "kicad_sym")
        except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError, RecursionError):
            notes.append("The symbol file could not be read, so the build's copy is shown.")
    spec = spec_symbol(lib, name) if name else None
    if spec and spec[0]:
        try:
            d = _symbol_dict(name, spec[0], spec[1], "build spec")
        except (ValueError, KeyError, TypeError):
            d = None
        if d:
            d["notes"] = notes
            return d
    raise PreviewError("There is no symbol to draw yet. Build the library." if not name else "The symbol could not be read. Build the library again.")


# ------------------------------------------------------------------ footprint

def _mm(v):
    return round(_num(v) * MM_PER_MIL, 4)


def _pad(f):
    shape = SHAPES.get(int(float(f[13])), "rect")
    w, h = _mm(f[11]), _mm(f[12])
    if shape == "round" and abs(w - h) > 0.001:
        shape = "oval"
    d = {"num": f[1], "x": _mm(f[2]), "y": _mm(f[3]), "rot": _num(f[4]) % 360, "w": w, "h": h, "shape": shape,
         "thru": f[5] == "Multi-Layer" or _num(f[7]) > 0, "hole": _mm(f[7])}
    if shape == "roundrect":
        d["radius"] = round(min(w, h) * (float(f[14]) / 200 if len(f) > 14 and f[14] else 0.25), 4)
    if int(float(f[8] or 0)) == 2:                         # a slot: its length and angle
        d["slot"], d["slot_rot"] = _mm(f[9]), _num(f[10])
    return d


def _pad_extent(p):
    t = math.radians(p["rot"])
    hw = (abs(p["w"] * math.cos(t)) + abs(p["h"] * math.sin(t))) / 2
    hh = (abs(p["w"] * math.sin(t)) + abs(p["h"] * math.cos(t))) / 2
    return p["x"] - hw, p["y"] - hh, p["x"] + hw, p["y"] + hh


STANDARD_PITCHES = (0.35, 0.4, 0.5, 0.65, 0.8, 0.95, 1.0, 1.016, 1.27, 1.5, 1.778, 2.0, 2.54, 3.5, 3.81, 5.0, 5.08)


def _pitch(centres):
    """The usual centre-to-centre distance of neighbouring pads, in mm: the commonest nearest-neighbour distance, snapped to a
    standard pitch when within 0.02 mm (a source's own rounding is 1.26 for 1.27), else to 0.01. None for one pad."""
    if len(centres) < 2:
        return None
    near = [min(math.hypot(a[0] - b[0], a[1] - b[1]) for b in centres if b is not a) for a in centres]
    near.sort()
    mid = near[len(near) // 2]
    std = min(STANDARD_PITCHES, key=lambda s: abs(s - mid))
    return std if abs(std - mid) <= 0.02 else round(mid, 2)


def footprint_from_lines(name, lines, source):
    pads, art = [], {"silk": [], "courtyard": [], "fab": []}
    for ln in lines:
        f = ln.split("|")
        try:
            if f[0] == "PAD" and len(f) >= 14:
                pads.append(_pad(f))
            elif f[0] == "TRACK" and LAYER_KIND.get(f[6]):
                art[LAYER_KIND[f[6]]].append({"k": "line", "x1": _mm(f[1]), "y1": _mm(f[2]), "x2": _mm(f[3]), "y2": _mm(f[4]), "w": _mm(f[5])})
            elif f[0] == "ARC" and LAYER_KIND.get(f[7]):
                art[LAYER_KIND[f[7]]].append({"k": "arc", "cx": _mm(f[1]), "cy": _mm(f[2]), "r": _mm(f[3]), "a0": _num(f[4]), "a1": _num(f[5]), "w": _mm(f[6])})
            elif f[0] == "REGION" and LAYER_KIND.get(f[1]) and len(f) >= 7:
                c = [_mm(v) for v in f[3:]]
                art[LAYER_KIND[f[1]]].append({"k": "poly", "pts": [[c[i], c[i + 1]] for i in range(0, len(c) - 1, 2)]})
        except (ValueError, IndexError):
            continue                                        # one odd line does not spoil the drawing
    if not pads:
        raise PreviewError("The footprint has no pads to draw.")
    ext = [_pad_extent(p) for p in pads]
    box = [min(e[0] for e in ext), min(e[1] for e in ext), max(e[2] for e in ext), max(e[3] for e in ext)]
    pin1 = next((p["num"] for p in pads if p["num"] in ("1", "A1")), pads[0]["num"])
    centres = sorted({(p["x"], p["y"]) for p in pads})
    pitch = _pitch(centres)
    cy = art["courtyard"]
    cy_box = None
    if cy:
        xs = [v for i in cy for v in ([i["x1"], i["x2"]] if i["k"] == "line" else [x for x, _ in i["pts"]] if i["k"] == "poly" else [i["cx"] - i["r"], i["cx"] + i["r"]])]
        ys = [v for i in cy for v in ([i["y1"], i["y2"]] if i["k"] == "line" else [y for _, y in i["pts"]] if i["k"] == "poly" else [i["cy"] - i["r"], i["cy"] + i["r"]])]
        cy_box = [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)]
    allx = [box[0], box[2]] + [v for i in art["silk"] if i["k"] == "line" for v in (i["x1"], i["x2"])]
    ally = [box[1], box[3]] + [v for i in art["silk"] if i["k"] == "line" for v in (i["y1"], i["y2"])]
    return {"name": name, "source": source, "unit": "mm", "pads": pads, "silk": art["silk"], "courtyard": art["courtyard"], "fab": art["fab"],
            "pin1": pin1, "pitch": pitch, "pad_extent": [round(box[2] - box[0], 3), round(box[3] - box[1], 3)],
            "courtyard_size": cy_box, "bounds": [min(allx), min(ally), max(allx), max(ally)]}


def footprint_preview(lib, entry):
    files = part_files(lib, entry)
    name = entry.get("footprint") or ""
    notes = []
    if files["mod"] is not None:
        try:
            fp = pc.convert_footprint(files["mod"].read_text(encoding="utf-8", errors="replace"))
            d = footprint_from_lines(str(fp["name"]).split(":")[-1], fp["lines"], "kicad_mod")
            d["errors"] = fp.get("errors", [])
            return d
        except PreviewError:
            raise
        except (ValueError, KeyError, IndexError, TypeError, OSError, UnicodeError, RecursionError):
            notes.append("The footprint file could not be read, so the build's copy is shown.")
    lines = spec_footprint(lib, name) if name else None
    if lines:
        d = footprint_from_lines(name, lines, "build spec")
        d["notes"] = notes
        return d
    raise PreviewError("There is no footprint to draw yet. Build the library." if not name else "The footprint could not be read. Build the library again.")


# ------------------------------------------------------------------ 3D

def model_info(lib, entry):
    files = part_files(lib, entry)
    return {"step": files["step"] is not None, "wrl": files["wrl"] is not None,
            "name": (files["wrl"] or files["step"] or pathlib.Path("")).stem,
            "step_bytes": files["step"].stat().st_size if files["step"] else 0, "wrl_bytes": files["wrl"].stat().st_size if files["wrl"] else 0}


def model_file(lib, entry, fmt):
    """(bytes, content type, file name) of the line's 3D model in `fmt` ('wrl' or 'step')."""
    if fmt not in ("wrl", "step"):
        raise PreviewError("Unknown model format.", 400)
    f = part_files(lib, entry)[fmt]
    if f is None:
        raise PreviewError("This part has no 3D model file of that kind.")
    if f.stat().st_size > MAX_MODEL_BYTES:
        raise PreviewError("The 3D model file is too large to preview.", 413)
    return f.read_bytes(), ("model/vrml" if fmt == "wrl" else "model/step"), f.name


# ------------------------------------------------------------------ one entry point for the server

def preview(lib, manifest, line, kind):
    """The preview data of one manifest line: kind 'symbol' | 'footprint' | 'model'. Raises PreviewError."""
    entry = manifest.get(line) if isinstance(manifest, dict) and isinstance(line, str) else None
    if not isinstance(entry, dict):
        raise PreviewError("This line is not in the library yet. Build the library.")
    if kind == "symbol":
        return symbol_preview(lib, entry)
    if kind == "footprint":
        return footprint_preview(lib, entry)
    if kind == "model":
        return model_info(lib, entry)
    raise PreviewError("Unknown preview kind.", 400)
