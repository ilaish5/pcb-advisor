"""R5 review 4: consent is a whitelist (a plain yes grants, an explicit no refuses, everything else gets a one-click confirm that restates
the action); evidence is a readable PDF of this part matched by token; a re-routed routed board says it is still routed; the kinds of a
rejection are ordered and all listed; a split paragraph keeps its spaces."""
import json
import pathlib

import pytest

import board_results
import pin_decisions
from test_unverified_pins import _sheet

ROOT = pathlib.Path(__file__).resolve().parent.parent
Q = "Replace the board's parts and copper? This wipes what is there (a backup is kept). Answer yes/no."
QHE = "להחליף את מיקום הרכיבים בלוח? זה מוחק את מה שיש (נשמר גיבוי). כן/לא?"
QR = "Replace the routing on the board? This wipes the existing tracks (a backup is kept). Answer yes/no."


def _granted(text, q=Q, kind="place"):
    import serve
    return not serve._replace_consent(kind, {}, text, q)


def _confirm(text, kind="place", project=None, **a):
    import serve
    meta = {}
    return meta["confirm"] if serve.replace_confirm(kind, {"replace": True, **a}, text, meta, project) else None


# ---------------------------------------------------------------- 1 consent: a whitelist
@pytest.mark.parametrize("text,q,kind", [
    ("yes", Q, "place"), ("Yes, replace it", Q, "place"), ("yes please, replace the placement", Q, "place"), ("yep, go ahead", Q, "place"),
    ("sure, redo the layout", Q, "place"), ("ok, replace it", Q, "place"), ("absolutely, yes, replace the current placement", Q, "place"),
    ("כן", QHE, "place"), ("כן, תחליף", QHE, "place"), ("בסדר, תחליף את המיקום בבקשה", QHE, "place"), ("yes, reroute the board", QR, "route"),
])
def test_a_plain_yes_with_at_most_the_same_action_is_granted(text, q, kind):
    assert _granted(text, q, kind)


PLAIN_WITH_EXTRA = [
    "yes, redo the layout, the old one before this was rushed", "yes, replace it and then show me the new layout",
    "yes, replace it, after all that's why I asked", "yes, wipe it, it is not worth keeping", "yes, replace it, I know what it means",
    "yes, replace it, the current placement makes no sense", "yes, replace the placement, that's fine by me",
]
PLAIN_WITH_EXTRA_HE = ["כן, תחליף את המיקום, הקודם לא היה טוב", "כן, תחליף, ואחר כך תראה לי", "כן, תחליף, לא צריך את הישן"]
NOT_A_GRANT = [
    "yes, replace it, provided nothing near J1 moves", "yes, replace it, but only on the top side", "yes, replace it, minus the connectors",
    "yes, replace it, all but the crystal", "yes, replace it — nope, changed course", "yes, replace it... no, don't", "yes, replace it; well, no, not today",
    "yes, replace it, I'm kidding of course", "yes, replace it, sure, and the moon is cheese", "yes, replace it, as soon as I get back",
    "yes, replace it, I'll handle the moving", "yes, I'd rather do the replacing", "yes, replace it, though I'm not convinced",
    "yes, replace it, hmmm", "yes, replace it, not really", "yes, replace it but keep the LEDs", "yes, replace it, apart from U4",
    "yes, replace it as long as J1 stays where it is", "yes, replace it in case the DRC passes afterwards", "yes, replace it after I commit my changes",
    "yes, sure, replace it, what could possibly go wrong", "yeah right, replace it, as if", "yes, replace it, said no one ever",
    "yes, replacing the placement is the last thing I want", "yes, never replace my placement", "yes, replace it, but let me do the moving",
    "yes, the replacement is something I will take on", "yes replace it, no wait, only the resistors", "yes, replace it and also reroute everything",
    "yes, replace it - no.", "yes. no. yes. replace it? no", "yes, I want to redraw it", "yes, scratch that", "yes, replace it, I want you to wait",
]
NOT_A_GRANT_HE = [
    "כן, תחליף את המיקום, אבל לא את המחברים", "כן, תחליף, רק תשאיר את J1", "כן, תחליף, נו באמת", "כן, תחליף את המיקום, אני אזיז את החלקים",
    "כן, תחליף את המיקום כשאני אחזור", "כן, תחליף, לא באמת", "כן, תחליף את המיקום. לא, עזוב", "כן, תחליף את המיקום בלי הנגדים",
    "כן בטח, תחליף, כאילו", "כן, הבנתי, אל תחליף כלום", "כן, אין צורך להחליף את המיקום", "כן, תחליף את המיקום בתנאי שהמחבר נשאר בצד",
    "כן, תחליף את המיקום וגם תנתב מחדש", "כן, אני רוצה לשרטט",
]


@pytest.mark.parametrize("text", PLAIN_WITH_EXTRA + NOT_A_GRANT)
def test_anything_beyond_a_plain_yes_is_never_a_grant(text):
    assert not _granted(text)


@pytest.mark.parametrize("text", PLAIN_WITH_EXTRA_HE + NOT_A_GRANT_HE)
def test_the_same_in_hebrew_is_never_a_grant(text):
    assert not _granted(text, QHE)


@pytest.mark.parametrize("text", PLAIN_WITH_EXTRA + [t for t in NOT_A_GRANT if "no." not in t and "no wait" not in t and "nope" not in t and ", no," not in t])
def test_whatever_is_not_a_grant_or_a_no_gets_a_one_click_confirm(text):
    c = _confirm(text)
    assert c and c["question"].startswith("Replace the whole placement") and c["yes"] and c["no"]


def test_a_negation_inside_the_message_does_not_remove_the_button():
    c = _confirm("yes, wipe it, it is not worth keeping")
    assert c and "Replace the whole placement" in c["question"]


@pytest.mark.parametrize("text", ["no", "No, stop", "stop", "wait, not now", "cancel that", "לא", "עצור", "חכה רגע"])
def test_an_explicit_no_first_gets_no_button(text):
    import serve
    meta = {}
    assert not serve.replace_confirm("place", {"replace": True}, text, meta) and "confirm" not in meta
    assert not _granted(text)


def test_the_confirm_says_how_many_parts_and_that_kept_parts_are_replaced_too(empty):
    _sheet(empty)
    import serve
    n = serve._parts_count(empty)
    assert n > 0
    c = _confirm("yes, replace it but keep the LEDs", project=empty)
    assert f"all {n} parts" in c["question"] and "including what you asked to keep" in c["question"]
    plain = _confirm("yes, replace it, I know what it means", project=empty)
    assert "including what you asked to keep" not in plain["question"]
    he = _confirm("כן, תחליף את המיקום בלי הנגדים", project=empty)
    assert str(n) in he["question"] and "גם מה שביקשת להשאיר" in he["question"]


def test_the_visible_corpus_phrase_is_still_read_as_before():
    p = ROOT / "tests" / "acceptance" / "corpora" / "fe_consent.json"
    if not p.exists():
        pytest.skip("no visible corpus here")
    q = json.loads(p.read_text(encoding="utf-8"))["question"]
    assert _granted("yes", q) and not _granted("no", q)


# ---------------------------------------------------------------- 2 evidence
def _real(path, pages=3):
    import pypdf
    w = pypdf.PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=100, height=100)
    with open(path, "wb") as f:
        w.write(f)


def _src(empty):
    import workspace
    d = workspace.project_dir(empty) / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ev(empty, d, name, page=1):
    return pin_decisions.valid_evidence(empty, [{"doc": name, "sha256": pin_decisions._sha256(d / name), "page": page}], "U1")


def test_evidence_with_a_page_count_that_cannot_be_read_is_refused(empty):
    _sheet(empty)
    d = _src(empty)
    (d / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 this is not a readable pdf at all")
    assert not _ev(empty, d, "ABCD1234.pdf")


def test_only_a_pdf_is_evidence(empty):
    _sheet(empty)
    d = _src(empty)
    (d / "ABCD1234.txt").write_text("a datasheet as text", encoding="utf-8")
    (d / "ABCD1234.png").write_bytes(b"\x89PNG\r\n")
    assert not _ev(empty, d, "ABCD1234.txt") and not _ev(empty, d, "ABCD1234.png")


def test_the_part_number_is_matched_as_a_token_not_a_substring(empty):
    _sheet(empty)
    d = _src(empty)
    _real(d / "ABCD12345-other.pdf")
    _real(d / "ABCD1234-rev2.pdf")
    assert not _ev(empty, d, "ABCD12345-other.pdf")                       # a different part whose number contains this one
    assert _ev(empty, d, "ABCD1234-rev2.pdf")


def test_a_refused_page_goes_through_the_one_click_reason_in_the_page():
    js = (ROOT / "ui" / "js" / "views" / "pins.js").read_text(encoding="utf-8")
    assert "citable" in js and "askPick" in js


def test_the_confirm_data_says_whether_a_doc_can_be_cited(empty):
    _sheet(empty)
    d = _src(empty)
    _real(d / "ABCD1234.pdf", 2)
    docs = pin_decisions.confirm_data(empty, "U1")["docs"]
    assert [x["name"] for x in docs] == ["ABCD1234.pdf"] and docs[0]["citable"] is True and docs[0]["pages"] == 2
    (d / "ABCD1234.pdf").write_bytes(b"damaged, no longer a pdf")
    docs = pin_decisions.confirm_data(empty, "U1")["docs"]
    assert docs and docs[0]["citable"] is False


# ---------------------------------------------------------------- 3 the stage of a re-routed board
def _pcb(monkeypatch, sha="r" * 64):
    import lineage
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: pathlib.Path("b.PcbDoc"))
    monkeypatch.setattr(lineage, "sha256_file", lambda p: sha)


def test_a_routed_board_whose_reroute_was_rejected_is_still_routed(empty, monkeypatch):
    import stages
    _pcb(monkeypatch)
    board_results.record(empty, "place", {})
    board_results.record(empty, "route", {})
    board_results.record(empty, "route", {"restored": True}, ok=False, error="Route rejected: 1 net could not be routed (VBUS). Cause: no room.")
    text = str(stages.pcb_stage(empty, {"altium_ok": {}}, board_results.latest(empty)))
    assert "still routed" in text and "VBUS" in text and "put back unrouted" not in text


def test_an_unrouted_board_whose_route_was_rejected_is_unrouted(empty, monkeypatch):
    import stages
    _pcb(monkeypatch)
    board_results.record(empty, "place", {})
    board_results.record(empty, "route", {"restored": True}, ok=False, error="Route rejected: 1 net could not be routed (VBUS).")
    text = str(stages.pcb_stage(empty, {"altium_ok": {}}, board_results.latest(empty)))
    assert "unrouted" in text and "still routed" not in text


def test_a_new_place_after_the_route_makes_a_rejected_route_unrouted_again(empty, monkeypatch):
    import stages
    _pcb(monkeypatch)
    board_results.record(empty, "place", {})
    board_results.record(empty, "route", {})
    board_results.record(empty, "place", {})
    board_results.record(empty, "route", {"restored": True}, ok=False, error="Route rejected: x.")
    text = str(stages.pcb_stage(empty, {"altium_ok": {}}, board_results.latest(empty)))
    assert "unrouted" in text and "still routed" not in text


# ---------------------------------------------------------------- 4 the order and the list of kinds
def _build(empty, tmp_path, **res):
    from test_r5_review3 import _build as b
    return b(empty, tmp_path, **res)


def test_a_pour_or_readback_failure_outranks_open_nets_in_the_title_and_both_are_listed(empty, tmp_path):
    o = _build(empty, tmp_path, failed=["VBUS"], problems=["not routed: 1 (VBUS: no room)", "the GND pour broke the rules and taking it off failed"])
    assert o["kind"] == "pour" and "pour" in o["title"].lower()
    assert o["kinds"] == ["pour", "open_nets"] and "VBUS" in o["cause_text"] and "VBUS" in " ".join(o["raw_problems"])
    o = _build(empty, tmp_path, failed=["VBUS"], problems=["after drawing, the board could not be read back", "not routed: 1 (VBUS)"])
    assert o["kind"] == "readback" and "open_nets" in o["kinds"]


def test_a_route_with_new_clearances_still_lists_its_other_problems(empty, tmp_path):
    from test_r5_review_fixes import LINES
    o = _build(empty, tmp_path, problems=["2 new clearance violations", "the board check was incomplete and could not be read in full"],
               drc_after={"Clearance": 2}, drc_violations=LINES)
    assert o["kind"] == "drc" and "unchecked" in o["kinds"]
    assert "incomplete" in o["cause_text"] and any("Move the parts named" in x["label"] for x in o["next"])


def test_the_bridge_raw_text_stays_reachable():
    import route_outcome
    res = {"restored": True, "failed": ["VBUS"], "problems": ["not routed: 1 (VBUS: no room)"], "summary": "RAW bridge summary"}
    out = route_outcome.attach("nonexistent-project", dict(res))
    assert out["summary_raw"] == "RAW bridge summary" and out["outcome"]["raw_problems"] == ["not routed: 1 (VBUS: no room)"]
    js = (ROOT / "ui" / "js" / "views" / "previews.js").read_text(encoding="utf-8")
    assert "summary_raw" in js or "raw_problems" in js


# ---------------------------------------------------------------- 5 the space between moved sentences
def test_a_cut_paragraph_keeps_the_space_between_moved_sentences():
    js = (ROOT / "ui" / "js" / "chat.js").read_text(encoding="utf-8")
    j = js.index("function chatSplitLong")
    body = js[j:js.index("function ", j + 10)]
    assert "moved.forEach((n, i)" in body and "n.textContent += ' '" in body
