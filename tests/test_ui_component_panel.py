"""
Tests for Component Panel, Zoom/Pan controls, and stage fit in UI and server API.
"""
import json
import pathlib
import re
import threading
import urllib.error
import urllib.request
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML_PATH = REPO / "ui" / "index.html"


def read_html() -> str:
    assert HTML_PATH.is_file(), "ui/index.html must exist"
    return HTML_PATH.read_text(encoding="utf-8")


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


def test_component_panel_static_ui_markup():
    content = read_html()

    # Aside component panel element exists
    assert 'id="comp-panel"' in content
    assert 'class="comp-panel card"' in content

    # Component panel shows designator, value, MPN, package, sheet, pins, BOM line
    assert "comp-panel-ref" in content
    assert "Designator" in content
    assert "Value/Comment" in content
    assert "MPN" in content
    assert "Package" in content
    assert "Sheet" in content
    assert "BOM line" in content
    assert "comp-pins-tbl" in content

    # Action buttons: Ask about this part, Show in BOM, Close
    assert 'data-act="ask-comp"' in content
    assert "Ask about this part" in content
    assert 'data-act="show-in-bom"' in content
    assert "Show in BOM" in content
    assert 'data-act="close-comp-panel"' in content

    # Net highlighting from pins
    assert 'data-act="highlight-net"' in content
    assert "highlightNet" in content

    # Escape key closes component panel
    assert re.search(r"e\.key\s*===\s*['\"]Escape['\"].*?closeCompPanel", content)


def test_component_panel_docked_right_and_narrow_screen_responsive():
    content = read_html()

    # CSS for .preview-layout and .comp-panel
    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert style_match
    style = style_match.group(1)

    # .preview-layout is a flex row with preview-main and comp-panel
    assert re.search(r"\.preview-layout\s*\{[^}]*display\s*:\s*flex", style)
    # .comp-panel is docked card with fixed/max width (not covering whole center)
    assert re.search(r"\.comp-panel\s*\{[^}]*width\s*:\s*320px", style)

    # Responsive media queries for narrow screens: flex-direction column (panel below preview)
    assert re.search(r"@media\s*\([^)]*max-width\s*:\s*900px\)[^{]*\{[^}]*\.preview-layout\s*\{[^}]*flex-direction\s*:\s*column", style)


def test_schematic_and_pcb_zoom_controls_and_fit_to_view():
    content = read_html()

    # Zoom controls (+, -, Fit) exist for schematic and PCB
    for act in ["sch-zoom-in", "sch-zoom-out", "sch-zoom-fit", "pcb-zoom-in", "pcb-zoom-out", "pcb-zoom-fit"]:
        assert f'data-act="{act}"' in content

    # Zoom functions exist
    assert "applyZoom" in content
    assert "resetZoom" in content
    assert "initZoomPan" in content

    # Wheel zoom and mouse drag pan inside preview box
    assert "updateZoomTransform" in content
    assert re.search(r"wrap\.addEventListener\(\s*['\"]wheel['\"]", content)
    assert re.search(r"wrap\.addEventListener\(\s*['\"]mousedown['\"]", content)


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
