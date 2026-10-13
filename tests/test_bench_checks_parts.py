import json

import pytest

from bench import checks_parts, detectors, incidents

FIX = incidents.FIXTURES


def _dirs():
    return sorted(p for p in FIX.iterdir() if (p / "incident.json").is_file())


@pytest.fixture(autouse=True)
def only_parts(monkeypatch):
    monkeypatch.setattr(detectors, "REGISTRY", list(checks_parts.DETECTORS))


def _run(d):
    inc = json.loads((d / "incident.json").read_text(encoding="utf-8"))
    return inc, detectors.run_all(d, inc)


@pytest.mark.parametrize("d", [p for p in _dirs() if int(p.name[:2]) <= 5], ids=lambda p: p.name)
def test_caught(d):
    inc, res = _run(d)
    assert not res["errors"]
    assert detectors.caught(res["findings"], inc["expect"])
    for f in res["findings"]:
        assert f["message"] and "\n" not in f["message"]


@pytest.mark.parametrize("d", [p for p in _dirs() if int(p.name[:2]) >= 6], ids=lambda p: p.name)
def test_no_false_positives(d):
    _, res = _run(d)
    assert res["errors"] == [] and res["findings"] == []


def test_rules_are_general():
    from jlc import expensive_extended_lines, is_standard_only, stock_shortfall
    from library import footprint_variant_conflict
    assert footprint_variant_conflict("A7670G-LABE", "LGA-124-A7670C-LASS")["footprint_variant"] == "C"
    assert footprint_variant_conflict("A7670G-LABE", "LGA-124-A7670G") is None
    assert footprint_variant_conflict("CL31A226KAHNNNE", "C1206") is None
    assert stock_shortfall(0, 1, 5) == 5 and stock_shortfall(None, 1, 5) == 0
    assert is_standard_only("Standard only") and not is_standard_only(None)
    rows = [{"refs": ["X"], "qty": 1, "unit_price": 20.0, "library_type": "Extended"},
            {"refs": ["Y"], "qty": 1, "unit_price": 20.0, "library_type": "Basic"}]
    assert [r["refs"] for r in expensive_extended_lines(rows)] == [["X"]]
