"""An agent's idea.propose never loses a requirement (E2E 2026-11-25: a regulator line replaced the USB-C one)."""
import serve
import store

USB = "USB-C 5 V only, 5.1k pull-downs on CC1 and CC2"
LDO = "AP2112K-3.3 LDO makes 3V3 from VBUS"


def rows(project):
    return [(i["topic"], i["text"]) for i in store.load_idea_working(project)["agreed"]]


def test_another_text_under_the_same_topic_keeps_both(empty):
    store.propose_idea(empty, "Power", USB)
    store.propose_idea(empty, "MCU", "STM32G0")
    store.propose_idea(empty, "Power", LDO)
    assert rows(empty) == [("Power", USB), ("Power (2)", LDO), ("MCU", "STM32G0")]
    store.propose_idea(empty, "Power", "Fuse on VBUS")
    assert [t for t, _ in rows(empty)] == ["Power", "Power (2)", "Power (3)", "MCU"]


def test_a_repeat_changes_nothing(empty):
    store.propose_idea(empty, "Power", USB)
    store.propose_idea(empty, "Power", LDO)
    before = rows(empty)
    store.propose_idea(empty, "Power", USB.upper() + ".")
    store.propose_idea(empty, "Power", LDO)
    assert rows(empty) == before


def test_a_text_that_says_all_of_the_old_one_updates_its_row(empty):
    store.propose_idea(empty, "Power", USB)
    store.propose_idea(empty, "Power", LDO)
    store.propose_idea(empty, "Power", LDO + ". 600 mA at least")
    assert rows(empty) == [("Power", USB), ("Power (2)", LDO + ". 600 mA at least")]


def test_words_inside_another_sentence_are_not_the_old_requirement(empty):
    for old, new in (("USB DFU", "No USB DFU, SWD only"), ("5 V", "5.5 V"), ("Li-ion", "Li-ion is out: 2x AA")):
        store.propose_idea(empty, old, old)
        store.propose_idea(empty, old, new)
        assert (old, old) in rows(empty) and (f"{old} (2)", new) in rows(empty)


def test_confirming_an_assumption_updates_it(empty):
    store.propose_idea(empty, "Power", "1S Li-ion (assumed)")
    store.propose_idea(empty, "Power", "1S Li-ion")
    assert rows(empty) == [("Power", "1S Li-ion")]


def test_replace_changes_the_row_and_keeps_the_old_text(empty):
    store.propose_idea(empty, "Power", USB)
    store.propose_idea(empty, "Power", "2x AA", replace=True)
    item = store.load_idea_working(empty)["agreed"][0]
    assert rows(empty) == [("Power", "2x AA")] and item["prev_text"] == USB


def test_a_long_topic_stays_within_the_limit(empty):
    topic = "T" * 60
    store.propose_idea(empty, topic, "a")
    store.propose_idea(empty, topic, "b")
    new = rows(empty)[1][0]
    assert len(new) == 60 and new.endswith(" (2)")


def test_save_and_revert_and_the_students_edit_still_work(empty):
    store.propose_idea(empty, "Power", USB)
    store.save_idea_from_draft(empty)
    store.propose_idea(empty, "Power", LDO)
    assert store.idea_draft_info(empty)["marks"]["items"] == {"Power (2)": "new"}
    store.revert_idea_draft(empty)
    assert rows(empty) == [("Power", USB)]
    store.propose_idea(empty, "Power", LDO)
    store.update_idea_item(empty, index=1, old_topic="Power (2)", topic="Regulator", text=LDO)
    store.save_idea_from_draft(empty)
    assert rows(empty) == [("Power", USB), ("Regulator", LDO)]


def test_the_action_replaces_only_on_the_students_own_words(empty):
    store.propose_idea(empty, "Power", USB)
    act = {"type": "idea.propose", "topic": "Power", "text": LDO, "replace": True, "student_said": "change the power"}
    applied, _, refused = serve.apply_actions(empty, [act], last_user="which regulator?")
    assert not refused and applied == ['idea.propose:Power (added as "Power (2)"; "Power" is unchanged)']
    assert rows(empty)[0] == ("Power", USB) and not serve.warned_map(applied)
    applied, _, _ = serve.apply_actions(empty, [{**act, "text": "2x AA"}], last_user="please change the power to 2x AA")
    assert applied == ["idea.propose:Power"] and rows(empty)[0] == ("Power", "2x AA")
