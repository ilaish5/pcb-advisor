"""Constraint targets written by name at Idea time (before references exist) must reach the placer: they are resolved to one BOM
line, bound to its reference, or block placement with candidates. A requirement about an edge that no constraint holds is said."""
import json

import pytest

import constraints
import serve
import store
from checks import coverage


def _line(ref, value, role, mpn="", refs=None):
    return {"key": ref, "refs": refs or [ref], "value": value, "role": role, "mpn": mpn}


BOM = [_line("J1", "USB-C 6P", "5 V power input (power only)", "TYPE-C 6P"),
       _line("U1", "AMS1117-3.3", "5 V to 3.3 V LDO", "AMS1117-3.3"),
       _line("C1", "10uF 25V", "LDO input capacitor", "CL21A106KAYNNNE"),
       _line("C2", "22uF 25V", "LDO output capacitor", "CL21A226MAQNNNE"),
       _line("U2", "SHT31-DIS", "Temperature/humidity sensor (I2C)", "SHT31-DIS-B2.5kS"),
       _line("C3", "100nF", "SHT31 VDD decoupling", "CC0603KRX7R9BB104"),
       _line("J2", "JST-SH 4P", "I2C connector (3V3, GND, SDA, SCL)", "SM04B-SRSS-TB(LF)(SN)"),
       _line("D1", "LED yellow-green", "Power indicator on 3.3 V", "KT-0603YG"),
       _line("R1", "5.1k", "CC1 pull-down", "0603WAF5101T5E"),
       _line("R2", "5.1k", "CC2 pull-down", "0603WAF5101T5E")]
BLOCKS = [{"id": "ldo", "label": "AMS1117-3.3"}, {"id": "usb", "label": "USB-C receptacle"}, {"id": "conn", "label": "I2C connector"}]


def _refs(target, bom=BOM):
    return constraints.match_part(target, bom, BLOCKS)["refs"]


@pytest.mark.parametrize("target, want", [
    ("J1", ["J1"]), ("u2", ["U2"]),                     # reference
    ("AMS1117-3.3", ["U1"]),                            # exact value
    ("SM04B-SRSS-TB(LF)(SN)", ["J2"]),                  # exact MPN
    ("USB-C", ["J1"]),                                  # value prefix
    ("SHT31", ["U2"]),                                  # the prefix wins over C3's "SHT31 VDD decoupling"
    ("I2C connector", ["J2"]),                          # words of the role
    ("USB-C receptacle", ["J1"]),                       # connector noun
    ("usb", ["J1"]), ("conn", ["J2"]),                  # block id -> label
])
def test_each_rule(target, want):
    assert _refs(target) == want


@pytest.mark.parametrize("target", ["LDO", "5.1k", "I2C", "U9", "C10", "flux capacitor", "10", ""])
def test_no_guess(target):
    assert _refs(target) == []


def test_two_lines_are_candidates_not_a_binding():
    got = constraints.match_part("LDO", BOM)
    assert got["refs"] == [] and [l["key"] for l in got["candidates"]] == ["U1", "C1", "C2"]
    assert _refs("USB-C", BOM + [_line("J3", "USB-C 16P", "data port")]) == []


def test_a_helper_passive_is_not_the_part_it_serves():
    got = constraints.match_part("SHT31", [l for l in BOM if l["key"] != "U2"])
    assert got["refs"] == [] and [l["key"] for l in got["candidates"]] == ["C3"]


def test_line_key_gives_all_refs():
    assert constraints.match_part("LEDS", [_line("LEDS", "red", "status", refs=["D2", "D3"])])["refs"] == ["D2", "D3"]


def test_names_with_spaces_are_valid_targets():
    assert constraints.validate_item({"kind": "edge", "target": "I2C connector"})["target"] == "I2C connector"
    for bad in (["U1"], {"a": 1}, None, 5, ""):
        with pytest.raises(ValueError):
            constraints.validate_item({"kind": "edge", "target": bad})


ITEMS = [{"id": "e_usb", "kind": "edge", "target": "USB-C", "side": "left"},
         {"id": "a_ldo", "kind": "attr", "target": "AMS1117-3.3", "attr": "heat_source"},
         {"id": "a_sht", "kind": "attr", "target": "SHT31", "attr": "heat_sensitive"}]
MECH = "USB-C on the left edge, I2C connector on the right edge"


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "pdir", lambda p: tmp_path)
    monkeypatch.setattr(store, "bom_lines", lambda p: [dict(l) for l in BOM])

    def make(items=ITEMS, text=MECH):
        idea = {"blocks": BLOCKS, "agreed": [{"topic": "Mechanical", "text": text, "status": "confirmed"},
                                             {"topic": "Assembly", "text": "all parts on the top side", "status": "confirmed"}],
                "constraints": {"items": [dict(i, status="confirmed") for i in items]}}
        (tmp_path / "idea.json").write_text(json.dumps(idea), encoding="utf-8")
        return "p"
    make.dir = tmp_path
    return make


def _targets(p):
    return {i["id"]: i.get("target") for i in constraints.confirmed(store.load_idea(p))}


def test_names_reach_the_placer_and_bind_to_refs(proj):
    p = proj()
    plan = constraints.plan_for_board(constraints.confirmed(store.load_idea(p)), [0, 0, 40, 30], *constraints.known_refs(p))
    assert plan["edge"] == {"J1": "L"} and {a["ref"] for a in plan["attrs"]} == {"U1", "U2"} and not plan["findings"]
    assert constraints.bind_all(p) == ["USB-C -> J1", "AMS1117-3.3 -> U1", "SHT31 -> U2"]
    assert _targets(p) == {"e_usb": "J1", "a_ldo": "U1", "a_sht": "U2"}
    assert constraints.bind_all(p) == [] and constraints.blocking(p) == ""


def test_the_draft_is_bound_too(proj):
    p = proj()
    idea = json.loads((proj.dir / "idea.json").read_text(encoding="utf-8"))
    store.idea_draft_path(p).write_text(json.dumps({"idea": idea}), encoding="utf-8")
    constraints.bind_all(p)
    got = json.loads(store.idea_draft_path(p).read_text(encoding="utf-8"))["idea"]
    assert [i["target"] for i in got["constraints"]["items"]] == ["J1", "U1", "U2"]


def test_no_binding_while_a_bom_proposal_waits(proj, monkeypatch):
    p = proj()
    monkeypatch.setattr(store, "proposals", lambda x: [{"status": "pending", "line": "C9"}])
    assert constraints.bind_when_bom_settled(p) == [] and _targets(p)["e_usb"] == "USB-C"
    monkeypatch.setattr(store, "proposals", lambda x: [{"status": "pending", "kind": "idea_diagram"}])
    assert constraints.bind_when_bom_settled(p)


def test_unbound_constraints_block_with_candidates_until_one_click(proj):
    p = proj([{"id": "a1", "kind": "attr", "target": "LDO", "attr": "heat_source"},
              {"id": "k1", "kind": "keep_apart", "a": "U1", "b": "flux capacitor"}])
    found = constraints.unresolved(p)
    assert [(f["id"], f["field"], [c["ref"] for c in f["candidates"]]) for f in found] == [
        ("a1", "target", ["U1", "C1", "C2"]), ("k1", "b", [])]
    why = serve.step_refusal(p, "place")
    assert "LDO" in why and "U1" in why and "C2" in why and "flux capacitor" in why
    with pytest.raises(ValueError):
        constraints.bind_one(p, "k1", "b", "U1")        # the two parts of a distance
    with pytest.raises(ValueError):
        constraints.bind_one(p, "a1", "target", "U99")
    constraints.bind_one(p, "a1", "target", "u1")
    constraints.remove_one(p, "k1")
    assert constraints.unresolved(p) == [] and _targets(p) == {"a1": "U1"}
    assert serve.step_refusal(p, "place") == ""


def test_requirement_without_a_constraint_is_a_finding_and_one_click_holds_it(proj):
    p = proj()
    [f] = coverage.edge_findings(store.load_idea(p), BOM)
    assert f["message"] == "Requirement says J2 on the right edge, no constraint holds it"
    assert (f["refs"], f["side"], f["key"]) == (["J2"], "right", "edge_uncovered:J2:right")
    constraints.hold_edge(p, "J2", "right")
    assert coverage.edge_findings(store.load_idea(p), BOM) == []
    got = [i for i in constraints.confirmed(store.load_idea(p)) if i.get("target") == "J2"]
    assert [(i["side"], i["by"]) for i in got] == [("right", "student")]


def test_wrong_side_and_unknown_subject_are_findings(proj):
    p = proj(text="Place the USB-C connector and the battery holder on the right edge.")
    msgs = [f["message"] for f in coverage.edge_findings(store.load_idea(p), BOM)]
    assert msgs == ["Requirement says J1 on the right edge, no constraint holds it"]
    p = proj(text="The antenna must be on the top edge")
    [f] = coverage.edge_findings(store.load_idea(p), BOM)
    assert f["refs"] == [] and "antenna on the top edge" in f["message"]


@pytest.mark.parametrize("text", ["JLC assembles all parts, all on the top side", "No parts on the left edge",
                                  "4 holes 3.5 mm from the edges", "40 x 30 mm board"])
def test_no_edge_finding_from_other_text(proj, text):
    p = proj(items=[], text=text)
    assert coverage.edge_findings(store.load_idea(p), BOM) == []


def test_the_bom_decision_binds_the_names(proj, monkeypatch):
    p = proj()
    prop = {"id": "p1", "status": "approved", "line": "J2", "changes": {}}
    monkeypatch.setattr(store, "decide", lambda *a, **k: {})
    monkeypatch.setattr(store, "proposals", lambda x: [prop])
    monkeypatch.setattr(serve.project_mod, "touch", lambda x: None)
    monkeypatch.setattr(serve, "recheck_missing", lambda x: None)
    serve.decide_and_note(p, None, "p1", "approved", note=False, redraw_now=False)
    assert _targets(p) == {"e_usb": "J1", "a_ldo": "U1", "a_sht": "U2"}
