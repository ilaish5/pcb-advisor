"""F-E: a replace is granted only to a plain affirmative and nothing more (a whitelist). A yes with extra words is NOT a grant, but it never
costs more than one click: the chat offers a confirm that says what will happen. Every way of taking the yes back is never a grant.
All phrasings here are written for this test."""
import pytest

import serve

Q = "Replace the placement of the parts on the board? This wipes what is placed (a backup is kept). Answer yes/no."


def _granted(phrase, kind="place", q=Q):
    return not serve._replace_consent(kind, {}, phrase, q)


def _confirm(phrase, kind="place"):
    meta = {}
    return serve.replace_confirm(kind, {"replace": True}, phrase, meta) and meta["confirm"]


@pytest.mark.parametrize("phrase", [
    "yes, replace it, thanks",
    "yes please replace the placement",
    "yeah go ahead and replace the placement now",
    "sure, redo the placement",
    "כן, תחליף את המיקום בבקשה",
])
def test_a_plain_yes_is_granted_at_once(phrase):
    assert _granted(phrase)


@pytest.mark.parametrize("phrase", [
    "yes, replace it, thanks a lot",
    "yes please replace the placement, I have a copy of my own",
    # reassurance and a judgement of the old work are not a negation of the action
    "yes, replace it, no problem at all",
    "yes, replace the placement, I do not mind losing it",
    "yes, replace it, nobody needs the old one, it is not good",
    "yes, replace it, I already did a few moves by hand and they can go",
    "yes replace it, a spare copy of the file is fine with me",
    "כן, תחליף את המיקום, אין בעיה",
    "כן, תחליף את המיקום, מה שיש לא טוב",
])
def test_a_yes_with_extra_words_is_not_a_grant_but_costs_one_click(phrase):
    assert not _granted(phrase) and _confirm(phrase)


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
    # a joke, a doubt or a second thought after the yes
    "yes, replace it, only joking",
    "yes, replace it /s",
    "yes, replace it, hmm, let me rethink",
    "yes, replace the placement, scrap that",
    "yes, replace it, I take it back",
    "yes, replace it, oops, that was a slip",
    "yes, replace it, though",
    "yes, replace it, but only the connectors",
    "yes, replace it, except the crystal",
    "כן, תחליף את המיקום, סתם בצחוק, לא",
    "כן, תחליף את המיקום, טעות שלי",
    "כן, תחליף את המיקום, אני אסדר את זה בעצמי אחר כך",
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


def test_the_visible_f_e_corpus_decides_the_same_way():
    """Read from tests/acceptance/corpora when the test runs (not copied): every affirmative is granted or confirmed with one click, no negative is ever granted."""
    import json
    import pathlib
    f = pathlib.Path(__file__).resolve().parent / "acceptance" / "corpora" / "fe_consent.json"
    if not f.exists():
        pytest.skip("the visible corpus is not in this checkout")
    d = json.loads(f.read_text(encoding="utf-8"))
    assert all(_granted(p, q=d["question"]) or _confirm(p) for p in d["affirmative"])       # a grant, or the one-click confirm: never a silent refusal
    assert not any(_granted(p, q=d["question"]) for p in d["negative"])
