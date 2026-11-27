"""Frozen corpora (A15). The visible half is in tests/acceptance/corpora/; the hidden half is owner-held outside git
(hidden-corpora/ at the repo root, or ACCEPTANCE_HIDDEN_CORPORA). Acceptance draws from both; a run without the hidden half
says so in its detail (the visible half alone is enough for the red proof, never for a final pass)."""
from __future__ import annotations

import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
VISIBLE = HERE.parent / "corpora"
HIDDEN = pathlib.Path(os.environ.get("ACCEPTANCE_HIDDEN_CORPORA") or HERE.parent.parent.parent / "hidden-corpora")


def load(name: str, key: str) -> tuple[list, str]:
    """(items from both halves, a note on which halves were used)."""
    vis = json.loads((VISIBLE / f"{name}.json").read_text(encoding="utf-8"))
    def wrap(x, half):
        return dict(x, half=half) if isinstance(x, dict) else {"text": x, "half": half}
    items = [wrap(x, "visible") for x in vis[key]]
    hp = HIDDEN / f"{name}.json"
    if hp.is_file():
        items += [wrap(x, "hidden") for x in json.loads(hp.read_text(encoding="utf-8"))[key]]
        note = f"{name}: visible + hidden halves ({len(items)} items)"
    else:
        note = f"{name}: VISIBLE HALF ONLY ({len(items)} items; hidden half not present, not valid for a final pass)"
    return items, note


def header(name: str) -> dict:
    return json.loads((VISIBLE / f"{name}.json").read_text(encoding="utf-8"))
