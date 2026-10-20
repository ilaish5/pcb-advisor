"""Outputs / DFM "Make again": the button next to every out-of-date or hand-edited output.

No JS runner in the suite, so the source is pinned (as in test_ui_dfm_outputs.py) and, when node is on PATH, the pure
planning function outRemakePlan is run for real. Every tool the plan accepts must be one the server's exporters record
in the lineage log, and every endpoint the UI calls must exist in serve.py.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
OUTPUTS = (REPO / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
CHECKS = (REPO / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
SERVE = (REPO / "scripts" / "serve.py").read_text(encoding="utf-8")

TOOLS = {"export_bom", "export_cpl", "outjob", "export_library", "gerber_zip"}


def _plan(row):
    """Run outRemakePlan from outputs.js under node."""
    start = OUTPUTS.index("const OUT_REMAKE_NO")
    end = OUTPUTS.index("function outRemakeBtn")
    js = ("const ALTIUM_DATA = null;\n" + OUTPUTS[start:end]
          + "\nconsole.log(JSON.stringify(outRemakePlan(" + json.dumps(row) + ")));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _row(name, tool, status="stale", reasons=()):
    return {"name": name, "lineage": {"status": status, "tool": tool, "reasons": list(reasons)}}


def test_every_tool_the_plan_knows_is_recorded_by_an_exporter():
    block = OUTPUTS[OUTPUTS.index("const OUT_REMAKE_NO"):OUTPUTS.index("const outAltiumLinked")]
    assert set(re.findall(r"(\w+): '", block)) == TOOLS
    recorded = "".join((REPO / "scripts" / f).read_text(encoding="utf-8") for f in
                       ("outjob.py", "jlc_upload.py", "skills/export_bom.py", "skills/export_cpl.py", "serve.py"))
    for tool in TOOLS:
        assert f'"{tool}"' in recorded, tool


def test_the_endpoints_the_buttons_call_exist_and_no_new_one_was_needed():
    for ep in ("/api/skill", "/api/cpl/export", "/api/outjob/generate", "/api/library/export", "/api/jlc/gerber-zip", "/api/altium/run-outjob"):
        assert ep in OUTPUTS and ep in SERVE, ep
    assert "/api/outputs/remake" not in SERVE


def test_edited_files_ask_in_the_page_not_with_window_confirm():
    assert "window.confirm" not in OUTPUTS and not re.search(r"(?<![\w.])confirm\(", OUTPUTS)
    assert "This file was edited by hand; making it again replaces your edits." in OUTPUTS
    assert "createElement('dialog')" in OUTPUTS


def test_outputs_rows_and_the_dfm_section_both_get_the_button_and_the_header_gets_make_all():
    assert "outRemakeBtn(f)" in OUTPUTS and "outRemakeBtn(f)" in CHECKS
    assert "'Make all again'" in CHECKS and "again.length > 1" in CHECKS
    assert "onAct('remake'" in OUTPUTS and "onAct('remake-all'" in OUTPUTS
    assert re.search(r"await refresh\(true\);\s*// the lineage is read again", OUTPUTS)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
class TestPlan:
    def test_fresh_and_unrecorded_get_nothing(self):
        assert _plan({"name": "a.csv", "lineage": {"status": "fresh", "tool": "export_bom"}})["kind"] == "none"
        assert _plan({"name": "a.csv"})["kind"] == "none"

    @pytest.mark.parametrize("tool", sorted(TOOLS - {"gerber_zip", "export_bom"}))
    def test_a_known_exporter_runs_again(self, tool):
        p = _plan(_row("x.out", tool))
        assert (p["kind"], p["label"], p["edited"]) == ("api", "Make again", False)

    def test_bom_needs_its_format_from_the_file_name(self):
        assert _plan(_row("demo_BOM_jlc.csv", "export_bom"))["kind"] == "api"
        p = _plan(_row("mine.csv", "export_bom"))
        assert p["kind"] == "none" and "BOM format" in p["why"]

    def test_edited_is_flagged_so_the_page_asks_first(self):
        assert _plan(_row("demo.OutJob", "outjob", "edited"))["edited"] is True

    def test_gerber_zip_with_a_changed_board_goes_through_altium(self):
        p = _plan(_row("demo_gerbers.zip", "gerber_zip", reasons=["demo.PcbDoc was saved after these Gerbers were generated"]))
        assert (p["kind"], p["label"]) == ("altium", "Generate the outputs in Altium first")

    def test_gerber_zip_for_another_reason_is_just_zipped_again(self):
        assert _plan(_row("demo_gerbers.zip", "gerber_zip", "edited"))["kind"] == "api"

    def test_unknown_tool_has_no_button_and_says_why(self):
        p = _plan(_row("x.bin", "some_future_tool"))
        assert p["kind"] == "none" and "some_future_tool" in p["why"]
