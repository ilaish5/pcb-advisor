"""
Wave 3 independent review: each finding at its root (turn_truth, history clipping, reply language, outputs classifier, retry rounds,
bridge exceptions, order options). Consent stays untouched: nothing here lets an action run that round 0 did not already allow.
"""
import turn_truth
import agent

LIB_SHEET = ["library.build: 4 symbols", "netlist.write:1"]


# ---- 1: a promise next to actions that ran never says "nothing ran" --------------------------------------------------
def test_promise_with_actions_that_ran_names_done_and_not_done():
    reply = "I built the library and wrote sheet 1. In my next reply I will draw it."
    lines = turn_truth.closing_lines(reply, LIB_SHEET, [], [])
    assert len(lines) == 1
    line = lines[0]
    assert "nothing ran" not in line
    assert "Done: library built, sheet 1 written" in line and "Not done: drawing" in line and "draw it" in line


def test_nothing_ran_still_says_so():
    line = turn_truth.closing_lines("In my next reply I will draw it.", [], [], [])[0]
    assert "nothing ran" in line
    assert turn_truth.closing_lines("In my next reply I will draw it.", [], [], ["altium.draw_schematic: busy"])[0] == "(Stopped: altium.draw_schematic: busy)"


def test_stop_line_in_hebrew():
    line = turn_truth.closing_lines("בתשובה הבאה אצייר אותה.", LIB_SHEET, [], [], lang="he")[0]
    assert "בוצע" in line and "לא בוצע" in line and "nothing ran" not in line


# ---- 2: verb forms only -----------------------------------------------------------------------------------------------
def test_nouns_do_not_trigger_the_card_correction():
    for text in ("You have 3 proposals waiting.", "There are 3 updates, 3 cards on the board.", "3 additions pending."):
        assert turn_truth.card_correction(text, [], []) == "", text


def test_verbs_still_trigger_the_card_correction():
    assert "not 3" in turn_truth.card_correction("I proposed 3 cards.", ["bom.propose:1"], [])
    assert "not 3" in turn_truth.card_correction("I created 3 BOM cards.", [], [])


# ---- 3: head + tail clipping, the question before the student's reply is whole ----------------------------------------
def test_clip_keeps_head_and_tail():
    text = "START " + "x" * 3000 + " END?"
    out = agent._clip(text, 600)
    assert len(out) <= 600 and out.startswith("START") and out.endswith("END?") and "…" in out


def test_the_agent_message_before_the_students_latest_is_never_clipped():
    question = "Here is the plan. " + "detail " * 400 + "Shall I draw it?"
    hist = [{"role": "user", "text": "hi"}, {"role": "agent", "text": "old " + "y" * 3000}, {"role": "user", "text": "go"},
            {"role": "agent", "text": question}]
    out = agent.history_lines(hist, 8)
    assert question in out
    assert "y" * 3000 not in out                           # older turns are still clipped
    sent = agent._request_history(hist, 8)
    assert sent[-1]["text"] == question and len(sent[1]["text"]) <= agent.CLIP_AGENT


def test_a_long_student_spec_keeps_its_end():
    spec = "Design: " + "a " * 600 + "and the LAST requirement is 3.3V."
    out = agent.history_lines([{"role": "user", "text": spec}, {"role": "agent", "text": "ok"}], 8)
    assert "LAST requirement is 3.3V." in out


# ---- 4: the language of the student's last typed message with enough letters ------------------------------------------
def _auto(monkeypatch):
    real = agent.workspace.get
    monkeypatch.setattr(agent.workspace, "get", lambda k, d=None: "auto" if k == "user.language" else real(k, d))


def test_auto_language_skips_generated_and_short_messages(monkeypatch):
    _auto(monkeypatch)
    heb = {"role": "user", "text": "תבדוק את הלוח בבקשה"}
    gen = {"role": "user", "text": "List the DFM findings", "generated": True}
    assert agent.language_code("List the DFM findings", [heb], True) == "he"
    assert agent.language_code("ok", [heb, gen], False) == "he"           # too short: the earlier typed message counts
    assert agent.language_code("R5 100k", [heb], False) == "he"
    assert agent.language_code("hello there", [heb], False) == "en"       # a longer typed message wins
    assert agent.language_code("ok", [], False) == "en"                   # nothing to go by: English for a typed message
    assert agent.language_code("List it", [], True) == ""
    assert agent.reply_language_line("ok", [heb]).startswith("Reply language: Hebrew")


# ---- 9: "[P1, P2]" in chat text is a connector's designators --------------------------------------------------------
def test_chat_inline_never_rewrites_designator_brackets(tmp_path):
    import json
    import shutil

    import pytest
    from test_ui_clarity import _const, _fn, _node, _src
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    core = _src("js/core.js")
    assert "srcTags" not in _fn(core, "inline")
    script = (_const(core, "srcTags") + _const(core, "unesc") + "const chip = () => '';" + _fn(core, "inline")
              + ";process.stdout.write(JSON.stringify([inline('Connector J1 pins [P1, P2] and [P3]'), srcTags('floor 0.1 mm [P1, P3]')]));")
    a, b = _node(script, tmp_path)
    assert a == "Connector J1 pins [P1, P2] and [P3]"
    assert b == "floor 0.1 mm (JLC source 1, 3)"      # the structured JLC fields (rules.js) still get the words
    assert json.dumps(a)


# ---- 5: one BOM classifier for the outputs check and the bridge's fallback ----------------------------------------------
def test_bom_folder_files_are_boms_for_the_check_and_for_the_bridge(tmp_path):
    import outputs_check
    from altium import bridge
    for name in ("MyBoard.csv", "MyBoard.xlsx"):
        p = tmp_path / "BOM" / name
        assert outputs_check.kind_of(p) == "bom" and bridge._is_bom(p) and outputs_check.is_bom_path(p)
    other = tmp_path / "Misc" / "MyBoard.csv"
    assert outputs_check.kind_of(other) is None and not bridge._is_bom(other)
    assert outputs_check.kind_of("Bill of Materials-X.xlsx") == "bom" and outputs_check.kind_of("Board_BOM.csv") == "bom"
    # verify() classifies by the full path: a BOM/<project>.xlsx counts as the BOM
    (tmp_path / "BOM").mkdir(exist_ok=True)
    f = tmp_path / "BOM" / "MyBoard.xlsx"
    f.write_bytes(b"x")
    res = outputs_check.verify("p", [str(f)], options={"assembly": True})
    assert [e["found"] for e in res["expected"] if e["kind"] == "bom"] == [["MyBoard.xlsx"]]


# ---- 6/7: what a retry may count and draw --------------------------------------------------------------------------------
import serve  # noqa: E402


def _fx(kind, code="prereq.no_project", sheet=None):
    return {"kind": kind, "code": code, "sheet": sheet, "replace": False, "partial": False}


def test_a_no_project_refusal_of_a_kind_the_retry_cannot_run_starts_no_round():
    for kind in ("altium.run_outjob", "altium.run_drc", "altium.add_pcb", "altium.skeleton"):
        assert serve.retry_kinds([_fx(kind)]) == []
        assert not serve.retry_expected({}, [_fx(kind)], False, 0)
    for kind in ("altium.create_project", "netlist.write", "altium.draw_schematic"):
        assert serve.retry_expected({}, [_fx(kind)], False, 0)


PARTS = {"1": {"parts": [{"ref": "R1"}, {"ref": "R2"}, {"ref": "C1"}]}}


def _grants(monkeypatch, project="p"):
    monkeypatch.setattr(serve.store, "load_sheet", lambda proj, sh: PARTS.get(sh, {}))
    return serve.retry_grants([_fx("altium.draw_schematic", "sheet.too_big", "1")], project)


def _write(sheet, *refs):
    return {"type": "netlist.write", "sheet": sheet, "data": {"parts": [{"ref": r} for r in refs]}}


def _draw(sheet):
    return {"type": "altium.draw_schematic", "sheet": sheet}


def test_a_split_off_sheet_may_be_drawn_when_its_parts_were_on_a_consented_sheet(monkeypatch):
    g = _grants(monkeypatch)
    acts = [_write("1", "R1"), _write("2", "R2", "C1"), _draw("1"), _draw("2")]
    allowed, notes = serve.retry_filter(acts, g)
    assert [a.get("sheet") for a in allowed if a["type"] == "altium.draw_schematic"] == ["1", "2"] and not notes


def test_a_new_sheet_with_other_parts_or_no_write_is_still_refused(monkeypatch):
    g = _grants(monkeypatch)
    for acts in ([_write("2", "R2", "U9"), _draw("2")],                     # a part that was on no consented sheet
                 [_draw("2")],                                              # not written by the retry
                 [_draw("2"), _write("2", "R2")],                           # written only after the draw
                 [_write("2"), _draw("2")]):                                # empty
        allowed, notes = serve.retry_filter(acts, g)
        assert not [a for a in allowed if a["type"] == "altium.draw_schematic"], acts
        assert any("only sheet 1 was agreed" in n for n in notes)


# ---- 8: an unexpected exception is one action's refusal ------------------------------------------------------------------
def test_routing_lost_survives_a_parse_error(tmp_path, monkeypatch):
    import struct

    from altium import bridge, pcbdoc

    def boom(path):
        raise struct.error("unpack requires a buffer of 4 bytes")
    monkeypatch.setattr(pcbdoc, "read_pcbdoc", boom)
    assert bridge._routing_lost(tmp_path / "x.PcbDoc") == {}


def test_one_failing_action_is_refused_and_the_turn_goes_on(empty, monkeypatch):
    import struct
    real = serve.store.propose_idea

    def boom(project, topic, text, by="agent"):
        if topic == "bad":
            raise struct.error("unpack requires a buffer of 4 bytes")
        return real(project, topic, text, by=by)
    monkeypatch.setattr(serve.store, "propose_idea", boom)
    acts = [{"type": "idea.propose", "topic": "bad", "text": "x"}, {"type": "idea.propose", "topic": "good", "text": "y"}]
    applied, _, refused = serve.apply_actions(empty, acts, last_user="hi", chat=[{"role": "user", "text": "hi"}])
    assert applied == ["idea.propose:good"]
    assert len(refused) == 1 and refused[0].startswith("idea.propose: failed unexpectedly (error: ")


# ---- 10: strict booleans -------------------------------------------------------------------------------------------------
def test_assembly_is_parsed_strictly(empty):
    import pytest

    import order_options
    for v, want in ((True, True), ("true", True), ("1", True), (1, True), (False, False), ("false", False), ("0", False), (0, False)):
        assert order_options.set_options(empty, assembly=v)["assembly"] is want, v
    for bad in ("maybe", "", "yes", 2, "FALSEY"):
        with pytest.raises(ValueError):
            order_options.set_options(empty, assembly=bad)
    assert order_options.get(empty)["assembly"] is False


# ---- residual: a generated message is never a consent source, not even by carrying an earlier instruction over ------------
def test_a_generated_message_never_draws_even_with_an_earlier_unused_instruction(empty, monkeypatch):
    from altium import bridge
    seen = []
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, s=None, replace=False: seen.append(1) or
                        {"parts": 1, "nets": [], "sheets": ["s"], "warnings": []})
    said = "תצייר אתה את הסכמה באלטיום"
    act = [{"type": "altium.draw_schematic", "student_said": said}]
    typed = {"role": "user", "text": said}
    # control: a typed follow-up after the unused instruction carries it over
    applied, _, refused = serve.apply_actions(empty, act, last_user="המשך", chat=[typed, {"role": "agent", "text": "ok"},
                                                                                 {"role": "user", "text": "המשך"}])
    assert seen and applied and not refused
    seen.clear()
    gen = {"role": "user", "text": "List the DFM findings", "generated": True}
    applied, _, refused = serve.apply_actions(empty, act, last_user=gen["text"], chat=[typed, {"role": "agent", "text": "ok"}, gen])
    assert not seen and not applied and refused
    assert serve.earlier_student_messages([typed, {"role": "agent", "text": "ok"}, gen], "draw", gen["text"]) == []


# ---- 11 / 12 / 4: the turn flow ------------------------------------------------------------------------------------------
from test_agent_retry import DRAW, SAID, agent_calls, fake_draw  # noqa: E402
from test_chat_followup import chat_records, followups, idle, scripted_respond  # noqa: E402
from test_chat_turns import call, server, wait_for  # noqa: E402,F401
from altium import bridge  # noqa: E402


def test_a_deferral_whose_retry_cannot_start_gets_its_stop_line(server, empty, monkeypatch):
    fake_draw(monkeypatch, fail=None)
    scripted_respond(monkeypatch, [{"reply": "I will draw it in my next reply.", "actions": [DRAW]}])
    monkeypatch.setattr(serve, "start_followup", lambda *a, **k: False)          # the TURNS race / a step running
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    recs = agent_calls(empty)
    assert recs[0]["text"].count("(Stopped:") == 0                                # the first record left the promise to the retry
    assert len(recs) == 2 and "(נעצר:" in recs[1]["text"] and "לא יכלה להתחיל" in recs[1]["text"]     # the student's language


def test_retry_records_carry_engine_and_model_and_the_server_lines_follow_the_language(server, empty, monkeypatch):
    fake_draw(monkeypatch, fail=1)
    scripted_respond(monkeypatch, [{"reply": "Drawing.", "actions": [DRAW], "model": "m-1"},
                                   {"reply": "Fixing.", "actions": [{"type": "library.build"}, DRAW, {"type": "altium.place_pcb"}],
                                    "model": "m-2"}])
    monkeypatch.setattr(bridge, "build_library", lambda p: {"lines": []})
    monkeypatch.setattr(serve, "library_build_summary", lambda p, r: "built")
    assert call(server, "POST", "/api/chat", empty, {"text": SAID})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    r = followups(empty)[0]
    assert r["engine"] == "fake" and r["model"] == "m-2"
    assert "(לא הוחל:" in r["text"] and "(Not applied:" not in r["text"]           # Hebrew student: the server's line is Hebrew
    assert r["refused"] and "not part of what the student agreed" in r["refused"][0]


def test_a_follow_up_to_a_generated_message_speaks_the_students_language(server, empty, monkeypatch):
    seen = []

    def respond(model, message, history, cancel=None, typed=None, generated=False, **kw):
        seen.append((typed, generated))
        return {"provider": "fake", "seconds": 1, "usage": {}, "reply": "ok", "actions": []}

    monkeypatch.setattr(serve.agent, "respond", respond)
    real = serve.apply_actions
    monkeypatch.setattr(serve, "apply_actions", lambda *a, **k: (["altium.draw_schematic: 1 sheet"], [], ["netlist.write:1 refused: x"]))
    assert call(server, "POST", "/api/chat", empty, {"text": "תבדוק את הלוח בבקשה"})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    seen.clear()
    assert call(server, "POST", "/api/chat", empty, {"text": "List the DFM findings", "generated": True})[0] == 200
    assert wait_for(lambda: len(followups(empty)) == 2) and idle(server, empty)
    assert seen[-1][1] is True                                    # the follow-up of a generated message is generated too
    assert serve.agent.language_code("List the DFM findings", chat_records(empty), True) == "he"
    del real
