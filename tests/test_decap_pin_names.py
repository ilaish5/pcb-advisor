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


def test_check_board_passes_the_datasheet_limit_and_pin_names_through():
    doc = h.decap_doc(h.cap("C1", 0, 0, "+3V3", "GND"), _numbered_ic("U1", 4.0, ["+3V3", "X", "GND"]))
    names = {"U1": {"1": "VDD", "2": "PA0", "3": "VSS"}}
    flagged = lambda **kw: [f for f in check_board(doc, outline_mm=[-5, -5, 40, 40], pin_names=names, **kw)["findings"]
                            if f["id"] == "decap_distance_excessive"]
    assert len(flagged()) == 1
    assert flagged(decap_limits={"U1": (5.0, "datasheet p.31")}) == []
