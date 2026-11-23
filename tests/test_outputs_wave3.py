"""Wave 3 stream 4, outputs: every claimed output is checked on the disk (68), N boards / assembly options (69),
the design report, hashes of hand-edited files, the archive and unsaved Altium documents (70). Fakes only: nothing here
needs Altium; see the live checklist in the report of this change."""
import json
import pathlib
import threading
import urllib.request
import zipfile

import pytest

import design_report
import order_options
import outjob
import outputs_check
import serve
import store
from altium import bridge
from test_altium_bridge import _linked_with_rules_board, _unblocked, fake  # noqa: F401  (fixtures)


# ---------------------------------------------------------------- 68 the outputs are checked on the disk

def _files(tmp_path, names, size=5):
    out = []
    for n in names:
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)
        out.append(str(p))
    return out


FULL = ["P_Schematics.pdf", "Gerber/P.GTL", "Gerber/P.GBL", "NC Drill/P-Plated.TXT", "BOM/P_BOM_jlc.csv", "Pick Place/Pick Place for P.txt"]


def test_every_output_the_outjob_makes_is_expected(tmp_path):
    job = tmp_path / "P.OutJob"
    job.write_text(outjob.OUTJOB_TEMPLATE.format(project="P"), encoding="latin-1")
    kinds = [k for k, _ in outputs_check.outjob_kinds(job)]
    assert kinds == ["pdf", "bom", "gerber", "drill", "cpl"]
    assert outputs_check.outjob_kinds(tmp_path / "none.OutJob") == []


def test_a_complete_set_is_ok(tmp_path):
    res = outputs_check.verify("p", _files(tmp_path, FULL), outjob=None, options={})
    assert res["ok"] and res["missing"] == [] and res["warnings"] == []


def test_a_missing_pdf_is_named_even_though_other_files_came_out(tmp_path):
    files = _files(tmp_path, [f for f in FULL if not f.endswith(".pdf")])
    res = outputs_check.verify("p", files, options={})
    assert not res["ok"] and res["missing"] == ["Schematic PDF"]
    assert "Not made" in res["warnings"][0] and "Schematic PDF" in res["message"]


def test_a_file_that_is_empty_or_not_on_the_disk_is_not_an_output(tmp_path):
    files = _files(tmp_path, FULL)
    pathlib.Path(files[0]).write_bytes(b"")                         # the PDF is empty
    files.append(str(tmp_path / "ghost.GTO"))                       # claimed, never written
    res = outputs_check.verify("p", files, options={})
    assert res["empty"] == ["P_Schematics.pdf"] and res["absent"] == ["ghost.GTO"] and "Schematic PDF" in res["missing"]
    assert not res["ok"]


def test_assembly_adds_the_bom_and_the_cpl_to_what_is_expected(tmp_path):
    files = _files(tmp_path, ["P_Schematics.pdf", "Gerber/P.GTL", "NC Drill/P-Plated.TXT", "BOM/b_BOM.csv"])
    assert outputs_check.verify("p", files, options={"assembly": False})["ok"]
    res = outputs_check.verify("p", files, options={"assembly": True})
    assert res["missing"] == ["Pick and place (CPL)"]
    cpl = _files(tmp_path, ["exports/P_cpl.csv"])
    assert outputs_check.verify("p", files, options={"assembly": True}, extra=cpl)["ok"]


def test_run_outjob_reports_a_missing_pdf_instead_of_claiming_it_all(lte, fake):                # noqa: F811
    _linked_with_rules_board(lte, fake)
    fake.only_gerbers = True
    res = bridge.run_outjob(lte)
    chk = res["outputs_check"]
    assert not chk["ok"] and "Schematic PDF" in chk["missing"] and "NC drill files" in chk["missing"]
    assert "Not made" in res["warnings"][0]
    assert "NOT made" in serve.outputs_summary(res) and "Schematic PDF" in serve.outputs_summary(res)
    assert outputs_check.load(lte)["missing"] == chk["missing"]                                # kept for the page and the report


def test_run_outjob_with_everything_made_says_nothing_is_missing(lte, fake, monkeypatch):      # noqa: F811
    monkeypatch.setattr(bridge, "rules_missing", lambda project: [])
    monkeypatch.setattr(bridge, "design_problems", lambda project: [])
    _linked_with_rules_board(lte, fake)
    res = bridge.run_outjob(lte)
    assert res["outputs_check"]["ok"] and not any("Not made" in w for w in res["warnings"])
    assert "NOT made" not in serve.outputs_summary(res)


def test_run_outjob_with_assembly_makes_the_cpl_itself(lte, fake, monkeypatch):                # noqa: F811
    monkeypatch.setattr(bridge, "rules_missing", lambda project: [])
    monkeypatch.setattr(bridge, "design_problems", lambda project: [])
    order_options.set_options(lte, boards=3, assembly=True)
    _linked_with_rules_board(lte, fake)
    res = bridge.run_outjob(lte)
    assert (store.pdir(lte) / "exports" / f"{lte}_cpl.csv").is_file()
    assert "Pick and place (CPL)" in [e["label"] for e in res["outputs_check"]["expected"] if e["found"]]


def test_the_cpl_without_a_placed_board_is_a_stub_and_says_so(lte):
    from skills import export_cpl
    res = export_cpl.export_cpl(lte)
    assert res["stub"] is True and any("every position in the CPL is 0.0000mm" in w for w in res["warnings"])


# ---------------------------------------------------------------- 70 unsaved documents in Altium

def test_unsaved_altium_documents_are_named_before_the_outputs_are_trusted(lte, fake, monkeypatch):    # noqa: F811
    monkeypatch.setattr(bridge, "rules_missing", lambda project: [])
    monkeypatch.setattr(bridge, "design_problems", lambda project: [])
    prj, pcb = _linked_with_rules_board(lte, fake)
    fake.unsaved = (pcb.name,)
    res = bridge.run_outjob(lte)
    assert "Altium has unsaved changes in" in res["warnings"][0] and pcb.name in res["warnings"][0]
    assert res["outputs_check"]["unsaved"] == [pcb.name]
    fake.unsaved = ()
    assert bridge.run_outjob(lte)["outputs_check"]["unsaved"] == []


# ---------------------------------------------------------------- 69 N boards and assembly

def test_the_order_options_default_save_and_refuse_nonsense(empty):
    assert order_options.get(empty) == {"boards": 5, "assembly": False, "set": False}
    assert order_options.set_options(empty, boards="12", assembly=True) == {"boards": 12, "assembly": True, "set": True}
    assert order_options.boards(empty) == 12
    for bad in (0, -3, "ten", 1.5, True, 10 ** 7):
        with pytest.raises(ValueError):
            order_options.set_options(empty, boards=bad)
    assert order_options.boards(empty) == 12                                  # a refused value changes nothing


def test_the_stock_check_uses_the_projects_own_boards(lte):
    import order_check
    base = order_check.order_check(lte)["lines"]
    order_options.set_options(lte, boards=50)
    more = order_check.order_check(lte)["lines"]
    assert base and all(m["need"] == m["qty"] * 50 for m in more) and all(b["need"] == b["qty"] * 5 for b in base)


# ---------------------------------------------------------------- 70 the design report, hashes, archive

def _alt(lte, tmp_path):
    prj = tmp_path / "alt" / "X.PrjPcb"
    prj.parent.mkdir(parents=True)
    prj.write_text("[Design]\n", encoding="latin-1")
    (prj.parent / "X.PcbDoc").write_bytes(b"pcb v1")
    (prj.parent / "X.SchDoc").write_bytes(b"sch v1")
    import project as project_mod
    meta = project_mod.load_meta(lte)
    meta["altium"] = {"project_file": str(prj), "pcb_file": str(prj.parent / "X.PcbDoc"), "outputs_dir": ""}
    project_mod.save_meta(lte, meta)
    return prj


def test_the_report_says_what_was_made_from_what_and_names_a_hand_edit(lte, tmp_path):
    prj = _alt(lte, tmp_path)
    first = design_report.build(lte)
    assert first["changed"] is None and first["files"] == 3
    md = (store.pdir(lte) / "exports" / first["file"]).read_text(encoding="utf-8")
    assert "# Design report" in md and "## Made from these Altium files" in md and "X.PcbDoc" in md and "## Accepted risks" in md
    assert "first report" in md
    (prj.parent / "X.PcbDoc").write_bytes(b"pcb v2 edited by hand in Altium")
    second = design_report.build(lte)
    assert [c["name"] for c in second["changed"]] == ["X.PcbDoc"] and second["changed"][0]["change"] == "edited"
    md2 = (store.pdir(lte) / "exports" / second["file"]).read_text(encoding="utf-8")
    assert "X.PcbDoc edited" in md2
    data = json.loads((store.pdir(lte) / "exports" / second["json"]).read_text(encoding="utf-8"))
    assert len(next(f for f in data["altium_files"] if f["name"] == "X.PcbDoc")["sha256"]) == 64


def test_the_report_without_an_altium_project_still_says_so(empty):
    res = design_report.build(empty)
    md = (store.pdir(empty) / "exports" / res["file"]).read_text(encoding="utf-8")
    assert "no Altium project is linked" in md


def test_the_archive_holds_the_altium_files_the_exports_and_the_report(lte, tmp_path):
    prj = _alt(lte, tmp_path)
    out = prj.parent / "Outputs" / "Gerber"
    out.mkdir(parents=True)
    (out / "X.GTL").write_text("G04*")
    (prj.parent / "Outputs" / ".advisor-backup").mkdir()
    (prj.parent / "Outputs" / ".advisor-backup" / "old.GTL").write_text("old")
    import project as project_mod
    meta = project_mod.load_meta(lte)
    meta["altium"]["outputs_dir"] = str(prj.parent / "Outputs")
    project_mod.save_meta(lte, meta)
    res = design_report.archive(lte)
    with zipfile.ZipFile(res["path"]) as z:
        names = set(z.namelist())
    assert {"altium/X.PrjPcb", "altium/X.PcbDoc", "altium-outputs/Gerber/X.GTL", f"exports/{lte}_design_report.md", "project.json"} <= names
    assert not any("old.GTL" in n for n in names) and res["skipped"] == []


# ---------------------------------------------------------------- the server

@pytest.fixture
def base(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    monkeypatch.setattr(serve, "QUIET", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _req(base, path, project, body=None):
    req = urllib.request.Request(f"{base}{path}?project={project}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_options_and_the_report_are_reachable_over_http(base, empty):
    assert _req(base, "/api/order/options", empty)[1] == {"boards": 5, "assembly": False, "set": False}
    code, out = _req(base, "/api/order/options", empty, {"boards": 8, "assembly": True})
    assert code == 200 and out["boards"] == 8 and out["assembly"] is True
    assert _req(base, "/api/order/options", empty, {"boards": "many"})[0] == 400
    code, out = _req(base, "/api/design-report", empty, {})
    assert code == 200 and out["file"].endswith("_design_report.md")
    code, out = _req(base, "/api/design-report", empty, {"archive": True})
    assert code == 200 and out["archive"].endswith(".zip") and out["files"] >= 1
    assert _req(base, "/api/outputs/check", empty)[1] == {}
