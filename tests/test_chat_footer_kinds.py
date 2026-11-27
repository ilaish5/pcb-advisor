"""R2 / W22: the 'No check ran behind this sentence' footer ties "a check ran" to the CLAIM. Every gateway records its check runs (Claude Code in the run
list, Antigravity in the call list); an ERC or schematic claim needs a schematic check in its turn, a DRC or board claim a board check; older chips
without the flag are judged from the command they kept in `raw`. The replay builds the turns of the real chats from the projects' turn logs."""
import json
import pathlib
import shutil
import subprocess

import pytest

import agent
import workspace

UI = pathlib.Path(__file__).resolve().parent.parent / "ui"


def _footer(chat, index):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    import re
    src = (UI / "js" / "chat.js").read_text(encoding="utf-8")
    fn = re.search(r"const CHAT_CHECK_SCRIPT = .*?function chatUncheckedClaim\(m\) \{.*?\n\}\n", src, re.S).group(0)
    prog = fn + "\nconst S = {chat: JSON.parse(require('fs').readFileSync(0, 'utf8'))};\nconsole.log(JSON.stringify(chatUncheckedClaim(S.chat[" + str(index) + "])));"
    r = subprocess.run([node, "-e", prog], input=json.dumps(chat), capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


U = {"role": "user", "text": "check"}


def A(text, *chips, **kw):
    return {"role": "agent", "text": text, "tools": list(chips), **kw}


def chip(script, **kw):
    return dict({"t": "Checking", "st": "ok", "script": script, "check": True}, **kw)


@pytest.mark.parametrize("text, script, footer", [
    ("The schematic has 0 ERC errors.", "schematic.py", False),
    ("The schematic has 0 ERC errors.", "validate_netlist.py", False),
    ("The schematic has 0 ERC errors.", "rules.py", True),
    ("The schematic has 0 ERC errors.", "verify_sources.py", True),
    ("The schematic has 0 ERC errors.", "drc_jlc_map.py", True),
    ("The schematic has 0 ERC errors.", "verify_part.py", True),
    ("The schematic has 0 ERC errors.", "board.py", True),
    ("0 DRC violations on the board.", "board.py", False),
    ("0 DRC violations on the board.", "drc_origin.py", False),
    ("0 DRC violations on the board.", "schematic.py", True),
    ("0 DRC violations on the board.", "rules.py", True),
    ("No ERC/DRC errors.", "schematic.py", True),
    ("There are 0 errors.", "rules.py", False),              # a claim of no kind: any check of the design
])
def test_the_check_must_be_of_the_kind_the_sentence_claims(text, script, footer):
    assert _footer([U, A(text, chip(script))], 1) is footer


def test_both_kinds_in_one_sentence_need_both_and_the_drc_action_is_a_board_check():
    both = "No ERC/DRC errors."
    assert _footer([U, A(both, chip("schematic.py"), chip("board.py"))], 1) is False
    assert _footer([U, A("0 DRC errors on the board.", applied=["altium.run_drc"])], 1) is False
    assert _footer([U, A("0 ERC errors.", applied=["altium.run_drc"])], 1) is True


def test_a_chip_that_failed_or_is_only_claimed_is_no_check():
    assert _footer([U, A("0 ERC errors.", chip("schematic.py", st="bad"))], 1) is True
    assert _footer([U, A("0 ERC errors.", {"t": "Schematic check", "st": "ok", "s": "claimed"})], 1) is True


def test_an_older_chip_without_the_flag_is_judged_from_the_command_it_kept():
    old = {"t": "Checking the schematic", "st": "ok", "raw": "Running schematic.py C:/x/y.PrjPcb"}
    assert _footer([U, A("The check found 0 errors.", old)], 1) is False
    assert _footer([U, A("The schematic check found 0 ERC errors.", {"t": "Reading", "st": "ok", "raw": "Running sources.py text P f.pdf"})], 1) is True


@pytest.mark.parametrize("text", [
    "no errors", "There are 0 errors.", "No ERC/DRC errors.", "No ERC errors found.",
    "\u05d0\u05d9\u05df \u05e9\u05d2\u05d9\u05d0\u05d4", "\u05d5\u05d0\u05d9\u05df \u05e9\u05d2\u05d9\u05d0\u05d5\u05ea",
    "\u05d0\u05d9\u05df \u05d0\u05e3 \u05e9\u05d2\u05d9\u05d0\u05d4", "\u05d0\u05d9\u05df \u05e9\u05d2\u05d9\u05d0\u05d5\u05ea \u05d1\u05dc\u05d5\u05d7",
])
def test_the_claim_forms_are_found_with_no_check(text):
    assert _footer([U, A(text)], 1) is True


# ---- the turns of the real chats, replayed from the projects' turn logs -------------------------------------------------------------

CALLS = [{"tool": "read_file", "input": {"Path": "C:/x/notes.md"}, "failed": False},
         {"tool": "run_command", "input": {"CommandLine": "python C:/p/pcb-advisor/scripts/checks/schematic.py Proj"}, "failed": False},
         {"tool": "run_command", "input": {"CommandLine": "python C:/p/pcb-advisor/scripts/sources.py text Proj U1.pdf \"Pin\""}, "failed": False}]


def test_an_antigravity_turn_gets_its_check_chip_from_the_recorded_calls():
    chips = agent.real_tools({"calls": CALLS}, [{"t": "Schematic check", "d": "Proj - 0 errors", "st": "ok"}])
    real = [c for c in chips if c.get("check")]
    assert len(real) == 1 and real[0]["script"] == "schematic.py" and real[0]["st"] == "ok"
    assert [c for c in chips if c.get("s") == "claimed"] and not any(c.get("check") for c in chips if c.get("s") == "claimed")
    assert _footer([U, A("**0 errors, 0 warnings** on the sheet.", *chips)], 1) is False
    only_claim = agent.real_tools({"calls": CALLS[2:]}, [{"t": "Schematic check", "st": "ok"}])
    assert not any(c.get("check") for c in only_claim)
    assert _footer([U, A("**0 errors, 0 warnings** on the sheet.", *only_claim)], 1) is True


def test_a_failed_call_is_no_check():
    assert not [c for c in agent.real_tools({"calls": [dict(CALLS[1], failed=True)]}, []) if c.get("check")]


def _project_files(name):
    d = workspace.projects_dir() / name
    return d if d.is_dir() else None


def _turns(d):
    out = {}
    for ln in (d / "turns-log.jsonl").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            t = json.loads(ln)
            out[t.get("ts")] = t
    return out


def test_replay_of_the_real_final_e2e_chat_gives_no_false_footer_on_its_checked_turns():
    d = _project_files("Final-E2E-4L")
    if not d or not (d / "turns-log.jsonl").exists():
        pytest.skip("the project is not on this machine")
    chat = [json.loads(ln) for f in sorted((d / "chats").glob("2026-11-27-0103.jsonl")) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    turns = _turns(d)
    hits = 0
    for i, m in enumerate(chat):
        t = turns.get(m.get("ts"))
        if m.get("role") != "agent" or not t or t.get("engine") != "antigravity":
            continue
        chat[i] = dict(m, tools=agent.real_tools({"calls": t.get("calls") or []}, m.get("tools") or []))
        ran = {c["script"] for c in chat[i]["tools"] if c.get("check")}
        if "schematic.py" in ran:
            hits += 1
            assert _footer(chat, i) is False, f"message {i} ran schematic.py in its turn"
    assert hits >= 3


def test_replay_of_the_real_ceramic_controller_message_with_an_older_chip():
    d = _project_files("ceramic-controller")
    f = d / "chats" / "2026-11-23-2243.jsonl" if d else None
    if not f or not f.exists():
        pytest.skip("the project is not on this machine")
    chat = [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    i = next(k for k, m in enumerate(chat) if m.get("role") == "agent" and any("schematic.py" in str(t.get("raw")) for t in m.get("tools") or []))
    assert _footer(chat, i) is False
