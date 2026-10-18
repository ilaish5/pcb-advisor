"""Extra rule kinds (validation, .RUL records, round trip) and the IPC standard presets."""
import pathlib
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import ipc_standards  # noqa: E402
import rule_kinds  # noqa: E402
from altium import read_rul  # noqa: E402
from rules import format_rul_bytes, rule_display_value, write_rul  # noqa: E402
from test_server import get, post, server  # noqa: E402,F401

# kind -> (values given, expected record keys/values, expected display)
CASES = {
    "Width": ({"min": "6mil", "pref": "10mil", "max": "40mil"}, {"MINLIMIT": "6mil", "PREFEREDWIDTH": "10mil", "MAXLIMIT": "40mil"}, "Min: 6mil, Pref: 10mil, Max: 40mil"),
    "Clearance": ({"gap": "0.2mm"}, {"GAP": "7.874mil", "GENERICCLEARANCE": "7.874mil"}, "7.874mil"),
    "RoutingVias": ({"hole": "12mil", "dia": "24mil"}, {"HOLEWIDTH": "12mil", "WIDTH": "24mil", "MINWIDTH": "24mil"}, "Hole: 12mil, Dia: 24mil"),
    "ComponentClearance": ({"gap": "20mil"}, {"GAP": "20mil", "VERTICALGAP": "20mil"}, "20mil"),
    "HoleSize": ({"min": "12mil", "max": "250mil"}, {"MINLIMIT": "12mil", "MAXLIMIT": "250mil", "ABSOLUTEVALUES": "TRUE"}, "Min: 12mil, Max: 250mil"),
    "MinimumAnnularRing": ({"ring": "8mil"}, {"MINIMUMRING": "8mil"}, "8mil"),
    "HoleToHoleClearance": ({"gap": "12mil"}, {"GAP": "12mil"}, "12mil"),
    "SolderMaskExpansion": ({"expansion": "3mil"}, {"EXPANSION": "3mil"}, "3mil"),
    "PasteMaskExpansion": ({"expansion": "-2mil"}, {"EXPANSION": "-2mil"}, "-2mil"),
    "SilkToSolderMaskClearance": ({"gap": "6mil"}, {"MINSILKSCREENTOMASKGAP": "6mil"}, "6mil"),
    "SilkToSilkClearance": ({"gap": "5mil"}, {"SILKTOSILKCLEARANCE": "5mil"}, "5mil"),
    "PlaneClearance": ({"gap": "20mil"}, {"CLEARANCE": "20mil"}, "20mil"),
    "PolygonConnect": ({"style": "Relief", "width": "12mil"}, {"CONNECTSTYLE": "Relief", "RELIEFCONDUCTORWIDTH": "12mil", "AIRGAPWIDTH": "10mil"}, "Relief, spoke 12mil, gap 10mil"),
    "DiffPairsRouting": ({"width": "6mil", "gap": "8mil"}, {"MOSTFREQGAP": "8mil", "MINLIMIT": "8mil", "TOPLAYER_PREFWIDTH": "6mil", "BOTTOMLAYER_MINWIDTH": "6mil", "MIDLAYER30_MAXWIDTH": "6mil"}, "Width: 6mil, Gap: 8mil"),
}


def test_every_kind_has_a_case():
    assert set(CASES) == set(rule_kinds.KINDS)


@pytest.mark.parametrize("kind", list(CASES))
def test_kind_validates_and_survives_a_rul_round_trip(kind, tmp_path):
    values, expect, display = CASES[kind]
    rule = rule_kinds.validate_rule({"name": f"T_{kind}", "kind": kind, "scope1": "InNetClass('HV')", "values": values})
    attrs = rule["attributes"]
    for k, v in expect.items():
        assert attrs[k] == v, k
    assert attrs["RULEKIND"] == kind and attrs["SCOPE1EXPRESSION"] == "InNetClass('HV')" and attrs["SCOPE2EXPRESSION"] == "All"
    assert rule["value"] == display == rule_display_value(attrs)
    write_rul([attrs], tmp_path / "x.RUL")
    back = read_rul(tmp_path / "x.RUL")
    assert len(back) == 1 and back[0] == attrs
    assert rule_display_value(back[0]) == display


@pytest.mark.parametrize("bad", [
    {"name": "A", "kind": "Nope", "values": {}},
    {"name": "", "kind": "Clearance", "values": {"gap": "5mil"}},
    {"name": "a|b", "kind": "Clearance", "values": {"gap": "5mil"}},
    {"name": "A", "kind": "Clearance", "values": {"gap": "abc"}},
    {"name": "A", "kind": "Clearance", "values": {}},
    {"name": "A", "kind": "Clearance", "values": {"gap": "-5mil"}},
    {"name": "A", "kind": "Clearance", "values": {"gap": "5mil"}, "scope1": "InNet('A'"},
    {"name": "A", "kind": "Clearance", "values": {"gap": "5mil"}, "scope1": "x|y"},
    {"name": "A", "kind": "Width", "values": {"min": "20mil", "pref": "10mil", "max": "40mil"}},
    {"name": "A", "kind": "HoleSize", "values": {"min": "30mil", "max": "12mil"}},
    {"name": "A", "kind": "RoutingVias", "values": {"hole": "24mil", "dia": "20mil"}},
    {"name": "A", "kind": "PolygonConnect", "values": {"style": "Thermal"}},
    {"name": "A", "kind": "DiffPairsRouting", "values": {"width": "6mil"}},
])
def test_bad_rules_are_refused(bad):
    with pytest.raises(ValueError):
        rule_kinds.validate_rule(bad)


def test_old_single_value_form_still_works_and_width_is_no_longer_written_as_a_gap():
    w = rule_kinds.validate_rule({"name": "PowerNet_Width", "kind": "Width", "scope1": "InNet('12V')", "value": "30mil"})
    assert w["attributes"]["MINLIMIT"] == w["attributes"]["MAXLIMIT"] == "30mil" and "GAP" not in w["attributes"]
    with pytest.raises(ValueError):
        rule_kinds.validate_rule({"name": "V", "kind": "RoutingVias", "value": "12mil"})
    # a rule stored by the old server (Width saved with a GAP only) is rebuilt on export
    old = {"name": "Old", "kind": "Width", "scope1": "All", "value": "30mil",
           "attributes": {"NAME": "Old", "RULEKIND": "Width", "SCOPE1EXPRESSION": "All", "GAP": "30mil"}}
    assert rule_kinds.record_for(old)["MINLIMIT"] == "30mil"


def test_scoped_extra_goes_above_and_scope_all_goes_below():
    recs = [{"NAME": "Clearance", "RULEKIND": "Clearance", "PRIORITY": "1", "SCOPE1EXPRESSION": "All", "SCOPE2EXPRESSION": "All"}]
    scoped = rule_kinds.validate_rule({"name": "HV", "kind": "Clearance", "scope1": "InNetClass('HV')", "values": {"gap": "1mm"}})
    allr = rule_kinds.validate_rule({"name": "Gen", "kind": "Clearance", "values": {"gap": "8mil"}})
    out = rule_kinds.append_extra_records(recs, [scoped, allr])
    prio = {r["NAME"]: r["PRIORITY"] for r in out}
    assert prio == {"Clearance": "2", "HV": "1", "Gen": "3"}
    assert format_rul_bytes(out)


# ------------------------------------------------------------ standards

@pytest.mark.parametrize("volts,loc,mm", [
    (10, "B2", 0.1), (60, "B2", 0.6), (60, "B1", 0.1), (60, "B4", 0.13), (150, "B2", 0.6), (151, "B2", 1.25),
    (300, "B1", 0.2), (500, "B2", 2.5), (1000, "B2", 5.0), (1000, "B4", 0.8 + 0.00305 * 500)])
def test_ipc2221b_table(volts, loc, mm):
    assert ipc_standards.clearance_mm(volts, loc) == pytest.approx(mm, abs=1e-4)


def test_standard_60v_external_uncoated():
    pre = ipc_standards.preview("ipc2221b", {"volts": "60", "location": "B2", "scope": "InNetClass('HV')"})
    (row,) = pre["rules"]
    assert pre["source"] == "standards/ipc-2221b-clearance.en.md"
    assert row["kind"] == "Clearance" and row["scope1"] == "InNetClass('HV')" and row["kept"] == "standard"
    assert row["standard_mm"] == 0.6 and row["value_mm"] == 0.6
    assert row["attributes"]["GAP"] == "23.622mil" and row["name"].startswith("IPC2221B_B2_60V")


def test_standard_is_never_weaker_than_jlc():
    jlc = ipc_standards._jlc(None, "Clearance")["value_mm"]
    pre = ipc_standards.preview("ipc2221b", {"volts": "5", "location": "B1"})   # standard 0.05 mm, below any JLC spacing
    (row,) = pre["rules"]
    assert row["kept"] == "jlc" and row["value_mm"] == pytest.approx(jlc, abs=1e-4) and row["value_mm"] > row["standard_mm"]
    assert "stricter value is kept" in row["note"]
    for cls in ("2", "3"):
        rows = ipc_standards.preview("ipc_class", {"class": cls})["rules"]
        assert {r["scope1"] for r in rows} == {"IsPad", "IsVia"}
        for r in rows:
            assert r["value_mm"] >= 0.05 and r["value_mm"] >= r["jlc_mm"] - 1e-9
            assert r["kept"] in ("jlc", "equal")


@pytest.mark.parametrize("params", [{"volts": "0"}, {"volts": "x"}, {"volts": "5000"}, {"volts": "50", "location": "A6"},
                                    {"volts": "50", "scope": "InNet('x'"}])
def test_standard_bad_input(params):
    with pytest.raises(ValueError):
        ipc_standards.preview("ipc2221b", params)
    with pytest.raises(ValueError):
        ipc_standards.preview("nope", {})


def test_standard_data_files_exist_and_are_cited():
    d = ipc_standards.data()
    for src in (d["clearance"]["source"], d["annular_ring"]["source"]):
        assert (REPO / "shared" / "reference" / src).is_file()


# ------------------------------------------------------------ API

def read_rul_bytes(raw):
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "x.RUL"
        p.write_bytes(raw)
        return read_rul(p)


def test_api_kinds_preview_apply_export_delete(server, lte):
    code, res = get(server, "/api/rules", lte)
    assert code == 200 and {k["kind"] for k in res["kinds"]} == set(rule_kinds.KINDS)
    assert {s["id"] for s in res["standards"]["standards"]} == {"ipc2221b", "ipc_class"}

    code, pre = get(server, "/api/rules/standard?standard=ipc2221b&volts=60&location=B2&scope=InNetClass('HV')", lte)
    assert code == 200 and pre["rules"][0]["value_mm"] == 0.6
    code, err = get(server, "/api/rules/standard?standard=ipc2221b&volts=-1", lte)
    assert code == 400 and "error" in err

    code, res = post(server, "/api/rules/standard", {"standard": "ipc2221b", "volts": 60, "location": "B2", "scope": "InNetClass('HV')"}, lte)
    assert code == 200 and len(res["added"]) == 1
    code, res = post(server, "/api/rules/extra", {"rule": {"name": "Diff90", "kind": "DiffPairsRouting", "values": {"width": "6mil", "gap": "8mil"}}}, lte)
    assert code == 200
    code, res = post(server, "/api/rules/extra", {"rule": {"name": "Bad", "kind": "HoleSize", "values": {"min": "30mil", "max": "12mil"}}}, lte)
    assert code == 400 and "error" in res

    code, raw = get(server, "/api/rules/export", lte, raw=True)
    assert code == 200
    names = {r["NAME"]: r for r in read_rul_bytes(raw)}
    hv = next(r for n, r in names.items() if n.startswith("IPC2221B_B2_60V"))
    assert hv["GAP"] == "23.622mil" and hv["PRIORITY"] == "1"
    assert names["Diff90"]["MOSTFREQGAP"] == "8mil"

    code, res = post(server, "/api/rules/extra/delete", {"name": "Diff90"}, lte)
    assert code == 200 and all(r["name"] != "Diff90" for r in res["extra"])


def test_api_choose_which_rules_apply(server, lte):
    # standard: only the ticked rows are added
    code, res = post(server, "/api/rules/standard", {"standard": "ipc_class", "params": {"class": "3"},
                                                     "names": ["IPC_Class3_AnnularRing_Via"]}, lte)
    assert code == 200 and res["added"] == ["IPC_Class3_AnnularRing_Via"]
    assert [r["name"] for r in res["extra"]] == ["IPC_Class3_AnnularRing_Via"]
    code, res = post(server, "/api/rules/standard", {"standard": "ipc_class", "params": {"class": "3"}, "names": []}, lte)
    assert code == 400

    # extra rules: an off rule stays in the list but not in the .RUL
    post(server, "/api/rules/extra", {"rule": {"name": "KeepMe", "kind": "SilkToSilkClearance", "values": {"gap": "5mil"}}}, lte)
    code, res = post(server, "/api/rules/extra/enabled", {"name": "IPC_Class3_AnnularRing_Via", "enabled": False}, lte)
    assert code == 200 and next(r for r in res["extra"] if r["name"] == "IPC_Class3_AnnularRing_Via")["enabled"] is False
    code, raw = get(server, "/api/rules/export", lte, raw=True)
    names = {r["NAME"] for r in read_rul_bytes(raw)}
    assert "KeepMe" in names and "IPC_Class3_AnnularRing_Via" not in names
    code, res = get(server, "/api/rules", lte)
    assert any(r["name"] == "IPC_Class3_AnnularRing_Via" for r in res["extra"])
    assert post(server, "/api/rules/extra/enabled", {"name": "nope", "enabled": True}, lte)[0] == 404

    # preset rules: off ones leave the .RUL and the diff, but stay in the preset list
    code, res = get(server, "/api/rules", lte)
    preset_names = [r["name"] for r in res["preset"]["rules"]]
    assert res["preset_off"] == [] and "Clearance" in preset_names
    code, res = post(server, "/api/rules/preset/enabled", {"name": "Clearance", "enabled": False}, lte)
    assert code == 200 and res["preset_off"] == ["Clearance"]
    code, res = get(server, "/api/rules", lte)
    assert "Clearance" in [r["name"] for r in res["preset"]["rules"]] and res["preset_off"] == ["Clearance"]
    assert "Clearance" not in [d["rule"] for d in res["diff"]]
    code, raw = get(server, "/api/rules/export", lte, raw=True)
    assert "Clearance" not in {r["NAME"] for r in read_rul_bytes(raw)}
    code, res = post(server, "/api/rules/preset/enabled", {"name": "Clearance", "enabled": True}, lte)
    assert res["preset_off"] == []
    assert post(server, "/api/rules/preset/enabled", {"name": "nope", "enabled": False}, lte)[0] == 404
