"""
Tests for Miro-like Block Diagram Editor (Idea stage):
- Migration old -> new (blocks/links -> shapes/connectors/frames) with auto-layout
- Save/load round trip
- Server-side validation rejects bad input (unknown types, length caps, non-finite numbers, count caps)
- Static checks that ui/diagram.js contains all listed tools, shortcuts, and undo/redo
- Agent proposal flow (idea.diagram proposals approve/reject)
- Static route in serve.py serving ui/diagram.js without path traversal
"""
import json
import math
import pathlib
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import model
import store

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def server(home, monkeypatch):
    """Real server handler on an ephemeral port."""
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post_json(base, path, body, project):
    url = f"{base}{path}{'&' if '?' in path else '?'}project={project}"
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get_raw(base, path):
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


# ---------------------------------------------------------------- migration

def test_migration_old_to_new_with_autolayout():
    """Old blocks without x/y get auto layout, and links migrate to connectors."""
    old_idea = {
        "goal": "Smart Sensor Hub",
        "blocks": [
            {"id": "mcu", "label": "STM32F401", "role": "Main MCU", "domain": "mcu"},
            {"id": "pwr", "label": "3.3V LDO", "role": "Regulator", "domain": "power", "x": 50, "y": 60},
            {"id": "sensor", "label": "BME280", "role": "Environmental Sensor", "domain": "sensing"},
        ],
        "links": [
            ["pwr", "mcu", "3.3V Power", False],
            {"from": "mcu", "to": "sensor", "label": "I2C Bus", "safety": True},
        ]
    }

    migrated = store.migrate_idea_diagram(old_idea)
    diag = migrated["diagram"]

    assert "shapes" in diag and "connectors" in diag and "frames" in diag
    shapes = diag["shapes"]
    connectors = diag["connectors"]

    assert len(shapes) == 3
    # Check shape fields
    for s in shapes:
        assert "id" in s
        assert s["type"] in store.VALID_SHAPE_TYPES
        assert isinstance(s["x"], (int, float)) and math.isfinite(s["x"])
        assert isinstance(s["y"], (int, float)) and math.isfinite(s["y"])
        assert s["w"] > 0 and s["h"] > 0
        assert "text" in s
        assert "fill" in s and "stroke" in s
        assert s["strokeStyle"] in store.VALID_STROKE_STYLES
        assert s["fontSize"] in store.VALID_FONT_SIZES
        assert isinstance(s["bold"], bool)
        assert s["align"] in store.VALID_ALIGN

    # Block 1 had no x/y -> auto layout must give non-null, finite values
    s_mcu = next(s for s in shapes if s["id"] == "mcu")
    assert s_mcu["x"] is not None and s_mcu["y"] is not None
    assert "STM32F401" in s_mcu["text"]
    assert s_mcu["domain"] == "mcu"

    # Block 2 had explicit x=50, y=60
    s_pwr = next(s for s in shapes if s["id"] == "pwr")
    assert s_pwr["x"] == 50.0 and s_pwr["y"] == 60.0

    # Check connectors
    assert len(connectors) == 2
    c0 = connectors[0]
    assert c0["from"]["shape"] == "pwr"
    assert c0["to"]["shape"] == "mcu"
    assert c0["label"] == "3.3V Power"
    assert c0["style"] == "solid"

    c1 = connectors[1]
    assert c1["from"]["shape"] == "mcu"
    assert c1["to"]["shape"] == "sensor"
    assert c1["label"] == "I2C Bus"
    assert c1["style"] == "dashed"  # safety=True migrates to dashed


# ---------------------------------------------------------------- round trip

def test_save_load_round_trip(empty):
    """Shapes, connectors, and frames persist and round-trip cleanly through store."""
    diagram_data = {
        "shapes": [
            {
                "id": "blk1",
                "type": "block",
                "x": 120.0,
                "y": 80.0,
                "w": 180.0,
                "h": 70.0,
                "text": "Main Controller\nESP32-S3",
                "fill": "#ebf5fb",
                "stroke": "#2980b9",
                "strokeStyle": "solid",
                "strokeWidth": 2.0,
                "fontSize": "M",
                "bold": True,
                "align": "center",
                "z": 1.0,
                "locked": False,
                "domain": "mcu",
            },
            {
                "id": "note1",
                "type": "sticky",
                "x": 340.0,
                "y": 90.0,
                "w": 140.0,
                "h": 140.0,
                "text": "Check ADC range",
                "fill": "#fef9c3",
                "stroke": "#ca8a04",
                "strokeStyle": "solid",
                "strokeWidth": 1.5,
                "fontSize": "S",
                "bold": False,
                "align": "left",
                "z": 2.0,
                "locked": False,
            }
        ],
        "connectors": [
            {
                "id": "c1",
                "from": {"shape": "blk1", "side": "right"},
                "to": {"shape": "note1", "side": "left"},
                "label": "note link",
                "stroke": "#64748b",
                "style": "dashed",
                "arrows": "end",
                "route": "elbow",
            }
        ],
        "frames": [
            {
                "id": "f1",
                "x": 80.0,
                "y": 40.0,
                "w": 500.0,
                "h": 260.0,
                "title": "Digital Domain",
                "stroke": "#94a3b8",
            }
        ]
    }

    idea = store.load_idea(empty)
    idea["diagram"] = diagram_data
    store.save_idea(empty, idea)

    # Reload from disk
    reloaded = store.load_idea(empty)
    r_diag = reloaded.get("diagram", {})

    assert len(r_diag["shapes"]) == 2
    assert len(r_diag["connectors"]) == 1
    assert len(r_diag["frames"]) == 1

    r_s0 = r_diag["shapes"][0]
    assert r_s0["id"] == "blk1"
    assert r_s0["text"] == "Main Controller\nESP32-S3"
    assert r_s0["fill"] == "#ebf5fb"
    assert r_s0["x"] == 120.0 and r_s0["y"] == 80.0

    r_c0 = r_diag["connectors"][0]
    assert r_c0["id"] == "c1"
    assert r_c0["from"]["shape"] == "blk1"
    assert r_c0["to"]["shape"] == "note1"
    assert r_c0["route"] == "elbow"

    r_f0 = r_diag["frames"][0]
    assert r_f0["id"] == "f1"
    assert r_f0["title"] == "Digital Domain"

    # Also verify model.build returns diagram
    m = model.build(empty)
    assert "diagram" in m
    assert len(m["diagram"]["shapes"]) == 2


# ---------------------------------------------------------------- validation

def test_validation_rejects_unknown_shape_type():
    with pytest.raises(ValueError, match="unknown shape type"):
        store.validate_diagram({
            "shapes": [{"id": "s1", "type": "pentagon", "x": 0, "y": 0, "w": 100, "h": 50}]
        })


def test_validation_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="must be finite number"):
        store.validate_diagram({
            "shapes": [{"id": "s1", "type": "block", "x": float("inf"), "y": 0, "w": 100, "h": 50}]
        })

    with pytest.raises(ValueError, match="must be finite number"):
        store.validate_diagram({
            "shapes": [{"id": "s1", "type": "block", "x": 0, "y": float("nan"), "w": 100, "h": 50}]
        })


def test_validation_rejects_string_length_overflow():
    with pytest.raises(ValueError, match="text must be string <= 2000 chars"):
        store.validate_diagram({
            "shapes": [{
                "id": "s1",
                "type": "block",
                "x": 0,
                "y": 0,
                "w": 100,
                "h": 50,
                "text": "A" * 2001
            }]
        })

    with pytest.raises(ValueError, match="label must be string <= 500 chars"):
        store.validate_diagram({
            "connectors": [{
                "id": "c1",
                "from": {"x": 0, "y": 0},
                "to": {"x": 10, "y": 10},
                "label": "B" * 501
            }]
        })


def test_validation_rejects_count_caps():
    many_shapes = [{"id": f"s{i}", "type": "block", "x": 0, "y": 0, "w": 10, "h": 10} for i in range(501)]
    with pytest.raises(ValueError, match="too many shapes"):
        store.validate_diagram({"shapes": many_shapes})

    many_frames = [{"id": f"f{i}", "x": 0, "y": 0, "w": 10, "h": 10, "title": "t"} for i in range(101)]
    with pytest.raises(ValueError, match="too many frames"):
        store.validate_diagram({"frames": many_frames})


def test_validation_rejects_invalid_connector_endpoints():
    with pytest.raises(ValueError, match="must have shape or x,y"):
        store.validate_diagram({
            "connectors": [{
                "id": "c1",
                "from": {"invalid": 123},
                "to": {"x": 10, "y": 10}
            }]
        })


# ---------------------------------------------------------------- static checks

def test_static_checks_diagram_js():
    """Verify ui/diagram.js exists, has all tools listed in prompt, and undo/redo."""
    diagram_path = REPO / "ui" / "diagram.js"
    assert diagram_path.is_file(), "ui/diagram.js must exist"
    content = diagram_path.read_text(encoding="utf-8")

    # Required tools in toolbar: Select (V), Hand (H), Block (B), Ellipse, Diamond,
    # Sticky note (N), Text (T), Connector/line (L), Frame (F)
    tools = [
        ("select", "Select", "V"),
        ("hand", "Hand", "H"),
        ("block", "Block", "B"),
        ("ellipse", "Ellipse"),
        ("diamond", "Diamond"),
        ("sticky", "Sticky", "N"),
        ("text", "Text", "T"),
        ("connector", "Connector", "L"),
        ("frame", "Frame", "F"),
    ]
    for t_spec in tools:
        found = False
        for token in t_spec:
            if token.lower() in content.lower():
                found = True
                break
        assert found, f"Tool {t_spec} must be present in ui/diagram.js"

    # Undo / Redo support
    assert "undo" in content.lower(), "Undo support required in diagram.js"
    assert "redo" in content.lower(), "Redo support required in diagram.js"
    assert "ctrl" in content.lower() or "meta" in content.lower(), "Keyboard shortcut handler required in diagram.js"

    # Other required Miro editor features
    assert "fit" in content.lower(), "Fit content function required in diagram.js"
    assert "snap" in content.lower(), "Snap to grid feature required in diagram.js"
    assert "grid" in content.lower(), "Dot grid feature required in diagram.js"
    assert "template" in content.lower(), "Template loader required in diagram.js"


# ---------------------------------------------------------------- proposal flow

def test_agent_proposal_flow(lte):
    """Proposals with kind=idea_diagram create pending proposal, approve updates diagram, reject discards."""
    proposed_diagram = {
        "shapes": [
            {
                "id": "prop_mcu",
                "type": "block",
                "x": 200.0,
                "y": 150.0,
                "w": 180.0,
                "h": 80.0,
                "text": "Proposed MCU Upgrade\nSTM32H7",
                "fill": "#ebf5fb",
                "stroke": "#2980b9",
                "strokeStyle": "solid",
                "strokeWidth": 2.0,
                "fontSize": "M",
                "bold": True,
                "align": "center",
                "z": 1.0,
                "locked": False,
            }
        ],
        "connectors": [],
        "frames": []
    }

    # Propose diagram update
    rec = store.propose_idea_diagram(lte, {"diagram": proposed_diagram}, reason="Upgrade MCU block")
    pid = rec["id"]
    assert rec["kind"] == "idea_diagram"
    assert rec["status"] == "pending"

    # Before decision, idea does not have the proposed shape
    idea_before = store.load_idea(lte)
    assert not any(s.get("id") == "prop_mcu" for s in idea_before.get("diagram", {}).get("shapes", []))

    # Reject proposal
    store.decide(lte, pid, "rejected")
    idea_after_reject = store.load_idea(lte)
    assert not any(s.get("id") == "prop_mcu" for s in idea_after_reject.get("diagram", {}).get("shapes", []))

    # Propose again and approve
    rec2 = store.propose_idea_diagram(lte, {"diagram": proposed_diagram}, reason="Upgrade MCU block approved")
    pid2 = rec2["id"]
    store.decide(lte, pid2, "approved")

    idea_after_approve = store.load_idea(lte)
    shapes_after = idea_after_approve.get("diagram", {}).get("shapes", [])
    assert any(s.get("id") == "prop_mcu" for s in shapes_after)


# ---------------------------------------------------------------- server endpoints

def test_server_static_route_and_no_path_traversal(server):
    """serve.py serves ui/diagram.js via whitelist and rejects path traversal."""
    status, ctype, body = get_raw(server, "/ui/diagram.js")
    assert status == 200
    assert "javascript" in ctype
    assert b"DiagramEditor" in body

    # Alias /diagram.js
    status2, _, body2 = get_raw(server, "/diagram.js")
    assert status2 == 200

    # Path traversal rejected
    status_bad, _, _ = get_raw(server, "/ui/../scripts/serve.py")
    assert status_bad in (403, 404)


def test_server_idea_diagram_api_endpoints(server, empty):
    """POST /api/idea/diagram validates and saves diagram state."""
    valid_payload = {
        "shapes": [
            {
                "id": "s_api",
                "type": "block",
                "x": 50.0,
                "y": 60.0,
                "w": 120.0,
                "h": 50.0,
                "text": "API Block",
                "fill": "#ffffff",
                "stroke": "#2980b9",
                "strokeStyle": "solid",
                "strokeWidth": 2.0,
                "fontSize": "M",
                "bold": True,
                "align": "center",
                "z": 1.0,
                "locked": False,
            }
        ],
        "connectors": [],
        "frames": []
    }

    # Valid diagram save
    code, res = post_json(server, "/api/idea/diagram", valid_payload, empty)
    assert code == 200
    assert "idea" in res
    assert res["idea"]["diagram"]["shapes"][0]["id"] == "s_api"

    # Bad diagram save -> rejected with 400
    bad_payload = {
        "shapes": [
            {
                "id": "s_bad",
                "type": "nonexistent_shape_type",
                "x": 0.0,
                "y": 0.0,
                "w": 100.0,
                "h": 50.0
            }
        ]
    }
    code_bad, res_bad = post_json(server, "/api/idea/diagram", bad_payload, empty)
    assert code_bad == 400
    assert "error" in res_bad
