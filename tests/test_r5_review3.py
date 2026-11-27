"""R5 third review: a rejected route is recorded as not routed and says why (by kind), the page shows the outcome, consent is a last-stance rule
with a one-click confirm for the unclear, how-to questions are review turns, evidence must be real and this part's, Hebrew not-run labels, and a
long plain paragraph splits. All sentences here are written for these tests."""
import pathlib

import pytest

import board_results
import pin_decisions
import turn_effects
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _sheet

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- 1 the stage of a board that was put back
def _pcb(monkeypatch, sha="r" * 64):
    import lineage
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: pathlib.Path("b.PcbDoc"))
    monkeypatch.setattr(lineage, "sha256_file", lambda p: sha)


def test_a_rejected_route_is_recorded_as_not_ok_with_its_reason(empty, monkeypatch):
    import serve
    from altium import bridge
    _pcb(monkeypatch)
    err = bridge.BridgeError("x")
    err.route_result = {"restored": True, "problems": ["not routed: 1 (VBUS: no room)"], "failed": ["VBUS"], "backup": ""}
    out = serve._rejected_route(empty, err)
    rec = board_results.records(empty)[-1]
    assert rec["op"] == "route" and rec["ok"] is False and rec["rejected"] is True and rec["error"]
    assert out["kind"] == "open_nets" and "VBUS" in rec["error"]


def test_the_pcb_stage_says_the_board_was_put_back_unrouted_and_why(empty, monkeypatch):
    import stages
    _pcb(monkeypatch)
    board_results.record(empty, "place", {})
    board_results.record(empty, "route", {"restored": True}, ok=False, error="Route rejected: 1 net could not be routed (VBUS). Cause: not routed: 1 (VBUS: no room).")
    st = stages.pcb_stage(empty, {"altium_ok": {}}, board_results.latest(empty))
    text = str(st)
    assert "put back unrouted" in text and "VBUS" in text
    assert "Routed, board check not run" not in text and "Check the board" not in text


# ---------------------------------------------------------------- 2 each kind of rejection keeps its own reason
def _build(empty, tmp_path, **res):
    import route_outcome
    pcb = tmp_path / "b.PcbDoc"
    pcb.write_bytes(b"v1")
    bk = tmp_path / "bk"
    bk.mkdir(exist_ok=True)
    (bk / "b.PcbDoc").write_bytes(b"v1")
    return route_outcome.build(empty, {"restored": True, "backup": str(bk), "drc_violations": [], "drc_violations_before": [], "drc_after": {}, "drc_before": {},
                                       **res}, pcb=pcb)


@pytest.mark.parametrize("kind,res", [
    ("open_nets", {"failed": ["VBUS"], "problems": ["not routed: 1 (VBUS: no room between U1 and C3)"]}),
    ("width", {"problems": ["the track on net VBUS would be 0.20 mm, narrower than the 0.50 mm its current needs"]}),
    ("pour", {"problems": ["the GND pour broke the rules and taking it off failed (no answer)"]}),
    ("readback", {"problems": ["after drawing, the board could not be read back or checked (no answer)"]}),
    ("other", {"problems": ["Altium said something this tool has no word for"]}),
])
def test_a_rejection_keeps_its_own_reason_title_and_next_step(empty, tmp_path, kind, res):
    o = _build(empty, tmp_path, **res)
    assert o["kind"] == kind and o["rejected"] is True and o["restored"] is True
    assert res["problems"][0][:30] in o["cause_text"]                    # the bridge's own words are kept
    assert o["count"] != 0 and o["count"] is not None                    # never "0 problems"
    assert "found new problems" not in o["title"]
    assert all("Move the parts named" not in x["label"] for x in o["next"])      # no part was named
    assert o["next"] and o["next"][-1]["label"]


def test_the_titles_of_the_kinds_differ(empty, tmp_path):
    titles = {_build(empty, tmp_path, **r)["title"] for r in (
        {"failed": ["VBUS"], "problems": ["not routed: 1 (VBUS: x)"]}, {"problems": ["narrower track"]},
        {"problems": ["the GND pour is not in the saved board"]}, {"problems": ["could not be read back"]})}
    assert len(titles) == 4


def test_a_rejection_with_drc_pairs_still_says_move_the_parts_named(empty, tmp_path):
    from test_r5_review_fixes import LINES
    o = _build(empty, tmp_path, problems=["2 new clearance violations"], drc_after={"Clearance": 2}, drc_violations=LINES)
    assert o["kind"] == "drc" and o["count"] == 2 and any("Move the parts named" in x["label"] for x in o["next"])


# ---------------------------------------------------------------- 3 the page shows the outcome
def test_the_page_renders_the_outcome_before_the_plain_error():
    js = (ROOT / "ui" / "js" / "views" / "previews.js").read_text(encoding="utf-8")
    i = js.index("async function pvFinish")
    body = js[i:js.index("if (c.after) c.after()", i)]
    assert body.index("r.outcome && r.outcome.rejected") < body.index("!r || r.error")
    assert "r.error || r.summary" in body                                  # the error text is inside the outcome note
    assert "o.cause_text" in js[js.index("function pvOutcomeHTML"):]       # a kind with no pairs shows the bridge's reason


# ---------------------------------------------------------------- 4 consent
Q = "Replace the board's parts and copper? This wipes what is there (a backup is kept). Answer yes/no."
QHE = "להחליף את המיקום והנחושת בלוח? זה מוחק את מה שיש (נשמר גיבוי). כן/לא?"


def _grants(text, q=Q, kind="place"):
    import serve
    return not serve._replace_consent(kind, {}, text, q)


@pytest.mark.parametrize("text", [
    "yes, replace it after I commit my changes", "yes, replace it as long as J1 stays where it is", "yes, replace it in case the DRC passes afterwards",
    "yes, replacing the placement is the last thing I want", "yes, the replacement is something I will take on",
    "yes, sure, replace it, what could possibly go wrong", "yeah right, replace it, as if", "yes, replace it, said no one ever",
    "yes, replace it, brilliant idea", "yes, replace it, let me do the rest", "yes, replace the placement and route again",
])
def test_a_yes_that_is_conditional_ironic_or_handed_over_is_not_a_grant(text):
    assert not _grants(text)


@pytest.mark.parametrize("text", [
    "כן, תחליף את המיקום אחרי שאני אשמור עותק", "כן בטח, תחליף, כאילו", "כן, תחליף, ממש רעיון מבריק", "כן, תחליף את המיקום, תן לי לעשות את זה",
    "כן, תחליף רק את הקבלים", "כן, תחליף את המיקום וגם תנתב מחדש",
])
def test_the_same_in_hebrew(text):
    assert not _grants(text, QHE)


@pytest.mark.parametrize("text", ["redo it for me", "yes, go ahead and redo the placement for me", "yes, replace it, no problem" if False else "yes, replace it please"])
def test_a_plain_yes_is_granted_even_with_for_me_in_it(text):
    import serve
    assert not serve._replace_consent("place", {}, text, Q.replace("copper?", "placement?"))


def test_an_unclear_yes_gets_a_one_click_confirm_that_restates_the_action():
    import serve
    meta = {}
    assert serve.replace_confirm("place", {"replace": True}, "yes, replace it after I commit my changes", meta)
    c = meta["confirm"]
    assert "Replace" in c["question"] and "backup" in c["question"] and c["yes"].startswith("Yes") and c["no"].startswith("No")
    # the click itself ("Yes, replace it") is read as the answer to that question
    assert not serve._replace_consent("place", {}, c["yes"], "Some text.\n\n" + c["question"])
    h = {}
    assert serve.replace_confirm("place", {"replace": True}, "כן, תחליף, כאילו", h) and "להחליף" in h["confirm"]["question"]
    assert not serve._replace_consent("place", {}, h["confirm"]["yes"], "טקסט.\n\n" + h["confirm"]["question"])


@pytest.mark.parametrize("text", ["no, do not replace it", "wait, not yet", "לא, אל תחליף", "stop", "עצור"])
def test_a_no_stop_or_wait_first_gets_no_confirm(text):
    import serve
    meta = {}
    assert not serve.replace_confirm("place", {"replace": True}, text, meta) and "confirm" not in meta


# ---------------------------------------------------------------- 5 how-to questions are review turns
HOWTO = ["How do I move C3 closer to U1?", "What should I change to fix the clearance?", "Why did the route fail?", "How should I place the decoupling caps?",
         "How do I redraw the schematic?", "איך לתקן את הקצר?", "איך להזיז את C3?", "מה צריך לשנות כדי לעבור את הבדיקה?", "How do I fix the short between U1 and U2?",
         "Where do I add a resistor?", "Is it ok to rotate U2?", "explain how to redo the routing", "How can I route the board by hand?"]


@pytest.mark.parametrize("text", HOWTO)
def test_a_how_to_question_is_a_review_turn(text):
    assert turn_effects.is_review(text)


@pytest.mark.parametrize("text", ["Can you move C3 next to U1?", "Could you redo the placement?", "תוכל להזיז את C3?", "Route the board?", "How do I do it? Just do it.",
                                  "Explain it, then route the board", "בבקשה תקן את הקצר", "Do it for me"])
def test_a_request_to_act_is_not_a_review_turn(text):
    assert not turn_effects.is_review(text)


# ---------------------------------------------------------------- 6 evidence
def _pdf(path, pages):
    import pypdf
    w = pypdf.PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=100, height=100)
    with open(path, "wb") as f:
        w.write(f)


def _folder(empty):
    import workspace
    d = workspace.project_dir(empty) / "sources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_evidence_needs_a_sha_a_page_inside_the_pdf_and_this_parts_file(empty, monkeypatch, tmp_path):
    import workspace
    _sheet(empty)
    d = _folder(empty)
    _pdf(d / "ABCD1234.pdf", 3)
    _pdf(d / "OTHER9999.pdf", 3)
    shared = tmp_path / "shared"
    shared.mkdir()
    _pdf(shared / "ZZZZ0000.pdf", 3)
    monkeypatch.setattr(workspace, "datasheets_dir", lambda: shared)
    sha = pin_decisions._sha256(d / "ABCD1234.pdf")

    def ev(doc, page, s):
        return pin_decisions.valid_evidence(empty, [{"doc": doc, "sha256": s, "page": page}], "U1")
    assert ev("ABCD1234.pdf", 3, sha)                                       # a real page of this part's datasheet
    assert not ev("ABCD1234.pdf", 4, sha)                                   # past the last page
    assert not ev("ABCD1234.pdf", 2, "")                                    # no sha
    assert not ev("OTHER9999.pdf", 1, pin_decisions._sha256(d / "OTHER9999.pdf"))      # a file of another part
    assert not ev("ZZZZ0000.pdf", 1, pin_decisions._sha256(shared / "ZZZZ0000.pdf"))   # shared, and maps to no part here


def test_a_shared_datasheet_of_this_part_is_evidence(empty, monkeypatch, tmp_path):
    import workspace
    _sheet(empty)
    shared = tmp_path / "shared"
    shared.mkdir()
    _pdf(shared / "abcd1234-rev2.pdf", 2)
    monkeypatch.setattr(workspace, "datasheets_dir", lambda: shared)
    got = pin_decisions.valid_evidence(empty, [{"doc": "abcd1234-rev2.pdf", "sha256": pin_decisions._sha256(shared / "abcd1234-rev2.pdf"), "page": 2}], "U1")
    assert got and got[0]["page"] == 2


@pytest.mark.parametrize("doc,page,use_sha", [("ABCD1234.pdf", 9, True), ("ABCD1234.pdf", 1, False), ("OTHER9999.pdf", 1, True)])
def test_bad_evidence_does_not_skip_the_reason_check(server, empty, doc, page, use_sha):  # noqa: F811
    _sheet(empty)
    d = _folder(empty)
    _pdf(d / "ABCD1234.pdf", 3)
    _pdf(d / "OTHER9999.pdf", 3)
    ev = [{"doc": doc, "sha256": pin_decisions._sha256(d / doc) if use_sha else "", "page": page}]
    assert call(server, "POST", "/api/pins/confirm", empty, {"line": "U1", "evidence": ev})[0] == 400
    assert pin_decisions.current(empty, "U1") is None


def test_good_evidence_still_confirms_without_a_typed_reason(server, empty):  # noqa: F811
    _sheet(empty)
    d = _folder(empty)
    _pdf(d / "ABCD1234.pdf", 3)
    ev = [{"doc": "ABCD1234.pdf", "sha256": pin_decisions._sha256(d / "ABCD1234.pdf"), "page": 2}]
    code, body = call(server, "POST", "/api/pins/confirm", empty, {"line": "U1", "evidence": ev})
    assert code == 200 and body["decision"]["reason"].startswith("Matches the datasheet pin table, page 2")


# ---------------------------------------------------------------- 7 Hebrew end line
def test_the_hebrew_end_line_names_what_did_not_run_as_the_thing_not_the_done_verb():
    line = turn_effects.text([], ["altium.route_pcb: not run. הסיבה כאן", "altium.place_pcb: not run. עוד סיבה", "bom.propose: not run. x"], lang="he")
    assert "לא רץ: ניתוב הלוח (הסיבה כאן)" in line and "מיקום החלקים" in line and "הצעת שינוי ב-BOM" in line
    assert "נותב הלוח" not in line and "routing" not in line and "propose" not in line


# ---------------------------------------------------------------- 8 a long plain paragraph splits
def test_a_long_plain_text_paragraph_can_be_cut_between_sentences():
    js = (ROOT / "ui" / "js" / "chat.js").read_text(encoding="utf-8")
    i = js.index("function chatSplittable")
    assert "t.firstElementChild || t" in js[i:i + 300]                       # a box that holds only text is splittable
    j = js.index("function chatSplitLong")
    assert "cuttable" in js[j:i] and "only.childNodes.length === 1" in js[j:i]
