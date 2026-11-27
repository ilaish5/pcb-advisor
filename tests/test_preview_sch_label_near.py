"""R2 / F-F: a designator stored far from its part is drawn beside the part; one stored near it stays where Altium put it."""
import re

import preview_sch as ps


def _svg(des_xy):
    own_pins = [{"number": "1", "name": "A", "x": 770, "y": 900, "length": 30, "orientation": 2, "hidden": False,
                 "show_name": True, "show_number": True, "part_id": 1}]
    comp = {"ref": "U7", "comment": "X", "x": 770, "y": 900, "current_part_id": 1, "pins": own_pins,
            "graphics": [{"kind": "rect", "part_id": 1, "x1": 770, "y1": 880, "x2": 850, "y2": 920, "solid": True}],
            "designator_text": {"text": "U7", "x": des_xy[0], "y": des_xy[1], "justification": 0, "orientation": 0, "font": 1, "hidden": False}}
    b = ps._Bounds()
    return ps._part_svg(comp, {}, 1, b)


def _label_xy(svg):
    m = re.search(r'<text[^>]*class="refd"[^>]*>', svg) or re.search(r'<text[^>]*refd[^>]*>', svg)
    x = float(re.search(r'x="(-?[\d.]+)"', m.group(0)).group(1))
    y = float(re.search(r'y="(-?[\d.]+)"', m.group(0)).group(1))
    return x, y


def test_a_far_designator_is_drawn_next_to_the_body():
    x, y = _label_xy(_svg((2000, 100)))
    assert abs(x - ps._px(770)) < 200 and abs(y - ps._py(900)) < 200


def test_a_near_designator_keeps_its_stored_place():
    x, y = _label_xy(_svg((775, 930)))
    assert abs(x - ps._px(775)) < 1 and abs(y - ps._py(930)) < 10
