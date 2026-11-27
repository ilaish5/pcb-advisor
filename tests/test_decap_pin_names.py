"""R2 / W23: a supply pin is decided by its pin function name from the symbol or netlist, never by sitting on a power net.
PcbDoc pads are numbers, so the names come in as `pin_names[ref][pad number]`."""
import pathlib
import sys
import types

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from checks import board
from checks.board import check_board, check_decoupling_caps


def _comp(ref, x, y, pattern=""):
    return {"ref": ref, "pattern": pattern, "lib_ref": "", "x_mm": x, "y_mm": y, "rotation": 0.0}


def _pad(ref, name, x, y, net=None):
    return {"ref": ref, "name": name, "net": net, "x_mm": x, "y_mm": y}


def _cap(ref, x, y, net_a, net_b):
    return [_comp(ref, x, y, "C0603")], [_pad(ref, "1", x, y, net_a), _pad(ref, "2", x + 1.4, y, net_b)]


def _doc(*parts):
    return {"components": [c for cs, _ in parts for c in cs], "pads": [p for _, ps in parts for p in ps]}


h = types.SimpleNamespace(comp=_comp, pad=_pad, cap=_cap, decap_doc=_doc)


def _numbered_ic(ref, x, nets):
    pads_ = [h.pad(ref, str(i + 1), x + i, 0.0, n) for i, n in enumerate(nets)]
    return [h.comp(ref, x, 0.0, pattern="SOIC8")], pads_


def test_a_power_net_pad_that_is_not_a_supply_pin_is_not_flagged():
    flash = _numbered_ic("U4", 20.0, ["X", "X", "+3V3", "GND", "X", "X", "X", "+3V3"])
    sw = ([h.comp("SW2", 25.0, 0.0, pattern="SW_TACT")],
          [h.pad("SW2", "1", 25.0, 0.0, "+3V3"), h.pad("SW2", "2", 26.0, 0.0, "X"), h.pad("SW2", "3", 27.0, 0.0, "GND")])
    names = {"U4": {"1": "SCK", "2": "MISO", "3": "CS", "4": "GND", "5": "MOSI", "6": "NC", "7": "HOLD", "8": "VCC"}}
    doc = h.decap_doc(h.cap("C1", 0, 0, "+3V3", "GND"), flash, sw)
    found = check_decoupling_caps(doc, pin_names=names)
    assert [f["message"].split(" on net")[0] for f in found] == ["Supply pin U4-8"]


def test_pads_with_numbers_only_and_no_pin_names_are_listed_as_not_checked_never_guessed():
    flash = _numbered_ic("U4", 20.0, ["X", "X", "+3V3", "GND", "X", "X", "X", "+3V3"])
    found = check_decoupling_caps(h.decap_doc(h.cap("C1", 0, 0, "+3V3", "GND"), flash))
    assert [(f["id"], f["refs"]) for f in found] == [("decap_not_checked", ["U4"])]
    assert "not known which" in found[0]["message"]


def test_vdda_vref_names_with_a_slash_are_supply_pins():
    for name in ("VDDA/VREF+", "VDD", "VREF+", "VBAT"):
        q = {"ref": "U1", "name": "12", "pin_name": name}
        assert board._supply_pin(q, h.comp("U1", 0, 0, pattern="LQFP48"), [q, q, q], "+3V3") is True, name
    q = {"ref": "U1", "name": "5", "pin_name": "PA5"}
    assert board._supply_pin(q, h.comp("U1", 0, 0, pattern="LQFP48"), [q, q, q], "+3V3") is False


def test_an_output_pin_named_vout_is_not_a_supply_pin_but_vin_is():
    q = lambda name: {"ref": "U5", "name": "2", "pin_name": name}
    comp = h.comp("U5", 0, 0, pattern="SOT23-5")
    assert board._supply_pin(q("VOUT"), comp, [q("VOUT")] * 3, "+3V3") is False
    assert board._supply_pin(q("VIN"), comp, [q("VIN")] * 3, "+3V3") is True


def test_a_distance_just_over_the_limit_is_printed_over_it():
    for x in (3.02, 3.03, 3.004):
        doc = h.decap_doc(h.cap("C1", 0, 0, "+3V3", "GND"), _numbered_ic("U1", x - 1.0, ["+3V3", "X", "GND"]))
        f = check_decoupling_caps(doc, pin_names={"U1": {"1": "VDD", "2": "PA0", "3": "VSS"}}, limits={"U1": (3.0, "datasheet p.1")})
        msgs = [m["message"] for m in f if m["id"] == "decap_distance_excessive"]
        for msg in msgs:
            shown = float(msg.split("is ")[1].split(" mm")[0])
            assert shown > 3.0, msg


def test_check_board_passes_the_datasheet_limit_and_pin_names_through():
    doc = h.decap_doc(h.cap("C1", 0, 0, "+3V3", "GND"), _numbered_ic("U1", 4.0, ["+3V3", "X", "GND"]))
    names = {"U1": {"1": "VDD", "2": "PA0", "3": "VSS"}}
    flagged = lambda **kw: [f for f in check_board(doc, outline_mm=[-5, -5, 40, 40], pin_names=names, **kw)["findings"]
                            if f["id"] == "decap_distance_excessive"]
    assert len(flagged()) == 1
    assert flagged(decap_limits={"U1": (5.0, "datasheet p.31")}) == []


def _real_path_doc():
    """A board in PcbDoc form (numbers only) with a TF-card socket whose pattern says nothing about 'sd', a header, a switch and a flash."""
    tf = ([h.comp("J2", 20.0, 0.0, pattern="TF-SMD_TF-01A")],
          [h.pad("J2", str(i), 20.0 + i, 0.0, n) for i, n in enumerate(["X", "X", "X", "+3V3", "X", "X", "GND", "X"], 1)])
    hdr = ([h.comp("J5", 40.0, 0.0, pattern="HDR1X4")], [h.pad("J5", str(i), 40.0 + i, 0.0, n) for i, n in enumerate(["+3V3", "X", "X", "GND"], 1)])
    sw = ([h.comp("SW2", 30.0, 0.0, pattern="SW_TACT")], [h.pad("SW2", "1", 30.0, 0.0, "+3V3"), h.pad("SW2", "2", 31.0, 0.0, "X"), h.pad("SW2", "3", 32.0, 0.0, "GND")])
    return h.decap_doc(h.cap("C2", 0, 0, "+3V3", "GND"), tf, hdr, sw)


_SHEET = {"id": "01", "parts": [
    {"ref": "J2", "pins": [{"num": str(i), "name": n} for i, n in enumerate(["DAT2", "CD/DAT3", "CMD", "VDD", "CLK", "VSS", "DAT0", "DAT1"], 1)]},
    {"ref": "J5", "pins": [{"num": str(i), "name": n} for i, n in enumerate(["1", "2", "3", "4"], 1)]},
    {"ref": "SW2", "pins": [{"num": "1", "name": "A"}, {"num": "2", "name": "B"}, {"num": "3", "name": "C"}]}]}


def test_the_real_path_with_a_design_flags_the_tf_socket_by_its_pin_names_and_nothing_else():
    res = check_board(_real_path_doc(), outline_mm=[-5, -5, 60, 40], design=_SHEET)
    flagged = [f for f in res["findings"] if f["id"] == "decap_distance_excessive"]
    assert [f["refs"] for f in flagged] == [["C2", "J2"]] and "J2-4" in flagged[0]["message"]
    assert not [f for f in res["findings"] if f["id"] == "decap_not_checked" and "J2" in f["refs"]]


def test_a_decap_limits_file_with_its_cite_is_read_and_one_without_is_not(tmp_path):
    (tmp_path / "decap-limits.json").write_text('{"U1": [5.0, "datasheet p.31"], "U2": [9.0, ""]}', encoding="utf-8")
    assert board.design_decap_limits(tmp_path) == {"U1": (5.0, "datasheet p.31")}
    assert board.design_decap_limits(tmp_path / "nope") is None
