"""
The JLC check done together with the student: the Gerber zip, finding the exported report, the guide in the DFM view.

Offline only. The Altium outputs are a synthetic board (scripts/jlc_testboard.py) copied into a temp folder shaped like
Altium's OutJob output; the Downloads folder is a temp folder with report PDFs drawn with PIL. Nothing logs in to JLC
and no test reads a real Downloads folder.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import threading
import urllib.error
import urllib.request
import zipfile

import pytest
from PIL import Image, ImageDraw

import dfm
import jlc_testboard
import jlc_upload
import project as project_mod
import serve
import workspace

REPO = pathlib.Path(__file__).resolve().parent.parent
VIEWS = REPO / "ui" / "js" / "views"
CHECKS = (VIEWS / "checks.js").read_text(encoding="utf-8")
OUTPUTS = (VIEWS / "outputs.js").read_text(encoding="utf-8")
CHECKS_CSS = (REPO / "ui" / "styles" / "checks.css").read_text(encoding="utf-8")
REPORT = "DFM analysis report_JLCDFM_empty_gerbers.pdf"


# ---------------------------------------------------------------- fixtures

def _altium(tmp_path, project, nested=True):
    """A linked Altium project whose OutJob output (Gerber and NC drill in sibling folders) is a synthetic board."""
    alt = tmp_path / "altium"
    out = alt / "Outputs"
    src = tmp_path / "tb"
    jlc_testboard.generate(src, formats=("outjob",))
    gdir, ddir = (out / "Production" / "Gerber", out / "Production" / "NC Drill") if nested else (out, out)
    gdir.mkdir(parents=True), ddir.mkdir(parents=True, exist_ok=True)
    for f in (src / "outjob").iterdir():
        shutil.copy(f, (ddir if "Plated" in f.name else gdir) / f.name)
    meta = project_mod.load_meta(project)
    meta["altium"] = {"project_file": str(alt / "x.PrjPcb"), "pcb_file": "", "outputs_dir": str(out)}
    project_mod.save_meta(project, meta)
    return out


@pytest.fixture
def linked(empty, tmp_path):
    return empty, _altium(tmp_path, empty)


def _tree(root):
    return sorted((str(p.relative_to(root)), p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*") if p.is_file())


def _pdf(path, ticks=(True, True)):
    """A report PDF: one tall image like JLCDFM's, with the 'Analyze project' check boxes drawn where the real ones are.
    ticks None draws no boxes at all (a header this code cannot read)."""
    img = Image.new("RGB", (2400, 1400), "white")
    d = ImageDraw.Draw(img)
    for x, on in zip((1093, 1337), ticks or ()):
        d.rectangle((x, 988, x + 26, 1019), fill=(205, 210, 220), outline=(120, 130, 150))
        if on:
            d.rectangle((x + 6, 997, x + 14, 1008), fill=(10, 10, 10))
    img.save(path, "PDF", resolution=100.0)
    return pathlib.Path(path)


@pytest.fixture
def downloads(tmp_path):
    d = tmp_path / "Downloads"
    d.mkdir()
    return d


# ---------------------------------------------------------------- 1. the Gerber zip

def test_extensions_are_classified_the_way_jlcs_altium_guide_lists_them():
    c = jlc_upload.classify
    assert c("a.GTL") == ("copper", "Top copper") and c("a.GBL") == ("copper", "Bottom copper")
    assert c("a.G2") == ("copper", "Inner copper 2") and c("a.GP1")[0] == "plane"
    assert c("a.GM1")[0] == "outline" and c("a.GKO")[0] == "outline" and c("a.GM13")[0] == "outline"
    assert c("a.GTS")[0] == "mask" and c("a.GTO")[0] == "silk" and c("a.GBP")[0] == "paste"
    assert c("a-Plated.TXT")[0] == "drill" and c("notes.md") is None and c("a.csv") is None


def test_the_zip_is_flat_complete_and_the_altium_folder_is_only_read(linked):
    name, out = linked
    before = _tree(out)
    res = jlc_upload.gerber_zip(name)
    assert _tree(out) == before                                    # nothing written, touched or deleted in Altium's folder
    path = workspace.project_dir(name) / "exports" / f"{name}_gerbers.zip"
    assert res["zip"] == path.name and path.is_file() and res["built_now"]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    assert all("/" not in n and "\\" not in n for n in names)      # flat: JLC wants no folder inside the archive
    assert {"TB1.GTL", "TB1.GBL", "TB1.GM1", "TB1.GTS", "TB1.GBS", "TB1-Plated.TXT", "TB1-NonPlated.TXT"} <= set(names)
    assert sorted(f["name"] for f in res["files"]) == sorted(names)
    assert res["complete"] and not [m for m in res["missing"] if m["level"] == "problem"]
    assert res["source"].endswith("Gerber") and res["drill_source"].endswith("NC Drill")     # the drill sits in a sibling folder
    assert res["generated"] and res["built"] and res["assembly"] == {"bom": None, "cpl": None}


def test_the_zip_names_the_bom_and_cpl_exports_that_exist(linked):
    name, _ = linked
    exports = workspace.project_dir(name) / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    (exports / f"{name}_BOM_jlc.csv").write_text("Comment,Designator\n", encoding="utf-8")
    (exports / f"{name}_cpl.csv").write_text("Designator,Mid X\n", encoding="utf-8")
    assert jlc_upload.gerber_zip(name)["assembly"] == {"bom": f"{name}_BOM_jlc.csv", "cpl": f"{name}_cpl.csv"}


def test_a_missing_outline_is_reported_as_a_problem_and_the_zip_is_still_written(linked):
    name, out = linked
    (out / "Production" / "Gerber" / "TB1.GM1").unlink()
    res = jlc_upload.gerber_zip(name)
    assert not res["complete"]
    gap = next(m for m in res["missing"] if m["layer"] == "Board outline")
    assert gap["level"] == "problem" and "cancels" in gap["why"]
    assert (workspace.project_dir(name) / "exports" / res["zip"]).is_file()


def test_an_outline_with_only_a_header_is_a_problem_and_one_with_draws_is_complete(linked):
    name, out = linked
    gm1 = out / "Production" / "Gerber" / "TB1.GM1"
    assert b"D01" in gm1.read_bytes() and jlc_upload.gerber_zip(name)["complete"]
    gm1.write_bytes(b"G04 Layer: Mechanical 1*\r\n%FSLAX45Y45*%\r\n%MOMM*%\r\n%ADD10C,0.1*%\r\nG01*\r\nD10*\r\nM02*\r\n")
    res = jlc_upload.gerber_zip(name)
    gap = next(m for m in res["missing"] if m["layer"] == "Board outline")
    assert not res["complete"] and gap["level"] == "problem" and "Create Primitives From Board Shape" in gap["why"]
    gm1.write_bytes(b"%FSLAX45Y45*%\r\n%ADD10C,0.1*%\r\nD10*\r\nX0Y0D02*\r\nX100000D01*\r\nM02*\r\n")
    assert jlc_upload.gerber_zip(name)["complete"]


def test_missing_drill_and_top_mask_are_problems_a_missing_bottom_silk_is_a_note(linked):
    name, out = linked
    for f in (out / "Production" / "NC Drill").iterdir():
        f.unlink()
    (out / "Production" / "Gerber" / "TB1.GTS").unlink()
    (out / "Production" / "Gerber" / "TB1.GBO").unlink(missing_ok=True)
    res = jlc_upload.gerber_zip(name)
    level = {m["layer"]: m["level"] for m in res["missing"]}
    assert level["NC drill"] == "problem" and level["Top solder mask"] == "problem"
    assert level.get("Bottom silkscreen") == "note"


def test_the_newest_gerber_set_wins_and_only_its_files_go_in(linked):
    name, out = linked
    gdir = out / "Production" / "Gerber"
    for f in list(gdir.iterdir()):                                  # an older export of another name
        old = gdir / f.name.replace("TB1", "OLD")
        shutil.copy(f, old)
        os.utime(old, (1_600_000_000, 1_600_000_000))
    with zipfile.ZipFile(workspace.project_dir(name) / "exports" / jlc_upload.gerber_zip(name)["zip"]) as z:
        assert z.namelist() and all(n.startswith("TB1") for n in z.namelist())


def test_backup_and_history_folders_are_not_read(linked):
    name, out = linked
    hist = out / "History" / "Gerber"
    hist.mkdir(parents=True)
    for f in (out / "Production" / "Gerber").iterdir():
        newer = hist / f.name.replace("TB1", "HIST")
        shutil.copy(f, newer)
        os.utime(newer, None)
    res = jlc_upload.gerber_zip(name)
    assert all(f["name"].startswith("TB1") for f in res["files"])


def test_a_flat_outputs_folder_works_too(empty, tmp_path):
    _altium(tmp_path, empty, nested=False)
    res = jlc_upload.gerber_zip(empty)
    assert res["complete"] and "drill_source" not in res


def test_gerber_x2_and_plane_files_get_a_warning(linked):
    name, out = linked
    gtl = out / "Production" / "Gerber" / "TB1.GTL"
    gtl.write_text("%TF.GenerationSoftware,Altium,Designer*%\n" + gtl.read_text(encoding="ascii"), encoding="ascii")
    (out / "Production" / "Gerber" / "TB1.GP1").write_text("G04 plane*\nM02*\n", encoding="ascii")
    warnings = " ".join(jlc_upload.gerber_zip(name)["warnings"])
    assert "X2" in warnings and "plane" in warnings.lower()


def test_an_old_layer_beside_new_ones_is_flagged(linked):
    name, out = linked
    old = out / "Production" / "Gerber" / "TB1.GTO"
    os.utime(old, (1_600_000_000, 1_600_000_000))
    assert any("TB1.GTO" in w for w in jlc_upload.gerber_zip(name)["warnings"])


def test_nothing_to_read_says_what_to_do(empty, tmp_path):
    with pytest.raises(jlc_upload.UploadError, match="Link the Altium project"):
        jlc_upload.gerber_zip(empty)                                # no link at all
    meta = project_mod.load_meta(empty)
    (tmp_path / "alt" / "Outputs").mkdir(parents=True)
    meta["altium"] = {"project_file": str(tmp_path / "alt" / "x.PrjPcb"), "pcb_file": "", "outputs_dir": str(tmp_path / "alt" / "Outputs")}
    project_mod.save_meta(empty, meta)
    with pytest.raises(jlc_upload.UploadError, match="Generate content"):
        jlc_upload.gerber_zip(empty)                                # a folder with no Gerbers in it


def test_zip_info_is_the_zip_as_it_is_on_disk(linked):
    name, _ = linked
    assert jlc_upload.zip_info(name) == {"exists": False, "zip": f"{name}_gerbers.zip"}
    built = jlc_upload.gerber_zip(name)
    info = jlc_upload.zip_info(name)
    assert info["exists"] and "built_now" not in info and info["files"] == built["files"] and info["missing"] == built["missing"]


# ---------------------------------------------------------------- 2. finding the report

def test_kind_is_read_from_the_header_check_boxes():
    def img(ticks):
        im = Image.new("RGB", (2400, 1400), "white")
        d = ImageDraw.Draw(im)
        for x, on in zip((1093, 1337), ticks):
            d.rectangle((x, 988, x + 26, 1019), fill=(205, 210, 220), outline=(120, 130, 150))
            if on:
                d.rectangle((x + 6, 997, x + 14, 1008), fill=(10, 10, 10))
        return im
    assert dfm.detect_kind(img((True, True))) == "both"
    assert dfm.detect_kind(img((True, False))) == "pcb"
    assert dfm.detect_kind(img((False, True))) == "smt"
    assert dfm.detect_kind(img((False, False))) is None            # neither ticked: not a header this reads
    assert dfm.detect_kind(Image.new("RGB", (2400, 1400), "white")) is None
    assert dfm.detect_kind(Image.new("RGB", (100, 100), "white")) is None


def test_ingest_auto_reads_the_kind_or_raises_before_writing_anything(empty, tmp_path):
    good = _pdf(tmp_path / "a.pdf", (True, False))
    assert dfm.ingest_pdf(good, empty, kind="auto")["kind"] == "pcb"
    bad = _pdf(tmp_path / "b.pdf", None)
    with pytest.raises(dfm.KindUnknown):
        dfm.ingest_pdf(bad, empty, kind="auto")
    assert not (workspace.project_dir(empty) / "checks" / "b").exists()
    idx = dfm.load_index(empty, "a")
    assert idx["sha256"] == hashlib.sha256(good.read_bytes()).hexdigest() and idx["source"] == "upload"


def test_a_new_report_in_downloads_is_added_and_says_where_the_kind_came_from(empty, downloads):
    _pdf(downloads / REPORT, (True, True))
    res = jlc_upload.pickup(empty, downloads=downloads)
    assert res["ok"] and res["folder_exists"] and not res["pending"] and not res["skipped"]
    [f] = res["found"]
    assert f["name"] == REPORT and f["kind"] == "both" and f["kind_from"] == "the report header" and f["slices"] == 1
    assert dfm.load_index(empty, f["stem"])["source"] == "downloads"
    assert [c["stem"] for c in dfm.list_checks(empty)] == [f["stem"]]


def test_only_report_pdfs_are_opened_other_files_are_not_even_read(empty, downloads, monkeypatch):
    _pdf(downloads / REPORT)
    (downloads / "tax-return.pdf").write_bytes(b"%PDF-1.4 private")
    (downloads / "family-photo.jpg").write_bytes(b"\xff\xd8 private")
    opened = []
    real = pathlib.Path.read_bytes
    monkeypatch.setattr(pathlib.Path, "read_bytes", lambda self: (opened.append(self.name), real(self))[1])
    res = jlc_upload.pickup(empty, downloads=downloads)
    assert [f["name"] for f in res["found"]] == [REPORT]
    assert opened == [REPORT]                                       # the other files in Downloads were only listed


def test_a_fake_pdf_is_skipped_with_the_reason(empty, downloads):
    (downloads / "DFM analysis report_JLCDFM_fake.pdf").write_bytes(b"<html>still downloading</html>")
    res = jlc_upload.pickup(empty, downloads=downloads)
    assert not res["found"] and res["skipped"][0]["reason"].startswith("not a PDF")
    assert dfm.list_checks(empty) == []


def test_the_same_file_is_never_added_twice(empty, downloads):
    _pdf(downloads / REPORT)
    first = jlc_upload.pickup(empty, downloads=downloads)
    assert len(first["found"]) == 1
    again = jlc_upload.pickup(empty, name=REPORT, downloads=downloads)        # even when asked for by name
    assert not again["found"] and [x["reason"] for x in again["skipped"]] == ["already added"]
    shutil.copy(downloads / REPORT, downloads / "DFM analysis report_JLCDFM_empty_gerbers (1).pdf")   # the browser's copy
    assert not jlc_upload.pickup(empty, name="DFM analysis report_JLCDFM_empty_gerbers (1).pdf", downloads=downloads)["found"]
    assert len(dfm.list_checks(empty)) == 1


def test_a_file_older_than_the_last_report_or_the_zip_is_not_new(empty, downloads, monkeypatch):
    _pdf(downloads / REPORT)
    monkeypatch.setattr(jlc_upload, "since", lambda project: jlc_upload.dt.datetime.now() + jlc_upload.dt.timedelta(hours=1))
    res = jlc_upload.pickup(empty, downloads=downloads)
    assert res["older"] == 1 and res["older_files"][0]["name"] == REPORT and not res["found"] and not res["skipped"]
    assert dfm.list_checks(empty) == []
    # the student can still take it by name
    assert [f["name"] for f in jlc_upload.pickup(empty, name=REPORT, downloads=downloads)["found"]] == [REPORT]


def test_since_is_the_later_of_the_last_report_and_the_zip(linked, downloads):
    name, _ = linked
    start = jlc_upload.since(name)
    assert jlc_upload.dt.datetime.now() - start > jlc_upload.dt.timedelta(hours=23)      # nothing yet: the last day
    jlc_upload.gerber_zip(name)
    zipped = jlc_upload.since(name)
    assert zipped > start
    _pdf(downloads / REPORT)
    jlc_upload.pickup(name, downloads=downloads)
    assert jlc_upload.since(name) >= zipped                                              # a report added after the zip moves it on


def test_a_report_whose_header_is_unclear_waits_for_an_answer(empty, downloads):
    _pdf(downloads / REPORT, None)
    res = jlc_upload.pickup(empty, downloads=downloads)
    assert not res["found"] and [p["name"] for p in res["pending"]] == [REPORT]
    assert dfm.list_checks(empty) == []                                                  # nothing is guessed or written
    done = jlc_upload.pickup(empty, kind="smt", name=REPORT, downloads=downloads)
    assert done["found"][0]["kind"] == "smt" and done["found"][0]["kind_from"] == "you"


def test_a_name_must_be_a_report_file_name_and_not_a_path(empty, downloads):
    for bad in ("../secrets.pdf", "sub/DFM analysis report_x.pdf", "..\\DFM analysis report_x.pdf", "passwords.txt", "notes.pdf"):
        with pytest.raises(ValueError):
            jlc_upload.pickup(empty, name=bad, downloads=downloads)
    with pytest.raises(ValueError):
        jlc_upload.pickup(empty, kind="everything", downloads=downloads)


def test_a_missing_downloads_folder_is_said_not_raised(empty, tmp_path):
    res = jlc_upload.pickup(empty, downloads=tmp_path / "nowhere")
    assert res["ok"] is False and res["folder_exists"] is False and res["found"] == []


def test_the_downloads_folder_comes_from_the_config_else_the_users_downloads(home, monkeypatch):
    monkeypatch.setattr(workspace, "_shell_downloads", lambda: home / "moved")      # Windows moved or redirected the folder
    assert jlc_upload.downloads_dir() == pathlib.Path.home() / "Downloads"           # a folder that is gone is not used
    (home / "moved").mkdir()
    assert jlc_upload.downloads_dir() == home / "moved"
    monkeypatch.setattr(workspace, "_shell_downloads", lambda: None)
    assert jlc_upload.downloads_dir() == pathlib.Path.home() / "Downloads"
    monkeypatch.setenv("JLC_TEST_DL", str(home / "dl"))
    workspace.set_value("workspace.downloads_dir", "%JLC_TEST_DL%" if os.name == "nt" else "$JLC_TEST_DL")
    assert jlc_upload.downloads_dir() == home / "dl"


# ---------------------------------------------------------------- the findings the agent lists

def test_the_agent_lists_findings_but_the_verdict_stays_the_students(empty, tmp_path):
    stem = dfm.ingest_pdf(_pdf(tmp_path / "r.pdf"), empty, kind="both")["stem"]
    row = {"section": "PCB DFM>Routing", "check": "Trace spacing", "worst": "0.09 mm", "level": "Warning", "danger": 0, "warning": 2,
           "good": 5, "layer": "GTL", "fix": "Widen the gap", "evidence": "slice 2"}
    res = dfm.merge_triage(empty, stem, [row, {"check": "Silk to pad", "verdict": "real"}])
    assert (res["added"], res["updated"]) == (2, 0)
    assert {r["verdict"] for r in res["triage"]} == {"unknown"}                           # a verdict in the row is ignored
    rows = dfm.load_triage(empty, stem)
    rows[0]["verdict"], rows[0]["fix"] = "model", "The student's own fix"
    dfm.save_triage(empty, stem, rows)
    again = dfm.merge_triage(empty, stem, [{**row, "fix": "Agent's fix", "warning": 3}])
    assert (again["added"], again["updated"]) == (0, 1)
    kept = next(r for r in again["triage"] if r["check"] == "Trace spacing")
    assert kept["verdict"] == "model" and kept["fix"] == "The student's own fix" and kept["warning"] == 3
    with pytest.raises(ValueError):
        dfm.merge_triage(empty, stem, [{"section": "x"}])
    with pytest.raises(FileNotFoundError):
        dfm.merge_triage(empty, "no-such-report", [row])


# ---------------------------------------------------------------- the command line (what the agent may run)

def test_the_command_line_runs_both_steps(linked, downloads, capsys):
    name, _ = linked
    dfm.main(["gerber-zip", name])
    assert json.loads(capsys.readouterr().out)["zip"] == f"{name}_gerbers.zip"
    workspace.set_value("workspace.downloads_dir", str(downloads))
    _pdf(downloads / REPORT)
    dfm.main(["pickup", name])
    out = json.loads(capsys.readouterr().out)
    assert out["found"][0]["kind"] == "both"
    with pytest.raises(SystemExit, match="--kind"):
        _pdf(downloads / "DFM analysis report_JLCDFM_other.pdf", None)
        dfm.main(["ingest", name, str(downloads / "DFM analysis report_JLCDFM_other.pdf"), "--kind", "auto"])


# ---------------------------------------------------------------- the server and the agent's actions

@pytest.fixture
def server(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _call(base, path, project, body=None):
    url = f"{base}{path}?project={project}"
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}) \
        if body is not None else urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_endpoints_build_the_zip_and_pick_up_the_report(server, linked, downloads):
    name, _ = linked
    assert _call(server, "/api/jlc/gerber-zip", name) == (200, {"exists": False, "zip": f"{name}_gerbers.zip"})
    code, built = _call(server, "/api/jlc/gerber-zip", name, {})
    assert code == 200 and built["complete"] and len(built["files"]) >= 7
    code, info = _call(server, "/api/jlc/gerber-zip", name)
    assert code == 200 and info["exists"] and info["files"] == built["files"]
    code, st = _call(server, "/api/exports", name)
    assert f"{name}_gerbers.zip" in [f["name"] for f in st["exports"]]                      # it shows in Outputs
    workspace.set_value("workspace.downloads_dir", str(downloads))
    _pdf(downloads / REPORT)
    code, res = _call(server, "/api/jlc/pickup", name, {})
    assert code == 200 and res["found"][0]["kind"] == "both"
    code, state = _call(server, "/api/state", name)
    assert [c["stem"] for c in state["checks"]] == [res["found"][0]["stem"]]                # and in the DFM view's state
    code, res = _call(server, "/api/jlc/pickup", name, {})
    assert code == 200 and res["found"] == []


def test_endpoints_refuse_what_cannot_be_done(server, empty, downloads):
    code, err = _call(server, "/api/jlc/gerber-zip", empty, {})
    assert code == 400 and "Altium" in err["error"]
    assert _call(server, "/api/jlc/pickup", empty, {"kind": "everything"})[0] == 400
    assert _call(server, "/api/jlc/pickup", empty, {"name": "../x.pdf"})[0] == 400
    workspace.set_value("workspace.downloads_dir", str(downloads))
    code, res = _call(server, "/api/jlc/pickup", empty, {"kind": "smt", "name": REPORT})
    assert code == 200 and res["found"] == [] and res["pending"] == []


def test_the_zip_can_be_downloaded(server, linked):
    name, _ = linked
    _call(server, "/api/jlc/gerber-zip", name, {})
    with urllib.request.urlopen(f"{server}/api/export/{name}_gerbers.zip?project={name}", timeout=10) as r:
        assert r.read(2) == b"PK"


def test_the_agent_can_run_both_steps_and_list_findings(linked, downloads):
    name, _ = linked
    workspace.set_value("workspace.downloads_dir", str(downloads))
    applied, _, refused = serve.apply_actions(name, [{"type": "jlc.gerber_zip"}, {"type": "jlc.pickup"}])
    assert applied[0].startswith(f"jlc.gerber_zip:{name}_gerbers.zip (") and "no new JLCDFM report" in refused[0]
    _pdf(downloads / REPORT, None)
    applied, _, refused = serve.apply_actions(name, [{"type": "jlc.pickup"}])
    assert not applied and "say pcb, smt or both" in refused[0]                              # asks, never guesses
    applied, _, refused = serve.apply_actions(name, [{"type": "jlc.pickup", "kind": "both", "name": REPORT}])
    stem = dfm.sanitize_stem(REPORT)
    assert applied == [f"jlc.pickup:{stem} (both)"] and not refused
    applied, _, refused = serve.apply_actions(name, [{"type": "dfm.triage", "stem": stem, "rows": [{"check": "Trace spacing", "warning": 2}]}])
    assert applied == [f"dfm.triage:{stem} (1 added, 0 updated)"] and not refused
    assert dfm.load_triage(name, stem)[0]["verdict"] == "unknown"
    _, _, refused = serve.apply_actions(name, [{"type": "dfm.triage", "stem": "no-such", "rows": [{"check": "x"}]}])
    assert refused and "dfm.triage" in refused[0]


def test_the_agent_is_told_the_actions_and_never_to_log_in():
    agents = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    skill = (REPO / "runtime" / "skills" / "manufacturer-and-dfm" / "SKILL.md").read_text(encoding="utf-8")
    for action in ("jlc.gerber_zip", "jlc.pickup", "dfm.triage"):
        assert f'"type": "{action}"' in agents and action in skill
    assert "dfm.py gerber-zip" in skill and "dfm.py pickup" in skill
    assert "never log in" in skill.lower() and "never ask for a password" in skill.lower()
    assert "jlcdfm.com" in skill and "export the PDF report" in skill


# ---------------------------------------------------------------- the guide in the views (source contracts)

def test_every_act_the_guide_uses_has_a_handler():
    for act in ("dfm-guide", "dfm-zip", "dfm-find", "dfm-kind", "ask-jlc-upload"):
        assert f"act: '{act}'" in CHECKS, act
        assert f"onAct('{act}'" in CHECKS, act
    assert "act: 'gen-gerber-zip'" in OUTPUTS and "onAct('gen-gerber-zip'" in OUTPUTS


def test_the_guide_has_the_four_steps_in_order_and_the_ask():
    guide = CHECKS[CHECKS.index("function dfmGuideHTML("):]
    guide = guide[:guide.index("\n}\n")]
    order = [guide.index(t) for t in ("Get the Gerber zip", "Open jlcdfm.com and sign in", "Upload and run the checks", "Find my report")]
    assert order == sorted(order)
    assert 'href="${DFM_JLC}" target="_blank" rel="noopener"' in guide and "const DFM_JLC = 'https://jlcdfm.com'" in CHECKS
    assert "askAbout({kind: 'dfm', id: 'jlc-upload', label: 'JLC upload', text: 'Walk me through the JLC DFM upload'})" in CHECKS
    assert "never asks for your password" in guide
    # with no report the guide is the view; with reports it comes from the header menu
    assert "dfmGuideHTML(true)" in CHECKS and "How to check at JLC" in CHECKS and "dfmGuide ? dfmGuideHTML(false)" in CHECKS


def test_the_upload_menu_finds_the_report_first_and_one_button_stays_primary():
    menu = CHECKS[CHECKS.index("function dfmUpload("):]
    menu = menu[:menu.index("\n}\n")]
    assert menu.index("act: 'dfm-find'") < menu.index("act: 'upload-dfm'")
    guide = CHECKS[CHECKS.index("function dfmGuideHTML("):]
    guide = guide[:guide.index("\n}\n")]
    assert "kind: 'pri'" not in guide and "kind: 'pri'" not in CHECKS[CHECKS.index("function dfmZipBody("):CHECKS.index("function dfmGuideHTML(")]


def test_the_report_is_looked_for_when_the_window_comes_back_and_a_find_is_a_quiet_toast():
    assert "addEventListener('focus', dfmLookOnFocus)" in CHECKS and "addEventListener('visibilitychange', dfmLookOnFocus)" in CHECKS
    look = CHECKS[CHECKS.index("function dfmLookOnFocus("):]
    look = look[:look.index("\n}\n")]
    assert "dfmVisible()" in look and "document.hidden" in look and "DFM_FOCUS_MS" in look and "dfmFindReports(false)" in look
    find = CHECKS[CHECKS.index("async function dfmFindReports("):]
    find = find[:find.index("\nfunction dfmLookOnFocus")]
    assert "`Found ${found[0].name}, added`" in find and "await refresh(true)" in find
    assert find.count("toast(") >= 5 and "if (manual" in find        # the automatic look says something only when it found one


def test_the_gerber_zip_is_in_the_outputs_export_menu_and_says_what_is_missing():
    items = OUTPUTS[OUTPUTS.index("const outExportItems"):]
    items = items[:items.index("];")]
    assert "label: 'Gerber zip for JLC'" in items and "act: 'gen-gerber-zip'" in items
    handler = OUTPUTS[OUTPUTS.index("onAct('gen-gerber-zip'"):]
    handler = handler[:handler.index("onAct('view-export'")]
    assert "dfmMakeZip()" in handler and "Missing:" in handler and "outWrote(" in handler


def test_the_new_markup_has_no_inline_style_and_no_hex_colour():
    for src in (CHECKS, OUTPUTS):
        assert not re.search(r'style\s*=\s*["\']', src) and "style=" not in src
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", CHECKS_CSS)
    assert "var(--" in CHECKS_CSS[CHECKS_CSS.index(".dfm-steps"):]


def test_the_gerber_zip_warns_when_the_board_does_not_match_the_design(linked, monkeypatch):
    from altium import bridge
    name, _ = linked
    monkeypatch.setattr(bridge, "design_problems", lambda project: ["Design and board disagree on net 'V_LED': R3-2 has no net."])
    res = jlc_upload.gerber_zip(name)
    assert any("does not match the design" in w and "V_LED" in w for w in res["warnings"])
    applied, _, _ = serve.apply_actions(name, [{"type": "jlc.gerber_zip"}])
    assert "WARNING: The board does not match the design" in applied[0]
    monkeypatch.setattr(bridge, "design_problems", lambda project: [])
    assert not [w for w in jlc_upload.gerber_zip(name)["warnings"] if "design" in w]


# ---------------------------------------------------------------- 1b. the files against the PcbDoc (spec A15)

_GM = "%FSLAX24Y24*%\n%MOIN*%\n%ADD10C,0.0039*%\nD10*\nX0Y0D02*\nX{w}Y0D01*\nY{h}D01*\nX0D01*\nY0D01*\nM02*\n"


def _exc(plated, holes):
    """Altium's Excellon: INCH,LZ, 2:4, a tool table T01F00S00C<inch>, hits X..Y.."""
    tools = sorted({d for d in holes})
    body = "".join(f"T{i + 1:02d}\n" + "".join(f"X00{j + 1}000Y003000\n" for j, h in enumerate(holes) if h == d)
                   for i, d in enumerate(tools))
    head = "".join(f"T{i + 1:02d}F00S00C{d / 25.4:.4f}\n" for i, d in enumerate(tools))
    return f"M48\n;FILE_FORMAT=2:4\nINCH,LZ\n;TYPE={'PLATED' if plated else 'NON_PLATED'}\n{head}%\n{body}M30\n"


def _set(tmp_path, *, holes=(0.3, 0.3, 1.1), npth=(2.2,), outline=(29.99994 / 25.4, 19.99996 / 25.4),
         copper=("GTL", "GBL"), name="a"):
    w, h = (int(round(v * 10000)) for v in outline)
    files = {f"{name}.{c}": "%FSLAX24Y24*%\n%MOIN*%\nX10Y10D03*\nM02*\n" for c in copper}
    files[f"{name}.GM1"] = _GM.format(w=w, h=h)
    files[f"{name}-Plated.TXT"] = _exc(True, holes)
    if npth:
        files[f"{name}-NonPlated.TXT"] = _exc(False, npth)
    zp = tmp_path / "z.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return zp


def _check(zp, facts):
    with zipfile.ZipFile(zp) as z:
        entries = [{"name": i.filename, "group": (jlc_upload.classify(i.filename) or ("other",))[0]} for i in z.infolist()]
        return [m["why"] for m in jlc_upload.content_problems(z, entries, facts)]


FACTS = {"plated": [0.3, 0.3, 1.1], "unplated": [2.2], "box": (30.0, 20.0), "copper": 2}


def test_the_content_check_passes_a_set_that_matches_the_board(tmp_path):
    assert _check(_set(tmp_path), FACTS) == []


def test_the_content_check_reads_what_altium_really_wrote():
    ex = jlc_upload.gerber_check.parse_excellon(_exc(True, [0.3, 0.3, 1.1]))
    assert ex["plated"] is True and sorted(ex["holes"]) == pytest.approx([0.3, 0.3, 1.1], abs=0.01)
    assert jlc_upload.gerber_check.parse_excellon("G04 not drill\n") is None


def test_a_missing_hole_is_flagged_with_the_numbers(tmp_path):
    msgs = _check(_set(tmp_path, holes=(0.3, 1.1)), FACTS)
    assert len(msgs) == 1 and "has 2 plated holes, the board has 3" in msgs[0] and "generate outputs again" in msgs[0]


def test_a_wrong_hole_diameter_is_flagged(tmp_path):
    msgs = _check(_set(tmp_path, holes=(0.3, 0.3, 1.0)), FACTS)
    assert len(msgs) == 1 and "hole sizes" in msgs[0] and "1 x 1 mm" in msgs[0] and "1 x 1.1 mm" in msgs[0]


def test_a_missing_non_plated_file_is_flagged(tmp_path):
    msgs = _check(_set(tmp_path, npth=()), FACTS)
    assert len(msgs) == 1 and "0 non-plated holes, the board has 1" in msgs[0]


def test_an_outline_of_another_size_is_flagged(tmp_path):
    msgs = _check(_set(tmp_path, outline=(40 / 25.4, 20 / 25.4)), FACTS)
    assert len(msgs) == 1 and "40.00 x 20.00 mm, the board is 30.00 x 20.00 mm" in msgs[0]


def test_a_missing_or_extra_copper_layer_is_flagged(tmp_path):
    less = _check(_set(tmp_path, copper=("GTL", "GBL")), {**FACTS, "copper": 4})
    more = _check(_set(tmp_path, copper=("GTL", "GBL", "G1")), FACTS)
    assert len(less) == 1 and "2 copper layer file(s)" in less[0] and "4 copper layers" in less[0]
    assert len(more) == 1 and "3 copper layer file(s)" in more[0]
    assert _check(_set(tmp_path, copper=("GTL", "GBL", "G1", "GP2")), {**FACTS, "copper": 4}) == []


def test_an_unreadable_pcbdoc_skips_the_content_check_without_failing(tmp_path):
    bad = tmp_path / "x.PcbDoc"
    bad.write_bytes(b"not an ole file")
    assert jlc_upload.board_facts(bad) is None
    res = jlc_upload._describe(_set(tmp_path), bad)
    assert res["content_check"]["checked"] is False and not any("older than the board" in m["why"] or "copper layers" in m["why"] for m in res["missing"])
    assert jlc_upload._describe(_set(tmp_path))["content_check"]["note"] == "no PcbDoc linked"


def test_the_describe_result_carries_the_content_problems(tmp_path, monkeypatch):
    monkeypatch.setattr(jlc_upload, "_facts_cached", lambda pcb: FACTS)
    res = jlc_upload._describe(_set(tmp_path, holes=(0.3, 1.1)), tmp_path / "b.PcbDoc")
    assert not res["complete"] and res["content_check"]["checked"]
    assert any("drill file has 2" in m["why"] for m in res["missing"])


# ---------------------------------------------------------------- 1c. review fixes of the content check

# Altium's slot file (Blink 555-SlotHoles-Plated.TXT): slots are routes, no G85
_SLOTS = ("M48\n;Layer_Color=9474304\n;FILE_FORMAT=2:4\nINCH,LZ\n;TYPE=PLATED\nT02F00S00C0.0236\n%\nG90\nG05\nT02\n"
          "G00X004252Y000992\nM15\nG01Y001268\nM16\nG00X004252Y002492\nM15\nG01Y002768\nM16\nM17\nM30\n")


def test_slots_written_as_routes_count_one_hole_each():
    ex = jlc_upload.gerber_check.parse_excellon(_SLOTS)
    assert len(ex["holes"]) == 2 and ex["holes"][0] == pytest.approx(0.6, abs=0.01)
    g85 = "M48\nMETRIC\n;TYPE=PLATED\nT1C0.800\n%\nT1\nX1.0Y1.0G85X2.0Y1.0\nX5.0Y5.0\nM30\n"
    assert len(jlc_upload.gerber_check.parse_excellon(g85)["holes"]) == 2


def test_a_board_with_round_holes_and_slots_in_two_files_passes(tmp_path):
    zp = tmp_path / "z.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("a.GTL", "x")
        z.writestr("a.GBL", "x")
        z.writestr("a-Round-Plated.TXT", _exc(True, [0.3, 0.3]))
        z.writestr("a-Slot-Plated.TXT", _SLOTS)
    facts = {"plated": [0.3, 0.3, 0.6, 0.6], "unplated": [], "box": None, "copper": 2}
    assert _check(zp, facts) == []


def test_an_unknown_type_falls_back_to_the_combined_count():
    ex = jlc_upload.gerber_check.parse_excellon("M48\nMETRIC\n;TYPE=MIXED\nT1C0.8\n%\nT1\nX1Y1\nM30\n")
    assert ex["plated"] is None
    assert jlc_upload.gerber_check.drill_problems([ex], {"plated": [0.8], "unplated": []}) == []
    assert jlc_upload.gerber_check.parse_excellon("M48\nMETRIC\n;TYPE=NONPLATED\nT1C0.8\n%\nT1\nX1Y1\n")["plated"] is False


def test_coarse_inch_diameters_get_the_tolerance_of_their_last_digit():
    ex = jlc_upload.gerber_check.parse_excellon("M48\nINCH,LZ\n;TYPE=PLATED\nT1C0.031\n%\nT1\nX1Y1\nM30\n")
    assert ex["holes"][0] == pytest.approx(0.7874, abs=1e-3)
    assert jlc_upload.gerber_check.drill_problems([ex], {"plated": [0.8], "unplated": []}) == []
    assert jlc_upload.gerber_check.drill_problems([ex], {"plated": [0.9], "unplated": []})


def test_tools_defined_in_the_body_and_a_second_header_count():
    text = "M48\nMETRIC\n;TYPE=PLATED\nT1C0.800\n%\nT1\nX1Y1\nT2C1.000\nT2\nX2Y2\nM48\nMETRIC\nT3C0.500\n%\nT3\nX3Y3\nM30\n"
    assert sorted(jlc_upload.gerber_check.parse_excellon(text)["holes"]) == [0.5, 0.8, 1.0]


def test_a_drill_file_over_the_cap_skips_the_whole_drill_comparison(tmp_path, monkeypatch):
    zp = _set(tmp_path, holes=(0.3, 1.1))                          # a wrong count that would be flagged
    assert _check(zp, FACTS)
    monkeypatch.setattr(jlc_upload.gerber_check, "MAX_BYTES", 40)
    assert not [m for m in _check(zp, FACTS) if "drill file" in m or "hole sizes" in m]


def test_a_two_layer_board_without_the_bottom_gerber_is_a_note_not_a_problem(tmp_path):
    zp = _set(tmp_path, copper=("GTL",))
    with zipfile.ZipFile(zp) as z:
        entries = [{"name": i.filename, "group": (jlc_upload.classify(i.filename) or ("other",))[0]} for i in z.infolist()]
        got = jlc_upload.content_problems(z, entries, FACTS)
    assert [m["level"] for m in got] == ["note"] and "plot Bottom Layer" in got[0]["why"]
    res = jlc_upload._describe(zp, tmp_path / "b.PcbDoc")
    assert res["missing"] is not None


def test_the_messages_say_to_save_the_pcbdoc_and_check_the_outline_layer(tmp_path):
    assert "save the PcbDoc in Altium first" in _check(_set(tmp_path, holes=(0.3, 1.1)), FACTS)[0]
    assert "save the PcbDoc in Altium first" in _check(_set(tmp_path, holes=(0.3, 0.3, 1.0)), FACTS)[0]
    out = _check(_set(tmp_path, outline=(40 / 25.4, 20 / 25.4)), FACTS)[0]
    assert "save the PcbDoc in Altium first" in out and "check the outline layer in the Gerber setup" in out
    assert "save the PcbDoc in Altium first" in _check(_set(tmp_path, copper=("GTL", "GBL", "G1")), FACTS)[0]


def test_x_y_lines_inside_a_route_are_not_holes():
    text = "M48\nINCH,LZ\n;TYPE=PLATED\nT02F00S00C0.0236\n%\nT02\nG00X004252Y000992\nM15\nG01Y001268\nX004300Y001300\nM16\nM30\n"
    assert len(jlc_upload.gerber_check.parse_excellon(text)["holes"]) == 1


def test_a_closed_board_edge_route_adds_no_holes():
    rout = "M48\nINCH,LZ\n;TYPE=NON_PLATED\nT01F00S00C0.0394\n%\nT01\nG00X0Y0\nM15\nG01Y7874\nX11811\nY0\nX0\nM16\nM30\n"
    assert jlc_upload.gerber_check.parse_excellon(rout)["holes"] == []
    only_tool = "M48\nMETRIC\nT1C2.0\nT2C0.8\n%\nT1\nG00X1Y1\nM15\nG01X9\nY9\nX1\nY1\nM16\nT2\nX3Y3\nM30\n"
    assert jlc_upload.gerber_check.parse_excellon(only_tool)["holes"] == [0.8]


def test_a_tool_defined_in_the_body_selects_itself():
    ex = jlc_upload.gerber_check.parse_excellon("M48\nMETRIC\n;TYPE=PLATED\n%\nT1C0.800\nX1.0Y1.0\nM30\n")
    assert ex["holes"] == [0.8]


def test_the_tolerance_from_few_decimals_is_capped():
    ex = jlc_upload.gerber_check.parse_excellon("M48\nMETRIC\n;TYPE=PLATED\nT1C1.0\n%\nT1\nX1Y1\nM30\n")
    assert ex["tol"] == pytest.approx(0.0127)
    assert jlc_upload.gerber_check.drill_problems([ex], {"plated": [1.04], "unplated": []})


def test_a_skipped_drill_file_makes_content_check_say_not_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(jlc_upload, "_facts_cached", lambda pcb: FACTS)
    monkeypatch.setattr(jlc_upload.gerber_check, "MAX_BYTES", 40)
    res = jlc_upload._describe(_set(tmp_path), tmp_path / "b.PcbDoc")
    assert res["content_check"]["checked"] is False and "drill files not checked" in res["content_check"]["note"]


def test_side_files_are_never_counted_or_walked(tmp_path):
    (tmp_path / "Gerber").mkdir()
    for n in ("a.GTL", "p-macro.APR_LIB", "Status Report.Txt", "run.log"):
        (tmp_path / "Gerber" / n).write_text("x")
    names = sorted(p.name for p, _ in jlc_upload._walk([tmp_path]))
    assert names == ["a.GTL"]
