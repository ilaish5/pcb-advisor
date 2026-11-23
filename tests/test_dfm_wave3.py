"""Wave 3 stream 4, DFM part: one Downloads resolver (28), suggested verdicts kept (26), reports scoped per project (29),
a read-only GET and a POST re-check (30). Offline; no test reads a real Downloads folder."""
import json
import pathlib
import threading
import urllib.error
import urllib.request

import pytest

import dfm
import jlc_upload
import partlib
import serve
import workspace
from test_jlc_upload import _pdf


# ---------------------------------------------------------------- 28 one Downloads resolver

def test_partlib_and_the_dfm_pickup_use_the_same_downloads_folder(home, monkeypatch):
    moved = home / "redirected" / "Downloads"
    moved.mkdir(parents=True)
    monkeypatch.setattr(workspace, "_shell_downloads", lambda: moved)
    assert jlc_upload.downloads_dir() == workspace.downloads_dir() == moved
    (moved / "vendor.zip").write_bytes(b"PK")
    assert [f.name for f in partlib._recent_downloads()] == ["vendor.zip"]       # the vendor zip is looked for where the DFM report is
    workspace.set_value("workspace.downloads_dir", str(home / "cfg"))
    (home / "cfg").mkdir()
    assert jlc_upload.downloads_dir() == home / "cfg" and partlib._recent_downloads() == []


@pytest.mark.skipif(not hasattr(__import__("os"), "name") or __import__("os").name != "nt", reason="Windows Known Folder API")
def test_the_known_folder_api_answers_on_windows():
    got = workspace.__dict__["_shell_downloads"]()
    assert got is None or isinstance(got, pathlib.Path)           # live value depends on the machine; it must not raise


# ---------------------------------------------------------------- 26 the agent's verdicts are kept as suggestions

def _report(empty, tmp_path):
    p = _pdf(tmp_path / "DFM analysis report_JLCDFM_empty.pdf")
    return dfm.ingest_pdf(p, empty, name=p.name, kind="both")["stem"]


def test_a_verdict_the_agent_judged_is_kept_beside_the_students_unknown(empty, tmp_path):
    stem = _report(empty, tmp_path)
    res = dfm.merge_triage(empty, stem, [{"section": "PCB DFM>Drill", "check": "Annular ring", "verdict": "real", "level": "Danger"},
                                         {"section": "PCB DFM>Drill", "check": "Hole size", "suggested_verdict": "by design"},
                                         {"section": "PCB DFM>Drill", "check": "Other", "verdict": "bogus"}])
    rows = {r["check"]: r for r in res["triage"]}
    assert rows["Annular ring"]["verdict"] == "unknown" and rows["Annular ring"]["suggested_verdict"] == "real"
    assert rows["Hole size"]["suggested_verdict"] == "by design" and rows["Other"]["suggested_verdict"] == ""
    assert dfm.load_triage(empty, stem)[0]["suggested_verdict"] == "real"                 # persisted on disk
    saved = dfm.accept_suggestion(empty, stem, 0)
    assert saved[0]["verdict"] == "real"
    with pytest.raises(ValueError):
        dfm.accept_suggestion(empty, stem, 2)                                              # nothing proposed
    again = dfm.merge_triage(empty, stem, [{"section": "PCB DFM>Drill", "check": "Annular ring", "verdict": "model"}])
    row = next(r for r in again["triage"] if r["check"] == "Annular ring")
    assert row["verdict"] == "real" and row["suggested_verdict"] == "model"               # the student's own verdict is never overwritten


# ---------------------------------------------------------------- 29 reports are scoped per project

def test_a_report_of_a_neighbour_project_is_not_picked_up(empty, tmp_path, home):
    workspace.project_dir("neighbour").mkdir(parents=True, exist_ok=True)
    dl = tmp_path / "dl"
    dl.mkdir()
    _pdf(dl / "DFM analysis report_JLCDFM_neighbour_gerbers.pdf", (True, False))
    res = jlc_upload.pickup(empty, downloads=dl)
    assert res["found"] == [] and "neighbour" in res["skipped"][0]["reason"]
    res = jlc_upload.pickup(empty, name="DFM analysis report_JLCDFM_neighbour_gerbers.pdf", downloads=dl)       # by name: the student's call
    assert len(res["found"]) == 1


def test_a_file_already_added_to_another_project_is_not_added_again(empty, tmp_path, home):
    workspace.project_dir("other").mkdir(parents=True, exist_ok=True)
    dl = tmp_path / "dl"
    dl.mkdir()
    p = _pdf(dl / "DFM analysis report_JLCDFM_x.pdf")
    dfm.ingest_pdf(p, "other", name=p.name, kind="both")
    res = jlc_upload.pickup(empty, downloads=dl)
    assert res["found"] == [] and "other" in res["skipped"][0]["reason"]


# ---------------------------------------------------------------- 27/30 the server

@pytest.fixture
def base(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(serve, "QUIET", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _get(base, path, project):
    with urllib.request.urlopen(f"{base}{path}?project={project}") as r:
        return json.loads(r.read())


def _post(base, path, project, body):
    req = urllib.request.Request(f"{base}{path}?project={project}", method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_downloads_folder_is_known_before_any_look(base, empty, home):
    workspace.set_value("workspace.downloads_dir", str(home / "dl"))
    got = _get(base, "/api/jlc/downloads", empty)
    assert got == {"folder": str(home / "dl"), "folder_exists": False}


def test_get_unverified_writes_nothing_and_the_recheck_is_a_post(base, empty, home, monkeypatch):
    import store
    calls = []
    monkeypatch.setattr(store, "recheck_pins", lambda p: calls.append(p) or {"unverified": [], "checked": [], "message": "ok"})
    got = _get(base, "/api/final/unverified", empty)
    assert calls == [] and got["unverified"] == [] and got["checked"] == []
    code, out = _post(base, "/api/final/unverified", empty, {})
    assert code == 200 and calls == [empty] and out["message"] == "ok"


def test_accepting_a_suggestion_over_http(base, empty, tmp_path):
    stem = _report(empty, tmp_path)
    dfm.merge_triage(empty, stem, [{"section": "PCB DFM>A", "check": "c", "verdict": "model"}])
    code, out = _post(base, "/api/checks/accept-suggestion", empty, {"stem": stem, "idx": 0})
    assert code == 200 and out["triage"][0]["verdict"] == "model"
    assert _post(base, "/api/checks/accept-suggestion", empty, {"stem": stem, "idx": 9})[0] == 400


# ---------------------------------------------------------------- the UI wiring (static: the JS has no browser test here)

def test_the_dfm_view_wires_the_wave3_behaviour():
    js = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    assert "api('/api/final/unverified', {})" in js and "api('/api/final/unverified')" not in js      # 30: the re-check is a POST
    assert "dfmRecheckBusy" in js and "Checking" in js                                                 # 30: progress shown
    assert "/api/jlc/downloads" in js                                                                  # 27: the folder before the first look
    assert "dfm-accept" in js and "suggested_verdict" in js                                            # 26
    assert "dfmAutoList(found)" in js and "send: true" in js                                           # 25: the listing turn starts by itself


def test_the_dfm_view_has_the_order_options_and_the_report():
    js = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    assert "/api/order/options" in js and "data-order-boards" in js and "data-order-assembly" in js
    assert "/api/design-report" in js and "dfm-report" in js
