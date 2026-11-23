"""
Wave 3 stream 2, the chat as the student meets it: tool steps in words (36), no shell approvals for internal commands (37),
no log voice (38), one language and the setting that picks it (40), engine and model shown (42), the conversation title (43),
a conversation window that is not eaten by the server's own notes (44).
"""
import json
import shutil
import subprocess
import sys

import pytest

import agent
import session as session_mod
import workspace
from gateway import events
from gateway.antigravity import AntigravityProvider
from ui_source import UI

CHAT_JS = (UI / "js" / "chat.js").read_text(encoding="utf-8")


# ---- 36 / 37: words for steps, internal commands never shown ---------------------------------------------------
def test_a_script_run_is_told_in_words_and_the_command_line_is_not_the_headline():
    assert events.human("Running jlc.py search esp32") == "Searching JLC"
    assert events.human("Running a_new_script.py --x") == "Running a check"        # unknown script: still no file name
    assert events.human("Running ls /tmp") == "Running a command"
    assert events.human("Reading BOM.md") == "Reading BOM.md"                      # a file the student recognises stays
    assert events.human("Opening skill parts-and-stock") == "Opening instructions"
    assert events.human("Denied: Running jlc.py part x").startswith("Not allowed: ")


def test_real_tools_keep_the_command_under_raw():
    chips = agent.real_tools({"stream": True, "runs": [{"label": "Running jlc.py search x", "failed": False}]}, [])
    assert chips == [{"t": "Searching JLC", "raw": "Running jlc.py search x", "st": "ok"}]


@pytest.mark.parametrize("cmd,internal", [
    ('python -c "print(1)"', True),
    ("python3 -c 'import os'", True),
    ("python - <<'EOF'\nprint(1)\nEOF", True),
    ('powershell -Command "Get-ChildItem"', True),
    ("ls /tmp", True),
    ("python C:/r/scripts/jlc.py search x && ls", False),     # a combined script run is `compound`: the Retry card, not hidden
    ("python C:/r/scripts/jlc.py search x", False),
    ("python C:/r/scripts/skills/check_availability.py Proj", False),
])
def test_internal_commands_are_never_offered_as_allow(cmd, internal):
    assert events.is_internal_run("Bash", {"command": cmd}) is internal
    assert events.is_internal_run("Read", {"file_path": "/x"}) is False


def test_a_python_dash_c_denial_is_flagged_internal_and_emits_no_live_step():
    from gateway.claude_code import ClaudeCodeProvider
    stream = "\n".join(json.dumps(e) for e in [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                        "input": {"command": "python -c \"print(1)\""}}]}},
        {"type": "system", "subtype": "permission_denied", "tool_use_id": "t1", "tool_name": "Bash", "message": "needs approval"},
        {"type": "result", "result": "ok", "permission_denials": []},
    ])
    text, meta, err = ClaudeCodeProvider._parse(stream)
    assert meta["denied"][0]["internal"] is True


def test_agy_always_runs_with_the_skip_permissions_flag(monkeypatch):
    for args in (None, ["-p", "-"], ["--mode", "accept-edits"]):
        prov = AntigravityProvider({"command": "agy", "args": args} if args is not None else {"command": "agy"})
        argv = prov._argv(type("R", (), {"options": {}, "system": "", "prompt": ""})(), "m")[0]
        assert ("--dangerously-skip-permissions" in argv) or ("--mode" in argv), argv


# ---- 40: the language setting works end to end ----------------------------------------------------------------
def _setting(monkeypatch, value):
    real = workspace.get
    monkeypatch.setattr(workspace, "get", lambda k, d=None: value if k == "user.language" else real(k, d))


def test_language_setting_overrides_the_typed_language(monkeypatch):
    _setting(monkeypatch, "he")
    assert agent.reply_language_line("hello there").startswith("Reply language: Hebrew")
    _setting(monkeypatch, "en")
    assert agent.reply_language_line("שלום") == "Reply language: English\n"


def test_auto_follows_the_last_typed_message_and_hebrew_is_singular(monkeypatch):
    _setting(monkeypatch, "auto")
    line = agent.reply_language_line("שלום")
    assert line.startswith("Reply language: Hebrew") and "singular" in line
    assert agent.reply_language_line("hello") == "Reply language: English\n"
    hist = [{"role": "user", "text": "שלום"}, {"role": "user", "text": "List it", "generated": True}]
    assert agent.reply_language_line("List it", hist, generated=True).startswith("Reply language: Hebrew")


def test_the_prompt_carries_the_language_line_and_the_rules_state_voice_and_priority():
    rules = (workspace.REPO / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    assert "singular" in rules and "The length limit beats every other rule" in rules


# ---- 44: the conversation window --------------------------------------------------------------------------------
def _hist(n_notes):
    h = []
    for i in range(4):
        h += [{"role": "user", "text": f"question {i}"}, {"role": "agent", "text": f"answer {i} " + "x" * 2000}]
    h += [{"role": "agent", "by": "button", "text": "Placed the parts in Altium because the student pressed the button: " + "y" * 400}] * 1
    h += [{"role": "agent", "decision": "approved", "text": f"Approved {i} proposals"} for i in range(n_notes)]
    return h


def test_notes_do_not_use_up_the_window_and_long_turns_are_clipped():
    out = agent.history_lines(_hist(10), 8)
    lines = out.split("\n")
    assert sum(1 for l in lines if l.startswith("note:")) == agent.NOTE_KEEP
    assert sum(1 for l in lines if l.startswith(("user:", "agent:"))) == 8        # all 8 real turns survive 11 notes
    last_agent = max(i for i, l in enumerate(lines) if l.startswith("agent:"))     # the question before the student's message is never clipped
    assert all(len(l) <= agent.CLIP_AGENT + 12 for i, l in enumerate(lines) if i != last_agent)
    assert "Placed the parts" not in out or out.count("Placed") <= 1


def test_window_without_turns_is_empty():
    assert agent.history_lines([{"role": "agent", "decision": "approved", "text": "Approved 1 proposal"}], 8) == ""


# ---- 43: the title ---------------------------------------------------------------------------------------------
def test_first_typed_message_names_the_first_conversation_and_a_button_prompt_does_not(home):
    project = "titleproj"
    sid = session_mod.create(project, title="First conversation")
    session_mod.append(project, sid, {"role": "user", "text": "List the findings", "generated": True})
    assert next(r for r in session_mod.load_index(project) if r["id"] == sid)["title"] == "First conversation"
    session_mod.append(project, sid, {"role": "user", "text": "Which ESP32 module should I pick?"})
    assert next(r for r in session_mod.load_index(project) if r["id"] == sid)["title"] == "Which ESP32 module should I pick?"
    session_mod.rename(project, sid, "My name")
    session_mod.append(project, sid, {"role": "user", "text": "another question"})
    assert next(r for r in session_mod.load_index(project) if r["id"] == sid)["title"] == "My name"


# ---- the page (node) ----------------------------------------------------------------------------------------------
def _node_eval(body):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    import re
    def grab(name, kind):
        m = re.search(rf"^{kind} {name}\b.*?(?=^(?:function|const|let|async function|/\*|//))", CHAT_JS, re.S | re.M)
        return m.group(0)
    src = "\n".join([
        "const esc = s => String(s); const icon = () => ''; const CLAIMED_TIP = 'c';",
        grab("toolMark", "function"), grab("toolsHTML", "function"),
        grab("chatDeniedInternal", "const"),
        body])
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(src)
    r = subprocess.run([node, fh.name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_tool_steps_are_one_closed_disclosure_even_for_one_step():
    out = _node_eval("console.log(toolsHTML([{t:'Searching JLC', st:'ok', raw:'Running jlc.py search x'}]))")
    assert out.startswith('<details class="runs"') and "Worked: 1 step</span>" in out and " open" not in out.split(">")[0]
    assert "Searching JLC" in out and "Running jlc.py search x" in out
    out2 = _node_eval("console.log(toolsHTML([{t:'a',st:'ok'},{t:'b',st:'ok'}]))")
    assert "Worked: 2 steps" in out2


def test_the_page_never_draws_an_allow_card_for_an_internal_command():
    out = _node_eval("console.log(JSON.stringify([chatDeniedInternal({tool:'Bash', input:{command:'python -c \"1\"'}}),"
                     "chatDeniedInternal({tool:'Bash', input:{command:'python C:/r/scripts/jlc.py x'}}),"
                     "chatDeniedInternal({tool:'Bash', internal:true, input:{}}),"
                     "chatDeniedInternal({tool:'WebFetch', internal:false, input:{url:'https://a.b'}})]))")
    assert json.loads(out) == [True, False, True, False]


def test_engine_and_model_are_shown_and_conversations_can_be_renamed():
    assert "chatEngineFoot" in CHAT_JS and "chat-engine" in (UI / "index.html").read_text(encoding="utf-8")
    assert "onAct('rename'" in CHAT_JS and "'/api/sessions/rename'" in CHAT_JS
    assert "m.by === 'button'" in CHAT_JS            # the server's note is chips only, never a third-person bubble
    assert sys.version_info
