"""Tests for scripts/checks/board.py (PcbDoc board layout checks)."""
import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from checks.board import check_board, check_decoupling_caps, check_edge_components

FIXTURES = REPO / "tests" / "fixtures" / "altium"


def test_finished_board_checks():
    """Verify board checks run on finished-board.PcbDoc fixture."""
    res = check_board(FIXTURES / "finished-board.PcbDoc")
    assert res["component_count"] == 56
    assert res["pad_count"] == 272
    assert res["net_count"] == 71

    finding_ids = {f["id"] for f in res["findings"]}
    # Should flag CPL rotation sanity list
    assert "cpl_rotation_sanity" in finding_ids

    # Should flag decap distance for far caps on finished board (e.g. C7 is 70 mm away)
    assert "decap_distance_excessive" in finding_ids
    decap_findings = [f for f in res["findings"] if f["id"] == "decap_distance_excessive"]
    assert any("C7" in f["refs"] for f in decap_findings)

    # Every finding conforms to schema
    for f in res["findings"]:
        assert "id" in f
        assert f["severity"] in ("error", "warning", "info")
        assert isinstance(f["refs"], list)
        assert "message" in f
        assert "evidence" in f


def test_connector_faces_inward_detected():
    """Verify connector opening pointing away from edge is flagged."""
    mock_doc = {
        "file": "mock.PcbDoc",
        "components": [
            {
                "ref": "J1",
                "pattern": "HDR1X2",
                "lib_ref": "Header 2",
                "x_mm": 5.0,  # near left edge (min_x = 0)
                "y_mm": 50.0,
                "rotation": 90.0,  # rotates (0, -1) to (1, 0) which points right/inward!
            },
            {
                "ref": "J2",
                "pattern": "HDR1X2",
                "lib_ref": "Header 2",
                "x_mm": 5.0,  # near left edge
                "y_mm": 20.0,
                "rotation": 270.0,  # rotates (0, -1) to (-1, 0) which points left/outward!
            }
        ],
        "pads": [
            {"ref": "J1", "x_mm": 5.0, "y_mm": 50.0, "net": "5V"},
            {"ref": "J2", "x_mm": 5.0, "y_mm": 20.0, "net": "5V"},
        ],
        "nets": ["5V"]
    }

    res = check_board(mock_doc, outline_mm=[0, 0, 100, 80])
    inward = [f for f in res["findings"] if f["id"] == "connector_faces_inward"]
    assert len(inward) == 1
    assert inward[0]["refs"] == ["J1"]
    assert "inward" in inward[0]["message"]
