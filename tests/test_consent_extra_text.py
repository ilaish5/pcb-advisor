"""F-E (ACCEPTANCE.md): a clear yes to the replace with extra text is a REAL grant; three bands decide the rest.
  grant    a clear affirmative to this action, trailing text allowed (a reason, thanks, a remark), unless a marker is attached to the action
  refuse   (no button) a no / stop / wait, a delay, the student doing it, a negation of the action
  confirm  (one click, restating what will happen) an exception or condition on the action, or what the rule cannot place (a doubt, a joke)
Deterministic closed word lists, no model. All phrasings here are written for this test; the visible corpus is read at run time."""
import json
import pathlib

import pytest

import serve

Q = "Replace the placement of the parts on the board? This wipes what is placed (a backup is kept). Answer yes/no."
QHE = "להחליף את מיקום הרכיבים בלוח? זה מוחק את מה שיש (נשמר גיבוי). כן/לא?"
QR = "Replace the routing on the board? This wipes the existing tracks (a backup is kept). Answer yes/no."


def band(phrase, kind="place", q=Q):
    return serve._replace_band(kind, {}, phrase, q)


def _granted(phrase, kind="place", q=Q):
    return not serve._replace_consent(kind, {}, phrase, q)


GRANT = [
    "yes", "yes, replace it, thanks", "yes please replace the placement", "yeah go ahead and replace the placement now", "sure, redo the placement",
    "yes, replace it, thanks a lot", "yes please replace the placement, I have a copy of my own", "yes, replace it, no problem at all",
    "yes, replace the placement, I do not mind losing it", "yes, replace it, nobody needs the old one, it is not good",
    "yes, replace it, I already did a few moves by hand and they can go", "yes replace it, a spare copy of the file is fine with me",
    "yes, redo the layout, the old one before this was rushed", "yes, replace it and then show me the new layout", "yes, replace it, after all that's why I asked",
    "yes, replace it. I'll look at the result afterwards", "yes, wipe it, it is not worth keeping", "yes, replace it, I'm done with the old one",
    "yes do it, replace the placement", "yes, replace the parts, the first try was bad", "yes, replace it, I know what it means", "yes, replace it, go for it",
    "yes, replace the placement, that's fine by me", "yes, replace it, the current placement makes no sense", "yes, go ahead and redo the whole placement for me",
    "yeah, wipe the current layout and place everything again", "ok, please replace it, I want a cleaner layout", "yes - replace the placement, the old one was just a test",
    "absolutely, yes, replace the current placement", "yes, replace it, I moved two parts by hand but they can go", "yes, thanks, without your help I would be lost",
    "yes, replace it, J1 looks fine as is", "yes, replace it, I will check the result later", "yes, replace it, tell me when it is done",
]
GRANT_HE = [
    "כן", "כן, תחליף", "כן, תחליף את המיקום בבקשה", "כן, תמקם את הרכיבים מחדש, המיקום הנוכחי צפוף מדי", "כן, תחליף את המיקום הקיים, הגיבוי מספיק לי",
    "כן כן, תחליף את המיקום, הישן היה רק ניסיון", "כן, תחליף את המיקום, הקודם לא היה טוב", "כן, תחליף, ואחר כך תראה לי", "כן, תחליף את המיקום, אני סומך עליך",
    "כן, תחליף, לא צריך את הישן", "כן, קדימה, תחליף את המיקום", "כן, תחליף את המיקום, אין בעיה", "כן, תחליף את המיקום, מה שיש לא טוב",
]
CONFIRM = [
    "yes, replace it, provided nothing near J1 moves", "yes, replace it, but only on the top side", "yes, replace it, minus the connectors", "yes, replace it, all but the crystal",
    "yes, replace it but keep the LEDs", "yes, replace it, apart from U4", "yes, replace it as long as J1 stays where it is", "yes, replace it assuming you keep the crystal near the MCU",
    "yes, replace it in case the DRC passes afterwards", "yes, replace it after I commit my changes", "yes, replace it, as soon as I get back", "yes, replace it without the LEDs",
    "yes, replace it, except the crystal", "yes, replace it, but only the connectors", "yes, replace it, but J2 and J3 stay exactly as placed", "yes, replace it, I'm sure about it unless the backup fails",
    "yes, replace it once the review is finished", "yes, replace it until I say otherwise", "yes replace it, only the resistors",
    # what the rule cannot place: a doubt, a joke (a known limit: irony is open-ended; the closed list below is all that is caught)
    "yes, replace it, though I'm not convinced", "yes, replace it, hmmm", "yes, replace it, not really", "yes, replace it? I guess", "yes, replace it, you wish",
    "yes, sure, replace it, what could possibly go wrong", "yeah right, replace it, as if", "yes, replace it, said no one ever", "yes, replace it, sure, and the moon is cheese",
]
CONFIRM_HE = [
    "כן, תחליף את המיקום, אבל לא את המחברים", "כן, תחליף, רק תשאיר את J1", "כן, תחליף את המיקום בלי הנגדים", "כן, תחליף את המיקום בתנאי שהמחבר נשאר בצד",
    "כן, תחליף את המיקום אחרי שאני אשמור עותק", "כן, תחליף את המיקום כשאני אחזור", "כן, תחליף רק את הקבלים", "כן, תחליף, אלא אם כן הגיבוי נכשל",
    "כן, תחליף את המיקום, חוץ מהקריסטל", "כן, תחליף את המיקום וגם תנתב מחדש", "כן, תחליף, נו באמת", "כן בטח, תחליף, כאילו",
]
REFUSE = [
    "yes, replace it... no, don't", "yes, replace it; well, no, not today", "yes, replace it, I'm kidding of course", "yes, replace it, I'll handle the moving",
    "yes, I'd rather do the replacing", "yes, replace it, the moving part is mine", "yes, replacing the placement is the last thing I want", "yes I read it; do not wipe anything",
    "yes, I understand, but no replacement please", "yes, the backup is fine; replacement is not", "yes, never replace my placement", "yes, replace it, but let me do the moving",
    "yes, the replacement is something I will take on", "yes, replace it; I'll be the one placing them", "yes, replace it, leave the actual moving to me",
    "yes replace it, no wait, only the resistors", "yes, replace it - no.", "yes, replace it, nope, changed course", "yes, replace it, hold on", "yes, replace it, not yet",
    "yes, replace it, maybe later", "yes, I want to redraw it", "yes, scratch that", "yes, redraw the schematic", "yes, add R5 to the BOM", "yes, replace it, I want you to wait",
    "yes, nothing should be replaced", "yes, replace none of it", "yes, the placement is not to be replaced", "yes, it will be replaced by me", "yes, replace it, but I want to do it by hand",
    "yes, I will replace the placement myself", "yes, let me replace it", "yes, replace it, changed my mind", "yes, replace it, only joking", "yes, replace it /s",
    "no", "No, stop", "stop", "wait, not now", "cancel that", "yes, replace it and also reroute everything",
]
REFUSE_HE = [
    "כן, הבנתי, אל תחליף כלום", "כן, אבל אסור לך להחליף את המיקום", "כן, אין צורך להחליף את המיקום", "כן, תחליף, את ההזזה אני אעשה", "כן, תחליף את המיקום, תן לי לעשות את זה",
    "כן, תחליף את המיקום, אני אזיז את החלקים", "כן, תחליף את המיקום. לא, עזוב", "כן, תחליף את המיקום, את ההזזה אעשה בעצמי", "כן, תחליף את המיקום, סתם בצחוק, לא",
    "כן, תחליף את המיקום, טעות שלי", "כן, תחליף את המיקום, התחרטתי", "כן, תחליף את המיקום. לא, רגע, רק את הנגדים", "לא", "עצור", "חכה רגע", "לא עכשיו", "כן, תחליף, לא באמת",
]


@pytest.mark.parametrize("phrase", GRANT)
def test_a_clear_yes_with_extra_text_is_a_real_grant(phrase):
    assert band(phrase) == "grant" and _granted(phrase)


@pytest.mark.parametrize("phrase", GRANT_HE)
def test_the_same_in_hebrew_is_a_real_grant(phrase):
    assert band(phrase, q=QHE) == "grant" and _granted(phrase, q=QHE)


@pytest.mark.parametrize("phrase", CONFIRM)
def test_an_exception_a_condition_or_a_doubt_on_the_action_is_a_confirm_never_a_grant(phrase):
    assert band(phrase) == "confirm" and not _granted(phrase)


@pytest.mark.parametrize("phrase", CONFIRM_HE)
def test_the_same_in_hebrew_is_a_confirm(phrase):
    assert band(phrase, q=QHE) == "confirm" and not _granted(phrase, q=QHE)


@pytest.mark.parametrize("phrase", REFUSE)
def test_a_negation_delay_self_do_or_stop_is_never_a_grant_and_gets_no_button(phrase):
    assert band(phrase) == "refuse" and not _granted(phrase)
    meta = {}
    assert not serve.replace_confirm("place", {"replace": True}, phrase, meta, None, Q) and "confirm" not in meta


@pytest.mark.parametrize("phrase", REFUSE_HE)
def test_the_same_in_hebrew_is_a_refusal(phrase):
    assert band(phrase, q=QHE) == "refuse" and not _granted(phrase, q=QHE)


def test_a_route_replace_is_read_the_same_way():
    assert band("yes, replace the routing, the old tracks are a mess", "route", QR) == "grant"
    assert band("yes, reroute the board from scratch please", "route", QR) == "grant"
    assert band("כן, תנתב מחדש את הלוח", "route", QR) == "grant"
    assert band("yes, replace the routing but keep the clock net", "route", QR) == "confirm"


def test_the_confirm_restates_the_action_and_says_kept_parts_are_replaced_too(empty):
    from test_unverified_pins import _sheet
    _sheet(empty)
    n = serve._parts_count(empty)
    assert n > 0
    m = {}
    assert serve.replace_confirm("place", {"replace": True}, "yes, replace it but keep the LEDs", m, empty, Q)
    q = m["confirm"]["question"]
    assert f"all {n} parts" in q and "including what you asked to keep" in q and m["confirm"]["yes"] and m["confirm"]["no"]
    m = {}
    assert serve.replace_confirm("place", {"replace": True}, "yes, replace it after I commit", m, empty, Q)
    assert "Replace the whole placement" in m["confirm"]["question"] and "including what you asked" not in m["confirm"]["question"]
    m = {}
    assert serve.replace_confirm("place", {"replace": True}, "כן, תחליף את המיקום בלי הנגדים", m, empty, QHE)
    assert str(n) in m["confirm"]["question"] and "גם מה שביקשת להשאיר" in m["confirm"]["question"]
    m = {}
    assert not serve.replace_confirm("place", {"replace": True}, "yes, replace it, thanks", m, empty, Q)        # a grant needs no confirm


def test_the_click_on_the_confirm_is_read_as_the_answer_to_it():
    m = {}
    assert serve.replace_confirm("place", {"replace": True}, "yes, replace it after I commit", m, None, Q)
    c = m["confirm"]
    assert not serve._replace_consent("place", {}, c["yes"], "Some text.\n\n" + c["question"])
    assert serve._replace_consent("place", {}, c["no"], "Some text.\n\n" + c["question"])


@pytest.mark.parametrize("phrase", ["redraw sheet 01 and also add R5 to the BOM", "yes, show me the preview", "ok, let me check", "thanks", "please"])
def test_a_yes_to_another_job_or_a_bare_thanks_is_not_a_grant(phrase):
    assert not _granted(phrase)


def test_the_dead_keyword_blocklists_are_gone():
    for name in ("_stance_cancelled", "_SARCASM", "_COND_ALL", "_SELF_FUT", "_plain_grant", "_bare_yes_only", "_AFFIRM_EN", "_BARE_YES", "_NEG_ALL", "_CONTRAST"):
        assert not hasattr(serve, name), name


def test_the_visible_f_e_corpus_decides_as_the_spec_says():
    """Read from tests/acceptance/corpora when the test runs (not copied): every affirmative with extra text is a REAL grant (not a confirm),
    no negative is ever granted."""
    f = pathlib.Path(__file__).resolve().parent / "acceptance" / "corpora" / "fe_consent.json"
    if not f.exists():
        pytest.skip("the visible corpus is not in this checkout")
    d = json.loads(f.read_text(encoding="utf-8"))
    assert all(_granted(p, q=d["question"]) for p in d["affirmative"])
    assert not any(_granted(p, q=d["question"]) for p in d["negative"])
