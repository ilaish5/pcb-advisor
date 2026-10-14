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


def test_every_data_act_in_the_markup_has_a_handler():
    # diagram.js handles the acts of its own toolbar itself, so only index.html and ui/js count here.
    # kit.js helpers take the action as an option (btn('Save', {act: 'save'}), menu items {act: 'x'}), so count those too.
    src = ui_html() + ui_js()
    emitted = set(re.findall(r'data-act=["\']([\w-]+)["\']', src)) | set(re.findall(r"\bact:\s*'([\w-]+)'", src))
    registered = set(re.findall(r"^onAct\('([\w-]+)'", ui_js(), re.M))
    assert emitted - registered == set(), f"data-act without onAct(): {sorted(emitted - registered)}"
