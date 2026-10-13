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


# ---------------------------------------------------------------------------
# verdicts: numeric comparison in mm against the preset and the JLC fab minimum
# ---------------------------------------------------------------------------
import json  # noqa: E402

from rules import (  # noqa: E402
    VERDICTS,
    annular_ring_summary,
    diff_pcbdoc,
    preset_values_mm,
    to_mm,
    values_same,
)


def _board(kind, **attrs):
    return {"NAME": kind, "RULEKIND": kind, "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All",
            "PRIORITY": "1", **attrs}


def _row(board_rules, kind, geom=None, preset=None):
    rows = diff_rules(board_rules, preset, board_geom=geom)
    return next(r for r in rows if r["kind"] == kind and r["status"] != "extra_on_board")


def test_to_mm_parses_units():
    assert to_mm("6mil") == pytest.approx(0.1524)
    assert to_mm("5.9055mil") == pytest.approx(0.15, abs=1e-4)
    assert to_mm("0.15mm") == pytest.approx(0.15)
    assert to_mm(" 0.15 MM ") == pytest.approx(0.15)
    assert to_mm("0.006in") == pytest.approx(0.1524)
    assert to_mm("15um") == pytest.approx(0.015)
    assert to_mm("-23.622mil") == pytest.approx(-0.6, abs=1e-4)
    assert to_mm("6") == pytest.approx(0.1524)      # bare number is mil, as in altium.pcbdoc.mil_to_mm
    assert to_mm(6) == pytest.approx(0.1524)
    for bad in ("", "abc", "6 furlongs", None, "Min: 5mil"):
        assert to_mm(bad) is None


def test_values_same_is_unit_rounding_only():
    assert values_same(0.15, 0.1524)          # 5.9055 mil vs 6 mil
    assert values_same(0.3, 0.3048)           # 11.811 mil vs 12 mil
    assert values_same(6.3, 6.35)             # within 2 %
    assert values_same(0.0500, 0.0508)        # within 0.003 mm
    assert not values_same(0.127, 0.1524)     # 5 mil vs 6 mil is a real difference
    assert not values_same(0.254, 0.1524)


def test_preset_has_numeric_fab_minimums():
    preset = get_jlc_preset()
    by_kind = {r["kind"]: r for r in preset["rules"]}
    assert by_kind["Clearance"]["fab_min_mm"] == 0.09
    assert by_kind["MinimumAnnularRing"]["fab_min_mm"] == 0.15
    assert by_kind["SilkToSolderMaskClearance"]["fab_min_mm"] == 0.15
    for kind in ("Width", "RoutingVias", "HoleSize", "SolderMaskExpansion"):
        assert "fab_min_mm" in by_kind[kind] and by_kind[kind]["fab_min_mm"] is None
    for kind in ("Clearance", "MinimumAnnularRing", "SilkToSolderMaskClearance"):
        assert by_kind[kind]["fab_min_source"] == preset["capabilities_url"]
    # the numeric view of a preset rule agrees with its .RUL attributes
    assert preset_values_mm(by_kind["Width"]) == pytest.approx({"min": 0.127, "pref": 0.2032, "max": 1.016})
    assert preset_values_mm(by_kind["RoutingVias"]) == pytest.approx({"hole": 0.3048, "dia": 0.6096})
    # ... and falls back to the *_mm keys / display string when there are no attributes
    bare = {"kind": "Width", "value": "Min: 5mil, Pref: 8mil, Max: 40mil"}
    assert preset_values_mm(bare) == pytest.approx({"min": 0.127, "pref": 0.2032, "max": 1.016})
    assert preset_values_mm({"kind": "Clearance", "value_mm": 0.1524}) == {"gap": 0.1524}


@pytest.mark.parametrize("gap,verdict", [
    ("5.9055mil", "same"),          # 0.15 mm vs 6 mil: unit rounding
    ("0.15mm", "same"),
    ("10mil", "safer"),
    ("4mil", "tighter_ok"),         # 0.1016 mm: tighter than 0.1524, above the 0.09 fab minimum
    ("0.09mm", "tighter_ok"),
    ("3mil", "below_fab_min"),      # 0.0762 mm < 0.09 mm
])
def test_verdict_clearance(gap, verdict):
    row = _row([_board("Clearance", GAP=gap, GENERICCLEARANCE=gap)], "Clearance")
    assert row["verdict"] == verdict
    assert row["status"] in ("match", "differs")   # the existing status is untouched
    assert row["decided_by"] == ["gap"] or verdict == "same"
    if verdict == "below_fab_min":
        assert "0.09" in row["detail"] and "BELOW" in row["detail"]


def test_verdict_width_min_decides_and_max_is_informational():
    def width(mn, pref, mx):
        return [_board("Width", MINLIMIT=mn, PREFEREDWIDTH=pref, MAXLIMIT=mx)]
    row = _row(width("5.9055mil", "7.874mil", "118.1102mil"), "Width")   # the real board
    assert row["verdict"] == "safer" and row["decided_by"] == ["min"]
    assert {b["name"]: b["verdict"] for b in row["bounds"]} == {"min": "safer", "pref": "same", "max": "unknown"}
    assert "max" in row["detail"] and "[decides]" in row["detail"]
    # a lower maximum is more restrictive; the min bound still decides
    row = _row(width("5mil", "8mil", "20mil"), "Width")
    assert row["verdict"] == "same"
    assert {b["name"]: b["verdict"] for b in row["bounds"]}["max"] == "safer"
    # a min tighter than the preset with no stored fab minimum cannot be called ok
    row = _row(width("4mil", "8mil", "40mil"), "Width")
    assert row["verdict"] == "unknown" and "no fab minimum" in row["detail"]
    # a larger preferred width alone does not change the verdict
    assert _row(width("5mil", "20mil", "40mil"), "Width")["verdict"] == "same"


def test_verdict_routing_vias_hole_and_dia():
    def vias(h, d):
        return [_board("RoutingVias", HOLEWIDTH=h, WIDTH=d)]
    assert _row(vias("11.811mil", "23.622mil"), "RoutingVias")["verdict"] == "same"
    row = _row(vias("16mil", "24mil"), "RoutingVias")
    assert row["verdict"] == "safer" and row["decided_by"] == ["hole"]
    assert _row(vias("28mil", "50mil"), "RoutingVias")["verdict"] == "safer"
    row = _row(vias("12mil", "20mil"), "RoutingVias")      # smaller pad: no fab minimum stored
    assert row["verdict"] == "unknown" and row["decided_by"] == ["dia"]
    # a smaller via is judged worse than a larger one even if the other bound is bigger
    assert _row(vias("10mil", "30mil"), "RoutingVias")["verdict"] == "unknown"


def test_verdict_hole_size_min_and_max_are_separate():
    def hole(mn, mx):
        return [_board("HoleSize", MINLIMIT=mn, MAXLIMIT=mx)]
    assert _row(hole("12mil", "250mil"), "HoleSize")["verdict"] == "same"
    assert _row(hole("12mil", "248.0315mil"), "HoleSize")["verdict"] == "same"
    row = _row(hole("16mil", "100mil"), "HoleSize")
    assert row["verdict"] == "safer" and row["decided_by"] == ["min"]
    # a maximum above the preset loosens the rule but is not a floor: it does not decide
    row = _row(hole("12mil", "400mil"), "HoleSize")
    assert row["verdict"] == "same" and "higher maximum" in row["detail"]
    assert {b["name"]: b["verdict"] for b in row["bounds"]}["max"] == "unknown"
    # a smaller minimum: tighter, no stored fab minimum
    assert _row(hole("7.874mil", "250mil"), "HoleSize")["verdict"] == "unknown"


def test_verdict_silk_and_mask():
    def silk(v):
        return [_board("SilkToSolderMaskClearance", MINSILKSCREENTOMASKGAP=v)]
    assert _row(silk("6mil"), "SilkToSolderMaskClearance")["verdict"] == "same"
    assert _row(silk("10mil"), "SilkToSolderMaskClearance")["verdict"] == "safer"
    row = _row(silk("5mil"), "SilkToSolderMaskClearance")           # 0.127 mm < 0.15 mm
    assert row["verdict"] == "below_fab_min" and "0.15" in row["detail"]
    # mask expansion is a standard value, not a limit: only "same" can be judged
    assert _row([_board("SolderMaskExpansion", EXPANSION="1.9685mil")], "SolderMaskExpansion")["verdict"] == "same"
    row = _row([_board("SolderMaskExpansion", EXPANSION="4mil")], "SolderMaskExpansion")
    assert row["verdict"] == "unknown" and "direction" in row["detail"]


def test_verdict_disabled_missing_and_extra_rows():
    off = _board("Clearance", GAP="10mil", ENABLED="FALSE", NAME="OffRule")
    row = next(r for r in diff_rules([off]) if r["rule"] == "OffRule")
    assert row["verdict"] == "unknown" and "disabled" in row["detail"]
    # a preset kind with no rule on the board
    row = _row([], "Clearance")
    assert row["status"] == "missing_on_board" and row["verdict"] == "unknown"
    # scoped extra rules are judged against the preset rule of their kind
    board = [_board("Clearance", GAP="6mil", GENERICCLEARANCE="6mil"),
             _board("Clearance", NAME="Clearance_RF", GAP="20mil", PRIORITY="2", SCOPE1EXPRESSION="InNet('RF')"),
             _board("Clearance", NAME="Clearance_Fine", GAP="3mil", PRIORITY="3", SCOPE1EXPRESSION="InNet('FINE')"),
             _board("RoomDefinition", NAME="Room_RF")]
    rows = {r["rule"]: r for r in diff_rules(board)}
    assert rows["Clearance_RF"]["status"] == "extra_on_board" and rows["Clearance_RF"]["verdict"] == "safer"
    assert rows["Clearance_Fine"]["verdict"] == "below_fab_min"
    assert rows["Room_RF"]["verdict"] == "unknown"
    for r in rows.values():
        assert r["verdict"] in VERDICTS and isinstance(r["detail"], str)


def test_annular_ring_summary_synthetic():
    doc = {
        "vias": [
            {"hole_mm": 0.3, "dia_mm": 0.6, "net": "GND", "x_mm": 1.0, "y_mm": 2.0},
            {"hole_mm": 0.4, "dia_mm": 0.8, "net": None, "x_mm": 3.0, "y_mm": 4.0},
        ],
        "drilled_pads": [
            {"ref": "J1", "name": "1", "hole_mm": 0.6, "min_size_mm": 1.0, "plated": True},
            {"ref": None, "name": "", "hole_mm": 3.2, "min_size_mm": 3.2, "plated": False},   # mounting hole: ignored
        ],
    }
    s = annular_ring_summary(doc)
    assert s["min_ring_mm"] == pytest.approx(0.15)
    assert s["worst"]["source"] == "via" and s["worst"]["hole_mm"] == 0.3
    assert (s["via_count"], s["pad_count"]) == (2, 1)
    assert s["min_via_ring_mm"] == pytest.approx(0.15) and s["min_pad_ring_mm"] == pytest.approx(0.2)
    # a plated pad can be the worst
    doc["drilled_pads"][0].update(hole_mm=0.9, min_size_mm=1.1)           # ring 0.1
    s = annular_ring_summary(doc)
    assert s["min_ring_mm"] == pytest.approx(0.1) and s["worst"]["source"] == "pad" and s["worst"]["ref"] == "J1"
    assert annular_ring_summary({"vias": [], "drilled_pads": []}) is None
    assert annular_ring_summary({}) is None


def _ring_row(vias, pads=(), preset=None):
    doc = {"vias": vias, "drilled_pads": list(pads)}
    return _row([], "MinimumAnnularRing", geom=doc, preset=preset)


@pytest.mark.parametrize("hole,dia,verdict", [
    (0.3, 0.6, "same"),             # ring 0.15 mm vs preset 6 mil: unit rounding
    (0.3, 0.8, "safer"),            # ring 0.25 mm
    (0.3, 0.58, "below_fab_min"),   # ring 0.14 mm < 0.15 mm
])
def test_missing_annular_ring_rule_uses_actual_vias(hole, dia, verdict):
    row = _ring_row([{"hole_mm": hole, "dia_mm": dia, "net": None, "x_mm": 0, "y_mm": 0}])
    assert row["status"] == "missing_on_board"      # unchanged
    assert row["verdict"] == verdict
    assert "no rule on the board" in row["detail"] and "actual minimum ring" in row["detail"]
    assert row["actual"]["min_ring_mm"] == pytest.approx((dia - hole) / 2)
    if verdict == "below_fab_min":
        assert "BELOW" in row["detail"]
    else:
        assert "fab minimum" in row["detail"]


def test_missing_annular_ring_tighter_ok_and_unknown():
    preset = [{"name": "MinimumAnnularRing", "kind": "MinimumAnnularRing", "value": "10mil", "fab_min_mm": 0.15,
               "attributes": {"NAME": "MinimumAnnularRing", "RULEKIND": "MinimumAnnularRing", "MINIMUMRING": "10mil"}}]
    row = _ring_row([{"hole_mm": 0.3, "dia_mm": 0.7}], preset=preset)      # ring 0.2 mm: < 0.254, >= 0.15
    assert row["verdict"] == "tighter_ok"
    assert _ring_row([])["verdict"] == "unknown"
    assert _ring_row([], preset=preset)["verdict"] == "unknown"
    # no geometry passed at all (e.g. a caller that only has the rules)
    assert _row([], "MinimumAnnularRing")["verdict"] == "unknown"
    # a pad can be the one that fails
    row = _ring_row([{"hole_mm": 0.3, "dia_mm": 0.8}], pads=[{"ref": "J1", "name": "2", "hole_mm": 1.0,
                                                              "min_size_mm": 1.2, "plated": True}])
    assert row["verdict"] == "below_fab_min" and "J1-2" in row["detail"]


def test_existing_annular_ring_rule_is_compared_and_shows_actual():
    geom = {"vias": [{"hole_mm": 0.3, "dia_mm": 0.6}], "drilled_pads": []}
    row = _row([_board("MinimumAnnularRing", MINIMUMRING="4mil")], "MinimumAnnularRing", geom=geom)
    assert row["status"] == "differs" and row["verdict"] == "below_fab_min"     # 0.1016 mm rule < 0.15 mm
    assert "actual minimum ring 0.15" in row["detail"]


def test_pcbdoc_reader_exposes_vias_and_drilled_pads():
    doc = read_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    assert {"file", "components", "nets", "pads", "rules", "classes"} <= set(doc)   # existing keys intact
    assert len(doc["vias"]) == 43
    assert {v["hole_mm"] for v in doc["vias"]} == {0.4064, 2.75}
    assert {v["dia_mm"] for v in doc["vias"]} == {0.762, 6.2}
    assert all(set(v) >= {"net", "x_mm", "y_mm", "dia_mm", "hole_mm"} for v in doc["vias"])
    plated = [p for p in doc["drilled_pads"] if p["plated"]]
    assert len(doc["drilled_pads"]) == 123 and len(plated) == 111      # 12 unplated mounting holes
    assert {p["hole_mm"] for p in plated} == {0.9, 1.778}
    ring = annular_ring_summary(doc)
    assert ring["min_ring_mm"] == pytest.approx((0.762 - 0.4064) / 2, abs=1e-4)
    # a board with no vias reads as an empty list, not an error
    assert read_pcbdoc(FIXTURES / "rules-board.PcbDoc")["vias"] == []


def test_diff_pcbdoc_and_cli_json():
    rows = diff_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    assert all(r["verdict"] in VERDICTS and isinstance(r["detail"], str) for r in rows)
    ring = next(r for r in rows if r["kind"] == "MinimumAnnularRing")
    assert ring["status"] == "missing_on_board" and ring["verdict"] == "safer"      # ring 0.178 mm
    cmd = [sys.executable, str(REPO / "scripts" / "rules.py"), "diff", "--json", str(FIXTURES / "finished-board.PcbDoc")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["annular_ring"]["min_ring_mm"] == pytest.approx(0.1778, abs=1e-4)
    assert all("verdict" in r and "detail" in r and "status" in r for r in out["rules"])
    # the table has a Verdict column
    cmd = [sys.executable, str(REPO / "scripts" / "rules.py"), "diff", str(FIXTURES / "finished-board.PcbDoc")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0 and "Verdict" in proc.stdout and "safer" in proc.stdout
