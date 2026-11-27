"""R5: a finding has a lifecycle (F-C), the tool's limits are registered (F-LIM), review turns only answer and Stop stops (W11),
a rejected route says what happened (U4). No Altium: the DRC runner and the files are fakes."""
import hashlib
import pathlib

import pytest

import ledger
import limits
import route_outcome
import turn_effects
import violation_pairs as vp
from test_chat_turns import call, server  # noqa: F401

LINES = [
    "Clearance Constraint: (0.100mm < 0.127mm) Between Pad J3-1(10mm,5mm) on Top Layer And Pad J3-2(10mm,6mm) on Top Layer",
    "Clearance Constraint: (0.100mm < 0.127mm) Between Pad J3-1(10mm,5mm) on Top Layer And Pad J3-2(10mm,6mm) on Top Layer",
    "Short-Circuit Constraint: Between Track (1mm,1mm)(2mm,2mm) on Top Layer And Pad U1-3(2mm,2mm) on Top Layer",
]


def test_pairs_count_every_line():
    rows = vp.group(LINES)
    assert sum(r["count"] for r in rows) == len(LINES)
    assert rows[0]["count"] == 2 and "J3-1" in vp.pair_words(rows[0])


def test_add_is_idempotent_and_ids_are_stable(empty):
    a = ledger.add(empty, "k1", "hand_step", "Move C3 away from U1", page="pcb")
    b = ledger.add(empty, "k1", "hand_step", "Move C3 away from U1", page="pcb")
    assert a["id"] == b["id"] and len(ledger.load(empty)["items"]) == 1
    assert a["state"] == "open"


def test_accept_needs_a_real_reason(empty):
    it = ledger.add(empty, "k2", "hand_step", "Widen the antenna keepout", page="pcb")
    for bad in ("", "  ", "ok", "12345678"):
        with pytest.raises(ValueError):
            ledger.accept(empty, it["id"], bad)
    r = ledger.accept(empty, it["id"], "the vendor said this gap is fine")
    assert r["state"] == "accepted" and r["reason"]


def test_jlc_reject_needs_make_anyway(empty):
    it = ledger.add(empty, "k3", "drc", "DRC Short-Circuit: 1 violation", page="pcb", extra={"jlc_reject": True})
    with pytest.raises(ValueError):
        ledger.accept(empty, it["id"], "I looked at it and it is fine")
    assert ledger.accept(empty, it["id"], "I looked at it and it is fine", make_anyway=True)["state"] == "accepted"


def test_done_without_a_check_does_not_close(empty):
    it = ledger.add(empty, "k4", "hand_step", "Solder the antenna", page="pcb")
    r = ledger.mark_done(empty, it["id"])
    assert r["state"] != "closed" and r["check_result"]["status"] == "not_checked"


def test_done_closes_only_on_a_passing_check_of_the_current_file(empty, monkeypatch):
    it = ledger.add(empty, "k5", "drc", "DRC Clearance: 2 violations", page="pcb", check={"type": "drc_rule", "rule": "Clearance"})
    sha = "a" * 64
    monkeypatch.setattr(ledger, "_pcb_sha", lambda p: sha)
    rec = {"pcb_sha256": sha, "drc": {"complete": True, "total": 2, "violations": LINES[:2], "rules": {"Clearance": 2}}}
    monkeypatch.setattr(ledger, "_drc_record", lambda p: rec)
    monkeypatch.setattr(ledger, "rule_counts", lambda drc: {"Clearance": 2})
    r = ledger.mark_done(empty, it["id"])
    assert r["state"] == "open"                          # still there: not closed
    sha2 = "b" * 64
    monkeypatch.setattr(ledger, "_pcb_sha", lambda p: sha2)
    rec2 = {"pcb_sha256": sha2, "drc": {"complete": True, "total": 0, "violations": []}}
    monkeypatch.setattr(ledger, "_drc_record", lambda p: rec2)
    monkeypatch.setattr(ledger, "rule_counts", lambda drc: {})
    r = ledger.mark_done(empty, it["id"])
    assert r["state"] == "closed" and r["last_check"]["sha256"] == sha2


def test_unchanged_file_is_not_closed_by_saying_done(empty, monkeypatch):
    sha = "c" * 64
    monkeypatch.setattr(ledger, "_pcb_sha", lambda p: sha)
    it = ledger.add(empty, "k6", "drc", "DRC Clearance: 1 violation", page="pcb", check={"type": "drc_rule", "rule": "Clearance"})
    r = ledger.mark_done(empty, it["id"])
    assert r["state"] == "open" and "not changed" in r["check_result"]["detail"]


def test_advice_that_breaks_a_system_rule_is_flagged(empty):
    c = ledger.advice_conflict("Add thermal vias under the exposed pad of U3 for heat.")
    assert c and c["rule"].startswith("No via in an SMD pad")
    assert not ledger.advice_conflict("Never put a via in the pad; place thermal vias next to the pad.")


def test_agent_reply_hand_steps_become_items(empty):
    items = ledger.track_advice(empty, "You need to move C3 away from U1 by hand in Altium, then tell me.")
    assert items is not None


def test_limits_registry_is_15_and_refused_ones_say_what_to_do():
    pub = limits.public()
    assert len(pub) == 15
    for l in pub:
        assert l["says"] and (l["status"] == "works" or l["instead"])


def test_limit_hit_opens_an_item_and_a_working_one_does_not(empty):
    refused = next(l for l in limits.public() if l["status"] == "refused")
    works = next(l for l in limits.public() if l["status"] == "works")
    assert limits.hit(empty, refused["id"], "test")["kind"] == "limit"
    assert limits.hit(empty, works["id"], "test") is None


def test_false_claim_about_layers_is_corrected():
    assert limits.false_claims("I cannot change the number of layers of the board.")
    assert not limits.false_claims("The board has 4 layers.")


def test_review_turns():
    assert turn_effects.is_review("anything", chip=True)
    assert turn_effects.is_review("why is the clearance failing?")
    assert not turn_effects.is_review("please route the board")
    assert turn_effects.review_refusal("altium.route_pcb")
    assert turn_effects.review_refusal("chat.ask") is None


def test_end_line_lists_every_side_effect():
    t = turn_effects.text(["altium.place_pcb", "altium.route_pcb"], ["altium.run_outjob: not run. x"], stopped=True)
    assert "placed the parts" in t and "routed the board" in t and "Did not run" in t and "Stop" in t
    assert turn_effects.text([], [], stopped=False) == ""


def _res(tmp_path, same=True):
    pcb = tmp_path / "b.PcbDoc"
    pcb.write_bytes(b"board-v1")
    bk = tmp_path / "bk"
    bk.mkdir()
    (bk / "b.PcbDoc").write_bytes(b"board-v1" if same else b"other")
    return pcb, {"restored": True, "backup": str(bk), "drc_violations": LINES, "drc_violations_before": [LINES[2]],
                 "drc_after": {"Clearance": 2}, "drc_before": {}, "summary": "raw altium text"}


def test_route_outcome_names_pairs_count_and_verifies_restore(empty, tmp_path):
    pcb, res = _res(tmp_path)
    o = route_outcome.build(empty, res, pcb=pcb)
    assert o["restored"] is True and o["count"] == 2
    assert "J3-1" in o["cause_text"] and "Restored from backup" in o["restored_text"]
    assert o["backup_sha256"] == hashlib.sha256(b"board-v1").hexdigest() == o["pcb_sha256"]
    assert len(o["next"]) >= 1
    assert not route_outcome.has_noise(o["message"])


def test_route_outcome_does_not_claim_a_restore_that_differs(empty, tmp_path):
    pcb, res = _res(tmp_path, same=False)
    o = route_outcome.build(empty, res, pcb=pcb)
    assert o["restored"] is False and "could NOT be confirmed" in o["restored_text"]


def test_pin_accept_with_a_blank_reason_is_refused(server, empty):
    assert call(server, "POST", "/api/pins/accept", empty, {"line": "U1:3", "reason": ""})[0] == 400
    assert call(server, "POST", "/api/pins/accept", empty, {"line": "U1:3", "reason": "  "})[0] == 400


def test_route_not_rejected_has_no_outcome(empty, tmp_path):
    assert route_outcome.build(empty, {"restored": False}, pcb=pathlib.Path(tmp_path / "x")) is None
