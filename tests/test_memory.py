"""
What a conversation remembers.

A memory file is the one place where losing a byte loses something nobody can
get back: the transcript still has the words, but nothing else records that a
student ruled an option out three weeks ago and why. So the degradation rules
matter more than the happy path - what it does when the engine hands back
something odd, and what it drops when it truly cannot fit.
"""
import session


SECTIONS = session.SECTIONS


def test_a_new_conversation_starts_with_all_four_headings(home):
    sid = session.create("p", title="first")
    text = session.read_memory("p", sid)
    for name in SECTIONS:
        assert f"## {name}" in text


def test_the_first_thing_the_student_says_names_the_conversation(home):
    sid = session.create("p")
    session.append("p", sid, {"role": "user", "text": "a freezer door alarm, 2xAA"})
    row = next(r for r in session.list_all("p") if r["id"] == sid)
    assert row["title"].startswith("a freezer door alarm")


def test_the_conversation_list_carries_the_last_thing_said(home):
    sid = session.create("p")
    assert next(r for r in session.list_all("p") if r["id"] == sid)["last"] is None       # nothing yet
    session.append("p", sid, {"role": "user", "text": "why   this\n  connector?"})
    session.append("p", sid, {"role": "agent", "text": "Because it is rated for 3 A.", "error": True})
    session.append("p", sid, {"role": "agent", "text": "Updated.", "decision": "approved", "proposal": "p1"})
    session.append("p", sid, {"role": "ctx", "part": {"ref": "J1"}})
    row = next(r for r in session.list_all("p") if r["id"] == sid)
    assert row["messages"] == 4
    assert row["last"] == {"role": "user", "text": "why this connector?"}      # an error, a decision note and a card are not "said"
    session.append("p", sid, {"role": "agent", "text": "x" * 500})
    assert len(next(r for r in session.list_all("p") if r["id"] == sid)["last"]["text"]) == 200


def test_a_later_message_does_not_rename_it(home):
    sid = session.create("p")
    session.append("p", sid, {"role": "user", "text": "first thing"})
    session.append("p", sid, {"role": "user", "text": "second thing"})
    row = next(r for r in session.list_all("p") if r["id"] == sid)
    assert row["title"] == "first thing"


# ---------------------------------------------------------------- normalize
#
# An engine narrates. "Here is the updated memory, 443 characters:" arrives
# attached to the document, and counting it against the limit pushes real
# content out to make room for chatter. The file is rebuilt from the headings
# we recognise, so anything else is dropped by construction.

def test_engine_chatter_around_the_document_is_dropped():
    out = session.normalize(
        "Sure! Here is the rewritten memory file:\n\n"
        "## The student's situation\n- 30x20 mm enclosure\n\n"
        "Let me know if you would like me to change anything.")
    assert "Sure!" not in out and "Let me know" not in out
    assert "- 30x20 mm enclosure" in out


def test_a_section_the_engine_invented_is_dropped():
    out = session.normalize("## Notes\n- something\n\n"
                            "## Open promises\n- check the connector rating")
    assert "## Notes" not in out
    assert "- check the connector rating" in out


def test_all_four_headings_survive_even_when_empty():
    out = session.normalize("## Open promises\n- one thing")
    for name in SECTIONS:
        assert f"## {name}" in out


def test_a_bare_line_is_kept_when_a_section_has_no_bullets():
    out = session.normalize("## The student's situation\nbudget is fifteen dollars")
    assert "- budget is fifteen dollars" in out


def test_a_trailing_comment_loses_to_the_real_bullets():
    """Chatter that lands inside a section, after content, is the common shape."""
    out = session.normalize("## The student's situation\n- 30x20 mm\n"
                            "That is everything I could find.")
    assert "- 30x20 mm" in out
    assert "everything I could find" not in out


# ---------------------------------------------------------------- fit
#
# Last resort only: the engine is asked twice to compress before this runs.
# It degrades in whole units, because half a sentence about why something was
# ruled out is worse than no sentence at all.

def test_a_file_within_the_limit_is_left_alone():
    text = session.normalize("## Open promises\n- one")
    out, trimmed = session.fit(text, limit=4000)
    assert out == text and trimmed is False


def test_it_drops_whole_sections_from_the_least_costly_end():
    text = session.normalize(
        "## The student's situation\n- " + "a" * 200 + "\n"
        "## Ruled out, and why\n- " + "b" * 200 + "\n"
        "## Open promises\n- " + "c" * 200 + "\n"
        "## How they work\n- " + "d" * 200)
    out, trimmed = session.fit(text, limit=500)
    assert trimmed
    assert "a" * 200 in out                  # the costliest to lose is kept
    assert "d" * 200 not in out              # the least costly goes first


def test_it_never_cuts_a_line_in_half_while_whole_lines_remain():
    text = session.normalize("## The student's situation\n"
                             + "\n".join(f"- fact number {i}" for i in range(40)))
    out, _ = session.fit(text, limit=300)
    body = [l for l in out.splitlines() if l.startswith("- ")]
    assert body, "something survived"
    assert all(l.endswith(tuple("0123456789")) for l in body), out


def test_it_keeps_the_heading_even_when_the_bullet_will_not_fit():
    """A file stripped back to its header has no structure for the next rewrite
    to merge into, so the section is not shortened - it is gone."""
    text = session.normalize("## The student's situation\n- " + "x" * 400)
    out, _ = session.fit(text, limit=200)
    assert "## The student's situation" in out
    assert len(out) <= 200


def test_the_limit_is_honoured_whatever_it_is():
    """The limit is described to the engine as hard, so it has to be hard here
    too - including when the header alone is already over it."""
    text = session.normalize("## The student's situation\n- " + "x" * 400
                             + "\n## Open promises\n- " + "y" * 400)
    for limit in (2000, 600, 300, 200, 150, 90, 40):
        out, _ = session.fit(text, limit=limit)
        assert len(out) <= limit, (limit, len(out))


def test_a_sentence_is_only_cut_when_nothing_whole_can_be_dropped():
    text = session.normalize("## The student's situation\n- " + "x" * 400)
    kept, _ = session.fit(text, limit=200)
    assert "…" not in kept          # the over-long bullet went whole
    cut, _ = session.fit(text, limit=60)
    assert cut.rstrip().endswith("…")   # nothing left to drop; marked as cut


# ---------------------------------------------------------------- compaction

def test_compaction_comes_due_after_the_configured_number_of_messages(home,
                                                                     monkeypatch):
    import workspace
    monkeypatch.setitem(workspace.load()["agent"], "memory_every", 3)
    sid = session.create("p")
    for i in range(2):
        session.append("p", sid, {"role": "user", "text": f"m{i}"})
    assert session.due_for_compaction("p", sid)[0] is False
    session.append("p", sid, {"role": "user", "text": "m2"})
    assert session.due_for_compaction("p", sid)[0] is True


def test_only_messages_since_the_last_rewrite_are_sent_for_compaction(home):
    sid = session.create("p")
    for i in range(4):
        session.append("p", sid, {"role": "user", "text": f"old{i}"})
    session.mark_compacted("p", sid)
    session.append("p", sid, {"role": "user", "text": "new"})
    fresh = session.messages_since_compaction("p", sid)
    assert [m["text"] for m in fresh] == ["new"]


# ---------------------------------------------------------------- sessions

def test_conversations_are_separate_files_and_deleting_one_is_a_file_operation(home):
    a = session.create("p", title="power")
    b = session.create("p", title="layout")
    assert a != b
    session.append("p", a, {"role": "user", "text": "only in a"})
    assert session.load_chat("p", b) == []
    session.delete("p", a)
    assert not session.chat_path("p", a).exists()
    assert not session.memory_path("p", a).exists()
    assert [r["id"] for r in session.list_all("p")] == [b]


def test_a_session_id_cannot_escape_the_project_folder(home):
    path = session.chat_path("p", "../../etc/passwd")
    assert ".." not in str(path)
