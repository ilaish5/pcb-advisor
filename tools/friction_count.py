"""Dev helper: count what the system makes the student do before a stage or the outputs can go on, per project.

    python tools/friction_count.py --home <folder that holds projects/> [--out counts.json] [project ...]

Works on a COPY of the projects (the model build stamps legacy accepts and rewrites bom.json): point --home at a temp folder,
never at the real workspace. Without project names every project under <home>/projects with a BOM is counted. Reads the
model the page shows (model.build), so a number here is a number the student sees.

Counts per project (every one is a place the system waits on the student):
  pin_rows        parts listed as unverified or mismatch (the DFM list and the manufacturing gate): one per BOM line
  pin_questions   what the student is asked after grouping identical parts (== pin_rows on a tree without grouping)
  pin_own_look    questions that need a person's own look (a mismatch, or no way to settle it in bulk)
  nc_pins         pins with no net and no NC mark, plus pins of a built symbol the netlist lacks (one gate: Mark NC)
  proposals       BOM proposals still pending
  lib_review      BOM lines whose library state is review / missing / error
  lib_buttons     per-row buttons the Library table shows (Verify / Accept / Confirm pins)
  supply          out-of-stock + wrong-code + not-yet-checked lines (BOM stage)
  gaps_parts      parts on a sheet that are not approved in the BOM
  outputs_blocked 1 when the manufacturing outputs are refused
  asks            the clicks that clear all of it: pin asks (one per part at HEAD; one bulk + the own-look rows with the waiting line)
                  + proposals + (1 if nc_pins) + lib_buttons
"""
import argparse
import json
import os
import pathlib
import re
import sys

POLARISED = ("D", "LED")


def _setup(home):
    os.environ["PCB_ADVISOR_HOME"] = str(pathlib.Path(home).resolve())
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))


def _prefix(ref):
    m = re.match(r"[A-Za-z]+", ref or "")
    return m.group(0).upper() if m else ""


def _kind(line):
    refs = line.get("refs") or []
    pre = {_prefix(r) for r in refs}
    if pre and pre <= set(POLARISED):
        return "polarised"
    if pre and pre <= {"J", "P"}:
        return "connector"
    return "ic" if line.get("datasheet") is None else "ic_linked"


def _row_buttons_head(row, line):
    """The buttons libAction (ui/js/views/pages.js) puts on a Library row, as the page decided before this audit."""
    n = 0
    if row["verify"] == "pass" and not row["accepted"]:
        return 1
    if row["verify"] != "pass" and row["symbol"]:
        open_ = bool(line) and line.get("pins_status") in ("unverified", "mismatch")
        refs = (line or {}).get("refs") or []
        can_verify = (not open_) or (bool(line.get("datasheet")) and not (refs and all(re.match(r"(D|LED)\d", r, re.I) for r in refs)))
        n += 1 if can_verify else 0
        n += 1 if open_ else 0
    return n


def measure(project):
    import model
    import store
    m = model.build(project)
    bom = {l["key"]: l for l in m["bom"]}
    with store.build_scope():
        rows = store.pins_to_resolve(project)
        gaps = store.pin_gaps(project)
        warn = store.manufacturing_warning(project)
    import pin_decisions
    waiting = getattr(pin_decisions, "waiting", None)
    summary = waiting(project) if waiting else None
    kinds = {}
    for r in rows:
        k = "mismatch" if r["status"] == "mismatch" else _kind(bom.get(r["line"]) or {})
        kinds[k] = kinds.get(k, 0) + 1
    lib_rows = m.get("library") or []
    mode = "new" if summary else "head"
    if summary:
        buttons = sum(summary["lib_buttons"].get(r["line"], 0) for r in lib_rows) if "lib_buttons" in summary else 0
    else:
        buttons = sum(_row_buttons_head(r, bom.get(r["line"])) for r in lib_rows)
    props = sum(1 for p in m.get("proposals") or [] if p.get("status") == "pending")
    stages = {s["id"]: s["state"] for s in m.get("stages") or []}
    t = m.get("totals") or {}
    nc = len(gaps["open"]) + len(gaps["unlisted"])
    out = {
        "project": project, "ui": mode,
        "bom_lines": len(bom), "refs_on_sheets": sum(len(l.get("refs") or []) for l in bom.values() if l.get("on_sheet")),
        "pin_rows": len(rows), "pin_refs": sum(len(r.get("refs") or [r["line"]]) for r in rows),
        "pin_kinds": kinds,
        "pin_questions": summary["questions"] if summary else len(rows),
        "pin_own_look": summary["own_look"] if summary else len(rows),
        "auto_verified": summary["auto_verified"] if summary else 0,
        "nc_pins": nc, "nc_proposal": len(store.nc_proposal(project)),
        "proposals": props,
        "lib_review": sum(1 for l in bom.values() if l.get("library") in ("review", "missing", "error")),
        "lib_buttons": buttons,
        "supply": (t.get("out_of_stock") or 0) + (t.get("to_verify") or 0) + (t.get("checking") or 0),
        "gaps_parts": len((m.get("sheet_gaps") or {}).get("parts") or []),
        "outputs_blocked": int(stages.get("outputs") == "blocked"), "blocked_why": (warn or "")[:160],
        "stages": stages,
    }
    # asks: the clicks the student must make before the gates open. At HEAD every unverified part is its own ask; with the waiting line
    # one "Confirm all" settles every question that is not a mismatch, so it counts as one.
    pins = ((1 if summary["bulk"] else 0) + summary["own_look"]) if summary else out["pin_rows"]
    out["asks"] = pins + props + (1 if nc else 0) + out["lib_buttons"]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--out")
    ap.add_argument("projects", nargs="*")
    a = ap.parse_args(argv)
    _setup(a.home)
    root = pathlib.Path(a.home) / "projects"
    if not root.is_dir():
        print(f"no projects folder under {a.home}: nothing to count")
        return 0
    names = a.projects or sorted(p.name for p in root.iterdir() if (p / "bom.json").is_file() or (p / "bom-log.jsonl").is_file())
    res = []
    for n in names:
        try:
            res.append(measure(n))
        except Exception as exc:        # noqa: BLE001 - one broken project never hides the others
            res.append({"project": n, "error": f"{type(exc).__name__}: {exc}"})
    for r in res:
        if "error" in r:
            print(f"{r['project']:<22} ERROR {r['error']}")
            continue
        print(f"{r['project']:<22} lines {r['bom_lines']:>3}  pin rows {r['pin_rows']:>2} (refs {r['pin_refs']:>2})  questions {r['pin_questions']:>2}  "
              f"own look {r['pin_own_look']:>2}  auto {r['auto_verified']:>2}  nc {r['nc_pins']:>2}  props {r['proposals']}  "
              f"lib review {r['lib_review']:>2}  lib buttons {r['lib_buttons']:>2}  supply {r['supply']:>2}  blocked {r['outputs_blocked']}  asks {r['asks']:>2}")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
