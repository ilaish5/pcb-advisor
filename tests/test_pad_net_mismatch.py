"""The built footprint's pads against the netlist, for every part (pin_model.pad_report): a pad with no net and no NC, and a netlist
pin naming a pad the footprint does not have, block the outputs and show on the Schematic page. E2E 25/11/2026 (USB-C + AMS1117 +
SHT31): the second VBUS / GND pads and the shell pads of the receptacle, the regulator's tab and the sensor's exposed pad reached the
board with no net, and nothing said so. The symbols here are GENERATED from the netlist (they cannot show a pad the netlist never
named), plus a sourced-symbol variant."""
import json
import pathlib

import pin_model
import stages
import store
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _add

REPO = pathlib.Path(__file__).resolve().parent.parent


def _pad(name, w=40, h=40, tht=False, plated=True):
    return f"PAD|{name}|0|0|0|{'Multi-Layer' if tht else 'Top Layer'}|{1 if plated else 0}|{30 if tht else 0}|0|0|0|{w}|{h}|1|"


def _library(empty, parts):
    """parts: {line key: (symbol, footprint, [pad lines], [(num, name)] symbol pins or None, source)} written as a built library."""
    lib = store.pdir(empty) / "library"
    (lib / "build").mkdir(parents=True, exist_ok=True)
    man, sym, fps = {}, [], ["FPLIB|<PCBLIB>"]
    for key, (symbol, footprint, pads, pins, source) in parts.items():
        man[key] = {"symbol": symbol, "footprint": footprint, "source": source}
        if source == "generated":
            man[key]["symbol_from"] = "netlist"
        sym += [f"SYMBOL|{symbol}"] + [f"PIN|{n}|{nm}|eElectricPassive|0|0|0|0|10" for n, nm in pins]
        fps += [f"FOOTPRINT|{footprint}|x"] + pads
    (lib / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (lib / "build" / "symbols_spec.txt").write_text("\n".join(sym) + "\n", encoding="cp1252")
    (lib / "build" / "footprints_spec.txt").write_text("\n".join(fps) + "\n", encoding="cp1252")


def _sheet(empty, parts):
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": ref, "section": "A", "pins": [{"num": n, "name": nm, "net": net} for n, nm, net in pins]} for ref, pins in parts.items()]})


def _pads(rep):
    return {(r["ref"], r["num"]): r for r in rep["unnetted"]}


# ---- the three E2E parts, each with a symbol generated from the netlist (pin_gaps cannot see what it was never given)

USBC_PADS = [_pad(n) for n in ("A4B9", "B4A9", "A1B12", "B1A12", "CC1", "CC2")] + [_pad(str(n), 60, 120, tht=True) for n in (1, 2, 3, 4)]
USBC_NETLIST = [("A4B9", "VBUS", "VBUS"), ("A1B12", "GND", "GND"), ("CC1", "CC1", "CC1"), ("CC2", "CC2", "CC2"), ("S1", "SHELL", "GND")]


def _usbc(empty, symbol_pins=None, source="generated"):
    _add(empty, "J1", "TYPE-C-31-M-12")
    _sheet(empty, {"J1": USBC_NETLIST})
    _library(empty, {"J1": ("SYM_J1", "USBC", USBC_PADS, symbol_pins if symbol_pins is not None else [(n, nm) for n, nm, _ in USBC_NETLIST], source)})


def test_usbc_second_vbus_second_gnd_and_shell_pads_block_and_s1_names_no_pad(empty):
    _usbc(empty)
    assert store.pin_gaps(empty) == {"open": [], "unlisted": []}            # the hole: nothing in the symbol-based check sees these
    rep = pin_model.pad_report(empty)
    pads = _pads(rep)
    assert set(pads) == {("J1", "B4A9"), ("J1", "B1A12"), ("J1", "1"), ("J1", "2"), ("J1", "3"), ("J1", "4")}
    assert pads["J1", "1"]["kind"] == "shell" and pads["J1", "4"]["kind"] == "shell"
    assert [(r["ref"], r["num"], r["net"]) for r in rep["nopad"]] == [("J1", "S1", "GND")]
    msg = store.manufacturing_warning(empty)
    assert msg.startswith("Not made yet") and "J1 pad B4A9" in msg and "J1 pad 1" in msg and "J1 pin S1 on net GND" in msg
    assert "footprint USBC has no such pad" in msg and "shell / mounting pad" in msg


def test_the_second_pad_of_a_twin_name_is_a_duplicate_with_its_twins_net(empty):
    _usbc(empty, symbol_pins=[("A4B9", "VBUS"), ("B4A9", "VBUS"), ("A1B12", "GND"), ("B1A12", "GND"), ("CC1", "CC1"), ("CC2", "CC2")])
    rep = _pads(pin_model.pad_report(empty))
    assert rep["J1", "B4A9"]["kind"] == "duplicate" and rep["J1", "B4A9"]["net"] == "VBUS"
    assert rep["J1", "B1A12"]["kind"] == "duplicate" and rep["J1", "B1A12"]["net"] == "GND"
    assert rep["J1", "B4A9"]["covered"] and rep["J1", "B4A9"]["wirable"]        # the symbol has the pin: pin_gaps lists it, counted once
    assert [(g["num"]) for g in store.pin_gaps(empty)["unlisted"]] == ["B4A9", "B1A12"]
    assert store.pad_gaps(empty)["pads"][0]["num"] == "1"                       # only what pin_gaps does not say is new
    text = pin_model.pad_text(pin_model.pad_report(empty))
    assert "pad B4A9" not in text and "J1 pad 1" in text


def test_ams1117_tab_pad_blocks_as_a_duplicate_of_vout(empty):
    _add(empty, "U1", "AMS1117-3.3")
    pads = [_pad("1"), _pad("2"), _pad("3"), _pad("4", 200, 100)]
    _sheet(empty, {"U1": [("1", "GND", "GND"), ("2", "VOUT", "+3V3"), ("3", "VIN", "+5V")]})
    _library(empty, {"U1": ("SYM_U1", "SOT223", pads, [("1", "GND"), ("2", "VOUT"), ("3", "VIN")], "generated")})
    assert store.pin_gaps(empty) == {"open": [], "unlisted": []}
    row = _pads(pin_model.pad_report(empty))["U1", "4"]
    assert row["kind"] == "thermal" and row["wirable"] and not row["covered"]       # a tab: big pad, nothing is named
    assert "U1 pad 4" in store.manufacturing_warning(empty)
    _library(empty, {"U1": ("SYM_U1", "SOT223", pads, [("1", "GND"), ("2", "VOUT"), ("3", "VIN"), ("4", "VOUT")], "easyeda")})
    row = _pads(pin_model.pad_report(empty))["U1", "4"]
    assert row["kind"] == "duplicate" and row["net"] == "+3V3" and row["covered"]    # a sourced symbol names the tab VOUT: the twin's net


def test_sht31_exposed_pad_blocks_and_an_nc_mark_clears_it(empty):
    _add(empty, "U2", "SHT31-DIS")
    pads = [_pad(str(n), 30, 60) for n in range(1, 9)] + [_pad("9", 160, 160)]
    pins = [(str(n), nm, net) for n, nm, net in zip(range(1, 9), ("SDA", "ADDR", "ALERT", "SCL", "VDD", "RESET", "NC", "VSS"),
                                                      ("SDA", "GND", "NC", "SCL", "+3V3", "+3V3", "NC", "GND"))]
    _sheet(empty, {"U2": pins})
    _library(empty, {"U2": ("SYM_U2", "DFN8", pads, [(n, nm) for n, nm, _ in pins], "generated")})
    row = _pads(pin_model.pad_report(empty))["U2", "9"]
    assert row["kind"] == "thermal" and row["net"] == ""
    assert "U2 pad 9" in store.manufacturing_warning(empty) and stages.sch_stage(empty, {"sheets": [{"id": "01"}], "sheet_gaps": {}})["state"] == "issues"
    res = store.mark_pins_nc(empty, [{"sheet": "01", "ref": "U2", "num": "9"}])         # the student's explicit choice
    assert res["marked"] == 1 and not pin_model.pad_report(empty)["unnetted"]
    assert "pad" not in store.manufacturing_warning(empty)
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]}["9"] == "NC"


# ---- what may and may not be swept up, and the resolutions

def test_mark_all_nc_never_takes_a_shell_exposed_or_duplicate_pad_and_a_net_can_be_set_instead(empty):
    _usbc(empty)
    store.write_sheet(empty, "01", {**store.load_sheet(empty, "01"), "parts": store.load_sheet(empty, "01")["parts"] + [
        {"ref": "R1", "section": "A", "pins": [{"num": "1", "name": "1", "net": "A"}, {"num": "2", "name": "2", "net": ""}]}]})
    _add(empty, "R1", "RC0603")
    assert store.mark_pins_nc(empty)["marked"] == 1                                  # R1 pin 2 (open) only; J1's pads are each a decision
    nets = {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]}
    assert "B4A9" not in nets and "1" not in nets
    for bad in ("Q_NOPE",):
        try:
            store.mark_pins_nc(empty, [{"sheet": "01", "ref": "J1", "num": "1"}], net=bad)
            raise AssertionError("an unknown net must be refused")
        except ValueError:
            pass
    try:
        store.mark_pins_nc(empty, None, net="GND")
        raise AssertionError("a net needs the pins listed")
    except ValueError:
        pass
    items = [{"sheet": "01", "ref": "J1", "num": n} for n in ("1", "2", "3", "4", "B1A12")]
    assert store.mark_pins_nc(empty, items, net="GND")["marked"] == 5
    assert store.mark_pins_nc(empty, [{"sheet": "01", "ref": "J1", "num": "B4A9"}], net="VBUS")["marked"] == 1
    assert not pin_model.pad_report(empty)["unnetted"]
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]}["B4A9"] == "VBUS"


def test_an_empty_name_pad_and_an_unplated_hole_are_ignored(empty):
    _add(empty, "U3", "ABCD1234")
    pads = [_pad("1"), _pad("2"), _pad("", tht=True), _pad("MH1", tht=True, plated=False)]
    _sheet(empty, {"U3": [("1", "A", "X"), ("2", "B", "Y")]})
    _library(empty, {"U3": ("SYM_U3", "FP3", pads, [("1", "A"), ("2", "B")], "generated")})
    assert pin_model.pad_report(empty) == {"unnetted": [], "nopad": []}


def test_nc_on_a_pad_the_footprint_lacks_touches_no_copper_but_a_wired_one_blocks(empty):
    _add(empty, "U3", "ABCD1234")
    _sheet(empty, {"U3": [("1", "A", "X"), ("2", "B", "NC"), ("7", "C", "NC"), ("8", "D", "Y")]})
    _library(empty, {"U3": ("SYM_U3", "FP3", [_pad("1"), _pad("2")], [("1", "A"), ("2", "B")], "generated")})
    rep = pin_model.pad_report(empty)
    assert [r["num"] for r in rep["nopad"]] == ["8"] and rep["unnetted"] == []


def test_a_part_with_pins_by_name_only_is_matched_to_the_symbol_not_flooded(empty):
    _add(empty, "U4", "ABCD1234")
    _sheet(empty, {"U4": [("", "VCC", "+3V3"), ("", "GND", "GND")]})
    _library(empty, {"U4": ("SYM_U4", "FP4", [_pad("1"), _pad("2")], [("1", "VCC"), ("2", "GND")], "easyeda")})
    assert pin_model.pad_report(empty) == {"unnetted": [], "nopad": []}


def test_dnp_lines_and_a_library_built_for_another_mpn_are_skipped(empty):
    _add(empty, "U3", "ABCD1234")
    _sheet(empty, {"U3": [("1", "A", "X"), ("2", "B", "Y")]})
    _library(empty, {"U3": ("SYM_U3", "FP3", [_pad("1"), _pad("2"), _pad("3")], [("1", "A"), ("2", "B")], "generated")})
    assert len(pin_model.pad_report(empty)["unnetted"]) == 1
    man = json.loads((store.pdir(empty) / "library" / "manifest.json").read_text())
    man["U3"]["mpn"] = "OLDER"
    (store.pdir(empty) / "library" / "manifest.json").write_text(json.dumps(man))
    assert pin_model.pad_report(empty)["unnetted"] == []


def test_a_symbol_without_the_pin_cannot_be_wired_and_says_so(empty):
    _add(empty, "U3", "ABCD1234")
    _sheet(empty, {"U3": [("1", "A", "X"), ("2", "B", "Y")]})
    _library(empty, {"U3": ("SYM_U3", "FP3", [_pad("1"), _pad("2"), _pad("3", 200, 100)], [("1", "A"), ("2", "B")], "easyeda")})
    row = pin_model.pad_report(empty)["unnetted"][0]
    assert not row["wirable"] and "cannot be wired" in pin_model.pad_text(pin_model.pad_report(empty))


# ---- the gate, the stage, the agent's writes

def test_the_gate_carries_the_pads_to_the_outputs_and_the_schematic_stage(empty):
    _usbc(empty)
    st = {s["id"]: s for s in stages.derive(empty, __import__("model").build(empty))[0]}
    assert st["outputs"]["state"] == "blocked" and st["outputs"]["gate"]["page"] == "sch"
    gaps = st["outputs"]["gate"]["gaps"]
    assert {i["num"] for i in gaps["pads"]} == {"B4A9", "B1A12", "1", "2", "3", "4"} and [i["num"] for i in gaps["nopad"]] == ["S1"]
    assert {i["kind"] for i in gaps["pads"]} == {"shell", ""} or {i["kind"] for i in gaps["pads"]} >= {"shell"}
    assert st["sch"]["state"] == "issues" and "footprint pads with no net" in st["sch"]["reason"] and "naming a pad" in st["sch"]["reason"]


def test_the_agent_cannot_clear_a_pad_with_nc_silently_and_the_write_says_what_is_open(empty):
    import serve
    _usbc(empty)
    data = store.load_sheet(empty, "01")
    data["parts"][0]["pins"] += [{"num": "B4A9", "name": "VBUS", "net": "NC"}]
    applied, _, refused = serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": data}], last_user="fix the sheet")
    assert not refused and "left open" in applied[0] and "BLOCKS THE OUTPUTS" in applied[0]
    assert "B4A9" not in {p["num"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]}
    assert ("J1", "B4A9") in {(i["ref"], i["num"]) for i in store.nc_proposal(empty)}
    assert store.approve_nc(empty)["marked"] >= 1                                       # the student's one click
    assert "pad B4A9" not in pin_model.pad_text(pin_model.pad_report(empty))


def test_the_agent_may_name_a_pad_a_generated_symbol_does_not_show_yet(empty):
    import serve
    _usbc(empty)
    data = store.load_sheet(empty, "01")
    data["parts"][0]["pins"] += [{"num": "B4A9", "name": "VBUS", "net": "VBUS"}]
    assert serve.netlist_symbol_errors(empty, data) == []                                # not "no pin in library symbol": the next build adds it
    assert serve.pad_note(empty).startswith(" BLOCKS THE OUTPUTS")


def test_nc_on_a_pad_a_sourced_symbol_lacks_is_no_draw_error():
    from altium import draw
    sym = {"name": "S", "pins": [{"number": "1", "name": "A"}, {"number": "2", "name": "B"}]}
    part = {"ref": "U1", "pins": [{"num": "1", "name": "A", "net": "X"}, {"num": "2", "name": "B", "net": "Y"}, {"num": "9", "name": "EP", "net": "NC"}]}
    _, warn, errors = draw.pin_nets(part, sym)
    assert errors == [] and any("pad 9 is marked NC" in w for w in warn)
    part["pins"][2]["net"] = "GND"
    assert draw.pin_nets(part, sym)[2]                                                    # a wired pad the symbol lacks stays an error


def test_the_api_sets_a_net_and_refuses_a_net_for_the_approve_route(empty, server):
    _usbc(empty)
    code, body = call(server, "POST", "/api/nc/mark", empty, {"items": [{"sheet": "01", "ref": "J1", "num": "1"}], "net": "GND"})
    assert code == 200 and body["marked"] == 1
    assert call(server, "POST", "/api/nc/approve", empty, {"net": "GND"})[0] == 400
    assert call(server, "POST", "/api/nc/mark", empty, {"net": "GND"})[0] == 400
    assert call(server, "POST", "/api/nc/mark", empty, {"items": [{"sheet": "01", "ref": "J1", "num": "2"}], "net": "NOT_A_NET"})[0] == 400


def test_the_page_offers_connect_buttons_and_leaves_the_risky_pads_out_of_mark_all():
    src = (REPO / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
    assert "OUT_RISKY" in src and "outBulkItems" in src and "'net-set-one'" in src and "Connect to " in src
    assert "i.gap !== 'nopad'" in src and "(gaps.pads || [])" in src and "(gaps.nopad || [])" in src
