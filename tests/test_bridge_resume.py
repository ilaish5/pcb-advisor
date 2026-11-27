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
    def __init__(self, tmp_path, monkeypatch, paused=False, late=0.0, resume_ends=True, stuck=False, ok_lets_go=False, cold=False, box=None,
                 extra_x2=0, launcher_s=None, slow=0.0, hang=False, box_title="Error", box_once=False):
        self.dir, self.cmds, self.runs, self.queue = tmp_path, [], [], []
        # the processes of X2.EXE: the one that runs (none on a cold start); a RunScript launch adds `extra_x2` that stay alive, or that exit
        # after launcher_s seconds (the launcher that hands its request to the running Altium); slow: the script logs for that long before
        # its end; hang: it starts, logs once and never ends
        self.pids, self.extra_x2, self.launcher_s, self.slow, self.hang = (set() if cold else {100}), extra_x2, launcher_s, slow, hang
        self.killed = []
        self.box_title, self.box_once = box_title, box_once
        self.paused, self.box, self.late, self.resume_ends, self.stuck, self.ok_lets_go = paused, (paused if box is None else box), late, resume_ends, stuck, ok_lets_go
        self.timers = []
        if paused:
            (tmp_path / "start-old.flag").write_text("x")
        monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
        monkeypatch.setattr(bridge, "_server", True)
        monkeypatch.setattr(bridge, "_exe", lambda: "x2.exe")
        monkeypatch.setattr(bridge, "stage_script", lambda: "x.PrjScr")
        monkeypatch.setattr(bridge, "_running", lambda: not cold)
        monkeypatch.setattr(bridge, "_x2_pids", lambda: set(self.pids))
        monkeypatch.setattr(bridge, "SECOND_X2_GRACE", 0.8)
        monkeypatch.setattr(bridge, "_dialog_boxes", self.boxes)
        monkeypatch.setattr(bridge, "_script_state", self.state)
        monkeypatch.setattr(bridge, "_post_enter", self.enter)
        monkeypatch.setattr(bridge.subprocess, "Popen", self.popen)
        real_sleep = time.sleep
        monkeypatch.setattr(bridge.time, "sleep", lambda s: real_sleep(min(s, 0.1)))
        monkeypatch.setattr(bridge, "RESUME_WAIT", 1.2)
        monkeypatch.setattr(bridge, "ALIVE_WAIT", 0.8)
        monkeypatch.setattr(bridge, "DIALOG_LOG", [])
        monkeypatch.setattr(bridge, "PREFLIGHT_NOTES", [])
        monkeypatch.setattr(bridge.macro_budget, "depth", 0)

    # ---- what Altium shows
    def boxes(self):
        return [{"hwnd": 1, "cls": "TMessageForm", "line": f"[TMessageForm] {self.box_title}: OK", "ok_only": True}] if self.box else []

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
        if self.slow or (self.hang and len(self.runs) < int(self.hang)):       # hang=N: the first N runs start, log once and never end
            self.slow_run()
            return
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

    def slow_run(self):
        self.queue.clear()
        req = self.dir / "request.txt"
        tok = req.read_bytes().decode("ascii").splitlines()[0].split("\t")[1]
        req.unlink()
        self.runs.append(tok)
        (self.dir / f"start-{tok}.flag").write_text("x")
        (self.dir / "log.txt").write_text("step 0\n")
        if not self.slow:
            return
        steps = int(self.slow / 0.15)

        def end():
            (self.dir / "response.txt").write_text("START\nOK 0\nDONE\n")
            (self.dir / f"end-{tok}.flag").write_text("x")
        for i in range(1, steps + 1):
            self.later(0.15 * i, lambda i=i: (self.dir / "log.txt").write_text(f"step {i}\n"))
        self.later(0.15 * steps + 0.1, end)

    def popen(self, cmd, *a, **k):
        self.cmds.append(cmd)
        if "RunScript" in cmd:
            self.queue.append("run")
            if not self.pids:
                self.pids.add(100)                      # a cold start: the Altium that starts
            for i in range(self.extra_x2):
                pid = 200 + len(self.pids)
                self.pids.add(pid)
                if self.launcher_s is not None:
                    self.later(self.launcher_s, lambda pid=pid: self.pids.discard(pid))
            if self.paused or self.stuck:
                self.box = not (self.box_once and self.sent("RunScript") > 1)       # the executor is busy: an error box, nothing starts
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


def test_the_layer_stack_second_layer_failure_says_the_first_is_already_in():
    """The second inner layer exists only after the first is inserted, so that check cannot come first: the message says so."""
    import pathlib
    pas = (pathlib.Path(bridge.__file__).parent / "bridge" / "AdvisorBridge.pas").read_text(encoding="utf-8", errors="replace")
    body = pas[pas.index("procedure PcbStack"):pas.index("procedure DispatchStep")]
    assert body.index("ERR the stack has no free signal layer for the first inner layer") < body.index("InsertInStackBelow(Top, M1)")
    assert "close it WITHOUT saving" in body


def test_after_a_failed_cold_start_the_cleanup_preflight_has_no_evidence_of_a_pause(world, monkeypatch):
    """A sign-in box on a cold start: the start failed, Altium is running by then, and the cleanup must not RunMacro on it."""
    a = world(cold=True, stuck=True)
    a.box = True
    seen = {"n": 0}

    def running():
        seen["n"] += 1
        return seen["n"] > 1                  # not running at the start (cold), running by the time the failure is cleaned up
    monkeypatch.setattr(bridge, "_running", running)
    with pytest.raises(bridge.BridgeError):
        bridge.run_commands([("PING",)], start_timeout=0.1)
    assert a.sent("RunMacro") == 0


def test_only_the_newest_start_flag_counts_for_a_run_in_progress(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    old, new = tmp_path / "start-old.flag", tmp_path / "start-new.flag"
    old.write_text("x")
    os.utime(old, (time.time() - 60, time.time() - 60))
    assert bridge.run_in_progress() is True                 # the only run, no end
    new.write_text("x")
    (tmp_path / "end-new.flag").write_text("x")
    assert bridge.run_in_progress() is False, "an older run that never ended is dead"


# ------------------------------------------------------------------ a second Altium, a long run, the last resort

def test_a_launch_that_leaves_a_second_altium_alive_is_a_failure_even_when_the_run_ended_well(world):
    """The model's run starts and answers DONE, as it would in the Altium that took the request. The extra process is what fails it:
    nothing it answered is taken for a pass."""
    a = world(extra_x2=1)
    with pytest.raises(bridge.BridgeError, match="second Altium"):
        run()
    assert a.runs, "the model did answer: the failure is the process, not the answer"
    assert not list(a.dir.glob("start-*.flag")), "a run we gave up on is not left 'in progress'"


def test_a_launcher_that_hands_over_and_exits_is_not_a_second_altium(world):
    a = world(extra_x2=1, launcher_s=0.2)
    assert run() == [f"ours {a.runs[0]}"]


def test_a_cold_start_may_start_one_altium_and_not_two(world):
    a = world(cold=True)
    assert run(), "one new X2.EXE is the Altium that was started"
    b = world(cold=True, extra_x2=1)
    with pytest.raises(bridge.BridgeError, match="second Altium"):
        run()
    assert len(b.pids) == 2
    assert a.runs


def test_a_script_that_keeps_logging_is_never_cut_off_by_the_total_timeout_and_tells_what_it_does(world, monkeypatch):
    a = world(slow=2.0)
    monkeypatch.setattr(bridge, "PROGRESS_EVERY", 0.3)
    seen = []
    with bridge.progress_to(seen.append):
        log = bridge.run_commands([("PING",)], start_timeout=0.5, stall_timeout=1, total_timeout=0.5)       # takes 4 times as long as asked
    assert log and log[-1].startswith("step ")
    assert a.runs and len(seen) >= 3 and all(s["text"].startswith("Altium is working") for s in seen), seen
    assert any("step" in s["text"] for s in seen) and seen[-1]["elapsed"] > 1


def test_a_script_that_stops_logging_is_stopped_at_the_stall_and_the_error_says_where(world):
    world(hang=True)
    with pytest.raises(bridge.BridgeError, match="Altium stopped in the middle of the script, after: step 0"):
        bridge.run_commands([("PING",)], start_timeout=0.5, stall_timeout=1, total_timeout=60)


def test_the_last_resort_closes_a_stuck_altium_that_holds_only_copies_and_says_so_in_one_line(world, monkeypatch, tmp_path):
    a = world(hang=True)
    ran = []
    monkeypatch.setattr(bridge.subprocess, "run", lambda cmd, *x, **k: ran.append(cmd) or type("R", (), {"stdout": "", "returncode": 0})())
    events = []
    monkeypatch.setattr(bridge.runlog, "event", lambda kind, **kw: events.append((kind, kw)))
    with pytest.raises(bridge.BridgeError) as e:
        bridge.run_commands([("PROJECT", str(tmp_path / "copy.PrjPcb")), ("PING",)], start_timeout=0.5, stall_timeout=1, total_timeout=60)
    assert ["taskkill", "/F", "/IM", "X2.EXE"] in ran
    assert "I closed it (only copies were open)" in str(e.value) and str(e.value).count("\n") == 0
    assert any(k == "altium-restart" and kw["done"] for k, kw in events), "logged"
    assert a.runs


def test_the_last_resort_leaves_altium_alone_when_the_student_s_own_project_may_be_open(world, monkeypatch):
    world(hang=True)
    ran = []
    monkeypatch.setattr(bridge.subprocess, "run", lambda cmd, *x, **k: ran.append(cmd) or type("R", (), {"stdout": "", "returncode": 0})())
    events = []
    monkeypatch.setattr(bridge.runlog, "event", lambda kind, **kw: events.append((kind, kw)))
    with pytest.raises(bridge.BridgeError) as e:
        bridge.run_commands([("PROJECT", r"D:\Students\Dana\Board.PrjPcb"), ("PING",)], start_timeout=0.5, stall_timeout=1, total_timeout=60)
    assert not [c for c in ran if c[0] == "taskkill"] and "closed it" not in str(e.value)
    assert any(k == "altium-restart" and not kw["done"] for k, kw in events), "the refusal is logged as well"


def test_the_last_resort_needs_a_start_flag_older_than_the_stall_limit_and_a_silent_log(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_RUN", {"token": "t", "cold": False, "evidence": False})
    ran = []
    monkeypatch.setattr(bridge.subprocess, "run", lambda cmd, *x, **k: ran.append(cmd) or type("R", (), {"stdout": "", "returncode": 0})())
    cmds = [("PROJECT", str(tmp_path / "copy.PrjPcb"))]
    assert bridge._restart_stuck(cmds, 60, time.time() - 100) == "", "no start flag: nothing is stuck"
    (tmp_path / "start-t.flag").write_text("x")
    assert bridge._restart_stuck(cmds, 60, time.time() - 100) == "", "a fresh start flag"
    import os
    os.utime(tmp_path / "start-t.flag", (time.time() - 100, time.time() - 100))
    assert bridge._restart_stuck(cmds, 60, time.time() - 5) == "", "the log moved a moment ago: it is alive"
    assert not ran
    assert "closed it" in bridge._restart_stuck(cmds, 60, time.time() - 100) and ran


# ------------------------------------------------------------------ the ERC cleanup after a stall: the request DID reach Altium

from test_erc_report import proj  # noqa: E402,F401  (the fixture: a project folder with a sheet and a board)


def test_after_a_stall_the_erc_cleanup_still_runs_because_the_request_reached_altium(world, proj, monkeypatch, tmp_path):
    """The real stall path: the OutJob batch starts, stops logging, and the bridge gives up on it (its start flag is taken away: a run we
    gave up on is not 'in progress'). That is NOT 'nothing reached Altium': the OutJob may be in the open project, so the cleanup call
    (LIBRELEASE and the marks) is sent, and only then the folder goes."""
    a = world(hang=1)
    monkeypatch.setattr(bridge, "_restart_stuck", lambda *x: "")      # no real taskkill from a test
    monkeypatch.setattr(bridge, "unsaved_documents", lambda prj: [])
    real = bridge.run_commands
    sent = []

    def quick(cmds, *x, **k):
        sent.append([c[0] for c in cmds])
        return real(cmds, start_timeout=0.5, stall_timeout=1, total_timeout=60)
    monkeypatch.setattr(bridge, "run_commands", quick)
    monkeypatch.setattr(bridge, "SETTLE_QUIET", 0.3)
    with pytest.raises(bridge.BridgeError, match="stopped in the middle"):
        bridge._erc_check(proj, tmp_path / "k.html")
    assert len(a.runs) == 2 and sent[1][:2] == ["PROJECT", "LIBRELEASE"], sent
    assert "UNMARK" in sent[1] and bridge.request_reached() is True
    assert not (proj.parent / bridge.ERC_DIR).exists(), "the cleanup ran, then the folder went"


def test_a_request_that_never_reached_altium_is_not_reached(world):
    world(stuck=True)
    with pytest.raises(bridge.BridgeError):
        run()
    assert bridge.request_reached() is False


def test_a_run_that_an_ok_let_go_on_is_waited_for_before_the_work_folder_goes(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "EXCHANGE", tmp_path)
    monkeypatch.setattr(bridge, "_RUN", {"token": "t", "cold": False, "evidence": False, "reached": True})
    monkeypatch.setattr(bridge, "SETTLE_QUIET", 1.0)
    sent = []
    monkeypatch.setattr(bridge, "_editscript", lambda c: sent.append(c))
    monkeypatch.setattr(bridge, "_close_dialogs", lambda *a, **k: [])
    real_sleep = time.sleep
    monkeypatch.setattr(bridge.time, "sleep", lambda s: real_sleep(min(s, 0.1)))
    log = tmp_path / "log.txt"
    log.write_text("0\n")
    timers = [threading.Timer(0.2 * i, lambda i=i: log.write_text(f"{i}\n")) for i in range(1, 6)]
    timers.append(threading.Timer(1.3, lambda: (tmp_path / "end-t.flag").write_text("x")))
    for t in timers:
        t.start()
    assert bridge.settle_failed_run() is True, "it moved and ended by itself"
    assert sent == [], "neither stopped nor resumed: it was working"
    for t in timers:
        t.join()
    (tmp_path / "end-t.flag").unlink()
    # one that was moving and then stops moving is stopped, not waited for ever
    log.write_text("x\n")
    assert bridge.settle_failed_run() is False and sent == ["Stop"]
    # one that was quiet already (the release stopped it) is not stopped a second time
    sent.clear()
    os_time = time.time() - 30
    import os
    os.utime(log, (os_time, os_time))
    assert bridge.settle_failed_run() is False and sent == []


# ------------------------------------------------------------------ what counts as evidence of a pause

def test_a_licence_warning_on_a_warm_altium_is_not_a_paused_script_and_gets_no_runmacro(world):
    """An OK-only box that is not the script's Error box (a licence warning) is closed, but it is no evidence of a pause: RunMacro would
    run the active script document and raise a new error box."""
    a = world(box=True, box_title="Warning")
    assert run() == [f"ours {a.runs[0]}"]
    assert a.sent("RunMacro") == 0
    assert bridge._RUN["evidence"] is False


def test_a_script_error_box_is_evidence_of_a_pause(world):
    a = world(paused=True, box=True)
    run()
    assert a.sent("RunMacro") == 1 and bridge._RUN["evidence"] is True


def test_the_evidence_is_the_whole_calls_history_not_the_last_release(world):
    """The first release sees the Error box (evidence), the second sees nothing; the run still does not start. The error must say that a
    script error blocked it (BLOCKED), as the first release proved, not 'Altium did not start' (what the last release alone would say)."""
    world(paused=True, box=False, resume_ends=False, box_once=True)
    with pytest.raises(bridge.BridgeError, match="a script error or a dialog box was blocking it"):
        run()
    assert bridge._RUN["evidence"] is True
