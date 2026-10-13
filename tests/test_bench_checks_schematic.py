"""Benchmark detectors for incidents 6/7/9 and the shared rules in checks/schematic.py."""
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from bench import detectors, incidents  # noqa: E402
from bench import checks_schematic  # noqa: E402
from checks import schematic as sch  # noqa: E402

MINE = {"vcc_cap_over_max", "fault_output_type_unverified", "f411_swap_vcap_missing"}


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(detectors, "REGISTRY", [
        (n, getattr(checks_schematic, n)) for n in
        ("pin_cap_over_max", "output_type_unverified", "swap_requirements")])


def _all():
    items, problems = incidents.load_all()
    assert not problems
    return items


def test_catches_6_7_9_and_quiet_elsewhere(registry):
    items = _all()
    assert len(items) == 12
    for inc in items:
        res = detectors.run_all(inc["_dir"], inc)
        assert res["errors"] == []
        if inc["id"] in (6, 7, 9):
            assert detectors.caught(res["findings"], inc["expect"]), inc["id"]
            assert all(f["message"] and f["source"] for f in res["findings"])
        else:
            assert res["findings"] == [], inc["id"]


NETS = {"VCC": ["U1-7", "C4-1"], "SIG": ["U1-3", "U2-1"], "PU": ["U1-5", "U2-2", "R9-1"],
        "CAPN": ["U6-30", "C7-1"], "BTN": ["U6-31", "J1-1"], "RN": ["R5-1", "U6-9"]}
PARTS = {"C4": {"value": "1uF"}, "C7": {"value": "4.7 uF"}, "R9": {"value": "10k"}, "R5": {"value": "1.5k"}}


def test_parse_capacitance():
    assert sch.parse_capacitance("1uF") == pytest.approx(1e-6)
    assert sch.parse_capacitance("100nF") == pytest.approx(1e-7)
    assert sch.parse_capacitance("0.22 uF") == pytest.approx(2.2e-7)
    assert sch.parse_capacitance("100uF 25V") == pytest.approx(1e-4)
    assert sch.parse_capacitance("10k") is None


def test_pin_cap_max():
    facts = {"part": "U1 X", "datasheet": "x.pdf", "facts": [
        {"page": 8, "pin": "7 VCC", "text": "Decouple 0.1 uF. Capacitance should be no more than 0.22 uF", "source": "t"}]}
    f = sch.check_pin_capacitance_max(NETS, PARTS, facts)
    assert len(f) == 1 and {"C4", "U1"} <= set(f[0]["refs"]) and "p.8" in f[0]["message"]
    ok = dict(PARTS, C4={"value": "100nF"})
    assert sch.check_pin_capacitance_max(NETS, ok, facts) == []


def test_output_type():
    facts = {"part": "U1 X", "output_type": "not stated in the datasheet",
             "facts": [{"page": 10, "text": "Pin 3 FAULT: fault output"}]}
    f = sch.check_output_type_unverified(NETS, PARTS, facts)
    assert len(f) == 1 and "U1" in f[0]["refs"] and "SIG" in f[0]["refs"]
    assert sch.check_output_type_unverified(NETS, PARTS, dict(facts, output_type="open-drain")) == []
    facts5 = {"part": "U1 X", "output_type": "not stated", "facts": [{"text": "Pin 5 X: output"}]}
    assert sch.check_output_type_unverified(NETS, PARTS, facts5) == []   # pull resistor present


def test_swap_requirements():
    facts = {"facts": [{"text": "pin 30 is VCAP_1"},
                       {"text": "VCAP_1 needs a ceramic capacitor to GND"},
                       {"text": "Has an internal USB D+ pull-up; an external 1.5k pull-up (R5) is not needed"}]}
    swap = "Replace U6 OLD with NEW"
    nets = {k: v for k, v in NETS.items() if k != "CAPN"}
    nets["SIG30"] = ["U6-30", "J1-3", "R5-2"]
    ids = {f["id"] for f in sch.check_swap_requirements(nets, PARTS, facts, swap)}
    assert ids == {"swap_pin_cap_missing", "swap_pullup_redundant"}
    nets2 = {k: v for k, v in NETS.items() if k != "RN"}
    nets2["V"] = ["U6-30", "C7-1"]
    assert sch.check_swap_requirements(nets2, PARTS, facts, swap) == []
    assert sch.check_swap_requirements(nets, PARTS, facts, "no swap here") == []
