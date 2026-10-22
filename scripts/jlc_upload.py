"""
The JLC check done together with the student, at the end of the design.

The student's JLCPCB account stays theirs: this module never logs in, never sees a password and never uploads. It does
the two things around the upload that need no account.

1. gerber_zip(project)   the zip JLCDFM and the JLC quote page take: the newest Gerber + NC drill set of the linked
                         Altium project, flat, written to projects/<p>/exports/<p>_gerbers.zip. The Altium folder is
                         only read. The result says which files went in, when they were written, and what is missing.
2. pickup(project)       the report the student exported from jlcdfm.com lands in their Downloads folder. This lists
                         that folder by name, opens only the JLCDFM report PDFs that arrived since the last report (or
                         since the zip was made), checks `%PDF-`, and ingests them with scripts/dfm.py.

CLI (through dfm.py, which the agent may run):
    python scripts/dfm.py gerber-zip <project>
    python scripts/dfm.py pickup <project> [--kind pcb|smt|both] [--name FILE]
"""
import datetime as dt
import os
import pathlib
import re
import sys
import zipfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dfm  # noqa: E402
import project as project_mod  # noqa: E402
import workspace  # noqa: E402

SKIP_DIRS = {"history", "__history", "__previews", ".git", ".venv", "node_modules", "__pycache__"}
MAX_WALK = 20000                      # files looked at in an outputs folder, so a huge tree cannot stall the server
ZIP_LIMIT_MB = 50                     # JLCDFM: "zip/rar format, max 50MB" (shared/reference/jlc/jlcdfm.en.md [D1])
FIRST_WINDOW_H = 24                   # no report and no zip yet: only files that arrived in the last day are new
MAX_PICKUP = 10                       # reports added by one pickup
MAX_REPORT_MB = 100
DRILL_EXT = {".txt", ".drl", ".xln", ".exc"}

# Altium's (Protel) extensions, as shared/reference/jlc/files-and-formats.en.md lists them
_FIXED = {
    ".gtl": ("copper", "Top copper"), ".gbl": ("copper", "Bottom copper"),
    ".gto": ("silk", "Top silkscreen"), ".gbo": ("silk", "Bottom silkscreen"),
    ".gts": ("mask", "Top solder mask"), ".gbs": ("mask", "Bottom solder mask"),
    ".gtp": ("paste", "Top paste"), ".gbp": ("paste", "Bottom paste"),
    ".gko": ("outline", "Board outline"),
}
# what is missing, and how much it matters: (group or exact label, shown name, extension to look for, level, why)
DFM_NAME = re.compile(r"^(?:dfm[ _-]*analysis[ _-]*report.*|.*jlcdfm.*)\.pdf$", re.I)


class UploadError(ValueError):
    """Nothing to build or read; the message says what to do."""


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def classify(name: str) -> tuple[str, str] | None:
    """(group, label) of an Altium output file by its extension, or None: copper, silk, mask, paste, outline, plane, drill."""
    ext = pathlib.PurePath(name).suffix.lower()
    if ext in _FIXED:
        return _FIXED[ext]
    if re.fullmatch(r"\.gm\d+", ext):
        return ("outline", "Board outline")
    if m := re.fullmatch(r"\.g(\d+)", ext):
        return ("copper", f"Inner copper {m.group(1)}")
    if m := re.fullmatch(r"\.gp(\d+)", ext):
        return ("plane", f"Inner plane {m.group(1)}")
    if ext in DRILL_EXT:
        return ("drill", "NC drill")
    return None


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _zip_path(project: str) -> pathlib.Path:
    return workspace.project_dir(project) / "exports" / f"{workspace.safe_name(project)}_gerbers.zip"


# ---------------------------------------------------------------- 1. the Gerber zip

def _roots(project: str) -> list[pathlib.Path]:
    """Where the Altium project's fabrication outputs can be: the linked outputs folder, 'Project Outputs for ...' next to
    the project file. Read only, never created."""
    link = project_mod.altium_link(project)
    roots: list[pathlib.Path] = []
    if link.get("outputs_dir"):
        roots.append(pathlib.Path(link["outputs_dir"]))
    if link.get("project_file"):
        prj = pathlib.Path(link["project_file"]).parent
        try:
            roots += sorted(p for p in prj.iterdir() if p.is_dir() and p.name.lower().startswith("project outputs for"))
        except OSError:
            pass
        roots.append(prj / "Outputs")
    out, seen = [], set()
    for r in roots:
        key = os.path.normcase(str(r))
        if key not in seen and r.is_dir():
            seen.add(key)
            out.append(r)
    return out


def _is_excellon(path: pathlib.Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"M48" in fh.read(2048)
    except OSError:
        return False


def _is_x2(path: pathlib.Path) -> bool:
    """Gerber X2 attributes (as %TF. or as G04 comments): JLC reads them before the file name (files-and-formats F1, F5)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return b"%TF." in head or b"G04 #@! TF." in head


def _walk(roots: list[pathlib.Path]):
    """(path, stat) of every file under the roots, not in a backup or history folder."""
    seen = 0
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
            for name in files:
                seen += 1
                if seen > MAX_WALK:
                    return
                p = pathlib.Path(dirpath) / name
                try:
                    yield p, p.stat()
                except OSError:
                    continue


def _stem(p: pathlib.Path) -> str:
    return p.stem.lower()


def find_set(project: str) -> dict[str, Any]:
    """The newest Gerber set and the NC drill files that go with it, in the linked Altium outputs: {gerbers, drills, roots}.
    Each is a list of (path, stat)."""
    roots = _roots(project)
    if not roots:
        raise UploadError("No Altium outputs folder to read. Link the Altium project in Settings, then run the OutJob "
                          "(Generate content) in Altium.")
    gerber: dict[tuple[str, str], list] = {}
    drills: dict[str, list] = {}
    for p, st in _walk(roots):
        c = classify(p.name)
        if not c or st.st_size == 0:
            continue
        if c[0] == "drill":
            if _is_excellon(p):
                drills.setdefault(str(p.parent), []).append((p, st))
        else:
            gerber.setdefault((str(p.parent), _stem(p)), []).append((p, st))
    if not gerber:
        names = ", ".join(r.name for r in roots)
        raise UploadError(f"No Gerber files (.GTL .GBL .GTS ...) under {names}. Run the OutJob in Altium "
                          "(Generate content), then try again.")
    newest = lambda files: max(st.st_mtime for _, st in files)
    (gdir, gstem), gfiles = max(gerber.items(), key=lambda kv: (newest(kv[1]), len(kv[1])))
    # the drill files: the same folder when it has them, else the folder written closest in time to the Gerbers
    pick = None
    if gdir in drills:
        pick = gdir
    elif drills:
        pick = min(drills, key=lambda d: abs(newest(drills[d]) - newest(gfiles)))
    dfiles = drills.get(pick, [])
    same = [(p, st) for p, st in dfiles if _stem(p).startswith(gstem)]
    return {"gerbers": sorted(gfiles, key=lambda x: x[0].name.lower()),
            "drills": sorted(same or dfiles, key=lambda x: x[0].name.lower()), "roots": roots}


EMPTY_SCAN_BYTES = 262144


def _has_draws(data: bytes) -> bool:
    """Whether a Gerber has any coordinate data or D01/D03 operation once its comments and %...% parameter blocks
    (format, apertures) are taken out. A header-only file (Altium's, when nothing was drawn on the layer) has none."""
    text = re.sub(rb"%.*?%", b"", data, flags=re.S)
    text = re.sub(rb"G04[^*]*\*", b"", text)
    return re.search(rb"[XY][-+]?\d|D0[13]\*", text) is not None


def _problems(entries: list[dict]) -> tuple[list[dict], list[str]]:
    """What the set lacks and what looks wrong, from the file list ({name, group, layer})."""
    have = {e["layer"] for e in entries}
    groups = [e["group"] for e in entries]
    missing, warnings = [], []

    def lack(layer, ext, level, why):
        missing.append({"layer": layer, "ext": ext, "level": level, "why": why})

    if "Top copper" not in have:
        lack("Top copper", ".GTL", "problem", "JLC builds the board from the copper layers.")
    if "outline" not in groups:
        lack("Board outline", ".GM1 or .GKO", "problem", "JLC cancels an order without an outline layer.")
    elif all(e.get("empty") for e in entries if e["group"] == "outline"):
        lack("Board outline", ".GM1 or .GKO", "problem",
             "The outline layer has no drawing: draw the board shape on it (Altium: Design » Board Shape » Create "
             "Primitives From Board Shape, on Mechanical 1) and run the outputs again.")
    if "drill" not in groups:
        lack("NC drill", ".TXT (Excellon)", "problem", "JLC cancels an order without a drill file, unless the board has no holes.")
    if "Top solder mask" not in have:
        lack("Top solder mask", ".GTS", "problem", "A missing mask layer covers the whole board in mask.")
    if "Bottom copper" not in have:
        lack("Bottom copper", ".GBL", "note", "Only a one-layer board has none.")
    elif "Bottom solder mask" not in have:
        lack("Bottom solder mask", ".GBS", "problem", "A missing mask layer covers the whole board in mask.")
    for layer, ext in (("Top silkscreen", ".GTO"), ("Bottom silkscreen", ".GBO")):
        if layer not in have and (layer.startswith("Top") or "Bottom copper" in have):
            lack(layer, ext, "note", "The board will carry no printing on that side.")
    outlines = [e["name"] for e in entries if e["group"] == "outline"]
    if len(outlines) > 1:
        warnings.append(f"{len(outlines)} outline layers ({', '.join(outlines)}): keep one, JLC may take the wrong one.")
    if "plane" in groups:
        warnings.append("Inner plane layers (.GP1): JLC's site does not look for them. Check the inner layers in JLCDFM.")
    return missing, warnings


def _describe(path: pathlib.Path) -> dict[str, Any]:
    """The zip as it is on disk: its files by layer, when they were written, what is missing."""
    with zipfile.ZipFile(path) as z:
        entries = []
        for i in z.infolist():
            c = classify(i.filename)
            when = dt.datetime(*i.date_time).isoformat(timespec="seconds")
            entries.append({"name": i.filename, "group": c[0] if c else "other", "layer": c[1] if c else "Other",
                            "bytes": i.file_size, "modified": when})
            if c and c[0] == "outline":
                with z.open(i) as fh:
                    entries[-1]["empty"] = not _has_draws(fh.read(EMPTY_SCAN_BYTES))
    missing, warnings = _problems(entries)
    size = path.stat().st_size
    if size > ZIP_LIMIT_MB * 1024 * 1024:
        warnings.append(f"The zip is {size / 1048576:.0f} MB; JLCDFM takes up to {ZIP_LIMIT_MB} MB.")
    exports = path.parent
    name = workspace.safe_name(path.name[: -len("_gerbers.zip")])
    assembly = {"bom": f"{name}_BOM_jlc.csv", "cpl": f"{name}_cpl.csv"}
    assembly = {k: (v if (exports / v).is_file() else None) for k, v in assembly.items()}
    return {
        "exists": True, "zip": path.name, "bytes": size, "built": _iso(path.stat().st_mtime),
        "generated": max((e["modified"] for e in entries), default=None), "files": entries,
        "complete": not any(m["level"] == "problem" for m in missing), "missing": missing, "warnings": warnings,
        "assembly": assembly,
    }


def zip_info(project: str) -> dict[str, Any]:
    """What gerber_zip made last time, or {"exists": False}."""
    path = _zip_path(project)
    if not path.is_file():
        return {"exists": False, "zip": path.name}
    try:
        return _describe(path)
    except (zipfile.BadZipFile, OSError):
        return {"exists": False, "zip": path.name}


def gerber_zip(project: str) -> dict[str, Any]:
    """Build projects/<p>/exports/<p>_gerbers.zip from the newest Gerber + NC drill set in the linked Altium outputs.
    Raises UploadError when there is nothing to read. The set is written even when layers are missing: `missing` says which."""
    found = find_set(project)
    files, seen = [], set()
    for p, st in found["gerbers"] + found["drills"]:
        if p.name.lower() in seen:
            continue                                                  # two files of one name cannot sit in a flat zip
        seen.add(p.name.lower())
        files.append((p, st))
    out = _zip_path(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for p, _ in files:
            z.write(p, arcname=p.name)                                # flat: JLC wants no folder inside the archive
    os.replace(tmp, out)
    res = _describe(out)
    newest = max(st.st_mtime for _, st in files)
    stale = [p.name for p, st in files if newest - st.st_mtime > 3600 and classify(p.name)[0] != "drill"]
    if stale:
        res["warnings"].append(f"{', '.join(stale)} written more than an hour before the rest: an old export? Generate the outputs again.")
    if found["drills"] and abs(max(st.st_mtime for _, st in found["drills"]) - max(st.st_mtime for _, st in found["gerbers"])) > 3600:
        res["warnings"].append("The drill files were written more than an hour apart from the Gerbers: generate both again.")
    if any(_is_x2(p) for p, _ in found["gerbers"]):
        res["warnings"].append("These look like Gerber X2 files. JLC's Altium guide asks for Gerber Files (RS-274X), not X2.")
    res["source"] = str(found["gerbers"][0][0].parent)
    if found["drills"] and found["drills"][0][0].parent != found["gerbers"][0][0].parent:
        res["drill_source"] = str(found["drills"][0][0].parent)
    res["built_now"] = True
    try:
        from altium import bridge
        design = bridge.design_problems(project)
    except Exception:                                    # the zip is still made; this only adds a warning
        design = []
    if design:
        res["warnings"].append(f"The board does not match the design ({len(design)} problem(s)): " + " | ".join(design[:5])
                               + (" ..." if len(design) > 5 else "") + " These Gerbers would be made without those connections.")
    import lineage
    pcb = lineage.linked_pcb(project)
    rec = lineage.note(project, out, lambda: [lineage.file_input("drill" if classify(p.name)[0] == "drill" else "gerber", p)
                                              for p, _ in files] + ([lineage.file_input("pcb", pcb)] if pcb else []),
                       "gerber_zip", source=res["source"])
    early = lineage.check(project, rec)["reasons"] if rec else []
    res["warnings"] += [w[0].upper() + w[1:] + ": generate the outputs in Altium again." for w in early if "saved after" in w]
    return res


# ---------------------------------------------------------------- 2. the report in Downloads

def downloads_dir() -> pathlib.Path:
    """Where the browser saves: `workspace.downloads_dir` in config.json, else the user's Downloads folder."""
    raw = workspace.get("workspace.downloads_dir") or ""
    if raw:
        return pathlib.Path(os.path.expandvars(str(raw))).expanduser()
    return pathlib.Path.home() / "Downloads"


def _arrived(st: os.stat_result) -> float:
    """When the file came to this folder. The creation time on Windows, so a browser that stamps the server's
    Last-Modified date on a download does not make a new file look old."""
    return max(st.st_mtime, getattr(st, "st_birthtime", st.st_ctime))


def since(project: str) -> dt.datetime:
    """A report is new when it arrived after this: the newest report of the project, or the zip made for it, whichever is
    later; with neither, the last day."""
    marks = [t for t in (dfm.last_ingest_at(project),) if t]
    z = _zip_path(project)
    if z.is_file():
        marks.append(dt.datetime.fromtimestamp(z.stat().st_mtime))
    return max(marks) if marks else dt.datetime.now() - dt.timedelta(hours=FIRST_WINDOW_H)


def pickup(project: str, kind: str | None = None, name: str | None = None, downloads: str | pathlib.Path | None = None) -> dict[str, Any]:
    """Add the JLCDFM reports that are new in the Downloads folder to the project.

    Only the folder listing and the matching PDFs are read: a file is opened when its name is a JLCDFM report name, it
    arrived after since(project) (or it is `name`), and it starts with `%PDF-`. A report whose header does not say what it
    covers is not added: it comes back under `pending` until `kind` ('pcb', 'smt' or 'both') or the student says.
    Returns {ok, folder, folder_exists, since, found, pending, skipped, older, older_files}."""
    if kind is not None and kind not in dfm.KINDS:
        raise ValueError(f"kind must be one of {', '.join(dfm.KINDS)}")
    if name is not None and (pathlib.PurePath(name).name != name or not DFM_NAME.match(name)):
        raise ValueError("name must be the file name of a JLCDFM report in the Downloads folder")
    folder = pathlib.Path(downloads) if downloads else downloads_dir()
    cutoff = since(project)
    res: dict[str, Any] = {"ok": True, "folder": str(folder), "folder_exists": folder.is_dir(), "since": cutoff.isoformat(timespec="seconds"),
                           "found": [], "pending": [], "skipped": [], "older": 0}
    if not res["folder_exists"]:
        res["ok"] = False
        return res
    cands, older = [], []
    try:
        with os.scandir(folder) as it:
            for e in it:
                if not DFM_NAME.match(e.name) or (name is not None and e.name != name):
                    continue
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                at = dt.datetime.fromtimestamp(_arrived(st))
                if name is None and at < cutoff:
                    res["older"] += 1
                    older.append({"name": e.name, "bytes": st.st_size, "arrived": at.isoformat(timespec="seconds")})
                    continue
                cands.append((at, e.path, e.name, st.st_size))
    except OSError as exc:
        res["ok"], res["error"] = False, f"could not list {folder}: {exc}"
        return res
    # the names of the older ones (newest first): the student can still pick one with `name`
    res["older_files"] = sorted(older, key=lambda o: o["arrived"], reverse=True)[:5]
    known = dfm.ingested_hashes(project)
    for at, path, fname, size in sorted(cands)[:MAX_PICKUP]:
        item = {"name": fname, "bytes": size, "arrived": at.isoformat(timespec="seconds")}
        if size > MAX_REPORT_MB * 1024 * 1024:
            res["skipped"].append({**item, "reason": f"larger than {MAX_REPORT_MB} MB"})
            continue
        try:
            raw = pathlib.Path(path).read_bytes()
        except OSError as exc:
            res["skipped"].append({**item, "reason": f"could not be read: {exc}"})
            continue
        if not raw.startswith(b"%PDF-"):
            res["skipped"].append({**item, "reason": "not a PDF (empty or still downloading?)"})
            continue
        sha = dfm.pdf_sha256(raw)
        if sha in known:
            res["skipped"].append({**item, "reason": "already added", "stem": known[sha]})
            continue
        try:
            r = dfm.ingest_pdf(raw, project, name=fname, kind=kind or "auto", source="downloads")
        except dfm.KindUnknown as exc:
            res["pending"].append({**item, "reason": str(exc)})
            continue
        except Exception as exc:                                       # a PDF of another kind, or a damaged one
            res["skipped"].append({**item, "reason": f"could not be read as a JLCDFM report: {exc}"})
            continue
        known[sha] = r["stem"]
        res["found"].append({**item, "stem": r["stem"], "kind": r["kind"], "slices": r["slices"],
                             "kind_from": "you" if kind else "the report header"})
    return res
