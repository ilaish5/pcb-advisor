"""
The follow-up turn: after a student turn with a refused or warned action the server runs ONE more agent turn that carries the
real results, so the reply no longer says "written" over a red refusal. The engine is faked at agent.respond.
"""
import time

import pytest

import session as session_mod
import workspace
from test_chat_turns import call, server, wait_for  # noqa: F401  (server is a fixture)


def scripted_respond(monkeypatch, replies):
    """respond answers from `replies` in order; every call is recorded as (message, history)."""
    import serve
    calls = []

    def respond(model, message, history, **kw):
        calls.append((message, history))
        r = replies[min(len(calls) - 1, len(replies) - 1)]
        return {"provider": "fake", "seconds": 1, "usage": {}, **r}

    monkeypatch.setattr(serve.agent, "respond", respond)
    return calls


def chat_records(project):
    return session_mod.load_chat(project, session_mod.current(project, None))


def idle(server, project, secs=5):
    return wait_for(lambda: call(server, "GET", "/api/chat/progress", project)[1]["running"] is False, secs)


BAD = {"type": "bogus.kind"}       # the server refuses an action it does not know


def test_a_refused_action_triggers_exactly_one_followup_with_the_results(server, empty, monkeypatch):
    calls = scripted_respond(monkeypatch, [
        {"reply": "Sheet 01 is written", "actions": [BAD]},
        {"reply": "Sorry, the sheet was not written.", "actions": [{"type": "bogus.other"}]}])      # its own refusal must not chain
    assert call(server, "POST", "/api/chat", empty, {"text": "write sheet 01"})[0] == 200
    assert wait_for(lambda: len(calls) == 2 and any(r.get("followup") for r in chat_records(empty)))
    assert idle(server, empty)
    time.sleep(0.3)
    assert len(calls) == 2
    msg, history = calls[1]
    assert msg.startswith("Results of your actions: ") and "refused: bogus.kind" in msg and "warnings: none" in msg
    assert "do not repeat actions that need the student's approval" in msg
    assert history[-1]["text"].startswith("Sheet 01 is written")
    recs = [r for r in chat_records(empty) if r["role"] == "agent"]
    assert [bool(r.get("followup")) for r in recs] == [False, True]
    assert recs[1]["text"].startswith("Sorry, the sheet was not written.") and recs[1]["refused"]


def test_a_warning_also_triggers_it_and_no_refusal_does_not(server, empty, monkeypatch):
    import serve
    calls = scripted_respond(monkeypatch, [{"reply": "fine", "actions": []}])
    assert call(server, "POST", "/api/chat", empty, {"text": "hi"})[0] == 200
    time.sleep(0.3)
    assert len(calls) == 1 and not any(r.get("followup") for r in chat_records(empty))
    monkeypatch.setattr(serve, "apply_actions", lambda *a, **k: (["netlist.write:01 (warnings: floating pin)"], [], []))
    calls = scripted_respond(monkeypatch, [{"reply": "written", "actions": [{"type": "x"}]}, {"reply": "with a warning", "actions": []}])
    assert call(server, "POST", "/api/chat", empty, {"text": "again"})[0] == 200
    assert wait_for(lambda: len(calls) == 2)
    assert "warnings: netlist.write:01 (warnings: floating pin)" in calls[1][0]


def test_setting_off_means_no_followup(server, empty, monkeypatch):
    import serve
    real = workspace.get
    monkeypatch.setattr(serve.workspace, "get", lambda k, d=None: False if k == "chat.followup_on_refusal" else real(k, d))
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [BAD]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    time.sleep(0.4)
    assert len(calls) == 1


def test_a_new_student_message_suppresses_it(server, empty, monkeypatch):
    import serve
    calls = scripted_respond(monkeypatch, [{"reply": "done", "actions": [BAD]}])
    real = serve._run_followup

    def late(proj, sess, *a):
        serve.say(proj, sess, {"ts": "2099-01-01T00:00:00", "role": "user", "text": "wait, new question"})
        return real(proj, sess, *a)

    monkeypatch.setattr(serve, "_run_followup", late)
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert idle(server, empty)
    time.sleep(0.3)
    assert len(calls) == 1 and not any(r.get("followup") for r in chat_records(empty))


def test_a_failed_followup_leaves_the_first_turn_as_it_is(server, empty, monkeypatch):
    import serve
    n = []

    def respond(model, message, history, **kw):
        n.append(1)
        if len(n) == 2:
            raise RuntimeError("engine died")
        return {"reply": "done", "actions": [BAD], "provider": "fake", "seconds": 1, "usage": {}}

    monkeypatch.setattr(serve.agent, "respond", respond)
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert wait_for(lambda: len(n) == 2) and idle(server, empty)
    recs = [r for r in chat_records(empty) if r["role"] == "agent"]
    assert len(recs) == 1 and recs[0]["refused"] and not recs[0].get("followup")


def test_the_followup_cannot_approve_or_resend_what_was_refused(server, empty, monkeypatch):
    import serve
    decided = []
    monkeypatch.setattr(serve.store, "may_auto_apply", lambda rec, mode=None: True)       # autonomy would approve everything
    monkeypatch.setattr(serve.store, "propose_bom", lambda *a, **k: {"id": "p9", "kind": "bom"})
    monkeypatch.setattr(serve, "decide_and_note", lambda *a, **k: decided.append(a[2]))
    prop = {"type": "bom.propose", "line": "R1", "changes": {"value": "1k"}}
    scripted_respond(monkeypatch, [
        {"reply": "done", "actions": [BAD]},
        {"reply": "Corrected.", "actions": [prop, BAD, {"type": "altium.draw_schematic", "student_said": "draw"}]}])
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    assert wait_for(lambda: any(r.get("followup") for r in chat_records(empty))) and idle(server, empty)
    f = [r for r in chat_records(empty) if r.get("followup")][0]
    assert f["proposals"] == ["p9"] and decided == []                  # proposed, never approved
    assert not any("bogus" in a or "draw_schematic" in a for a in f["applied"]) and not f.get("refused")


def test_followup_ui_label_and_config_default():
    from ui_source import UI
    js = (UI / "js" / "chat.js").read_text(encoding="utf-8")
    css = (UI / "styles" / "chat.css").read_text(encoding="utf-8")
    assert "m.followup" in js and "After the results" in js and ".chat-followup{" in css
    assert workspace.get("chat.followup_on_refusal") is True
