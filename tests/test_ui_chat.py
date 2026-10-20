"""
The chat column (ui/js/chat.js, ui/styles/chat.css, the chat section of ui/index.html), pinned from the source:
what other files rely on, what the markup must keep for keyboards and screen readers, and what must never come back.
The behaviour itself (autosize, Enter, Retry, aria-live) was driven in a real browser when the column was built.
"""
import re

from ui_source import UI, ui_html, ui_js

CHAT_JS = (UI / "js" / "chat.js").read_text(encoding="utf-8")
CHAT_CSS = (UI / "styles" / "chat.css").read_text(encoding="utf-8")


def chat_section():
    html = ui_html()
    start = re.search(r'<section[^>]*class="[^"]*\bchat\b[^"]*"', html).start()      # the shell decides where the column sits
    return html[start:html.index("</section>", start)]


def tag(markup, element_id):
    """The opening tag of the element with this id."""
    m = re.search(r"<\w+\b[^>]*\bid=\"%s\"[^>]*>" % re.escape(element_id), markup)
    assert m, f"no element with id={element_id}"
    return m.group(0)


def test_the_ids_other_files_and_tests_rely_on_are_kept():
    sec = chat_section()
    for i in ("msgs", "input", "form", "sendbtn", "convs", "chat-chip"):
        tag(sec, i)


def test_the_composer_is_a_textarea_that_picks_its_own_direction():
    t = tag(chat_section(), "input")
    assert t.startswith("<textarea")
    assert 'dir="auto"' in t          # Hebrew and English in the same box
    assert 'rows="1"' in t            # chat.js grows it from one line
    assert "aria-label" in t


def test_the_thread_is_not_a_live_region_but_new_answers_are_announced_in_one():
    sec = chat_section()
    assert "aria-live" not in tag(sec, "msgs")        # a poll that redraws the thread must not read the whole chat aloud
    assert 'aria-live="polite"' in tag(sec, "chat-live")
    assert "chatAnnounce(" in CHAT_JS


def test_the_header_emits_toggle_chat_and_leaves_registering_it_to_the_shell():
    sec = chat_section()
    assert 'data-act="toggle-chat"' in sec
    assert "onAct('toggle-chat'" not in CHAT_JS


def test_every_ask_button_in_the_app_has_one_entry_point_for_all_kinds():
    assert re.search(r"^function askAbout\(", CHAT_JS, re.M)
    kinds = re.search(r"const CHAT_CHIPS = \{(.*?)\n\};", CHAT_JS, re.S).group(1)
    for kind in ("part", "net", "file", "dfm", "rule", "zone"):
        assert re.search(r"^\s*%s:\s*\{" % kind, kinds, re.M), f"askAbout cannot point at a {kind}"
    body = CHAT_JS[CHAT_JS.index("function askAbout("):CHAT_JS.index("/* ---------- small helpers")]
    assert "typeof showChat === 'function'" in body       # the shell's show-the-chat, when the chat can be hidden
    assert "setView('chat')" in body                      # and the narrow-screen view switch
    assert ".focus()" in body
    assert "const fresh = !inp.value.trim()" in body      # the default question goes into an empty box only, never over a draft


def test_globals_the_other_areas_call_are_still_there():
    for name in ("askAbout", "send", "renderChat", "renderChatChip", "switchSession", "openPart", "diffHTML"):
        assert re.search(r"^(async )?function %s\(" % name, CHAT_JS, re.M), name


def test_enter_sends_shift_enter_is_a_new_line_and_an_ime_confirm_is_left_alone():
    assert re.search(r"e\.key === 'Enter' && !e\.shiftKey && !e\.isComposing && e\.keyCode !== 229", CHAT_JS)
    assert "chatAutosize" in CHAT_JS and "scrollHeight" in CHAT_JS


def test_a_diagram_proposal_is_a_card_of_its_own_not_a_bom_change():
    body = CHAT_JS[CHAT_JS.index("function diffHTML("):CHAT_JS.index("/* ---------- messages")]
    assert "idea_diagram" in body
    assert "Review on the canvas" in body and "review-diagram" in body
    assert re.search(r"^onAct\('review-diagram'", CHAT_JS, re.M)
    # values are always run through propShow() and esc(): an object printed raw reads "[object Object]"
    assert "propShow(" in body and "esc(" in body
    assert "${p.changes[k]}" not in body and "${p.before[k]}" not in body
    # approve and reject keep the generic route in core.js, which draws no toast of its own
    assert "chatLead" in body                      # one filled Approve in the thread, not one per waiting card
    assert "decide: 'approved'" in body and "decide: 'rejected'" in body and "pid: p.id" in body
    core = (UI / "js" / "core.js").read_text(encoding="utf-8")
    line = next(l for l in core.splitlines() if "if (d.decide)" in l)
    assert "toast(" not in line


def test_old_chat_furniture_stays_removed():
    for gone in ("Proposed BOM change", "stageHTML", "clear-file-chip"):
        assert gone not in CHAT_JS, gone
    assert not re.search(r"""['"`>]PCB Advisor""", CHAT_JS)      # no name label above every answer (the file's own header comment may say it)
    assert "dir=\"auto\"" in CHAT_JS              # paragraphs, lists and bubbles pick their own direction


def test_text_from_the_student_and_the_agent_is_escaped_before_it_is_markup():
    assert "esc(m.text)" in CHAT_JS                # the student's bubble
    assert "fmt(m.text, m.cites)" in CHAT_JS                # fmt() escapes first
    assert "esc(m.about.label)" in CHAT_JS
    assert not re.search(r"innerHTML\s*=\s*m\.text", CHAT_JS)


def test_the_conversation_list_shows_what_was_last_said():
    body = CHAT_JS[CHAT_JS.index("function renderConvs("):CHAT_JS.index("function chatCloseConvs(")]
    assert "r.last" in body and "You: " in body
    assert "esc(" in body


def test_a_failed_send_is_drawn_under_the_box_with_retry_and_the_text_is_not_lost():
    send = CHAT_JS[CHAT_JS.index("async function send("):CHAT_JS.index("function chatSubmit(")]
    assert "{soft: true}" in send                  # api() must not toast; the error line says it
    assert "chatError" in send and "inp.value = text" in send
    assert "errorLine(" in CHAT_JS
    assert re.search(r"^onAct\('retry'", CHAT_JS, re.M)
    assert "data-act=\"stop\"" not in CHAT_JS      # the server cannot cancel a running ask, so there is no Stop to pretend with


def test_no_hex_colours_and_no_hebrew_in_the_chat_files():
    declarations = " ".join(re.findall(r"\{([^{}]*)\}", CHAT_CSS))        # property values only, so an #id selector is not a colour
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", declarations), "chat.css must use the tokens in base.css"
    assert not re.search(r"\brgba?\(|\bhsla?\(", CHAT_CSS)
    for name, text in (("chat.js", CHAT_JS), ("chat.css", CHAT_CSS), ("chat section", chat_section())):
        assert not re.search(r"[\u0590-\u05ff]", text), f"Hebrew literal in {name}: use an escape or the data"


def test_the_chat_stylesheet_only_styles_the_chat():
    selectors = re.findall(r"(?m)^([^\s@/}{][^{]*)\{", CHAT_CSS)
    allowed = (".chat", ".conv", ".msgs", ".msg", ".thread-h", ".runs", ".prop", ".composer", ".sug", ".box", ".chip-x", ".send", ".chat-")
    stray = [s.strip() for s in selectors if not s.strip().startswith(allowed)]
    assert stray == [], f"chat.css styles things outside the chat: {stray}"
