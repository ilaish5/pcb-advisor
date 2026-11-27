"""A script Altium left paused, resumed with RunMacro, and the files it leaves behind. A small model of Altium (real clock, short waits):
one executor that runs one script at a time, a RunScript that is queued while a run is paused (and raises an error box), RunMacro (F9)
that resumes the paused run, Stop, and the request.txt a run consumes. The bridge is the real one.

What must hold: a request runs at most ONCE; the answer read is this request's own (never the old run's response.txt / end flag);
RunMacro is sent only with evidence of a pause and at most twice per call; a sign-in box on a cold start is not a pause."""
import threading
import time

import pytest

from altium import bridge


class Altium:
    def __init__(self, tmp_path, monkeypatch, paused=False, late=0.0, resume_ends=True, stuck=False, ok_lets_go=False, cold=False, box=None):
        self.dir, self.cmds, self.runs, self.queue = tmp_path, [], [], []
        self.paused, self.box, self.late, self.resume_ends, self.stuck, self.ok_lets_go = paused, (paused if box is None else box), late, resume_ends, stuck, ok_lets_go
        self.timers = []
        if paused:
            (tmp_path / "start-old.flag").write_text("x")
        monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
        monkeypatch.setattr(bridge, "_server", True)
        monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
        monkeypatch.setattr(bridge, "stage_script", lambda: "x.PrjScr")
        monkeypatch.setattr(bridge, "_running", lambda: not cold)
        monkeypatch.setattr(bridge, "_dialog_boxes", self.boxes)
        monkeypatch.setattr(bridge, "_script_state", self.state)
        monkeypatch.setattr(bridge, "_post_enter", self.enter)
        monkeypatch.setattr(bridge.subprocess, "Popen", self.popen)
        real_sleep = time.sleep
        monkeypatch.setattr(bridge.time, "sleep", lambda s: real_sleep(min(s, 0.1)))
        monkeypatch.setattr(bridge, "RESUME_WAIT", 0.8)
        monkeypatch.setattr(bridge, "ALIVE_WAIT", 0.5)
        monkeypatch.setattr(bridge, "DIALOG_LOG", [])
        monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [])
        monkeypatch.setattr(bridge.macro_budget, "depth", 0)

    # ---- what Altium shows
    def boxes(self):
        return [{"hwnd": 1, "cls": "TMessageForm", "line": "[TMessageForm] Error: OK", "ok_only": True}] if self.box else []

    def state(self):
        return {"boxes": [b["line"] for b in self.boxes()], "foreign": [], "windows": []}

    def enter(self, hwnd):
        self.box = self.stuck                          # a stuck executor raises its box again
        if self.paused and self.ok_lets_go:
            self.later(0.15, lambda: (self.dir / "log.txt").write_text("old step\n"))
            self.later(0.45, self.end_old)

    # ---- the executor
    def later(self, secs, fn):
        t = threading.Timer(secs, fn)
        t.start()
        self.timers.append(t)

    def end_old(self):
        (self.dir / "response.txt").write_text("START\nOK 0\nDONE\n")        # the OLD run's answer
        (self.dir / "log.txt").write_text("old log\n")
        (self.dir / "end-old.flag").write_text("x")
        self.paused = False

    def execute(self):
        while self.queue:
            self.queue.pop(0)
            req = self.dir / "request.txt"
            if not req.is_file():
                continue                                # a RunScript that finds no request does nothing
            lines = req.read_bytes().decode("ascii").splitlines()
            req.unlink()
            tok = lines[0].split("\t")[1]
            self.runs.append(tok)
            (self.dir / f"start-{tok}.flag").write_text("x")
            (self.dir / "response.txt").write_text("START\nOK 0\nDONE\n")
            (self.dir / "log.txt").write_text(f"ours {tok}\n")
            (self.dir / f"end-{tok}.flag").write_text("x")

    def popen(self, cmd, *a, **k):
        self.cmds.append(cmd)
        if "RunScript" in cmd:
            self.queue.append("run")
            if self.paused or self.stuck:
                self.box = True                         # the executor is busy: an error box, nothing starts
            else:
                self.execute()
        elif "RunMacro" in cmd:
            if self.paused and self.resume_ends and not self.stuck:
                self.end_old()
                self.later(self.late, self.execute) if self.late else self.execute()
        elif "Stop" in cmd:
            self.paused = False
            self.queue.clear()

    def sent(self, word):
        return sum(1 for c in self.cmds if word in c)

    def done(self):
        for t in self.timers:
            t.join()


@pytest.fixture
def world(tmp_path, monkeypatch):
    made = []

    def make(**kw):
        a = Altium(tmp_path, monkeypatch, **kw)
        made.append(a)
        return a
    yield make
    for a in made:
        a.done()


def run(**kw):
    return bridge.run_commands([("PING",)], start_timeout=0.5, **kw)


def test_a_paused_run_resumed_by_runmacro_does_not_leave_a_false_done_and_the_request_runs_once(world):
    """Attempt 1 raises the error box and queues; RunMacro resumes the old run, which writes ITS OWN response.txt (DONE) and end flag. The
    answer taken is this request's, and the queued RunScript plus the second attempt run the request once, not twice."""
    a = world(paused=True, box=False)      # nothing is open before the request is sent: the box comes with the first RunScript
    log = run()
    assert len(a.runs) == 1, "the request ran exactly once"
    assert log == [f"ours {a.runs[0]}"], "the log read is this run's, not the old run's"
    assert a.sent("RunMacro") == 1 and a.sent("Stop") == 0


def test_a_start_that_comes_late_after_the_resume_is_not_started_twice(world):
    a = world(paused=True, box=False, late=0.6)
    log = run()
    assert len(a.runs) == 1 and log == [f"ours {a.runs[0]}"]
    a.done()
    a.queue.append("run")
    a.execute()
    assert len(a.runs) == 1, "a RunScript that arrives after the request was consumed does nothing"


def test_a_request_that_never_started_is_taken_back_so_a_late_runscript_cannot_run_it(world):
    a = world(stuck=True, paused=True, resume_ends=False)
    with pytest.raises(bridge.BridgeError, match="Altium cannot run scripts right now"):
        run()
    assert not (a.dir / "request.txt").exists()
    a.queue.append("run")
    a.execute()
    assert a.runs == []


def test_runmacro_is_sent_at_most_twice_for_one_call(world):
    a = world(stuck=True, paused=True, resume_ends=False)
    with pytest.raises(bridge.BridgeError):
        run()
    assert a.sent("RunMacro") <= 2
    assert a.sent("Stop") >= 1, "Stop is the last resort"


def test_the_budget_holds_for_a_whole_block_with_its_cleanup_call(world):
    a = world(stuck=True, paused=True, resume_ends=False)
    with bridge.macro_budget():
        for _ in range(2):
            with pytest.raises(bridge.BridgeError):
                run()
    assert a.sent("RunMacro") <= 2, "two failing calls inside one block still send two RunMacro in all"


def test_an_ok_box_that_lets_the_run_go_on_gets_no_runmacro_and_no_stop(world):
    """The OK alone released it: a log line shows the run is alive, so F9 would run the ACTIVE script document."""
    a = world(paused=True, ok_lets_go=True)
    log = run()
    assert a.sent("RunMacro") == 0 and a.sent("Stop") == 0
    assert len(a.runs) == 1 and log == [f"ours {a.runs[0]}"]


def test_a_sign_in_box_on_a_cold_start_is_not_a_paused_script(world):
    a = world(paused=False, cold=True, stuck=True)
    a.box = True
    with pytest.raises(bridge.BridgeError) as err:
        bridge.run_commands([("PING",)], start_timeout=0.1)
    assert a.sent("RunMacro") == 0, "no RunMacro without evidence of a pause"
    msg = str(err.value)
    assert "sign in" in msg and "F9" not in msg and "paused" not in msg


def test_the_f9_text_is_only_for_a_real_pause(world):
    world(stuck=True, paused=True, resume_ends=False)
    with pytest.raises(bridge.BridgeError) as err:
        run()
    assert "F9" in str(err.value)


def test_the_preflight_resumes_with_runmacro_not_stop_first(world):
    a = world(paused=True)
    rec = bridge.preflight(strict=True)
    assert rec and a.sent("RunMacro") == 1 and a.sent("Stop") == 0


def test_flags_of_an_old_run_are_never_taken_for_ours(world, tmp_path):
    a = world()
    (tmp_path / "end-old.flag").write_text("x")
    (tmp_path / "start.flag").write_text("x")           # the old fixed names are ignored too
    (tmp_path / "end.flag").write_text("x")
    log = run()
    assert log == [f"ours {a.runs[0]}"] and len(a.runs) == 1
    assert not (tmp_path / "end.flag").exists() and not (tmp_path / "start.flag").exists()


def test_the_run_in_progress_reads_the_token_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    assert bridge.run_in_progress() is False
    (tmp_path / "request.txt").write_text("x")
    assert bridge.run_in_progress() is True
    (tmp_path / "request.txt").unlink()
    (tmp_path / "start-a.flag").write_text("x")
    assert bridge.run_in_progress() is True
    (tmp_path / "end-a.flag").write_text("x")
    assert bridge.run_in_progress() is False


def test_the_script_consumes_the_request_and_names_its_flags_with_the_token():
    import pathlib
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    assert "DeleteFile(Dir + 'request.txt')" in pas and "FlagName('start')" in pas and "FlagName('end')" in pas
    assert "if (not FileExists(Dir + 'request.txt')) then Exit;" in pas, "a late RunScript finds no request: nothing runs, no error"
    assert pas.index("FileExists(Dir + 'request.txt')") < pas.index("Req.LoadFromFile(Dir + 'request.txt')")


def test_the_layer_stack_checks_come_before_the_first_change():
    import pathlib
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    body = pas[pas.index("procedure PcbStack"):pas.index("procedure DispatchStep")]
    assert body.index("no room for two more signal layers") < body.index("InsertInStackBelow(Top, M1)")
    assert "close it WITHOUT saving" in body
