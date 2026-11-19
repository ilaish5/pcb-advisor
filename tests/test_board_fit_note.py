"""The chat note after a BOM approval when the board is too small (serve.board_fit_note) and the bridge estimate behind it."""
import json

import serve
import store
from altium import bridge


def test_board_fit_check_reads_the_idea_size_and_the_bom(empty):
    (store.pdir(empty) / "idea.json").write_text(json.dumps({"board": {"width_mm": 20, "height_mm": 20}}), encoding="utf-8")
    store.append(empty, "bom-log.jsonl", {"ts": store.now(), "line": "U1", "changes": {"refs": ["U1"], "package": "LQFP-100"}})
    for i in range(1, 9):
        store.append(empty, "bom-log.jsonl", {"ts": store.now(), "line": f"R{i}", "changes": {"refs": [f"R{i}"], "package": "0805"}})
    fit = bridge.board_fit_check(empty)
    assert fit and fit["tight"] and fit["size"] == (20.0, 20.0) and "20 x 20 mm" in fit["text"] and "not changed" in fit["text"]
    (store.pdir(empty) / "idea.json").write_text(json.dumps({"board": {"width_mm": 100, "height_mm": 100}}), encoding="utf-8")
    assert not bridge.board_fit_check(empty)["tight"] and bridge.board_fit_check(empty)["text"] == ""


def _fit(text, tight=True, suggest=(60, 45)):
    return lambda project: {"text": text, "tight": tight, "suggest": suggest}


def test_the_chat_says_it_once_per_state_even_when_the_figures_move_and_after_a_restart(empty, monkeypatch):
    said = []
    monkeypatch.setattr(serve, "say", lambda project, sess, msg: said.append(msg["text"]))
    monkeypatch.setattr(bridge, "board_fit_check", _fit("Too small, 43 parts 1000 mm2."))
    serve.board_fit_note(empty, None)
    monkeypatch.setattr(bridge, "board_fit_check", _fit("Too small, 44 parts 1010 mm2."))      # another approval: the text moves, the state does not
    serve.board_fit_note(empty, None)
    serve.board_fit_note(empty, None)
    assert len(said) == 1 and "Too small" in said[0]
    assert (store.pdir(empty) / "fit-said.json").is_file()                                     # kept on disk: a restart says nothing new
    monkeypatch.setattr(bridge, "board_fit_check", _fit("Too small, bigger now.", suggest=(70, 50)))
    serve.board_fit_note(empty, None)
    assert len(said) == 2                                                                      # another suggested size is news
    monkeypatch.setattr(bridge, "board_fit_check", lambda project: {"text": "", "tight": False, "suggest": None})
    serve.board_fit_note(empty, None)
    assert not (store.pdir(empty) / "fit-said.json").exists() and len(said) == 2
    monkeypatch.setattr(bridge, "board_fit_check", _fit("Too small again.", suggest=(70, 50)))
    serve.board_fit_note(empty, None)
    assert len(said) == 3
