"""Bugs found by the first live run on a new STM32 project: a stop word inside a sentence, duplicate pin names, `pcb.py show`,
the DRC list of the route step, the silk the library generator draws, footprint findings, section names, stale empty sheets."""
import importlib.util
import pathlib

import pytest

import project as project_mod  # noqa: F401
import serve
from altium import draw
from checks import board
from test_altium_draw import drawn, SHEET, SYMS  # noqa: F401  (drawn: the fixture)

REPO = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- 1. stop words

def test_a_no_inside_a_sentence_is_not_a_stop():
    msg = ("Split the netlist into two sheets as the tool says, and arrange the parts so that no signal net runs between the two "
           "sheets (only 3V3, 5V and GND may be on both). Then draw both sheets in Altium.")
    assert not serve._STOP_ANY.search(msg)
    assert not serve._STOP_ANY.search("There is no way around it, draw it")
    assert not serve._STOP_ANY.search("אין שום בעיה, תצייר את שני הגיליונות")


@pytest.mark.parametrize("msg", ["no", "No.", "nope", "no, wait", "No thanks", "wait", "stop please", "not yet", "לא", "לא עכשיו", "חכה",
                                 "עצור", "אל תצייר עכשיו", "ok but don't draw yet", "never mind, I'll do it myself", "cancel"])
def test_real_stops_still_stop(msg):
    assert serve._STOP_ANY.search(msg)


# ---------------------------------------------------------------- 2. duplicate pin names

def _usbc():
    nums = [("A1B12", "GND"), ("A4B9", "VBUS"), ("A5", "CC1"), ("B4A9", "VBUS"), ("B1A12", "GND"),
            ("1", "SHELL"), ("2", "SHELL"), ("3", "SHELL"), ("4", "SHELL")]
    return {"name": "USBC", "pins": [{"number": n, "name": nm} for n, nm in nums]}


def _part(pins):
    return {"ref": "J1", "pins": [{"name": n, "net": net} for n, net in pins]}


def test_a_net_on_a_duplicated_pin_name_connects_every_pin_of_that_name():
    part = _part([("GND", "GND"), ("VBUS", "VBUS"), ("CC1", "CC1_NET"), ("SHELL", "GND")])
    why = []
    assert serve._renumber_by_name(part, _usbc(), why) and not why
    by = {p["num"]: p["net"] for p in part["pins"]}
    assert by == {"A1B12": "GND", "B1A12": "GND", "A4B9": "VBUS", "B4A9": "VBUS", "A5": "CC1_NET",
                  "1": "GND", "2": "GND", "3": "GND", "4": "GND"}
    assert draw.pin_nets(part, _usbc())[2] == []


def test_the_same_name_listed_twice_with_the_same_net_is_one_node():
    part = _part([("GND", "GND"), ("GND", "GND"), ("VBUS", "VBUS"), ("CC1", "X"), ("SHELL", "GND")])
    assert serve._renumber_by_name(part, _usbc())
    assert len(part["pins"]) == 9


def test_a_duplicated_name_with_different_nets_is_refused_with_the_real_cause_and_nothing_is_wired():
    part = _part([("GND", "GND"), ("GND", "AGND"), ("VBUS", "VBUS"), ("CC1", "X"), ("SHELL", "GND")])
    before = [dict(p) for p in part["pins"]]
    why = []
    assert not serve._renumber_by_name(part, _usbc(), why)
    assert part["pins"] == before
    assert why and "GND" in why[0] and "different nets" in why[0] and "pin numbers" in why[0]


def test_more_listings_than_pins_and_unknown_names_are_refused_with_a_reason():
    for pins, word in (([("CC1", "X"), ("CC1", "X")], "only 1"), ([("FOO", "X")], "not a pin")):
        part = _part(pins)
        why = []
        assert not serve._renumber_by_name(part, _usbc(), why)
        assert word in why[0]


def test_an_unnumbered_pin_is_not_blamed_with_an_empty_number():
    errs = draw.pin_nets(_part([("DN2", "USB_DN")]), _usbc())[2]
    assert errs and "has no pin number" in errs[0] and "DN2" in errs[0] and "netlist pin  (" not in errs[0]


# ---------------------------------------------------------------- 3. pcb.py show

def test_pcb_show_survives_a_model_without_requirements_or_totals():
    spec = importlib.util.spec_from_file_location("pcb_cli", REPO / "pcb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.show_lines({"project": "P", "idea": {}, "sheets": []})
    assert lines[0].startswith("P: idea open") and len(lines) == 2
    lines = mod.show_lines({"project": "P", "idea": {"requirements": [{"text": "r1", "ok": True}, "junk", {"ok": None}]},
                            "proposals": [{"status": "pending"}], "totals": {"lines": 2, "cost": 1.5}})
    assert any("r1" in ln for ln in lines) and any("PENDING" in ln for ln in lines)


# ---------------------------------------------------------------- 4. the whole DRC list reaches the student

def test_route_summary_carries_every_drc_rule_not_the_watched_six():
    line = "Clearance 0, Un-Routed Net 16, Minimum Solder Mask Sliver 68, Silk To Solder Mask 218, total 316"
    res = {"summary": "42 nets routed, saved; own check: no open nets", "drc_line": line, "warnings": []}
    s = serve.route_summary(res)
    assert line in s
    res["summary"] = f"42 nets routed; Altium DRC: {line}"
    assert serve.route_summary(res).count(line) == 1


# ---------------------------------------------------------------- 5. silk, mask, annular ring

def test_silk_clip_distance_is_mask_expansion_plus_the_silk_to_mask_rule():
    import partlib_convert as conv
    import partlib_generate as gen
    assert conv.SILK_TO_COPPER_MIL == pytest.approx(8.0)
    # a vendor silk line 6 mil from the copper edge is cut away (it would be 4 mil from the mask opening, rule 6)
    lines = ["PAD|1|0|0|0|Top Layer|1|0|0|0|0|40|40|2|", "TRACK|-15|29|15|29|6.0|Top Overlay"]      # copper edge y=20, silk edge 29-3=26: 6 mil
    assert not [ln for ln in conv.clip_silk(lines) if ln.endswith("Top Overlay")]
    ok = ["PAD|1|0|0|0|Top Layer|1|0|0|0|0|40|40|2|", "TRACK|-100|32|100|32|6.0|Top Overlay"]       # silk edge 29: 9 mil
    assert [ln for ln in conv.clip_silk(ok) if ln.endswith("Top Overlay")] == [ok[1]]
    assert gen.CLEAR * conv.MM >= conv.SILK_TO_COPPER_MIL + 3          # generated footprints keep the same distance (centre = edge + half width)


def test_footprint_findings_name_the_part_and_a_way_forward():
    rules = [{"RULEKIND": "MinimumAnnularRing", "SCOPE1EXPRESSION": "IsPad", "MINIMUMRING": "10mil", "ENABLED": "TRUE"},
             {"RULEKIND": "SolderMaskExpansion", "SCOPE1EXPRESSION": "All", "EXPANSION": "2mil", "ENABLED": "TRUE"},
             {"RULEKIND": "MinimumSolderMaskSliver", "SCOPE1EXPRESSION": "All", "MINSOLDERMASKWIDTH": "6mil", "ENABLED": "TRUE"}]
    # two 0.3 mm wide pads on a 0.5 mm pitch (gap 0.2 mm, dam 0.098 mm), and a shell pad with a 0.2 mm ring
    pads = [{"ref": "J1", "name": str(i), "layer": 1, "x_mm": i * 0.5, "y_mm": 0, "sx_mm": 0.3, "sy_mm": 1.0, "rot": 0.0} for i in (1, 2)]
    doc = {"rules": rules, "pads": pads,
           "drilled_pads": [{"ref": "J1", "name": "S1", "hole_mm": 0.6, "min_size_mm": 1.0, "plated": True}]}
    found = {f["id"]: f for f in board.check_footprint_rules(doc)}
    assert set(found) == {"footprint_ring_below_rule", "footprint_mask_sliver"}
    assert "J1" in found["footprint_ring_below_rule"]["message"] and "Way forward" in found["footprint_ring_below_rule"]["message"]
    assert "0.098" in found["footprint_mask_sliver"]["message"] and "JLC's 0.1" in found["footprint_mask_sliver"]["message"]
    # a pad pair far enough apart, a ring big enough, a board without the rules: nothing
    ok = {"rules": rules, "pads": [{**p, "x_mm": p["x_mm"] * 3} for p in pads],
          "drilled_pads": [{"ref": "J1", "name": "S1", "hole_mm": 0.6, "min_size_mm": 1.2, "plated": True}]}
    assert board.check_footprint_rules(ok) == []
    assert board.check_footprint_rules({"pads": pads, "drilled_pads": doc["drilled_pads"]}) == []


# ---------------------------------------------------------------- 6. section names in the split message

def test_the_split_message_shows_section_titles_and_parts_not_the_internal_letters():
    from test_altium_draw import _big
    sheet = _big()
    sheet["sections"][0]["title"] = "Power supply"
    p = draw.plan_sheet(sheet, {x["ref"]: SYMS["R1"] for x in sheet["parts"]}, "l", "d")
    msg = p["errors"][0]
    assert "sheet 1: Power supply (" in msg and "sheet 1: A," not in msg


