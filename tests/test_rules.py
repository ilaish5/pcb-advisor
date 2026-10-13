"""Tests for scripts/rules.py: .RUL writer, JLC presets, and PcbDoc diffs."""
import pathlib
import subprocess
import sys
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from altium import read_pcbdoc, read_rul  # noqa: E402
from rules import (  # noqa: E402
    diff_rules,
    format_rul_bytes,
    get_jlc_preset,
    get_preset_rule_records,
    write_rul,
)

FIXTURES = REPO / "tests" / "fixtures" / "altium"


def test_rul_roundtrip(tmp_path):
    """Verify write_rul and format_rul_bytes round-trip with read_rul."""
    original_rules = [
        {"NAME": "Width_Default", "RULEKIND": "Width", "MINLIMIT": "5mil", "PREFEREDWIDTH": "10mil", "MAXLIMIT": "50mil"},
        {"NAME": "Clearance_Power", "RULEKIND": "Clearance", "GAP": "15mil", "GENERICCLEARANCE": "15mil"},
        {"NAME": "Via_Std", "RULEKIND": "RoutingVias", "MINHOLEWIDTH": "12mil", "HOLEWIDTH": "12mil", "MINWIDTH": "24mil", "WIDTH": "24mil"},
    ]

    raw_bytes = format_rul_bytes(original_rules)
    # Must use \xb6\r\n line ends
    assert b"\xb6\r\n" in raw_bytes

    out_file = tmp_path / "roundtrip.RUL"
    write_rul(original_rules, out_file)
    assert out_file.is_file()

    parsed = read_rul(out_file)
    assert len(parsed) == len(original_rules)
    for orig, read in zip(original_rules, parsed):
        for k, v in orig.items():
            assert read.get(k) == v


def test_jlc_preset_contains_seven_categories():
    """Verify JLC preset contains clearance, width, via, annular ring, hole, silk, and mask rules."""
    preset = get_jlc_preset()
    assert preset.get("capabilities_url") == "https://jlcpcb.com/capabilities/pcb-capabilities"
    assert "_comment" in preset or "capabilities_url" in preset

    rules = preset.get("rules", [])
    assert len(rules) >= 7

    kinds = [r.get("kind") for r in rules]
    # 7 required preset categories: clearance, width, via, annular ring, hole, silk, mask
    assert "Clearance" in kinds
    assert "Width" in kinds
    assert "RoutingVias" in kinds
    assert "MinimumAnnularRing" in kinds
    assert "HoleSize" in kinds
    assert "SilkToSolderMaskClearance" in kinds
    assert "SolderMaskExpansion" in kinds

    # Each rule has attributes to build .RUL
    records = get_preset_rule_records()
    assert len(records) >= 7
    for rec in records:
        assert "NAME" in rec
        assert "RULEKIND" in rec


def test_rules_diff_table_structure():
    """Verify diff_rules returns rows with {rule, kind, board value, preset value, status}."""
    doc = read_pcbdoc(FIXTURES / "rules-board.PcbDoc")
    board_rules = doc.get("rules", [])
    diff = diff_rules(board_rules)

    assert len(diff) >= 7
    for row in diff:
        assert "rule" in row
        assert "kind" in row
        assert "board value" in row
        assert "preset value" in row
        assert "status" in row
        assert row["status"] in ("match", "differs", "missing_on_board", "extra_on_board")

    # Check specific expected findings on rules-board
    clearance_row = next(r for r in diff if r["kind"] == "Clearance")
    assert clearance_row["board value"] == "10mil"
    assert clearance_row["preset value"] == "6mil"
    assert clearance_row["status"] == "differs"

    annular_row = next(r for r in diff if r["kind"] == "MinimumAnnularRing")
    assert annular_row["status"] == "missing_on_board"


def test_rules_cli_export(tmp_path):
    """Verify python scripts/rules.py export produces a readable .RUL file."""
    out_rul = tmp_path / "exported.RUL"
    cmd = [sys.executable, str(REPO / "scripts" / "rules.py"), "export", str(out_rul)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert out_rul.is_file()

    read_back = read_rul(out_rul)
    assert len(read_back) >= 7
    assert any(r.get("RULEKIND") == "Clearance" for r in read_back)


def test_rules_cli_diff():
    """Verify python scripts/rules.py diff prints the diff table."""
    cmd = [sys.executable, str(REPO / "scripts" / "rules.py"), "diff", str(FIXTURES / "rules-board.PcbDoc")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Clearance" in proc.stdout
    assert "differs" in proc.stdout


from rules import board_rul_records  # noqa: E402

PRESET_KINDS = ("Clearance", "Width", "RoutingVias", "MinimumAnnularRing", "HoleSize",
                "SilkToSolderMaskClearance", "SolderMaskExpansion")


def test_board_aware_export_roundtrip(tmp_path):
    board_path = FIXTURES / "rules-board.PcbDoc"
    board = read_pcbdoc(board_path)["rules"]
    preset = get_preset_rule_records()
    recs = board_rul_records(board_path, preset)
    board_kinds = {r["RULEKIND"] for r in board}
    scope_all = {r["RULEKIND"] for r in board
                 if r.get("SCOPE1EXPRESSION") == "All" and r.get("SCOPE2EXPRESSION") == "All"}
    added = [p for p in preset if p["RULEKIND"] not in scope_all]
    assert len(recs) == len(board) + len(added)
    out = write_rul(recs, tmp_path / "b.RUL")
    back = read_rul(out)
    assert len(back) == len(recs)
    by_uid = {r["UNIQUEID"]: r for r in back}
    assert len(by_uid) == len(back)
    for b in board:  # names and UNIQUEIDs preserved
        assert by_uid[b["UNIQUEID"]]["NAME"] == b["NAME"]
    clr = by_uid["NCKWLEIT"]
    assert clr["GAP"] == "6mil" and clr["GENERICCLEARANCE"] == "6mil" and clr["PRIORITY"] == "1"
    assert clr["NETSCOPE"] == "DifferentNets"
    ring = next(r for r in back if r["RULEKIND"] == "MinimumAnnularRing")
    assert ring["MINIMUMRING"] == "6mil" and "MINIMUM" not in ring
    assert by_uid["TORKYMCQ"]["HOLEWIDTH"] == "12mil"
    # the IsPad-scoped silk rule is untouched; the preset rule is added at lowest priority
    assert by_uid["FNWDUPRT"]["MINSILKSCREENTOMASKGAP"] == "10mil"
    silk = [r for r in back if r["RULEKIND"] == "SilkToSolderMaskClearance" and r["UNIQUEID"] != "FNWDUPRT"]
    assert len(silk) == 1 and silk[0]["MINSILKSCREENTOMASKGAP"] == "6mil" and silk[0]["PRIORITY"] == "2"


def test_diff_uses_effective_priority():
    board = [
        {"NAME": "Clearance", "RULEKIND": "Clearance", "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All",
         "PRIORITY": "1", "GAP": "10mil"},
        {"NAME": "Clearance_1", "RULEKIND": "Clearance", "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All",
         "PRIORITY": "2", "GAP": "6mil"},
    ]
    row = next(r for r in diff_rules(board) if r["kind"] == "Clearance" and r["status"] != "extra_on_board")
    assert row["status"] == "differs" and row["board value"] == "10mil"
    board[1]["PRIORITY"], board[0]["PRIORITY"] = "1", "2"  # JLC rule raised to the top
    row = next(r for r in diff_rules(board) if r["kind"] == "Clearance" and r["status"] != "extra_on_board")
    assert row["status"] == "match" and row["rule"] == "Clearance_1"


def test_preset_keys_exist_in_altium_records():
    fixture_keys = {}
    for f in FIXTURES.glob("*.PcbDoc"):
        for r in read_pcbdoc(f)["rules"]:
            fixture_keys.setdefault(r["RULEKIND"], set()).update(r)
    for rec in get_preset_rule_records():
        kind = rec["RULEKIND"]
        if kind not in fixture_keys:  # MinimumAnnularRing: key read back from an AD26-saved PcbDoc
            assert kind == "MinimumAnnularRing" and "MINIMUMRING" in rec and "MINIMUM" not in rec
            continue
        for k in rec:
            assert k in fixture_keys[kind], (kind, k)
