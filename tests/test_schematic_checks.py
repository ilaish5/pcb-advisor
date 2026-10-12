"""Tests for scripts/checks/schematic.py (Schematic netlist and review checks)."""
import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from checks.schematic import (
    build_schdoc_sheet_netlist,
    build_multisheet_schdoc_netlist,
    check_schematic,
)
from altium.schdoc import read_schdoc

FIXTURES = REPO / "tests" / "fixtures" / "altium"
PROJECT = FIXTURES / "project"


def test_schdoc_geometry_join_digital_io():
    """Verify geometry join generates nets connecting pins, net labels, power ports, and ports."""
    doc = read_schdoc(PROJECT / "Digital_IO.SchDoc")
    res = build_schdoc_sheet_netlist(doc)

    assert "nets" in res
    assert len(res["nets"]) > 0
    # Net labels on Digital_IO should name nets
    assert any(k in res["nets"] for k in ("IOexpand_CS", "IOexpand_C\\S\\", "SDA1", "SCL1", "3V3", "5V", "GND"))


def test_multisheet_project_checks():
    """Verify checks run across the five project SchDoc sheets."""
    res = check_schematic(PROJECT)
    assert res["net_count"] > 0
    assert res["pin_count"] > 0
    assert isinstance(res["findings"], list)

    finding_ids = {f["id"] for f in res["findings"]}
    # Labels without ports across sheets should be flagged as info
    assert "net_only_by_label_on_one_sheet" in finding_ids

    for f in res["findings"]:
        assert "id" in f
        assert f["severity"] in ("error", "warning", "info")
        assert isinstance(f["refs"], list)
        assert "message" in f
        assert "evidence" in f


def test_schematic_checks_mock_rules():
    """Verify single-pin nets, unconnected IC power pins, and pin-net mismatches are detected."""
    mock_sheet = {
        "file": "TestSheet.SchDoc",
        "components": [
            {
                "ref": "U1",
                "pins": [
                    {"number": "1", "name": "VCC", "x": 100, "y": 100, "length": 10, "orientation": 0},
                    {"number": "2", "name": "GND", "x": 100, "y": 80, "length": 10, "orientation": 0},
                    {"number": "3", "name": "OUT", "x": 100, "y": 60, "length": 10, "orientation": 0},
                    {"number": "4", "name": "VDD", "x": 100, "y": 40, "length": 10, "orientation": 0},  # unconnected
                ]
            },
            {
                "ref": "R1",
                "pins": [
                    {"number": "1", "name": "1", "x": 200, "y": 80, "length": 10, "orientation": 2},
                    {"number": "2", "name": "2", "x": 250, "y": 80, "length": 10, "orientation": 0},
                ]
            }
        ],
        "wires": [
            # Connect U1 pin 2 (GND) to R1 pin 1, labeled "3V3" -> pin net mismatch!
            {"points": [(110, 80), (190, 80)]},
            # Single pin wire on U1 pin 3 (OUT)
            {"points": [(110, 60), (150, 60)]},
        ],
        "net_labels": [
            {"text": "3V3", "x": 150, "y": 80},
            {"text": "SOLO_NET", "x": 130, "y": 60},
        ],
        "power_ports": [],
        "ports": [],
    }

    res = check_schematic(mock_sheet)
    finding_ids = [f["id"] for f in res["findings"]]

    assert "single_pin_net" in finding_ids
    assert "unconnected_ic_power" in finding_ids
    assert "pin_net_mismatch" in finding_ids

    mismatch = next(f for f in res["findings"] if f["id"] == "pin_net_mismatch")
    assert "U1" in mismatch["refs"]
    assert "Ground pin" in mismatch["message"]
