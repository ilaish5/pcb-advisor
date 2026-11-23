"""Wave 3 rows 60 (state-driven chat chips, quick reply from the structured ask), 61 (one Outputs list), 62 (project search + archive),
and the chat's date through whenText()."""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

import workspace
from test_chat_turns import call, server  # noqa: F401  (fixtures)
from ui_source import UI

CHAT_JS = (UI / "js" / "chat.js").read_text(encoding="utf-8")
OUT_JS = (UI / "js" / "views" / "outputs.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def run_node(js):
    if not NODE:
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "t.js"
        f.write_text(js, encoding="utf-8")
        out = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# ---------------------------------------------------------------- 60 chips

def _chips(state):
    start = CHAT_JS.index("const CHAT_PROMPTS")
    end = CHAT_JS.index("function chatAnnounce")
    stub = ("const S = " + json.dumps(state) + "; const currentRow = () => ({}); const chatStage = () => " + json.dumps(state.get("stage", "bom")) + ";\n")
    return run_node(stub + CHAT_JS[start:end] + "\nconsole.log(JSON.stringify(chatSuggestionItems()));")


def _stage(id_, state, nxt="", open_=0, primary=False):
    return {"id": id_, "state": state, "open": open_, "primary": primary, "next": {"label": nxt, "act": "go:" + id_}}


def test_chips_follow_the_stage_the_work_is_in():
    a = _chips({"chat": [], "stages": [_stage("idea", "clean"), _stage("bom", "issues", "Fix the BOM", 3, True)], "stage": "bom"})
    assert "What is wrong in the BOM (3 open), and how do I fix it?" in [c["text"] for c in a]
    b = _chips({"chat": [], "stages": [_stage("idea", "clean"), _stage("bom", "clean"), _stage("sch", "not_started", "Draw in Altium", 0, True)], "stage": "sch"})
    texts = [c["text"] for c in b]
    assert "Help me with the next step: Draw in Altium" in texts
    assert texts != [c["text"] for c in a]                       # the chips change as the project advances


def test_a_pending_yes_no_question_gets_one_click_quick_replies_first():
    chips = _chips({"chat": [{"role": "user", "text": "hi"}, {"role": "agent", "text": "Draw it?", "ask": {"question": "Draw it?", "yes": "Yes, draw it", "no": "Not yet"}}],
                    "stages": [], "stage": "sch"})
    assert [(c["text"], c.get("quick")) for c in chips[:2]] == [("Yes, draw it", True), ("Not yet", True)]
    plain = _chips({"chat": [{"role": "agent", "text": "Done."}], "stages": [], "stage": "sch"})
    assert not any(c.get("quick") for c in plain)


def test_ask_comes_from_the_structured_action_not_from_the_text(home):
    import serve
    assert serve.ask_of([{"type": "chat.ask", "question": "Route it?", "yes": "Yes, route", "no": "Later"}]) == {"question": "Route it?", "yes": "Yes, route", "no": "Later"}
    assert serve.ask_of([{"type": "chat.ask", "question": "Route it?"}]) == {"question": "Route it?", "yes": "Yes", "no": "No"}
    assert serve.ask_of([{"type": "idea.ready"}]) is None and serve.ask_of(None) is None
    import project
    name = project.create("asker", title="Asker")
    applied, proposals, refused = serve.apply_actions(name, [{"type": "chat.ask", "question": "Go?"}])
    assert (applied, proposals, refused) == ([], [], [])         # no chip, no refusal


def test_the_chat_has_no_year_less_date_formatter():
    assert "toLocaleDateString" not in CHAT_JS and "whenText(" in CHAT_JS


# ---------------------------------------------------------------- 61 one Outputs list

def test_outputs_is_one_table_with_altium_folders_as_rows():
    start = OUT_JS.index("function outAltRows")
    end = OUT_JS.index("function outLimits")
    js = ("const esc = s => String(s); const tag = (t, tone, title) => `<span class=\"tag\">${t}</span>`; const outFull = s => s; const outAgo = s => 'now';\n"
          "const outRow = f => `<tr class=\"file\">${f.name}</tr>`; const outOld = () => [];\n"
          + OUT_JS[start:end]
          + "\nconst a = {root: 'R', folders: [{folder: '.', files: 2, newest: 'x'}, {folder: 'Gerber', files: 12, newest: 'x'}]};"
          "\nconsole.log(JSON.stringify({t: outTable([{name: 'a.csv'}], a)}));")
    t = run_node(js)["t"]
    assert t.count("<table") == 1 and "file\">a.csv" in t
    assert "Altium outputs (top level)" in t and 'data-folder="Gerber"' in t and "12 files" in t
    assert ">.<" not in t and "In Altium's outputs folder" in t
    assert "<h2>In Altium's outputs folder</h2>" not in OUT_JS


# ---------------------------------------------------------------- 62 projects menu: search + archive

def test_menu_has_search_and_archived_group():
    shell = (UI / "js" / "shell.js").read_text(encoding="utf-8")
    assert "data-menu-search" in shell and "Archived (" in shell and "archive-project" in shell and "unarchive-project" in shell
    assert "/api/projects/archive" in shell
    assert "askChoice" not in shell.split("onAct('archive-project'")[1].split("onAct('unarchive-project'")[0]     # no confirmation


def test_archive_is_reversible_busy_safe_and_listed(server, empty):  # noqa: F811
    import serve
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Old"})[0] == 200
    folder = workspace.projects_dir() / "Old"
    (folder / "keep.txt").write_text("precious")
    with serve.STEP_LOCK:
        assert call(server, "POST", "/api/projects/archive", empty, {"name": "Old"})[0] == 409
    assert folder.is_dir()
    code, body = call(server, "POST", "/api/projects/archive", empty, {"name": "Old"})
    assert code == 200 and not folder.exists() and "Old" not in [p["name"] for p in body["projects"]]
    assert [a["name"] for a in body["archive"]] == ["Old"]
    assert (workspace.projects_dir() / ".archive" / "Old" / "keep.txt").read_text() == "precious"
    assert [a["name"] for a in call(server, "GET", "/api/projects", empty)[1]["archive"]] == ["Old"]
    assert call(server, "POST", "/api/projects/archive", empty, {"name": "Nope"})[0] == 404
    code, body = call(server, "POST", "/api/projects/unarchive", empty, {"name": "Old"})
    assert code == 200 and (folder / "keep.txt").read_text() == "precious" and body["archive"] == []
    assert call(server, "POST", "/api/projects/unarchive", empty, {"name": "../x"})[0] == 404


def test_unarchive_never_overwrites_a_live_project(server, empty):  # noqa: F811
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Twin"})[0] == 200
    assert call(server, "POST", "/api/projects/archive", empty, {"name": "Twin"})[0] == 200
    assert call(server, "POST", "/api/projects/new", empty, {"name": "Twin"})[0] == 200
    assert call(server, "POST", "/api/projects/unarchive", empty, {"name": "Twin"})[0] == 409
    assert call(server, "POST", "/api/projects/archive", empty, {"name": "Twin"})[0] == 200       # the second archive gets its own folder
    assert len(call(server, "GET", "/api/projects", empty)[1]["archive"]) == 2
