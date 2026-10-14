"""
The page's rules tab (a verdict per rule) and DFM tab (one report listed in both segments).

The UI has no JS test runner here, so these read the UI source (tests/ui_source.py)
the way the other UI tests do; the behaviour itself was driven in headless Edge when it was written.
"""
import pathlib
import re

import pytest
from PIL import Image

import dfm
import model
import project
import store
from ui_source import ui_all, ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML = ui_all()
JS = ui_js()


def _body(name):
    """The source of one top-level function of the page."""
    start = JS.index(f"function {name}(")
    nxt = re.search(r"\n(?:async )?function \w+\(|\nlet \w+ = ", JS[start + 10:])
    return JS[start:start + 10 + (nxt.start() if nxt else 20000)]


RULES_JS = (REPO / "ui" / "js" / "views" / "rules.js").read_text(encoding="utf-8")
RULES_CSS = (REPO / "ui" / "styles" / "rules.css").read_text(encoding="utf-8")


def test_the_rules_diff_has_one_result_column_that_escapes_the_detail():
    # one "Result" per rule (the old Status and Verdict columns said the same thing twice)
    assert "<th>Rule</th><th>Your board</th><th>JLC preset</th><th>Result</th>" in RULES_JS
    assert "<th>Status</th>" not in RULES_JS and "<th>Verdict</th>" not in RULES_JS
    for verdict in ("same", "safer", "tighter_ok", "below_fab_min", "unknown"):
        assert f"{verdict}: [" in RULES_JS, verdict
    for label in ("'Below JLC minimum'", "'Stricter'", "'Matches'", "'Tighter than preset'", "'bad'", "'warn'", "'ok'"):
        assert label in RULES_JS, label
    assert "VERDICT[d.verdict] || VERDICT.unknown" in RULES_JS         # a row without a verdict is "not judged"
    assert "esc(d.detail || '')" in RULES_JS and "esc(d.detail)" in RULES_JS   # the text comes from a board file
    # the detail sits under the tag and wraps: the table cells are nowrap, so the wrapping is pinned in the css
    assert re.search(r"\.rules-tbl \.why\{[^}]*white-space:normal", RULES_CSS)


def test_the_ui_verdicts_are_the_servers_verdicts():
    import rules as rules_server
    ui = re.search(r"const VERDICT = \{(.*?)\n\};", RULES_JS, re.S).group(1)
    assert set(re.findall(r"^\s*(\w+): \[", ui, re.M)) == set(rules_server.VERDICTS)


def test_the_rules_view_keeps_its_contracts():
    assert "function rulesHTML(container" in RULES_JS and "async function runCalculator(d)" in RULES_JS
    # the Rules | Calculators choice is a remembered preference, never touching storage without a try/catch
    assert "lsGet(RULES_SEG_KEY)" in RULES_JS and "lsSet(RULES_SEG_KEY" in RULES_JS and "localStorage" not in RULES_JS
    # the three disclosures start closed (open only when the user opened one, or the preset when there is no board)
    assert 'class="disc rules-disc"' in RULES_JS and "${open ? ' open' : ''}" in RULES_JS
    # the calculators answer while typing: no Calculate buttons, one debounce
    assert "Calculate" not in RULES_JS and "setTimeout(() => runCalculator" in RULES_JS
    # no inline styles, no guidance bar, no old card classes in the new markup
    assert "style=" not in RULES_JS and "guidanceBarHTML" not in RULES_JS
    for old in ("vhead", "kpi", 'class="howto', "warnbox", 'class="card'):
        assert old not in RULES_JS, old


@pytest.mark.parametrize("cls", ["ok", "warn", "bad"])
def test_the_verdict_tag_classes_exist(cls):
    assert re.search(rf"\.tag\.{cls}\{{", HTML), cls


def test_a_both_report_is_listed_in_both_dfm_segments():
    checks = _body("checksHTML")
    assert "['pcb', 'both'].includes(c.kind || 'pcb')" in checks       # no kind at all is a bare-board report
    assert "['smt', 'both'].includes(c.kind)" in checks
    # the segment on show, not the report's own kind, decides which report and which findings are drawn
    assert "const kind = dfmSeg === 'smt' ? 'smt' : 'pcb';" in checks
    assert "dfmFindings(stem, kind)" in checks and "'data-kind': kind" in checks
    assert "(kind === 'smt' ? curSmtCheckStem : curPcbCheckStem) || curPcbCheckStem || curSmtCheckStem" in HTML   # dfmStemFor
    assert "curCheckStem" not in HTML, "one current report per segment, no third one"
    # a 'both' report holds the bare board analyses ('PCB DFM>...') and the assembly ones ('SMT DFM>...'): each segment
    # lists its own findings, and a finding with no section is a bare-board one
    rows = _body("dfmRows")
    assert "c.kind === 'both'" in rows
    assert r"/^\s*smt\b/i.test(r.section || '') ? segKind === 'smt' : segKind === 'pcb'" in rows


def test_the_bom_table_flags_a_code_that_is_another_part():
    bom = (REPO / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")
    assert f"const CODE_RISK = '{store.CODE_RISK}'" in bom             # the same string the server writes into l.risk
    # that risk becomes a "Code is another part" tag, and the supplier's own explanation is the tag's tooltip
    assert "risks.includes(CODE_RISK)" in bom and "text: 'Code is another part'" in bom
    assert "l.supply?.LCSC?.code_mismatch" in bom


def test_state_carries_the_kind_of_a_both_report(home, tmp_path):
    name = project.create("both-report", title="Both")
    pdf = tmp_path / "report.pdf"
    Image.new("RGB", (800, 2000), (240, 240, 240)).save(str(pdf), "PDF")
    dfm.ingest_pdf(pdf, name, kind="both")
    assert [c["kind"] for c in model.build(project=name)["checks"]] == ["both"]
    assert [c["kind"] for c in dfm.list_checks(name, "smt")] == ["both"]
    assert [c["kind"] for c in dfm.list_checks(name, "pcb")] == ["both"]
