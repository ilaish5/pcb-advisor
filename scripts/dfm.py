"""
Ingest and triage JLCDFM report PDFs.

A JLCDFM report PDF (dfm.jlcdfm.com) is typically one tall page containing a single
embedded JPEG (~2400 x 15000 px) with no text layer.

This script extracts the embedded image using pypdf, slices it into ~1400 px height
slices stored in projects/<p>/checks/<report-stem>/, and writes index.json.
Triage findings are stored in projects/<p>/checks/<report-stem>/triage.json.

CLI:
    python scripts/dfm.py ingest <project> <pdf_path>
    python scripts/dfm.py list <project>
    python scripts/dfm.py triage <project> <stem>
"""
import argparse
import datetime as dt
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


def ingest_pdf(pdf_input: str | pathlib.Path | bytes, project: str, name: str | None = None) -> dict[str, Any]:
    """
    Ingest a JLCDFM report PDF, extract image, slice it, and write index.json + triage.json.
    """
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

    slices = slice_image(tallest, checks_dir, slice_height=SLICE_HEIGHT)

    index_data = {
        "stem": stem,
        "original_name": name,
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
        "dir": str(checks_dir),
        "slices": len(slices),
        "slice_files": [s["file"] for s in slices],
        "index": index_data,
    }


def list_checks(project: str) -> list[dict[str, Any]]:
    """List all check reports for a project."""
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
            triage_file = d / "triage.json"
            triage_rows = []
            if triage_file.is_file():
                try:
                    triage_rows = json.loads(triage_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            results.append({
                "stem": d.name,
                "original_name": idx.get("original_name", d.name),
                "slice_count": idx.get("slice_count", len(list(d.glob("slice_*.jpg")))),
                "created_at": idx.get("created_at"),
                "header_info": idx.get("header_info", {}),
                "triage_count": len(triage_rows),
            })
    return results


def load_index(project: str, stem: str) -> dict[str, Any]:
    """Load index.json for a check report."""
    idx_file = workspace.project_dir(project) / "checks" / stem / "index.json"
    if not idx_file.is_file():
        raise FileNotFoundError(f"Check report '{stem}' not found in project '{project}'")
    return json.loads(idx_file.read_text(encoding="utf-8"))


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

    list_p = sub.add_parser("list")
    list_p.add_argument("project", help="Project name")

    triage_p = sub.add_parser("triage")
    triage_p.add_argument("project", help="Project name")
    triage_p.add_argument("stem", help="Check report stem")

    args = ap.parse_args(argv)

    if args.cmd == "ingest":
        res = ingest_pdf(args.pdf, args.project)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        res = list_checks(args.project)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "triage":
        res = load_triage(args.project, args.stem)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
