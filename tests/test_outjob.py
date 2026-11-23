"""Tests for scripts/outjob.py (Altium OutJob generation)."""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import outjob
import workspace


def test_generate_outjob(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "home", lambda: tmp_path / "ws")
    proj = "demo"

    res = outjob.generate_outjob(proj)
    assert res["ok"] is True
    assert res["file"] == "demo.OutJob"
    p = pathlib.Path(res["path"])
    assert p.is_file()

    text = p.read_text(encoding="utf-8")
    assert "[OutputJobFile]" in text
    assert "OutputType1=Schematic Print" in text
    assert "OutputType2=BOM_PartType" in text
    assert "OutputType3=Gerber" in text
    assert "OutputType4=NC Drill" in text
    assert "OutputType5=Pick Place" in text
    assert "demo_Schematics.pdf" in text

    # Verify Mechanical1 is NOT in AddToAllPlots (avoid Incident 11 issue)
    assert "AddToAllPlots.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|" in text
    assert "16908289" not in text.split("AddToAllPlots.Set=")[1].split("|")[0]

    # Verify instruction message
    assert "read-only" in res["instruction"]
    assert "copy" in res["instruction"]


def test_pick_place_csv_loses_mechanical_holes_and_keepouts_but_keeps_real_parts(tmp_path):
    f = tmp_path / "Pick Place for Demo.csv"
    f.write_text('"Designator","Comment","Layer","Footprint","Center-X(mm)"\r\n"R1","10k","TopLayer","0603","1.0"\r\n"H1","","TopLayer","MH_3.2","2.0"\r\n'
                 '"KO1","","TopLayer","KO_a","3.0"\r\n"H2","real header","TopLayer","HDR","4.0"\r\n', encoding="utf-8")
    gone = outjob.strip_mechanical_rows(f, real_refs={"H2"})
    assert gone == ["H1", "KO1"]
    text = f.read_text(encoding="utf-8")
    assert '"R1"' in text and '"H2"' in text and '"H1"' not in text and '"KO1"' not in text and text.startswith('"Designator"')
    assert outjob.strip_mechanical_rows(f, real_refs={"H2"}) == []                      # idempotent
    other = tmp_path / "bom.csv"
    other.write_text('"Designator"\r\n"H1"\r\n', encoding="utf-8")
    assert outjob.strip_mechanical_rows(other) == [] and "H1" in other.read_text(encoding="utf-8")        # not a pick-and-place file
