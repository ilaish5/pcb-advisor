"""
The design report and the archive: what was made, from which inputs, which checks passed, which risks were accepted.

A final project needs one paper that says this, and a way to get the same board back. Both are derived from what the
project holds now (nothing is typed in by hand), so they cannot drift from the design:

    exports/<p>_design_report.md    for reading and printing; exports/<p>_design_report.json for the machine
    archive/<p>_<time>.zip          the Altium project files, the outputs, the exports, the report, the lineage log

The report carries the sha256 of every Altium project file. Compared with the previous report it names the files that
changed in between: a hand edit in Altium has a fingerprint, so "the board as ordered" can be told from "the board now".
Every section that cannot be read says so; nothing is left out silently.

    python scripts/design_report.py <project> [report | archive]
"""
import datetime as dt
import json
import pathlib
import sys
import zipfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lineage  # noqa: E402
import project as project_mod  # noqa: E402
import store  # noqa: E402
import workspace  # noqa: E402

ALTIUM_SUFFIXES = (".prjpcb", ".schdoc", ".pcbdoc", ".pcblib", ".schlib", ".outjob", ".rul")
MAX_FILE_MB = 50
SKIP_PARTS = {".advisor-backup", "history", "__history", "__previews", ".git"}


def _prj(project: str) -> pathlib.Path | None:
    p = project_mod.altium_link(project).get("project_file")
    return pathlib.Path(p) if p and pathlib.Path(p).is_file() else None


def altium_files(project: str) -> list[dict[str, Any]]:
    """The Altium project's own files with their sha256: the project file and every document it lists, plus the libraries and
    the rule file beside it. [{name, path, bytes, modified, sha256}], sorted by name."""
    prj = _prj(project)
    if not prj:
        return []
    found: dict[str, pathlib.Path] = {str(prj): prj}
    try:
        for f in prj.parent.iterdir():
            if f.is_file() and f.suffix.lower() in ALTIUM_SUFFIXES:
                found[str(f)] = f
    except OSError:
        pass
    out = []
    for f in sorted(found.values(), key=lambda p: p.name.lower()):
        try:
            st = f.stat()
            out.append({"name": f.name, "path": str(f), "bytes": st.st_size, "sha256": lineage.sha256_file(f),
                        "modified": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
        except OSError:
            out.append({"name": f.name, "path": str(f), "bytes": None, "sha256": "", "modified": "", "unreadable": True})
    return out


def changed_since(previous: list[dict], now: list[dict]) -> list[dict[str, str]]:
    """Files whose sha256 differs from the previous report's (edited by hand in Altium, or by a step), added, or gone."""
    was = {f["name"]: f.get("sha256", "") for f in previous or []}
    cur = {f["name"]: f.get("sha256", "") for f in now}
    out = [{"name": n, "change": "edited" if n in was else "added", "was": was.get(n, ""), "now": s}
           for n, s in cur.items() if was.get(n) != s]
    out += [{"name": n, "change": "gone", "was": s, "now": ""} for n, s in was.items() if n not in cur]
    return sorted(out, key=lambda c: c["name"].lower())


def _safe(fn, what: str):
    """A section that cannot be read says why instead of vanishing: (value, '') or (None, reason)."""
    try:
        return fn(), ""
    except Exception as exc:
        return None, f"{what} could not be read ({type(exc).__name__}: {exc})"


def _paths(project: str) -> tuple[pathlib.Path, pathlib.Path]:
    base = workspace.safe_name(project)
    exp = store.pdir(project) / "exports"
    return exp / f"{base}_design_report.md", exp / f"{base}_design_report.json"


def collect(project: str) -> dict[str, Any]:
    """Everything the report says, as data."""
    import dfm
    import order_options
    import outputs_check
    import pin_decisions
    gaps: list[str] = []

    def keep(res):
        val, why = res
        if why:
            gaps.append(why)
        return val

    meta = project_mod.load_meta(project)
    idea = keep(_safe(lambda: store.load_idea(project), "the idea")) or {}
    bom = keep(_safe(lambda: store.bom(project, write=False), "the BOM")) or []
    unverified = keep(_safe(lambda: store.pins_to_resolve(project), "the pin check")) or []
    risks = keep(_safe(lambda: pin_decisions.risks(project), "the accepted risks")) or []
    import board_results
    latest = keep(_safe(lambda: board_results.latest(project), "the board check")) or {}
    drc = (latest.get("board_check") or {}) if isinstance(latest, dict) else {}
    dfm_reports = keep(_safe(lambda: dfm.list_checks(project), "the DFM reports")) or []
    lin = keep(_safe(lambda: lineage.status(project), "the output lineage")) or []
    files = altium_files(project)
    prev = None
    try:
        prev = json.loads(_paths(project)[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {
        "project": project, "title": meta.get("title") or project, "generated": store.now(),
        "tool_version": lineage._version(),
        "design": {"idea_title": (idea or {}).get("title") if isinstance(idea, dict) else None,
                   "board": project_mod.board(project), "bom_lines": len(bom), "sheets": len(store.sheet_ids(project)),
                   "parts": [{"refs": l.get("refs", []), "mpn": l.get("mpn"), "lcsc": l.get("lcsc") or l.get("code") or "",
                              "pins": l.get("pins_status")} for l in bom if l.get("refs")]},
        "order": order_options.get(project),
        "altium_files": files,
        "changed_since_previous_report": changed_since((prev or {}).get("altium_files", []), files) if prev else None,
        "previous_report": (prev or {}).get("generated"),
        "outputs": [{"name": r.get("name"), "status": r.get("status"), "reasons": r.get("reasons", []),
                     "made_from": [i.get("role") for i in r.get("inputs", [])]}
                    for r in lin if str(r.get("output", "")).startswith("exports/")],
        "outputs_check": outputs_check.load(project),
        "checks": {
            "pins_unresolved": [{"refs": r.get("refs"), "status": r.get("status")} for r in unverified],
            "board_check": ({"total": (drc.get("drc") or {}).get("total"), "at": drc.get("ts"), "stale": drc.get("stale")}
                            if drc else None),
            "dfm": [{"report": c.get("stem"), "kind": c.get("kind"), "findings": c.get("triage_count"),
                     "open": c.get("triage_open"), "real": c.get("triage_real")} for c in dfm_reports],
        },
        "accepted_risks": risks,
        "unavailable": gaps,
    }


def render_md(d: dict[str, Any]) -> str:
    L = [f"# Design report: {d['title']}", "",
         f"Generated {d['generated']} by the PCB Advisor (version {d.get('tool_version') or 'unknown'}). "
         "Everything below is read from the project when this report is made.", ""]
    des = d["design"]
    L += ["## What was designed", f"- {des['bom_lines']} BOM lines on {des['sheets']} sheet(s)."]
    for k, v in sorted((des.get("board") or {}).items()):
        L.append(f"- {k}: {v}")
    o = d["order"]
    L += [f"- Order: {o['boards']} board(s), {'with assembly (BOM and CPL)' if o['assembly'] else 'bare boards, no assembly'}"
          + ("" if o["set"] else " (default: not chosen yet)"), ""]
    if des["parts"]:
        L += ["## Parts", "| Refs | MPN | LCSC | Pins |", "|---|---|---|---|"]
        L += [f"| {', '.join(p['refs'])} | {p['mpn'] or ''} | {p['lcsc']} | {p['pins'] or ''} |" for p in des["parts"]]
        L.append("")
    L += ["## Made from these Altium files (sha256)"]
    L += [f"- `{f['name']}` {f['sha256'][:16] or 'unreadable'} ({f['modified']})" for f in d["altium_files"]] or ["- no Altium project is linked"]
    ch = d["changed_since_previous_report"]
    if ch is None:
        L.append("- This is the first report: later reports name the files edited in between.")
    elif ch:
        L += [f"- Since the report of {d['previous_report']}: " + ", ".join(f"{c['name']} {c['change']}" for c in ch)
              + ". Edited by hand in Altium or by a step: the board is not the one of the earlier report."]
    else:
        L.append(f"- No Altium file changed since the report of {d['previous_report']}.")
    L.append("")
    L += ["## Outputs"]
    for r in d["outputs"]:
        L.append(f"- `{r['name']}`: {r['status']}" + (f" ({'; '.join(r['reasons'])})" if r["reasons"] else ""))
    oc = d.get("outputs_check")
    if oc:
        L.append(f"- Outputs check of {oc.get('at')}: " + ("every expected output was there." if oc.get("ok") else oc.get("message", "see the warnings")))
        if oc.get("unsaved"):
            L.append(f"- Altium had unsaved changes in {', '.join(oc['unsaved'])} when the outputs were made.")
    elif not d["outputs"]:
        L.append("- No outputs yet.")
    L.append("")
    c = d["checks"]
    L += ["## Checks"]
    L.append("- Pins: " + (f"{len(c['pins_unresolved'])} part(s) still unverified" if c["pins_unresolved"] else "every part verified or accepted"))
    b = c["board_check"]
    L.append("- Board check (Altium DRC): " + (f"{b['total']} violation(s) at {b['at']}" + (" (the board changed since)" if b.get("stale") else "")
                                              if b and b.get("total") is not None else "not run"))
    for r in c["dfm"] or []:
        L.append(f"- JLC DFM report {r['report']} ({r['kind']}): {r['findings']} finding(s), {r['open']} not reviewed, {r['real']} real")
    if not c["dfm"]:
        L.append("- JLC DFM: no report added")
    L.append("")
    L += ["## Accepted risks (decided by the student, not by a datasheet)"]
    L += [f"- {', '.join(r['refs'])} {r.get('mpn') or ''}: {r.get('reason') or r.get('basis') or 'accepted'} ({r.get('ts', '')})"
          for r in d["accepted_risks"]] or ["- none"]
    if d["unavailable"]:
        L += ["", "## Not available", *[f"- {g}" for g in d["unavailable"]]]
    return "\n".join(L) + "\n"


def build(project: str) -> dict[str, Any]:
    """Write exports/<p>_design_report.md and .json; returns {file, json, sections, changed, unavailable}."""
    d = collect(project)
    md, js = _paths(project)
    md.parent.mkdir(parents=True, exist_ok=True)
    store._write_text(md, render_md(d))
    store._write_text(js, json.dumps(d, ensure_ascii=False, indent=2, default=str))
    pcb = lineage.linked_pcb(project)
    lineage.note(project, md, lambda: [lineage.file_input("pcb", pcb)] if pcb else [], "design_report")
    return {"file": md.name, "json": js.name, "changed": d["changed_since_previous_report"], "unavailable": d["unavailable"],
            "files": len(d["altium_files"])}


def archive(project: str) -> dict[str, Any]:
    """archive/<p>_<time>.zip of everything needed to get this board back. A file over MAX_FILE_MB is named in `skipped`."""
    import jlc_upload
    rep = build(project)                               # the archive carries a report made now
    pdir = store.pdir(project)
    dest_dir = pdir / "archive"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{workspace.safe_name(project)}_{stamp}.zip"
    todo: list[tuple[pathlib.Path, str]] = []
    for f in altium_files(project):
        todo.append((pathlib.Path(f["path"]), "altium/" + f["name"]))
    for root in jlc_upload._roots(project):
        for p in sorted(root.rglob("*")):
            if p.is_file() and not (set(x.lower() for x in p.parts) & SKIP_PARTS):
                todo.append((p, "altium-outputs/" + p.relative_to(root).as_posix()))
    exp = pdir / "exports"
    if exp.is_dir():
        todo += [(p, "exports/" + p.name) for p in sorted(exp.iterdir()) if p.is_file() and not p.name.endswith(".part")]
    for name in ("project.json", "lineage-log.jsonl"):
        if (pdir / name).is_file():
            todo.append((pdir / name, name))
    skipped, n, seen = [], 0, set()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p, arc in todo:
            if arc in seen:
                continue
            seen.add(arc)
            try:
                if p.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                    skipped.append(arc)
                    continue
                z.write(p, arc)
                n += 1
            except OSError:
                skipped.append(arc)
    return {"archive": dest.name, "path": str(dest), "files": n, "bytes": dest.stat().st_size, "skipped": skipped, "report": rep["file"]}


def main(argv=None):
    import oscompat
    oscompat.utf8_stdio()
    args = sys.argv[1:] if argv is None else list(argv)
    project = args[0]
    what = args[1] if len(args) > 1 else "report"
    print(json.dumps(archive(project) if what == "archive" else build(project), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
