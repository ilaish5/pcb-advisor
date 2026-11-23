"""The block diagram must not miswire: no link through a block it does not join, no two links on one line, no label
on a block. Server layout (store._auto_layout + diagram_route) and the browser router (ui/diagram.js routeConnectors)
follow the same rules; the node tests run the JS on the same geometry and compare."""
import json
import os
import pathlib
import shutil
import subprocess

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
    assert "routeConnectors(this.data.shapes, this.data.connectors)" in src
    assert "routePathD(rt.points)" in src
    assert "rt.label" in src[src.index("connectorLabelPoint(c, p1, p2) {"):][:300]
