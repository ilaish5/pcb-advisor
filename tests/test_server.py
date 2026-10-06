"""
The write path.

The server is the only writer, so these are the tests that matter most: what it
refuses is as much a part of the contract as what it records.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "redraw", lambda project: None)   # no drawing stack
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}?project={project}", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---------------------------------------------------------------- refusals
#
# Each of these used to be accepted, and each one cost something: a decision
# withdrawn with no record of why, a discussion closed with no record of what
# settled it, a typo'd id written into an append-only log forever.

def test_withdrawing_without_a_reason_is_refused(server, battery_mcu):
    code, body = post(server, "/api/retract", {"node": "req.vout"}, battery_mcu)
    assert code == 400 and "why" in body["error"]


def test_withdrawing_a_question_that_does_not_exist_is_refused(server, battery_mcu):
    code, body = post(server, "/api/retract",
                      {"node": "req.nope", "why": "x"}, battery_mcu)
    assert code == 400 and "no such question" in body["error"]


def test_closing_a_thread_without_a_reason_is_refused(server, battery_mcu):
    code, body = post(server, "/api/thread/resolve", {"anchor": "req.vout"}, battery_mcu)
    assert code == 400 and "settled" in body["error"]


def test_a_thread_on_an_invented_anchor_is_refused(server, battery_mcu):
    """An unchecked anchor is an invisible orphan forever: one typo and the
    thread never appears beside anything again."""
    code, body = post(server, "/api/message",
                      {"anchor": "made.up", "text": "hi", "ask_agent": False},
                      battery_mcu)
    assert code == 400 and "no such anchor" in body["error"]


def test_a_refusal_answers_with_json_not_with_the_design(server, battery_mcu):
    """The browser used to assign this body straight into its application
    state. Whatever else changes, a refusal must stay small and named."""
    code, body = post(server, "/api/retract", {"node": "req.nope", "why": "x"},
                      battery_mcu)
    assert code == 400 and set(body) == {"error"}


# ---------------------------------------------------------------- writes

def test_withdrawing_records_the_reason_and_drops_the_rules(server, battery_mcu):
    post(server, "/api/answer",
         {"node": "power.topology", "value": "linear"}, battery_mcu)
    code, m = post(server, "/api/retract",
                   {"node": "power.topology", "why": "runs from the cells"}, battery_mcu)
    assert code == 200
    assert not [c for c in m["constraints"] if c["from_node"] == "power.topology"]
    gone = [n for n in m["irrelevant"] if n.get("withdrawn")]
    assert gone and gone[0]["reason"] == "runs from the cells"


def test_the_chat_shows_a_withdrawal_as_a_removal(server, battery_mcu):
    """It reuses the decision card, and a green tick over a list of rules that
    were just REMOVED reads as though they had been added."""
    post(server, "/api/answer",
         {"node": "power.topology", "value": "linear"}, battery_mcu)
    _, m = post(server, "/api/retract",
                {"node": "power.topology", "why": "no regulator"}, battery_mcu)
    card = [c for c in m["chat"] if c.get("role") == "decision"][-1]
    assert card["withdrawn"] is True
    assert {r["id"] for r in card["locked"]} == {"lin.thermal", "lin.copper", "lin.esr"}


def test_an_answer_that_records_nothing_yet_says_what_it_is_waiting_for(server,
                                                                        battery_mcu):
    """Otherwise it is indistinguishable from an answer the corpus has nothing
    to say about, and the student cannot tell which just happened."""
    _, m = post(server, "/api/answer",
                {"node": "req.source", "value": "battery"}, battery_mcu)
    card = [c for c in m["chat"] if c.get("role") == "decision"][-1]
    assert not card["locked"]
    assert {w["needs"] for w in card["waiting"]} == {"a voltage regulator"}


def test_reopening_puts_the_question_back(server, battery_mcu):
    post(server, "/api/retract", {"node": "power.topology", "why": "no regulator"},
         battery_mcu)
    code, m = post(server, "/api/reopen", {"node": "power.topology"}, battery_mcu)
    assert code == 200
    assert "power.topology" in [n["id"] for n in m["open"]]


def test_an_agent_ask_on_the_thread_it_is_answering_is_dropped(server, battery_mcu,
                                                               monkeypatch):
    """The reply and the ask both land on that anchor, so one question produced
    two agent lines with the same timestamp, contradicting each other."""
    import serve

    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {
        "reply": "here is the answer",
        "actions": [{"type": "ask", "anchor": "req.vout", "text": "and a question"}],
    })
    _, m = post(server, "/api/message",
                {"anchor": "req.vout", "text": "why 3.3?"}, battery_mcu)
    said = [x for x in m["threads"]["req.vout"]["messages"] if x["role"] == "agent"]
    assert [x["text"] for x in said] == ["here is the answer"]


def test_an_agent_ask_on_a_different_element_is_kept(server, battery_mcu, monkeypatch):
    import serve

    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {
        "reply": "answering that",
        "actions": [{"type": "ask", "anchor": "req.iload", "text": "about current"}],
    })
    _, m = post(server, "/api/message",
                {"anchor": "req.vout", "text": "why 3.3?"}, battery_mcu)
    assert "req.iload" in m["threads"]


def test_the_browser_cannot_set_a_config_key_that_is_not_its_own(server, battery_mcu):
    code, body = post(server, "/api/config",
                      {"set": {"corpus.status": "authored"}}, battery_mcu)
    assert code == 400 and "not settable" in body["error"]


def test_a_model_belongs_to_the_engine_it_was_chosen_for(server, battery_mcu):
    """A Gemini id sent to Claude Code fails every turn, so switching engine
    must not carry the previous engine's model with it."""
    import workspace
    post(server, "/api/config", {"set": {"agent.provider": "antigravity",
                                         "agent.model": "gemini-x"}}, battery_mcu)
    assert workspace.get("agent.providers.antigravity.model") == "gemini-x"
    code, body = post(server, "/api/config",
                      {"set": {"agent.provider": "claude_code"}}, battery_mcu)
    assert code == 200
    assert body["config"]["agent"]["model"] == ""
    assert workspace.get("agent.providers.claude_code.model") == ""
