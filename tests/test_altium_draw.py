"""altium.draw_schematic: the netlist -> script lines part is pure Python (scripts/altium/draw.py), the action asks the student
first (same quote guard as idea.confirm), and a sheet that already has parts is never wiped without replace."""
import pathlib

import pytest

import serve
import store
import workspace
from altium import bridge, draw
from altium.lib import read_schlib  # noqa: F401  (the real reader is replaced below; kept to show what the fake stands in for)
from test_altium_bridge import FakeAltium, fake  # noqa: F401  (fake: the fixture)


def symbol(name, pins):
    """A library symbol: pins = [(number, name, x, y, orientation)], 100 mil long."""
    return {"name": name, "pins": [{"number": n, "name": nm, "x": x, "y": y, "length": 100, "orientation": o, "part_id": 1}
                                   for n, nm, x, y, o in pins]}


RES = [("1", "1", -100, 0, 2), ("2", "2", 100, 0, 0)]
IC = [("1", "VIN", -300, 100, 2), ("2", "GND", -300, 0, 2), ("3", "EN", -300, -100, 2), ("4", "OUT", 300, 0, 0),
      ("5", "NC", 300, 100, 0)]
SHEET = {"id": "01", "title": "Power", "sections": [{"id": "PWR", "title": "Input"}],
         "parts": [
             {"ref": "U1", "section": "PWR", "pins": [{"num": "1", "name": "VIN", "net": "+5V"}, {"num": "2", "name": "GND", "net": "GND"},
                                                       {"num": "3", "name": "EN", "net": "ENABLE_SIGNAL"}, {"num": "4", "name": "OUT", "net": "+3V3"},
                                                       {"num": "5", "name": "NC", "net": "NC"}]},
             {"ref": "R1", "section": "PWR", "pins": [{"num": "1", "name": "1", "net": "+5V"}, {"num": "2", "name": "2", "net": "ENABLE_SIGNAL"}]},
             {"ref": "R2", "section": "PWR", "pins": [{"num": "1", "name": "1", "net": "ENABLE_SIGNAL"}, {"num": "2", "name": "2", "net": "GND"}]}]}
SYMS = {"U1": symbol("IC1", IC), "R1": symbol("RES", RES), "R2": symbol("RES", RES)}


def simulate(commands):
    """What Altium would save for these script lines, as read_schdoc returns it (pins already at their sheet position)."""
    doc = {"components": [], "wires": [], "net_labels": [], "power_ports": [], "ports": [], "junctions": [], "no_erc": []}
    syms = {s["name"]: s for s in SYMS.values()}
    for c in commands:
        if c[0] == "PLACE":
            _, _, ref, lib, _, x, y, n = c
            pins = [{"number": p["number"], "name": p["name"], "x": int(x) + p["x"], "y": int(y) + p["y"], "length": p["length"],
                     "orientation": p["orientation"], "electrical": 4, "hidden": False} for p in syms[lib]["pins"]]
            doc["components"].append({"ref": ref, "lib_ref": lib, "pins": pins, "footprint": "FP"})
        elif c[0] == "WIRE":
            doc["wires"].append({"points": [(int(c[2]), int(c[3])), (int(c[4]), int(c[5]))]})
        elif c[0] == "NETLABEL":
            doc["net_labels"].append({"text": c[5], "x": int(c[2]), "y": int(c[3])})
        elif c[0] == "POWER":
            doc["power_ports"].append({"text": c[6], "x": int(c[2]), "y": int(c[3])})
        elif c[0] == "NOERC":
            doc["no_erc"].append({"x": int(c[2]), "y": int(c[3])})
    return doc


def plan(**kw):
    return draw.plan_sheet(SHEET, SYMS, "lib.SchLib", "sheet.SchDoc", **kw)


# ---------------------------------------------------------------- the pure part

def test_nets_are_drawn_as_power_ports_or_net_labels():
    assert [draw.net_kind(n) for n in ("GND", "AGND", "+5V", "+3V3", "VCC", "3V3", "ENABLE_SIGNAL", "V_LED", "CC1")] == \
        ["gnd", "gnd", "rail", "rail", "rail", "rail", "label", "label", "label"]


def test_every_part_is_placed_with_its_library_pin_count():
    p = plan()
    assert not p["errors"]
    places = {c[2]: c for c in p["commands"] if c[0] == "PLACE"}
    assert set(places) == {"U1", "R1", "R2"}
    assert places["U1"][3] == "IC1" and places["U1"][4] == "lib.SchLib" and places["U1"][7] == "5" and places["R1"][7] == "2"
    assert p["commands"][0] == ("DRAWBEGIN", "sheet.SchDoc", "0") and p["commands"][-1] == ("SAVE", "sheet.SchDoc")


def test_connected_pins_get_a_stub_with_a_label_or_power_port_and_nc_a_no_erc_cross():
    p = plan()
    kinds = [c[0] for c in p["commands"]]
    assert kinds.count("NOERC") == 1 and p["no_erc"] == ["U1-5"]
    assert kinds.count("WIRE") == 8                   # 9 pins, one of them NC
    assert {c[5] for c in p["commands"] if c[0] == "NETLABEL"} >= {"ENABLE_SIGNAL"}
    assert {c[6] for c in p["commands"] if c[0] == "POWER"} >= {"GND", "+5V"}
    assert sorted(p["expected"]["GND"]) == ["R2-2", "U1-2"]


def test_open_pins_are_reported_not_drawn():
    sheet = {**SHEET, "parts": [{"ref": "R1", "pins": [{"num": "1", "net": "+5V"}, {"num": "2", "net": ""}]}]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
    assert any("open pin" in w for w in p["warnings"]) and [c[0] for c in p["commands"]].count("WIRE") == 1


def test_a_part_without_a_library_symbol_stops_the_plan():
    p = draw.plan_sheet(SHEET, {"R1": SYMS["R1"]}, "l", "d")
    assert p["commands"] == [] and any("U1" in e and "library" in e for e in p["errors"])


def test_parts_do_not_overlap_and_stay_on_the_grid_and_the_sheet():
    p = plan()
    boxes = []
    for part in p["parts"]:
        cell = draw.part_cell(next(x for x in SHEET["parts"] if x["ref"] == part["ref"]), SYMS[part["ref"]])
        bx0, by0, bx1, by1 = cell["box"]
        boxes.append((part["x"] + bx0, part["y"] + by0, part["x"] + bx1, part["y"] + by1))
        assert part["x"] % 100 == 0 and part["y"] % 100 == 0
        assert draw.AREA[0] <= boxes[-1][0] and boxes[-1][2] <= draw.AREA[2] and draw.AREA[1] <= boxes[-1][1]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


def test_a_design_too_big_for_one_sheet_is_refused_before_anything_is_drawn():
    parts = [{"ref": f"R{i}", "pins": [{"num": "1", "net": f"NET_NUMBER_{i}_LONG"}, {"num": "2", "net": "GND"}]} for i in range(1, 80)]
    p = draw.plan_sheet({"parts": parts}, {x["ref"]: SYMS["R1"] for x in parts}, "l", "d")
    assert p["commands"] == [] and any("does not fit" in e for e in p["errors"])


def test_a_stub_is_long_enough_for_its_label():
    assert draw.stub_length("A_VERY_LONG_NET_NAME") > draw.stub_length("A")


def test_the_drawn_sheet_matches_the_netlist():
    p = plan()
    assert draw.verify_sheet(p, simulate(p["commands"]), {"U1": "FP", "R1": "FP"}) == []


def test_a_missing_wire_a_short_pin_count_and_a_lost_footprint_are_all_found():
    p = plan()
    doc = simulate(p["commands"])
    doc["wires"].pop(0)
    doc["components"][1]["pins"].pop()
    doc["components"][2]["footprint"] = ""
    found = " | ".join(draw.verify_sheet(p, doc, {"R2": "FP"}))
    assert "should be on" in found and "has 1 pins" in found and "lost its footprint" in found


# ---------------------------------------------------------------- the action and the bridge

@pytest.fixture
def drawn(empty, home, monkeypatch):
    """A linked project with one netlist sheet, a library file and a stand-in Altium that saves what it is told to draw."""
    store.write_sheet(empty, "01", SHEET)
    fake = FakeAltium()
    saved = {}

    def run(commands, **kw):
        fake(commands, **kw)
        for c in commands:
            if c[0] == "DRAWCHECK" and (saved.get("components") or saved.get("wires")) and c[2] != "1":
                raise bridge.BridgeError("Altium refused a step: the sheet already has objects")
            if c[0] == "DRAWCHECK" and saved.get("modified"):
                raise bridge.BridgeError("Altium refused a step: the sheet is open in Altium with unsaved changes")
            if c[0] == "PLACE" and saved.get("fail_on") == c[2]:
                raise bridge.BridgeError(f"Altium refused a step: {c[2]} was placed with 1 pins")
        if any(c[0] == "PLACE" for c in commands):
            saved.clear()
            saved.update(simulate(commands))
        return []
    monkeypatch.setattr(bridge, "run_commands", run)
    workspace.set_value("altium.projects_dir", str(home / "altium"))
    bridge.new_project(empty)
    lp = bridge.library_paths(empty)
    lp["schlib"].parent.mkdir(parents=True, exist_ok=True)
    lp["schlib"].write_bytes(b"schlib")
    monkeypatch.setattr(bridge, "read_schlib", lambda path: {"symbols": list(SYMS.values())[:1] + [SYMS["R1"]]})
    monkeypatch.setattr(store, "bom_lines", lambda project: [{"key": r, "refs": [r]} for r in ("U1", "R1", "R2")])
    monkeypatch.setattr(store, "library_manifest", lambda project: {r: {"symbol": SYMS[r]["name"], "footprint": "FP"} for r in SYMS})
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "read_schdoc", lambda path: dict(saved) if saved else {"components": []})
    import checks.schematic as cs
    monkeypatch.setattr(cs, "check_schematic", lambda doc: {"findings": []})
    return empty, fake, saved


def test_draw_schematic_draws_saves_and_checks(drawn):
    project, fake, saved = drawn
    res = bridge.draw_schematic(project)
    assert res["parts"] == 3 and set(res["nets"]) == {"+5V", "GND", "ENABLE_SIGNAL", "+3V3"} and res["problems"] == []
    cmds = fake.flat()
    assert [c[0] for c in cmds].count("PLACE") == 3 and cmds[-1][0] in ("SAVE", "SAVEPRJ")
    assert any(e["op"] == "draw-schematic" for e in store.read_jsonl(store.pdir(project) / "altium-log.jsonl"))


def test_a_sheet_that_already_has_parts_is_refused_unless_replace_is_given(drawn):
    project, fake, saved = drawn
    bridge.draw_schematic(project)
    fake.runs.clear()
    with pytest.raises(bridge.BridgeError, match="already has"):
        bridge.draw_schematic(project)
    res = bridge.draw_schematic(project, replace=True)
    assert res["backup"] and [c for c in fake.flat() if c[0] == "DRAWBEGIN"][0][2] == "1"


def test_the_old_sheet_is_copied_to_the_backup_before_a_redraw(drawn):
    project, fake, saved = drawn
    doc = next(pathlib.Path(bridge._linked(project)).parent.glob("*.SchDoc"))
    doc.write_bytes(b"the student's drawing")
    saved["components"] = [{"ref": "C9"}]
    res = bridge.draw_schematic(project, replace=True)
    assert (pathlib.Path(res["backup"]) / doc.name).read_bytes() == b"the student's drawing"


def test_a_sheet_that_does_not_match_the_netlist_fails_loudly(drawn, monkeypatch):
    project, fake, saved = drawn
    real = draw.verify_sheet
    monkeypatch.setattr(draw, "verify_sheet", lambda *a, **k: real(*a, **k) + ["U1 has 3 pins on the sheet, the library symbol IC1 has 5"])
    with pytest.raises(bridge.BridgeError, match="does not match the netlist.*3 pins"):
        bridge.draw_schematic(project)


def test_the_library_must_be_built_first(drawn):
    project, _, _ = drawn
    bridge.library_paths(project)["schlib"].unlink()
    with pytest.raises(bridge.BridgeError, match="library"):
        bridge.draw_schematic(project)


def _run(project, act, said):
    return serve.apply_actions(project, [{"type": "altium.draw_schematic", **act}], last_user=said)


@pytest.fixture
def spy(monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "draw_schematic", lambda p, s=None, replace=False: seen.append(replace) or
                        {"parts": 3, "nets": ["GND"], "sheets": ["s"], "warnings": []})
    return seen


def test_the_action_waits_for_the_students_own_words(drawn, spy):
    project = drawn[0]
    applied, _, refused = _run(project, {}, "ok, continue")
    assert not spy and not applied and "Ask the student first" in refused[0]
    _, _, refused = _run(project, {"student_said": "please draw it for me"}, "ok, continue")
    assert not spy and refused
    applied, _, refused = _run(project, {"student_said": "draw it for me"}, "Yes please, draw it for me!")
    assert spy == [False] and applied[0].startswith("altium.draw_schematic: 3 parts") and not refused


def test_a_fragment_of_a_message_is_no_consent(drawn, spy):
    project = drawn[0]
    for said, user in (("draw it", "I'll draw it myself"), ("draw it", "I think I should draw it the first time, then you check it"),
                       ("draw", "no, don't draw anything yet please")):
        _, _, refused = _run(project, {"student_said": said}, user)
        assert refused, (said, user)
    assert not spy


def test_a_student_who_draws_it_themselves_never_triggers_the_action(drawn, spy):
    project = drawn[0]
    for user in ("I'll draw it myself", "I will draw it", "i draw it", "אני אשרטט בעצמי", "אני אצייר את זה", "אשרטט אני"):
        _, _, refused = _run(project, {"student_said": user}, user)
        assert refused and "themselves" in refused[0], user
    assert not spy


def test_lavad_is_not_a_negation(drawn, spy):
    project = drawn[0]
    applied, _, refused = _run(project, {"student_said": "תשרטט לבד"}, "תשרטט לבד")
    assert spy == [False] and applied and not refused


def test_replace_needs_its_own_quote_with_a_redraw_word(drawn, spy):
    project = drawn[0]
    said = "draw it and replace the old one"
    _, _, refused = _run(project, {"student_said": said, "replace": True}, said)
    assert not spy and "replaced" in refused[0]                      # no replace_said
    _, _, refused = _run(project, {"student_said": said, "replace": True, "replace_said": "draw it"}, said)
    assert not spy and refused                                        # a quote without a redraw word
    _, _, refused = _run(project, {"student_said": said, "replace": True, "replace_said": "replace the sheet"}, said)
    assert not spy and refused                                        # not their words
    applied, _, refused = _run(project, {"student_said": said, "replace": True, "replace_said": "replace the old one"}, said)
    assert spy == [True] and applied and not refused
    applied, _, _ = _run(project, {"student_said": "תשרטט מחדש", "replace": True, "replace_said": "מחדש"}, "תשרטט מחדש")
    assert spy == [True, True]


def test_replace_false_never_needs_the_second_quote(drawn, spy):
    _run(drawn[0], {"student_said": "draw it for me", "replace": False}, "draw it for me")
    assert spy == [False]


def test_a_refusal_from_the_bridge_is_reported_not_raised(drawn):
    project, fake, saved = drawn
    saved["components"] = [{"ref": "X1"}]
    applied, _, refused = serve.apply_actions(project, [{"type": "altium.draw_schematic", "student_said": "draw it for me"}], last_user="draw it for me")
    assert not applied and "altium.draw_schematic:" in refused[0]


def test_the_pascal_side_has_the_commands_the_planner_sends():
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    for name in {c[0] for c in plan()["commands"]}:
        assert f"Cmd = '{name}'" in pas, name
    assert "MoveToXY" in pas and "LoadComponentFromLibrary" in pas


# ---------------------------------------------------------------- what the planner refuses, and what the bridge protects

def part(ref, pins):
    return {"ref": ref, "pins": pins}


def test_a_pin_name_that_belongs_to_another_library_pin_is_an_error():
    sheet = {"parts": [part("R1", [{"num": "1", "name": "2", "net": "+5V"}, {"num": "2", "name": "1", "net": "GND"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
    assert p["commands"] == [] and any("pin 1 is 2 in the netlist, but 2 is pin 2" in e for e in p["errors"])


def test_an_alias_pin_name_is_a_warning_and_matched_by_number():
    sheet = {"parts": [part("R1", [{"num": "1", "name": "A", "net": "+5V"}, {"num": "2", "name": "2", "net": "GND"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
    assert not p["errors"] and any("pin 1 is called A in the netlist and 1 in the library" in w for w in p["warnings"])
    assert sorted(p["expected"]["+5V"]) == ["R1-1"]


def test_a_netlist_pin_the_library_symbol_lacks_stops_before_drawing():
    sheet = {"parts": [part("R1", [{"num": "1", "net": "+5V"}, {"num": "2", "net": "GND"}, {"num": "3", "name": "X", "net": "A"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
    assert p["commands"] == [] and any("netlist pin 3" in e for e in p["errors"])


def test_a_pin_the_netlist_does_not_list_is_a_warning_and_stays_undrawn():
    sheet = {"parts": [part("R1", [{"num": "1", "net": "+5V"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
    assert not p["errors"] and any("pin 2" in w and "not in the netlist" in w for w in p["warnings"])


def test_a_multi_part_symbol_is_refused_before_anything_is_drawn():
    two = symbol("OPAMP2", [("1", "OUT", 100, 0, 0), ("2", "IN", -100, 0, 2)])
    two["pins"][0]["part_id"] = 2
    sheet = {"parts": [part("U1", [{"num": "1", "net": "A"}, {"num": "2", "net": "B"}])]}
    p = draw.plan_sheet(sheet, {"U1": two}, "l", "d")
    assert p["commands"] == [] and any("several parts" in e for e in p["errors"])


def test_names_that_cannot_travel_to_altium_are_refused_up_front():
    for bad in ("R\t1", "R\n2", "שם"):           # a part ref cannot be renamed here (it is the link to the BOM); a net name can (see below)
        sheet = {"parts": [part(bad, [{"num": "1", "net": "A"}, {"num": "2", "net": "GND"}])]}
        p = draw.plan_sheet(sheet, {bad: SYMS["R1"]}, "l", "d")
        assert p["commands"] == [] and any("non-ASCII" in e for e in p["errors"]), bad
    for net in ("NET\tA", "NET\nB", "שם"):
        sheet = {"parts": [part("R1", [{"num": "1", "net": net}, {"num": "2", "net": "GND"}])]}
        p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
        assert p["errors"] == [] and net in p["renamed"], net


def test_a_non_ascii_section_title_is_only_a_warning_and_the_heading_falls_back():
    sheet = {"sections": [{"id": "A", "title": "מתח"}, {"id": "B", "title": "Plain"}],
             "parts": [{**part("R1", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), "section": "A"},
                       {**part("R2", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), "section": "B"}]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d")
    assert not p["errors"] and any("Section 1" in w for w in p["warnings"])
    frames = [c[6] for c in p["commands"] if c[0] == "FRAME"]
    assert frames == ["[advisor] Section 1", "[advisor] B - Plain"]
    assert all(all(ord(ch) < 127 for ch in a) for c in p["commands"] for a in c)


def test_hidden_pins_get_no_stub_and_a_differing_net_is_a_warning():
    ic = symbol("IC", [("1", "VCC", -100, 0, 2), ("2", "OUT", 100, 0, 0), ("3", "GND", 0, -100, 3)])
    ic["pins"][0]["conglomerate"] = 4 | 2
    sheet = {"parts": [part("U1", [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "OUT", "net": "SIG"},
                                   {"num": "3", "name": "GND", "net": "GND"}])]}
    p = draw.plan_sheet(sheet, {"U1": ic}, "l", "d")
    assert not p["errors"] and sorted(t for tags in p["expected"].values() for t in tags) == ["U1-2", "U1-3"]
    assert any("hidden pin 1 (VCC)" in w and "+3V3" in w for w in p["warnings"])
    sheet["parts"][0]["pins"][0]["net"] = "VCC"
    assert not any("hidden" in w for w in draw.plan_sheet(sheet, {"U1": ic}, "l", "d")["warnings"])


def test_a_sheet_with_only_wires_is_not_empty(drawn):
    project, fake, saved = drawn
    saved["wires"] = [{"points": [(0, 0), (1, 1)]}]
    saved["components"] = []
    with pytest.raises(bridge.BridgeError, match="already has"):
        bridge.draw_schematic(project)


def test_the_sheet_is_checked_in_altium_before_it_is_touched_and_a_refusal_is_not_reverted(drawn):
    project, fake, saved = drawn
    bridge.draw_schematic(project)
    saved["modified"] = True
    fake.runs.clear()
    with pytest.raises(bridge.BridgeError, match="unsaved changes"):
        bridge.draw_schematic(project, replace=True)
    names = [c[0] for c in fake.flat()]
    assert "DRAWCHECK" in names and "REVERT" not in names and "PLACE" not in names and "DRAWBEGIN" not in names


def test_a_run_that_fails_halfway_closes_the_sheet_without_saving(drawn):
    project, fake, saved = drawn
    saved["fail_on"] = "R1"
    with pytest.raises(bridge.BridgeError, match="closed in Altium without saving"):
        bridge.draw_schematic(project)
    assert [c[0] for c in fake.runs[-1]] == ["PROJECT", "REVERT"]


def test_the_pascal_side_never_wipes_without_replace_and_checks_for_nil_and_unsaved_changes():
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")
    body = pas[pas.index("procedure DrawBegin"):pas.index("procedure PlacePart")]
    assert body.index("Replace <> '1'") < body.index("RemoveKind")
    assert "DrawnCount" in body and "D.Modified" in pas[pas.index("procedure DrawCheck"):pas.index("procedure DrawBegin")]
    for name in ("PlacePart", "DrawWire", "DrawNetLabel", "DrawPower", "DrawNoErc"):
        seg = pas[pas.index(f"procedure {name}"):]
        seg = seg[:seg.index("\nend;")]
        assert "if (Sch = nil)" in seg, name


def test_draw_consent_refuses_a_negated_request():
    import serve
    for msg in ("Don't draw it, I want to try", "אל תשרטט, אני רוצה לנסות", "אני לא רוצה שתשרטט את זה"):
        assert serve._draw_consent({"student_said": msg}, msg) != "", msg
    assert serve._draw_consent({"student_said": "תשרטט אתה בבקשה"}, "תשרטט אתה בבקשה") == ""


def test_another_spelling_of_the_pin_name_is_silent_but_an_alias_swap_is_an_error():
    # the live run of 16/11: CTRL/CONT, RESET/RST on the 555 and A/K vs +/- on the LED filled four warnings
    ic = {"ref": "U1", "pins": [{"num": "1", "name": "VIN", "net": "+5V"}, {"num": "2", "name": "GROUND", "net": "GND"},
                                {"num": "3", "name": "ENABLE", "net": "X"}, {"num": "4", "name": "OUTPUT", "net": "Y"}]}
    p = draw.plan_sheet({"parts": [ic]}, {"U1": SYMS["U1"]}, "l", "d")
    assert not p["errors"] and not any("is called" in w for w in p["warnings"])
    led = {"ref": "D1", "pins": [{"num": "1", "name": "K", "net": "GND"}, {"num": "2", "name": "A", "net": "Y"}]}
    p = draw.plan_sheet({"parts": [led]}, {"D1": symbol("LED", [("1", "-", -100, 0, 2), ("2", "+", 100, 0, 0)])}, "l", "d")
    assert not p["errors"] and not any("is called" in w for w in p["warnings"])
    swap = {"ref": "U1", "pins": [{"num": "3", "name": "OUTPUT", "net": "X"}, {"num": "4", "name": "ENABLE", "net": "Y"}]}
    p = draw.plan_sheet({"parts": [swap]}, {"U1": SYMS["U1"]}, "l", "d")
    assert p["commands"] == [] and any("pin 3 is OUTPUT in the netlist, but OUTPUT is pin 4" in e for e in p["errors"])


def test_a_part_with_unverified_pins_is_named_in_its_section_heading_on_the_drawn_sheet():
    # spec principle 3: "unverified" stays visible on the student's own Altium sheet, not only in the advisor
    import copy
    sheet = copy.deepcopy(SHEET)
    sheet["parts"][0]["pins_source"] = "agent"
    p = draw.plan_sheet(sheet, SYMS, "lib.SchLib", "sheet.SchDoc")
    assert not p["errors"] and p["unverified"] == ["U1"]
    heads = [c[6] for c in p["commands"] if c[0] == "FRAME"]
    assert heads == ["[advisor] PWR - Input | pins not checked against a datasheet: U1"]


def test_a_sheet_with_every_pin_verified_has_a_plain_heading():
    p = plan()
    assert p["unverified"] == [] and [c[6] for c in p["commands"] if c[0] == "FRAME"] == ["[advisor] PWR - Input"]


# ---------------------------------------------------------------- section frames enclose their whole block

def _frames(p):
    return {c[6].split()[1]: tuple(int(v) for v in c[2:6]) for c in p["commands"] if c[0] == "FRAME"}


def _drawn_extent(p, sid_of_ref):
    """{section: [(x0, y0, x1, y1)]} of everything the commands draw for that section's parts: pin tips, wires, labels (by their
    text length), power ports. Read from the commands, not from the layout's own numbers."""
    ext = {}
    syms = {x["name"]: x for x in SYMS.values()}
    cur = None
    for c in p["commands"]:
        if c[0] == "PLACE":
            cur = c[2]
            ox, oy = int(c[5]), int(c[6])
            for pin in syms[c[3]]["pins"]:
                ext.setdefault(sid_of_ref[cur], []).append((ox + pin["x"], oy + pin["y"], ox + pin["x"], oy + pin["y"]))
        elif c[0] == "WIRE":
            ext[sid_of_ref[cur]].append((min(int(c[2]), int(c[4])), min(int(c[3]), int(c[5])),
                                         max(int(c[2]), int(c[4])), max(int(c[3]), int(c[5]))))
        elif c[0] == "NETLABEL":
            x, y, rot, text = int(c[2]), int(c[3]), int(c[4]), c[5]
            w = len(text) * draw.CHAR
            ext[sid_of_ref[cur]].append((x, y, x + (0 if rot else w), y + (w if rot else 0)))
        elif c[0] == "POWER":
            ext[sid_of_ref[cur]].append((int(c[2]) - 100, int(c[3]) - 100, int(c[2]) + 100, int(c[3]) + 100))
    return ext


def _sections_sheet(spec, extra=None):
    """spec: [(section id, title, [(ref, key of SYMS)])] -> (plan, {ref: section})."""
    sections = [{"id": sid, "title": title} for sid, title, _ in spec]
    parts, sec, keys = [], {}, {}
    for sid, _, refs in spec:
        for ref, key in refs:
            pins = [{"num": q["number"], "name": q["name"],
                     "net": "GND" if q["name"] == "GND" else "+5V" if q["name"] == "VIN" else f"N_{ref}_{q['number']}"}
                    for q in SYMS[key]["pins"]]
            parts.append({"ref": ref, "section": sid, "pins": pins, **(extra or {}).get(ref, {})})
            sec[ref], keys[ref] = sid, key
    return draw.plan_sheet({"sections": sections, "parts": parts}, {r: SYMS[k] for r, k in keys.items()}, "l", "d"), sec


def test_a_section_frame_encloses_everything_drawn_for_its_section():
    # a real IC symbol with long labels, power ports and a no-ERC pin, and resistors with labels: all of it inside its frame
    p, sec = _sections_sheet([("A", "MCU Decoupling and Core Regulator", [("U1", "U1"), ("R1", "R1"), ("R2", "R2"), ("U2", "U1")]),
                              ("B", "Crystal", [("R3", "R1"), ("R4", "R2")])])
    assert not p["errors"]
    frames = _frames(p)
    ext = _drawn_extent(p, sec)
    assert set(frames) == {"A", "B"} and set(ext) == {"A", "B"}
    for sid, (fx, fy, fw, fh) in frames.items():
        for x0, y0, x1, y1 in ext[sid]:
            assert fx <= x0 and fy <= y0 and x1 <= fx + fw and y1 <= fy + fh - draw.HEADER, (sid, (fx, fy, fw, fh), (x0, y0, x1, y1))


def test_three_or_more_section_frames_do_not_overlap_and_stay_between_the_border_and_the_title_block():
    rows = [("R%d" % i, "R1") for i in range(1, 15)]
    p, sec = _sections_sheet([("A", "First", rows[:5]), ("B", "Second", rows[5:9]), ("C", "Third", rows[9:12]), ("D", "Fourth", rows[12:])],
                             extra={"R1": {"pins_source": "agent"}})
    assert not p["errors"]
    frames = list(_frames(p).values())
    assert len(frames) == 4
    for i, (ax, ay, aw, ah) in enumerate(frames):
        for bx, by, bw, bh in frames[i + 1:]:
            assert ay >= by + bh or by >= ay + ah or ax + aw <= bx or bx + bw <= ax
        assert ax >= 0 and ax + aw <= draw.AREA[2] + draw.FRAME_PAD
        assert ay >= draw.AREA[1] and ay + ah <= draw.AREA[3]           # above the title block, below the top of the area


def test_a_design_that_fits_only_without_the_frame_margins_is_refused():
    rows = [("R%d" % i, "R1") for i in range(1, 80)]
    p, _ = _sections_sheet([("A", "Many", rows)])
    assert p["commands"] == [] and any("does not fit" in e for e in p["errors"])


def test_a_frame_never_reaches_below_the_drawing_area():
    # shrink the area until the cells still fit but the frame (a margin lower) would not
    cells = [("A", draw.part_cell(part("R1", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), SYMS["R1"]))]
    secs = [{"id": "A", "title": "T"}]
    pos, heads, problems = draw.layout(cells, secs)
    assert not problems
    fy = heads[0][0][1]
    cell_bottom = pos["R1"][1] + cells[0][1]["box"][1]
    tight = (draw.AREA[0], cell_bottom, draw.AREA[2], draw.AREA[3])         # the cell box touches the bottom edge: the frame would not fit
    assert fy < cell_bottom and draw.layout(cells, secs, tight)[2]


def test_a_part_with_a_pin_off_the_grid_does_not_move_the_next_section_off_it():
    odd = symbol("ODD", [("1", "1", -100, 50, 2), ("2", "2", 100, 0, 0)])        # a pin 50 mil off the grid
    sheet = {"sections": [{"id": "A", "title": "One"}, {"id": "B", "title": "Two"}],
             "parts": [{**part("R1", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), "section": "A"},
                       {**part("R2", [{"num": "1", "net": "Y"}, {"num": "2", "net": "GND"}]), "section": "B"}]}
    p = draw.plan_sheet(sheet, {"R1": odd, "R2": SYMS["R2"]}, "l", "d")
    assert not p["errors"]
    for c in p["commands"]:
        if c[0] == "PLACE":
            assert int(c[5]) % 100 == 0 and int(c[6]) % 100 == 0, c
        if c[0] == "FRAME":
            assert all(int(v) % 100 == 0 for v in c[2:6]), c
    r2 = next(c for c in p["commands"] if c[0] == "PLACE" and c[2] == "R2")
    for pin in SYMS["R2"]["pins"]:                                           # R2's pin tips sit on the grid
        assert (int(r2[5]) + draw.tip(pin)[0]) % 100 == 0 and (int(r2[6]) + draw.tip(pin)[1]) % 100 == 0


def test_the_sheet_estimate_uses_the_same_title_strip_height_as_the_drawing():
    cells = [("A", draw.part_cell(part("R1", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), SYMS["R1"]))]
    secs = [{"id": "A", "title": "T"}]
    short = draw.layout(cells, secs)[1][0][0][3]
    long_text = "[advisor] A - T | pins not checked against a datasheet: " + ", ".join(f"U{i}" for i in range(40))
    assert draw.layout(cells, secs, texts={"A": long_text})[1][0][0][3] > short
    many = [("A", draw.part_cell(part(f"R{i}", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}]), SYMS["R1"])) for i in range(1, 30)]
    assert draw.split_groups(many, secs)[1] == [] and draw.split_groups(many, secs, texts={"A": "x" * 6000})[1] == ["A"]


def test_every_frame_text_starts_with_the_advisor_tag_so_a_redraw_clears_only_ours():
    p, _ = _sections_sheet([("A", "One", [("R1", "R1")]), ("B", "Two", [("R2", "R2")])])
    texts = [c[6] for c in p["commands"] if c[0] == "FRAME"]
    assert len(texts) == 2 and all(t.startswith(draw.TAG) for t in texts)      # ClearFrames removes exactly the frames that start so
    assert not "Note: my own text frame".startswith(draw.TAG)                  # a student's frame has no tag: it stays


def test_the_pascal_frame_is_not_solid_and_the_hide_list_is_freed():
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")   # Pascal cannot run here
    assert "F.IsSolid := False;" in pas[pas.index("procedure AddFrame"):pas.index("procedure TitleBlock")]
    assert "Hide.Free;" in pas[pas.index("procedure LibHidePinNames"):pas.index("{ ---------------------------------------------------------------- package }")]


# ---------------------------------------------------------------- U7: the draw step solves these itself

def test_a_hebrew_net_name_is_transliterated_deterministically():
    assert draw.transliterate("אדמה") == "ADMH"
    assert draw.transliterate("שלום") == "SHLVM"
    assert draw.transliterate("Vcc_café") == "Vcc_cafe"          # NFKD drops the accent
    assert draw.transliterate("+5V") == "+5V" and draw.transliterate("GND") == "GND"
    assert draw.transliterate("\u22125V") == "-5V"                 # the Unicode minus keeps its meaning
    assert draw.transliterate("A\u2605B") == "A_B"
    assert draw.transliterate("GND_אנלוגי") == "GND_ANLVGY" and draw.net_kind("GND_ANLVGY") == "gnd"


def test_two_names_never_share_a_drawn_name():
    names = ["אדמה", "ADMH", "admh", "ADMH_2", "Café", "Cafe", "GND"]
    a = draw.net_aliases(names)
    assert a == draw.net_aliases(list(reversed(names)))                                          # no dependence on the order
    assert "ADMH" not in a and "GND" not in a                                                    # plain names keep their own
    drawn = [x.upper() for x in a.values()] + ["ADMH", "ADMH_2", "CAFE", "GND", "ADMH"]
    assert len(set(drawn)) == len(drawn) - 1                                                      # (ADMH twice above: admh and ADMH)
    assert a["Café"] == "Cafe_2"
    assert a["אדמה"].startswith("ADMH_") and a["אדמה"].upper() not in ("ADMH", "ADMH_2")


def test_a_non_ascii_net_is_drawn_under_its_ascii_name_and_reported():
    sheet = {"parts": [part("R1", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}]),
                       part("R2", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d")
    assert not p["errors"] and p["renamed"] == {"אדמה": "ADMH"}
    assert any("'אדמה' drawn as 'ADMH'" in w for w in p["warnings"])
    assert set(p["expected"]) == {"ADMH", "GND"}
    assert all(all(ord(ch) < 127 for ch in a) for c in p["commands"] for a in c)
    assert sheet["parts"][0]["pins"][0]["net"] == "אדמה"                     # the netlist is not rewritten


def test_the_read_back_compares_with_the_transliterated_names():
    sheet = {"parts": [part("R1", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}]),
                       part("R2", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}])]}
    p = draw.plan_sheet(sheet, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d")
    saved = simulate(p["commands"])
    assert draw.verify_sheet(p, saved) == []
    assert "ADMH" in str(saved) and "אדמה" not in str(saved)


def test_a_net_on_two_sheets_gets_the_same_drawn_name_on_both():
    a = draw.net_aliases(["אדמה"])
    one = draw.plan_sheet({"parts": [part("R1", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}])]}, {"R1": SYMS["R1"]}, "l", "d", aliases=a)
    two = draw.plan_sheet({"parts": [part("R2", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}])]}, {"R2": SYMS["R2"]}, "l", "d", aliases=a)
    assert set(one["expected"]) == set(two["expected"]) == {"ADMH", "GND"}


def _big():
    parts = [{"ref": f"R{i}", "section": "A" if i < 40 else "B",
              "pins": [{"num": "1", "net": f"NET_NUMBER_{i}_LONG"}, {"num": "2", "net": "SHARED_SIGNAL_NAME" if i in (1, 70) else "GND"}]}
             for i in range(1, 80)]
    return {"sections": [{"id": "A"}, {"id": "B"}], "parts": parts}


def test_a_too_big_design_names_the_sheets_it_needs_and_the_nets_between_them():
    sheet = _big()
    p = draw.plan_sheet(sheet, {x["ref"]: SYMS["R1"] for x in sheet["parts"]}, "l", "d")
    assert p["commands"] == [] and p["errors"]
    msg = p["errors"][0]
    assert "does not fit" in msg and "needs about" in msg and "SHARED_SIGNAL_NAME" in msg and "ports" in msg


def test_the_split_groups_sections_in_order_and_flags_a_section_too_big_alone():
    sheet = _big()
    cells = [(p["section"], draw.part_cell(p, SYMS["R1"])) for p in sheet["parts"]]
    groups, too_big = draw.split_groups(cells, sheet["sections"])
    assert [sid for g in groups for sid in g] == ["A", "B"] and groups[0][0] == "A"
    assert too_big          # 40 parts do not fit one sheet even alone
    small = [c for c in cells if c[0] == "A"][:5] + [("B", c) for _, c in cells[40:45]]
    assert draw.split_groups(small, sheet["sections"]) == ([["A", "B"]], [])


def _dirty_sheet(project, monkeypatch, saves=True):
    """Altium holds the project's sheet open with unsaved changes; a SAVE writes the file (or, with saves=False, does nothing)."""
    real = bridge.run_commands
    doc = next(pathlib.Path(bridge._linked(project)).parent.glob("*.SchDoc"))
    doc.write_bytes(b"the student's edits")
    state = {"dirty": True, "sent": []}

    def run(commands, **kw):
        state["sent"].append([c[0] for c in commands])
        if any(c[0] == "DOCSTATE" for c in commands):
            return ["docstate open modified=%d" % state["dirty"]] * sum(c[0] == "DOCSTATE" for c in commands)
        if any(c[0] == "SAVE" for c in commands) and saves:
            doc.write_bytes(b"the student's edits, saved")
            state["dirty"] = False
        return real(commands, **kw)
    monkeypatch.setattr(bridge, "run_commands", run)
    return doc, state


def test_an_unsaved_open_sheet_is_saved_first_and_the_draw_says_so(drawn, monkeypatch):
    project, fake, saved = drawn
    doc, state = _dirty_sheet(project, monkeypatch)
    res = bridge.draw_schematic(project, replace=True)
    sent = state["sent"]
    assert res["saved_first"] == [doc.name]
    assert res["warnings"][0] == f"saved {doc.name} before drawing (it had unsaved changes in Altium)"
    assert sent.index(["PROJECT", "SAVE"]) < next(i for i, s in enumerate(sent) if "DRAWCHECK" in s)
    assert (pathlib.Path(res["backup"]) / doc.name).read_bytes() == b"the student's edits, saved"


def test_a_save_that_does_not_happen_refuses_before_any_backup_or_drawing(drawn, monkeypatch):
    project, fake, saved = drawn
    doc, state = _dirty_sheet(project, monkeypatch, saves=False)
    with pytest.raises(bridge.BridgeError, match=r"save did not happen.*Ctrl\+S"):
        bridge.draw_schematic(project, replace=True)
    flat = [n for s in state["sent"] for n in s]
    assert "DRAWCHECK" not in flat and "PLACE" not in flat and "DRAWBEGIN" not in flat
    assert not (doc.parent / ".advisor-backup").exists()


def test_a_refusal_after_the_save_says_the_sheet_was_saved(drawn, monkeypatch):
    project, fake, saved = drawn
    doc, state = _dirty_sheet(project, monkeypatch)
    saved["modified"] = True                    # the stand-in Altium still refuses at DRAWCHECK
    with pytest.raises(bridge.BridgeError, match=rf"I saved {doc.name}.*Ctrl\+S"):
        bridge.draw_schematic(project, replace=True)


def test_when_altium_still_holds_unsaved_changes_the_refusal_says_what_to_click(drawn):
    project, fake, saved = drawn
    bridge.draw_schematic(project)
    saved["modified"] = True
    with pytest.raises(bridge.BridgeError, match=r"Ctrl\+S"):
        bridge.draw_schematic(project, replace=True)


def test_draw_schematic_reports_renamed_nets(drawn):
    project, fake, saved = drawn
    sh = store.load_sheet(project, "01")
    for p in sh["parts"]:
        for pin in p["pins"]:
            if pin["net"] == "ENABLE_SIGNAL":
                pin["net"] = "הפעלה"
    store.write_sheet(project, "01", sh)
    res = bridge.draw_schematic(project)
    drawn_name = draw.transliterate("הפעלה")
    assert res["renamed_nets"] == {"הפעלה": drawn_name} and drawn_name in res["nets"] and res["problems"] == []
    assert any(f"'הפעלה' drawn as {drawn_name!r}" in w for w in res["warnings"])


def test_a_path_with_a_non_ascii_character_is_an_error_not_a_question_mark():
    with pytest.raises(bridge.BridgeError, match="path"):
        bridge._ascii("C:\\Users\\שם\\x.SchDoc")
    assert bridge._ascii("café") == "cafe" and bridge._ascii("אדמה") == "ADMH"


# ---------------------------------------------------------------- one persisted alias map: draw, place and rules agree

def _rename_nets(project, mapping, sid="01"):
    sh = store.load_sheet(project, sid)
    for p in sh["parts"]:
        for pin in p["pins"]:
            pin["net"] = mapping.get(pin["net"], pin["net"])
    store.write_sheet(project, sid, sh)


def test_the_alias_map_is_persisted_and_stable(empty):
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "עב"}, {"num": "2", "net": "GND"}])]})
    assert draw.alias_map(empty) == {"עב": "AB"}
    assert (store.pdir(empty) / "net-names.json").is_file()
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "עב"}, {"num": "2", "net": "אב"}]),
                                             part("R2", [{"num": "1", "net": "AB_2"}, {"num": "2", "net": "GND"}])]})
    got = draw.alias_map(empty)
    assert got["עב"] == "AB" and got["אב"] == "AB_3"          # AB is taken, AB_2 is a plain net of the design
    assert draw.drawn_net_name(empty, "GND") == "GND" and draw.drawn_net_name(empty, "אב") == "AB_3"
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "אב"}, {"num": "2", "net": "GND"}])]})
    assert draw.alias_map(empty) == {"אב": "AB_3"}                # stays, although עב is gone and AB is free again
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "עב"}, {"num": "2", "net": "אב"}]), part("R2", [{"num": "1", "net": "AB"}, {"num": "2", "net": "GND"}])]})
    with pytest.raises(draw.AliasConflict):                      # a plain AB now would short עב's drawn name
        draw.alias_map(empty)


def test_sheet_two_never_shorts_two_nets_when_sheet_one_is_drawn_first(drawn):
    project, fake, saved = drawn
    _rename_nets(project, {"ENABLE_SIGNAL": "עב"})
    res = bridge.draw_schematic(project)
    assert res["renamed_nets"] == {"עב": "AB"}
    sh2 = {"title": "Second", "parts": [part("R9", [{"num": "1", "net": "אב"}, {"num": "2", "net": "עב"}])]}
    store.write_sheet(project, "02", sh2)
    names = draw.alias_map(project)
    assert names == {"עב": "AB", "אב": "AB_2"}


def test_a_transliteration_that_looks_like_a_supply_or_ground_stays_an_ordinary_net():
    for name, bare in (("ודד", "VDD"), ("גנד", "GND"), ("וסס", "VSS"), ("3ו3", "3V3")):
        assert draw.transliterate(name) == bare
        got = draw.assign_aliases({}, [name])[0][name]
        assert got == "N_" + bare, name
        assert draw.net_kind(got) == "label" and draw._power_kind(got) == "label"
        from altium import route
        assert not route._RAIL.match(got) and not route._is_gnd(got)
    # a name that already is a power / ground name keeps its meaning
    assert draw.assign_aliases({}, ["GND_אנלוגי"])[0]["GND_אנלוגי"] == "GND_ANLVGY"
    assert draw._power_kind("GND_ANLVGY") == "gnd"


def test_draw_then_place_use_the_same_names_end_to_end(drawn, monkeypatch):
    from altium import layout
    project, fake, saved = drawn
    _rename_nets(project, {"ENABLE_SIGNAL": "אדמה", "+3V3": "ADMH"})
    res = bridge.draw_schematic(project)
    assert res["problems"] == [] and res["renamed_nets"] == {"אדמה": "ADMH_2"}
    got = {}
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {r: ("u", "01") for r in ("U1", "R1", "R2")})
    monkeypatch.setattr(bridge, "_project_pcb", lambda project: pathlib.Path("B.PcbDoc"))
    monkeypatch.setattr(bridge, "_board_size", lambda project: (30, 25))
    monkeypatch.setattr(bridge, "_clearance_mm", lambda project: 0.2)
    monkeypatch.setattr(bridge, "design_problems", lambda project: [])

    def place_on(prj, pcb, pcblib, parts, **kw):
        got["parts"] = parts
        return {"placed": parts, "outline": [0, 0, 30, 25], "backup": "", "problems": [], "warnings": [], "drill_findings": [],
                "restored": False}
    monkeypatch.setattr(bridge, "place_on", place_on)
    bridge.place_pcb(project)
    parts = got["parts"]
    assert layout.text_problems(parts) == []                      # no refusal for the Hebrew net
    cmds = layout.plan_commands("B.PcbDoc", None, False, [{"ref": p["ref"], "footprint": "FP", "x": 0, "y": 0, "rot": 0} for p in parts],
                                {}, parts, "L.PcbLib")
    padnet = {(c[2], c[3]): c[4] for c in cmds if c[0] == "PADNET"}
    assert padnet[("R1", "2")] == "ADMH_2" and padnet[("U1", "4")] == "ADMH"        # the Hebrew net and the plain one: two nets
    assert all(all(ord(ch) < 127 for ch in a) for c in cmds for a in c)
    board = {"components": [{"ref": p["ref"], "pattern": "FP"} for p in parts],
             "pads": [{"ref": r, "name": n, "net": net} for (r, n), net in padnet.items()]}
    nets = [x for x in layout.verify_layout(board, parts) if " is on net " in x]
    assert nets == []                                             # the board pads agree with the drawn names: no false mismatch


def test_a_width_rule_on_a_hebrew_net_lands_on_the_right_net_and_is_found_again(lte, fake):
    import json
    import rule_kinds
    prj, pcb = _rules_board(lte, fake)
    store.write_sheet(lte, "99", {"parts": [part("R90", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "ADMH"}])]})
    rec = rule_kinds.build_attributes({"name": "W_heb", "kind": "Width", "scope1": "InNet('אדמה')", "scope2": "All",
                                       "values": {"min": "10mil", "pref": "20mil", "max": "50mil"}})
    (store.pdir(lte) / "rules.json").write_text(json.dumps([{"name": "W_heb", "kind": "Width", "scope1": "InNet('אדמה')",
                                                             "attributes": rec}], ensure_ascii=False), encoding="utf-8")
    todo, _ = bridge.rule_plan(lte, pcb)
    mine = [r for r, _ in todo if r["NAME"] == "W_heb"]
    assert mine and mine[0]["SCOPE1EXPRESSION"] == "InNet('ADMH_2')"           # not ADMH: that is the other net
    cmds = bridge.rule_commands(pcb, todo)
    assert all(f.isascii() for c in cmds for f in c)
    again = [r for r, _ in bridge.rule_plan(lte, pcb)[0] if r["NAME"] == "W_heb"]
    assert again and again[0]["SCOPE1EXPRESSION"] == "InNet('ADMH_2')"         # the next import sees the same name
    from altium import route
    assert route.rules_from_doc({"rules": [dict(mine[0], ENABLED="TRUE")]})["net_width"] == {"ADMH_2": route.rules_from_doc(
        {"rules": [dict(mine[0], ENABLED="TRUE")]})["net_width"]["ADMH_2"]}


def _rules_board(lte, fake):
    import project as project_mod
    res = bridge.new_project(lte)
    pcb = pathlib.Path(project_mod.altium_link(lte)["pcb_file"])
    pcb.write_bytes((pathlib.Path(__file__).parent / "fixtures" / "altium" / "rules-board.PcbDoc").read_bytes())
    fake.runs.clear()
    return pathlib.Path(res["project_file"]), pcb


# ---------------------------------------------------------------- a stale alias never blocks the student

def test_a_stale_alias_gives_way_when_the_net_is_renamed_to_that_plain_name(drawn, monkeypatch):
    project, fake, saved = drawn
    _rename_nets(project, {"ENABLE_SIGNAL": "אדמה"})
    assert bridge.draw_schematic(project)["renamed_nets"] == {"אדמה": "ADMH"}
    _rename_nets(project, {"אדמה": "ADMH"})                          # the student renames the net to the plain name
    assert draw.alias_map(project) == {}
    assert "אדמה" not in (store.pdir(project) / "net-names.json").read_text(encoding="utf-8")
    saved.clear()
    res = bridge.draw_schematic(project, replace=True)
    assert res["problems"] == [] and "ADMH" in res["nets"]
    monkeypatch.setattr(bridge, "_sch_links", lambda prj: {r: ("u", "01") for r in ("U1", "R1", "R2")})
    assert {p["ref"] for p in bridge._netlist_parts(project)} == {"U1", "R1", "R2"}


def test_a_new_plain_net_equal_to_the_drawn_name_of_a_removed_net_is_allowed(empty):
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "אדמה"}, {"num": "2", "net": "GND"}])]})
    assert draw.alias_map(empty) == {"אדמה": "ADMH"}
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "X"}, {"num": "2", "net": "GND"}])]})
    assert draw.alias_map(empty) == {}                                # stale, nobody uses ADMH: it stays in the file
    assert "אדמה" in (store.pdir(empty) / "net-names.json").read_text(encoding="utf-8")
    store.write_sheet(empty, "01", {"parts": [part("R1", [{"num": "1", "net": "ADMH"}, {"num": "2", "net": "GND"}])]})
    assert draw.alias_map(empty) == {}


def test_a_net_name_clash_never_fails_open(drawn, monkeypatch):
    project, fake, saved = drawn
    _rename_nets(project, {"ENABLE_SIGNAL": "עב"})
    draw.alias_map(project)
    store.write_sheet(project, "02", {"parts": [part("R9", [{"num": "1", "net": "AB"}, {"num": "2", "net": "עב"}])]})
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: pathlib.Path("B.PcbDoc"))
    monkeypatch.setattr(bridge.rules_mod, "read_pcbdoc", lambda p: {"rules": []})
    with pytest.raises(bridge.AliasError):
        bridge.rules_missing(project)                                 # route_pcb's gate: refuses, never "nothing missing"
    assert bridge.rules_never_imported(project) is True
    msgs = bridge.design_problems(project)
    assert len(msgs) == 1 and "could not be compared" in msgs[0]
