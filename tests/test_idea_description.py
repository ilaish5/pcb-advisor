"""The description at the top of the Idea sheet: the board in plain words. The student writes it, or the agent proposes
it (idea.describe) and the student accepts or dismisses; a dismissed proposal puts the old text back. Reachable from the
UI, the API and the agent's actions alike."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import agent
import model
import serve
import store
from ui_source import UI

IDEA_JS = (UI / "js" / "views" / "idea.js").read_text(encoding="utf-8")


@pytest.fixture
def server(home, monkeypatch):
    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(f"{base}{path}?project={project}", method="POST", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_the_students_text_is_agreed_as_written(empty):
    idea = store.set_idea_goal(empty, "  A device controller.\n\nIt reads the temperature.  ", by="student")
    assert idea["goal"] == "A device controller.\n\nIt reads the temperature."
    assert idea["goal_by"] == "student" and idea["goal_status"] == "confirmed" and "goal_prev" not in idea
    with pytest.raises(ValueError):
        store.set_idea_goal(empty, "x" * (store.GOAL_MAX + 1))


def test_the_agents_text_is_a_proposal_and_dismiss_puts_the_old_text_back(empty):
    store.set_idea_goal(empty, "Mine.", by="student")
    store.set_idea_goal(empty, "First try.", by="agent")
    idea = store.set_idea_goal(empty, "Second try.", by="agent")
    assert idea["goal"] == "Second try." and idea["goal_status"] == "proposed"
    assert idea["goal_prev"] == {"text": "Mine.", "by": "student"}, "a second proposal keeps what the first replaced"
    idea = store.decide_idea_goal(empty, accept=False)
    assert idea["goal"] == "Mine." and idea["goal_status"] == "confirmed" and "goal_prev" not in idea
    with pytest.raises(KeyError):
        store.decide_idea_goal(empty, accept=True)          # nothing proposed now
    with pytest.raises(ValueError):
        store.set_idea_goal(empty, "   ", by="agent")       # the agent cannot propose an empty description


def test_confirming_the_idea_accepts_a_proposed_description(empty):
    store.set_idea_goal(empty, "Proposed.", by="agent")
    idea = store.confirm_idea(empty)
    assert idea["goal"] == "Proposed." and idea["goal_status"] == "confirmed" and "goal_prev" not in idea


def test_the_agent_proposes_with_idea_describe(empty):
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.describe", "text": "A tracker for bikes."}])
    assert applied == ["idea.describe"] and not refused
    idea = store.load_idea(empty)
    assert idea["goal"] == "A tracker for bikes." and idea["goal_by"] == "agent" and idea["goal_status"] == "proposed"
    _, _, refused = serve.apply_actions(empty, [{"type": "idea.describe", "text": ""}])
    assert refused and refused[0].startswith("idea.describe")
    # the agent sees whether its text is still only a proposal
    assert json.loads(agent._summary(model.build(empty)))["idea"]["goal_status"] == "proposed"


def test_the_api_writes_accepts_and_dismisses(empty, server):
    st, res = post(server, "/api/idea/goal", {"text": "Written in the sheet."}, empty)
    assert st == 200 and res["idea"]["goal"] == "Written in the sheet." and res["idea"]["goal_status"] == "confirmed"
    st, res = post(server, "/api/idea/goal/confirm", {}, empty)
    assert st == 400, "nothing to accept"
    store.set_idea_goal(empty, "The agent's words.", by="agent")
    st, res = post(server, "/api/idea/goal/dismiss", {}, empty)
    assert st == 200 and res["idea"]["goal"] == "Written in the sheet."
    store.set_idea_goal(empty, "The agent's words.", by="agent")
    st, res = post(server, "/api/idea/goal/confirm", {}, empty)
    assert st == 200 and res["idea"]["goal"] == "The agent's words." and res["idea"]["goal_status"] == "confirmed"
    st, _ = post(server, "/api/idea/goal", {"text": "x" * (store.GOAL_MAX + 1)}, empty)
    assert st == 400
    # the older route still writes it, as the student's
    st, res = post(server, "/api/idea", {"goal": "Through the old route."}, empty)
    assert st == 200 and res["idea"]["goal"] == "Through the old route." and res["idea"]["goal_by"] == "student"


def test_the_sheet_shows_the_description_above_the_requirements():
    assert "function descHTML" in IDEA_JS
    reqs = IDEA_JS[IDEA_JS.index("function requirementsHTML"):IDEA_JS.index("// The agent's pending diagram proposal")]
    assert reqs.index("descHTML()") < reqs.index("req-list"), "the description comes first, in the same scroll region"
    for route in ("/api/idea/goal'", "/api/idea/goal/confirm", "/api/idea/goal/dismiss"):
        assert route in IDEA_JS, route
    for act in ("edit-desc", "save-desc", "cancel-desc", "confirm-desc", "dismiss-desc"):
        assert f"'{act}'" in IDEA_JS, act
    # paragraphs matter here: Enter is a new line, Ctrl+Enter saves; a poll never replaces an open form
    assert "e.ctrlKey || e.metaKey" in IDEA_JS
    assert ".desc-edit-form:not([hidden])" in IDEA_JS
    # a proposed description holds back "Confirm idea" like a proposed requirement does
    head = IDEA_JS[IDEA_JS.index("function ideaHeaderHTML"):IDEA_JS.index("function reqRowHTML")]
    assert "descProposed()" in head


def test_the_agent_is_told_the_description_is_the_context_for_every_answer():
    rules = (agent.RULES_DIR / "AGENTS.md").read_text(encoding="utf-8")
    where = rules[rules.index("# WHERE THINGS ARE"):]
    assert "idea.goal" in where and "context for every answer" in where and "idea.describe" in where
