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
