"""Stop on the button runs, and the Rules / Outputs buttons as step buttons: the same live list, the same lock, the same answer after a
reload. The bridge is faked: nothing here touches Altium."""
import pathlib
import threading

import pytest

import serve
import session as session_mod
import store
from altium import bridge
from test_chat_turns import call, server  # noqa: F401
from test_step_buttons import BUILT, IMPORTED, PLACED, spy, world  # noqa: F401
from test_unverified_pins import _sheet
from ui_source import ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
RAN = {"files": ["a.GTL", "b.GTO"], "added": False, "warnings": ["w1"], "outjob": "x.OutJob"}


def _free():
    return not serve.STEP_LOCK.locked()


def test_stop_between_steps_marks_the_rest_stopped_and_frees_the_run(empty, world, monkeypatch):
    world.update(schlib=False, pcb=False)
    world["sync"]()
    seen = []

    def build_then_stop(p, *a, **k):
        seen.append("build_library")
        assert serve.step_stop(empty) is True            # the student presses Stop while the library is being built
        assert serve.step_status(empty)["stopping"] is True
        return dict(BUILT)
    monkeypatch.setattr(bridge, "build_library", build_then_stop)
    code, body, _ = serve.run_step_button(empty, None, "place", {})
    assert code == 200 and body["stopped"] is True
    assert body["message"] == "Stopped after Building the project library in Altium; nothing after it ran."
    assert seen == ["build_library"] and "add_pcb" not in [n for n, _, _ in world["log"]] and "place_pcb" not in [n for n, _, _ in world["log"]]
    st = serve.step_status(empty)
    assert st["running"] is False and st["stopping"] is False and st["stopped"] is True
    assert [(x["key"], x["state"]) for x in st["steps"]] == [("library.build", "done"), ("altium.add_pcb", "stopped"), ("altium.place_pcb", "stopped")]
    assert _free() and not [k for k in serve.TURNS if k[0] == empty]
    # nothing is left that the next click trips on: the same step runs through
    world.update(schlib=True, pcb=True)
    monkeypatch.setattr(bridge, "build_library", lambda p, *a, **k: dict(BUILT))
    world["log"].clear()
    code, body, _ = serve.run_step_button(empty, None, "place", {})
    assert code == 200 and "stopped" not in body and [n for n, _, _ in world["log"]] == ["place_pcb"]


def test_the_stop_endpoint_stops_a_running_run_and_is_409_when_none_runs(server, empty, world, monkeypatch):
    assert call(server, "POST", "/api/altium/step-stop", empty, {})[0] == 409
    started, release = threading.Event(), threading.Event()

    def slow_build(p, *a, **k):
        started.set()
        release.wait(10)
        return dict(BUILT)
    monkeypatch.setattr(bridge, "build_library", slow_build)
    world.update(schlib=False)
    world["sync"]()
    first = {}
    t = threading.Thread(target=lambda: first.update(r=call(server, "POST", "/api/altium/place", empty, {})), daemon=True)
    t.start()
    assert started.wait(5)
    assert call(server, "POST", "/api/altium/step-stop", empty, {}) == (200, {"ok": True})
    assert call(server, "GET", "/api/altium/step-status", empty)[1]["stopping"] is True
    release.set()
    t.join(10)
    code, body = first["r"]
    assert code == 200 and body["stopped"] is True and "nothing after it ran" in body["message"]
    assert "place_pcb" not in [n for n, _, _ in world["log"]] and _free()
    assert call(server, "POST", "/api/altium/step-stop", empty, {})[0] == 409          # the run is over: nothing to stop


def test_stop_during_the_last_step_lets_it_finish_whole(empty, world, monkeypatch):
    """A step in Altium is never cut in the middle (a half-written file): Stop pressed during it ends the run only after it."""
    def place_then_stop(p, replace=False):
        serve.step_stop(empty)
        return dict(PLACED)
    monkeypatch.setattr(bridge, "place_pcb", place_then_stop)
    code, body, _ = serve.run_step_button(empty, None, "place", {})
    assert code == 200 and "stopped" not in body and body["summary"].startswith("2 parts placed")
    st = serve.step_status(empty)
    assert st["running"] is False and st["stopping"] is False and _free()


def test_stopped_run_tells_the_agent_what_ran(empty, world, monkeypatch):
    world.update(schlib=False)
    world["sync"]()
    monkeypatch.setattr(bridge, "build_library", lambda p, *a, **k: serve.step_stop(empty) and dict(BUILT))
    serve.run_step_button(empty, session_mod.current(empty, None), "draw", {})
    from test_step_buttons import button_notes
    notes = button_notes(empty)
    assert len(notes) == 1 and "pressed Stop" in notes[0]["text"] and "Stopped after" in notes[0]["text"]
    assert "altium.draw_schematic" not in " ".join(notes[0]["applied"])             # the step itself did not happen
    assert step_taken(empty)["stopped"] is True


def step_taken(project):
    return serve.step_status(project, take=True)


# ---- Rules and Outputs are step buttons

def test_rules_and_outputs_runs_show_in_step_status_and_resume(server, empty, world, monkeypatch):
    monkeypatch.setattr(bridge, "run_outjob", lambda p: dict(RAN))
    for path, step, label in (("/api/altium/import-rules", "rules", "Importing the JLC rules"),
                              ("/api/altium/run-outjob", "outputs", "Generating the outputs in Altium")):
        started, release = threading.Event(), threading.Event()
        real = bridge.import_rules if step == "rules" else bridge.run_outjob

        def slow(p, *a, _real=real, **k):
            started.set()
            release.wait(10)
            return _real(p, *a, **k)
        monkeypatch.setattr(bridge, "import_rules" if step == "rules" else "run_outjob", slow)
        first = {}
        t = threading.Thread(target=lambda: first.update(r=call(server, "POST", path, empty, {})), daemon=True)
        t.start()
        assert started.wait(5)
        st = call(server, "GET", "/api/altium/step-status", empty)[1]
        assert st["running"] is True and st["step"] == step and st["steps"][-1]["label"] == label
        release.set()
        t.join(10)
        code, body = first["r"]
        assert code == 200 and body["summary"] and "warnings" in body
        monkeypatch.setattr(bridge, "import_rules", lambda p, *a, **k: dict(IMPORTED))
    # the page that was reloaded reads the finished run once, with the step's name so it knows which tab it belongs to
    code, body, _ = serve.run_step_button(empty, None, "outputs", {})
    assert code == 200
    st = serve.step_status(empty, take=True)
    assert st["step"] == "outputs" and st["summary"] == "Altium wrote 2 files" and serve.step_status(empty) == {"running": False}


def test_the_rules_answer_keeps_the_chat_sentence_and_warns_on_what_altium_did_not_keep(empty, world, monkeypatch):
    res = {"created": ["A"], "updated": [], "skipped": [{"name": "S", "why": "no value"}], "unconfirmed": ["A"], "message": ""}
    monkeypatch.setattr(bridge, "import_rules", lambda p: dict(res))
    code, body, _ = serve.run_step_button(empty, None, "rules", {})
    assert code == 200 and body["summary"] == serve.import_rules_summary(res)
    assert body["warnings"] == ["Skipped 1: S (no value).", "Altium did not keep: A."]
    assert body["created"] == ["A"]                              # the bridge's own fields stay in the answer


def test_the_rules_step_adds_a_pcbdoc_first_when_the_project_has_none(empty, world):
    world["pcb"] = False
    code, body, _ = serve.run_step_button(empty, None, "rules", {})
    assert code == 200 and [n for n, _, _ in world["log"]] == ["add_pcb", "import_rules"]


def test_the_outputs_plan_adds_the_outjob_as_a_visible_step_when_missing(empty, world, monkeypatch):
    order = []
    monkeypatch.setattr(bridge, "read_prjpcb", lambda prj: {"pcbs": ["P.PcbDoc"], "outjobs": []})
    monkeypatch.setattr(bridge, "add_outjob", lambda p: order.append(("add_outjob", serve.STEP_LOCK.locked())) or {"file": "P.OutJob", "backup": ""})
    monkeypatch.setattr(bridge, "run_outjob", lambda p: order.append(("run_outjob", serve.STEP_LOCK.locked())) or dict(RAN))
    assert serve.step_plan(empty, "outputs") == ["outjob.generate"]
    code, body, _ = serve.run_step_button(empty, None, "outputs", {})
    assert code == 200 and order == [("add_outjob", True), ("run_outjob", True)]
    st = serve.step_status(empty)
    assert [(x["key"], x["state"], x["label"]) for x in st["steps"]] == [
        ("outjob.generate", "done", "Adding the OutJob to the project"), ("altium.run_outjob", "done", "Generating the outputs in Altium")]
    assert body["prepared"] == ["outjob.generate"] and body["added"] is True and "(OutJob added to the project)" in body["summary"]


def test_the_outputs_plan_is_empty_when_the_project_has_an_outjob(empty, world, monkeypatch):
    monkeypatch.setattr(bridge, "read_prjpcb", lambda prj: {"pcbs": ["P.PcbDoc"], "outjobs": ["P.OutJob"]})
    assert serve.step_plan(empty, "outputs") == []


def test_an_outjob_that_cannot_be_added_stops_the_run_before_the_outputs(empty, world, monkeypatch):
    monkeypatch.setattr(bridge, "read_prjpcb", lambda prj: {"pcbs": ["P.PcbDoc"], "outjobs": []})

    def boom(p):
        raise bridge.BridgeError("P.OutJob is in the project folder but not in the project; add it to the project first.")
    monkeypatch.setattr(bridge, "add_outjob", boom)
    monkeypatch.setattr(bridge, "run_outjob", lambda p: pytest.fail("the outputs must not run after a failed preparation"))
    code, body, _ = serve.run_step_button(empty, None, "outputs", {})
    assert code == 400 and body["error"].startswith("Adding the OutJob failed:") and "The outputs were not generated." in body["error"]
    assert [x["state"] for x in serve.step_status(empty)["steps"]] == ["failed", "skipped"] and _free()


def test_the_outputs_run_is_refused_at_plan_time_while_a_part_is_unverified_and_passes_after_accept(empty, world, monkeypatch):
    ran = []
    monkeypatch.setattr(bridge, "run_outjob", lambda p: ran.append(1) or dict(RAN))
    _sheet(empty)
    code, body, _ = serve.run_step_button(empty, None, "outputs", {})
    assert code == 400 and body["error"].startswith("Not made yet: 1 part has pins nobody checked") and "DFM > Unverified parts" in body["error"]
    assert ran == [] and _free()
    st = serve.step_status(empty)                              # a refusal is an answer: the page that reloads finds it
    assert st["running"] is False and st["error"] == body["error"] and [x["state"] for x in st["steps"]] == ["failed"]
    store.accept_pins(empty, "U1")
    code, body, _ = serve.run_step_button(empty, None, "outputs", {})
    assert code == 200 and ran == [1]


# ---- the page

def test_the_page_has_a_stop_button_and_the_rules_and_outputs_step_buttons():
    js = ui_js()
    assert "act: 'altium-step-stop'" in js and "onAct('altium-step-stop'" in js and "'/api/altium/step-stop'" in js
    note = js[js.index("function pvStepNote"):js.index("async function pvRunStep")]
    assert "pvStopBtn()" in note                                  # always, also for a run with a single step
    assert "(stopped)" in js and "r.stopped" in js and "r.message" in js
    for url in ("/api/altium/import-rules", "/api/altium/run-outjob"):
        assert f"url: '{url}'" in js
    rules = (REPO / "ui" / "js" / "views" / "rules.js").read_text(encoding="utf-8")
    assert "pvStepBtn('rules')" in rules and "pvStepNote('rules')" in rules and "rules-apply-altium" not in rules
    outputs = (REPO / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
    assert "pvStepNote('outputs')" in outputs and "pvStepBtn('outputs'" in outputs
    chat = (REPO / "ui" / "js" / "chat.js").read_text(encoding="utf-8")
    assert "r && r.error && pending" in chat[chat.index("async function chatStop"):chat.index("/* ---------- sending")]      # a 409 never leaves "Stopping…"


def test_outputs_primary_is_the_altium_route_and_the_outjob_is_secondary():
    outputs = (REPO / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
    head = outputs[outputs.index("function outHeader"):outputs.index("const outExportItems")]
    assert "const actions = (linked ? outOutjobBtn(false) : '')" in head                  # Generate OutJob moves to the secondary actions
    assert "const primary = linked ? outAltiumBtn(true) : outOutjobBtn(true)" in head      # no linked project: the manual route stays primary
    assert "'Generate OutJob'" in outputs and "label: 'Generate outputs in Altium'" not in outputs
    assert "label: 'Generate outputs in Altium'" in ui_js()


def test_the_generate_buttons_are_disabled_with_the_reason_while_pins_are_unverified():
    outputs = (REPO / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
    checks = (REPO / "ui" / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    why = outputs[outputs.index("function outBlockWhy"):outputs.index("function outBlockNote")]
    assert "dfmUnverified()" in why and "DFM > Unverified parts" in why             # the same parts the DFM page lists; no server call, no verify
    assert "api(" not in why
    assert "page: 'checks'" in outputs[outputs.index("function outBlockNote"):][:400]      # the link to DFM
    alt = outputs[outputs.index("function outAltiumBtn"):outputs.index("const outOutjobBtn")]
    assert "disabled: !!why" in alt and "title: why" in alt
    items = outputs[outputs.index("const outExportItems"):]
    items = items[:items.index("];")]
    assert "act: 'gen-gerber-zip', disabled: !!outBlockWhy()" in items
    assert "disabled: dfmZipBusy || !!held" in checks and "title: held" in checks     # DFM > "Get the zip"
    assert "outBlockNote()" in outputs[outputs.index("function outputsHTML"):]
