"""More tests of the pour check: region holes, other copper of the net, round pads, dead copper note."""
import pathlib
import struct
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

from altium import pcbdoc, pourcheck  # noqa: E402
from test_altium_pourcheck import doc, pad, rect  # noqa: E402


def test_shape_wholly_inside_a_hole_does_not_touch():
    hole = [(10, 3), (20, 3), (20, 7), (10, 7)]
    d = doc([rect(0, 0, 30, 10, holes=[hole])], [pad(5, 5), pad(25, 5), pad(15, 5, name="2")])
    r = pourcheck.check(d)
    assert [p["name"] for p in r["unjoined_pads"]] == ["2"]
    d = doc([rect(0, 0, 30, 10, holes=[hole])], [pad(5, 5), pad(25, 5), pad(10, 5, name="2")])   # straddles the hole edge
    assert pourcheck.check(d)["ok"]
    # a piece lying in the hole of the big piece is cut off, not joined to it
    d = doc([rect(0, 0, 30, 10, holes=[hole]), rect(12, 4, 18, 6)], [pad(5, 5), pad(25, 5), pad(28, 8)])
    assert len(pourcheck.check(d)["islands"]) == 1


def test_piece_of_unknown_polygon_is_not_the_pour_net():
    d = doc([rect(0, 0, 30, 10, polygon_net=None)], [pad(5, 5), pad(15, 5), pad(25, 5)])
    r = pourcheck.check(d)
    assert r["checked"] is False and not r["ok"]


def test_arcs_fills_regions_and_component_tracks_join():
    base = [rect(0, 0, 30, 10), rect(40, 0, 50, 10)]
    pads = [pad(5, 5), pad(15, 5), pad(25, 5)]
    assert pourcheck.check(doc(base, pads))["ok"] is False
    d = doc(base, pads)
    d["fills"] = [{"layer": 32, "net": "GND", "x1_mm": 28, "y1_mm": 4, "x2_mm": 42, "y2_mm": 6, "rot": 0.0}]
    assert pourcheck.check(d)["ok"]
    d = doc(base + [{"layer": 32, "net": "GND", "polygon": False, "in_component": False, "kind": 0, "holes": [],
                     "points_mm": [(28, 4), (42, 4), (42, 6), (28, 6)]}], pads)
    assert pourcheck.check(d)["ok"]
    d = doc(base, pads, tracks=[{"layer": 32, "net": "GND", "in_component": True, "x1_mm": 25, "y1_mm": 5, "x2_mm": 45,
                                 "y2_mm": 5, "width_mm": 0.3}])
    assert pourcheck.check(d)["ok"]
    # an arc from (45, 5) over the top to (25, 5): centre (35, 5), radius 10, 0 to 180 degrees
    d = doc(base, pads)
    d["arcs"] = [{"layer": 32, "net": "GND", "in_component": False, "cx_mm": 35, "cy_mm": 5, "r_mm": 10, "a1": 0.0, "a2": 180.0,
                  "width_mm": 0.3}]
    assert pourcheck.check(d)["ok"]


def test_round_pad_corner_gap_is_not_a_touch():
    # a round pad of diameter 2 centred (30.8, 10.8): its square reaches the corner (30, 10) of the piece, the circle does not
    p = pad(30.8, 10.8, name="2")
    p.update(shape=1, sx_mm=2.0, sy_mm=2.0)
    d = doc([rect(0, 0, 30, 10)], [pad(5, 5), pad(25, 5), p])
    assert [x["name"] for x in pourcheck.check(d)["unjoined_pads"]] == ["2"]
    p["shape"] = 2
    assert pourcheck.check(d)["ok"]


def test_dead_copper_note_and_island_area():
    d = doc([rect(0, 0, 30, 10), rect(40, 0, 50, 10, polygon_remove_dead=False)], [pad(5, 5), pad(15, 5), pad(25, 5)])
    r = pourcheck.check(d)
    assert r["islands"][0]["area_mm2"] == 100.0
    assert "Remove Dead Copper is off in polygon GND_Bot" in r["note"]


def test_region_holes_are_read():
    k = 10000 / 0.0254                      # mm to file units
    text = b"V7_LAYER=BOTTOM|KIND=0|ISSHAPEBASED=FALSE\x00"
    head = bytearray(18)
    head[0] = 32
    head[3:5] = struct.pack("<H", 0xFFFF)
    head[5:7] = struct.pack("<H", 0)         # polygon 0
    head[7:9] = struct.pack("<H", 0xFFFF)
    head[14:16] = struct.pack("<H", 1)       # one hole
    outline = struct.pack("<8d", 0, 0, 10 * k, 0, 10 * k, 10 * k, 0, 10 * k)
    hole = struct.pack("<I", 3) + struct.pack("<6d", 2 * k, 2 * k, 5 * k, 2 * k, 5 * k, 5 * k)
    rec = bytes(head) + struct.pack("<I", len(text)) + text + struct.pack("<I", 4) + outline + hole
    reg = pcbdoc.parse_regions(b"\x0b" + struct.pack("<I", len(rec)) + rec, ["N"], [{"net": "N", "remove_dead": False}])
    assert len(reg) == 1 and reg[0]["polygon_net"] == "N" and reg[0]["polygon_remove_dead"] is False
    assert len(reg[0]["points_mm"]) == 4
    assert reg[0]["holes"] == [[(2.0, 2.0), (5.0, 2.0), (5.0, 5.0)]]
