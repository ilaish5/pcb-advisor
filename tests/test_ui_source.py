"""
The UI is split over files (see tests/ui_source.py); these keep the split honest:
every file is loaded by index.html, and every data-act the markup emits has a handler.
"""
import re

from ui_source import UI, ui_html, ui_js


def test_every_ui_file_is_loaded_by_index_html_and_every_link_exists():
    html = ui_html()
    for path in sorted(UI.rglob("*.css")) + sorted((UI / "js").rglob("*.js")):
        url = "/ui/" + path.relative_to(UI).as_posix()
        assert f'"{url}"' in html, f"{url} is not linked from ui/index.html"
    for url in re.findall(r'(?:href|src)="(/ui/[^"]+)"', html):
        assert (UI / url[len("/ui/"):]).is_file(), f"ui/index.html links {url}, which does not exist"


def test_load_order_theme_first_then_kit_core_and_boot_last():
    srcs = re.findall(r'<script\s+src="(/ui/js/[^"]+)"', ui_html())
    # theme-boot runs in <head> before the first paint; kit (pure helpers) and core come before every area file
    assert srcs[:3] == ["/ui/js/theme-boot.js", "/ui/js/kit.js", "/ui/js/core.js"], srcs
    assert srcs[-1] == "/ui/js/boot.js", srcs
    # the frame (shell) comes before the views that call go() and openSide(); the palette needs the viewer (it opens documents)
    # and everything else loaded, and runs just before boot
    assert srcs.index("/ui/js/shell.js") < srcs.index("/ui/js/chat.js") < srcs.index("/ui/js/viewer.js") < srcs.index("/ui/js/palette.js") < srcs.index("/ui/js/boot.js"), srcs
    assert srcs.index("/ui/js/core.js") < srcs.index("/ui/js/shell.js"), srcs


def test_stylesheet_order_base_core_shell_then_the_areas():
    hrefs = re.findall(r'<link\s+rel="stylesheet"\s+href="(/ui/styles/[^"]+)"', ui_html())
    assert hrefs[:3] == ["/ui/styles/base.css", "/ui/styles/core.css", "/ui/styles/shell.css"], hrefs


def test_the_frames_actions_are_registered():
    """The nav, the side sheet, the palette and the splitter use these data-act names; each needs exactly one handler."""
    registered = re.findall(r"^onAct\('([\w-]+)'", ui_js(), re.M)
    for name in ("palette", "toggle-chat", "newproj", "side-open", "side-set", "side-swap", "side-close", "reset-layout"):
        assert registered.count(name) == 1, f"onAct('{name}') must be registered exactly once, found {registered.count(name)}"


def test_no_action_is_registered_twice():
    registered = re.findall(r"^onAct\('([\w-]+)'", ui_js(), re.M)
    dupes = sorted({n for n in registered if registered.count(n) > 1})
    assert dupes == [], f"registered more than once (the last one silently wins): {dupes}"


def test_the_page_skeleton_has_the_frame_landmarks():
    html = ui_html()
    for needle in ('<nav class="nav"', 'id="nav"', 'id="panes"', 'id="splitter-chat"', '<section class="chat"', 'id="toast"', 'role="status"'):
        assert needle in html, f"ui/index.html must contain {needle}"
    assert 'id="viewer"' not in html, "documents open in the side sheet; there is no separate viewer panel"


def test_every_data_act_in_the_markup_has_a_handler():
    # diagram.js handles the acts of its own toolbar itself, so only index.html and ui/js count here.
    # kit.js helpers take the action as an option (btn('Save', {act: 'save'}), menu items {act: 'x'}), so count those too.
    src = ui_html() + ui_js()
    emitted = set(re.findall(r'data-act=["\']([\w-]+)["\']', src)) | set(re.findall(r"\bact:\s*'([\w-]+)'", src))
    registered = set(re.findall(r"^onAct\('([\w-]+)'", ui_js(), re.M))
    assert emitted - registered == set(), f"data-act without onAct(): {sorted(emitted - registered)}"
