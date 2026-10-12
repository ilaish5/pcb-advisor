"""Unit tests for Task D: Schematic preview, PCB preview, block diagram, and project keeping."""
import json
import pathlib
import threading
import urllib.request
import pytest

import keeping
import preview_pcb
import preview_sch
import store


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_keeping_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr("workspace.project_dir", lambda name=None: tmp_path / (name or "demo"))
    proj = "demo"
    (tmp_path / proj).mkdir(parents=True, exist_ok=True)

    # Empty decisions
    assert keeping.list_decisions(proj) == []

    # Append first decision
    entry1 = keeping.append_decision(proj, "Use ESP32-S3-WROOM-1", who="student", why="WiFi + BLE required", source="datasheet p.4")
    assert entry1["decision"] == "Use ESP32-S3-WROOM-1"
    assert entry1["who"] == "student"

    # Append second decision
    entry2 = keeping.append_decision(proj, "Switch LDO to TPS7A25", who="advisor", why="Lower dropout", source="TI app note")
    assert entry2["decision"] == "Switch LDO to TPS7A25"

    # List decisions
    decs = keeping.list_decisions(proj)
    assert len(decs) == 2
    assert decs[0]["decision"] == "Use ESP32-S3-WROOM-1"
    assert decs[1]["decision"] == "Switch LDO to TPS7A25"
    assert decs[1]["who"] == "advisor"


def test_keeping_change_impact(tmp_path, monkeypatch):
    monkeypatch.setattr("workspace.project_dir", lambda name=None: tmp_path / (name or "demo"))
    proj = "demo"
    (tmp_path / proj).mkdir(parents=True, exist_ok=True)

    impacts = keeping.change_impact(proj, "U1")
    assert len(impacts) == 13
    cats = {i["category"] for i in impacts}
    assert "Symbol and pin map" in cats
    assert "Footprint and 3D model" in cats
    assert "Supply voltage and decoupling" in cats
    assert "PCB placement" in cats
    assert "BOM line and LCSC number" in cats


def test_keeping_file_organization(tmp_path, monkeypatch):
    monkeypatch.setattr("workspace.project_dir", lambda name=None: tmp_path / (name or "demo"))
    proj = "demo"
    pdir = tmp_path / proj
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "idea.json").write_text("{}", encoding="utf-8")
    (pdir / "notes.md").write_text("# Notes", encoding="utf-8")

    rep = keeping.file_organization(proj)
    assert rep["project"] == "demo"
    assert "present" in rep
    assert "missing" in rep
    present_names = [p["name"] for p in rep["present"]]
    assert "idea.json" in present_names
    assert "notes.md" in present_names
    missing_names = [m["name"] for m in rep["missing"]]
    assert "JLC BOM" in missing_names


def test_preview_sch_render(tmp_path):
    fixtures_dir = pathlib.Path(__file__).parent / "fixtures" / "altium"
    schdoc_path = fixtures_dir / "project" / "CAN_Interface.SchDoc"
    assert schdoc_path.is_file()

    svg = preview_sch.render_schdoc(schdoc_path)
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert 'class="sch"' in svg
    assert "CAN_Interface" in svg


def test_preview_pcb_outline_and_render(tmp_path):
    fixtures_dir = pathlib.Path(__file__).parent / "fixtures" / "altium"
    pcbdoc_path = fixtures_dir / "finished-board.PcbDoc"
    assert pcbdoc_path.is_file()

    # Board outline extraction
    outline = preview_pcb.get_board_outline(pcbdoc_path)
    assert outline is not None
    assert len(outline) >= 3

    # Render top layer
    svg_top = preview_pcb.render_pcbdoc(pcbdoc_path, active_layer="top")
    assert svg_top.startswith("<svg")
    assert 'id="pcb-layer-top"' in svg_top
    assert 'pcb-outline' in svg_top

    # Render with plan overlay
    plan = {
        "groups": [{"name": "Power", "x": 10, "y": 10, "w": 20, "h": 20}],
        "keep_outs": [{"name": "Antenna", "x": 5, "y": 5, "w": 10, "h": 10}],
        "critical_nets": [{"net": "SPI_CLK", "note": "match length"}]
    }
    svg_plan = preview_pcb.render_pcbdoc(pcbdoc_path, plan=plan, active_layer="all")
    assert 'id="pcb-layer-plan"' in svg_plan
    assert "Power" in svg_plan
    assert "Antenna" in svg_plan


def test_preview_placement_plan_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr("workspace.project_dir", lambda name=None: tmp_path / (name or "demo"))
    proj = "demo"
    plan = {
        "groups": [{"name": "MCU Zone", "x": 15, "y": 15, "w": 25, "h": 25}],
        "keep_outs": [],
        "critical_nets": []
    }
    saved = preview_pcb.save_placement_plan(proj, plan)
    assert saved == plan

    loaded = preview_pcb.load_placement_plan(proj)
    assert loaded["groups"][0]["name"] == "MCU Zone"


def test_server_previews_and_keeping(server, lte):
    # Test /api/preview/sch.svg
    with urllib.request.urlopen(f"{server}/api/preview/sch.svg?project={lte}") as r:
        assert r.status == 200
        body = r.read().decode("utf-8")
        assert body.startswith("<svg")

    # Test /api/preview/pcb.svg
    with urllib.request.urlopen(f"{server}/api/preview/pcb.svg?project={lte}&layer=top") as r:
        assert r.status == 200
        body = r.read().decode("utf-8")
        assert body.startswith("<svg")

    # Test /api/placement/plan GET & POST
    plan_data = {"groups": [{"name": "RF", "x": 0, "y": 0, "w": 10, "h": 10}]}
    req = urllib.request.Request(
        f"{server}/api/placement/plan?project={lte}",
        data=json.dumps(plan_data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        assert r.status == 200
        res = json.loads(r.read())
        assert res.get("ok") is True

    # Test /api/keeping/decisions and POST /api/keeping/decision
    dec_data = {"decision": "Use SMD crystal 16MHz", "who": "student", "why": "Space constraint"}
    req = urllib.request.Request(
        f"{server}/api/keeping/decision?project={lte}",
        data=json.dumps(dec_data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        assert r.status == 200
        res = json.loads(r.read())
        assert res.get("ok") is True
        assert res["entry"]["decision"] == "Use SMD crystal 16MHz"

    with urllib.request.urlopen(f"{server}/api/keeping/decisions?project={lte}") as r:
        assert r.status == 200
        res = json.loads(r.read())
        assert len(res["decisions"]) >= 1

    # Test /api/keeping/impact
    with urllib.request.urlopen(f"{server}/api/keeping/impact?project={lte}&item=U1") as r:
        assert r.status == 200
        res = json.loads(r.read())
        assert len(res["impacts"]) == 13

    # Test /api/keeping/report
    with urllib.request.urlopen(f"{server}/api/keeping/report?project={lte}") as r:
        assert r.status == 200
        res = json.loads(r.read())
        assert "present" in res
        assert "missing" in res
