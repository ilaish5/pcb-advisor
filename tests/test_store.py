"""
The data layer: append-only logs in, derived views out.
"""
import json

import pytest

import store


def test_the_bom_is_folded_from_its_log(lte):
    lines = {l["key"]: l for l in store.bom(lte)}
    assert lines["U5"]["mpn"] == "TXS0104EPWR"
    assert lines["C100"]["refs"] == ["C34", "C35", "C36", "C42"]
    # the derived file exists and matches
    on_disk = json.loads((store.pdir(lte) / "bom.json").read_text(encoding="utf-8"))
    assert {l["key"] for l in on_disk} == set(lines)


def test_a_later_event_overrides_an_earlier_one_without_editing_the_log(lte):
    before = (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8")
    store.edit_bom(lte, "R30", "note", "check with scope")
    after = (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8")
    assert after.startswith(before) and len(after) > len(before)
    assert {l["key"]: l for l in store.bom_lines(lte)}["R30"]["note"] == "check with scope"


def test_only_known_bom_fields_can_be_edited(lte):
    with pytest.raises(ValueError):
        store.edit_bom(lte, "R30", "supply", {})
    with pytest.raises(KeyError):
        store.edit_bom(lte, "NOPE", "note", "x")


def test_a_changed_mpn_has_no_supply_until_a_check_answers(lte):
    assert {l["key"]: l for l in store.bom(lte)}["U5"]["supply"] is not None
    store.edit_bom(lte, "U5", "mpn", "TXS0104EPW")
    line = {l["key"]: l for l in store.bom(lte)}["U5"]
    assert line["supply"] is None                     # the UI shows "checking"
    store.add_supply(lte, "U5", "LCSC", 500, 0.5, "TXS0104EPW", source="LCSC C1")
    assert {l["key"]: l for l in store.bom(lte)}["U5"]["supply"]["LCSC"]["stock"] == 500


def test_a_proposal_changes_nothing_until_approved(lte):
    before = {l["key"]: dict(l) for l in store.bom(lte)}["D30"]
    pid = [p for p in store.proposals(lte) if p["status"] == "pending"][0]["id"]
    assert {l["key"]: l for l in store.bom(lte)}["D30"]["mpn"] == before["mpn"]
    store.decide(lte, pid, "approved")
    d30 = {l["key"]: l for l in store.bom(lte)}["D30"]
    assert d30["mpn"] == "PESD5V0S1BL" and d30["package"] == "SOD-882"
    assert d30["supply"] is None                      # new MPN, nothing checked yet
    assert d30["library"] == "review"                 # model exists, student has not accepted it
    with pytest.raises(ValueError):
        store.decide(lte, pid, "rejected")            # decided once


def test_a_rejected_proposal_changes_nothing(lte):
    pid = [p for p in store.proposals(lte) if p["status"] == "pending"][0]["id"]
    log = (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8")
    store.decide(lte, pid["id"] if isinstance(pid, dict) else pid, "rejected")
    assert (store.pdir(lte) / "bom-log.jsonl").read_text(encoding="utf-8") == log
    assert {l["key"]: l for l in store.bom(lte)}["D30"]["mpn"] == "ESD56301D05"


def test_a_proposal_for_an_unknown_line_needs_new(lte):
    with pytest.raises(ValueError):
        store.propose_bom(lte, "ZZ9", {"mpn": "X"})
    rec = store.propose_bom(lte, "ZZ9", {"mpn": "X", "refs": ["ZZ9"]}, new=True)
    assert rec["new"] is True


def test_library_status_needs_both_a_pass_and_the_student(lte):
    lib = {r["line"]: r for r in store.library_view(lte)}
    assert lib["U5"]["verify"] == "pass" and lib["U5"]["accepted"] and lib["U5"]["status"] == "ok"
    assert lib["D31"]["status"] == "review" and lib["D30"]["status"] == "missing"
    store.add_library(lte, "D31", {"verify": "pass"}, by="verify_part")
    assert {r["line"]: r for r in store.library_view(lte)}["D31"]["status"] == "review"   # not accepted yet
    store.add_library(lte, "D31", {"accepted": True}, by="student")
    assert {r["line"]: r for r in store.library_view(lte)}["D31"]["status"] == "ok"


def test_standard_parts_are_left_out_of_the_library(lte):
    assert "Q3" not in {r["line"] for r in store.library_view(lte)}


def test_totals_count_what_is_bought_and_what_is_missing(lte):
    t = store.totals(store.bom(lte))
    assert t["out_of_stock"] == 1                     # D30
    assert t["to_verify"] == 2                        # D30 missing, D31 review
    assert t["parts"] == 22 and t["cost"] > 0


def test_a_netlist_is_checked_against_the_bom(lte):
    refs = {r for l in store.bom_lines(lte) for r in l["refs"]}
    sheet = {"sections": [{"id": "A"}], "parts": [
        {"ref": "U5", "section": "A", "pins": [{"name": "VCCA", "num": "1", "net": "+3V3"}]},
        {"ref": "U99", "section": "A", "pins": [{"name": "X", "num": "1", "net": "N1"}]},
        {"ref": "C34", "section": "A", "pins": [{"name": "1", "num": "1", "net": ""}]}]}
    errors = store.validate_sheet(sheet, refs)
    assert any("U99" in e and "not in the BOM" in e for e in errors)
    assert any("C34" in e and "no net" in e for e in errors)
    assert not any("U5" in e for e in errors)


def test_write_sheet_refuses_a_bad_sheet_and_writes_a_good_one(lte):
    bad = store.write_sheet(lte, "09", {"parts": [{"ref": "U5", "pins": [{"name": "A", "num": "1", "net": ""}]}]})
    assert not bad["ok"] and "09" not in store.sheet_ids(lte)
    good = store.write_sheet(lte, "09", {"title": "t", "parts": [
        {"ref": "U5", "pins": [{"name": "A", "num": "1", "net": "NC"}]}]})
    assert good["ok"] and "09" in store.sheet_ids(lte)


def test_the_idea_is_confirmed_only_by_a_call_that_says_so(lte, empty):
    store.propose_idea(empty, "Power", "Li-ion", by="agent")
    idea = store.load_idea(empty)
    assert idea["agreed"][0]["status"] == "proposed" and not idea["confirmed"]
    store.confirm_idea(empty)
    idea = store.load_idea(empty)
    assert idea["confirmed"] and idea["agreed"][0]["status"] == "confirmed"


def test_a_torn_last_line_does_not_take_the_project_down(lte):
    with open(store.pdir(lte) / "bom-log.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"ts": "x", "line": ')
    assert len(store.bom(lte)) == 19


def test_v1_sketch_is_read_as_an_idea(empty):
    d = store.pdir(empty)
    (d / "idea.json").unlink(missing_ok=True)
    (d / "sketch.json").write_text(json.dumps({"brief": "a thing", "blocks": [{"id": "A"}], "links": [], "confirmed": True}),
                                   encoding="utf-8")
    idea = store.load_idea(empty)
    assert idea["goal"] == "a thing" and idea["confirmed"] and idea["blocks"] == [{"id": "A"}]
