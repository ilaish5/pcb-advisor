"""Three usability fixes: the BOM part count against the schematic, the board size typed directly (no "Confirm idea" first), and the
partial route offered as a second button after "no tracks drawn" (the click is the consent). The bridge is faked."""
import json
import pathlib

import pytest

import store
from altium import bridge, layout
from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
BOM_JS = (REPO / "ui" / "js" / "views" / "bom.js").read_text(encoding="utf-8")
CHAT_JS_ALL = (REPO / "ui" / "js" / "chat.js").read_text(encoding="utf-8")


def _bom(project, refs_per_line):
    log = store.pdir(project) / "bom-log.jsonl"
    log.write_text("".join(json.dumps({"line": k, "changes": {"refs": r, "value": k}}) + "\n" for k, r in refs_per_line.items()), encoding="utf-8")


def _sheet(project, refs):
    res = store.write_sheet(project, "main", {"parts": [{"ref": r, "pins": [{"num": "1", "name": "1", "net": "N"}]} for r in refs]})
    assert res["ok"]


# ---- 1. BOM count against the schematic

def test_a_part_in_the_schematic_but_not_in_the_bom_is_named(empty):
    _bom(empty, {"R": ["R1", "R2"], "C": ["C1"]})
    _sheet(empty, ["R1", "R2", "C1", "U4"])
    c = store.bom_design_count(empty)
    assert c["only_in_design"] == ["U4"] and c["only_in_bom"] == []
    assert c["message"] == "3 designators in the BOM (DNP and test points included), 4 in the schematic: U4 is in the schematic but not in the BOM"
    import model
    assert model.build(empty)["bom_count_check"] == c


def test_a_part_in_the_bom_but_not_in_the_schematic_is_named(empty):
    _bom(empty, {"R": ["R1", "R2"], "C": ["C1"]})
    _sheet(empty, ["R1", "R2"])
    c = store.bom_design_count(empty)
    assert c["only_in_bom"] == ["C1"] and "C1 is in the BOM but not in the schematic" in c["message"]


@pytest.mark.parametrize("bom,sheet", [({}, ["R1"]), ({"R": ["R1"]}, []), ({"R": ["R1"], "X": []}, ["R1"])])
def test_no_warning_when_one_side_is_unknown(empty, bom, sheet):
    _bom(empty, bom)
    if sheet:
        _sheet(empty, sheet)
    assert store.bom_design_count(empty) is None


def test_no_warning_when_they_agree(empty):
    _bom(empty, {"R": ["R1", "R2"]})
    _sheet(empty, ["R2", "R1"])
    assert store.bom_design_count(empty) is None


def test_the_bom_tab_shows_the_server_message():
    assert "S.bom_count_check" in BOM_JS and "bomCountNote()" in BOM_JS and "c.message" in BOM_JS


# ---- 2. board size without "Confirm idea"

def test_the_board_size_can_be_set_before_the_idea_is_confirmed(server, empty):
    assert not store.load_idea(empty).get("confirmed")
    code, body = call(server, "POST", "/api/idea/board", empty, {"width": 60, "height": 40})
    assert code == 200 and body["idea"]["board"] == {"width_mm": 60.0, "height_mm": 40.0}
    assert layout.board_size(store.load_idea(empty)) == (60.0, 40.0)         # what placement reads
    assert bridge._board_size(empty) == (60.0, 40.0)
    assert not store.load_idea(empty).get("confirmed")


def test_the_board_size_in_cm_is_converted_and_survives_a_draft(server, empty):
    store.propose_idea(empty, "Power", "5 V in")                              # makes a draft
    assert store.has_idea_draft(empty)
    assert call(server, "POST", "/api/idea/board", empty, {"width": 6, "height": 4.5, "unit": "cm"})[0] == 200
    store.save_idea_from_draft(empty)
    assert store.load_idea(empty)["board"] == {"width_mm": 60.0, "height_mm": 45.0}


@pytest.mark.parametrize("body", [{"width": 0, "height": 40}, {"width": -5, "height": 40}, {"width": "abc", "height": 40},
                                  {"width": 5, "height": 40}, {"width": 600, "height": 40}, {"width": 60},
                                  {"width": 60, "height": 40, "unit": "inch"}, {"width": "nan", "height": 40}])
def test_a_bad_board_size_is_refused_and_nothing_is_stored(server, empty, body):
    code, res = call(server, "POST", "/api/idea/board", empty, body)
    assert code == 400 and res["error"]
    assert "board" not in store.load_idea(empty)


def test_both_empty_clears_the_board_size(server, empty):
    call(server, "POST", "/api/idea/board", empty, {"width": 60, "height": 40})
    assert call(server, "POST", "/api/idea/board", empty, {"width": "", "height": ""})[0] == 200
    assert "board" not in store.load_idea(empty)


def test_the_idea_page_has_a_board_size_field_that_does_not_need_confirm():
    js = (REPO / "ui" / "js" / "views" / "idea.js").read_text(encoding="utf-8")
    assert "boardSizeHTML()" in js and "/api/idea/board" in js and "set-board-size" in js
    row = js[js.index("function boardSizeHTML"):js.index("function requirementsHTML")]
    assert "disabled" not in row and "confirmed" not in row


# ---- 3. the partial route button

ROUTED_PARTIAL = {"summary": "3 nets routed; PARTIAL ROUTE, left open: GND (no way)", "warnings": ["open nets, not routed: GND"], "routed": ["A"], "failed": [("GND", "no way")]}


def test_a_route_that_cannot_finish_offers_the_partial_route_and_never_takes_it_alone(server, empty, monkeypatch):
    seen = []

    def route(p, replace=False, keep_partial=False):
        seen.append(keep_partial)
        if keep_partial:
            return dict(ROUTED_PARTIAL)
        err = bridge.BridgeError("no tracks drawn: could not route GND (no way)")
        err.open_nets = ["GND"]
        raise err

    monkeypatch.setattr(bridge, "route_pcb", route)
    code, body = call(server, "POST", "/api/altium/route", empty, {})
    assert code == 400 and "no tracks drawn" in body["error"] and body["partial_offer"] == ["GND"] and seen == [False]
    code, body = call(server, "POST", "/api/altium/route", empty, {"keep_partial": True})      # the button
    assert code == 200 and seen == [False, True] and "left open: GND" in body["summary"] and "partial_offer" not in body


def test_other_failures_offer_no_partial_route(server, empty, monkeypatch):
    def route(p, replace=False, keep_partial=False):
        raise bridge.BridgeError("Import the JLC rules first")
    monkeypatch.setattr(bridge, "route_pcb", route)
    code, body = call(server, "POST", "/api/altium/route", empty, {})
    assert code == 400 and "partial_offer" not in body


def test_the_page_offers_the_second_button_and_sends_keep_partial():
    js = ui_js()
    assert "Route the rest and leave ' + n.partial.join(', ') + ' open'" in js
    assert "keep_partial: true" in js and "partial: r && Array.isArray(r.partial_offer)" in js
    assert "d.partial === '1'" in js


# ---- BOM page: pending proposals, readable cards, auto stock check, tooltips



def test_bom_page_wiring_for_pending_proposals_and_stock():
    assert "bomPending()" in BOM_JS and "prop-decide" in CHAT_JS_ALL and "waiting for your approval" in BOM_JS
    assert "bomAutoCheck" not in BOM_JS and "priced lines only" in BOM_JS and "propListHTML" in BOM_JS
    assert "No symbol or footprint" in BOM_JS and "more problem" in BOM_JS


def test_group_card_lists_fields_not_raw_text():
    import pathlib
    chat = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "chat.js").read_text(encoding="utf-8")
    assert "propRowOf(p" in chat and "esc(propSummary(p))" not in chat and "prop-grow" not in chat
    assert "bomAutoCheck" not in chat
