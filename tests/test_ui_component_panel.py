"""
Tests for the inspector (the right-hand drawer), the zoom and pan controls of the two previews, stage fit,
and the component endpoint behind the inspector.
"""
import json
import pathlib
import re
import threading
import urllib.error
import urllib.request
import pytest

from ui_source import ui_all, ui_css

REPO = pathlib.Path(__file__).resolve().parent.parent


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


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


def get(base, path, project, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={project}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_component_endpoint_missing_ref(server, lte):
    code, body = get(server, "/api/sch/component", lte)
    assert code == 400
    assert "ref required" in body.get("error", "")


def test_component_endpoint_unknown_ref(server, lte):
    code, body = get(server, "/api/sch/component?ref=U999", lte)
    assert code == 404
    assert "not found" in body.get("error", "")


def test_component_endpoint_valid_component(server, lte):
    code, body = get(server, "/api/sch/component?ref=U1", lte)
    assert code == 200
    assert body["ref"] == "U1"
    assert "sheet" in body
    assert "pins" in body
    assert isinstance(body["pins"], list)
    assert "params" in body
    assert "bom" in body
    assert body["value"] or body.get("comment") or body.get("mpn")


def _view(name):
    return (REPO / "ui" / "js" / "views" / name).read_text(encoding="utf-8")


def _style(name):
    return (REPO / "ui" / "styles" / name).read_text(encoding="utf-8")


def _func(src, name):
    """The text of a top-level function: from 'function name(' to the next top-level declaration."""
    m = re.search(rf"^(?:async )?function {name}\(", src, re.M)
    assert m, f"function {name} must exist"
    nxt = re.search(r"^(?:async )?function \w+\(|^(?:const|let|onAct|document\.)", src[m.end():], re.M)
    return src[m.start(): m.end() + (nxt.start() if nxt else len(src))]


# ---------------------------------------------------------------------------------------------------
# The inspector: the one right-hand drawer (views/inspector.js). It replaced the component panel that lived inside the
# schematic and layout views (comp-panel, openCompPanel, the sel-bars) and the BOM-only detail panel.
# ---------------------------------------------------------------------------------------------------
def test_the_component_panel_and_the_selection_bars_are_gone():
    content = read_html()
    for gone in ("comp-panel", "compPanel", "openCompPanel", "renderCompPanel", "sel-bar", "preview-layout", "plan-card",
                 "ask-comp", "show-in-bom", "ask-anchor", "ask-sch", "ask-pcb", "clear-sch-sel", "clear-pcb-sel", "highlight-net"):
        assert gone not in _view("previews.js") + _view("inspector.js") + _style("previews.css") + _style("inspector.css"), gone
    assert "function inspectorHTML(" in _view("inspector.js")
    # the shell hands the drawer whatever the inspector returns
    assert "inspectorHTML()" in _func((REPO / "ui" / "js" / "core.js").read_text(encoding="utf-8"), "renderDetail")
    assert content.count("function inspectorHTML(") == 1


def test_inspector_part_sections_and_header():
    src = _view("inspector.js")
    # header: one primary Ask, a menu with the secondary things, a close button
    part = _func(src, "inspPartHTML")
    assert re.search(r"btn\('Ask',\s*\{kind: 'pri'", part)
    assert part.count("kind: 'pri'") == 1, "one primary button in the part inspector"
    for label in ("Alternatives", "Show on schematic", "Show on layout", "Open datasheet"):
        assert label in part, label
    assert "menu(" in part and "act: 'close'" in src
    # sections without boxes, in the specified order
    order = [part.index(x) for x in ("insp-where-h", "insp-nets-h", "inspStockHTML(l)", "inspLibHTML(l)", "inspDatasheetHTML(l)", "insp-pins-h")]
    assert order == sorted(order)
    for title in ("Where used", "Nets", "Stock and price", "Library", "Datasheet"):
        assert f"'{title}'" in src, title
    # pins are collapsed by default and come from /api/sch/component
    assert "details" in src and "Pins of " in src and "/api/sch/component" in src
    assert not re.search(r"<details[^>]*\bopen\b(?!=)", src.replace("${inspPinsOpen ? ' open' : ''}", ""))


def test_inspector_role_note_and_mpn_are_edited_in_place_and_saved_by_the_bom_handler():
    src = _view("inspector.js")
    for field in ("mpn", "role", "note"):
        assert f"field('{field}'" in src, field
    assert 'class="in quiet' in src and 'data-edit="${name}" data-line="${esc(l.key)}"' in src
    # the save lives with the BOM (one /api/bom/edit handler for every input[data-edit])
    bom = _view("bom.js")
    assert "data-edit" in bom and "/api/bom/edit" in bom


def test_inspector_library_row_and_its_contextual_action():
    src = _view("inspector.js")
    lib = _func(src, "inspLibHTML")
    assert "Symbol" in lib and "Footprint" in lib and "3D" in lib and "STEP" in lib
    # Accept once verified and not yet accepted; Verify while it is not verified and a symbol exists; neither otherwise
    assert re.search(r"e\.verify === 'pass' && !e\.accepted\s*\?\s*btn\('Accept'.*accept: l\.key", lib, re.S)
    assert re.search(r":\s*e\.verify !== 'pass' && e\.symbol\s*\?\s*btn\('Verify'.*verify: l\.key", lib, re.S)
    # the generic data-accept / data-verify routes in core.js do the work
    core = (REPO / "ui" / "js" / "core.js").read_text(encoding="utf-8")
    assert "d.accept" in core and "d.verify" in core
    assert "Altium default library" in lib


def test_inspector_datasheet_section_gets_or_opens_the_datasheet():
    src = _view("inspector.js")
    ds = _func(src, "inspDatasheetHTML")
    assert "None stored" in ds and "act: 'get-datasheet'" in ds and "src: l.datasheet" in ds


def test_inspector_nets_are_buttons_that_do_something():
    """The old net chips were dead data-net buttons."""
    src = _view("inspector.js")
    assert 'class="insp-net" data-act="pick-net" data-net=' in src
    handler = re.search(r"onAct\('pick-net'.*?\n\}\);", src, re.S).group(0)
    assert "pickNet(d.net)" in handler and "revealNet" in handler
    css = _style("inspector.css")
    assert re.search(r"\.insp-net\s*\{[^}]*color\s*:\s*var\(--net\)", css), "nets are violet"
    # a long list stays short until asked
    assert "insp-more" in src and "INSP_CAP" in src


def test_inspector_net_and_zone_views_and_the_ask_contexts():
    src = _view("inspector.js")
    assert "function inspNetHTML(" in src and "function inspZoneHTML(" in src and "function inspRefHTML(" in src
    assert "Connected parts" in src
    for kind, act in (("part", "insp-ask"), ("net", "ask-net"), ("zone", "ask-zone")):
        assert re.search(rf"askAbout\(\{{kind: '{kind}'", src), kind
        assert f"onAct('{act}'" in src, act
    # the BOM's own row button keeps its own action name, the two must not share one
    assert "onAct('ask-part'" not in src


def test_inspector_acts_all_have_handlers_and_do_not_collide_with_the_bom():
    inspector, previews, bom = _view("inspector.js"), _view("previews.js"), _view("bom.js")
    mine = ["close", "insp-ask", "ask-net", "ask-zone", "show-sch", "show-pcb", "pick-net", "pick-part", "hl-net", "insp-more",
            "sch-sheet", "sch-retry", "pcb-retry", "toggle-layer", "pv-link",
            "sch-zoom-in", "sch-zoom-out", "sch-zoom-fit", "pcb-zoom-in", "pcb-zoom-out", "pcb-zoom-fit"]
    for act in mine:
        owners = [n for n, t in (("inspector", inspector), ("previews", previews)) if f"onAct('{act}'" in t]
        assert len(owners) == 1, f"{act} must be handled in exactly one of my files, found {owners}"
        assert f"onAct('{act}'" not in bom, f"{act} collides with bom.js"
    # the ones the inspector borrows from the BOM are theirs
    for act in ("alts", "get-datasheet"):
        assert f"onAct('{act}'" in bom and f"onAct('{act}'" not in inspector + previews


def test_escape_closes_the_inspector_unless_something_is_on_top():
    src = _view("inspector.js")
    m = re.search(r"document\.addEventListener\('keydown'.*?\n\}\);", src, re.S)
    assert m
    h = m.group(0)
    assert "'Escape'" in h and "closeInspector()" in h
    for guard in ("defaultPrevented", "uiBusy()", "bomDrawer", "#viewer"):
        assert guard in h, guard


def test_selection_toggles_classes_and_never_redraws_the_drawing():
    """Re-rendering the SVG on a click reset the zoom and flickered."""
    prev = _view("previews.js")
    insp = _view("inspector.js")
    for name in ("applyFocus", "highlightNet", "pvKeepClear"):
        body = _func(prev, name)
        assert "innerHTML" not in body and "renderCenter" not in body and "render(" not in body, name
        assert "classList.toggle" in body or name == "pvKeepClear", name
    for name in ("pickNet", "pickZone", "closeInspector", "inspRefresh"):
        body = _func(insp, name)
        assert "renderCenter" not in body, name
    # picking a part off the drawing selects it; it does not rebuild the sheet either
    assert "pickPart(" in _func(prev, "afterSheet") + prev  # wired in the click delegate
    assert "g.part.sel" in prev and "g.pcb-comp.sel" in prev


def test_the_drawing_slides_aside_for_the_drawer_and_the_zoom_stays():
    prev = _view("previews.js")
    assert "function pvKeepClear(" in prev and "function pvViewport(" in prev
    assert "pvKeepClear" in _view("inspector.js")
    # no per-selection zoom reset in the keep-clear path
    assert "z.scale" not in _func(prev, "pvKeepClear")


def test_schematic_and_pcb_zoom_controls_and_fit_to_view():
    content = read_html()

    # Zoom controls (-, +, Fit) float in the canvas of both previews: one helper builds them for either kind
    prev = _view("previews.js")
    for suffix in ("zoom-out", "zoom-in", "zoom-fit"):
        assert f"act: kind + '-{suffix}'" in prev, suffix
    for act in ["sch-zoom-in", "sch-zoom-out", "sch-zoom-fit", "pcb-zoom-in", "pcb-zoom-out", "pcb-zoom-fit"]:
        assert f"onAct('{act}'" in prev, act

    # Zoom functions exist
    assert "applyZoom" in content
    assert "resetZoom" in content
    assert "initZoomPan" in content

    # Wheel zoom and mouse drag pan inside preview box
    assert "updateZoomTransform" in content
    assert re.search(r"wrap\.addEventListener\(\s*['\"]wheel['\"]", content)
    assert re.search(r"wrap\.addEventListener\(\s*['\"]mousedown['\"]", content)


def test_the_two_previews_fill_the_sheet_and_the_drawing_fills_its_canvas():
    css = _style("previews.css")
    pv = re.search(r"\.pv\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    for decl in ("display:flex", "flex-direction:column", "height:100%", "min-width:0"):
        assert decl in pv, decl
    stage = re.search(r"\.pv-stage\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "flex:1" in stage and "min-height:0" in stage
    canvas = re.search(r"\.pv-canvas>svg\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "width:100%" in canvas and "height:100%" in canvas
    assert "min-width:760px" not in css and "min-width:980px" not in css
    # the canvas colours are the tokens, in both themes
    assert re.search(r"\.sch-canvas\s*\{[^}]*var\(--sch-bg\)", css)
    assert re.search(r"\.pcb-canvas\s*\{[^}]*var\(--pcb-bg\)", css)


def test_area_files_use_tokens_not_hex_colours():
    for name in ("previews.css", "inspector.css"):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", _style(name)), name
    for name in ("previews.js", "inspector.js"):
        code = re.sub(r"//[^\n]*|/\*.*?\*/", "", _view(name), flags=re.S)
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", code), name


def test_the_layout_view_offers_what_exists():
    """The plan counts and the Plan layer only appear when there is a plan: 3/1/2 used to be invented."""
    src = _view("previews.js")
    plan = _func(src, "pvPlan")
    assert "return null" in plan
    html = _func(src, "pcbHTML")
    assert "pvPlan()" in html
    assert not re.search(r"\b3 zones|\b1 keep-out|\b2 critical", src)
    assert "No PCB linked" in src and "Link a project" in src and "act: 'pv-link'" in src


def test_stage_fit_and_block_diagram_scaling():
    content = read_html()

    # Block diagram SVG has viewBox, width=100%, height=100%, and preserveAspectRatio
    diag_match = re.search(r'<svg[^>]*id=["\']diag-svg["\'][^>]*>', content)
    assert diag_match, "diag-svg element must exist"
    tag = diag_match.group(0)
    assert 'viewBox="0 0 860 520"' in tag or "viewBox='0 0 860 520'" in tag
    assert 'width="100%"' in tag or "width='100%'" in tag
    assert 'height="100%"' in tag or "height='100%'" in tag
    assert "preserveAspectRatio" in tag

    # Requirements list has inner scrolling container
    assert "overflow-y:auto" in content or "overflow-y: auto" in content
