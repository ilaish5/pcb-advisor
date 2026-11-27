"""F-E: a yes that opens the message grants replace even with more words after it; a yes taken back never does."""
import json
import pathlib

import pytest

import serve

CORPUS = pathlib.Path(__file__).resolve().parent / "acceptance" / "corpora" / "fe_consent.json"
Q = "Replace the placement of the parts on the board? This wipes what is placed (a backup is kept). Answer yes/no."


def _granted(phrase):
    return not serve._replace_consent("place", {}, phrase, Q)


@pytest.mark.skipif(not CORPUS.is_file(), reason="corpus not in this checkout")
def test_visible_corpus_affirmatives_granted_and_negatives_refused():
    c = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert [p for p in c["affirmative"] if not _granted(p)] == []
    assert [p for p in c["negative"] if _granted(p)] == []


@pytest.mark.parametrize("phrase", [
    "yes, replace it, I saved my own copy already",
    "yes please replace it, the old placement was only a test",
    "sure, redo the placement, the current one is not mine",
])
def test_extra_text_after_a_yes_is_consent(phrase):
    assert _granted(phrase)


@pytest.mark.parametrize("phrase", [
    "yes, but I will do it myself",
    "yes, replace it but keep my routing",
    "yes but actually let me look first",
    "yes, replace it if the backup works",
    "yes replace it, no wait",
    "yes, do not replace the board",
    "yes, replace it. Or should I do it by hand?",
    "yes, add R5 to the BOM",
])
def test_a_yes_taken_back_is_not_consent(phrase):
    assert not _granted(phrase)


def test_no_yes_without_the_question():
    assert serve._replace_consent("place", {}, "yes, replace it, thanks a lot for the help", "Here is the placement.")
