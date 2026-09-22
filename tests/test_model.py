"""
What the engine does with a design.

Every test here is a defect that reached a student before it was caught, so
each one names the behaviour rather than the function.
"""
import model


def ids(rows):
    return [r["id"] for r in rows]


# ---------------------------------------------------------------- reachability

def test_a_question_waits_on_a_guard_that_is_not_settled_yet(battery_mcu):
    """Before the topology is chosen, both branches are still ahead of you.

    They must read as waiting, not as ruled out, or the student loses the one
    step of lookahead that shows where the path continues."""
    m = model.build(project=battery_mcu)
    assert "power.linear.package" in ids(m["blocked"])
    assert "power.switching.freq" in ids(m["blocked"])


def test_a_guard_that_is_settled_otherwise_rules_a_question_out(board):
    p = board(blocks=(("BAT", "power_in"), ("MCU", "mcu")), links=(("BAT", "MCU"),),
              decisions=({"node": "req.source", "value": "battery"},
                         {"node": "req.vout", "value": "v3v3"},
                         {"node": "req.iload", "value": "i_low"},
                         {"node": "power.topology", "value": "linear"}))
    m = model.build(project=p)
    assert "power.switching.freq" in ids(m["irrelevant"])


def test_a_question_behind_a_ruled_out_one_is_ruled_out_too(board):
    """power.inductor is guarded to switching AND depends on the switching
    frequency. Checking the dependency first reported 'waiting on' a question
    that was itself guarded off - a node that could never be finished or
    dismissed, sitting in the progress count forever."""
    p = board(blocks=(("BAT", "power_in"), ("MCU", "mcu")), links=(("BAT", "MCU"),),
              decisions=({"node": "req.source", "value": "battery"},
                         {"node": "req.vout", "value": "v3v3"},
                         {"node": "req.iload", "value": "i_low"},
                         {"node": "power.topology", "value": "linear"}))
    m = model.build(project=p)
    assert "power.inductor" in ids(m["irrelevant"])
    assert "power.inductor" not in ids(m["blocked"])


# ---------------------------------------------------------------- withdrawal

def test_a_question_can_be_withdrawn_and_takes_its_rules_with_it(battery_mcu):
    p = battery_mcu
    first = model.build(project=p)
    assert "power.topology" in ids(first["open"])

    _append(p, {"node": "power.topology", "value": "linear"})
    with_reg = model.build(project=p)
    assert {"lin.thermal", "lin.copper", "lin.esr"} <= set(ids(with_reg["constraints"]))

    _append(p, {"node": "power.topology", "retract": True,
                "why": "no regulator - the MCU runs from the cells"})
    m = model.build(project=p)
    assert "power.topology" not in ids(m["answered"])
    assert not [c for c in m["constraints"] if c["from_node"] == "power.topology"]
    gone = [n for n in m["irrelevant"] if n.get("withdrawn")]
    assert ids(gone) == ["power.topology"]
    assert "no regulator" in gone[0]["reason"]


def test_withdrawing_clears_everything_waiting_behind_it(battery_mcu):
    """The deadlock this was built for: four power questions unreachable, the
    one holding them up impossible to answer truthfully."""
    p = battery_mcu
    _append(p, {"node": "power.topology", "retract": True, "why": "no regulator"})
    m = model.build(project=p)
    assert not [n for n in m["blocked"] if n["id"].startswith("power.")]


def test_a_withdrawal_can_be_undone(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "power.topology", "retract": True, "why": "no regulator"})
    _append(p, {"node": "power.topology", "reopen": True})
    m = model.build(project=p)
    assert "power.topology" in ids(m["open"])
    assert not [n for n in m["irrelevant"] if n.get("withdrawn")]


def test_the_log_still_shows_what_was_answered_and_why_it_went(battery_mcu, home):
    """A withdrawal is an append, never a delete: the record of a student
    changing their mind is the thing worth keeping."""
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    _append(p, {"node": "power.topology", "retract": True, "why": "no regulator"})
    lines = (home / "projects" / p / "decisions.jsonl").read_text().splitlines()
    assert any('"value": "linear"' in l for l in lines)
    assert any('"retract": true' in l and "no regulator" in l for l in lines)


# ---------------------------------------------------------------- needs_block

def test_a_rule_about_a_part_is_withheld_while_that_part_is_absent(battery_mcu):
    m = model.build(project=battery_mcu)
    live = set(ids(m["constraints"]))
    held = {w["id"] for w in m["withheld"]}
    assert {"pwr.iq", "pwr.in.falling"} <= held
    assert not ({"pwr.iq", "pwr.in.falling"} & live)


def test_a_withheld_rule_says_what_it_is_waiting_for_in_words(battery_mcu):
    m = model.build(project=battery_mcu)
    w = next(x for x in m["withheld"] if x["id"] == "pwr.iq")
    assert w["needs"] == "a voltage regulator"      # never the id


def test_the_rule_comes_back_when_the_part_does(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    m = model.build(project=p)
    assert {"pwr.iq", "pwr.in.falling"} <= set(ids(m["constraints"]))
    assert not m["withheld"]


def test_a_rule_can_need_a_part_from_another_domain(board):
    """analog.star.single is authored in the analog cascade and needs a
    regulator, which only the power cascade contributes. Nothing could catch
    that before: the corpus treated a regulator as a given across domains."""
    p = board(blocks=(("BAT", "power_in"), ("MCU", "mcu"), ("SNS", "sensor")),
              links=(("BAT", "MCU"), ("SNS", "MCU")),
              decisions=({"node": "analog.ground", "value": "split_star"},))
    m = model.build(project=p)
    assert "analog.star.single" in {w["id"] for w in m["withheld"]}


def test_no_regulator_is_a_choice_that_records_real_rules(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "direct"})
    m = model.build(project=p)
    assert "U_REG" not in ids(m["blocks"])           # it adds no part
    assert {"direct.range", "direct.brownout"} <= set(ids(m["constraints"]))
    assert not m["blocked"]


# ---------------------------------------------------------------- threads

def test_closing_a_thread_records_why(battery_mcu, home):
    p = battery_mcu
    _thread(home, p, {"anchor": "req.vout", "role": "user", "text": "never 3.3 V"})
    _thread(home, p, {"anchor": "req.vout", "role": "resolved", "text": "switched to direct"})
    t = model.build(project=p)["threads"]["req.vout"]
    assert t["resolved"] and t["resolution"] == "switched to direct"


def test_a_thread_about_something_still_live_is_noted_not_done(battery_mcu, home):
    """Resolve used to be a read receipt presented as closure: a thread saying
    a decision contradicted the board could be dismissed in one click while the
    decision, and every rule under it, stayed in the design."""
    p = battery_mcu
    _thread(home, p, {"anchor": "req.vout", "role": "user", "text": "never 3.3 V"})
    _thread(home, p, {"anchor": "req.vout", "role": "resolved", "text": "noted"})
    assert model.build(project=p)["threads"]["req.vout"]["still_live"] is True


def test_a_thread_about_something_withdrawn_is_done(battery_mcu, home):
    p = battery_mcu
    _thread(home, p, {"anchor": "req.vout", "role": "user", "text": "never 3.3 V"})
    _thread(home, p, {"anchor": "req.vout", "role": "resolved", "text": "withdrew it"})
    _append(p, {"node": "req.vout", "retract": True, "why": "no regulated rail"})
    assert model.build(project=p)["threads"]["req.vout"]["still_live"] is False


# ---------------------------------------------------------------- designators

def test_the_legend_covers_only_what_is_on_this_board(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    d = model.build(project=p)["designators"]
    assert {r["prefix"] for r in d} == {"J", "U"}
    assert dict((r["prefix"], r["means"]) for r in d)["U"] == "integrated circuit"


def test_a_board_with_no_designators_gets_no_legend(board):
    p = board(blocks=(("BAT", "power_in"), ("MCU", "mcu")), links=(("BAT", "MCU"),),
              confirmed=False)
    assert model.build(project=p)["designators"] == []


# ---------------------------------------------------------------- helpers

def _append(project, record):
    import workspace
    path = workspace.projects_dir() / project / "decisions.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        import json
        fh.write(json.dumps({"ts": "2026-01-01T00:00:01", "by": "user", **record}) + "\n")


def _thread(home, project, record):
    import json
    path = home / "projects" / project / "threads.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": "2026-01-01T00:00:02", **record}) + "\n")
