"""
Tests for live block diagram editing by the agent, undo, requirements editing, and stage strip highlight.
"""
import copy
import json
import math
import pathlib
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import agent
import model
import serve
import session
import store
from ui_source import ui_all

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def server(home, monkeypatch):
    """Real server handler on an ephemeral port."""
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


# -----------------------------------------------------------------------------
# 1. Diagram Ops Tests
# -----------------------------------------------------------------------------

def test_add_shape_and_auto_placement(empty):
    """Test add_shape with explicit coords and with auto placement."""
    ops1 = [
        {"op": "add_shape", "id": "usb", "text": "USB-C\nInput 5V", "type": "box", "x": 100, "y": 100, "w": 120, "h": 60, "domain": "power"}
    ]
    res1 = store.apply_diagram_edit(empty, ops1)
    assert res1["ok"]
    assert "usb" in res1["touched"]
    diag = store.load_idea_working(empty)["diagram"]
    assert len(diag["shapes"]) == 1
    s_usb = diag["shapes"][0]
    assert s_usb["id"] == "usb"
    assert s_usb["x"] == 100 and s_usb["y"] == 100
    assert s_usb["domain"] == "power"

    # Now add another shape without coordinates: should auto-place near existing shape without overlap
    ops2 = [
        {"op": "add_shape", "id": "mcu", "text": "MCU\nSTM32", "type": "box", "domain": "mcu"}
    ]
    res2 = store.apply_diagram_edit(empty, ops2)
    assert res2["ok"]
    diag2 = store.load_idea_working(empty)["diagram"]
    assert len(diag2["shapes"]) == 2
    s_mcu = next(s for s in diag2["shapes"] if s["id"] == "mcu")
    # Coordinates must be finite and not directly overlapping (x, y) != (100, 100)
    assert math.isfinite(s_mcu["x"]) and math.isfinite(s_mcu["y"])
    assert not (s_mcu["x"] == s_usb["x"] and s_mcu["y"] == s_usb["y"])


def test_update_shape(empty):
    """Test update_shape modifies attributes."""
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "s1", "text": "Old Text", "x": 50, "y": 50}])
    res = store.apply_diagram_edit(empty, [{"op": "update_shape", "id": "s1", "text": "New Text\nRole", "domain": "power", "role": "Charger"}])
    assert res["ok"]
    assert "s1" in res["touched"]
    diag = store.load_idea_working(empty)["diagram"]
    s = diag["shapes"][0]
    assert s["text"] == "New Text\nRole"
    assert s["domain"] == "power"
    assert s["role"] == "Charger"


def test_delete_shape_removes_incident_connectors(empty):
    """Test delete_shape removes the shape and all incident connectors."""
    store.apply_diagram_edit(empty, [
        {"op": "add_shape", "id": "s1", "text": "A", "x": 0, "y": 0},
        {"op": "add_shape", "id": "s2", "text": "B", "x": 200, "y": 0},
        {"op": "add_shape", "id": "s3", "text": "C", "x": 400, "y": 0},
        {"op": "add_connector", "id": "c1", "from": "s1", "to": "s2", "label": "AB"},
        {"op": "add_connector", "id": "c2", "from": "s2", "to": "s3", "label": "BC"},
        {"op": "add_connector", "id": "c3", "from": "s1", "to": "s3", "label": "AC"},
    ])
    diag_before = store.load_idea_working(empty)["diagram"]
    assert len(diag_before["shapes"]) == 3
    assert len(diag_before["connectors"]) == 3

    # Delete s2: c1 and c2 should be removed; c3 should remain
    res = store.apply_diagram_edit(empty, [{"op": "delete_shape", "id": "s2"}])
    assert res["ok"]
    diag_after = store.load_idea_working(empty)["diagram"]
    assert len(diag_after["shapes"]) == 2
    assert not any(s["id"] == "s2" for s in diag_after["shapes"])
    assert len(diag_after["connectors"]) == 1
    assert diag_after["connectors"][0]["id"] == "c3"


def test_connector_ops(empty):
    """Test adding, updating, and deleting connectors."""
    store.apply_diagram_edit(empty, [
        {"op": "add_shape", "id": "pwr", "text": "5V", "x": 0, "y": 0},
        {"op": "add_shape", "id": "ldo", "text": "3V3", "x": 200, "y": 0},
    ])
    # Add connector
    res_add = store.apply_diagram_edit(empty, [
        {"op": "add_connector", "id": "c_pwr", "from": "pwr", "to": "ldo", "label": "5V In", "style": "solid", "arrows": "to"}
    ])
    assert res_add["ok"]
    diag = store.load_idea_working(empty)["diagram"]
    assert len(diag["connectors"]) == 1
    c = diag["connectors"][0]
    assert c["label"] == "5V In"
    assert c["style"] == "solid"

    # Update connector
    res_up = store.apply_diagram_edit(empty, [
        {"op": "update_connector", "id": "c_pwr", "label": "5V 500mA", "style": "thick"}
    ])
    assert res_up["ok"]
    c_up = store.load_idea_working(empty)["diagram"]["connectors"][0]
    assert c_up["label"] == "5V 500mA"
    assert c_up["style"] == "thick"

    # Delete connector
    res_del = store.apply_diagram_edit(empty, [{"op": "delete_connector", "id": "c_pwr"}])
    assert res_del["ok"]
    assert len(store.load_idea_working(empty)["diagram"]["connectors"]) == 0


def test_frame_ops(empty):
    """Test adding, updating, and deleting frames, including 'around' bounds calculation."""
    store.apply_diagram_edit(empty, [
        {"op": "add_shape", "id": "s1", "text": "S1", "x": 100, "y": 100, "w": 100, "h": 50},
        {"op": "add_shape", "id": "s2", "text": "S2", "x": 300, "y": 200, "w": 100, "h": 50},
    ])
    # Add frame around s1 and s2 with 20 padding
    res = store.apply_diagram_edit(empty, [
        {"op": "add_frame", "id": "f1", "title": "Subsystem", "around": ["s1", "s2"], "padding": 20, "stroke": "#2980b9"}
    ])
    assert res["ok"]
    diag = store.load_idea_working(empty)["diagram"]
    assert len(diag["frames"]) == 1
    f = diag["frames"][0]
    assert f["title"] == "Subsystem"
    # min_x = 100, pad = 20 -> x = 80
    assert f["x"] == 80
    # min_y = 100, pad = 20 -> y = 80
    assert f["y"] == 80
    # max_x = 300 + 100 = 400 -> w = (400 - 100) + 40 = 340
    assert f["w"] == 340
    # max_y = 200 + 50 = 250 -> h = (250 - 100) + 40 = 190
    assert f["h"] == 190

    # Update frame title
    res_up = store.apply_diagram_edit(empty, [{"op": "update_frame", "id": "f1", "title": "Power Domain"}])
    assert res_up["ok"]
    assert store.load_idea_working(empty)["diagram"]["frames"][0]["title"] == "Power Domain"

    # Delete frame
    res_del = store.apply_diagram_edit(empty, [{"op": "delete_frame", "id": "f1"}])
    assert res_del["ok"]
    assert len(store.load_idea_working(empty)["diagram"]["frames"]) == 0


def test_auto_layout(empty):
    """Test auto_layout arranges shapes topologically and updates enclosing frame bounds."""
    store.apply_diagram_edit(empty, [
        {"op": "add_shape", "id": "usb", "text": "USB", "x": 500, "y": 400},
        {"op": "add_shape", "id": "mcu", "text": "MCU", "x": 10, "y": 10},
        {"op": "add_connector", "from": "usb", "to": "mcu", "label": "5V"},
        {"op": "add_frame", "id": "f_all", "title": "All", "around": ["usb", "mcu"]}
    ])
    res = store.apply_diagram_edit(empty, [{"op": "auto_layout"}])
    assert res["ok"]
    diag = store.load_idea_working(empty)["diagram"]
    s_usb = next(s for s in diag["shapes"] if s["id"] == "usb")
    s_mcu = next(s for s in diag["shapes"] if s["id"] == "mcu")
    # In topological left-to-right from usb -> mcu, usb x should be < mcu x
    assert s_usb["x"] < s_mcu["x"]
    # Frame f_all must enclose both shapes
    f = diag["frames"][0]
    assert f["x"] <= s_usb["x"]
    assert f["x"] + f["w"] >= s_mcu["x"] + s_mcu["w"]


# -----------------------------------------------------------------------------
# 2. Validation and Refusal Tests (Diagram Intact)
# -----------------------------------------------------------------------------

def test_invalid_op_refused_diagram_unchanged(empty):
    """Test that any invalid op causes the entire batch to be refused and diagram left intact."""
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "init", "text": "Initial"}])
    diag_before = copy.deepcopy(store.load_idea_working(empty)["diagram"])

    # 1. Unknown op
    with pytest.raises(ValueError, match="unknown op"):
        store.apply_diagram_edit(empty, [{"op": "teleport_shape", "id": "init"}])
    assert store.load_idea_working(empty)["diagram"] == diag_before

    # 2. Invalid shape type
    with pytest.raises(ValueError):
        store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "bad", "type": "triangle_nonexistent"}])
    assert store.load_idea_working(empty)["diagram"] == diag_before

    # 3. Non-finite coordinates
    with pytest.raises(ValueError):
        store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "bad", "x": float("nan"), "y": 100}])
    assert store.load_idea_working(empty)["diagram"] == diag_before

    # 4. Connector to nonexistent shape
    with pytest.raises(ValueError):
        store.apply_diagram_edit(empty, [{"op": "add_connector", "from": "init", "to": "ghost_shape"}])
    assert store.load_idea_working(empty)["diagram"] == diag_before


def test_cap_100_ops(empty):
    """Test cap of 100 ops per action."""
    ops_101 = [{"op": "add_shape", "id": f"s_{i}", "text": f"S{i}"} for i in range(101)]
    with pytest.raises(ValueError, match="max 100"):
        store.apply_diagram_edit(empty, ops_101)


# -----------------------------------------------------------------------------
# 3. Undo Tests
# -----------------------------------------------------------------------------

def test_undo_restores_diagram_and_history_cap(empty, server):
    """Test undo restores diagram and history is capped at 20."""
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "base", "text": "Base"}])
    
    # Apply 25 edits
    for i in range(1, 26):
        store.apply_diagram_edit(empty, [{"op": "add_shape", "id": f"s_{i}", "text": f"Step {i}"}])

    hist = store.diagram_history(empty)
    assert len(hist) <= 20

    # Test store.undo_diagram
    diag_restored = store.undo_diagram(empty)
    # Most recent added was s_25, restored should have s_24 as the last one
    s_ids = {s["id"] for s in diag_restored["shapes"]}
    assert "s_24" in s_ids
    assert "s_25" not in s_ids

    # Test POST /api/idea/diagram/undo endpoint
    status, out = post_json(server, "/api/idea/diagram/undo", {}, empty)
    assert status == 200
    assert out["ok"]
    assert "diagram" in out
    s_ids_endpoint = {s["id"] for s in out["diagram"]["shapes"]}
    assert "s_23" in s_ids_endpoint
    assert "s_24" not in s_ids_endpoint


# -----------------------------------------------------------------------------
# 4. Chat Action Direct Application
# -----------------------------------------------------------------------------

def test_chat_live_diagram_edit_direct(empty, server, monkeypatch):
    """Test idea.diagram.edit action works directly via /api/chat with agent.respond monkeypatched."""
    def fake_respond(model_state, text, chat, backend=None, **_kw):
        return {
            "reply": "Added USB and Charger blocks directly.",
            "actions": [
                {
                    "type": "idea.diagram.edit",
                    "reason": "Add power blocks",
                    "ops": [
                        {"op": "add_shape", "id": "usb", "text": "USB-C\n5V", "domain": "power"},
                        {"op": "add_shape", "id": "chg", "text": "Charger\nBQ24075", "domain": "power"},
                        {"op": "add_connector", "from": "usb", "to": "chg", "label": "5V"}
                    ]
                }
            ]
        }

    monkeypatch.setattr(agent, "respond", fake_respond)

    status, out = post_json(server, "/api/chat", {"text": "Add a charger between USB and battery"}, empty)
    assert status == 200
    # No proposal required: applied directly
    assert "idea.diagram.edit" in out.get("last_actions", [])
    assert "diagram_touched" in out
    assert set(out["diagram_touched"]).issuperset({"usb", "chg"})

    # Check project state
    diag = store.load_idea_working(empty)["diagram"]
    shape_ids = {s["id"] for s in diag["shapes"]}
    assert "usb" in shape_ids and "chg" in shape_ids
    assert len(diag["connectors"]) == 1
    assert diag["connectors"][0]["label"] == "5V"

    # Agent message bubble in chat record
    chat_msgs = session.load_chat(empty, out["session"])
    agent_msg = chat_msgs[-1]
    assert agent_msg["role"] == "agent"
    assert "idea.diagram.edit" in agent_msg["applied"]
    assert set(agent_msg.get("diagram_touched", [])).issuperset({"usb", "chg"})


# -----------------------------------------------------------------------------
# 5. Compact Diagram Context in Agent State
# -----------------------------------------------------------------------------

def test_compact_diagram_in_state(empty):
    """Agent sees compact diagram (ids, text, domain, rounded bounds, connectors, frames)."""
    store.apply_diagram_edit(empty, [
        {"op": "add_shape", "id": "mcu", "text": "MCU\nSTM32", "x": 10.4, "y": 20.6, "w": 100.2, "h": 50.1, "domain": "mcu"},
        {"op": "add_shape", "id": "led", "text": "LED", "x": 200, "y": 20, "domain": "ui"},
        {"op": "add_connector", "from": "mcu", "to": "led", "label": "GPIO"},
        {"op": "add_frame", "id": "f1", "title": "Main", "around": ["mcu", "led"]}
    ])
    m = model.build(project=empty)
    summary_str = agent._summary(m)
    summary = json.loads(summary_str)
    diag = summary.get("diagram")
    assert diag is not None
    # Shapes have rounded coordinates
    s_mcu = next(s for s in diag["shapes"] if s["id"] == "mcu")
    assert s_mcu["x"] == 10 and s_mcu["y"] == 21
    assert s_mcu["w"] == 100 and s_mcu["h"] == 50
    assert s_mcu["domain"] == "mcu"
    # Connectors
    assert len(diag["connectors"]) == 1
    assert diag["connectors"][0]["from"] == "mcu"
    assert diag["connectors"][0]["to"] == "led"
    # Frames have member shape ids
    assert len(diag["frames"]) == 1
    assert set(diag["frames"][0]["members"]) == {"mcu", "led"}


# -----------------------------------------------------------------------------
# 6. Documentation Checks
# -----------------------------------------------------------------------------

def test_agents_md_and_skills_documentation():
    """Verify AGENTS.md and SKILL.md contain required diagram editing documentation."""
    agents_md = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    assert "idea.diagram.edit" in agents_md
    assert "idea.diagram" in agents_md

    skill_md = (REPO / "runtime" / "skills" / "idea-and-requirements" / "SKILL.md").read_text(encoding="utf-8")
    assert "idea.diagram.edit" in skill_md
    assert "diagram-ops.md" in skill_md

    ops_md = (REPO / "runtime" / "skills" / "idea-and-requirements" / "references" / "diagram-ops.md").read_text(encoding="utf-8")
    for op in ("add_shape", "update_shape", "delete_shape", "add_connector", "update_connector", "delete_connector",
              "add_frame", "update_frame", "delete_frame", "auto_layout"):
        assert op in ops_md
    assert "Power Chain" in ops_md
    assert "MCU and Buses" in ops_md
    assert "Dashed Domain Frame" in ops_md


# -----------------------------------------------------------------------------
# 7. Requirements Endpoints Tests
# -----------------------------------------------------------------------------

def _legacy_proposed(project, topic, text):
    """A requirement the agent proposed before the draft existed (old projects still carry these)."""
    idea = store.load_idea(project)
    idea["agreed"].append({"topic": topic, "text": text, "by": "agent", "status": "proposed", "ts": store.now()})
    store.save_idea(project, idea)


def test_requirements_endpoints(empty, server):
    """Test requirements endpoints: add, update, rename conflict, confirm, delete, move."""
    # 1. Add requirement
    st, res = post_json(server, "/api/idea/item", {"topic": "Power", "text": "LiPo battery 3.7V"}, empty)
    assert st == 200
    items = res["idea"]["agreed"]
    assert len(items) == 1
    assert items[0]["topic"] == "Power"
    assert items[0]["by"] == "student"
    assert items[0]["status"] == "confirmed"

    # Validation: empty or too long
    st_bad1, _ = post_json(server, "/api/idea/item", {"topic": "A" * 65, "text": "Valid"}, empty)
    assert st_bad1 == 400
    st_bad2, _ = post_json(server, "/api/idea/item", {"topic": "Valid", "text": "B" * 1005}, empty)
    assert st_bad2 == 400

    # Add second item
    post_json(server, "/api/idea/item", {"topic": "MCU", "text": "STM32G0"}, empty)

    # 2. Update / rename
    st_up, res_up = post_json(server, "/api/idea/item/update", {"old_topic": "Power", "topic": "Power Supply", "text": "USB-C + LiPo"}, empty)
    assert st_up == 200
    assert any(i["topic"] == "Power Supply" for i in res_up["idea"]["agreed"])

    # Rename conflict: rename to MCU (already exists)
    st_conf, _ = post_json(server, "/api/idea/item/update", {"old_topic": "Power Supply", "topic": "MCU", "text": "Conflict"}, empty)
    assert st_conf == 400

    # 3. Confirm a proposed item (an old project's; the agent now writes straight into the draft)
    store.save_idea_from_draft(empty)
    _legacy_proposed(empty, "Radio", "BLE 5.0")
    item_radio = next(i for i in store.load_idea_working(empty)["agreed"] if i["topic"] == "Radio")
    assert item_radio["status"] == "proposed"
    st_cfm, res_cfm = post_json(server, "/api/idea/item/confirm", {"topic": "Radio"}, empty)
    assert st_cfm == 200
    assert next(i for i in res_cfm["idea"]["agreed"] if i["topic"] == "Radio")["status"] == "confirmed"

    # 4. Move item
    # agreed order: ["Power Supply", "MCU", "Radio"]
    st_mv, res_mv = post_json(server, "/api/idea/item/move", {"from": 2, "to": 0}, empty)
    assert st_mv == 200
    assert res_mv["idea"]["agreed"][0]["topic"] == "Radio"

    # 5. Delete item
    st_del, res_del = post_json(server, "/api/idea/item/delete", {"topic": "MCU"}, empty)
    assert st_del == 200
    assert res_del["deleted"]["topic"] == "MCU"
    assert not any(i["topic"] == "MCU" for i in res_del["idea"]["agreed"])


def test_agent_proposal_preserves_student_prev_text(empty):
    """The agent's change to a student's topic lands in the draft at once; the old text is kept in prev_text."""
    store.propose_idea(empty, "Memory", "64MB SPI NOR Flash", by="student")
    assert store.load_idea_working(empty)["agreed"][0]["status"] == "confirmed"

    # Agent proposes update
    store.propose_idea(empty, "Memory", "32MB SPI NOR Flash is enough", by="agent")
    item = store.load_idea_working(empty)["agreed"][0]
    assert item["status"] == "confirmed" and item["by"] == "agent"
    assert item["text"] == "32MB SPI NOR Flash is enough"
    assert item["prev_text"] == "64MB SPI NOR Flash"


# -----------------------------------------------------------------------------
# 8. Static UI Checks
# -----------------------------------------------------------------------------

def test_static_ui_checks():
    """Static checks for requirement editing controls, stage strip highlight, and diagram pulse/undo."""
    index_html = ui_all()
    diagram_js = (REPO / "ui" / "diagram.js").read_text(encoding="utf-8")

    # Requirement editing controls in the UI source (index.html + ui/js)
    assert "req-row" in index_html
    assert "req-edit-btn" in index_html or "edit-req" in index_html  # ✎
    assert "req-del-btn" in index_html or "delete-req" in index_html  # 🗑
    assert "req-confirm-btn" in index_html or "confirm-req" in index_html  # ✓
    # A requirement moves by its grip (drag) or from the keyboard: Alt+Up / Alt+Down on the focused row (no arrow buttons)
    idea_js = (REPO / "ui" / "js" / "views" / "idea.js").read_text(encoding="utf-8")
    assert "moveReq(" in idea_js and "e.altKey" in idea_js and "'ArrowUp'" in idea_js and "'ArrowDown'" in idea_js
    assert "req-move-up" not in idea_js and "req-move-down" not in idea_js, "the row has one grip and the keyboard, not arrow buttons"
    assert "req-drag-handle" in index_html
    assert "+ Add requirement" in index_html
    assert "/api/idea/item/update" in index_html
    assert "/api/idea/item/delete" in index_html
    assert "/api/idea/item/confirm" in index_html
    assert "/api/idea/item/move" in index_html

    # The stage trace in the nav marks the stage the main sheet shows (the stepper strip and editor tabs are gone)
    assert "const here = mainView()" in index_html
    assert "${here === id ? ' aria-current=\"page\"' : ''}" in index_html

    # Undo diagram change button in chat
    assert "undo-diagram" in index_html
    assert "/api/idea/diagram/undo" in index_html

    # Diagram editor pulse animation and server undo
    assert "diag-pulse" in diagram_js
    assert "canServerUndo" in diagram_js or "onServerUndo" in diagram_js
    assert "updateData(newData, touchedIds" in diagram_js
