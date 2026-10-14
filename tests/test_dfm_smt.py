"""Tests for JLCDFM SMT (assembly) report support, kind storage/listing, serve endpoint, and UI."""
import base64
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
import pytest
from PIL import Image
from http.server import ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dfm
import serve
import workspace
from ui_source import ui_all


def make_test_pdf(tmp_path, filename="report.pdf"):
    """Create a minimal synthetic PDF report."""
    img = Image.new("RGB", (800, 1500), color=(250, 250, 250))
    pdf_path = tmp_path / filename
    img.save(str(pdf_path), "PDF")
    return pdf_path


@pytest.fixture
def test_server(tmp_path, monkeypatch):
    """Run serve.Handler on an ephemeral port."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post_json(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}{chr(38) if chr(63) in path else chr(63)}project={project}",
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_dfm_kind_stored_and_listed(tmp_path, monkeypatch):
    """Test that kind ('pcb' vs 'smt') is stored in index.json and returned by list_checks."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"

    pdf_pcb = make_test_pdf(tmp_path, "pcb_report.pdf")
    pdf_smt = make_test_pdf(tmp_path, "smt_report.pdf")

    # Ingest PCB (default)
    res_pcb = dfm.ingest_pdf(pdf_pcb, proj)
    assert res_pcb["kind"] == "pcb"
    idx_pcb = dfm.load_index(proj, res_pcb["stem"])
    assert idx_pcb["kind"] == "pcb"

    # Ingest SMT explicitly
    res_smt = dfm.ingest_pdf(pdf_smt, proj, kind="smt")
    assert res_smt["kind"] == "smt"
    idx_smt = dfm.load_index(proj, res_smt["stem"])
    assert idx_smt["kind"] == "smt"

    # List all checks
    all_checks = dfm.list_checks(proj)
    assert len(all_checks) == 2
    by_stem = {c["stem"]: c["kind"] for c in all_checks}
    assert by_stem[res_pcb["stem"]] == "pcb"
    assert by_stem[res_smt["stem"]] == "smt"

    # Filtered listing
    pcb_only = dfm.list_checks(proj, kind="pcb")
    assert len(pcb_only) == 1 and pcb_only[0]["stem"] == res_pcb["stem"]

    smt_only = dfm.list_checks(proj, kind="smt")
    assert len(smt_only) == 1 and smt_only[0]["stem"] == res_smt["stem"]


def test_dfm_legacy_report_without_kind(tmp_path, monkeypatch):
    """Old reports without kind in index.json must read as 'pcb'."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"
    pdir = workspace.project_dir(proj)
    checks_dir = pdir / "checks" / "legacy_report"
    checks_dir.mkdir(parents=True, exist_ok=True)

    legacy_index = {
        "stem": "legacy_report",
        "original_name": "legacy_report.pdf",
        "width": 1000,
        "height": 2000,
        "slice_count": 2,
    }
    (checks_dir / "index.json").write_text(json.dumps(legacy_index), encoding="utf-8")

    loaded = dfm.load_index(proj, "legacy_report")
    assert loaded["kind"] == "pcb"

    checks = dfm.list_checks(proj)
    assert len(checks) == 1
    assert checks[0]["stem"] == "legacy_report"
    assert checks[0]["kind"] == "pcb"


def test_dfm_cli_kind(tmp_path, monkeypatch, capsys):
    """Test CLI --kind option for ingest and list."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"
    pdf = make_test_pdf(tmp_path, "cli_smt.pdf")

    dfm.main(["ingest", proj, str(pdf), "--kind", "smt"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["kind"] == "smt"

    # Invalid kind in ingest_pdf
    with pytest.raises(ValueError):
        dfm.ingest_pdf(pdf, proj, kind="invalid_kind")


def test_a_report_of_both_kinds_lists_under_pcb_and_smt(tmp_path, monkeypatch):
    """JLCDFM's PCB+SMT report (a real one, 2026-10-12) holds both analyses in one PDF."""
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"
    dfm.ingest_pdf(make_test_pdf(tmp_path, "both.pdf"), proj, kind="both")
    dfm.ingest_pdf(make_test_pdf(tmp_path, "bare.pdf"), proj, kind="pcb")
    assert sorted(c["stem"] for c in dfm.list_checks(proj, kind="pcb")) == ["bare", "both"]
    assert [c["stem"] for c in dfm.list_checks(proj, kind="smt")] == ["both"]
    assert dfm.list_checks(proj, kind="smt")[0]["kind"] == "both"


def test_serve_upload_validates_kind(test_server, tmp_path):
    """Upload endpoint validates kind: accepts pcb/smt, rejects invalid with 400."""
    proj = "demo"
    pdf_path = make_test_pdf(tmp_path, "upload_test.pdf")
    b64 = base64.b64encode(pdf_path.read_bytes()).decode("ascii")

    # Bad kind -> 400
    code, res = post_json(test_server, "/api/checks/upload", {"name": "report.pdf", "data_b64": b64, "kind": "unsupported"}, proj)
    assert code == 400
    assert "invalid kind" in res.get("error", "").lower()

    # Good kind smt -> 200
    code, res = post_json(test_server, "/api/checks/upload", {"name": "report_smt.pdf", "data_b64": b64, "kind": "smt"}, proj)
    assert code == 200
    assert res["kind"] == "smt"

    # Default kind (omitted) -> 200 pcb
    code, res = post_json(test_server, "/api/checks/upload", {"name": "report_pcb.pdf", "data_b64": b64}, proj)
    assert code == 200
    assert res["kind"] == "pcb"


def test_ui_has_both_cards_and_status_line():
    """Verify that the UI source includes both PCB and SMT DFM cards and status line."""
    html = ui_all()

    # Two clear cards
    assert "PCB DFM (bare board)" in html
    assert "SMT DFM (assembly)" in html

    # Mentions what they check and source from dfm.jlcdfm.com
    assert "dfm.jlcdfm.com" in html
    assert "trace/space, annular ring, drill, solder mask, silkscreen" in html
    assert "pad/footprint vs part, component spacing, polarity/pin 1" in html

    # Status line indicating which report is missing before ordering assembly
    assert "Missing both PCB DFM (bare board) and SMT DFM (assembly) reports before ordering assembly." in html
    assert "Missing SMT DFM (assembly) report before ordering assembly." in html
    assert "Missing PCB DFM (bare board) report before ordering assembly." in html
    assert "before ordering assembly" in html

    # Grid / wrap layout
    assert "dfm-cards-grid" in html

    # Single upload button per card (no top-level duplicate upload button in header)
    assert 'data-act="upload-dfm" data-kind=' in html
    # The old standalone top button 'Upload JLCDFM report' should not be present in vhead
    assert '<button class="btn pri" data-act="upload-dfm">Upload JLCDFM report</button>' not in html
