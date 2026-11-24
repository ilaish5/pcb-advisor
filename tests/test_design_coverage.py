"""E2E kiln E2: the LTE board came out with no SIM card. The modem's SIM pins were all NC and the SIM socket J3 sat in the BOM on no
sheet, and nothing said so. checks/coverage.py: interface pins on NC (one finding per part and interface) and Idea requirements
whose BOM parts are on no sheet; the student marks one "intended" with one click; the agent and the DFM page see the open ones."""
import json
import pathlib

import pytest

import agent
import model
import store
from checks import coverage
from test_chat_turns import call, server  # noqa: F401

REPO = pathlib.Path(__file__).resolve().parent.parent

MODEM_PINS = [("1", "VBAT", "+3V8"), ("2", "GND", "GND"), ("10", "VSIM", "NC"), ("11", "SIM_DAT", "NC"), ("12", "SIM_CLK", "NC"),
              ("13", "SIM_RST", "NC"), ("20", "TXD", "LTE_TX"), ("21", "RXD", "LTE_RX"), ("30", "ANT_MAIN", "RF_ANT"),
              ("40", "DBG_TXD", "NC"), ("41", "RFU", "NC")]


def _modem(pins=MODEM_PINS):
    return {"ref": "U6", "section": "A", "pins": [{"num": n, "name": a, "net": net} for n, a, net in pins]}


def _sheets(*parts):
    return [{"id": "03", "parts": list(parts)}]


BOM = [{"key": "U6", "refs": ["U6"], "value": "WH-LTE-7S1", "role": "LTE Cat-1 modem",
        "description": "LTE module; SIM slot and IPEX antenna on the module"},
       {"key": "J3", "refs": ["J3"], "value": "Nano-SIM socket", "role": "SIM card holder"},
       {"key": "U10", "refs": ["U10"], "value": "ESDA6V1", "role": "SIM line ESD"},
       {"key": "R22", "refs": ["R22", "R23", "R24"], "value": "22R", "role": "SIM series resistor"},
       {"key": "U3", "refs": ["U3"], "value": "MAX31855", "role": "Thermocouple amplifier"},
       {"key": "C29", "refs": ["C29"], "value": "33pF", "role": "SIM decoupling", "dnp": True}]
IDEA = {"goal": "Kiln controller with LTE reporting.",
        "agreed": [{"topic": "Connectivity", "text": "LTE Cat-1 modem with a nano-SIM card.", "status": "confirmed"},
                   {"topic": "Sensing", "text": "Type K thermocouple input.", "status": "confirmed"},
                   {"topic": "Case", "text": "Fits a DIN rail box.", "status": "confirmed"}]}


# ------------------------------------------------------------------ interface pins on NC

def test_all_sim_pins_nc_is_one_finding_naming_the_pins():
    found = coverage.interface_nc(_sheets(_modem()), BOM)
    assert [f["message"] for f in found] == ["U6 SIM interface not connected (VSIM, SIM_DAT, SIM_CLK, SIM_RST)"]
    assert found[0]["severity"] == "warning" and found[0]["refs"] == ["U6"] and found[0]["key"] == "interface_nc:U6:sim"


def test_wired_sim_and_debug_uart_and_rfu_raise_nothing():
    pins = [(n, a, "SIM_" + a if a.startswith(("VSIM", "SIM")) else net) for n, a, net in MODEM_PINS]
    assert coverage.interface_nc(_sheets(_modem(pins)), BOM) == []          # DBG_TXD and RFU on NC are fine


def test_one_pin_of_a_group_nc_is_info_only():
    pins = [("10", "VSIM", "VSIM"), ("11", "SIM_DAT", "SIM_DAT"), ("14", "SIM_DET", "NC")]
    [f] = coverage.interface_nc(_sheets(_modem(pins)), BOM)
    assert f["severity"] == "info" and "partly" in f["message"] and "SIM_DET" in f["message"]


@pytest.mark.parametrize("name,label", [("USB_DP", "USB"), ("USB_DM", "USB"), ("ANT", "antenna/RF"), ("RF_IN", "antenna/RF"),
                                        ("SWDIO", "SWD debug"), ("SWCLK", "SWD debug"), ("BOOT0", "BOOT0")])
def test_other_interfaces_on_nc(name, label):
    part = {"ref": "U1", "value": "STM32", "pins": [{"num": "1", "name": name, "net": "NC"}]}
    [f] = coverage.interface_nc(_sheets(part), [])
    assert f["message"] == f"U1 {label} interface not connected ({name})"


def test_uart_counts_only_on_a_modem():
    mcu = {"ref": "U1", "value": "STM32F103", "pins": [{"num": "1", "name": "TXD", "net": "NC"}]}
    assert coverage.interface_nc(_sheets(mcu), []) == []
    modem = _modem([("20", "TXD", "NC"), ("21", "RXD", "NC")])
    assert [f["message"] for f in coverage.interface_nc(_sheets(modem), BOM)] == ["U6 UART interface not connected (TXD, RXD)"]


def test_ordinary_pins_are_no_interface():
    for name in ("PA5", "GPIO3", "SIMO", "RFU", "ANTI", "NC", "RESET", "VDD"):
        assert coverage.interface_of(name, modem=True) is None, name


# ------------------------------------------------------------------ requirement coverage

def test_requirement_parts_on_no_sheet_is_a_finding():
    sheets = _sheets(_modem(), {"ref": "U3", "pins": [{"num": "1", "name": "T+", "net": "TC_P"}]})
    rows = coverage.requirement_coverage(IDEA, BOM, sheets)
    by = {r["keyword"]: r for r in rows}
    assert by["thermocouple"]["status"] == "covered" and by["thermocouple"]["on_sheet"] == ["U3"]
    assert by["sim"]["status"] == "missing" and by["sim"]["requirement"].lower() == "nano-sim"
    assert [p["refs"] for p in by["sim"]["missing_parts"]] == [["J3"], ["U10"], ["R22", "R23", "R24"]]     # C29 is DNP: not asked for
    [f] = coverage.coverage_findings(rows)
    assert f["message"] == ("Requirement 'nano-SIM': J3 (Nano-SIM socket), U10 (ESDA6V1), R22, R23, R24 (22R) "
                            "are in the BOM but on no sheet")


def test_single_part_message_and_no_invented_coverage():
    bom = [{"key": "J3", "refs": ["J3"], "value": "Nano-SIM socket", "role": "SIM card holder"}]
    [f] = coverage.coverage_findings(coverage.requirement_coverage(IDEA, bom, _sheets(_modem())))
    assert f["message"] == "Requirement 'nano-SIM': J3 (Nano-SIM socket) is in the BOM but on no sheet"
    # the case requirement matches no keyword; the thermocouple one has no BOM line here: neither gets a row
    assert {r["keyword"] for r in coverage.requirement_coverage(IDEA, bom, _sheets(_modem()))} == {"sim"}


def test_nothing_drawn_yet_says_nothing():
    assert coverage.requirement_coverage(IDEA, BOM, []) == []


# ------------------------------------------------------------------ the project: model, agent, one-click intended, pcb.py check

@pytest.fixture
def kiln(empty):
    for line in BOM:
        store.propose_bom(empty, line["key"], {k: v for k, v in line.items() if k != "key"}, new=True)
        store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    store.write_sheet(empty, "03", {"sections": [{"id": "A", "title": "LTE"}], "parts": [_modem()]})
    (store.pdir(empty) / "idea.json").write_text(json.dumps(IDEA), encoding="utf-8")
    return empty


def test_model_and_agent_see_both_findings(kiln):
    m = model.build(kiln)
    msgs = [f["message"] for f in m["design_findings"]["open"]]
    assert "U6 SIM interface not connected (VSIM, SIM_DAT, SIM_CLK, SIM_RST)" in msgs
    assert any(x.startswith("Requirement 'nano-SIM': J3 (Nano-SIM socket)") for x in msgs)
    s = json.loads(agent._summary(m))
    assert s["design_findings"] == msgs
    assert any(r["requirement"].lower() == "nano-sim" and "J3" in r["missing"] for r in s["requirement_coverage"])


def test_intended_is_one_click_and_comes_back_when_the_finding_changes(kiln, server):  # noqa: F811
    st, r = call(server, "POST", "/api/design-findings/intended", kiln, {"key": "interface_nc:U6:sim"})
    assert st == 200 and r["ok"]
    df = coverage.design_findings(kiln)
    assert [f["key"] for f in df["intended"]] == ["interface_nc:U6:sim"]
    assert "interface_nc:U6:sim" not in {f["key"] for f in df["open"]}
    told = json.loads(agent._summary(model.build(kiln))).get("design_findings", [])
    assert told and not any("SIM interface" in x for x in told)       # the agent no longer hears it; the J3 one stays
    sheet = store.load_sheet(kiln, "03")                                # another SIM pin goes NC: a new finding, shown again
    sheet["parts"][0]["pins"].append({"num": "14", "name": "SIM_DET", "net": "NC"})
    store.write_sheet(kiln, "03", sheet)
    assert "interface_nc:U6:sim" in {f["key"] for f in coverage.design_findings(kiln)["open"]}
    st, r = call(server, "POST", "/api/design-findings/intended", kiln, {"key": "no:such"})
    assert st == 400


def test_undo_shows_it_again(kiln):
    coverage.mark(kiln, "requirement_uncovered:sim")
    assert "requirement_uncovered:sim" not in {f["key"] for f in coverage.design_findings(kiln)["open"]}
    coverage.mark(kiln, "requirement_uncovered:sim", intended=False)
    assert "requirement_uncovered:sim" in {f["key"] for f in coverage.design_findings(kiln)["open"]}


def test_pcb_check_prints_the_findings_as_warnings(kiln, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pcb_cli", REPO / "pcb.py")
    pcb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pcb)
    pcb.cmd_check([kiln])
    out = capsys.readouterr().out
    assert "warn  empty: U6 SIM interface not connected" in out and "warn  empty: Requirement 'nano-SIM'" in out


def test_dfm_page_has_the_intended_button():
    js = (REPO / "ui/js/views/checks.js").read_text(encoding="utf-8")
    assert "dfmDesignHTML()" in js and "/api/design-findings/intended" in js and "act: 'design-intended'" in js
