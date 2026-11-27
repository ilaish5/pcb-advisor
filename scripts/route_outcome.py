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


def _open_nets(res):
    out = []
    for n in list(res.get("failed") or []) + list(res.get("saved_open") or []) + list(res.get("open_nets") or []):
        out.append(str(n[0] if isinstance(n, (list, tuple)) else n))
    return list(dict.fromkeys(out))


def kind_of(res, total):
    """The kind of rejection, read from what the bridge said: "drc" (new violations of the rejecting check), "open_nets", "width", "pour",
    "readback", "unchecked", or "other". Each has its own title and next step; the bridge's own words stay as the reason."""
    if total:
        return "drc"
    text = " | ".join(str(p) for p in res.get("problems") or []).lower()
    if _open_nets(res) or "not routed" in text or "un-routed" in text:
        return "open_nets"
    if "width" in text or "narrow" in text:
        return "width"
    if "pour" in text or "plane" in text:
        return "pour"
    if "read back" in text:
        return "readback"
    if "could not be read in full" in text or "unchecked" in text:
        return "unchecked"
    return "other"


def reason_of(res):
    """The bridge's own reason, kept: its problems, each cut at a word, never replaced by a generic sentence."""
    out = []
    for p in (res.get("problems") or [])[:3]:
        t = " ".join(str(p).split())
        out.append(t if len(t) <= 200 else t[:200].rsplit(" ", 1)[0] + " ...")
    return "; ".join(out)


_TITLES = {"open_nets": "Route rejected: some nets could not be routed", "width": "Route rejected: tracks would be narrower than the current needs",
           "pour": "Route rejected: the copper pour or plane did not come out", "readback": "Route rejected: the board could not be read back after drawing",
           "unchecked": "Route rejected: the board check could not be read in full", "other": "Route rejected"}
_NEXT = {"open_nets": "Make room near the open nets (move a part, or free a layer), then route again",
         "width": "Check the net currents and the track widths, then route again",
         "pour": "Look at the pour reason above, fix it in Altium, then route again",
         "readback": "Open the board in Altium and look at it, then route again",
         "unchecked": "Run the design rule check in Altium and look at its list, then route again",
         "other": "Look at the reason above, fix what it names, then route again"}


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
        kind = kind_of(res, total)
        bk = backup_file(res, pcb)
        bsha, csha = (sha256_of(bk) if bk else ""), (sha256_of(pcb) if pcb else "")
        verified = bool(bsha) and bsha == csha
        nets = _open_nets(res)
        if kind == "drc":
            title = title_of(rows, total)
            cause = "; ".join(r["words"] for r in rows[:6]) + (f"; and {len(rows) - 6} more pairs" if len(rows) > 6 else "")
            count = total
            first = "Move the parts named above, then route again" if any(r.get("a") for r in rows) else _NEXT["other"]
        else:
            title = _TITLES[kind]
            if kind == "open_nets" and nets:
                title = f"Route rejected: {_plural(len(nets), 'net')} could not be routed ({', '.join(nets[:5])}{' ...' if len(nets) > 5 else ''})"
            cause = reason_of(res)
            count = len(nets) if kind == "open_nets" and nets else len(res.get("problems") or [])
            first = _NEXT[kind]
        restored = (f"Restored from backup: the board file is the same as before the route (checked, sha256 {csha[:12]})." if verified else
                    "The board file could NOT be confirmed as restored: it differs from the backup. Look at the file in Altium before going on.")
        nxt = [{"id": "findings", "label": "See the problems in Findings"}, {"id": "route_again", "label": first}]
        if kind == "open_nets" or res.get("partial_offer"):
            nxt.append({"id": "partial", "label": "Route the rest and leave the failed nets open"})
        out = {"rejected": True, "kind": kind, "title": title, "count": count or None, "causes": rows[:30], "cause_text": cause, "restored": verified,
               "restored_claimed": bool(res.get("restored")), "backup_sha256": bsha, "pcb_sha256": csha, "next": nxt,
               "message": f"{title}. {restored}" + (f" Cause: {cause}." if cause else ""), "restored_text": restored}
        try:
            import ledger
            it = ledger.add(project, f"route:{csha[:16] or bsha[:16] or 'x'}", "hand_step", title,
                            (f"Cause: {cause}. " if cause else "") + first + ", by pressing Route board.",
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
            return {"rejected": True, "title": "Route rejected", "count": None, "causes": [], "cause_text": "", "restored": False,
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
