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


from rules import _preset_scopes, _rule_scopes, board_rul_records  # noqa: E402

PRESET_KINDS = ("Clearance", "Width", "RoutingVias", "MinimumAnnularRing", "HoleSize",
                "SilkToSolderMaskClearance", "SolderMaskExpansion")


def test_board_aware_export_roundtrip(tmp_path):
    board_path = FIXTURES / "rules-board.PcbDoc"
    board = read_pcbdoc(board_path)["rules"]
    preset = get_preset_rule_records()
    recs = board_rul_records(board_path, preset)
    # a preset rule is added unless the board already has a rule of that kind with the same scopes
    have = {(r["RULEKIND"], _rule_scopes(r)) for r in board}
    added = [p for p in preset if (p["RULEKIND"], _preset_scopes({"attributes": p})) not in have]
    assert {p["NAME"] for p in added} == {"MinimumAnnularRing_PTH", "MinimumAnnularRing_Via", "SilkToSolderMaskClearance",
                                          "BoardOutlineClearance", "HoleToHoleClearance_PTH", "ViasUnderSMD"}
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
    rings = {r["NAME"]: r for r in back if r["RULEKIND"] == "MinimumAnnularRing"}
    assert rings["MinimumAnnularRing_PTH"]["MINIMUMRING"] == "10mil" and "MINIMUM" not in rings["MinimumAnnularRing_PTH"]
    assert rings["MinimumAnnularRing_PTH"]["SCOPE1EXPRESSION"] == "IsPad" and rings["MinimumAnnularRing_PTH"]["PRIORITY"] == "1"
    assert rings["MinimumAnnularRing_Via"]["MINIMUMRING"] == "6mil"
    assert rings["MinimumAnnularRing_Via"]["SCOPE1EXPRESSION"] == "IsVia" and rings["MinimumAnnularRing_Via"]["PRIORITY"] == "2"
    # the board's own scope-All hole to hole rule takes the JLC value; the pad-to-pad rule goes above it
    assert by_uid["TADLXEHF"]["GAP"] == "8mil" and by_uid["TADLXEHF"]["PRIORITY"] == "2"
    h2h = next(r for r in back if r["NAME"] == "HoleToHoleClearance_PTH")
    assert (h2h["GAP"], h2h["SCOPE1EXPRESSION"], h2h["SCOPE2EXPRESSION"], h2h["PRIORITY"]) == ("18mil", "IsPad", "IsPad", "1")
    assert by_uid["JXRRNWRL"]["MINSOLDERMASKWIDTH"] == "6mil"          # sliver rule updated in place
    outline = next(r for r in back if r["RULEKIND"] == "BoardOutlineClearance")
    assert outline["GAP"] == outline["GENERICCLEARANCE"] == "12mil" and outline["NETSCOPE"] == "DifferentNets"
    assert next(r for r in back if r["RULEKIND"] == "ViasUnderSMD")["ALLOWED"] == "FALSE"
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
        if kind not in fixture_keys:
            # The fixtures have no such rule. The keys come from a real Altium export of a finished board
            # (AD26): MinimumAnnularRing uses MINIMUMRING; ViasUnderSMD uses ALLOWED.
            assert kind in ("MinimumAnnularRing", "ViasUnderSMD"), kind
            if kind == "MinimumAnnularRing":
                assert "MINIMUMRING" in rec and "MINIMUM" not in rec
            else:
                assert rec["ALLOWED"] == "FALSE"
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
    """Fab floors are JLC's own minimums, read from its capabilities page (shared/reference/jlc/pcb-capabilities.en.md)."""
    preset = get_jlc_preset()                       # no board given: 2 layers, 1 oz, green
    by_name = {r["name"]: r for r in preset["rules"]}
    assert by_name["Clearance"]["fab_min_mm"] == 0.10         # P1: 2-layer 1 oz track/space 0.10 mm (4 mil); was 0.09 (the multilayer value)
    assert by_name["Width"]["fab_min_mm"] == 0.10             # was None: no floor was stored
    assert by_name["MinimumAnnularRing_PTH"]["fab_min_mm"] == 0.18    # P1: 2-layer 1 oz PTH ring 0.18 mm; was 0.15 for pads and vias
    assert by_name["MinimumAnnularRing_Via"]["fab_min_mm"] == 0.05    # P1: smallest via 0.15 / 0.25 mm, ring (0.25 - 0.15) / 2
    assert by_name["RoutingVias"]["fab_min_mm"] == {"hole": 0.15, "dia": 0.25}       # P1; was None
    assert by_name["HoleSize"]["fab_min_mm"] == {"min": 0.15}                        # P1 drills 0.15 to 6.3 mm; was None
    assert by_name["SilkToSolderMaskClearance"]["fab_min_mm"] == 0.15                # P1 pad to silkscreen
    assert by_name["MinimumSolderMaskSliver"]["fab_min_mm"] == 0.10                  # P1 mask bridge, 1 oz green
    assert by_name["BoardOutlineClearance"]["fab_min_mm"] == 0.2                     # P1 copper to routed edge
    assert by_name["HoleToHoleClearance_PTH"]["fab_min_mm"] == 0.45                  # P1 hole to hole, pad to pad
    assert by_name["HoleToHoleClearance"]["fab_min_mm"] == 0.2                       # P1 hole to hole, via to via
    assert by_name["SolderMaskExpansion"]["fab_min_mm"] is None and by_name["ViasUnderSMD"]["fab_min_mm"] is None
    for r in preset["rules"]:
        if r["fab_min_mm"] is not None:
            assert r["fab_min_source"] == preset["capabilities_url"] and r["fab_min_basis"]
    # the numeric view of a preset rule agrees with its .RUL attributes
    assert preset_values_mm(by_name["Width"]) == pytest.approx({"min": 0.127, "pref": 0.2032, "max": 1.016})
    assert preset_values_mm(by_name["RoutingVias"]) == pytest.approx({"hole": 0.3048, "dia": 0.6096})
    # ... and falls back to the *_mm keys / display string when there are no attributes
    bare = {"kind": "Width", "value": "Min: 5mil, Pref: 8mil, Max: 40mil"}
    assert preset_values_mm(bare) == pytest.approx({"min": 0.127, "pref": 0.2032, "max": 1.016})
    assert preset_values_mm({"kind": "Clearance", "value_mm": 0.1524}) == {"gap": 0.1524}


@pytest.mark.parametrize("gap,verdict", [
    ("5.9055mil", "same"),          # 0.15 mm vs 6 mil: unit rounding
    ("0.15mm", "same"),
    ("10mil", "safer"),
    ("4mil", "tighter_ok"),         # 0.1016 mm: tighter than 0.1524, above JLC's 0.10 mm 2-layer floor
    ("0.1mm", "tighter_ok"),        # exactly JLC's floor
    ("0.09mm", "below_fab_min"),    # was tighter_ok against the old 0.09 floor, which is the multilayer limit
    ("3mil", "below_fab_min"),      # 0.0762 mm < 0.10 mm
])
def test_verdict_clearance(gap, verdict):
    row = _row([_board("Clearance", GAP=gap, GENERICCLEARANCE=gap)], "Clearance")
    assert row["verdict"] == verdict
    assert row["status"] in ("match", "differs")   # the existing status is untouched
    assert row["decided_by"] == ["gap"] or verdict == "same"
    if verdict == "below_fab_min":
        assert "0.1 mm" in row["detail"] and "BELOW" in row["detail"]


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
    # a min tighter than the preset is ok down to JLC's floor (0.10 mm, 2-layer 1 oz) and below it is not;
    # before, no floor was stored and any smaller value was "unknown"
    row = _row(width("4mil", "8mil", "40mil"), "Width")
    assert row["verdict"] == "tighter_ok" and row["decided_by"] == ["min"]
    row = _row(width("3mil", "8mil", "40mil"), "Width")
    assert row["verdict"] == "below_fab_min" and "0.1 mm" in row["detail"]
    # a larger preferred width alone does not change the verdict
    assert _row(width("5mil", "20mil", "40mil"), "Width")["verdict"] == "same"


def test_verdict_routing_vias_hole_and_dia():
    def vias(h, d):
        return [_board("RoutingVias", HOLEWIDTH=h, WIDTH=d)]
    assert _row(vias("11.811mil", "23.622mil"), "RoutingVias")["verdict"] == "same"
    row = _row(vias("16mil", "24mil"), "RoutingVias")
    assert row["verdict"] == "safer" and row["decided_by"] == ["hole"]
    assert _row(vias("28mil", "50mil"), "RoutingVias")["verdict"] == "safer"
    # a smaller pad is fine down to JLC's smallest via (0.15 / 0.25 mm, P1) and not below it
    row = _row(vias("12mil", "20mil"), "RoutingVias")      # 0.508 mm pad
    assert row["verdict"] == "tighter_ok" and row["decided_by"] == ["dia"]
    assert _row(vias("12mil", "9mil"), "RoutingVias")["verdict"] == "below_fab_min"          # 0.2286 mm pad < 0.25 mm
    assert _row(vias("5mil", "30mil"), "RoutingVias")["verdict"] == "below_fab_min"          # 0.127 mm hole < 0.15 mm
    # a smaller via is judged worse than a larger one even if the other bound is bigger
    assert _row(vias("10mil", "30mil"), "RoutingVias")["verdict"] == "tighter_ok"


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
    # a smaller minimum is fine down to JLC's smallest drill (0.15 mm, P1); the maximum is 6.3 mm, not 250 mil
    assert _row(hole("7.874mil", "250mil"), "HoleSize")["verdict"] == "tighter_ok"          # was "unknown": no floor stored
    row = _row(hole("5mil", "250mil"), "HoleSize")                                            # 0.127 mm
    assert row["verdict"] == "below_fab_min" and "0.15" in row["detail"]


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


def _ring_row(vias, pads=(), preset=None, which=None):
    """The MinimumAnnularRing row for a board with no ring rule. The default preset has one rule for pads
    (MinimumAnnularRing_PTH, scope IsPad) and one for vias (MinimumAnnularRing_Via, scope IsVia): pick with `which`."""
    doc = {"vias": vias, "drilled_pads": list(pads)}
    rows = diff_rules([], preset, board_geom=doc)
    rows = [r for r in rows if r["kind"] == "MinimumAnnularRing"]
    return next(r for r in rows if which is None or r["rule"].endswith(which))


@pytest.mark.parametrize("hole,dia,verdict", [
    (0.3, 0.6, "same"),             # ring 0.15 mm vs preset 6 mil: unit rounding
    (0.3, 0.8, "safer"),            # ring 0.25 mm
    (0.3, 0.58, "tighter_ok"),      # ring 0.14 mm: was below_fab_min against 0.15 mm; JLC's smallest via (0.15 / 0.25) has a 0.05 mm ring
    (0.3, 0.38, "below_fab_min"),   # ring 0.04 mm < 0.05 mm
])
def test_missing_via_ring_rule_uses_actual_vias(hole, dia, verdict):
    row = _ring_row([{"hole_mm": hole, "dia_mm": dia, "net": None, "x_mm": 0, "y_mm": 0}], which="_Via")
    assert row["status"] == "missing_on_board"      # unchanged
    assert row["verdict"] == verdict
    assert "no rule on the board" in row["detail"] and "actual minimum ring" in row["detail"]
    assert row["actual"]["min_ring_mm"] == pytest.approx((dia - hole) / 2)
    if verdict == "below_fab_min":
        assert "BELOW" in row["detail"]
    else:
        assert "fab min" in row["detail"]


@pytest.mark.parametrize("hole,size,verdict", [
    (1.0, 1.508, "same"),           # ring 0.254 mm = the 10 mil preset
    (1.0, 1.6, "safer"),            # ring 0.3 mm
    (1.0, 1.4, "tighter_ok"),       # ring 0.2 mm: tighter than 10 mil, above JLC's 0.18 mm (2-layer 1 oz)
    (1.0, 1.3, "below_fab_min"),    # ring 0.15 mm < 0.18 mm; before this passed against 0.15 mm
])
def test_missing_pad_ring_rule_uses_plated_pads_only(hole, size, verdict):
    pad = {"ref": "J1", "name": "2", "hole_mm": hole, "min_size_mm": size, "plated": True}
    via = {"hole_mm": 0.3, "dia_mm": 0.8}           # ring 0.25: the pad rule must not look at it
    row = _ring_row([via], pads=[pad], which="_PTH")
    assert row["verdict"] == verdict and "J1-2" in row["detail"] and "1 plated pads" in row["detail"]
    assert row["actual"]["min_ring_mm"] == pytest.approx((size - hole) / 2) and row["actual"]["via_count"] == 0
    # an unplated mounting hole is not a pad ring
    mount = {"ref": None, "name": "", "hole_mm": 3.2, "min_size_mm": 3.2, "plated": False}
    assert _ring_row([via], pads=[mount], which="_PTH")["verdict"] == "unknown"
    assert _ring_row([], pads=[pad], which="_Via")["verdict"] == "unknown"          # no vias: nothing to judge


def test_missing_annular_ring_tighter_ok_and_unknown():
    preset = [{"name": "MinimumAnnularRing", "kind": "MinimumAnnularRing", "value": "10mil", "fab_min_mm": 0.15,
               "attributes": {"NAME": "MinimumAnnularRing", "RULEKIND": "MinimumAnnularRing", "MINIMUMRING": "10mil"}}]
    row = _ring_row([{"hole_mm": 0.3, "dia_mm": 0.7}], preset=preset)      # ring 0.2 mm: < 0.254, >= 0.15
    assert row["verdict"] == "tighter_ok"
    assert _ring_row([])["verdict"] == "unknown"
    assert _ring_row([], preset=preset)["verdict"] == "unknown"
    # no geometry passed at all (e.g. a caller that only has the rules)
    assert _row([], "MinimumAnnularRing")["verdict"] == "unknown"
    # a rule with no scope looks at vias and pads together: a pad can be the one that fails
    row = _ring_row([{"hole_mm": 0.3, "dia_mm": 0.8}], preset=preset,
                    pads=[{"ref": "J1", "name": "2", "hole_mm": 1.0, "min_size_mm": 1.2, "plated": True}])
    assert row["verdict"] == "below_fab_min" and "J1-2" in row["detail"]


def test_existing_annular_ring_rule_is_compared_and_shows_actual():
    geom = {"vias": [{"hole_mm": 0.3, "dia_mm": 0.6}], "drilled_pads": []}
    rows = diff_rules([_board("MinimumAnnularRing", MINIMUMRING="4mil")], board_geom=geom)
    ring = {r["rule"]: r for r in rows if r["kind"] == "MinimumAnnularRing"}
    # the board's one scope-All ring rule governs pads and vias: it is judged against both preset rules
    assert set(ring) == {"MinimumAnnularRing_PTH", "MinimumAnnularRing_Via"}
    assert all(r["status"] == "differs" for r in ring.values())
    assert ring["MinimumAnnularRing_PTH"]["verdict"] == "below_fab_min"        # 0.1016 mm < 0.18 mm (pads, 2 layers)
    assert ring["MinimumAnnularRing_Via"]["verdict"] == "tighter_ok"           # 0.1016 mm >= 0.05 mm (vias)
    assert "actual minimum ring 0.15" in ring["MinimumAnnularRing_Via"]["detail"]
    assert "(all objects) also applies" in ring["MinimumAnnularRing_Via"]["detail"]
    assert not [r for r in rows if r["status"] == "extra_on_board" and r["kind"] == "MinimumAnnularRing"]


def test_scoped_annular_ring_rules_match_by_scope():
    board = [_board("MinimumAnnularRing", NAME="Ring_Pads", MINIMUMRING="10mil", SCOPE1EXPRESSION="IsPad"),
             _board("MinimumAnnularRing", NAME="Ring_Vias", MINIMUMRING="4mil", SCOPE1EXPRESSION="IsVia", PRIORITY="2")]
    rows = {r["rule"]: r for r in diff_rules(board)}
    assert rows["Ring_Pads"]["status"] == "match" and rows["Ring_Pads"]["verdict"] == "same"
    assert rows["Ring_Vias"]["verdict"] == "tighter_ok" and rows["Ring_Vias"]["status"] == "differs"
    assert rows["Ring_Pads"]["kind"] == rows["Ring_Vias"]["kind"] == "MinimumAnnularRing"
    assert not [r for r in rows.values() if r["status"] in ("extra_on_board", "missing_on_board")
                and r["kind"] == "MinimumAnnularRing"]


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
    ring = {r["rule"]: r for r in rows if r["kind"] == "MinimumAnnularRing"}
    assert all(r["status"] == "missing_on_board" for r in ring.values())
    assert ring["MinimumAnnularRing_Via"]["verdict"] == "safer"          # via ring 0.178 mm vs 6 mil
    assert ring["MinimumAnnularRing_PTH"]["verdict"] == "safer"          # pad ring 0.3 mm vs 10 mil
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


# ---------------------------------------------------------------------------
# the preset follows the board: layers, copper weight, mask colour (scripts/jlc_preset.py)
# Evidence: JLC's capabilities page, shared/reference/jlc/pcb-capabilities.en.md ([P1] etc.), and
# JLCDFM's own limits, docs/bench-runs/jlc-live-2026-10-14/jlcdfm_rules.json (read 2026-10-14).
# ---------------------------------------------------------------------------
import jlc_preset  # noqa: E402
from rules import board_settings  # noqa: E402

JLCDFM_FILE = REPO / "docs" / "bench-runs" / "jlc-live-2026-10-14" / "jlcdfm_rules.json"


def _named(board=None):
    return {r["name"]: r for r in get_jlc_preset(board)["rules"]}


def _preset_for(board=None):
    return get_jlc_preset(board)["rules"]


def test_preset_name_and_floors_follow_layers_and_copper():
    for unknown in (None, {}, {"layers": "abc"}, {"copper_oz": None}, "junk"):
        assert get_jlc_preset(unknown)["name"] == "JLC 2-layer 1 oz"
    two = _named({"layers": 2, "copper_oz": 1.0})
    assert two["Clearance"]["fab_min_mm"] == 0.10 and two["MinimumAnnularRing_PTH"]["fab_min_mm"] == 0.18
    assert two["Clearance"]["value"] == "6mil" and two["MinimumAnnularRing_PTH"]["value"] == "10mil"
    # multilayer 1 oz: track/space 0.09 mm (3.5 mil), PTH ring 0.15 mm absolute / 0.20 mm recommended (8 mil) [P1]
    p4 = get_jlc_preset({"layers": 4, "copper_oz": 1.0})
    assert p4["name"] == "JLC 4-layer 1 oz"
    four = {r["name"]: r for r in p4["rules"]}
    assert four["Clearance"]["fab_min_mm"] == 0.09 and four["Width"]["fab_min_mm"] == 0.09
    assert four["Clearance"]["value"] == "6mil"                    # JLCDFM rates 6 mil Good, 5.9 mil Warning
    assert four["MinimumAnnularRing_PTH"]["fab_min_mm"] == 0.15 and four["MinimumAnnularRing_PTH"]["value"] == "8mil"
    assert four["MinimumAnnularRing_Via"]["value"] == "6mil"
    # 2 oz (P3): track/space 0.16 mm on any layer count, PTH ring >= 0.254 mm, mask bridge 0.20 mm
    for layers in (2, 4):
        p = get_jlc_preset({"layers": layers, "copper_oz": 2})
        assert p["name"] == f"JLC {layers}-layer 2 oz"
        n = {r["name"]: r for r in p["rules"]}
        assert n["Clearance"]["fab_min_mm"] == n["Width"]["fab_min_mm"] == 0.16
        assert n["Clearance"]["value"] == "8mil" and n["Width"]["value"].startswith("Min: 8mil")
        assert n["MinimumAnnularRing_PTH"]["fab_min_mm"] == 0.254 and n["MinimumAnnularRing_PTH"]["value"] == "10mil"
        assert n["MinimumSolderMaskSliver"]["fab_min_mm"] == 0.20 and n["MinimumSolderMaskSliver"]["value"] == "8mil"
    # heavy copper exists on 2-layer boards only (2.5 / 3.5 / 4.5 oz: 0.20 / 0.25 / 0.30 mm)
    for oz, floor in ((2.5, 0.20), (3.5, 0.25), (4.5, 0.30)):
        assert _named({"layers": 2, "copper_oz": oz})["Clearance"]["fab_min_mm"] == floor
    assert get_jlc_preset({"layers": 4, "copper_oz": 3.5})["name"] == "JLC 4-layer 2 oz"
    # a project block holds strings sometimes
    assert get_jlc_preset({"layers": "4", "copper_oz": "1 oz"})["name"] == "JLC 4-layer 1 oz"
    # 1-layer boards: 0.3 mm smallest drill and via [P1]
    one = _named({"layers": 1})
    assert get_jlc_preset({"layers": 1})["name"] == "JLC 1-layer 1 oz"
    assert one["HoleSize"]["fab_min_mm"] == {"min": 0.3} and one["RoutingVias"]["fab_min_mm"] == {"hole": 0.3, "dia": 0.5}


def test_mask_colour_changes_the_mask_bridge_floor():
    # P1: 1 oz mask bridge 0.10 mm for green, red, yellow, blue, purple; 0.13 mm for black and white; 2 oz 0.20 mm any colour
    assert _named()["MinimumSolderMaskSliver"]["fab_min_mm"] == 0.10
    for colour, floor in (("green", 0.10), ("Red", 0.10), ("black", 0.13), ("White", 0.13), ("matte black", 0.13)):
        n = _named({"layers": 2, "copper_oz": 1, "mask_colour": colour})
        assert n["MinimumSolderMaskSliver"]["fab_min_mm"] == floor, colour
    assert _named({"layers": 2, "copper_oz": 2, "mask_colour": "black"})["MinimumSolderMaskSliver"]["fab_min_mm"] == 0.20
    # a 0.10 mm sliver rule passes on green and is below the floor on black
    board = [_board("MinimumSolderMaskSliver", MINSOLDERMASKWIDTH="0.1mm")]
    assert _row(board, "MinimumSolderMaskSliver", preset=_preset_for())["verdict"] == "tighter_ok"
    assert _row(board, "MinimumSolderMaskSliver", preset=_preset_for({"mask_colour": "black"}))["verdict"] == "below_fab_min"


def test_preset_has_scoped_annular_ring_rules():
    n = _named()
    pth, via = n["MinimumAnnularRing_PTH"], n["MinimumAnnularRing_Via"]
    assert (pth["kind"], pth["scope1"], pth["attributes"]["SCOPE1EXPRESSION"]) == ("MinimumAnnularRing", "IsPad", "IsPad")
    assert (via["kind"], via["scope1"], via["attributes"]["SCOPE1EXPRESSION"]) == ("MinimumAnnularRing", "IsVia", "IsVia")
    assert pth["attributes"]["PRIORITY"] == "1" and via["attributes"]["PRIORITY"] == "2"
    assert pth["attributes"]["MINIMUMRING"] == "10mil" and via["attributes"]["MINIMUMRING"] == "6mil"
    assert "MinimumAnnularRing" not in n          # no scope-All ring rule: pads and vias have different JLC limits


def test_new_rule_kinds_use_altium_rul_syntax(tmp_path):
    """The keys and scope strings are the ones in Altium's own export of a finished board (AD26)
    and in tests/fixtures/altium; write_rul / read_rul keep them."""
    recs = get_preset_rule_records()
    back = read_rul(write_rul(recs, tmp_path / "preset.RUL"))
    assert back == recs
    by_name = {r["NAME"]: r for r in back}
    outline = by_name["BoardOutlineClearance"]
    assert outline["GAP"] == "12mil" and outline["GENERICCLEARANCE"] == "12mil"
    assert by_name["MinimumSolderMaskSliver"]["MINSOLDERMASKWIDTH"] == "6mil"
    pad_pair = by_name["HoleToHoleClearance_PTH"]
    assert (pad_pair["SCOPE1EXPRESSION"], pad_pair["SCOPE2EXPRESSION"], pad_pair["GAP"]) == ("IsPad", "IsPad", "18mil")
    other = by_name["HoleToHoleClearance"]
    assert (other["SCOPE1EXPRESSION"], other["SCOPE2EXPRESSION"], other["GAP"], other["PRIORITY"]) == ("All", "All", "8mil", "2")
    assert by_name["ViasUnderSMD"]["ALLOWED"] == "FALSE"
    assert by_name["MinimumAnnularRing_Via"]["SCOPE1EXPRESSION"] == "IsVia"
    assert all(r["ENABLED"] == "TRUE" and r["SCOPE2EXPRESSION"] for r in back)


def test_hole_size_maximum_is_jlcs_6_3_mm():
    hs = _named()["HoleSize"]
    assert hs["attributes"]["MAXLIMIT"] == "248.0315mil" and hs["attributes"]["MINLIMIT"] == "12mil"
    assert to_mm("248.0315mil") == pytest.approx(6.3, abs=1e-4)           # P1: drills 0.15 to 6.3 mm; was 250 mil = 6.35 mm
    assert preset_values_mm(hs)["max"] == pytest.approx(6.3, abs=1e-4)
    assert hs["max_mm"] == 6.3


def test_mask_expansion_description_does_not_invent_a_jlc_standard():
    me = _named()["SolderMaskExpansion"]
    # the old text said "fab standard 0.05mm"; JLC accepts 1:1 openings and recommends 0.1 mm (P1, P7)
    assert "fab standard" not in me["description"].lower() and "standard 0.05" not in me["description"]
    assert "1:1" in me["description"] and "0.1 mm" in me["description"] and "0.09" in me["description"]
    assert me["value"] == "2mil" and me["fab_min_mm"] is None


def test_dfm_limits_in_the_preset_are_the_ones_jlcdfm_serves():
    if not JLCDFM_FILE.is_file():
        pytest.skip("JLCDFM limits evidence file is not in this checkout")
    served = {r["title"]: r["range_mil"] for r in json.loads(JLCDFM_FILE.read_text(encoding="utf-8"))["rules"].values()}
    for title, rng in jlc_preset.DFM.items():
        assert served[title] == rng, title


@pytest.mark.parametrize("board", [None, {"layers": 4}, {"layers": 2, "copper_oz": 2}, {"layers": 4, "copper_oz": 2},
                                   {"layers": 2, "copper_oz": 3.5}])
def test_every_preset_value_is_good_in_jlcdfm(board):
    """The preset values are chosen so JLCDFM (whole-mil limits) shows no Danger or Warning for them."""
    rules_ = _preset_for(board)
    for r in rules_:
        vals = preset_values_mm(r)
        for chk in r.get("jlcdfm") or []:
            level = jlc_preset.dfm_level(next(iter(vals.values())), chk["range_mil"])
            assert level in ("Good", "Not reported"), (r["name"], chk["check"], level)
    n = {r["name"]: r for r in rules_}
    # silk to pad in JLCDFM = silk to mask opening + mask expansion: Danger below 5 mil, Warning below 7 mil
    silk_mm = preset_values_mm(n["SilkToSolderMaskClearance"])["gap"] + preset_values_mm(n["SolderMaskExpansion"])["expansion"]
    assert jlc_preset.dfm_level(silk_mm, jlc_preset.DFM["Silkscreen to pad"]) in ("Good", "Not reported")


def test_jlcdfm_levels_follow_its_whole_mil_limits():
    rng = jlc_preset.DFM["Trace spacing"]                                  # 4 / 6 / 8 mil
    assert jlc_preset.dfm_level(0.10, rng) == "Danger"                     # 3.94 mil: JLC's page accepts it, JLCDFM does not
    assert jlc_preset.dfm_level(0.1016, rng) == "Warning"
    assert jlc_preset.dfm_level(0.15, rng) == "Warning"                    # 5.9 mil
    assert jlc_preset.dfm_level(0.1524, rng) == "Good"
    assert jlc_preset.dfm_level(0.2032, rng) == "Not reported"


def test_jlcdfm_note_is_added_to_the_detail_but_the_verdict_stays_the_fab_floor():
    row = _row([_board("Clearance", GAP="5.9055mil", GENERICCLEARANCE="5.9055mil")], "Clearance")
    assert row["verdict"] == "same"                                        # 0.15 mm against 6 mil: unit rounding
    assert "JLCDFM Trace spacing: Warning (below 6 mil)" in row["detail"]
    assert row["bounds"][0]["jlcdfm"] == "Warning"
    row = _row([_board("Clearance", GAP="3.9370mil", GENERICCLEARANCE="3.9370mil")], "Clearance")   # 0.10 mm: JLC accepts it
    assert row["verdict"] == "tighter_ok" and "Danger (below 4 mil)" in row["detail"]
    assert "JLCDFM" not in _row([_board("Clearance", GAP="10mil", GENERICCLEARANCE="10mil")], "Clearance")["detail"]
    # the missing ring rows say it too (a 5.9 mil via ring is a JLCDFM Warning)
    ring = _ring_row([{"hole_mm": 0.3, "dia_mm": 0.6}], which="_Via")
    assert ring["verdict"] == "same" and "JLCDFM Annular ring: Warning (below 6 mil)" in ring["detail"]


@pytest.mark.parametrize("value,verdict", [
    ("6mil", "same"),
    ("10mil", "safer"),
    ("4mil", "tighter_ok"),         # 0.1016 mm >= 0.10 mm
    ("2.7559mil", "below_fab_min"), # 0.07 mm: a real USB-C sliver rule
])
def test_verdict_mask_sliver(value, verdict):
    assert _row([_board("MinimumSolderMaskSliver", MINSOLDERMASKWIDTH=value)], "MinimumSolderMaskSliver")["verdict"] == verdict


@pytest.mark.parametrize("value,verdict", [
    ("12mil", "same"),
    ("11.811mil", "same"),          # 0.3 mm, a real board
    ("20mil", "safer"),
    ("0.2mm", "tighter_ok"),        # JLC: copper to routed edge >= 0.2 mm
    ("0.15mm", "below_fab_min"),
])
def test_verdict_board_outline_clearance(value, verdict):
    row = _row([_board("BoardOutlineClearance", GAP=value, GENERICCLEARANCE=value)], "BoardOutlineClearance")
    assert row["verdict"] == verdict


def test_hole_to_hole_rules_pad_pair_and_everything_else():
    # one scope-All rule on the board (as in a real board, 10 mil = 0.254 mm) governs pad pairs too
    rows = {r["rule"]: r for r in diff_rules([_board("HoleToHoleClearance", GAP="10mil")])}
    pth, other = rows["HoleToHoleClearance_PTH"], rows["HoleToHoleClearance"]
    assert pth["verdict"] == "below_fab_min" and "0.45" in pth["detail"]           # JLC pad to pad 0.45 mm [P1]
    assert "(all objects) also applies" in pth["detail"]
    assert other["verdict"] == "safer" and other["status"] == "differs"            # 0.254 mm vs 8 mil, JLC via to via 0.2 mm
    assert not [r for r in rows.values() if r["status"] == "extra_on_board"]
    # scoped board rules are matched to the preset rule with the same scopes
    board = [_board("HoleToHoleClearance", NAME="H2H_pads", GAP="18mil", SCOPE1EXPRESSION="IsPad", SCOPE2EXPRESSION="IsPad"),
             _board("HoleToHoleClearance", NAME="H2H_all", GAP="8mil", PRIORITY="2")]
    rows = {r["rule"]: r for r in diff_rules(board)}
    assert rows["H2H_pads"]["status"] == "match" and rows["H2H_all"]["status"] == "match"
    assert len(rows) == len(_preset_for())


def test_vias_under_smd_is_a_flag_not_a_number():
    row = _row([_board("ViasUnderSMD", ALLOWED="FALSE")], "ViasUnderSMD")
    assert (row["status"], row["verdict"], row["board value"]) == ("match", "same", "Not allowed")
    row = _row([_board("ViasUnderSMD", ALLOWED="TRUE")], "ViasUnderSMD")
    assert row["status"] == "differs" and row["verdict"] == "unknown" and "filled" in row["detail"]
    assert _row([], "ViasUnderSMD")["status"] == "missing_on_board"


def test_board_settings_and_project_board_pick_the_preset(empty):
    import project
    assert board_settings(layers=4, oz=2) == {"layers": 4, "copper_oz": 2}
    assert board_settings() == {}
    board = project.board(empty)
    assert board["mask_colour"] == "green"                                   # config/defaults.json engineering_defaults
    assert get_jlc_preset(project.board(empty))["name"] == "JLC 2-layer 1 oz"
    project.touch(empty, board={**board, "layers": 4, "copper_oz": 2.0})
    assert get_jlc_preset(project.board(empty))["name"] == "JLC 4-layer 2 oz"
    assert get_jlc_preset(board_settings(empty, layers=2))["name"] == "JLC 2-layer 2 oz"      # the command line wins


def test_rules_cli_takes_layers_and_copper(tmp_path):
    script = str(REPO / "scripts" / "rules.py")
    proc = subprocess.run([sys.executable, script, "preset", "--layers", "4", "--oz", "2"], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.startswith("JLC 4-layer 2 oz")
    assert "MinimumAnnularRing_PTH" in proc.stdout and "[IsPad]" in proc.stdout
    out = tmp_path / "four.RUL"
    proc = subprocess.run([sys.executable, script, "export", str(out), "--layers", "4"], capture_output=True, text=True)
    assert proc.returncode == 0 and "JLC 4-layer 1 oz" in proc.stdout
    recs = {r["NAME"]: r for r in read_rul(out)}
    assert recs["MinimumAnnularRing_PTH"]["MINIMUMRING"] == "8mil" and recs["Clearance"]["GAP"] == "6mil"
    board = str(FIXTURES / "rules-board.PcbDoc")
    proc = subprocess.run([sys.executable, script, "diff", "--json", board, "--layers", "4"], capture_output=True, text=True)
    assert proc.returncode == 0 and json.loads(proc.stdout)["preset"] == "JLC 4-layer 1 oz"


def test_jlc_live_coupons_are_judged_by_the_scoped_rule_of_their_object():
    import jlc_live
    v, checks = jlc_live.preset_verdict({"kind": "annular_ring"}, {"ring_mm": 0.15})            # pad ring: floor 0.18 mm
    assert v == "below_fab_min" and checks == [("MinimumAnnularRing", "below_fab_min")]
    v, checks = jlc_live.preset_verdict({"kind": "via", "nominal": {}}, {"ring_mm": 0.05, "drill_mm": 0.15, "dia_mm": 0.25})
    assert v == "tighter_ok"                                                                    # JLC's smallest via
    v, _ = jlc_live.preset_verdict({"kind": "hole_to_hole", "nominal": {"what": "pad-pad"}}, {"gap_mm": 0.40})
    assert v == "below_fab_min"
    v, _ = jlc_live.preset_verdict({"kind": "hole_to_hole", "nominal": {"what": "via-via"}}, {"gap_mm": 0.25})
    assert v == "safer"
