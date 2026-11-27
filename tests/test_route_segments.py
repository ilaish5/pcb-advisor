"""A valid routing never fails on a clock: the 120 s segment is renewed while nets are still closing, it stops only on a stall (a whole segment
with no progress) or at the longest time, and says which; and what it is doing reaches the step's line in the UI (first state at once, never a
gap longer than 10 s). The router is the real one; time is a virtual clock that advances with every look at it, so the tests are deterministic."""
import time

import pytest

import serve
from altium import bridge, route
from test_altium_route import dense_board, rules
from test_chat_turns import call, server  # noqa: F401
from test_step_buttons import ROUTED, spy, world  # noqa: F401


class Virtual:
    """Stands for the `time` module inside route.py: every look at the clock is one second later."""

    def __init__(self, start=1000.0, step=1.0):
        self.t, self.step = start, step

    def time(self):
        self.t += self.step
        return self.t


@pytest.fixture
def clock(monkeypatch):
    v = Virtual()
    monkeypatch.setattr(route, "time", v)
    return v


# ------------------------------------------------------------------ the clock itself

def test_a_segment_with_progress_is_renewed_and_says_so(clock):
    seen = []
    c = route.Clock(10, 100, seen.append, t0=clock.t)
    c.note(0, total=5)
    clock.t += 5
    c.note(2)                                           # a net closed in this segment
    clock.t += 6                                        # past the end of segment 1
    assert c.expired() is False and c.segment == 2
    assert c.snapshot()["text"].startswith("Still routing, segment 2: 3 nets left of 5")
    assert seen[-1]["segment"] == 2 and seen[-1]["done"] == 2


def test_a_segment_without_progress_ends_the_routing_as_a_stall_and_says_so(clock):
    c = route.Clock(10, 100, None, t0=clock.t)
    c.note(0, total=5)
    clock.t += 11
    assert c.expired() is True and c.stop == "stall"
    clock.t += 1
    assert c.expired() is True                          # it stays ended
    assert "no net was closed in the last 10 s" in c.reason() and "ran out of time" in c.reason()
    assert "Routing stopped" in c.text() and "no progress" in c.text()


def test_the_longest_time_is_a_hard_end_even_with_progress_and_says_so(clock):
    c = route.Clock(10, 25, None, t0=clock.t)
    c.note(0, total=50)
    done = 0
    for _ in range(40):
        clock.t += 3
        done += 1
        c.note(done)
        if c.expired():
            break
    assert c.stop == "ceiling" and c.segment == 3       # 10 + 10 + 5 s
    assert "longest routing time, 25 s" in c.reason() and "still making progress" in c.reason()


def test_overlaps_dropping_count_as_progress_when_no_net_closed(clock):
    c = route.Clock(10, 100, None, t0=clock.t)
    c.note(3, total=5, fine=-40)
    clock.t += 5
    c.note(3, fine=-12)                                 # the negotiated engine: fewer overlaps, no net closed yet
    clock.t += 6
    assert c.expired() is False and c.segment == 2


def test_without_a_longest_time_the_second_is_the_cap_and_the_old_words_stay(clock):
    c = route.Clock(10, None, None, t0=clock.t)
    c.note(0, total=5)
    clock.t += 5
    c.note(4)
    clock.t += 6
    assert c.expired() is True and c.stop == "ceiling"
    assert c.reason() == "not routed (ran out of time)"


def test_more_renews_the_segment_before_a_next_attempt_when_there_was_progress(clock):
    c = route.Clock(10, 100, None, t0=clock.t)
    c.note(0, total=5)
    clock.t += 8
    c.note(1)
    assert c.more(5) is True and c.segment == 2         # 8 s in, a 5 s attempt does not fit: the segment is renewed
    c2 = route.Clock(10, 100, None, t0=clock.t)
    c2.note(0, total=5)
    clock.t += 8
    assert c2.more(5) is False and c2.stop == "" and c2.segment == 1        # no progress: no renewal; nothing latched


# ------------------------------------------------------------------ the router with that clock

def _run(clock, seconds, max_seconds):
    doc, box = dense_board(), [0, 0, 40, 30]
    r = rules(clearance=0.254, width=0.254, width_min=0.254, via_dia=1.27, via_hole=0.71)
    events = []
    clock.t = 1000.0
    res = route.plan_routes(doc, box, r, seconds=seconds, max_seconds=max_seconds, progress=events.append)
    return res, events, clock.t - 1000.0, (doc, box, r)


def test_a_router_still_making_progress_at_the_segment_edge_continues_and_finishes(clock):
    whole, _, spent, _ = _run(clock, 10 ** 9, None)
    assert whole["failed"] == []
    seg = spent / 2
    capped, _, _, _ = _run(clock, seg, None)
    assert capped["failed"] and any("ran out of time" in why or "no way" in why for _n, why in capped["failed"])    # the old cap: open nets
    res, events, _, (doc, box, r) = _run(clock, seg, 10 ** 9)
    assert res["failed"] == [] and res["stats"]["segments"] >= 2 and res["stats"]["stopped"] == ""
    assert route.violations(doc, res["items"], r, box) == []
    assert any(e["segment"] >= 2 and e["text"].startswith("Still routing, segment") for e in events), "the UI is told it carries on"


def test_a_router_that_reaches_the_longest_time_keeps_what_it_routed_and_names_the_open_nets(clock):
    whole, _, spent, _ = _run(clock, 10 ** 9, None)
    res, _events, _, (doc, box, r) = _run(clock, spent / 8, spent / 4)
    assert res["stats"]["stopped"] in ("ceiling", "stall")
    assert res["failed"], "nets are left open"
    out_of_time = [why for _n, why in res["failed"] if "ran out of time" in why]
    assert out_of_time and all(("longest routing time" in w) if res["stats"]["stopped"] == "ceiling" else ("no net was closed" in w) for w in out_of_time)
    assert res["routed"], "what was routed is kept"
    assert route.violations(doc, res["items"], r, box) == []


def test_the_first_state_comes_at_once_and_there_is_never_a_gap_over_ten_seconds(clock):
    res, events, spent, _ = _run(clock, 10 ** 9, None)
    assert events and events[0]["done"] == 0 and events[0]["text"].startswith("Routing: 0 of")
    stamps = [e["elapsed"] for e in events]
    assert stamps[0] <= 2 and max(b - a for a, b in zip(stamps, stamps[1:])) <= 10, stamps
    assert events[-1]["done"] >= events[0]["done"] and all(e["total"] for e in events[1:])
    assert {"elapsed", "done", "total", "open", "phase", "segment", "stopped", "text"} <= set(events[0])
    assert any("attempt 1 of" in e["phase"] for e in events) or any("rip-up" in e["phase"] for e in events)


def test_the_heartbeat_reports_without_a_search_asking_the_clock(monkeypatch):
    monkeypatch.setattr(route, "HEARTBEAT_S", 0.05)
    seen = []
    c = route.Clock(100, None, seen.append)
    n0 = len(seen)
    stop = route._heartbeat(c)
    time.sleep(0.4)
    stop()
    after = len(seen)
    assert after - n0 >= 3, "a report every beat, from a thread"
    time.sleep(0.2)
    assert len(seen) == after, "and none after it is ended"


# ------------------------------------------------------------------ from the bridge to the step's line

def test_route_on_passes_the_segment_and_the_ceiling_and_the_callback(tmp_path, monkeypatch):
    from test_altium_route_bridge import _route_fakes
    _route_fakes(monkeypatch, tmp_path)
    got = {}
    real = route.plan_routes

    def spy_plan(doc, box, rules_, **kw):
        got.update(kw)
        return real(doc, box, rules_, **kw)
    monkeypatch.setattr(route, "plan_routes", spy_plan)
    events = []
    with bridge.progress_to(events.append):
        bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc")
    assert got["seconds"] == route.SEGMENT_S == 120.0 and got["max_seconds"] == route.SECONDS_MAX
    assert callable(got["progress"])
    assert any(e.get("text", "").startswith("Routing: ") for e in events), events
    got.clear()
    bridge.route_on(tmp_path / "P.PrjPcb", tmp_path / "B.PcbDoc", seconds=20)       # a caller that names seconds names the cap
    assert got["seconds"] == 20 and got["max_seconds"] is None and got["progress"] is None


def test_the_running_steps_status_carries_what_the_routing_says_and_loses_it_at_the_end(server, empty, spy, monkeypatch):
    seen = []

    def routing(p, replace=False, keep_partial=False):
        bridge.report_progress({"text": "Routing: 31 of 45 nets routed, attempt 2 of 4", "done": 31, "total": 45, "segment": 1, "elapsed": 12.0})
        seen.append(serve.step_status(empty))
        bridge.report_progress({"text": "Still routing, segment 2: 9 nets left of 45", "done": 36, "total": 45, "segment": 2})
        seen.append(serve.step_status(empty))
        return dict(ROUTED)
    monkeypatch.setattr(bridge, "route_pcb", routing)
    assert call(server, "POST", "/api/altium/route", empty, {})[0] == 200
    first, second = seen
    assert first["running"] and first["progress"]["text"] == "Routing: 31 of 45 nets routed, attempt 2 of 4"
    assert first["progress"]["done"] == 31 and first["progress"]["total"] == 45
    assert second["progress"]["text"].startswith("Still routing, segment 2") and second["progress"]["segment"] == 2
    after = serve.step_status(empty)
    assert "progress" not in after, "a finished run carries no progress line"


def test_progress_outside_a_step_goes_nowhere_and_a_failing_listener_never_stops_the_work(monkeypatch):
    bridge.report_progress({"text": "nobody listens"})              # no step: nothing happens, nothing raises

    def boom(info):
        raise RuntimeError("the page is gone")
    with bridge.progress_to(boom):
        bridge.report_progress({"text": "x"})
        c = route.Clock(10, None, bridge.progress_fn())
        c.note(1, total=2)                                          # the clock swallows it as well
    assert bridge.progress_fn() is None


def test_the_ui_shows_the_progress_text_in_place():
    import pathlib
    js = (pathlib.Path(serve.__file__).parent.parent / "ui" / "js" / "views" / "previews.js").read_text(encoding="utf-8")
    assert "pvRun.progress.text" in js and "pvShowDetail()" in js
    assert js.count("pvDetailHTML()") >= 3, "the single line, the slim bar and the list of steps all carry it"


# ------------------------------------------------------------------ a stall is work, not only seconds

def test_a_slow_machine_that_did_little_work_in_a_segment_is_not_stalled(clock, monkeypatch):
    """The same board must give the same result on a slow runner: a segment without progress ends the routing only when the search also
    spent STALL_WORK expansions in it; with less it is a slow machine, and the routing goes on (until the longest time)."""
    monkeypatch.setattr(route, "STALL_WORK", 1000)
    c = route.Clock(10, 100, None, t0=clock.t)
    c.note(0, total=5, work=100)
    clock.t += 11
    c.note(0, work=400)                                    # a whole segment, 300 expansions, nothing closed
    assert c.expired() is False and c.stop == "" and c.segment == 2
    clock.t += 11
    c.note(0, work=900)
    assert c.expired() is False and c.segment == 3
    clock.t += 11
    c.note(0, work=1500)                                   # now 1400 expansions without progress: that is a stall
    assert c.expired() is True and c.stop == "stall"


def test_the_longest_time_still_ends_a_slow_search_and_a_second_router_counter_adds_up(clock, monkeypatch):
    monkeypatch.setattr(route, "STALL_WORK", 10 ** 9)
    c = route.Clock(10, 25, None, t0=clock.t)
    c.note(0, total=5, work=500)
    c.note(0, work=900)
    c.note(0, work=50)                                     # the next attempt's router counts from 0 again
    assert c.work == 900 + 50
    clock.t += 30
    assert c.expired() is True and c.stop == "ceiling"
