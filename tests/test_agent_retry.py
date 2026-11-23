"""
W3 stream 1 (RCA ש1, ledger 31 / 32 / 39): a mechanical refusal is retried in the follow-up without asking again, the retry never gets more
than round 0 was granted, and the stored closing text never contradicts the server's records.
Bridge calls and the engine are faked; consent runs for real (serve.apply_actions with the original typed message and chat).
"""
import threading
import time

import pytest

import serve
import turn_truth
from altium import bridge, draw
from test_altium_draw import RES, SHEET, SYMS, symbol
from test_chat_followup import chat_records, followups, idle, scripted_respond
from test_chat_turns import call, server, wait_for  # noqa: F401  (server is a fixture)

SAID = "תצייר אתה את הסכמה באלטיום"
DRAW = {"type": "altium.draw_schematic", "student_said": SAID}
LIB = "prereq.library_not_built"
OK_DRAW = {"parts": 3, "nets": ["GND"], "sheets": ["s"], "warnings": []}


def U(t, **kw):
    return {"role": "user", "text": t, **kw}


def fake_draw(monkeypatch, fail=1, code=LIB):
    """bridge.draw_schematic raises Fixable(code) `fail` times (None = always), then draws."""
    seen = []

    def run(project, sheet=None, replace=False):
        seen.append((sheet, replace))
        if fail is None or len(seen) <= fail:
            raise bridge.Fixable(code, "The project library is not built yet: run library.build first")
        return dict(OK_DRAW)

    monkeypatch.setattr(bridge, "draw_schematic", run)
    return seen


def spy_apply(monkeypatch):
    """The real apply_actions, recording every call's arguments."""
    calls, real = [], serve.apply_actions

    def wrapper(project, actions, *a, **k):
        calls.append({"actions": actions, **k})
        return real(project, actions, *a, **k)

    monkeypatch.setattr(serve, "apply_actions", wrapper)
    return calls


def agent_calls(empty):
    return [r for r in chat_records(empty) if r["role"] == "agent"]


# ---------------------------------------------------------------- the frozen set and where codes come from

def test_the_neutral_code_set_is_frozen():
    assert bridge.NEUTRAL_CODES == frozenset({"pins.unmapped", "sheet.too_big", "prereq.library_not_built", "prereq.no_project",
                                              "prereq.no_netlist", "prereq.rules_not_imported"})
    assert serve.FOLLOWUP_MAX_RETRY == 2
    assert serve.RETRY_WHITELIST == frozenset({"netlist.write", "library.build", "altium.create_project", "altium.import_rules"})
    with pytest.raises(ValueError):
        bridge.Fixable("anything.else", "x")


def test_plan_sheet_assigns_codes_structurally():
    assert draw.plan_sheet(SHEET, {"R1": SYMS["R1"]}, "l", "d")["fix_code"] == LIB
    bad = {**SHEET, "parts": [{"ref": "R1", "pins": [{"num": "9", "name": "9", "net": "+5V"}, {"num": "2", "name": "2", "net": "GND"}]}]}
    assert draw.plan_sheet(bad, {"R1": SYMS["R1"]}, "l", "d")["fix_code"] == "pins.unmapped"
    parts = [{"ref": f"R{i}", "pins": [{"num": "1", "net": f"NET_NUMBER_{i}_LONG"}, {"num": "2", "net": "GND"}]} for i in range(1, 80)]
    assert draw.plan_sheet({"parts": parts}, {x["ref"]: SYMS["R1"] for x in parts}, "l", "d")["fix_code"] == "sheet.too_big"
    multi = symbol("RES2", RES)
    multi["pins"][1]["part_id"] = 2
    assert draw.plan_sheet({"parts": [{"ref": "R1", "pins": [{"num": "1", "net": "A"}, {"num": "2", "net": "B"}]}]}, {"R1": multi}, "l", "d")["fix_code"] is None


def test_a_fixable_refusal_is_recorded_after_consent_only(empty, monkeypatch):
    fake_draw(monkeypatch, fail=None)
    fixes = []
    applied, _, refused = serve.apply_actions(empty, [DRAW], last_user=SAID, chat=[U(SAID)], fixables=fixes)
    assert not applied and refused and [(f["kind"], f["code"]) for f in fixes] == [("altium.draw_schematic", LIB)]


@pytest.mark.parametrize("said,last,chat", [
    ("", "המשך", [U("hello"), U("המשך")]),                                          # no consent at all
    ("כן", "המשך", [U("כן"), {"role": "agent", "text": "ok", "applied": []}, U("המשך")]),    # a bare yes from an earlier turn
    (SAID, SAID, [U(SAID, generated=True)]),                                         # a button wrote the message
    (SAID, "אני אצייר בעצמי", [U(SAID), U("אני אצייר בעצמי")]),                      # the student draws himself
])
def test_every_consent_refusal_is_never_neutral(empty, monkeypatch, said, last, chat):
    seen = fake_draw(monkeypatch, fail=None)
    fixes = []
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.draw_schematic", "student_said": said}], last_user=last, chat=chat,
                                              fixables=fixes)
    assert not applied and refused and not seen and fixes == []


def test_rules_not_imported_is_neutral_for_route_only(empty, monkeypatch):
    def boom(*a, **k):
        raise bridge.Fixable("prereq.rules_not_imported", "Import the JLC rules first")
    monkeypatch.setattr(bridge, "route_pcb", boom)
    fixes = []
    msg = "route the board for me"
    serve.apply_actions(empty, [{"type": "altium.route_pcb", "student_said": msg}], last_user=msg, chat=[U(msg)], fixables=fixes)
    assert [f["code"] for f in fixes] == ["prereq.rules_not_imported"]
    monkeypatch.setattr(bridge, "place_pcb", boom)           # the same code on another kind is not a neutral refusal
    other = []
    serve.apply_actions(empty, [{"type": "altium.place_pcb", "student_said": "place the parts for me"}], last_user="place the parts for me",
                        chat=[U("place the parts for me")], fixables=other)
    assert serve.retry_kinds(other) == []


def test_needs_replace_and_plain_bridge_errors_are_never_neutral(empty, monkeypatch):
    def boom(*a, **k):
        raise bridge.BridgeError("sheet.xml already has 12 objects (parts, wires, labels). I never wipe a drawing")
    monkeypatch.setattr(bridge, "draw_schematic", boom)
    fixes = []
    serve.apply_actions(empty, [DRAW], last_user=SAID, chat=[U(SAID)], fixables=fixes)
    assert fixes == []


# ---------------------------------------------------------------- what a retry may run

def fx(kind, sheet=None, replace=False, partial=False, code=LIB):
    return {"kind": kind, "code": code, "sheet": sheet, "replace": replace, "partial": partial}


def test_the_retry_filter_whitelists_and_never_widens_the_grant():
    grants = serve.retry_grants([fx("altium.draw_schematic", sheet="01")])
    acts = [{"type": "library.build"}, {"type": "netlist.write", "sheet": "01", "data": {}}, {"type": "altium.import_rules"},
            {"type": "altium.create_project"},
            {"type": "altium.draw_schematic", "sheet": "01"},
            {"type": "altium.draw_schematic", "sheet": "02"},            # a sheet round 0 never named
            {"type": "altium.draw_schematic"},                             # all sheets, round 0 named one
            {"type": "altium.draw_schematic", "sheet": "01", "replace": True},   # replace was not granted
            {"type": "altium.place_pcb"}, {"type": "altium.route_pcb"},    # other kinds: no consent in round 0
            {"type": "bom.propose", "line": "x", "changes": {}}, {"type": "netlist.remove", "sheet": "01"},
            {"type": "jlc.gerber_zip"}, {"type": "idea.confirm"}]
    allowed, notes = serve.retry_filter(acts, grants)
    assert [(a["type"], a.get("sheet")) for a in allowed] == [("library.build", None), ("netlist.write", "01"), ("altium.import_rules", None),
                                                              ("altium.create_project", None), ("altium.draw_schematic", "01")]
    assert len(notes) == len(acts) - len(allowed)


def test_replace_and_partial_pass_only_when_round_0_carried_them():
    grants = serve.retry_grants([fx("altium.draw_schematic", replace=True), fx("altium.route_pcb", partial=True, code="prereq.rules_not_imported")])
    allowed, _ = serve.retry_filter([{"type": "altium.draw_schematic", "sheet": "05", "replace": True},
                                     {"type": "altium.route_pcb", "partial": True}, {"type": "altium.route_pcb", "replace": True}], grants)
    assert [a["type"] for a in allowed] == ["altium.draw_schematic", "altium.route_pcb"] and allowed[1].get("partial")


# ---------------------------------------------------------------- the turn flow

def test_a_neutral_refusal_is_retried_with_round_0_consent_and_stores_its_applied_list(server, empty, monkeypatch):
    seen = fake_draw(monkeypatch, fail=1)
    calls = spy_apply(monkeypatch)
    agent = scripted_respond(monkeypatch, [{"reply": "Drawing sheet 01 now.", "actions": [DRAW]},
                                           {"reply": "Building the library first.", "actions": [{"type": "library.build"}, DRAW]}])
    monkeypatch.setattr(bridge, "build_library", lambda p: {"lines": []})
    monkeypatch.setattr(serve, "library_build_summary", lambda p, r: "built")
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    assert len(agent) == 2 and agent[1][0].startswith("Results of your actions: ") and "mechanical" in agent[1][0]
    r = followups(empty)[0]
    assert r["retry"] == 1 and any(x.startswith("altium.draw_schematic") for x in r["applied"]) and len(seen) == 2
    # the retry ran with the ORIGINAL typed message and the chat before the main record, never with the follow-up prompt
    assert calls[1]["last_user"] == SAID and calls[1]["allow_auto"] is False and calls[1]["chat"][-1]["text"] == SAID
    assert all("Results of your actions" not in str(m.get("text")) for m in calls[1]["chat"])
    # the record uses the consent up: a bare yes next turn does not redraw
    assert serve.earlier_student_messages([*chat_records(empty), U("yes")], "draw", "yes") == []


def test_at_most_two_retry_rounds(server, empty, monkeypatch):
    fake_draw(monkeypatch, fail=None)
    agent = scripted_respond(monkeypatch, [{"reply": "Drawing.", "actions": [DRAW]}])
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert wait_for(lambda: len(followups(empty)) == 2, 8) and idle(server, empty)
    time.sleep(0.3)
    assert len(agent) == 3 and [r["retry"] for r in followups(empty)] == [1, 2]


@pytest.mark.parametrize("text,generated", [("hello, write the netlist", False), (SAID, True), ("אני אצייר בעצמי, תכתוב את הרשימה", False)])
def test_a_retry_never_draws_without_round_0_consent(server, empty, monkeypatch, text, generated):
    seen = fake_draw(monkeypatch, fail=None)
    fixed = {"type": "netlist.write", "sheet": "01", "data": {"parts": []}}

    def refusing(project, actions, *a, fixables=None, **k):
        fixables.append({"kind": "netlist.write", "code": "pins.unmapped", "sheet": "01", "replace": False, "partial": False})
        return [], [], ["netlist.write:01 refused: pins"]
    real = serve.apply_actions
    state = {"n": 0}

    def route(project, actions, *a, **k):
        state["n"] += 1
        return refusing(project, actions, *a, **k) if state["n"] == 1 else real(project, actions, *a, **k)

    monkeypatch.setattr(serve, "apply_actions", route)
    scripted_respond(monkeypatch, [{"reply": "writing", "actions": [fixed, {**DRAW, "student_said": SAID}]},
                                   {"reply": "fixed", "actions": [DRAW]}])
    assert call(server, "POST", "/api/chat", empty, {"text": text, "generated": generated})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    r = followups(empty)[0]
    assert not seen and not r["applied"] and any("not part of what the student agreed" in x for x in r["refused"])


def test_a_new_message_during_a_retry_cancels_it_and_nothing_runs(server, empty, monkeypatch):
    seen = fake_draw(monkeypatch, fail=1)
    started = threading.Event()

    def blocking(cancel):
        started.set()
        assert cancel.wait(10)
        return {"reply": "half", "actions": [DRAW], "partial": True, "error_kind": "stopped"}

    agent = scripted_respond(monkeypatch, [{"reply": "Drawing.", "actions": [DRAW]}, blocking,
                                           {"reply": "answer to the new question", "actions": []}])
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert started.wait(5)
    assert call(server, "POST", "/api/chat", empty, {"text": "new question"})[0] == 200
    assert len(agent) == 3 and not followups(empty) and len(seen) == 1


def test_stop_ends_a_retry(server, empty, monkeypatch):
    seen = fake_draw(monkeypatch, fail=1)
    started = threading.Event()

    def blocking(cancel):
        started.set()
        assert cancel.wait(10)
        return {"reply": "half", "actions": [DRAW], "partial": True, "error_kind": "stopped"}

    scripted_respond(monkeypatch, [{"reply": "Drawing.", "actions": [DRAW]}, blocking])
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert started.wait(5)
    assert call(server, "POST", "/api/chat/stop", empty)[0] == 200
    assert idle(server, empty) and not followups(empty) and len(seen) == 1


def test_a_retry_does_not_start_while_altium_is_busy(server, empty, monkeypatch):
    fake_draw(monkeypatch, fail=None)
    agent = scripted_respond(monkeypatch, [{"reply": "Drawing.", "actions": [DRAW]}])
    serve.STEP_LOCK.acquire()
    try:
        assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] in (200, 409)
    finally:
        serve.STEP_LOCK.release()
    time.sleep(0.3)
    assert len(agent) <= 1 and not followups(empty)


# ---------------------------------------------------------------- the closing text (rows 31 and 39)

def test_a_count_that_contradicts_the_cards_gets_one_correction():
    applied = [f"bom.propose:L{i}" for i in range(11)]
    assert "created 11 BOM cards, not 12" in turn_truth.card_correction("I added 12 BOM lines for you.", applied, [])
    assert turn_truth.card_correction("I proposed 11 cards.", applied, []) == ""
    assert turn_truth.card_correction("The BOM has 40 lines.", applied, []) == ""            # not a claim about this turn
    assert "no BOM cards" in turn_truth.card_correction("I added 3 cards.", [], [])


def test_a_promise_nothing_keeps_is_stopped_by_the_server():
    assert turn_truth.promises_work("I'm sending it in my next reply.", ["idea.ready"], [])
    assert turn_truth.promises_work("I will now draw the sheet.", [], [])
    assert not turn_truth.promises_work("I will now draw the sheet.", ["altium.draw_schematic: ok"], [])
    assert not turn_truth.promises_work("Sheet 01 is drawn.", [], [])
    assert turn_truth.stopped_line(["altium.draw_schematic: not run. no consent"]).startswith("(Stopped: altium.draw_schematic")
    assert "nothing ran" in turn_truth.stopped_line([])
    assert turn_truth.closing_lines("next reply", [], [], [], retry_follows=True) == []


def test_the_stored_reply_carries_the_correction_and_the_stopped_line(server, empty, monkeypatch):
    scripted_respond(monkeypatch, [{"reply": "I'll send the rest in my next reply.", "actions": []}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go on"})[0] == 200
    assert agent_calls(empty)[-1]["text"].endswith("nothing ran; write again or press the button)")


def test_no_stopped_line_when_a_retry_is_about_to_do_the_work(server, empty, monkeypatch):
    fake_draw(monkeypatch, fail=1)
    scripted_respond(monkeypatch, [{"reply": "I will now draw it.", "actions": [DRAW]}, {"reply": "done", "actions": [DRAW]}])
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    assert "(Stopped:" not in agent_calls(empty)[0]["text"]
