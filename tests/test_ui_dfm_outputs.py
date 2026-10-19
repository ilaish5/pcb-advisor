"""
The DFM and Outputs views: ui/js/views/checks.js, outputs.js and their stylesheets.

The UI has no JS test runner here, so these read the source (the way test_ui_source.py and test_ui_rules_dfm.py do) and
pin what the views promise: the verdicts mean what the server means, "ready" needs every finding judged, a change is
saved silently, an export says what it wrote, and the two stylesheets take their colours from the design tokens.
The behaviour itself was driven in headless Edge (screenshots in both themes, two sizes, no JS errors).
"""
import pathlib
import re

import dfm

REPO = pathlib.Path(__file__).resolve().parent.parent
VIEWS = REPO / "ui" / "js" / "views"
STYLES = REPO / "ui" / "styles"
CHECKS = (VIEWS / "checks.js").read_text(encoding="utf-8")
OUTPUTS = (VIEWS / "outputs.js").read_text(encoding="utf-8")
BOM = (VIEWS / "bom.js").read_text(encoding="utf-8")
CHECKS_CSS = (STYLES / "checks.css").read_text(encoding="utf-8")
OUTPUTS_CSS = (STYLES / "outputs.css").read_text(encoding="utf-8")


def _block(src, name):
    """The source of one top-level function."""
    start = src.index(f"function {name}(")
    nxt = re.search(r"\n(?:async )?function \w+\(|\nonAct\(|\nonChange\(|\ndocument\.addEventListener", src[start + 10:])
    return src[start:start + 10 + (nxt.start() if nxt else len(src))]


# ---------- DFM ----------

def test_the_dfm_verdicts_are_the_servers_verdicts_with_plain_names():
    table = re.search(r"const DFM_VERDICTS = \[(.*?)\n\];", CHECKS, re.S).group(1)
    stored = re.findall(r"\['([a-z ]+)', '([^']+)'", table)
    assert {v for v, _ in stored} == dfm.ALLOWED_VERDICTS
    labels = dict(stored)
    # "model" is JLC's model of the part being off, which the user reads as a false alarm
    assert labels == {"unknown": "Not reviewed", "real": "Real issue", "model": "False alarm", "by design": "By design"}
    # the verdict is the only colour in a row besides the level dot: to review warns, real is bad, judged is quiet
    assert "'unknown': 'v-open', 'real': 'v-real', 'model': 'v-done', 'by design': 'v-done'" in CHECKS
    assert re.search(r"\.dfm-v\.v-open\{color:var\(--warn\)\}", CHECKS_CSS)
    assert re.search(r"\.dfm-v\.v-real\{color:var\(--bad\)", CHECKS_CSS)


def test_dfm_is_ready_only_when_every_finding_is_judged_and_none_is_real():
    """Bug 12: the header said ready as soon as a report existed."""
    header = _block(CHECKS, "dfmHeader")
    assert "const ready = t.known && t.n > 0 && !t.open && !t.real && !unv && !gaps.open_pins.length && !gaps.parts.length;" in header      # and no part with unverified pins
    assert "label: 'Ready to order'" in header and "ready &&" in header
    assert "Ready" not in _block(CHECKS, "checksHTML")           # a report existing says nothing about the board
    # the counts come from the loaded findings, else from the state the server summarises (triage_open, triage_real)
    totals = _block(CHECKS, "dfmTotals")
    assert "const v = dfmVerdict(r); if (v === 'unknown') open++; else if (v === 'real') real++;" in totals
    assert "c.triage_open != null" in totals and "else known = false" in totals
    # an unknown verdict counts as still to review, like the server's verdict_of
    assert "DFM_VERDICTS.some(x => x[0] === v) ? v : 'unknown'" in CHECKS


def test_dfm_saves_every_change_silently_and_in_order():
    assert "Triage saved" not in CHECKS and "toast('Saved" not in CHECKS
    # one handler for a verdict, a fix and an evidence text; the field says which row and which column
    assert "onChange(t => t.closest && t.closest('[data-triage-field]')" in CHECKS
    for field in ("verdict", "fix", "evidence"):
        assert f'data-triage-field="{field}"' in CHECKS or f"dfmField('{field.title()}', '{field}'" in CHECKS, field
    # the whole table goes out, one save after another, and a failed save loads the table again
    save = _block(CHECKS, "dfmSave")
    assert "api('/api/checks/triage', {stem, rows: triageMap[stem]})" in save and "dfmQueue[stem]" in save
    assert "dfmFetchTriage(stem)" in _block(CHECKS, "dfmSaveOrReload")
    # the sig the server returns is kept, so the state's triage_sig is not read as someone else's change
    assert "dfmSig[stem] = r.sig" in save and "c.triage_sig !== dfmSig[st]" in _block(CHECKS, "dfmSync")


def test_a_dfm_finding_opens_in_place_and_is_a_keyboard_stop():
    row = _block(CHECKS, "dfmRow")
    assert 'tabindex="0" aria-expanded="${open}"' in row
    assert 'aria-label="Verdict for ${esc(name)}"' in row
    keys = CHECKS[CHECKS.index("document.addEventListener('keydown'"):]
    for key in ("'Enter'", "' '", "'ArrowDown'", "'ArrowUp'", "'Escape'"):
        assert key in keys, key
    # a click on the verdict, a field or a button is theirs; only the rest of the row toggles it
    assert "!e.target.closest('button, a, select, input, textarea, label')" in CHECKS
    # the finding's own numbers and Remove (with an Undo) live in the opened row
    assert "act: 'del-triage-row'" in CHECKS and "label: 'Undo'" in CHECKS


def test_dfm_has_its_loading_error_and_empty_states():
    findings = _block(CHECKS, "dfmFindings")
    assert "loadingLine('Loading findings')" in findings and "errorLine('load the findings'" in findings
    assert "act: 'dfm-retry'" in findings and "onAct('dfm-retry'" in CHECKS
    assert "Nothing is listed for this report yet." in findings
    assert "loadingLine('Loading slices')" in _block(CHECKS, "dfmSlices")
    # a failed upload says why (api() toasts the server's reason); a lost connection has its own words
    assert "Couldn't reach the app" in CHECKS
    assert "dfmBusy" in _block(CHECKS, "dfmUpload") and "'Uploading…'" in CHECKS


def test_dfm_slices_open_beside_the_findings_without_colliding_across_reports():
    assert "act: 'view-slice'" in CHECKS or 'data-act="view-slice"' in CHECKS
    assert "openFileAsTab({name: d.slice, path: d.stem + '/' + d.slice, stem: d.stem, slice: d.slice, fileType: 'dfm'})" in CHECKS


def test_the_views_keep_the_shells_signatures():
    assert "function checksHTML(container)" in CHECKS
    assert "function outputsHTML(container)" in OUTPUTS


# ---------- Outputs ----------

def test_outputs_exports_through_the_bom_acts_and_says_what_it_wrote():
    """Bug 2: an export gave no feedback and the list did not refresh."""
    items = OUTPUTS[OUTPUTS.index("const outExportItems ="):OUTPUTS.index("function outRow(")]
    # the BOM exports are bom.js's `export` act (one handler, one toast); Outputs only offers them, with their names
    assert "onAct('export'" not in OUTPUTS and "onAct('export'" in BOM
    assert "{label: BOM_EXPORTS.jlc, act: 'export', attrs: {fmt: 'jlc'}}" in items
    assert "{label: BOM_EXPORTS.generic, act: 'export', attrs: {fmt: 'generic'}}" in items
    assert "pcbway" not in OUTPUTS.lower()
    assert "jlc: 'BOM (JLC)'" in BOM and "generic: 'BOM (generic)'" in BOM
    assert "{label: 'Pick and place (CPL)', act: 'gen-cpl'}" in items
    # the OutJob and the pick and place file refresh the list, then toast with a Download action
    wrote = _block(OUTPUTS, "outWrote")
    assert "await refresh(true)" in wrote and "label: 'Download'" in wrote and "bomDownload(file)" in wrote
    assert "outWrote('OutJob generated." in OUTPUTS and "outWrote('Pick and place (CPL) exported'" in OUTPUTS
    # the palette runs gen-outjob without a button, so the act must not depend on the element
    gen = OUTPUTS[OUTPUTS.index("onAct('gen-outjob'"):OUTPUTS.index("onAct('gen-cpl'")]
    assert "el." not in gen


def test_outputs_has_one_primary_a_files_table_and_no_banner():
    assert "btn('Generate OutJob', {kind: 'pri', act: 'gen-outjob'" in OUTPUTS
    assert OUTPUTS.count("kind: 'pri'") == 2                       # the header's and the empty state's, never both at once
    assert "emptyState('Nothing exported yet'" in OUTPUTS
    for gone in ("outjobBanner", "close-outjob-banner", "guidanceBarHTML", "style="):
        assert gone not in OUTPUTS, gone
    # a file's name opens it beside the sheet, and the list says when it was written
    assert "onAct('view-export'" in OUTPUTS and "fileType: 'export'" in OUTPUTS
    # when: the state's own export items carry it (model.build), so the view makes no call of its own
    assert "fetch" not in OUTPUTS and "api(" not in OUTPUTS.replace("await api('/api/outjob/generate', {})", "").replace("await api('/api/cpl/export', {})", "").replace("await api('/api/altium/run-outjob', {})", "")
    row = _block(OUTPUTS, "outRow")
    assert "f.modified" in row and "f.modified" in OUTPUTS[OUTPUTS.index("function outputsHTML"):]
    assert "/api/exports" not in OUTPUTS and "outTimes" not in OUTPUTS and "loadExportTimes" not in OUTPUTS


def test_outputs_file_sizes_read_in_bytes_kb_and_mb():
    size = _block(OUTPUTS, "outSize")
    assert "`${n} B`" in size and "KB" in size and "MB" in size
    assert "toFixed(n < 10240 ? 1 : 0)" in size                      # 7.3 KB, but 40 KB


# ---------- both ----------

def test_the_two_views_use_no_raw_colours_and_no_unguarded_storage():
    for name, src in (("checks.css", CHECKS_CSS), ("outputs.css", OUTPUTS_CSS), ("checks.js", CHECKS), ("outputs.js", OUTPUTS)):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b(?![\w-])", src), f"{name} has a hex colour"
        assert not re.search(r"\brgba?\(|\bhsla?\(", src), f"{name} has a raw colour function"
        assert "localStorage" not in src and "sessionStorage" not in src, name
    # the narrow sheet drops columns by the sheet's width (a container), not the window's
    assert "@container (max-width:" in CHECKS_CSS and "@container (max-width:" in OUTPUTS_CSS
    # no Hebrew in the sources
    for src in (CHECKS, OUTPUTS, CHECKS_CSS, OUTPUTS_CSS):
        assert not re.search(r"[֐-׿]", src)
