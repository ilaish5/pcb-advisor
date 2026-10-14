"""
Static checks for right-button pan in zoomable views (previews and diagram canvas),
context menu suppression on drag, setPointerCapture usage, PCB preview empty-state HTML text,
Idea tab full-height layout, compact diagram toolbar, and right nav overflow fix.
"""
import pathlib
import re
import pytest

from ui_source import ui_all

REPO = pathlib.Path(__file__).resolve().parent.parent
DIAGRAM_PATH = REPO / "ui" / "diagram.js"


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


def read_diagram() -> str:
    assert DIAGRAM_PATH.is_file(), "ui/diagram.js must exist"
    return DIAGRAM_PATH.read_text(encoding="utf-8")


def test_shared_pan_helper_defined_and_exported():
    """Verify shared attachPanHelper function is defined in diagram.js and exported."""
    d_content = read_diagram()
    assert "function attachPanHelper(" in d_content, "attachPanHelper must be defined in ui/diagram.js"
    assert "DiagramEditor.attachPanHelper = attachPanHelper" in d_content
    assert "window.attachPanHelper = attachPanHelper" in d_content


def test_right_button_and_middle_button_pan():
    """Verify attachPanHelper checks button === 2 (right button) and button === 1 (middle button)."""
    d_content = read_diagram()
    # Check button === 2 and button === 1 in attachPanHelper
    assert re.search(r"(?:e\.button|button)\s*===\s*2", d_content), "attachPanHelper must check button === 2 for right mouse button pan"
    assert re.search(r"(?:e\.button|button)\s*===\s*1", d_content), "attachPanHelper must check button === 1 for middle mouse button pan"


def test_contextmenu_suppression_on_drag():
    """Verify context menu is suppressed only when right button actually dragged > 4 px."""
    d_content = read_diagram()
    assert "contextmenu" in d_content, "attachPanHelper must handle contextmenu event"
    assert "preventDefault" in d_content, "attachPanHelper must call preventDefault on contextmenu"
    # Check > 4 px drag threshold
    assert re.search(r">\s*4", d_content), "attachPanHelper must check drag movement > 4 px"


def test_pointer_capture_and_pointer_events():
    """Verify pointer events and setPointerCapture are used so drag continues outside the box."""
    d_content = read_diagram()
    assert "pointerdown" in d_content, "attachPanHelper must listen to pointerdown"
    assert "pointermove" in d_content, "attachPanHelper must listen to pointermove"
    assert "pointerup" in d_content, "attachPanHelper must listen to pointerup"
    assert "setPointerCapture" in d_content, "attachPanHelper must use setPointerCapture"
    assert "releasePointerCapture" in d_content, "attachPanHelper must release pointer capture on up"


def test_cursor_grabbing_while_panning():
    """Verify cursor: grabbing is shown while panning."""
    d_content = read_diagram()
    h_content = read_html()
    assert "grabbing" in d_content, "attachPanHelper must set cursor to grabbing during pan"
    assert "cursor: grabbing" in d_content or "cursor:grabbing" in d_content or "cursor:grabbing" in h_content or "cursor: grabbing" in h_content


def test_both_previews_use_shared_pan_helper():
    """Verify both schematic preview and PCB preview use initZoomPan with attachPanHelper."""
    h_content = read_html()
    # initZoomPan references attachPanHelper
    assert "attachPanHelper" in h_content, "initZoomPan must use the shared attachPanHelper"
    # Both schematic and PCB preview initialize zoom/pan (views/previews.js hands each canvas its own zoom state)
    assert re.search(r"initZoomPan\(\s*wrap\s*,\s*schZoom\)", h_content), "Schematic preview must use initZoomPan"
    assert re.search(r"initZoomPan\(\s*wrap\s*,\s*pcbZoom\)", h_content), "PCB preview must use initZoomPan"
    assert 'id="schwrap"' in h_content and 'id="pcbwrap"' in h_content


def test_empty_space_left_pan_in_previews_preserves_clicks():
    """Verify previews allow left-drag only on empty space, preserving component/net clicks."""
    h_content = read_html()
    # Left drag on empty space checks for non-interactive targets
    assert re.search(r"e\.button\s*===\s*0", h_content), "initZoomPan must handle button === 0 for left-drag on empty space"
    assert "g.part" in h_content and "pcb-comp" in h_content, "interactive elements check must include components"
    # Net labels, power ports, pads and zones stay clickable too
    assert "g.net-label" in h_content and "rect.pad" in h_content and "g.plan-group" in h_content
    # Component clicks still check didDrag (drag > 4 px is not a click)
    assert "z.didDrag" in h_content or "schZoom.didDrag" in h_content
    assert "zoomState.didDrag" in h_content


def test_diagram_editor_uses_shared_pan_helper():
    """Verify DiagramEditor binds attachPanHelper on its canvas."""
    d_content = read_diagram()
    assert re.search(r"this\.panHelper\s*=\s*attachPanHelper\(\s*this\.svgEl", d_content), "DiagramEditor must attach shared panHelper to this.svgEl"


def test_pcb_empty_state_text_html_centered():
    """The no-PCB state is a normal-size HTML empty state centred in the sheet, not text scaled with an SVG."""
    h_content = read_html()
    assert "formatPcbPreview" in h_content, "formatPcbPreview helper must format PCB preview content"
    assert "Settings to view PCB" in h_content, "Empty state detection must check for the server's Settings to view PCB message"
    assert "pcb-empty-state" in h_content, "HTML empty state element must use pcb-empty-state class"
    assert "emptyState('No PCB linked'" in h_content and "Link a project" in h_content
    # Centred, in the sheet's own stylesheet
    css = (REPO / "ui" / "styles" / "previews.css").read_text(encoding="utf-8")
    rule = re.search(r"\.pcb-empty-state\s*\{([^}]*)\}", css).group(1)
    assert "justify-content:center" in rule.replace(" ", "")
    assert "align-items:center" in rule.replace(" ", "")


def test_idea_tab_layout_no_vertical_scroll():
    """Verify Idea tab does not scroll: requirements card is compact, canvas flex: 1, min-height: 0."""
    h_content = read_html()
    # .idea-layout flex column, min-height: 0, flex: 1
    assert re.search(r"\.idea-layout\s*\{[^}]*display\s*:\s*flex", h_content)
    assert re.search(r"\.idea-layout\s*\{[^}]*flex-direction\s*:\s*column", h_content)
    assert re.search(r"\.idea-layout\s*\{[^}]*min-height\s*:\s*0", h_content)
    assert re.search(r"\.idea-layout\s*\{[^}]*flex\s*:\s*1", h_content)

    # Diagram card flex: 1, min-height: 0
    assert re.search(r"\.diagram-card\s*\{[^}]*flex\s*:\s*1", h_content)
    assert re.search(r"\.diagram-card\s*\{[^}]*min-height\s*:\s*0", h_content)

    # Compact requirements card
    assert re.search(r"\.agreed-card\s*\{[^}]*max-height\s*:\s*130px", h_content) or re.search(r"agreed-card.*max-height", h_content)

    # Tab body view with idea stage does not scroll
    assert re.search(r"\.stage-idea[^{]*\{[^}]*overflow\s*:\s*hidden", h_content) or re.search(r"has\(\.idea-layout\)[^{]*\{[^}]*overflow\s*:\s*hidden", h_content)


def test_diagram_toolbar_compact_one_or_two_rows():
    """Verify diagram toolbar fits in one or two rows (row-gap, compact button styling, hidden SVG labels)."""
    d_content = read_diagram()
    assert "row-gap" in d_content, "Toolbar must specify row-gap for clean 1-2 row wrapping"
    assert re.search(r"\.diag-tb-btn\s+svg\s*\+\s*span\s*\{\s*display\s*:\s*none", d_content), "SVG icon button label spans should be hidden to fit toolbar in 1-2 rows"


def test_right_nav_no_horizontal_scroll():
    """Verify the nav has overflow-x:hidden, labels ellipsis, and the muted count (.hint) is always visible."""
    h_content = read_html()
    # .nav has overflow-x:hidden
    assert re.search(r"(?m)^\.nav\s*\{[^}]*overflow-x\s*:\s*hidden", h_content), ".nav must have overflow-x:hidden"
    # .nitem .lbl has ellipsis
    assert re.search(r"\.nitem\s+\.lbl\s*\{[^}]*text-overflow\s*:\s*ellipsis", h_content), ".nitem .lbl must have text-overflow:ellipsis"
    # .nitem .hint (the count next to a stage) has flex:none so it is never cut off
    assert re.search(r"\.nitem\s+\.hint\s*\{[^}]*flex\s*:\s*none", h_content), ".nitem .hint must have flex:none so counts are always visible"
    # the project name ellipsizes too (a long name must not widen the nav)
    assert re.search(r"\.proj\s+\.nm\s*\{[^}]*text-overflow\s*:\s*ellipsis", h_content), ".proj .nm must have text-overflow:ellipsis"
