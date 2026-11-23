"""The agent cannot clear the open-pin gate silently: NC on an open / unlisted pin of the current netlist waits as one proposal the
student approves with one click, unless the student's own message in that turn asked for NC. New sheets with NC per datasheet are free."""
import pin_decisions
import serve
import store
from test_chat_turns import call, server  # noqa: F401
from test_unverified_pins import _add


def _sheet(empty):
    _add(empty, "U1", "ABCD1234")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "EN", "net": ""},
                                                {"num": "3", "name": "IO", "net": ""}]}]})
    pin_decisions.accept(empty, "U1")


def _nc_data(extra_net="+5V"):
    return {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": extra_net}, {"num": "2", "name": "EN", "net": "NC"},
                                                {"num": "3", "name": "IO", "net": "NC"}]}]}


def _nets(empty):
    return {p["num"]: p["net"] for p in store.load_sheet(empty, "01")["parts"][0]["pins"]}


def test_agent_nc_on_open_pins_becomes_one_proposal_not_a_silent_mark(empty):
    _sheet(empty)
    applied, _, refused = serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data()}], last_user="please fix the sheet")
    assert not refused and "left open" in applied[0]
    assert _nets(empty) == {"1": "+5V", "2": "", "3": ""}                       # the rest of the write landed, the NC marks did not
    assert [(i["ref"], i["num"]) for i in store.nc_proposal(empty)] == [("U1", "2"), ("U1", "3")]
    assert store.manufacturing_warning(empty)                                  # the gate is still closed
    res = store.approve_nc(empty)                                              # one click
    assert res["marked"] == 2 and _nets(empty) == {"1": "+5V", "2": "NC", "3": "NC"}
    assert store.manufacturing_warning(empty) == "" and store.nc_proposal(empty) == []


def test_untick_some_and_dismiss(empty, server):
    _sheet(empty)
    serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data()}], last_user="fix")
    code, body = call(server, "POST", "/api/nc/approve", empty, {"items": [{"sheet": "01", "ref": "U1", "num": "3"}]})
    assert code == 200 and body["marked"] == 1 and _nets(empty)["2"] == "" and _nets(empty)["3"] == "NC"
    assert store.nc_proposal(empty) == []                                      # the unticked one is dropped, not kept pending
    serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data()}], last_user="fix")
    assert call(server, "POST", "/api/nc/dismiss", empty, {})[0] == 200 and store.nc_proposal(empty) == []


def test_student_asking_for_nc_in_the_same_turn_applies_directly(empty):
    _sheet(empty)
    said = "mark the open pins as NC"
    applied, _, _ = serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data(), "student_said": said}], last_user=said)
    assert _nets(empty) == {"1": "+5V", "2": "NC", "3": "NC"} and store.nc_proposal(empty) == []
    assert store.manufacturing_warning(empty) == ""


def test_a_quote_that_does_not_ask_for_nc_or_a_question_or_a_button_message_still_holds(empty):
    for said, generated in (("fix the sheet", False), ("should I mark the open pins as NC?", False), ("I'll mark them NC myself", False)):
        _sheet(empty)
        serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data(), "student_said": said}], last_user=said)
        assert _nets(empty)["2"] == "", said
        store.clear_nc_proposal(empty)
    chat = [{"role": "user", "text": "mark the open pins as NC", "generated": True}]      # a button's text is not the student's words
    serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "01", "data": _nc_data(), "student_said": "mark the open pins as NC"}],
                         last_user="mark the open pins as NC", chat=chat)
    assert _nets(empty)["2"] == ""


def test_new_sheet_with_nc_pins_per_the_datasheet_is_not_held(empty):
    _add(empty, "U2", "ABCD1234")
    data = {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U2", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "NC", "net": "NC"}]}]}
    serve._apply_actions(empty, [{"type": "netlist.write", "sheet": "02", "data": data}], last_user="draw it")
    assert store.nc_proposal(empty) == []
    assert {p["num"]: p["net"] for p in store.load_sheet(empty, "02")["parts"][0]["pins"]}["2"] == "NC"


def test_nc_spellings_are_one_helper():
    import pinnames
    from altium import draw
    assert all(pinnames.is_nc_net(n) and draw.is_nc(n) for n in ("NC", "nc", "N/C", " NO_ERC "))
    assert not pinnames.is_nc_net("") and not pinnames.is_nc_net("GND")


def test_ui_has_the_nc_block_note_on_schematic_per_pin_and_posts_the_shown_items():
    import pathlib
    ui = pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views"
    out, pv = (ui / "outputs.js").read_text(encoding="utf-8"), (ui / "previews.js").read_text(encoding="utf-8")
    assert "outBlockNote()" in pv[pv.index("title: 'Schematic'"):][:600]            # the same note on the Schematic page
    assert "'nc-mark-one'" in out and "'nc-approve'" in out and "data-nc-prop" in out
    assert "outGapItems(outGate()).map(ncItem)" in out                               # nc-mark-all sends exactly what the note lists
    assert "/api/nc/mark', {}" not in out
