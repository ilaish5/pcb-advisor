"""
The UI source as text, wherever it lives.

ui/index.html is only the page skeleton; styles live in ui/styles/*.css and code in
ui/js/**/*.js (plus ui/diagram.js, the diagram editor). Tests that look for a string
in "the UI" use these helpers instead of reading one file, so moving code between the
files does not break them.

    ui_html()   the text of ui/index.html
    ui_css()    every stylesheet, in the order index.html links them (the cascade order)
    ui_js()     every script under ui/js, in the order index.html loads them (not diagram.js)
    ui_all()    html + css + js, for "this string appears somewhere in the UI"
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
UI = REPO / "ui"


def ui_html():
    return (UI / "index.html").read_text(encoding="utf-8")


def _linked(pattern):
    """Files under ui/ that index.html references with `pattern` (group 1 = the /ui/... path), in tag order."""
    return [UI / m.group(1)[len("/ui/"):] for m in re.finditer(pattern, ui_html())]


def ui_css_files():
    linked = _linked(r'<link\s+rel="stylesheet"\s+href="(/ui/[^"]+\.css)"')
    extra = sorted(p for p in UI.rglob("*.css") if p not in linked)
    return linked + extra


def ui_js_files():
    linked = [p for p in _linked(r'<script\s+src="(/ui/js/[^"]+\.js)"')]
    extra = sorted(p for p in (UI / "js").rglob("*.js") if p not in linked)
    return linked + extra


def _read(paths):
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


def ui_css():
    return _read(ui_css_files())


def ui_js():
    return _read(ui_js_files())


def ui_all():
    return "\n".join([ui_html(), ui_css(), ui_js()])
