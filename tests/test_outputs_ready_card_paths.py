"""R2 / U7: the 'Before you order' card is on every Outputs page state: no files, Altium state without files, and files listed."""
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")


def test_every_return_of_outputsHTML_carries_the_readiness_card():
    body = SRC[SRC.index("function outputsHTML("):SRC.index("/* ---------- action + change handlers")]
    returns = re.findall(r"return [^;]*;", body, re.S)
    assert len(returns) == 3
    assert all("outReadyCard()" in r for r in returns)


def test_an_unknown_readiness_shows_the_pins_and_conditions_rows_as_not_checked_never_zero_or_green():
    card = SRC[SRC.index("function outReadyCard("):SRC.index("onAct(\x27out-make-anyway\x27")]
    for line in card.splitlines():
        if "unverified parts: every part" in line or "0 open conditions" in line:
            assert "!!unknown" in line and "not checked" in line and "esc(unknown.why" in line
