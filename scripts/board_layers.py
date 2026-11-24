"""The board's copper layer count: what the tool can build (2 or 4), the check every writer goes through, and the layer count a piece
of idea text states.

project.json `board.layers` is the one stored number. The Idea page sets it (/api/idea/layers), the agent's requirement text sets it
(store.propose_idea reads "4 layers" out of the text), and the project meta endpoint is checked by the same function, so no writer
can leave a value the router, the stack-up and the outputs do not know. Any other count is refused with the same message.
"""
import re

LAYER_CHOICES = (2, 4)
DEFAULT_LAYERS = 2

_NUM = r"(\d{1,2})"
# "4 layers", "4-layer board", "four layer", Hebrew "4 שכבות" / "לוח 4 שכבות"; the words one to eight are read too
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10}
_WORD = "|".join(_WORDS)
_COUNT = re.compile(rf"\b(?:{_NUM}|({_WORD}))[\s-]*(?:copper\s+)?layers?\b|\b{_NUM}\s+שכבות|שכבות\s*[:=]?\s*{_NUM}\b", re.I)
_BOARDISH = re.compile(r"board|pcb|stack|copper|לוח|מעגל מודפס|גרבר", re.I)


def refusal(value):
    """The message a count the tool does not build gets."""
    return (f"{value} copper layers is not something this tool builds: it makes 2 or 4 layer boards (4 layers are signal, ground plane, "
            "power plane, signal, the JLC 4-layer stack-up). Choose 2 or 4 layers in the Idea.")


def check(value):
    """The layer count as an int when it is 2 or 4, else ValueError with the refusal message. A bool, a fraction or text that is not a
    whole number is refused too (4.5 and "four" are not accepted from the API; the text reader below understands words)."""
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("the number of layers must be 2 or 4")
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"the number of layers must be 2 or 4, not {value!r}") from None
    if n != int(n) or int(n) not in LAYER_CHOICES:
        raise ValueError(refusal(value))
    return int(n)


def from_text(topic, text):
    """The layer count the requirement `topic` / `text` states, or None when it states none. Only text about the board or its
    stack-up counts ("4 layers of protection" is not a statement about the board): the topic or the text names the board, the pcb, the
    stack-up, copper or layers. The first count wins; a number outside 1..40 is not a layer count."""
    blob = f"{topic or ''} {text or ''}"
    if not _BOARDISH.search(blob):
        return None
    m = _COUNT.search(f"{text or ''}") or _COUNT.search(blob)
    if not m:
        return None
    raw = next((g for g in m.groups() if g), None)
    if raw is None:
        return None
    n = _WORDS.get(raw.lower()) if not raw.isdigit() else int(raw)
    return n if n and 1 <= n <= 40 else None


def of_board(board):
    """The layer count a project's board settings hold (2 when none or not a valid one: the tool's default)."""
    try:
        return check((board or {}).get("layers", DEFAULT_LAYERS))
    except ValueError:
        return DEFAULT_LAYERS
