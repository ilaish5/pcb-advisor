"""Board metrics read from the PcbDoc and PcbLib (oracle/pcbdoc.py, raw olefile). One @metric per catalogue id or lettered part.

Every check finds its objects by rule (geometry, nets, pad counts, library data), never by a fixture designator, net name or
coordinate (A9). Thresholds come from thresholds.py only (A7). Each metric has a control builder (canaries/board.py) that makes a
corrected copy on which the same check passes, and a seeded canary that injects one random defect into that copy and requires the
check to fail on exactly that object; a control that cannot be shown to fail on its canary raises, so it never reports a green.
"""
from __future__ import annotations

import json
import math

from lib import Result, metric
import thresholds as TH
from oracle import pcbdoc as P
from canaries import board as CB

COURTYARD_LAYER = 71    # Mechanical 15: the Altium IPC-library courtyard layer (ACCEPTANCE.md W17)


def _tv(t):
    return t["value"]


def _with_canary(build, inject, check):
    """Control builder: `build(ctx)` makes the corrected copy; `inject(control_ctx)` returns (defect_ctx, token) with one random
    defect (ctx.rng); the check must FAIL on the defect and name `token`. Otherwise the control is an error, not a pass."""
    def control(ctx):
        c = build(ctx)
        bad, token = inject(c)
        r = check(bad)
        if r.status != "fail" or token not in json.dumps(r.measured, default=str):
            raise AssertionError(f"canary not caught: injected {token!r}, check says {r.status} {r.measured!r}")
        return c
    return control


def _pcbs(ctx):
    libs = sorted((ctx.altium / "Library").glob("*.PcbLib"))
    if not libs:
        raise FileNotFoundError(f"no PcbLib under {ctx.altium / 'Library'}")
    return libs


# ======================================================================================================================== W27
JLC = _tv(TH.JLC04161H_7628)


def _jlc_stack():
    return [{"kind": "copper", "cu_mm": JLC["outer_cu_mil"] * P.MIL_MM},
            {"kind": "dielectric", "diel_mm": JLC["prepreg_mm"], "er": JLC["prepreg_er"]},
            {"kind": "copper", "cu_mm": JLC["inner_cu_mil"] * P.MIL_MM},
            {"kind": "dielectric", "diel_mm": JLC["core_mm"], "er": JLC["core_er"]},
            {"kind": "copper", "cu_mm": JLC["inner_cu_mil"] * P.MIL_MM},
            {"kind": "dielectric", "diel_mm": JLC["prepreg_mm"], "er": JLC["prepreg_er"]},
            {"kind": "copper", "cu_mm": JLC["outer_cu_mil"] * P.MIL_MM}]


def _stack_diffs(doc: P.PcbDoc):
    """Differences between the PcbDoc stack and JLC04161H-7628, or None when the board is not 4-layer."""
    rows = doc.stack()
    if sum(1 for r in rows if r["kind"] == "copper") != 4:
        return None
    want, out = _jlc_stack(), []
    if len(rows) != len(want):
        return [f"stack has {len(rows)} rows between the outer coppers, JLC04161H has {len(want)}"]
    tol, er_tol = _tv(TH.STACK_TOL_MM), _tv(TH.STACK_ER_TOL)
    di = 0
    for r, w in zip(rows, want):
        if r["kind"] != w["kind"]:
            out.append(f"{r['name']}: is {r['kind']}, JLC04161H has {w['kind']}")
        elif w["kind"] == "copper":
            if r["cop_mm"] is None or abs(r["cop_mm"] - w["cu_mm"]) > tol:
                out.append(f"{r['name']}: copper {r['cop_mm'] and round(r['cop_mm'], 4)} mm, want {round(w['cu_mm'], 4)} mm")
        else:
            di += 1
            if r["diel_mm"] is None or abs(r["diel_mm"] - w["diel_mm"]) > tol or r["er"] is None or abs(r["er"] - w["er"]) > er_tol:
                out.append(f"{r['name']} (dielectric {di}): {r['diel_mm'] and round(r['diel_mm'], 4)} mm Er {r['er']}, "
                           f"want {w['diel_mm']} mm Er {w['er']}")
    return out


def _w27_build(ctx):
    doc = P.PcbDoc(ctx.pcbdoc())
    upd = CB.stack_updates(doc.stack(), doc.stack_v8(), _jlc_stack())
    doc.close()
    return CB.with_board_updates(ctx, "W27-control", upd)


def _w27_inject(c):
    doc = P.PcbDoc(c.pcbdoc())
    rows = [r for r in doc.stack() if r["kind"] == "dielectric"]
    r = c.rng.choice(rows)
    doc.close()
    pre = f"V9_STACK_LAYER{r['n']}_"
    if c.rng.random() < 0.5:
        upd = {pre + "DIELHEIGHT": CB.mil_text(r["diel_mm"] + c.rng.choice([-1, 1]) * c.rng.uniform(0.02, 0.08))}
    else:
        upd = {pre + "DIELCONST": f"{r['er'] + c.rng.choice([-1, 1]) * c.rng.uniform(0.2, 0.6):.2f}"}
    return CB.with_board_updates(c, "W27-canary", upd), r["name"]


@metric(id="W27", title="Layer stack equals JLC04161H-7628 (dielectric height, Er, copper)", root="R1", level="L", p0=("P0-3",),
        control=_with_canary(_w27_build, _w27_inject, lambda c: w27(c)))
def w27(ctx):
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        diffs = _stack_diffs(doc)
    ev = [ctx.ev(f, "Board6 stack (V9_STACK_LAYER*)")]
    if diffs is None:
        return Result("not_run", detail="not a 4-layer board: JLC04161H-7628 does not apply", evidence=ev)
    return Result("pass" if not diffs else "fail", measured=diffs, expected="layers differing from JLC04161H-7628 = 0", evidence=ev)


# ======================================================================================================================== W32(a)
_RULE_SKIP = {"SELECTION", "UNIQUEID", "COMMENT"}


def _same_value(a: str, b: str) -> bool:
    try:
        return abs(P.mil_value(a) - P.mil_value(b)) <= _tv(TH.STACK_TOL_MM)
    except ValueError:
        return a.strip().lower() == b.strip().lower()


def _rules_json(ctx):
    f = ctx.project / "rules.json"
    return f, json.loads(f.read_text(encoding="utf-8"))


@metric(id="W32(a)", title="Every rule in rules.json is in Rules6 (name, kind, scope, values)", root="R4", level="L", p0=("P0-1", "P0-3"),
        control=lambda ctx: _w32a_control(ctx))
def w32a(ctx):
    rf, wanted = _rules_json(ctx)
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        have = {r.get("NAME"): r for r in doc.rules()}
    out = []
    for w in wanted:
        got = have.get(w["name"])
        if got is None:
            out.append(f"missing: {w['name']} ({w['kind']})")
            continue
        for k, v in (w.get("attributes") or {}).items():
            if k not in _RULE_SKIP and not _same_value(str(v), got.get(k, "")):
                out.append(f"differs: {w['name']} {k} want {v!r} got {got.get(k)!r}")
    return Result("pass" if not out else "fail", measured=out, expected="rules of rules.json missing or different in Rules6 = 0",
                  evidence=[ctx.ev(rf, "rules.json"), ctx.ev(f, "Rules6")])


def _w32a_extra(ctx, mutate=None):
    _, wanted = _rules_json(ctx)
    attrs = []
    for w in wanted:
        a = dict(w["attributes"])
        if mutate and w["name"] == mutate[0]:
            a[mutate[1]] = mutate[2]
        attrs.append(a)
    return attrs


def _w32a_control(ctx):
    _, wanted = _rules_json(ctx)
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        have = {r.get("NAME") for r in doc.rules()}
    # the control adds the rules the document lacks, with exactly the attributes rules.json gives them
    extra = [dict(w["attributes"]) for w in wanted if w["name"] not in have]
    if not extra:
        raise AssertionError("the PcbDoc already holds every rule; the control has nothing to correct")
    copy = ("project/rules.json",)
    c = CB.with_rules(ctx, "W32a-control", extra, copy=copy)
    # canary: one rule added with a random wrong value must be named as 'differs'
    pick = ctx.rng.choice(extra)
    key = next(k for k in pick if k in ("CLEARANCE", "GAP", "MINLIMIT", "MAXLIMIT", "PREFEREDWIDTH", "WIDTH"))
    wrong = dict(pick, **{key: f"{ctx.rng.uniform(31, 90):.3f}mil"})
    bad = CB.with_rules(ctx, "W32a-canary", [wrong] + [e for e in extra if e is not pick], copy=copy)
    r = w32a(bad)
    if r.status != "fail" or pick["NAME"] not in json.dumps(r.measured):
        raise AssertionError(f"canary not caught: {pick['NAME']} {key} -> {r.status} {r.measured}")
    return c


# ======================================================================================================================== W17
def _components(segs):
    """Connected groups of courtyard segments [(x1, y1, x2, y2)]; a group is closed when every node has an even degree."""
    snap = lambda x, y: (round(x * 200), round(y * 200))     # 0.005 mm grid
    parent: dict = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    deg: dict = {}
    for x1, y1, x2, y2 in segs:
        a, b = snap(x1, y1), snap(x2, y2)
        parent[find(a)] = find(b)
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    groups: dict = {}
    for x1, y1, x2, y2 in segs:
        g = groups.setdefault(find(snap(x1, y1)), {"pts": [], "nodes": set()})
        g["pts"] += [(x1, y1), (x2, y2)]
        g["nodes"] |= {snap(x1, y1), snap(x2, y2)}
    for g in groups.values():
        g["closed"] = all(deg[n] % 2 == 0 and deg[n] >= 2 for n in g["nodes"])
        xs, ys = [p[0] for p in g["pts"]], [p[1] for p in g["pts"]]
        g["bbox"] = (min(xs), min(ys), max(xs), max(ys))
    return list(groups.values())


def courtyard_shortfall(fp: P.Footprint, layer: int = COURTYARD_LAYER):
    """(problem text or None, margin mm) of a footprint's courtyard: the largest closed outline on `layer` must enclose every pad
    copper extent and every 3D body by the IPC-7351B excess."""
    segs = [(t.x1, t.y1, t.x2, t.y2) for t in fp.tracks if t.layer == layer]
    for a in fp.arcs:
        if a.layer == layer:
            pts = a.points()
            segs.append((*pts[0], *pts[-1]))
    if not segs:
        return "no outline on the courtyard layer", None
    groups = _components(segs)
    g = max(groups, key=lambda g: (g["bbox"][2] - g["bbox"][0]) * (g["bbox"][3] - g["bbox"][1]))
    if not g["closed"]:
        return "the outline is not closed", None
    need = []
    for p in fp.pads:
        need.append(p.extent())
    for b in fp.bodies:
        bb = b.bbox()
        if bb is None:
            raise ValueError(f"{fp.name}: 3D body with no readable outline")
        need.append(bb)
    x0, y0 = min(n[0] for n in need), min(n[1] for n in need)
    x1, y1 = max(n[2] for n in need), max(n[3] for n in need)
    bx0, by0, bx1, by1 = g["bbox"]
    margin = min(x0 - bx0, y0 - by0, bx1 - x1, by1 - y1)
    if margin < _tv(TH.COURTYARD_EXCESS_MM) - _tv(TH.GEOM_TOL_MM):
        return f"courtyard excess {margin:.2f} mm < {_tv(TH.COURTYARD_EXCESS_MM)} mm", margin
    return None, margin


def _real_footprints(path):
    return [fp for fp in P.read_pcblib(path) if any(p.plated for p in fp.pads)]


def _w17_build(ctx):
    c = CB.sparse_root(ctx, "W17-control")
    for lib in _pcbs(ctx):
        CB.rewrite_courtyards(lib, c.altium / "Library" / lib.name, COURTYARD_LAYER, _tv(TH.COURTYARD_EXCESS_MM) + 0.05)
    return c


def _w17_inject(c):
    libs = _pcbs(c)
    fps = [(lib, fp) for lib in libs for fp in _real_footprints(lib)]
    lib, fp = c.rng.choice(fps)
    bad = CB.sparse_root(c, "W17-canary")
    for l2 in libs:
        shrink = {fp.name: 0.2} if l2.name == lib.name else {}
        CB.rewrite_courtyards(l2, bad.altium / "Library" / l2.name, COURTYARD_LAYER, _tv(TH.COURTYARD_EXCESS_MM) + 0.05, shrink)
    return bad, fp.name


@metric(id="W17", title="Every footprint has a closed courtyard enclosing pads and body plus the IPC-7351B excess", root="R4", level="L",
        control=_with_canary(_w17_build, _w17_inject, lambda c: w17(c)))
def w17(ctx):
    failing, n, ev = [], 0, []
    for lib in _pcbs(ctx):
        ev.append(ctx.ev(lib, "PcbLib"))
        for fp in _real_footprints(lib):
            n += 1
            why, _ = courtyard_shortfall(fp)
            if why:
                failing.append(f"{fp.name}: {why}")
    if n == 0:
        return Result("error", detail="no footprint with a plated pad in the library", evidence=ev)
    return Result("pass" if not failing else "fail", measured=failing, expected="footprints without a courtyard = 0",
                  detail=f"{len(failing)}/{n} footprints", evidence=ev)


# ======================================================================================================================== W31
import re

_XTAL_WORDS = re.compile(r"crystal|xtal|resonator|oscillator", re.I)


def find_crystals(ctx, doc: P.PcbDoc):
    """Crystal components by rule: the BOM line's role, or the footprint pattern, names a crystal / resonator / oscillator.
    Returns [(Component, [pad, ...])]."""
    bom = json.loads((ctx.project / "bom.json").read_text(encoding="utf-8"))
    refs = {ref for line in bom if _XTAL_WORDS.search(f"{line.get('role') or ''} {line.get('package') or ''}") for ref in line.get("refs") or []}
    out = []
    for c in doc.components():
        if c.ref in refs or _XTAL_WORDS.search(c.pattern):
            pads = [p for p in doc.pads() if p.comp == c.index]
            if len(pads) < 2:
                raise ValueError(f"{c.ref}: a crystal with {len(pads)} pads")
            out.append((c, pads))
    return out


def _crystal_geometry(ctx, doc):
    """Per crystal: component, pads, own (non-ground) nets, courtyard rectangle (pads and body plus the IPC-7351B excess), and the
    copper layers the rule looks at (its outer layer and the adjacent inner layer, from the stack order)."""
    gnd, m = P.ground_nets(doc), _tv(TH.COURTYARD_EXCESS_MM)
    out = []
    for c, pads in find_crystals(ctx, doc):
        x0, y0, x1, y1 = P.comp_bbox(doc, c.index)
        out.append({"c": c, "pads": pads, "own": {p.net for p in pads if p.net} - gnd, "rect": (x0 - m, y0 - m, x1 + m, y1 + m),
                    "layers": {1 if c.layer.upper().startswith("T") else 32, P.adjacent_inner(doc, c.layer)} - {None}})
    return out


def _foreign_in(doc, g, gnd, layers):
    """Nets of tracks (on `layers`) and vias that are not the crystal's own nets or ground and touch its courtyard rectangle."""
    rect, found = g["rect"], set()
    for t in doc.tracks():
        if t.layer in layers and t.comp is None and t.net not in g["own"] and t.net not in gnd                 and P.seg_hits_rect(t.x1, t.y1, t.x2, t.y2, t.width / 2, rect):
            found.add(t.net or "(no net)")
    for v in doc.vias():
        if v.net not in g["own"] and v.net not in gnd and rect[0] - v.dia / 2 <= v.x <= rect[2] + v.dia / 2                 and rect[1] - v.dia / 2 <= v.y <= rect[3] + v.dia / 2:
            found.add(v.net or "(no net)")
    return found


def _crystal_findings(ctx, doc):
    """([(kind, text)], n_foreign_on_any_layer): kind foreign | via | long | unrouted for every crystal on the board."""
    gnd = P.ground_nets(doc)
    max_len, max_vias = _tv(TH.XTAL_MAX_TRACK_MM), _tv(TH.XTAL_VIAS_ON_PATH)
    all_layers = set(range(1, 33)) | set(range(39, 55))
    out, wide = [], 0
    for g in _crystal_geometry(ctx, doc):
        c, pads = g["c"], g["pads"]
        wide += len(_foreign_in(doc, g, gnd, all_layers))
        out += [("foreign", f"{c.ref}: foreign net {n} in the courtyard") for n in sorted(_foreign_in(doc, g, gnd, g["layers"]))]
        for net in sorted(g["own"]):
            nv = sum(1 for v in doc.vias() if v.net == net)
            if nv > max_vias:
                out.append(("via", f"{c.ref}: {nv} vias on {net}"))
            mcu = [p for p in doc.pads() if p.net == net and p.comp not in (None, c.index)]
            mine = [p for p in pads if p.net == net]
            if not mcu or not mine:
                continue
            ic = max(mcu, key=lambda p: sum(1 for q in doc.pads() if q.comp == p.comp))      # the part with the most pins
            best = [L for L in (P.route_length(doc, net, ic, q) for q in mine) if L is not None]
            if not best:
                out.append(("unrouted", f"{c.ref}: {net} is not routed from {ic.ref} pin {ic.name}"))
            elif min(best) > max_len:
                out.append(("long", f"{c.ref}: {net} track {min(best):.1f} mm from {ic.ref} pin {ic.name} > {max_len} mm"))
    return out, wide


@metric(id="W31", title="Crystal layout: no foreign copper under it, no vias on its path, track length within the limit", root="R3",
        level="L", control=lambda ctx: _w31_control(ctx))
def w31(ctx):
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        found, wide = _crystal_findings(ctx, doc)
        n = len(find_crystals(ctx, doc))
    if n == 0:
        return Result("error", detail="no crystal found on the board", evidence=[ctx.ev(f, "PcbDoc")])
    counts = {k: sum(1 for kk, _ in found if kk == k) for k in ("foreign", "via", "long", "unrouted")}
    return Result("pass" if not found else "fail", measured=[t for _, t in found], expected="crystal violations = 0",
                  detail=", ".join(f"{k} {v}" for k, v in counts.items()) + f" (foreign nets on any copper layer: {wide})", evidence=[ctx.ev(f, "Tracks6, Vias6, Pads6"),
                                                                                         ctx.ev(ctx.project / "bom.json", "BOM roles")])


def _w31_control(ctx):
    """SYNTHETIC control: the fixture PcbDoc with (1) every track and via of a foreign net removed from each crystal courtyard (all
    copper layers) and (2) every track and via on a crystal's own nets replaced by one straight track from the IC pad to the crystal
    pad on the crystal's outer layer. It is not a routable board; it is the smallest edit that makes every W31 rule hold. The
    canary then draws one random foreign-net track through a random crystal courtyard on a rule layer: W31 must fail naming it."""
    copy = ("project/bom.json",)
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        gnd = P.ground_nets(doc)
        geo = _crystal_geometry(ctx, doc)
        own_all = set().union(*(g["own"] for g in geo))
        nets = doc.nets()
        adds = []
        for g in geo:
            for net in sorted(g["own"]):
                mcu = [p for p in doc.pads() if p.net == net and p.comp not in (None, g["c"].index)]
                mine = [p for p in g["pads"] if p.net == net]
                ic = max(mcu, key=lambda p: sum(1 for q in doc.pads() if q.comp == p.comp))
                adds.append((1 if g["c"].layer.upper().startswith("T") else 32, net, ic.x, ic.y, mine[0].x, mine[0].y, 0.2))

    def hits_any(x0, y0, x1, y1, half):
        return any(P.seg_hits_rect(x0, y0, x1, y1, half, g["rect"]) for g in geo)

    def near_any(v):
        return any(g["rect"][0] - v.dia / 2 <= v.x <= g["rect"][2] + v.dia / 2 and g["rect"][1] - v.dia / 2 <= v.y <= g["rect"][3] + v.dia / 2
                   for g in geo)
    c = CB.rewrite_routing(
        ctx, "W31-control",
        keep_track=lambda t: not (t.net in own_all or (P.is_copper(t.layer) and t.comp is None and t.net not in gnd
                                                       and hits_any(t.x1, t.y1, t.x2, t.y2, t.width / 2))),
        keep_via=lambda v: not (v.net in own_all or (v.net not in gnd and near_any(v))),
        add_tracks=adds, copy=copy)
    # canary
    g = ctx.rng.choice(geo)
    foreign = [n for n in nets if n and n not in g["own"] and n not in gnd and n.upper() != "NC"]
    net = ctx.rng.choice(foreign)
    layer = ctx.rng.choice(sorted(g["layers"]))
    x0, y0, x1, y1 = g["rect"]
    ym = (y0 + y1) / 2
    bad = CB.rewrite_routing(c, "W31-canary", add_tracks=[(layer, net, x0 - 0.5, ym, x1 + 0.5, ym, 0.2)], copy=copy)
    r = w31(bad)
    if r.status != "fail" or f"{g['c'].ref}: foreign net {net} " not in json.dumps(r.measured):
        raise AssertionError(f"canary not caught: {g['c'].ref} {net} layer {layer}: {r.status} {r.measured}")
    return c
