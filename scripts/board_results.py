"""Stream A: what Altium said about the board, kept. Every place / route / DRC / outputs run appends one record to
projects/<p>/board-log.jsonl (append-only), so the answer outlives the page's toast and the page reload.

    {"ts", "op": "place|route|drc|outputs", "ok", "pcb", "pcb_sha256",
     "drc": {"rules": {...}, "total", "unrouted", "clean", "violations": [...]} | None,
     "summary": {"placed", "routed", "failed", "tracks", "vias", "open_nets", "files"}, "warnings": [...], "error"}

The record only restates fields of the bridge's result dicts (nothing is guessed). `latest()` is what the stage model reads:
the newest record of each op and `board_check`, the newest successful record that carries a design rule check, with `stale` true
when the PcbDoc has changed since (size / mtime / hash differ). Reading is by stat only; the PcbDoc is hashed when a record is written.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402

LOG = "board-log.jsonl"
OPS = ("place", "route", "drc", "outputs")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _drc_of(op, res):
    """The design rule check carried by a result, in the record's shape; None when the result has none (never a guess)."""
    if op == "drc":
        if not isinstance(res, dict) or "total" not in res:
            return None
        return {"rules": dict(res.get("rules") or {}), "total": _int(res.get("total")), "unrouted": _int(res.get("unrouted")) or 0,
                "clean": bool(res.get("clean")), "complete": bool(res.get("complete")), "violations": list(res.get("violations") or [])}
    if op == "route" and isinstance(res, dict) and res.get("drc_total") is not None:
        rules = dict(res.get("drc_rules") or {})
        return {"rules": rules, "total": _int(res.get("drc_total")), "unrouted": sum(n for k, n in rules.items() if k.startswith("Un-Routed Net")),
                "clean": bool(res.get("drc_clean")), "complete": bool(res.get("drc_complete")), "violations": []}
    return None


def _summary_of(op, res):
    if not isinstance(res, dict):
        return {}
    if op == "place":
        return {"placed": len(res.get("placed") or [])}
    if op == "route":
        failed = [x[0] if isinstance(x, (list, tuple)) else x for x in res.get("failed") or []]
        return {"routed": len(res.get("routed") or []), "failed": len(failed), "tracks": _int(res.get("tracks")) or 0,
                "vias": _int(res.get("vias")) or 0, "open_nets": list(res.get("open_nets") or failed)}
    if op == "outputs":
        return {"files": len(res.get("files") or [])}
    return {}


def _pcb(project):
    try:
        import lineage
        pcb = lineage.linked_pcb(project)
        return (str(pcb), lineage.sha256_file(pcb)) if pcb else ("", "")
    except Exception:       # noqa: BLE001 - a record is never lost because the file could not be hashed
        return "", ""


def record(project, step, res, ok=True, error=""):
    """Append the record of a finished step. `step` is the button's name (place, route, drc, outputs; others are ignored).
    Returns the record, or None when the step is not one of ours. Never raises: a log that cannot be written is not a failed step."""
    op = {"outputs": "outputs", "place": "place", "route": "route", "drc": "drc"}.get(step)
    if not op:
        return None
    try:
        res = res if isinstance(res, dict) else {}
        pcb, sha = _pcb(project)
        # A DRC record carries the sha of the file it actually checked. A rejected route was checked on the routed board, which the restore
        # has since replaced: that file no longer exists, so its result is NOT stamped on the restored file (it would close or open findings
        # of a board nobody has). The record keeps the step's outcome, without a design rule check.
        rejected = op == "route" and bool(res.get("restored"))
        rec = {"ts": store.now_ms(), "op": op, "ok": bool(ok), "pcb": pcb, "pcb_sha256": sha,
               "drc": _drc_of(op, res) if ok and not rejected else None, "summary": _summary_of(op, res) if ok else {},
               "warnings": [str(w) for w in (res.get("warnings") or [])][:40]}
        if rejected:
            rec["rejected"] = True
        if error:
            rec["error"] = str(error)[:600]
        return store.append(project, LOG, rec)
    except Exception:       # noqa: BLE001
        return None


def rebase_check(project, old_sha, note="the outline was drawn on Mechanical 1 only"):
    """The newest board check was made on the PcbDoc `old_sha`; the file changed since only by a repair that touches no copper (the
    outline drawn on Mechanical 1), so the check still holds: a copy of it is recorded against the file as it is now. Returns the
    new record, or None (no check on that sha, an unchanged file, or a log that cannot be written)."""
    try:
        recs = records(project)
        chk = next((r for r in reversed(recs) if r.get("ok") and r.get("drc") and r["drc"].get("total") is not None), None)
        pcb, sha = _pcb(project)
        if not chk or not old_sha or chk.get("pcb_sha256") != old_sha or not sha or sha == old_sha:
            return None
        rec = {**{k: v for k, v in chk.items() if k not in ("seq", "stale")}, "ts": store.now_ms(), "pcb": pcb, "pcb_sha256": sha,
               "warnings": list(chk.get("warnings") or []) + [note]}
        return store.append(project, LOG, rec)
    except Exception:       # noqa: BLE001
        return None


def records(project):
    try:
        return store.read_jsonl(store.pdir(project) / LOG)
    except Exception:       # noqa: BLE001
        return []


def _stale(project, rec):
    """True when the PcbDoc is not the one the record was made on (or its file cannot be read)."""
    if not rec:
        return False
    try:
        import lineage
        pcb = lineage.linked_pcb(project)
        if not pcb or not rec.get("pcb_sha256"):
            return True
        return lineage.sha256_file(pcb) != rec["pcb_sha256"]        # memoised on (path, size, mtime_ns): a poll that finds nothing new reads no file
    except Exception:       # noqa: BLE001
        return True


def latest(project):
    """{op: newest record (with "stale")} for the four ops, and "board_check": the newest ok record with a design rule check."""
    recs = records(project)
    out = {}
    for i, r in enumerate(recs):
        if r.get("op") in OPS:
            out[r["op"]] = {**r, "seq": i}       # log order: two steps in the same millisecond still have an order
    out = {k: {**v, "stale": _stale(project, v)} for k, v in out.items()}
    chk = next((r for r in reversed(recs) if r.get("ok") and r.get("drc") and r["drc"].get("total") is not None), None)
    out["board_check"] = {**chk, "stale": _stale(project, chk)} if chk else None
    return out


def run_drc(project, bridge):
    """The Check board step: Altium's batch design rule check on the linked PcbDoc (READ_ONLY), the report parsed as the bridge does.
    Returns parse_drc's dict plus warnings and the line the page shows."""
    prj = bridge._linked(project)
    pcb = bridge._project_pcb(project)
    with tempfile.TemporaryDirectory(prefix="advisor-drc-") as tmp:
        res = bridge.run_drc(prj, pcb, pathlib.Path(tmp) / "drc.txt")
    res = dict(res)
    res["drc_line"] = bridge.drc_line(res)
    res["warnings"] = [] if res.get("complete") else ["the design rule check report is incomplete, so the board is not counted as checked"]
    return res


def drc_summary(res):
    line = res.get("drc_line") or ""
    return f"Altium DRC, every rule: {line}" if line else "Altium DRC finished"

