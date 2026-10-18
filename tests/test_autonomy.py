"""
Autonomy: "act, show, allow undo; ask only for what matters".

agent.autonomy = ask | important (default) | auto decides which proposals are applied without a click.
store.classify_proposal is the one place that sorts a proposal into routine / important / critical.
Undo is a compensating log entry that restores the `before` the proposal recorded.
"""
import pytest

import store
import workspace
from test_server import server, post  # noqa: F401  (server is a fixture)


def prop(kind="bom", changes=None, before=None, new=False):
    return {"kind": kind, "line": "X1", "changes": changes or {}, "before": before or {}, "new": new}


CLASSIFY = [
    (prop(changes={"value": "10k"}, before={"value": "1k"}), "routine"),
    (prop(changes={"package": "0603", "value": "1uF"}, new=True), "routine"),
    (prop(changes={"note": "check", "dnp": True}), "routine"),
    (prop(changes={"datasheet": "x.pdf"}), "routine"),
    (prop(changes={"refs": ["R1"]}), "routine"),
    (prop(changes={"mpn": "STM32G031F6P6"}, new=True), "important"),            # new IC
    (prop(changes={"mpn": "AP2112K"}, before={"mpn": "LM1117"}), "important"),  # MPN change
    (prop(changes={"mpn": "AP2112K"}, before={"mpn": "AP2112K"}), "routine"),   # same MPN again
    (prop(changes={"mpn": "—"}), "routine"),
    (prop(changes={"lcsc": "C12345"}, before={"lcsc": ""}), "important"),
    (prop(changes={"deleted": True}), "critical"),
    (prop(kind="idea_diagram", changes={"diagram": {}}), "routine"),
    (prop(kind="idea_confirm"), "important"),
    (prop(kind="altium_write"), "important"),
    (prop(kind="order"), "critical"),
    (prop(kind="jlc_upload"), "critical"),
    (prop(kind="delete_sheet"), "critical"),
    (prop(kind="something_new"), "important"),
]


@pytest.mark.parametrize("p,level", CLASSIFY)
def test_classification_table(p, level):
    assert store.classify_proposal(p) == level


@pytest.mark.parametrize("mode,level,auto", [
    ("ask", "routine", False), ("ask", "important", False), ("ask", "critical", False),
    ("important", "routine", True), ("important", "important", False), ("important", "critical", False),
    ("auto", "routine", True), ("auto", "important", True), ("auto", "critical", False),
])
def test_what_each_mode_lets_through(mode, level, auto):
    p = {"routine": prop(changes={"value": "1"}), "important": prop(changes={"mpn": "A1"}),
         "critical": prop(kind="order")}[level]
    assert store.may_auto_apply(p, mode) is auto


def test_default_is_important_and_a_bad_value_is_refused(server, lte):
    assert store.autonomy() == "important"
    code, body = post(server, "/api/config", {"set": {"agent.autonomy": "yolo"}}, lte)
    assert code == 400
    code, body = post(server, "/api/config", {"set": {"agent.autonomy": "auto"}}, lte)
    assert code == 200 and body["config"]["agent"]["autonomy"] == "auto"
    with pytest.raises(SystemExit):
        workspace.set_value("agent.autonomy", "nope")


def _agent_says(monkeypatch, actions):
    import agent
    monkeypatch.setattr(agent, "respond", lambda *a, **k: {"reply": "ok", "tools": [], "actions": actions})


def _bom(project, key):
    return next(l for l in store.bom_lines(project) if l["key"] == key)


def _first_with_value(project):
    return next(l for l in store.bom_lines(project) if l.get("value"))


def test_important_mode_applies_a_routine_proposal_and_holds_an_ic(server, lte, monkeypatch):
    l = _first_with_value(lte)
    _agent_says(monkeypatch, [
        {"type": "bom.propose", "line": l["key"], "changes": {"value": "123k"}, "reason": "r"},
        {"type": "bom.propose", "line": "U99", "new": True, "changes": {"mpn": "NEWIC1", "package": "SOT-23"}},
    ])
    code, st = post(server, "/api/chat", {"text": "go"}, lte)
    assert code == 200
    by_line = {p["line"]: p for p in st["proposals"]}
    assert by_line[l["key"]]["status"] == "approved" and by_line[l["key"]]["decided_by"] == "auto"
    assert _bom(lte, l["key"])["value"] == "123k"
    assert by_line["U99"]["status"] == "pending"                       # an IC waits
    assert not any(x["key"] == "U99" for x in store.bom_lines(lte))
    # the log is the one an Approve click writes
    entry = [e for e in store.read_jsonl(store.pdir(lte) / "bom-log.jsonl") if e.get("proposal") == by_line[l["key"]]["id"]]
    assert entry and entry[0]["by"] == "agent-approved" and entry[0]["before"]["value"] == l["value"]


def test_ask_mode_keeps_every_proposal_pending(server, lte, monkeypatch):
    workspace.set_value("agent.autonomy", "ask")
    l = _first_with_value(lte)
    _agent_says(monkeypatch, [{"type": "bom.propose", "line": l["key"], "changes": {"value": "9k9"}}])
    _, st = post(server, "/api/chat", {"text": "go"}, lte)
    assert st["proposals"][-1]["status"] == "pending"
    assert _bom(lte, l["key"])["value"] == l["value"]


def test_auto_mode_applies_an_ic_but_never_an_order(server, lte, monkeypatch):
    workspace.set_value("agent.autonomy", "auto")
    _agent_says(monkeypatch, [{"type": "bom.propose", "line": "U98", "new": True, "changes": {"mpn": "ICX"}}])
    _, st = post(server, "/api/chat", {"text": "go"}, lte)
    assert st["proposals"][-1]["status"] == "approved"
    assert not store.may_auto_apply({"kind": "order"}, "auto")


def test_undo_restores_the_previous_bom_and_is_logged(server, lte):
    l = _first_with_value(lte)
    rec = store.propose_bom(lte, l["key"], {"value": "777k"}, reason="t")
    store.decide(lte, rec["id"], "approved")
    assert _bom(lte, l["key"])["value"] == "777k"
    n_before = len(store.read_jsonl(store.pdir(lte) / "bom-log.jsonl"))
    code, st = post(server, "/api/undo", {"id": rec["id"]}, lte)
    assert code == 200
    assert _bom(lte, l["key"])["value"] == l["value"]
    log = store.read_jsonl(store.pdir(lte) / "bom-log.jsonl")
    assert len(log) == n_before + 1 and log[-1]["by"] == "undo" and log[-1]["undoes"] == rec["id"]   # appended, not rewritten
    assert next(p for p in st["proposals"] if p["id"] == rec["id"])["status"] == "undone"
    code, body = post(server, "/api/undo", {"id": rec["id"]}, lte)
    assert code == 409 and "already undone" in body["error"]


def test_undo_of_a_new_line_removes_it_and_a_later_change_blocks_an_undo(server, lte):
    new = store.propose_bom(lte, "R90", {"value": "1k", "package": "0603"}, new=True)
    store.decide(lte, new["id"], "approved")
    assert any(x["key"] == "R90" for x in store.bom_lines(lte))
    later = store.propose_bom(lte, "R90", {"value": "2k"})
    store.decide(lte, later["id"], "approved")
    code, body = post(server, "/api/undo", {"id": new["id"]}, lte)
    assert code == 409 and "undo that later change first" in body["error"]
    assert post(server, "/api/undo", {"id": later["id"]}, lte)[0] == 200      # reverse order works
    assert _bom(lte, "R90")["value"] == "1k"
    assert post(server, "/api/undo", {"id": new["id"]}, lte)[0] == 200
    assert not any(x["key"] == "R90" for x in store.bom_lines(lte))


def test_undo_of_a_sheet_write_restores_the_sheet(server, lte):
    sid = store.sheet_ids(lte)[0]
    old = store.load_sheet(lte, sid)
    res = store.write_sheet_logged(lte, sid, {**old, "title": "changed by test"})
    assert res["ok"] and res["change"].startswith("s")
    assert store.load_sheet(lte, sid)["title"] == "changed by test"
    code, st = post(server, "/api/undo", {"id": res["change"]}, lte)
    assert code == 200 and store.load_sheet(lte, sid) == old
    assert any(h["id"] == res["change"] and h["status"] == "undone" for h in st["history"])


def test_batch_endpoint_applies_in_order_and_reports_each(server, lte):
    workspace.set_value("agent.autonomy", "ask")
    ids = [store.propose_bom(lte, f"R8{i}", {"value": f"{i}k"}, new=True)["id"] for i in range(3)]
    code, st = post(server, "/api/proposals/batch", {"ids": ids + ["pNOPE"], "decision": "approved"}, lte)
    assert code == 200
    assert [r["ok"] for r in st["results"]] == [True, True, True, False]
    assert all(any(x["key"] == f"R8{i}" for x in store.bom_lines(lte)) for i in range(3))
    _, st = post(server, "/api/proposals/batch", {"ids": ids[:1], "decision": "approved"}, lte)
    assert st["results"][0]["ok"] is False and "already" in st["results"][0]["error"]
    assert post(server, "/api/proposals/batch", {"ids": [], "decision": "approved"}, lte)[0] == 400
    rid = store.propose_bom(lte, "R85", {"value": "5k"}, new=True)["id"]
    _, st = post(server, "/api/proposals/batch", {"ids": [rid], "decision": "rejected"}, lte)
    assert st["results"][0]["ok"] and next(p for p in st["proposals"] if p["id"] == rid)["status"] == "rejected"
