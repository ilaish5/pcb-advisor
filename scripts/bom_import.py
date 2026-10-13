"""
Import the BOM of an existing Altium project, and say where the files disagree.

    python scripts/bom_import.py <project> <bom.csv> [--prjpcb P] [--pcb P] [--apply]

The default is a dry run: it reads the BOM CSV, reads every SchDoc of the PrjPcb and
the PcbDoc, compares the three and writes projects/<project>/checks/bom-import.json
and bom-import.md. With --apply it also appends one bom-log event per line
(by=import), and one library-log event per line whose symbol and footprint the
project names (verify=unchecked). Import works into an EMPTY BOM only.

The source files are never "fixed": a disagreement is a finding, and the imported
line keeps what the CSV says. An LCSC code in the CSV is stored as a declared code
(`lcsc`), not as a stock answer - the availability check still looks it up.
"""
import argparse
import ast
import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oscompat   # noqa: E402
import project as project_mod  # noqa: E402
import store      # noqa: E402
import workspace  # noqa: E402

# header names, normalised (lower case, letters and digits only), in order of preference
COLUMNS = {
    "designators": ("designator", "designators", "reference", "references", "refdes", "ref"),
    "value": ("value", "comment"),
    "mpn": ("mpn", "manufacturerpartnumber", "manufacturerpart", "partnumber", "mfrpartnumber"),
    "manufacturer": ("manufacturer", "manufacturername", "mfr", "mfg"),
    "lcsc": ("lcsc", "lcscpart", "lcscpartnumber", "jlcpcbpart", "jlcpart", "supplierpart"),
    "footprint": ("footprint", "package"),
    "description": ("description",),
    "qty": ("quantity", "qty"),
}
# the same idea for the parameters of a schematic component
PARAM_MPN = ("manufacturerpartnumber", "mpn", "mp", "partnumber", "mfrpartnumber", "manufacturerpn")
PARAM_MFR = ("manufacturername", "manufacturer", "mf", "mfr")
EMPTY = {"", "none", "-", "—", "n/a", "na", "null", "*"}

SKIP_DIRS = {"history", "__previews", ".git", ".venv", "_legacy", "node_modules", "__pycache__"}
SEVERITY = {"error": 0, "warn": 1, "info": 2}
KINDS = ("missing_in_schematic", "missing_in_bom", "board_only", "missing_on_board",
         "footprint_mismatch", "mpn_mismatch", "value_mismatch", "stale_link",
         "broken_parameter", "qty_mismatch", "duplicate_ref", "unannotated", "source_error")


class BomImportError(ValueError):
    """Something the caller can fix: a bad path, a CSV without designators."""


class BomNotEmpty(BomImportError):
    """v1 imports into an empty BOM only; merging two BOMs is a different feature."""


class PathRefused(BomImportError):
    """A path outside the Altium project and the project folder."""


# ---------------------------------------------------------------- small helpers

def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def natural(ref):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", str(ref))]


def _clean(v):
    v = str(v or "").strip()
    return "" if v.lower() in EMPTY else v


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source(role, path):
    p = pathlib.Path(path)
    st = p.stat()
    return {"role": role, "path": str(p), "name": p.name,
            "mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "bytes": st.st_size, "sha256": _sha256(p)}


def _inside(path, root):
    try:
        a, b = os.path.normcase(str(path)), os.path.normcase(str(root))
        return os.path.commonpath([a, b]) == b
    except ValueError:        # another drive
        return False


def _n(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _short(refs, n=4):
    refs = list(refs)
    return ", ".join(refs[:n]) + (f" and {len(refs) - n} more" if len(refs) > n else "")


_DICT_REPR = re.compile(r"^\s*\{.*\}\s*$", re.S)


def clean_manufacturer(raw):
    """A manufacturer that arrived as the repr of a Python dict (a broken library
    parameter: `{'manufacturer': u'W\\xfcrth Elektronik'}`) -> (clean text, broken)."""
    raw = str(raw or "").strip()
    if not _DICT_REPR.match(raw):
        return raw, False
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, dict):
            val = val.get("manufacturer") or next((v for v in val.values() if isinstance(v, str)), "")
        return str(val or "").strip(), True
    except (ValueError, SyntaxError):
        m = re.search(r"u?'((?:[^'\\]|\\.)*)'\s*\}\s*$", raw)
        if not m:
            return "", True
        text = re.sub(r"\\x([0-9a-fA-F]{2})", lambda x: chr(int(x.group(1), 16)), m.group(1))
        return text.strip(), True


def split_refs(cell):
    return sorted({r for r in re.split(r"[,;\s]+", str(cell or "")) if r}, key=natural)


# ---------------------------------------------------------------- the CSV

def _decode(raw):
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252"


def _table(path):
    """(header map, [(row number, cells)], encoding, delimiter). The header is the first of
    the first ten rows that has a designator column - Altium can add a preamble. A row
    number is the one a spreadsheet shows, so a finding can name the row to look at."""
    text, enc = _decode(pathlib.Path(path).read_bytes())
    first = next((l for l in text.splitlines() if l.strip()), "")
    delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
    rows = [r for r in csv.reader(io.StringIO(text, newline=""), delimiter=delim)]
    for i, row in enumerate(rows[:10]):
        keys = [_key(c) for c in row]
        if any(k in COLUMNS["designators"] for k in keys):
            cols = {}
            for field, names in COLUMNS.items():
                for name in names:
                    if name in keys:
                        cols[field] = keys.index(name)
                        break
            return cols, [(j + 1, r) for j, r in enumerate(rows) if j > i and any(c.strip() for c in r)], enc, delim
    raise BomImportError(f"{pathlib.Path(path).name}: no Designator column found (expected Designator, "
                         "Designators or Reference in the first rows)")


def inspect_csv(path):
    """The lines of a BOM CSV plus what was understood about the file."""
    cols, rows, enc, delim = _table(path)
    lines, skipped = [], []
    for n, row in rows:
        cell = lambda f: (row[cols[f]].strip() if f in cols and cols[f] < len(row) else "")
        refs = split_refs(cell("designators"))
        if not refs:
            skipped.append({"row": n, "why": "no designators"})
            continue
        mfr, broken = clean_manufacturer(cell("manufacturer"))
        code = cell("lcsc")
        qty = cell("qty")
        try:
            qty = int(float(qty)) if qty else None
        except ValueError:
            qty = None
        lines.append({
            "row": n, "refs": refs, "value": cell("value"), "mpn": _clean(cell("mpn")),
            "manufacturer": _clean(mfr), "lcsc": code.upper() if re.fullmatch(r"(?i)C\d{2,}", code) else "",
            "footprint": cell("footprint"), "description": cell("description"), "qty": qty,
            "broken": [{"field": "manufacturer", "raw": cell("manufacturer")}] if broken else [],
        })
    return {"lines": lines, "skipped": skipped, "encoding": enc, "delimiter": delim,
            "columns": {f: i for f, i in cols.items()}, "rows": len(rows)}


def read_bom_csv(path):
    """Lines of a BOM CSV: refs (natural order), value, mpn, manufacturer (cleaned),
    lcsc, footprint, description, qty (as written) and what was broken in the row."""
    return inspect_csv(path)["lines"]


# ---------------------------------------------------------------- the Altium project

def _param(params, names):
    by_key = {_key(k): v for k, v in params.items()}
    for n in names:
        v = _clean(by_key.get(n))
        if v:
            return v
    return ""


_DNP = re.compile(r"(?i)\b(dnp|dni|do not (fit|populate|place)|not fitted)\b")


def _part(ref, stem, comp):
    params = comp.get("params") or {}
    comment = str(comp.get("comment") or "").strip()
    mfr, mfr_broken = clean_manufacturer(_param(params, PARAM_MFR))
    broken = {k: v for k, v in params.items() if isinstance(v, str) and _DICT_REPR.match(v)}
    return {
        "ref": ref, "sheet": stem, "comment": comment,
        "description": str(comp.get("description") or "").strip(),
        "footprint": str(comp.get("footprint") or "").strip(),
        "lib_ref": str(comp.get("lib_ref") or "").strip(),
        "mpn": _param(params, PARAM_MPN), "manufacturer": mfr,
        "urls": {k: v.strip() for k, v in params.items()
                 if isinstance(v, str) and re.match(r"(?i)^https?://", v.strip())},
        "broken": broken,
        "dnp": bool(_DNP.search(comment) or _DNP.search(str(params.get("DNP", "")) + " ")
                    or str(params.get("Fitted", "")).strip().lower() in ("no", "false", "0")),
    }


def read_altium_parts(prjpcb_path, pcb_path=None):
    """Per-ref data of every SchDoc of the project and of the PcbDoc. A multi-part
    component is one record, so it is one ref. A designator that still ends in '?'
    is not annotated: it cannot be matched to anything and is listed apart."""
    from altium import AltiumReadError, read_any
    prj = pathlib.Path(prjpcb_path)
    try:
        summary = read_any(prj)
    except AltiumReadError as exc:
        raise BomImportError(f"cannot read {prj.name}: {exc}") from exc
    sources = [_source("prjpcb", prj)]
    errors, sch, unannotated, dupes, stems = [], {}, [], {}, []

    for rel in summary.get("sheets", []):
        path = prj.parent / pathlib.PurePosixPath(rel.replace("\\", "/"))
        stem = path.stem
        try:
            doc = read_any(path)
            sources.append(_source("schdoc", path))
        except (AltiumReadError, OSError) as exc:
            errors.append(f"{rel}: {exc}")
            continue
        stems.append(stem)
        for comp in doc.get("components", []):
            ref = str(comp.get("ref") or "").strip()
            if not ref or ref.endswith("?"):
                unannotated.append({"ref": ref or "?", "sheet": stem, "comment": comp.get("comment", "")})
            elif ref in sch:
                dupes.setdefault(ref, [sch[ref]["sheet"]]).append(stem)
            else:
                sch[ref] = _part(ref, stem, comp)

    if pcb_path is None:
        pcbs = summary.get("pcbs", [])
        if len(pcbs) == 1:
            pcb_path = prj.parent / pathlib.PurePosixPath(pcbs[0].replace("\\", "/"))
    pcb = None
    if pcb_path:
        try:
            doc = read_any(pcb_path)
            sources.append(_source("pcbdoc", pcb_path))
            pcb = {}
            for c in doc.get("components", []):
                ref = str(c.get("ref") or "").strip()
                if ref:
                    pcb[ref] = {"ref": ref, "pattern": str(c.get("pattern") or "").strip(),
                                "layer": c.get("layer")}
        except (AltiumReadError, OSError) as exc:
            errors.append(f"{pathlib.Path(pcb_path).name}: {exc}")
    return {"sch": sch, "pcb": pcb, "unannotated": unannotated, "duplicates": dupes,
            "errors": errors, "sources": sources, "sheets": stems}


# ---------------------------------------------------------------- compare

def _norm_value(v):
    return re.sub(r"\s+", "", str(v or "").lower().replace("µ", "u").replace("μ", "u"))


def _mpn_match(a, b):
    """'same' | 'suffix' | 'differ'. Case and spaces never matter; a packaging suffix
    (/TR, +T, -TR) or punctuation alone is the same part ordered on a reel."""
    a, b = re.sub(r"\s+", "", a.lower()), re.sub(r"\s+", "", b.lower())
    if a == b:
        return "same"

    def core(s):
        while True:
            t = re.sub(r"(/tr|\+t|-tr|\+)$", "", s)
            if t == s:
                return _alnum(s)
            s = t
    return "suffix" if core(a) and core(a) == core(b) else "differ"


def _mpn_candidates(s):
    return [p.strip() for p in re.split(r"[,;]", s or "") if p.strip()]


_NOT_BOUGHT = re.compile(r"(?i)^(tp|mh|fid|nt|logo|mtg)[_-]?\d+\w*$")


def _mentions(url, *needles):
    u, flat = url.lower(), _alnum(url)
    for n in needles:
        n = (n or "").strip()
        if not n:
            continue
        if re.fullmatch(r"(?i)C\d{2,}", n):
            if n.lower() in u:
                return True
        elif _alnum(n)[:7] and _alnum(n)[:7] in flat:
            return True
    return False


def _has_path(url):
    return bool(re.sub(r"(?i)^https?://[^/?#]*/?", "", url).strip("/"))


def compare(csv_lines, altium):
    """Findings: {"kind","severity","refs","message","csv","sch","pcb"}. Sorted worst
    first. Reports only - nothing here changes what will be imported."""
    findings = []

    def add(kind, severity, refs, message, csv_=None, sch_=None, pcb_=None):
        findings.append({"kind": kind, "severity": severity, "refs": sorted(refs, key=natural),
                         "message": message, "csv": csv_, "sch": sch_, "pcb": pcb_})

    altium = altium or {}
    sch = altium.get("sch") or {}
    # no schematic at all (none linked, or none of its sheets could be read): nothing to compare against
    have_sch = altium.get("sch") is not None and not (not sch and altium.get("errors"))
    pcb = altium.get("pcb")

    for err in altium.get("errors", []):
        add("source_error", "error", [], f"Could not read {err}. Everything compared against it is incomplete.")

    # -- the CSV on its own
    seen = {}
    for line in csv_lines:
        for ref in line["refs"]:
            seen.setdefault(ref, []).append(line)
    for ref, where in seen.items():
        if len(where) > 1:
            add("duplicate_ref", "error", [ref],
                f"{ref} is listed on {len(where)} BOM lines (CSV rows {', '.join(str(l['row']) for l in where)}).",
                csv_=", ".join(l["value"] or l["mpn"] for l in where))
    for ref, comps in (altium.get("duplicates") or {}).items():
        add("duplicate_ref", "error", [ref], f"{ref} is used in more than one place in the schematic ({', '.join(comps)}).",
            sch_=", ".join(comps))

    for line in csv_lines:
        refs = line["refs"]
        if line.get("qty") is not None and line["qty"] != len(refs):
            add("qty_mismatch", "warn", refs, f"Row {line['row']}: Quantity says {line['qty']} but "
                f"{len(refs)} designators are listed ({_short(refs)}).", csv_=f"Qty {line['qty']}, {len(refs)} refs")

    # a broken parameter is one finding, whether the CSV, the schematic or both carry it
    sch_broken = {r: next(iter(p["broken"].values())) for r, p in sch.items() if p["broken"]}
    covered = set()
    for line in csv_lines:
        refs = line["refs"]
        for b in line.get("broken") or []:
            covered.update(refs)
            add("broken_parameter", "warn", refs, f"{_short(refs)}: the {b['field']} is a broken parameter "
                f"({b['raw']}) - imported as '{line.get(b['field'], '')}'. Fix the library parameter in Altium.",
                csv_=b["raw"], sch_=next((sch_broken[r] for r in refs if r in sch_broken), None))
    for ref, raw in sch_broken.items():
        if ref not in covered:
            add("broken_parameter", "warn", [ref], f"{ref}: a schematic parameter is a broken value ({raw}). "
                "Fix the library parameter in Altium.", sch_=raw)

    if not have_sch:
        return _sorted(findings)

    # -- CSV against the schematic and the board
    fp, mp, vl, stale = {}, {}, {}, {}
    for line in csv_lines:
        gone = [r for r in line["refs"] if r not in sch]
        for ref in gone:
            add("missing_in_schematic", "error", [ref],
                f"{ref} is in the BOM CSV (row {line['row']}) but in no schematic sheet of the project.",
                csv_=" ".join(x for x in (line["value"], line["mpn"]) if x))
        for ref in line["refs"]:
            part = sch.get(ref)
            if not part:
                continue
            pat = (pcb or {}).get(ref, {}).get("pattern") if pcb is not None else None
            fps = {_alnum(x) for x in (line["footprint"], part["footprint"], pat) if x}
            if len(fps) > 1:
                fp.setdefault((line["footprint"], part["footprint"], pat), []).append(ref)

            cands = _mpn_candidates(part["mpn"])
            if line["mpn"] and cands:
                grades = [_mpn_match(line["mpn"], c) for c in cands]
                best = "same" if "same" in grades else "suffix" if "suffix" in grades else "differ"
                if best != "same":
                    mp.setdefault((best, line["mpn"], part["mpn"]), []).append(ref)

            cmt = part["comment"]
            if line["value"] and cmt and not cmt.startswith("=") and _norm_value(line["value"]) != _norm_value(cmt):
                vl.setdefault((line["value"], cmt), []).append(ref)

            for name, url in part["urls"].items():
                if _has_path(url) and (line["mpn"] or part["mpn"] or line["lcsc"]) and not _mentions(
                        url, line["mpn"], *cands, line["lcsc"]):
                    stale.setdefault((url, line["mpn"] or part["mpn"], line["lcsc"]), {}).setdefault(name, []).append(ref)

    for (c, s, p), refs in fp.items():
        add("footprint_mismatch", "warn", refs, f"{_short(refs)}: the footprint differs between the files - CSV "
            f"'{c}', schematic '{s}', PcbDoc '{p if p is not None else '(not on the board)'}'.", c, s, p)
    for (grade, c, s), refs in mp.items():
        if grade == "suffix":
            add("mpn_mismatch", "warn", refs, f"{_short(refs)}: MPN differs only by a packaging suffix - CSV '{c}', "
                f"schematic '{s}'.", c, s)
        else:
            add("mpn_mismatch", "error", refs, f"{_short(refs)}: MPN differs - CSV '{c}', schematic parameter '{s}'. "
                "The import keeps the CSV's.", c, s)
    for (c, s), refs in vl.items():
        add("value_mismatch", "info", refs, f"{_short(refs)}: value '{c}' in the CSV, comment '{s}' in the schematic.", c, s)
    for (url, mpn, code), by_name in stale.items():      # one finding per link, however many parameters carry it
        refs = sorted({r for rs in by_name.values() for r in rs}, key=natural)
        names = "', '".join(by_name)
        what = " nor ".join(x for x in (mpn, f"LCSC {code}" if code else "") if x)
        add("stale_link", "warn", refs, f"{_short(refs)}: parameter '{names}' mentions neither {what} - it may point at "
            f"another part: {url}", mpn or code, url)

    # -- the schematic against the CSV
    in_csv = set(seen)
    for ref, part in sch.items():
        if ref in in_csv:
            continue
        calm = part["dnp"] or _NOT_BOUGHT.match(ref)
        add("missing_in_bom", "info" if calm else "warn", [ref],
            f"{ref} is in the schematic ({part['sheet']}) but on no line of the BOM CSV"
            + (" - marked do-not-fit." if part["dnp"] else " - looks like a test point or mechanical part." if calm else "."),
            sch_=" ".join(x for x in (part["comment"], part["footprint"]) if x))

    # -- the board
    if pcb is not None:
        for ref, c in pcb.items():
            if ref not in sch:
                calm = _NOT_BOUGHT.match(ref) or re.match(r"(?i)^(h|m)\d+$", ref)
                add("board_only", "info" if calm else "warn", [ref],
                    f"{ref} is on the PcbDoc ({c['pattern']}) but in no schematic sheet"
                    + (" (mounting hole, logo or fiducial)." if calm else "."), pcb_=c["pattern"])
        for ref, part in sch.items():
            if ref not in pcb:
                add("missing_on_board", "warn", [ref], f"{ref} ({part['sheet']}) is in the schematic but not on the PcbDoc.",
                    sch_=part["footprint"])

    un = altium.get("unannotated") or []
    if un:
        add("unannotated", "warn", [u["ref"] for u in un][:200],
            f"{len(un)} schematic components still have a '?' designator ({_short([u['ref'] for u in un], 6)}). "
            "Annotate them in Altium, then export the BOM again.")
    return _sorted(findings)


def _sorted(findings):
    return sorted(findings, key=lambda f: (SEVERITY[f["severity"]], f["kind"], natural(f["refs"][0]) if f["refs"] else []))


# ---------------------------------------------------------------- the lines to import

def build_lines(csv_lines, altium=None):
    """The bom-log `changes` of every line, keyed like the rest of the BOM: by the first
    designator. The CSV is the truth; a field it leaves empty is filled from the
    schematic (an Altium default BOM has no MPN column, the component parameters do)."""
    sch = (altium or {}).get("sch") or {}
    out, used = [], set()
    for line in csv_lines:
        refs = line["refs"]
        part = next((sch[r] for r in refs if r in sch), {})
        key, n = refs[0], 2
        while key in used:               # only a duplicated designator gets here; compare() reports it
            key, n = f"{refs[0]}-{n}", n + 1
        used.add(key)
        comment = part.get("comment", "")
        changes = {
            "refs": refs,
            "value": line["value"] or ("" if comment.startswith("=") else comment),
            "description": line["description"] or part.get("description", ""),
            "mpn": line["mpn"] or (_mpn_candidates(part.get("mpn", "")) or [""])[0],
            "manufacturer": line["manufacturer"] or part.get("manufacturer", ""),
            "package": line["footprint"] or part.get("footprint", ""),
        }
        if line["lcsc"]:
            changes["lcsc"] = line["lcsc"]
        if part.get("sheet"):
            changes["sheet"] = part["sheet"]
        out.append({"line": key, "changes": changes})
    return out


def library_entries(entries, altium):
    """A finished project's parts already have a symbol and a footprint: the ones the
    schematic and the PcbDoc use. Recorded as in the library and unchecked - nothing
    here compares a footprint with its datasheet, so the student still reviews them."""
    sch = (altium or {}).get("sch") or {}
    pcb = (altium or {}).get("pcb") or {}
    out = []
    for e in entries:
        refs = e["changes"]["refs"]
        part = next((sch[r] for r in refs if r in sch), {})
        symbol = part.get("lib_ref", "")
        footprint = next((pcb[r]["pattern"] for r in refs if pcb.get(r, {}).get("pattern")), "") \
            or part.get("footprint", "")
        if symbol and footprint:
            out.append({"line": e["line"], "changes": {
                "symbol": symbol, "footprint": footprint, "model_source": "Altium project",
                "verify": "unchecked", "accepted": False, "issues": ""}})
    return out


# ---------------------------------------------------------------- one run

def _altium_paths(project, prjpcb, pcb):
    link = project_mod.altium_link(project)
    prj = prjpcb or link["project_file"] or None
    if prj and not pathlib.Path(prj).is_file():
        raise BomImportError(f"Altium project not found: {prj}")
    if pcb is None and prj and link["project_file"] and pathlib.Path(prj) == pathlib.Path(link["project_file"]):
        pcb = link["pcb_file"] or None
    return prj, pcb


def _run(project, csv_path, prjpcb=None, pcb=None):
    csv_path = pathlib.Path(csv_path)
    if not csv_path.is_file():
        raise BomImportError(f"BOM file not found: {csv_path}")
    info = inspect_csv(csv_path)
    prj, pcb_path = _altium_paths(project, prjpcb, pcb)
    altium = read_altium_parts(prj, pcb_path) if prj else None
    findings = compare(info["lines"], altium)
    by_kind, by_sev = {}, {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        by_sev[f["severity"]] += 1
    report = {
        "project": project, "generated": store.now(), "applied": False,
        "sources": [_source("bom_csv", csv_path)] + (altium["sources"] if altium else []),
        "csv": {"rows": info["rows"], "lines": len(info["lines"]),
                "refs": sum(len(l["refs"]) for l in info["lines"]), "encoding": info["encoding"],
                "columns": sorted(info["columns"]), "skipped": info["skipped"]},
        "altium": None if not altium else {
            "sheets": altium["sheets"], "sch_components": len(altium["sch"]),
            "pcb_components": None if altium["pcb"] is None else len(altium["pcb"]),
            "unannotated": len(altium["unannotated"])},
        "bom_empty": not store.bom_lines(project),
        "by_severity": by_sev, "by_kind": by_kind, "findings": findings,
    }
    return report, info["lines"], altium


def report_dir(project):
    return store.pdir(project) / "checks"


def write_report(project, report):
    d = report_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    (d / "bom-import.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "bom-import.md").write_text(markdown(report), encoding="utf-8")


def markdown(report):
    cell = lambda v: str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")
    csv_src = next(s for s in report["sources"] if s["role"] == "bom_csv")
    out = [f"# BOM import - {report['project']}", "",
           f"{'Imported' if report['applied'] else 'Preview (nothing imported)'} at {report['generated']}. "
           f"{_n(report['csv']['lines'], 'BOM line')}, {_n(report['csv']['refs'], 'designator')} from {csv_src['name']}.", "",
           "## Sources", "", "| role | file | modified | sha256 |", "|---|---|---|---|"]
    out += [f"| {s['role']} | {cell(s['path'])} | {s['mtime']} | {s['sha256'][:12]} |" for s in report["sources"]]
    sev = report["by_severity"]
    out += ["", "## Findings", "", f"{_n(sev['error'], 'error')}, {_n(sev['warn'], 'warning')}, {_n(sev['info'], 'note')}.", ""]
    if report["by_kind"]:
        out += ["| kind | count |", "|---|---|"] + [f"| {k} | {n} |" for k, n in sorted(report["by_kind"].items())] + [""]
        out += ["| severity | kind | refs | message |", "|---|---|---|---|"]
        out += [f"| {f['severity']} | {f['kind']} | {cell(_short(f['refs'], 6))} | {cell(f['message'])} |"
                for f in report["findings"]]
    else:
        out.append("The files agree.")
    out += ["", "The source files are never changed. A finding is for you to decide; the imported "
            "lines keep what the BOM CSV says.", ""]
    return "\n".join(out)


def preview(project, csv_path, prjpcb=None, pcb=None):
    """Read and compare; write the report, not the BOM."""
    report, _, _ = _run(project, csv_path, prjpcb, pcb)
    write_report(project, report)
    return report


def apply(project, csv_path, prjpcb=None, pcb=None):
    """Append one bom-log event per line (by=import). Into an empty BOM only."""
    if not project_mod.exists(project):
        raise BomImportError(f"no such project: {project}")
    n = len(store.bom_lines(project))
    if n:
        raise BomNotEmpty(f"The BOM already has {n} lines. Import works into an empty BOM.")
    report, lines, altium = _run(project, csv_path, prjpcb, pcb)
    src = next(s for s in report["sources"] if s["role"] == "bom_csv")
    reason = f"Imported from {src['name']} (sha256 {src['sha256'][:12]})"
    entries = build_lines(lines, altium)
    ts = store.now()
    for e in entries:
        store.append(project, "bom-log.jsonl", {"ts": ts, "by": "import", "line": e["line"],
                                                "changes": e["changes"], "reason": reason})
    lib = library_entries(entries, altium)
    for e in lib:
        store.append(project, "library-log.jsonl", {"ts": ts, "by": "import", "line": e["line"],
                                                    "changes": e["changes"], "reason": reason})
    report.update(applied=True, imported_lines=len(entries), library_lines=len(lib), bom_empty=False)
    write_report(project, report)
    store.bom(project)                    # bom.json follows the log
    project_mod.touch(project)
    return report


# ---------------------------------------------------------------- finding the CSV

def altium_dirs(project):
    """The linked Altium project's folder and its outputs folder, where they exist."""
    link = project_mod.altium_link(project)
    dirs = []
    if link["project_file"]:
        dirs.append(pathlib.Path(link["project_file"]).parent)
    if link["outputs_dir"]:
        dirs.append(pathlib.Path(link["outputs_dir"]))
    return [d for d in dirs if d.is_dir()]


def candidates(project, limit=50):
    """BOM-like CSV files under the linked outputs folder and the project folder,
    newest first. Backups, previews and the virtual environment are not searched."""
    out, seen = [], set()
    for root in altium_dirs(project):
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
            for name in files:
                if not (name.lower().endswith(".csv") and "bom" in name.lower()):
                    continue
                path = pathlib.Path(dirpath) / name
                real = os.path.normcase(str(path.resolve()))
                if real in seen:
                    continue
                seen.add(real)
                try:
                    cols, rows, _, _ = _table(path)
                    mtime = path.stat().st_mtime
                except (BomImportError, OSError):
                    continue                  # not a BOM we can read
                out.append({"path": str(path), "name": name, "folder": str(pathlib.Path(dirpath)),
                            "mtime": dt.datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                            "rows": len(rows), "has_lcsc": "lcsc" in cols, "has_mpn": "mpn" in cols,
                            "_t": mtime})
    out.sort(key=lambda c: c["_t"], reverse=True)
    for c in out:
        del c["_t"]
    return out[:limit]


def resolve_csv(project, csv_path, restrict=True):
    """The CSV to read. For a request from the browser (restrict) it must sit inside the
    linked Altium project's folder or the project's own folder: a path from a web page
    is never a licence to read any file on the disk. A relative path is tried against
    both folders."""
    raw = str(csv_path or "").strip()
    if not raw:
        raise BomImportError("csv path required")
    roots = [*altium_dirs(project), store.pdir(project)]
    p = pathlib.Path(raw)
    if not p.is_absolute():
        p = next((r / p for r in roots if (r / p).is_file()), p)
    try:
        target = p.resolve()
    except (OSError, ValueError) as exc:
        raise BomImportError(f"bad path: {exc}") from exc
    if restrict and not any(_inside(target, r.resolve()) for r in roots):
        raise PathRefused("The BOM file must be inside the linked Altium project or the project folder.")
    if target.suffix.lower() != ".csv":
        raise BomImportError("The BOM file must be a .csv")
    if not target.is_file():
        raise BomImportError(f"BOM file not found: {target.name}")
    return target


# ---------------------------------------------------------------- command line

def summary(report):
    sev, csv_info = report["by_severity"], report["csv"]
    src = {s["role"]: s for s in report["sources"]}
    alt = report["altium"]
    out = [f"BOM import for {report['project']}: {'IMPORTED' if report['applied'] else 'dry run, nothing written to the BOM'}",
           f"  BOM CSV   {src['bom_csv']['path']}",
           f"            {_n(csv_info['lines'], 'line')}, {_n(csv_info['refs'], 'designator')}, sha256 {src['bom_csv']['sha256'][:12]}, "
           f"modified {src['bom_csv']['mtime']}"]
    if alt:
        out.append(f"  Altium    {src['prjpcb']['path']}: {len(alt['sheets'])} sheets, {alt['sch_components']} components"
                   + (f"; PcbDoc {alt['pcb_components']} components" if alt["pcb_components"] is not None
                      else "; no PcbDoc compared"))
    else:
        out.append("  Altium    no project linked: only the CSV itself was checked")
    out.append(f"  Findings  {_n(sev['error'], 'error')}, {_n(sev['warn'], 'warning')}, {_n(sev['info'], 'note')}")
    out += [f"    {k:22} {n}" for k, n in sorted(report["by_kind"].items(), key=lambda kv: (-kv[1], kv[0]))]
    for f in report["findings"]:
        out.append(f"  [{f['severity']:5}] {f['kind']:20} {f['message']}")
    out.append(f"  Report    {report_dir(report['project']) / 'bom-import.md'}")
    if not report["applied"]:
        out.append("  Add --apply to import." if report["bom_empty"]
                   else "  The BOM already has lines: import works into an empty BOM only.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import a BOM CSV exported from Altium, and compare it with the project.")
    ap.add_argument("project")
    ap.add_argument("csv", nargs="?", help="the BOM CSV; omit to list the candidates")
    ap.add_argument("--prjpcb", help="default: the project's Altium link")
    ap.add_argument("--pcb", help="default: the project's Altium link")
    ap.add_argument("--apply", action="store_true", help="append the lines to the (empty) BOM")
    a = ap.parse_args(argv)
    name = workspace.safe_name(a.project)
    try:
        if not project_mod.exists(name):
            raise BomImportError(f"no such project: {a.project}")
        if not a.csv:
            for c in candidates(name):
                print(f"{c['mtime']}  {c['rows']:>4} rows  {'LCSC' if c['has_lcsc'] else '    '}  {c['path']}")
            return 0
        report = (apply if a.apply else preview)(name, a.csv, a.prjpcb, a.pcb)
    except BomImportError as exc:
        raise SystemExit(f"bom_import: {exc}")
    print(summary(report))
    return 0


if __name__ == "__main__":
    oscompat.utf8_stdio()
    sys.exit(main())
