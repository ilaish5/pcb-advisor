"""Project keeping: decision log, change impact, and final file organization.

Usage:
    python scripts/keeping.py <project> log "<decision>" [--why "<why>"] [--who "<who>"] [--source "<source>"]
    python scripts/keeping.py <project> decisions
    python scripts/keeping.py <project> impact <part_or_net>
    python scripts/keeping.py <project> report
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import project as project_mod
import store
import workspace


def _notes_path(project: str) -> pathlib.Path:
    return workspace.project_dir(project) / "notes.md"


def append_decision(project: str, decision: str, who: str = "student", why: str = "", source: str = "", date: str = None) -> dict:
    """Append a decision to notes.md under '## Decision Log'."""
    p = _notes_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.is_file():
        text = "# Notes\n\nYours. Nothing derives from this file and nothing overwrites it.\n"
    else:
        text = p.read_text(encoding="utf-8")

    today = date or dt.date.today().isoformat()
    entry = {
        "date": today,
        "decision": decision.strip(),
        "who": who.strip() or "student",
        "why": why.strip() or "—",
        "source": source.strip() or "student preference",
    }

    log_header = "## Decision Log"
    row = f"| {entry['date']} | {entry['decision']} | {entry['who']} | {entry['why']} | {entry['source']} |"

    if log_header not in text:
        text = text.rstrip() + f"\n\n{log_header}\n\n| Date | Decision | Who | Why | Source |\n|---|---|---|---|---|\n{row}\n"
    else:
        # Append below the header / table
        lines = text.splitlines()
        hdr_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == log_header:
                hdr_idx = i
                break
        # Find next section or EOF
        next_sec = len(lines)
        for i in range(hdr_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                next_sec = i
                break

        # Check if table headers exist
        has_table = any("| Date |" in l for l in lines[hdr_idx:next_sec])
        if not has_table:
            lines.insert(hdr_idx + 1, "| Date | Decision | Who | Why | Source |")
            lines.insert(hdr_idx + 2, "|---|---|---|---|---|")
            lines.insert(hdr_idx + 3, row)
        else:
            lines.insert(next_sec, row)
        text = "\n".join(lines).rstrip() + "\n"

    p.write_text(text, encoding="utf-8")
    return entry


def list_decisions(project: str) -> list[dict]:
    """List recorded decisions from notes.md."""
    p = _notes_path(project)
    if not p.is_file():
        return []

    lines = p.read_text(encoding="utf-8").splitlines()
    in_log = False
    decisions = []

    for line in lines:
        stripped = line.strip()
        if stripped == "## Decision Log":
            in_log = True
            continue
        elif in_log and stripped.startswith("## "):
            in_log = False
            continue

        if in_log and stripped.startswith("|"):
            parts = [c.strip() for c in stripped.strip("|").split("|")]
            if len(parts) >= 5:
                if parts[0].lower() in ("date", "---") or parts[0].startswith("-"):
                    continue
                decisions.append({
                    "date": parts[0],
                    "decision": parts[1],
                    "who": parts[2],
                    "why": parts[3],
                    "source": parts[4],
                })
        elif in_log and (stripped.startswith("-") or stripped.startswith("*")):
            m = re.match(r"^[-*]\s+(\d{4}-\d{2}-\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*)$", stripped)
            if m:
                decisions.append({
                    "date": m.group(1),
                    "decision": m.group(2),
                    "who": m.group(3),
                    "why": m.group(4),
                    "source": m.group(5),
                })
    return decisions


def change_impact(project: str, item: str) -> list[dict]:
    """Walk the 13 change impact categories for a changed part or net."""
    item = item.strip()
    is_net = item.startswith("+") or item in ("GND", "VCC", "VDD") or item.isupper() and "_" in item

    # Gather project context
    bom = store.bom_lines(project)
    matched_line = next((l for l in bom if item in l.get("refs", []) or l.get("mpn") == item or l["key"] == item), None)
    if matched_line and not is_net:
        ref_str = ", ".join(matched_line.get("refs", [item]))
        mpn = matched_line.get("mpn", item)
    else:
        ref_str = item
        mpn = item

    impacts = [
        {
            "category": "Symbol and pin map",
            "affected": "yes" if not is_net else "no",
            "why": f"Pin assignments, logical grouping or pin count may differ for {mpn}" if not is_net else "Net name change does not alter symbol graphics",
            "file_to_edit": "Altium schematic symbol / SchLib" if not is_net else "—",
            "source": "Datasheet pinout table" if not is_net else "Practice",
        },
        {
            "category": "Footprint and 3D model",
            "affected": "yes" if not is_net else "no",
            "why": f"Package dimensions, land pattern or height may differ for {mpn}" if not is_net else "Pads remain the same physical footprint",
            "file_to_edit": "Altium footprint / PcbLib" if not is_net else "—",
            "source": "Package specifications" if not is_net else "Practice",
        },
        {
            "category": "Supply voltage and decoupling",
            "affected": "yes",
            "why": f"Check voltage tolerance, rail requirements and capacitor values near {ref_str}",
            "file_to_edit": "Schematic power sheets",
            "source": "Electrical characteristics / Abs max",
        },
        {
            "category": "Pull-ups and level shifting",
            "affected": "unknown",
            "why": f"I/O drive strength, open-drain requirements or 5V tolerance on {ref_str}",
            "file_to_edit": "Schematic signal sheets",
            "source": "I/O port specifications",
        },
        {
            "category": "Clock or crystal",
            "affected": "unknown" if not is_net else ("yes" if "CLK" in item or "OSC" in item else "no"),
            "why": f"Oscillator load caps, frequency limits or internal PLL settings for {ref_str}",
            "file_to_edit": "Schematic / firmware init",
            "source": "Clock and timing specifications",
        },
        {
            "category": "Programming and debug connector",
            "affected": "unknown" if not is_net else ("yes" if any(k in item for k in ("SWD", "JTAG", "BOOT", "UART")) else "no"),
            "why": f"Check SWD/JTAG pinout, boot strap pins or USB DFU pins for {ref_str}",
            "file_to_edit": "Debug header on schematic",
            "source": "Reference manual / Boot modes",
        },
        {
            "category": "Boot pins",
            "affected": "unknown" if not is_net else ("yes" if "BOOT" in item else "no"),
            "why": f"Boot mode configuration pull-up/down resistors for {ref_str}",
            "file_to_edit": "Schematic boot circuit",
            "source": "Boot configuration application note",
        },
        {
            "category": "Net names used in rules",
            "affected": "yes" if is_net else "unknown",
            "why": f"Rule classes (Clearance, Width, Differential Pairs) referencing {item}",
            "file_to_edit": ".RUL / Altium PCB Rules",
            "source": "PCB design rules",
        },
        {
            "category": "PCB placement",
            "affected": "yes",
            "why": f"Physical room, thermal relief, orientation or zone constraints for {ref_str}",
            "file_to_edit": "Altium PcbDoc placement",
            "source": "Placement plan",
        },
        {
            "category": "BOM line and LCSC number",
            "affected": "yes" if not is_net else "no",
            "why": f"MPN, manufacturer and JLC part code must update for {mpn}" if not is_net else "Nets are not purchased BOM items",
            "file_to_edit": "bom-log.jsonl / bom.json",
            "source": "JLC parts catalog",
        },
        {
            "category": "CPL rotation",
            "affected": "yes" if not is_net else "no",
            "why": f"Pin 1 orientation in tape/reel vs footprint for {mpn}" if not is_net else "Nets have no assembly placement",
            "file_to_edit": "Pick and place / CPL export",
            "source": "JLC SMT component orientation guidelines",
        },
        {
            "category": "Silkscreen text",
            "affected": "unknown",
            "why": f"Designator labels, pin indicators or polarity markers for {ref_str}",
            "file_to_edit": "Altium PcbDoc silkscreen layers",
            "source": "Practice",
        },
        {
            "category": "Notes and decision log",
            "affected": "yes",
            "why": f"Record the justification for swapping {ref_str} in notes.md",
            "file_to_edit": "notes.md (Decision Log)",
            "source": "Project keeping",
        },
    ]
    return impacts


# Folders that hold old copies, not outputs: a match in there would hide a missing output.
_SKIP_DIRS = {"history", "__previews", ".git", ".venv", "_legacy", "__pycache__"}


def _find_outputs(roots, patterns):
    """Newest file under any root whose lower-case name matches a pattern (searched in order)."""
    import fnmatch
    for pat in patterns:
        hits = []
        for root in roots:
            for f in root.rglob("*"):
                rel = f.relative_to(root).parts[:-1]
                if f.is_file() and not _SKIP_DIRS & {p.lower() for p in rel} and fnmatch.fnmatch(f.name.lower(), pat):
                    hits.append(f)
        if hits:
            return max(hits, key=lambda f: f.stat().st_mtime)
    return None


def file_organization(project: str) -> dict:
    """Report present and missing files for the final project submission.

    Outputs are looked for in the project's exports/ and, for a linked Altium project, in its Outputs
    folder and its own folder (libraries): that is where Altium writes them. An output older than the
    document it is made from is listed with `older_than`, so a Gerber from before the last board save
    does not pass as current."""
    pdir = workspace.project_dir(project)
    exports_dir = pdir / "exports"
    link = project_mod.altium_link(project)

    # Core files
    core_files = [
        ("idea.json", "Project requirements & block diagram", pdir / "idea.json"),
        ("notes.md", "Project notes & decision log", pdir / "notes.md"),
        ("bom.json", "Derived bill of materials", pdir / "bom.json"),
        ("project.json", "Project metadata & links", pdir / "project.json"),
    ]

    pcb = pathlib.Path(link["pcb_file"]) if link.get("pcb_file") else None
    prj = pathlib.Path(link["project_file"]) if link.get("project_file") else None
    sch = sorted(prj.parent.glob("*.SchDoc"), key=lambda f: f.stat().st_mtime)[-1:] if prj and prj.is_file() else []
    sch = sch[0] if sch else None
    # label, description, patterns (lower case, in order of preference), the document it is made from
    export_patterns = [
        ("JLC BOM", "JLCPCB SMT bill of materials (CSV)", ["*jlc*bom*.csv", "*bom*jlc*.csv", "*bom*.csv"], sch),
        ("Generic BOM", "Generic bill of materials (CSV)", ["*generic*bom*.csv", "*altium*bom*.csv", "*bom*full*.csv"], sch),
        ("CPL / Pick & Place", "SMT component placement list", ["*cpl*.csv", "*pick*place*.csv", "*placement*.csv"], pcb),
        ("Gerber files", "PCB fabrication gerber archive", ["*gerber*.zip", "*fab*.zip"], pcb),
        ("Schematic (PDF)", "Printable schematic document", ["*schematic*.pdf", "*sch*.pdf"], sch),
        ("Altium library", "Project integrated library package", ["*.intlib", "*library*.zip"], None),
    ]
    roots = [exports_dir]
    if link.get("outputs_dir"):
        roots.append(pathlib.Path(link["outputs_dir"]))
    if prj:
        roots.append(prj.parent / "Libraries")
    roots = [r for r in roots if r.is_dir()]

    present = []
    missing = []

    for name, desc, path in core_files:
        if path.is_file():
            present.append({"name": name, "description": desc, "path": str(path)})
        else:
            missing.append({"name": name, "description": desc, "expected_path": str(path)})

    for label, desc, patterns, source in export_patterns:
        hit = _find_outputs(roots, patterns)
        if not hit:
            missing.append({"name": label, "description": desc, "expected_path": f"exports/{patterns[0]}"})
            continue
        row = {"name": label, "description": desc, "path": str(hit),
               "saved": dt.datetime.fromtimestamp(hit.stat().st_mtime).isoformat(timespec="seconds")}
        if source and source.is_file() and source.stat().st_mtime > hit.stat().st_mtime:
            row["older_than"] = source.name
        present.append(row)

    # Check linked Altium files if any
    if link.get("project_file"):
        pf = pathlib.Path(link["project_file"])
        if pf.is_file():
            present.append({"name": "Altium PrjPcb", "description": "Linked Altium project", "path": str(pf)})
        else:
            missing.append({"name": "Altium PrjPcb", "description": "Linked Altium project", "expected_path": str(pf)})
    if link.get("pcb_file"):
        pf = pathlib.Path(link["pcb_file"])
        if pf.is_file():
            present.append({"name": "Altium PcbDoc", "description": "Linked PCB document", "path": str(pf)})
        else:
            missing.append({"name": "Altium PcbDoc", "description": "Linked PCB document", "expected_path": str(pf)})

    return {
        "project": project,
        "present": present,
        "missing": missing,
        "total_present": len(present),
        "total_missing": len(missing),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="keeping", description="Project keeping assistant")
    ap.add_argument("project", help="Project name")
    sub = ap.add_subparsers(dest="command", required=True)

    # log
    p_log = sub.add_parser("log", help="Append a decision")
    p_log.add_argument("decision", help="Decision text")
    p_log.add_argument("--who", default="student", help="Who made the decision")
    p_log.add_argument("--why", default="", help="Rationale / reason")
    p_log.add_argument("--source", default="student preference", help="Citing source")
    p_log.add_argument("--date", default=None, help="Date YYYY-MM-DD")

    # decisions
    sub.add_parser("decisions", help="List logged decisions")

    # impact
    p_imp = sub.add_parser("impact", help="List change impact for a part or net")
    p_imp.add_argument("item", help="Component designator or net name")

    # report
    sub.add_parser("report", help="Check file organization and missing outputs")

    args = ap.parse_args(argv)

    if args.command == "log":
        res = append_decision(args.project, args.decision, who=args.who, why=args.why, source=args.source, date=args.date)
        print(f"Decision logged: {res['date']} | {res['decision']}")

    elif args.command == "decisions":
        decs = list_decisions(args.project)
        if not decs:
            print("No decisions recorded yet.")
        else:
            print(f"Decision Log ({len(decs)} entries):")
            for d in decs:
                print(f"  [{d['date']}] {d['decision']} (By: {d['who']}; Why: {d['why']}; Source: {d['source']})")

    elif args.command == "impact":
        impacts = change_impact(args.project, args.item)
        print(f"Change Impact for {args.item} ({len(impacts)} checks):")
        for imp in impacts:
            aff = "YES" if imp["affected"] == "yes" else ("NO" if imp["affected"] == "no" else "?")
            print(f"  [{aff:3}] {imp['category']:32} -> {imp['why']}")

    elif args.command == "report":
        rep = file_organization(args.project)
        print(f"File Organization Report for {args.project}:")
        print(f"  Present: {rep['total_present']} files")
        for item in rep["present"]:
            old = f"  (older than {item['older_than']}: re-export or confirm nothing changed)" \
                if item.get("older_than") else ""
            print(f"    {'!' if old else '✓'} {item['name']}: {item.get('path', '')}{old}")
        print(f"  Missing: {rep['total_missing']} files")
        for item in rep["missing"]:
            print(f"    ✗ {item['name']} ({item['description']})")


if __name__ == "__main__":
    main()
