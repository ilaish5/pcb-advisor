"""The extension shim (scripts/ext.py): routes, actions and model keys added from other modules, with no change when none is registered."""
import json

import pytest

import ext
from test_chat_turns import call, server  # noqa: F401
from test_security_locks import EVIL, raw


@pytest.fixture(autouse=True)
def clean_registries():
    saved = {name: list(getattr(ext, name)) for name in ("GET", "POST", "ACTIONS", "MODEL", "SUMMARY")}
    yield
    for name, items in saved.items():
        getattr(ext, name)[:] = items


def test_registered_post_and_get_are_reachable_and_guarded(server, empty):
    ext.POST.append(lambda h, path, body: {"echo": body, "project": h.project()} if path == "/api/ext/ping" else None)
    ext.GET.append(lambda h, path, q: {"q": q} if path == "/api/ext/ping" else None)
    code, body = call(server, "POST", "/api/ext/ping", empty, {"a": 1})
    assert code == 200 and body == {"echo": {"a": 1}, "project": empty}
    code, body = call(server, "GET", "/api/ext/ping?x=2", empty)
    assert code == 200 and body["q"]["x"] == "2"
    for method in ("POST", "GET"):                       # the guards run before the extensions
        assert raw(server, method, f"/api/ext/ping?project={empty}", {}, EVIL)[0] == 403
        assert raw(server, method, f"/api/ext/ping?project={empty}", {}, {"Origin": "https://evil.example"})[0] == 403
    assert raw(server, "POST", f"/api/ext/ping?project={empty}", {}, {"Sec-Fetch-Site": "cross-site"})[0] == 403


def test_extension_error_status_and_pass_through(server, empty):
    def refuse(h, path, body):
        if path == "/api/ext/nope":
            raise ext.HTTPError(409, "not now")
    ext.POST.append(refuse)
    assert call(server, "POST", "/api/ext/nope", empty, {}) == (409, {"error": "not now"})
    assert call(server, "POST", "/api/ext/other", empty, {}) == (404, {"error": "not found"})


def test_unregistered_paths_still_404(server, empty):
    assert call(server, "POST", "/api/ext/none", empty, {}) == (404, {"error": "not found"})
    assert call(server, "GET", "/api/ext/none", empty) == (404, {"error": "not found"})
    assert call(server, "GET", "/api/state", empty)[0] == 200


def test_built_in_routes_win_over_extensions(server, empty):
    ext.GET.append(lambda h, path, q: {"hijacked": True})
    ext.POST.append(lambda h, path, body: {"hijacked": True})
    assert "hijacked" not in call(server, "GET", "/api/config", empty)[1]
    assert "hijacked" not in call(server, "POST", "/api/chat/stop", empty, {})[1]


def test_model_and_summary_extensions(empty):
    import agent
    import model
    assert "ext_key" not in model.build(project=empty)
    ext.MODEL.append(lambda project, m: {"ext_key": {"project": project, "has_bom": "bom" in m}})
    ext.SUMMARY.append(lambda project, s: {"ext_summary": ["x"]})
    m = model.build(project=empty)
    assert m["ext_key"] == {"project": empty, "has_bom": True}
    assert json.loads(agent._summary(m))["ext_summary"] == ["x"]


def test_action_extension_for_unknown_kind(empty):
    import serve
    old = serve._apply_actions(empty, [{"type": "ext.unknown"}])
    assert old == ([], [], ["ext.unknown: not a known action, or fields missing"])
    seen = []

    def mine(project, a, ctx):
        if a.get("type") != "ext.hello":
            return None
        seen.append((project, ctx["last_user"]))
        return "ext.hello:ok"
    ext.ACTIONS.append(mine)
    assert serve._apply_actions(empty, [{"type": "ext.hello"}], last_user="hi") == (["ext.hello:ok"], [], [])
    assert seen == [(empty, "hi")]
    assert serve._apply_actions(empty, [{"type": "ext.unknown"}]) == old       # nobody claims it: the old answer stays


def test_load_imports_the_stream_modules_and_register_decorator():
    ext.load()
    import sys
    assert all(name in sys.modules for name in ext.MODULES)

    @ext.register("model")
    def f(project, m):
        return {}
    assert f in ext.MODEL
