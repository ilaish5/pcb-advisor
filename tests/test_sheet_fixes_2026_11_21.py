"""Fixes from the live text verify of 2026-11-21: one sheet per SchDoc (a planned sheet named Main owns Main.SchDoc), removing and renaming
a netlist sheet, the designator staying beside its part, the consent guard reading "don't delete X" as no refusal to draw, the sheet
template (A4, 100 mil grid) the drawing assumes."""
import json
import pathlib

import pytest

import serve
import store
from altium import bridge, draw
from test_altium_draw import SHEET
from test_altium_draw_real_sheets import ROOT, SHEETS, lib_for
from test_no_placeholder_sheets import SHEET2, started  # noqa: F401
from test_altium_draw_text import FIX

PAS = (pathlib.Path(draw.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. one sheet, one file

def test_a_planned_sheet_named_main_owns_main_schdoc_and_sheet_02_does_not_take_it(started):  # noqa: F811
    project, fake, drawn_on = started
    store.write_sheet(project, "Main", {**SHEET, "id": "Main", "title": "Core"})
    prj = bridge._linked(project)
    out = bridge.add_sheet(project, "02")
    assert pathlib.Path(out["file"]).name == "02 Logic.SchDoc" and not out.get("adopted")      # the placeholder is not 02's
    out = bridge.add_sheet(project, "Main")
    assert pathlib.Path(out["file"]).name == "Main.SchDoc"
    files = {sid: bridge._sheet_doc(project, prj, sid, adopt=False) for sid in ("01", "02", "Main")}
    names = [f.name.lower() for f in files.values() if f is not None]
    assert len(names) == len(set(names)), files                                                 # no file holds two sheets
    assert files["Main"].name == "Main.SchDoc" and files["02"].name == "02 Logic.SchDoc"


def test_the_mapping_is_one_to_one_even_when_a_sheet_was_recorded_on_a_file_another_sheet_is_named_after(started):  # noqa: F811
    project, fake, drawn_on = started
    bridge.add_sheet(project, "02")                      # no sheet Main yet: 02 takes the empty placeholder, as before
    store.write_sheet(project, "Main", {**SHEET, "id": "Main", "title": "Core"})
    prj = bridge._linked(project)
    got = {sid: bridge._sheet_doc(project, prj, sid) for sid in ("02", "Main")}
    assert got["02"].name == "Main.SchDoc"               # 02 stays on its recorded file ...
    assert got["Main"] is None or got["Main"].name != "Main.SchDoc"      # ... and Main does not claim it a second time


# ---------------------------------------------------------------- 1b. remove / rename a netlist sheet

def test_remove_sheet_is_undoable_and_keeps_the_record(empty):
    store.write_sheet(empty, "01", SHEET)
    store.write_sheet(empty, "Main", {**SHEET, "id": "Main"})
    res = store.remove_sheet_logged(empty, "Main")
    assert res["ok"] and store.sheet_ids(empty) == ["01"]
    assert not store.remove_sheet_logged(empty, "Main")["ok"]            # already gone
    store.undo(empty, res["change"])
    assert store.sheet_ids(empty) == ["01", "Main"]


def test_rename_sheet_leaves_no_duplicate_and_refuses_a_taken_id(empty):
    store.write_sheet(empty, "Main", {**SHEET, "id": "Main", "title": "Core"})
    store.write_sheet(empty, "02", {**SHEET, "id": "02"})
    assert not store.rename_sheet_logged(empty, "Main", "02")["ok"]      # taken
    assert not store.rename_sheet_logged(empty, "Nope", "01")["ok"]
    res = store.rename_sheet_logged(empty, "Main", "01")
    assert res["ok"] and store.sheet_ids(empty) == ["01", "02"]
    assert store.load_sheet(empty, "01")["title"] == "Core" and store.load_sheet(empty, "01")["id"] == "01"
    for cid in reversed(res["changes"]):
        store.undo(empty, cid)
    assert store.sheet_ids(empty) == ["02", "Main"]


def test_the_agent_removes_or_renames_a_sheet_only_when_the_student_said_so(empty):
    store.write_sheet(empty, "Main", {**SHEET, "id": "Main"})
    store.write_sheet(empty, "02", {**SHEET, "id": "02"})

    def run(action, said):
        return serve.apply_actions(empty, [{**action, "student_said": said}], last_user=said)
    _, _, refused = run({"type": "netlist.remove", "sheet": "Main"}, "אל תמחק את Main")
    assert refused and store.sheet_ids(empty) == ["02", "Main"]
    _, _, refused = run({"type": "netlist.remove", "sheet": "Main"}, "do not delete Main")
    assert refused and store.sheet_ids(empty) == ["02", "Main"]
    _, _, refused = run({"type": "netlist.remove", "sheet": "Main"}, "hello there")
    assert refused
    applied, _, refused = run({"type": "netlist.rename", "sheet": "Main", "to": "01"}, "שנה את Main ל-01")
    assert applied and not refused and store.sheet_ids(empty) == ["01", "02"]
    applied, _, refused = run({"type": "netlist.remove", "sheet": "02"}, "please delete sheet 02")
    assert applied and store.sheet_ids(empty) == ["01"], refused


# ---------------------------------------------------------------- 2. the designator stays beside the part

def _dist(box, spot, h=draw.TEXT_H):
    """Distance in mils from a text's box (x, y, x + w, y + h) to the body box (0 when they touch)."""
    x, y, w = spot
    dx = max(box[0] - (x + w), x - box[2], 0)
    dy = max(box[1] - (y + h), y - box[3], 0)
    return max(dx, dy)


def test_a_wide_comment_does_not_pull_the_designator_away_from_the_body():
    body = (-200, -100, 200, 300)
    long = "SWITCH TACTILE SPST-NO 4 PAD 6X6MM SMD HIGH PROFILE WITH LONG NAME " * 2
    for ink in ([], [(-1000, 300, 1000, 450)], [(-1000, 300, 1000, 450), (-1000, -400, 1000, -100)],
                [(-1000, 300, 1000, 450), (-1000, -400, 1000, -100), (200, -100, 600, 300)]):
        t = draw.part_texts("SW1", long, body, ink)
        assert _dist(body, t["des"]) <= 500, (ink, t)
        assert t["com"][2] == len(long) * draw.TEXT_CHAR                # the whole comment, unchanged width
        assert all(not draw._hit((x, y, x + w, y + draw.TEXT_H), r, 20) for x, y, w in t.values() for r in ink)


@pytest.mark.parametrize("proj,name", SHEETS)
def test_every_real_sheet_has_each_designator_beside_its_body(proj, name):
    sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
    lib = lib_for(proj, sheet)
    for p in sheet["parts"]:
        cell = draw.part_cell(p, lib[p["ref"]])
        body = draw._body(lib[p["ref"]])
        assert _dist(body, cell["texts"]["des"]) <= 600, (p["ref"], body, cell["texts"])


def test_the_verify_fixture_switch_comment_is_whole_and_beside_the_body():
    import test_altium_draw_text as tt
    p, sh = tt.planned("Main")
    lib = tt._lib_for(sh)
    for part in sh["parts"]:
        cell = draw.part_cell(part, lib[part["ref"]])
        assert _dist(draw._body(lib[part["ref"]]), cell["texts"]["des"]) <= 600, (part["ref"], cell["texts"])
    assert FIX.is_dir()


# ---------------------------------------------------------------- 3. the consent guard

DRAW_ALL = "תצייר את הסכמה בכל ארבעת הגיליונות ותחליף את מה שיש"
DRAW_ALL_EN = "please draw the schematic on all four sheets and replace what is there"


def _consent(said, last, earlier=(), **extra):
    return serve._consent("draw", {"student_said": said, **extra}, last, list(earlier))


def test_a_negation_that_targets_another_action_is_no_refusal_to_draw():
    # the live run: the draw request, then "don't delete Main" (read as a stop), then "go on"
    for ask, deny in ((DRAW_ALL, "אל תמחק את Main"), (DRAW_ALL, "אל תסיר את גיליון 02, זה בסדר"), (DRAW_ALL_EN, "don't delete Main"),
                      (DRAW_ALL_EN, "please do not remove sheet 02"), (DRAW_ALL_EN, "never rename Main")):
        assert _consent(ask, "המשך", [deny, ask]) == "", deny
        assert _consent(ask, "go on", [deny, "ok", ask]) == "", deny
    msg = "אל תמחק את Main, תשרטט את הסכמה"            # one message: refuses the delete, asks for the draw
    assert _consent(msg, msg) == ""


def test_a_real_no_or_wait_after_the_request_still_blocks():
    for deny in ("חכה רגע", "אל תשרטט עדיין", "wait", "don't draw it yet", "stop", "לא, חכה", "אל תמחק את Main, ואל תשרטט"):
        assert _consent(DRAW_ALL, "המשך", [deny, DRAW_ALL]) != "", deny
        assert _consent(DRAW_ALL_EN, "go on", [deny, DRAW_ALL_EN]) != "", deny
    assert serve._STOP_ANY.search("אל תמחק את Main", "draw") is False
    assert serve._STOP_ANY.search("אל תמחק את Main. חכה", "draw") is True
    assert serve._STOP_ANY.search("אל תמחק את Main") is True                 # without a kind: the old reading, a no to anything


def test_a_later_explicit_request_overrides_an_earlier_refusal():
    refusal = ["אל תמחק את Main", "חכה, אל תשרטט"]
    assert _consent(DRAW_ALL, "המשך", [DRAW_ALL, *refusal]) == ""
    assert _consent(DRAW_ALL_EN, "go on", [DRAW_ALL_EN, "wait", "stop"]) == ""
    assert _consent(DRAW_ALL, DRAW_ALL, refusal, replace=True, replace_said="תחליף") == ""         # asked in this very message
    assert _consent(DRAW_ALL_EN, DRAW_ALL_EN, ["stop"], replace=True, replace_said="replace") == ""


# ---------------------------------------------------------------- 4/5. the sheet the drawing code assumes

def test_the_area_is_derived_from_the_sheet_and_frames_stay_inside_its_inner_border():
    w, h = draw.SHEET_SIZE
    assert draw.AREA[2] + draw.FRAME_PAD <= w - draw.SHEET_BORDER and draw.AREA[3] <= h - draw.SHEET_BORDER
    assert draw.AREA[0] >= draw.SHEET_BORDER and draw.AREA[1] >= draw.SHEET_BORDER
    for proj, name in SHEETS:
        sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
        plan = draw.plan_sheet(sheet, lib_for(proj, sheet), "l", "d")
        for c in (c for c in plan["commands"] if c[0] == "FRAME"):
            x, y, fw, fh = (int(v) for v in c[2:6])
            assert x >= draw.SHEET_BORDER and x + fw <= w - draw.SHEET_BORDER and y + fh <= h - draw.SHEET_BORDER, (proj, name, c[2:6])


def test_the_bridge_sets_the_sheet_the_drawing_assumes_when_it_draws_or_makes_a_skeleton():
    assert f"Sch.SheetStyle := {draw.SHEET_STYLE};" in PAS
    assert f"Sch.SnapGridSize := MilsToCoord({draw.GRID});" in PAS and f"Sch.VisibleGridSize := MilsToCoord({draw.GRID});" in PAS
    assert "Sch.SnapGridOn := True;" in PAS
    seg = PAS[PAS.index("procedure DrawBegin"):]
    seg = seg[:seg.index("\nend;")]
    assert "SheetSetup(Sch);" in seg and seg.index("SheetSetup(Sch);") < seg.index("ClearFrames(Path);")
    seg = PAS[PAS.index("procedure TitleBlock"):]
    assert "SheetSetup(Sch);" in seg[:seg.index("\nend;")]
    assert all(ord(ch) < 128 for ch in PAS)


# ---------------------------------------------------------------- 6. what the compile flagged: a plan that cannot make floating ports or doubly named nets

def _on(pt, a, b):
    (x, y), (x1, y1), (x2, y2) = pt, a, b
    return min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2) and (x2 - x1) * (y - y1) == (y2 - y1) * (x - x1)


@pytest.mark.parametrize("proj,name", SHEETS)
def test_every_power_port_and_label_sits_on_a_wire_and_no_wire_net_has_two_names(proj, name):
    sheet = json.loads((ROOT / proj / name).read_text(encoding="utf-8"))
    cmds = draw.plan_sheet(sheet, lib_for(proj, sheet), "l", "d")["commands"]
    segs = [((int(c[2]), int(c[3])), (int(c[4]), int(c[5]))) for c in cmds if c[0] == "WIRE"]
    par = list(range(len(segs)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i, (a, b) in enumerate(segs):
        for j, (c, e) in enumerate(segs):
            if i < j and (any(_on(q, a, b) for q in (c, e)) or any(_on(q, c, e) for q in (a, b))):
                par[find(i)] = find(j)
    names = {}
    for c in cmds:
        if c[0] in ("POWER", "NETLABEL"):
            pt = (int(c[2]), int(c[3]))
            hit = [i for i, (a, b) in enumerate(segs) if _on(pt, a, b)]
            assert hit, (c, "not on any wire")
            if c[0] == "POWER":
                assert any(pt in (segs[i][0], segs[i][1]) for i in hit), (c, "a power port must sit at a wire end")
            names.setdefault(find(hit[0]), set()).add(c[-1])
    assert all(len(v) == 1 for v in names.values()), [v for v in names.values() if len(v) > 1]


# ---------------------------------------------------------------- review round: stops, questions, negations, overwrites, atomic rename

@pytest.mark.parametrize("deny", ["wait until I delete the old parts", "not yet - I'm still removing parts", "אל תשנה כלום עדיין",
                                  "wait, I will rename the sheets first", "אל תשרטט, אני מוחק קודם"])
def test_a_stop_in_a_clause_with_a_delete_or_change_verb_still_stops(deny):
    assert serve._STOP_ANY.search(deny, "draw")
    assert _consent(DRAW_ALL, "המשך", [deny, DRAW_ALL]) != ""
    assert _consent(DRAW_ALL_EN, "go on", [deny, DRAW_ALL_EN]) != ""


def test_only_the_negation_of_the_other_verb_is_cut_out():
    assert not serve._STOP_ANY.search("don't delete Main", "draw") and not serve._STOP_ANY.search("אל תמחק את Main", "draw")
    assert not serve._STOP_ANY.search("never remove the old sheet", "draw")
    assert serve._STOP_ANY.search("don't draw or delete anything", "draw")
    assert serve._STOP_ANY.search("don't delete Main, wait", "draw")


EDIT_REFUSED = [
    ("netlist.remove", "Main", None, "should I delete Main?"),
    ("netlist.rename", "Main", "01", "how do I rename the sheet Main to 01?"),
    ("netlist.remove", "Main", None, "delete Main. wait, actually no"),
    ("netlist.remove", "Main", None, "remove Main, no wait"),
    ("netlist.remove", "Main", None, "never delete Main"),
    ("netlist.remove", "Main", None, "Main shouldn't be deleted"),
    ("netlist.remove", "Main", None, "no need to delete Main"),
    ("netlist.remove", "Main", None, "אסור למחוק את Main"),
    ("netlist.remove", "Main", None, "לא למחוק את Main"),
    ("netlist.remove", "Main", None, "אל תמחק את Main"),
    ("netlist.rename", "Main", "01", "אל תשנה את Main ל-01"),
    ("netlist.remove", "Main", None, "rename 02 to Power"),                     # the quote is about another sheet and another verb
    ("netlist.rename", "Main", "01", "delete Main"),                              # a remove word is no rename
    ("netlist.rename", "Main", "01", "rename Main"),                              # no new id in the quote
]


@pytest.mark.parametrize("kind,sheet,to,said", EDIT_REFUSED)
def test_a_sheet_is_never_changed_on_a_refusal_question_or_wrong_quote(kind, sheet, to, said):
    a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) != ""


def test_a_clear_instruction_still_changes_a_sheet():
    for kind, sheet, to, said in (("netlist.remove", "Main", None, "please delete the sheet Main"), ("netlist.remove", "Main", None, "תמחק את Main"),
                                  ("netlist.rename", "Main", "01", "rename Main to 01"), ("netlist.rename", "Main", "01", "שנה את Main ל-01")):
        a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
        assert serve._sheet_edit_consent(kind, a, said) == "", said


@pytest.mark.parametrize("said,word", [("תצייר את הסכמה אבל אל תמחק את מה שיש", "תמחק"), ("draw the schematic, don't replace anything", "replace"),
                                       ("draw the schematic without replacing what is there", "replacing"),
                                       ("draw the schematic but never overwrite the sheet", "overwrite")])
def test_a_negated_replace_word_does_not_allow_a_wipe(said, word):
    assert _consent(said, said, replace=True, replace_said=word) != ""
    assert _consent(said, said) == ""                                           # the draw itself is still asked for


def test_a_replace_word_that_is_asked_for_still_works():
    for said, word in (("תצייר את הסכמה ותחליף את מה שיש", "תחליף"), ("draw the schematic and replace what is there", "replace"),
                       ("תצייר את הסכמה מחדש", "מחדש")):
        assert _consent(said, said, replace=True, replace_said=word) == "", said


def test_a_new_sheet_never_overwrites_the_file_another_sheet_is_drawn_on(started):  # noqa: F811
    project, fake, drawn_on = started
    prj = bridge._linked(project)
    bridge.draw_schematic(project)                                    # 01 on Main.SchDoc, 02 on "02 Logic.SchDoc"
    assert store.remove_sheet_logged(project, "01")["ok"]
    assert store.rename_sheet_logged(project, "02", "01")["ok"]       # sheet 01 (Logic) now owns "02 Logic.SchDoc"
    store.write_sheet(project, "02", {**SHEET2, "id": "02"})          # a new sheet 02 with the same title
    assert store.sheet_docs(project)["01"] == "02 Logic.SchDoc"
    for call in (lambda: bridge.draw_schematic(project, replace=True), lambda: bridge.skeleton(project)):
        with pytest.raises(bridge.BridgeError, match="taken already"):
            call()
    assert bridge._sheet_doc(project, prj, "01", adopt=False).name == "02 Logic.SchDoc"


def test_two_sheets_recorded_on_one_file_are_an_error_not_a_shared_file(started):  # noqa: F811
    project, fake, drawn_on = started
    prj = bridge._linked(project)
    store.append(project, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"01": "X.SchDoc", "02": "X.SchDoc"}})
    with pytest.raises(bridge.BridgeError, match="both recorded"):
        bridge._sheet_doc(project, prj, "02")


def test_a_rename_is_one_change_and_its_undo_leaves_one_sheet_on_the_file(empty):
    store.write_sheet(empty, "02", {**SHEET, "id": "02", "title": "Logic"})
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"02": "02 Logic.SchDoc"}})
    res = store.rename_sheet_logged(empty, "02", "01")
    assert len(res["changes"]) == 1 and store.sheet_ids(empty) == ["01"] and store.sheet_docs(empty) == {"01": "02 Logic.SchDoc"}
    store.undo(empty, res["change"])
    assert store.sheet_ids(empty) == ["02"] and store.sheet_docs(empty) == {"02": "02 Logic.SchDoc"}
    res = store.rename_sheet_logged(empty, "02", "01")
    store.write_sheet(empty, "02", {**SHEET, "id": "02"})            # the old id is taken again
    with pytest.raises(store.UndoRefused):
        store.undo(empty, res["change"])
    assert store.sheet_ids(empty) == ["01", "02"] and store.sheet_docs(empty) == {"01": "02 Logic.SchDoc"}


def test_undoing_a_removal_refuses_when_its_file_belongs_to_another_sheet_now(empty):
    store.write_sheet(empty, "01", SHEET)
    store.write_sheet(empty, "02", {**SHEET, "id": "02"})
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"01": "A.SchDoc"}})
    res = store.remove_sheet_logged(empty, "01")
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"02": "A.SchDoc"}})
    with pytest.raises(store.UndoRefused):
        store.undo(empty, res["change"])
    assert store.sheet_ids(empty) == ["02"]


def test_the_title_block_step_checks_the_sheet_exists_before_the_setup():
    seg = PAS[PAS.index("procedure TitleBlock"):]
    seg = seg[:seg.index("\nend;")]
    assert seg.index("(Sch = nil)") < seg.index("SheetSetup(Sch);")


# ---------------------------------------------------------------- second review round

PART_OR_SELF = [
    ("netlist.remove", "Main", None, "remove the LED from sheet Main"),            # a part, not the sheet
    ("netlist.remove", "Main", None, "delete resistor R3 from Main"),
    ("netlist.remove", "Main", None, "תסיר את ה-LED מ-Main"),
    ("netlist.remove", "Main", None, "תמחק את הנגד מהגיליון Main"),
    ("netlist.remove", "Main", None, "I'll delete Main myself"),
    ("netlist.remove", "Main", None, "I will delete Main"),
    ("netlist.remove", "Main", None, "אני אמחק את Main בעצמי"),
    ("netlist.remove", "Main", None, "אמחק את Main"),
    ("netlist.rename", "Main", "01", "I'll rename Main to 01 myself"),
    ("netlist.rename", "Main", "01", "אשנה את Main ל-01"),
    ("netlist.rename", "Main", "01", "rename Main to 01, don't draw yet"),         # pinned: a stop anywhere in the message refuses (intended)
]


@pytest.mark.parametrize("kind,sheet,to,said", PART_OR_SELF)
def test_part_removal_and_do_it_myself_are_no_consent_to_change_a_sheet(kind, sheet, to, said):
    a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) != ""


@pytest.mark.parametrize("kind,sheet,to,said", [
    ("netlist.remove", "Main", None, "delete Main since it is not used"),
    ("netlist.remove", "Main", None, "תמחק את Main כי הוא לא בשימוש"),
    ("netlist.remove", "Main", None, "please remove the sheet Main, it is not needed"),
    ("netlist.rename", "Main", "01", "שנה את Main ל01"),
    ("netlist.rename", "Main", "01", "שנה את Main ל-01"),
    ("netlist.rename", "Main", "01", "תשנה את שם הגיליון Main ל01"),
    ("netlist.remove", "02", None, "delete sheet 02"),
])
def test_a_trailing_negation_or_a_hebrew_prefix_does_not_refuse_a_clear_request(kind, sheet, to, said):
    a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) == ""


def test_undoing_a_rename_refuses_when_the_old_file_belongs_to_another_sheet_now(empty):
    store.write_sheet(empty, "02", {**SHEET, "id": "02", "title": "Logic"})
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"02": "L.SchDoc"}})
    res = store.rename_sheet_logged(empty, "02", "01")
    store.write_sheet(empty, "05", {**SHEET, "id": "05"})
    store.append(empty, "altium-log.jsonl", {"ts": store.now(), "by": "test", "op": "sheet-docs", "sheet_docs": {"05": "L.SchDoc", "01": "L2.SchDoc"}})
    with pytest.raises(store.UndoRefused):
        store.undo(empty, res["change"])
    assert store.sheet_ids(empty) == ["01", "05"]


# ---------------------------------------------------------------- third review round: the sheet must be the verb's direct object

@pytest.mark.parametrize("kind,to,said", [
    ("netlist.remove", None, "delete the parts on Main"),
    ("netlist.remove", None, "remove the LED on Main"),
    ("netlist.remove", None, "delete everything on sheet Main"),
    ("netlist.remove", None, "תמחק את הנגד בגיליון Main"),
    ("netlist.remove", None, "תמחק את הנגד על Main"),
    ("netlist.remove", None, "remove the LED from Main"),
    ("netlist.remove", None, "remove D1 in Main"),
    ("netlist.rename", "01", "rename the title of Main to 01"),
    ("netlist.rename", "01", "שנה את הכותרת של Main ל-01"),
    ("netlist.remove", None, "תמחק את Main אבל רק אחרי שתשרטט"),
    ("netlist.remove", None, "delete Main, but only after you draw"),
    ("netlist.remove", None, "first draw, then delete Main"),
    ("netlist.remove", None, "תמחק את Main קודם"),
    ("netlist.remove", None, "תמחק את הנגד מהגיליון Main"),
])
def test_a_part_on_a_sheet_a_title_or_a_condition_is_no_consent_to_change_the_sheet(kind, to, said):
    a = {"type": kind, "sheet": "Main", "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) != ""


@pytest.mark.parametrize("kind,to,said", [
    ("netlist.remove", None, "תמחק מהר את Main"),                    # "מהר" is "quickly", not "from"
    ("netlist.remove", None, "delete Main now, please"),
    ("netlist.remove", None, "delete the sheet Main"),
    ("netlist.remove", None, "תמחק את גיליון Main"),
    ("netlist.remove", None, "Main should be deleted"),
    ("netlist.rename", "01", "rename the name of Main to 01"),
    ("netlist.rename", "01", "תשנה את שם הגיליון Main ל-01"),
    ("netlist.rename", "01", "Main should be renamed to 01"),
])
def test_the_sheet_as_the_direct_object_is_still_accepted(kind, to, said):
    a = {"type": kind, "sheet": "Main", "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) == "", said


# ---------------------------------------------------------------- fourth round: the whole clause must be the sheet shape

@pytest.mark.parametrize("kind,sheet,to,said", [
    ("netlist.remove", "Main", None, "delete Main's parts"),
    ("netlist.remove", "Main", None, "remove Main's LED"),
    ("netlist.remove", "Main", None, "delete the Main LED"),
    ("netlist.remove", "Main", None, "delete Main resistors"),
    ("netlist.remove", "Main", None, "תמחק את Main הנגדים"),
    ("netlist.remove", "Power", None, "delete the power LED"),                       # a LED, not sheet Power (case matters)
    ("netlist.rename", "Main", "01", "rename Main's title to 01"),
    ("netlist.rename", "Main", "01", "rename Main to 01 and the LED"),
    ("netlist.remove", "Main", None, "delete Main and the LED"),
    ("netlist.remove", "Main", None, "delete Main sheet parts"),
    ("netlist.rename", "Main", "01", "rename Main 01"),
    ("netlist.remove", "Main", None, "delete Main, delete the parts on it"),         # every clause with the verb has to fit
])
def test_words_after_the_sheet_name_make_it_about_something_else(kind, sheet, to, said):
    a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) != "", said


@pytest.mark.parametrize("kind,sheet,to,said", [
    ("netlist.remove", "Main", None, "delete Main sheet"),
    ("netlist.remove", "Main", None, "please delete Main entirely"),
    ("netlist.remove", "Main", None, "delete sheet Main from the project"),
    ("netlist.remove", "Main", None, "תמחק את גיליון Main לגמרי"),
    ("netlist.remove", "Main", None, "תמחק את Main מהפרויקט"),
    ("netlist.remove", "Power", None, "delete the sheet Power"),
    ("netlist.remove", "02", None, "delete the SHEET 02 completely"),
    ("netlist.rename", "Main", "01", "change the name of Main to 01"),
    ("netlist.rename", "Main", "01", "rename Main to 01 please"),
    ("netlist.rename", "Main", "01", "rename sheet Main to 01"),
    ("netlist.rename", "Main", "01", "שנה את Main ל01 בבקשה"),
    ("netlist.rename", "Main", "01", "Main should be renamed to 01"),
    ("netlist.remove", "Main", None, "Main must be deleted"),
])
def test_the_whole_clause_shape_is_accepted(kind, sheet, to, said):
    a = {"type": kind, "sheet": sheet, "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) == "", said


# ---------------------------------------------------------------- fifth round: the student's whole clause, not the agent's quote of it

@pytest.mark.parametrize("kind,sheet,to,said,quote", [
    ("netlist.remove", "Main", None, "delete the Main LED", "delete the Main"),
    ("netlist.remove", "Main", None, "delete Main's parts", "delete Main"),
    ("netlist.remove", "Main", None, "תמחק את Main הנגדים", "תמחק את Main"),
    ("netlist.rename", "Main", "01", "rename Main to 01.5", "rename Main to 01"),
    ("netlist.remove", "Main", None, "please delete Main and the LED, thanks", "delete Main"),
    ("netlist.remove", "Power", None, "delete the power LED", "delete the power"),
])
def test_a_partial_quote_of_a_longer_clause_is_no_consent(kind, sheet, to, said, quote):
    a = {"type": kind, "sheet": sheet, "student_said": quote, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) != "", (said, quote)


@pytest.mark.parametrize("kind,sheet,to,said,quote", [
    ("netlist.remove", "Main", None, "please, delete Main. We draw later.", "delete Main"),      # the clause ends at the comma / dot
    ("netlist.remove", "Main", None, "delete main", "delete main"),
    ("netlist.remove", "Power", None, "delete the sheet power", "delete the sheet power"),
    ("netlist.remove", "Main", None, "ותמחק את Main", "ותמחק את Main"),
    ("netlist.remove", "Main", None, "I'd like you to delete Main", "delete Main"),
    ("netlist.remove", "Main", None, "can you delete Main", "delete Main"),
    ("netlist.remove", "Main", None, "please can you delete the sheet Main", "delete the sheet Main"),
    ("netlist.rename", "Main", "01", "rename Main to 01.", "rename Main to 01"),
    ("netlist.remove", "Main", None, "first look at the board, delete Main", "delete Main"),      # "first" alone is no condition
])
def test_the_whole_clause_is_checked_and_polite_or_hebrew_lead_ins_are_fine(kind, sheet, to, said, quote):
    a = {"type": kind, "sheet": sheet, "student_said": quote, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) == "", (said, quote)


def test_a_question_is_still_a_question_but_a_polite_request_is_not():
    a = {"type": "netlist.remove", "sheet": "Main", "student_said": "delete Main"}
    for q in ("do you think we should delete Main", "should I delete Main", "do you want me to delete Main?"):
        assert serve._sheet_edit_consent("netlist.remove", a, q) != "", q


# ---------------------------------------------------------------- sixth round: a question or a hedge is no consent

@pytest.mark.parametrize("kind,to,said", [
    ("netlist.remove", None, "will you delete Main?"),
    ("netlist.remove", None, "can you delete Main? I'm not sure it's needed"),
    ("netlist.remove", None, "תוכל למחוק את Main?"),
    ("netlist.remove", None, "תמחק את Main?"),
    ("netlist.rename", "01", "can you rename Main to 01?"),
    ("netlist.remove", None, "could you delete Main?"),
    ("netlist.remove", None, "will you delete Main"),
    ("netlist.remove", None, "can you delete Main, I'm not sure"),
    ("netlist.remove", None, "maybe delete Main"),
    ("netlist.remove", None, "delete Main, or should I keep it"),
    ("netlist.remove", None, "אולי למחוק את Main"),
    ("netlist.remove", None, "תמחק את Main, אני לא בטוח"),
    ("netlist.remove", None, "תמחק את Main או שנשאיר"),
])
def test_a_question_or_a_hedge_is_no_consent_to_change_a_sheet(kind, to, said):
    a = {"type": kind, "sheet": "Main", "student_said": said.rstrip("?"), **({"to": to} if to else {})}
    a2 = {**a, "student_said": said}
    assert serve._sheet_edit_consent(kind, a2, said) != "", said


@pytest.mark.parametrize("kind,to,said", [
    ("netlist.remove", None, "can you delete Main"),
    ("netlist.remove", None, "could you delete Main"),
    ("netlist.remove", None, "would you please delete Main"),
    ("netlist.remove", None, "תוכל למחוק את Main"),
    ("netlist.remove", None, "אני רוצה שתמחק את Main"),
    ("netlist.rename", "01", "אני רוצה שתשנה את Main ל-01"),
    ("netlist.rename", "01", "can you rename Main to 01"),
])
def test_a_polite_or_that_form_request_without_a_question_is_accepted(kind, to, said):
    a = {"type": kind, "sheet": "Main", "student_said": said, **({"to": to} if to else {})}
    assert serve._sheet_edit_consent(kind, a, said) == "", said
