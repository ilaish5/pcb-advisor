"""T27/T29/T32/T16: the student's instruction counts from an earlier turn (until that action ran), the one-turn chain create ->
library.build -> netlist.write -> draw works, a table row naming C2 needs C2 in a BOM line, the reply language line."""
import pytest

import agent
import serve
import store
from altium import bridge
from test_chat_turns import server  # noqa: F401
from test_netlist_symbol_pins import _setup

SAID = "תצייר אתה את הסכמה באלטיום"


def U(t):
    return {"role": "user", "text": t}


def A(t, *applied):
    return {"role": "agent", "text": t, "applied": list(applied)}


@pytest.fixture
def spy(monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, s=None, replace=False: seen.append(replace) or
                        {"parts": 3, "nets": ["GND"], "sheets": ["s"], "warnings": []})
    return seen


def _draw(project, said, last, chat):
    return serve.apply_actions(project, [{"type": "altium.draw_schematic", "student_said": said}], last_user=last, chat=chat)


def test_consent_given_before_a_library_build_turn_still_counts(empty, spy):
    chat = [U(SAID), A("building", "library.build: 2 of 2 lines built"), U("המשך")]
    applied, _, refused = _draw(empty, SAID, "המשך", chat)
    assert spy == [False] and applied and not refused


def test_instruction_and_action_in_one_turn(empty, spy):
    applied, _, refused = _draw(empty, SAID, SAID, [U(SAID)])
    assert spy == [False] and applied and not refused


def test_no_consent_at_all_is_refused_with_what_is_missing(empty, spy):
    applied, _, refused = _draw(empty, "", "המשך", [U("hello"), A("hi"), U("המשך")])
    assert not spy and not applied
    assert "student_said" in refused[0] and "Ask the student first" in refused[0] and "tell you to draw" in refused[0]


def test_a_bare_yes_from_an_earlier_turn_is_no_consent(empty, spy):
    _, _, refused = _draw(empty, "כן", "המשך", [U("כן"), A("ok"), U("המשך")])
    assert refused and not spy


def test_the_consent_is_used_up_by_a_draw_that_ran(empty, spy):
    chat = [U(SAID), A("done", "altium.draw_schematic: 3 parts drawn"), U("תודה")]
    _, _, refused = _draw(empty, SAID, "תודה", chat)
    assert refused and not spy


def test_a_newer_do_it_myself_cancels_an_older_yes(empty, spy):
    chat = [U(SAID), A("ok"), U("אני אצייר את הסכמה בעצמי"), A("ok"), U("המשך")]
    _, _, refused = _draw(empty, SAID, "המשך", chat)
    assert refused and "themselves" in refused[0] and not spy


def test_place_and_route_need_their_own_word_in_the_earlier_message(empty, monkeypatch):
    chat = [U(SAID), A("ok"), U("המשך")]
    for kind in ("altium.place_pcb", "altium.route_pcb"):
        _, _, refused = serve.apply_actions(empty, [{"type": kind, "student_said": SAID}], last_user="המשך", chat=chat)
        assert refused and "not run" in refused[0], kind
    seen = []
    monkeypatch.setattr(bridge, "place_pcb", lambda p, replace=False: seen.append(1) or {"placed": ["U1"], "outline_created": False, "warnings": []})
    said = "תמקם אתה את הרכיבים"
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.place_pcb", "student_said": said}], last_user="המשך",
                                              chat=[U(said), A("ok", "library.build: x"), U("המשך")])
    assert seen and applied and not refused


def test_one_turn_chain_create_build_netlist_draw(empty, monkeypatch):
    import partlib
    data = _setup(empty, [("1", "GND"), ("2", "VBUS")])           # pin NAMES only; the numbers come from the built symbol
    lib = partlib.library_dir(empty)
    spec = (lib / "build" / "symbols_spec.txt").read_text(encoding="cp1252")
    manifest = (lib / "manifest.json").read_text(encoding="utf-8")
    (lib / "build" / "symbols_spec.txt").unlink()
    (lib / "manifest.json").unlink()
    order = []

    def build(project):
        order.append("build")
        (lib / "build").mkdir(parents=True, exist_ok=True)
        (lib / "build" / "symbols_spec.txt").write_text(spec, encoding="cp1252")
        (lib / "manifest.json").write_text(manifest, encoding="utf-8")
        return {"built": 1, "lines": 1}

    monkeypatch.setattr(bridge, "create", lambda p: order.append("create") or {})
    monkeypatch.setattr(bridge, "build_library", build)
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, s=None, replace=False: order.append("draw") or
                        {"parts": 1, "nets": ["GND"], "sheets": ["s"], "warnings": []})
    acts = [{"type": "altium.create_project"}, {"type": "library.build"}, {"type": "netlist.write", "sheet": "01", "data": data},
            {"type": "altium.draw_schematic", "student_said": SAID}]
    applied, _, refused = serve.apply_actions(empty, acts, last_user=SAID, chat=[U(SAID)])
    assert not refused and order == ["create", "build", "draw"], (applied, refused)
    assert any("matched by pin name" in x for x in applied)
    assert [p["num"] for p in data["parts"][0]["pins"]] == ["A1B12", "A4B9"]


def test_refs_named_in_a_table_row_must_be_in_a_bom_line(empty):
    store.propose_bom(empty, "C1", {"mpn": "CL21", "refs": ["C1"], "value": "100nF"}, new=True)
    table = "| Ref | Part |\n|---|---|\n| C1, C2 | 100nF |\n| R1 | 1k |\n"
    assert serve.refs_missing_from_bom(empty, table) == ["C2"]
    store.propose_bom(empty, "C1", {"refs": ["C1", "C2"]}, new=True)
    assert serve.refs_missing_from_bom(empty, table) == []
    assert serve.refs_missing_from_bom(empty, "C1 and C2 are fine") == []


def test_reply_language_line():
    assert agent.reply_language_line("כן, תצייר") == "Reply language: Hebrew\n"
    assert agent.reply_language_line("yes, draw it") == ""
    hist = [{"role": "user", "text": "שלום"}, {"role": "agent", "text": "hi"}, {"role": "user", "text": "List the findings", "generated": True}]
    assert agent.reply_language_line("List the findings", hist, generated=True) == "Reply language: Hebrew\n"
    assert agent.reply_language_line("List the findings", [{"role": "user", "text": "hello"}], generated=True) == ""


# ---- review round: what counts as the student's instruction, and what cancels it

ROUTE_SAID = "route the board for me"


def _consent(kind, said, last, earlier=()):
    return serve._consent(kind, {"student_said": said}, last, earlier)


def test_a_cancel_in_the_current_message_wins_over_an_older_quote():
    for now in ("actually I'll route it myself", "no", "not yet", "wait", "לא עכשיו", "חכה", "עצור", "אל תנתב עכשיו", "stop please"):
        assert _consent("route", ROUTE_SAID, now, [ROUTE_SAID]) != "", now
    assert _consent("route", ROUTE_SAID, "go on", [ROUTE_SAID]) == ""


def test_a_newer_do_it_myself_alone_cancels_an_older_instruction():
    for mid in ("never mind, I'll do it myself", "אני אעשה את זה בעצמי", "no", "wait, not yet", "עצור"):
        why = _consent("route", ROUTE_SAID, "go on", [mid, ROUTE_SAID])
        assert why != "", mid
    assert _consent("route", ROUTE_SAID, "go on", ["thanks", ROUTE_SAID]) == ""


def test_an_old_question_or_topic_mention_is_no_instruction():
    for said in ("how do I route this?", "how to route the board", "explain the schematic", "איך מנתבים את הלוח?",
                 "can you route the board", "I want to route the board someday"):
        kind = "route" if "schematic" not in said else "draw"
        assert _consent(kind, said, "go on", [said]) != "", said
    assert _consent("draw", "you draw the block diagram", "go on", ["you draw the block diagram"]) != ""
    assert _consent("draw", "you draw the schematic", "go on", ["you draw the schematic"]) == ""
    assert _consent("route", "תנתב אתה את הלוח", "go on", ["תנתב אתה את הלוח"]) == ""
    assert _consent("place", "please place the parts on the board", "ok", ["please place the parts on the board"]) == ""
    assert _consent("place", "go ahead and place the components", "ok", ["go ahead and place the components"]) == ""


def test_the_last_message_as_a_question_or_block_diagram_is_no_instruction_either():
    assert _consent("route", "how do I route this?", "how do I route this?") != ""
    assert _consent("place", "איך ממקמים את הרכיבים?", "איך ממקמים את הרכיבים?") != ""
    assert _consent("draw", "you draw the block diagram", "you draw the block diagram") != ""
    assert _consent("route", ROUTE_SAID, ROUTE_SAID) == ""


def test_a_do_it_myself_about_another_object_does_not_cancel():
    said = "I'll do the PCB myself, you draw the schematic"
    assert _consent("draw", said, said) == ""
    said = "אני אנתב בעצמי ואתה תצייר את הסכמה"
    assert _consent("draw", said, said) == ""
    said = "I'll route the board myself but you place the parts"
    assert _consent("place", said, said) == ""
    assert _consent("route", said, said) != ""


def test_an_unclear_do_it_myself_is_refused_and_the_agent_is_told_to_ask_who():
    said = "I'll do the PCB myself, please route the board"
    why = _consent("route", said, said)
    assert "who routes" in why and "Do not route" in why
    said = "you draw the schematic, I'll do it myself"
    assert "who draws" in _consent("draw", said, said)


def test_a_button_message_is_not_the_students_consent(empty, spy):
    gen = {"role": "user", "text": SAID, "generated": True}
    _, _, refused = _draw(empty, SAID, SAID, [gen])                       # the last message was made by a button
    assert refused and not spy
    chat = [gen, A("ok"), U("המשך")]                                      # and an earlier one
    _, _, refused = _draw(empty, SAID, "המשך", chat)
    assert refused and not spy
    assert serve.earlier_student_messages([gen, U("hello"), U("now")], "draw", "now") == ["hello"]


def test_a_cancel_after_the_quote_blocks_the_whole_action_path(empty, monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "route_pcb", lambda p, replace=False, keep_partial=False: seen.append(1) or {"summary": "ok", "warnings": []})
    chat = [U(ROUTE_SAID), A("ok"), U("actually I'll route it myself")]
    _, _, refused = serve.apply_actions(empty, [{"type": "altium.route_pcb", "student_said": ROUTE_SAID}], last_user="actually I'll route it myself", chat=chat)
    assert refused and not seen


def test_a_turn_that_applied_something_with_an_empty_reply_leaves_its_marker(server, empty, monkeypatch):
    from test_chat_turns import call
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {"reply": "", "actions": [{"type": "idea.describe", "text": "a blinking LED"}],
                                                                  "provider": "fake", "seconds": 1, "usage": {}})
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    import session as session_mod
    rec = [r for r in session_mod.load_chat(empty, session_mod.current(empty, None)) if r["role"] == "agent"]
    assert rec and rec[-1]["applied"]


def test_a_failing_bom_check_cannot_lose_the_reply_or_the_marker(server, empty, monkeypatch):
    from test_chat_turns import call
    import session as session_mod
    monkeypatch.setattr(serve, "refs_missing_from_bom", lambda p, r: 1 / 0)
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {
        "reply": "done", "actions": [{"type": "bom.propose", "line": "C1", "new": True, "changes": {"mpn": "X1", "refs": ["C1"], "value": "100nF"}}],
        "provider": "fake", "seconds": 1, "usage": {}})
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    rec = [r for r in session_mod.load_chat(empty, session_mod.current(empty, None)) if r["role"] == "agent"]
    assert rec and rec[-1]["text"] == "done"
