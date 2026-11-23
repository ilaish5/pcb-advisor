"""Stream C: the board's physical constraints (mounting holes, edge parts, keep-apart, keep-outs, part attributes).

A constraint is data in the idea (idea["constraints"]), not free text: the placer, the router and the board checks read it, and the
agent states a board fact only from what check_requirements measured on the saved board (see board_facts).

    idea["constraints"] = {"version": 1, "items": [item, ...]}
    item = {"id", "kind", "by": "agent"|"student", "status": "proposed"|"confirmed", "note"?, ...kind fields}
      mounting_hole  diameter_mm (default 3.2), inset_mm (3.5, centre to each board edge), corners ["BL","BR","TL","TR"] or points_mm [[x, y]]
                     (from the board's lower left corner)
      edge           target (a part), side: any|left|right|top|bottom
      keep_apart     a, b (parts), min_mm
      keepout        rect_mm [x0, y0, x1, y1] from the board's lower left corner, or edge + depth_mm (a strip along a whole edge)
      attr           target, attr: heat_source|heat_sensitive|rf_antenna   (recorded; nothing on the board can prove it)

The agent proposes (action idea.constrain), the student confirms everything with the one Save of the idea; only SAVED, confirmed
items reach the library, the placer and the checks. Holes and keep-outs are generated as MECH_ footprints (H1.., KO1..) in the
project library and placed with the existing FPBATCH / PLACEFP: the Altium script has no hole command.
"""
import json
import math
import pathlib
import re
import time

import ext

VERSION = 1
KINDS = ("mounting_hole", "edge", "keep_apart", "keepout", "attr")
ATTRS = ("heat_source", "heat_sensitive", "rf_antenna")
SIDES = ("any", "left", "right", "top", "bottom")
CORNERS = ("BL", "BR", "TL", "TR")
DEFAULTS = {"hole_dia_mm": 3.2, "hole_inset_mm": 3.5, "apart_mm": 10.0, "edge_gap_mm": 1.5}
SIDE_LETTER = {"left": "L", "right": "R", "top": "T", "bottom": "B"}
HOLE_PREFIX, KEEPOUT_PREFIX = "H", "KO"
MECH_REF = re.compile(r"^(?:H|KO)\d+$")
FACTS_FILE = "board-facts.json"
BY = ("agent", "student")
STATUS = ("proposed", "confirmed")


def empty():
    return {"version": VERSION, "items": []}


def _num(item, key, default=None, lo=None, hi=None):
    v = item.get(key, default)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{item.get('kind')}: {key} must be a number") from None
    if not math.isfinite(v) or (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ValueError(f"{item.get('kind')}: {key} {v:g} is outside {lo:g} to {hi:g}")
    return round(v, 3)


def _ref(item, key):
    v = str(item.get(key) or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,23}", v):
        raise ValueError(f"{item.get('kind')}: {key} must be a part (a reference such as U1, or a BOM line)")
    return v


def validate_item(item):
    """One clean item (unknown keys dropped, defaults filled in) or ValueError."""
    if not isinstance(item, dict):
        raise ValueError("a constraint is an object")
    kind = item.get("kind")
    if kind not in KINDS:
        raise ValueError(f"constraint kind must be one of {', '.join(KINDS)}")
    out = {"id": str(item.get("id") or "")[:24], "kind": kind, "by": item.get("by") if item.get("by") in BY else "student",
           "status": item.get("status") if item.get("status") in STATUS else "proposed"}
    if item.get("note"):
        out["note"] = str(item["note"])[:200]
    if kind == "mounting_hole":
        out["diameter_mm"] = _num(item, "diameter_mm", DEFAULTS["hole_dia_mm"], 0.5, 10)
        if item.get("points_mm") not in (None, []):
            pts = item["points_mm"]
            if not isinstance(pts, list) or not all(isinstance(p, (list, tuple)) and len(p) == 2 for p in pts) or len(pts) > 12:
                raise ValueError("mounting_hole: points_mm is a list of [x, y] (at most 12)")
            out["points_mm"] = [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in pts]
        else:
            out["inset_mm"] = _num(item, "inset_mm", DEFAULTS["hole_inset_mm"], 1, 50)
            corners = item.get("corners") or list(CORNERS)
            if not isinstance(corners, list) or not corners or any(c not in CORNERS for c in corners):
                raise ValueError("mounting_hole: corners are BL, BR, TL, TR")
            out["corners"] = [c for c in CORNERS if c in corners]
    elif kind == "edge":
        out["target"] = _ref(item, "target")
        out["side"] = item.get("side") if item.get("side") in SIDES else "any"
    elif kind == "keep_apart":
        out["a"], out["b"] = _ref(item, "a"), _ref(item, "b")
        if out["a"] == out["b"]:
            raise ValueError("keep_apart: a and b are the same part")
        out["min_mm"] = _num(item, "min_mm", DEFAULTS["apart_mm"], 0.5, 200)
    elif kind == "keepout":
        if item.get("rect_mm"):
            r = item["rect_mm"]
            if not isinstance(r, (list, tuple)) or len(r) != 4:
                raise ValueError("keepout: rect_mm is [x0, y0, x1, y1]")
            x0, y0, x1, y1 = (round(float(v), 3) for v in r)
            if x1 - x0 < 0.5 or y1 - y0 < 0.5:
                raise ValueError("keepout: rect_mm must be at least 0.5 mm in each direction (x0 < x1, y0 < y1)")
            out["rect_mm"] = [x0, y0, x1, y1]
        elif item.get("edge") in SIDE_LETTER:
            out["edge"] = item["edge"]
            out["depth_mm"] = _num(item, "depth_mm", None, 0.5, 100)
        else:
            raise ValueError("keepout: give rect_mm [x0, y0, x1, y1] or edge (left|right|top|bottom) with depth_mm")
    else:
        out["target"] = _ref(item, "target")
        if item.get("attr") not in ATTRS:
            raise ValueError(f"attr: attr must be one of {', '.join(ATTRS)}")
        out["attr"] = item["attr"]
    return out


def validate(c):
    """The constraints object, clean, ids unique; ValueError when an item is wrong. None / {} is no constraints."""
    if c in (None, {}, []):
        return empty()
    if not isinstance(c, dict) or not isinstance(c.get("items", []), list):
        raise ValueError("constraints is {\"version\": 1, \"items\": [...]}")
    if len(c.get("items", [])) > 60:
        raise ValueError("at most 60 constraints")
    items, used = [], set()
    for raw in c.get("items", []):
        it = validate_item(raw)
        base = it["id"] or {"mounting_hole": "holes", "edge": "edge", "keep_apart": "apart", "keepout": "keepout", "attr": "attr"}[it["kind"]]
        n, name = 1, base if it["id"] else f"{base}-1"
        while name in used:
            n += 1
            name = f"{base}-{n}"
        it["id"] = name
        used.add(name)
        items.append(it)
    return {"version": VERSION, "items": items}


def of(idea):
    """The items of an idea dict (clean; a broken record gives no items rather than an exception)."""
    try:
        return validate((idea or {}).get("constraints"))["items"]
    except ValueError:
        return []


def confirmed(idea):
    return [i for i in of(idea) if i["status"] == "confirmed"]


def confirm_all(idea):
    """The Save of the idea is the student's one confirmation: every proposed item becomes confirmed (the idea dict is changed)."""
    c = validate((idea or {}).get("constraints"))
    if any(i["status"] != "confirmed" for i in c["items"]):
        for i in c["items"]:
            i["status"] = "confirmed"
    if c["items"] or "constraints" in idea:
        idea["constraints"] = c
    return idea


def changes(saved, draft):
    """How many constraints differ between the saved idea and the draft (added, removed or changed): counted by store.idea_changes,
    so a draft that only holds constraints is a draft that can be saved."""
    a = {i["id"]: json.dumps(i, sort_keys=True) for i in of(saved)}
    b = {i["id"]: json.dumps(i, sort_keys=True) for i in of(draft)}
    return sum(1 for k in set(a) | set(b) if a.get(k) != b.get(k))


# ---------------------------------------------------------------- what the constraints mean on a board

def corner_points(item, outline):
    """[(x, y)] mm board coordinates of a mounting_hole item on an outline [x0, y0, x1, y1]."""
    x0, y0, x1, y1 = outline
    if item.get("points_mm"):
        return [(x0 + p[0], y0 + p[1]) for p in item["points_mm"]]
    d = item.get("inset_mm", DEFAULTS["hole_inset_mm"])
    pos = {"BL": (x0 + d, y0 + d), "BR": (x1 - d, y0 + d), "TL": (x0 + d, y1 - d), "TR": (x1 - d, y1 - d)}
    return [pos[c] for c in item.get("corners", CORNERS)]


def keepout_rect(item, size=None, outline=None):
    """[x0, y0, x1, y1] mm FROM THE BOARD'S LOWER LEFT CORNER of a keepout item (an edge strip needs the board size), or None."""
    if item.get("rect_mm"):
        return list(item["rect_mm"])
    if not size:
        if outline:
            size = (outline[2] - outline[0], outline[3] - outline[1])
        else:
            return None
    w, h = size
    d = item.get("depth_mm") or 0
    return {"left": [0, 0, d, h], "right": [w - d, 0, w, h], "bottom": [0, 0, w, d], "top": [0, h - d, w, h]}.get(item.get("edge"))


def mech_name(kind_prefix, n):
    return f"{kind_prefix}{n}"


def library_specs(idea):
    """[{name, desc, lines}] mechanical footprints the project library must hold for the idea's CONFIRMED constraints: one hole
    footprint per diameter, one keep-out box per keepout item. A keep-out strip along an edge needs the board size."""
    import partlib_generate as gen
    from altium import layout
    specs, seen = [], set()
    size = layout.board_size(idea)
    for it in confirmed(idea):
        if it["kind"] == "mounting_hole":
            sp = gen.mounting_hole(it["diameter_mm"])
        elif it["kind"] == "keepout":
            rect = keepout_rect(it, size)
            if rect is None:
                continue
            sp = gen.keepout_box(rect[2] - rect[0], rect[3] - rect[1], name=gen.keepout_name(it["id"]))
        else:
            continue
        if sp["name"] not in seen:
            seen.add(sp["name"])
            specs.append(sp)
    return specs


def known_refs(project):
    """Every part reference the project knows (BOM lines): {REF_UPPER: ref} plus the BOM line keys as {KEY_UPPER: [refs]}."""
    import store
    refs, lines = {}, {}
    for l in store.bom_lines(project):
        for r in l.get("refs") or []:
            refs[r.upper()] = r
        if l.get("key"):
            lines[str(l["key"]).upper()] = list(l.get("refs") or [])
    return refs, lines


def resolve(target, refs, lines):
    """The part references a constraint target names: a reference, or a BOM line key (all its references). [] when unknown."""
    t = str(target or "").upper()
    if t in refs:
        return [refs[t]]
    return list(lines.get(t, []))


def plan_for_board(items, outline, refs=None, lines=None, size=None):
    """What the placer and the checks need from the CONFIRMED items, for a board outline [x0, y0, x1, y1]:
    {"holes": [{ref, footprint, x, y, rot, dia, item}], "keepouts": [{ref, footprint, x, y, rect, item}] (board mm),
     "edge": {part ref: side letter or ""}, "apart": [(ref a, ref b, min mm)], "attrs": [...], "findings": [str]}.
    Mechanical references are H1.. and KO1.. in item order. A target that is no part of the project is a finding, never a guess."""
    import partlib_generate as gen
    findings = []
    out = {"holes": [], "keepouts": [], "edge": {}, "apart": [], "attrs": [], "findings": findings}

    def parts(target, item):
        if refs is None:
            return [target]
        got = resolve(target, refs, lines or {})
        if not got:
            findings.append(f"constraint {item['id']} has no part: {target} is not a part of this project")
        return got
    nh = nk = 0
    for it in items:
        if it["kind"] == "mounting_hole":
            pts = corner_points(it, outline)
            r = it["diameter_mm"] / 2 + 0.3
            ok = [(x, y) for x, y in pts if outline[0] + r <= x <= outline[2] - r and outline[1] + r <= y <= outline[3] - r]
            if len(ok) < len(pts):
                findings.append(f"constraint {it['id']}: a hole at the board edge or outside the board was not placed")
            if any(math.hypot(a[0] - b[0], a[1] - b[1]) < it["diameter_mm"] + 1.0 for i, a in enumerate(ok) for b in ok[i + 1:]):
                findings.append(f"constraint {it['id']}: the holes would touch each other, the board is too small for them")
                ok = []
            for x, y in ok:
                nh += 1
                out["holes"].append({"ref": mech_name(HOLE_PREFIX, nh), "footprint": gen.mounting_hole_name(it["diameter_mm"]),
                                     "x": round(x, 3), "y": round(y, 3), "rot": 0, "dia": it["diameter_mm"], "item": it["id"]})
        elif it["kind"] == "keepout":
            rect = keepout_rect(it, size, outline)
            if rect is None:
                findings.append(f"constraint {it['id']}: the keep-out strip needs the board size")
                continue
            box = [outline[0] + rect[0], outline[1] + rect[1], outline[0] + rect[2], outline[1] + rect[3]]
            nk += 1
            out["keepouts"].append({"ref": mech_name(KEEPOUT_PREFIX, nk), "footprint": gen.keepout_name(it["id"]),
                                    "x": round((box[0] + box[2]) / 2, 3), "y": round((box[1] + box[3]) / 2, 3), "rot": 0,
                                    "rect": [round(v, 3) for v in box], "item": it["id"]})
        elif it["kind"] == "edge":
            for r in parts(it["target"], it):
                out["edge"][r] = SIDE_LETTER.get(it["side"], "")
        elif it["kind"] == "keep_apart":
            for a in parts(it["a"], it):
                for b in parts(it["b"], it):
                    if a != b:
                        out["apart"].append((a, b, it["min_mm"]))
        elif it["kind"] == "attr":
            for r in parts(it["target"], it):
                out["attrs"].append({"ref": r, "attr": it["attr"], "item": it["id"]})
    return out


def is_mech_ref(ref):
    return bool(MECH_REF.match(str(ref or "")))


# ---------------------------------------------------------------- the measured board: facts and requirement rows

def _facts_path(project):
    import store
    return store.pdir(project) / FACTS_FILE


def _pcb_stamp(pcb):
    try:
        st = pathlib.Path(pcb).stat()
        return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    except OSError:
        return None


def record_facts(project, doc, outline, pcb="", drc_total=None, size=None):
    """Measure the saved board (read_pcbdoc dict) against the confirmed constraints and keep the answer next to the project, with the
    board file's size and time so it is known to be stale after any later change. Never raises (a check that cannot run is
    no reason to fail a placement); returns the facts, or None."""
    try:
        import store
        from checks import requirements
        items = confirmed(store.load_idea(project))
        refs, lines = known_refs(project)
        facts = requirements.measure(doc, outline, items, refs=refs, lines=lines, size=size)
        facts.update(measured_at=time.strftime("%Y-%m-%dT%H:%M:%S"), pcb=str(pcb), stamp=_pcb_stamp(pcb) if pcb else None,
                     drc_total=drc_total, outline=[round(v, 3) for v in outline] if outline else None)
        store._atomic_write_json(_facts_path(project), facts)
        return facts
    except Exception:       # noqa: BLE001 - see the docstring
        return None


def load_facts(project):
    """The recorded facts with "stale" set (the board file changed since, or there is no board file), or None when nothing was measured."""
    try:
        facts = json.loads(_facts_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(facts, dict):
        return None
    stamp = facts.get("stamp")
    facts["stale"] = bool(stamp is None or stamp != _pcb_stamp(facts.get("pcb") or ""))
    return facts


def requirement_rows(project, idea=None):
    """One row per CONFIRMED constraint: {id, kind, status: met|violated|unverifiable, measured, need}. The measurement is the last
    one recorded for the board; when the board changed since (or was never measured) every row says unverifiable."""
    import store
    idea = idea if idea is not None else store.load_idea(project)
    facts = load_facts(project)
    got = {r["id"]: r for r in (facts or {}).get("requirements", [])} if facts and not facts.get("stale") else {}
    rows = []
    for it in confirmed(idea):
        if it["id"] in got:
            rows.append(got[it["id"]])
        else:
            why = "the board was not measured yet" if not facts else "the board changed since it was last measured"
            rows.append({"id": it["id"], "kind": it["kind"], "status": "unverifiable", "measured": why,
                         "need": describe(it)})
    for r in (facts or {}).get("requirements", []):          # rows the checker adds itself (copper under a module's antenna keep-out)
        if r["id"].startswith("auto:") and not (facts or {}).get("stale"):
            rows.append(r)
    return rows


def describe(it):
    k = it["kind"]
    if k == "mounting_hole":
        n = len(it.get("points_mm") or it.get("corners") or [])
        return f"{n} mounting hole{'s' if n != 1 else ''}, {it['diameter_mm']:g} mm"
    if k == "edge":
        return f"{it['target']} at the {it['side']} edge" if it["side"] != "any" else f"{it['target']} at a board edge"
    if k == "keep_apart":
        return f"{it['a']} at least {it['min_mm']:g} mm from {it['b']}"
    if k == "keepout":
        return "no copper in the keep-out"
    return f"{it['target']}: {it['attr'].replace('_', ' ')}"


@ext.register("model")
def _model(project, out):
    try:
        return {"requirements": requirement_rows(project, out.get("idea") if isinstance(out.get("idea"), dict) else None)}
    except Exception as exc:       # noqa: BLE001 - the state must always build
        return {"requirements": [], "requirements_error": str(exc)}


@ext.register("summary")
def _summary(project, s):
    """What the agent may say about the board: only these measured facts, or "none measured"."""
    import store
    idea = store.load_idea_working(project) if project else {}
    facts = load_facts(project) if project else None
    res = {"constraints": [dict(i) for i in of(idea)],
           "board_facts": "none measured: say planned, never is" if not facts else {
               k: facts.get(k) for k in ("measured_at", "stale", "size", "on_board", "edge_parts", "holes", "keepouts",
                                         "copper_under_keepout", "drc_total", "requirements")}}
    if facts and facts.get("stale"):
        res["board_facts"]["note"] = "the board file changed since this was measured"
    return res


# ---------------------------------------------------------------- the agent's action and the student's edit

def _save(project, c):
    import store
    idea = store.load_idea_working(project)
    idea["constraints"] = validate(c)
    store.save_idea_draft(project, idea)
    return idea["constraints"]


@ext.register("action")
def _idea_constrain(project, action, ctx):
    """idea.constrain {op: add|update|remove, item: {...}}: writes PROPOSED items into the idea draft; the student confirms them all
    with the one Save of the idea (nothing is asked item by item)."""
    if action.get("type") != "idea.constrain":
        return None
    import store
    op = action.get("op") or "add"
    item = action.get("item")
    if op not in ("add", "update", "remove") or not isinstance(item, dict):
        raise ValueError("idea.constrain needs op (add, update or remove) and item {kind, ...}")
    cur = validate(store.load_idea_working(project).get("constraints"))["items"]
    if op == "remove":
        keep = [i for i in cur if i["id"] != item.get("id")]
        if len(keep) == len(cur):
            raise ValueError(f"no constraint {item.get('id')}")
        _save(project, {"items": keep})
        return f"idea.constrain:remove {item.get('id')}"
    new = dict(item, by="agent", status="proposed")
    if op == "update":
        if not any(i["id"] == item.get("id") for i in cur):
            raise ValueError(f"no constraint {item.get('id')}")
        merged = [dict(i, **new) if i["id"] == item["id"] else i for i in cur]
    else:
        merged = cur + [new]
    saved = _save(project, {"items": merged})
    got = [i for i in saved["items"] if i["id"] == item.get("id")] or saved["items"][-1:]
    return f"idea.constrain:{op} {got[0]['id']} (proposed; the student confirms with Save)"


@ext.register("post")
def _post(handler, path, data):
    if path != "/api/idea/constraints":
        return None
    items = (data or {}).get("items")
    if not isinstance(items, list):
        raise ext.HTTPError(400, "items must be a list")
    proj = handler.project()
    try:
        c = _save(proj, {"items": [dict(i, by=i.get("by") or "student") for i in items if isinstance(i, dict)]})
    except ValueError as exc:
        raise ext.HTTPError(400, str(exc)) from exc
    return {"ok": True, "constraints": c}
