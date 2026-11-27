"""R2 / W33 / U7: the readiness summary counts what was read back; no evidence is open, never green."""
import json

import board_results
import readiness
import store


def _record(project, rules, total=None, complete=True, sha="abc123"):
    drc = {"rules": rules, "total": sum(rules.values()) if total is None else total, "unrouted": 0, "clean": not rules,
           "complete": complete, "violations": []}
    rec = {"ts": 1, "op": "drc", "ok": True, "pcb": "x.PcbDoc", "pcb_sha256": sha, "drc": drc}
    p = store.pdir(project) / "board-log.jsonl"
    p.write_text(json.dumps(rec) + "\n", encoding="utf-8")


def _current(monkeypatch, stale=False):
    monkeypatch.setattr(board_results, "_stale", lambda project, rec: stale)


def test_no_check_is_not_checked_and_open(empty):
    d = readiness.drc_open(empty)
    assert d["state"] == "not_checked" and d["total"] is None
    s = readiness.summary(empty)
    assert not s["ready"] and any(i["id"] == "drc_state" for i in s["items"])


def test_a_stale_or_partial_check_is_open_with_its_state(empty, monkeypatch):
    _record(empty, {"Clearance Constraint (Gap=0.1mm) (All),(All)": 2})
    _current(monkeypatch, stale=True)
    assert readiness.drc_open(empty)["state"] == "stale"
    _current(monkeypatch)
    _record(empty, {"Clearance Constraint (Gap=0.1mm) (All),(All)": 2}, complete=False)
    assert readiness.drc_open(empty)["state"] == "partial"
    assert not readiness.summary(empty)["ready"]


def test_classes_sum_to_the_total_and_unlisted_counts_are_unclassified(empty, monkeypatch):
    _current(monkeypatch)
    _record(empty, {"Short-Circuit Constraint (Allowed=No) (All),(All)": 2, "Silk To Solder Mask Clearance (Gap=1mil)": 3,
                    "Clearance Constraint (Gap=0.1mm) (All),(All)": 4}, total=12)
    d = readiness.drc_open(empty)
    assert d["state"] == "checked" and sum(d["by_class"].values()) == 12
    assert d["by_class"]["JLC-reject"] == 2 and d["by_class"]["cosmetic"] == 3 and d["by_class"]["unclassified"] == 4 + 3
    assert d["by_rule"]["Clearance Constraint"] == 4
    blk = readiness.manifest_block(empty)
    assert blk["total"] == 12 and blk["pcb_sha256"] == "abc123" and "12 violation" in blk["scope"]


def test_a_clean_complete_current_check_has_no_drc_item(empty, monkeypatch):
    _current(monkeypatch)
    _record(empty, {})
    assert not [i for i in readiness.summary(empty)["items"] if i["id"].startswith("drc")]


def test_make_anyway_covers_one_check_and_is_consumed(empty, monkeypatch):
    _current(monkeypatch)
    _record(empty, {"Short-Circuit Constraint (Allowed=No) (All),(All)": 2})
    assert "JLC would reject" in readiness.reject_block(empty) and "JLC would reject" in store.manufacturing_block(empty)
    rec = readiness.make_anyway(empty)
    assert rec["reject"] == 2 and readiness.reject_block(empty) == ""
    _record(empty, {"Short-Circuit Constraint (Allowed=No) (All),(All)": 3})          # another check: the decision does not carry over
    assert readiness.reject_block(empty)
    _record(empty, {"Short-Circuit Constraint (Allowed=No) (All),(All)": 2})
    assert readiness.consume_override(empty)["reject"] == 2
    assert readiness.reject_block(empty)


def test_the_manifest_states_the_open_drc_items(empty, monkeypatch):
    import pin_decisions
    _current(monkeypatch)
    _record(empty, {"Clearance Constraint (Gap=0.1mm) (All),(All)": 4, "Minimum Annular Ring (Minimum=8mil)": 6})
    path = pin_decisions.write_manifest(empty)
    man = json.loads(open(path, encoding="utf-8").read())
    assert man["drc_open"]["drc_open_by_rule"] == {"Clearance Constraint": 4, "Minimum Annular Ring": 6}
    assert man["drc_open"]["total"] == 10 and sum(man["drc_open"]["drc_by_class"].values()) == 10


def test_unverified_parts_are_counted_by_evidence(empty):
    from test_unverified_pins import _sheet
    _sheet(empty)
    assert readiness.unchecked_pin_lines(empty) == ["U1"]
    store.accept_pins(empty, "U1")
    assert readiness.unchecked_pin_lines(empty) == []
