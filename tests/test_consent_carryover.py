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


# ---------------------------------------------------------------- replace: only a short, unambiguous replace or yes

LIVE = "שרטט מחדש את 01 ו-02 באלטיום"
ASKED = "Replace the drawing on sheet 01? This wipes what is drawn there (a backup is kept). Answer yes/no."


def _rep(msg, prev=""):
    return serve._draw_consent({"student_said": msg, "replace": True, "sheet": "01"}, msg, (), prev)


@pytest.mark.parametrize("msg", [
    "כן, תחליף", "yes, replace it", "תשרטט מחדש", "redraw sheet 01", "overwrite it", LIVE,
    "draw it and replace the old one", "תדרוס את 01", "redo sheet 01", "re-do sheet 01",
    "דרוס את 01", "החלף את 01", "כן, תחליפי", "אני רוצה שתשרטט מחדש",
])
def test_a_short_clear_replace_is_granted(msg):
    assert _rep(msg) == "", msg


def test_place_and_route_short_clear_replace_is_granted():
    assert serve._consent("place", {"student_said": "תמקם מחדש את הרכיבים", "replace": True}, "תמקם מחדש את הרכיבים") == ""
    assert serve._consent("route", {"student_said": "re-route the board from scratch", "replace": True}, "re-route the board from scratch") == ""


ASKED_PLACE = "Replace the board's parts and copper? This wipes what is there (a backup is kept). Answer yes/no."
ASKED_ROUTE = "Replace the board's tracks? This wipes what is there (a backup is kept). Answer yes/no."


def test_a_bare_yes_counts_only_after_the_agent_asked_about_replacing():
    for ans in ("כן", "yes", "כן בבקשה", "yes please"):
        assert _rep(ans, "להחליף את הציור בגיליון 01? זה ימחק מה שציור שם. כן/לא?") == "", ans
        assert _rep(ans, ASKED) == "", ans
        assert _rep(ans) != "", ans                                  # nothing was asked
        assert _rep(ans, "Shall I add the LED?") != "", ans          # asked about something else


@pytest.mark.parametrize("kind,ask,other", [
    ("place", ASKED_PLACE, ASKED),
    ("place", "להחליף את הרכיבים והנחושת על הלוח? כן/לא?", ASKED_ROUTE),
    ("place", "Redo the placement?", ASKED_ROUTE),
    ("route", ASKED_ROUTE, ASKED),
    ("route", "להחליף את המסלולים על הלוח? כן/לא?", ASKED_PLACE),
    ("route", "Re-route the board?", ASKED_PLACE),
])
def test_place_and_route_short_reply_works_only_after_kind_matching_replace_question(kind, ask, other):
    for ans in ("כן", "yes", "כן בבקשה", "yes please", "כן, תחליף", "yes, replace it"):
        assert serve._consent(kind, {"student_said": ans, "replace": True}, ans, (), ask) == "", (kind, ans, ask)
        assert serve._consent(kind, {"student_said": ans, "replace": True}, ans, (), "") != "", (kind, ans)
        assert serve._consent(kind, {"student_said": ans, "replace": True}, ans, (), other) != "", (kind, ans, other)


@pytest.mark.parametrize("prev", [
    "Shall I replace R1 with a 10k resistor?",
    "You do not need to start over. Should I check stock?",
    "למחוק את גיליון 02?",
    "Will you redraw it by hand in Altium?",
    "Will you redraw sheet 01 yourself?",
    "תשרטט מחדש בעצמך?",
    "תשרטט את זה ביד?",
    "See https://example.com/?x=1 to redraw sheet 01.",
    "Check the potentiometer wiper on sheet 01?",
    "Shall I add the replacement chip?",
])
def test_unrelated_manual_or_url_questions_never_enable_bare_yes_replace(prev):
    for kind in ("draw", "place", "route"):
        assert serve._consent(kind, {"student_said": "yes", "replace": True}, "yes", (), prev) != "", (kind, prev)
        assert serve._consent(kind, {"student_said": "כן", "replace": True}, "כן", (), prev) != "", (kind, prev)


@pytest.mark.parametrize("msg", [
    "yes, add R5 to BOM", "כן, תוסיף נגד", "ok, let me check", "sure, show me the preview",
    "בסדר, תעבור ל-BOM", "thanks", "תודה", "please", "בבקשה",
])
def test_yes_with_unrelated_command_never_grants_replace(msg):
    assert _rep(msg, ASKED) != "", msg
    assert serve._consent("place", {"student_said": msg, "replace": True}, msg, (), ASKED_PLACE) != "", msg
    assert serve._consent("route", {"student_said": msg, "replace": True}, msg, (), ASKED_ROUTE) != "", msg


@pytest.mark.parametrize("msg", [
    "לא, אל תחליף", "maybe redraw", "redraw? not sure", "I don't need you to redraw", "don't overwrite", "בעצם אל", "לא לא", "redraw, no",
    "wait, overwrite it", "overwrite it, stop", "redraw only if empty", "אולי תשרטט מחדש", "redraw after the library",
    "שרטט את הסכמה, אין צורך להתחיל מחדש", "שרטט את הסכמה מבלי להחליף", "תימנע מלהתחיל מחדש", "redraw is not needed",
    # Hebrew negation prefixes, ketiv haser, and extra refusal words
    "תשרטט את הסכמה, ואל מחדש", "תשרטט מחדש, ואל", "חשוב שלא תחליף את 01", "רוצה שלא תשרטט מחדש",
    "שאל תחליף", "שאין צורך מחדש", "שבלי להחליף", "שמבלי להחליף", "שללא מחדש", "שאסור להחליף",
    "תמנע מלשרטט מחדש", "להימנע מלשרטט מחדש", "להמנע מלשרטט מחדש", "נמנע מלהחליף", "הימנע מלהחליף", "תימנעי מלהחליף",
    "מיותר לשרטט מחדש", "חבל לשרטט מחדש", "איני רוצה להחליף", "אינני רוצה להחליף", "אינו מחליף", "אינה מחליפה",
    "ורגע, תשרטט מחדש", "ואם תשרטט מחדש", "ורק תשרטט מחדש", "שאם תחליף", "במידה ותחליף", "לאחר מכן תחליף",
    # Reversal / keep / preserve / abort
    "Redraw the schematic. Keep what is there.", "Redraw the schematic. Scratch that.",
    "Redraw the schematic. On second thought, keep it.", "תשרטט מחדש את הסכמה. תשאיר את מה שיש.",
    "Redraw it. Forget it.", "Redraw it. Skip it.", "Redraw it. Leave it.",
    "תשרטט מחדש. תוותר.", "תשרטט מחדש. תשכח מזה.", "תשרטט מחדש. בעצם תשאיר.",
    "redraw it, preserve old", "redraw it, retain old", "redraw it, save copy", "redraw it, back up",
    "redraw it, abort", "redraw it, pause", "hang on, redraw it", "changed my mind, redraw",
    "actually redraw it", "redraw it instead", "rather redraw it", "however redraw it",
    "redraw it though", "although redraw it", "redraw except 01", "redraw is a bad idea", "redraw is unnecessary",
    "תשרטט מחדש, שמור", "תשרטט מחדש, תשמור", "תשרטט מחדש, במקום", "עדיף לשרטט מחדש",
    "תשרטט מחדש אבל לאט", "תשרטט מחדש אך 01", "תשרטט מחדש חוץ מ-02", "תשרטט מחדש מלבד 02",
    "הפסק, תשרטט מחדש", "תפסיק, תשרטט מחדש", "תחכי, תשרטט מחדש", "תעצרי, תשרטט מחדש",
    "תבטל, תשרטט מחדש", "תבטלי, תשרטט מחדש", "עזבי, תשרטט מחדש", "תעזוב, תשרטט מחדש", "תעזבי, תשרטט מחדש",
    # English contractions / negations / nothing / none
    "won't redraw sheet 01", "can't redraw sheet 01", "wouldn't redraw sheet 01", "couldn't redraw",
    "mustn't redraw", "needn't redraw", "didn't redraw", "doesn't redraw", "isn't redraw", "aren't redraw",
    "cannot redraw sheet 01", "nah, redraw", "naw, redraw", "negative, redraw", "draw it, replace nothing", "replace none",
    # Questions without ? (sentence-start and comma-joined)
    "should we redraw sheet 01", "why redraw sheet 01", "האם להחליף את 01", "אפשר להחליף את 01",
    "draw the schematic, why replace it",
    # Hedges & conditions (English & Hebrew)
    "first redraw sheet 01", "when done redraw", "whenever redraw", "while redraw", "later redraw", "soon redraw",
    "might redraw", "may redraw", "could redraw", "would redraw", "should redraw",
    "unsure, redraw", "uncertain, redraw", "guess redraw", "suppose redraw", "wonder redraw",
    "possibly redraw", "potentially redraw", "likely redraw", "pending redraw", "assuming redraw", "provided redraw",
    "כדאי לשרטט מחדש", "תשרטט מחדש ואז", "תשרטט מחדש אז", "כשנסיים תשרטט מחדש", "כאשר נסיים תשרטט מחדש",
    "בהמשך תשרטט מחדש", "בינתיים תשרטט מחדש", "עדיין תשרטט מחדש", "כרגע תשרטט מחדש",
    "שנייה, תשרטט מחדש", "שניה, תשרטט מחדש", "מאוחר יותר תשרטט מחדש", "אחר-כך תשרטט מחדש", 'אח"כ תשרטט מחדש',
    "בתנאי שתשרטט מחדש", "תלוי, תשרטט מחדש", "בספק, תשרטט מחדש", "כנראה תשרטט מחדש",
    "יתכן ותשרטט מחדש", "ייתכן ותשרטט מחדש", "לדעתי תשרטט מחדש", "מתלבט אם להחליף", "מתלבטת להחליף",
    # Self-do replace
    "I will replace sheet 01", "I'll overwrite sheet 01", "I'll redraw sheet 01", "I want to redraw it",
    "אני אחליף את 01", "אני רוצה לשרטט מחדש", "אני אעשה את הסכמה מחדש",
    # Substring traps
    "draw it, irreplaceable part", "draw the schematic for the replacement chip", "draw with freedom",
])
def test_a_short_negated_hedged_conditional_or_stopped_message_never_grants_replace(msg):
    assert _rep(msg) != "", msg


def test_place_and_route_substring_and_self_do_traps_stay_refused():
    for msg in ("place preplaced parts", "place the replacement parts on the board", "place the parts with freedom"):
        assert serve._consent("place", {"student_said": msg, "replace": True}, msg) != "", msg
    assert serve._consent("route", {"student_said": "I'll re-route the board", "replace": True}, "I'll re-route the board") != ""


@pytest.mark.parametrize("msg", [
    "שרטט את 01 ו-02 ואל תמחק כלום", "שרטט את הסכמה ותחליף את כל מה שיש שם ואז נמשיך הלאה לשלב הבא",
    "לא צריך לשרטט את 01 ו-02 מחדש", "draw the schematic and overwrite it. don't do it", "redraw the schematic and then we move to the PCB",
    "replace the schematic in Altium, I don't need the old one", "I think it is a good idea to redraw the whole schematic now please",
    "תצייר את הסכמה אבל אל תמחק את מה שיש", "draw it but don't replace anything",
])
def test_earlier_round_long_or_negated_messages_stay_refused(msg):
    assert _rep(msg) != "", msg


def test_a_long_clear_replace_message_is_refused_and_the_text_asks_a_yes_no_question():
    msg = "תשרטט את הסכמה כולה מחדש בבקשה עכשיו ותודה רבה על העזרה"
    why = _rep(msg)
    assert "The sheet is only wiped" in why and "yes/no" in why and "sheet 01" in why and "wipes" in why
    assert "The board's parts and copper are only wiped" in serve._replace_consent("place", {}, "nope")
    assert "The board's tracks are only wiped" in serve._replace_consent("route", {}, "nope")


def test_an_earlier_message_never_grants_replace():
    msg = "תצייר את הסכמה"
    earlier = ["שרטט מחדש"]
    assert serve._draw_consent({"student_said": msg, "replace": True}, msg, earlier) != ""


def test_the_previous_agent_text_is_found_before_the_current_message():
    chat = [{"role": "agent", "text": ASKED}, {"role": "user", "text": "yes"}]
    assert serve.previous_agent_text(chat, "yes") == ASKED
    assert serve.previous_agent_text([{"role": "agent", "text": ASKED}, {"role": "user", "text": " yes \n"}], "yes") == ASKED
    assert serve.previous_agent_text([{"role": "user", "text": "yes"}], "yes") == ""
    # Strips server-appended refusal notes so a refused replace never masquerades as the agent asking yes/no
    with_refusal = {"role": "agent", "text": f"Drawing now.\n\n(Not applied: {ASKED})"}
    assert serve.previous_agent_text([with_refusal, {"role": "user", "text": "yes"}], "yes") == "Drawing now."
    only_refusal = {"role": "agent", "text": f"(Not applied: {ASKED})"}
    assert serve.previous_agent_text([only_refusal, {"role": "user", "text": "yes"}], "yes") == ""
    # Skips error records and stops at unanswered generated user prompts
    err_chat = [{"role": "user", "text": "draw"}, {"role": "agent", "text": ASKED, "error": True}, {"role": "user", "text": "yes"}]
    assert serve.previous_agent_text(err_chat, "yes") == ""
    gen_chat = [{"role": "agent", "text": ASKED}, {"role": "user", "text": "List findings", "generated": True}, {"role": "user", "text": "yes"}]
    assert serve.previous_agent_text(gen_chat, "yes") == ""


def test_place_and_route_replace_yes_works_end_to_end_via_apply_actions(empty, monkeypatch):
    placed, routed = [], []
    monkeypatch.setattr(bridge, "place_pcb", lambda p, replace=False: placed.append(replace) or {"placed": ["U1"], "outline_created": False, "warnings": []})
    monkeypatch.setattr(bridge, "route_pcb", lambda p, replace=False, keep_partial=False: routed.append(replace) or {"summary": "ok", "warnings": []})
    applied, _, refused = serve.apply_actions(
        empty, [{"type": "altium.place_pcb", "student_said": "כן", "replace": True}],
        last_user="כן", chat=[A(ASKED_PLACE), U("כן")],
    )
    assert applied and not refused and placed == [True]
    applied, _, refused = serve.apply_actions(
        empty, [{"type": "altium.route_pcb", "student_said": "yes, replace it", "replace": True}],
        last_user="yes, replace it", chat=[A(ASKED_ROUTE), U("yes, replace it")],
    )
    assert applied and not refused and routed == [True]


def test_the_too_short_quote_refusal_names_the_fix():
    msg = "תודה על הרשימה. תצייר את הסכמה באלטיום בבקשה, ואחר כך נמשיך הלאה לשלב הבא של הפרויקט"
    why = serve._draw_consent({"student_said": "תצייר את הסכמה באלטיום"}, msg)
    assert why and "student_said" in why and "WHOLE message" in why
