"""Tests for scripts/outjob.py (Altium OutJob generation)."""
import pathlib
import sys
import pytest

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
