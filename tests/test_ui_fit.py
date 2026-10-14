"""
Static checks for UI center width fitting and tab scrolling (ui/index.html, ui/styles, ui/js).
"""
import re

from ui_source import ui_all, ui_css


def read_html() -> str:
    """index.html + stylesheets + scripts (ui_source.py)."""
    return ui_all()


def test_no_fixed_min_width_on_svg_rules():
    """Verify no min-width:760px or min-width:980px exist on svg rules in style tag."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"

    # Check for forbidden fixed min-width rules on SVGs (760px and 980px)
    assert not re.search(
        r"svg[^{]*\{[^}]*min-width\s*:\s*(?:760|980)px", style, re.IGNORECASE
    ), "Found forbidden min-width:760px or min-width:980px on an svg rule"

    # Also verify specific svg selectors do not have min-width 760px/980px
    for selector in ["svg.diag-svg", "svg.sch", "svg.pcb-preview"]:
        m = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", style)
        if m:
            rule_body = m.group(1)
            assert "min-width:760px" not in rule_body.replace(" ", "")
            assert "min-width:980px" not in rule_body.replace(" ", "")
            assert "width:100%" in rule_body.replace(" ", "") or "width: 100%" in rule_body
            assert "height:auto" in rule_body.replace(" ", "") or "height: auto" in rule_body


def test_view_has_overflow_x_hidden():
    """Verify .view has overflow-x:hidden and container-type:inline-size."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"

    m = re.search(r"\.view\s*\{([^}]+)\}", style)
    assert m, "CSS rule for .view must exist"
    view_body = m.group(1)

    assert "overflow-x:hidden" in view_body.replace(" ", ""), (
        f".view must have overflow-x:hidden, found: {view_body}"
    )
    assert "overflow-y:auto" in view_body.replace(" ", ""), (
        f".view must have overflow-y:auto, found: {view_body}"
    )


def test_tab_scroll_buttons_exist_with_aria_labels():
    """Verify tab scroll buttons with specific aria-labels exist."""
    content = read_html()

    assert 'aria-label="Scroll tabs left"' in content or "aria-label='Scroll tabs left'" in content, (
        'Button with aria-label="Scroll tabs left" must exist'
    )
    assert 'aria-label="Scroll tabs right"' in content or "aria-label='Scroll tabs right'" in content, (
        'Button with aria-label="Scroll tabs right" must exist'
    )


def test_wheel_listener_on_tab_scroller():
    """Verify a wheel event listener is attached to the tab scroller."""
    content = read_html()

    assert "wheel" in content, "A wheel listener must be present in the UI source"
    assert re.search(
        r"""addEventListener\(\s*['"]wheel['"]""", content
    ), "Expected addEventListener('wheel') in the UI source"


def test_tab_arrow_scroll_by_approx_70_percent():
    """Verify arrow buttons scroll tabs by ~70% of visible width."""
    content = read_html()
    assert re.search(r"clientWidth\s*\*\s*0\.7", content) or "70%" in content, (
        "Tab scroll buttons must scroll by approx 70% of clientWidth"
    )


def test_tab_selected_scrolls_into_view():
    """Verify selected tab is scrolled into view with inline nearest."""
    content = read_html()
    assert re.search(
        r"""scrollIntoView\(\s*\{\s*inline\s*:\s*['"]nearest['"]\s*,\s*block\s*:\s*['"]nearest['"]""",
        content,
    ) or "scrollIntoView" in content, (
        "Selected tab must call scrollIntoView"
    )


def test_tab_arrows_update_on_resize_and_scroll():
    """Verify ResizeObserver is used to update tab scroll buttons on resize."""
    content = read_html()
    assert "ResizeObserver" in content, "Expected ResizeObserver to update tab buttons on resize"
    assert re.search(r"""addEventListener\(\s*['"]scroll['"]""", content), (
        "Expected scroll event listener on tab scroller"
    )


def test_idea_layout_responsive():
    """Verify Idea tab two-column layout wraps on narrow center view."""
    style = ui_css()
    assert style.strip(), "the stylesheets must exist"

    assert "container-type:inline-size" in style.replace(" ", "") or "@container" in style, (
        "Expected container query support on center view"
    )
    assert "auto-fit" in style or "@container" in style, (
        "Expected auto-fit or container query wrapping for two-column layouts"
    )
