"""
Integration tests for checks, dfm, outjob, and anchored discussion endpoints.
"""
import base64
import io
import json
import pathlib
import threading
import urllib.error
import urllib.request

from PIL import Image
import pytest

import serve


@pytest.fixture
def server(home, monkeypatch):
    from http.server import ThreadingHTTPServer

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}{chr(38) if chr(63) in path else chr(63)}project={project}",
        method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path, project, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={project}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _synthetic_pdf_b64():
    img = Image.new("RGB", (800, 3200), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_checks_dfm_api(server, lte):
    b64 = _synthetic_pdf_b64()
    status, res = post(server, "/api/checks/upload", {"name": "dfm_report.pdf", "data_b64": b64}, lte)
    assert status == 200
    stem = res["stem"]
    slices = res["slice_files"]
    assert len(slices) >= 2

    # list checks
    status, res = get(server, "/api/checks", lte)
    assert status == 200
    assert any(c["stem"] == stem for c in res["checks"])

    # fetch slice
    status, data = get(server, f"/api/checks/slice?stem={stem}&slice={slices[0]}", lte, raw=True)
    assert status == 200
    assert data.startswith(b"\xff\xd8")  # JPEG header

    # fetch index
    status, idx = get(server, f"/api/checks/index?stem={stem}", lte)
    assert status == 200
    assert idx["stem"] == stem
    assert idx["slice_count"] == len(slices)

    # triage get/post
    status, trg = get(server, f"/api/checks/triage?stem={stem}", lte)
    assert status == 200
    assert trg["triage"] == []

    rows = [{
        "section": "PCB DFM",
        "check": "Minimum trace width",
        "worst": "0.12 mm",
        "level": "Warning",
        "danger": 0,
        "warning": 1,
        "good": 10,
        "layer": "TopLayer",
        "verdict": "real",
        "fix": "Increase neck trace width",
        "evidence": "slice_000.jpg",
    }]
    status, save_res = post(server, "/api/checks/triage", {"stem": stem, "rows": rows}, lte)
    assert status == 200
    assert save_res["ok"] is True

    status, trg2 = get(server, f"/api/checks/triage?stem={stem}", lte)
    assert status == 200
    assert len(trg2["triage"]) == 1
    assert trg2["triage"][0]["check"] == "Minimum trace width"
    assert trg2["triage"][0]["verdict"] == "real"


def _row(check, verdict, section="PCB DFM>Silkscreen layer analysis"):
    return {"section": section, "check": check, "worst": "", "level": "Danger", "danger": 1, "warning": 0, "good": 0,
            "layer": "GTO", "verdict": verdict, "fix": "", "evidence": ""}


def test_the_state_and_the_triage_endpoints_carry_what_the_dfm_header_needs(server, lte):
    """The DFM header counts findings still to review and real issues, and sees a table the agent changed, from the
    state alone: triage_open, triage_real and triage_sig, the same sig the triage endpoints return."""
    status, res = post(server, "/api/checks/upload", {"name": "dfm_report.pdf", "data_b64": _synthetic_pdf_b64()}, lte)
    assert status == 200
    stem = res["stem"]

    def report():
        status, st = get(server, "/api/state", lte)
        assert status == 200
        return next(c for c in st["checks"] if c["stem"] == stem)

    empty = report()
    assert (empty["triage_count"], empty["triage_open"], empty["triage_real"]) == (0, 0, 0)
    status, trg = get(server, f"/api/checks/triage?stem={stem}", lte)
    assert status == 200 and trg["sig"] == empty["triage_sig"]

    rows = [_row("Silkscreen to pad", "real"), _row("Silkscreen line width", "unknown"),
            _row("Pad spacing", "by design"), _row("Pin outer edge", "model"), _row("Odd one", "nonsense")]
    status, saved = post(server, "/api/checks/triage", {"stem": stem, "rows": rows}, lte)
    assert status == 200 and saved["ok"] is True and saved["sig"] != empty["triage_sig"]
    now = report()
    # a verdict the server does not know is still to review, and "model" (JLC's model is off) is judged
    assert (now["triage_count"], now["triage_open"], now["triage_real"]) == (5, 2, 1)
    assert now["triage_sig"] == saved["sig"]
    status, trg = get(server, f"/api/checks/triage?stem={stem}", lte)
    assert trg["sig"] == saved["sig"] and len(trg["triage"]) == 5

    # saving the same table again changes nothing; judging one more finding does
    status, again = post(server, "/api/checks/triage", {"stem": stem, "rows": saved["triage"]}, lte)
    assert again["sig"] == saved["sig"]
    saved["triage"][1]["verdict"] = "by design"
    status, judged = post(server, "/api/checks/triage", {"stem": stem, "rows": saved["triage"]}, lte)
    assert judged["sig"] != saved["sig"]
    now = report()
    assert (now["triage_open"], now["triage_real"]) == (1, 1) and now["triage_sig"] == judged["sig"]


def test_outjob_and_cpl_and_exports_api(server, lte):
    # OutJob generation
    status, res = post(server, "/api/outjob/generate", {}, lte)
    assert status == 200
    assert res["path"].endswith(".OutJob")
    assert "copy" in res["instruction"].lower()

    # CPL export
    status, cpl_res = post(server, "/api/cpl/export", {}, lte)
    assert status == 200
    assert cpl_res["count"] > 0

    # exports list
    status, exp = get(server, "/api/exports", lte)
    assert status == 200
    names = [f["name"] for f in exp["exports"]]
    assert any(n.endswith(".OutJob") for n in names)
    assert any("cpl" in n.lower() for n in names)
    # the Outputs view shows when each file was written: the state has only the size, this list has the time
    assert all(len(f["modified"]) == 19 and f["modified"][10] == "T" for f in exp["exports"])
    assert all(f["url"] == f"/api/export/{f['name']}" for f in exp["exports"])

    # the state the Outputs tab renders from carries the same name and a size
    status, st = get(server, "/api/state", lte)
    assert status == 200
    by_name = {f["name"]: f for f in st["exports"]}
    assert set(by_name) == set(names)
    assert all(f["size"] > 0 for f in by_name.values())

    # download export
    outjob_name = next(n for n in names if n.endswith(".OutJob"))
    status, content = get(server, f"/api/export/{outjob_name}", lte, raw=True)
    assert status == 200
    assert b"OutputJobFile" in content


def test_thread_open_anchors(server, lte):
    # DFM anchor
    status, res = post(server, "/api/thread/open", {"anchor": "dfm:report_1:TraceWidth"}, lte)
    assert status == 200
    assert "session" in res

    status, st = get(server, f"/api/state?session={res['session']}", lte)
    assert status == 200
    first_msg = st["chat"][0]["text"]
    assert "TraceWidth" in first_msg

    # Net anchor
    status, res2 = post(server, "/api/thread/open", {"anchor": "net:+3V3"}, lte)
    assert status == 200
    status, st2 = get(server, f"/api/state?session={res2['session']}", lte)
    assert status == 200
    assert "+3V3" in st2["chat"][0]["text"]
