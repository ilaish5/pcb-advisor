"""Pin decisions downstream (W2-B): the accepted risk stays visible in the sheet, the drawn heading, the order check and the manifest;
rule 11 of AGENTS.md says what the gate does; a guessed pinout warns when it is written."""
import copy
import json
import pathlib

import order_check
import pin_decisions
import render_sheet
import store
from altium import draw
from test_altium_draw import SHEET, SYMS
from test_unverified_pins import _sheet

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_rules_match_gate():
    """Rule 11: R/C/L/crystal never ask; connectors, diodes and LEDs are confirmed before manufacturing files."""
    text = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    rule = text[text.index("\n11. "):text.index("\n# HOW TO ANSWER")]
    assert "R/C/L/crystal need no datasheet" in rule and "Connectors, diodes and LEDs" in rule
    assert "confirms pin numbers/polarity before manufacturing" in rule
    gated = set(store.CONNECTOR_PREFIXES) | set(store.POLARISED_PREFIXES)
    assert gated == {"J", "P", "D", "LED"} and gated <= set(store.SIMPLE_PREFIXES)
    for prefix in ("R", "C", "L", "Y", "XTAL"):        # never asked: no datasheet and no decision still gives ""
        assert prefix in store.SIMPLE_PREFIXES and prefix not in gated
        assert store.pins_status({"key": prefix + "1", "refs": [prefix + "1"]}, {})[0] == ""
    for prefix in gated:
        assert store.pins_status({"key": prefix + "1", "refs": [prefix + "1"]}, {})[0] == "unverified"
    assert "not pin assignments" in text and "never write `pin_decision`" in text


def test_writing_a_guessed_pinout_warns_once(empty):
    res = _sheet(empty)
    assert any("pins of U1 is a guess" in w and "datasheet page" in w for w in res["warnings"])
    again = store.write_sheet(empty, "01", {k: v for k, v in store.load_sheet(empty, "01").items() if k != "id"})
    assert not any("a guess" in w for w in again["warnings"])          # unchanged pins: not said again


def test_the_sheet_marks_an_accepted_part_and_the_drawn_heading_says_so(empty):
    _sheet(empty)
    pin_decisions.accept(empty, "U1")
    svg = render_sheet.render_sheet(store.load_sheet(empty, "01"), store.bom_lines(empty))
    assert "accepted, not verified" in svg and "Pins not checked against a datasheet yet" not in svg
    sheet = copy.deepcopy(SHEET)
    sheet["parts"][0]["pins_source"] = "student"
    p = draw.plan_sheet(sheet, SYMS, "lib.SchLib", "sheet.SchDoc")
    assert p["accepted_pins"] == ["U1"] and p["unverified"] == []
    assert [c[6] for c in p["commands"] if c[0] == "FRAME"] == ["[advisor] PWR - Input | pins accepted by student, not verified: U1"]


def test_order_check_carries_the_accepted_risk_and_writes_a_manifest_beside_the_zip(empty):
    _sheet(empty)
    pin_decisions.accept(empty, "U1", evidence=[{"doc": "d.pdf", "page": 3}])
    res = order_check.order_check(empty)
    assert res["counts"]["accepted_risk"] == 1
    assert {l["line"]: l["pin_decision"]["basis"] for l in res["lines"] if l["pin_decision"]} == {"U1": "datasheet_page"}
    assert "accepted_risk" not in order_check.summary(res)
    manifest = json.loads((store.pdir(empty) / "exports" / f"{empty}_order_manifest.json").read_text(encoding="utf-8"))
    assert [r["line"] for r in manifest["accepted_risks"]] == ["U1"] and manifest["unverified"] == [] and "generated" in manifest
