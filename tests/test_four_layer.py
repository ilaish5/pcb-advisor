"""4 layer boards (E9): the layer count in project.json (2 or 4, nothing else), the router's plane nets (vias, no inner signal tracks),
the plane pours, the stack-up check. The bridge to Altium is not used here (its live run is in docs/FOUR-LAYER.md)."""
import pytest

import board_layers
import project as project_mod
import store
from altium import bridge, route
from test_altium_route import JLC, pad, rules
from test_chat_turns import call, server  # noqa: F401


# ---- the layer count: one validator, every writer goes through it

@pytest.mark.parametrize("value,want", [(2, 2), (4, 4), ("4", 4), (4.0, 4), ("2", 2)])
def test_two_and_four_are_accepted(value, want):
    assert board_layers.check(value) == want


@pytest.mark.parametrize("value", [1, 3, 6, 8, 0, -2, 4.5, "four", "", None, True, False, [4]])
def test_any_other_layer_count_is_refused(value):
    with pytest.raises(ValueError):
        board_layers.check(value)


def test_the_refusal_names_the_choices():
    msg = board_layers.refusal(6)
    assert "6 copper layers" in msg and "2 or 4" in msg


def test_layer_count_read_out_of_requirement_text():
    f = board_layers.from_text
    assert f("Board", "a 4 layer board with ground and power planes") == 4
    assert f("PCB", "4-layer stack-up") == 4
    assert f("Stack", "four layers: signal, ground, power, signal") == 4
    assert f("Board", "2 layers is enough") == 2
    assert f("Board", "a 6 layer board") == 6                      # read, then refused by the writer
    assert f("לוח", "לוח 4 שכבות") == 4
    assert f("Power", "the supply has 3 layers of protection") is None       # not about the board
    assert f("Board", "5 V input, 2 A") is None
    assert f("Board", "") is None


def test_board_layers_default_and_invalid_stored_value():
    assert board_layers.of_board({}) == 2 and board_layers.of_board(None) == 2
    assert board_layers.of_board({"layers": 4}) == 4
    assert board_layers.of_board({"layers": 3}) == 2 and board_layers.of_board({"layers": "x"}) == 2


def test_set_layers_writes_project_json_and_refuses_the_rest(empty):
    assert project_mod.layers(empty) == 2
    assert project_mod.set_layers(empty, 4) == 4
    assert project_mod.layers(empty) == 4 and project_mod.load_meta(empty)["board"]["layers"] == 4
    with pytest.raises(ValueError):
        project_mod.set_layers(empty, 6)
    assert project_mod.load_meta(empty)["board"]["layers"] == 4           # the refused value was not written


def test_the_idea_endpoint_sets_two_or_four_and_refuses_the_rest(server, empty):
    code, body = call(server, "POST", "/api/idea/layers", empty, {"layers": 4})
    assert code == 200 and project_mod.layers(empty) == 4
    code, body = call(server, "POST", "/api/idea/layers", empty, {"layers": 3})
    assert code == 400 and "2 or 4" in body["error"] and project_mod.layers(empty) == 4
    assert call(server, "POST", "/api/idea/layers", empty, {"layers": 2})[0] == 200 and project_mod.layers(empty) == 2


def test_the_meta_endpoint_checks_layers_too(server, empty):
    code, body = call(server, "POST", "/api/project/meta", empty, {"board": {"layers": 8}})
    assert code == 400 and "2 or 4" in body["error"]
    assert project_mod.layers(empty) == 2
    assert call(server, "POST", "/api/project/meta", empty, {"board": {"layers": 4}})[0] == 200 and project_mod.layers(empty) == 4


def test_a_requirement_that_states_the_layers_sets_them_and_a_bad_count_is_not_written(empty):
    store.propose_idea(empty, "Board", "a 4 layer board with a ground and a power plane")
    assert project_mod.layers(empty) == 4
    with pytest.raises(ValueError) as e:
        store.propose_idea(empty, "Board", "a 6 layer board")
    assert "2 or 4" in str(e.value) and project_mod.layers(empty) == 4
    assert not [i for i in store.load_idea_working(empty)["agreed"] if "6 layer" in i["text"]]
    store.propose_idea(empty, "Power", "5 V in, 2 A")                 # no count: nothing changes
    assert project_mod.layers(empty) == 4


def test_the_idea_page_has_the_layers_select():
    import pathlib
    js = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "idea.js").read_text(encoding="utf-8")
    assert "board-layers" in js and "/api/idea/layers" in js


def test_the_jlc_preset_follows_the_layer_count():
    import jlc_preset
    assert jlc_preset.variant({"layers": 4})["layers"] == 4 and jlc_preset.variant({"layers": 4})["multilayer"]
    assert jlc_preset.variant({"layers": 4})["name"].startswith("JLC 4-layer")
    assert not jlc_preset.variant({})["multilayer"]


# ---- the stack-up of the file against the project

def test_stack_mismatch():
    m = bridge.stack_mismatch
    assert m(2, 2) == "" and m(4, 4) == "" and m(4, 2) == ""            # a 2 layer file gets its inner layers
    assert "does not take inner layers out" in m(2, 4)
    assert "could not be read" in m(4, None)
    assert m(2, None) == ""                                             # no stack record: the default 2 layer board
    assert "does not take inner layers out" in m(4, 6) and "only adds" in m(6, 4)


# ---- the router: plane nets

def board():
    """A small IC with ground and supply pins, a decoupling cap each side, one bottom layer ground pad, two signals."""
    pads = []
    for i in range(6):
        pads.append(pad("U1", str(i + 1), 12 + i * 1.27, 14, ["GND", "3V3", "S1", "GND", "3V3", "S2"][i], 0.6, 1.6))
    for i, n in enumerate(["S1", "GND", "3V3", "S2", "GND", "3V3"]):
        pads.append(pad("U1", str(12 - i), 12 + i * 1.27, 20, n, 0.6, 1.6))
    pads += [pad("C1", "1", 8, 8, "3V3"), pad("C1", "2", 8, 10.5, "GND"), pad("C2", "1", 28, 8, "3V3"), pad("C2", "2", 28, 10.5, "GND"),
             pad("R1", "1", 10, 26, "S1"), pad("R1", "2", 16, 26, "S2"), pad("D1", "1", 24, 26, "GND", layer=32),
             pad("D1", "2", 28, 26, "S1", layer=32)]
    return {"pads": pads}


PLANES = {"GND": "mid1", "3V3": "mid2"}
R = dict(clearance=0.254, width=0.254, width_min=0.254, via_dia=1.27, via_hole=0.71)


def _plan(doc=None, planes=PLANES):
    doc = doc or board()
    box = [0, 0, 40, 32]
    r = rules(**R)
    return doc, box, r, route.plan_routes(doc, box, r, seconds=90, planes=planes)


def test_plane_nets_are_joined_by_a_stub_and_a_via_never_by_a_web_of_tracks():
    doc, box, r, res = _plan()
    assert not res["failed"], res["failed"]
    assert res["planes"] == PLANES
    assert route.violations(doc, res["items"], r, box) == []
    for net in PLANES:
        mine = [i for i in res["items"] if i["net"] == net]
        vias = [i for i in mine if i["kind"] == "via"]
        tracks = [i for i in mine if i["kind"] == "track"]
        pads = [p for p in doc["pads"] if p["net"] == net]
        assert vias and len(vias) <= len(pads)
        # every pad has copper to a via within a short reach: the plane joins the pads, not tracks between them
        assert all(abs(t["x1"] - t["x2"]) + abs(t["y1"] - t["y2"]) < 6 for t in tracks)
        for p in pads:
            assert any(((v["x"] - p["x_mm"]) ** 2 + (v["y"] - p["y_mm"]) ** 2) ** 0.5 < 5 for v in vias)


def test_the_bottom_layer_plane_pad_gets_its_via_too():
    doc, box, r, res = _plan()
    d1 = next(p for p in doc["pads"] if p["ref"] == "D1" and p["name"] == "1")
    assert d1["layer"] == 32
    gnd = [i for i in res["items"] if i["net"] == "GND"]
    near = [v for v in gnd if v["kind"] == "via" and ((v["x"] - d1["x_mm"]) ** 2 + (v["y"] - d1["y_mm"]) ** 2) ** 0.5 < 5]
    assert near                                                         # not taken to be in a bottom pour: a plane is inside the board


def test_no_signal_track_on_an_inner_layer_and_signals_stay_routed():
    doc, box, r, res = _plan()
    assert {i["layer"] for i in res["items"] if i["kind"] == "track"} <= {1, 32}      # the router draws top and bottom only
    assert {"S1", "S2"} <= set(res["routed"])
    for net in ("S1", "S2"):
        assert not [i for i in res["items"] if i["net"] == net and i["kind"] == "track" and i["layer"] not in (1, 32)]


def test_a_through_hole_pad_of_a_plane_net_needs_no_via():
    pads = [pad("J1", "1", 10, 10, "GND"), pad("J1", "2", 10, 12.54, "S1"), pad("R1", "1", 20, 10, "S1"), pad("R1", "2", 20, 14, "GND"),
            pad("R2", "1", 26, 10, "GND"), pad("R2", "2", 26, 14, "3V3"), pad("R3", "1", 30, 10, "3V3"), pad("R3", "2", 30, 14, "3V3")]
    pads[0].update(layer=74, hole_mm=1.0, sx_mm=1.7, sy_mm=1.7)
    pads[1].update(layer=74, hole_mm=1.0, sx_mm=1.7, sy_mm=1.7)
    doc = {"pads": pads}
    res = route.plan_routes(doc, [0, 0, 40, 24], rules(**R), seconds=60, planes={"GND": "mid1", "3V3": "mid2"})
    assert not res["failed"], res["failed"]
    # J1-1 is through hole: it is in the plane by itself, so the GND vias serve R1-2 and R2-1 only (they may share one)
    gnd_vias = [i for i in res["items"] if i["net"] == "GND" and i["kind"] == "via"]
    assert 1 <= len(gnd_vias) <= 2


def test_without_planes_the_router_is_as_before():
    doc = board()
    res = route.plan_routes(doc, [0, 0, 40, 32], rules(**R), seconds=90)
    assert "planes" in res and res["planes"] == {}
    assert not res["failed"], res["failed"]


def test_a_plane_net_that_cannot_reach_a_via_fails_closed_and_is_named():
    # the pad sits in a corner closed by other nets' copper on both layers: the net is reported failed, not silently left open
    doc = board()
    box = [0, 0, 40, 32]
    res = route.plan_routes(doc, box, rules(**R), seconds=60, planes={"GND": "mid1", "NOSUCH": "mid2"})
    assert "NOSUCH" not in res["planes"]                                 # a plane for a net the board does not have is not invented
    assert not res["failed"], res["failed"]


# ---- which nets are planes

def test_plane_nets_for_picks_ground_and_the_main_supply():
    doc = board()
    assert route.plane_nets_for(doc) == {"GND": "mid1", "3V3": "mid2"}
    doc2 = {"pads": [p for p in doc["pads"] if p["net"] != "3V3"]}
    assert route.plane_nets_for(doc2) == {"GND": "mid1"}               # none is invented
    assert route.plane_nets_for({"pads": [p for p in doc["pads"] if p["net"].startswith("S")]}) == {}


# ---- the commands: the pours on the inner layers

def test_route_commands_pour_the_planes_on_the_inner_layers_after_the_copper():
    items = [{"kind": "track", "layer": 1, "x1": 1, "y1": 1, "x2": 2, "y2": 2, "width": 0.25, "net": "S1"},
             {"kind": "via", "x": 3, "y": 3, "dia": 0.6, "hole": 0.3, "net": "GND"}]
    cmds = route.route_commands("a.PcbDoc", items, planes=PLANES, box=[0, 0, 40, 32], edge=0.3)
    kinds = [c[0] for c in cmds]
    assert kinds == ["ROUTEBEGIN", "TRACK", "VIA", "POLY", "POLY", "PCBSAVE"]
    polys = [c for c in cmds if c[0] == "POLY"]
    assert [(c[2], c[3]) for c in polys] == [("mid1", "GND"), ("mid2", "3V3")]
    assert polys[0][4:] == ("0.3000", "0.3000", "39.7000", "31.7000")


def test_the_plane_pours_keep_out_of_an_antenna_area():
    cmds = route.route_commands("a.PcbDoc", [], planes={"GND": "mid1"}, box=[0, 0, 40, 32], keepouts=[[30, 0, 40, 10]])
    polys = [c for c in cmds if c[0] == "POLY"]
    assert len(polys) >= 2 and all(c[2] == "mid1" for c in polys)
    for c in polys:                                                      # no pour rectangle overlaps the keep-out
        x0, y0, x1, y1 = (float(v) for v in c[4:])
        assert not (x0 < 30 and x1 > 30 and y0 < 10) and not (x0 >= 30 and y0 < 10)


def test_pour_commands_are_unchanged_without_planes():
    cmds = route.route_commands("a.PcbDoc", [], pour_net="GND", box=[0, 0, 40, 32])
    assert [(c[0], c[2]) for c in cmds if c[0] == "POLY"] == [("POLY", "bottom")]


# ---- what the router says it cannot do

def test_inner_copper_is_refused_on_two_layers_and_only_the_planes_pours_are_allowed_on_four():
    pour = {"layer": 2, "polygon": True, "net": "GND"}
    track = {"layer": 3, "net": "S1", "x1_mm": 0, "y1_mm": 0, "x2_mm": 1, "y2_mm": 1, "width_mm": 0.2}
    base = {"pads": [pad("R1", "1", 5, 5, "A")]}
    assert route.capability_check(dict(base, regions=[pour])) and "inner layers" in route.capability_check(dict(base, regions=[pour]))[0]
    assert not route.capability_check(dict(base, regions=[pour]), layers=4)             # the plane's own pour
    assert "inner layers" in route.capability_check(dict(base, regions=[pour], tracks=[track]), layers=4)[0]
    assert "inner layers" in route.capability_check(dict(base, regions=[dict(pour, layer=4)]), layers=4)[0]
