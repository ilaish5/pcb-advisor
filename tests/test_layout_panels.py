"""
The chat column and the navigation: the chat can never run past the window, can always be brought back, and the nav folds
to a rail with one click. Source checks, plus the pure width clamp run in node (skipped when node is missing).
"""
import re
import shutil
import subprocess

import pytest

from ui_source import UI, ui_html

SHELL_JS = (UI / "js" / "shell.js").read_text(encoding="utf-8")
SHELL_CSS = (UI / "styles" / "shell.css").read_text(encoding="utf-8")
CHAT_CSS = (UI / "styles" / "chat.css").read_text(encoding="utf-8")


def flat(s: str) -> str:
    return s.replace(" ", "")


def test_chat_grid_has_a_shrinkable_column():
    """An implicit auto column grows to the widest unbreakable line and pushes the composer past the edge."""
    rule = re.search(r"^\.chat\{([^}]*)\}", CHAT_CSS, re.M).group(1)
    assert "grid-template-columns:minmax(0,1fr)" in flat(rule)
    assert "overflow:hidden" in flat(rule)


def test_restore_tab_exists_when_the_chat_is_hidden():
    tab = re.search(r'<button[^>]*class="chat-tab"[^>]*>', ui_html())
    assert tab, "index.html has the restore tab"
    assert 'data-act="toggle-chat"' in tab.group(0) and "aria-label=" in tab.group(0) and "title=" in tab.group(0)
    css = flat(SHELL_CSS)
    assert ".app.chat-off>.chat-tab{display:flex}" in css, "wide: the tab shows while the chat is hidden"
    assert ".app:not(.chat-open)>.chat-tab{display:flex}" in css, "drawer: the tab shows while the drawer is closed"
    assert "position:fixed;right:10px;top:17px" in css, "top right, level with the hide button in the chat header"
    assert "top:50%" not in re.search(r"\.chat-tab\{[^}]*\}", SHELL_CSS).group(0), "the restore tab is top-anchored"
    assert re.search(r"\.app\.chat-off>\.panes\{margin-right:(3\d|[4-9]\d)px", css), "the sheets leave room for the tab"
    assert "onAct('toggle-chat'" in SHELL_JS and "(e.key === 'j' || e.key === 'J')" in SHELL_JS


def test_dragging_to_the_minimum_stops_or_hides_never_a_zero_width_chat():
    move = re.search(r"function onSplitMove\(e\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "Math.max(CHAT_MIN" in move, "while dragging the width never goes below CHAT_MIN"
    up = re.search(r"function onSplitUp\(e\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "CHAT_DROP" in up and "hideChat()" in up, "dragged shut: the chat is hidden, and the restore tab appears"
    assert "Math.max(CHAT_MIN" in up


def test_nav_toggle_with_state_and_storage():
    fn = re.search(r"function navToggleHTML\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    for needle in ("aria-expanded", "aria-label", "title=", 'data-act="toggle-nav"', 'data-nav="navtog"'):
        assert needle in fn, needle
    nav = re.search(r"function navHTML\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "navToggleHTML()" in nav and nav.index("navToggleHTML()") < nav.index('class="trace"'), "the toggle sits at the top, before the stage list"
    assert "navToggleHTML()" in nav, "the button is drawn by navHTML, so the 4s redraw keeps it and its state"
    assert "onAct('toggle-nav'" in SHELL_JS
    # stored with the other layout state, inside the try/catch helpers
    assert re.search(r"JSON\.stringify\(\{chatWidth, chatHidden, navMin\}\)", SHELL_JS)
    assert "typeof st.navMin === 'boolean'" in SHELL_JS
    assert "lsSet(LAYOUT_KEY" in SHELL_JS
    css = flat(SHELL_CSS)
    assert ".app.nav-min{--nav-w:56px}" in css
    assert "(max-width:1280px)" in SHELL_JS, "by default the nav is a rail while the window is <=1280px"
    assert "navMin = null;" in SHELL_JS.split("function resetLayout()")[1].split("}")[0], "reset layout also resets the nav"


def test_chat_header_has_hide_button_and_engine_label_lives_in_the_composer():
    html = ui_html()
    head = re.search(r'<header class="chat-h">(.*?)</header>', html, re.S).group(1)
    assert re.search(r'<button[^>]*data-act="toggle-chat"[^>]*aria-label="Hide chat \(Ctrl J\)"', head)
    assert "chat-engine" not in head and "Claude Code" not in head, "the header holds the title only"
    comp = re.search(r'<div class="composer"[^>]*>(.*?)</div>\s*</section>', html, re.S).group(1)
    assert 'id="chat-engine"' in comp
    rule = re.search(r"^\.chat-engine\{([^}]*)\}", CHAT_CSS, re.M).group(1)
    assert "white-space:nowrap" in flat(rule) and "text-overflow:ellipsis" in flat(rule)


def test_nav_redraw_guard_is_kept():
    assert "navPressed" in SHELL_JS and "lastNavHTML" in SHELL_JS


def test_chat_width_is_clamped_against_the_window_minus_the_nav():
    fn = re.search(r"function maxChatWidth\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert "app.clientWidth" in fn and "nav.offsetWidth" in fn and "PANES_MIN" in fn and "SPLIT_W" in fn
    sync = re.search(r"function syncChat\(\)\s*\{(.*?)\n\}", SHELL_JS, re.S).group(1)
    assert sync.index("syncNavMin()") < sync.index("cssChatWidth("), "the nav width is settled before the chat is clamped"
    assert re.search(r"addEventListener\('resize', \(\) => \{ if \(!chatDrag\) \{ syncNavMin\(\);", SHELL_JS)


def test_max_chat_width_runs_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    consts = re.search(r"const CHAT_MIN = .*?;", SHELL_JS).group(0)
    fn = re.search(r"function maxChatWidth\(\)\s*\{.*?\n\}", SHELL_JS, re.S).group(0)
    script = (
        consts + "\nlet W = 1600, N = 232;\n"
        "const els = {'#app': {get clientWidth() { return W; }}, '#nav': {get offsetWidth() { return N; }}};\n"
        "const $ = s => els[s];\n" + fn + "\n"
        "const out = [];\n"
        "for (const [w, n] of [[1270, 56], [1270, 232], [1600, 56], [1600, 232], [1101, 56], [2400, 232]]) {\n"
        "  W = w; N = n; const m = maxChatWidth();\n"
        "  out.push([w, n, m, m >= CHAT_MIN, m <= CHAT_MAX, w - n - 6 - m >= PANES_MIN]);\n"
        "}\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tmp_path / "clamp.js"
    f.write_text(script, encoding="utf-8")
    r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    import json

    rows = json.loads(r.stdout.strip().splitlines()[-1])
    for w, n, m, ok_min, ok_max, ok_room in rows:
        assert ok_min and ok_max and ok_room, (w, n, m)
    assert rows[0][2] == 720 and rows[1][2] == 612, "a wider nav leaves the chat less room"
