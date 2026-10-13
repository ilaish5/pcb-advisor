"""
Export the BOM for a manufacturer.

    python scripts/skills/export_bom.py <project> [jlc|pcbway|generic]

Writes projects/<project>/exports/<project>_BOM_<format>.csv. Lines that are not
fitted (DNP) or not bought (test pads) are left out and listed in the output, so
nothing disappears silently. JLC needs an LCSC part number: it comes from the last
availability check, else from the code declared on the line (an import from Altium);
a line without one is listed under "needs_lcsc".
"""
import csv
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import oscompat   # noqa: E402
import store      # noqa: E402
import workspace  # noqa: E402

FORMATS = {
    "jlc": ["Comment", "Designator", "Footprint", "LCSC Part #"],
    "pcbway": ["Designator", "Qty", "MPN", "Manufacturer", "Package", "Description"],
    "generic": ["Designator", "Value", "Footprint", "MPN", "Manufacturer", "Quantity"],
}


def lcsc_code(project, key, line=None):
    """The code of the last stock check; failing that, the one declared on the line."""
    code = ""
    for ev in store.read_jsonl(store.pdir(project) / "supply-log.jsonl"):
        if ev.get("line") == key and ev.get("supplier") == "LCSC":
            m = re.search(r"C\d{3,}", ev.get("source") or "")
            if m:
                code = m.group(0)
    return code or (line or {}).get("lcsc") or ""


def export(project, fmt="generic"):
    if fmt not in FORMATS:
        raise SystemExit(f"format must be one of {', '.join(FORMATS)}")
    lines = store.bom(project, write=False)
    left_out, needs = [], []
    out_dir = store.pdir(project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{project}_BOM_{fmt}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(FORMATS[fmt])
        for l in lines:
            if not store.qty(l):
                left_out.append(l["key"])
                continue
            refs = ", ".join(l["refs"])
            if fmt == "jlc":
                code = lcsc_code(project, l["key"], l)
                if not code:
                    needs.append(l["key"])
                w.writerow([l.get("value") or l.get("mpn"), refs, l.get("package", ""), code])
            elif fmt == "pcbway":
                w.writerow([refs, len(l["refs"]), l.get("mpn", ""), l.get("manufacturer", ""),
                            l.get("package", ""), l.get("description", "")])
            else:
                w.writerow([refs, l.get("value", ""), l.get("package", ""), l.get("mpn", ""),
                            l.get("manufacturer", ""), len(l["refs"])])
    home = workspace.home()
    shown = path.relative_to(home).as_posix() if path.is_relative_to(home) else str(path)
    return {"file": shown, "format": fmt, "lines": len(lines) - len(left_out),
            "left_out": left_out, "needs_lcsc": needs}


if __name__ == "__main__":
    oscompat.utf8_stdio()
    print(json.dumps(export(sys.argv[1] if len(sys.argv) > 1 else "demo",
                            sys.argv[2] if len(sys.argv) > 2 else "generic"), ensure_ascii=False, indent=2))
