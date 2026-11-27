"""R2 / U7: the 'Before you order' card is on every Outputs page state: no files, Altium state without files, and files listed."""
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parent.parent / "ui" / "js" / "views" / "outputs.js").read_text(encoding="utf-8")


def test_every_return_of_outputsHTML_carries_the_readiness_card():
    body = SRC[SRC.index("function outputsHTML("):SRC.index("/* ---------- action + change handlers")]
    returns = re.findall(r"return [^;]*;", body, re.S)
    assert len(returns) == 3
    assert all("outReadyCard()" in r for r in returns)
