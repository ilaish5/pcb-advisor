"""Where a design rule violation comes from: the part's own footprint, the router, or the placement.

Altium's report lines name the objects ("Pad J1-3(10mm,4mm) Top Layer And Pad J1-4(...)", "Via (x,y) ... And Track (...)"). From
those names alone a violation is classified:

    footprint  two pads of the SAME part (a fine-pitch footprint: nothing the router or the placement can change)
    router     a via or a track is one of the objects (the router drew it)
    placement  pads of two different parts
    placement  also: one pad with text, a region or a hole (objects are named, one is not a router object)
    unknown    the line names no object at all (never guessed)

classify() gives the violations per rule with these origins; table() joins them with the JLC map into the table the student
and the agent read: {rule, n, by_origin, jlc, jlc_level, explained}. "explained" = every violation of the rule has an origin.
"""
import re

from checks import drc_jlc_map

_PAD = re.compile(r"\bPad\s+([A-Za-z]+\d+)\s*-\s*([A-Za-z0-9_.+-]+)", re.I)
_ROUTER = re.compile(r"\b(Via|Track|Arc)\b", re.I)


def origin(message):
    """The origin of one violation line ("Rule: text"), see the module doc."""
    text = str(message)
    if _ROUTER.search(text):
        return "router"
    pads = _PAD.findall(text)
    if len(pads) >= 2:
        return "footprint" if len({r.upper() for r, _ in pads}) == 1 else "placement"
    try:       # a line that names objects but not two pads (a pad and text or a region, a polygon, a hole): placement or the board's own copper
        import violation_pairs
        named = violation_pairs.objects(text)
    except Exception:       # noqa: BLE001
        named = ()
    if named:
        return "placement"
    return "unknown"


def classify(violations, doc=None):
    """{rule short name: {"n", "by_origin": {origin: n}, "examples": [first 3 lines]}} from the report's violation lines."""
    out = {}
    for v in violations or []:
        rule, _, rest = str(v).partition(":")
        key = drc_jlc_map.short(rule) or "unknown rule"
        e = out.setdefault(key, {"n": 0, "by_origin": {}, "examples": []})
        o = origin(rest or v)
        e["n"] += 1
        e["by_origin"][o] = e["by_origin"].get(o, 0) + 1
        if len(e["examples"]) < 3:
            e["examples"].append(str(v)[:200])
    return out


def table(drc, doc=None):
    """Rows for the DRC result {"rules": {name: count}, "violations": [...]}: one per rule that has violations, largest first.
    n is the report's own count; when the report lists fewer detail lines than that, the difference is "unlisted" (not explained)."""
    if not isinstance(drc, dict):
        return []
    by_rule = classify(drc.get("violations"), doc)
    rows = []
    counts = {}
    for name, n in (drc.get("rules") or {}).items():
        k = drc_jlc_map.short(name)
        counts[k] = counts.get(k, 0) + n
    for k, n in counts.items():
        if not n:
            continue
        got = by_rule.get(k, {"n": 0, "by_origin": {}, "examples": []})
        by_origin = dict(got["by_origin"])
        if n > got["n"]:
            by_origin["unlisted"] = n - got["n"]
        item = drc_jlc_map.jlc_item(k)
        rows.append({"rule": k, "n": n, "by_origin": by_origin, "jlc": item, "jlc_level": drc_jlc_map.level(k),
                     "explained": "unknown" not in by_origin and "unlisted" not in by_origin, "examples": got["examples"]})
    return sorted(rows, key=lambda r: -r["n"])


def new_unwatched(before, after, watched):
    """Rules NOT in `watched` (bridge.DRC_WATCHED) whose count rose from `before` to `after` ({rule: count} dicts, full rule text
    keys): ["Minimum Solder Mask Sliver 7 -> 21 (+14)"]. The pass criteria of a route do not change; this only says what they miss."""
    def fold(d):
        out = {}
        for name, n in (d or {}).items():
            if not any(str(name).startswith(w) for w in watched):
                out[drc_jlc_map.short(name)] = out.get(drc_jlc_map.short(name), 0) + n
        return out
    b, a = fold(before), fold(after)
    return [f"{k} {b.get(k, 0)} -> {n} (+{n - b.get(k, 0)})" for k, n in sorted(a.items()) if n > b.get(k, 0)]
