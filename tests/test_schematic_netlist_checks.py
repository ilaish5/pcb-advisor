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
