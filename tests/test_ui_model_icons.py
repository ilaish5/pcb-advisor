"""
The Library "Models" icons and their quick previews, read from the UI source: four icons in a fixed order, the state each
one maps to, the words each says, the legend, and the vendored 3D libraries the preview loads.
"""
import re

from ui_source import UI, ui_html, ui_js


def test_four_icons_in_order_with_words_for_every_state():
    js = ui_js()
    states = js[js.index("function libModelStates"):js.index("function libIconsHTML")]
    order = [states.index(f"['{k}'") for k in ("symbol", "footprint", "model", "pins")]
    assert order == sorted(order)
    for cls in ("ok", "no", "bad"):
        assert f"'{cls}'" in states
    icons = js[js.index("function libIconsHTML"):js.index("function libLegendHTML")]
    assert 'title="${esc(say)}"' in icons and 'aria-label="${esc(name' in icons
    assert 'data-act="lib-preview"' in icons and "MIC_WORD[state]" in icons
    words = js[js.index("const MIC_WORD"):js.index("const MIC_WORD") + 120]
    assert "basic" not in words                                                # exactly three states: no separate "basic" look
    for word in ("present", "missing", "needs attention"):
        assert word in words


def test_states_map_the_way_the_brief_says():
    js = ui_js()
    states = js[js.index("function libModelStates"):js.index("function libIconsHTML")]
    assert "build_status === 'error'" in states and "'bad'" in states          # a footprint error is red
    assert "source === 'generated'" in states and "basic, generated" in states  # a generated footprint is green, said in words only
    assert "'basic'" not in states
    assert "r.step ?" in states                                                # a STEP file is a real 3D model
    assert "libPinsState(r)" in states
    assert "build_status === 'missing'" in states                              # a line the build made nothing for is not green: its preview has nothing to draw
    assert "Pins unverified" in js and "Pins conflict" in js


def test_the_legend_sits_above_the_table_and_the_built_tag_stays():
    js = ui_js()
    assert 'id="lib-legend"' in js
    page = js[js.index("function libHTML"):]
    assert page.index("libLegendHTML()") < page.index("${body}")
    assert "mic-built" in js and "Not built" in js


def test_the_inspector_shows_the_same_icons():
    js = (UI / "js" / "views" / "inspector.js").read_text(encoding="utf-8")
    assert "libIconsHTML(libRowOf(l))" in js


def test_the_preview_is_a_dialog_with_the_four_kinds_and_a_build_action():
    js = (UI / "js" / "views" / "modelpreview.js").read_text(encoding="utf-8")
    assert "onAct('lib-preview'" in js and "showModal" in js
    for kind in ("symbol", "footprint", "model", "pins"):
        assert f"'{kind}'" in js
    assert "libbuild" in js and "libAction" in js
    assert "/api/library/preview?" in js


def test_the_3d_libraries_are_vendored_and_documented():
    html = ui_html()
    assert re.search(r'"three"\s*:\s*"/ui/vendor/three/build/three\.module\.js"', html)
    v = UI / "vendor"
    for rel in ("three/build/three.module.js", "three/examples/jsm/loaders/VRMLLoader.js", "three/examples/jsm/controls/OrbitControls.js",
                "three/LICENSE", "occt/occt-import-js.js", "occt/occt-import-js.wasm", "occt/license.occt-import-js.txt"):
        assert (v / rel).is_file(), rel
    readme = (v / "README.md").read_text(encoding="utf-8")
    for s in ("0.170.0", "0.23", "MIT", "LGPL"):
        assert s in readme


def test_the_icons_have_no_frame_no_fill_and_the_legend_has_three_entries():
    css = (UI / "styles" / "modelpreview.css").read_text(encoding="utf-8")
    assert ".mic.basic" not in css and ".mp-tab.basic" not in css
    assert "fill:currentColor" not in css and "fill-opacity" not in css and ".mic .m" not in css
    mic = re.search(r"^\.mic\{[^}]*\}", css, re.M).group(0)
    assert "background:transparent" in mic and "border:0" in mic
    js = ui_js()
    legend = js[js.index("function libLegendHTML"):js.index("/* a line the build pipeline knows")]
    assert legend.count("${k('") == 3
    assert "basic" not in legend


def test_the_four_glyphs_are_inline_icons_in_the_shared_table():
    kit = (UI / "js" / "kit.js").read_text(encoding="utf-8")
    for name in ("'model-symbol'", "'model-3d'", "'model-pins'", "chip:"):
        assert name in kit
    assert "MIC_ICON = {symbol: 'model-symbol', footprint: 'chip', model: 'model-3d', pins: 'model-pins'}" in ui_js()


# ------------------------------------------------------------ nothing is fetched from the network at runtime

# The type faces are self-hosted too (ui/vendor/fonts), so no host is allowed: the page works with no network at all.
EXTERNAL_FONT_HOSTS = set()

_EXT = r"(?:https?:)?//([A-Za-z0-9.-]+)"
_Q = r"""["'`]"""
_RESOURCE_PATTERNS = [
    re.compile(r"<(?:script|img|source|iframe|video|audio|embed|object|input)\b[^>]*?\b(?:src|data)\s*=\s*" + _Q + _EXT, re.I),
    re.compile(r"<link\b[^>]*?\bhref\s*=\s*" + _Q + _EXT, re.I),
    re.compile(r"<use\b[^>]*?\bhref\s*=\s*" + _Q + _EXT, re.I),
    re.compile(r"@import\s+(?:url\()?\s*" + _Q + "?" + _EXT, re.I),
    re.compile(r"url\(\s*" + _Q + "?" + _EXT, re.I),
    re.compile(r"\bimport\s*\(\s*" + _Q + _EXT),
    re.compile(r"\bfrom\s+" + _Q + _EXT),
    re.compile(r"\bimportScripts\(\s*" + _Q + _EXT),
    re.compile(r"new\s+(?:Shared)?Worker\(\s*" + _Q + _EXT),
    re.compile(r"\.(?:src|href)\s*=\s*" + _Q + _EXT),
]


def test_no_script_style_font_or_icon_comes_from_the_network():
    found = []
    for f in sorted(UI.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".html", ".js", ".css", ".mjs", ".svg"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for pat in _RESOURCE_PATTERNS:
            for m in pat.finditer(text):
                if m.group(1).lower() not in EXTERNAL_FONT_HOSTS:
                    found.append(f"{f.relative_to(UI).as_posix()}: {m.group(0)[:100]}")
    assert not found, "these files load something from the network:\n" + "\n".join(found)


def test_the_scan_catches_what_it_is_meant_to():
    probes = ['<script src="https://cdn.example.com/x.js">', '<link rel="stylesheet" href="//x.org/a.css">',
              "@font-face{src:url(https://x.org/f.woff2)}", "import('https://esm.sh/three')", "s.src = 'https://x.org/a.js'",
              '<img src="http://x.org/i.svg">']
    for t in probes:
        assert any(p.search(t) for p in _RESOURCE_PATTERNS), t
    for ok in ['<script src="/ui/js/x.js">', '<a href="https://github.com/x">', "url(data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E)"]:
        assert not any(p.search(ok) for p in _RESOURCE_PATTERNS), ok


def test_the_importmap_and_the_3d_code_load_only_from_the_app():
    html = ui_html()
    assert '"three":"/ui/vendor/three/build/three.module.js"' in html.replace(" ", "")
    m3d = (UI / "js" / "views" / "model3d.js").read_text(encoding="utf-8")
    assert "M3D_VENDOR = '/ui/vendor/'" in m3d and "cdn" not in m3d.lower()


def test_the_type_faces_are_self_hosted():
    html = ui_html()
    assert 'href="/ui/vendor/fonts/fonts.css"' in html and "googleapis" not in html and "gstatic" not in html
    fonts = UI / "vendor" / "fonts"
    css = (fonts / "fonts.css").read_text(encoding="utf-8")
    files = re.findall(r"url\(([^)]+\.woff2)\)", css)
    assert files and all((fonts / f).is_file() for f in files)
    for family in ("Atkinson Hyperlegible Next", "Atkinson Hyperlegible Mono"):
        assert f"font-family:'{family}'" in css
    assert (fonts / "LICENSE.atkinson-hyperlegible-next.txt").is_file() and (fonts / "LICENSE.atkinson-hyperlegible-mono.txt").is_file()
    assert "url(http" not in css and "url(//" not in css
