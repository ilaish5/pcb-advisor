"""Fixes from the 2026-11-20 end-to-end run: every new SchDoc is in the Altium project (not only the first one), no home path in the
activity report, a Create button on the Library page, one name per DRC rule, a board-size estimate before Place."""
import pathlib

import pytest

import workspace
from altium import bridge
from altium.prjpcb import read_prjpcb
from test_altium_bridge import FakeAltium


class FirstSheetOnly(FakeAltium):
    """What the live run showed: Altium adds only the first new SchDoc to the project; the later ones are saved as files but
    stay free documents. ADDDOC (the by-hand add) works."""

    def __init__(self, broken_adddoc=False):
        super().__init__()
        self.sch_seen = 0
        self.broken_adddoc = broken_adddoc

    def __call__(self, commands, **kw):
        cmds = []
        for c in commands:
            if c[0] == "SCH":
                self.sch_seen += 1
                if self.sch_seen > 1:
                    pathlib.Path(c[1]).write_bytes(b"x")          # a file, but not a document of the project
                    continue
            if c[0] == "ADDDOC" and self.broken_adddoc:
                continue
            cmds.append(c)
        return super().__call__(cmds, **kw)


@pytest.fixture
def first_only(monkeypatch, home):
    f = FirstSheetOnly()
    monkeypatch.setattr(bridge, "run_commands", f)
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    return f


def _four_sheets(monkeypatch):
    monkeypatch.setattr(bridge, "_sheets", lambda project: [(f"{i:02d}", f"Part {i}", {}) for i in range(1, 5)])


def test_new_project_with_four_sheets_lists_every_sheet(empty, first_only, monkeypatch):
    _four_sheets(monkeypatch)
    res = bridge.new_project(empty)
    got = read_prjpcb(res["project_file"])
    assert len(got["sheets"]) == 4 and not got["missing"]
    assert [c[0] for c in first_only.flat()].count("ADDDOC") == 3        # the three that Altium left out were added by hand


def test_add_sheet_for_a_later_sheet_is_added_to_the_project(empty, first_only):
    bridge.new_project(empty)
    for name in ("Two", "Three", "Four"):
        first_only.sch_seen = 5                                         # Altium does not add these by itself
        bridge.add_sheet(empty, name)
    prj = bridge._linked(empty)
    assert {pathlib.PureWindowsPath(s).name for s in read_prjpcb(prj)["sheets"]} == {"Main.SchDoc", "Two.SchDoc", "Three.SchDoc", "Four.SchDoc"}


def test_a_sheet_missing_from_the_project_after_the_run_is_a_clear_error(empty, monkeypatch, home):
    f = FirstSheetOnly(broken_adddoc=True)
    monkeypatch.setattr(bridge, "run_commands", f)
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    bridge.new_project(empty)
    f.sch_seen = 5
    with pytest.raises(bridge.BridgeError, match=r"Two\.SchDoc.*not in the Altium project"):
        bridge.add_sheet(empty, "Two")


def test_the_bridge_script_adds_a_new_sheet_to_the_project_unless_it_is_listed():
    src = (pathlib.Path(__file__).parent.parent / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    body = src[src.index("procedure NewDocument"):src.index("function SchOf")]
    assert "(Kind = 'PCB')" not in body and "DM_AddSourceDocument(Path)" in body and "DM_LogicalDocuments" in body
    assert "CloseObject" not in body
