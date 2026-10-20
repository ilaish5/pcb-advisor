"""
Background checks: the queue (dedupe, never raises), citation verification stored beside the chat, and the stock
check after a BOM change. Nothing here touches the network: check_availability is faked at background._check.
"""
import json
import pathlib
import threading
import time

import pytest

import background
import session as session_mod
import sources
import store

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(background, "STOCK_GAP", 0)
    background._tried.clear()
    assert background.wait_idle(5)
    yield
    assert background.wait_idle(5)


def test_a_key_already_queued_or_running_is_not_added_again():
    gate, ran = threading.Event(), []
    started = threading.Event()

    def slow():
        started.set()
        gate.wait(5)
        ran.append("slow")

    assert background.submit("k1", slow) is True
    assert started.wait(5)
    assert background.submit("k1", lambda: ran.append("dup")) is False      # running
    assert background.submit("k2", lambda: ran.append("two")) is True
    assert background.submit("k2", lambda: ran.append("two-dup")) is False  # queued
    assert background.is_active("k1") and background.is_active("k2")
    gate.set()
    assert background.wait_idle(5)
    assert ran == ["slow", "two"]
    assert not background.is_active("k1")


def test_a_job_that_raises_does_not_kill_the_worker(capsys):
    ran = []
    background.submit("boom", lambda: 1 / 0)
    background.submit("after", lambda: ran.append("ok"))
    assert background.wait_idle(5)
    assert ran == ["ok"]
    assert "ZeroDivisionError" in capsys.readouterr().err


def test_a_rerun_request_while_running_runs_once_more():
    gate, started, n = threading.Event(), threading.Event(), []

    def job():
        n.append(1)
        started.set()
        gate.wait(5)

    background.submit("r", job, rerun=True)
    assert started.wait(5)
    assert background.submit("r", job, rerun=True) is False
    assert background.submit("r", job, rerun=True) is False       # asked twice: still one more run
    gate.set()
    assert background.wait_idle(5)
    assert len(n) == 2


def seed_chat(project, text):
    rec = {"ts": "2026-10-20T10:00:00", "role": "agent", "text": text}
    session_mod.append(project, "main", rec)
    return rec


def test_citations_are_checked_and_stored_by_record_ts(empty):
    d = sources.folder_of(empty)
    d.mkdir(parents=True, exist_ok=True)
    (d / "ds.md").write_text("The ESDA6V1W5 has a pin configuration with three pins.", encoding="utf-8")
    rec = seed_chat(empty, 'Pins {{src:ds.md|"pin configuration with three pins"}} and '
                           '{{src:ds.md|"a made up sentence"}} and {{src:gone.pdf|p. 2}} and {{src:ds.md|p. 1, Pins}} '
                           'and {{src:JLC query "esda" 2026-10-20}}')
    assert background.verify_record_async(empty, "main", rec["ts"], rec["text"])
    assert background.wait_idle(5)
    done = background.read_cites(empty, "main")[rec["ts"]]
    items = done["items"]
    assert done["state"] == "done" and len(items) == 4          # the JLC query is a script run, not a file
    assert items['ds.md|"pin configuration with three pins"']["status"] == "ok"
    assert items['ds.md|"a made up sentence"']["status"] == "not_found"
    assert items["gone.pdf|p. 2"]["status"] == "missing_file"
    assert items["ds.md|p. 1, Pins"]["status"] == "ok"           # no quote: the file exists
    assert all(v["reason"] for v in items.values())


def test_a_quote_without_quotation_marks_is_still_matched_and_a_miss_is_not_an_error(empty):
    d = sources.folder_of(empty)
    d.mkdir(parents=True, exist_ok=True)
    (d / "notes.txt").write_text("Place a 100 uF tantalum and a 100 nF ceramic capacitor close to the VBAT pins.",
                                 encoding="utf-8")
    assert background.check_one(empty, "notes.txt", "Place a 100 uF tantalum and a 100 nF ceramic capacitor")[
        "reason"] == "quote found in file"
    miss = background.check_one(empty, "notes.txt", "Section four about the power supply design rules")
    assert miss == {"status": "ok", "reason": "file found"}                 # maybe a heading: not marked wrong
    assert background.check_one(empty, "notes.txt", "p. 2, Pin configuration")["reason"] == "file found"


def test_nothing_to_check_queues_nothing(empty):
    assert background.verify_record_async(empty, "main", "t", "no citations, only {{ref:D1}}") is False


def test_the_state_carries_cites_checking_then_done(empty):
    d = sources.folder_of(empty)
    d.mkdir(parents=True, exist_ok=True)
    (d / "ds.md").write_text("alpha beta gamma", encoding="utf-8")
    rec = seed_chat(empty, 'x {{src:ds.md|"alpha beta"}}')
    gate = threading.Event()
    background.submit("blocker", lambda: gate.wait(5))          # keeps the verify job queued behind it
    background.verify_record_async(empty, "main", rec["ts"], rec["text"])
    import model
    m = model.build(project=empty, session="main")
    assert m["chat"][-1]["cites"] == {"state": "checking"}
    gate.set()
    assert background.wait_idle(5)
    m = model.build(project=empty, session="main")
    c = m["chat"][-1]["cites"]
    assert c["state"] == "done" and c["items"]['ds.md|"alpha beta"']["status"] == "ok"
    # the log itself is untouched: the result lives beside it
    assert "cites" not in session_mod.load_chat(empty, "main")[-1]


def test_an_unchecked_old_record_has_no_cites(empty):
    seed_chat(empty, "old {{src:ds.md|p. 1}}")
    import model
    assert "cites" not in model.build(project=empty, session="main")["chat"][-1]


def test_a_stock_check_is_queued_once_per_line_and_only_for_lines_without_an_answer(lte, monkeypatch):
    calls = []
    monkeypatch.setattr(background, "_check", lambda p, keys: calls.append(set(keys)) or [])
    lines = [l["key"] for l in store.bom_lines(lte) if background._line_wants_stock(l)]
    assert lines
    key = lines[0]
    assert background.stock_line_async(lte, key) is True
    assert background.wait_idle(5)
    assert calls == [{key}]
    # a line asked for recently without an answer is not asked again by the sweep
    assert key not in background.lines_missing_stock(lte)


def test_stock_state_missing_stale_fresh_checking(lte, monkeypatch):
    import datetime as dt
    now = dt.datetime(2026, 10, 20, 12, 0, 0)
    assert background.stock_state(lte, "X", None, now)["state"] == "missing"
    old = {"LCSC": {"checked_at": "2026-10-19T10:00:00"}}
    assert background.stock_state(lte, "X", old, now)["state"] == "stale"
    new = {"LCSC": {"checked_at": "2026-10-20T10:00:00"}}
    assert background.stock_state(lte, "X", new, now) == {"state": "fresh", "checked_at": "2026-10-20T10:00:00"}
    gate = threading.Event()
    background.submit(background.stock_key(lte, "X"), lambda: gate.wait(5))
    assert background.stock_state(lte, "X", new, now)["state"] == "checking"
    gate.set()


def test_the_agent_is_told_when_stock_was_checked(lte):
    import agent
    import model
    s = json.loads(agent._summary(model.build(project=lte)))
    assert all("stock_check" in row for row in s["bom"])
    assert {row["stock_check"]["state"] for row in s["bom"]} <= {"missing", "stale", "fresh", "checking"}


def test_recheck_async_goes_through_the_queue(lte, monkeypatch):
    import serve
    calls = []
    monkeypatch.setattr(background, "_check", lambda p, keys: calls.append(set(keys)) or [])
    key = next(l["key"] for l in store.bom_lines(lte) if background._line_wants_stock(l))
    serve.recheck_async(lte, key)
    serve.recheck_async(lte, key)
    assert background.wait_idle(5)
    assert 1 <= len(calls) <= 2          # the second ask may rerun once; never two at the same time


def test_the_chat_draws_the_check_on_each_chip():
    core = (REPO / "ui/js/core.js").read_text(encoding="utf-8")
    chat = (REPO / "ui/js/chat.js").read_text(encoding="utf-8")
    assert "function fmt(text, cites)" in core and "cite-checking" in core and "cite-bad" in core
    assert "fmt(m.text, m.cites)" in chat, "the agent record's check reaches its chips"
    assert "m.cites.state" in chat, "a result arriving redraws the thread"
    assert "citeChips" not in (REPO / "ui/js/markdown.js").read_text(encoding="utf-8")
