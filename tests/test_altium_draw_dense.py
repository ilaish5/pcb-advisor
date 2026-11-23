"""Dense parts: no two net-label text boxes overlap and no label's text crosses a pin or wire of another stub."""
import itertools

from altium import draw


def _sym(pins):
    return {"name": "MOD", "pins": [{"number": str(n), "name": f"P{n}", "x": x, "y": y, "length": 100, "orientation": o, "part_id": 1}
                                    for n, x, y, o in pins]}


def _module(per_side=20, top=0):
    pins, n = [], 1
    for i in range(per_side):
        pins.append((n, -600, 1000 - i * 100, 2))
        n += 1
    for i in range(per_side):
        pins.append((n, 600, 1000 - i * 100, 0))
        n += 1
    for i in range(top):
        pins.append((n, -500 + i * 100, 1200, 1))
        n += 1
    return pins


def _cell(pins):
    sym = _sym(pins)
    part = {"ref": "U1", "pins": [{"num": str(p[0]), "name": f"P{p[0]}", "net": f"SIGNAL_NAME_{p[0]}"} for p in pins]}
    return draw.part_cell(part, sym)


def _label_box(s):
    ax, ay = s["at"]
    w = draw.label_width(s["net"])
    return (ax, ay, ax + w, ay + draw.TEXT_H) if s["rot"] == 0 else (ax - draw.TEXT_H, ay, ax, ay + w)


def _strict(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check_cell(c):
    labels = [s for s in c["stubs"] if s["kind"] == "label"]
    boxes = [(s, _label_box(s)) for s in labels]
    for (s1, b1), (s2, b2) in itertools.combinations(boxes, 2):
        assert not _strict(b1, b2), f"labels {s1['net']} and {s2['net']} overlap"
    for s, b in boxes:
        for o in c["stubs"]:
            if o is s or o["kind"] == "nc":
                continue
            (x1, y1), (x2, y2) = o["tip"], o["end"]
            wire = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            assert not _strict(b, wire), f"label {s['net']} crosses the wire of {o['net']}"


def test_dense_module_labels_do_not_overlap():
    check_cell(_cell(_module()))


def test_dense_module_with_top_row():
    check_cell(_cell(_module(10, 8)))


def _quad(per_side=10, pitch=100):
    pins, n = [], 1
    for i in range(per_side):
        pins.append((n, -500, 450 - i * pitch, 2)); n += 1
    for i in range(per_side):
        pins.append((n, -450 + i * pitch, -500, 3)); n += 1
    for i in range(per_side):
        pins.append((n, 500, -450 + i * pitch, 0)); n += 1
    for i in range(per_side):
        pins.append((n, 450 - i * pitch, 500, 1)); n += 1
    return pins


def test_quad_part_labels_do_not_overlap():
    for pitch in (100, 200):
        check_cell(_cell(_quad(10, pitch)))
