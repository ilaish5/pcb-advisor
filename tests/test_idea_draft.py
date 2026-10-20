"""The idea draft: agent and student edits go into a draft, Save makes it the idea, Revert drops it."""
import json

import store
from test_server import get, post, server  # noqa: F401  (the fixture and the two helpers)


def test_old_projects_without_a_draft_load_unchanged(lte):
    assert not store.has_idea_draft(lte)
    assert store.load_idea_working(lte) == store.load_idea(lte)
    assert store.idea_draft_info(lte)["active"] is False


def test_edits_go_to_the_draft_and_the_saved_idea_stays(empty):
    store.propose_idea(empty, "Power", "Li-ion", by="agent")
    store.set_idea_goal(empty, "A sensor node", by="student")
    assert store.load_idea(empty)["agreed"] == [] and store.load_idea(empty)["goal"] == ""
    w = store.load_idea_working(empty)
    assert w["agreed"][0]["topic"] == "Power" and w["goal"] == "A sensor node"
    assert store.idea_draft_info(empty)["changes"] == 2


def test_diagram_edits_join_the_draft(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "mcu", "text": "MCU"}])
    assert not store.load_idea(empty)["diagram"]["shapes"]
    assert store.load_idea_working(empty)["diagram"]["shapes"][0]["id"] == "mcu"
    store.undo_diagram(empty)
    assert not store.has_idea_draft(empty)          # back to the saved idea: nothing left to save


def test_save_makes_the_draft_the_idea_with_one_version(empty):
    store.propose_idea(empty, "Power", "Li-ion", by="student")
    store.save_idea_from_draft(empty)
    assert store.load_idea(empty)["agreed"][0]["topic"] == "Power"
    assert not store.has_idea_draft(empty)
    versions = store.idea_versions(empty)
    assert versions[-1]["n"] == len(versions) and "1 change" in versions[-1]["summary"]
    assert store.idea_draft_info(empty)["active"] is False


def test_revert_goes_back_to_the_saved_version(empty):
    store.propose_idea(empty, "Power", "Li-ion", by="student")
    store.save_idea_from_draft(empty)
    store.propose_idea(empty, "USB", "Type-C", by="student")
    assert len(store.load_idea_working(empty)["agreed"]) == 2
    assert store.revert_idea_draft(empty) is True
    assert [i["topic"] for i in store.load_idea_working(empty)["agreed"]] == ["Power"]
    assert store.revert_idea_draft(empty) is False


def test_history_keeps_at_least_ten_versions_and_restore_lands_in_the_draft(empty):
    for i in range(12):
        store.propose_idea(empty, f"T{i}", "x", by="student")
        store.save_idea_from_draft(empty)
    versions = store.idea_versions(empty)
    assert len(versions) >= 10
    n = versions[-3]["n"]
    store.restore_idea_version(empty, n)
    assert store.has_idea_draft(empty) and len(store.load_idea(empty)["agreed"]) == 12   # saved untouched
    assert len(store.load_idea_working(empty)["agreed"]) == 10
    try:
        store.restore_idea_version(empty, 9999)
        assert False
    except KeyError:
        pass


def test_confirm_saves_the_draft_first_and_keeps_the_saved_idea_what_downstream_reads(empty):
    store.propose_idea(empty, "Power", "Li-ion", by="agent")          # proposed, in the draft
    assert store.load_idea(empty)["confirmed"] is False
    store.confirm_idea(empty)
    saved = store.load_idea(empty)
    assert saved["confirmed"] and saved["agreed"][0]["status"] == "confirmed"
    assert not store.has_idea_draft(empty)


def _legacy(project, *items, goal=None):
    """Proposed items as an old project (before the draft) stored them."""
    idea = store.load_idea(project)
    idea["agreed"] += [{"topic": t, "text": x, "by": "agent", "status": "proposed", "ts": store.now()} for t, x in items]
    if goal is not None:
        idea.update(goal=goal, goal_by="agent", goal_status="proposed", goal_prev={"text": "", "by": "student"})
    store.save_idea(project, idea)


def test_the_agents_requirements_go_straight_into_the_draft(empty):
    store.propose_idea(empty, "Power", "Li-ion", by="agent")
    w = store.load_idea_working(empty)
    assert w["agreed"][0]["status"] == "confirmed" and w["agreed"][0]["by"] == "agent"
    assert store.load_idea(empty)["agreed"] == [], "the saved idea waits for Save"
    assert store.idea_draft_info(empty)["marks"]["items"] == {"Power": "new"}
    store.save_idea_from_draft(empty)
    store.propose_idea(empty, "Power", "2x AA", by="agent")
    assert store.idea_draft_info(empty)["marks"]["items"] == {"Power": "changed"}


def test_accept_all_and_dismiss_all(empty):
    _legacy(empty, ("Power", "Li-ion"), ("USB", "Type-C"))
    store.accept_all_proposed(empty, accept=True)
    assert {i["status"] for i in store.load_idea_working(empty)["agreed"]} == {"confirmed"}
    store.save_idea_from_draft(empty)
    _legacy(empty, ("RF", "868 MHz"), goal="A node")
    store.accept_all_proposed(empty, accept=False)
    w = store.load_idea_working(empty)
    assert [i["topic"] for i in w["agreed"]] == ["Power", "USB"] and w["goal"] == ""


def test_a_torn_draft_file_falls_back_to_the_saved_idea(empty):
    store.propose_idea(empty, "Power", "x", by="student")
    store.idea_draft_path(empty).write_text("{ not json", encoding="utf-8")
    assert store.load_idea_working(empty) == store.load_idea(empty)


def test_endpoints_save_revert_restore_confirm_and_accept_all(server, empty):  # noqa: F811
    code, st = post(server, "/api/idea/item", {"topic": "Power", "text": "Li-ion"}, empty)
    assert code == 200 and st["idea_draft"]["active"] and st["idea_draft"]["changes"] == 1
    assert st["idea"]["agreed"][0]["topic"] == "Power"
    code, st = post(server, "/api/idea/draft/revert", {}, empty)
    assert st["idea"]["agreed"] == [] and not st["idea_draft"]["active"]
    code, err = post(server, "/api/idea/confirm", {}, empty)
    assert code == 400 and "requirement" in err["error"]
    post(server, "/api/idea/item", {"topic": "Power", "text": "Li-ion"}, empty)
    code, st = post(server, "/api/idea/draft/save", {}, empty)
    assert not st["idea_draft"]["active"] and st["idea_draft"]["versions"]
    n = st["idea_draft"]["versions"][0]["n"]
    post(server, "/api/idea/item", {"topic": "USB", "text": "C"}, empty)
    code, st = post(server, "/api/idea/version/restore", {"n": n}, empty)
    assert code == 200 and len(st["idea"]["agreed"]) == 1
    code, err = post(server, "/api/idea/version/restore", {"n": 999}, empty)
    assert code == 404
    store.propose_idea(empty, "RF", "868", by="agent")
    code, st = post(server, "/api/idea/items/accept-all", {}, empty)
    assert all(i["status"] == "confirmed" for i in st["idea"]["agreed"])
    code, st = post(server, "/api/idea/confirm", {}, empty)
    assert code == 200 and st["idea"]["confirmed"] and not st["idea_draft"]["active"]
    assert json.loads((store.pdir(empty) / "idea.json").read_text())["confirmed"] is True


def test_idea_ready_action_and_failed_quote_downgrade(empty):
    import serve
    store.propose_idea(empty, "Power", "x", by="agent")
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.ready"}])
    assert applied == ["idea.ready"] and not refused
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.confirm", "student_said": "nope"}], last_user="hi")
    assert applied == ["idea.ready"] and not refused and not store.load_idea(empty)["confirmed"]


def test_the_ui_has_the_draft_bar_accept_all_and_the_chat_confirm_button():
    import pathlib
    ui = pathlib.Path(__file__).resolve().parent.parent / "ui" / "js"
    idea = (ui / "views" / "idea.js").read_text(encoding="utf-8")
    chat = (ui / "chat.js").read_text(encoding="utf-8")
    for needle in ("act: 'draft-save'", "act: 'draft-revert'", "act: 'accept-all'", "act: 'dismiss-all'",
                   "/api/idea/draft/save", "/api/idea/draft/revert", "/api/idea/items/accept-all", "since your last save"):
        assert needle in idea, needle
    assert "disabled: !items.length, title: why" in idea            # Confirm needs a requirement, not an empty proposals list
    assert "idea.ready" in chat and "chat-confirm-idea" in chat


def test_a_twice_escaped_line_break_in_a_diagram_label_becomes_a_line_break(empty):
    store.apply_diagram_edit(empty, [{"op": "add_shape", "id": "bat", "text": "Coin cell\\nCR2032"}])
    shape = store.load_idea_working(empty)["diagram"]["shapes"][0]
    assert shape["text"] == "Coin cell\nCR2032"
    assert store.idea_draft_info(empty)["marks"]["goal"] is False
    store.set_idea_goal(empty, "A sensor.", by="agent")
    assert store.idea_draft_info(empty)["marks"]["goal"] == "new"
