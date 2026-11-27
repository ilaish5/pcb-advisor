"""F-E: a yes that opens the message grants replace even with a few more words after it; every way of taking the yes back refuses.
The rule is grammatical (negation, reversal, stop, hedge, condition, question, doing it oneself, another kind of work), not a list of phrases.
All phrasings here are written for this test."""
import pytest

import serve

Q = "Replace the placement of the parts on the board? This wipes what is placed (a backup is kept). Answer yes/no."


def _granted(phrase, kind="place", q=Q):
    return not serve._replace_consent(kind, {}, phrase, q)


@pytest.mark.parametrize("phrase", [
    "yes, replace it, thanks a lot",
    "yes please replace the placement, I have a copy of my own",
    "yeah go ahead and replace the placement now",
    "sure, redo the placement",
])
def test_a_clear_yes_with_extra_words_is_consent(phrase):
    assert _granted(phrase)


@pytest.mark.parametrize("phrase", [
    # negation
    "yes, nothing should be replaced",
    "yes, replace none of it",
    "yes, the placement is not to be replaced",
    "yes, never replace the placement",
    "yes, the old placement will be kept, redo it",
    # the student does it
    "yes, it will be replaced by me",
    "yes, replace it, but I want to do it by hand",
    "yes, I will replace the placement myself",
    "yes, let me replace it",
    # reversal / second thoughts
    "yes, replace it, changed my mind",
    "yes, replace it but keep my routing",
    "yes replace it, actually wait",
    "yes, replace it if the backup works",
    # question
    "yes, replace it. Or should I do it by hand?",
    # other kind of work
    "yes, redraw the schematic",
    "yes, add R5 to the BOM",
    # Hebrew: yes then taken back, or done by hand
    "כן, תחליף את המיקום אבל בעצם אני אעשה את זה ידנית",
    "כן, תחליף את המיקום, התחרטתי",
])
def test_a_yes_taken_back_or_aimed_elsewhere_is_not_consent(phrase):
    assert not _granted(phrase)


def test_a_yes_to_another_question_is_not_consent():
    other = "Draw the schematic again? This wipes the sheet (a backup is kept). Answer yes/no."
    assert not _granted("yes please replace it, thanks a lot, that sounds good to me", kind="place", q=other)


def test_no_yes_without_the_question():
    assert not _granted("yes, replace it, thanks a lot for all the help today", q="Here is the placement.")
