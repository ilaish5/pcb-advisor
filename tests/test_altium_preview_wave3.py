"""Wave 3 stream 4: previews. A designator is drawn once on the PCB preview (10); a switch is drawn as a switch, and an
unknown "kind" falls back to the designator (11). Fakes only; nothing here needs Altium."""
import re

from scripts.preview_pcb import render_pcbdoc
from scripts.skills import render_sheet


def _doc(texts):
    comps = [{"ref": "R1", "x_mm": 10, "y_mm": 10, "rotation": 0.0, "layer": "TOP"},
             {"ref": "R2", "x_mm": 20, "y_mm": 10, "rotation": 0.0, "layer": "TOP"}]
    return {"components": comps, "pads": [], "tracks": [], "arcs": [], "texts": texts, "vias": [], "nets": [], "polygons": [],
            "regions": [], "fills": []}


def _labels(svg, ref):
    """Every text of the preview that reads `ref`."""
    return len(re.findall(rf">{ref}</text>", svg))


def test_a_designator_drawn_on_the_silkscreen_is_not_labelled_twice():
    silk = [{"layer": 33, "text": "R1", "x_mm": 10, "y_mm": 8, "height_mm": 1.0, "rotation": 0.0, "mirrored": False, "kind": "designator"}]
    svg = render_pcbdoc(_doc(silk))
    assert _labels(svg, "R1") == 1                      # the silk text only
    assert _labels(svg, "R2") == 1                      # R2's designator is hidden: the box keeps its own label


def test_with_no_silk_designator_the_box_label_is_kept():
    svg = render_pcbdoc(_doc([]))
    assert _labels(svg, "R1") == 1 and _labels(svg, "R2") == 1


def _part(ref, kind=None, pins=2):
    p = {"ref": ref, "section": "A", "pins": [{"name": str(i + 1), "num": str(i + 1), "net": "GND" if i else "BTN"} for i in range(pins)]}
    if kind:
        p["kind"] = kind
    return p


def test_a_switch_is_a_switch_whatever_the_agent_called_it():
    assert render_sheet.part_kind(_part("SW1")) == "switch"                       # by its designator
    for word in ("switch", "sw", "button", "SWITCH"):
        assert render_sheet.part_kind(_part("X9", word)) == "switch", word
    assert render_sheet.part_kind(_part("SW1", "conn")) == "conn"                 # an explicit known kind still wins
    assert render_sheet.part_kind(_part("R3", "wibble")) == "res"                 # an unknown word is no kind: the designator decides


def test_a_two_pin_switch_draws_its_contact_and_both_labels():
    svg, w, h = render_sheet.render_part(_part("SW1"), None, {"mpn": "TS-1187", "value": "TS-1187"})
    assert "SW1" in svg and "TS-1187" in svg and "<line" in svg and w > 0 and h > 0
    assert "BTN" in svg and "GND" in svg                                           # both nets are shown
