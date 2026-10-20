"""
Lineage: every exported file says what it was made from, and whether it still matches.
"""
import os
import pathlib

import export_bom
import lineage
import model
import outjob
import project as project_mod
import store
import workspace

from test_jlc_upload import _altium


def _row(project, name):
    return lineage.by_name(project)[name]


def test_a_fresh_export_is_current_and_names_its_inputs(lte):
    export_bom.export(lte, "jlc")
    name = f"{lte}_BOM_jlc.csv"
    row = _row(lte, name)
    assert row["status"] == "fresh" and row["tool"] == "export_bom" and not row["reasons"]
    rec = lineage.latest(lte)[f"exports/{name}"]
    assert rec["inputs"][0] == {**rec["inputs"][0], "kind": "state", "name": "bom_csv", "args": ["jlc"]}
    assert len(rec["sha256"]) == 64


def test_a_bom_edit_makes_the_csv_stale_and_one_the_csv_does_not_show_does_not(lte):
    export_bom.export(lte, "jlc")
    name = f"{lte}_BOM_jlc.csv"
    line = store.bom_lines(lte)[0]
    store.edit_bom(lte, line["key"], "note", (line.get("note") or "") + " changed")     # not a column of the CSV
    assert _row(lte, name)["status"] == "fresh"
    store.edit_bom(lte, line["key"], "value", (line.get("value") or "") + "X")
    row = _row(lte, name)
    assert row["status"] == "stale" and "the BOM changed since" in row["reasons"]
    export_bom.export(lte, "jlc")                       # made again: current again
    assert _row(lte, name)["status"] == "fresh"


def test_an_output_edited_by_hand_and_one_deleted(lte):
    export_bom.export(lte, "generic")
    path = workspace.project_dir(lte) / "exports" / f"{lte}_BOM_generic.csv"
    path.write_text(path.read_text(encoding="utf-8") + "extra,row\n", encoding="utf-8")
    assert _row(lte, path.name)["status"] == "edited"
    assert [r["name"] for r in lineage.stale(lte)] == [path.name]
    path.unlink()
    rows = {r["output"]: r for r in lineage.status(lte)}
    assert rows[f"exports/{path.name}"]["status"] == "missing"


def test_a_file_put_there_by_hand_is_unknown(empty):
    exp = workspace.project_dir(empty) / "exports"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "mine.csv").write_text("a,b\n", encoding="utf-8")
    assert _row(empty, "mine.csv")["status"] == "unknown"
    assert lineage.stale(empty) == []                   # unknown is not a reason to block an order


def test_the_state_carries_lineage_for_the_outputs_view(lte):
    outjob.generate_outjob(lte)
    ex = {e["name"]: e for e in model.build(lte)["exports"]}
    lin = next(e["lineage"] for n, e in ex.items() if n.endswith(".OutJob"))
    assert lin["status"] == "fresh" and lin["tool"] == "outjob"


def test_a_pcb_saved_after_the_gerbers_is_flagged_when_zipping(empty, tmp_path):
    import jlc_upload
    out = _altium(tmp_path, empty)
    pcb = out.parent / "board.PcbDoc"
    pcb.write_bytes(b"pcb")
    meta = project_mod.load_meta(empty)
    meta["altium"]["pcb_file"] = str(pcb)
    project_mod.save_meta(empty, meta)
    newest = max(f.stat().st_mtime for f in out.rglob("*") if f.is_file())
    os.utime(pcb, (newest + 600, newest + 600))         # saved ten minutes after Altium generated the Gerbers
    res = jlc_upload.gerber_zip(empty)
    assert any("saved after these Gerbers" in w for w in res["warnings"])
    row = _row(empty, f"{empty}_gerbers.zip")
    assert row["status"] == "stale" and "saved after" in row["reasons"][0]


def test_a_gerber_changed_after_zipping_makes_the_zip_stale(empty, tmp_path):
    import jlc_upload
    out = _altium(tmp_path, empty)
    jlc_upload.gerber_zip(empty)
    assert _row(empty, f"{empty}_gerbers.zip")["status"] == "fresh"
    gtl = next(out.rglob("*.GTL"))
    gtl.write_bytes(gtl.read_bytes() + b"\n")
    row = _row(empty, f"{empty}_gerbers.zip")
    assert row["status"] == "stale" and any(gtl.name in r for r in row["reasons"])


def test_a_lineage_failure_never_fails_the_export(lte, monkeypatch, capsys):
    def boom(*a, **k):
        raise PermissionError("held open by another program")
    monkeypatch.setattr(lineage, "state_input", boom)
    res = export_bom.export(lte, "jlc")                  # the CSV is written all the same
    assert (workspace.project_dir(lte) / "exports" / f"{lte}_BOM_jlc.csv").is_file()
    assert "could not record" in capsys.readouterr().err
    assert res is not None


def test_cli_exits_1_when_something_must_be_made_again(lte, capsys):
    export_bom.export(lte, "jlc")
    assert lineage.main([lte]) == 0
    line = store.bom_lines(lte)[0]
    store.edit_bom(lte, line["key"], "value", (line.get("value") or "") + "X")
    assert lineage.main([lte]) == 1
    assert "STALE" in capsys.readouterr().out
