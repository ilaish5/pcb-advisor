"""R2 / W22: the 'No check ran behind this sentence' footer goes on an agent answer that claims a zero count with no tool result in its turn,
in any language, and never on a DRC or review result that came from a tool."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

UI = pathlib.Path(__file__).resolve().parent.parent / "ui"


def _claim(chat, index):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    src = (UI / "js" / "chat.js").read_text(encoding="utf-8")
    fn = re.search(r"const CHAT_CHECK_SCRIPT = .*?function chatUncheckedClaim\(m\) \{.*?\n\}\n", src, re.S).group(0)
    prog = fn + "\nconst S = {chat: " + json.dumps(chat) + "};\nconsole.log(JSON.stringify(chatUncheckedClaim(S.chat[" + str(index) + "])));"
    r = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def A(text, **kw):
    return {"role": "agent", "text": text, **kw}


U = {"role": "user", "text": "review"}


def test_a_zero_claim_with_no_tool_in_the_turn_is_footnoted_in_any_language():
    assert _claim([U, A("I read the sheet: 0 errors.")], 1) is True
    assert _claim([U, A("No issues found on this sheet.")], 1) is True
    assert _claim([U, A("קראתי את הדף: 0 שגיאות.")], 1) is True
    assert _claim([U, A("Das Blatt hat 0 Fehler.")], 1) is True


def test_a_drc_result_from_a_tool_is_not_footnoted():
    assert _claim([U, A("The board check found 0 violations.", tools=[{"t": "Checking the board", "script": "board.py", "check": True}])], 1) is False
    assert _claim([U, A("Scope: 5 rule classes. Nothing found in them.")], 1) is False
    # the tool's own review message came earlier in the same turn, the model's summary follows
    assert _claim([U, A("The tool's check found nothing.\n\nScope: 5 classes", by="review"), A("So: 0 problems.")], 2) is False


def test_a_claim_in_an_earlier_turn_does_not_excuse_a_later_one():
    assert _claim([U, A("check\n\nScope: x"), U, A("This one is fine: 0 errors")], 3) is True


def test_only_a_checking_tool_hides_the_footer_a_document_read_does_not():
    claim = "The sheet has 0 errors."
    assert _claim([U, A(claim, tools=[{"t": "Read datasheet", "d": "STM32 p.31"}])], 1) is True
    assert _claim([U, A(claim, tools=[{"t": "Read file", "raw": "notes.md"}])], 1) is True
    # the product's own labels: a check is told by the recorded script / flag, not by the words
    for chip in ({"t": "Checking the board", "script": "board.py", "check": True}, {"t": "Checking the schematic", "script": "schematic.py", "check": True},
                 {"t": "Schematic check", "script": "schematic_review.py"}, {"t": "Anything", "check": True}):
        assert _claim([U, A(claim, tools=[chip])], 1) is False, chip
    assert _claim([U, A(claim, tools=[{"t": "Checking the board"}])], 1) is True      # words alone prove nothing
    assert _claim([U, A(claim, applied=["altium.run_drc"])], 1) is False
    assert _claim([U, A("read it", tools=[{"t": "Read file"}]), A(claim)], 2) is True


def test_numbers_that_are_not_a_count_of_errors_are_not_a_claim():
    for text in ("Keep BOOT0 low at reset.", "PA0 and PA1 are free.", "Use a 0 ohm link here.", "0 volts across it.",
                 "Pull-down: 0 ohm to GND"):
        assert _claim([U, A(text)], 1) is False, text
    assert _claim([U, A("No problems on this sheet.")], 1) is True
    assert _claim([U, A("DRC shows 0 violations.")], 1) is True


def test_the_claim_forms_with_a_qualifier_a_colon_or_no_digit_are_found():
    for text in ("There are no ERC errors.", "0 DRC violations.", "Errors: 0", "Zero design errors.", "No wiring errors on this sheet.",
                 "אין שגיאות בדף", "לא נמצאו בעיות"):
        assert _claim([U, A(text)], 1) is True, text


def test_plain_text_with_a_number_is_not_a_claim():
    assert _claim([U, A("Set R5 to 10 k and keep 0.1 uF at each pin.")], 1) is False
