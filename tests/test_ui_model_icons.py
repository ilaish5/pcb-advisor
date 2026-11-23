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
    for cls in ("ok", "basic", "no", "bad"):
        assert f"'{cls}'" in states
    icons = js[js.index("function libIconsHTML"):js.index("function libLegendHTML")]
    assert 'title="${esc(say)}"' in icons and 'aria-label="${esc(name' in icons
    assert 'data-act="lib-preview"' in icons and "MIC_WORD[state]" in icons
    words = js[js.index("const MIC_WORD"):js.index("const MIC_WORD") + 120]
    for word in ("present", "basic", "missing", "needs attention"):
        assert word in words


def test_states_map_the_way_the_brief_says():
    js = ui_js()
    states = js[js.index("function libModelStates"):js.index("function libIconsHTML")]
    assert "build_status === 'error'" in states and "'bad'" in states          # a footprint error is red
    assert "source === 'generated'" in states and "'basic'" in states          # a generated footprint is basic
    assert "r.step ?" in states                                                # a STEP file is a real 3D model
    assert "libPinsState(r)" in states
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
