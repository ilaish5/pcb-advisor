"""R5 review fixes, tested by what they DO: the ledger as a store (one item per reply, atomic, a damaged file is an error), the DRC record of a
rejected route, the end line of a turn, the reason a risk needs, and the chat text functions run in node. All text here is written for these tests."""
import json
import pathlib
import shutil
import subprocess

import pytest

import board_results
import ledger
import turn_effects
from test_chat_turns import call, server  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


# ---------------------------------------------------------------- one item per reply
REPLY = ("Two things need your hands. In Altium, move C3 away from U1 so the pads clear. "
         "Then drag the track on net VBUS by hand so it stays 0.3 mm from J2.")


def test_one_reply_makes_one_item_with_every_part_it_names(empty):
    items = ledger.track_advice(empty, REPLY)
    assert len(items) == 1
    doc = ledger.load(empty)
    assert len(doc["items"]) == 1
    it = doc["items"][0]
    assert it["kind"] == "hand_step" and it["state"] == "open"
    assert {"C3", "U1", "J2"} <= set(it["refs"])


def test_the_annotated_and_the_stored_reply_are_the_same_item(empty):
    text, ids = ledger.annotate_reply(empty, REPLY)
    assert len(ids) == 1 and "Tracked on your Findings list" in text
    ledger.track_advice(empty, text)                       # the same reply read back from the stored chat, with the annotation on it
    assert len(ledger.load(empty)["items"]) == 1


def test_backfill_does_not_add_what_is_tracked_nor_reopen_what_was_done(empty):
    import store
    text, ids = ledger.annotate_reply(empty, REPLY)
    chats = store.pdir(empty) / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    (chats / "s1.jsonl").write_text(json.dumps({"role": "agent", "text": text, "ts": "t"}) + "\n", encoding="utf-8")
    ledger.accept(empty, ids[0], "I moved it myself and checked the gap")
    ledger.view(empty)
    doc = ledger.load(empty)
    assert len(doc["items"]) == 1 and doc["items"][0]["state"] == "accepted"


@pytest.mark.parametrize("sentence", [
    "I will run the DRC in Altium now and tell you what it says.",
    "You don't need to do anything by hand, the tool does it for you.",
    "Do you want me to move C3 in Altium myself?",
])
def test_a_sentence_that_asks_nothing_of_the_student_is_not_an_item(empty, sentence):
    assert ledger.track_advice(empty, sentence) == []
    assert ledger.load(empty)["items"] == []


@pytest.mark.parametrize("sentence", [
    "Put thermal vias next to the exposed pad of U3 for the heat.",
    "Place the thermal vias beside the pad, not in it.",
])
def test_advice_next_to_a_pad_is_not_a_via_in_pad(sentence):
    assert not ledger.advice_conflict(sentence)


def test_advice_for_a_via_in_the_pad_is_still_flagged():
    assert ledger.advice_conflict("Add thermal vias inside the exposed pad of U3.")


def test_a_manual_item_can_be_closed_by_the_student_with_a_reason(empty):
    items = ledger.track_advice(empty, REPLY)
    done = ledger.accept(empty, items[0]["id"], "done by hand, checked on the board")
    assert done["state"] == "accepted" and done["reason"]


# ---------------------------------------------------------------- the store
def test_a_damaged_ledger_is_an_error_the_student_sees_never_an_empty_list(empty, server):  # noqa: F811
    ledger.add(empty, "k", "hand_step", "Move C3 away from U1 by hand", page="pcb")
    p = ledger._path(empty)
    good = p.read_text(encoding="utf-8")
    p.write_text(good[: len(good) // 2], encoding="utf-8")        # a torn write
    with pytest.raises(ledger.LedgerCorrupt):
        ledger.load(empty)
    with pytest.raises(ledger.LedgerCorrupt):
        ledger.add(empty, "k2", "hand_step", "Another step by hand in Altium", page="pcb")
    assert p.read_text(encoding="utf-8") == good[: len(good) // 2]        # nothing was written over it
    code, body = call(server, "GET", "/api/ledger", empty)
    assert code == 500 and "damaged" in json.dumps(body)
    text, ids = ledger.annotate_reply(empty, REPLY)
    assert ids == [] and "Nothing in this reply was added" in text


def test_the_ledger_is_written_whole_and_swapped_in(empty, monkeypatch):
    seen = []
    real = ledger.os.replace
    monkeypatch.setattr(ledger.os, "replace", lambda a, b: (seen.append((pathlib.Path(a).name, pathlib.Path(b).name)), real(a, b))[1])
    ledger.add(empty, "k", "hand_step", "Move C3 away from U1 by hand", page="pcb")
    assert seen and seen[-1][1] == "ledger.json" and seen[-1][0] != "ledger.json"
    assert not list(ledger._path(empty).parent.glob("*.tmp"))


# ---------------------------------------------------------------- a rejected route
def _pcb(monkeypatch, sha):
    import lineage
    monkeypatch.setattr(lineage, "linked_pcb", lambda p: pathlib.Path("b.PcbDoc"))
    monkeypatch.setattr(lineage, "sha256_file", lambda p: sha)


def test_a_rejected_route_does_not_stamp_its_drc_on_the_restored_file(empty, monkeypatch):
    _pcb(monkeypatch, "r" * 64)
    res = {"restored": True, "drc_total": 7, "drc_rules": {"Clearance": 7}, "drc_clean": False, "drc_complete": True}
    rec = board_results.record(empty, "route", res)
    assert rec["drc"] is None and rec["rejected"] is True
    assert board_results.latest(empty)["board_check"] is None


def test_an_accepted_route_records_its_drc_on_the_file_it_checked(empty, monkeypatch):
    _pcb(monkeypatch, "n" * 64)
    res = {"restored": False, "drc_total": 0, "drc_rules": {}, "drc_clean": True, "drc_complete": True}
    rec = board_results.record(empty, "route", res)
    assert rec["drc"]["clean"] is True and rec["pcb_sha256"] == "n" * 64


def test_a_rejected_route_never_closes_or_opens_findings(empty, monkeypatch):
    _pcb(monkeypatch, "r" * 64)
    it = ledger.add(empty, "d1", "drc", "DRC Clearance: 2 violations", page="pcb", check={"type": "drc_rule", "rule": "Clearance"})
    board_results.record(empty, "route", {"restored": True, "drc_total": 0, "drc_rules": {}, "drc_clean": True, "drc_complete": True})
    ledger.sync_drc(empty)
    assert ledger.load(empty)["items"][0]["id"] == it["id"] and ledger.load(empty)["items"][0]["state"] == "open"


def test_the_end_line_of_a_turn_does_not_say_a_rejected_route_was_done():
    line = turn_effects.text([], ["altium.route_pcb: The route was rejected and the board restored from backup. It stays as it was."])
    assert "Changed in this turn" not in line and "routed the board" not in line
    assert "Did not run" in line and "routing the board" in line and "Nothing was changed" in line


def test_a_restore_that_could_not_be_confirmed_has_its_own_message(empty, tmp_path):
    import route_outcome
    o = route_outcome.build(empty, {"restored": True, "backup": str(tmp_path / "nope"), "drc_violations": ["x"], "drc_violations_before": [],
                                    "drc_after": {}, "drc_before": {}}, pcb=tmp_path / "missing.PcbDoc")
    assert o and o["rejected"] is True and o["restored"] is False
    assert "confirm" in o["message"].lower() and not route_outcome.has_noise(o["message"])


# ---------------------------------------------------------------- a reason is a reason
@pytest.mark.parametrize("reason", [None, "", "  ", "ok"])
@pytest.mark.parametrize("path", ["/api/pins/accept", "/api/pins/confirm"])
def test_accepting_a_risk_needs_a_reason_the_student_wrote(server, empty, path, reason):  # noqa: F811
    from test_pin_decisions import _sheet
    _sheet(empty)
    body = {"line": "U1"} if reason is None else {"line": "U1", "reason": reason}
    assert call(server, "POST", path, empty, body)[0] == 400


def test_accept_all_without_a_reason_is_refused(server, empty):  # noqa: F811
    from test_pin_decisions import _sheet
    _sheet(empty)
    assert call(server, "POST", "/api/pins/accept-all", empty, {"confirm": True})[0] == 400


def test_a_decision_with_no_reason_and_no_evidence_is_never_given_one():
    import pin_decisions
    assert pin_decisions._evidence_words({"basis": "blind"}) == ""
    assert "datasheet.pdf" in pin_decisions._evidence_words({"evidence": [{"doc": "datasheet.pdf", "page": 3}]})


# ---------------------------------------------------------------- the chat text functions, run in node
def _node(js):
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _extract(path, name):
    src = (ROOT / "ui" / "js" / path).read_text(encoding="utf-8")
    i = src.index(f"function {name}(")
    j = src.index("\n}\n", i) + 2
    return src[i:j]


needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


@needs_node
def test_a_table_row_keeps_the_pipe_inside_a_source_marker():
    chat = (ROOT / "ui" / "js" / "chat.js").read_text(encoding="utf-8")
    i = chat.index("const CHAT_SCRUB")
    j = chat.index("];", i) + 2
    js = chat[i:j] + _extract("chat.js", "chatScrub") + """
    const out = chatScrub('| Part | Where |\\n|---|---|\\n| U1 | {{src:a.pdf|p. 3}} |');
    console.log(JSON.stringify(out));"""
    out = _node(js)
    assert "{{src:a.pdf|p. 3}}" in out and "U1" in out and "---" not in out


@needs_node
def test_a_button_puts_its_ledger_id_in_a_data_attribute_not_the_html_id():
    kit = (ROOT / "ui" / "js" / "kit.js").read_text(encoding="utf-8")
    i = kit.index("function kattrs(")
    js = ("const kesc = s => String(s ?? '').replace(/[&<>\"']/g, c => '&#' + c.charCodeAt(0) + ';');\nconst icon = () => '';\n"
          + _extract("kit.js", "kattrs") + _extract("kit.js", "btn")
          + "\nconsole.log(JSON.stringify(btn('Done', {act: 'ledger-done', lid: 'F-007'})));")
    assert kit and i >= 0
    html = _node(js)
    assert 'data-lid="F-007"' in html and ' id="' not in html
