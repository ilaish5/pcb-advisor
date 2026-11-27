"""Before you order: what is still open, counted from what was read back, never from "the step ran" (R2, ACCEPTANCE W33, U3, U7).

    summary(project) -> {"ready": bool, "open": n, "items": [{id, label, count, state, page, why}], "drc": drc_open(project)}

Every number comes from a record of the real artifact: the design rule check Altium wrote for the PcbDoc as it is now (board-log.jsonl,
read back with the PcbDoc sha256), the BOM's pin evidence records, and the requirement rows. A check with no evidence, a check on
an older PcbDoc and a check read only in part are all OPEN, with their state named, and never green. Green (ready) needs every
item at zero and the DRC checked, complete and on the current file.

DRC classes: JLC-reject (a short circuit, an unrouted net: the board is wrong whatever the fab says), cosmetic (silkscreen
rules), unclassified (every other rule: no measured size is on record, so nothing says whether JLC accepts it). Only the owner's
F-H classifier (R4) may move a rule out of unclassified; until then it counts as open.
"""
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402

CLASSES = ("JLC-reject", "JLC-accept", "cosmetic", "unclassified")
_REJECT = ("short-circuit", "un-routed net", "unrouted net")
_COSMETIC = ("silk to silk", "silk to solder mask", "silk to board outline")


def _short(rule):
    """The rule as Altium names it before its parameters: 'Clearance Constraint (Gap=...)' -> 'Clearance Constraint'."""
    return re.split(r"\s*[(:]", str(rule), maxsplit=1)[0].strip()


def drc_class(rule):
    s = _short(rule).lower().replace(" constraint", "")
    if any(s.startswith(x) for x in _REJECT):
        return "JLC-reject"
    if any(s.startswith(x) for x in _COSMETIC):
        return "cosmetic"
    return "unclassified"


def drc_open(project):
    """The design rule check of the PcbDoc as it is now:
    {state: not_checked|stale|partial|checked, total, by_rule, by_class, pcb_sha256, scope, why}. The counts are Altium's own report
    (every rule it ran), so the scope says which rules and how many violations; `by_class` sums to `total`."""
    try:
        import board_results
        chk = (board_results.latest(project) or {}).get("board_check")
    except Exception:       # noqa: BLE001 - no readable log is no check
        chk = None
    out = {"state": "not_checked", "total": None, "by_rule": {}, "by_class": {c: 0 for c in CLASSES}, "pcb_sha256": "", "scope": "",
           "why": "no design rule check of the PcbDoc is on record"}
    if not chk:
        return out
    d = chk.get("drc") or {}
    rules = {}
    for k, n in (d.get("rules") or {}).items():
        if n:
            rules[_short(k)] = rules.get(_short(k), 0) + n
    total = d.get("total")
    by_class = {c: 0 for c in CLASSES}
    for k, n in rules.items():
        by_class[drc_class(k)] += n
    listed = sum(rules.values())
    if isinstance(total, int) and total > listed:
        by_class["unclassified"] += total - listed          # a count the rule table does not explain is never dropped
    out.update(total=total, by_rule=rules, by_class=by_class, pcb_sha256=chk.get("pcb_sha256") or "",
               scope=f"Altium design rule check, {len(rules)} rule(s) with violations, {total} violation(s) in all")
    if chk.get("stale"):
        out.update(state="stale", why="the PcbDoc changed since this check: it says nothing about the file as it is now")
    elif d.get("complete") is False:
        out.update(state="partial", why="the check report was not read in full, so the counts are a lower bound")
    elif not isinstance(total, int):
        out.update(state="partial", why="the check gave no total")
    else:
        out.update(state="checked", why="")
    return out


def unchecked_pin_lines(project, bom=None):
    """BOM lines (buyable, on the board) whose pins no datasheet pin table checked and no student accepted: evidence record absent,
    stale or partial. A part with nothing to check (an unpolarised two-terminal passive) is not counted."""
    out = []
    for l in (store.bom(project, write=False) if bom is None else bom):
        if not l.get("refs") or l.get("dnp") or l.get("nobuy"):
            continue
        st = l.get("pins_status")
        if st in ("accepted", "not_applicable"):
            continue
        if st == "verified" and l.get("pins_basis") == "datasheet" and l.get("pins_evidence"):
            continue
        out.append(l["key"])
    return out


def open_conditions(project):
    """Confirmed requirements that are not met on the board as it is now (violated, or unverifiable because the board was not
    measured or changed since)."""
    try:
        import constraints
        return [r for r in constraints.requirement_rows(project) if r.get("status") != "met"]
    except Exception as e:       # noqa: BLE001 - the conditions could not be read: that is not "0 open", it is unchecked, with the reason
        return [{"id": UNREAD, "status": "not_checked", "why": f"{type(e).__name__}: {e}"[:200]}]


UNREAD = "conditions_unread"


def summary(project, bom=None):
    drc = drc_open(project)
    items = []
    if drc["state"] != "checked":
        items.append({"id": "drc_state", "label": "Board check " + drc["state"].replace("_", " "), "count": 1, "state": drc["state"],
                      "page": "pcb", "why": drc["why"]})
    rej, unc, cos = drc["by_class"]["JLC-reject"], drc["by_class"]["unclassified"], drc["by_class"]["cosmetic"]
    if rej:
        items.append({"id": "drc_reject", "label": f"{rej} DRC violation(s) JLC would reject", "count": rej, "state": "open", "page": "pcb",
                      "why": "short circuits and unrouted nets"})
    if unc:
        items.append({"id": "drc_unclassified", "label": f"{unc} DRC violation(s) not classified", "count": unc, "state": "open", "page": "pcb",
                      "why": "no measured size on record: nobody has said whether JLC accepts them"})
    if cos:
        items.append({"id": "drc_cosmetic", "label": f"{cos} cosmetic DRC violation(s)", "count": cos, "state": "open", "page": "pcb", "why": ""})
    pins = unchecked_pin_lines(project, bom)
    if pins:
        items.append({"id": "unverified_parts", "label": f"{len(pins)} part(s) with pins not checked against a datasheet", "count": len(pins),
                      "state": "open", "page": "checks", "why": ", ".join(pins[:12])})
    conds = open_conditions(project)
    if conds and conds[0].get("id") == UNREAD:
        items.append({"id": "open_conditions", "label": "Requirement conditions not checked", "count": 1, "state": "not_checked", "page": "pcb",
                      "why": "the requirement rows could not be read: " + str(conds[0].get("why"))})
    elif conds:
        items.append({"id": "open_conditions", "label": f"{len(conds)} requirement condition(s) not met or not measured",
                      "count": len(conds), "state": "open", "page": "pcb", "why": ", ".join(str(r.get("id")) for r in conds[:12])})
    return {"ready": not items, "open": sum(i["count"] for i in items), "items": items, "drc": drc}


def manifest_block(project):
    """What the order manifest states about the open DRC items: the same numbers the Outputs page shows, for the PcbDoc sha256 they
    were counted on, with the scope. Class counts and the per-rule counts both sum to the total."""
    drc = drc_open(project)
    return {"state": drc["state"], "pcb_sha256": drc["pcb_sha256"], "total": drc["total"], "scope": drc["scope"] or drc["why"],
            "drc_open_by_rule": drc["by_rule"], "drc_by_class": drc["by_class"]}


# ---------------------------------------------------------------- "make anyway": a per-run decision that names what stays open
OVERRIDE = "outputs-override.json"


def _override_path(project):
    return store.pdir(project) / OVERRIDE


def override_current(project):
    """The Make anyway record when it covers the check as it is now (same PcbDoc sha256, same JLC-reject count), else None. It is not used
    up by a run: Generate outputs and the Gerber zip both read it, so the zip step is not refused after the files were made. A new
    PcbDoc or a different count ends it, and the student is asked again."""
    drc = drc_open(project)
    if drc["state"] != "checked" or not drc["by_class"]["JLC-reject"]:
        return None
    try:
        rec = store.json.loads(_override_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if rec.get("pcb_sha256") == drc["pcb_sha256"] and rec.get("reject") == drc["by_class"]["JLC-reject"]:
        return rec
    return None


def reject_block(project):
    """"" when no JLC-reject DRC item is open on the current PcbDoc, or the student pressed Make anyway for exactly this check; else
    the refusal, with the count and the way past it. (Unrouted nets are route_block's: this adds the other rejects, e.g. shorts.)"""
    drc = drc_open(project)
    n = drc["by_class"]["JLC-reject"] if drc["state"] == "checked" else 0
    if not n:
        return ""
    if override_current(project):
        return ""
    rules = ", ".join(f"{k} {v}" for k, v in drc["by_rule"].items() if drc_class(k) == "JLC-reject")
    return (f"Not made yet: the board check has {n} violation(s) JLC would reject ({rules}). Fix them on the Layout page, "
            "or press Make anyway: the files are made once and the order manifest lists these open items.")


def make_anyway(project):
    """The student's one-run decision: remember which check (PcbDoc sha256, reject count) it covers and which items stay open."""
    drc = drc_open(project)
    rec = {"ts": store.now(), "pcb_sha256": drc["pcb_sha256"], "reject": drc["by_class"]["JLC-reject"],
           "open_by_rule": {k: v for k, v in drc["by_rule"].items() if drc_class(k) == "JLC-reject"}}
    store._write_text(_override_path(project), store.json.dumps(rec, indent=2))
    return rec


def consume_override(project):
    """The recorded decision that covers the check now (for the manifest of the run that just made the files), or None. Not removed here:
    the zip step after the files must pass the same gate; the record lapses by itself when the PcbDoc or the count changes."""
    return override_current(project)
