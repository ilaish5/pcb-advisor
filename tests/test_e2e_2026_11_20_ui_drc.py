"""2026-11-20: the library build's 'no Altium project' note has the Create button (on the BOM page, where Build library is now),
and the DRC summary names each rule once."""
import pathlib
import re

from altium import bridge

BOM = (pathlib.Path(__file__).parent.parent / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")


def test_the_library_note_about_a_missing_altium_project_has_create_and_link_buttons():
    m = re.search(r"function bomLibNote\(\) \{.*?\n\}", BOM, re.S)
    assert m and "No Altium project is linked" in m.group(0)
    assert "act: 'altium-create'" in m.group(0) and "act: 'pv-link'" in m.group(0)
    assert "No Altium project is linked" in (pathlib.Path(bridge.__file__).read_text(encoding="utf-8"))     # the text the build error carries


def test_the_drc_line_names_each_rule_once_with_the_sum_of_its_counts():
    res = {"rules": {"Minimum Annular Ring (Minimum=0.1mm) (All)": 0, "Minimum Annular Ring (Minimum=0.15mm) (OnLayer('Top'))": 7,
                     "Silk To Solder Mask (Clearance=0mm) (IsPad),(All)": 0, "Silk To Solder Mask (Clearance=0.1mm) (All),(All)": 29,
                     "Clearance Constraint (Gap=0.127mm) (All),(All)": 0},
           "total": 36, "complete": True}
    line = bridge.drc_line(res)
    assert line == "Minimum Annular Ring 7, Silk To Solder Mask 29, Clearance 0, total 36"
    assert line.count("Minimum Annular Ring") == 1 and line.count("Silk To Solder Mask") == 1
