"""The Draw / Place / Route buttons: the click is the consent. The server endpoints call the bridge, say the same sentence the chat path
says, flag "already there" so the page can offer Replace, refuse a second Altium step at the same time, and leave a note the agent reads.
The bridge is faked: nothing here touches Altium."""
import pathlib
import threading

import pytest

import serve
import session as session_mod
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
DRAWN = {"parts": 3, "nets": ["GND", "VCC"], "sheets": ["a.SchDoc"], "warnings": ["w1"], "problems": [], "backup": "", "created": []}
PLACED = {"placed": ["R1", "C1"], "outline": [0, 0, 1, 1], "outline_created": True, "warnings": ["w2", "w3"], "backup": "", "problems": []}
ROUTED = {"summary": "4 nets routed with 9 tracks and 1 vias, saved", "warnings": [], "routed": [], "failed": []}
ENDPOINTS = {"draw": "/api/altium/draw-schematic", "place": "/api/altium/place", "route": "/api/altium/route"}
BRIDGE_FN = {"draw": "draw_schematic", "place": "place_pcb", "route": "route_pcb"}


@pytest.fixture
def spy(monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, sheet=None, replace=False: seen.append(("draw", sheet, replace)) or dict(DRAWN))
    monkeypatch.setattr(bridge, "place_pcb", lambda p, replace=False: seen.append(("place", replace)) or dict(PLACED))
    monkeypatch.setattr(bridge, "route_pcb", lambda p, replace=False, keep_partial=False: seen.append(("route", replace, keep_partial)) or dict(ROUTED))
    return seen


def test_each_endpoint_calls_its_bridge_function_with_replace_only_when_asked(server, empty, spy):
    assert call(server, "POST", ENDPOINTS["draw"], empty, {})[0] == 200
    assert call(server, "POST", ENDPOINTS["draw"], empty, {"sheet": "1", "replace": True})[0] == 200
    assert call(server, "POST", ENDPOINTS["place"], empty, {})[0] == 200
    assert call(server, "POST", ENDPOINTS["place"], empty, {"replace": True})[0] == 200
    assert call(server, "POST", ENDPOINTS["route"], empty, {})[0] == 200
    assert call(server, "POST", ENDPOINTS["route"], empty, {"replace": True, "keep_partial": True})[0] == 200
    # keep_partial in the body is ignored: half a route stays only by consent in words, in the chat
    assert spy == [("draw", None, False), ("draw", "1", True), ("place", False), ("place", True), ("route", False, False), ("route", True, False)]


def test_the_summary_is_the_sentence_the_chat_path_writes(server, empty, spy):
    for step, res in (("draw", DRAWN), ("place", PLACED), ("route", ROUTED)):
        code, body = call(server, "POST", ENDPOINTS[step], empty, {})
        assert code == 200 and body["summary"] == serve.STEP_SUMMARY[step](res)
        assert body["warnings"] == res["warnings"]
    assert serve.draw_summary(DRAWN) == "3 parts and 2 nets drawn on 1 sheet(s), saved and checked against the netlist (1 warnings: w1)"
    assert serve.place_summary(PLACED) == "2 parts placed, outline created, saved and checked against the netlist (2 warnings: w2; w3)"
    # the chat path builds its text from the same helpers
    said = "תצייר אתה את הסכמה באלטיום"
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.draw_schematic", "student_said": said}], last_user=said,
                                              chat=[{"role": "user", "text": said}])
    assert applied == ["altium.draw_schematic: " + serve.draw_summary(DRAWN)] and not refused


@pytest.mark.parametrize("step", ["draw", "place", "route"])
def test_a_bridge_error_is_a_400_and_not_flagged_as_needs_replace(server, empty, monkeypatch, step):
    def boom(*a, **k):
        raise bridge.BridgeError("The project library is not built yet")
    monkeypatch.setattr(bridge, BRIDGE_FN[step], boom)
    code, body = call(server, "POST", ENDPOINTS[step], empty, {})
    assert code == 400 and body == {"error": "The project library is not built yet"}


@pytest.mark.parametrize("step,msg", [
    ("draw", "Sheet1.SchDoc already has 12 objects (parts, wires, labels). I never wipe a drawing: say so if it should be redrawn (replace), the old file is kept in .advisor-backup."),
    ("place", "Altium refused a step: the board already has 4 parts or copper objects; nothing was changed (last step: pcbcheck)"),
    ("route", "Altium refused a step: the board already has 7 tracks, vias or pours; nothing was changed (last step: pcbcheck)"),
])
def test_an_existing_result_is_flagged_so_the_page_can_offer_replace(server, empty, monkeypatch, step, msg):
    def refuse(*a, **k):
        raise bridge.BridgeError(msg)
    monkeypatch.setattr(bridge, BRIDGE_FN[step], refuse)
    code, body = call(server, "POST", ENDPOINTS[step], empty, {})
    assert code == 400 and body["needs_replace"] is True and body["error"] == msg
    code, body = call(server, "POST", ENDPOINTS[step], empty, {"replace": True})       # replace was on: this is not the "already there" case
    assert code == 400 and "needs_replace" not in body


def test_needs_replace_detection_matches_the_wording_in_the_bridge_sources():
    """The refusal has no code, only a message: pin the pieces of it in bridge.py and AdvisorBridge.pas, so a reworded refusal fails here."""
    py = (REPO / "scripts" / "altium" / "bridge.py").read_text(encoding="utf-8")
    pas = (REPO / "scripts" / "altium" / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    assert "already has {have} objects (parts, wires, labels)" in py
    assert "'ERR the sheet already has ' + IntToStr(n) + ' objects (parts, wires, labels)" in pas
    assert "'ERR the board already has ' + IntToStr(n) + ' tracks, vias or pours; nothing was changed'" in pas
    assert "'ERR the board already has ' + IntToStr(n) + ' parts or copper objects; nothing was changed'" in pas
    assert serve.needs_replace(bridge.BridgeError("Altium refused a step: the board already has 3 parts or copper objects; nothing was changed (last step: x)"))
    assert serve.needs_replace(bridge.BridgeError("Altium refused a step: the sheet already has 9 objects (parts, wires, labels); nothing was changed (last step: x)"))
    assert not serve.needs_replace(bridge.BridgeError("There are no parts on the board: place the parts first (altium.place_pcb)."))


def test_a_step_that_is_running_blocks_a_second_one(server, empty, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(p, replace=False):
        started.set()
        release.wait(10)
        return dict(PLACED)
    monkeypatch.setattr(bridge, "place_pcb", slow)
    monkeypatch.setattr(bridge, "route_pcb", lambda *a, **k: pytest.fail("a second Altium step must not start"))
    first = {}
    t = threading.Thread(target=lambda: first.update(r=call(server, "POST", ENDPOINTS["place"], empty, {})), daemon=True)
    t.start()
    assert started.wait(5)
    code, body = call(server, "POST", ENDPOINTS["route"], empty, {})
    assert code == 409 and body["error"] == serve.ALTIUM_BUSY
    release.set()
    t.join(10)
    assert first["r"][0] == 200
    assert call(server, "POST", ENDPOINTS["place"], empty, {})[0] == 200          # the lock is free again


def test_a_chat_turn_in_flight_for_the_project_blocks_the_button(server, empty, spy):
    with serve.TURNS_LOCK:
        serve.TURNS[(empty, "s1")] = {}
    try:
        code, body = call(server, "POST", ENDPOINTS["draw"], empty, {})
    finally:
        with serve.TURNS_LOCK:
            serve.TURNS.pop((empty, "s1"), None)
    assert code == 409 and "chat is still answering" in body["error"] and spy == []


def test_the_agent_finds_a_note_in_the_conversation_after_a_button_step(server, empty, spy):
    code, body = call(server, "POST", ENDPOINTS["place"], empty, {})
    assert code == 200
    notes = [m for m in session_mod.load_chat(empty, session_mod.current(empty, None)) if m.get("by") == "button"]
    assert len(notes) == 1 and notes[0]["role"] == "agent"
    assert "Placed the parts in Altium because the student pressed the button" in notes[0]["text"]
    assert serve.place_summary(PLACED) in notes[0]["text"]


def test_a_failed_button_step_leaves_no_note(server, empty, monkeypatch):
    def boom(*a, **k):
        raise bridge.BridgeError("nope")
    monkeypatch.setattr(bridge, "route_pcb", boom)
    call(server, "POST", ENDPOINTS["route"], empty, {})
    assert not [m for m in session_mod.load_chat(empty, session_mod.current(empty, None)) if m.get("by") == "button"]


def test_the_chat_path_still_refuses_without_consent_words(empty, spy):
    for kind in ("altium.draw_schematic", "altium.place_pcb", "altium.route_pcb"):
        applied, _, refused = serve.apply_actions(empty, [{"type": kind}], last_user="המשך", chat=[{"role": "user", "text": "המשך"}])
        assert not applied and refused and "not run" in refused[0]
    assert spy == []


# ---- the page: the three buttons and their handler, in the shared UI source

def test_the_pages_have_the_buttons_and_hit_the_endpoints():
    js = ui_js()
    for url in ENDPOINTS.values():
        assert f"url: '{url}'" in js
    assert "pvStepBtn('draw')" in js and "pvStepBtn('place')" in js and "pvStepBtn('route')" in js
    assert "onAct('altium-step'" in js and "act: 'altium-step'" in js
    for label in ("Draw in Altium", "Place parts", "Route board", "Replace the existing drawing", "Replace the existing placement",
                  "Replace the existing routes"):
        assert f"'{label}'" in js
    assert "ALTIUM_DATA.linked.project_file" in js[js.index("function pvAltiumLinked"):js.index("function pvStepBtn")]     # only when linked
    run = js[js.index("async function pvRunStep"):js.index("onAct('altium-step'")]
    assert "r.needs_replace" in run and "replace: !!replace" in run and "r.summary" in run and "r.warnings" in run
    assert "confirm(" not in run and "alert(" not in run
    # replace is sent only by the Replace button of the note, never by the header button
    assert "replace(/^Altium refused a step: /, '')" in run and "nothing was changed" in run      # the note drops the script's step log
    assert "refresh(true)" in run and "loadAltium(true)" in run and "Lost contact with the server" in run
    assert "pvRunStep(d.step, d.replace === '1')" in js
    header = js[js.index("function pvStepBtn"):js.index("function pvStepNote")]
    assert "replace" not in header
    note = js[js.index("function pvStepNote"):js.index("async function pvRunStep")]
    assert "replace: '1'" in note and "'Keep it'" in note and "pvStepNote('sch')" in js and "pvStepNote('pcb')" in js
    assert "loadingLine(PV_STEPS[pvBusy].busy)" in note            # the working line stays while Altium runs
    assert "disabled: pvBusy ? true : undefined" in header         # no second step while one runs


def test_a_chat_action_does_not_start_in_altium_while_a_button_step_runs(empty, spy):
    said = "תצייר אתה את הסכמה באלטיום"
    assert serve.STEP_LOCK.acquire(blocking=False)
    try:
        applied, _, refused = serve.apply_actions(empty, [{"type": "altium.draw_schematic", "student_said": said}], last_user=said,
                                                  chat=[{"role": "user", "text": said}])
    finally:
        serve.STEP_LOCK.release()
    assert not applied and "still running in Altium" in refused[0] and spy == []


# ---- one Altium operation at a time, whoever starts it

def test_an_unexpected_error_is_an_answer_and_frees_the_lock(server, empty, monkeypatch):
    def bug(*a, **k):
        raise KeyError("net_width")
    monkeypatch.setattr(bridge, "place_pcb", bug)
    code, body = call(server, "POST", ENDPOINTS["place"], empty, {})
    assert code == 500 and "unexpected error" in body["error"] and "KeyError" in body["error"]
    assert not serve.STEP_LOCK.locked()


def test_a_note_that_cannot_be_written_does_not_turn_a_done_step_into_a_failure(server, empty, spy, monkeypatch):
    def full(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(serve, "say", full)
    code, body = call(server, "POST", ENDPOINTS["place"], empty, {})
    assert code == 200 and body["summary"] == serve.place_summary(PLACED)


def test_the_chat_does_not_start_a_turn_while_a_step_runs(server, empty, monkeypatch):
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: pytest.fail("no turn may start while Altium works on a step"))
    assert serve.STEP_LOCK.acquire(blocking=False)
    try:
        code, body = call(server, "POST", "/api/chat", empty, {"text": "מה המצב?"})
    finally:
        serve.STEP_LOCK.release()
    assert code == 409 and "Altium is busy" in body["error"]
    assert not [m for m in session_mod.load_chat(empty, session_mod.current(empty, None)) if m.get("role") == "user"]     # not stored: it is sent again


@pytest.mark.parametrize("path,fn", [("/api/altium/import-rules", "import_rules"), ("/api/altium/run-outjob", "run_outjob"),
                                     ("/api/library/build", "build_library"), ("/api/altium/create", "create")])
def test_the_other_altium_buttons_wait_for_a_running_step(server, empty, monkeypatch, path, fn):
    monkeypatch.setattr(bridge, fn, lambda *a, **k: pytest.fail("a second Altium operation must not start"))
    monkeypatch.setattr(serve.store, "manufacturing_block", lambda p: "")
    assert serve.STEP_LOCK.acquire(blocking=False)
    try:
        code, body = call(server, "POST", path, empty, {})
    finally:
        serve.STEP_LOCK.release()
    assert code == 409 and body["error"] == serve.ALTIUM_BUSY


def test_the_other_altium_buttons_free_the_lock_when_they_fail(server, empty, monkeypatch):
    def boom(*a, **k):
        raise bridge.BridgeError("nope")
    monkeypatch.setattr(bridge, "import_rules", boom)
    assert call(server, "POST", "/api/altium/import-rules", empty, {})[0] == 400
    assert not serve.STEP_LOCK.locked()


def test_a_chat_turn_holds_the_lock_while_its_altium_action_runs_and_frees_it(empty, monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, sheet=None, replace=False: seen.append(serve.STEP_LOCK.locked()) or dict(DRAWN))
    said = "תצייר אתה את הסכמה באלטיום"
    applied, _, refused = serve.apply_actions(empty, [{"type": "altium.draw_schematic", "student_said": said}], last_user=said,
                                              chat=[{"role": "user", "text": said}])
    assert applied and not refused and seen == [True] and not serve.STEP_LOCK.locked()
    serve.apply_actions(empty, [{"type": "idea.ready"}])              # nothing for Altium: the lock is not taken
    assert not serve.STEP_LOCK.locked()


def test_a_button_step_uses_up_consent_given_in_words_before_it(server, empty, spy):
    """The student asked in words for a redraw that did not happen, then drew with the button: the old sentence is no licence to wipe
    what the button drew."""
    old = "תצייר אתה את הסכמה באלטיום מחדש"
    chat = [{"role": "user", "text": old}, {"role": "agent", "text": "The library is not built yet."}]
    assert serve.earlier_student_messages(chat, "draw", "תודה") == [old]
    assert call(server, "POST", ENDPOINTS["draw"], empty, {})[0] == 200
    note = [m for m in session_mod.load_chat(empty, session_mod.current(empty, None)) if m.get("by") == "button"][0]
    assert note["applied"] == ["altium.draw_schematic: " + serve.draw_summary(DRAWN)]
    assert serve.earlier_student_messages(chat + [note, {"role": "user", "text": "תודה"}], "draw", "תודה") == []


def test_the_note_of_a_step_with_warnings_is_marked_warned_like_the_chat_result(server, empty, spy):
    assert call(server, "POST", ENDPOINTS["place"], empty, {})[0] == 200           # PLACED carries two warnings
    assert call(server, "POST", ENDPOINTS["route"], empty, {})[0] == 200           # ROUTED carries none
    notes = [m for m in session_mod.load_chat(empty, session_mod.current(empty, None)) if m.get("by") == "button"]
    assert notes[0]["warned"] == serve.warned_map(notes[0]["applied"]) and list(notes[0]["warned"].values()) == ["w2; w3"]
    assert "warned" not in notes[1]


@pytest.mark.parametrize("path,fn", [("/api/altium/import-rules", "import_rules"), ("/api/altium/run-outjob", "run_outjob"),
                                     ("/api/library/build", "build_library"), ("/api/altium/create", "create")])
def test_the_other_altium_buttons_wait_for_a_chat_turn_of_the_project(server, empty, monkeypatch, path, fn):
    monkeypatch.setattr(bridge, fn, lambda *a, **k: pytest.fail("no Altium operation may start while the chat answers"))
    monkeypatch.setattr(serve.store, "manufacturing_block", lambda p: "")
    with serve.TURNS_LOCK:
        serve.TURNS[(empty, "s1")] = {}
    try:
        code, body = call(server, "POST", path, empty, {})
    finally:
        with serve.TURNS_LOCK:
            serve.TURNS.pop((empty, "s1"), None)
    assert code == 409 and "chat is still answering" in body["error"] and not serve.STEP_LOCK.locked()


def test_a_chat_turn_is_registered_before_anything_slow_and_a_step_button_waits_for_it(server, empty, spy, monkeypatch):
    """The turn is in TURNS from the moment the checks pass (not only when the engine starts), so a button clicked while the
    message is being prepared is refused; a failure while preparing takes the turn out again."""
    seen = {}

    def build(*a, **k):
        seen["registered"] = any(k2[0] == empty for k2 in serve.TURNS)
        seen["button"] = serve.run_step_button(empty, None, "place", {})[0]
        raise RuntimeError("stop here")
    monkeypatch.setattr(serve.model, "build", build)
    try:
        call(server, "POST", "/api/chat", empty, {"text": "hello"})
    except Exception:
        pass                      # the handler lets the error go: the connection drops
    assert seen == {"registered": True, "button": 409} and spy == []
    assert not [k for k in serve.TURNS if k[0] == empty]
