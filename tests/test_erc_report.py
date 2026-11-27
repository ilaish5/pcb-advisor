"""Altium's own electrical rules check (Compile / ERC) of the schematic, read from the HTML report Altium writes (the OutJob "Electrical
Rules Check" output): parse_erc, erc_split, the OutJob generator and bridge.erc_check with the bridge mocked. No script walks the
violation objects (that call raised and paused the debugger). An unknown or unreadable report is "unchecked", never "clean"."""
import pathlib

import pytest

import outjob
from altium import bridge

ROW = ('<tr class="onmouseout_odd" onmouseover="className = \'onmouseover_odd\'" onmouseout="className = \'onmouseout_odd\'">\n'
       '<td class="column1">{cls}</td>\n<td class="column2">{doc}</td>\n<td class="column3">{msg}</td>\n</tr>\n')


def report(rows=(), clean=False, closed=True, heading=True, header=True, extra=""):
    """A report with the structure of the one Altium 26.8 writes: the front matter table, then the Class | Document | Message table."""
    body = "".join(ROW.format(cls=c, doc=d, msg=m) for c, d, m in rows)
    if clean:
        body += '<tr><td class="column1">Successful Compile; No Violations Found.</td></tr>\n'
    return ('<html>\n<head><style type="text/css">td, th { padding: 0.5em; }</style></head>\n<body onload="">'
            + ('<h1>Electrical Rule Check Report</h1>\n' if heading else '<h1>Something else</h1>\n')
            + '<table class="front_matter">\n<tr class="front_matter"><td class="front_matter_column1">Date:</td>'
              '<td class="front_matter_column2"></td><td class="front_matter_column3">11/27/2026</td></tr>\n</table>'
            + '<a name="IDOC1"><table>\n'
            + ('<tr><th class="column1">Class</th><th class="column2">Document</th><th class="column3">Message</th></tr>\n' if header else '')
            + body + '</table></a>' + extra + '<hr><a href="#top">Back to top</a></body>\n' + ('</html>\n' if closed else ''))


@pytest.fixture
def write(tmp_path):
    def w(text, name="r.html"):
        f = tmp_path / name
        f.write_text(text, encoding="utf-8")
        return f
    return w


SAMPLE = [("Error", "Power.SchDoc", "Duplicate Component Designators C?"),
          ("Warning", "Power.SchDoc", "Net CS has only one pin (Pin J4-24)"),
          ("Warning", "Power.SchDoc", "Net GPIO4 has only one pin (Pin J4-7)"),
          ("Error", "Main.SchDoc", "Net \\IO_RESET contains multiple Input Ports (Port \\IO_RESET, Port \\IO_RESET)."),
          ("Warning", "Main.SchDoc", "Floating Power Object 5V at (3000mil,4300mil)"),
          ("Warning", "Main.SchDoc", "Component C3 at 3320mil,2940mil: Component revision is Out of Date")]


def test_a_report_with_errors_and_warnings_is_read_in_full(write):
    res = bridge.parse_erc(write(report(SAMPLE)))
    assert res["complete"] is True and res["clean"] is False and res["problems"] == []
    assert (res["n_errors"], res["n_warnings"], res["total"]) == (2, 4, 6)
    first = res["rows"][0]
    assert first["level"] == "error" and first["class"] == "Error" and first["document"] == "Power.SchDoc"
    assert first["message"] == "Duplicate Component Designators C?" and first["object"] == "C?"
    assert bridge.erc_line(res) == "2 errors, 4 warnings"
    assert res["kinds"]["Net has only one pin"] == 2


def test_the_message_is_kept_as_altium_wrote_it_and_split_only_for_grouping(write):
    res = bridge.parse_erc(write(report(SAMPLE)))
    msgs = [r["message"] for r in res["rows"]]
    assert msgs == [m for _, _, m in SAMPLE]
    by = {r["message"]: r for r in res["rows"]}
    one = by["Net CS has only one pin (Pin J4-24)"]
    assert (one["kind"], one["object"]) == ("Net has only one pin", "Pin J4-24")
    fl = by["Floating Power Object 5V at (3000mil,4300mil)"]
    assert (fl["kind"], fl["object"], fl["location"]) == ("Floating Power Object", "5V", "3000mil,4300mil")
    comp = by["Component C3 at 3320mil,2940mil: Component revision is Out of Date"]
    assert (comp["kind"], comp["object"], comp["location"]) == ("Component revision is Out of Date", "Component C3", "3320mil,2940mil")
    assert by[SAMPLE[3][2]]["kind"] == "Net contains multiple Input Ports"


def test_warnings_only_and_the_singular(write):
    res = bridge.parse_erc(write(report([("Warning", "A.SchDoc", "Net X has no driving source (Pin U1-1)")])))
    assert res["complete"] and (res["n_errors"], res["n_warnings"]) == (0, 1)
    assert bridge.erc_line(res) == "0 errors, 1 warning"


def test_an_empty_but_valid_report_is_clean_and_only_it(write):
    res = bridge.parse_erc(write(report(clean=True)))
    assert res["complete"] is True and res["clean"] is True and res["rows"] == [] and res["total"] == 0
    assert bridge.erc_line(res) == "no violations (clean)"


def test_a_page_without_rows_and_without_the_success_line_is_not_clean(write):
    res = bridge.parse_erc(write(report()))
    assert res["complete"] is False and res["clean"] is False
    assert res["n_errors"] is None and res["n_warnings"] is None and res["total"] is None and res["kinds"] is None
    assert bridge.erc_line(res).startswith("unchecked (")


def test_a_cut_report_is_unchecked_and_gives_no_count(write):
    res = bridge.parse_erc(write(report(SAMPLE[:2], closed=False)))
    assert res["complete"] is False and res["clean"] is False and res["n_errors"] is None and res["total"] is None
    assert any("cut off" in p for p in res["problems"])
    assert res["rows"], "what was read stays available, but it is not counted"
    cut = bridge.parse_erc(write(report(clean=True, closed=False)))
    assert cut["complete"] is False and cut["clean"] is False


def test_not_an_erc_report_or_a_changed_layout_is_unchecked(write):
    wrong = bridge.parse_erc(write(report(SAMPLE, heading=False)))
    assert wrong["complete"] is False and any("not an Electrical Rule Check report" in p for p in wrong["problems"])
    nohead = bridge.parse_erc(write(report(SAMPLE, header=False)))
    assert nohead["complete"] is False and any("header is missing" in p for p in nohead["problems"])
    unknown = bridge.parse_erc(write(report([("Info", "A.SchDoc", "something new")] + SAMPLE[:1])))
    assert unknown["complete"] is False and any("unknown class" in p for p in unknown["problems"]) and unknown["n_errors"] is None
    stray = bridge.parse_erc(write(report(SAMPLE[:1], extra="<table><tr><td>one</td><td>two</td></tr></table>")))
    assert stray["complete"] is False
    both = bridge.parse_erc(write(report(SAMPLE[:1], clean=True)))
    assert both["complete"] is False and both["clean"] is False


def test_garbage_empty_and_missing_files(write, tmp_path):
    assert bridge.parse_erc(tmp_path / "missing.html") is None
    for text in ("", "not html at all \x00\x01", "<html><body>Error</body></html>"):
        res = bridge.parse_erc(write(text, "g.html"))
        assert res["complete"] is False and res["clean"] is False and res["n_errors"] is None
    assert bridge.erc_line(None) .startswith("unchecked")


def test_a_cp1252_report_is_read(tmp_path):
    f = tmp_path / "c.html"
    f.write_bytes(report([("Warning", "Sch\u00e9ma.SchDoc", "Net X has no driving source (Pin U1-1)")]).encode("cp1252"))
    res = bridge.parse_erc(f)
    assert res["complete"] and res["rows"][0]["document"] == "Sch\u00e9ma.SchDoc"


@pytest.mark.parametrize("text,want", [
    ("Net CS has only one pin (Pin J4-24).", ("Net has only one pin", "Pin J4-24", "")),
    ("Un-Designated Part C?", ("Un-Designated Part", "C?", "")),
    ("Nets have multiple names", ("Nets have multiple names", "", "")),
    ("Off grid Port RELAY1 at 1564.903mil,3500mil", ("Off grid Port", "RELAY1", "1564.903mil,3500mil")),
])
def test_erc_split_best_effort(text, want):
    got = bridge.erc_split(text)
    assert got[0] == want[0] and got[2] == want[2] and (got[1] == want[1] or not want[1])


@pytest.mark.parametrize("text", ["", "(", ")))", "Net", "Net ((( at", "x" * 5000])
def test_erc_split_never_raises(text):
    kind, obj, loc = bridge.erc_split(text)
    assert isinstance(kind, str) and isinstance(obj, str) and isinstance(loc, str)


# ---------------------------------------------------------------- the OutJob that makes the report

def test_the_erc_outjob_asks_for_the_validation_output_into_a_folder_structure():
    text = outjob.erc_outjob(base="C:/x/out")
    assert "OutputType1=Electrical Rules Check" in text and "OutputCategory1=Validation" in text
    assert "OutputMedium1=Folder Structure" in text and "OutputBasePath1=C:/x/out" in text
    assert "ERCType1=" in text and "ERCConnectionMatrixL1=" in text and "ERCConnectionMatrixL17=" in text


def test_the_erc_outjob_carries_the_project_levels_and_matrix():
    matrix = {1: "N" * 17, 5: "W" + "E" * 16}
    text = outjob.erc_outjob({1: "2", 7: "0"}, matrix)
    lines = dict(l.split("=", 1) for l in text.splitlines() if "=" in l)
    cfg = [v for k, v in lines.items() if k.startswith("Configuration1_Item1")][0]
    assert "ERCType1=2" in cfg and "ERCType7=0" in cfg
    assert "ERCConnectionMatrixL5=W" + "E" * 16 in cfg
    assert "ERCType2=" in cfg, "a type the project does not set keeps Altium's default"


def test_project_settings_read_from_the_prjpcb(tmp_path):
    prj = tmp_path / "P.PrjPcb"
    prj.write_text("[Design]\nVersion=1.0\n[Electrical Rules Check]\nType1=2\nType2=0\nTypeX=9\nType3=7\n"
                   "[ERC Connection Matrix]\nL1=NNNNNNNNNNNNNNNNN\nL2=short\n", encoding="utf-8")
    levels, matrix, from_project = bridge.erc_project_settings(prj)
    assert levels == {1: "2", 2: "0"} and matrix == {1: "N" * 17} and from_project is True
    other = tmp_path / "Q.PrjPcb"
    other.write_text("[Design]\nVersion=1.0\n", encoding="utf-8")
    assert bridge.erc_project_settings(other) == ({}, {}, False)
    assert bridge.erc_project_settings(tmp_path / "none.PrjPcb") == ({}, {}, False)


# ---------------------------------------------------------------- erc_check with the bridge mocked

@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "A.SchDoc").write_bytes(b"sheet")
    (d / "B.PcbDoc").write_bytes(b"board")
    prj = d / "P.PrjPcb"
    prj.write_text("[Design]\nVersion=1.0\n[Document1]\nDocumentPath=A.SchDoc\n[Document2]\nDocumentPath=B.PcbDoc\n", encoding="utf-8")
    return prj


class FakeAltium:
    """Stands for run_commands: when the OUTJOB command comes, writes the report where Altium would; records every batch."""

    def __init__(self, monkeypatch, text, unsaved=(), fail=None):
        self.batches, self.text, self.fail = [], text, fail
        monkeypatch.setattr(bridge, "run_commands", self.run)
        monkeypatch.setattr(bridge, "unsaved_documents", lambda prj: list(unsaved))

    def run(self, cmds, *a, **kw):
        self.batches.append([tuple(map(str, c)) for c in cmds])
        for c in cmds:
            if c[0] == "OUTJOB":
                if self.fail:
                    raise bridge.BridgeError(self.fail)
                out = pathlib.Path(c[3]) / "ERC"
                out.mkdir(parents=True, exist_ok=True)
                if self.text is not None:
                    (out / "P.html").write_text(self.text, encoding="utf-8")
        return []


def test_erc_check_runs_the_outjob_reads_the_report_and_cleans_up(proj, tmp_path, monkeypatch):
    fake = FakeAltium(monkeypatch, report(SAMPLE))
    res = bridge.erc_check(proj, tmp_path / "keep" / "report.html")
    assert res["complete"] and (res["n_errors"], res["n_warnings"]) == (2, 4) and res["line"] == "2 errors, 4 warnings"
    assert res["levels_from"] == "default" and res["unsaved"] == [] and res["n_warnings"] == 4
    (cmds,) = fake.batches
    assert [c[0] for c in cmds] == ["PROJECT", "OUTJOB", "LIBRELEASE", "UNMARK", "UNMARK", "UNMARK"]       # the sheet, the board and the project file
    assert cmds[1][2] == "Folder Structure" and cmds[1][4] == "GeneratedFiles"
    assert (tmp_path / "keep" / "report.html").is_file(), "the report is kept"
    assert not (proj.parent / bridge.ERC_DIR).exists(), "the OutJob and the report leave the student's folder"
    assert not list(proj.parent.rglob("*.OutJob"))
    assert set(res["inputs"]) == {"A.SchDoc", "(ERC settings)"}


def test_a_document_that_was_unsaved_is_not_marked_saved_and_is_named(proj, tmp_path, monkeypatch):
    fake = FakeAltium(monkeypatch, report(clean=True), unsaved=["A.SchDoc"])
    res = bridge.erc_check(proj, tmp_path / "k.html")
    unmarked = [c[1] for c in fake.batches[0] if c[0] == "UNMARK"]
    assert all(not u.endswith("A.SchDoc") for u in unmarked) and any(u.endswith("B.PcbDoc") for u in unmarked)
    assert res["unsaved"] == ["A.SchDoc"] and any("unsaved changes in A.SchDoc" in w for w in res["warnings"])
    assert res["clean"] is True


def test_when_altium_cannot_be_asked_about_unsaved_nothing_is_marked_saved(proj, tmp_path, monkeypatch):
    fake = FakeAltium(monkeypatch, report(clean=True))

    def refuse(prj):
        raise bridge.BridgeError("no Altium")
    monkeypatch.setattr(bridge, "unsaved_documents", refuse)
    res = bridge.erc_check(proj, tmp_path / "k.html")
    assert not any(c[0] == "UNMARK" for c in fake.batches[0]) and res["unsaved"] is None


def test_the_projects_own_levels_are_used(proj, tmp_path, monkeypatch):
    proj.write_text(proj.read_text(encoding="utf-8") + "[Electrical Rules Check]\nType1=0\n", encoding="utf-8")
    seen = []
    real = outjob.erc_outjob
    monkeypatch.setattr(outjob, "erc_outjob", lambda levels=None, matrix=None, base="": seen.append(levels) or real(levels, matrix, base))
    FakeAltium(monkeypatch, report(clean=True))
    res = bridge.erc_check(proj, tmp_path / "k.html")
    assert seen == [{1: "0"}] and res["levels_from"] == "project"


def test_a_project_without_a_sheet_on_the_disk_is_refused_not_called_clean(proj, tmp_path, monkeypatch):
    (proj.parent / "A.SchDoc").unlink()
    fake = FakeAltium(monkeypatch, report(clean=True))
    with pytest.raises(bridge.BridgeError, match="no schematic sheet"):
        bridge.erc_check(proj, tmp_path / "k.html")
    assert fake.batches == [], "Altium is not even asked"


def test_no_report_file_is_an_error_never_clean(proj, tmp_path, monkeypatch):
    FakeAltium(monkeypatch, None)
    with pytest.raises(bridge.BridgeError, match="wrote no report"):
        bridge.erc_check(proj, tmp_path / "k.html")
    assert not (proj.parent / bridge.ERC_DIR).exists()


def test_a_report_that_is_not_complete_comes_back_unchecked_with_a_warning(proj, tmp_path, monkeypatch):
    FakeAltium(monkeypatch, report(SAMPLE, closed=False))
    res = bridge.erc_check(proj, tmp_path / "k.html")
    assert res["complete"] is False and res["clean"] is False and res["n_errors"] is None
    assert res["line"].startswith("unchecked (") and any("not counted as checked" in w for w in res["warnings"])


def test_a_failed_outjob_is_an_error_and_the_outjob_is_taken_out_again(proj, tmp_path, monkeypatch):
    fake = FakeAltium(monkeypatch, report(clean=True), fail="Altium stopped")
    with pytest.raises(bridge.BridgeError, match="Altium stopped"):
        bridge.erc_check(proj, tmp_path / "k.html")
    assert len(fake.batches) == 2 and [c[0] for c in fake.batches[1]] == ["PROJECT", "LIBRELEASE"]
    assert not (proj.parent / bridge.ERC_DIR).exists()


def test_a_stale_report_from_an_earlier_run_is_not_taken(proj, tmp_path, monkeypatch):
    import os
    import time
    old = proj.parent / bridge.ERC_DIR / "report" / "ERC"

    class Late(FakeAltium):
        def run(self, cmds, *a, **kw):
            for c in cmds:                           # an old file is there, and Altium writes nothing new
                if c[0] == "OUTJOB":
                    out = pathlib.Path(c[3]) / "ERC"
                    out.mkdir(parents=True, exist_ok=True)
                    f = out / "P.html"
                    f.write_text(report(clean=True), encoding="utf-8")
                    os.utime(f, (time.time() - 3600, time.time() - 3600))
            return []
    Late(monkeypatch, None)
    with pytest.raises(bridge.BridgeError, match="wrote no report"):
        bridge.erc_check(proj, tmp_path / "k.html")
    assert old is not None


def test_erc_inputs_change_with_a_sheet_and_with_the_settings(proj):
    a = bridge.erc_inputs(proj)
    (proj.parent / "A.SchDoc").write_bytes(b"sheet edited")
    b = bridge.erc_inputs(proj)
    assert a["A.SchDoc"] != b["A.SchDoc"] and a["(ERC settings)"] == b["(ERC settings)"]
    proj.write_text(proj.read_text(encoding="utf-8") + "[Electrical Rules Check]\nType1=2\n", encoding="utf-8")
    assert bridge.erc_inputs(proj)["(ERC settings)"] != b["(ERC settings)"]


def test_the_report_is_never_read_by_walking_violation_objects():
    src = pathlib.Path(bridge.__file__).parent.joinpath("bridge", "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    assert "DM_Violations" not in src and "DM_ErrorLevelString" not in src
