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
    m = model.build(project=p)
    d = m["designators"]
    on_board = {b["id"] for b in m["blocks"]}
    # every class listed is one this board actually prints, and nothing more
    assert {r["prefix"] for r in d} == {
        pre for pre in model.DESIGNATORS
        if any(str(b.get("label") or b["id"]).split("\n")[0].startswith(pre)
               and str(b.get("label") or b["id"]).split("\n")[0][len(pre):].isdigit()
               for b in m["blocks"])}
    assert dict((r["prefix"], r["means"]) for r in d)["U"] == "integrated circuit"
    assert "U_REG" in on_board


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


# ---------------------------------------------------------------- stale premise

def test_a_decision_is_not_withdrawn_along_with_what_it_rested_on(battery_mcu):
    """Cascading would delete work the student did and never asked to undo."""
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    _append(p, {"node": "req.vout", "retract": True, "why": "no regulated rail"})
    m = model.build(project=p)
    assert "power.topology" in ids(m["answered"])


def test_but_it_says_the_premise_is_gone(battery_mcu):
    """Silence here is how a board keeps carrying rules nobody would choose
    again - the decision stands, the reason for it does not."""
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    _append(p, {"node": "req.vout", "retract": True, "why": "no regulated rail"})
    m = model.build(project=p)
    node = next(n for n in m["answered"] if n["id"] == "power.topology")
    assert node["rests_on"] == ["req.vout"]
    assert m["progress"]["resting_on_withdrawn"] == 1


def test_putting_the_question_back_clears_the_flag(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "power.topology", "value": "linear"})
    _append(p, {"node": "req.vout", "retract": True, "why": "no regulated rail"})
    _append(p, {"node": "req.vout", "value": "v3v3"})
    m = model.build(project=p)
    assert not [n for n in m["answered"] if n.get("rests_on")]


# ---------------------------------------------------------------- defaults

def test_the_corpus_answers_what_has_one_defensible_answer(battery_mcu):
    """Fourteen rows of equal weight is what a student called a mess. A question
    nobody would argue about should not cost them a decision."""
    m = model.build(project=battery_mcu)
    theirs = {n["id"] for n in m["answered"] if n["chosen_by"] != "corpus"}
    corpus = {n["id"]: n["chosen"] for n in m["answered"] if n["chosen_by"] == "corpus"}
    assert corpus.get("mcu.decoupling") == "per_pin"
    assert corpus.get("mcu.program") == "header"
    assert not (theirs & set(corpus))


def test_a_default_carries_the_sentence_the_student_will_read(battery_mcu):
    n = next(x for x in model.build(project=battery_mcu)["answered"]
             if x["id"] == "mcu.decoupling")
    assert n["default_why"] and n["default_provenance"] in model.PROVENANCE
    assert n["default_icon"]


def test_a_conditional_default_reads_an_earlier_answer(battery_mcu):
    """A cell's voltage is low enough that a diode's drop is a real cost, so the
    same question defaults differently on a battery than on a wall adapter."""
    p = battery_mcu
    _append(p, {"node": "req.iload", "value": "i_low"})   # unblocks protection
    m = model.build(project=p)
    assert next(x for x in m["answered"] if x["id"] == "power.protection")["chosen"] == "pfet"


def test_the_fallback_applies_when_no_condition_matches(board):
    p = board(blocks=(("J1", "power_in"), ("MCU", "mcu")), links=(("J1", "MCU"),),
              decisions=({"node": "req.source", "value": "wall"},
                         {"node": "req.iload", "value": "i_low"}))
    m = model.build(project=p)
    got = next(x for x in m["answered"] if x["id"] == "power.protection")
    assert got["chosen"] == "series_schottky" and got["chosen_by"] == "corpus"


def test_a_default_never_overrides_the_student(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "mcu.decoupling", "value": "bulk_only"})
    n = next(x for x in model.build(project=p)["answered"] if x["id"] == "mcu.decoupling")
    assert n["chosen"] == "bulk_only" and n["chosen_by"] == "user"


def test_a_default_is_never_written_to_the_log(battery_mcu, home):
    """A persisted default goes stale the moment the answer it keys on changes -
    the same bug class as a decision nobody can retract."""
    model.build(project=battery_mcu)
    lines = (home / "projects" / battery_mcu / "decisions.jsonl").read_text().splitlines()
    assert not any("mcu.decoupling" in l for l in lines)
    assert not any('"corpus"' in l for l in lines)


def test_a_default_still_locks_the_rules_that_follow_from_it(battery_mcu):
    m = model.build(project=battery_mcu)
    assert "mcu.decap.place" in ids(m["constraints"])


def test_who_decided_what_is_counted_apart(battery_mcu):
    """A tool that says twelve decisions when the student made three is lying
    about their work."""
    p = model.build(project=battery_mcu)["progress"]
    assert p["by_user"] == 3 and p["by_corpus"] >= 2
    assert p["by_user"] + p["by_corpus"] == p["answered"]


def test_withdrawing_a_question_stops_its_default_too(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "mcu.decoupling", "retract": True, "why": "no ICs on this board"})
    m = model.build(project=p)
    assert "mcu.decoupling" not in ids(m["answered"])
    assert "mcu.decap.place" not in ids(m["constraints"])


# ---------------------------------------------------------------- quantities

def test_a_question_can_ask_for_a_number(battery_mcu):
    """The tool walked a whole battery design and never asked how long it had to
    last - the most consequential number on the board - because every answer it
    could hold was one of a fixed list."""
    n = next(x for x in model.build(project=battery_mcu)["open"] if x["id"] == "req.runtime")
    assert n["answer"]["kind"] == "quantity" and n["answer"]["unit"] == "hours"
    assert not n.get("options")


def test_the_number_is_stored_as_a_number_and_shown_with_its_unit(battery_mcu):
    p = battery_mcu
    _append(p, {"node": "req.runtime", "value": 8760})
    n = next(x for x in model.build(project=p)["answered"] if x["id"] == "req.runtime")
    assert n["chosen"] == 8760 and n["unit"] == "hours"
    assert n["chosen_label"] == "8760 hours"


def test_the_rules_that_follow_quote_the_number_back(battery_mcu):
    """A rule about a quantity that cannot mention the quantity is a leaflet."""
    p = battery_mcu
    _append(p, {"node": "req.runtime", "value": 8760})
    live = [c for c in model.build(project=p)["constraints"] if c["from_node"] == "req.runtime"]
    assert live and all("8760" in c["text"] for c in live)
    assert not any("{value}" in c["text"] for c in live)


def test_a_value_outside_the_range_is_refused_with_the_range():
    spec = {"kind": "quantity", "unit": "hours", "min": 1, "max": 100000}
    for bad in (0, -5, 1e9):
        value, why = model.coerce_quantity(spec, bad)
        assert value is None and "1 to 100000 hours" in why


def test_a_value_that_is_not_a_number_is_refused():
    spec = {"kind": "quantity", "unit": "hours", "min": 1}
    for bad in ("a year", "", None, "8760 hours"):
        assert model.coerce_quantity(spec, bad)[0] is None


def test_a_number_written_as_text_is_still_a_number():
    """The browser sends the field as a string; the log should hold a number."""
    assert model.coerce_quantity({"kind": "quantity", "unit": "h"}, " 8760 ")[0] == 8760.0


def test_a_guard_going_false_takes_the_rules_but_leaves_the_answer(battery_mcu):
    """req.runtime only applies to a battery. Answer it, move to a wall adapter,
    and the answer used to stay with two cell-budget rules live on a board that
    has no cells - the same shape as a 3.3 V rail on a board with no regulator."""
    p = battery_mcu
    _append(p, {"node": "req.runtime", "value": 8760})
    assert [c for c in model.build(project=p)["constraints"] if c["from_node"] == "req.runtime"]

    _append(p, {"node": "req.source", "value": "wall"})
    m = model.build(project=p)
    n = next(x for x in m["answered"] if x["id"] == "req.runtime")
    assert n["chosen"] == 8760                      # their answer is not deleted
    assert n["rests_on"] == ["req.source"]          # but it is flagged
    assert not [c for c in m["constraints"] if c["from_node"] == "req.runtime"]
    assert {w["id"] for w in m["withheld"]} >= {"pwr.budget", "pwr.budget.sleep"}


def test_a_number_question_is_not_asked_when_its_guard_does_not_hold(board):
    p = board(blocks=(("J1", "power_in"), ("MCU", "mcu")), links=(("J1", "MCU"),),
              decisions=({"node": "req.source", "value": "wall"},))
    assert "req.runtime" not in ids(model.build(project=p)["open"])
