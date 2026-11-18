"""Runtime verify round: one source for a part's pin reason, the board size stored on confirm, refs named in the reply but in no
line, and a view that does not rewrite bom.json."""
import serve
import sources
import store
from test_chat_turns import server  # noqa: F401


def _ic_on_sheet(empty, ds_text=None):
    store.propose_bom(empty, "U1", {"mpn": "ABCD1234", "refs": ["U1"]}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    store.write_sheet(empty, "01", {"sections": [{"id": "A", "title": "T"}], "parts": [
        {"ref": "U1", "section": "A", "pins": [{"num": "1", "name": "VCC", "net": "+3V3"}, {"num": "2", "name": "GND", "net": "GND"}]}]})
    if ds_text is not None:
        folder = sources.folder_of(empty)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ABCD1234.pdf").write_bytes(b"%PDF-1.4 x")
        (folder / "ABCD1234.pdf.txt").write_text(ds_text, encoding="utf-8")


def _u1(empty):
    return {l["key"]: l for l in store.bom(empty, write=False)}["U1"]


def test_an_unchecked_datasheet_gives_the_same_reason_on_every_surface(empty):
    _ic_on_sheet(empty, "ABCD1234 datasheet\nA pinout drawing only, no table.\n")
    att = store.attach_datasheet(empty, "U1", "ABCD1234.pdf")
    u1 = _u1(empty)
    reason = store.library_parts(empty)["U1"]["issues"]
    assert att["status"] == "unchecked" and reason
    # DFM Unverified parts and the BOM tag read pins_issues; the link toast reads the attach result: one text, with the check's reason
    assert u1["pins_status"] == "unverified" and reason in u1["pins_issues"] and "ABCD1234.pdf is linked" in u1["pins_issues"]
    assert att["issues"] == u1["pins_issues"]
    assert [r["issues"] for r in store.unverified_parts(empty, verify_new=False)] == [u1["pins_issues"]]


def test_unverified_always_says_why(empty):
    _ic_on_sheet(empty)
    assert "no datasheet linked" in _u1(empty)["pins_issues"]
    line = {"refs": ["U1"], "datasheet": "X.pdf"}
    assert "X.pdf is linked" in store.pins_status(line, {})[1]


def test_recheck_says_what_it_checked(empty):
    _ic_on_sheet(empty)
    out = store.recheck_pins(empty)
    assert out["checked"] == [] and "Nothing new to check" in out["message"] and len(out["unverified"]) == 1
    _ic_on_sheet(empty, "ABCD1234 datasheet\nPin Functions\nPIN NAME DESCRIPTION\n1 VCC Supply\n2 GND Ground\n")
    out = store.recheck_pins(empty)
    assert [c["status"] for c in out["checked"]] == ["verified"] and "U1 pins verified" in out["message"]
    assert store.recheck_pins(empty)["message"] == "Every part's pins are verified or accepted"


def test_confirm_stores_the_board_size_the_idea_states(empty):
    store.set_idea_goal(empty, "LED blinker with 555 from USB-C, board 30x25", by="agent")
    store.propose_idea(empty, "Power", "USB-C 5V", by="agent")
    store.confirm_idea(empty)
    assert store.load_idea(empty)["board"] == {"width_mm": 30.0, "height_mm": 25.0, "source": "text"}
    # a size the student typed wins over the text, on every later confirm
    store.set_board_size(empty, 40, 30)
    store.confirm_idea(empty)
    assert store.load_idea(empty)["board"] == {"width_mm": 40.0, "height_mm": 30.0}


def test_a_size_read_from_text_follows_the_text():
    idea = {"goal": "a board 30x25", "board": {"width_mm": 20, "height_mm": 20, "source": "text"}}
    assert store.board_from_text(idea)["board"]["width_mm"] == 30.0
    idea["goal"] = "a blinker"
    assert "board" not in store.board_from_text(idea)


def test_refs_listed_in_bullets_ranges_and_ref_tokens_must_be_in_a_line(empty):
    for key in ("R1", "R3", "C2"):
        store.propose_bom(empty, key, {"mpn": "", "refs": [key], "value": "1k"}, new=True)
    reply = ("| Part | Refs | Value |\n|---|---|---|\n| CC pull-down | {{ref:R1}}, {{ref:R2}} | 5.1k |\n"
             "- **R3-R4** 22R series\n- C2/C3: 100nF\n- PA9, PA10 go to the UART\nprose names R7, R8 freely\n"
             "- R1, NE555: timer, C2, SS14: the diode\n")
    assert serve.refs_missing_from_bom(empty, reply) == ["R2", "R4", "C3"]


def test_a_view_does_not_rewrite_an_unchanged_bom_json(empty, monkeypatch):
    store.propose_bom(empty, "R1", {"mpn": "", "refs": ["R1"], "value": "1k"}, new=True)
    store.bom(empty)
    wrote = []
    real = store._write_text
    monkeypatch.setattr(store, "_write_text", lambda p, t: wrote.append(p.name) or real(p, t))
    store.bom(empty)
    assert "bom.json" not in wrote
    store.propose_bom(empty, "R2", {"mpn": "", "refs": ["R2"], "value": "2k"}, new=True)
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    store.bom(empty)
    assert "bom.json" in wrote


def test_the_chat_warns_when_the_reply_names_a_ref_no_line_holds(server, empty, monkeypatch):
    from test_chat_turns import call
    import session as session_mod
    monkeypatch.setattr(serve.agent, "respond", lambda *a, **k: {
        "reply": "Proposed:\n- {{ref:R1}}, {{ref:R2}}: 5.1k CC pull-downs",
        "actions": [{"type": "bom.propose", "line": "R1", "new": True, "changes": {"refs": ["R1"], "value": "5.1k", "role": "CC"}}],
        "provider": "fake", "seconds": 1, "usage": {}})
    assert call(server, "POST", "/api/chat", empty, {"text": "go"})[0] == 200
    rec = [r for r in session_mod.load_chat(empty, session_mod.current(empty, None)) if r["role"] == "agent" and r.get("applied")][-1]
    assert any(k.startswith("bom.check") and "R2" in v for k, v in (rec.get("warned") or {}).items())


def test_a_size_of_another_thing_is_not_the_board():
    from altium import layout
    for text in ("LED blinker, the board shows a 128x64 OLED", "OLED 128x64 on top", "LCD 16x2 display", "an 8x8 LED matrix",
                 "board with an OLED 128x64", "OLED size 128x64 pixels"):
        assert layout.board_size({"goal": text}) is None, text
    assert layout.board_size({"goal": "a 128x64 OLED on a 40x30 board"}) == (40.0, 30.0)
    assert layout.board_size({"goal": "board 40x30, OLED 128x64"}) == (40.0, 30.0)
    assert layout.board_size({"goal": "the PCB must be 50x40 mm"}) == (50.0, 40.0)


def test_set_with_the_same_numbers_keeps_a_size_read_from_the_text(empty):
    store.set_idea_goal(empty, "a blinker, board 30x25", by="agent")
    store.propose_idea(empty, "Power", "USB-C", by="agent")
    store.confirm_idea(empty)
    store.set_board_size(empty, "30", "25")
    assert store.load_idea(empty)["board"]["source"] == "text"
    store.set_board_size(empty, 31, 25)
    assert "source" not in store.load_idea(empty)["board"]


def test_recheck_words_an_accepted_conflict_and_an_off_sheet_part_honestly(empty):
    _ic_on_sheet(empty, "ABCD1234 datasheet\nPin Functions\nPIN NAME DESCRIPTION\n1 VIN Supply\n2 GND Ground\n")
    store.attach_datasheet(empty, "U1", "ABCD1234.pdf")
    store.accept_pins(empty, "U1")
    line = {**_u1(empty)}
    assert store._checked_outcome(line, store.library_parts(empty)["U1"]) == ("accepted", "conflicts with the datasheet, your accept stands")
    line.update(on_sheet=[], pins_status="unverified")
    assert store._checked_outcome(line, {"verify": "unchecked"}) == ("unverified", "still unverified (not on a sheet yet)")


def test_the_recheck_count_leaves_out_do_not_buy_lines_like_the_gate(empty):
    _ic_on_sheet(empty)
    assert len(store.recheck_pins(empty)["unverified"]) == 1
    store.propose_bom(empty, "U1", {"nobuy": True})
    store.decide(empty, store.proposals(empty)[-1]["id"], "approved")
    out = store.recheck_pins(empty)
    assert out["unverified"] == [] and out["message"] == "Every part's pins are verified or accepted"
    assert store.manufacturing_warning(empty) == ""


def test_detach_says_the_full_no_datasheet_reason(empty):
    _ic_on_sheet(empty, "ABCD1234 datasheet\nno table\n")
    store.attach_datasheet(empty, "U1", "ABCD1234.pdf")
    store.detach_datasheet(empty, "U1")
    assert _u1(empty)["pins_issues"] == store.NO_DATASHEET
