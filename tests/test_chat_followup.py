"""
The follow-up turn: after a student turn with a worthwhile refused / warned action the server runs ONE more, TEXT-ONLY agent turn
that carries the real results, so the reply no longer says "written" over a red refusal. The engine is faked at agent.respond.
"""
import threading
import time

import pytest

import session as session_mod
import workspace
from test_chat_turns import call, server, wait_for  # noqa: F401  (server is a fixture)

REFUSED = "netlist.write:01 refused: pin U1.3 has no net"


def scripted_respond(monkeypatch, replies):
    """respond answers from `replies` in order; every call is recorded as (message, history). A reply may be a callable(cancel)."""
    import serve
    calls = []

    def respond(model, message, history, cancel=None, **kw):
        calls.append((message, history))
        r = replies[min(len(calls) - 1, len(replies) - 1)]
        r = r(cancel) if callable(r) else r
        return {"provider": "fake", "seconds": 1, "usage": {}, **r}

    monkeypatch.setattr(serve.agent, "respond", respond)
    return calls


def refuse_everything(monkeypatch, refused=(REFUSED,), applied=(), once=True):
    import serve
    seen = []

    def fake(proj, actions, *a, **k):
        seen.append(actions)
        return list(applied), [], (list(refused) if len(seen) == 1 or not once else [])

    monkeypatch.setattr(serve, "apply_actions", fake)
    return seen


def chat_records(project):
    return session_mod.load_chat(project, session_mod.current(project, None))


def idle(server, project, secs=5):
    return wait_for(lambda: call(server, "GET", "/api/chat/progress", project)[1]["running"] is False, secs)


def followups(project):
    return [r for r in chat_records(project) if r.get("followup")]


def test_a_refused_action_triggers_exactly_one_text_only_followup(server, empty, monkeypatch):
    seen = refuse_everything(monkeypatch)
    calls = scripted_respond(monkeypatch, [
        {"reply": "Sheet 01 is written", "actions": [{"type": "netlist.write"}]},
        {"reply": "Sorry, the sheet was not written.", "actions": [{"type": "netlist.write"}, {"type": "bom.propose"}]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "write sheet 01"})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    time.sleep(0.3)
    assert len(calls) == 2
    msg, history = calls[1]
    assert msg.startswith("Results of your actions: ") and f"refused: {REFUSED}" in msg and "warnings: none" in msg
    assert "do not repeat actions that need the student's approval" in msg
    assert history[-1]["text"].startswith("Sheet 01 is written")
    assert len(seen) == 1                                           # A: the follow-up's actions were dropped, never applied
    f = followups(empty)[0]
    assert f["text"] == "Sorry, the sheet was not written." and f["applied"] == [] and not f.get("proposals")


def test_which_refusals_and_warnings_are_worth_a_followup():
    import serve
    worthy = serve.followup_worthy
    for r in ("netlist.write:01 refused: x", "altium.draw_schematic: not run. why", "library.add: no BOM line R1", "jlc.pickup: no new report",
              "order.check: boom", "bom.propose: bad", "the reply's actions block could not be read (JSON error at line 3); nothing in it was applied"):
        assert worthy([], [r]), r
    for r in ("altium.place_pcb: stopped by the student before it ran",
              "altium.draw_schematic: not run. Another step is still running in Altium (started with a button); try again",
              "the agent edited system files: a.py; they were restored", "the agent edited project files directly: x; they were restored",
              "auto-apply of p1 failed, it waits for you: x", "bom.check: nothing"):
        assert not worthy([], [r]), r
    assert worthy(["netlist.write:01 (warnings: floating pin)"], [])
    assert worthy(["altium.draw_schematic WARNING: x"], [])
    assert not worthy(["bom.propose:R1 (warning: R1 has no value)"], [])
    assert not worthy(["bom.check: WARNING: R9 named in the reply but in no BOM line"], [])
    assert not worthy([], [])


def test_value_only_warning_and_no_refusal_do_not_trigger(server, empty, monkeypatch):
    refuse_everything(monkeypatch, refused=(), applied=("bom.propose:R1 (warning: R1 has no value)",))
    calls = scripted_respond(monkeypatch, [{"reply": "fine", "actions": [{"type": "bom.propose"}]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "hi"})[0] == 200
    time.sleep(0.3)
    assert len(calls) == 1 and not followups(empty)


def test_a_stop_refusal_does_not_trigger(server, empty, monkeypatch):
    refuse_everything(monkeypatch, refused=("altium.draw_schematic: stopped by the student before it ran",))
    calls = scripted_respond(monkeypatch, [{"reply": "drawing", "actions": [{"type": "x"}]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "hi"})[0] == 200
    time.sleep(0.3)
    assert len(calls) == 1 and not followups(empty)


def test_setting_off_means_no_followup(server, empty, monkeypatch):
    import serve
    refuse_everything(monkeypatch)
    real = workspace.get
    monkeypatch.setattr(serve.workspace, "get", lambda k, d=None: False if k == "chat.followup_on_refusal" else real(k, d))
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    time.sleep(0.4)
    assert len(calls) == 1


def blocking_followup(started):
    def run(cancel):
        started.set()
        assert cancel.wait(10), "the follow-up was never cancelled"
        return {"reply": "half", "actions": [], "partial": True, "error_kind": "stopped"}
    return run


def test_a_new_student_message_cancels_the_followup_and_runs_without_a_409(server, empty, monkeypatch):
    refuse_everything(monkeypatch)
    started = threading.Event()
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}, blocking_followup(started),
                                           {"reply": "answer to the new question", "actions": []}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert started.wait(5)
    code, _ = call(server, "POST", "/api/chat", empty, {"text": "new question"})
    assert code == 200 and len(calls) == 3
    texts = [r["text"] for r in chat_records(empty) if r["role"] == "agent"]
    assert texts[-1] == "answer to the new question" and not followups(empty)       # H: the cancelled follow-up stored nothing


def test_a_step_button_cancels_the_followup_and_starts(server, empty, monkeypatch):
    import serve
    refuse_everything(monkeypatch)
    started = threading.Event()
    scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}, blocking_followup(started)])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert started.wait(5)
    try:
        assert serve.altium_start(empty) == ""
    finally:
        if serve.STEP_LOCK.locked():
            serve.STEP_LOCK.release()
    assert idle(server, empty) and not followups(empty)


def test_the_state_says_a_followup_is_running_and_stop_ends_it(server, empty, monkeypatch):
    refuse_everything(monkeypatch)
    started = threading.Event()
    scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}, blocking_followup(started)])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert started.wait(5)
    assert call(server, "GET", "/api/state", empty)[1]["followup_running"] is True
    assert call(server, "POST", "/api/chat/stop", empty)[0] == 200
    assert idle(server, empty)
    assert call(server, "GET", "/api/state", empty)[1]["followup_running"] is False
    assert not followups(empty)


def test_a_new_message_before_it_starts_suppresses_it(server, empty, monkeypatch):
    import serve
    refuse_everything(monkeypatch)
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}])
    real = serve._run_followup

    def late(proj, sess, *a):
        serve.say(proj, sess, {"ts": "2099-01-01T00:00:00", "role": "user", "text": "wait, new question"})
        return real(proj, sess, *a)

    monkeypatch.setattr(serve, "_run_followup", late)
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert idle(server, empty)
    time.sleep(0.3)
    assert len(calls) == 1 and not followups(empty)


def test_a_failed_followup_leaves_the_first_turn_as_it_is(server, empty, monkeypatch):
    import serve
    refuse_everything(monkeypatch)
    n = []

    def respond(model, message, history, **kw):
        n.append(1)
        if len(n) == 2:
            raise RuntimeError("engine died")
        return {"reply": "done", "actions": [{"type": "x"}], "provider": "fake", "seconds": 1, "usage": {}}

    monkeypatch.setattr(serve.agent, "respond", respond)
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert wait_for(lambda: len(n) == 2) and idle(server, empty)
    recs = [r for r in chat_records(empty) if r["role"] == "agent"]
    assert len(recs) == 1 and recs[0]["refused"] and not recs[0].get("followup")


def test_the_followup_is_wrapped_in_both_guards_and_its_citations_are_verified(server, empty, monkeypatch):
    import background
    import serve
    refuse_everything(monkeypatch)
    order, verified = [], []
    real_b, real_e = serve.project_guard.begin, serve.project_guard.end
    monkeypatch.setattr(serve.project_guard, "begin", lambda p: (order.append("begin"), real_b(p))[1])
    monkeypatch.setattr(serve.project_guard, "end", lambda g: (order.append("end"), real_e(g))[1])
    monkeypatch.setattr(background, "verify_record_async", lambda p, s, ts, text: verified.append(text))
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]},
                                           {"reply": "Not written [datasheet.pdf p.3]", "actions": [], "parse_refused": ["the reply's actions block was cut off before its end; nothing in it was applied"]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert wait_for(lambda: followups(empty)) and idle(server, empty)
    assert order == ["begin", "end", "begin", "end"]               # the first turn's guards, then the follow-up's
    f = followups(empty)[0]
    assert any("cut off" in r for r in f["refused"])
    assert any(v.startswith("Not written [datasheet.pdf p.3]") for v in verified) and len(calls) == 2


def test_a_discarded_followup_still_reports_what_the_guards_restored(server, empty, monkeypatch):
    import serve
    refuse_everything(monkeypatch)
    monkeypatch.setattr(serve.project_guard, "end", lambda g: (["sheets/01.json"], []) if serve.followup_running(empty, session_mod.current(empty, None)) else ([], []))
    started = threading.Event()

    def edits_then_cancelled(cancel):
        started.set()
        cancel.wait(10)
        return {"reply": "half", "actions": [], "partial": True, "error_kind": "stopped"}

    scripted_respond(monkeypatch, [{"reply": "done", "actions": [{"type": "x"}]}, edits_then_cancelled])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert started.wait(5)
    # followup_running is False once cancelled, so make the guard report on its own: stop first, then it ends
    monkeypatch.setattr(serve.project_guard, "end", lambda g: (["sheets/01.json"], []))
    assert call(server, "POST", "/api/chat/stop", empty)[0] == 200
    assert idle(server, empty)
    f = followups(empty)
    assert len(f) == 1 and "edited project files" in f[0]["refused"][0] and f[0]["text"].startswith("(Not applied: ")


def test_followup_ui_label_indicator_and_config_default():
    from ui_source import UI
    js = (UI / "js" / "chat.js").read_text(encoding="utf-8")
    css = (UI / "styles" / "chat.css").read_text(encoding="utf-8")
    assert "m.followup" in js and "After the results" in js and ".chat-followup{" in css
    assert "S.followup_running" in js and "Checking the results" in js and "chat-followup-stop" in js
    assert "/api/chat/stop" in js[js.index("onAct('chat-followup-stop'"):][:200]
    assert workspace.get("chat.followup_on_refusal") is True
