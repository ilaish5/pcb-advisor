"""A draft schematic can always be drawn (docs/DRAFT-SCHEMATIC.md): a part the library has no symbol for, no library at all, or a symbol
that does not fit the netlist's pins is drawn as a PLACEHOLDER (a rectangle with the netlist's own pins), every net still connected; the sheet
says DRAFT, the stage says draft (not done), store.manufacturing_warning keeps the outputs blocked until a redraw has the real symbols.
Altium is faked here; the live run is in the report."""
import os
import pathlib

import pytest

import stages
import store
import workspace
from altium import bridge, draw
from test_altium_bridge import FakeAltium
from test_altium_draw import SHEET, SYMS


# ---------------------------------------------------------------- the placeholder symbol (pure)

def part(ref, pins):
    return {"ref": ref, "pins": [{"num": n, "name": nm, "net": net} for n, nm, net in pins]}


def test_a_placeholder_keeps_the_netlists_pin_numbers_and_names_and_is_all_passive():
    ph = draw.placeholder(SHEET["parts"][0], draw.NO_SYMBOL, "PH_U1")
    sym = ph["symbol"]
    assert sorted(p["number"] for p in sym["pins"]) == ["1", "2", "3", "4", "5"]
    assert {p["number"]: p["name"] for p in sym["pins"]} == {"1": "VIN", "2": "GND", "3": "EN", "4": "OUT", "5": "NC"}
    assert {p["electrical"] for p in sym["pins"]} == {"Passive"} and not ph["warnings"]
    assert sym["name"] == "PH_U1" and sym["comment"] == "PLACEHOLDER: no library symbol yet" and sym["designator"] == "U?"
    assert ph["part"]["pins"][2]["net"] == "ENABLE_SIGNAL"                # the netlist's nets travel with the part
    assert sym["body"][0] < 0 < sym["body"][2] and sym["joined"] == [] and sym["pins"][0]["part_id"] == 1


def test_the_spec_lines_make_the_same_pins_the_symbol_dict_says(tmp_path):
    ph = draw.placeholder(SHEET["parts"][0], draw.NO_SYMBOL, "PH_U1")
    f = tmp_path / "spec.txt"
    f.write_bytes(("\n".join(["LIBRARY|x"] + ph["spec"]) + "\n").encode("cp1252"))
    got = bridge.spec_symbols(f)["PH_U1"]
    assert sorted(got) == sorted((p["number"], p["name"], "Passive") for p in ph["symbol"]["pins"])
    assert ph["props"] == "PH_U1=U|PLACEHOLDER: no library symbol yet"


def test_a_pin_the_library_cannot_hold_gets_the_next_free_number_and_says_so():
    p = part("U2", [("1", "A", "N1"), ("", "B", "N2"), ("1", "C", "N3"), ("TOOLONGNUM", "D", "N4"), ("5", "", "N5")])
    ph = draw.placeholder(p, draw.NO_SYMBOL, "PH_U2")
    nums = [x["num"] for x in ph["part"]["pins"]]
    assert nums[0] == "1" and nums[4] == "5" and len(set(nums)) == 5 and all(draw._PIN_NUM.fullmatch(n) for n in nums)
    assert len(ph["warnings"]) == 3 and "no pin number" in ph["warnings"][0] and "'TOOLONGNUM'" in ph["warnings"][2]
    assert ph["part"]["pins"][4]["name"] == "5"                          # a pin with no name is called by its number


def test_non_ascii_pin_names_are_drawn_as_ascii_and_the_netlist_is_not_changed():
    src = part("J1", [("1", "אדמה", "GND"), ("2", "VBUS", "+5V")])
    ph = draw.placeholder(src, draw.NO_SYMBOL, "PH_J1")
    assert all(draw._plain(p["name"]) for p in ph["symbol"]["pins"])
    assert src["pins"][0]["name"] == "אדמה"


def test_the_symbol_checks_say_why_a_library_symbol_cannot_draw_the_part():
    assert draw.symbol_problems(SHEET["parts"][1], SYMS["R1"]) == []
    wrong = part("R1", [("1", "1", "A"), ("2", "2", "B"), ("3", "3", "C")])
    assert any("netlist pin 3" in e for e in draw.symbol_problems(wrong, SYMS["R1"]))
    multi = {**SYMS["R1"], "pins": [{**p, "part_id": i + 1} for i, p in enumerate(SYMS["R1"]["pins"])]}
    assert any("several parts" in e for e in draw.symbol_problems(SHEET["parts"][1], multi))


# ---------------------------------------------------------------- the plan

def ph_for(*refs, why=draw.NO_SYMBOL):
    return {r: {"why": why, "name": draw.placeholder_name(r), "schlib": "draft.SchLib"} for r in refs}


def test_a_draft_plan_places_placeholders_from_the_draft_library_and_keeps_every_net():
    full = draw.plan_sheet(SHEET, SYMS, "lib.SchLib", "s.SchDoc")
    mixed = draw.plan_sheet(SHEET, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "lib.SchLib", "s.SchDoc", placeholders=ph_for("U1"))
    assert not mixed["errors"] and mixed["placeholders"] == [{"ref": "U1", "why": draw.NO_SYMBOL}]
    places = {c[2]: c for c in mixed["commands"] if c[0] == "PLACE"}
    assert places["U1"][3] == "PH_U1" and places["U1"][4] == "draft.SchLib" and places["R1"][4] == "lib.SchLib"
    assert {n: sorted(t) for n, t in mixed["expected"].items()} == {n: sorted(t) for n, t in full["expected"].items()}      # every net still joins the same pins
    assert mixed["no_erc"] == full["no_erc"] == ["U1-5"]
    assert mixed["parts"][0].get("placeholder") is True


def test_the_frame_title_says_draft_and_names_the_placeholders():
    mixed = draw.plan_sheet(SHEET, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d", placeholders=ph_for("U1"))
    frame = next(c for c in mixed["commands"] if c[0] == "FRAME")
    assert frame[-1] == "[advisor] PWR - Input | DRAFT, placeholder parts: U1".replace("[advisor]", draw.TAG)
    many = {"parts": [part(f"U{i}", [("1", "A", "N")]) for i in range(1, 9)], "sections": [{"id": "S", "title": "t"}]}
    text = next(c for c in draw.plan_sheet(many, {}, "l", "d", placeholders=ph_for(*[f"U{i}" for i in range(1, 9)]))["commands"] if c[0] == "FRAME")[-1]
    assert "U1, U2, U3, U4, U5, U6 +2" in text


def test_a_sheet_without_sections_gets_a_draft_frame_only_when_it_has_a_placeholder():
    flat = {"parts": SHEET["parts"]}
    plain = draw.plan_sheet(flat, SYMS, "l", "d")
    assert not [c for c in plain["commands"] if c[0] == "FRAME"]
    drafted = draw.plan_sheet(flat, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d", placeholders=ph_for("U1"))
    frames = [c for c in drafted["commands"] if c[0] == "FRAME"]
    assert len(frames) == 1 and "DRAFT, placeholder parts: U1" in frames[0][-1]


def test_a_sheet_with_no_placeholder_is_planned_exactly_as_before():
    """The commands of an all-good sheet: no DRAFT text, no placeholder, the project library in every PLACE (checked once against the
    plan of commit 20d85b4: identical)."""
    a = draw.plan_sheet(SHEET, SYMS, "lib.SchLib", "s.SchDoc")
    assert a == draw.plan_sheet(SHEET, SYMS, "lib.SchLib", "s.SchDoc", placeholders={}) and a["placeholders"] == []
    assert "DRAFT" not in " ".join(str(v) for c in a["commands"] for v in c)
    assert {c[4] for c in a["commands"] if c[0] == "PLACE"} == {"lib.SchLib"} and all("placeholder" not in p for p in a["parts"])
    assert [c[0] for c in a["commands"]][:2] == ["DRAWBEGIN", "FRAME"] and a["commands"][-1] == ("SAVE", "s.SchDoc")


def test_a_part_the_netlist_lists_no_pins_for_is_still_drawn_as_a_rectangle():
    lone = {"parts": [{"ref": "TP1", "pins": []}, SHEET["parts"][1]]}
    p = draw.plan_sheet(lone, {"R1": SYMS["R1"]}, "l", "d", placeholders=ph_for("TP1"))
    assert not p["errors"] and {c[2] for c in p["commands"] if c[0] == "PLACE"} == {"TP1", "R1"}


def test_a_part_with_no_symbol_and_no_placeholder_is_still_an_error():
    p = draw.plan_sheet(SHEET, {"R1": SYMS["R1"], "R2": SYMS["R2"]}, "l", "d")
    assert p["commands"] == [] and any("U1" in e for e in p["errors"])


# ---------------------------------------------------------------- the bridge, Altium faked

class World:
    """A linked project with one netlist sheet, the library files and a stand-in Altium that saves what it is told to draw. The draft
    library is made by build_draft_library for real, except that the read-back returns what was asked."""
    def __init__(self, project, home, monkeypatch):
        self.project, self.fake, self.saved, self.items, self.asked = project, FakeAltium(), {}, {}, {}
        self.lib_symbols = {"IC1": SYMS["U1"], "RES": SYMS["R1"]}
        self.monkeypatch = monkeypatch
        store.write_sheet(project, "01", SHEET)
        monkeypatch.setattr(bridge, "run_commands", self.run)
        workspace.set_value("altium.projects_dir", str(home / "altium"))
        bridge.new_project(project)
        self.lp = bridge.library_paths(project)
        self.lp["schlib"].parent.mkdir(parents=True, exist_ok=True)
        self.lp["schlib"].write_bytes(b"schlib")
        monkeypatch.setattr(bridge, "read_schlib", self.read_schlib)
        self.refs = ("U1", "R1", "R2")
        monkeypatch.setattr(store, "bom_lines", lambda p: [{"key": r, "refs": [r]} for r in self.refs])
        self.manifest = {r: {"symbol": SYMS[r]["name"], "footprint": "FP"} for r in SYMS}
        monkeypatch.setattr(store, "library_manifest", lambda p: self.manifest)
        import checks.schematic as cs            # imported BEFORE the patch: it binds read_schdoc at import, and would keep the fake for good
        import altium.schdoc
        read = lambda path: dict(self.saved) if self.saved else {"components": []}      # noqa: E731
        monkeypatch.setattr(altium.schdoc, "read_schdoc", read)
        monkeypatch.setattr(cs, "read_schdoc", read)
        monkeypatch.setattr(cs, "check_schematic", lambda doc: {"findings": []})

    def read_schlib(self, path):
        if str(path).endswith("-Draft.SchLib"):
            return {"symbols": [it["symbol"] for it in self.items.values()]}
        if not self.lib_symbols:
            raise OSError("not a library")
        return {"symbols": list(self.lib_symbols.values())}

    def run(self, commands, **kw):
        self.fake(commands, **kw)
        for c in commands:
            if c[0] == "DRAWCHECK" and (self.saved.get("components") or self.saved.get("wires")) and c[2] != "1":
                raise bridge.BridgeError("Altium refused a step: the sheet already has objects")
            if c[0] == "SYMBATCH" and str(c[1]).endswith("-Draft.SchLib"):
                spec = bridge.spec_symbols(c[2])
                self.items = {n: self.asked[n] for n in spec}
        if any(c[0] == "PLACE" for c in commands):
            self.saved.clear()
            self.saved.update(self.simulate(commands))
        return []

    def simulate(self, commands):
        doc = {"components": [], "wires": [], "net_labels": [], "power_ports": [], "ports": [], "junctions": [], "no_erc": []}
        syms = {s["name"]: s for s in SYMS.values()}
        for c in commands:
            if c[0] == "PLACE":
                _, _, ref, lib, schlib, x, y = c[:7]
                sym = self.items[lib]["symbol"] if lib in self.items else syms[lib]
                pins = [{"number": p["number"], "name": p["name"], "x": int(x) + p["x"], "y": int(y) + p["y"], "length": p["length"],
                         "orientation": p["orientation"], "electrical": 4, "hidden": False} for p in sym["pins"]]
                doc["components"].append({"ref": ref, "lib_ref": lib, "pins": pins, "footprint": "" if lib in self.items else "FP", "schlib": schlib})
            elif c[0] == "WIRE":
                doc["wires"].append({"points": [(int(c[2]), int(c[3])), (int(c[4]), int(c[5]))]})
            elif c[0] == "NETLABEL":
                doc["net_labels"].append({"text": c[5], "x": int(c[2]), "y": int(c[3])})
            elif c[0] == "POWER":
                doc["power_ports"].append({"text": c[6], "x": int(c[2]), "y": int(c[3])})
            elif c[0] == "NOERC":
                doc["no_erc"].append({"x": int(c[2]), "y": int(c[3])})
        return doc

    def commands(self, kind):
        return [c for c in self.fake.flat() if c[0] == kind]


@pytest.fixture
def world(empty, home, monkeypatch):
    w = World(empty, home, monkeypatch)
    real = draw.placeholder

    def record(p, why, name):                       # what the bridge asks Altium to make, kept so the fake can answer the read-back
        got = real(p, why, name)
        w.asked[name] = got
        return got
    monkeypatch.setattr(draw, "placeholder", record)
    return w


def test_with_no_library_at_all_every_part_is_drawn_as_a_placeholder_and_every_net_is_connected(world):
    world.lp["schlib"].unlink()
    res = bridge.draw_schematic(world.project)
    assert res["problems"] == [] and res["parts"] == 3 and {x["ref"] for x in res["placeholders"]} == {"U1", "R1", "R2"}
    assert {x["why"] for x in res["placeholders"]} == {draw.NO_SYMBOL} and "not built yet" in res["placeholders"][0]["detail"]
    assert set(res["nets"]) == {"+5V", "GND", "ENABLE_SIGNAL", "+3V3"}
    places = world.commands("PLACE")
    assert {c[3] for c in places} == {"PH_U1", "PH_R1", "PH_R2"} and {c[4] for c in places} == {str(bridge.draft_library_path(world.project))}
    assert any("DRAFT" in c[-1] for c in world.commands("FRAME"))
    # the draft library is made, read back, drawn from and closed again
    kinds = [c[0] for run in world.fake.runs for c in run]
    assert kinds.index("SYMBATCH") < kinds.index("PLACE") and "SYMREMOVE" in kinds and kinds.count("LIBCLOSE") == 2
    last = [e for e in store.read_jsonl(store.pdir(world.project) / "altium-log.jsonl") if e["op"] == "draw-schematic"][-1]
    assert [x["ref"] for x in last["draft"]["01"]] == ["U1", "R1", "R2"]


def test_a_part_without_a_symbol_in_a_built_library_is_the_only_placeholder(world):
    world.manifest["U1"]["symbol"] = "MISSING"
    res = bridge.draw_schematic(world.project)
    assert [x["ref"] for x in res["placeholders"]] == ["U1"] and "has no symbol for this part" in res["placeholders"][0]["detail"]
    places = {c[2]: c for c in world.commands("PLACE")}
    assert places["U1"][3] == "PH_U1" and places["R1"][3] == "RES" and places["R1"][4] == str(world.lp["schlib"])


def test_a_symbol_that_does_not_match_the_netlist_pins_is_a_placeholder_instead_of_a_refusal(world):
    sheet = {**SHEET, "parts": [{**SHEET["parts"][0], "pins": SHEET["parts"][0]["pins"] + [{"num": "9", "name": "X", "net": "SPARE"}]}, *SHEET["parts"][1:]]}
    store.write_sheet(world.project, "01", sheet)
    res = bridge.draw_schematic(world.project)
    assert [(x["ref"], x["why"]) for x in res["placeholders"]] == [("U1", draw.BAD_SYMBOL)] and "netlist pin 9" in res["placeholders"][0]["detail"]
    assert "SPARE" in res["nets"] and res["problems"] == []


def test_a_library_that_cannot_be_read_is_not_an_error(world):
    world.lib_symbols = {}
    res = bridge.draw_schematic(world.project)
    assert len(res["placeholders"]) == 3 and "could not be read" in res["placeholders"][0]["detail"]


def test_a_part_whose_footprint_is_in_error_is_drawn_with_its_symbol_and_listed(world, monkeypatch):
    monkeypatch.setattr(store, "footprint_error_parts", lambda p, refs=None, buyable=False: [{"line": "R1", "refs": ["R1"], "footprint": "FPX", "errors": ["bad pad"]}])
    res = bridge.draw_schematic(world.project)
    assert res["placeholders"] == [] and res["footprint_errors"] == ["R1"] and res["problems"] == []
    assert {c[3] for c in world.commands("PLACE")} == {"IC1", "RES"} and any("R1" in w and "footprint is in error" in w for w in res["warnings"])
    assert "SYMBATCH" not in [c[0] for c in world.fake.flat()]               # no draft library when nothing is a placeholder
    assert stages.draft_summary(world.project)["footprint_errors"] == ["R1"]
    with pytest.raises(bridge.BridgeError, match="footprint with errors"):    # the placement still refuses it
        bridge.refuse_footprint_errors(world.project, {"R1"}, "place")


def test_a_redraw_with_the_real_symbols_replaces_the_placeholders_and_clears_the_draft(world):
    world.lp["schlib"].unlink()
    bridge.draw_schematic(world.project)
    assert [x["ref"] for x in store.draft_parts(world.project)] == ["U1", "R1", "R2"]
    world.lp["schlib"].write_bytes(b"schlib")                                 # the library was built
    world.fake.runs.clear()
    with pytest.raises(bridge.BridgeError, match="already has"):              # never wiped without replace
        bridge.draw_schematic(world.project)
    res = bridge.draw_schematic(world.project, replace=True)
    assert res["placeholders"] == [] and res["backup"] and store.draft_parts(world.project) == []
    assert [c[3] for c in world.commands("PLACE")] == ["IC1", "RES", "RES"]
    assert [c for c in world.commands("DRAWBEGIN")][0][2] == "1"


def test_the_draft_is_kept_per_sheet_and_dropped_with_a_part_or_a_sheet_the_design_no_longer_has(world):
    world.lp["schlib"].unlink()
    bridge.draw_schematic(world.project)
    assert [(x["sheet"], x["ref"]) for x in store.draft_parts(world.project)] == [("01", "U1"), ("01", "R1"), ("01", "R2")]
    store.write_sheet(world.project, "01", {**SHEET, "parts": SHEET["parts"][:2]})        # R2 is gone from the netlist
    assert [x["ref"] for x in store.draft_parts(world.project)] == ["U1", "R1"]
    store.append(world.project, "altium-log.jsonl", {"op": "draw-schematic", "sheet_docs": {"01": "x.SchDoc"}})    # a record from before drafts
    assert store.draft_parts(world.project) == []


def test_the_outputs_stay_blocked_while_a_placeholder_is_on_the_sheet(world, monkeypatch):
    monkeypatch.setattr(store, "pins_to_resolve", lambda p: [])
    monkeypatch.setattr(store, "pin_gaps", lambda p: {"open": [], "unlisted": []})
    monkeypatch.setattr(store, "footprint_error_parts", lambda p, refs=None, buyable=False: [])
    assert store.manufacturing_warning(world.project) == ""
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    why = store.manufacturing_warning(world.project)
    assert why.startswith("Not made yet: ") and "the schematic is a draft: 1 part is a placeholder" in why and "U1" in why
    assert "draw the schematic again" in why
    gate = stages.outputs_stage(world.project, {})["gate"]
    assert gate["blocked"] and gate["why"] == why and gate["page"] == "sch"
    world.manifest["U1"]["symbol"] = "IC1"
    bridge.draw_schematic(world.project, replace=True)
    assert store.manufacturing_warning(world.project) == ""


def test_a_footprint_in_error_and_a_placeholder_are_both_named_in_the_gate(world, monkeypatch):
    monkeypatch.setattr(store, "pins_to_resolve", lambda p: [])
    monkeypatch.setattr(store, "pin_gaps", lambda p: {"open": [], "unlisted": []})
    monkeypatch.setattr(store, "footprint_error_parts", lambda p, refs=None, buyable=False: [{"line": "R1", "refs": ["R1"], "footprint": "FPX", "errors": ["bad pad"]}])
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    why = store.manufacturing_warning(world.project)
    assert why.startswith("Not made yet: 1 part has a footprint with errors") and "Also: the schematic is a draft" in why


def test_the_schematic_stage_says_draft_not_done_and_clean_only_after_the_redraw(world, monkeypatch):
    monkeypatch.setattr(store, "pin_gaps", lambda p: {"open": [], "unlisted": []})
    model = {"sheets": [{"id": "01"}], "sheet_gaps": {}}
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    st = stages.sch_stage(world.project, model)
    assert st["state"] == "in_progress" and st["reason"].startswith("Draft: 1 placeholder part (U1)") and st["next"]["act"] == "go:sch"
    summary = stages.draft_summary(world.project)
    assert summary["text"].startswith("Draft: 1 part drawn as a placeholder") and [x["ref"] for x in summary["parts"]] == ["U1"]
    world.manifest["U1"]["symbol"] = "IC1"
    bridge.draw_schematic(world.project, replace=True)
    assert stages.sch_stage(world.project, model)["state"] == "clean" and stages.draft_summary(world.project)["text"] == ""


def test_open_pins_and_placeholders_are_both_said_by_the_schematic_stage(world, monkeypatch):
    monkeypatch.setattr(store, "pin_gaps", lambda p: {"open": [{"sheet": "01", "ref": "U1", "num": "3", "name": "EN"}], "unlisted": []})
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    st = stages.sch_stage(world.project, {"sheets": [{"id": "01"}], "sheet_gaps": {}})
    assert st["state"] == "issues" and "1 open pin" in st["reason"] and "1 placeholder part (draft)" in st["reason"] and st["open"] == 2


def test_the_model_carries_the_draft_for_the_page(world):
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    out = stages._model(world.project, {"sheets": [{"id": "01"}]})
    assert out["draft"]["parts"][0]["ref"] == "U1" and "placeholder" in out["draft"]["text"]


# ---------------------------------------------------------------- the draft library, the pre-check

def test_the_draft_library_is_read_back_and_a_difference_stops_the_draw_before_anything_is_drawn(world, monkeypatch):
    world.lp["schlib"].unlink()
    real = world.read_schlib

    def wrong(path):
        got = real(path)
        if str(path).endswith("-Draft.SchLib"):
            got["symbols"][0] = {**got["symbols"][0], "pins": got["symbols"][0]["pins"][:-1]}
        return got
    monkeypatch.setattr(bridge, "read_schlib", wrong)
    with pytest.raises(bridge.BridgeError, match="placeholder symbols could not be made.*pins differ.*Nothing was drawn"):
        bridge.draw_schematic(world.project)
    assert not world.commands("PLACE") and not world.commands("DRAWBEGIN")


def test_the_draft_library_never_goes_into_the_project_library(world):
    assert bridge.draft_library_path(world.project) != world.lp["schlib"] and bridge.draft_library_path(world.project).parent == world.lp["folder"]
    assert bridge.draft_library_path(world.project).name.endswith("-Draft.SchLib")


def test_the_library_is_built_first_only_for_a_part_it_may_give_a_symbol(world, monkeypatch):
    monkeypatch.setattr(bridge, "library_stale", lambda p: True)
    assert bridge.draw_needs_library(world.project) is False                  # every part has its symbol
    world.manifest["U1"]["symbol"] = "MISSING"
    assert bridge.draw_needs_library(world.project) is True and bridge.draw_needs_library(world.project, "02") is False
    monkeypatch.setattr(bridge, "library_stale", lambda p: False)
    assert bridge.draw_needs_library(world.project) is False                  # an up to date library will not gain a symbol from a build


def test_the_sources_say_the_draft_is_not_wiped_and_the_old_refusals_are_gone():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "altium" / "bridge.py").read_text(encoding="utf-8")
    body = src[src.index("def draw_schematic("):src.index("def _tool_made_sheets")]
    assert "refuse_footprint_errors" not in body and "library_not_built" not in body and "I never wipe a drawing" in body


def test_the_board_is_not_placed_from_a_draft_schematic(world, monkeypatch):
    """A part placed now is linked to the placeholder's schematic id (_sch_links); the redraw makes a new component with a new id, and Update PCB would add the part again."""
    monkeypatch.setattr(bridge, "_project_pcb", lambda p: world.lp["folder"] / "x.PcbDoc")
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    with pytest.raises(bridge.BridgeError, match="still a draft: U1 is a placeholder.*Nothing was changed"):
        bridge.place_pcb(world.project)


def _doc_path(world):
    import project as project_mod
    return pathlib.Path(project_mod.altium_link(world.project)["project_file"]).parent / store.sheet_docs(world.project)["01"]


def test_a_failed_or_restored_draw_record_does_not_clear_the_draft(world):
    world.lp["schlib"].unlink()
    bridge.draw_schematic(world.project)
    for extra in ({"error": "Altium refused a step"}, {"restored": ["01 Power.SchDoc"]}, {"failed": ["01"]}):
        store.append(world.project, "altium-log.jsonl", {"op": "draw-schematic", "sheet_docs": {"01": "x.SchDoc"}, **extra})
        assert [x["ref"] for x in store.draft_parts(world.project)] == ["U1", "R1", "R2"], extra


def test_a_part_the_student_drew_by_hand_in_altium_is_no_longer_a_placeholder(world, monkeypatch):
    """A multi-part symbol is a placeholder that says "draw it by hand": the hand drawing, saved, lifts it. So does a restored backup."""
    world.lp["schlib"].unlink()
    bridge.draw_schematic(world.project)
    path = _doc_path(world)
    path.write_bytes(b"schdoc")
    reads = []
    held = {"components": [{"ref": "U1", "lib_ref": "STM32_UNIT_A"}, {"ref": "R1", "lib_ref": "PH_R1"}, {"ref": "R2", "lib_ref": "PH_R2"}]}
    import altium.schdoc
    monkeypatch.setattr(altium.schdoc, "read_schdoc", lambda p: (reads.append(p), held)[1])
    assert len(store.draft_parts(world.project)) == 3 and not reads                  # the file is not newer than the draw: not even read
    later = path.stat().st_mtime + 120
    os.utime(path, (later, later))                                                   # saved by the student after the draw
    assert [x["ref"] for x in store.draft_parts(world.project)] == ["R1", "R2"] and reads
    held["components"] = [c for c in held["components"] if c["ref"] != "R1"]          # a part deleted from the sheet is no placeholder either
    assert [x["ref"] for x in store.draft_parts(world.project)] == ["R2"]
    monkeypatch.setattr(altium.schdoc, "read_schdoc", lambda p: (_ for _ in ()).throw(OSError("locked")))
    assert len(store.draft_parts(world.project)) == 3                                # cannot be read: stays a draft (fail closed)


def test_the_layout_stage_sends_the_student_to_the_schematic_while_it_is_a_draft(world):
    world.manifest["U1"]["symbol"] = "MISSING"
    bridge.draw_schematic(world.project)
    st = stages.pcb_stage(world.project, {}, {})
    assert st["state"] == "not_started" and "still a draft" in st["reason"] and st["next"]["act"] == "go:sch"
    world.manifest["U1"]["symbol"] = "IC1"
    bridge.draw_schematic(world.project, replace=True)
    assert stages.pcb_stage(world.project, {}, {})["next"]["act"] == "go:pcb"


def test_the_chat_draw_goes_on_when_the_library_build_in_the_same_turn_is_refused(world, monkeypatch):
    """[library.build, altium.draw_schematic] from the agent: the build is refused, the draw still runs and says what is a placeholder."""
    import serve
    world.lp["schlib"].unlink()
    said = "תצייר אתה את הסכמה באלטיום"

    def broken(project):
        raise bridge.BridgeError("The library data has no symbols to build.")
    monkeypatch.setattr(bridge, "build_library", broken)
    applied, _, refused = serve.apply_actions(world.project, [{"type": "library.build"}, {"type": "altium.draw_schematic", "student_said": said}],
                                              last_user=said, chat=[{"role": "user", "text": said}])
    assert any(r.startswith("library.build") for r in refused)
    draw_done = [a for a in applied if a.startswith("altium.draw_schematic")]
    assert draw_done and "DRAFT" in draw_done[0] and "U1" in draw_done[0], (applied, refused)
    assert {x["ref"] for x in store.draft_parts(world.project)} == {"U1", "R1", "R2"}
