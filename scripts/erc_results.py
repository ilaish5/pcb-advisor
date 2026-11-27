"""What Altium's own electrical rules check (Compile / ERC) said about the schematic, kept. Every "Check schematic in Altium" run appends
one record to projects/<p>/erc-log.jsonl (append-only), so the answer outlives the page's toast and the page reload.

    {"ts", "op": "erc", "ok", "prj", "inputs": {sheet: sha256, "(ERC settings)": sha256},
     "erc": {"complete", "clean", "errors", "warnings", "total", "kinds", "rows": [{level, class, document, message, kind, object,
             "location"}], "problems", "levels_from", "unsaved", "line", "report"} | None, "warnings": [...], "error"}

The record restates what bridge.erc_check returned (the parse of the report file Altium wrote; nothing is guessed). `public()` is what
the page reads: the counts (errors / warnings / total) are given ONLY when the report was read in full (complete), and a failed or
partly read run says so (`state` "unchecked") and never "clean". `stale` is true when a schematic sheet or the project's ERC settings
changed since the run (the sheet files are hashed by lineage.sha256_file, memoised on path / size / mtime, so a poll reads nothing new).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402

LOG = "erc-log.jsonl"
MAX_ROWS = 1000          # a project with more messages than this keeps the first ones; the counts are the full ones


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _erc_of(res):
    """The record's erc block from a bridge.erc_check result; None when the result is not one (never a guess)."""
    if not isinstance(res, dict) or "complete" not in res:
        return None
    complete = res.get("complete") is True
    rows = [r for r in (res.get("rows") or []) if isinstance(r, dict)][:MAX_ROWS]
    return {"complete": complete, "clean": bool(res.get("clean")) and complete,
            "errors": _int(res.get("n_errors")) if complete else None, "warnings": _int(res.get("n_warnings")) if complete else None,
            "total": _int(res.get("total")) if complete else None, "kinds": dict(res.get("kinds") or {}) if complete else None,
            "rows": rows, "problems": [str(p) for p in (res.get("problems") or [])][:20], "levels_from": res.get("levels_from") or "",
            "unsaved": list(res.get("unsaved") or []), "line": str(res.get("line") or ""), "report": str(res.get("report") or "")}


def record(project, step, res, ok=True, error=""):
    """Append the record of a finished Check schematic step (`step` "erc"; other steps are ignored). Returns the record, or None when the
    step is not ours. Never raises: a log that cannot be written is not a failed step."""
    if step != "erc":
        return None
    try:
        res = res if isinstance(res, dict) else {}
        rec = {"ts": store.now_ms(), "op": "erc", "ok": bool(ok), "prj": _prj(project), "inputs": dict(res.get("inputs") or {}),
               "erc": _erc_of(res) if ok else None, "warnings": [str(w) for w in (res.get("warnings") or [])][:40]}
        if error:
            rec["error"] = str(error)[:600]
        return store.append(project, LOG, rec)
    except Exception:       # noqa: BLE001
        return None


def _prj(project):
    try:
        import project as project_mod
        return str(project_mod.altium_link(project).get("project_file") or "")
    except Exception:       # noqa: BLE001
        return ""


def records(project):
    try:
        return store.read_jsonl(store.pdir(project) / LOG)
    except Exception:       # noqa: BLE001
        return []


def _stale(project, rec):
    """True when the schematic (or the project's ERC settings) is not what the record was made from, or cannot be read now."""
    if not rec:
        return False
    try:
        from altium import bridge
        prj = _prj(project)
        if not prj or not pathlib.Path(prj).is_file() or not rec.get("inputs"):
            return True
        return bridge.erc_inputs(prj) != rec["inputs"]
    except Exception:       # noqa: BLE001
        return True


def latest(project):
    """The newest record (with "stale" and "seq"), or None when no check was ever run."""
    recs = records(project)
    if not recs:
        return None
    rec = {**recs[-1], "seq": len(recs) - 1}
    rec["stale"] = _stale(project, rec) if rec.get("ok") else False
    return rec


def public(project):
    """What the page shows, or None when no check was run. `state`: "clean" (complete, no violations), "violations" (complete, some),
    "unchecked" (the run failed, or the report was not read in full: no count, no clean). `counts` is the dict {errors, warnings,
    total} only for a complete report."""
    rec = latest(project)
    if not rec:
        return None
    erc = rec.get("erc") or {}
    complete = bool(rec.get("ok") and erc.get("complete"))
    if not complete:
        state = "unchecked"
    else:
        state = "clean" if erc.get("clean") else "violations"
    out = {"ts": rec.get("ts"), "seq": rec.get("seq"), "ok": bool(rec.get("ok")), "state": state, "complete": complete,
           "stale": bool(rec.get("stale")), "error": rec.get("error") or "", "warnings": list(rec.get("warnings") or []),
           "problems": list(erc.get("problems") or []), "unsaved": list(erc.get("unsaved") or []),
           "levels_from": erc.get("levels_from") or "", "line": erc.get("line") or "",
           "counts": ({"errors": erc.get("errors"), "warnings": erc.get("warnings"), "total": erc.get("total")} if complete else None),
           "kinds": erc.get("kinds") if complete else None, "rows": list(erc.get("rows") or []) if complete else []}
    if not complete and not out["error"]:
        out["error"] = "Altium's ERC report was not read in full: " + ("; ".join(out["problems"]) or "no readable report")
    return out


def run_erc(project, bridge):
    """The Check schematic step: bridge.run_erc (Altium's own ERC, read from its report file). Returns its dict plus the line the page shows."""
    res = dict(bridge.run_erc(project))
    res.setdefault("line", bridge.erc_line(res))
    return res


def erc_summary(res):
    line = res.get("line") or ""
    return f"Electrical rules check: {line}" if line else "Electrical rules check finished"
