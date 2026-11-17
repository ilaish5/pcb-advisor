"""Tests for the ground pour check (scripts/altium/pourcheck.py)."""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from altium import pourcheck, read_pcbdoc  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "altium" / "finished-board.PcbDoc"


def rect(x0, y0, x1, y1, layer=32, net=None, **kw):
    r = {"layer": layer, "net": net, "polygon": True, "in_component": False, "kind": 0,
         "points_mm": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}
    r.update(kw)
    return r


def pad(x, y, net="GND", layer=74, ref="J1", name="1"):
    return {"ref": ref, "name": name, "net": net, "layer": layer, "x_mm": x, "y_mm": y, "sx_mm": 1.0, "sy_mm": 1.0,
            "rot": 0.0, "hole_mm": 0.8 if layer == 74 else 0.0}


def doc(regions, pads, tracks=(), vias=()):
    return {"regions": regions, "pads": pads, "tracks": list(tracks), "vias": list(vias), "nets": ["GND"]}


def test_pour_touching_all_pads_is_ok():
    d = doc([rect(0, 0, 30, 10)], [pad(5, 5), pad(15, 5), pad(25, 5)])
    r = pourcheck.check(d)
    assert r["checked"] and r["ok"] and r["islands"] == [] and r["unjoined_pads"] == []


def test_cut_off_island_is_reported():
    d = doc([rect(0, 0, 30, 10), rect(40, 0, 50, 10)], [pad(5, 5), pad(15, 5), pad(25, 5)])
    r = pourcheck.check(d)
    assert r["checked"] and not r["ok"]
    assert len(r["islands"]) == 1 and r["islands"][0]["bbox_mm"][0] == 40.0


def test_island_joined_by_a_track_to_a_pad_is_not_an_island():
    d = doc([rect(0, 0, 30, 10), rect(40, 0, 50, 10)], [pad(5, 5), pad(15, 5), pad(25, 5)],
            tracks=[{"layer": 32, "net": "GND", "in_component": False, "x1_mm": 25, "y1_mm": 5, "x2_mm": 45, "y2_mm": 5,
                     "width_mm": 0.3}])
    r = pourcheck.check(d)
    assert r["ok"] and r["islands"] == []


def test_pad_outside_the_pour_without_track_is_reported():
    d = doc([rect(0, 0, 30, 10)], [pad(5, 5), pad(15, 5), pad(25, 5), pad(60, 5, ref="J2", name="3")])
    r = pourcheck.check(d)
    assert r["checked"] and not r["ok"] and r["islands"] == []
    assert [(p["ref"], p["name"]) for p in r["unjoined_pads"]] == [("J2", "3")]


def test_pad_outside_the_pour_with_track_to_the_net_is_fine():
    d = doc([rect(0, 0, 30, 10)], [pad(5, 5), pad(15, 5), pad(25, 5), pad(40, 5, ref="J2", name="3")],
            tracks=[{"layer": 32, "net": "GND", "in_component": False, "x1_mm": 25, "y1_mm": 5, "x2_mm": 40, "y2_mm": 5,
                     "width_mm": 0.3}])
    assert pourcheck.check(d)["ok"]


def test_smd_pad_on_the_other_layer_is_not_required_to_touch():
    d = doc([rect(0, 0, 30, 10)], [pad(5, 5), pad(15, 5), pad(25, 5), pad(60, 5, layer=1, ref="U1", name="2")])
    assert pourcheck.check(d)["ok"]


def test_other_nets_polygon_is_ignored():
    d = doc([rect(0, 0, 30, 10, polygon_net="GND"), rect(100, 0, 110, 10, polygon_net="5V")],
            [pad(5, 5), pad(15, 5), pad(25, 5)])
    assert pourcheck.check(d)["ok"]


def test_unreadable_geometry_is_never_ok():
    for d in (doc([], [pad(5, 5), pad(15, 5), pad(25, 5)]),
              doc([rect(0, 0, 1, 1, points_mm=[])], [pad(5, 5), pad(15, 5), pad(25, 5)]),
              {"pads": [pad(5, 5), pad(15, 5), pad(25, 5)]},
              doc([rect(0, 0, 30, 10)], [pad(5, 5)]),          # no ground net with 3 pads
              None):
        r = pourcheck.check(d)
        assert r["checked"] is False and r["ok"] is False and r["note"]


def test_real_fixture_is_stable():
    d = read_pcbdoc(FIXTURE)
    # the pours of the fixture: GND (net of polygon 0 bottom, polygon 5 top), 5V and 12V, read from Polygons6
    assert {r["polygon_net"] for r in d["regions"] if r["polygon"]} == {"GND", "5V", "12V"}
    r12 = pourcheck.check(d, net="12V")
    assert r12["checked"] and r12["ok"]
    r = pourcheck.check(d)                       # GND, bottom and top
    assert r["checked"] and r["unjoined_pads"] == []
    assert len(r["islands"]) == 14 and sorted({i["layer"] for i in r["islands"]}) == [1, 32]
    # hand check: the board-size 4 point GND piece of the bottom layer (25.659..126.868 mm) holds the through-hole GND pads, so it is
    # not an island; the two bottom islands are the thin slivers near x 76..80, y 33..41
    bottom = sorted(i["bbox_mm"] for i in r["islands"] if i["layer"] == 32)
    assert bottom == [[76.293, 33.041, 77.427, 41.18], [78.173, 32.783, 79.764, 41.18]]
    assert pourcheck.check(d, layer=32)["islands"] == [i for i in r["islands"] if i["layer"] == 32]
    assert pourcheck.check(d) == r
