"""Width by current (scripts/altium/netcurrent.py, route.plan_routes widths, store.propose_net_current)."""
import pathlib

import pytest

import store
import workspace
from test_autonomy import _agent_says
from test_server import get, post, server  # noqa: F401  (server is a fixture)
from altium import netcurrent, route
from test_altium_route import pad, rules


def _two_net_board(net):
    return {"pads": [pad("J1", "1", 4, 4, net), pad("J2", "1", 16, 4, net), pad("J1", "2", 4, 8, "SIG"), pad("J2", "2", 16, 8, "SIG")]}


def _widths(nets, currents=None, estimates=None, oz=1.0, rise=10.0, **kw):
    return netcurrent.net_widths(nets, rules(**kw), currents, estimates, oz, rise, is_rail=lambda n: n.startswith("+"))


def test_a_1a_rail_is_wider_than_a_01a_one():
    w = _widths(["+5V", "+3V3"], currents={"+5V": 1.0, "+3V3": 0.1})
    assert w["+5V"]["width_mm"] > w["+3V3"]["width_mm"] and w["+5V"]["source"] == "set"
    assert w["+3V3"]["width_mm"] == 0.127                          # the board's width_min is the floor
    assert 0.25 < w["+5V"]["width_mm"] < 0.35                      # IPC-2221, 1 A, 10 C, 1 oz: about 0.3 mm


def test_unknown_current_gives_the_rail_default_and_says_so():
    w = _widths(["+5V", "SIG"])
    assert w["+5V"]["width_mm"] == 0.3 and w["+5V"]["source"] == "rail default" and w["+5V"]["current_a"] is None
    assert "current unknown" in w["+5V"]["note"]
    assert w["SIG"]["source"] == "rule" and w["SIG"]["width_mm"] == 0.127


def test_a_regulator_estimate_is_used_and_a_set_current_wins():
    w = _widths(["+5V", "+3V3"], estimates={"+5V": 2.0, "+3V3": 2.0}, currents={"+3V3": 0.1})
    assert w["+5V"]["source"] == "regulator" and w["+5V"]["width_mm"] > 0.6
    assert w["+3V3"]["source"] == "set" and w["+3V3"]["current_a"] == 0.1


def test_a_wider_pcbdoc_rule_wins_and_says_so():
    w = _widths(["+5V"], currents={"+5V": 1.0}, net_width={"+5V": 0.8})
    assert w["+5V"]["width_mm"] == 0.8 and w["+5V"]["source"] == "rule" and "wider and wins" in w["+5V"]["note"]


def test_a_narrower_pcbdoc_rule_is_kept_with_a_warning():
    w = _widths(["+5V"], currents={"+5V": 1.0}, net_width={"+5V": 0.15})
    assert w["+5V"]["width_mm"] == 0.15 and "narrower than needed" in w["+5V"]["note"]


def test_the_width_is_clamped_to_the_rule_maximum():
    w = _widths(["+5V"], currents={"+5V": 10.0}, width_max=1.0)
    assert w["+5V"]["width_mm"] == 1.0 and "allows at most 1 mm" in w["+5V"]["note"]


def test_a_current_out_of_range_gets_no_invented_width():
    for amps in (50.0, 0.0, -1.0):
        w = _widths(["+5V"], currents={"+5V": amps})
        assert w["+5V"]["width_mm"] is None and "outside IPC-2221 range" in w["+5V"]["note"]
    assert _widths(["+5V"], currents={"+5V": 1.0}, rise=5)["+5V"]["width_mm"] is None       # a rise outside 10-100 C
    # and the router does not invent one: the rail default is drawn, the note stays
    res = route.plan_routes(_two_net_board("+5V"), [0, 0, 20, 12], dict(rules(), net_current={"+5V": 50.0}), seconds=30)
    assert res["widths"]["+5V"]["width_mm"] == 0.3 and "outside IPC-2221 range" in res["widths"]["+5V"]["note"]
    assert res["widths"]["+5V"]["wanted_mm"] is None


def test_plan_routes_returns_the_widths_and_draws_them():
    res = route.plan_routes(_two_net_board("+5V"), [0, 0, 20, 12], dict(rules(), net_current={"+5V": 1.0}, copper_oz=1.0, temp_rise_c=10.0),
                            seconds=30)
    assert not res["failed"]
    w = res["widths"]
    assert w["+5V"]["source"] == "set" and w["+5V"]["current_a"] == 1.0 and w["+5V"]["width_mm"] == w["+5V"]["wanted_mm"] > 0.25
    assert w["SIG"]["width_mm"] == 0.127
    assert {i["width"] for i in res["items"] if i["kind"] == "track" and i["net"] == "+5V"} == {w["+5V"]["width_mm"]}
    line = netcurrent.width_line(w)
    assert line.startswith("track widths: +5V ") and "1 A, set" in line and "SIG" not in line


def test_thicker_copper_and_a_bigger_rise_make_the_track_narrower():
    one = _widths(["+5V"], currents={"+5V": 2.0})["+5V"]["width_mm"]
    two = _widths(["+5V"], currents={"+5V": 2.0}, oz=2.0)["+5V"]["width_mm"]
    hot = _widths(["+5V"], currents={"+5V": 2.0}, rise=30)["+5V"]["width_mm"]
    assert two < one and hot < one


def test_regulator_currents_from_the_bom_and_netlist():
    lines = [{"key": "U1", "refs": ["U1"], "role": "3.3 V LDO regulator", "iout_a": 0.8},
             {"key": "U2", "refs": ["U2"], "role": "LDO regulator"},                      # no rating written: no estimate
             {"key": "R1", "refs": ["R1"], "role": "pull-up", "iout_a": 5}]              # not a regulator
    sheets = [{"parts": [{"ref": "U1", "pins": [{"name": "VIN", "net": "+5V"}, {"name": "VOUT", "net": "+3V3"}]},
                         {"ref": "U2", "pins": [{"name": "VOUT", "net": "+1V8"}]}]}]
    assert netcurrent.regulator_currents(lines, sheets) == {"+3V3": 0.8}


def test_a_net_current_change_needs_approval_and_is_undoable(lte):
    p = store.propose_net_current(lte, "+5V", 1.5, reason="the motor draws 1.5 A")
    assert p["status"] == "pending" and store.classify_proposal(p) == "important"
    assert not store.may_auto_apply(p, "ask") and not store.may_auto_apply(p, "important")
    assert store.net_currents(lte) == {}                      # nothing changed before the click
    store.decide(lte, p["id"], "approved")
    assert store.net_currents(lte) == {"+5V": 1.5}
    store.undo_proposal(lte, p["id"])
    assert store.net_currents(lte) == {}
    with pytest.raises(ValueError):
        store.propose_net_current(lte, "+5V", -1)
    with pytest.raises(ValueError):
        store.propose_net_current(lte, "+5V", "lots")


# ---- the agent action, the student's own edit, the Rules tab, the docs

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_the_agent_action_is_a_proposal_that_waits_in_ask_and_important_mode(server, lte, monkeypatch):
    for mode in ("ask", "important"):
        workspace.set_value("agent.autonomy", mode)
        _agent_says(monkeypatch, [{"type": "net.set_current", "net": "+5V", "amps": 0.5, "reason": "USB VBUS", "sources": ["usb.pdf"]}])
        _, st = post(server, "/api/chat", {"text": "go"}, lte)
        assert st["proposals"][-1]["status"] == "pending" and st["proposals"][-1]["kind"] == "net_current"
        assert store.net_currents(lte) == {}
    workspace.set_value("agent.autonomy", "ask")
    _agent_says(monkeypatch, [{"type": "net.set_current", "net": "+5V", "amps": -3}])
    post(server, "/api/chat", {"text": "go"}, lte)
    assert store.net_currents(lte) == {}                            # a bad amount is refused, not stored


def test_a_student_set_applies_at_once_and_a_blank_clears(server, lte):
    code, body = post(server, "/api/net-currents", {"net": "+5V", "amps": "1.5"}, lte)
    assert code == 200 and store.net_currents(lte) == {"+5V": 1.5}
    assert store.read_jsonl(store.pdir(lte) / "net-currents.jsonl")[-1]["by"] == "student"
    code, body = get(server, "/api/net-currents", lte)
    assert code == 200 and isinstance(body["nets"], list)
    code, body = post(server, "/api/net-currents", {"net": "+5V", "amps": ""}, lte)
    assert code == 200 and store.net_currents(lte) == {}
    assert post(server, "/api/net-currents", {"net": "+5V", "amps": "x"}, lte)[0] == 400


def test_route_board_reads_the_currents_again_each_time(lte):
    from altium import bridge
    assert bridge.net_current_inputs(lte)["currents"] == {}
    store.set_net_current(lte, "+3V3", 2.0)
    assert bridge.net_current_inputs(lte)["currents"] == {"+3V3": 2.0}       # route_pcb calls this on every run
    row = next((r for r in bridge.net_current_rows(lte) if r["net"] == "+3V3"), None)
    assert row is None or (row["source"] == "set" and row["width_mm"] > 0.5)


def test_the_rules_tab_has_the_net_currents_table_and_the_agent_knows_the_action():
    js = (REPO / "ui" / "js" / "views" / "rules.js").read_text(encoding="utf-8")
    assert "/api/net-currents" in js and "data-net-amps" in js and "'Net currents'" in js
    agents = (REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    assert '"net.set_current"' in agents and len(agents.splitlines()) <= 150
    skill = (REPO / "runtime" / "skills" / "placement-and-routing-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "net.set_current" in skill
    assert all(len(l) <= 160 for l in skill.splitlines()[3:])
