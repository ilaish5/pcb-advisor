"""
Static checks that the app fits the window: the sheet may shrink, wide content scrolls inside it, the frame
changes shape at 1280 / 1100 / 860 px, and the chat width follows the window (ui/styles, ui/js/shell.js).
"""
import re

from ui_source import UI, ui_all, ui_css

SHELL_JS = (UI / "js" / "shell.js").read_text(encoding="utf-8")
SHELL_CSS = (UI / "styles" / "shell.css").read_text(encoding="utf-8")


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


def media_block(css: str, query: str) -> str:
    idx = css.find("@media (" + query)
    assert idx != -1, f"@media ({query}...) must exist"
    start = css.find("{", idx)
    depth, end = 1, start + 1
    while depth and end < len(css):
        depth += {"{": 1, "}": -1}.get(css[end], 0)
        end += 1
    return css[start + 1 : end - 1]


def test_no_fixed_min_width_on_svg_rules():
    """No min-width:760px or min-width:980px on an svg rule, and the drawings fill their canvas instead."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"

    # Check for forbidden fixed min-width rules on SVGs (760px and 980px)
    assert not re.search(
        r"svg[^{]*\{[^}]*min-width\s*:\s*(?:760|980)px", style, re.IGNORECASE
    ), "Found forbidden min-width:760px or min-width:980px on an svg rule"

    # The schematic and the layout drawings sit in .pv-canvas and take its whole size (they scale with the sheet)
    m = re.search(r"\.pv-canvas\s*>\s*svg\s*\{([^}]+)\}", style)
    assert m, ".pv-canvas>svg must exist"
    body = m.group(1).replace(" ", "")
    assert "width:100%" in body and "height:100%" in body
    assert "min-width" not in body

    # The diagram keeps its own rule
    m = re.search(r"svg\.diag-svg\s*\{([^}]+)\}", style)
    if m:
        assert "min-width:760px" not in m.group(1).replace(" ", "")
        assert "min-width:980px" not in m.group(1).replace(" ", "")


def test_view_has_overflow_x_hidden():
    """Verify .view has overflow-x:hidden, scrolls vertically, and is a size container for the views' container queries."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"

    m = re.search(r"\.view\s*\{([^}]+)\}", style)
    assert m, "CSS rule for .view must exist"
    view_body = m.group(1).replace(" ", "")

    assert "overflow-x:hidden" in view_body, f".view must have overflow-x:hidden, found: {m.group(1)}"
    assert "overflow-y:auto" in view_body, f".view must have overflow-y:auto, found: {m.group(1)}"
    assert "container-type:inline-size" in view_body, f".view must be an inline-size container, found: {m.group(1)}"
    assert "min-width:0" in view_body, ".view must be allowed to shrink inside a flex or grid parent"


def test_first_view_rule_is_the_core_one():
    """core.css loads before every view stylesheet and its .view rule comes first, so a view can only refine it."""
    core = (UI / "styles" / "core.css").read_text(encoding="utf-8")
    first_rule = re.search(r"^[^/\s][^{]*\{", core, re.M).group(0)
    assert first_rule.strip() == ".view{", first_rule
    html = read_html()
    assert html.find("/ui/styles/core.css") < html.find("/ui/styles/shell.css") < html.find("/ui/styles/chat.css")


def test_the_sheets_can_shrink_so_wide_content_never_pushes_the_chat_out():
    assert "minmax(0,1fr)" in SHELL_CSS.replace(" ", ""), "the middle column of the frame must be minmax(0,1fr)"
    for rule in (r"\.app>\*\s*\{[^}]*min-width\s*:\s*0", r"\.pane\s*\{[^}]*min-width\s*:\s*0", r"\.panes\s*\{[^}]*display\s*:\s*flex"):
        assert re.search(rule, SHELL_CSS), f"shell.css must match {rule}"
    pane = re.search(r"\.pane\s*\{([^}]+)\}", SHELL_CSS).group(1).replace(" ", "")
    assert "overflow:hidden" in pane, "a sheet clips; its .view scrolls"
    assert "flex:11" in pane or "flex:1 1" in re.search(r"\.pane\s*\{([^}]+)\}", SHELL_CSS).group(1), "two sheets share the width equally"


def test_wide_tables_scroll_inside_their_own_wrapper():
    core = (UI / "styles" / "core.css").read_text(encoding="utf-8").replace(" ", "")
    assert ".tblwrap{overflow-x:auto}" in core


def test_nav_scrolls_when_the_window_is_short_and_never_sideways():
    nav = re.search(r"^\.nav\s*\{([^}]+)\}", SHELL_CSS, re.M).group(1).replace(" ", "")
    assert "overflow-y:auto" in nav and "overflow-x:hidden" in nav


def test_frame_changes_shape_at_three_widths():
    rail = media_block(SHELL_CSS, "max-width:1280px").replace(" ", "")
    assert "--nav-w:56px" in rail, "<=1280px: the nav is a 56px rail"
    drawer = media_block(SHELL_CSS, "max-width:1100px").replace(" ", "")
    assert ".app.chat-open>.chat" in drawer and "position:fixed" in drawer, "<=1100px: the chat is a drawer"
    one = media_block(SHELL_CSS, "max-width:860px").replace(" ", "")
    assert "grid-template-columns:minmax(0,1fr)" in one, "<=860px: one column"
    # the same widths drive the script (chatMode), so CSS and JS cannot disagree
    assert "(max-width:1100px)" in SHELL_JS and "(max-width:860px)" in SHELL_JS


def test_chat_width_follows_the_window():
    assert re.search(r"addEventListener\(\s*'resize'", SHELL_JS), "a window resize re-clamps the chat width"
    assert re.search(r"matchMedia\(mq\)\.addEventListener\(\s*'change'", SHELL_JS), "crossing a breakpoint re-syncs the frame"
    assert re.search(r"function maxChatWidth\(\)", SHELL_JS) and "PANES_MIN" in SHELL_JS


def test_command_palette_result_scrolls_into_view():
    palette = (UI / "js" / "palette.js").read_text(encoding="utf-8")
    assert re.search(r"scrollIntoView\(\s*\{\s*block\s*:\s*'nearest'\s*\}", palette), "the highlighted result stays visible while arrowing"
    assert "scrollIntoView({block: 'center'})" in palette, "a part picked in the palette is scrolled to in the BOM"


def test_idea_layout_responsive():
    """The Idea sheet answers to the width and height of its own sheet (a container query), not to the window."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"
    idea = (UI / "styles" / "idea.css").read_text(encoding="utf-8")
    flat = idea.replace(" ", "")

    # .view is the size container, so the rules below follow the sheet when one or two sheets share the window
    assert "container-type:inline-size" in re.search(r"\.view\s*\{([^}]+)\}", style).group(1).replace(" ", "")
    assert re.search(r"@container\(max-width:\d+px\)\{[^}]*\.idea-prop\{flex-wrap:wrap\}", flat), (
        "a narrow sheet: the proposal bar wraps its buttons under the message"
    )

    # a short window: the list gives way (a capped, scrolling list) and the canvas keeps a minimum height
    assert re.search(r"\.idea-reqs\{[^}]*max-height:\d+%", flat)
    assert re.search(r"\.idea-reqs:has\(\.req-add-form:not\(\[hidden\]\)\)[^{]*\{max-height:\d+%", flat), "an open form gets more room"
    assert re.search(r"\.idea-canvas\{[^}]*min-height:\d+px", flat)

    # the toolbar wraps to a second row inside a narrow canvas instead of overflowing it
    assert re.search(r"\.diag-rail\{[^}]*flex-wrap:wrap", flat)
    assert "overflow-x" not in re.search(r"\.req-scroll\{([^}]*)\}", flat).group(1), "long words wrap in a requirement; nothing scrolls sideways"
    assert "overflow-wrap:anywhere" in flat
