"""The schematic preview (scripts/preview_sch.py) keeps what Altium stores: pins run out of the body, names sit inside it,
texts stay clear of lines and of each other, and net label boxes are shorter than the 100 mil pin pitch.

The pictures are checked as geometry: the SVG is parsed and every text gets the box its font size gives it."""
import math
import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

import preview_sch as ps
from altium.schdoc import PIN_DIRECTION, pin_tip, read_schdoc

PROJECT = pathlib.Path(__file__).parent / "fixtures" / "altium" / "project"
SHEETS = sorted(PROJECT.glob("*.SchDoc"))
PITCH = 10 * ps.SCALE      # 100 mil in px


# ---------- a sheet written by hand: an 8-pin buck converter and a resistor ----------

def _pin(number, name, x, y, orientation, **kw):
    return {"number": str(number), "name": name, "x": x, "y": y, "length": 30, "orientation": orientation,
            "hidden": False, "show_name": True, "show_number": True, "part_id": 1, **kw}


def _text(text, x, y, justification, font=1):
    return {"text": text, "x": x, "y": y, "justification": justification, "orientation": 0, "font": font, "hidden": False}


def _doc():
    left = [_pin(i + 1, n, 770, 920 - 10 * i, 2) for i, n in enumerate(["AAM", "IN", "SW", "GND"])]
    right = [_pin(8 - i, n, 890, 920 - 10 * i, 0) for i, n in enumerate(["FB", "VCC", "EN/SYNC", "BST"])]
    u1 = {"ref": "U1", "comment": "MP2315GJ-Z", "x": 740, "y": 920, "current_part_id": 1, "pins": left + right,
          "graphics": [{"kind": "rect", "part_id": 1, "x1": 770, "y1": 870, "x2": 890, "y2": 940, "solid": True}],
          "designator_text": _text("U1", 770, 946, 0), "comment_text": _text("MP2315GJ-Z", 770, 864, 6)}
    # a resistor with no drawing in the doc: stored pins only, numbers shown, names not
    r1 = {"ref": "R1", "comment": "100k", "x": 1060, "y": 910, "current_part_id": 1, "graphics": [],
          "pins": [_pin(1, "1", 1060, 920, 1, length=10, show_name=False), _pin(2, "2", 1060, 900, 3, length=10, show_name=False)]}
    labels = [{"text": n, "name": n, "x": 700, "y": 920 - 10 * i, "orientation": 0, "font": 1} for i, n in enumerate(["AAM", "+12V", "SW", "GND"])]
    wires = [{"points": [(700, 920 - 10 * i), (740, 920 - 10 * i)]} for i in range(4)]
    return {"file": "hand.SchDoc", "components": [u1, r1], "wires": wires, "net_labels": labels, "junctions": [],
            "power_ports": [{"text": "+12V", "x": 1060, "y": 940, "style": 2, "orientation": 1, "show_name": True, "font": 1},
                            {"text": "GND", "x": 1060, "y": 880, "style": 4, "orientation": 3, "show_name": False, "font": 1}],
            "ports": [], "fonts": {1: {"size": 10, "name": "Times New Roman", "bold": False, "italic": False}}, "system_font": 1}


# ---------- reading the picture back ----------

def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _classes(el):
    return (el.get("class") or "").split()


def _text_box(t):
    """The box (x0, y0, x1, y1) of a <text>: anchor, baseline, size and rotation as the SVG states them."""
    fs = float(re.search(r"font-size:([\d.]+)px", t.get("style")).group(1))
    s = "".join(t.itertext())
    w, h = len(s) * ps.CHAR_W * fs, ps.CAP_H * fs
    x, y = float(t.get("x")), float(t.get("y"))
    x0 = x - {"start": 0, "middle": w / 2, "end": w}[t.get("text-anchor", "start")]
    corners = [(x0, y - h), (x0 + w, y - h), (x0, y), (x0 + w, y)]
    m = re.search(r"rotate\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)", t.get("transform") or "")
    if m:
        a, cx, cy = math.radians(float(m.group(1))), float(m.group(2)), float(m.group(3))
        corners = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a), cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a))
                   for px, py in corners]
    return (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))


class Picture:
    """What a part of the SVG draws: its body rectangles, pin lines, and the boxes of its texts by class."""

    def __init__(self, g):
        self.bodies = [(float(r.get("x")), float(r.get("y")), float(r.get("x")) + float(r.get("width")), float(r.get("y")) + float(r.get("height")))
                       for r in g.iter() if _tag(r) == "rect" and "body" in _classes(r)]
        self.pins = [tuple(float(ln.get(k)) for k in ("x1", "y1", "x2", "y2")) for ln in g.iter() if _tag(ln) == "line" and "pin" in _classes(ln)]
        self.texts = {}
        for t in g.iter():
            if _tag(t) == "text":
                self.texts.setdefault(_classes(t)[0] if _classes(t) else "", []).append(("".join(t.itertext()), _text_box(t)))


def _parts(svg):
    root = ET.fromstring(svg)
    return root, {g.get("data-ref"): Picture(g) for g in root.iter() if _tag(g) == "g" and "part" in _classes(g)}


def _hit(a, b, tol=0.5):
    return not (a[2] <= b[0] + tol or b[2] <= a[0] + tol or a[3] <= b[1] + tol or b[3] <= a[1] + tol)


def _segment_box(seg):
    return (min(seg[0], seg[2]), min(seg[1], seg[3]), max(seg[0], seg[2]) + 0.01, max(seg[1], seg[3]) + 0.01)


def _inside(box, body, tol=0.5):
    return box[0] >= body[0] - tol and box[1] >= body[1] - tol and box[2] <= body[2] + tol and box[3] <= body[3] + tol


# ---------- the tests ----------

def test_a_pin_line_runs_out_of_the_body_to_its_connection_point():
    _, parts = _parts(ps.render_schdoc(_doc()))
    u1 = parts["U1"]
    body = u1.bodies[0]
    assert len(u1.pins) == 8
    for x1, y1, x2, y2 in u1.pins:
        # the stored location is on the body edge; the line ends 30 units (60 px) outside it
        assert min(abs(x1 - body[0]), abs(x1 - body[2])) < 0.5
        assert abs(math.hypot(x2 - x1, y2 - y1) - 30 * ps.SCALE) < 0.5
        assert not _hit(_segment_box((x1, y1, x2, y2)), body), "the pin line runs into the body"


def test_pin_tip_is_pinlength_from_the_location_in_the_pins_direction():
    for rotation, (dx, dy) in PIN_DIRECTION.items():
        assert pin_tip({"x": 100, "y": 200, "length": 30, "orientation": rotation}) == (100 + 30 * dx, 200 + 30 * dy)


def test_pin_names_sit_inside_the_body_and_clear_of_every_pin_line():
    _, parts = _parts(ps.render_schdoc(_doc()))
    u1 = parts["U1"]
    names = u1.texts["pname"]
    assert sorted(n for n, _ in names) == sorted(["AAM", "IN", "SW", "GND", "BST", "VCC", "EN/SYNC", "FB"])
    for name, box in names:
        assert _inside(box, u1.bodies[0]), f"{name} is not inside the body"
        for pin in u1.pins:
            assert not _hit(box, _segment_box(pin)), f"{name} is struck through by a pin line"
    # the names of the left and the right pins do not run into each other
    for (a, ba), (b, bb) in zip(names, names[1:]):
        assert not _hit(ba, bb), (a, b)


def test_pin_numbers_stay_off_the_line_and_off_the_names():
    _, parts = _parts(ps.render_schdoc(_doc()))
    for ref in ("U1", "R1"):
        pic = parts[ref]
        assert pic.texts["pnum"]
        for num, box in pic.texts["pnum"]:
            for pin in pic.pins:
                assert not _hit(box, _segment_box(pin)), f"{ref} pin number {num} sits on a pin line"
            for name, nbox in pic.texts.get("pname", []):
                assert not _hit(box, nbox), (num, name)


def test_designator_and_comment_sit_where_the_sheet_stores_them_and_clear_of_the_pins():
    _, parts = _parts(ps.render_schdoc(_doc()))
    u1 = parts["U1"]
    (des, dbox), = u1.texts["refd"]
    (com, cbox), = u1.texts["mpn"]
    assert (des, com) == ("U1", "MP2315GJ-Z")
    # the designator hangs on its anchor (770, 946) from the left and above, the comment from (770, 864) below
    assert abs(dbox[0] - ps._px(770)) < 0.5 and abs(dbox[3] - ps._py(946)) < 0.5
    assert abs(cbox[0] - ps._px(770)) < 0.5 and abs(cbox[1] - ps._py(864)) < 0.5
    body = u1.bodies[0]
    assert dbox[3] <= body[1] and cbox[1] >= body[3], "above and below the body, not on it"
    for box in (dbox, cbox):
        for _, other in u1.texts["pname"] + u1.texts["pnum"]:
            assert not _hit(box, other)
        for pin in u1.pins:
            assert not _hit(box, _segment_box(pin))


def test_without_stored_positions_designator_and_comment_go_above_and_below_the_body():
    doc = _doc()
    for c in doc["components"]:
        c.pop("designator_text", None)
        c.pop("comment_text", None)
    _, parts = _parts(ps.render_schdoc(doc))
    for ref in ("U1", "R1"):
        pic = parts[ref]
        body = pic.bodies[0]
        (_, dbox), = pic.texts["refd"]
        (_, cbox), = pic.texts["mpn"]
        assert dbox[3] <= body[1] and cbox[1] >= body[3]
        for box in (dbox, cbox):
            for pin in pic.pins:
                assert not _hit(box, _segment_box(pin))


def test_a_part_without_a_drawing_gets_a_body_between_its_pins():
    _, parts = _parts(ps.render_schdoc(_doc()))
    r1 = parts["R1"]
    body = r1.bodies[0]
    for pin in r1.pins:
        assert not _hit(_segment_box(pin), body)
    # the pins' body ends (y 920 and 900 units) are on its top and bottom edges
    assert abs(body[1] - ps._py(920)) < 0.5 and abs(body[3] - ps._py(900)) < 0.5
    assert "pname" not in r1.texts, "the resistor's pins do not show a name"


def test_hidden_pins_are_not_drawn_and_a_name_is_drawn_only_when_the_pin_shows_it():
    doc = _doc()
    pins = doc["components"][0]["pins"]
    pins[0]["hidden"] = True
    pins[1]["show_name"] = False
    pins[2]["show_number"] = False
    _, parts = _parts(ps.render_schdoc(doc))
    u1 = parts["U1"]
    assert len(u1.pins) == 7
    assert "AAM" not in [n for n, _ in u1.texts["pname"]] and "IN" not in [n for n, _ in u1.texts["pname"]]
    assert "3" not in [n for n, _ in u1.texts["pnum"]]


def test_net_label_boxes_on_neighbouring_pins_are_shorter_than_the_pitch_and_do_not_meet():
    root, _ = _parts(ps.render_schdoc(_doc()))
    boxes = []
    for g in root.iter():
        if _tag(g) == "g" and "net-label" in _classes(g):
            r = next(e for e in g.iter() if _tag(e) == "rect")
            boxes.append((g.get("data-net"), (float(r.get("x")), float(r.get("y")), float(r.get("x")) + float(r.get("width")), float(r.get("y")) + float(r.get("height")))))
    assert len(boxes) == 4
    for name, box in boxes:
        assert box[3] - box[1] < PITCH * 0.85, f"{name}: a label box must stay well under the pin pitch"
    for (a, ba), (b, bb) in zip(boxes, boxes[1:]):
        assert not _hit(ba, bb, 0.0), (a, b)
    # the box sits on the wire it names, not over it
    wires = [[tuple(map(float, p.split(","))) for p in w.get("points").split()] for w in root.iter() if _tag(w) == "polyline" and "w" in _classes(w)]
    for (name, box), wire in zip(boxes, wires):
        assert box[3] <= wire[0][1] + 0.01, name


def test_net_label_text_fits_its_box():
    root, _ = _parts(ps.render_schdoc(_doc()))
    for g in root.iter():
        if _tag(g) == "g" and "net-label" in _classes(g):
            r = next(e for e in g.iter() if _tag(e) == "rect")
            box = (float(r.get("x")), float(r.get("y")), float(r.get("x")) + float(r.get("width")), float(r.get("y")) + float(r.get("height")))
            assert _inside(_text_box(next(e for e in g.iter() if _tag(e) == "text")), box)


def test_a_vertical_net_label_reads_upward_and_stays_beside_its_wire():
    doc = _doc()
    doc["net_labels"] = [{"text": "I2C_SDA", "name": "I2C_SDA", "x": 500, "y": 500, "orientation": 1, "font": 1}]
    svg = ps.render_schdoc(doc)
    assert 'transform="rotate(-90 1000.0 -1000.0)"' in svg


def test_power_ports_point_the_way_they_are_stored_and_ground_shows_no_name():
    root, _ = _parts(ps.render_schdoc(_doc()))
    ports = {g.get("data-net"): g for g in root.iter() if _tag(g) == "g" and "power-port" in _classes(g)}
    up, down = ports["+12V"], ports["GND"]
    # the +12V bar is above its connection point (1060, 940), the ground symbol below its point (1060, 880)
    path = next(e for e in up.iter() if _tag(e) == "path").get("d")
    ys = [float(v) for v in re.findall(r"[ML]\s*[-\d.]+ ([-\d.]+)", path)]
    assert min(ys) < ps._py(940) - 0.1
    path = next(e for e in down.iter() if _tag(e) == "path").get("d")
    ys = [float(v) for v in re.findall(r"[ML]\s*[-\d.]+ ([-\d.]+)", path)]
    assert max(ys) > ps._py(880) + 0.1
    assert any(_tag(e) == "text" for e in up.iter()) and not any(_tag(e) == "text" for e in down.iter())


def test_the_view_box_holds_the_whole_drawing():
    svg = ps.render_schdoc(_doc())
    vx, vy, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    root, parts = _parts(svg)
    for pic in parts.values():
        for box in [b for boxes in pic.texts.values() for _, b in boxes] + pic.bodies:
            assert box[0] >= vx and box[1] >= vy and box[2] <= vx + w and box[3] <= vy + h


# ---------- the real sheets of the fixtures ----------

def test_schdoc_reader_returns_the_drawing_the_font_table_and_the_text_positions():
    doc = read_schdoc(PROJECT / "CAN_Interface.SchDoc")
    assert doc["fonts"][doc["system_font"]]["size"] > 0
    drawn = [c for c in doc["components"] if c["graphics"]]
    assert drawn, "components keep their body drawing"
    assert {g["kind"] for c in doc["components"] for g in c["graphics"]} <= {"rect", "polyline", "polygon", "arc", "text"}
    assert any(c["designator_text"] and c["designator_text"]["text"] == c["ref"] for c in doc["components"])
    for c in doc["components"]:
        for p in c["pins"]:
            assert isinstance(p["show_name"], bool) and isinstance(p["show_number"], bool)
        for t in (c["designator_text"], c["comment_text"]):
            assert t is None or 0 <= t["justification"] <= 8


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_pin_text_never_touches_a_pin_line_or_other_pin_text_on_the_real_sheets(sheet):
    _, parts = _parts(ps.render_schdoc(sheet))
    assert parts
    for ref, pic in parts.items():
        texts = [(c, s, b) for c in ("pname", "pnum") for s, b in pic.texts.get(c, [])]
        for cls, s, box in texts:
            for pin in pic.pins:
                assert not _hit(box, _segment_box(pin), 0.3), f"{ref}: {cls} {s!r} sits on a pin line"
        for (c1, s1, b1), (c2, s2, b2) in zip(texts, texts[1:]):
            if c1 == c2:
                assert not _hit(b1, b2), f"{ref}: {s1!r} runs into {s2!r}"


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_a_pin_that_starts_on_the_body_edge_runs_out_of_it_on_the_real_sheets(sheet):
    doc = read_schdoc(sheet)
    _, parts = _parts(ps.render_schdoc(doc))
    checked = 0
    for comp in doc["components"]:
        pic = parts[comp["ref"]]
        if len(pic.bodies) != 1:        # a symbol drawn with lines, or with several rectangles: no one edge to test
            continue
        body = pic.bodies[0]
        for pin in pic.pins:
            if min(abs(pin[0] - body[0]), abs(pin[0] - body[2]), abs(pin[1] - body[1]), abs(pin[1] - body[3])) < 0.5:
                assert not _hit(_segment_box(pin), body, 0.5), f"{comp['ref']}: pin line inside the body"
                checked += 1
    assert checked, "the sheet has parts with a rectangular body"
