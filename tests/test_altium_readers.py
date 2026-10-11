"""Tests for read-only Altium file readers (SchDoc, PcbDoc, PrjPcb, RUL)."""
import pathlib
import subprocess
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from altium import (  # noqa: E402
    AltiumReadError,
    pad_net_map,
    read_any,
    read_pcbdoc,
    read_prjpcb,
    read_rul,
    read_schdoc,
)

FIXTURES = REPO / "tests" / "fixtures" / "altium"
PROJECT = FIXTURES / "project"


def test_pcbdoc_fixtures_parse():
    """Verify both PcbDoc fixtures parse with expected counts and fields."""
    rb = read_pcbdoc(FIXTURES / "rules-board.PcbDoc")
    assert rb["file"] == "rules-board.PcbDoc"
    assert len(rb["components"]) == 59
    assert len(rb["nets"]) == 76
    assert len(rb["rules"]) == 35
    assert len(rb["pads"]) == 281
    assert all(r.get("RULEKIND") for r in rb["rules"])
    assert all(c["ref"] for c in rb["components"])

    fb = read_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    assert fb["file"] == "finished-board.PcbDoc"
    assert len(fb["components"]) == 56
    assert len(fb["nets"]) == 71
    assert len(fb["rules"]) == 45
    assert len(fb["pads"]) == 272
    assert all(r.get("RULEKIND") for r in fb["rules"])
    assert all(c["ref"] for c in fb["components"])

    # Most pads have a net on finished board
    with_net = [p for p in fb["pads"] if p["net"]]
    assert len(with_net) == 247
    assert len(with_net) > len(fb["pads"]) * 0.9


def test_pcbdoc_pad_net_map():
    """Verify pad_net_map correctly aggregates pads per net."""
    fb = read_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    pnm = pad_net_map(fb)
    assert pnm["RELAY1"] == ["J4-29", "U1-3"]
    assert pnm["RELAY2"] == ["J4-31", "U1-6"]


def test_schdoc_fixtures_parse():
    """Verify all five SchDoc fixtures parse with components, pins, wires, and labels."""
    expected = {
        "CAN_Interface.SchDoc": {"comps": 17, "pins": 59, "wires": 25, "labels": 9, "ports": 6},
        "Digital_IO.SchDoc": {"comps": 12, "pins": 91, "wires": 34, "labels": 30, "ports": 10},
        "Power Supply.SchDoc": {"comps": 15, "pins": 38, "wires": 7, "labels": 0, "ports": 0},
        "Processor_Interface.SchDoc": {"comps": 3, "pins": 44, "wires": 40, "labels": 27, "ports": 13},
        "Relay_IO.SchDoc": {"comps": 13, "pins": 48, "wires": 16, "labels": 3, "ports": 1},
    }

    for name, exp in expected.items():
        doc = read_schdoc(PROJECT / name)
        assert doc["file"] == name
        assert len(doc["components"]) == exp["comps"]
        assert len(doc["wires"]) == exp["wires"]
        assert len(doc["net_labels"]) == exp["labels"]
        assert len(doc["ports"]) == exp["ports"]

        total_pins = sum(len(c["pins"]) for c in doc["components"])
        assert total_pins == exp["pins"]

        # Every component has a ref and at least one pin
        for c in doc["components"]:
            assert c["ref"]
            assert len(c["pins"]) >= 1
            for pin in c["pins"]:
                assert pin["number"]

        # Footprint names are present
        assert any(c["footprint"] for c in doc["components"])

        # Wires have at least 2 points
        for w in doc["wires"]:
            assert len(w["points"]) >= 2


def test_prjpcb_fixture_parse():
    """Verify PrjPcb fixture lists sheets and reports missing documents."""
    prj = read_prjpcb(PROJECT / "WCTopping.PrjPcb")
    assert prj["file"] == "WCTopping.PrjPcb"
    assert prj["name"] == "WCTopping"
    assert len(prj["documents"]) == 5
    assert len(prj["sheets"]) == 5
    assert prj["pcbs"] == []
    assert prj["outjobs"] == []
    assert prj["missing"] == []


def test_rul_roundtrip(tmp_path):
    """Verify .RUL byte parsing and file reading."""
    rule_data = (
        b"|NAME=WidthConstraint_1|RULEKIND=Width|MINLIMIT=10mil|MAXLIMIT=30mil|\xb6\r\n"
        b"|NAME=Clearance_1|RULEKIND=Clearance|GAP=8mil|\xb6\r\n"
    )
    rul_file = tmp_path / "test.RUL"
    rul_file.write_bytes(rule_data)

    rules = read_rul(rul_file)
    assert len(rules) == 2
    assert rules[0]["NAME"] == "WidthConstraint_1"
    assert rules[0]["RULEKIND"] == "Width"
    assert rules[1]["NAME"] == "Clearance_1"
    assert rules[1]["RULEKIND"] == "Clearance"


def test_read_any_dispatcher():
    """Verify read_any dispatches based on file extension case-insensitively."""
    sch = read_any(PROJECT / "Digital_IO.SchDoc")
    assert sch["file"] == "Digital_IO.SchDoc"
    pcb = read_any(FIXTURES / "rules-board.PcbDoc")
    assert pcb["file"] == "rules-board.PcbDoc"
    prj = read_any(PROJECT / "WCTopping.PrjPcb")
    assert prj["name"] == "WCTopping"


def test_errors_raised(tmp_path):
    """Verify AltiumReadError on bad file formats, missing files, and missing streams."""
    # Missing file
    with pytest.raises(AltiumReadError):
        read_pcbdoc(tmp_path / "nonexistent.PcbDoc")

    # Non-OLE file renamed to .PcbDoc
    fake_pcb = tmp_path / "fake.PcbDoc"
    fake_pcb.write_text("not an ole file")
    with pytest.raises(AltiumReadError):
        read_pcbdoc(fake_pcb)

    # OLE file without expected stream (parts.SchLib lacks Pads6/Data)
    schlib = FIXTURES / "parts.SchLib"
    with pytest.raises(AltiumReadError):
        read_pcbdoc(schlib)

    # Unsupported extension via read_any
    bad_ext = tmp_path / "test.unknown"
    bad_ext.write_text("hello")
    with pytest.raises(AltiumReadError):
        read_any(bad_ext)


def test_dump_cli(tmp_path):
    """Verify dump.py CLI exit codes (0 on success, 2 on error)."""
    cmd_ok = [sys.executable, str(REPO / "scripts" / "altium" / "dump.py"), str(FIXTURES / "finished-board.PcbDoc")]
    proc_ok = subprocess.run(cmd_ok, capture_output=True, text=True)
    assert proc_ok.returncode == 0
    assert "finished-board.PcbDoc" in proc_ok.stdout

    cmd_bad = [sys.executable, str(REPO / "scripts" / "altium" / "dump.py"), str(tmp_path / "missing.PcbDoc")]
    proc_bad = subprocess.run(cmd_bad, capture_output=True, text=True)
    assert proc_bad.returncode == 2


def test_dump_cli_net():
    """Verify dump.py --net prints the pads of one net."""
    cmd = [sys.executable, str(REPO / "scripts" / "altium" / "dump.py"),
           str(FIXTURES / "finished-board.PcbDoc"), "--net", "RELAY1"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert '"J4-29", "U1-3"' in proc.stdout
    proc = subprocess.run(cmd[:-1] + ["NO_SUCH_NET"], capture_output=True, text=True)
    assert proc.returncode == 2
