"""
The page's rules tab (a verdict per rule) and DFM tab (one report for both cards).

The UI has no JS test runner here, so these read ui/index.html the way the other
UI tests do; the behaviour itself was driven in headless Edge when it was written.
"""
import pathlib
import re

import pytest
from PIL import Image

import dfm
import model
import project

REPO = pathlib.Path(__file__).resolve().parent.parent
HTML = (REPO / "ui" / "index.html").read_text(encoding="utf-8")


def _body(name):
    """The source of one top-level function of the page."""
    start = HTML.index(f"function {name}(")
    nxt = re.search(r"\n(?:async )?function \w+\(|\nlet \w+ = ", HTML[start + 10:])
    return HTML[start:start + 10 + (nxt.start() if nxt else 20000)]


def test_the_rules_diff_has_a_verdict_column_that_escapes_the_detail():
    rules = _body("rulesHTML")
    assert "<th>Status</th><th>Verdict</th>" in rules
    for verdict in ("same", "safer", "tighter_ok", "below_fab_min", "unknown"):
        assert f"{verdict}: [" in rules, verdict
    assert "'Below fab min'" in rules and "'bad'" in rules and "'Tighter, within fab limit'" in rules
    assert "VERDICT[d.verdict] || VERDICT.unknown" in rules             # a row without a verdict is "not judged"
    assert "esc(d.detail || '')" in rules and "esc(d.detail)" in rules   # the text comes from a board file
    assert "white-space:normal" in rules                               # .libt cells are nowrap: the detail must wrap


@pytest.mark.parametrize("cls", ["ok", "warn", "bad", "plan"])
def test_the_verdict_tag_classes_exist(cls):
    assert re.search(rf"\.tag\.{cls}\{{", HTML), cls


def test_a_both_report_is_listed_in_both_dfm_cards():
    checks = _body("checksHTML")
    assert "['pcb', 'both'].includes(c.kind || 'pcb')" in checks       # no kind at all is a bare-board report
    assert "['smt', 'both'].includes(c.kind)" in checks
    # the card's own kind, not the report's, decides what its buttons and selector do
    assert "renderCard('pcb'," in checks and "renderCard('smt'," in checks
    assert 'data-kind="${kind}"' in checks and "curCheck.kind === 'both'" in checks
    assert "d.kind === 'smt' ? curSmtCheckStem : curPcbCheckStem" in HTML


def test_the_bom_table_flags_a_code_that_is_another_part():
    assert "const CODE_RISK = 'LCSC code is another part'" in HTML
    assert "r === CODE_RISK" in HTML and "l.supply?.LCSC?.code_mismatch" in HTML


def test_state_carries_the_kind_of_a_both_report(home, tmp_path):
    name = project.create("both-report", title="Both")
    pdf = tmp_path / "report.pdf"
    Image.new("RGB", (800, 2000), (240, 240, 240)).save(str(pdf), "PDF")
    dfm.ingest_pdf(pdf, name, kind="both")
    assert [c["kind"] for c in model.build(project=name)["checks"]] == ["both"]
    assert [c["kind"] for c in dfm.list_checks(name, "smt")] == ["both"]
    assert [c["kind"] for c in dfm.list_checks(name, "pcb")] == ["both"]
