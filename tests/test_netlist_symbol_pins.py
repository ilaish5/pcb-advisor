"""netlist.write refuses pin numbers the built library symbol does not have, listing the symbol's real pins."""
import serve
import store


def _setup(empty, nums):
    import partlib
    store.propose_bom(empty, "J1", {"mpn": "USB-C", "refs": ["J1"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    lib = partlib.library_dir(empty)
    (lib / "build").mkdir(parents=True, exist_ok=True)
    (lib / "manifest.json").write_text('{"J1": {"symbol": "USBC"}}', encoding="utf-8")
    (lib / "build" / "symbols_spec.txt").write_text(
        "SYMBOL|USBC|x|1\nPIN|A1B12|GND|eElectricPassive|0|0|0|1|100\nPIN|A4B9|VBUS|eElectricPassive|0|0|0|1|100\n", encoding="cp1252")
    return {"sections": [{"id": "A", "title": "T"}], "parts": [{"ref": "J1", "section": "A", "pins": [
        {"num": n, "name": nm, "net": "GND"} for n, nm in nums]}]}


def test_invented_pin_numbers_are_refused_with_the_real_ones(empty):
    errs = serve.netlist_symbol_errors(empty, _setup(empty, [("1", "GND"), ("2", "SBU1")]))
    assert errs and "A1B12=GND" in errs[0] and "A4B9=VBUS" in errs[0] and "pin 1" in errs[0]
    applied, _, refused = serve.apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _setup(empty, [("1", "FOO")])}])
    assert refused and "A4B9=VBUS" in refused[0] and not applied


def test_matching_pins_and_no_library_pass(empty):
    assert serve.netlist_symbol_errors(empty, _setup(empty, [("A1B12", "GND"), ("A4B9", "VBUS")])) == []
    assert serve.netlist_symbol_errors("nope-project-x", {"parts": []}) == []


def test_bom_propose_warns_when_a_passive_has_no_value(empty):
    act = lambda ch: [{"type": "bom.propose", "line": "R1", "changes": {"mpn": "0805W8F5101T5E", **ch}, "new": True, "reason": "r"}]
    applied, _, _ = serve.apply_actions(empty, act({}))
    assert "warning" in applied[0] and "no value" in applied[0] and serve.warning_of(applied[0])
    applied, _, _ = serve.apply_actions(empty, [{**act({"value": "5.1k"})[0], "line": "R2"}])
    assert applied == ["bom.propose:R2"]


def test_pin_names_fill_the_numbers_from_the_symbol(empty):
    data = _setup(empty, [("1", "gnd"), ("2", "VBUS")])
    notes = []
    assert serve.netlist_symbol_errors(empty, data, notes) == []
    assert [p["num"] for p in data["parts"][0]["pins"]] == ["A1B12", "A4B9"]
    assert notes == ["J1: pin numbers taken from the library symbol USBC (matched by pin name)"]
    applied, _, refused = serve.apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _setup(empty, [("1", "GND"), ("2", "VBUS")])}])
    assert not refused and "matched by pin name" in applied[0]


def test_ambiguous_or_unmatched_names_still_refuse(empty):
    for pins in ([("1", "GND"), ("2", "GND")], [("1", "GND"), ("2", "SBU1")]):
        data = _setup(empty, pins)
        errs = serve.netlist_symbol_errors(empty, data, [])
        assert errs and "A1B12=GND" in errs[0]
        assert [p["num"] for p in data["parts"][0]["pins"]] == [n for n, _ in pins]


def test_stale_symbol_is_skipped_after_a_part_change(empty):
    import json
    import partlib
    data = _setup(empty, [("1", "GND")])
    (partlib.library_dir(empty) / "manifest.json").write_text(json.dumps({"J1": {"symbol": "USBC", "mpn": "OLD-MPN"}}), encoding="utf-8")
    assert serve.netlist_symbol_errors(empty, data) == []


def test_stop_skips_actions_that_have_not_started(empty):
    import threading
    ev = threading.Event()
    ev.set()
    applied, _, refused = serve.apply_actions(empty, [{"type": "idea.ready"}], cancel=ev)
    assert not applied and "stopped by the student before it ran" in refused[0]
