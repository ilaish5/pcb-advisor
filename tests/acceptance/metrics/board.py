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


# ======================================================================================================================== W28
def _default_width(doc: P.PcbDoc) -> float:
    """The board's default track width (mm): the preferred width of the highest-priority enabled Width rule whose scope is All."""
    rules = [r for r in doc.rules() if r.get("RULEKIND") == "Width" and r.get("ENABLED", "TRUE").upper() == "TRUE"
             and r.get("SCOPE1EXPRESSION", "").strip().lower() == "all"]
    if not rules:
        raise ValueError("no enabled Width rule with scope All: the default width is unknown")
    r = min(rules, key=lambda r: int(r.get("PRIORITY", "99") or 99))
    return P.mil_value(r["PREFEREDWIDTH"])


def _min_widths(doc: P.PcbDoc) -> dict[str, float]:
    w: dict[str, float] = {}
    for t in doc.tracks():
        if P.is_copper(t.layer) and t.net and t.comp is None:
            w[t.net] = min(w.get(t.net, 1e9), t.width)
    return w


def _w28_build(ctx):
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        base, narrow = _default_width(doc), {n: w for n, w in _min_widths(doc).items()}
    fix = {n: base for n, w in narrow.items() if w < base - _tv(TH.GEOM_TOL_MM)}
    if not fix:
        raise AssertionError("no net is narrower than the default width: nothing for the control to correct")
    return CB.rewrite_routing(ctx, "W28-control", set_width=fix)


def _w28_inject(c):
    with P.PcbDoc(c.pcbdoc()) as doc:
        base, nets = _default_width(doc), sorted(_min_widths(doc))
    net = c.rng.choice(nets)
    return CB.rewrite_routing(c, "W28-canary", set_width={net: round(base * c.rng.uniform(0.4, 0.8), 4)}), net


@metric(id="W28", title="No net is drawn narrower than the width it gets with no current entered (baseline part of W28)", root="R3",
        level="L", control=_with_canary(_w28_build, _w28_inject, lambda c: w28(c)))
def w28(ctx):
    """Baseline half of W28 only: the minimum drawn width of every net (Tracks6, copper, not component-owned) must be at least the
    board's default width (the All-scope Width rule's preferred width). The IPC-2221 half (width for the entered current, rise and
    copper weight) is NOT measured here: shared/reference has no cited IPC-2221 width formula, so no value is invented (contract rule 7)."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        base, widths = _default_width(doc), _min_widths(doc)
    if not widths:
        return Result("error", detail="no routed net in the PcbDoc", evidence=[ctx.ev(f, "Tracks6, Rules6")])
    tol = _tv(TH.GEOM_TOL_MM)
    bad = [f"{n}: {w:.4f} mm < default {base:.4f} mm" for n, w in sorted(widths.items()) if w < base - tol]
    return Result("pass" if not bad else "fail", measured=bad, expected="nets narrower than the no-current width = 0",
                  detail=f"{len(bad)}/{len(widths)} nets", evidence=[ctx.ev(f, "Tracks6, Rules6")])


# ======================================================================================================================== W25(a)
import datetime as dt
import pathlib


def _snapshots(ctx):
    """[(time, path)] of every PcbDoc state kept: each `.advisor-backup/<YYYYMMDD-HHMMSS>/*.PcbDoc` and the final document (time max)."""
    out = []
    for d in sorted((ctx.altium / ".advisor-backup").glob("*")) if (ctx.altium / ".advisor-backup").is_dir() else []:
        docs = sorted(d.glob("*.PcbDoc"))
        if docs:
            out.append((dt.datetime.strptime(d.name, "%Y%m%d-%H%M%S"), docs[0]))
    out.append((dt.datetime.max, ctx.pcbdoc()))
    return out


def _ko_requirements(ctx):
    """(requirements, deleted_at): the keep-out items of the latest idea version that has any, and the time of the first later
    version that has none (None when they still exist)."""
    f = ctx.project / "idea-versions.json"
    vs = sorted(json.loads(f.read_text(encoding="utf-8")), key=lambda v: v["n"])
    items = lambda v: ((v.get("idea") or {}).get("constraints") or {}).get("items") or []
    has = [i for i, v in enumerate(vs) if any(it.get("kind") == "keepout" for it in items(v))]
    if not has:
        return [], None, f
    last = has[-1]
    reqs = [it for it in items(vs[last]) if it.get("kind") == "keepout"]
    gone = dt.datetime.fromisoformat(vs[last + 1]["ts"]) if last + 1 < len(vs) else None
    return reqs, gone, f


def _snapshot_for(ctx, gone):
    """The latest PcbDoc state at or before the moment the requirement was deleted (the final document when it was never deleted)."""
    snaps = [s for s in _snapshots(ctx) if gone is None or s[0] <= gone]
    return snaps[-1] if snaps else None


def _origin(doc):
    o = doc.outline()
    return min(p[0] for p in o), min(p[1] for p in o)


def _w25_problems(doc, reqs):
    ox, oy = _origin(doc)
    tol = _tv(TH.GEOM_TOL_MM)
    regs = [r for r in doc.regions() if r.points]
    out = []
    for q in reqs:
        a, b, c, d = q["rect_mm"]
        rect = (ox + a, oy + b, ox + c, oy + d)
        ov = lambda x0, y0, x1, y1: x0 < rect[2] - tol and x1 > rect[0] + tol and y0 < rect[3] - tol and y1 > rect[1] + tol
        bb = lambda pts: (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        ko = [bb(r.points) for r in regs if r.keepout and ov(*bb(r.points))]
        ko_pts = [(t.x1, t.y1) for t in doc.tracks() if t.layer == P.L_KEEPOUT and ov(min(t.x1, t.x2), min(t.y1, t.y2), max(t.x1, t.x2), max(t.y1, t.y2))] \
            + [(t.x2, t.y2) for t in doc.tracks() if t.layer == P.L_KEEPOUT and ov(min(t.x1, t.x2), min(t.y1, t.y2), max(t.x1, t.x2), max(t.y1, t.y2))]
        if ko_pts:
            ko.append(bb(ko_pts))
        covered = bool(ko) and min(k[0] for k in ko) <= rect[0] + tol and min(k[1] for k in ko) <= rect[1] + tol \
            and max(k[2] for k in ko) >= rect[2] - tol and max(k[3] for k in ko) >= rect[3] - tol
        cu = []
        for p in doc.pads():
            if p.plated and ov(*p.extent()):          # a non-plated hole carries no copper
                cu.append(f"pad {p.ref}-{p.name}")
        for t in doc.tracks():
            if P.is_copper(t.layer) and P.seg_hits_rect(t.x1, t.y1, t.x2, t.y2, t.width / 2, rect):
                cu.append(f"track {layer_name(t.layer)} {t.net}")
        for v in doc.vias():
            if ov(v.x - v.dia / 2, v.y - v.dia / 2, v.x + v.dia / 2, v.y + v.dia / 2):
                cu.append(f"via {v.net}")
        for r in regs:
            if not r.keepout and not r.poured and P.is_copper(r.layer) and ov(*bb(r.points)):
                cu.append(f"region {layer_name(r.layer)} {r.net or 'no net'}")
        why = []
        if not covered:
            why.append("no keep-out object covers it")
        if cu:
            why.append(f"copper inside: {len(cu)} ({', '.join(sorted(set(cu))[:3])})")
        if why:
            out.append(f"{q['id']}: " + "; ".join(why))
    return out


layer_name = P.layer_name


def _w25_root(ctx, name, snapshot, patch_rects=None, add_tracks=None):
    """Sparse root with idea-versions.json, the final PcbDoc and one `.advisor-backup` snapshot written from `snapshot` (patched)."""
    final = ctx.pcbdoc()
    c = CB.sparse_root(ctx, name, copy=("project/idea-versions.json", str(final.relative_to(ctx.root)).replace("\\", "/")))
    stamp, src = snapshot
    dst = c.altium / ".advisor-backup" / stamp.strftime("%Y%m%d-%H%M%S") / src.name
    CB.regions_to_keepout(src, dst, patch_rects or [], add_tracks, template_from=final)
    return c


def _w25_build(ctx):
    reqs, gone, _ = _ko_requirements(ctx)
    snap = _snapshot_for(ctx, gone)
    with P.PcbDoc(snap[1]) as doc:
        ox, oy = _origin(doc)
    rects = [(ox + q["rect_mm"][0], oy + q["rect_mm"][1], ox + q["rect_mm"][2], oy + q["rect_mm"][3]) for q in reqs]
    return _w25_root(ctx, "W25a-control", snap, patch_rects=rects)


def _w25_inject(c):
    reqs, gone, _ = _ko_requirements(c)
    snap = _snapshot_for(c, gone)
    q = c.rng.choice(reqs)
    with P.PcbDoc(snap[1]) as doc:
        ox, oy = _origin(doc)
        net = c.rng.choice([n for n in doc.nets() if n])
    a, b, x, y = q["rect_mm"]
    cx, cy = ox + (a + x) / 2, oy + (b + y) / 2
    track = (c.rng.choice([1, 32]), net, cx - 1.0, cy, cx + 1.0, cy, 0.2)
    return _w25_root(c, "W25a-canary", snap, add_tracks=[track]), q["id"]


@metric(id="W25(a)", title="Each keep-out requirement is a keep-out object with no copper inside", root="R4", level="L", p0=("P0-3", "P0-1"),
        control=_with_canary(_w25_build, _w25_inject, lambda c: w25a(c)))
def w25a(ctx):
    """Requirements: the keep-out items (rect_mm from the board origin) of the latest idea version that has any. The PcbDoc state
    checked is the latest snapshot at or before the version in which they disappeared (the final document if they never did)."""
    reqs, gone, vf = _ko_requirements(ctx)
    if not reqs:
        return Result("not_run", detail="no idea version has a keep-out requirement", evidence=[ctx.ev(vf, "idea-versions")])
    snap = _snapshot_for(ctx, gone)
    if snap is None:
        return Result("error", detail="no PcbDoc state from before the requirement was removed", evidence=[ctx.ev(vf, "idea-versions")])
    with P.PcbDoc(snap[1]) as doc:
        bad = _w25_problems(doc, reqs)
    return Result("pass" if not bad else "fail", measured=bad, expected="keep-out requirements without a clean keep-out object = 0",
                  detail=f"{len(bad)}/{len(reqs)} requirements; PcbDoc state {snap[1].parent.name}",
                  evidence=[ctx.ev(vf, "idea-versions"), ctx.ev(snap[1], "PcbDoc state")])


# ======================================================================================================================== W23 / W24
_CAP_VALUE = re.compile(r"^\s*[\d.]+\s*[pnuµμ]F\b", re.I)
_SUPPLY_PIN = re.compile(r"^(?:V(?:DD|CC|IO|PP)\w*|AVDD\w*|DVDD\w*|VBAT|VCAP\w*|VIN|VOUT|VBUS)$", re.I)
_CARD_ROLE = re.compile(r"card|micro\s*sd|\bsd\b|\btf\b", re.I)
_FLAG = re.compile(r"^\s*([A-Z]+\d+) is ([\d.]+) mm from ([A-Z]+\d+) pin (\w+)", re.M)


def _bom_lines(ctx):
    b = json.loads((ctx.project / "bom.json").read_text(encoding="utf-8"))
    return {ref: line for line in b for ref in line.get("refs") or []}


def _netlist_parts(ctx):
    parts = {}
    for f in sorted((ctx.project / "netlist").glob("*.json")):
        for p in json.loads(f.read_text(encoding="utf-8")).get("parts") or []:
            parts[p["ref"]] = p
    return parts


def _decap_model(ctx, doc):
    """({(ic, pin): {"name", "net", "d": nearest same-net cap distance mm or None, "cap"}}, {cap ref: {"net", "d", "pin": (ic, pin)}}).
    Supply pins: pins of ICs and card connectors (netlist kind and BOM role) whose function name is a supply name. A decap is a
    capacitor (BOM value in F) with one pad on ground and the other on the supply net; distances are pad centre to pad centre."""
    bom, parts, gnd = _bom_lines(ctx), _netlist_parts(ctx), P.ground_nets(doc)
    pads = [p for p in doc.pads() if p.ref]
    by_ref: dict = {}
    for p in pads:
        by_ref.setdefault(p.ref, []).append(p)
    caps = {}
    for ref, ps in by_ref.items():
        if len(ps) == 2 and _CAP_VALUE.match(str(bom.get(ref, {}).get("value") or "")):
            hot = [p for p in ps if p.net and p.net not in gnd]
            if len(hot) == 1 and any(p.net in gnd for p in ps):
                caps[ref] = hot[0]
    pins = {}
    for ref, part in parts.items():
        role = str(bom.get(ref, {}).get("role") or "")
        if not (part.get("kind") == "ic" or (part.get("kind") == "conn" and _CARD_ROLE.search(role))):
            continue
        for q in part["pins"]:
            if _SUPPLY_PIN.match(q["name"].split("/")[0].strip()):
                mine = [p for p in by_ref.get(ref, []) if p.name == q["num"]]
                if not mine or not mine[0].net or mine[0].net in gnd:
                    continue
                p = mine[0]
                near = [(math.hypot(c.x - p.x, c.y - p.y), cref) for cref, c in caps.items() if c.net == p.net]
                d, cref = min(near) if near else (None, None)
                pins[(ref, q["num"])] = {"name": q["name"], "net": p.net, "d": d, "cap": cref, "x": p.x, "y": p.y}
    capinfo = {}
    for cref, c in caps.items():
        near = [(math.hypot(c.x - v["x"], c.y - v["y"]), k) for k, v in pins.items() if v["net"] == c.net]
        if near:
            d, k = min(near)
            capinfo[cref] = {"net": c.net, "d": d, "pin": k}
    return pins, capinfo


def _place_flags(ctx):
    """Flag lines of the product's latest placement run in board-log.jsonl: [(ref, mm, ic, pin)]. Text of the product's own output
    (the claim W23/W24 compare with the oracle); it is read, never trusted."""
    f = ctx.project / "board-log.jsonl"
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    places = [r for r in rows if r.get("op") == "place"]
    if not places:
        return [], f
    last = max(places, key=lambda r: r["ts"])
    return [(m[0], float(m[1]), m[2], m[3]) for w in last.get("warnings") or [] for m in _FLAG.findall(w)], f


def _board_copy(ctx):
    final = str(ctx.pcbdoc().relative_to(ctx.root)).replace("\\", "/")
    nl = tuple(f"project/netlist/{p.name}" for p in (ctx.project / "netlist").glob("*.json"))
    return ("project/bom.json", final) + nl


def _flag_control(ctx, name, lines):
    """Sparse root with the fixture PcbDoc, bom, netlist and a board-log whose latest place run also lists `lines`."""
    c = CB.sparse_root(ctx, name, copy=_board_copy(ctx))
    rows = [json.loads(l) for l in (ctx.project / "board-log.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows.append({"ts": "2999-01-01T00:00:00.000", "op": "place", "ok": True, "summary": {"placed": 0}, "warnings": list(lines)})
    (c.project / "board-log.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return c


def _moved_root(c, name, shifts):
    """Sparse root like `c` (bom, netlist, board-log) whose PcbDoc has components moved by `shifts` {index: (dx, dy)}."""
    bad = CB.sparse_root(c, name, copy=("project/bom.json", "project/board-log.jsonl")
                         + tuple(f"project/netlist/{p.name}" for p in (c.project / "netlist").glob("*.json")))
    CB.move_components(c.pcbdoc(), bad.altium / c.pcbdoc().name, shifts)
    return bad


def _w23_oracle(ctx, doc):
    pins, _ = _decap_model(ctx, doc)
    d_lim = _tv(TH.DECAP_FALLBACK_MM)
    return {k: v for k, v in pins.items() if v["d"] is None or v["d"] > d_lim}, pins


def _w23_build(ctx):
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        bad, _ = _w23_oracle(ctx, doc)
    lines = [f"{v['cap'] or 'no cap'} is {v['d'] or 0:.1f} mm from {k[0]} pin {k[1]} ({v['name']}); limit {_tv(TH.DECAP_FALLBACK_MM):g} mm"
             for k, v in sorted(bad.items())]
    return _flag_control(ctx, "W23-control", lines)


def _w23_inject(c):
    """Canary: pick a random supply pin and move every same-net capacitor within the limit of it 30 mm away; its pin becomes an
    unflagged violation."""
    with P.PcbDoc(c.pcbdoc()) as doc:
        bad, pins = _w23_oracle(c, doc)
        pin = c.rng.choice(sorted(k for k in pins if k not in bad))
        v = pins[pin]
        bom = _bom_lines(c)
        comps = {x.ref: x.index for x in doc.components()}
        movers = {comps[p.ref]: (30.0, 30.0) for p in doc.pads()
                  if p.ref and p.net == v["net"] and _CAP_VALUE.match(str(bom.get(p.ref, {}).get("value") or ""))
                  and math.hypot(p.x - v["x"], p.y - v["y"]) <= _tv(TH.DECAP_FALLBACK_MM)}
    return _moved_root(c, "W23-canary", movers), f"{pin[0]} pin {pin[1]} "


@metric(id="W23", title="Decoupling flags equal the oracle set: supply pins whose nearest same-net cap is over the limit", root="R2",
        level="L", p0=("P0-3",), control=_with_canary(_w23_build, _w23_inject, lambda c: w23(c)))
def w23(ctx):
    """Limit: DECAP_FALLBACK_MM (OD-1: no part datasheet value is available to the oracle, so the fallback applies, labelled general
    knowledge). Grain per ACCEPTANCE W23: each supply pin of every IC and card connector against its nearest same-net capacitor.
    Flagged = the (IC, pin) pairs named in the product's latest placement warnings; the flagged set must equal the oracle set, so a
    pin flagged although within the limit also fails (set difference both ways)."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        bad, pins = _w23_oracle(ctx, doc)
    if not pins:
        return Result("error", detail="no supply pin found", evidence=[ctx.ev(f, "PcbDoc")])
    flags, lf = _place_flags(ctx)
    flagged = {(ic, pin) for _, _, ic, pin in flags}
    miss = sorted(set(bad) - flagged)
    extra = sorted((flagged & set(pins)) - set(bad))
    out = [f"{ic} pin {pin} ({bad[(ic, pin)]['name']}): nearest cap "
           f"{('%.2f mm' % bad[(ic, pin)]['d']) if bad[(ic, pin)]['d'] is not None else 'none'}, not flagged" for ic, pin in miss]
    out += [f"{ic} pin {pin}: flagged but within the limit" for ic, pin in extra]
    return Result("pass" if not out else "fail", measured=out, expected="oracle set minus flagged set = 0 (and none flagged in error)",
                  detail=f"oracle {len(bad)} pins over the limit of {len(pins)}; flagged {len(flagged)}",
                  evidence=[ctx.ev(f, "Pads6"), ctx.ev(lf, "placement warnings"), ctx.ev(ctx.project / "bom.json", "BOM")])


# ---- W24: cap-centric plus crystals
def _w24_oracle(ctx, doc):
    """Records (cap -> its nearest supply pin, crystal -> its MCU pins) whose distance is over the limit, [(ref, text)]."""
    pins, caps = _decap_model(ctx, doc)
    d_lim, x_lim = _tv(TH.DECAP_FALLBACK_MM), _tv(TH.XTAL_MAX_TRACK_MM)
    out = [(cref, f"{cref} is {v['d']:.1f} mm from {v['pin'][0]} pin {v['pin'][1]}") for cref, v in sorted(caps.items()) if v["d"] > d_lim]
    for g in _crystal_geometry(ctx, doc):
        c = g["c"]
        for net in sorted(g["own"]):
            mcu = [p for p in doc.pads() if p.net == net and p.comp not in (None, c.index)]
            mine = [p for p in g["pads"] if p.net == net]
            if not mcu or not mine:
                continue
            ic = max(mcu, key=lambda p: sum(1 for q in doc.pads() if q.comp == p.comp))
            d = min(math.hypot(ic.x - q.x, ic.y - q.y) for q in mine)
            if d > x_lim:
                out.append((c.ref, f"{c.ref} is {d:.1f} mm from {ic.ref} pin {ic.name}"))
    return out


def _w24_build(ctx):
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        bad = _w24_oracle(ctx, doc)
    return _flag_control(ctx, "W24-control", [f"{text}; limit {_tv(TH.DECAP_FALLBACK_MM):g} mm" for _, text in bad])


def _w24_inject(c):
    with P.PcbDoc(c.pcbdoc()) as doc:
        _, caps = _decap_model(c, doc)
        cref = c.rng.choice(sorted(k for k, v in caps.items() if v["d"] <= _tv(TH.DECAP_FALLBACK_MM)))
        idx = {x.ref: x.index for x in doc.components()}[cref]
    return _moved_root(c, "W24-canary", {idx: (30.0, 30.0)}), f"{cref} is "


@metric(id="W24", title="Placement distances: every decap near its pin and every crystal near its MCU, or flagged", root="R3", level="L",
        p0=("P0-1",), control=_with_canary(_w24_build, _w24_inject, lambda c: w24(c)))
def w24(ctx):
    """Records are derived from the placed board by rule (the product writes no typed constraint records on 27/11): each capacitor to
    its nearest same-net supply pin (limit DECAP_FALLBACK_MM), each crystal pad to its MCU pin (limit XTAL_MAX_TRACK_MM). A record over
    its limit must be named in the product's latest placement warnings, otherwise it is unflagged."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        over = _w24_oracle(ctx, doc)
        _, caps = _decap_model(ctx, doc)
    if not caps:
        return Result("error", detail="no decoupling capacitor found", evidence=[ctx.ev(f, "PcbDoc")])
    flags, lf = _place_flags(ctx)
    flagged = {ref for ref, *_ in flags}
    out = [f"{text}, not flagged" for ref, text in over if ref not in flagged]
    return Result("pass" if not out else "fail", measured=out, expected="records over the limit and not flagged = 0",
                  detail=f"{len(over)} records over the limit, {len(out)} unflagged",
                  evidence=[ctx.ev(f, "Pads6"), ctx.ev(lf, "placement warnings")])


# ======================================================================================================================== W34(b) / W18 / F-H(c)
def _walk_text(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk_text(v, path + (str(k),))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk_text(v, path + (str(i),))
    elif isinstance(o, str):
        yield path, o


def _order_manifest_file(ctx):
    fs = sorted((ctx.project / "exports").glob("*_order_manifest.json"))
    if len(fs) != 1:
        raise FileNotFoundError(f"expected one *_order_manifest.json in {ctx.project / 'exports'}, found {len(fs)}")
    return fs[0]


def _product_findings(ctx):
    """Free-text findings of the product's order manifest (every string except the raw Altium DRC dump under a 'drc' key: those lines
    are unclassified Altium output, F-H a, not a finding the product made), and the file."""
    f = _order_manifest_file(ctx)
    d = json.loads(f.read_text(encoding="utf-8"))
    return [t for p, t in _walk_text(d) if not any("drc" in k.lower() for k in p)], f


def _names(text: str, ref: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(ref)}(?![A-Za-z0-9])", text) is not None


_CPL_WORDS = re.compile(r"\bCPL\b|centroid|pick[\s-]*(?:and|&)?[\s-]*place|placement point|\borigin\b", re.I)


def _centres(doc):
    """{ref: {"pad_origin", "body_origin", "body_pad"}} in mm: pad bounding-box centre (copper extents, OD-5), footprint origin and 3D
    body bounding-box centre. Parts with no pad are skipped; body_* is None when the part has no body."""
    out = {}
    for c in doc.components():
        boxes = [p.extent() for p in doc.pads() if p.comp == c.index]
        if not boxes:
            continue
        pc = ((min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2, (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2)
        bb = [b.bbox() for b in doc.bodies() if b.comp == c.index and b.bbox()]
        bc = ((min(b[0] for b in bb) + max(b[2] for b in bb)) / 2, (min(b[1] for b in bb) + max(b[3] for b in bb)) / 2) if bb else None
        out[c.ref] = {"pad_origin": math.hypot(pc[0] - c.x, pc[1] - c.y),
                      "body_origin": math.hypot(bc[0] - c.x, bc[1] - c.y) if bc else None,
                      "body_pad": math.hypot(bc[0] - pc[0], bc[1] - pc[1]) if bc else None}
    return out


def _cpl_offset_parts(doc):
    """Parts whose pad centre, origin and body centre differ by more than CPL_FLAG_MM (OD-5): {ref: (worst mm, text)}."""
    lim = _tv(TH.CPL_FLAG_MM)
    out = {}
    for ref, c in _centres(doc).items():
        vals = {k: v for k, v in c.items() if v is not None}
        worst = max(vals.values())
        if worst > lim:
            k = max(vals, key=vals.get)
            out[ref] = (worst, f"{k.replace('_', ' to ')} {worst:.2f} mm")
    return out


def _lib_issues(ctx):
    f = ctx.project / "library" / "manifest.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    return {ref: v for ref, v in m.items() if isinstance(v, dict)}, f


def _offset_files(ctx):
    om = _order_manifest_file(ctx)
    return (str(ctx.pcbdoc().relative_to(ctx.root)).replace("\\", "/"), str(om.relative_to(ctx.root)).replace("\\", "/"),
            "project/library/manifest.json")


def _w34_build(ctx):
    """Control: the fixture PcbDoc, a library manifest as it is and an order manifest that also carries a production finding for
    every part the oracle lists."""
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        parts = _cpl_offset_parts(doc)
    c = CB.sparse_root(ctx, "W34-control", copy=_offset_files(ctx))
    om = c.project / "exports" / _order_manifest_file(ctx).name
    d = json.loads(om.read_text(encoding="utf-8"))
    d["cpl_findings"] = [f"{ref}: the pick and place point (pad box centre) is off the footprint origin or body centre ({t}); "
                         f"check its CPL position" for ref, (_, t) in sorted(parts.items())]
    om.write_text(json.dumps(d), encoding="utf-8")
    return c


def _w34_inject(c, lib_issue: bool = False):
    """Canary: the origin of a random pad-bearing part with no offset moves 1.0 mm (pads stay) and nothing flags it."""
    with P.PcbDoc(c.pcbdoc()) as doc:
        ok = _cpl_offset_parts(doc)
        cands = sorted(r for r in _centres(doc) if r not in ok and sum(1 for p in doc.pads() if p.ref == r) >= 2)
        ref = c.rng.choice(cands)
        idx = {x.ref: x.index for x in doc.components()}[ref]
    bad = CB.sparse_root(c, "W34-canary", copy=_offset_files(c))
    CB.move_components(c.pcbdoc(), bad.altium / c.pcbdoc().name, {idx: (1.0, 0.0)}, pads=False)
    if lib_issue:
        lf = bad.project / "library" / "manifest.json"
        m = json.loads(lf.read_text(encoding="utf-8"))
        e = m.setdefault(ref, {})
        e["status"], e["issues"] = "warn", [f"the 3D body of footprint {ref} is centred 1.0 mm from its pads (limit 0.5 mm): the model may be offset"]
        lf.write_text(json.dumps(m), encoding="utf-8")
    return bad, f"{ref}: "


@metric(id="W34(b)", title="Every part whose pad centre, origin and body centre differ by more than the CPL flag limit has a production finding",
        root="R4", level="U", p0=("P0-3",), control=_with_canary(_w34_build, _w34_inject, lambda c: w34b(c)))
def w34b(ctx):
    """Oracle: pad bounding-box centre, footprint origin and 3D body centre from the PcbDoc; limit CPL_FLAG_MM (OD-5). A part is flagged
    when a free-text finding of the order manifest names it together with a CPL / centroid / pick-and-place / origin wording. The 3D
    warnings of the library manifest are not production findings (that is W18). The CPL file itself (U5 on 27/11) is W34(a), not read
    here."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        parts = _cpl_offset_parts(doc)
        total = len(_centres(doc))
    if not total:
        return Result("error", detail="no part with pads found", evidence=[ctx.ev(f, "PcbDoc")])
    texts, mf = _product_findings(ctx)
    out = [f"{ref}: {t}, no production finding" for ref, (_, t) in sorted(parts.items())
           if not any(_names(x, ref) and _CPL_WORDS.search(x) for x in texts)]
    return Result("pass" if not out else "fail", measured=out, expected="parts over the limit without a production finding = 0",
                  detail=f"{len(parts)} of {total} parts over {_tv(TH.CPL_FLAG_MM):g} mm; {len(out)} unflagged",
                  evidence=[ctx.ev(f, "Pads6, Components6, ComponentBodies6"), ctx.ev(mf, "order manifest findings")])


def _w18_inject(c):
    return _w34_inject(c, lib_issue=True)


@metric(id="W18", title="An offset that moves the CPL point is a production finding, not only a 3D warning", root="R4", level="U",
        p0=(), control=_with_canary(_w34_build, _w18_inject, lambda c: w18(c)))
def w18(ctx):
    """Misclassified = a part the library manifest reports as a 3D offset whose pad centre, origin and body centre differ by more than
    CPL_FLAG_MM (so the CPL point moves) and that no production finding names. Not covered here: the comparison of the figures the
    product shows with the oracle's (the product's figures come from the STEP model, which the PcbDoc/PcbLib reader does not read)."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        parts = _cpl_offset_parts(doc)
    lib, lf = _lib_issues(ctx)
    d3 = {ref for ref, v in lib.items() if any(re.search(r"\b3D\b", str(i)) for i in v.get("issues") or [])}
    texts, mf = _product_findings(ctx)
    if not d3:
        return Result("error", detail="the library manifest has no 3D finding to classify", evidence=[ctx.ev(lf, "library manifest")])
    out = [f"{ref}: {parts[ref][1]}, classed only as a 3D warning" for ref in sorted(d3 & set(parts))
           if not any(_names(x, ref) and _CPL_WORDS.search(x) for x in texts)]
    return Result("pass" if not out else "fail", measured=out, expected="misclassified = 0",
                  detail=f"{len(d3)} parts with a 3D warning, {len(d3 & set(parts))} of them move the CPL point",
                  evidence=[ctx.ev(f, "PcbDoc"), ctx.ev(lf, "library manifest 3D warnings"), ctx.ev(mf, "order manifest findings")])


# ---- F-H (c): parts and copper at the board edge
_MM = re.compile(r"\d+(?:\.\d+)?\s*mm", re.I)


def _edge_need(doc):
    """[(kind, label, gap mm, limit mm)] over the limit: components <= EDGE_ASSEMBLY_MIN_MM, copper < EDGE_COPPER_MIN_MM. Gaps compare
    after GEOM_TOL_MM (coordinate resolution), so a gap stored as 0.29999 mm counts as 0.3 mm."""
    tol, la, lc = _tv(TH.GEOM_TOL_MM), _tv(TH.EDGE_ASSEMBLY_MIN_MM), _tv(TH.EDGE_COPPER_MIN_MM)
    out = []
    for kind, label, gap in P.edge_gaps(doc):
        if kind == "component" and gap <= la + tol:
            out.append((kind, label, gap, la))
        elif kind != "component" and gap < lc - tol:
            out.append((kind, label or "?", gap, lc))
    return out


def _edge_flagged(texts, kind, label) -> bool:
    for x in texts:
        if re.search(r"\bedge\b", x, re.I) and _MM.search(x) and (_names(x, label) if label else False):
            return True
    return False


def _fh_build(ctx):
    with P.PcbDoc(ctx.pcbdoc()) as doc:
        need = _edge_need(doc)
    c = CB.sparse_root(ctx, "F-H-control", copy=(str(ctx.pcbdoc().relative_to(ctx.root)).replace("\\", "/"),
                                                  str(_order_manifest_file(ctx).relative_to(ctx.root)).replace("\\", "/")))
    om = c.project / "exports" / _order_manifest_file(ctx).name
    d = json.loads(om.read_text(encoding="utf-8"))
    d["edge_findings"] = [f"{label}: {gap:.2f} mm from the board edge; JLC asks more than {lim:g} mm" for _, label, gap, lim in need]
    om.write_text(json.dumps(d), encoding="utf-8")
    return c


def _fh_inject(c):
    """Canary: a random movable part moves to 0.1 mm of the board edge (its origin and pads shift together); nothing flags it."""
    with P.PcbDoc(c.pcbdoc()) as doc:
        gaps = {l: g for k, l, g in P.edge_gaps(doc) if k == "component"}
        o = doc.outline()
        left = min(p[0] for p in o)
        cands = sorted(r for r, g in gaps.items() if g > 1.0 and sum(1 for p in doc.pads() if p.ref == r) >= 2)
        ref = c.rng.choice(cands)
        comp = {x.ref: x for x in doc.components()}[ref]
        boxes = [p.extent() for p in doc.pads() if p.comp == comp.index and p.plated]
        dx = (left + 0.1) - min(b[0] for b in boxes)
    bad = CB.sparse_root(c, "F-H-canary", copy=(str(c.pcbdoc().relative_to(c.root)).replace("\\", "/"),
                                                 str(_order_manifest_file(c).relative_to(c.root)).replace("\\", "/")))
    CB.move_components(c.pcbdoc(), bad.altium / c.pcbdoc().name, {comp.index: (dx, 0.0)})
    return bad, f"{ref} ("


@metric(id="F-H(c)", title="A part within 0.3 mm of the board edge, or copper within 0.2 mm of it, is flagged", root="R4", level="L",
        p0=(), control=_with_canary(_fh_build, _fh_inject, lambda c: fh_c(c)))
def fh_c(ctx):
    """Limits: EDGE_ASSEMBLY_MIN_MM (> 0.3 mm for components, so 0.3 mm or less is a finding) and EDGE_COPPER_MIN_MM (>= 0.2 mm for
    copper). Gaps measured from the Board6 outline to plated pad copper and 3D bodies per part, and to track and via copper. A finding
    counts when a free-text finding of the order manifest names the part (or the net) with the word edge and a distance in mm; the
    raw Altium DRC lines are not findings."""
    f = ctx.pcbdoc()
    with P.PcbDoc(f) as doc:
        need = _edge_need(doc)
        n = sum(1 for k, *_ in P.edge_gaps(doc) if k == "component")
    if not n:
        return Result("error", detail="no component to measure", evidence=[ctx.ev(f, "PcbDoc")])
    texts, mf = _product_findings(ctx)
    out = [f"{label} ({kind}) is {gap:.2f} mm from the board edge (limit {lim:g} mm), not flagged"
           for kind, label, gap, lim in need if not _edge_flagged(texts, kind, label)]
    return Result("pass" if not out else "fail", measured=out, expected="over-limit parts and copper without a finding = 0",
                  detail=f"{len(need)} items over the limit of {n} components; {len(out)} unflagged",
                  evidence=[ctx.ev(f, "Board6 outline, Pads6"), ctx.ev(mf, "order manifest findings")])


# ======================================================================================================================== F-J (e)
_EP_CLAIM = re.compile(r"\bpin\s+(\w+)\b[^;:]*:\s*exposed pad", re.I)


def _verify_claims(ctx):
    """{part ref: [pin numbers claimed to be an exposed pad]} from the latest verify_part row of each part in library-log.jsonl."""
    f = ctx.project / "library-log.jsonl"
    last = {}
    for l in f.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("by") == "verify_part" and r.get("line"):
                last[r["line"]] = r
    return {ref: _EP_CLAIM.findall(str(r.get("changes"))) for ref, r in last.items()}, f


def _is_exposed(fp, pin: str) -> bool | None:
    """Rule without a number: pad `pin` is an exposed pad when its copper box is larger than that of every pad with another name
    in the same footprint (the single largest pad). None when the footprint has no pad of that name."""
    mine = [p.xs * p.ys for p in fp.pads if p.name == pin]
    rest = [p.xs * p.ys for p in fp.pads if p.name != pin]
    if not mine:
        return None
    return bool(rest) and max(mine) > max(rest) * (1 + 1e-6)


def _fj_lookup(ctx):
    lib, lf = _lib_issues(ctx)
    fps = {fp.name: fp for path in _pcbs(ctx) for fp in P.read_pcblib(path)}
    return lib, lf, fps


def _fj_false(ctx):
    claims, cf = _verify_claims(ctx)
    lib, lf, fps = _fj_lookup(ctx)
    bad, n = [], 0
    for ref, pins in sorted(claims.items()):
        fp = fps.get((lib.get(ref) or {}).get("footprint"))
        for pin in pins:
            n += 1
            if fp is None:
                bad.append((ref, pin, "footprint not found in the PcbLib"))
            elif _is_exposed(fp, pin) is not True:
                bad.append((ref, pin, f"{fp.name} has no exposed pad named {pin}" if _is_exposed(fp, pin) is None
                            else f"pad {pin} of {fp.name} is an ordinary pad"))
    return bad, n, cf, lf


def _fj_files(ctx):
    libs = [str(p.relative_to(ctx.root)).replace("\\", "/") for p in _pcbs(ctx)]
    return ("project/library-log.jsonl", "project/library/manifest.json", *libs)


def _fj_build(ctx):
    """Control: the verify messages with every false exposed-pad claim removed from the text."""
    bad, _, _, _ = _fj_false(ctx)
    c = CB.sparse_root(ctx, "F-J-control", copy=_fj_files(ctx))
    f = c.project / "library-log.jsonl"
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        if r.get("by") == "verify_part":
            for ref, pin, _ in bad:
                if r.get("line") == ref:
                    r["changes"] = re.sub(rf"(\bpin\s+{re.escape(pin)}\b[^;:]*):\s*exposed pad", r"\1", str(r["changes"]))
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return c


def _fj_inject(c):
    """Canary: a new verify message for a random part claims a random ordinary pad of its footprint is an exposed pad."""
    lib, _, fps = _fj_lookup(c)
    cands = sorted((ref, p.name) for ref, v in lib.items() if (fp := fps.get(v.get("footprint"))) and len(fp.pads) >= 2
                   for p in fp.pads if _is_exposed(fp, p.name) is False)
    ref, pin = c.rng.choice(cands)
    f = c.project / "library-log.jsonl"
    msg = f"{ref}: not found as a row of the datasheet's pin table: pin {pin} X: exposed pad: the datasheet's table does not say its net"
    with open(f, "a", encoding="utf-8") as h:
        h.write(json.dumps({"ts": "2999-01-01T00:00:00.000", "by": "verify_part", "line": ref, "changes": str({"verify": "unchecked", "issues": msg})}) + "\n")
    return c, f"{ref}: pin {pin} "


def _fj_canary_root(c):
    bad = CB.sparse_root(c, "F-J-canary", copy=_fj_files(c))
    return bad


@metric(id="F-J(e)", title="Every exposed-pad claim in a verify message equals the PcbLib pad geometry", root="R3", level="L", p0=("P0-1",),
        control=_with_canary(_fj_build, lambda c: _fj_inject(_fj_canary_root(c)), lambda c: fj_e(c)))
def fj_e(ctx):
    """Claim: the latest verify_part message of a part in library-log.jsonl says "pin N <name>: exposed pad". Oracle: the PcbLib
    footprint named in the library manifest. Rule without a number: a pad is an exposed pad when it is larger than every pad with
    another name in its footprint (no shared/reference source gives a size ratio, so none is invented). Not covered: pin-count claims."""
    bad, n, cf, lf = _fj_false(ctx)
    if n == 0:
        return Result("error", detail="no exposed-pad claim in any verify message", evidence=[ctx.ev(cf, "verify messages")])
    out = [f"{ref}: pin {pin} is claimed to be an exposed pad, but {why}" for ref, pin, why in bad]
    return Result("pass" if not out else "fail", measured=out, expected="false exposed-pad claims = 0",
                  detail=f"{len(bad)} of {n} claims false, in {len({r for r, *_ in bad})} part(s)",
                  evidence=[ctx.ev(cf, "verify messages"), ctx.ev(lf, "library manifest")] + [ctx.ev(p, "PcbLib") for p in _pcbs(ctx)])
