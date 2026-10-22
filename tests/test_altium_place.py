"""altium.place_pcb / route_pcb: the consent guard per action, the DRC report parser, the PCBCHECK log parser."""
import pytest

import serve
from altium import bridge


def test_place_consent():
    said = "please place the parts for me"
    assert serve._consent("place", {"student_said": said}, said) == ""
    assert serve._consent("place", {"student_said": "place"}, said) != ""
    mine = "I'll place them myself"
    assert serve._consent("place", {"student_said": mine}, mine) != ""


def test_place_consent_is_not_route_consent():
    said = "I'll route myself, you place"
    assert serve._consent("route", {"student_said": said}, said) != ""


def test_replace_needs_words():
    said = "place them for me"
    assert serve._consent("place", {"student_said": said, "replace": True}, said) != ""
    said2 = "place them again, replace what is there"
    assert serve._consent("place", {"student_said": said2, "replace": True, "replace_said": "replace"}, said2) == ""


def test_route_consent_needs_route_word():
    said = "yes, route it for me"
    assert serve._consent("route", {"student_said": said}, said) == ""
    said = "yes please"
    assert serve._consent("route", {"student_said": said}, said) != ""


def test_parse_drc(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("Rule Violations|Un-Routed Net Constraint|13\nRule Violations|Clearance|0\nUn-Routed Net Constraint|||Net GND unrouted\n",
                 encoding="cp1252")
    r = bridge.parse_drc(f)
    assert r["unrouted"] == 13 and r["total"] == 13 and len(r["violations"]) == 1
    assert bridge.parse_drc(tmp_path / "none.txt") is None


def test_pcbcheck_info():
    log = ["pcbcheck objects=0 parts=0 tracks=0 outline_pts=4 box_mil=1000,1000,7000,5000"]
    i = bridge._pcbcheck_info(log)
    assert i["box_mil"] == (1000, 1000, 7000, 5000) and i["points"] == 4
    assert bridge._pcbcheck_info(["nothing"]) is None


def test_a_schematic_yes_is_not_consent_to_place_or_route():
    for said in ("yes", "yes, go ahead", "ok do it", "תשרטט לבד"):
        assert serve._consent("place", {"student_said": said}, said) != ""
        assert serve._consent("route", {"student_said": said}, said) != ""
    assert serve._consent("place", {"student_said": "תמקם את הרכיבים"}, "תמקם את הרכיבים") == ""
    assert serve._consent("route", {"student_said": "please route the board"}, "please route the board") == ""
    assert serve._consent("route", {"student_said": "please place the parts"}, "please place the parts") != ""    # a place yes is not a route yes
