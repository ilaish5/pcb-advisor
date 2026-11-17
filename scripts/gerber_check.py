"""The produced Gerber and drill files against the PcbDoc they claim to come from (spec A15).

Pure functions: text in, numbers out. jlc_upload calls them with the files of the zip and the facts read from the PcbDoc.
Compared: the hole count and diameters (plated and non-plated), the outline size, the number of copper layers.
Altium's own formats (read from a real OutJob output): Excellon "INCH,LZ" with ";TYPE=PLATED" / ";TYPE=NON_PLATED" and a tool
table "T01F00S00C0.0120"; Gerber "%FSLAX24Y24*%" "%MOIN*%" with G04 comments, D01/D02/D03 and G02/G03 arcs (I/J)."""
import collections
import math
import re

HOLE_TOL_MM = 0.01
OUTLINE_TOL_MM = 0.05
MAX_BYTES = 262144                       # a file is read up to this many bytes; a longer one is not checked


SAVE_FIRST = "save the PcbDoc in Altium first, then generate outputs again"


def parse_excellon(text: str) -> dict | None:
    """{"plated": True/False/None, "holes": [diameter_mm, ...], "tol": mm} of one Excellon file, or None when it is not one.
    One entry per hit (a hit line X..Y.., or a lone X.. / Y.. after the previous one), per G85 slot and per M15..M16 route
    (Altium writes slots as routes: G00X..Y.., M15, G01.., M16). Tools may be defined in any header or in the body, and a
    second M48 header adds to the first. `tol` is half the last digit of the diameters as written (inch 2:3 writes 0.8 mm
    as 0.031)."""
    if "M48" not in text[:2048]:
        return None
    metric, tools, cur, holes, plated, tol = False, {}, None, [], None, 0.0
    routing, x, y, start = False, None, None, (None, None)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(";"):
            m = re.match(r";\s*TYPE\s*=\s*(\w+)", line, re.I)
            if m:
                t = m.group(1).upper().replace("_", "")
                plated = True if t == "PLATED" else False if t == "NONPLATED" else None     # MIXED etc.: unknown
            continue
        if line.startswith(("METRIC", "M71")):
            metric = True
        elif line.startswith(("INCH", "M72")):
            metric = False
        m = re.match(r"T(\d+)(?:[A-BD-Z]\d*(?:\.\d+)?)*C(\d*)\.?(\d*)", line)
        if m and (m.group(2) or m.group(3)):
            k = 1.0 if metric else 25.4
            tools[int(m.group(1))] = float(f"{m.group(2) or 0}.{m.group(3) or 0}") * k
            tol = max(tol, min(0.5 * 10 ** -len(m.group(3)) * k, 0.0127))      # half the last digit, at most half of 0.001 in
            cur = int(m.group(1))                                              # a tool defined in the body also selects it
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        mx, my = re.search(r"X([-+]?[\d.]+)", line), re.search(r"Y([-+]?[\d.]+)", line)
        if routing and line.startswith(("M16", "M17")):
            if (x, y) != start and cur in tools:                  # an open route is a slot; a closed one (board outline) is no hole
                holes.append(round(tools[cur], 4))
            routing = False
        elif line.startswith("M15"):
            routing, start = True, (x, y)
        if mx:
            x = mx.group(1)
        if my:
            y = my.group(1)
        if routing or cur not in tools:
            continue
        if line[0] in "XY":
            holes.append(round(tools[cur], 4))                    # a hit; a G85 slot is one hit line as well
    return {"plated": plated, "holes": holes, "tol": tol}


def parse_gerber_extent(text: str) -> dict | None:
    """{"w": mm, "h": mm} of the drawn extent (centre lines of strokes, arcs included) of one RS-274X file, or None when it has no
    readable format header or no coordinate."""
    fs = re.search(r"%FS([LT])A?X(\d)(\d)Y(\d)(\d)\*%", text)
    mo = re.search(r"%MO(IN|MM)\*%", text)
    if not fs or not mo:
        return None
    zero, dec = fs.group(1), int(fs.group(3))
    digits = int(fs.group(2)) + dec
    unit = 25.4 if mo.group(1) == "IN" else 1.0
    body = re.sub(r"%.*?%", "", text, flags=re.S)
    body = re.sub(r"G04[^*]*\*", "", body)

    def num(s):
        sign = -1 if s.startswith("-") else 1
        d = s.lstrip("+-")
        if zero == "T":
            d = d.ljust(digits, "0")
        return sign * int(d or "0") / (10 ** dec) * unit

    x = y = 0.0
    mode, multi = 1, True
    pts: list[tuple[float, float]] = []
    for st in body.split("*"):
        st = st.strip()
        if not st:
            continue
        if "G75" in st:
            multi = True
        elif "G74" in st:
            multi = False
        for g, v in (("G01", 1), ("G02", 2), ("G03", 3)):
            if g in st:
                mode = v
        mx, my = re.search(r"X([-+]?\d+)", st), re.search(r"Y([-+]?\d+)", st)
        if not (mx or my):
            continue
        x0, y0 = x, y
        if mx:
            x = num(mx.group(1))
        if my:
            y = num(my.group(1))
        if re.search(r"D02", st) and not re.search(r"D0[13]", st):
            continue                                              # a move: part of the drawing only once something is drawn from it
        if re.search(r"D01", st):
            pts.append((x0, y0))
        pts.append((x, y))
        mi, mj = re.search(r"I([-+]?\d+)", st), re.search(r"J([-+]?\d+)", st)
        if mode in (2, 3) and multi and (mi or mj) and re.search(r"D01", st):
            cx = x0 + (num(mi.group(1)) if mi else 0.0)
            cy = y0 + (num(mj.group(1)) if mj else 0.0)
            r = math.hypot(x0 - cx, y0 - cy)
            a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y - cy, x - cx)
            if mode == 3:
                while a1 <= a0:
                    a1 += 2 * math.pi
                sweep = a1 - a0
            else:
                while a1 >= a0:
                    a1 -= 2 * math.pi
                sweep = a1 - a0
            if abs(sweep) < 1e-9:
                sweep = 2 * math.pi if mode == 3 else -2 * math.pi        # a full circle
            for k in range(1, 33):
                a = a0 + sweep * k / 32
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"w": max(xs) - min(xs), "h": max(ys) - min(ys)}


def _fmt_holes(ds) -> str:
    c = collections.Counter(round(d, 2) for d in ds)
    return ", ".join(f"{n} x {d:g} mm" for d, n in sorted(c.items())) or "none"


def drill_problems(files: list[dict], board: dict) -> list[str]:
    """Messages for the drill files (parse_excellon results) that do not carry the board's holes.
    board: {"plated": [dia_mm...], "unplated": [dia_mm...]} from the PcbDoc's drilled pads and vias."""
    out = []
    if not files:
        return out
    tol = max([HOLE_TOL_MM] + [f.get("tol", 0.0) for f in files])
    known = all(f["plated"] is not None for f in files)
    if known:
        sets = [("plated", [d for f in files if f["plated"] for d in f["holes"]], board["plated"]),
                ("non-plated", [d for f in files if not f["plated"] for d in f["holes"]], board["unplated"])]
    else:
        sets = [("", [d for f in files for d in f["holes"]], board["plated"] + board["unplated"])]
    for label, got, want in sets:
        tag = f"{label} " if label else ""
        if len(got) != len(want):
            out.append(f"drill file has {len(got)} {tag}holes, the board has {len(want)}: the files are older than the board or from "
                       f"another PcbDoc; {SAVE_FIRST}")
        elif any(abs(a - b) > tol for a, b in zip(sorted(got), sorted(want))):
            out.append(f"{tag}hole sizes in the drill file ({_fmt_holes(got)}) differ from the board's ({_fmt_holes(want)}): "
                       f"the files are from another version of the board; {SAVE_FIRST}")
    return out


def outline_problems(extents: list[dict], box: tuple[float, float] | None) -> list[str]:
    """Messages when no drawn outline file has the board's width and height (mm). Origin and 90 degree rotation do not matter."""
    if not extents or not box:
        return []
    bw, bh = box
    for e in extents:
        for w, h in ((e["w"], e["h"]), (e["h"], e["w"])):
            if abs(w - bw) <= OUTLINE_TOL_MM and abs(h - bh) <= OUTLINE_TOL_MM:
                return []
    e = extents[0]
    return [f"outline layer is {e['w']:.2f} x {e['h']:.2f} mm, the board is {bw:.2f} x {bh:.2f} mm: the files are older than the "
            f"board or from another PcbDoc; check the outline layer in the Gerber setup, or {SAVE_FIRST}"]


def copper_problems(names: list[str], expected: int | None) -> tuple[list[str], list[str]]:
    """(problems, notes) when the copper layer files (GTL, GBL, inner signal and plane) are not as many as the board's copper
    layers. A two-layer board with only the top file is a note: its bottom layer may just not be plotted."""
    if not expected or len(names) == expected:
        return [], []
    low = {n.lower().rsplit(".", 1)[-1] for n in names}
    if expected == 2 and len(names) == 1 and low == {"gtl"}:
        return [], ["the board has a bottom layer but no bottom copper Gerber: plot Bottom Layer in the Gerber setup, "
                    "or order a 1-layer board"]
    return [f"{len(names)} copper layer file(s) ({', '.join(sorted(names)) or 'none'}), the board has {expected} copper "
            f"layers: {SAVE_FIRST}"], []
