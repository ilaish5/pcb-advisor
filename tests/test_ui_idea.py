"""
Static checks for the Idea sheet (ui/js/views/idea.js, ui/styles/idea.css) and for how ui/diagram.js lives inside it:
the editor is built once and survives the poll, is destroyed with its canvas, listens only while it is on the page, answers
only the keys that are meant for it, shows an agent proposal as a read-only preview, and draws in both themes.

There is no browser in the test run, so these pin the source (the behaviour itself was checked in a real browser).
"""
import pathlib
import re

from ui_source import UI, ui_all

REPO = pathlib.Path(__file__).resolve().parent.parent
IDEA_JS = (UI / "js" / "views" / "idea.js").read_text(encoding="utf-8")
IDEA_CSS = (UI / "styles" / "idea.css").read_text(encoding="utf-8")
DIAGRAM_JS = (UI / "diagram.js").read_text(encoding="utf-8")


def method_body(src: str, name: str) -> str:
    """Body of a class method written at the usual four-space indent (the same shape test_diagram.py relies on)."""
    m = re.search(r"\n    (?:async )?" + re.escape(name) + r"\([^)]*\) \{\n(.*?)\n    \}\n", src, re.DOTALL)
    assert m, f"method {name}() must exist in ui/diagram.js"
    return m.group(1)


# -- the sheet ----------------------------------------------------------------------------------------------------------

def test_idea_sheet_is_built_from_the_kit_and_never_opens_a_native_dialog():
    for call in ("viewHeader(", "metaLine(", "btn(", "tag(", "dot(", "icon("):
        assert call in IDEA_JS, f"idea.js must build its pieces with the kit: {call}"
    assert not re.search(r"(?<![\w.])(?:prompt|confirm|alert)\(", IDEA_JS), "no native dialogs: the sheet edits in place and undoes with a toast"
    assert "window.prompt" not in IDEA_JS and "window.confirm" not in IDEA_JS
    # the two header actions: confirm the idea, then go on to the BOM
    assert "act: 'confirmidea'" in IDEA_JS and "act: 'idea-next'" in IDEA_JS
    # one hook for the shell, one for the poll
    assert re.search(r"function ideaHTML\(container", IDEA_JS) and re.search(r"function updateIdeaContent\(container", IDEA_JS)


def test_deleting_a_requirement_is_undone_with_a_toast_not_a_confirm():
    body = IDEA_JS[IDEA_JS.index("async function deleteReq"):IDEA_JS.index("async function moveReq")]
    assert "/api/idea/item/delete" in body
    assert "label: 'Undo'" in body and "/api/idea/item'" in body and "/api/idea/item/move" in body, (
        "Undo adds the requirement again and moves it back where it was"
    )


def test_the_words_of_a_requirement_open_the_editor_through_their_own_click_handler():
    # the app's click delegate only routes buttons, links and svg groups: a data-act on <b> or <span> would never run
    assert 'class="req-topic" data-act' not in IDEA_JS and 'class="req-text" data-act' not in IDEA_JS
    assert re.search(r"addEventListener\('click',[^\n]*\n[^\n]*closest\('\.req-topic, \.req-text'\)", IDEA_JS)
    assert "isCollapsed" in IDEA_JS, "selecting words to copy them is not a click to edit"


def test_the_requirement_list_keyboard_and_drag_routes():
    assert "'F2'" in IDEA_JS and "'Delete'" in IDEA_JS and "e.altKey" in IDEA_JS
    assert "e.stopPropagation()" in IDEA_JS, "Delete on a row must not also delete a selected block (the editor listens on window)"
    # drag starts from the grip only, so the text stays selectable
    assert re.search(r"closest\('\.req-drag-handle'\)", IDEA_JS) and "row.draggable = true" in IDEA_JS
    assert "tabindex" in IDEA_JS and "focusin" in IDEA_JS, "one tab stop for the list, arrows move between rows"


def test_the_list_split_is_remembered_and_survives_blocked_storage():
    assert "pcb_advisor_idea_split" in IDEA_JS
    for fn in ("loadIdeaSplit", "saveIdeaSplit"):
        body = IDEA_JS[IDEA_JS.index("function " + fn):]
        body = body[: body.index("\n}\n")]
        assert "try {" in body and "catch" in body, f"{fn} must work with storage blocked"
    assert "dblclick" in IDEA_JS and "role=\"separator\"" in IDEA_JS, "double-click resets the split; the handle is a labelled separator with keys"


def test_a_save_flushed_after_a_project_switch_does_not_write_to_the_wrong_project():
    mount = IDEA_JS[IDEA_JS.index("function mountDiagramEditor"):IDEA_JS.index("/* ---------- pieces of the sheet")]
    assert "const mountProject = PROJECT" in mount
    assert re.search(r"onSave:[^\n]*\n[^\n]*\n\s*if \(PROJECT !== mountProject\) return;", mount)


def test_the_poll_redraws_the_sheet_in_pieces_and_keeps_the_editor():
    body = IDEA_JS[IDEA_JS.index("function updateIdeaContent"):IDEA_JS.index("/* ---------- requirements: edit, add")]
    assert "updateData(ideaDiagram())" in body, "the poll hands the editor the new data; it does not rebuild the canvas"
    assert "never eat what is being typed" in body, "an open edit or add form is not replaced by a poll"
    assert "_ideaSig" in body, "header and list are compared before they are touched"
    # the canvas keeps the class the shell looks for, so the shell updates in place instead of re-rendering the sheet
    assert 'class="diagram-mount-point"' in IDEA_JS


def test_the_placeholder_svg_the_shell_and_tests_rely_on():
    assert '<svg class="diag-svg" id="diag-svg" viewBox="0 0 860 520" width="100%" height="100%" preserveAspectRatio="xMidYMid meet"' in IDEA_JS


# -- the proposal on the canvas ---------------------------------------------------------------------------------------

def test_a_diagram_proposal_is_reviewed_on_the_canvas_before_it_is_applied():
    bar = IDEA_JS[IDEA_JS.index("function proposalBarHTML"):IDEA_JS.index("function refreshIdeaBar")]
    assert "The agent suggests changes to the diagram" in bar and "Previewing the agent's changes" in bar
    for label in ("'Review'", "'Apply'", "'Dismiss'", "'Back'"):
        assert label in bar
    assert "act: 'idea-review'" in bar and "act: 'idea-review-back'" in bar
    assert "decide: what" in bar or "decide:" in bar, "Apply and Dismiss go through the app's proposal decision route"
    # one editor method shows it, one puts the live diagram back
    assert "setPreview(" in IDEA_JS and "ed.setPreview(prev)" in IDEA_JS
    assert "previewProposal" not in DIAGRAM_JS and "previewProposal" not in IDEA_JS, "the old overlay method is replaced by setPreview()"


def test_the_editor_preview_is_read_only_and_never_saved():
    assert re.search(r"\n    setPreview\(", DIAGRAM_JS) and re.search(r"\n    isPreviewing\(", DIAGRAM_JS) and re.search(r"\n    endPreview\(", DIAGRAM_JS)
    set_preview = method_body(DIAGRAM_JS, "setPreview")
    assert "previewChanged" in set_preview and "is-preview" in set_preview and "onPreview" in set_preview
    for name in ("onMouseDown", "onDoubleClick", "onKeyDown"):
        assert "this.previewing" in method_body(DIAGRAM_JS, name), f"{name}() must do nothing while a proposal is on show"
    assert "this.previewing" in method_body(DIAGRAM_JS, "triggerAutosave"), "a proposal on show starts no autosave"
    assert "this.liveData()" in method_body(DIAGRAM_JS, "saveNow"), "a save already waiting sends the live diagram, never the proposal"
    assert "is-changed" in DIAGRAM_JS and ".is-changed" in IDEA_CSS, "what the proposal changes is marked"
    assert ".miro-diagram-editor.is-preview" in IDEA_CSS


# -- the editor's lifecycle --------------------------------------------------------------------------------------------

def test_the_editor_joins_its_mount_point_instead_of_replacing_it():
    init = method_body(DIAGRAM_JS, "initDom")
    assert "classList.add('miro-diagram-editor')" in init
    assert "mountEl.className =" not in init and "mountEl.style.cssText" not in init, (
        "overwriting className lost 'diagram-mount-point', so every poll rebuilt the sheet and leaked an editor"
    )
    assert "createElement('style')" not in DIAGRAM_JS, "the editor's styles are in ui/styles/idea.css"


def test_the_editor_can_be_destroyed_and_leaves_nothing_behind():
    destroy = method_body(DIAGRAM_JS, "destroy")
    for step in ("flushSave()", "removeEventListener", "panHelper.destroy()", "disconnect()", "clearTimeout", "_diagramEditor = null", "onDestroy"):
        assert step in destroy, f"destroy() must {step}"
    assert "this.destroyed = true" in destroy and "if (this.destroyed) return;" in destroy, "destroy() is safe to call twice"
    # every window listener goes through listen(), which destroy() undoes
    assert re.search(r"\n    listen\(target, type, fn, opts\) \{", DIAGRAM_JS)
    bind = method_body(DIAGRAM_JS, "bindEvents")
    assert "window.addEventListener" not in bind and "document.addEventListener" not in bind
    for ev in ("mousemove", "mouseup", "keydown", "keyup"):
        assert f"this.listen(window, '{ev}'" in bind
    # a canvas that left the page cleans itself up
    assert "isConnected" in method_body(DIAGRAM_JS, "alive")
    # and the sheet releases editors whose canvas was replaced
    assert "releaseIdeaEditors(" in IDEA_JS and "ed.destroy()" in IDEA_JS and "onDestroy:" in IDEA_JS


def test_a_poll_does_not_wipe_the_undo_history_or_a_drag_in_progress():
    update = method_body(DIAGRAM_JS, "updateData")
    assert "serverSnapshot" in update, "data equal to what the editor last sent or received is not re-applied"
    assert "touchedIds" in update
    assert "serverSnapshot" in method_body(DIAGRAM_JS, "saveNow"), "a save updates the snapshot"


def test_keys_belong_to_the_canvas_only_when_they_are_meant_for_it():
    owns = method_body(DIAGRAM_JS, "ownsKeys")
    for tag in ("INPUT", "TEXTAREA", "SELECT", "isContentEditable"):
        assert tag in owns
    assert "this.kbActive" in owns and "this.mountEl.contains(" in owns
    assert "this.ownsKeys(e)" in method_body(DIAGRAM_JS, "onKeyDown")
    assert "this.listen(window, 'pointerdown'" in DIAGRAM_JS, "the last press tells which key handler is live"


def test_two_editors_on_one_page_do_not_share_svg_ids():
    assert re.search(r"diag-grid-pattern-\$\{", DIAGRAM_JS) and re.search(r"diag-arrow-end-\$\{", DIAGRAM_JS)
    assert "editorSeq" in DIAGRAM_JS


def test_dead_actions_of_the_old_toolbar_are_gone():
    html = ui_all() + DIAGRAM_JS
    for dead in ("diag-add", "diag-del-block", "diag-cycle-domain", "diag-link-start", "diag-cancel-link", "diag-edit-edge"):
        assert f'"{dead}"' not in html and f"'{dead}'" not in html, f"{dead} had no handler and no button"


# -- drawing in both themes -------------------------------------------------------------------------------------------

def test_the_idea_stylesheet_uses_tokens_not_colours():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", IDEA_CSS), "idea.css takes every colour from the tokens in base.css"
    assert len(re.findall(r"rgba?\(", IDEA_CSS)) <= 1, "the one literal is the toolbar's hairline shadow"
    assert "var(--sig)" in IDEA_CSS and "var(--canvas)" in IDEA_CSS and "var(--sheet)" in IDEA_CSS


def test_the_editor_chrome_has_no_hard_coded_colours():
    # hex literals are data (domain presets, templates, the dark pairs); none may sit in markup or inline CSS
    assert not re.search(r"=\"#[0-9a-fA-F]{3,8}\"", DIAGRAM_JS)
    assert not re.search(r"[:=]\s*#[0-9a-fA-F]{3,8}\s*[;\"]", DIAGRAM_JS)
    assert "cssText" not in DIAGRAM_JS
    # a selected block or line is outlined with the app's accent
    assert "'var(--sig)'" in method_body(DIAGRAM_JS, "renderShapes")
    assert "'var(--sig)'" in method_body(DIAGRAM_JS, "renderConnectors")


def _table(name: str) -> dict:
    m = re.search(r"const " + name + r" = \{(.*?)\n  \};", DIAGRAM_JS, re.DOTALL)
    assert m, f"{name} must exist"
    return dict(re.findall(r"'(#[0-9a-f]{6})':\s*'(#[0-9a-f]{6})'", m.group(1)))


def _lum(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_dark_pairs_keep_the_preset_blocks_readable_and_the_stored_colours_untouched():
    fills, strokes, texts = _table("DARK_FILL"), _table("DARK_STROKE"), _table("DARK_TEXT")
    presets = re.findall(r"\{ id: '(\w+)', name: '[^']*', fill: '([^']+)', stroke: '([^']+)', text: '([^']+)' \}", DIAGRAM_JS)
    assert len(presets) >= 8
    dark_canvas = "#18181b"   # --canvas in the dark theme (ui/styles/base.css)
    for pid, fill, stroke, text in presets:
        if fill != "none":
            assert fill in fills, f"preset {pid}: its fill needs a dark pair"
            assert _contrast(texts[text], fills[fill]) >= 4.5, f"preset {pid}: text on its dark fill must reach 4.5:1"
        assert stroke in strokes, f"preset {pid}: its outline needs a dark pair"
        assert _contrast(strokes[stroke], dark_canvas) >= 3, f"preset {pid}: the outline must stand out from the dark canvas"
    # the mapping is applied when drawing a copy: the stored shape is not changed
    shapes = method_body(DIAGRAM_JS, "renderShapes")
    assert "Object.assign({}, s, { fill: col.fill })" in shapes
    assert not re.search(r"\bs\.(?:fill|stroke)\s*=[^=]", shapes)
    assert "diagramIsDark" in DIAGRAM_JS and "MutationObserver" in DIAGRAM_JS and "prefers-color-scheme" in DIAGRAM_JS, (
        "the editor redraws when the theme flips"
    )
