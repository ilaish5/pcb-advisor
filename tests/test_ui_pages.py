"""
Static checks for the Library, Sources and Settings pages and the document viewer
(ui/js/views/pages.js, ui/js/viewer.js, ui/styles/pages.css, ui/styles/viewer.css).

They pin the structure of the redesign: one primary button per view, empty, loading and error states, Settings that saves
one field at a time, Sources with its two scopes, escaping of server values, and a viewer without the old dead code.
"""
import pathlib
import re

from ui_source import UI, ui_js

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

PAGES = (UI / "js" / "views" / "pages.js").read_text(encoding="utf-8")
VIEWER = (UI / "js" / "viewer.js").read_text(encoding="utf-8")
SHELL = (UI / "js" / "shell.js").read_text(encoding="utf-8")
PAGES_CSS = (UI / "styles" / "pages.css").read_text(encoding="utf-8")
VIEWER_CSS = (UI / "styles" / "viewer.css").read_text(encoding="utf-8")
SOURCES = {"pages.js": PAGES, "viewer.js": VIEWER}


def func_body(src: str, name: str) -> str:
    """The text of `function name(...) {...}`, found by matching braces."""
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", src)
    assert m, f"function {name}() must exist"
    start = src.index("{", m.end())
    depth, end = 1, start + 1
    while depth and end < len(src):
        depth += {"{": 1, "}": -1}.get(src[end], 0)
        end += 1
    return src[start:end]


def test_no_browser_dialogs():
    """askText() replaces prompt(); nothing here uses the browser's own dialogs."""
    for name, src in SOURCES.items():
        for dialog in ("prompt(", "confirm(", "alert("):
            assert not re.search(r"(?<![\w.])" + re.escape(dialog), src), f"{name} must not call {dialog}"
    assert "askText(" in PAGES


def test_no_hebrew_literals_only_the_entity():
    """The language label is an HTML entity so no Hebrew letter is stored in a source file."""
    for name, src in SOURCES.items():
        assert not re.search("[֐-׿]", src), f"{name} holds a Hebrew literal"
    assert "&#1506;&#1489;&#1512;&#1497;&#1514;" in PAGES


def test_one_primary_button_per_view():
    """Library and Sources each have exactly one primary action; Settings has none (it saves as you type)."""
    lib = func_body(PAGES, "libHTML")
    src = func_body(PAGES, "sourcesHTML")
    assert lib.count("kind: 'pri'") == 1 and "Build library" in lib
    assert src.count("kind: 'pri'") == 1 and "Add" in src
    for settings in (func_body(PAGES, "settingsBody"), func_body(PAGES, "setAgentHTML"), func_body(PAGES, "setAltiumHTML")):
        assert "kind: 'pri'" not in settings
    assert "kind: 'pri'" not in VIEWER, "a document has no primary action"


def test_every_page_has_empty_loading_and_error_states():
    assert "emptyState(" in func_body(PAGES, "libHTML"), "Library needs an empty state"
    src = func_body(PAGES, "sourcesHTML")
    assert "emptyState(" in src and "loadingLine(" in src, "Sources needs an empty state and a busy state while adding"
    settings = func_body(PAGES, "settingsBody")
    assert "loadingLine(" in settings and "errorLine(" in settings, "Settings needs a loading and an error state"
    altium = func_body(PAGES, "setAltiumHTML")
    assert "loadingLine(" in altium and "errorLine(" in altium
    for state in ("loadingLine(", "errorLine(", "emptyState("):
        assert state in VIEWER, f"the viewer needs {state}"


def test_altium_load_failure_shows_an_error_with_retry_and_does_not_loop():
    """Bug: a failed loadAltium() left 'Loading...' on screen forever and was called again on every draw."""
    load = func_body(PAGES, "loadAltium")
    assert "ALTIUM_ERR = " in load, "a failure is remembered"
    assert re.search(r"if \(altiumLoading \|\| \(ALTIUM_ERR && !force\)\) return", load), "no second request while one runs or after a failure"
    assert "catch" in load
    altium = func_body(PAGES, "setAltiumHTML")
    assert re.search(r"if \(ALTIUM_ERR\) return errorLine\(", altium)
    assert "act: 'altium-retry'" in altium
    assert re.search(r"onAct\('altium-retry'[^\n]*loadAltium\(true\)", PAGES), "Retry forces a new request"
    # the config can fail to load too
    assert "act: 'settings-retry'" in func_body(PAGES, "settingsBody")
    assert "onAct('settings-retry'" in PAGES


def test_settings_saves_one_field_at_a_time_without_save_buttons():
    """Bug: Save and Save path both saved everything. Now each field posts only its own key, after a short pause for text."""
    assert not re.search(r"Save path|data-act=\"saveset\"|act: 'saveset'|act: 'savemem'|onAct\('saveset'|onAct\('savemem'", PAGES)
    assert not re.search(r"btn\('Save\b", PAGES), "no Save button: settings save as you change them"
    save = func_body(PAGES, "pgSave")
    assert "api('/api/config', {set: {[key]: value}})" in save, "a config field sends only its own key"
    assert "api('/api/memory', {text: el.value})" in save
    assert "/api/altium/link" in save
    assert "dataset.set" in save and "dataset.link" in save and "dataset.mem" in save
    assert "if (!pgDirty(el)) return;" in save, "an untouched field is not saved"
    assert "setTimeout(() => pgSave(t), 700)" in PAGES, "text is saved after a pause, not on every key"
    assert "'Saved'" in PAGES and "2000" in PAGES, "'Saved' shows next to the field for two seconds"
    # no handler collects every field into one request
    assert "querySelectorAll('[data-set]')" not in PAGES


def test_settings_sections_follow_the_spec():
    body = func_body(PAGES, "settingsBody")
    order = [body.index(f"section('{s}'") for s in ("Appearance", "Agent", "Altium", "Memory")]
    assert order == sorted(order)
    assert "setSkillsHTML()" in body and body.index("setSkillsHTML()") > order[-1]
    assert "act: 'reset-layout'" in body, "Reset layout is a link at the bottom of Settings"
    assert body.rindex("reset-layout") > body.index("setSkillsHTML()")
    assert "act: 'set-theme'" in body and "System" in body and "Light" in body and "Dark" in body
    skills = func_body(PAGES, "setSkillsHTML")
    assert "s.available" in skills, "unbuilt skills are hidden"
    assert "id: 'set-skills'" in skills
    # Skills stays a route (the palette and old links use it) but is drawn as part of Settings
    assert "return settingsBody();" in func_body(PAGES, "skillsHTML")


def test_sources_has_two_scopes_and_adds_into_the_project():
    src = func_body(PAGES, "sourcesHTML")
    for value in ("'all'", "'shared'", "'project'"):
        assert value in src
    assert "act: 'src-filter'" in src
    assert "Upload file" in src and "From URL" in src and "act: 'upload'" in src and "act: 'addurl'" in src
    assert PAGES.count("api('/api/upload'") == 1 and PAGES.count("api('/api/fetch_source'") == 1
    assert "python scripts/sources.py restore" in PAGES, "the restore command is shown when files are missing"
    assert "act: 'src-copy'" in src
    row = func_body(PAGES, "srcRow")
    assert "data-src=" in row, "a name opens the document through the generic data-src route"
    assert "'Missing'" in row


def test_sources_lists_the_general_library_by_its_path_and_counts_the_two_scopes():
    """A general document is named by its path under shared/reference, the name a citation uses: the folders are shown quieter."""
    label = func_body(PAGES, "srcLabel")
    assert "lastIndexOf('/')" in label and 'class="dir"' in label and label.count("esc(") == 2
    row = func_body(PAGES, "srcRow")
    assert "srcLabel(s.name)" in row and row.count("esc(s.name)") >= 1
    assert ".src-name .dir{" in PAGES_CSS
    assert re.search(r"\.src-name \.dir\{flex:0 1 auto\}", PAGES_CSS) and re.search(r"\.src-name \.file\{flex:none;max-width:100%\}", PAGES_CSS), \
        "the folders give way first and the file name keeps its width, so it never gets a sub-pixel ellipsis"
    assert re.search(r"\.src-tbl td\.src-n\{[^}]*max-width:0", PAGES_CSS), "the name column takes what the table leaves"
    assert re.search(r"\.src-cell\{[^}]*container-type:inline-size", PAGES_CSS) and re.search(
        r"@container \(max-width:\d+px\)\{\.src-name \.dir\{display:none\}\}", PAGES_CSS), \
        "a narrow cell shows the file name only, never a sliver of a folder"
    src = func_body(PAGES, "sourcesHTML")
    assert "label: 'in this project'" in src and "label: 'shared'" in src, "the header counts the two scopes, not one file total"
    assert "act: 'src-filter'" in src and "s.scope === srcFilter" in src
    assert "s.name.includes('/')" in func_body(PAGES, "srcTip"), "a long path that is cut short is in the tooltip in full"


def test_the_two_citations_in_the_ui_name_documents_of_the_library():
    """Rules and Library cite a general document with a chip: its name must be one the Sources list has."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import sources
    names = set(sources.reference_files())
    rules = (UI / "js" / "views" / "rules.js").read_text(encoding="utf-8")
    cited = re.search(r"const RULES_SRC = '([^']+)'", rules).group(1)
    assert cited == "jlc/pcb-capabilities.en.md" and cited in names
    assert "chip(RULES_SRC)" in rules, "the citation is a chip that opens the document, not plain text"
    course = re.search(r"const PG_COURSE_LIB = '([^']+)'", PAGES).group(1)
    assert course in names
    assert "chip(PG_COURSE_LIB, " in func_body(PAGES, "libExportHTML") and "AD20 Essentials Course Exercises.pdf" not in PAGES


def test_server_values_are_escaped():
    """Names, paths and text from the server never go into markup raw."""
    for name, src in SOURCES.items():
        for field in ("s.name", "s.size", "s.used_for", "s.origin", "r.mpn", "r.line", "l.project_file", "l.outputs_dir",
                      "libExport.file", "S.memory", "data.error", "err.message"):
            assert not re.search(r"\$\{\s*" + re.escape(field) + r"\s*\}", src), f"{name}: ${{{field}}} must go through esc()"
    for attr in ("src=\"${raw}\"", "href=\"${s.url}\""):
        assert attr not in VIEWER
    assert 'dir="auto"' in PAGES, "the memory text may be Hebrew: it takes its own direction"


def test_library_row_actions_and_keyboard():
    action = func_body(PAGES, "libAction")
    assert "accept:" in action and "verify:" in action, "one quiet action: Verify, then Accept"
    assert "Accept" in action and "Verify" in action
    row = func_body(PAGES, "libRow")
    assert 'tabindex="0"' in row and "data-key=" in row, "a row opens the inspector and takes keyboard focus"
    assert ".lib-tbl tbody tr[data-key]" in PAGES and "'Enter'" in PAGES
    assert "act: 'libexport'" in func_body(PAGES, "libHTML")
    # the install steps are a disclosure shown after an export, and the old export card is gone
    assert "<details class=\"disc lib-how\">" in func_body(PAGES, "libExportHTML")
    assert "closecard" not in PAGES


def test_link_and_unlink_refresh_the_bom_import_cache():
    """Linking another Altium project changes where the BOM looks for import candidates."""
    assert func_body(PAGES, "pgLink").count("impFor = null") == 1
    assert re.search(r"onAct\('altium-unlink'.*?impFor = null", PAGES, re.S)


def test_viewer_documents():
    assert "DOC_CSV_ROWS = 500" in VIEWER and "Showing ${DOC_CSV_ROWS} of" in VIEWER, "a CSV shows 500 rows and says how many there are"
    assert "tbl dense" in VIEWER
    assert "doc-pdf" in VIEWER and "#page=" in VIEWER, "a PDF fills the pane and opens at the cited page"
    # Altium files: one line of counts, then the useful lists (the dead legacy viewer had them)
    altium = func_body(VIEWER, "docAltiumHTML")
    for piece in ("metaLine(", "Components", "Sheets", "PCBs", "OutJobs", "Rules", "data-altium-path"):
        assert piece in altium, piece
    # the header: the file name, an Ask icon and a menu with Download and Open in new tab
    header = func_body(VIEWER, "docHeader")
    assert "Ask about this file" in header and "Download" in header and "Open in new tab" in header
    # a stale document must not overwrite a newer one
    assert "dataset.docKey" in func_body(VIEWER, "renderFileTabContent")


def test_one_way_to_open_a_document():
    """Chips, tables, the palette, links to Altium files, Outputs and DFM all open a document through openFileAsTab."""
    scripts = ui_js()
    assert re.search(r"function\s+fileDownload\s*\(", VIEWER) and len(re.findall(r"fileDownload\(", scripts)) > 1
    for gone in ("openViewerSource", "openViewerAltium", "openViewerExport", "openViewerSlice"):
        assert gone not in scripts, f"{gone}: open documents with openFileAsTab"
    for caller in ("core.js", "palette.js", "views/outputs.js", "views/checks.js"):
        text = (UI / "js" / caller).read_text(encoding="utf-8")
        assert "openFileAsTab(" in text, caller
    assert "openFileAsTab({name: d.src, path: d.src, where: d.where})" in (UI / "js" / "core.js").read_text(encoding="utf-8")
    body = func_body(SHELL, "openFileAsTab")
    assert "setView('work')" in body, "a document opened from the chat drawer must close the drawer"
    assert "fileType: 'dfm'" in scripts and "stem" in func_body(VIEWER, "renderFileTabContent")


def test_viewer_has_no_dead_legacy_code():
    """Bug: about 330 lines of the old overlay viewer were never called. They stay deleted."""
    for dead in ("closeViewer", "closeviewer", "viewer-overlay", "FILE_BADGES", "fname-btn", "ext-lnk", "vtitle", "innerHTML = viewer"):
        assert dead not in VIEWER, dead
        assert dead not in VIEWER_CSS, dead
    assert len(VIEWER.splitlines()) < 330, "the viewer is a small file; a big one means the legacy code came back"


def test_styles_use_tokens_not_colours():
    for name, css in (("pages.css", PAGES_CSS), ("viewer.css", VIEWER_CSS)):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), f"{name} must use design tokens, not hex colours"
        assert not re.search(r"\brgba?\(", css), f"{name} must use design tokens, not rgb()"
