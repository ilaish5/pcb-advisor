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


# ---------------------------------------------------------------------------
# False positives found by running the checker on a finished, ECO'd project.
# Synthetic sheets (dict input): one test per cause that was fixed.
# ---------------------------------------------------------------------------
import json

from checks import schematic as sch_mod
from checks.schematic import (
    _board_findings,
    compare_with_board,
    net_scope_of,
    pin_hot_spot,
)


def _pin(number, name, x, y, orientation=0, length=10, **kw):
    return {"number": number, "name": name, "x": x, "y": y, "length": length,
            "orientation": orientation, "electrical": 4, **kw}


def _sheet(components, wires=(), labels=(), power=(), ports=(), junctions=(), no_erc=(), file="S.SchDoc"):
    """A SchDoc dict. ports: (name, x, y, {extra keys such as width})."""
    return {
        "file": file,
        "components": list(components),
        "wires": [{"points": list(w)} for w in wires],
        "net_labels": [{"text": t, "x": x, "y": y} for t, x, y in labels],
        "power_ports": [{"text": t, "x": x, "y": y} for t, x, y in power],
        "ports": [{"name": n, "x": x, "y": y, **extra} for n, x, y, extra in ports],
        "junctions": [{"x": x, "y": y} for x, y in junctions],
        "no_erc": [{"x": x, "y": y, "active": a} for x, y, a in no_erc],
    }


def _ids(res):
    return [f["id"] for f in res["findings"]]


def _together(res, *tags):
    pm = {t: n for n, ps in res["netlist"].items() for t in ps}
    return len({pm[t] for t in tags}) == 1


def test_pin_hot_spot_four_orientations():
    assert pin_hot_spot(_pin("1", "a", 100, 100, 0)) == (110, 100)
    assert pin_hot_spot(_pin("1", "a", 100, 100, 1)) == (100, 110)
    assert pin_hot_spot(_pin("1", "a", 100, 100, 2)) == (90, 100)
    assert pin_hot_spot(_pin("1", "a", 100, 100, 3)) == (100, 90)


def test_rotated_mirrored_component_pins_are_already_in_sheet_coordinates():
    """A component placed rotated/mirrored keeps its pin records in sheet coordinates with the pin
    direction already turned: the component's own orientation must not move the hot spots again."""
    u1 = {"ref": "U1", "orientation": 1, "mirrored": True, "x": 500, "y": 500,
          "pins": [_pin("1", "IN", 100, 100, 2), _pin("2", "OUT", 100, 80, 3)]}
    r1 = {"ref": "R1", "orientation": 3, "pins": [_pin("1", "1", 60, 100, 0), _pin("2", "2", 60, 60, 0)]}
    r2 = {"ref": "R2", "pins": [_pin("1", "1", 100, 50, 1)]}
    # U1-1 end (90,100) - R1-1 end (70,100); U1-2 end (100,70) - R2-1 end (100,60)
    res = check_schematic(_sheet([u1, r1, r2], wires=[[(70, 100), (90, 100)], [(100, 70), (100, 60)]]))
    assert _together(res, "U1-1", "R1-1")
    assert _together(res, "U1-2", "R2-1")
    assert not _together(res, "U1-1", "U1-2")


def test_wire_ending_inside_another_wire_is_a_t_connection():
    """A pin wired to the middle of another wire (T) is on that net, with or without a junction record."""
    comps = [{"ref": "R1", "pins": [_pin("1", "1", 0, 0, 2), _pin("2", "2", 110, 0, 0)]},
             {"ref": "R2", "pins": [_pin("1", "1", 50, 70, 3)]}]
    # R1-1 end (-10,0), R1-2 end (120,0), R2-1 end (50,60): wire A spans R1, wire B drops from A's middle
    res = check_schematic(_sheet(comps, wires=[[(-10, 0), (120, 0)], [(50, 0), (50, 60)]]))
    assert _together(res, "R1-1", "R1-2", "R2-1")
    res = check_schematic(_sheet(comps, wires=[[(-10, 0), (120, 0)], [(50, 0), (50, 60)]], junctions=[(50, 0)]))
    assert _together(res, "R1-1", "R1-2", "R2-1")


def test_crossing_wires_join_only_with_a_junction():
    comps = [{"ref": "R1", "pins": [_pin("1", "1", 0, 10, 2), _pin("2", "2", 110, 10, 0)]},
             {"ref": "R2", "pins": [_pin("1", "1", 50, 40, 3), _pin("2", "2", 50, -20, 1)]}]
    wires = [[(-10, 10), (120, 10)], [(50, 30), (50, -10)]]
    res = check_schematic(_sheet(comps, wires=wires))
    assert _together(res, "R1-1", "R1-2") and _together(res, "R2-1", "R2-2")
    assert not _together(res, "R1-1", "R2-1")
    res = check_schematic(_sheet(comps, wires=wires, junctions=[(50, 10)]))
    assert _together(res, "R1-1", "R1-2", "R2-1", "R2-2")


def test_a_point_on_several_wires_joins_all_of_them():
    """The old join stopped at the first wire a pin end touched."""
    comps = [{"ref": "R1", "pins": [_pin("1", "1", 20, 0, 2)]}, {"ref": "R2", "pins": [_pin("1", "1", 0, 0, 0)]},
             {"ref": "R3", "pins": [_pin("1", "1", 10, 100, 3)]}]
    # R1-1 and R2-1 both end at (10,0); wire X passes through that point, wire Y ends on X there
    wires = [[(0, 0), (30, 0)], [(10, 0), (10, 90)]]
    res = check_schematic(_sheet(comps, wires=wires))
    assert _together(res, "R1-1", "R2-1", "R3-1")


def test_power_port_and_net_label_directly_on_a_pin_end_without_wire():
    u1 = {"ref": "U1", "pins": [_pin("1", "VDD", 100, 100, 2), _pin("2", "OUT", 100, 80, 2)]}
    c1 = {"ref": "C1", "pins": [_pin("1", "1", 200, 100, 0), _pin("2", "2", 200, 60, 0)]}
    c2 = {"ref": "C2", "pins": [_pin("1", "1", 300, 80, 0)]}
    sheet = _sheet([u1, c1, c2], power=[("+3V3", 90, 100), ("+3V3", 210, 100), ("GND", 210, 60)],
                   labels=[("OUT", 90, 80), ("OUT", 310, 80)])
    res = check_schematic(sheet)
    assert res["netlist"]["+3V3"] == ["C1-1", "U1-1"]
    assert res["netlist"]["OUT"] == ["C2-1", "U1-2"]
    assert "unconnected_ic_power" not in _ids(res)
    # C1-2 sits alone on GND (only one pin in this tiny sheet): the only single-pin finding
    singles = [f for f in res["findings"] if f["id"] == "single_pin_net"]
    assert [f["refs"] for f in singles] == [["C1"]]


def test_stacked_pins_at_one_hot_spot_share_a_net():
    u1 = {"ref": "U1", "pins": [_pin("1", "GND", 100, 100, 2), _pin("2", "GND", 100, 100, 2)]}
    c1 = {"ref": "C1", "pins": [_pin("1", "1", 0, 100, 0)]}
    res = check_schematic(_sheet([u1, c1], wires=[[(10, 100), (90, 100)]], power=[("GND", 50, 100)]))
    assert res["netlist"] == {"GND": ["C1-1", "U1-1", "U1-2"]}
    assert "pin_net_mismatch" not in _ids(res)


def test_only_the_placed_part_of_a_multipart_component_exists():
    u1 = {"ref": "U1", "part_count": 3, "current_part_id": 1,
          "pins": [_pin("1", "A", 100, 100, 2, part_id=1), _pin("9", "B", 100, 100, 2, part_id=2)]}
    res = check_schematic(_sheet([u1], wires=[[(90, 100), (50, 100)]], labels=[("X", 60, 100)]))
    assert res["pin_count"] == 1 and res["netlist"] == {"X": ["U1-1"]}


def test_hidden_power_pin_joins_the_net_named_like_the_pin():
    u1 = {"ref": "U1", "pins": [_pin("14", "VCC", 100, 100, 2, hidden=True, electrical=7)]}
    c1 = {"ref": "C1", "pins": [_pin("1", "1", 0, 100, 0)]}
    res = check_schematic(_sheet([u1, c1], wires=[[(10, 100), (50, 100)]], power=[("VCC", 50, 100)]))
    assert res["netlist"] == {"VCC": ["C1-1", "U1-14"]}
    assert "unconnected_ic_power" not in _ids(res)
    # with no power port anywhere the hidden pin still reaches its named net
    res = check_schematic(_sheet([u1]))
    assert res["netlist"] == {"VCC": ["U1-14"]}


def test_near_integer_coordinates_snap_to_the_grid():
    """Altium writes 129 + 0.9921 for a point it means as 130."""
    u1 = {"ref": "U1", "pins": [_pin("1", "IN", 100, 100, 2)]}
    r1 = {"ref": "R1", "pins": [_pin("1", "1", 0, 100, 0)]}
    res = check_schematic(_sheet([u1, r1], wires=[[(10.0, 100.008), (89.9921, 100)]]))
    assert _together(res, "U1-1", "R1-1")


def test_no_erc_pin_is_one_info_not_a_single_pin_warning_per_pin():
    u1 = {"ref": "U1", "pins": [_pin(str(i), f"IO{i}", 100, 100 - 10 * i, 0) for i in range(1, 6)]}
    # IO1, IO2, IO3 marked (IO2 twice, as in a real sheet); IO4's marker is disabled; IO5 has none
    marks = [(110, 90, True), (110, 80, True), (110, 80, True), (110, 70, True), (110, 60, False)]
    res = check_schematic(_sheet([u1], no_erc=marks))
    singles = " ".join(f["evidence"] for f in res["findings"] if f["id"] == "single_pin_net")
    assert "U1-4" in singles and "U1-5" in singles and "U1-1" not in singles and "U1-3" not in singles
    assert _ids(res).count("single_pin_net") == 2
    info = [f for f in res["findings"] if f["id"] == "no_erc_unused_pins"]
    assert len(info) == 1 and info[0]["severity"] == "info"
    assert "3 unused pin" in info[0]["message"]
    assert res["no_erc_pins"] == ["U1-1", "U1-2", "U1-3"]


def test_no_erc_on_an_unconnected_power_pin_is_not_an_error():
    u1 = {"ref": "U1", "pins": [_pin("1", "VDD", 100, 100, 0), _pin("2", "GND", 100, 90, 0)]}
    res = check_schematic(_sheet([u1], no_erc=[(110, 100, True)]))
    msgs = [f["message"] for f in res["findings"] if f["id"] == "unconnected_ic_power"]
    assert len(msgs) == 1 and "GND" in msgs[0]  # the unmarked pin is still reported, the marked VDD is not


def test_unconnected_pin_is_not_a_ground_mismatch():
    u1 = {"ref": "U1", "pins": [_pin("1", "GND", 100, 100, 0)]}
    res = check_schematic(_sheet([u1]))
    assert "pin_net_mismatch" not in _ids(res)
    assert "single_pin_net" in _ids(res)


def test_label_used_to_name_a_net_inside_a_sheet_is_not_reported():
    r1 = {"ref": "R1", "pins": [_pin("1", "1", 0, 0, 0), _pin("2", "2", 100, 0, 2)]}
    r2 = {"ref": "R2", "pins": [_pin("1", "1", 0, 50, 0), _pin("2", "2", 100, 50, 2)]}
    wires = [[(10, 0), (90, 0)], [(10, 50), (90, 50)]]
    # SW names a 2-pin net once; BST appears twice on two wires (same net by name)
    res = check_schematic(_sheet([r1, r2], wires=wires, labels=[("SW", 50, 0), ("BST", 20, 50), ("BST", 70, 50)]))
    assert "net_only_by_label_on_one_sheet" not in _ids(res)
    assert sorted(res["netlist"]) == ["BST", "SW"]


def test_lonely_label_that_connects_nothing_is_reported():
    r1 = {"ref": "R1", "pins": [_pin("1", "1", 0, 0, 0)]}
    res = check_schematic(_sheet([r1], wires=[[(10, 0), (60, 0)]], labels=[("LONELY", 40, 0), ("FLOAT", 300, 300)]))
    infos = [f for f in res["findings"] if f["id"] == "net_only_by_label_on_one_sheet"]
    msgs = " ".join(f["message"] for f in infos)
    assert "LONELY" in msgs and "FLOAT" in msgs and len(infos) == 2
    assert all(f["severity"] == "info" for f in infos)


def test_label_with_a_partner_on_another_sheet_connects_the_sheets():
    a = _sheet([{"ref": "R1", "pins": [_pin("1", "1", 0, 0, 0)]}], wires=[[(10, 0), (60, 0)]],
               labels=[("SIG", 40, 0)], file="A.SchDoc")
    b = _sheet([{"ref": "R2", "pins": [_pin("1", "1", 0, 0, 0)]}], wires=[[(10, 0), (60, 0)]],
               labels=[("SIG", 40, 0)], file="B.SchDoc")
    res = check_schematic([a, b])
    assert res["netlist"]["SIG"] == ["R1-1", "R2-1"]
    assert "net_only_by_label_on_one_sheet" not in _ids(res) and "single_pin_net" not in _ids(res)


def test_port_without_partner_on_another_sheet_is_reported_only_in_a_multisheet_project():
    def sh(name, port):
        return _sheet([{"ref": name[0] + "1", "pins": [_pin("1", "1", 0, 0, 0), _pin("2", "2", 100, 0, 2)]}],
                      wires=[[(10, 0), (90, 0)]], ports=[(port, 40, 0, {"width": 0})], file=name)
    res = check_schematic([sh("A.SchDoc", "TXD"), sh("B.SchDoc", "TXD")])
    assert "net_only_by_label_on_one_sheet" not in _ids(res)
    res = check_schematic([sh("A.SchDoc", "TXD"), sh("B.SchDoc", "ORPHAN")])
    msgs = [f["message"] for f in res["findings"] if f["id"] == "net_only_by_label_on_one_sheet"]
    assert len(msgs) == 2 and any("ORPHAN" in m for m in msgs)
    assert "net_only_by_label_on_one_sheet" not in _ids(check_schematic(sh("A.SchDoc", "TXD")))


def test_port_joins_the_wires_at_both_ends():
    comps = [{"ref": "R1", "pins": [_pin("1", "1", 0, 0, 0)]}, {"ref": "R2", "pins": [_pin("1", "1", 300, 0, 2)]}]
    sheet = _sheet(comps, wires=[[(10, 0), (30, 0)], [(290, 0), (270, 0)]], ports=[("BUS", 30, 0, {"width": 240})])
    res = check_schematic(sheet)
    assert res["netlist"]["BUS"] == ["R1-1", "R2-1"]


def test_unannotated_parts_do_not_share_pin_tags():
    def mk(y):
        return {"ref": "R?", "pins": [_pin("1", "1", 0, y, 0), _pin("2", "2", 100, y, 2)]}
    res = check_schematic(_sheet([mk(0), mk(50)], wires=[[(10, 0), (90, 0)], [(10, 50), (90, 50)]]))
    assert res["pin_count"] == 4 and len(res["netlist"]) == 2
    assert "unannotated_components" in _ids(res)


def test_net_scope_from_project_and_sheet_symbols():
    plain = {"record_counts": {"27": 3}}
    with_symbols = {"record_counts": {"15": 2}}
    assert net_scope_of(None, [plain]) == "global"
    assert net_scope_of({"settings": {}}, [plain, with_symbols]) == "sheet"
    assert net_scope_of({"settings": {"NETIDENTIFIERSCOPE": "Global"}}, [with_symbols]) == "global"
    assert net_scope_of({"settings": {"NETIDENTIFIERSCOPE": "Hierarchical"}}, [plain]) == "sheet"


def test_local_net_labels_stay_on_their_sheet():
    def sh(name, ref):
        return _sheet([{"ref": ref, "pins": [_pin("1", "1", 0, 0, 0)]}], wires=[[(10, 0), (60, 0)]],
                      labels=[("SIG", 40, 0)], file=name)
    docs = [sh("A.SchDoc", "R1"), sh("B.SchDoc", "R2")]
    assert sch_mod.build_multisheet_schdoc_netlist(docs, "global")["nets"] == {"SIG": ["R1-1", "R2-1"]}
    assert sorted(sch_mod.build_multisheet_schdoc_netlist(docs, "sheet")["nets"]) == ["SIG", "SIG@B.SchDoc"]


# ---------------------------------------------------------------------------
# compare_with_board
# ---------------------------------------------------------------------------
def _pads(*rows):
    return {"pads": [{"ref": r, "name": n, "net": net} for r, n, net in rows]}


def test_compare_with_board_reports_connectivity_differences_not_names():
    sch = {"nets": {"GND": ["C1-2", "U1-1", "U1-2"], "SIG": ["R1-1", "U1-4"], "NetU1_3": ["U1-3"],
                    "NetR1_2": ["R1-2"], "ONLYSCH": ["J1-1"]}}
    pcb = _pads(("C1", "2", "GND"), ("U1", "1", "GND"), ("U1", "2", None),      # U1-2 open on the board
                ("R1", "1", "SIG"), ("U1", "4", "SIG"), ("U1", "3", "SIG"),    # U1-3 joined to SIG on the board
                ("R1", "2", "N_7"),                                              # renamed auto net: same group
                ("Z1", "1", "X"), (None, "1", "GND"))                            # board only; pad without ref
    cmp = compare_with_board(sch, pcb)
    kinds = {m["pin"]: m["kind"] for m in cmp["mismatches"]}
    assert kinds == {"U1-2": "unconnected_in_board", "U1-3": "unconnected_in_schematic",
                     "C1-2": "different_nets", "U1-1": "different_nets",   # lost their GND peer U1-2
                     "R1-1": "different_nets", "U1-4": "different_nets"}   # gained the peer U1-3
    assert "R1-2" not in kinds                                            # renamed net, same group
    assert cmp["only_in_schematic"] == ["J1-1"] and cmp["only_in_board"] == ["Z1-1"]
    assert cmp["compared_pins"] == 7 and cmp["matching_pins"] == 1
    u13 = next(m for m in cmp["mismatches"] if m["pin"] == "U1-3")
    assert u13["together_in_board_only"] == ["R1-1", "U1-4"] and u13["board_net"] == "SIG"


def test_compare_with_board_identical_connectivity_has_no_mismatch():
    sch = {"nets": {"GND": ["C1-2", "U1-1"], "NetU1_3": ["U1-3"]}}
    cmp = compare_with_board(sch, _pads(("C1", "2", "GND"), ("U1", "1", "GND"), ("U1", "3", None)))
    assert cmp["mismatches"] == [] and cmp["matching_pins"] == 3


def test_check_schematic_with_board_adds_findings_and_json_keys():
    u1 = {"ref": "U1", "pins": [_pin("1", "GND", 100, 100, 2), _pin("2", "IN", 100, 90, 2)]}
    c1 = {"ref": "C1", "pins": [_pin("1", "1", 0, 100, 0), _pin("2", "2", 0, 90, 0)]}
    sheet = _sheet([u1, c1], wires=[[(10, 100), (90, 100)]], power=[("GND", 50, 100)])
    # board: U1-1 ok, C1-1 is not on GND, U1-2 and C1-2 are joined (the schematic leaves both open)
    board = _pads(("U1", "1", "GND"), ("C1", "1", "VCC"), ("U1", "2", "N1"), ("C1", "2", "N1"))
    res = check_schematic(sheet, board=board)
    errs = [f for f in res["findings"] if f["id"] == "board_netlist_mismatch"]
    assert errs and all(f["severity"] == "error" for f in errs)
    assert {m["pin"] for m in res["board_mismatches"]} == {"C1-1", "U1-2", "C1-2", "U1-1"}
    json.dumps(res)  # all of it is JSON
    clean = check_schematic(sheet, board=_pads(("U1", "1", "GND"), ("C1", "1", "GND"),
                                               ("U1", "2", "A"), ("C1", "2", "B")))
    assert clean["board_mismatches"] == [] and "board_netlist_mismatch" not in _ids(clean)
    assert check_schematic(sheet)["board_mismatches"] == []
    assert _board_findings({"mismatches": []}) == []


def test_board_pins_missing_is_reported():
    sheet = _sheet([{"ref": "U1", "pins": [_pin("1", "A", 0, 0, 0), _pin("2", "B", 0, 10, 0)]}])
    res = check_schematic(sheet, board=_pads(("U1", "1", None)))
    miss = [f for f in res["findings"] if f["id"] == "board_pins_missing"]
    assert len(miss) == 1 and "1 schematic pin" in miss[0]["message"]


def test_project_source_forms_agree():
    """Folder and .PrjPcb of the same project give the same netlist."""
    by_folder = check_schematic(PROJECT)
    by_prj = check_schematic(PROJECT / "WCTopping.PrjPcb")
    assert by_prj["netlist"] == by_folder["netlist"] and by_prj["net_count"] > 0
    assert by_prj["net_scope"] == "global"


def test_cli_board_option_prints_board_mismatches(capsys):
    sch_mod.main([str(PROJECT), "--board", str(FIXTURES / "finished-board.PcbDoc")])
    out = json.loads(capsys.readouterr().out)
    assert isinstance(out["board_mismatches"], list)
    assert "compared_pins" in out["board_compare"]


def test_real_finished_project_matches_its_board():
    """A finished real project (a private folder, never copied into this repo; set PCB_ADVISOR_REAL_PROJECT):
    the netlist built from its sheets has the connectivity of the PcbDoc that ECO made from them,
    and the only finding is the No ERC count. Skipped when the variable is not set."""
    import os
    env = os.environ.get("PCB_ADVISOR_REAL_PROJECT")
    proj = pathlib.Path(env) if env else None
    boards = sorted(proj.glob("*.PcbDoc")) if proj and proj.is_dir() else []
    if not boards:
        pytest.skip("real project not available (set PCB_ADVISOR_REAL_PROJECT)")
    board = boards[0]
    res = check_schematic(proj, board=board)
    assert res["board_mismatches"] == []
    assert res["board_compare"]["compared_pins"] > 500
    assert {f["id"] for f in res["findings"]} <= {"no_erc_unused_pins"}
