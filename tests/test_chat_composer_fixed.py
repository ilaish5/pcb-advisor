"""
The composer never moves (Cursor / VS Code chat): the box, the send/stop button and the engine line are pinned at the bottom
of the chat column, and the turn in flight is the last item of the message list, right above them. Static checks of
ui/index.html, ui/js/chat.js and ui/styles/chat.css.
"""
import re

from ui_source import UI, ui_html

CHAT_JS = (UI / "js" / "chat.js").read_text(encoding="utf-8")
CHAT_CSS = (UI / "styles" / "chat.css").read_text(encoding="utf-8")
HTML = ui_html()


def flat(s):
    return re.sub(r"\s+", "", s)


def body(start, end):
    return CHAT_JS[CHAT_JS.index(start):CHAT_JS.index(end)]


def chat_section():
    return re.search(r'<section class="chat"[^>]*>(.*?)</section>', HTML, re.S).group(1)


def msgs_block():
    return re.search(r'<div class="msgs" id="msgs"[^>]*>(.*?)\n    </div>', chat_section(), re.S).group(1)


def composer_block():
    return re.search(r'<div class="composer"[^>]*>(.*)</div>\s*$', chat_section(), re.S).group(1)


def css_rule(selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", CHAT_CSS)
    assert m, f"no rule for {selector}"
    return flat(m.group(1))


# ---------- the progress renders inside the message list ----------

def test_the_status_and_the_chips_are_inside_the_message_list_after_the_thread():
    msgs = msgs_block()
    order = [msgs.index(x) for x in ('id="chat-thread"', 'id="chat-status"', 'id="sugs"')]
    assert order == sorted(order), "the thread, then the turn in flight, then the starter chips"


def test_the_thread_is_drawn_into_its_own_box_so_the_progress_survives_a_redraw():
    rt = body("function renderThread(", "/* ---------- the composer ---------- */")
    assert "$('#chat-thread')" in rt and "$('#msgs')" not in rt
    assert "box.innerHTML = html" in rt


def test_the_turn_in_flight_is_a_line_and_a_closed_steps_toggle():
    work = body("function chatWorkHTML(", "function chatTick(")
    assert 'class="spin"' in work and 'id="chat-clock"' in work and '<details class="chat-steps"' in work
    assert "Steps (" in work and "chatStepsOpen ? ' open' : ''" in work
    tick = body("function chatTick(", "/* one look at the server")
    assert "' · '" in tick and "' s'" in tick, '"Talking to Altium · 17 s" on one line'


def test_the_steps_start_closed_each_turn_and_keep_their_state_during_it():
    assert "chatStepsOpen = false" in body("async function send(", "function chatSubmit(")
    assert "chatStepsOpen = false" in body("async function chatResume(", "async function chatResumeEnd(")
    assert "chatStepsOpen = e.target.open" in CHAT_JS
    rc = body("function renderComposer(", "/* The turn in flight")
    # one build per turn, then patched: a poll does not close the list or take the focus off it
    assert "pending ? 'work'" in rc and "chatStepsSync(st, steps)" in rc
    assert "'work:' + steps" not in rc


def test_the_finished_turn_is_the_worked_record_in_the_thread():
    assert "Worked: ${items.length} step" in CHAT_JS
    assert re.search(r"return toolsHTML\(m\.tools\) \+", CHAT_JS)


# ---------- nothing is appended after the composer ----------

def test_nothing_is_rendered_after_the_composer():
    comp = composer_block()
    for gone in ('id="chat-status"', 'id="sugs"', "chat-steps", "chat-work"):
        assert gone not in comp, f"{gone} must not be in the composer"
    assert comp.rstrip().endswith('title="The engine and model used for new answers"></div>'), "the engine line is the last thing"
    assert re.search(r'</form>\s*<div class="chat-engine"', comp)
    assert chat_section().rstrip().endswith("</div>"), "the composer closes the chat column"


def test_the_script_never_writes_into_the_composer():
    assert "#composer" not in CHAT_JS and ".composer" not in CHAT_JS
    assert not re.search(r"\$\('#form'\)\.(after|append|insertAdjacentHTML)", CHAT_JS)


# ---------- the composer area has a fixed layout ----------

def test_the_composer_is_the_last_auto_row_under_the_scrolling_list():
    assert "grid-template-rows:autominmax(0,1fr)auto" in css_rule(".chat")
    msgs = css_rule(".msgs")
    assert "min-height:0" in msgs and "overflow:auto" in msgs
    comp = css_rule(".composer")
    assert "position:relative" in comp and "flex:none" in comp


def test_the_engine_line_has_a_fixed_height_even_when_empty():
    eng = css_rule(".chat-engine")
    assert "height:22px" in eng and "white-space:nowrap" in eng
    assert ".chat-engine:empty" not in CHAT_CSS


def test_jump_to_latest_floats_without_taking_room():
    assert 'data-act="chat-jump"' in composer_block() and "Jump to latest" in composer_block()
    jump = css_rule(".chat-jump")
    assert "position:absolute" in jump and "bottom:calc(100%+6px)" in jump
    assert ".chat-jump[hidden]{display:none}" in flat(CHAT_CSS)


def test_the_list_follows_its_end_only_while_the_student_is_there():
    follow = body("function chatFollow(", "function chatJump(")
    assert "if (chatAtEnd" in follow and "j.hidden = chatAtEnd" in follow
    rt = body("function renderThread(", "/* ---------- the composer ---------- */")
    assert "S.chat.at(-1).role === 'user'" in rt, "only the student's own message brings them back to the end"
    assert "chatAtEnd = sc.scrollHeight - sc.scrollTop - sc.clientHeight <" in CHAT_JS
    assert "new ResizeObserver(() => chatFollow())" in CHAT_JS
    assert "onAct('chat-jump'" in CHAT_JS


def test_status_and_chips_collapse_when_empty_so_they_leave_no_gap():
    assert ".chat-status:empty{display:none}" in flat(CHAT_CSS)
    assert ".sugs:empty{display:none}" in flat(CHAT_CSS)
