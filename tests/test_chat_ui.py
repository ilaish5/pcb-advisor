"""
The chat column while an agent turn runs (ui/js/chat.js): progress, Stop, the queue, partial turns, denial and error
cards. Static checks in the style of test_checks_ui.py; the behaviour was driven in a real browser by the orchestrator.
"""
import re
import shutil
import subprocess

import pytest

from ui_source import UI

CHAT_JS = (UI / "js" / "chat.js").read_text(encoding="utf-8")
CHAT_CSS = (UI / "styles" / "chat.css").read_text(encoding="utf-8")


def body(start, end):
    return CHAT_JS[CHAT_JS.index(start):CHAT_JS.index(end)]


def test_node_accepts_the_script():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, "--check", str(UI / "js" / "chat.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_progress_is_polled_every_second_while_pending_and_errors_are_ignored():
    assert "'/api/chat/progress'" in CHAT_JS
    send = body("async function send(", "function chatSubmit(")
    assert "setInterval(chatPoll, 1000)" in send and "clearInterval(chatPoller)" in send
    poll = body("async function chatPoll(", "async function chatStop(")
    assert "if (!pending" in poll and "catch (e)" in poll and "{soft: true}" in poll
    assert "current" in body("function chatTick(", "/* one look at the server")
    assert "chat-steps" in CHAT_JS and "<details" in CHAT_JS            # the collapsible list of the last steps


def test_the_send_button_becomes_stop_and_posts_to_the_stop_endpoint():
    assert "'/api/chat/stop'" in CHAT_JS
    upd = body("function chatUpdateSend(", "/* what went wrong with the last message")
    assert "'stop'" in upd and "icon(pending ? 'stop' : 'up')" in upd
    assert "if (pending) chatStop()" in CHAT_JS                         # the form's submit is Stop while pending
    assert "chatStopping" in CHAT_JS


def test_text_typed_while_pending_waits_in_a_queue_that_goes_out_as_one_message():
    sub = body("function chatSubmit(", "async function openPart(")
    assert "if (pending) { chatEnqueue(t)" in sub                       # the box no longer refuses input
    assert "chatQueue" in CHAT_JS and "Queued" in CHAT_JS
    assert "queue-remove" in CHAT_JS and "icon: 'x'" in CHAT_JS
    flush = body("async function chatFlush(", "/* ---------- messages")
    assert "join('\\n\\n')" in flush                                    # one message, a blank line between the texts
    assert "session" in flush                                           # a queue belongs to the conversation it was typed in
    out = body("function chatOutcome(", "/* the queue of one conversation")
    assert "'stopped'" in out and "'error'" in out
    send = body("async function send(", "function chatSubmit(")
    assert "outcome !== 'error'" in send and "chatFlush(" in send       # an error keeps the queue unsent


def test_a_partial_record_shows_its_text_a_muted_line_continue_and_retry():
    assert "Stopped after" in CHAT_JS and "steps: " in CHAT_JS
    assert "No output for" in CHAT_JS and "— stopped" in CHAT_JS
    assert "Continue from where you stopped." in CHAT_JS and "Steps already done: " in CHAT_JS
    part = body("function chatPartialHTML(", "/* what the advisor tried to run")
    assert "act: 'chat-continue'" in part and "act: 'retry'" in part
    for flag in ("partial", "stopped", "timed_out"):
        assert re.search(r"m\.%s\b" % flag, CHAT_JS), flag


def test_a_denied_command_is_a_card_with_allow_and_retry_or_an_explanation():
    assert "'/api/chat/allow'" in CHAT_JS
    allow = body("onAct('chat-allow'", "onAct('queue-remove'")
    assert "turn_ts: d.ts" in allow and "index:" in allow and "chatLastUser()" in allow
    cards = body("function chatDeniedHTML(", "const chatQueueOf")
    assert "The advisor wanted to run:" in cards and "d.reason" in cards
    assert "Allow and retry" in cards and "ts: m.ts" in cards and "d.compound" in cards
    assert "It tried a combined command; Retry asks it to run them one by one." in cards
    assert "esc(chatDeniedLabel(d))" in cards                           # the command is data, always escaped


def test_every_error_kind_has_its_card_or_is_drawn_as_a_partial_turn():
    card = body("function chatErrorCard(", "function renderComposer(")
    for kind in ("not_logged_in", "not_installed", "usage_limit"):
        assert f"'{kind}'" in card, kind
    for kind in ("idle_timeout", "total_timeout", "stopped"):
        assert f"'{kind}'" in body("const CHAT_PARTIAL", "const chatIsPartial"), kind
    assert "/login" in card and "pcb-advisor#install" in card and "retry_at" in card
    assert "Switch engine" in card and "chat-settings" in card
    assert "chatErrorCard(err) || errorLine(" in CHAT_JS                # an unknown kind keeps today's error line
    assert "Retry" in card and "act: 'retry'" in card
    assert "$('#set-provider')" in CHAT_JS                              # Settings › Engine


def test_an_old_failed_reply_still_becomes_retry_under_the_box():
    cur = body("function chatCurrentError(", "/* the starter questions")
    assert "last.error" in cur and "what: 'get an answer'" in cur
    assert "if (m.error || m.decision) return ''" in CHAT_JS
