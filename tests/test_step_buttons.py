"""The Draw / Place / Route buttons: the click is the consent. The server endpoints call the bridge, say the same sentence the chat path
says, flag "already there" so the page can offer Replace, refuse a second Altium step at the same time, and leave a note the agent reads.
The bridge is faked: nothing here touches Altium."""
import pathlib
import threading
import time

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
    # keep_partial in the body is the click of "Route the rest and leave X open": it is the consent (the chat path asks for words)
    assert spy == [("draw", None, False), ("draw", "1", True), ("place", False), ("place", True), ("route", False, False), ("route", True, True)]


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
    assert "pvRunStep(d.step, d.replace === '1', d.partial === '1')" in js
    header = js[js.index("function pvStepBtn"):js.index("function pvStepNote")]
    assert "replace" not in header
    note = js[js.index("function pvStepNote"):js.index("async function pvRunStep")]
    assert "replace: '1'" in note and "'Keep it'" in note and "pvStepNote('sch')" in js and "pvStepNote('pcb')" in js
    assert "loadingLine(PV_STEPS[pvBusy].busy)" in note            # the working line stays while Altium runs
    assert "disabled: pvBusy || o.disabled ? true : undefined" in header         # no second step while one runs


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
    monkeypatch.setattr(serve.store, "manufacturing_warning", lambda p: "")
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
    for _ in range(100):      # the handler frees the lock just after it has sent the answer
        if not serve.STEP_LOCK.locked():
            break
        time.sleep(0.02)
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
    monkeypatch.setattr(serve.store, "manufacturing_warning", lambda p: "")
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


# ---- preparations: a button runs by itself what its step needs first (library build, add PcbDoc, import rules)

BUILT = {"built": 7, "lines": 7, "notices": []}
IMPORTED = {"created": ["A", "B"], "updated": ["C"], "skipped": [], "unconfirmed": [], "message": ""}
LIB_SENTENCE = "library.build: 7 of 7 lines built, IntLib installed"
RULES_SENTENCE = "altium.import_rules: 2 added, 1 updated"


def button_notes(project):
    return [m for m in session_mod.load_chat(project, session_mod.current(project, None)) if m.get("by") == "button"]


@pytest.fixture
def world(monkeypatch, tmp_path, spy):
    """The file checks the plan reads, and fake bridge calls that record the order, the replace they got and whether STEP_LOCK was held."""
    w = {"schlib": True, "stale": False, "pcb": True, "rules": [], "log": [], "fail": {}}
    schlib = tmp_path / "L.SchLib"
    monkeypatch.setattr(bridge, "library_paths", lambda p: {"schlib": schlib, "pcblib": schlib})
    monkeypatch.setattr(bridge, "library_stale", lambda p: w["stale"])        # true after almost every edit: never a reason to rebuild
    monkeypatch.setattr(bridge, "read_prjpcb", lambda prj: {"pcbs": ["P.PcbDoc"] if w["pcb"] else []})
    monkeypatch.setattr(bridge, "_linked", lambda p: tmp_path / "P.PrjPcb")

    def project_pcb(p):
        if not w["pcb"]:
            raise bridge.BridgeError("The linked Altium project has no PcbDoc yet. Add one first (add-pcb).")
        return tmp_path / "P.PcbDoc"
    monkeypatch.setattr(bridge, "_project_pcb", project_pcb)
    monkeypatch.setattr(bridge, "rules_missing", lambda p: w["rules"])
    monkeypatch.setattr(bridge, "rules_never_imported", lambda p: bool(w["rules"]) and not w.get("some_rules"))

    def fake(name, res):
        def f(project, *a, **k):
            w["log"].append((name, serve.STEP_LOCK.locked(), k.get("replace")))
            if name in w["fail"]:
                raise bridge.BridgeError(w["fail"][name])
            return dict(res)
        monkeypatch.setattr(bridge, name, f)
    fake("build_library", BUILT)
    fake("add_pcb", {"file": str(tmp_path / "P.PcbDoc"), "backup": ""})
    fake("import_rules", IMPORTED)
    for name, res in (("draw_schematic", DRAWN), ("place_pcb", PLACED), ("route_pcb", ROUTED)):
        fake(name, res)

    def sync():                       # the SchLib file the plan looks for
        if w["schlib"]:
            schlib.write_text("x")
        elif schlib.exists():
            schlib.unlink()
    w["sync"] = sync
    sync()
    return w


def ran(w):
    return [n for n, _, _ in w["log"]]


@pytest.mark.parametrize("step,setup,expected", [
    ("draw", {}, ["draw_schematic"]),
    ("draw", {"schlib": False}, ["build_library", "draw_schematic"]),
    ("draw", {"stale": True}, ["draw_schematic"]),                       # a library that is only older than the BOM is not rebuilt
    ("place", {}, ["place_pcb"]),
    ("place", {"stale": True, "pcb": False}, ["add_pcb", "place_pcb"]),
    ("place", {"schlib": False, "pcb": False}, ["build_library", "add_pcb", "place_pcb"]),
    ("route", {"rules": ["X"], "some_rules": True}, ["route_pcb"]),       # imported before, one rule missing: the student's edit stays
    ("place", {"pcb": False}, ["add_pcb", "place_pcb"]),
    ("place", {"schlib": False}, ["build_library", "place_pcb"]),
    ("route", {}, ["route_pcb"]),
    ("route", {"rules": ["X"]}, ["import_rules", "route_pcb"]),
    ("route", {"stale": True, "schlib": False, "pcb": False}, ["route_pcb"]),     # routing prepares only the rules, nothing else
])
def test_the_plan_runs_only_the_needed_preparations_in_order(server, empty, world, step, setup, expected):
    world.update(setup)
    world["sync"]()
    assert call(server, "POST", ENDPOINTS[step], empty, {})[0] == 200
    assert ran(world) == expected


def test_drawing_is_not_a_preparation_for_place_nor_placing_for_route(empty, world):
    world.update(schlib=False, pcb=False, rules=["X"])
    world["sync"]()
    assert serve.step_plan(empty, "place") == ["library.build", "altium.add_pcb"]
    assert serve.step_plan(empty, "route") == ["altium.import_rules"]


def test_a_planning_check_that_raises_plans_nothing(empty, monkeypatch):
    def boom(*a, **k):
        raise bridge.BridgeError("The project is not linked")
    monkeypatch.setattr(bridge, "library_paths", boom)
    monkeypatch.setattr(bridge, "_linked", boom)
    monkeypatch.setattr(bridge, "rules_missing", lambda p: (_ for _ in ()).throw(RuntimeError("x")))
    assert [serve.step_plan(empty, s) for s in ("draw", "place", "route")] == [[], [], []]


def test_preparations_never_replace_and_the_step_does(server, empty, world):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    assert call(server, "POST", ENDPOINTS["place"], empty, {"replace": True})[0] == 200
    assert world["log"] == [("build_library", True, None), ("add_pcb", True, None), ("place_pcb", True, True)]
    world["log"].clear()
    world.update(rules=["X"])
    assert call(server, "POST", ENDPOINTS["route"], empty, {"replace": True})[0] == 200
    assert world["log"] == [("import_rules", True, None), ("route_pcb", True, True)]


def test_the_lock_is_held_from_the_first_preparation_to_the_end_and_freed(server, empty, world):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    assert call(server, "POST", ENDPOINTS["place"], empty, {})[0] == 200
    assert [held for _, held, _ in world["log"]] == [True, True, True] and not serve.STEP_LOCK.locked()


def test_the_answer_lists_what_was_prepared_with_the_chat_sentences(server, empty, world):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    code, body = call(server, "POST", ENDPOINTS["place"], empty, {})
    assert code == 200 and body["summary"] == serve.place_summary(PLACED) and body["warnings"] == PLACED["warnings"]
    assert body["prepared"] == [LIB_SENTENCE, "altium.add_pcb"]
    world.update(rules=["X"])
    assert call(server, "POST", ENDPOINTS["route"], empty, {})[1]["prepared"] == [RULES_SENTENCE]
    world.update(schlib=True)
    world["sync"]()
    assert "prepared" not in call(server, "POST", ENDPOINTS["draw"], empty, {})[1]          # nothing was needed: the answer is as before
    assert serve.library_build_summary(empty, BUILT) == "7 of 7 lines built, IntLib installed"
    assert serve.import_rules_summary({**IMPORTED, "skipped": [{"name": "S"}], "unconfirmed": ["U"], "message": "m"}) == \
        "2 added, 1 updated, 1 skipped (S), not confirmed: U. m"


def test_the_chat_path_says_the_same_sentences_for_library_and_rules(empty, world):
    applied, _, refused = serve.apply_actions(empty, [{"type": "library.build"}, {"type": "altium.import_rules"}])
    assert applied == [LIB_SENTENCE, RULES_SENTENCE] and not refused


def test_the_note_carries_the_preparations_then_the_step_and_marks_warnings(server, empty, world):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    assert call(server, "POST", ENDPOINTS["place"], empty, {})[0] == 200
    note = button_notes(empty)[0]
    assert note["applied"] == [LIB_SENTENCE, "altium.add_pcb", "altium.place_pcb: " + serve.place_summary(PLACED)]
    assert note["warned"] == serve.warned_map(note["applied"]) and list(note["warned"].values()) == ["w2; w3"]
    assert note["text"].startswith("Placed the parts in Altium after building the library and adding a PcbDoc because the student pressed the button: ")


@pytest.mark.parametrize("step,setup,fail,done,error", [
    ("place", {"schlib": False, "pcb": False}, "build_library", [], "Building the library failed: boom. The parts were not placed."),
    ("place", {"schlib": False, "pcb": False}, "add_pcb", ["build_library"], "The library was built. Adding the PcbDoc failed: boom. The parts were not placed."),
    ("route", {"rules": ["X"]}, "import_rules", [], "Importing the JLC rules failed: boom. The board was not routed."),
    ("draw", {"schlib": False}, "build_library", [], "Building the library failed: boom. The schematic was not drawn."),
])
def test_a_failing_preparation_stops_the_chain(server, empty, world, step, setup, fail, done, error):
    world.update(setup)
    world["sync"]()
    world["fail"][fail] = "boom. "
    code, body = call(server, "POST", ENDPOINTS[step], empty, {"replace": True})
    assert code == 400 and "needs_replace" not in body and body["error"] == error
    assert ran(world) == done + [fail] and not serve.STEP_LOCK.locked()          # the later steps never ran
    notes = button_notes(empty)
    if done:
        assert len(notes) == 1 and notes[0]["applied"] == [LIB_SENTENCE] and "building the library" in notes[0]["text"]
    else:
        assert not notes


def test_a_preparation_refusal_that_looks_like_already_there_is_not_needs_replace(server, empty, world):
    world["rules"] = ["X"]
    world["fail"]["import_rules"] = "the board already has 7 tracks, vias or pours; nothing was changed"
    code, body = call(server, "POST", ENDPOINTS["route"], empty, {})
    assert code == 400 and "needs_replace" not in body


def test_a_step_failing_after_preparations_keeps_its_own_error_and_notes_the_preparations(server, empty, world):
    world.update(schlib=False)
    world["sync"]()
    refusal = "the board already has 4 parts or copper objects; nothing was changed (last step: pcbcheck)"
    world["fail"]["place_pcb"] = refusal
    code, body = call(server, "POST", ENDPOINTS["place"], empty, {})
    assert code == 400 and body["error"] == refusal and body["needs_replace"] is True
    assert body["prepared"] == [LIB_SENTENCE] and body["done_first"] == "The library was built."
    note = button_notes(empty)[0]
    assert note["applied"] == [LIB_SENTENCE] and "place_pcb" not in " ".join(note["applied"])


def test_an_unexpected_error_in_a_preparation_is_a_500_and_frees_the_lock(server, empty, world, monkeypatch):
    world["rules"] = ["X"]
    monkeypatch.setattr(bridge, "import_rules", lambda *a, **k: (_ for _ in ()).throw(KeyError("k")))
    code, body = call(server, "POST", ENDPOINTS["route"], empty, {})
    assert code == 500 and "Importing the JLC rules failed" in body["error"] and "KeyError" in body["error"] and not serve.STEP_LOCK.locked()


def test_step_status_shows_the_live_list_then_the_result_once(server, empty, world, monkeypatch):
    assert call(server, "GET", "/api/altium/step-status", empty)[1] == {"running": False}
    started, release = threading.Event(), threading.Event()

    def slow(p, *a, **k):
        started.set()
        release.wait(10)
        return dict(IMPORTED)
    monkeypatch.setattr(bridge, "import_rules", slow)
    world["rules"] = ["X"]
    first = {}
    t = threading.Thread(target=lambda: first.update(r=call(server, "POST", ENDPOINTS["route"], empty, {})), daemon=True)
    t.start()
    assert started.wait(5)
    st = call(server, "GET", "/api/altium/step-status", empty)[1]
    assert st["running"] is True and st["step"] == "route"
    assert [(x["key"], x["state"]) for x in st["steps"]] == [("altium.import_rules", "running"), ("altium.route_pcb", "waiting")]
    assert [x["label"] for x in st["steps"]] == ["Importing the JLC rules", "Routing the board"]
    assert call(server, "GET", "/api/altium/step-status?take=1", empty)[1]["running"] is True       # take never clears a run in progress
    release.set()
    t.join(10)
    assert first["r"][0] == 200
    assert call(server, "GET", "/api/altium/step-status", empty)[1] == {"running": False}           # delivered with the POST answer: gone


def test_a_finished_run_is_read_once_by_a_page_that_missed_the_answer_and_never_reaches_the_next_run(empty, world):
    code, body, _ = serve.run_step_button(empty, None, "route", {})              # in process: the answer is never "delivered" over HTTP
    assert code == 200
    st = serve.step_status(empty)
    assert st["running"] is False and st["summary"] == body["summary"] and [x["state"] for x in st["steps"]] == ["done"]
    assert serve.step_status(empty, take=True)["summary"] == body["summary"]
    assert serve.step_status(empty) == {"running": False}
    world["fail"]["route_pcb"] = "nope"
    serve.run_step_button(empty, None, "route", {})
    assert serve.step_status(empty)["error"] == "nope"
    world["fail"].clear()
    world["rules"] = ["X"]
    serve.run_step_button(empty, None, "route", {})                            # the next run replaces the old record
    st = serve.step_status(empty)
    assert "error" not in st and [x["key"] for x in st["steps"]] == ["altium.import_rules", "altium.route_pcb"]


def test_a_failed_run_marks_the_failed_step_and_skips_the_rest(empty, world):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    world["fail"]["add_pcb"] = "no"
    assert serve.run_step_button(empty, None, "place", {})[0] == 400
    st = serve.step_status(empty)
    assert [x["state"] for x in st["steps"]] == ["done", "failed", "skipped"] and st["running"] is False and "Adding the PcbDoc failed" in st["error"]


def test_a_busy_refusal_does_not_touch_the_record_of_the_running_step(server, empty, world):
    serve._run_begin(empty, "route", ["altium.route_pcb"])
    assert serve.STEP_LOCK.acquire(blocking=False)
    try:
        assert call(server, "POST", ENDPOINTS["draw"], empty, {})[0] == 409
    finally:
        serve.STEP_LOCK.release()
    assert serve.step_status(empty)["running"] is True


def test_the_page_polls_the_run_while_busy_and_resumes_after_a_reload():
    js = ui_js()
    assert "/api/altium/step-status" in js
    poll = js[js.index("function pvPollStart"):js.index("function pvAltiumLinked")]
    assert "setInterval(" in poll and "1500" in poll and "clearInterval(" in poll and "!pvBusy" in poll and "soft: true" in poll
    run = js[js.index("async function pvRunStep"):js.index("async function pvFinish")]
    assert "pvPollStart(false)" in run and "pvPollStop()" in run and "pvFinish(" in run
    assert "refresh(true)" in js[js.index("async function pvFinish"):js.index("async function pvResume")]      # the same path for both ways in
    resume = js[js.index("async function pvResume"):js.index("onAct('altium-step'")]
    assert "step-status?take=1" in resume and "pvBusy = r.step" in resume and "pvPollStart(true)" in resume and "pvFinish(" in resume
    assert "pvResume()" in js[js.index("function pvStepNote"):js.index("async function pvRunStep")]       # asked once, when the pages render
    assert "pvPrepNames(r)" in js and "built the library" in js and "first + " in js


def test_a_result_that_cannot_be_put_into_words_is_an_answer_and_no_record_stays_running(empty, world, monkeypatch):
    monkeypatch.setattr(bridge, "route_pcb", lambda p, replace=False, keep_partial=False: {"warnings": []})      # no "summary" key
    code, body, _ = serve.run_step_button(empty, None, "route", {})
    assert code == 500 and "could not be read" in body["error"] and not serve.STEP_LOCK.locked()
    assert serve.step_status(empty)["running"] is False


def test_an_answer_clears_only_its_own_run(empty, world):
    _, _, first = serve.run_step_button(empty, None, "route", {})
    _, _, second = serve.run_step_button(empty, None, "route", {})
    assert first and second and first != second
    serve.step_ack(empty, first)                      # the first answer arrives late: the second run's record is not its to clear
    assert serve.step_status(empty).get("step") == "route"
    serve.step_ack(empty, second)
    assert serve.step_status(empty) == {"running": False}


def test_a_preparation_that_worked_is_not_reported_failed_when_its_sentence_cannot_be_made(empty, world, monkeypatch):
    world["rules"] = ["X"]
    monkeypatch.setattr(serve, "import_rules_summary", lambda res: 1 / 0)
    code, body, _ = serve.run_step_button(empty, None, "route", {})
    assert code == 200 and ran(world) == ["import_rules", "route_pcb"] and body["prepared"] == ["altium.import_rules"]


def test_the_page_that_was_reloaded_never_stays_busy_and_long_refusals_are_cut_readably():
    js = ui_js()
    poll = js[js.index("function pvPollStart"):js.index("function pvPollStop")]
    assert "else if (resumed) {" in poll and "{gone: true}" in poll and "pvPollStop();" in poll      # ended and already taken: stop, say so
    gone = js[js.index("else if (r && r.gone)"):js.index("else if (!r || r.error)")]
    assert "kind: 'warn'" in gone and "kind: 'ok'" not in gone and "finished" not in gone      # ended, never "succeeded": this page did not see the answer
    cut = js[js.index("function chatRefusedHTML"):js.index("function msgHTML")]
    assert "if (cut.length < 160) cut = s.slice(0, 220);" in cut and "<details" in cut and "esc(s.slice(cut.length))" in cut



def test_a_body_that_is_not_an_object_runs_the_plain_step_and_touches_no_older_record(empty, world):
    code, body, run_id = serve.run_step_button(empty, None, "route", ["replace"])
    assert code == 200 and ran(world) == ["route_pcb"] and world["log"][0][2] is False and run_id


def test_a_part_missing_from_the_library_makes_the_step_build_it_and_try_once_more(empty, world):
    """A line approved after the last build: draw refuses before it touches anything. The button builds and draws; the chat is not needed."""
    world["fail"]["draw_schematic"] = "Sheet 01 cannot be drawn: J1: no symbol in the project library (run library.build first)"
    real_build = bridge.build_library

    def build(project, *a, **k):
        world["fail"].pop("draw_schematic")            # after the build the part is there
        return real_build(project, *a, **k)
    bridge.build_library = build
    try:
        code, body, _ = serve.run_step_button(empty, None, "draw", {})
    finally:
        bridge.build_library = real_build
    assert code == 200 and ran(world) == ["draw_schematic", "build_library", "draw_schematic"]
    assert body["prepared"][0].startswith("library.build: ") and all(held for _, held, _ in world["log"])


def test_a_library_that_still_lacks_the_part_after_the_build_is_reported_once_not_looped(empty, world):
    world["fail"]["draw_schematic"] = "Sheet 01 cannot be drawn: J1: no symbol in the project library (run library.build first)"
    code, body, _ = serve.run_step_button(empty, None, "draw", {})
    assert code == 400 and ran(world) == ["draw_schematic", "build_library", "draw_schematic"]
    assert "no symbol in the project library" in body["error"] and body["done_first"] == "The library was built."
    assert not serve.STEP_LOCK.locked() and serve.step_status(empty)["running"] is False


def test_pin_numbers_filled_from_the_symbol_are_a_remark_not_an_amber_warning():
    filled = "netlist.write:01, pin numbers of U1, R1 matched by pin name to the library symbols"
    assert serve.warning_of(filled) == ""
    assert serve.warning_of(filled + " (warnings: net X has one pin)") == "net X has one pin"


def _usage(project):
    import json
    import workspace
    f = workspace.projects_dir() / project / "usage-log.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def test_a_step_writes_begin_and_end_usage_records_with_what_the_person_was_shown(empty, world):
    serve.run_step_button(empty, None, "route", {})
    begin, end = [r for r in _usage(empty) if r["kind"] == "step"]
    assert begin["phase"] == "begin" and begin["ok"] is True
    assert end["phase"] == "end" and end["ok"] is True and end["shown"] and end["steps"]
    world["fail"]["route_pcb"] = "Altium refused: no copper layers"
    serve.run_step_button(empty, None, "route", {})
    failed = [r for r in _usage(empty) if r["kind"] == "step"][-1]
    assert failed["ok"] is False and "no copper layers" in failed["shown"]


def test_two_runs_started_in_the_same_clock_tick_never_share_an_id(empty, monkeypatch):
    monkeypatch.setattr(serve.time, "time", lambda: 1000.0)
    ids = {serve._run_begin(empty, "route", ["altium.route_pcb"]) for _ in range(50)}
    assert len(ids) == 50


@pytest.mark.parametrize("step,msg,want,gone", [
    ("draw", "There is no netlist sheet to draw (no sheet 01): write the netlist first (netlist.write).",
     "ask the agent in the chat to write the schematic first", "netlist.write"),
    ("place", "The board has no outline yet and the project does not say how big the board is (idea: board size). Ask the student "
              "for the board width and height in mm (do not guess), record it with idea.update, or draw the outline in Altium "
              "first. Nothing was changed.",
     "Tell the agent in the chat the board width and height in mm", "Ask the student"),
    ("route", "Import the JLC rules first (altium.import_rules), then route: the board does not have Width. Nothing was changed.",
     "Import the JLC rules first (Rules, Apply rules in Altium)", "altium.import_rules"),
])
def test_a_refusal_on_a_button_page_is_in_the_students_words(server, empty, monkeypatch, step, msg, want, gone):
    # 1b of the status table: the button page showed the agent's wording ("(netlist.write)", "Ask the student ...")
    def refuse(*a, **k):
        raise bridge.BridgeError(msg)
    monkeypatch.setattr(bridge, BRIDGE_FN[step], refuse)
    code, body = call(server, "POST", ENDPOINTS[step], empty, {})
    assert code == 400 and want in body["error"] and gone not in body["error"]


def test_button_words_leave_the_library_hint_readable_and_other_text_alone():
    assert serve.button_words("No footprint in the project library for R1: run library.build first.") == \
        "No footprint in the project library for R1: build the library first: Library page, Build library."
    assert serve.NEEDS_LIBRARY.search("run library.build first")        # the retry still reads the bridge's own text
    assert serve.button_words("Altium refused a step: nothing was changed") == "Altium refused a step: nothing was changed"


def test_after_the_button_rebuilt_the_library_it_does_not_send_the_student_to_build_it_again(server, empty, world, monkeypatch):
    # review of 1b: the retry after a rebuild failed again on the same part; "build the library" would be a useless click
    def refuse(*a, **k):
        raise bridge.BridgeError("Sheet 01 cannot be drawn: R5: no symbol in the project library (run library.build first)")
    monkeypatch.setattr(bridge, BRIDGE_FN["draw"], refuse)
    code, body = call(server, "POST", ENDPOINTS["draw"], empty, {})
    assert code == 400 and "library.build" not in body["error"] and "Build library" not in body["error"]
    assert "(the library was just built without it: open the part on the Library page)" in body["error"]


def test_the_layout_page_offers_place_parts_before_a_pcbdoc_exists():
    # Place adds the PcbDoc itself (step_plan), so the empty Layout page still shows the button the agent points to
    js = ui_js()
    line = next(l for l in js.splitlines() if "if (pvNoPcb(text)) return" in l)
    assert "pvStepBtn('place')" in line and "pvStepNote('pcb')" in line
