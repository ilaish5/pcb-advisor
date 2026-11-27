"""The pin confirm UI (ui/js/views/pins.js): one click, the datasheet page next to the pins, no reason, one confirm for everything left."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

UI = pathlib.Path(__file__).resolve().parent.parent / "ui"
PINS = (UI / "js" / "views" / "pins.js").read_text(encoding="utf-8")


def _fn(name):
    i = PINS.index(f"function {name}(")
    j = PINS.index("\n}\n", i) + 3
    return PINS[i:j]


def test_the_dialog_shows_the_page_next_to_the_pins_with_one_button_and_an_optional_wrong_mark():
    h = _fn("pinsDialogHTML")
    assert "pinsDocUrl(" in h and "pins-frame" in h and "iframe" in h
    u = _fn("pinsDocUrl")
    assert "/api/source/" in u and "#page=" in u and "PINS_PDF_PARAMS" in u
    assert h.count('type="submit"') == 1 and "Pins match" in h
    assert "data-pin-wrong" in h and "required" not in h and "<textarea" not in h and 'name="reason"' not in h


def test_the_datasheet_opens_at_the_pin_page_fitted_to_the_width_with_the_viewer_sidebar_closed_in_a_near_full_window():
    params = re.search(r"PINS_PDF_PARAMS = '([^']+)'", PINS).group(1).split("&")
    assert "zoom=page-width" in params and "pagemode=none" in params and "navpanes=0" in params and "view=FitH" in params
    css = (UI / "styles" / "pins.css").read_text(encoding="utf-8")
    dlg = re.search(r"\.dlg\.pins-dlg\{([^}]*)\}", css).group(1)
    assert "calc(100vw" in dlg and "calc(100vh" in dlg and "max-width:none" in dlg       # the viewer gets nearly the whole window
    assert re.search(r"\.pins-frame\{[^}]*flex:1", css)                                  # and the frame takes all the height left
    assert "Open in a new tab" in _fn("pinsDialogHTML")


def test_accept_all_is_one_click_and_asks_again_only_for_parts_nothing_but_the_students_word_settles():
    """The waiting line names the parts and its button is the one click. The extra confirm is kept only for an IC with no datasheet check
    (a real engineering check the click would skip), and it names those parts; everything else is done at once, with an Undo."""
    h = PINS[PINS.index("onAct('accept-all-pins'"):]
    assert h.count("askPick(") == 1 and "askText(" not in h and "blind" in h and "confirm: true" in h and "reason" in h
    assert h.index("askPick(") < h.index("/api/pins/accept-all")
    assert "Undo" in h and "/api/pins/revoke" in h


def test_the_flow_is_wired_to_the_server_routes_and_the_dfm_page():
    for route in ("/api/pins/confirm-data", "/api/pins/confirm", "/api/pins/revoke", "/api/pins/accept-all"):
        assert route in PINS
    checks = (UI / "js" / "views" / "checks.js").read_text(encoding="utf-8")
    assert "pinRisksHTML()" in checks and "pinsAcceptAllBtn()" in checks
    assert "Accepted risk" in (UI / "js" / "views" / "bom.js").read_text(encoding="utf-8")
    assert "pinsInspHTML(l)" in (UI / "js" / "views" / "inspector.js").read_text(encoding="utf-8")
    assert "verifyToast(r.result)" in (UI / "js" / "core.js").read_text(encoding="utf-8")
    assert "text_state" in (UI / "js" / "viewer.js").read_text(encoding="utf-8")
    assert "Text not read yet" in (UI / "js" / "viewer.js").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_verify_toast_names_the_reason_and_the_way_forward(tmp_path):
    script = _fn("verifyToast") + ";process.stdout.write(JSON.stringify([" + ",".join(
        f"verifyToast({json.dumps(v)})" for v in (
            {"verify": "unchecked", "issues": "ABCD.pdf is linked, but its pins could not be checked; no pin table found"},
            {"verify": "pass", "issues": ""}, {"verify": "mismatch", "issues": "pin 2 is GND; the table says VIN"})) + "]));"
    (tmp_path / "t.js").write_text(script, encoding="utf-8")        # a file, not -e: a shell wrapper around node mangles quotes
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    unchecked, ok, bad = json.loads(r.stdout)
    assert unchecked.startswith("Could not verify the pins: ABCD.pdf is linked") and "Confirm pins" in unchecked and "unchecked" not in unchecked
    assert ok == "Pins verified against the datasheet"
    assert re.match(r"Pins conflict with the datasheet: pin 2 is GND", bad)
