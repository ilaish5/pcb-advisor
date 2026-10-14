"""
Static checks for the app frame: one splitter between the sheets and the chat column, the chat width and its
collapse, the responsive frame (rail, drawer, one column) and layout persistence
(ui/index.html, ui/styles/shell.css, ui/js/shell.js).
"""
import re

from ui_source import UI, ui_all, ui_css, ui_html, ui_js

SHELL_JS = (UI / "js" / "shell.js").read_text(encoding="utf-8")
SHELL_CSS = (UI / "styles" / "shell.css").read_text(encoding="utf-8")


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


def media_block(css: str, query: str) -> str:
    """The body of the first @media block whose condition contains `query`, found by matching braces."""
    idx = css.find("@media (" + query)
    assert idx != -1, f"@media ({query}...) must exist"
    start = css.find("{", idx)
    depth, end = 1, start + 1
    while depth and end < len(css):
        depth += {"{": 1, "}": -1}.get(css[end], 0)
        end += 1
    return css[start + 1 : end - 1]


def test_one_vertical_separator_between_the_sheets_and_the_chat():
    """The only resize handle is the chat splitter: a keyboard-operable vertical separator between #panes and the chat."""
    html = ui_html()
    separators = re.findall(r'<[^>]+role=["\']separator["\'][^>]*>', html)
    assert len(separators) == 1, f"Expected exactly one separator, found {len(separators)}: {separators}"
    sep = separators[0]
    assert 'id="splitter-chat"' in sep
    assert 'aria-orientation="vertical"' in sep
    assert 'tabindex="0"' in sep, "the splitter must be reachable by keyboard"
    assert re.search(r'aria-label="[^"]+"', sep), "the splitter needs a name"
    panes = html.find('id="panes"')
    splitter = html.find('id="splitter-chat"')
    chat = html.find('<section class="chat"')
    assert -1 not in (panes, splitter, chat)
    assert panes < splitter < chat, "the splitter sits between the sheets and the chat column"


def test_localstorage_inside_try_catch():
    """Layout is persisted in localStorage; every call is wrapped in try/catch (blocked storage must not break the page)."""
    assert "localStorage" in read_html(), "the UI must use localStorage to persist layout"
    script = ui_js()
    assert script.strip(), "no scripts found under ui/js"

    lines = script.splitlines()
    ls_line_indices = [i for i, line in enumerate(lines) if "localStorage." in line]
    assert len(ls_line_indices) >= 3, "Expected localStorage calls for getItem, setItem, removeItem"

    for idx in ls_line_indices:
        prev_chunk = "\n".join(lines[max(0, idx - 10) : idx + 1])
        next_chunk = "\n".join(lines[idx : min(len(lines), idx + 10)])
        assert "try" in prev_chunk, f"localStorage on line {idx + 1} not preceded by try block"
        assert "catch" in next_chunk, f"localStorage on line {idx + 1} not followed by catch block"


def test_layout_is_saved_per_browser_and_the_side_sheet_per_project():
    assert "LAYOUT_KEY = 'pcb_advisor_shell'" in SHELL_JS
    assert re.search(r"saveLayout\(\)\s*\{[^}]*chatWidth[^}]*chatHidden", SHELL_JS), "the chat width and whether it is hidden are saved"
    assert "SIDE_KEY = 'pcb_advisor_side:'" in SHELL_JS
    assert "SIDE_KEY + PROJECT" in SHELL_JS, "the side sheet is remembered per project"
    # the keys of the removed layouts (left chat, nav width, editor tabs) are cleaned up, not read
    assert "lsDel('pcb_advisor_layout')" in SHELL_JS
    assert "lsDel('pcb_advisor_editor_tabs')" in SHELL_JS


def test_reset_layout_handler_forgets_the_saved_layout():
    """The Reset layout link lives in Settings (the pages area) and fires data-act="reset-layout"; the frame owns the handler."""
    assert "onAct('reset-layout'" in SHELL_JS
    body = re.search(r"function resetLayout\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S)
    assert body, "resetLayout() must exist"
    assert "lsDel(LAYOUT_KEY)" in body.group(1)
    assert "lsDel(SIDE_KEY + PROJECT)" in body.group(1)
    assert "chatWidth = CHAT_DEFAULT" in body.group(1)


def test_old_nav_splitter_compact_mode_and_hidden_centre_are_gone():
    content = read_html()
    assert "splitter-nav" not in content, "the nav has no resize handle any more"
    assert ".nav.compact" not in content
    assert "centerHidden" not in content, "the 'hide the centre' mode is gone"
    assert 'class="panel work"' not in content and 'class="panel chat"' not in content


def test_chat_width_is_a_css_variable_with_limits():
    assert re.search(r"setProperty\('--chat-w'", SHELL_JS), "the chat width is a CSS variable on #app"
    assert "var(--chat-w)" in SHELL_CSS
    assert re.search(r"CHAT_MIN = 300", SHELL_JS) and re.search(r"CHAT_MAX = 720", SHELL_JS)
    assert "PANES_MIN" in SHELL_JS, "the chat may not squeeze the sheets below a working width"
    for attr in ("aria-valuemin", "aria-valuemax", "aria-valuenow"):
        assert attr in SHELL_JS, f"the splitter must expose {attr}"


def test_splitter_keyboard_pointer_and_reset():
    for key in ("ArrowLeft", "ArrowRight", "Home", "End", "Enter"):
        assert f"'{key}'" in SHELL_JS, f"the splitter handles {key}"
    assert "dblclick" in SHELL_JS, "double-click resets the width"
    assert "setPointerCapture" in SHELL_JS, "dragging must keep working when the pointer leaves the handle"
    assert re.search(r"CHAT_DROP", SHELL_JS), "dragging the chat narrower than the minimum hides it"


def test_chat_can_be_hidden_and_brought_back():
    assert re.search(r"function hideChat\b", SHELL_JS) and re.search(r"function showChat\b", SHELL_JS)
    assert "(e.key === 'j' || e.key === 'J')" in SHELL_JS, "Ctrl+J toggles the chat"
    assert "onAct('toggle-chat'" in SHELL_JS
    assert re.search(r"\.app\.chat-off>\.chat[^{]*\{[^}]*display\s*:\s*none", SHELL_CSS), "a hidden chat takes no column"
    # hiding the chat while the focus is inside it must not strand the focus
    hide = re.search(r"function hideChat\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert ".focus()" in hide


def test_hidden_attribute_always_wins():
    """The hidden attribute always wins over a component's display rule (the side sheet, the detail drawer and menus rely on it)."""
    assert re.search(r"\[hidden\]\s*\{\s*display\s*:\s*none\s*!important", ui_css()), "[hidden]{display:none !important} must be kept"


def test_nav_is_a_56px_rail_at_1280():
    block = media_block(SHELL_CSS, "max-width:1280px")
    assert "--nav-w:56px" in block.replace(" ", "")
    assert re.search(r"\.nitem\s+\.lbl[^{]*\{[^}]*display\s*:\s*none", block), "labels are hidden in the rail"
    assert "title=" in SHELL_JS and "aria-label=" in SHELL_JS, "every stage button carries its name and state in title and aria-label"


def test_chat_is_a_drawer_at_1100():
    block = media_block(SHELL_CSS, "max-width:1100px")
    compact = block.replace(" ", "")
    assert ".app>.splitter" in compact and "display:none" in compact, "no splitter when the chat is a drawer"
    assert ".app.chat-open>.chat" in compact and "position:fixed" in compact
    assert "chatDrawer" in SHELL_JS and "'drawer'" in SHELL_JS
    assert "e.key === 'Escape' && chatDrawer" in SHELL_JS, "Esc closes the drawer"


def test_narrow_screen_is_one_column_with_a_work_chat_switch():
    block = media_block(SHELL_CSS, "max-width:860px")
    compact = block.replace(" ", "")
    assert "grid-template-columns:minmax(0,1fr)" in compact, "one column"
    assert '.app[data-view="chat"]>.panes{display:none}' in compact, "Chat replaces the sheets"
    assert ".viewsw{display:inline-flex" in compact, "the Work / Chat switch appears"
    assert 'data-view="work"' in SHELL_JS and 'data-view="chat"' in SHELL_JS
    assert "data-view" in ui_html(), "#app starts on the work view"


def test_handle_styles_and_cursor():
    """The splitter has a col-resize cursor, a hover line and a visible keyboard focus."""
    css = ui_css()
    assert "col-resize" in css, "Splitter must use cursor: col-resize"
    assert ".splitter:hover" in css, "Splitter must have a hover line"
    assert ".splitter:focus-visible" in css, "Splitter must show keyboard focus"
