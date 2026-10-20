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
import re
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

    idea = store.load_idea_working(empty)
    idea["diagram"] = diagram_data
    store.save_idea(empty, idea)

    # Reload from disk
    reloaded = store.load_idea_working(empty)
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


@pytest.mark.parametrize("injected", [
    '#fff" onmouseover="alert(1)',
    "#fff' onmouseover='alert(1)",
    "<script>alert(1)</script>",
    '#fff">',
    "blue<script>",
])
def test_validation_rejects_injected_fill(injected):
    with pytest.raises(ValueError, match="invalid fill"):
        store.validate_diagram({
            "shapes": [{"id": "s1", "type": "block", "x": 0, "y": 0, "w": 100, "h": 50, "fill": injected}]
        })


@pytest.mark.parametrize("injected", [
    '#000" onmouseover="alert(1)',
    "#000' onmouseover='alert(1)",
    "<script>alert(1)</script>",
    '#000">',
])
def test_validation_rejects_injected_stroke(injected):
    with pytest.raises(ValueError, match="invalid stroke"):
        store.validate_diagram({
            "shapes": [{"id": "s1", "type": "block", "x": 0, "y": 0, "w": 100, "h": 50, "stroke": injected}]
        })
    with pytest.raises(ValueError, match="invalid stroke"):
        store.validate_diagram({
            "connectors": [{"id": "c1", "from": {"x": 0, "y": 0}, "to": {"x": 10, "y": 10}, "stroke": injected}]
        })
    with pytest.raises(ValueError, match="invalid stroke"):
        store.validate_diagram({
            "frames": [{"id": "f1", "x": 0, "y": 0, "w": 100, "h": 50, "stroke": injected}]
        })


@pytest.mark.parametrize("injected", [
    's1" onmouseover="alert(1)',
    "s1' onmouseover='alert(1)",
    "<script>alert(1)</script>",
    's1">',
    "s 1",
])
def test_validation_rejects_injected_id(injected):
    with pytest.raises(ValueError, match="invalid shape id"):
        store.validate_diagram({
            "shapes": [{"id": injected, "type": "block", "x": 0, "y": 0, "w": 100, "h": 50}]
        })
    with pytest.raises(ValueError, match="invalid connector id"):
        store.validate_diagram({
            "connectors": [{"id": injected, "from": {"x": 0, "y": 0}, "to": {"x": 10, "y": 10}}]
        })
    with pytest.raises(ValueError, match="invalid frame id"):
        store.validate_diagram({
            "frames": [{"id": injected, "x": 0, "y": 0, "w": 100, "h": 50}]
        })


def test_migration_replaces_bad_ids_and_colours():
    old_idea = {
        "blocks": [
            {"id": 'bad"id', "label": "Bad ID Block", "domain": "mcu", "fill": '#fff" onmouseover="alert(1)', "stroke": '<script>'},
            {"id": "valid_id", "label": "Valid Block", "domain": "invalid_domain", "fill": "valid_color", "stroke": "bad'stroke"},
        ],
        "links": [
            ['bad"id', "valid_id", "link1"],
        ]
    }
    migrated = store.migrate_idea_diagram(old_idea)
    diag = migrated["diagram"]
    assert store.validate_diagram(diag)  # must pass validate_diagram
    assert len(diag["shapes"]) == 2
    s0 = diag["shapes"][0]
    assert s0["id"] == "block_0"
    assert s0["fill"] == store.DOMAIN_COLORS["mcu"]["fill"]
    assert s0["stroke"] == store.DOMAIN_COLORS["mcu"]["stroke"]
    s1 = diag["shapes"][1]
    assert s1["id"] == "valid_id"
    # bad fill/stroke replaced by domain default
    assert s1["fill"] == "#f1f5f9"
    assert s1["stroke"] == "#64748b"
    c0 = diag["connectors"][0]
    assert c0["from"]["shape"] == "block_0"
    assert c0["to"]["shape"] == "valid_id"


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

    # Security hardening checks
    assert "sanitizemodel" in content.lower(), "sanitizeModel function required in diagram.js"
    assert "&#39;" in content, "escapeHtml in diagram.js must escape single quote with &#39;"


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
    idea_before = store.load_idea_working(lte)
    assert not any(s.get("id") == "prop_mcu" for s in idea_before.get("diagram", {}).get("shapes", []))

    # Reject proposal
    store.decide(lte, pid, "rejected")
    idea_after_reject = store.load_idea_working(lte)
    assert not any(s.get("id") == "prop_mcu" for s in idea_after_reject.get("diagram", {}).get("shapes", []))

    # Propose again and approve
    rec2 = store.propose_idea_diagram(lte, {"diagram": proposed_diagram}, reason="Upgrade MCU block approved")
    pid2 = rec2["id"]
    store.decide(lte, pid2, "approved")

    idea_after_approve = store.load_idea_working(lte)
    shapes_after = idea_after_approve.get("diagram", {}).get("shapes", [])
    assert any(s.get("id") == "prop_mcu" for s in shapes_after)


def test_point_ends_survive_save_and_load(empty):
    shape = {"type": "ellipse", "x": 0.0, "y": 0.0, "w": 160.0, "h": 80.0, "text": ""}
    idea = store.load_idea_working(empty)
    idea["diagram"] = {
        "shapes": [dict(shape, id="a"), dict(shape, id="b", x=300.0)],
        "connectors": [{"id": "c1", "from": {"shape": "a", "point": "bottom"},
                        "to": {"shape": "b", "point": "top-left"}}],
        "frames": [],
    }
    store.save_idea(empty, idea)
    c = store.load_idea_working(empty)["diagram"]["connectors"][0]
    assert c["from"] == {"shape": "a", "point": "bottom"}
    assert c["to"] == {"shape": "b", "point": "top-left"}


def test_proposals_in_the_same_millisecond_get_distinct_ids(lte, monkeypatch):
    import datetime as real_dt
    fixed = real_dt.datetime(2026, 10, 13, 21, 0, 0, 123456)

    class FrozenDatetime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(store.dt, "datetime", FrozenDatetime)
    first = store.propose_idea_diagram(lte, {"diagram": {"shapes": [], "connectors": [], "frames": []}})
    second = store.propose_idea_diagram(lte, {"diagram": {"shapes": [], "connectors": [], "frames": []}})
    assert first["id"] != second["id"]
    store.decide(lte, first["id"], "rejected")
    store.decide(lte, second["id"], "approved")


@pytest.mark.parametrize("bad_field,bad_val", [
    ("fill", '#fff" onmouseover="alert(1)'),
    ("stroke", '#000<script>alert(1)</script>'),
    ("id", 's1" onclick="alert(1)'),
])
def test_proposal_approval_with_injected_value_refused_and_idea_unchanged(empty, bad_field, bad_val):
    initial_idea = store.load_idea_working(empty)
    store.save_idea(empty, initial_idea)
    idea_path = store.pdir(empty) / "idea.json"
    idea_before = idea_path.read_text(encoding="utf-8")

    shape_dict = {
        "id": "bad_shape" if bad_field != "id" else bad_val,
        "type": "block",
        "x": 100.0,
        "y": 100.0,
        "w": 160.0,
        "h": 68.0,
        "text": "Malicious Block",
        "fill": "#ffffff" if bad_field != "fill" else bad_val,
        "stroke": "#2980b9" if bad_field != "stroke" else bad_val,
    }
    rec = store.propose_idea_diagram(
        empty,
        {"diagram": {"shapes": [shape_dict], "connectors": [], "frames": []}},
        reason="Agent proposed injected block"
    )
    pid = rec["id"]

    with pytest.raises(ValueError):
        store.decide(empty, pid, "approved")

    idea_after = idea_path.read_text(encoding="utf-8")
    assert idea_after == idea_before

    props = store.proposals(empty)
    target_prop = next(p for p in props if p["id"] == pid)
    assert target_prop["status"] != "approved"


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


# ---------------------------------------------------------------- icon-only toolbar & 16 shapes

SIXTEEN_SHAPE_TYPES = [
    "rectangle", "ellipse", "diamond", "triangle",
    "rounded_rectangle", "cloud", "star", "arrow_right",
    "parallelogram", "hexagon", "octagon", "double_arrow",
    "speech_callout", "cylinder", "process", "note_brace",
]


def test_rail_buttons_aria_labels_and_no_visible_text_labels():
    """Verify left rail buttons have aria-labels and no visible text labels."""
    diagram_path = REPO / "ui" / "diagram.js"
    content = diagram_path.read_text(encoding="utf-8")

    # Match buttons in the left rail
    rail_match = re.search(r'rail\.innerHTML\s*=\s*`(.*?)`;', content, re.DOTALL)
    assert rail_match, "Left rail HTML must exist in diagram.js"
    rail_html = rail_match.group(1)

    buttons = re.findall(r'<button[^>]*class="[^"]*diag-rail-btn[^"]*"[^>]*>.*?</button>', rail_html, re.DOTALL)
    assert len(buttons) >= 9, f"Rail must have tool and action buttons, found {len(buttons)}"

    for b in buttons:
        assert 'aria-label="' in b, f"Rail button must have aria-label: {b}"
        assert 'title="' in b, f"Rail button must have title: {b}"
        # Strip the icons (an inline <svg>, or a ${getIconSvg('name', size)} call that draws one) and tags to check for any visible text
        stripped = re.sub(r'<svg.*?</svg>', '', b, flags=re.DOTALL)
        stripped = re.sub(r'\$\{getIconSvg\([^)]*\)\}', '', stripped)
        text_content = re.sub(r'<[^>]+>', '', stripped).strip()
        assert not text_content, f"Rail button must not contain visible text label: {text_content!r}"


def test_16_shape_types_exist_in_diagram_js_and_valid_shape_types():
    """Verify all 16 shape types exist in ui/diagram.js and store.VALID_SHAPE_TYPES."""
    diagram_path = REPO / "ui" / "diagram.js"
    content = diagram_path.read_text(encoding="utf-8")

    for st in SIXTEEN_SHAPE_TYPES:
        assert st in store.VALID_SHAPE_TYPES, f"{st} must be in store.VALID_SHAPE_TYPES"
        assert f"'{st}'" in content or f'"{st}"' in content, f"{st} must exist in ui/diagram.js"


def test_context_bar_has_fill_border_line_style_and_arrow_controls():
    """Verify context bar has fill, border, 3 line styles, and 3 arrowheads."""
    diagram_path = REPO / "ui" / "diagram.js"
    content = diagram_path.read_text(encoding="utf-8")

    # Fill and border palette controls
    assert 'toggle-fill-palette' in content, "Context bar must have fill color palette control"
    assert 'toggle-border-palette' in content, "Context bar must have border color palette control"

    # 3 line style controls (solid, dashed, dotted)
    assert 'data-val="solid"' in content
    assert 'data-val="dashed"' in content
    assert 'data-val="dotted"' in content

    # 3 arrow controls (none, end, both)
    assert 'data-val="none"' in content
    assert 'data-val="end"' in content
    assert 'data-val="both"' in content


def test_validation_accepts_16_shape_types_and_rejects_unknown():
    """Verify validation accepts all 16 shape types and still rejects unknown ones."""
    for st in SIXTEEN_SHAPE_TYPES:
        valid_doc = {
            "shapes": [{
                "id": f"shape_{st}",
                "type": st,
                "x": 10.0,
                "y": 20.0,
                "w": 160.0,
                "h": 68.0,
            }]
        }
        res = store.validate_diagram(valid_doc)
        assert res["shapes"][0]["type"] == st

    # Reject unknown shape types
    for bad in ["pentagon", "star_polygon", "nonexistent_shape", "custom_poly"]:
        with pytest.raises(ValueError, match="unknown shape type"):
            store.validate_diagram({
                "shapes": [{"id": "s_bad", "type": bad, "x": 0, "y": 0, "w": 100, "h": 50}]
            })



# ---------------------------------------------------------------- coordinates + connection points

def _diagram_js():
    return (REPO / "ui" / "diagram.js").read_text(encoding="utf-8")


def _method_body(content, name):
    """Source text of a class method `name(...) {` up to the next 4-space-indented method."""
    m = re.search(r"\n    (?:async )?" + re.escape(name) + r"\([^)]*\) \{\n(.*?)\n    \}\n", content, re.DOTALL)
    assert m, f"method {name} not found in diagram.js"
    return m.group(1)


def test_single_client_to_diagram_conversion_helper():
    js = _diagram_js()
    body = _method_body(js, "clientToDiagram")
    assert "createSVGPoint" in body
    assert "getScreenCTM" in body and ".inverse()" in body
    assert "viewportEl" in body, "must use the pan/zoom group's CTM"
    # the old ad-hoc converter must be gone and the helper defined exactly once
    assert "screenToCanvas" not in js
    assert len(re.findall(r"\n    clientToDiagram\(", js)) == 1
    # the unconverted svg viewBox (letterboxing) was the cause of the cursor offset
    assert "setAttribute('viewBox', '0 0 860 520')" not in js


def test_all_pointer_paths_use_the_helper():
    js = _diagram_js()
    for name in ("onMouseDown", "onMouseMove", "onMouseUp", "onDoubleClick"):
        assert "this.clientToDiagram(" in _method_body(js, name), f"{name} must convert via clientToDiagram"
    assert "this.clientToDiagram(" in _method_body(js, "pasteClipboard"), "paste at cursor must use the helper"
    # create (click centred on cursor / drag press-to-release), marquee, drag and connector paths take helper output
    finish = _method_body(js, "finishDrawingShape")
    assert "pos.x - sz.w / 2" in finish and "pos.y - sz.h / 2" in finish, "click-create must centre on the cursor"
    assert "this.drawStart" in finish and "Math.max(this.drawStart.x, pos.x)" in finish
    assert "canvasPos" in _method_body(js, "onMouseDown")
    assert "this.marqueeStart = { x: canvasPos.x, y: canvasPos.y }" in js
    assert "this.doDragItems(canvasPos)" in js
    assert "this.doDragConnEnd(canvasPos)" in js
    assert "this.finishConnecting(canvasPos)" in js
    # no other client->canvas maths on the mount/wrapper rect
    for name in ("onMouseDown", "onMouseMove", "onMouseUp", "onDoubleClick", "finishDrawingShape", "createShapeAt"):
        assert "getBoundingClientRect" not in _method_body(js, name)
    assert "mountEl.getBoundingClientRect" not in js


def test_snap_radius_points_and_highlight_present():
    js = _diagram_js()
    assert re.search(r"SNAP_RADIUS_PX\s*=\s*16\b", js)
    assert re.search(r"DETACH_RADIUS_PX\s*=\s*24\b", js)
    assert "findSnapTarget" in js and "getConnectionPoints" in js
    # 4 side midpoints + 4 corners for every shape, all on the outline (anchorPoint)
    assert "ANCHOR_NAMES" in js
    for p in ("top-left", "top-right", "bottom-right", "bottom-left"):
        assert f"'{p}'" in js
    # nearest point highlighted
    assert "is-snap" in js and "connectionPointsHtml" in js
    # inside a shape -> nearest side midpoint
    assert "nearestSidePoint" in _method_body(js, "findSnapTarget")
    # release stores {shape, point}
    assert "point: sr.target.point" in _method_body(js, "resolveEndForDrop")
    assert "this.draggingConnEnd" in js and "diag-conn-end-handle" in js
    # loose ends are hollow circles
    assert "diag-conn-free-end" in js


def test_attached_ends_recompute_on_move():
    js = _diagram_js()
    # ends are derived from the shape on every render, never cached
    body = _method_body(js, "getEndpointCoords")
    assert "getShapePortPosition" in body and "ep.point || ep.side" in body
    assert "getEndpointCoords" in _method_body(js, "renderConnectors")
    assert "this.render()" in _method_body(js, "doDragItems")
    assert "this.render()" in _method_body(js, "doResize")
    assert "buildConnectorPath" in _method_body(js, "renderConnectors")


def test_elbow_route_with_ends_on_different_axes_takes_one_bend_and_its_label_sits_on_it():
    js = _diagram_js()
    # A side to a top or bottom (e.g. a STOP line into a driver's bottom): out along the start's axis, in along the
    # end's, one bend. Before, the route always used the start's axis and ran its last leg along the box edge.
    kind = _method_body(js, "elbowKind")
    assert "d1 && d2 && d1 !== d2" in kind and "'hv'" in kind and "'vh'" in kind
    path = _method_body(js, "buildConnectorPath")
    assert "H ${p2.x} V ${p2.y}" in path and "V ${p2.y} H ${p2.x}" in path
    # the label is drawn, and edited, on the path: the middle of the longest leg of a one-bend route
    assert "connectorLabelPoint" in _method_body(js, "renderConnectors")
    assert "connectorLabelPoint" in js[js.index("type === 'connector'"):][:600]


def test_sanitize_model_keeps_point_and_legacy_side():
    js = _diagram_js()
    assert "VALID_ENDPOINT_POINTS" in js
    assert "ep.point" in js and "ep.side" in js  # new {shape, point} and old {shape, side} both load
    assert "escapeHtml(" in _method_body(js, "renderPorts")


def test_validation_accepts_shape_point_endpoints():
    shapes = [
        {"id": "a", "type": "block", "x": 0, "y": 0, "w": 100, "h": 50},
        {"id": "b", "type": "ellipse", "x": 300, "y": 0, "w": 100, "h": 50},
    ]
    for pt in ("top", "right", "bottom", "left", "top-left", "top-right", "bottom-right", "bottom-left"):
        res = store.validate_diagram({
            "shapes": shapes,
            "connectors": [{"id": "c1", "from": {"shape": "a", "point": pt}, "to": {"shape": "b", "point": "left"}}],
        })
        assert res["connectors"][0]["from"] == {"shape": "a", "point": pt}
        assert res["connectors"][0]["to"] == {"shape": "b", "point": "left"}
    # legacy side-style and free ends still load
    res = store.validate_diagram({
        "shapes": shapes,
        "connectors": [{"id": "c2", "from": {"shape": "a", "side": "right"}, "to": {"x": 5, "y": 6}}],
    })
    assert res["connectors"][0]["from"] == {"shape": "a", "side": "right"}
    assert res["connectors"][0]["to"] == {"x": 5.0, "y": 6.0}


def test_validation_rejects_bad_point_and_unknown_shape():
    shapes = [{"id": "a", "type": "block", "x": 0, "y": 0, "w": 100, "h": 50}]
    for bad in ("middle", "TOP", "", None, 5, "top-center"):
        with pytest.raises(ValueError, match="invalid point"):
            store.validate_diagram({
                "shapes": shapes,
                "connectors": [{"id": "c1", "from": {"shape": "a", "point": bad}, "to": {"x": 1, "y": 1}}],
            })
    with pytest.raises(ValueError, match="unknown shape"):
        store.validate_diagram({
            "shapes": shapes,
            "connectors": [{"id": "c1", "from": {"shape": "ghost", "point": "top"}, "to": {"x": 1, "y": 1}}],
        })


# ---------------------------------------------------------------- anchor geometry (static: no JS runtime)

def test_anchor_point_covers_every_palette_shape_on_outline():
    js = (REPO / "ui" / "diagram.js").read_text(encoding="utf-8")
    assert "function anchorPoint(shape, pointName)" in js
    palette = re.findall(r"\{ type: '([a-z_]+)', name:", js[js.index("const SHAPES_16"):])
    assert len(palette) == 16
    body = js[js.index("function anchorPoint(shape, pointName)"):js.index("function sanitizeModel")]
    frac_keys = set(re.findall(r"^\s{4}([a-z_]+): \[\[", js, re.M))
    handled = frac_keys | set(re.findall(r"type === '([a-z_]+)'", body))
    # process and sticky intentionally use the rectangle fractions (their outline is the box)
    for t in palette:
        assert t in handled or t in ("process",), f"anchorPoint must handle shape type {t}"
    # connection points / port positions use the pure function, not the bounding box
    assert "return anchorPoint(s, point);" in js
    assert "ANCHOR_NAMES.map" in js
    # all 8 point names stay resolvable for every shape
    for n in ("top", "right", "bottom", "left", "top-left", "top-right", "bottom-right", "bottom-left"):
        assert f"'{n}'" in js.split("const ANCHOR_NAMES")[1].split("\n")[0]
    # fraction table rows each carry all 8 points
    for row in re.findall(r"^\s{4}[a-z_]+: (\[\[.*\]\]),?$", js, re.M):
        assert row.count("], [") == 7
