"""Manufacturing-output metrics: Gerber / drill / CPL / BOM / manifest / order note (ACCEPTANCE.md Part B: W19 W29 W32(b) W33 W34 W35 F-I).

Everything is measured from the files in the upload set (project/exports/*_gerbers.zip and friends); the product's own logs and
status flags are never read as proof (A1). No fixture refdes, net name or coordinate appears in a check (A9): objects are found by
rule (every untented via, every non-plated hole, every pad enclosed by the other pads of its part, ...).

Not registered here, because they need the product's behaviour or the DOM (listed in the builder's report): W37, F-I(e), F-I(f).
"""
from __future__ import annotations

import functools
import hashlib
import json
import pathlib
import re

import thresholds as TH
from lib import Result, metric
from oracle import fabfiles, gerber, excellon
from oracle import gerber_geom as geom

import canaries.outputs as can  # synthetic corrected sets and seeded defect injectors

REACH = 1.0           # mm: how far from a hole wall the copper search looks (> every threshold used)


# ------------------------------------------------------------------------------------------------------------ loading
class FabSet:
    def __init__(self, zip_path: pathlib.Path) -> None:
        self.path = zip_path
        layers, others = gerber.load_zip(zip_path)
        self.board = gerber.Board(layers)
        self.holes: list[excellon.Hole] = []
        for nm, data in sorted(others.items()):
            if excellon.is_drill_name(nm):
                self.holes += excellon.parse(nm, data)
        self._nets = None

    @property
    def vias(self) -> list[excellon.Hole]:
        return [h for h in self.holes if h.plated and h.slot_to is None and h.d <= TH.VIA_MAX_HOLE_MM["value"] + 1e-9]

    @property
    def nets(self) -> gerber.Nets:
        if self._nets is None:
            self._nets = gerber.Nets(self.board, self.holes)
        return self._nets

    def sides(self):
        for side in ("top", "bottom"):
            yield side, self.board.get("copper", side), self.board.get("mask", side), self.board.get("paste", side)


_CACHE: dict = {}


def gerber_zip(ctx) -> pathlib.Path | None:
    d = ctx.project / "exports"
    zips = sorted(d.glob("*.zip")) if d.is_dir() else []
    zips = [z for z in zips if re.search(r"gerber", z.name, re.I)] or zips
    return zips[0] if zips else None


def load(ctx) -> FabSet | None:
    z = gerber_zip(ctx)
    if z is None:
        return None
    key = (str(z), z.stat().st_size, hashlib.sha256(z.read_bytes()).hexdigest())
    if key not in _CACHE:
        _CACHE[key] = FabSet(z)
    return _CACHE[key]


def _no_zip(ctx, expected: str) -> Result:
    return Result("fail", measured="no Gerber zip in project/exports", expected=expected,
                  detail="the upload set has no Gerber zip, so nothing can be shown to be right")


def _fmt(points, n=6) -> str:
    return "; ".join(points[:n]) + (f"; ... (+{len(points) - n})" if len(points) > n else "")


def _mask_colour(ctx) -> str:
    try:
        c = json.loads((ctx.project / "project.json").read_text(encoding="utf-8")).get("board", {}).get("mask_colour", "green")
    except (OSError, ValueError):
        c = "green"
    return c if c in TH.MASK_BRIDGE_MIN_MM["value"] else "green"


# ------------------------------------------------------------------------------------------------------------ W29(a) mask webs
def mask_webs(fs: FabSet, limit: float) -> list[dict]:
    """Pairs of mask openings on one side that are separated by a strip of mask narrower than `limit` (and not touching: openings
    closer than 1.2 coordinate steps are one opening)."""
    out = []
    for side, _cu, mk, _p in fs.sides():
        if mk is None:
            continue
        eps = 1.2 * mk.step
        g = mk.grid()
        for p in mk.dark():
            for j in g.near(p.bbox, limit):
                if j <= p.idx or not mk.prims[j].dark:
                    continue
                q = mk.prims[j]
                d = p.dist(q, limit)
                if eps < d < limit:
                    out.append({"side": side, "gap": d, "a": (p.bbox[0] + p.bbox[2]) / 2, "ay": (p.bbox[1] + p.bbox[3]) / 2,
                                "bx": (q.bbox[0] + q.bbox[2]) / 2, "by": (q.bbox[1] + q.bbox[3]) / 2})
    return out


def _web_text(w):
    return f"{w['side']} ({w['a']:.2f},{w['ay']:.2f})-({w['bx']:.2f},{w['by']:.2f}) web {w['gap']:.3f}"


def _w29a_control(ctx):
    _selftest(ctx, "web", w29a, locate=True)
    return can.control_ctx(ctx, "W29a-control")


@metric(id="W29(a)", title="Mask webs narrower than the JLC minimum (from the Gerber mask layers)", root="R4", level="U",
        p0=("P0-3",), control=_w29a_control)
def w29a(ctx):
    fs = load(ctx)
    if fs is None:
        return _no_zip(ctx, "mask webs < minimum = 0")
    colour = _mask_colour(ctx)
    limit = TH.MASK_BRIDGE_MIN_MM["value"][colour]
    webs = mask_webs(fs, limit)
    return Result("pass" if not webs else "fail", measured=len(webs),
                  expected=f"mask webs narrower than {limit} mm ({colour} mask, 1 oz; JLC pcb-capabilities § Solder mask) = 0",
                  detail=f"{len(webs)} webs; narrowest {min((w['gap'] for w in webs), default=0):.3f} mm; " +
                         _fmt([_web_text(w) for w in sorted(webs, key=lambda w: w['gap'])]),
                  evidence=[ctx.ev(fs.path, "Gerber zip (GTS/GBS read)")])


# ------------------------------------------------------------------------------------------------------------ W29(b) bare vias
def _exposed_pieces(cu: gerber.Layer, mk: gerber.Layer, prim: gerber.Prim) -> list[list]:
    """Polygons of the part of `prim` that lies inside a mask opening."""
    pieces = []
    for j in mk.grid().near(prim.bbox):
        op = mk.prims[j]
        if not op.dark:
            continue
        for oa in op.polys:
            for pa in prim.polys:
                if geom.poly_poly_dist(pa, oa, 1e-9) > 0:
                    continue
                if op.kind == "flash":
                    c = geom.clip_convex(pa, oa)
                    if len(c) >= 3 and geom.area(c) > 0:
                        pieces.append(c)
                else:                                      # an opening that is not a flash (rare): count the whole object
                    pieces.append(pa)
    return pieces


def bare_via_violations(fs: FabSet, limit: float) -> list[dict]:
    """Every via whose bare copper (copper inside a mask opening) is closer than `limit` to other exposed copper that is not
    connected to it (nets rebuilt from the Gerbers, see gerber.Nets). One record per (via, side, other object)."""
    out = []
    nets = fs.nets
    for side, cu, mk, _p in fs.sides():
        if cu is None or mk is None:
            continue
        for v in fs.vias:
            vp = next((cu.prims[i] for i in cu.grid().near((v.x, v.y, v.x, v.y))
                       if cu.prims[i].kind == "flash" and cu.prims[i].dark and cu.prims[i].contains((v.x, v.y))
                       and abs(cu.prims[i].x - v.x) < 2 * cu.step + 1e-9), None)
            if vp is None:
                continue
            bare = _exposed_pieces(cu, mk, vp)
            if not bare:
                continue                                   # tented on this side
            vnet = nets.net(cu, vp)
            for i in cu.grid().near(vp.bbox, limit):
                p = cu.prims[i]
                if p is vp or not p.dark or nets.net(cu, p) == vnet:
                    continue
                best = limit
                for ob in _exposed_pieces(cu, mk, p):
                    for vb in bare:
                        best = min(best, geom.poly_poly_dist(vb, ob, best))
                if best < limit:
                    is_via = p.kind == "flash" and any(abs(p.x - w.x) < 2 * cu.step and abs(p.y - w.y) < 2 * cu.step for w in fs.vias)
                    out.append({"via": (v.x, v.y), "side": side, "gap": best,
                                "other": "via" if is_via else ("pad" if p.kind == "flash" else p.kind),
                                "at": ((p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2)})
    return out


def _w29b_control(ctx):
    _selftest(ctx, "via_pad", w29b, locate=True)
    return can.control_ctx(ctx, "W29b-control", legal_open=True)   # one untented via at a legal 0.30 mm from a pad must pass


@metric(id="W29(b)", title="Bare via copper too close to other exposed copper (from the Gerbers)", root="R4", level="U",
        p0=("P0-3",), control=_w29b_control)
def w29b(ctx):
    fs = load(ctx)
    if fs is None:
        return _no_zip(ctx, "bare vias closer than the minimum to other exposed copper = 0")
    limit = TH.BARE_VIA_TO_EXPOSED_COPPER_MM["value"]
    viol = bare_via_violations(fs, limit)
    vias = {v["via"] for v in viol}
    pad_only = {v["via"] for v in viol if v["other"] == "pad"}
    return Result("pass" if not vias else "fail", measured=len(vias),
                  expected=f"untented vias with other-net exposed copper closer than {limit} mm = 0 "
                           "(JLC pcb-capabilities § Via covering options, Untented, HASL)",
                  detail=f"{len(vias)} vias of {len(fs.vias)}; {len(pad_only)} of them near a pad (the ACCEPTANCE figure counts pads "
                         f"only); other exposed copper = pad / bare via / bare track piece, net from the Gerbers. " +
                         _fmt([f"{v['side']} via ({v['via'][0]:.2f},{v['via'][1]:.2f}) {v['gap']:.3f} to {v['other']}" for v in
                               sorted(viol, key=lambda v: v['gap'])]),
                  evidence=[ctx.ev(fs.path, "Gerber zip (copper + mask + drill read)")])


# ------------------------------------------------------------------------------------------------------------ W32(b) NPTH walls
def npth_violations(fs: FabSet, limit: float) -> list[dict]:
    out = []
    for h in fs.holes:
        if h.plated:
            continue
        for ly in fs.board.copper():
            d, q = ly.nearest_material(h.core, h.d / 2, REACH)
            if d is not None and d < limit:
                out.append({"hole": (h.x, h.y), "d": h.d, "layer": ly.side, "gap": max(d, 0.0), "at": q})
    return out


def _w32b_control(ctx):
    _selftest(ctx, "npth", w32b, locate=True)
    return can.control_ctx(ctx, "W32b-control")


@metric(id="W32(b)", title="Copper (pours included) closer than the minimum to a non-plated hole wall", root="R4", level="U",
        p0=("P0-1", "P0-3"), control=_w32b_control)
def w32b(ctx):
    fs = load(ctx)
    if fs is None:
        return _no_zip(ctx, "copper to NPTH wall below the minimum = 0")
    limit = TH.NPTH_TO_COPPER_MM["value"]
    viol = npth_violations(fs, limit)
    n_npth = sum(1 for h in fs.holes if not h.plated)
    return Result("pass" if not viol else "fail", measured=len(viol),
                  expected=f"(non-plated hole, copper layer) pairs with copper closer than {limit} mm to the wall = 0 "
                           "(JLC pcb-capabilities § Traces and spacing, NPTH to track)",
                  detail=f"{len(viol)} pairs over {n_npth} non-plated holes; smallest gap {min((v['gap'] for v in viol), default=0):.3f} mm; " +
                         _fmt([f"{v['layer']} hole ({v['hole'][0]:.2f},{v['hole'][1]:.2f}) d{v['d']:.2f} gap {v['gap']:.3f}" for v in
                               sorted(viol, key=lambda v: v['gap'])]),
                  evidence=[ctx.ev(fs.path, "Gerber zip (copper layers + NPTH drill read)")])


# ------------------------------------------------------------------------------------------------------------ canary self-test
def _near(detail: str, at, tol: float = 1.0) -> bool:
    return any(abs(float(a) - at[0]) <= tol and abs(float(b) - at[1]) <= tol
               for a, b in re.findall(r"\((-?\d+\.\d+),(-?\d+\.\d+)\)", detail))


def _selftest(ctx, defect: str, fn, locate: bool = False) -> None:
    """A5: inject one defect at a seeded random place into a clean synthetic set; the metric must fail (and name the place)."""
    c = can.control_ctx(ctx, f"canary-{defect}", defect)
    r = fn(c)
    if r.status != "fail":
        raise AssertionError(f"canary '{defect}' at {c.canary} was not detected: {r.status} measured={r.measured}")
    if locate and c.canary.get("at") and not _near(r.detail, c.canary["at"]):
        raise AssertionError(f"canary '{defect}' detected but the detail does not name its place {c.canary['at']}: {r.detail[:200]}")


# ------------------------------------------------------------------------------------------------------------ pad ownership
def pad_owners(ctx, fs: FabSet):
    """Copper pads of every part, as Gerber flash objects: ({ref: (side, [Prim])}, [unmatched pad descriptions]) or None.

    A Gerber set carries no pad ownership (this Altium output has no X2 component attributes), so ownership comes from the Altium
    PcbDoc read independently (oracle.pcbdoc, raw olefile; ACCEPTANCE W34 oracle 'U + B + olefile'): each PcbDoc pad (ref, x, y) is
    matched to the copper flash at that position on the part's side, within 0.02 mm. The pad GEOMETRY used by every metric is the
    Gerber flash, never the PcbDoc size. A pad with no flash at its position is returned in the second list (fail-closed).
    A synthetic control has no PcbDoc: `ctx.pad_table` = [(ref, side, x, y)] stands in for it."""
    table = getattr(ctx, "pad_table", None)
    if table is None:
        try:
            from oracle import pcbdoc
        except ImportError:
            return None
        with pcbdoc.PcbDoc(ctx.pcbdoc()) as doc:
            side_of = {c.ref: ("bottom" if c.layer.upper().startswith("B") else "top") for c in doc.components()}
            table = [(p.ref, side_of.get(p.ref, "top"), p.x, p.y) for p in doc.pads() if p.ref]
    out: dict[str, tuple[str, list]] = {}
    missing = []
    for ref, side, x, y in table:
        cu = fs.board.get("copper", side)
        best = None
        if cu is not None:
            for i in cu.grid().near((x, y, x, y), 0.02):
                q = cu.prims[i]
                if q.kind == "flash" and q.dark:
                    d = abs(q.x - x) + abs(q.y - y)
                    if d < 0.02 and (best is None or d < best[0]):
                        best = (d, q)
        if best is None:
            missing.append(f"{ref} pad at ({x:.2f},{y:.2f}) has no copper flash")
        else:
            out.setdefault(ref, (side, []))[1].append(best[1])
    return out, missing


def _padbox(prims) -> tuple:
    return (min(q.bbox[0] for q in prims), min(q.bbox[1] for q in prims), max(q.bbox[2] for q in prims), max(q.bbox[3] for q in prims))


def _need_owners(ctx, fs, expected):
    o = pad_owners(ctx, fs)
    if o is None:
        return None, Result("fail", measured="no pad ownership source", expected=expected,
                            detail="oracle.pcbdoc (the PcbDoc reader) is not available, so pads cannot be tied to designators")
    return o, None


# ------------------------------------------------------------------------------------------------------------ W19 exposed pad paste
def exposed_pads(owned: dict, holes: list) -> list[tuple]:
    """(ref, side, pad Prim) of every exposed / thermal pad: a pad of a part with at least 4 other pads whose centre lies inside the
    bounding box of the other pads, is at least 4 times the median area of the others, and is not a through-hole pad (a plated hole or
    slot centred on it that is at least 40 % of its smaller side, e.g. a connector shield). Found by rule, no refdes (A9)."""
    def through_hole(p):
        w, h = p.size
        cx, cy = (p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2
        return any(abs((h_.x + h_.core[1][0]) / 2 - cx) < 0.05 and abs((h_.y + h_.core[1][1]) / 2 - cy) < 0.05 and h_.d >= 0.4 * min(w, h)
                   for h_ in holes if h_.plated)
    out = []
    for ref, (side, prims) in owned.items():
        if len(prims) < 5:
            continue
        for p in prims:
            others = [q for q in prims if q is not p]
            b = _padbox(others)
            areas = sorted(q.area() for q in others)
            med = areas[len(areas) // 2]
            cx, cy = (p.bbox[0] + p.bbox[2]) / 2, (p.bbox[1] + p.bbox[3]) / 2
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3] and p.area() >= 4 * med and not through_hole(p):
                out.append((ref, side, p))
    return out


def paste_coverage(paste: gerber.Layer | None, pad: gerber.Prim) -> float:
    if paste is None:
        return 0.0
    got = 0.0
    for j in paste.grid().near(pad.bbox):
        op = paste.prims[j]
        if not op.dark:
            continue
        for oa in op.polys:
            for pa in pad.polys:
                c = geom.clip_convex(pa, oa)
                if len(c) >= 3:
                    got += geom.area(c)
    return got / pad.area()


def _w19_control(ctx):
    _selftest(ctx, "ep_full", w19, locate=True)
    return can.control_ctx(ctx, "W19-control")


@metric(id="W19", title="Exposed pad paste coverage outside 50-80 % (from GTP/GBP)", root="R4", level="U",
        p0=(), control=_w19_control)
def w19(ctx):
    lo, hi = TH.EP_PASTE_COVERAGE["value"]
    exp = (f"exposed pads with paste coverage outside {lo:.0%}-{hi:.0%} = 0 (IPC-7525 range, owner decision OD-4, general knowledge; "
           "a datasheet stencil recommendation is not read)")
    fs = load(ctx)
    if fs is None:
        return _no_zip(ctx, exp)
    o, err = _need_owners(ctx, fs, exp)
    if err:
        return err
    owned, missing = o
    bad, seen = [], 0
    for ref, side, pad in exposed_pads(owned, fs.holes):
        seen += 1
        cov = paste_coverage(fs.board.get("paste", side), pad)
        if not (lo - 1e-9 <= cov <= hi + 1e-9):
            bad.append(f"{ref} {side} pad at ({pad.x:.2f},{pad.y:.2f}) {pad.area():.2f} mm2: paste {cov:.0%}")
    return Result("pass" if not bad else "fail", measured=len(bad), expected=exp,
                  detail=f"{seen} exposed pads found; " + (_fmt(bad) if bad else "all inside the range"),
                  evidence=[ctx.ev(fs.path, "Gerber zip (copper + paste read)")])


# ------------------------------------------------------------------------------------------------------------ order manifest helpers
def _manifest(ctx):
    d = ctx.project / "exports"
    fs_ = sorted(d.glob("*manifest*.json")) if d.is_dir() else []
    if not fs_:
        return None, None
    try:
        return fabfiles.read_json(fs_[0]), fs_[0]
    except (OSError, ValueError):
        return None, fs_[0]


# ------------------------------------------------------------------------------------------------------------ W33 DRC open items
def _class_breakdown(man: dict, raw_keys=("board_check",)):
    """Second accepted form (ACCEPTANCE W33 wording): a dict outside the raw record whose keys name the JLC classes
    (reject / accept / cosmetic) with integer counts. Returns {class: n} or None."""
    def walk(v):
        if isinstance(v, dict):
            cls = {k: x for k, x in v.items() if isinstance(x, int) and not isinstance(x, bool) and re.search(r"reject|accept|cosmetic", str(k), re.I)}
            if len(cls) >= 2:
                return cls
            for x in v.values():
                r = walk(x)
                if r:
                    return r
        elif isinstance(v, list):
            for x in v:
                r = walk(x)
                if r:
                    return r
        return None
    return walk({k: v for k, v in man.items() if k not in raw_keys})


def _w33_control(ctx):
    _selftest(ctx, "drc_hidden", w33)
    c2 = can.control_ctx(ctx, "W33-control-class")          # the other accepted form: counts by JLC class
    mp = next((c2.project / "exports").glob("*manifest*.json"))
    man = json.loads(mp.read_text(encoding="utf-8"))
    n = len(man["board_check"]["drc"]["drc"]["violations"])
    man.pop("drc_open_by_rule")
    man["drc_by_class"] = {"JLC-reject": n // 3, "JLC-accept": n - n // 3 - 1, "cosmetic": 1}
    mp.write_text(json.dumps(man), encoding="utf-8")
    r = w33(c2)
    if r.status != "pass":
        raise AssertionError(f"W33 rejects a manifest that states the counts by class: {r.detail[:200]}")
    return can.control_ctx(ctx, "W33-control")


@metric(id="W33", title="Open DRC items that the order manifest does not mention (artifact part)", root="R2", level="B",
        p0=("P0-3",), control=_w33_control)
def w33(ctx):
    exp = "open DRC items whose rule class and count are not stated in the manifest (outside the raw board_check record) = 0"
    man, path = _manifest(ctx)
    if man is None:
        return Result("fail", measured="no manifest", expected=exp, detail="project/exports has no readable *manifest*.json")
    viol = fabfiles.drc_violations(man)
    if viol is None:
        return Result("fail", measured="no DRC record", expected=exp,
                      detail="the manifest holds no DRC result, so nobody can tell whether violations are open",
                      evidence=[ctx.ev(path, "order manifest")])
    text = fabfiles.manifest_text_outside(man)
    by_class = _class_breakdown(man)
    if by_class is not None and viol and sum(by_class.values()) == len(viol):
        return Result("pass", measured=0, expected=exp,
                      detail=f"{len(viol)} open items stated by class in the manifest: {by_class}", evidence=[ctx.ev(path, "order manifest")])
    by_rule: dict[str, int] = {}
    for v in viol:
        r = fabfiles.drc_rule_name(v)
        by_rule[r] = by_rule.get(r, 0) + 1
    unmentioned = {}
    for rule, n in by_rule.items():
        rx = re.escape(rule)
        if not re.search(rf"(?is){rx}.{{0,80}}(?<!\d){n}(?!\d)|(?<!\d){n}(?!\d).{{0,80}}{rx}", text):
            unmentioned[rule] = n
    open_items = sum(unmentioned.values())
    return Result("pass" if not open_items else "fail", measured=open_items, expected=exp,
                  detail=f"{len(viol)} open items in {len(by_rule)} rule classes; {len(unmentioned)} classes not mentioned: " +
                         _fmt([f"{r} x{n}" for r, n in sorted(unmentioned.items(), key=lambda kv: -kv[1])]),
                  evidence=[ctx.ev(path, "order manifest")])


# ------------------------------------------------------------------------------------------------------------ W34 CPL
def _uploaded_cpl(ctx):
    d = ctx.project / "exports"
    cs = [f for f, k in fabfiles.find_cpl_files(ctx.root) if k == "jlc" and f.parent == d]
    return cs[0] if cs else None


_RULE_STATED = re.compile(r"(?is)\bpads?\b.{0,60}(bounding|bbox|box)|(bounding|bbox).{0,60}\bpads?\b|(centre|center)\s+of\s+(all\s+)?(the\s+)?pads")


def _w34a_control(ctx):
    _selftest(ctx, "cpl_origin", w34a, locate=True)
    return can.control_ctx(ctx, "W34a-control")


@metric(id="W34(a)", title="CPL point is the pad bounding-box centre of every part, and the manifest states the rule", root="R4", level="U",
        p0=("P0-3",), control=_w34a_control)
def w34a(ctx):
    tol = TH.DISPLAY_TOL_MM["value"]
    exp = (f"parts whose CPL point differs from the pad bounding-box centre by more than {tol} mm = 0, and the manifest states the "
           "rule (OD-5; JLC cpl-reference-point: geometric centre)")
    fs = load(ctx)
    cpl = _uploaded_cpl(ctx)
    if fs is None:
        return _no_zip(ctx, exp)
    if cpl is None:
        return Result("fail", measured="no CPL csv", expected=exp, detail="project/exports has no JLC CPL (Designator, Mid X, Mid Y)")
    o, err = _need_owners(ctx, fs, exp)
    if err:
        return err
    owned, missing = o
    items = []
    for r in fabfiles.read_cpl_csv(cpl):
        got = owned.get(r.ref)
        if not got:
            items.append(f"{r.ref}: no pads found, cannot be checked")
            continue
        b = _padbox(got[1])
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if abs(cx - r.x) > tol + 1e-9 or abs(cy - r.y) > tol + 1e-9:
            items.append(f"{r.ref} CPL ({r.x:.3f},{r.y:.3f}) pad-box centre ({cx:.3f},{cy:.3f})")
    items += [f"pad without copper flash: {m}" for m in missing]
    man, mpath = _manifest(ctx)
    stated = bool(man is not None and _RULE_STATED.search(fabfiles.manifest_text_outside(man)))
    if not stated:
        items.append("the manifest does not state the CPL reference-point rule")
    return Result("pass" if not items else "fail", measured=len(items), expected=exp,
                  detail=f"{len(items)} items; " + _fmt(items) + "; pad ownership from the PcbDoc, pad geometry from the Gerber flashes",
                  evidence=[ctx.ev(cpl, "uploaded CPL"), ctx.ev(fs.path, "Gerber zip (copper flashes)")])


def _w34c_control(ctx):
    _selftest(ctx, "cpl_check_wrong", w34c)
    return can.control_ctx(ctx, "W34c-control")


@metric(id="W34(c)", title="outputs-check validates the uploaded CPL, by sha256", root="R4", level="B", p0=("P0-3",),
        control=_w34c_control)
def w34c(ctx):
    exp = "outputs-check's CPL entry is exactly the uploaded exports CPL file and carries its sha256: mismatches = 0"
    cpl = _uploaded_cpl(ctx)
    p = ctx.project / "outputs-check.json"
    if cpl is None or not p.is_file():
        return Result("fail", measured="missing", expected=exp, detail="no uploaded CPL, or no outputs-check.json")
    oc = fabfiles.read_json(p)
    ent = [e for e in oc.get("expected", []) if e.get("kind") == "cpl"]
    found = [f for e in ent for f in e.get("found", [])]
    names = [f["name"] if isinstance(f, dict) else str(f) for f in found]
    ev = [ctx.ev(p, "outputs-check"), ctx.ev(cpl, "uploaded CPL")]
    if names != [cpl.name]:
        return Result("fail", measured=1, expected=exp, detail=f"outputs-check validated {names or 'no CPL'}, the uploaded file is {cpl.name}",
                      evidence=ev)
    want = hashlib.sha256(cpl.read_bytes()).hexdigest()
    got = (found[0].get("sha256") if isinstance(found[0], dict) else None) or next((e.get("sha256") for e in ent if e.get("sha256")), None)
    if got != want:
        return Result("fail", measured=1, expected=exp,
                      detail=f"outputs-check names {cpl.name} but its sha256 is {'absent' if not got else 'wrong'}", evidence=ev)
    return Result("pass", measured=0, expected=exp, detail="the validated CPL is the uploaded one (sha256 equal)", evidence=ev)


# ------------------------------------------------------------------------------------------------------------ W35 order note vs Gerbers
def via_openings(fs: FabSet) -> tuple[int, int]:
    """(number of (via, side) pairs with a mask opening over the via centre, number of vias)."""
    n = 0
    for side, _cu, mk, _p in fs.sides():
        if mk is None:
            continue
        n += sum(1 for v in fs.vias if mk.covered((v.x, v.y)))
    return n, len(fs.vias)


def _w35_control(ctx):
    _selftest(ctx, "tent_flip", w35)
    _selftest(ctx, "note_missing", w35)
    return can.control_ctx(ctx, "W35-control")


@metric(id="W35", title="Order note fab statements (via tenting, layer count) contradict the Gerbers", root="R1", level="B",
        p0=("P0-3",), control=_w35_control)
def w35(ctx):
    exp = ("contradictions between the order note and the Gerbers = 0 (tented <=> no via opening in GTS/GBS; layer count = copper "
           "layers); a tenting statement is required")
    fs = load(ctx)
    if fs is None:
        return _no_zip(ctx, exp)
    text, path, source = fabfiles.order_note(ctx.root)
    if text is None:
        return Result("fail", measured=1, expected=exp, detail="no order note: no exported note and no 'order note' section in notes.md")
    opens, nvia = via_openings(fs)
    bad = []
    ts = fabfiles.tenting_statements(text)
    if not ts:
        bad.append("the note makes no statement about via tenting")
    for ln, kind in ts:
        if kind == "tented" and opens:
            bad.append(f"says tented but {opens} via openings in GTS/GBS ({nvia} vias): \"{ln[:60]}\"")
        if kind == "untented" and not opens:
            bad.append(f"says untented but there is no via opening in GTS/GBS: \"{ln[:60]}\"")
    ncu = len(fs.board.copper())
    for ln, n in fabfiles.layer_count_statements(text):
        if n != ncu:
            bad.append(f"says {n} layers but the Gerbers have {ncu} copper layers: \"{ln[:60]}\"")
    return Result("pass" if not bad else "fail", measured=len(bad), expected=exp,
                  detail=f"note from {source}; {len(bad)} contradictions; " + _fmt(bad),
                  evidence=[ctx.ev(path, f"order note ({source})"), ctx.ev(fs.path, "Gerber zip (mask + copper read)")])


# ------------------------------------------------------------------------------------------------------------ F-I
def _fia_control(ctx):
    _selftest(ctx, "note_missing", fia)
    return can.control_ctx(ctx, "FIa-control")


@metric(id="F-I(a)", title="The export contains an order note", root="R1", level="B", p0=(), control=_fia_control)
def fia(ctx):
    notes = fabfiles.exported_order_notes(ctx.root)
    return Result("pass" if notes else "fail", measured=len(notes), expected="order-note / README files in project/exports >= 1",
                  detail=", ".join(n.name for n in notes) or "project/exports holds no order note or README",
                  evidence=[ctx.ev(n, "order note") for n in notes])


def _fib_control(ctx):
    _selftest(ctx, "stack_missing", fib)
    return can.control_ctx(ctx, "FIb-control")


@metric(id="F-I(b)", title="The manifest has a stack field", root="R1", level="B", p0=(), control=_fib_control)
def fib(ctx):
    man, path = _manifest(ctx)
    st = man.get("stack") if isinstance(man, dict) else None
    ok = bool(st)
    return Result("pass" if ok else "fail", measured=1 if ok else 0,
                  expected="manifest has a non-empty `stack` field = 1 (equality to Board6 is W27's)",
                  detail=f"stack = {st!r}" if ok else "the manifest has no `stack` field",
                  evidence=[ctx.ev(path, "order manifest")] if path else [])


def _fic_control(ctx):
    _selftest(ctx, "extra_cpl", fic)
    return can.control_ctx(ctx, "FIc-control")


@metric(id="F-I(c)", title="Exactly one CPL in the upload set", root="R1", level="B", p0=(), control=_fic_control)
def fic(ctx):
    found = fabfiles.find_cpl_files(ctx.root)
    return Result("pass" if len(found) == 1 else "fail", measured=len(found),
                  expected="pick-and-place files in the upload folders = 1",
                  detail="; ".join(str(f.relative_to(ctx.root)) for f, _k in found) or "no CPL found",
                  evidence=[ctx.ev(f, "CPL") for f, _k in found])


def _fid_control(ctx):
    _selftest(ctx, "bom_split", fid)
    return can.control_ctx(ctx, "FId-control")


@metric(id="F-I(d)", title="BOM lines sharing LCSC code, value and footprint are merged or flagged", root="R1", level="B", p0=(),
        control=_fid_control)
def fid(ctx):
    d = ctx.project / "exports"
    boms = sorted(d.glob("*BOM*.csv")) if d.is_dir() else []
    if not boms:
        return Result("fail", measured="no BOM", expected="unmerged unflagged duplicate BOM groups = 0", detail="project/exports has no BOM csv")
    man, _p = _manifest(ctx)
    flagged_text = fabfiles.manifest_text_outside(man) if man else ""
    groups = fabfiles.duplicate_lcsc_groups(fabfiles.read_bom_jlc(boms[0]))
    def flagged(g):      # the manifest must name the code AND every designator of the group
        return g[0].lcsc in flagged_text and all(re.search(rf"(?<![A-Za-z0-9]){re.escape(r)}(?![A-Za-z0-9])", flagged_text)
                                                 for ln in g for r in ln.refs)
    bad = [g for g in groups if not flagged(g)]
    return Result("pass" if not bad else "fail", measured=len(bad),
                  expected="BOM groups (same LCSC, value, footprint) neither merged nor flagged in the manifest = 0",
                  detail=_fmt([f"{g[0].lcsc} {g[0].comment}: {' + '.join(','.join(x.refs) for x in g)}" for g in bad]) or "none",
                  evidence=[ctx.ev(boms[0], "BOM")])
