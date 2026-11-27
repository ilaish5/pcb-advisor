"""The block diagram must not miswire: no link through a block it does not join, no two links on one line, no label
on a block. Server layout (store._auto_layout + diagram_route) and the browser router (ui/diagram.js routeConnectors)
follow the same rules; the node tests run the JS on the same geometry and compare."""
import json
import os
import pathlib
import random
import shutil
import subprocess
import time

import pytest

import diagram_route
import store

REPO = pathlib.Path(__file__).resolve().parent.parent

# the shape of UX-E2E-ESP32C3: esd -> mcu and btn -> mcu skip a column
LINKS = [("conn_1", "usb", "esd", "5V, D+/D-"), ("conn_3", "ldo", "mcu", "3V3"), ("conn_4", "esd", "mcu", "USB D+/D-"),
         ("conn_5", "mcu", "sht", "I2C"), ("conn_6", "mcu", "led", "GPIO"), ("conn_7", "btn", "mcu", "BOOT, EN"),
         ("conn_2", "esd", "ldo", "5V")]


def fixture():
    shapes = [{"id": i, "type": "block", "x": 10.0 * n, "y": 7.0 * n, "w": 160.0, "h": 68.0}
              for n, i in enumerate(["usb", "esd", "ldo", "mcu", "sht", "led", "btn"])]
    conns = [{"id": c, "from": {"shape": a, "side": "right"}, "to": {"shape": b, "side": "left"}, "label": lab,
              "route": "elbow"} for c, a, b, lab in LINKS]
    return shapes, conns


def _inside(u, v, box):
    x0, y0, x1, y1 = box
    if u["y"] == v["y"]:
        return y0 < u["y"] < y1 and max(u["x"], v["x"]) > x0 and min(u["x"], v["x"]) < x1
    return x0 < u["x"] < x1 and max(u["y"], v["y"]) > y0 and min(u["y"], v["y"]) < y1


def _span(u, v, p, q, axis):
    lo = max(min(u[axis], v[axis]), min(p[axis], q[axis]))
    hi = min(max(u[axis], v[axis]), max(p[axis], q[axis]))
    return hi - lo


def assert_clean(shapes, conns, routes):
    """An independent check of finished routes (does not call route_problems)."""
    box = {s["id"]: (s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"]) for s in shapes}
    segs = {}
    for c in conns:
        r = routes[c["id"]]
        assert r["ok"], c["id"]
        ends = {c["from"]["shape"], c["to"]["shape"]}
        pts = r["points"]
        segs[c["id"]] = list(zip(pts, pts[1:]))
        for u, v in segs[c["id"]]:
            assert u["x"] == v["x"] or u["y"] == v["y"], "orthogonal only"
            for sid, b in box.items():
                if sid not in ends:
                    assert not _inside(u, v, b), f"{c['id']} runs through {sid}"
        lab = r["label"]
        for sid, b in box.items():
            assert not (lab["x"] - lab["w"] / 2 < b[2] and lab["x"] + lab["w"] / 2 > b[0]
                        and lab["y"] - lab["h"] / 2 < b[3] and lab["y"] + lab["h"] / 2 > b[1]), \
                f"label of {c['id']} sits on {sid}"
    ids = list(segs)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            for u, v in segs[a]:
                for p, q in segs[b]:
                    if u["y"] == v["y"] == p["y"] == q["y"]:
                        assert _span(u, v, p, q, "x") <= 1, (a, b)
                    if u["x"] == v["x"] == p["x"] == q["x"]:
                        assert _span(u, v, p, q, "y") <= 1, (a, b)


def test_the_old_elbow_really_ran_a_skipping_link_through_the_block_between():
    # root cause: ranks became columns at x = 80 + 240k, so esd -> mcu "H midX V y2 H x2" passed the ldo block
    legacy = diagram_route._legacy({"id": "k", "route": "elbow", "from": {"shape": "esd", "side": "right"},
                                    "to": {"shape": "mcu", "side": "left"}},
                                   {"x": 480.0, "y": 114.0}, {"x": 800.0, "y": 130.0})
    ldo = (560.0, 80.0, 720.0, 148.0)
    assert any(diagram_route._hits(u, v, ldo) for u, v in diagram_route._segs(legacy))


def test_auto_layout_of_the_seven_block_diagram_is_clean():
    shapes, conns = fixture()
    report = []
    store._auto_layout(shapes, conns, [], report)
    assert report == []
    assert diagram_route.route_problems(shapes, conns) == []
    assert_clean(shapes, conns, diagram_route.route_connectors(shapes, conns))
    # columns by depth are kept: sources left of the hub, what it drives on the right
    x = {s["id"]: s["x"] for s in shapes}
    assert x["usb"] < x["esd"] < x["ldo"] < x["mcu"] < x["sht"] == x["led"]


def test_links_on_one_block_side_get_distinct_ports():
    shapes, conns = fixture()
    store._auto_layout(shapes, conns, [], [])
    routes = diagram_route.route_connectors(shapes, conns)
    into_mcu = [routes[c]["p2"] for c in ("conn_3", "conn_4", "conn_7")]
    assert len({p["y"] for p in into_mcu}) == 3
    mcu = next(s for s in shapes if s["id"] == "mcu")
    assert all(mcu["y"] < p["y"] < mcu["y"] + mcu["h"] for p in into_mcu)
    assert len({routes[c]["p1"]["y"] for c in ("conn_5", "conn_6")}) == 2


def test_the_router_alone_detours_a_link_around_a_block_in_its_way():
    # even a hand-made layout (a block between the ends) is drawn around the block
    shapes = [{"id": i, "type": "block", "x": x, "y": 100.0, "w": 160.0, "h": 68.0}
              for i, x in (("a", 0.0), ("b", 240.0), ("c", 480.0))]
    conns = [{"id": "k", "from": {"shape": "a", "side": "right"}, "to": {"shape": "c", "side": "left"}, "label": "SPI"}]
    assert_clean(shapes, conns, diagram_route.route_connectors(shapes, conns))


def test_a_layout_that_cannot_be_clean_is_reported(monkeypatch):
    shapes, conns = fixture()
    monkeypatch.setattr(diagram_route, "route_problems", lambda s, c: ["conn_4 crosses ldo"])
    report = []
    store._auto_layout(shapes, conns, [], report)
    assert report == ["conn_4 crosses ldo"]


def test_apply_diagram_edit_auto_layout_is_clean_and_warns_when_not(empty, monkeypatch):
    ops = [{"op": "add_shape", "id": i, "text": i, "x": 5, "y": 5} for i in ("usb", "esd", "ldo", "mcu", "sht", "led", "btn")]
    ops += [{"op": "add_connector", "id": c, "from": a, "to": b, "label": lab} for c, a, b, lab in LINKS]
    res = store.apply_diagram_edit(empty, ops + [{"op": "auto_layout"}])
    assert "layout_warning" not in res
    d = store.load_idea_working(empty)["diagram"]
    assert diagram_route.route_problems(d["shapes"], d["connectors"]) == []
    monkeypatch.setattr(diagram_route, "route_problems", lambda s, c: ["conn_4 crosses ldo"])
    res = store.apply_diagram_edit(empty, [{"op": "auto_layout"}])
    assert "conn_4 crosses ldo" in res["layout_warning"]


# ---------------------------------------------------------------- the same geometry through ui/diagram.js

def _node():
    exe = os.environ.get("NODE_BIN") or shutil.which("node")
    if not exe:
        pytest.skip("node is not installed")
    return exe


def run_js_router(shapes, conns):
    code = ("const D=require(process.argv[1]);const i=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(D.routeConnectors(i.shapes,i.connectors)));")
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")  # lets a node-flavoured Electron binary act as node
    r = subprocess.run([_node(), "-e", code, str(REPO / "ui" / "diagram.js")],
                       input=json.dumps({"shapes": shapes, "connectors": conns}),
                       capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _norm(routes):
    return json.loads(json.dumps(routes))


def test_js_router_is_clean_on_the_seven_block_diagram_and_matches_python():
    shapes, conns = fixture()
    store._auto_layout(shapes, conns, [], [])
    js = run_js_router(shapes, conns)
    assert_clean(shapes, conns, js)
    assert js == _norm(diagram_route.route_connectors(shapes, conns))


def test_js_router_matches_python_on_a_hand_made_row():
    shapes = [{"id": i, "type": "block", "x": x, "y": 100.0, "w": 160.0, "h": 68.0}
              for i, x in (("a", 0.0), ("b", 240.0), ("c", 480.0), ("d", 720.0))]
    conns = [{"id": "k1", "from": {"shape": "a", "side": "right"}, "to": {"shape": "c", "side": "left"}, "label": "SPI"},
             {"id": "k2", "from": {"shape": "a", "side": "right"}, "to": {"shape": "d", "side": "left"}, "label": "I2C"},
             {"id": "k3", "from": {"shape": "d", "side": "bottom"}, "to": {"shape": "b", "side": "top"}}]
    assert run_js_router(shapes, conns) == _norm(diagram_route.route_connectors(shapes, conns))


def test_the_renderer_uses_the_router_and_keeps_the_label_where_it_is_drawn():
    src = (REPO / "ui" / "diagram.js").read_text(encoding="utf-8")
    assert "routeConnectors(this.data.shapes, this.data.connectors, this._routeOpts)" in src
    assert "routePathD(rt.points)" in src
    assert "rt.label" in src[src.index("connectorLabelPoint(c, p1, p2) {"):][:300]


def _close(a, b, tol=1e-9):
    """Equal up to float noise (sin / cos of the star differ in the last digit between engines)."""
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= tol
    return a == b


def run_js(code, payload):
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    full = "const D=require(process.argv[1]);const i=JSON.parse(require('fs').readFileSync(0,'utf8'));" + code
    r = subprocess.run([_node(), "-e", full, str(REPO / "ui" / "diagram.js")], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


SHAPE_TYPES = ["rectangle", "block", "rounded_rectangle", "pill", "ellipse", "diamond", "triangle", "parallelogram",
               "hexagon", "octagon", "arrow_right", "double_arrow", "cloud", "note_brace", "cylinder", "star",
               "speech_callout", "database", "no_such_shape"]
POINTS = ["top", "right", "bottom", "left", "top-left", "top-right", "bottom-right", "bottom-left", "nonsense"]


def test_python_anchor_is_the_outline_point_the_browser_uses_for_every_shape_and_point():
    shapes = [{"id": f"s{n}", "type": t, "x": 13.0, "y": 29.0, "w": 150.0, "h": 70.0} for n, t in enumerate(SHAPE_TYPES)]
    js = run_js("process.stdout.write(JSON.stringify(i.shapes.map(s=>i.points.map(p=>D.anchorPoint(s,p)))));",
                {"shapes": shapes, "points": POINTS})
    for s, row in zip(shapes, js):
        for name, want in zip(POINTS, row):
            assert _close(diagram_route._anchor(s, name), want), (s["type"], name)
    # a speech callout's body is 0.76 h tall: its bottom side is not the bottom of the box
    call = diagram_route._anchor({"type": "speech_callout", "x": 0, "y": 0, "w": 100, "h": 100}, "bottom")
    assert call["y"] == 76.0


def test_js_router_matches_python_on_non_rectangle_shapes():
    types = ["ellipse", "diamond", "speech_callout", "cylinder", "star", "hexagon", "rounded_rectangle", "rectangle"]
    shapes = [{"id": f"n{k}", "type": t, "x": 40.0 + 230.0 * (k % 4), "y": 40.0 + 150.0 * (k // 4), "w": 150.0, "h": 70.0}
              for k, t in enumerate(types)]
    sides = ["right", "left", "top", "bottom"]
    pairs = [(0, 1), (1, 2), (2, 7), (4, 6), (5, 3), (0, 5), (3, 7), (6, 1)]
    conns = [{"id": f"k{k}", "from": {"shape": f"n{a}", "point": sides[k % 4]},
              "to": {"shape": f"n{b}", "point": sides[(k + 1) % 4 if k % 3 else (k + 2) % 4]}, "label": "bus"}
             for k, (a, b) in enumerate(pairs)]
    py = diagram_route.route_connectors(shapes, conns)
    js = run_js("process.stdout.write(JSON.stringify(D.routeConnectors(i.shapes,i.connectors)));",
                {"shapes": shapes, "connectors": conns})
    assert _close(js, _norm(py))


def test_label_width_counts_code_points_in_both_routers():
    label = "LED \U0001F600\U0001F600 bus"  # two emoji: 2 code points, 4 UTF-16 units
    shapes = [{"id": "a", "type": "block", "x": 0.0, "y": 0.0, "w": 160.0, "h": 68.0},
              {"id": "b", "type": "block", "x": 400.0, "y": 0.0, "w": 160.0, "h": 68.0}]
    conns = [{"id": "k", "from": {"shape": "a", "side": "right"}, "to": {"shape": "b", "side": "left"}, "label": label}]
    py = diagram_route.route_connectors(shapes, conns)
    assert py["k"]["label"]["w"] == max(len(label) * 7.5 + 16, 32) == diagram_route.label_width(label)
    assert run_js_router(shapes, conns) == _norm(py)


def _big(n, links, seed=1):
    rnd = random.Random(seed)
    shapes = [{"id": f"b{i}", "type": "rectangle", "x": 0.0, "y": 0.0, "w": 140.0, "h": 60.0} for i in range(n)]
    conns = []
    for j in range(links):
        a, b = rnd.sample(range(n), 2)
        conns.append({"id": f"c{j}", "from": {"shape": f"b{a}", "point": "right"},
                      "to": {"shape": f"b{b}", "point": "left"}, "label": "SPI bus"})
    return shapes, conns


def test_auto_layout_of_a_big_diagram_stays_fast():
    # was 10 s at 50 blocks / 80 links, inside the HTTP request of the agent's edit
    shapes, conns = _big(50, 80)
    t = time.perf_counter()
    store._auto_layout(shapes, conns, [], [])
    assert time.perf_counter() - t < 20.0      # a hang guard (it was 10 s before the fix, it measures about 0.2 s): not a speed test of the CI runner
    shapes, conns = _big(15, 22)
    t = time.perf_counter()
    store._auto_layout(shapes, conns, [], [])
    assert time.perf_counter() - t < 6.0


def test_js_router_of_a_big_diagram_is_fast_enough_to_run_per_frame():
    shapes = [{"id": f"b{i}", "type": "rectangle", "x": (i % 6) * 240.0 + 80, "y": (i // 6) * 120.0 + 80,
               "w": 140.0, "h": 60.0} for i in range(50)]
    rnd = random.Random(3)
    conns = []
    for j in range(80):
        a, b = rnd.sample(range(50), 2)
        conns.append({"id": f"c{j}", "from": {"shape": f"b{a}", "point": "right"},
                      "to": {"shape": f"b{b}", "point": "left"}, "label": "SPI bus"})
    ms = run_js("const t=Date.now();for(let k=0;k<3;k++)D.routeConnectors(i.shapes,i.connectors);"
                "process.stdout.write(JSON.stringify((Date.now()-t)/3));", {"shapes": shapes, "connectors": conns})
    assert ms < 5000      # a hang guard (it measures about 100-300 ms): a slow CI runner must not fail a router that works; the results are asserted by the tests around it


def test_dragging_a_block_routes_again_only_the_links_on_it_and_the_drop_routes_all():
    shapes, conns = fixture()
    store._auto_layout(shapes, conns, [], [])
    moved = [dict(s, y=s["y"] + 15.0) if s["id"] == "sht" else s for s in shapes]
    res = run_js("const full=D.routeConnectors(i.shapes,i.connectors);"
                 "const part=D.routeConnectors(i.moved,i.connectors,{only:new Set(['sht']),prev:full});"
                 "const drop=D.routeConnectors(i.moved,i.connectors);"
                 "process.stdout.write(JSON.stringify({full,part,drop}));",
                 {"shapes": shapes, "moved": moved, "connectors": conns})
    for c in conns:
        if "sht" in (c["from"]["shape"], c["to"]["shape"]):
            assert res["part"][c["id"]]["p2"] == res["drop"][c["id"]]["p2"] != res["full"][c["id"]]["p2"]
        else:
            assert res["part"][c["id"]]["points"] == res["full"][c["id"]]["points"]
    assert res["drop"] == _norm(diagram_route.route_connectors(moved, conns))


def test_a_drag_redraws_once_per_animation_frame_and_the_drop_cancels_it():
    src = (REPO / "ui" / "diagram.js").read_text(encoding="utf-8")
    drag = src[src.index("    doDragItems(pos) {"):src.index("    renderDuringDrag(movedIds) {")]
    assert "this.renderDuringDrag(" in drag and "this.render();" not in drag
    assert "requestAnimationFrame" in src[src.index("    renderDuringDrag(movedIds) {"):][:500]
    up = src[src.index("    onMouseUp(e) {"):][:2200]
    assert up.count("this.cancelDragRender();") == 2
