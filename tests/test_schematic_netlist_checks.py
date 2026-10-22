"""check_schematic on the tool's own netlist sheets (the sheet preview stage, before Altium)."""
import json
import subprocess
import sys

import store
from checks import schematic


def pin(num, name, net):
    return {"num": num, "name": name, "net": net}


def write(project, parts, sid="01"):
    sheet = {"sections": [{"id": "A", "title": "T"}], "parts": [{"section": "A", **p} for p in parts], "notes": []}
    assert store.write_sheet(project, sid, sheet)["ok"]


def ids(res, fid):
    return [f for f in res["findings"] if f["id"] == fid]


def driver(diode):
    parts = [
        {"ref": "Q1", "pins": [pin("1", "B", "CTRL"), pin("2", "E", "GND"), pin("3", "C", "BZ_LOW")]},
        {"ref": "BZ1", "pins": [pin("1", "+", "+5V"), pin("2", "-", "BZ_LOW")]},
    ]
    if diode:
        parts.append({"ref": "D1", "pins": [pin("1", "K", "+5V"), pin("2", "A", "BZ_LOW")]})
    return parts


def bz(empty, mpn, description):
    store.propose_bom(empty, "BZ1", {"mpn": mpn, "description": description, "refs": ["BZ1"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")


def test_open_ic_power_pin_is_found_from_project_name(empty):
    write(empty, [{"ref": "U1", "pins": [pin("1", "VDD", ""), pin("2", "GND", "GND"), pin("3", "NC", "NC")]},
                  {"ref": "C1", "pins": [pin("1", "1", "+3V3"), pin("2", "2", "GND")]}])
    res = schematic.check_schematic(empty)
    assert res["net_count"] > 0 and res["pin_count"] == 5
    found = ids(res, "unconnected_ic_power")
    assert found and found[0]["refs"] == ["U1"]
    assert "U1-3" in res["no_erc_pins"]
    assert not any("U1-3" in f["message"] for f in ids(res, "single_pin_net"))


def test_sheet_dict_and_folder_forms(empty):
    write(empty, [{"ref": "U1", "pins": [pin("1", "VDD", ""), pin("2", "GND", "GND")]}])
    sheet = store.load_sheet(empty, "01")
    assert ids(schematic.check_schematic(sheet), "unconnected_ic_power")
    assert ids(schematic.check_schematic(store.netlist_dir(empty)), "unconnected_ic_power")
    assert ids(schematic.check_schematic(store.netlist_dir(empty) / "01.json"), "unconnected_ic_power")


def test_collector_driving_buzzer_without_diode_warns(empty):
    bz(empty, "MLT-8530", "Magnetic buzzer 3V")
    write(empty, driver(False))
    found = ids(schematic.check_schematic(empty), "inductive_load_no_flyback")
    assert len(found) == 1 and found[0]["severity"] == "warning" and found[0]["refs"] == ["BZ1", "Q1"]
    assert "diode" in found[0]["message"] and "cathode" in found[0]["message"]


def test_diode_across_the_load_clears_it(empty):
    bz(empty, "MLT-8530", "Magnetic buzzer 3V")
    write(empty, driver(True))
    assert not ids(schematic.check_schematic(empty), "inductive_load_no_flyback")


def test_piezo_buzzer_is_skipped_and_unknown_is_info(empty):
    bz(empty, "PS1240", "Piezo buzzer")
    write(empty, driver(False))
    assert not ids(schematic.check_schematic(empty), "inductive_load_no_flyback")
    # no BOM text: unknown, so only an info
    found = ids(schematic.check_schematic({"parts": driver(False)}), "inductive_load_no_flyback")
    assert [f["severity"] for f in found] == ["info"]


def test_cli_takes_a_project_name(empty):
    write(empty, driver(False))
    out = subprocess.run([sys.executable, str(schematic.__file__), empty], capture_output=True, text=True, encoding="utf-8")
    assert json.loads(out.stdout)["net_count"] > 0


# ---------------------------------------------------------------------------
# Design intent against the board: the USB-LED case (R3 on the schematic had no pins, so the board lost V_LED and R3's 5V)
# ---------------------------------------------------------------------------
def usb_led_sheet():
    return {"id": "01", "sections": [{"id": "A", "title": "T"}], "notes": [], "parts": [
        {"ref": "J1", "section": "A", "kind": "conn", "pins": [
            pin("A4B9", "VBUS", "+5V"), pin("B4A9", "VBUS", "+5V"), pin("A1B12", "GND", "GND"),
            pin("A6", "DP1", "NC"), pin("A7", "DN1", "")]},
        {"ref": "R3", "section": "A", "kind": "passive", "pins": [pin("1", "1", "+5V"), pin("2", "2", "V_LED")]},
        {"ref": "D1", "section": "A", "kind": "led", "pins": [pin("1", "K", "GND"), pin("2", "A", "V_LED")]},
    ]}


def usb_led_board(connected):
    rows = [("J1", "A4B9", "+5V"), ("J1", "B4A9", "+5V"), ("J1", "A1B12", "GND"), ("J1", "A6", None), ("J1", "A7", None),
            ("D1", "1", "GND"), ("D1", "2", "V_LED"),
            ("R3", "1", "+5V" if connected else None), ("R3", "2", "V_LED" if connected else None)]
    return {"pads": [{"ref": r, "name": n, "net": net} for r, n, net in rows]}


def test_a_board_missing_the_led_connections_is_an_error_naming_the_net_and_pins():
    findings = schematic.design_vs_board([usb_led_sheet()], usb_led_board(False))
    errs = [f for f in findings if f["severity"] == "error"]
    text = " ".join(f["message"] for f in errs)
    assert {f["id"] for f in errs} == {"design_net_mismatch"}
    assert "V_LED" in text and "R3-1" in text and "R3-2" in text and "+5V" in text
    assert not [f for f in findings if "A6" in f["message"] or "A7" in f["message"]]      # NC / open pins are never flagged


def test_a_matching_board_has_no_findings_and_the_folder_forms_work(tmp_path):
    assert schematic.design_vs_board([usb_led_sheet()], usb_led_board(True)) == []
    proj = tmp_path / "USB-LED"
    (proj / "netlist").mkdir(parents=True)
    (proj / "netlist" / "01.json").write_text(json.dumps(usb_led_sheet()), encoding="utf-8")
    for source in (proj, proj / "netlist", proj / "netlist" / "01.json"):
        assert schematic.check_schematic(source)["net_count"] == 5
        assert schematic.design_vs_board(source, usb_led_board(True)) == []
        bad = schematic.check_schematic(source, board=usb_led_board(False))
        assert {f["id"] for f in bad["findings"] if f["severity"] == "error"} == {"design_net_mismatch"}


def test_missing_part_wrong_net_short_and_unknown_pin():
    board = usb_led_board(True)
    board["pads"] = [p for p in board["pads"] if p["ref"] != "D1"]
    ids_ = {f["id"]: f for f in schematic.design_vs_board([usb_led_sheet()], board)}
    assert ids_["design_part_missing"]["refs"] == ["D1"] and ids_["design_part_missing"]["severity"] == "error"
    board = usb_led_board(True)
    next(p for p in board["pads"] if (p["ref"], p["name"]) == ("R3", "2"))["net"] = "GND"        # V_LED pin on GND
    found = {f["id"]: f for f in schematic.design_vs_board([usb_led_sheet()], board)}
    assert "should be on 'V_LED' but is on 'GND'" in found["design_net_mismatch"]["message"]
    assert "design_nets_shorted" in found and "GND" in found["design_nets_shorted"]["message"]
    board = usb_led_board(True)
    next(p for p in board["pads"] if (p["ref"], p["name"]) == ("R3", "1"))["name"] = "P1"        # numbering that does not match
    unk = [f for f in schematic.design_vs_board([usb_led_sheet()], board) if f["id"] == "design_pin_unknown"]
    assert unk and unk[0]["severity"] == "warning" and "R3" in unk[0]["refs"] and "1" in unk[0]["message"]


def test_a_merged_pin_number_matches_its_split_pads():
    sheet = {"parts": [{"ref": "J1", "pins": [pin("A4B9", "VBUS", "+5V"), pin("B8", "X", "+5V")]}, {"ref": "J2", "pins": [pin("A4/B9", "V", "+5V"), pin("B8", "X", "+5V")]}]}
    board = {"pads": [{"ref": "J1", "name": "A4", "net": "+5V"}, {"ref": "J1", "name": "B9", "net": "+5V"},
                      {"ref": "J1", "name": "B8", "net": "+5V"}]}
    board["pads"] += [{"ref": "J2", "name": "A4B9", "net": "+5V"}, {"ref": "J2", "name": "B8", "net": "+5V"}]
    assert schematic.check_intent_vs_board([sheet], board) == []
