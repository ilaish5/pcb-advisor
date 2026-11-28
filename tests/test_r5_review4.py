"""R5 review 4: evidence is a readable PDF of this part matched by token; a re-routed routed board says it is still routed; the kinds of a
rejection are ordered and all listed; a split paragraph keeps its spaces. (The consent bands are in test_consent_bands.py.)"""
import pathlib

import board_results
import pin_decisions
from test_unverified_pins import _sheet

ROOT = pathlib.Path(__file__).resolve().parent.parent


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
