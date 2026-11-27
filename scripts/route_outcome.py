"""U4: a rejected route is not a dead end. The route step puts the board file back when Altium's check finds new problems; this module
turns that answer into the end message the student reads:

  * the cause in words, as object pairs with a count that is the number of NEW violation lines of the rejecting check;
  * "restored from backup", said only when the backup's sha256 equals the PcbDoc on disk now (read here, not taken from a flag);
  * at least one next action, and a ledger item for the problems so they do not live in the chat only.

Nothing here talks to Altium. `build` reads the step's result dict and two files.
"""
import collections
import hashlib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import violation_pairs as vp  # noqa: E402

_RULE_WORDS = {"Clearance": "clearance", "Short-Circuit": "short", "Un-Routed Net": "unrouted connection", "Width": "track width",
               "Minimum Annular Ring": "annular ring", "Board Outline Clearance": "board edge clearance",
               "Silk To Solder Mask Clearance": "silk over a pad", "Hole To Hole Clearance": "hole spacing"}


def sha256_of(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def new_lines(res):
    """The violation lines of the rejecting check that the board did not have before the route (a multiset difference)."""
    after = collections.Counter(str(x) for x in res.get("drc_violations") or [])
    before = collections.Counter(str(x) for x in res.get("drc_violations_before") or [])
    out = []
    for line, n in after.items():
        out += [line] * max(0, n - before.get(line, 0))
    return out


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def causes(res):
    """[{"rule", "a", "b", "count", "words"}] one row per rule and object pair, and the total of NEW violations."""
    lines = new_lines(res)
    rows = vp.group(lines)
    total = len(lines)
    if not lines:        # a result with no detail lines (older bridge answer): the rules' own counts, said as such
        after, before = res.get("drc_after") or {}, res.get("drc_before") or {}
        for rule, n in after.items():
            d = int(n or 0) - int(before.get(rule, 0) or 0)
            if d > 0:
                rows.append({"rule": vp.rule_of(rule), "a": "", "b": "", "count": d, "example": ""})
                total += d
    for r in rows:
        r["words"] = vp.pair_words(r)
    return rows, total


def title_of(rows, total):
    by = collections.Counter()
    for r in rows:
        by[r["rule"]] += r["count"]
    if not by:
        return "Route rejected: the board check found new problems"
    parts = [f"{_plural(n, _RULE_WORDS.get(rule, rule.lower() or 'problem'))}" for rule, n in by.most_common(2)]
    more = len(by) - 2
    t = "Route rejected: " + " and ".join(parts) + (f" and {more} more kinds" if more > 0 else "")
    return t if len(t) <= 70 else f"Route rejected: {_plural(total, 'new problem')}"


def backup_file(res, pcb):
    b = res.get("backup")
    return pathlib.Path(str(b)) / pathlib.Path(str(pcb)).name if b and pcb else None


def build(project, res, pcb=None):
    """The outcome of a rejected route, or None when the route was not rejected (nothing restored). Never raises."""
    try:
        if not isinstance(res, dict) or not res.get("restored"):
            return None
        if pcb is None:
            import lineage
            pcb = lineage.linked_pcb(project)
        rows, total = causes(res)
        bk = backup_file(res, pcb)
        bsha, csha = (sha256_of(bk) if bk else ""), (sha256_of(pcb) if pcb else "")
        verified = bool(bsha) and bsha == csha
        title = title_of(rows, total)
        cause = "; ".join(r["words"] for r in rows[:6]) + (f"; and {len(rows) - 6} more pairs" if len(rows) > 6 else "")
        restored = (f"Restored from backup: the board file is the same as before the route (checked, sha256 {csha[:12]})." if verified else
                    "The board file could NOT be confirmed as restored: it differs from the backup. Look at the file in Altium before going on.")
        nxt = [{"id": "findings", "label": "See the problems in Findings"},
               {"id": "route_again", "label": "Move the parts named above, then route again"}]
        if res.get("partial_offer") or res.get("saved_open"):
            nxt.append({"id": "partial", "label": "Route the rest and leave the failed nets open"})
        out = {"rejected": True, "title": title, "count": total, "causes": rows[:30], "cause_text": cause, "restored": verified,
               "restored_claimed": bool(res.get("restored")), "backup_sha256": bsha, "pcb_sha256": csha, "next": nxt,
               "message": f"{title}. {restored}" + (f" Cause: {cause}." if cause else ""), "restored_text": restored}
        try:
            import ledger
            it = ledger.add(project, f"route:{csha[:16] or bsha[:16] or 'x'}", "hand_step", title,
                            (f"Cause: {cause}. " if cause else "") + "Move or rework the parts named, then press Route board again.",
                            page="pcb", check={"type": "manual"}, source="route", severity="warn")
            out["ledger_id"] = it["id"]
        except Exception:       # noqa: BLE001 - the answer is never lost because the ledger could not be written
            pass
        return out
    except Exception as exc:       # noqa: BLE001
        print(f"(route outcome not built: {type(exc).__name__}: {exc})", file=sys.stderr)
        if isinstance(res, dict) and res.get("restored"):         # the worst case has its own plain message, never a raw path or a trace
            msg = ("The route was rejected. The tool could not read the board files to confirm that the board was put back, so it cannot "
                   "say it was restored. Look at the file in Altium before going on.")
            return {"rejected": True, "title": "Route rejected", "count": 0, "causes": [], "cause_text": "", "restored": False,
                    "restored_claimed": True, "backup_sha256": "", "pcb_sha256": "", "next": [{"id": "findings", "label": "See the problems in Findings"}],
                    "message": msg, "restored_text": msg}
        return None


def attach(project, res):
    """Put the outcome on the step's result and make its message the summary (the raw summary stays as `summary_raw`)."""
    o = build(project, res)
    if o:
        res["outcome"] = o
        res["summary_raw"] = res.get("summary", "")
        res["summary"] = o["message"]
    return res


def has_noise(text):
    """True when text holds what the collapsed message must not: paths, error classes, script names, hex codes, float noise."""
    return bool(re.search(r"[A-Za-z]:\\|\\\\|\.py\b|\.pas\b|\.js\b|Error\b|0x[0-9A-Fa-f]+|\d\.\d{5,}", text or ""))
