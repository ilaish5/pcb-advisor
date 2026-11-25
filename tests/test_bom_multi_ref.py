"""A role that names several parts needs a ref for each (E2E 2026-11-25: "CC1/CC2 pull-downs" got R1 only)."""
import json

import pytest

import agent
import model
import role_refs
import serve
import store


@pytest.mark.parametrize("role, n", [
    ("CC1/CC2 pull-downs", 2), ("SDA/SCL pull-ups", 2), ("LDO input/output caps", 2), ("LDO input and output capacitors", 2),
    ("USB-C CC1/CC2 pull-down", 2), ("pull-ups on SDA and SCL", 2), ("USB D+/D- series resistors", 2),
    ("MOSI/MISO/SCK series resistors", 3), ("USB_DP/USB_DM series resistors", 2), ("2x 100nF decoupling", 2),
    ("decoupling x4", 4), ("I2C pull-up pair", 2), ("pair of load caps", 2), ("two I2C pull-ups", 2), ("pull-ups on both lines", 2),
])
def test_roles_that_name_several_parts(role, n):
    assert role_refs.parts_named(role) == n


@pytest.mark.parametrize("role", [
    "I2C/SMBus pull-up", "I2C/SMBus pull-ups", "USB D+ pull-up to 3V3", "BOOT0 pull-down", "decoupling", "Crystal load caps",
    "CANH/CANL termination resistor", "D+/D- termination resistor", "resistor between CANH and CANL", "differential pair termination",
    "OSC_IN/OSC_OUT feedback resistor", "3V3/5V select resistor", "RE/DE pull-down", "ESD and EMI filter caps", "sets 2x gain",
    "SDA/SCL", "USB-C power and data", "SPI/I2C select resistor",
])
def test_roles_that_do_not(role):
    assert role_refs.parts_named(role) < 2


def test_only_passive_lines_are_judged():
    for refs in (["J1"], ["U3"], ["D1"]):
        assert not role_refs.finding({"key": refs[0], "role": "D+/D- series resistors", "refs": refs})


def test_lines_with_the_same_role_count_together():
    a = {"key": "R1", "role": "CC1/CC2 pull-down", "refs": ["R1"]}
    assert role_refs.finding(a)
    assert not role_refs.finding(a, [a, {"key": "R2", "role": "cc1/cc2 pull-down", "refs": ["R2"]}])


def act(line, refs, role, value="5.1k"):
    return {"type": "bom.propose", "line": line, "new": True, "changes": {"refs": refs, "value": value, "role": role}}


def test_a_short_line_is_flagged_to_both_and_never_applied_unasked(empty, monkeypatch):
    monkeypatch.setattr(store, "autonomy", lambda: "auto")
    applied, proposals, refused = serve.apply_actions(empty, [act("R1", ["R1"], "CC1/CC2 pull-downs")])
    assert not refused and "names 2 parts" in serve.warned_map(applied)[applied[0]]
    prop = store.proposals(empty)[-1]
    assert prop["status"] == "pending" and "names 2 parts" in prop["role_finding"]
    summary = agent._summary(model.build(project=empty))
    summary = json.loads(summary) if isinstance(summary, str) else summary
    assert "names 2 parts" in summary["pending_proposals"][0]["check"]
    store.decide(empty, proposals[0], "approved")             # flag, never change: the student may still take it
    line = store.bom(empty, write=False)[0]
    assert line["refs"] == ["R1"] and "names 2 parts" in line["role_finding"]
    again = agent._summary(model.build(project=empty))
    assert "names 2 parts" in json.loads(again)["bom"][0]["check"]


def test_a_corrected_line_has_no_finding(empty):
    applied, _, _ = serve.apply_actions(empty, [act("R1", ["R1", "R2"], "CC1/CC2 pull-downs")])
    assert applied == ["bom.propose:R1"] and "role_finding" not in store.proposals(empty)[-1]


def test_a_qty_the_server_expands_is_enough(empty):
    a = act("C1", ["C1"], "LDO input/output caps", "1uF")
    a["changes"]["qty"] = 2
    applied, _, _ = serve.apply_actions(empty, [a])
    assert applied == ["bom.propose:C1"] and len(store.proposals(empty)[-1]["changes"]["refs"]) == 2


def test_both_warnings_share_one_suffix(empty):
    a = act("R3", ["R3"], "SDA/SCL pull-ups", "")
    applied, _, _ = serve.apply_actions(empty, [a])
    text = serve.warned_map(applied)[applied[0]]
    assert "has no value" in text and "names 2 parts" in text and "(warning" not in text


def _approved_line(project, key="R1"):
    store.propose_bom(project, key, {"mpn": "", "refs": [key], "value": "5.1k", "role": "CC1/CC2 pull-downs"}, new=True)
    store.decide(project, store.proposals(project)[-1]["id"], "approved")


def test_an_existing_line_goes_from_qty_1_to_2(empty, monkeypatch):
    monkeypatch.setattr(store, "autonomy", lambda: "auto")
    _approved_line(empty)
    applied, proposals, refused = serve.apply_actions(empty, [
        {"type": "bom.propose", "line": "R1", "changes": {"qty": 2, "value": "5.1k"}}])
    assert not refused and applied == ["bom.propose:R1"]
    prop = store.proposals(empty)[-1]
    assert prop["changes"]["refs"] == ["R1", "R2"] and "qty" not in prop["changes"] and prop["before"]["refs"] == ["R1"]
    assert prop["status"] == "approved"                      # autonomy "auto" applies it; before, it was dropped
    assert store.bom(empty, write=False)[0]["refs"] == ["R1", "R2"]
    assert not store.bom(empty, write=False)[0]["role_finding"]


def test_the_extra_ref_skips_refs_taken(empty):
    _approved_line(empty, "R1")
    _approved_line(empty, "R2")
    rec = store.propose_bom(empty, "R1", {"qty": 2})
    assert rec["changes"]["refs"] == ["R1", "R3"]


def test_a_qty_that_cannot_be_applied_is_an_error_not_a_drop(empty):
    _approved_line(empty)
    store.propose_bom(empty, "R1", {"refs": ["R1", "R2"]})
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    for qty in (1, 0, "2", 2.5, True):
        with pytest.raises(ValueError, match="qty"):
            store.propose_bom(empty, "R1", {"qty": qty})
    applied, _, refused = serve.apply_actions(empty, [{"type": "bom.propose", "line": "R1", "changes": {"qty": 1}}])
    assert not applied and refused and "qty 1" in refused[0]
    with pytest.raises(ValueError, match="designator"):
        store.propose_bom(empty, "USBC", {"qty": 2, "value": "x"}, new=True)
