"""Review fixes of the step buttons: the UI block matches the server's filter, each Rules sentence shows once, add_outjob is idempotent and
adds a file that is already on disk, Stop is held on the last step, and the Remake of the Altium files is the step button."""
import pathlib

import pytest

import serve
import session as session_mod
from altium import bridge
from test_step_buttons import BUILT, button_notes, spy, world  # noqa: F401
from ui_source import ui_js

REPO = pathlib.Path(__file__).resolve().parent.parent
VIEWS = REPO / "ui" / "js" / "views"


def test_a_line_with_refs_but_on_no_sheet_does_not_block_the_page():
    checks = (VIEWS / "checks.js").read_text(encoding="utf-8")
    fn = checks[checks.index("function dfmUnverified()"):checks.index("function dfmUnverifiedHTML")]
    assert "(l.on_sheet || []).length" in fn                  # the server's own filter (store.unverified_parts)


def test_rules_sentences_show_once_in_the_note_and_in_the_agent_note(empty, world, monkeypatch):
    res = {"created": ["A"], "updated": [], "skipped": [{"name": "S", "why": "no value"}], "unconfirmed": ["A"], "message": ""}
    monkeypatch.setattr(bridge, "import_rules", lambda p: dict(res))
    serve.run_step_button(empty, session_mod.current(empty, None), "rules", {})
    text = button_notes(empty)[0]["text"]
    assert text.count("skipped (S)") == 1 and text.count("not confirmed: A") == 1
    assert "c.page === 'rules' ? 999" in ui_js()              # the page's warning list adds nothing for rules: the summary has them


def test_the_rules_note_tells_the_agent_when_an_empty_pcbdoc_was_added(empty, world):
    world["pcb"] = False
    serve.run_step_button(empty, session_mod.current(empty, None), "rules", {})
    assert "empty one was added" in button_notes(empty)[0]["text"]


@pytest.fixture
def prj(tmp_path, monkeypatch):
    f = tmp_path / "P.PrjPcb"
    f.write_text("x")
    sent, listed = [], []
    monkeypatch.setattr(bridge, "_linked", lambda p: f)
    monkeypatch.setattr(bridge, "read_prjpcb", lambda p: {"pcbs": [], "outjobs": listed})
    monkeypatch.setattr(bridge, "run_commands", lambda cmds, *a, **k: sent.append([c[0] for c in cmds]))
    monkeypatch.setattr(bridge, "_log", lambda *a, **k: None)
    monkeypatch.setattr(bridge.outjob, "generate_outjob", lambda p, filename=None, out_dir=None: (out_dir / filename).write_text("new"))
    return tmp_path, sent, listed


def test_add_outjob_adds_a_file_that_is_already_on_disk_and_never_overwrites_it(prj, empty):
    tmp, sent, _ = prj
    (tmp / "P.OutJob").write_text("students")
    res = bridge.add_outjob(empty)
    assert sent == [["PROJECT", "ADDDOC", "SAVEPRJ"]] and (tmp / "P.OutJob").read_text() == "students" and res["file"].endswith("P.OutJob")


def test_add_outjob_after_a_failed_add_works_on_the_next_click_and_is_idempotent(prj, empty, monkeypatch):
    tmp, sent, listed = prj
    real = bridge.run_commands

    def fail(cmds, *a, **k):
        raise bridge.BridgeError("Altium refused a step")
    monkeypatch.setattr(bridge, "run_commands", fail)
    with pytest.raises(bridge.BridgeError):
        bridge.add_outjob(empty)
    assert (tmp / "P.OutJob").exists()                        # written before the add: the next click must not refuse because of it
    monkeypatch.setattr(bridge, "run_commands", real)
    bridge.add_outjob(empty)
    assert sent == [["PROJECT", "ADDDOC", "SAVEPRJ"]]
    listed.append("P.OutJob")                                 # now the project lists it: nothing more is sent
    assert bridge.add_outjob(empty) == {"file": "", "backup": ""} and len(sent) == 1


def test_stop_is_held_on_the_last_step_and_a_stopped_run_is_logged_as_stopped(empty, world, monkeypatch):
    js = ui_js()
    stop = js[js.index("function pvStopBtn"):js.index("function pvStepNote")]
    assert "This step finishes as one Altium operation" in stop and "pvStopping || last" in stop
    logged = []
    monkeypatch.setattr(serve.runlog, "event", lambda *a, **k: logged.append(k))
    world.update(schlib=False)
    world["sync"]()
    monkeypatch.setattr(bridge, "build_library", lambda p, *a, **k: serve.step_stop(empty) and dict(BUILT))
    serve.run_step_button(empty, None, "draw", {})
    end = [k for k in logged if k.get("phase") == "end"][-1]
    assert end["ok"] is False and end["stopped"] is True


def test_the_remake_of_the_altium_files_uses_the_step_button_and_holds_the_others():
    outputs = (VIEWS / "outputs.js").read_text(encoding="utf-8")
    fn = outputs[outputs.index("async function outRunAltium"):outputs.index("let outRemaking")]
    assert "pvRunStep('outputs')" in fn and "/api/altium/run-outjob" not in fn
    assert "|| !!pvBusy" in outputs[outputs.index("function outRemakeBtn"):outputs.index("// An in-page confirm")]


def test_a_stopped_outputs_run_does_not_count_as_made_for_the_remake():
    root = pathlib.Path(__file__).resolve().parent.parent
    out = (root / "ui/js/views/outputs.js").read_text(encoding="utf-8")
    pv = (root / "ui/js/views/previews.js").read_text(encoding="utf-8")
    assert "kind: 'warn', stopped: true" in pv
    assert "n.kind !== 'bad' && !n.stopped" in out
