"""Benchmark detectors for incidents 8, 10, 11, 12 plus the product functions behind them."""
import json
import pathlib

import pytest

import outjob
from bench import detectors
from bench import checks_board, checks_idea  # noqa: F401 - registers
from checks import board, idea

FIX = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "bench" / "fixtures"
MODS = ("bench.checks_board", "bench.checks_idea")


@pytest.fixture(autouse=True)
def my_registry(monkeypatch):
    reg = [(c, f) for c, f in detectors.REGISTRY if f.__module__ in MODS]
    assert len({c for c, _ in reg}) == 4
    monkeypatch.setattr(detectors, "REGISTRY", reg)


def test_fixtures_caught_and_quiet_elsewhere():
    n = 0
    for d in sorted(p for p in FIX.iterdir() if p.is_dir()):
        inc = json.loads((d / "incident.json").read_text(encoding="utf-8"))
        res = detectors.run_all(d, inc)
        assert res["errors"] == []
        if inc["id"] in (8, 10, 11, 12):
            assert detectors.caught(res["findings"], inc["expect"]), d.name
            n += 1
        else:
            assert res["findings"] == [], d.name
    assert n == 4


def test_connector_inward_positive_negative():
    spec = {"J1": {"wire_entry_dir_at_rot0": [0.0, -1.0]}}
    row = lambda r: [{"ref": "J1", "x_mm": 7, "y_mm": 40, "rotation": r}]
    bad = board.check_connectors_from_placement(row(90), [0, 0, 100, 80], spec)
    assert bad and bad[0]["refs"] == ["J1"]
    assert board.check_connectors_from_placement(row(270), [0, 0, 100, 80], spec) == []


def test_parse_placement_csv():
    rows = board.parse_placement_csv("Designator,Mid X,Mid Y,Layer,Rotation\nU1,1.5mm,2mm,Top,180\n")
    assert rows == [{"ref": "U1", "x_mm": 1.5, "y_mm": 2.0, "layer": "Top", "rotation": 180.0}]


def test_cpl_model_rotation():
    cpl = [{"ref": "U1", "rotation": 0}, {"ref": "U2", "rotation": 90}]
    f = board.check_cpl_vs_model_rotation(cpl, {"U1": 90, "U2": 0, "U9": 180})
    assert len(f) == 1 and f[0]["refs"] == ["U1"]
    assert board.check_cpl_vs_model_rotation(cpl, {"U1": 360, "U2": 0}) == []


def test_outjob_gerber_config():
    cfg = "X=1|AddToAllPlots.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean,16908290~1|Mirror.Set=a"
    f = outjob.check_gerber_plot_config(cfg, ["a.GTL"])
    assert f and f[0]["refs"] == ["Mechanical2"] and "1 Gerber" in f[0]["message"]
    clean = "X=1|AddToAllPlots.Set=SerializeLayerHash.Version~2,ClassName~TLayerToBoolean|Mirror.Set=a"
    assert outjob.check_gerber_plot_config(clean) == []
    assert outjob.check_gerber_plot_config("no config here") == []


def test_idea_flashing():
    t = "- Must: USB connection for flashing firmware.\n| ref | part |\n|---|---|\n| U6 | STM32F103RET6 |\n"
    f = idea.check_flashing_plan(t)
    assert f and f[0]["refs"] == ["U6"] and "AN2606" in f[0]["message"]
    assert idea.check_flashing_plan(t.replace("F103RET6", "F411CEU6")) == []
    assert idea.check_flashing_plan(t.replace("USB connection for flashing firmware", "an LED")) == []
    assert idea.check_flashing_plan(t.replace("STM32F103RET6", "STM32H743")) == []


def test_table_rows_have_sources():
    for r in idea.load_table():
        assert r["source"] and r["usb_dfu_rom"] in ("yes", "no", "unknown")
