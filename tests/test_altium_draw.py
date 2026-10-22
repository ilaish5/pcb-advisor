"""altium.draw_schematic: the netlist -> script lines part is pure Python (scripts/altium/draw.py), the action asks the student
first (same quote guard as idea.confirm), and a sheet that already has parts is never wiped without replace."""
import pathlib

import pytest

import project as project_mod
import serve
import store
import workspace
from altium import bridge, draw
from altium.lib import read_schlib  # noqa: F401  (the real reader is replaced below; kept to show what the fake stands in for)
from test_altium_bridge import FakeAltium


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
    for bad in ("NET\tA", "NET\nB", "שם"):
        sheet = {"parts": [part("R1", [{"num": "1", "net": bad}, {"num": "2", "net": "GND"}])]}
        p = draw.plan_sheet(sheet, {"R1": SYMS["R1"]}, "l", "d")
        assert p["commands"] == [] and any("non-ASCII" in e for e in p["errors"]), bad


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
