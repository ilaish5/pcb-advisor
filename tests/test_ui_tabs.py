"""
Static checks for what the frame shows: one main sheet and an optional side sheet (no editor groups, tab bars or
drag and drop), the stage trace as the one way to navigate, documents opening in the side sheet, localStorage in try/catch,
and container-taking stage render functions (ui/index.html, ui/styles, ui/js).
"""
import re

from ui_source import UI, ui_all, ui_html, ui_js

SHELL_JS = (UI / "js" / "shell.js").read_text(encoding="utf-8")
CORE_JS = (UI / "js" / "core.js").read_text(encoding="utf-8")
BOOT_JS = (UI / "js" / "boot.js").read_text(encoding="utf-8")
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


def test_main_sheet_side_sheet_and_inspector_structure():
    html = ui_html()
    # the main sheet holds its view and the inspector drawer; the side sheet has its own small header and view
    assert re.search(r'<main class="pane work" id="work"[^>]*>.*?id="view".*?id="detail"[^>]*hidden', html, re.S)
    assert re.search(r'<section class="pane side" id="side"[^>]*hidden>\s*<header class="side-h" id="side-h">.*?id="view-side"', html, re.S)
    for name in ("function mainView", "function sideView", "function renderMain", "function renderSide", "function openSide", "function closeSide", "function swapSheets", "function toggleSide"):
        assert name in SHELL_JS, f"shell.js must define {name}"
    # the side header: a menu to pick what it shows, swap, close
    head = re.search(r"function sideHeadHTML\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    for token in ("menu(", "side-swap", "side-close"):
        assert token in head
    assert "act: 'side-set'" in SHELL_JS and "onAct('side-set'" in SHELL_JS


def test_editor_groups_tab_bars_and_drag_and_drop_are_gone():
    # the frame's own files (the views' stylesheets are checked by their owners)
    core_css = (UI / "styles" / "core.css").read_text(encoding="utf-8")
    content = "\n".join([ui_html(), ui_js(), SHELL_CSS, core_css])
    for gone in ("editor-groups-container", "editor-group", "editor-tabs-bar", "editor-tab", "editor-divider", "close-tab",
                 "toggle-stage-strip", "split-editor", "unsplit-editor", "drop-zone", 'id="whead"', "tab-stage-mark"):
        assert gone not in content, f"{gone} belongs to the old editor tabs and must be gone"


def test_the_stage_trace_is_the_one_way_to_navigate():
    nav = re.search(r"function navHTML\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert 'class="trace"' in nav and 'data-tab="${id}"' in nav, "one button per stage in the trace"
    assert 'aria-current="page"' in nav, "the open sheet is marked for assistive technology"
    assert "data-page=" in nav, "Library, Sources and Settings are pages"
    assert re.search(r"STAGES = \[\['idea', 'Idea'\], \['bom', 'BOM'\], \['sch', 'Schematic'\], \['pcb', 'Layout'\], \['rules', 'Rules'\], \['outputs', 'Outputs'\], \['checks', 'DFM'\]\]", SHELL_JS), \
        "stage ids stay, labels are the new names"
    # the click delegate: d.tab -> a stage, d.page -> a page; both go through go()
    assert "go('workspace', d.tab)" in CORE_JS and "go(d.page)" in CORE_JS
    # go(page, tab) and select(key) stay global, the test harness drives them
    assert re.search(r"function go\(p, t\)", SHELL_JS) and re.search(r"function select\(key", CORE_JS)


def test_page_and_tab_in_the_url_are_honoured_on_load():
    assert "URLQ.get('page')" in BOOT_JS and "URLQ.get('tab')" in BOOT_JS
    assert "initMain(initialMain())" in BOOT_JS, "the first sheet is set before the first paint"
    assert "restoreSide()" in BOOT_JS, "the side sheet comes back per project"


def test_documents_open_in_the_side_sheet_and_a_sheet_is_never_shown_twice():
    body = re.search(r"function openFileAsTab\(info\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "openSide(" in body, "a document opens the side sheet"
    assert "already open in the main sheet" in SHELL_JS, "the same stage is not shown in both sheets (global preview ids)"
    set_main = re.search(r"function setMain\(item\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "sideItem = mainItem" in set_main, "going to what the side sheet shows swaps the sheets"


def test_narrow_screen_the_side_sheet_covers_the_main_sheet():
    block = media_block(SHELL_CSS, "max-width:860px").replace(" ", "")
    assert ".pane.side{position:absolute;inset:0" in block
    assert ".app.has-side.pane.work{visibility:hidden}" in block, "the covered sheet must not take keyboard focus"


def test_localstorage_inside_try_catch_all_occurrences():
    content = read_html()
    script = ui_js()
    assert script.strip(), "no scripts found under ui/js"

    lines = script.splitlines()
    ls_line_indices = [i for i, line in enumerate(lines) if "localStorage." in line]
    assert len(ls_line_indices) >= 5, "Expected localStorage calls for layout, the side sheet and the theme"

    for idx in ls_line_indices:
        prev_chunk = "\n".join(lines[max(0, idx - 10) : idx + 1])
        next_chunk = "\n".join(lines[idx : min(len(lines), idx + 10)])
        assert "try" in prev_chunk, f"localStorage on line {idx + 1} not preceded by try block"
        assert "catch" in next_chunk, f"localStorage on line {idx + 1} not followed by catch block"

    # Reset layout forgets the side sheet too
    assert "resetLayout" in content
    assert "reset-layout" in content


def test_stage_render_functions_take_container():
    content = read_html()
    # Stage render functions taking container parameter
    assert re.search(r"function\s+bomHTML\s*\(\s*container\b", content), "bomHTML must take container parameter"
    assert re.search(r"function\s+schHTML\s*\(\s*container\b", content), "schHTML must take container parameter"
    assert re.search(r"function\s+pcbHTML\s*\(\s*container\b", content), "pcbHTML must take container parameter"
    assert re.search(r"function\s+ideaHTML\s*\(\s*container\b", content), "ideaHTML must take container parameter"
    assert re.search(r"function\s+rulesHTML\s*\(\s*container\b", content), "rulesHTML must take container parameter"
    assert re.search(r"function\s+outputsHTML\s*\(\s*container\b", content), "outputsHTML must take container parameter"
    assert re.search(r"function\s+checksHTML\s*\(\s*container\b", content), "checksHTML must take container parameter"
    assert re.search(r"function\s+renderStage\s*\([^)]*container[^)]*\)", content), "renderStage must take container parameter"
