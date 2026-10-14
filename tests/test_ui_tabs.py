"""
Static checks for center area editor groups, stages and files as tabs,
split view controls, drag & drop handlers, localStorage in try/catch,
and container-taking stage render functions (ui/index.html, ui/styles, ui/js).
"""
import pathlib
import re

from ui_source import ui_all, ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


def test_editor_groups_and_tab_structure():
    content = read_html()
    assert "editor-groups-container" in content, "Missing .editor-groups-container"
    assert "editor-group" in content, "Missing .editor-group"
    assert "editor-tabs-bar" in content, "Missing .editor-tabs-bar"
    assert "editor-tabs" in content, "Missing .editor-tabs"
    assert "editor-tab" in content, "Missing .editor-tab"

    # Stage tab mark ◆ and file badges
    assert "◆" in content or "tab-stage-mark" in content, "Stage tabs must show ◆ mark"
    for badge in ["PDF", "SCH", "PCB", "IMG", "TXT"]:
        assert badge in content, f"Missing file type badge: {badge}"

    # Tab close button
    assert 'data-act="close-tab"' in content, "Missing data-act='close-tab'"
    assert 'aria-label="Close tab"' in content or "aria-label='Close tab'" in content, (
        "Missing aria-label='Close tab'"
    )

    # Stage strip toggle
    assert 'data-act="toggle-stage-strip"' in content, "Missing data-act='toggle-stage-strip'"
    assert "toggle-stage-strip" in content


def test_split_unsplit_controls_with_aria_labels():
    content = read_html()
    # Split / unsplit controls
    assert 'data-act="split-editor"' in content, "Missing data-act='split-editor'"
    assert 'aria-label="Split editor"' in content or "aria-label='Split editor'" in content, (
        "Missing aria-label='Split editor'"
    )
    assert "⇆" in content, "Missing split button icon ⇆"
    assert 'data-act="unsplit-editor"' in content, "Missing data-act='unsplit-editor'"
    assert 'aria-label="Unsplit editor"' in content or "aria-label='Unsplit editor'" in content, (
        "Missing aria-label='Unsplit editor'"
    )
    assert "▭" in content, "Missing unsplit button icon ▭"

    # Resize divider
    assert "editor-divider" in content, "Missing .editor-divider"
    assert 'aria-label="Resize editor split"' in content or "Resize editor split" in content, (
        "Missing aria-label for resize divider"
    )

    # Double-click and keyboard resize
    assert "dblclick" in content, "Missing double-click handler for divider"
    assert "50/50" in content or "0.5" in content, "Divider must reset to 50/50 on double click"
    assert "0.12" in content, "Missing < 12% unsplit threshold"
    assert "0.88" in content, "Missing > 88% unsplit threshold"


def test_drag_and_drop_handlers():
    content = read_html()
    # Drag attributes and handlers
    assert 'draggable="true"' in content or "draggable" in content, "Tabs must be draggable"
    for evt in ["dragstart", "dragover", "dragleave", "drop", "dragend"]:
        assert evt in content, f"Missing drag event handler: {evt}"

    # Drop zones
    assert "drop-zone" in content, "Missing drop-zone"
    assert "drop-zone-left" in content, "Missing drop-zone-left"
    assert "drop-zone-right" in content, "Missing drop-zone-right"

    # Keyboard alternative Ctrl+Alt+Left/Right
    assert "ctrlKey" in content and "altKey" in content, "Missing Ctrl+Alt keyboard shortcut handler"
    assert "ArrowLeft" in content or "Left" in content, "Missing ArrowLeft keyboard navigation"
    assert "ArrowRight" in content or "Right" in content, "Missing ArrowRight keyboard navigation"


def test_localstorage_inside_try_catch_all_occurrences():
    content = read_html()
    script = ui_js()
    assert script.strip(), "no scripts found under ui/js"

    lines = script.splitlines()
    ls_line_indices = [i for i, line in enumerate(lines) if "localStorage." in line]
    assert len(ls_line_indices) >= 5, "Expected localStorage calls for layout and tabs persistence"

    for idx in ls_line_indices:
        prev_chunk = "\n".join(lines[max(0, idx - 10) : idx + 1])
        next_chunk = "\n".join(lines[idx : min(len(lines), idx + 10)])
        assert "try" in prev_chunk, f"localStorage on line {idx + 1} not preceded by try block"
        assert "catch" in next_chunk, f"localStorage on line {idx + 1} not followed by catch block"

    # Reset layout resets tabs too
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


def test_narrow_center_disables_split():
    content = read_html()
    assert "640px" in content, "Missing 640px threshold for disabling split"
    assert ".editor-divider" in content
