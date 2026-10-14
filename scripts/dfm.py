"""
Ingest and triage JLCDFM report PDFs.

A JLCDFM report PDF (jlcdfm.com) is typically one tall page containing a single
embedded JPEG (~2400 x 15000 px) with no text layer.

This script extracts the embedded image using pypdf, slices it into ~1400 px height
slices stored in projects/<p>/checks/<report-stem>/, and writes index.json.
Triage findings are stored in projects/<p>/checks/<report-stem>/triage.json.

CLI:
    python scripts/dfm.py ingest <project> <pdf_path> [--kind pcb|smt|both|auto]
    python scripts/dfm.py list <project> [--kind pcb|smt]
    python scripts/dfm.py triage <project> <stem>
    python scripts/dfm.py gerber-zip <project>                        the Gerber + drill zip JLC wants (scripts/jlc_upload.py)
    python scripts/dfm.py pickup <project> [--kind K] [--name FILE]   new JLCDFM reports from the Downloads folder
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import sys
from typing import Any

import pypdf
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import oscompat  # noqa: E402
import workspace  # noqa: E402

SLICE_HEIGHT = 1400
KINDS = ("pcb", "smt", "both")
ALLOWED_VERDICTS = {"real", "model", "by design", "unknown"}


def sanitize_stem(name: str) -> str:
    """Create a clean directory name from a PDF filename."""
    stem = pathlib.Path(name).stem
    clean = re.sub(r"[^\w\-.]", "_", stem).strip("_")
    return clean or "dfm_report"


def extract_embedded_images(pdf_input: str | pathlib.Path | bytes) -> list[Image.Image]:
    """Extract embedded images from a PDF using pypdf."""
    if isinstance(pdf_input, (str, pathlib.Path)):
        reader = pypdf.PdfReader(str(pdf_input))
    elif isinstance(pdf_input, bytes):
        reader = pypdf.PdfReader(io.BytesIO(pdf_input))
    else:
        raise ValueError("pdf_input must be a path or bytes")

    images = []
    for page in reader.pages:
        for img_obj in page.images:
            try:
                # pypdf exposes .image as a PIL Image object
                if hasattr(img_obj, "image") and img_obj.image is not None:
                    images.append(img_obj.image.convert("RGB"))
                elif hasattr(img_obj, "data") and img_obj.data:
                    im = Image.open(io.BytesIO(img_obj.data)).convert("RGB")
                    images.append(im)
            except Exception as exc:
                print(f"Warning: could not decode image {getattr(img_obj, 'name', '?')}: {exc}", file=sys.stderr)
    return images


def slice_image(img: Image.Image, out_dir: pathlib.Path, slice_height: int = SLICE_HEIGHT) -> list[dict[str, Any]]:
    """Cut tall image into slices of ~slice_height px height and save as JPEGs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = img.size
    slices = []
    idx = 0
    for y in range(0, h, slice_height):
        y_end = min(y + slice_height, h)
        box = (0, y, w, y_end)
        cropped = img.crop(box)
        slice_filename = f"slice_{idx:03d}.jpg"
        slice_path = out_dir / slice_filename
        cropped.save(slice_path, "JPEG", quality=85)
        slices.append({
            "index": idx,
            "file": slice_filename,
            "y_start": y,
            "y_end": y_end,
            "width": w,
            "height": y_end - y,
        })
        idx += 1
    return slices


class KindUnknown(ValueError):
    """The report's header did not say which analyses ran, and nobody said: ask the student."""


# The header of a JLCDFM report (the first slice) ends in a row "Analyze project:" with one check box per analysis, in
# this order: PCB DFM, SMT DFM. A ticked box holds a dark check mark. Checked on a real report (both ticked, 2400 px
# wide); a bare-board-only or assembly-only report is read from the same glyph and not yet seen on a real report.
_BOX_RUN = re.compile(rb"(?<!\xff)\xff{24,44}(?!\xff)")      # a box is one 24..44 px run of non-white pixels
_KIND_OF_TICKS = {(True, True): "both", (True, False): "pcb", (False, True): "smt"}


def _check_boxes(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Boxes (x0, x1, y0, y1) in the header band of a report image: runs that keep their place for 20+ rows."""
    w, h = img.size
    x0, x1, y0, y1 = int(w * 0.3), int(w * 0.75), min(600, h), min(1300, h)
    if x1 - x0 < 50 or y1 - y0 < 30:
        return []
    band = img.crop((x0, y0, x1, y1)).convert("L").point(lambda v: 255 if v < 235 else 0)
    data, bw = band.tobytes(), band.size[0]
    active: list[dict] = []
    done: list[dict] = []
    for y in range(band.size[1]):
        row = data[y * bw:(y + 1) * bw]
        carried = []
        for m in _BOX_RUN.finditer(row):
            a, b = m.span()
            run = next((r for r in active if abs(r["x0"] - a) <= 3 and abs(r["x1"] - b) <= 3), None)
            if run:
                active.remove(run)
                run["last"], run["n"] = y, run["n"] + 1
            else:
                run = {"x0": a, "x1": b, "first": y, "last": y, "n": 1}
            carried.append(run)
        done += [r for r in active if r["last"] < y - 1]
        active = carried + [r for r in active if r["last"] >= y - 1]
    return [(r["x0"] + x0, r["x1"] + x0, r["first"] + y0, r["last"] + y0) for r in done + active
            if r["n"] >= 20 and 24 <= r["last"] - r["first"] + 1 <= 44]


def detect_kind(img: Image.Image) -> str | None:
    """'pcb', 'smt' or 'both' from the "Analyze project" check boxes in the report header; None when the header is not
    the one this reads (not exactly two boxes in a row, or neither ticked), so the caller asks the student."""
    boxes = sorted(_check_boxes(img))
    if len(boxes) != 2 or abs(boxes[0][2] - boxes[1][2]) > 6:
        return None
    gray = img.convert("L")
    ticks = []
    for x0, x1, y0, y1 in boxes:
        dark = sum(gray.crop((x0, y0, x1 + 1, y1 + 1)).histogram()[:90])                   # the check mark is near black
        if 6 < dark < 30:
            return None                                       # neither clearly empty nor clearly ticked
        ticks.append(dark >= 30)
    return _KIND_OF_TICKS.get(tuple(ticks))


def pdf_sha256(pdf_input: str | pathlib.Path | bytes) -> str:
    raw = pdf_input if isinstance(pdf_input, bytes) else pathlib.Path(pdf_input).read_bytes()
    return hashlib.sha256(raw).hexdigest()


def ingest_pdf(pdf_input: str | pathlib.Path | bytes, project: str, name: str | None = None, kind: str = "pcb",
               source: str = "upload") -> dict[str, Any]:
    """
    Ingest a JLCDFM report PDF, extract image, slice it, and write index.json + triage.json.
    kind is 'pcb', 'smt' or 'both' (one JLCDFM report can cover the bare board and the assembly). Defaults to 'pcb'.
    kind 'auto' reads it from the report's header and raises KindUnknown (nothing written) when the header does not say.
    index.json keeps the file's sha256 and where it came from (upload, downloads, cli), so the same file is never added twice.
    """
    kind = (kind or "pcb").lower().strip()
    if kind not in KINDS + ("auto",):
        raise ValueError(f"Invalid report kind: '{kind}'. Expected 'pcb', 'smt', 'both' or 'auto'")

    if name is None:
        if isinstance(pdf_input, (str, pathlib.Path)):
            name = pathlib.Path(pdf_input).name
        else:
            name = "dfm_report.pdf"

    stem = sanitize_stem(name)
    pdir = workspace.project_dir(project)
    checks_dir = pdir / "checks" / stem

    images = extract_embedded_images(pdf_input)
    if not images:
        raise ValueError(f"No embedded images found in PDF '{name}'")

    # In JLCDFM, there is usually one tall image. If multiple, take the tallest/largest.
    tallest = max(images, key=lambda im: im.size[1])

    if kind == "auto":
        kind = detect_kind(tallest)
        if kind is None:
            raise KindUnknown(f"'{name}': the report header does not say whether it covers the bare board, the assembly or both")

    slices = slice_image(tallest, checks_dir, slice_height=SLICE_HEIGHT)

    index_data = {
        "stem": stem,
        "kind": kind,
        "original_name": name,
        "sha256": pdf_sha256(pdf_input),
        "source": source,
        "width": tallest.size[0],
        "height": tallest.size[1],
        "slice_height": SLICE_HEIGHT,
        "slice_count": len(slices),
        "slices": slices,
        "header_info": {
            "status": "unknown_until_read",
            "file_name": "unknown",
            "generation_time": "unknown",
            "layers": "unknown",
            "pcb_size": "unknown",
        },
        "created_at": dt.datetime.now().isoformat(),
    }

    (checks_dir / "index.json").write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    triage_path = checks_dir / "triage.json"
    if not triage_path.exists():
        triage_path.write_text("[]", encoding="utf-8")

    return {
        "stem": stem,
        "kind": kind,
        "dir": str(checks_dir),
        "slices": len(slices),
        "slice_files": [s["file"] for s in slices],
        "index": index_data,
    }


def _indexes(project: str):
    """index.json of every report of the project (a missing or damaged one is skipped)."""
    root = workspace.project_dir(project) / "checks"
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        f = d / "index.json"
        if d.is_dir() and f.is_file():
            try:
                yield json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue


def ingested_hashes(project: str) -> dict[str, str]:
    """sha256 of every report file already added to the project -> its stem. Reports added before the hash was kept are not here."""
    return {i["sha256"]: i.get("stem", "") for i in _indexes(project) if i.get("sha256")}


def last_ingest_at(project: str) -> dt.datetime | None:
    """When the newest report of the project was added (local time), or None."""
    times = []
    for i in _indexes(project):
        try:
            times.append(dt.datetime.fromisoformat(i["created_at"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(times) if times else None


def list_checks(project: str, kind: str | None = None) -> list[dict[str, Any]]:
    """List all check reports for a project. Optionally filter by kind ('pcb' | 'smt'); a 'both' report is in either."""
    pdir = workspace.project_dir(project)
    checks_root = pdir / "checks"
    if not checks_root.is_dir():
        return []

    results = []
    for d in sorted(checks_root.iterdir()):
        if not d.is_dir():
            continue
        idx_file = d / "index.json"
        if idx_file.is_file():
            try:
                idx = json.loads(idx_file.read_text(encoding="utf-8"))
            except Exception:
                idx = {}
            report_kind = idx.get("kind", "pcb")
            if kind and report_kind not in (kind, "both"):
                continue
            triage_file = d / "triage.json"
            triage_rows = []
            if triage_file.is_file():
                try:
                    triage_rows = json.loads(triage_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            results.append({
                "stem": d.name,
                "kind": report_kind,
                "original_name": idx.get("original_name", d.name),
                "slice_count": idx.get("slice_count", len(list(d.glob("slice_*.jpg")))),
                "created_at": idx.get("created_at"),
                "header_info": idx.get("header_info", {}),
                "triage_count": len(triage_rows),
                **triage_summary(triage_rows),
            })
    return results


def verdict_of(row: Any) -> str:
    """The verdict a triage row counts as: anything that is not a known verdict is still to review."""
    v = str(row.get("verdict", "unknown") if isinstance(row, dict) else "unknown").strip().lower()
    return v if v in ALLOWED_VERDICTS else "unknown"


def triage_sig(rows: list[dict[str, Any]]) -> str:
    """A short fingerprint of a triage table. The state carries it, so the UI sees that the agent or a script changed a
    table the UI already loaded, without a reload."""
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def triage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What the DFM header needs from a table without loading it: findings still to review, real issues, the fingerprint."""
    verdicts = [verdict_of(r) for r in rows]
    return {
        "triage_open": verdicts.count("unknown"),
        "triage_real": verdicts.count("real"),
        "triage_sig": triage_sig(rows),
    }


def load_index(project: str, stem: str) -> dict[str, Any]:
    """Load index.json for a check report."""
    idx_file = workspace.project_dir(project) / "checks" / stem / "index.json"
    if not idx_file.is_file():
        raise FileNotFoundError(f"Check report '{stem}' not found in project '{project}'")
    data = json.loads(idx_file.read_text(encoding="utf-8"))
    if "kind" not in data:
        data["kind"] = "pcb"
    return data


def load_triage(project: str, stem: str) -> list[dict[str, Any]]:
    """Load triage.json for a check report."""
    triage_file = workspace.project_dir(project) / "checks" / stem / "triage.json"
    if not triage_file.is_file():
        return []
    return json.loads(triage_file.read_text(encoding="utf-8"))


def validate_triage_row(row: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a triage table row."""
    verdict = str(row.get("verdict", "unknown")).strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "unknown"
    return {
        "section": str(row.get("section", "")),
        "check": str(row.get("check", "")),
        "worst": str(row.get("worst", "")),
        "level": str(row.get("level", "Normal")),
        "danger": int(row.get("danger", 0)),
        "warning": int(row.get("warning", 0)),
        "good": int(row.get("good", 0)),
        "layer": str(row.get("layer", "")),
        "verdict": verdict,
        "fix": str(row.get("fix", "")),
        "evidence": str(row.get("evidence", "")),
    }


def save_triage(project: str, stem: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Save triage rows for a check report."""
    checks_dir = workspace.project_dir(project) / "checks" / stem
    if not checks_dir.is_dir():
        checks_dir.mkdir(parents=True, exist_ok=True)
    norm_rows = [validate_triage_row(r) for r in rows]
    (checks_dir / "triage.json").write_text(json.dumps(norm_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return norm_rows


def merge_triage(project: str, stem: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The agent lists findings it read from the slices. A row is added, or updated when the table already has one with the
    same section, check and layer. A verdict is the student's: a new row starts 'unknown', an existing row keeps its own,
    and a fix or evidence the student already wrote is not replaced."""
    load_index(project, stem)                                       # the report must exist
    table = load_triage(project, stem)
    key = lambda r: tuple(str(r.get(k, "")).strip().lower() for k in ("section", "check", "layer"))
    by_key = {key(r): r for r in table}
    added = updated = 0
    for raw in rows:
        if not isinstance(raw, dict) or not str(raw.get("check", "")).strip():
            raise ValueError("every row needs a check name")
        new = validate_triage_row({**raw, "verdict": "unknown"})
        old = by_key.get(key(new))
        if old is None:
            table.append(new)
            by_key[key(new)] = new
            added += 1
            continue
        for f in ("worst", "level", "danger", "warning", "good"):
            if f in raw:
                old[f] = new[f]
        for f in ("fix", "evidence"):
            if not str(old.get(f, "")).strip():
                old[f] = new[f]
        updated += 1
    saved = save_triage(project, stem, table)
    return {"stem": stem, "added": added, "updated": updated, "triage": saved, "sig": triage_sig(saved)}


def get_slice_path(project: str, stem: str, slice_file: str) -> pathlib.Path | None:
    """Safely resolve path to a slice JPEG within the check folder."""
    base = (workspace.project_dir(project) / "checks" / stem).resolve()
    target = (base / slice_file).resolve()
    if base in target.parents and target.is_file():
        return target
    return None


def main(argv=None):
    oscompat.utf8_stdio()
    ap = argparse.ArgumentParser(description="JLCDFM report ingest and triage")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ingest_p = sub.add_parser("ingest")
    ingest_p.add_argument("project", help="Project name")
    ingest_p.add_argument("pdf", help="Path to JLCDFM PDF report")
    ingest_p.add_argument("--kind", choices=list(KINDS) + ["auto"], default="pcb",
                          help="Report kind: 'pcb' (bare board), 'smt' (assembly), 'both', or 'auto' (read from the "
                               "report header), default 'pcb'")

    list_p = sub.add_parser("list")
    list_p.add_argument("project", help="Project name")
    list_p.add_argument("--kind", choices=["pcb", "smt"], default=None,
                        help="Filter by report kind ('pcb' or 'smt')")

    triage_p = sub.add_parser("triage")
    triage_p.add_argument("project", help="Project name")
    triage_p.add_argument("stem", help="Check report stem")

    zip_p = sub.add_parser("gerber-zip", help="build the Gerber + drill zip JLC wants, from the linked Altium outputs")
    zip_p.add_argument("project", help="Project name")

    pick_p = sub.add_parser("pickup", help="add the new JLCDFM report PDFs found in the Downloads folder")
    pick_p.add_argument("project", help="Project name")
    pick_p.add_argument("--kind", choices=list(KINDS), default=None, help="what a report covers, when its header does not say")
    pick_p.add_argument("--name", default=None, help="only this file of the Downloads folder")

    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        try:
            res = ingest_pdf(args.pdf, args.project, kind=args.kind, source="cli")
        except KindUnknown as exc:
            raise SystemExit(f"{exc}. Run again with --kind pcb, smt or both.")
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "gerber-zip":
        import jlc_upload
        print(json.dumps(jlc_upload.gerber_zip(args.project), ensure_ascii=False, indent=2))
    elif args.cmd == "pickup":
        import jlc_upload
        print(json.dumps(jlc_upload.pickup(args.project, kind=args.kind, name=args.name), ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        res = list_checks(args.project, kind=args.kind)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "triage":
        res = load_triage(args.project, args.stem)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
