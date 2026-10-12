"""
Static checks for UI resize handles, collapse/restore, compact navigation,
and layout persistence in ui/index.html.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML_PATH = REPO / "ui" / "index.html"


def read_html() -> str:
    assert HTML_PATH.is_file(), "ui/index.html must exist"
    return HTML_PATH.read_text(encoding="utf-8")


def test_two_vertical_separator_elements():
    """Ensure exactly two elements with role='separator' exist with vertical orientation."""
    content = read_html()
    separators = re.findall(r'<[^>]+role=["\']separator["\'][^>]*>', content)
    assert len(separators) == 2, f"Expected exactly two separators, found {len(separators)}: {separators}"

    for sep in separators:
        assert 'aria-orientation="vertical"' in sep or "aria-orientation='vertical'" in sep, (
            f"Separator missing aria-orientation='vertical': {sep}"
        )

    # Verify positions: one between chat and work, one between work and nav
    chat_idx = content.find('class="panel chat"')
    work_idx = content.find('class="panel work"')
    nav_idx = content.find('class="nav"')

    assert chat_idx != -1 and work_idx != -1 and nav_idx != -1

    sep1_idx = content.find('id="splitter-chat"')
    sep2_idx = content.find('id="splitter-nav"')

    assert sep1_idx != -1 and sep2_idx != -1
    assert chat_idx < sep1_idx < work_idx, "splitter-chat must be between chat and work panels"
    assert work_idx < sep2_idx < nav_idx, "splitter-nav must be between work and nav panels"


def test_localstorage_inside_try_catch():
    """Verify localStorage is used to persist layout and every call is wrapped in try/catch."""
    content = read_html()
    assert "localStorage" in content, "ui/index.html must use localStorage to persist layout"

    # Find script section
    script_match = re.search(r"<script>(.*)</script>", content, re.DOTALL)
    assert script_match, "<script> block not found in ui/index.html"
    script = script_match.group(1)

    lines = script.splitlines()
    ls_line_indices = [i for i, line in enumerate(lines) if "localStorage." in line]
    assert len(ls_line_indices) >= 3, "Expected localStorage calls for getItem, setItem, removeItem"

    for idx in ls_line_indices:
        prev_chunk = "\n".join(lines[max(0, idx - 10) : idx + 1])
        next_chunk = "\n".join(lines[idx : min(len(lines), idx + 10)])
        assert "try" in prev_chunk, f"localStorage on line {idx + 1} not preceded by try block"
        assert "catch" in next_chunk, f"localStorage on line {idx + 1} not followed by catch block"


def test_reset_layout_control():
    """Ensure a 'Reset layout' control exists in settings and has event handling."""
    content = read_html()
    assert "Reset layout" in content, "ui/index.html must contain a 'Reset layout' control"

    # Verify button exists in settings HTML
    assert re.search(r'<button[^>]+data-act=["\']reset-layout["\'][^>]*>\s*Reset layout\s*</button>', content), (
        "Expected a button with data-act='reset-layout' labeled 'Reset layout'"
    )

    # Verify event handler or function resets layout
    assert "reset-layout" in content
    assert "resetLayout" in content


def test_nav_compact_rules_exist():
    """Ensure .nav.compact CSS rules exist for narrow navigation mode (~60px to ~150px)."""
    content = read_html()

    assert ".nav.compact" in content, "CSS must define .nav.compact rules"
    assert re.search(r"\.nav\.compact\b[^{]*\{", content), "Missing .nav.compact selector"
    assert re.search(r"\.nav\.compact\s+\.lbl", content), "Missing .nav.compact child selectors for label hiding"
    assert re.search(r"\.nav\.compact\s+\.nitem", content), "Missing .nav.compact .nitem rule"


def test_viewer_hidden_style_kept():
    """Ensure .viewer[hidden]{display:none} rule is preserved."""
    content = read_html()
    assert ".viewer[hidden]{display:none}" in content, ".viewer[hidden]{display:none} must be kept intact"


def test_narrow_screen_hides_handles():
    """Ensure on narrow screens (max-width:860px) the splitters are hidden."""
    content = read_html()
    # Find @media (max-width:860px) block
    idx = content.find("@media (max-width:860px)")
    assert idx != -1, "@media (max-width:860px) query must exist"
    # Slice the media query block by matching braces
    start = content.find("{", idx)
    depth = 1
    end = start + 1
    while depth > 0 and end < len(content):
        if content[end] == "{":
            depth += 1
        elif content[end] == "}":
            depth -= 1
        end += 1
    mq_body = content[start:end]
    assert ".splitter" in mq_body and "display:none" in mq_body.replace(" ", ""), (
        "@media (max-width:860px) must hide .splitter"
    )


def test_handle_styles_and_cursor():
    """Ensure splitter has col-resize cursor and hover styling."""
    content = read_html()
    assert "col-resize" in content, "Splitter must use cursor: col-resize"
    assert ".splitter:hover" in content or ".splitter:hover::after" in content, (
        "Splitter must have hover visible line style"
    )
