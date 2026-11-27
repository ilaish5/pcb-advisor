"""R2 / U6: an extra rule the .RUL export cannot write is marked skipped with its reason, and the Rules stage is not clear."""
import json

import rule_kinds
import stages
import store


def _extra(project, rows):
    (store.pdir(project) / "rules.json").write_text(json.dumps(rows), encoding="utf-8")


BAD = {"name": "Rcanary", "kind": "KindUnknownXyz", "scope1": "All", "scope2": "All", "values": {"gap": "10mil"}, "enabled": True}


def test_an_unsupported_kind_is_marked_with_its_reason_and_a_supported_one_is_not():
    good = {"name": "W1", "kind": "Width", "scope1": "InNet('12V')", "value": "30mil", "enabled": True}
    got = rule_kinds.mark_skipped([good, BAD, {**BAD, "name": "off", "enabled": False}])
    assert not got[0].get("skipped")
    assert "unsupported" in got[1]["skipped"] and "KindUnknownXyz" in got[1]["skipped"]
    assert not got[2].get("skipped")                       # a rule turned off is left out on purpose, not skipped


def test_marking_changes_nothing_stored():
    rows = [dict(BAD)]
    rule_kinds.mark_skipped(rows)
    assert "skipped" not in rows[0]


def test_the_rules_stage_is_never_clear_while_a_rule_is_skipped(empty):
    _extra(empty, [BAD])
    st = stages.rules_stage(empty)
    assert st["state"] == "issues" and st["severity"] == "warn" and "Rcanary" in st["reason"]
    _extra(empty, [])
    assert stages.rules_stage(empty)["state"] != "issues" or "skipped" not in stages.rules_stage(empty)["reason"]
