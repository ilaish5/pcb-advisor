"""R2 / W5: an assumption is confirmed only by the student on that item; a save that changes an agreed item reopens the confirmation."""
import store


def _idea(project, items):
    idea = store.load_idea_working(project)
    idea["agreed"] = items
    store.save_idea_draft(project, idea)


def _agreed(project):
    return {i["topic"]: i for i in store.load_idea_working(project)["agreed"]}


def test_an_assumed_item_is_not_confirmed_by_confirm_idea_or_accept_all(empty):
    _idea(empty, [{"topic": "Power", "text": "USB-C only", "status": "proposed", "by": "agent"},
                  {"topic": "Clock", "text": "LSE for the RTC (assumed)", "status": "proposed", "by": "agent"},
                  {"topic": "Flag", "text": "no battery", "status": "proposed", "by": "agent", "assumed": True}])
    store.accept_all_proposed(empty)
    a = _agreed(empty)
    assert a["Power"]["status"] == "confirmed" and a["Clock"]["status"] == "proposed" and a["Flag"]["status"] == "proposed"
    store.confirm_idea(empty)
    a = _agreed(empty)
    assert a["Clock"]["status"] == "proposed" and a["Flag"]["status"] == "proposed"


def test_the_student_confirming_that_item_confirms_it_and_records_who(empty):
    _idea(empty, [{"topic": "Clock", "text": "LSE for the RTC (assumed)", "status": "proposed", "by": "agent"}])
    store.confirm_idea_item(empty, topic="Clock")
    c = _agreed(empty)["Clock"]
    assert c["status"] == "confirmed" and c["by"] == "student"


def test_a_save_that_changes_an_agreed_item_after_confirm_says_changed_since_confirm(empty):
    _idea(empty, [{"topic": "Power", "text": "USB-C only", "status": "confirmed", "by": "student"}])
    store.confirm_idea(empty)
    assert not store.load_idea(empty).get("changed_since_confirm")
    idea = store.load_idea_working(empty)
    idea["agreed"][0]["text"] = "USB-C and a 1S battery"
    store.save_idea_draft(empty, idea)
    store.save_idea_from_draft(empty)
    saved = store.load_idea(empty)
    assert saved["confirmed"] and saved["changed_since_confirm"] is True
    store.confirm_idea(empty)
    assert not store.load_idea(empty).get("changed_since_confirm")          # confirmed again


def test_a_no_op_save_keeps_the_idea_confirmed(empty):
    _idea(empty, [{"topic": "Power", "text": "USB-C only", "status": "confirmed", "by": "student"}])
    store.confirm_idea(empty)
    idea = store.load_idea_working(empty)
    idea["goal"] = idea.get("goal", "") + " "          # a save that changes no agreed item
    store.save_idea_draft(empty, idea)
    store.save_idea_from_draft(empty)
    assert not store.load_idea(empty).get("changed_since_confirm")
