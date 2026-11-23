"""Keep-outs when the Altium probe says the Keep-Out layer did not take: the confirmed rectangles and a radio module's antenna area go to
the router and the pour directly (Python side), and the notice says exactly what is and is not protected."""
import json

import partlib
import store
from altium import bridge, route
from test_altium_route import pad, rules
from test_altium_route_review import _gap_to
from test_unverified_pins import _add

NO_LAYER = {"pas_hash": "x", "keepout_layer": False, "npth": True, "slot": None, "problems": ["objects on 'Keep-Out Layer' did not arrive"]}


def test_notice_says_what_is_and_is_not_protected():
    text = bridge.keepout_notice(NO_LAYER)
    assert "Protected: this program's placer, router and ground pour" in text and "Not protected: Altium's own design rule check" in text
    assert bridge.keepout_notice({"keepout_layer": True, "npth": True, "problems": []}) == ""
    assert "unplated" in bridge.keepout_notice({"keepout_layer": True, "npth": False, "problems": ["x"]})


def test_probe_false_router_and_pour_keep_clear_of_the_passed_rectangles(tmp_path, monkeypatch):
    cache = tmp_path / "caps.json"
    monkeypatch.setattr(bridge, "capabilities_path", lambda: cache)
    monkeypatch.setattr(bridge, "_script_hash", lambda: "x")
    cache.write_text(json.dumps(NO_LAYER), encoding="utf-8")
    caps = bridge.capabilities_cached()
    assert caps and not caps["keepout_layer"]                       # the fake probe: no keep-out layer
    doc = {"pads": [pad("R1", "1", 4, 7, "A"), pad("R2", "1", 16, 7, "A")]}            # nothing keep-out in the document itself
    area = [8.0, 4.0, 12.0, 10.0]                                      # right between the two pads
    box = [0, 0, 20, 14]
    r = rules(keepout_rects=[area])
    res = route.plan_routes(doc, box, r, seconds=60)
    assert res["routed"] == ["A"], res["failed"]
    assert _gap_to(res["items"], ("rect", tuple(area)), (route.TOP, route.BOT)) >= 0 - 1e-6        # no track, no via touches the area
    assert route.violations(doc, res["items"], r, box) == []
    polys = [c for c in route.route_commands("x.PcbDoc", res["items"], pour_net="GND", box=[0, 0, 40, 30], keepouts=[[10, 10, 20, 20]]) if c[0] == "POLY"]
    assert polys
    for _, _, _, _, x0, y0, x1, y1 in polys:
        assert not (float(x0) < 20 and float(x1) > 10 and float(y0) < 20 and float(y1) > 10)
    wall = {"pads": [pad("R1", "1", 4, 7, "A"), pad("R2", "1", 16, 7, "A")]}
    res = route.plan_routes(wall, box, rules(keepout_rects=[[9.9, -1, 10.1, 15]]), seconds=20, rounds=2)
    assert res["failed"] and not res["items"]                             # a full-height wall: nothing can cross it, on either layer


def test_python_keepouts_from_confirmed_constraints_and_a_radio_module(empty):
    _add(empty, "U1", "ESP32-WROOM")
    idea = {"constraints": {"version": 1, "items": [
        {"id": "k1", "kind": "keepout", "rect_mm": [3, 3, 8, 8], "status": "confirmed", "by": "student"},
        {"id": "k2", "kind": "keepout", "rect_mm": [20, 20, 25, 25], "status": "proposed", "by": "agent"}]}}
    (store.pdir(empty) / "idea.json").write_text(json.dumps(idea), encoding="utf-8")
    lib = partlib.library_dir(empty)
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.json").write_text(json.dumps({"U1": {"rf": {"antenna_side": "T", "keepout_box": [-5, 2, 5, 6]}}}), encoding="utf-8")
    doc = {"components": [{"ref": "U1", "x_mm": 30, "y_mm": 10, "rotation": 90.0, "layer": "Top"}]}
    rects = bridge.python_keepouts(empty, doc, [0, 0, 40, 30])
    assert [3, 3, 8, 8] in rects and [20, 20, 25, 25] not in rects          # only confirmed items
    assert [24.0, 5.0, 28.0, 15.0] in rects                                # the module's box turned 90 degrees about its position
