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

import session as session_mod
import store


@pytest.fixture
def server(home, monkeypatch):
    """The real handler on an ephemeral port, in this process."""
    from http.server import ThreadingHTTPServer
    import serve

    monkeypatch.setattr(serve, "QUIET", True)
    monkeypatch.setattr(serve, "recheck_async", lambda project, key: None)   # no network
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(base, path, body, project):
    req = urllib.request.Request(
        f"{base}{path}{chr(38) if chr(63) in path else chr(63)}project={project}", method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(base, path, project, raw=False):
    try:
        with urllib.request.urlopen(f"{base}{path}{'&' if '?' in path else '?'}project={project}", timeout=10) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def line(state, key):
    return next(l for l in state["bom"] if l["key"] == key)


# ---------------------------------------------------------------- reading

def test_state_carries_everything_the_ui_draws(server, lte):
    code, st = get(server, "/api/state", lte)
    assert code == 200
    for key in ("idea", "bom", "totals", "proposals", "sheets", "library", "sources", "chat", "sessions"):
        assert key in st, key
    assert st["sheets"][0]["id"] == "03" and "U4" in st["sheets"][0]["parts"]


def test_the_sheet_is_served_as_svg(server, lte):
    code, body = get(server, "/api/sheet.svg?sheet=03", lte, raw=True)
    assert code == 200 and body.startswith(b"<svg")
    assert get(server, "/api/sheet.svg?sheet=99", lte)[0] == 404


def test_the_skills_page_comes_from_the_registry(server, lte):
    code, body = get(server, "/api/skills", lte)
    assert code == 200 and any(s["name"] == "Check availability" and s["available"] for s in body["skills"])


# ---------------------------------------------------------------- the student decides

def test_approving_a_proposal_changes_the_bom_and_the_library_together(server, lte):
    _, st = get(server, "/api/state", lte)
    prop = next(p for p in st["proposals"] if p["status"] == "pending")
    assert line(st, "D30")["mpn"] == "ESD56301D05"
    code, st = post(server, "/api/proposal", {"id": prop["id"], "decision": "approved"}, lte)
    assert code == 200
    d30 = line(st, "D30")
    assert d30["mpn"] == "PESD5V0S1BL" and d30["library"] == "review" and d30["supply"] is None
    assert next(p for p in st["proposals"] if p["id"] == prop["id"])["status"] == "approved"


def test_rejecting_changes_nothing(server, lte):
    _, st = get(server, "/api/state", lte)
    prop = next(p for p in st["proposals"] if p["status"] == "pending")
    code, st = post(server, "/api/proposal", {"id": prop["id"], "decision": "rejected"}, lte)
    assert code == 200 and line(st, "D30")["mpn"] == "ESD56301D05"


def test_a_proposal_cannot_be_decided_twice_or_with_a_made_up_decision(server, lte):
    _, st = get(server, "/api/state", lte)
    pid = next(p for p in st["proposals"] if p["status"] == "pending")["id"]
    assert post(server, "/api/proposal", {"id": pid, "decision": "maybe"}, lte)[0] == 400
    assert post(server, "/api/proposal", {"id": pid, "decision": "rejected"}, lte)[0] == 200
    assert post(server, "/api/proposal", {"id": pid, "decision": "approved"}, lte)[0] == 400
    assert post(server, "/api/proposal", {"id": "nope", "decision": "approved"}, lte)[0] == 404


def test_editing_an_mpn_marks_the_line_as_checking(server, lte):
    code, st = post(server, "/api/bom/edit", {"line": "U5", "field": "mpn", "value": "TXS0104EPW"}, lte)
    assert code == 200 and line(st, "U5")["supply"] is None and st["totals"]["checking"] >= 1


def test_editing_a_field_that_is_not_editable_is_refused(server, lte):
    assert post(server, "/api/bom/edit", {"line": "U5", "field": "supply", "value": 1}, lte)[0] == 400
    assert post(server, "/api/bom/edit", {"line": "NOPE", "field": "note", "value": "x"}, lte)[0] == 404


def test_a_student_cannot_accept_a_part_that_failed_verification(server, lte):
    assert post(server, "/api/library/accept", {"line": "D31"}, lte)[0] == 400       # mismatch
    assert post(server, "/api/library/accept", {"line": "NOPE"}, lte)[0] == 404
    store.add_library(lte, "D31", {"verify": "pass"}, by="verify_part")
    code, st = post(server, "/api/library/accept", {"line": "D31"}, lte)
    assert code == 200 and line(st, "D31")["library"] == "ok"


def test_the_library_export_warns_about_what_is_unverified(server, lte):
    code, out = post(server, "/api/library/export", {}, lte)
    assert code == 200 and out["file"].endswith("_library.zip")
    assert any("D31" in w for w in out["warnings"]) and any("D30" in w for w in out["warnings"])
    code, body = get(server, f"/api/export/{out['file']}", lte, raw=True)
    assert code == 200 and body[:2] == b"PK"


# ---------------------------------------------------------------- what the agent may do

def test_a_bom_proposal_from_the_agent_changes_nothing_by_itself(home, lte):
    import serve
    applied, props, refused = serve.apply_actions(lte, [{
        "type": "bom.propose", "line": "U5", "changes": {"mpn": "SN74AXC4T774"}, "reason": "test",
        "sources": ["txs0104e.pdf"]}])
    assert props and not refused
    assert {l["key"]: l for l in store.bom(lte)}["U5"]["mpn"] == "TXS0104EPWR"
    assert any(p["id"] == props[0] and p["status"] == "pending" for p in store.proposals(lte))


def test_the_agent_cannot_mark_a_part_verified_or_accepted(home, lte):
    import serve
    serve.apply_actions(lte, [{"type": "library.add", "line": "D31", "changes": {
        "verify": "pass", "accepted": True, "model_source": "SnapEDA"}}])
    serve.apply_actions(lte, [{"type": "bom.propose", "line": "D30", "changes": {"mpn": "X"},
                               "library": {"verify": "pass", "accepted": True, "symbol": True}}])
    entry = store.library_parts(lte)["D31"]
    assert entry["verify"] == "mismatch" and entry["accepted"] is False
    prop = [p for p in store.proposals(lte) if p["changes"].get("mpn") == "X"][0]
    assert prop["library"] == {"symbol": True}


def test_a_netlist_with_a_part_without_pins_is_refused_and_gaps_only_warn(home, lte):
    import serve
    applied, _, refused = serve.apply_actions(lte, [{"type": "netlist.write", "sheet": "05", "data": {
        "parts": [{"ref": "U99", "pins": []}]}}])
    assert not applied and "05" not in store.sheet_ids(lte)
    assert "U99" in refused[0] and "no pins" in refused[0]
    applied, _, refused = serve.apply_actions(lte, [{"type": "netlist.write", "sheet": "05", "data": {
        "parts": [{"ref": "U99", "pins": [{"name": "A", "num": "1", "net": "N"}]},
                  {"ref": "U5", "pins": [{"name": "B", "num": "2", "net": ""}]}]}}])
    assert not refused and "05" in store.sheet_ids(lte)
    assert "U99: not in the BOM yet" in applied[0] and "U5.B: open pin" in applied[0]


def test_confirming_the_idea_needs_a_quote_from_the_student(home, empty):
    """A confirm whose quote does not hold up is not an error: it becomes idea.ready (the Confirm button)."""
    import serve
    store.propose_idea(empty, "Power", "Li-ion", by="agent")
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.confirm"}], last_user="yes")
    assert applied == ["idea.ready"] and not refused and not store.load_idea(empty)["confirmed"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.confirm", "student_said": "sure thing"}],
                                              last_user="Yes, confirmed.")
    assert applied == ["idea.ready"] and not refused and not store.load_idea(empty)["confirmed"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.confirm", "student_said": "yes, confirmed"}],
                                              last_user="Yes, confirmed.")
    assert applied == ["idea.confirm"] and store.load_idea(empty)["confirmed"]
    assert store.load_idea(empty)["agreed"][0]["status"] == "confirmed"      # saving the draft came with it


def test_an_unknown_action_is_reported_not_swallowed(home, lte):
    import serve
    _, _, refused = serve.apply_actions(lte, [{"type": "answer", "node": "x"}, {"type": "bom.propose", "line": "NOPE", "changes": {}}])
    assert len(refused) == 2


def test_a_part_conversation_is_anchored_and_starts_with_its_context(home, lte):
    import serve
    sid = serve.open_part_session(lte, "C35")             # a ref inside the C100 line
    row = next(r for r in session_mod.list_all(lte) if r["id"] == sid)
    assert row["anchor"] == "C100"
    chat = session_mod.load_chat(lte, sid)
    assert chat[0]["role"] == "ctx" and chat[0]["part"]["mpn"] == "CL05B104KO5NNNC"
    assert "+3V3" in chat[0]["part"]["nets"]
    assert serve.open_part_session(lte, "C34") == sid      # the same line, the same conversation


def test_chat_stores_the_replys_tools_and_proposals(server, lte, monkeypatch):
    import agent
    import workspace
    workspace.set_value("agent.autonomy", "ask")      # a routine proposal would otherwise be applied (and noted) at once
    monkeypatch.setattr(agent, "respond", lambda m, ask, hist, backend=None, timeout=None, **_kw: {
        "reply": "Proposed.", "tools": [{"t": "Check availability", "d": "x", "st": "ok"}],
        "actions": [{"type": "bom.propose", "line": "U5", "changes": {"note": "n"}, "reason": "r"}]})
    code, st = post(server, "/api/chat", {"text": "hello"}, lte)
    assert code == 200
    last = st["chat"][-1]
    assert last["role"] == "agent" and last["tools"][0]["t"] == "Check availability" and last["proposals"]
    assert st["chat"][-2]["text"] == "hello"


def test_chat_in_a_part_conversation_gives_the_agent_that_parts_context(server, lte, monkeypatch):
    import agent
    seen = {}
    monkeypatch.setattr(agent, "respond", lambda m, ask, hist, backend=None, timeout=None, **_kw: (
        seen.update(ask=ask) or {"reply": "ok", "actions": [], "tools": []}))
    _, out = post(server, "/api/thread/open", {"anchor": "U5"}, lte)
    code, _ = post(server, f"/api/chat?session={out['session']}", {"text": "why OE?"}, lte)
    assert code == 200 and "TXS0104EPWR" in seen["ask"] and "why OE?" in seen["ask"]


def test_an_ask_chip_reaches_the_engine_and_stays_on_the_students_message(server, lte, monkeypatch):
    import agent
    seen = []
    monkeypatch.setattr(agent, "respond", lambda m, ask, hist, backend=None, timeout=None, **_kw: (
        seen.append(ask) or {"reply": "ok", "actions": [], "tools": []}))
    monkeypatch.setattr(agent, "compact", lambda *a, **k: {"ok": True})    # no real engine call for memory
    _, st = post(server, "/api/chat", {"text": "is this right?", "about": {"kind": "part", "id": "U5", "label": "U5"}}, lte)
    assert "TXS0104EPWR" in seen[0] and seen[0].endswith("is this right?")        # a part brings its context card
    user = next(m for m in st["chat"] if m.get("text") == "is this right?")
    assert user["about"] == {"kind": "part", "id": "U5", "label": "U5"}
    post(server, "/api/chat", {"text": "why?", "about": {"kind": "net", "id": "+3V3", "label": "+3V3"}}, lte)
    assert "net '+3V3'" in seen[1] and seen[1].endswith("why?")
    # a chip the server does not know is ignored, not trusted
    _, st = post(server, "/api/chat", {"text": "hm", "about": {"kind": "shell", "id": "rm"}}, lte)
    assert seen[2] == "hm" and "about" not in next(m for m in st["chat"] if m.get("text") == "hm")


def test_a_reply_the_engine_failed_to_give_is_marked_so_the_chat_can_offer_retry(server, lte, monkeypatch):
    import agent
    monkeypatch.setattr(agent, "respond", lambda *a, **k: {"reply": "[agy] timed out", "actions": [], "error": True})
    _, st = post(server, "/api/chat", {"text": "hello"}, lte)
    assert st["chat"][-1]["error"] is True
    monkeypatch.setattr(agent, "respond", lambda *a, **k: {"reply": "Hi.", "actions": []})
    _, st = post(server, "/api/chat", {"text": "again"}, lte)
    assert "error" not in st["chat"][-1]


def test_the_note_of_a_decision_is_marked_so_the_chat_does_not_repeat_the_card(server, lte):
    _, st = get(server, "/api/state", lte)
    pid = next(p for p in st["proposals"] if p["status"] == "pending")["id"]
    _, st = post(server, "/api/proposal", {"id": pid, "decision": "rejected"}, lte)
    note = st["chat"][-1]
    assert note["role"] == "agent" and note["decision"] == "rejected" and note["proposal"] == pid
    row = next(r for r in st["sessions"] if r["id"] == st["session"])
    assert row["last"] is None or "Rejected" not in row["last"]["text"]


def test_a_confirm_without_a_quote_is_not_shown_as_a_refusal(server, lte, monkeypatch):
    import agent
    monkeypatch.setattr(agent, "respond", lambda *a, **k: {
        "reply": "Done.", "tools": [], "actions": [{"type": "idea.confirm"}]})
    _, st = post(server, "/api/chat", {"text": "yes"}, lte)
    assert "Not applied" not in st["chat"][-1]["text"] and "idea.ready" in st["chat"][-1]["applied"]


def test_a_refused_action_is_named_in_the_reply_and_kept_out_of_the_applied_list(server, lte, monkeypatch):
    """The model's text is written before the action results: a refused action must still be visible to the student."""
    import agent
    monkeypatch.setattr(agent, "respond", lambda *a, **k: {
        "reply": "Done, the Gerbers are being produced.", "tools": [], "actions": [{"type": "jlc.no_such_action"}]})
    _, st = post(server, "/api/chat", {"text": "make the gerbers"}, lte)
    last = st["chat"][-1]
    assert "(Not applied: jlc.no_such_action" in last["text"] and last["applied"] == []


# ---------------------------------------------------------------- the rest of the surface

def test_the_browser_cannot_set_a_config_key_that_is_not_its_own(server, lte):
    code, body = post(server, "/api/config", {"set": {"server.port": 1}}, lte)
    assert code == 400 and "not settable" in body["error"]


def test_a_model_belongs_to_the_engine_it_was_chosen_for(server, lte):
    """A Gemini id sent to Claude Code fails every turn, so switching engine
    must not carry the previous engine's model with it."""
    import workspace
    post(server, "/api/config", {"set": {"agent.provider": "antigravity", "agent.model": "gemini-x"}}, lte)
    assert workspace.get("agent.providers.antigravity.model") == "gemini-x"
    code, body = post(server, "/api/config", {"set": {"agent.provider": "claude_code"}}, lte)
    assert code == 200 and body["config"]["agent"]["model"] == "sonnet"          # claude_code's own default


def test_an_upload_gets_a_safe_name_and_a_sidecar_with_its_hash(server, lte):
    import base64
    code, st = post(server, "/api/upload", {"name": "test:file?.pdf", "data_b64": base64.b64encode(b"%PDF-1.4 hello").decode()}, lte)
    assert code == 200
    row = next(s for s in st["sources"] if s["name"] == "test_file_.pdf")
    assert row["scope"] == "project" and row["present"] and row["sha256"] == "f31cdee0"


def test_a_citation_resolves_to_a_listed_source(lte):
    import model
    names = {s["name"] for s in model.list_sources(lte)}
    assert set(model.citations(lte)) <= names


def test_the_agent_prompt_survives_a_context_card_in_the_history(home, lte, monkeypatch):
    """A part conversation starts with a card that has no text; it used to crash the turn."""
    import agent
    import gateway
    import model
    import serve
    seen = {}

    class Res:
        ok, text, provider, model, error = True, "fine", "claude_code", "", ""
    monkeypatch.setattr(gateway, "route", lambda req, name=None: (seen.update(prompt=req.prompt) or Res()))
    sid = serve.open_part_session(lte, "U5")
    m = model.build(project=lte, session=sid)
    out = agent.respond(m, "why OE?", m["chat"], backend="claude_code")
    assert out["reply"] == "fine" and "why OE?" in seen["prompt"]


def test_rules_endpoints(server, lte):
    # GET /api/rules
    code, res = get(server, "/api/rules", lte)
    assert code == 200
    assert "preset" in res
    assert len(res["preset"]["rules"]) >= 7
    assert "diff" in res
    assert res["missing_in_pcb"] == []                  # no PcbDoc linked: nothing to report

    # POST /api/rules/extra
    code, res = post(server, "/api/rules/extra", {
        "rule": {"name": "PowerNet_Width", "kind": "Width", "scope1": "InNet('12V')", "value": "30mil"}
    }, lte)
    assert code == 200 and res.get("ok") is True

    # GET /api/rules/export
    code, raw = get(server, "/api/rules/export", lte, raw=True)
    assert code == 200
    assert b"\xb6\r\n" in raw
    assert b"PowerNet_Width" in raw


def test_rules_preset_follows_the_project_board(server, lte):
    import project
    code, res = get(server, "/api/rules", lte)
    assert code == 200 and res["preset"]["name"] == "JLC 2-layer 1 oz"
    project.touch(lte, board={**project.board(lte), "layers": 4, "copper_oz": 2.0})
    code, res = get(server, "/api/rules", lte)
    assert res["preset"]["name"] == "JLC 4-layer 2 oz"
    ring = next(r for r in res["preset"]["rules"] if r["name"] == "MinimumAnnularRing_PTH")
    assert ring["scope1"] == "IsPad" and ring["fab_min_mm"] == 0.254
    code, raw = get(server, "/api/rules/export?plain=1", lte, raw=True)
    assert code == 200 and b"MinimumAnnularRing_PTH" in raw and b"SCOPE1EXPRESSION=IsVia" in raw


def test_calc_endpoints(server, lte):
    # GET /api/calc (trace width)
    code, res = get(server, "/api/calc?type=trace_width&current=2.0", lte)
    assert code == 200
    assert "value" in res and "formula" in res and "source" in res

    # POST /api/calc (divider)
    code, res = post(server, "/api/calc", {"type": "divider", "vin": 5.0, "vout": 3.3}, lte)
    assert code == 200
    assert "value" in res and "formula" in res and "source" in res

    # POST /api/calc (led)
    code, res = post(server, "/api/calc", {"type": "led", "v_supply": 5.0, "v_forward": 2.0, "i_ma": 20}, lte)
    assert code == 200
    assert "value" in res and "formula" in res and "source" in res

    # POST /api/calc (microstrip)
    code, res = post(server, "/api/calc", {"type": "microstrip", "w": 0.3, "h": 0.2}, lte)
    assert code == 200
    assert "value" in res and "formula" in res and "source" in res


def test_library_endpoints(server, lte):
    # GET /api/library/search
    code, res = get(server, "/api/library/search?mpn=NE555P", lte)
    assert code == 200
    assert "links" in res and "LCSC" in res["links"]

    # POST /api/library/check_package
    code, res = post(server, "/api/library/check_package", {"bom_pkg": "LQFP-48", "jlc_pkg": "LQFP-48"}, lte)
    assert code == 200
    assert res.get("match") is True

    # POST /api/library/build_script
    code, res = post(server, "/api/library/build_script", {}, lte)
    assert code == 200
    assert res.get("ok") is True


# ---------------------------------------------------------------- static files under /ui/

def get_static(base, path):
    """Raw GET (no project parameter): status, Content-Type, body. Errors come back as values, not exceptions."""
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def test_ui_serves_script_files_from_ui_dir(server):
    status, ctype, body = get_static(server, "/ui/js/core.js")
    assert status == 200
    assert ctype.startswith("application/javascript")
    assert b"ACTIONS" in body
    # nested folders work, and the old alias still points at diagram.js
    assert get_static(server, "/ui/js/views/bom.js")[0] == 200
    status, ctype, body = get_static(server, "/diagram.js")
    assert status == 200 and ctype.startswith("application/javascript") and b"DiagramEditor" in body


def test_ui_serves_every_stylesheet_the_page_links(server):
    import re
    status, ctype, html = get_static(server, "/")
    assert status == 200 and ctype.startswith("text/html")
    hrefs = re.findall(r'<link rel="stylesheet" href="(/ui/[^"]+\.css)"', html.decode("utf-8"))
    assert "/ui/styles/core.css" in hrefs
    for href in hrefs:
        status, ctype, body = get_static(server, href)
        assert status == 200, href
        assert ctype.startswith("text/css"), href
        assert body.strip(), href


def test_ui_serves_every_script_the_page_loads(server):
    import re
    status, _, html = get_static(server, "/")
    srcs = re.findall(r'<script src="(/ui/[^"]+)"', html.decode("utf-8"))
    assert "/ui/js/core.js" in srcs and "/ui/js/boot.js" in srcs
    for src in srcs:
        status, ctype, _ = get_static(server, src)
        assert status == 200 and ctype.startswith("application/javascript"), src


def test_ui_static_refuses_paths_outside_ui_dir(server):
    for bad in ("/ui/../scripts/serve.py", "/ui/../config.json", "/ui/%2e%2e/config.json",
                "/ui/js/../../config.json", "/ui//config.json", "/ui/..%5cconfig.json"):
        status, _, body = get_static(server, bad)
        assert status in (403, 404), bad
        assert b"workspace" not in body and b"projects_dir" not in body, bad


def test_ui_static_refuses_unknown_extensions_and_missing_files(server):
    assert get_static(server, "/ui/index.html")[0] == 404        # the page itself is served at / only
    assert get_static(server, "/ui/js/core.py")[0] == 404
    assert get_static(server, "/ui/js/")[0] == 404
    assert get_static(server, "/ui/js/nope.js")[0] == 404
    assert get_static(server, "/ui/styles/nope.css")[0] == 404
    assert get_static(server, "/ui/js/core.js%00.png")[0] in (403, 404)
    assert get_static(server, "/tabs.js")[0] == 404             # old dead entries are gone


# ---------------------------------------------------------------- a file another program holds

def test_a_locked_idea_file_is_an_answer_not_a_dropped_connection(server, lte, monkeypatch):
    import pathlib
    store.save_idea(lte, {"agreed": []})
    store.save_idea_draft(lte, {"agreed": []})
    real = pathlib.Path.read_text

    def locked(self, *a, **k):
        if self.name == "idea.json":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", locked)
    code, body = post(server, "/api/idea/draft/save", {}, lte)
    assert code == 423 and "idea.json is open in another program" in body["error"]


def test_a_chat_posted_while_a_turn_runs_is_refused_and_not_stored(server, lte, monkeypatch):
    import serve
    monkeypatch.setattr(serve.Handler, "session", lambda self, proj: "s1")
    with serve.TURNS_LOCK:
        serve.TURNS[(lte, "s1")] = {"cancel": threading.Event()}
    try:
        before = len(get(server, "/api/state", lte)[1]["chat"])
        code, body = post(server, "/api/chat", {"text": "hello again"}, lte)
        assert code == 409
        assert len(get(server, "/api/state", lte)[1]["chat"]) == before
    finally:
        with serve.TURNS_LOCK:
            serve.TURNS.pop((lte, "s1"), None)
