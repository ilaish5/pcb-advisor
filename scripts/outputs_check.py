"""
Did the outputs really come out? A step that says "Altium wrote 12 files" is only a claim: Altium reported
"Documents Printed: 0" and the schematic PDF was not there, and nothing said so.

verify() looks at the disk after every output step. Every output the OutJob is set to make (its output types) must have
produced a file, every file claimed must exist and not be empty, and for an order with assembly the BOM and the CPL
must be there too. What is missing is named, so the student is told and the step does not read as done.

    python scripts/outputs_check.py <project>        the check of the last outputs, again, from the disk
"""
import configparser
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import store  # noqa: E402

RECORD = "outputs-check.json"

# OutJob output type -> (kind, what the student calls it)
OUTJOB_KINDS = {
    "schematic print": ("pdf", "Schematic PDF"),
    "pdf": ("pdf", "Schematic PDF"),
    "bom_parttype": ("bom", "Bill of materials"),
    "bom": ("bom", "Bill of materials"),
    "gerber": ("gerber", "Gerber files"),
    "nc drill": ("drill", "NC drill files"),
    "pick place": ("cpl", "Pick and place (CPL)"),
}
DEFAULT_KINDS = [("pdf", "Schematic PDF"), ("bom", "Bill of materials"), ("gerber", "Gerber files"), ("drill", "NC drill files")]
LABEL = {"pdf": "Schematic PDF", "bom": "Bill of materials", "gerber": "Gerber files", "drill": "NC drill files",
         "cpl": "Pick and place (CPL)"}


def outjob_kinds(outjob) -> list[tuple[str, str]]:
    """[(kind, label)] of the output types an OutJob file makes, in file order; [] when it cannot be read."""
    if not outjob or not pathlib.Path(outjob).is_file():
        return []
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read(str(outjob), encoding="latin-1")
    except configparser.Error:
        return []
    out = []
    for sec in cp.sections():
        if not sec.startswith("OutputGroup"):
            continue
        for key, val in cp.items(sec):
            if re.fullmatch(r"OutputType\d+", key):
                hit = OUTJOB_KINDS.get(val.strip().lower())
                if hit and hit not in out:
                    out.append(hit)
    return out


def kind_of(name: str) -> str | None:
    """Which output a file is: pdf, bom, gerber, drill, cpl (by its name and extension), else None."""
    import jlc_upload
    low = pathlib.PurePath(name).name.lower()
    ext = pathlib.PurePath(name).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if "bom" in re.split(r"[^a-z]+", low) or "bill of materials" in low or "bom_" in low:
        return "bom"
    if "pick" in low and "place" in low or "_cpl" in low or low.endswith("cpl.csv") or "centroid" in low:
        return "cpl"
    cls = jlc_upload.classify(name)
    if cls and cls[0] == "drill":
        return "drill"
    if cls:
        return "gerber"
    return None


def verify(project: str, files, outjob=None, options: dict | None = None, extra=()) -> dict:
    """Check what the outputs step claims against the disk.
    files: the paths the step says it wrote; outjob: the OutJob that ran (its output types are what is expected; without
    it the standard set is); options: order_options.get() (assembly adds the BOM and the CPL); extra: further files that
    count (the CPL the system exports itself).
    Returns {ok, expected: [{kind, label, found: [names]}], missing: [labels], empty: [names], absent: [names], warnings, message}."""
    options = options or {}
    wanted = list(outjob_kinds(outjob)) or list(DEFAULT_KINDS)
    if options.get("assembly"):
        for k in ("bom", "cpl"):
            if k not in [w[0] for w in wanted]:
                wanted.append((k, LABEL[k]))
    paths = [pathlib.Path(f) for f in list(files or []) + list(extra or [])]
    absent = sorted({p.name for p in paths if not p.is_file()})
    empty = sorted({p.name for p in paths if p.is_file() and p.stat().st_size == 0})
    good = [p for p in paths if p.is_file() and p.stat().st_size > 0]
    expected = [{"kind": k, "label": label, "found": sorted({p.name for p in good if kind_of(p.name) == k})} for k, label in wanted]
    missing = [e["label"] for e in expected if not e["found"]]
    warnings = []
    if missing:
        warnings.append("Not made, although the outputs step ran: " + ", ".join(missing)
                        + ". Open the OutJob in Altium and check that output and its container, then generate again.")
    if absent:
        warnings.append("Reported as written but not on the disk: " + ", ".join(absent[:6]) + (" ..." if len(absent) > 6 else ""))
    if empty:
        warnings.append("Written empty: " + ", ".join(empty[:6]) + (" ..." if len(empty) > 6 else "") + ". An empty output cannot be used.")
    ok = not (missing or absent or empty)
    res = {"ok": ok, "checked": len(paths), "expected": expected, "missing": missing, "empty": empty, "absent": absent,
           "warnings": warnings, "at": store.now(),
           "message": "every expected output is there" if ok else "; ".join(warnings)}
    return res


def save(project: str, res: dict) -> None:
    """The newest check, kept for the design report and the page."""
    try:
        store._write_text(store.pdir(project) / RECORD, json.dumps(res, ensure_ascii=False, indent=2))
    except OSError:
        pass


def load(project: str) -> dict | None:
    try:
        return json.loads((store.pdir(project) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None):
    import oscompat
    import order_options
    oscompat.utf8_stdio()
    args = sys.argv[1:] if argv is None else list(argv)
    project = args[0]
    import jlc_upload
    files = []
    for root in jlc_upload._roots(project):
        files += [str(p) for p in pathlib.Path(root).rglob("*") if p.is_file() and ".advisor-backup" not in p.parts]
    res = verify(project, files, options=order_options.get(project))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
