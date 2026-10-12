"""Tests for scripts/dfm.py (JLCDFM PDF ingest, slice generation, triage table)."""
import io
import json
import pathlib
import sys
import pytest
from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dfm
import workspace


def make_synthetic_pdf(tmp_path, width=2000, height=3500, filename="report.pdf"):
    """Create a synthetic tall PDF containing a single embedded JPEG image."""
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    # Draw some color bands to simulate a tall report
    for y in range(0, height, 500):
        for x in range(0, width, 200):
            box = (x, y, min(x + 100, width), min(y + 200, height))
            sub = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color=((x * 7) % 255, (y * 3) % 255, 128))
            img.paste(sub, box)

    pdf_path = tmp_path / filename
    img.save(str(pdf_path), "PDF")
    return pdf_path, width, height


def test_dfm_ingest_synthetic_pdf(tmp_path, monkeypatch):
    """Test extracting tall image from PDF and cutting into ~1400 px slices."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"
    pdf_path, w, h = make_synthetic_pdf(tmp_path, width=2000, height=3500, filename="DFM analysis report_JLCDFM_test.pdf")

    res = dfm.ingest_pdf(pdf_path, proj)
    assert res["stem"] == "DFM_analysis_report_JLCDFM_test"
    assert res["kind"] == "pcb"
    assert res["slices"] == 3  # 3500 px / 1400 = 3 slices (0..1400, 1400..2800, 2800..3500)

    # Check files on disk
    check_dir = pathlib.Path(res["dir"])
    assert check_dir.is_dir()
    assert (check_dir / "index.json").is_file()
    assert (check_dir / "triage.json").is_file()

    slice_files = sorted(check_dir.glob("slice_*.jpg"))
    assert len(slice_files) == 3

    index_data = dfm.load_index(proj, res["stem"])
    assert index_data["kind"] == "pcb"
    assert index_data["width"] == w
    assert index_data["height"] == h
    assert len(index_data["slices"]) == 3
    assert index_data["slices"][0]["height"] == 1400
    assert index_data["slices"][1]["height"] == 1400
    assert index_data["slices"][2]["height"] == 700

    # Test list_checks
    checks = dfm.list_checks(proj)
    assert len(checks) == 1
    assert checks[0]["stem"] == res["stem"]
    assert checks[0]["kind"] == "pcb"
    assert checks[0]["slice_count"] == 3

    # Test slice serving helper
    slice_0 = dfm.get_slice_path(proj, res["stem"], "slice_000.jpg")
    assert slice_0 is not None and slice_0.is_file()

    # Path traversal attack check
    assert dfm.get_slice_path(proj, res["stem"], "../../../evil.txt") is None


def test_dfm_triage_store(tmp_path, monkeypatch):
    """Test saving and loading triage table rows."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"
    pdf_path, _, _ = make_synthetic_pdf(tmp_path, width=1000, height=1500, filename="report2.pdf")
    res = dfm.ingest_pdf(pdf_path, proj)

    stem = res["stem"]
    rows = [
        {
            "section": "PCB DFM>Routing layer analysis",
            "check": "Trace to board edge",
            "worst": "0.15mm",
            "level": "Danger",
            "danger": 48,
            "warning": 0,
            "good": 0,
            "layer": "Top",
            "verdict": "real",
            "fix": "Pull trace back 0.3mm from edge",
            "evidence": "OutJob plotted Mechanical1 on all copper layers",
        },
        {
            "section": "SMT DFM>Component assembly analysis",
            "check": "Pin outer edge",
            "worst": "0.2mm",
            "level": "Warning",
            "danger": 0,
            "warning": 10,
            "good": 0,
            "layer": "component_+_top",
            "verdict": "model",
            "fix": "Adjust JLC 3D model rotation",
            "evidence": "Footprint pad length matches datasheet",
        },
    ]

    saved = dfm.save_triage(proj, stem, rows)
    assert len(saved) == 2
    assert saved[0]["verdict"] == "real"
    assert saved[1]["verdict"] == "model"

    loaded = dfm.load_triage(proj, stem)
    assert len(loaded) == 2
    assert loaded[0]["check"] == "Trace to board edge"
    assert loaded[0]["danger"] == 48
