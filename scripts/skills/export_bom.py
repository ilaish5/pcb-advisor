"""
Export the BOM for a manufacturer.

    python scripts/skills/export_bom.py <project> [jlc|pcbway|generic]

Writes projects/<project>/exports/<project>_BOM_<format>.csv. Lines that are not
fitted (DNP) or not bought (test pads) are left out and listed in the output, so
nothing disappears silently. The JLC BOM also leaves out every designator that is on
no drawn sheet (off_sheet), and says so in left_out_text. JLC needs an LCSC part number: it is the code declared on the line (an import
from Altium, an order swap), else the one the last availability check found for the line's current MPN;
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
    """The code declared on the line; failing that, the one of the last stock check of the line's current MPN.
    A code checked for another MPN, or a hit that is not the exact part, is never exported."""
    declared = ((line or {}).get("lcsc") or "").strip()
    if declared:
        return declared
    mpn = ((line or {}).get("mpn") or "").strip().lower()
    code = ""
    for ev in store.read_jsonl(store.pdir(project) / "supply-log.jsonl"):
        if (ev.get("line") == key and ev.get("supplier") == "LCSC" and (ev.get("mpn") or "").strip().lower() == mpn
                and ev.get("exact") is not False and not ev.get("code_mismatch")):
            m = re.search(r"C\d{3,}", ev.get("source") or "")
            if m:
                code = m.group(0)
    return code


DNP_TEXT = re.compile(r"\bDNP\b|\bDNF\b|\bdo not (populate|place|fit|mount)\b|\bnot fitted\b", re.I)


def is_dnp(line):
    """Not fitted: the DNP flag, or a value / MPN / comment that says so ("DNP", "do not populate"): never a line JLC places."""
    return bool(line.get("dnp")) or any(DNP_TEXT.search(str(line.get(k) or "")) for k in ("value", "mpn", "comment"))


def sheet_refs(project):
    """The designators the schematic holds: on a drawn sheet (store.sheet_docs) once anything is drawn, else on any sheet of the
    design. None when the design has no sheet with a part (a BOM-only project): then nothing can be compared and nothing is dropped."""
    drawn = {str(k) for k in store.sheet_docs(project)}
    refs, drawn_refs = set(), set()
    for sh in store.sheet_ids(project):
        got = {p.get("ref") for p in store.load_sheet(project, sh).get("parts", []) if p.get("ref")}
        refs |= got
        if str(sh) in drawn:
            drawn_refs |= got
    if drawn:
        return drawn_refs
    return refs or None


def table(project, fmt="generic"):
    """{rows (header first), left_out, needs_lcsc, dnp, off_sheet}: exactly what the CSV holds and what it left out. The JLC BOM
    (what is placed on the board) leaves out DNP lines (flag or text) and every designator on no drawn sheet, so it never lists a
    part the board does not have (E3, 24/11/2026); off_sheet = [{line, refs}] names them, a line keeping its other refs."""
    if fmt not in FORMATS:
        raise SystemExit(f"format must be one of {', '.join(FORMATS)}")
    lines = store.bom(project, write=False)
    on = sheet_refs(project) if fmt == "jlc" else None
    out, left_out, needs, dnp, off = [FORMATS[fmt]], [], [], [], []
    for l in lines:
        if fmt == "jlc" and is_dnp(l) and l.get("refs"):
            dnp.append(l["key"])
            left_out.append(l["key"])
            continue
        if not store.qty(l):
            left_out.append(l["key"])
            continue
        kept = list(l["refs"])
        if on is not None:
            gone = [r for r in kept if r not in on]
            if gone:
                off.append({"line": l["key"], "refs": gone})
                kept = [r for r in kept if r in on]
            if not kept:
                left_out.append(l["key"])
                continue
        refs = ", ".join(kept)
        if fmt == "jlc":
            code = lcsc_code(project, l["key"], l)
            if not code:
                needs.append(l["key"])
            out.append([l.get("value") or l.get("mpn"), refs, l.get("package", ""), code])
        elif fmt == "pcbway":
            out.append([refs, len(kept), l.get("mpn", ""), l.get("manufacturer", ""),
                        l.get("package", ""), l.get("description", "")])
        else:
            out.append([refs, l.get("value", ""), l.get("package", ""), l.get("mpn", ""),
                        l.get("manufacturer", ""), len(kept)])
    return {"rows": out, "left_out": left_out, "needs_lcsc": needs, "dnp": dnp, "off_sheet": off}


def rows(project, fmt="generic"):
    """(rows with the header first, left_out, needs_lcsc): exactly what the CSV holds. Lineage fingerprints this."""
    t = table(project, fmt)
    return t["rows"], t["left_out"], t["needs_lcsc"]


def left_out_text(res):
    """One line naming what the export left out ("" when nothing): DNP lines and designators on no drawn sheet."""
    said = []
    if res.get("dnp"):
        said.append(f"{len(res['dnp'])} DNP line(s): {', '.join(res['dnp'][:8])}{' ...' if len(res['dnp']) > 8 else ''}")
    off = [r for x in res.get("off_sheet") or [] for r in x["refs"]]
    if off:
        said.append(f"{len(off)} part(s) on no drawn sheet: {', '.join(off[:10])}{' ...' if len(off) > 10 else ''}")
    return ("Left out of the JLC BOM: " + "; ".join(said) + ".") if said else ""


def export(project, fmt="generic"):
    t = table(project, fmt)
    out_dir = store.pdir(project) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{project}_BOM_{fmt}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(t["rows"])
    import lineage
    lineage.note(project, path, lambda: [lineage.state_input(project, "bom_csv", fmt)], "export_bom")
    home = workspace.home()
    shown = path.relative_to(home).as_posix() if path.is_relative_to(home) else str(path)
    res = {"file": shown, "format": fmt, "lines": len(t["rows"]) - 1,
           "left_out": t["left_out"], "needs_lcsc": t["needs_lcsc"], "dnp": t["dnp"], "off_sheet": t["off_sheet"]}
    res["left_out_text"] = left_out_text(res)
    return res


if __name__ == "__main__":
    oscompat.utf8_stdio()
    print(json.dumps(export(sys.argv[1] if len(sys.argv) > 1 else "demo",
                            sys.argv[2] if len(sys.argv) > 2 else "generic"), ensure_ascii=False, indent=2))
