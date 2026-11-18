"""Runtime-verification fixes: a new project never gets a silent numbered name, and the UI contracts of the compact step note,
the Outputs/DFM reasons, the Altium-only readiness rows, the board size row and the resumed chat."""
import re

from test_chat_turns import call, server  # noqa: F401
from ui_source import ui_js


def test_new_project_with_a_taken_name_is_refused_with_the_existing_name(server, empty):
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln"})
    assert code == 200 and body["created"] == "Kiln" and "note" not in body
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln"})
    assert code == 409 and body["exists"] == "Kiln"
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "Kiln", "allow_copy": True})
    assert code == 200 and body["created"] == "Kiln-2" and body["folder"] == "Kiln-2" and "Kiln-2" in body["note"]


def test_new_project_with_odd_characters_names_the_folder_used(server, empty):
    code, body = call(server, "POST", "/api/projects/new", empty, {"name": "a/b<c>"})
    assert code == 200 and body["created"] == "a-b-c" and "a-b-c" in body["note"]


def test_the_ui_contracts():
    js = ui_js()
    assert "function pvCompact" in js and "Show ${c.warnings.length}" in js          # compact step note, warnings behind a toggle
    assert "function outLimits" in js and "needs Altium. The Altium outputs" not in js
    assert "dfm-zip-why" in js                                                       # the disabled zip button says why in text
    assert "READY_ALTIUM_IDS" in js and "readyShow" in js
    assert re.search(r"placeholder=\"e\.g\. 30\"", js)
    assert "chatResume" in js and "Ran ${items.length} steps" in js
    assert "askChoice" in js and "allow_copy" in js
