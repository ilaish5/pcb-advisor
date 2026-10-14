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


def test_outputs_are_found_in_the_linked_altium_folder_and_flagged_when_older(tmp_path, monkeypatch):
    """Altium writes outputs next to the project, not into exports/. A Gerber older than the last
    board save is listed with older_than; copies in History/ never count."""
    import os
    import project as project_mod
    monkeypatch.setattr("workspace.project_dir", lambda name=None: tmp_path / (name or "demo"))
    (tmp_path / "demo").mkdir()
    alt = tmp_path / "alt"
    (alt / "Outputs" / "Assembly").mkdir(parents=True)
    (alt / "History").mkdir()
    (alt / "a.PrjPcb").write_text("", encoding="utf-8")
    (alt / "b.SchDoc").write_text("", encoding="utf-8")
    gerber = alt / "Outputs" / "Board-Gerber.zip"
    gerber.write_bytes(b"x")
    cpl = alt / "Outputs" / "Assembly" / "CPL-JLC.csv"
    cpl.write_text("x", encoding="utf-8")
    (alt / "History" / "old_Schematics.pdf").write_bytes(b"x")
    pcb = alt / "board.PcbDoc"
    pcb.write_bytes(b"x")
    os.utime(gerber, (1_000_000, 1_000_000))
    os.utime(pcb, (2_000_000, 2_000_000))
    os.utime(cpl, (3_000_000, 3_000_000))
    monkeypatch.setattr(project_mod, "altium_link", lambda name: {
        "project_file": str(alt / "a.PrjPcb"), "pcb_file": str(pcb), "outputs_dir": str(alt / "Outputs")})

    rep = keeping.file_organization("demo")
    found = {p["name"]: p for p in rep["present"]}
    assert found["Gerber files"]["older_than"] == "board.PcbDoc"
    assert "older_than" not in found["CPL / Pick & Place"]
    assert "Schematic (PDF)" in [m["name"] for m in rep["missing"]]


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


def test_board_shape_comes_from_board6():
    """A real board kept the 7000 x 5000 mil default in BoardRegions while Board6 held the 100 x 80 mm shape."""
    rec = {"VX0": "1000mil", "VY0": "1000mil", "VX1": "4937.0079mil", "VY1": "1000mil",
           "VX2": "4937.0079mil", "VY2": "4149.6063mil", "VX3": "1000mil", "VY3": "4149.6063mil",
           "VX4": "1000mil", "VY4": "1000mil"}
    pts = preview_pcb.board6_outline(rec)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert (min(xs), min(ys), round(max(xs), 1), round(max(ys), 1)) == (25.4, 25.4, 125.4, 105.4)
    arc = {"VX0": "0mil", "VY0": "0mil", "KIND0": "1", "CX0": "0mil", "CY0": "0mil", "R0": "1000mil",
           "SA0": "0", "EA0": "90", "VX1": "0mil", "VY1": "1000mil"}
    pts = preview_pcb.board6_outline(arc)
    assert len(pts) == 10 and pts[0] == (25.4, 0.0) and abs(pts[8][0]) < 1e-3 and pts[8][1] == 25.4
    assert preview_pcb.board6_outline({"VX0": "0mil", "VY0": "0mil"}) is None


# ---------------------------------------------------------------------------------------------------
# The two server-drawn pictures are inlined into the page, so their <style> is global there.
# These pin the contract: every rule is scoped to the picture, colours come from the page's tokens
# (var(--x, fallback)), and the ids and classes the UI (views/previews.js) hooks into stay put.
# ---------------------------------------------------------------------------------------------------
import re

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "altium"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _style(svg):
    m = re.search(r"<style>(.*?)</style>", svg, re.S)
    assert m, "the picture carries its own <style>"
    return m.group(1)


def _selectors(css):
    """Every selector of every rule in a flat stylesheet (there is no @media in these)."""
    out = []
    for head in re.findall(r"([^{}]+)\{", css):
        out += [x.strip() for x in head.split(",") if x.strip()]
    return out


def _markup(svg):
    return re.sub(r"<style>.*?</style>", "", svg, flags=re.S)


@pytest.fixture(scope="module")
def sch_svg():
    return preview_sch.render_schdoc(FIXTURES / "project" / "CAN_Interface.SchDoc")


@pytest.fixture(scope="module")
def pcb_svg():
    plan = {
        "groups": [{"name": "Power", "x": 10, "y": 10, "w": 20, "h": 20}],
        "keep_outs": [{"name": "Antenna", "x": 5, "y": 5, "w": 10, "h": 10}],
        "critical_nets": [{"net": "SPI_CLK", "note": "match length"}],
    }
    return preview_pcb.render_pcbdoc(FIXTURES / "finished-board.PcbDoc", plan=plan)


def test_sch_picture_style_is_scoped_to_the_picture(sch_svg):
    css = _style(sch_svg)
    sels = _selectors(css)
    assert len(sels) > 10
    assert all(x.startswith(preview_sch.SCOPE) for x in sels), [x for x in sels if not x.startswith(preview_sch.SCOPE)]
    assert 'data-render="schdoc"' in sch_svg and 'class="sch"' in sch_svg


def test_sch_picture_colours_are_the_pages_tokens_with_fallbacks(sch_svg):
    css = _style(sch_svg)
    for token in ("--sch-bg", "--sch-text", "--sch-wire", "--sch-body", "--sch-body-line", "--sch-pwr", "--net", "--net-soft", "--sig", "--sig-soft"):
        assert re.search(r"var\(" + token + r",\s*[^)]+\)", css), f"{token} must be read with a fallback"
    # a hex colour is only ever the fallback inside var(), never a bare fill or stroke
    for decl in re.findall(r"(?:fill|stroke)\s*:\s*([^;}]+)", css):
        assert not HEX.match(decl.strip()), decl
    # the markup carries no colours at all: the background and the net labels are styled by classes
    assert not HEX.search(_markup(sch_svg))
    assert 'class="sch-bg"' in sch_svg


def test_sch_picture_has_the_rules_for_toggling_selection_classes(sch_svg):
    css = _style(sch_svg)
    for frag in (".part.sel", ".part:focus-visible", ".hl-net", ".netfocus", ".focus"):
        assert frag in css, frag
    # a part carries what the UI needs to pick it
    assert re.search(r'<g class="part" data-ref="[^"]+" id="part-[^"]+"', sch_svg)
    assert "hlbox" in sch_svg


def test_sch_empty_document_still_draws_a_picture():
    svg = preview_sch.render_schdoc({"components": [], "wires": []}, title="Empty")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_pcb_picture_style_is_scoped_and_uses_tokens(pcb_svg):
    css = _style(pcb_svg)
    sels = _selectors(css)
    assert len(sels) > 20
    assert all(x.startswith(preview_pcb.SCOPE) for x in sels), [x for x in sels if not x.startswith(preview_pcb.SCOPE)]
    for token in ("--pcb-bg", "--pcb-grid", "--ink-3"):
        assert re.search(r"var\(" + token + r",\s*[^)]+\)", css), f"{token} must be read with a fallback"
    # the layer colours are data: defined once, as variables on the picture, and used by name everywhere else
    root = re.search(r"svg\.pcb-preview\s*\{([^}]*)\}", css).group(1)
    for var in ("--c-top", "--c-bottom", "--c-multi", "--c-crit", "--c-sel", "--c-net"):
        assert re.search(var + r"\s*:\s*#[0-9a-fA-F]{3,8}", root), var
    rest = css.replace(root, "")
    assert not HEX.search(re.sub(r"var\([^)]*\)", "", rest)), "hex colours belong to the variables on the root rule"


def test_pcb_markup_has_no_colours_and_the_legend_uses_the_drawings_classes(pcb_svg):
    markup = _markup(pcb_svg)
    assert not HEX.search(markup), set(HEX.findall(markup))
    legend = re.search(r'<g class="legend"[^>]*>(.*?)</g>', pcb_svg, re.S).group(1)
    for cls in ("pad-top", "pad-bottom", "pad-multi"):
        assert f'class="{cls}' in legend, cls
        assert f".{cls}" in _style(pcb_svg)
    assert "Critical net" in legend                 # the plan names a critical net
    assert 'class="pcb-bg"' in pcb_svg


def test_pcb_picture_keeps_the_ids_and_classes_the_ui_hooks_into(pcb_svg):
    assert pcb_svg.startswith("<svg") and 'id="pcb-preview"' in pcb_svg and "pcb-preview layer-all" in pcb_svg
    for needle in ('id="pcb-layer-outline"', 'id="pcb-layer-plan"', 'id="pcb-layer-bottom"', 'id="pcb-layer-top"', "pcb-outline"):
        assert needle in pcb_svg, needle
    assert re.search(r'<g class="pcb-comp[^"]*" data-ref="[^"]+" id="pcb-comp-[^"]+"', pcb_svg)
    assert re.search(r'<rect class="pad [^"]*"[^>]* data-ref="[^"]+" data-net="[^"]*"', pcb_svg)
    assert '<g class="plan-group" data-group="Power"' in pcb_svg
    assert "plan-keepout" in pcb_svg and "Keep-out: Antenna" in pcb_svg


def test_pcb_plan_colour_is_data_but_cannot_break_out_of_the_style_attribute():
    assert preview_pcb._safe_color("#ff8800") == "#ff8800"
    assert preview_pcb._safe_color("teal") == "teal"
    for bad in ("red;} body{display:none", "url(javascript:alert(1))", '"><script>', "#12", "rgb(1,2,3)", ""):
        assert preview_pcb._safe_color(bad) == "", bad
    board = FIXTURES / "finished-board.PcbDoc"
    evil = {"groups": [{"name": "Zone", "x": 1, "y": 1, "w": 4, "h": 4, "color": "red;} body{display:none"}]}
    assert "display:none" not in preview_pcb.render_pcbdoc(board, plan=evil)
    good = {"groups": [{"name": "Zone", "x": 1, "y": 1, "w": 4, "h": 4, "color": "#ff8800"}]}
    assert 'style="--zone:#ff8800"' in preview_pcb.render_pcbdoc(board, plan=good)


def test_pcb_legend_has_no_critical_swatch_without_a_critical_net():
    svg = preview_pcb.render_pcbdoc(FIXTURES / "finished-board.PcbDoc")
    assert "Critical net" not in svg


def test_pcb_picture_without_a_pcb_says_so_in_the_words_the_ui_looks_for():
    # views/previews.js turns this text into its "No PCB linked" state
    svg = preview_pcb.render_project_pcb("no-such-project-x")
    assert "No Altium .PcbDoc linked" in svg
    assert "Settings to view PCB" in svg
    assert not HEX.search(svg.replace("var(--pcb-bg,#121820)", "").replace("var(--ink-3,#94a0bd)", ""))
