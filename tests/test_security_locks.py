"""Default-deny for state changes (cross-site, DNS rebinding), the safe project delete, the update/step lock, and a concurrent-safe, idempotent decide."""
import http.client
import inspect
import json
import re
import threading

import pytest  # noqa: F401

import store
import workspace
from test_chat_turns import call, server  # noqa: F401


def raw(base, method, path, body=None, headers=None):
    """One request with exactly the headers given (urllib would set its own Host)."""
    host, port = base[len("http://"):].split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=15)
    h = {"Content-Type": "application/json", **(headers or {})}
    c.putrequest(method, path, skip_host="Host" in h)
    for k, v in h.items():
        c.putheader(k, v)
    data = json.dumps(body or {}).encode() if method == "POST" else b""
    c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    out = (r.status, r.read())
    c.close()
    return out


EVIL = {"Origin": "https://evil.example", "Host": "evil"}


def post_routes():
    """Every literal route _post handles, read from its source so a new route is covered without editing this test."""
    import serve
    src = inspect.getsource(serve.Handler._post)
    paths = set()
    for m in re.finditer(r'if path (?:==|in) ([^\n]*?):\s*(?:#[^\n]*)?\n', src):
        paths.update(re.findall(r'"(/api/[^"]+)"', m.group(1)))
    return sorted(paths)


def test_every_post_route_refuses_a_cross_site_request(server, empty):
    routes = post_routes()
    assert len(routes) > 60 and "/api/projects/delete" in routes and "/api/chat" in routes and "/api/altium/route" in routes
    for path in routes:
        assert raw(server, "POST", f"{path}?project={empty}", {}, EVIL)[0] == 403, path
        # a foreign Origin on an allowed Host, a rebinding Host without Origin, and a cross-site fetch are all refused too
        assert raw(server, "POST", f"{path}?project={empty}", {}, {"Origin": "https://evil.example"})[0] == 403, path
        assert raw(server, "POST", f"{path}?project={empty}", {}, {"Host": "evil"})[0] == 403, path
        assert raw(server, "POST", f"{path}?project={empty}", {}, {"Sec-Fetch-Site": "cross-site"})[0] == 403, path


def test_local_callers_still_work(server, empty):
    port = server.rsplit(":", 1)[1]
    for hdrs in ({}, {"Host": f"localhost:{port}"}, {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"},
                 {"Sec-Fetch-Site": "same-origin"}):
        assert raw(server, "POST", f"/api/chat/stop?project={empty}", {}, hdrs)[0] != 403, hdrs
    assert raw(server, "GET", f"/api/state?project={empty}", None, EVIL)[0] == 403       # reads of the API are refused to a rebound host too
    assert raw(server, "GET", f"/api/final/unverified?project={empty}", None, {"Origin": "https://evil.example"})[0] == 403
    assert raw(server, "GET", f"/api/state?project={empty}")[0] == 200


def test_delete_moves_to_trash_and_refuses_while_busy(server, empty):
    import serve
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Doomed"})[0] == 200
    folder = workspace.projects_dir() / "Doomed"
    (folder / "keep.txt").write_text("precious")
    with serve.STEP_LOCK:                                   # an Altium step is running
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "Doomed"})[0] == 409
    assert folder.is_dir()
    serve.TURNS[("Doomed", "s")] = serve._new_turn()        # a chat turn is answering
    try:
        assert call(server, "POST", "/api/projects/delete", empty, {"name": "Doomed"})[0] == 409
    finally:
        serve.TURNS.pop(("Doomed", "s"))
    assert folder.is_dir()
    code, body = call(server, "POST", "/api/projects/delete", empty, {"name": "Doomed"})
    assert code == 200 and not folder.exists()
    assert "Doomed" not in [p["name"] for p in body["projects"]]
    kept = list((workspace.projects_dir() / ".trash").glob("Doomed-*/keep.txt"))
    assert len(kept) == 1 and kept[0].read_text() == "precious"       # recoverable
    # a cross-site page cannot delete anything
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Safe"})[0] == 200
    assert raw(server, "POST", f"/api/projects/delete?project={empty}", {"name": "Safe"}, EVIL)[0] == 403
    assert (workspace.projects_dir() / "Safe").is_dir()


def test_update_refused_while_an_altium_step_runs(monkeypatch):
    import serve
    import update
    monkeypatch.setattr(update, "apply", lambda: pytest.fail("must not apply"))
    with serve.STEP_LOCK:
        code, res = serve.apply_update()
    assert code == 409 and "Altium" in res["error"]


def _proposal(project):
    return store.propose_bom(project, "R1", {"description": "x", "refs": ["R1"]}, reason="t", new=True)["id"]


def test_decide_same_way_twice_is_a_noop_and_a_conflict_fails(empty):
    pid = _proposal(empty)
    store.decide(empty, pid, "rejected")
    again = store.decide(empty, pid, "rejected")
    assert again["id"] == pid
    assert [p["status"] for p in store.proposals(empty) if p["id"] == pid] == ["rejected"]
    with pytest.raises(ValueError):
        store.decide(empty, pid, "approved")


def test_concurrent_decisions_are_applied_once(empty):
    pid = _proposal(empty)
    out = []

    def go(d):
        try:
            store.decide(empty, pid, d)
            out.append(d)
        except ValueError:
            out.append("fail")
    ts = [threading.Thread(target=go, args=("approved",)) for _ in range(6)] + [threading.Thread(target=go, args=("rejected",))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    final = [p["status"] for p in store.proposals(empty) if p["id"] == pid]
    assert len(final) == 1 and final[0] in ("approved", "rejected")
    assert out.count("fail") == (6 if final[0] == "rejected" else 1)        # only the conflicting way fails
    log = workspace.projects_dir() / empty / "bom-log.jsonl"
    n = len(log.read_text().splitlines()) if log.exists() else 0
    assert n == (1 if final[0] == "approved" else 0)           # one approval writes one BOM line, never two


def test_batch_repeat_is_not_reported_as_failure(server, empty):
    pid = _proposal(empty)
    for _ in range(2):
        code, body = call(server, "POST", "/api/proposals/batch", empty, {"ids": [pid], "decision": "rejected"})
        assert code == 200 and body["results"][0]["ok"] is True
    assert call(server, "POST", "/api/proposals/batch", empty, {"ids": [pid], "decision": "approved"})[1]["results"][0]["ok"] is False
