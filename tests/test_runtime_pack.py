"""
The runtime pack: runtime/ in the repo is the source, the engine home is where the
engines read it from. Engines are mocked; nothing here starts a real CLI.
"""
import json
import pathlib
import re
import shutil

import pytest

import agent
import gateway
import oscompat
import runtime_pack
import workspace

REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def src(tmp_path, monkeypatch):
    """A tiny pack of our own, so the tests do not depend on what skills exist today."""
    root = tmp_path / "src"
    (root / "skills" / "alpha" / "scripts").mkdir(parents=True)
    (root / "skills" / "beta").mkdir()
    (root / "AGENTS.md").write_text("You are a test.\n", encoding="utf-8")
    (root / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: a\n---\n", encoding="utf-8")
    (root / "skills" / "alpha" / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    (root / "skills" / "beta" / "SKILL.md").write_text("---\nname: beta\ndescription: b\n---\n", encoding="utf-8")
    monkeypatch.setattr(runtime_pack, "SOURCE", root)
    return root


def test_pytest_tmp_is_not_in_a_git_tree(tmp_path):
    assert runtime_pack._git_root(tmp_path) is None


def test_sync_makes_both_skill_trees_and_claude_md(src, tmp_path):
    dest = tmp_path / "engine"
    assert runtime_pack.sync(dest) == dest.resolve()
    assert (dest / "AGENTS.md").read_text(encoding="utf-8") == "You are a test.\n"
    assert (dest / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"
    for tree in (".agents/skills", ".claude/skills"):
        assert (dest / tree / "alpha" / "SKILL.md").is_file()
        assert (dest / tree / "alpha" / "scripts" / "run.py").is_file()
        assert (dest / tree / "beta" / "SKILL.md").is_file()
    manifest = json.loads((dest / ".pack.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"AGENTS.md", "skills/alpha/SKILL.md", "skills/alpha/scripts/run.py",
                                      "skills/beta/SKILL.md"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in manifest["files"].values())
    assert runtime_pack.check(dest) == []


def test_sync_is_idempotent_and_only_rewrites_what_changed(src, tmp_path):
    dest = tmp_path / "engine"
    runtime_pack.sync(dest)
    assert runtime_pack.sync.last["written"]
    runtime_pack.sync(dest)
    assert runtime_pack.sync.last == {"dest": str(dest.resolve()), "written": [], "removed": []}
    (src / "AGENTS.md").write_text("You are a changed test.\n", encoding="utf-8")
    runtime_pack.sync(dest)
    assert sorted(runtime_pack.sync.last["written"]) == [".pack.json", "AGENTS.md"]


def test_sync_prunes_a_skill_that_left_the_source(src, tmp_path):
    dest = tmp_path / "engine"
    runtime_pack.sync(dest)
    shutil.rmtree(src / "skills" / "beta")
    runtime_pack.sync(dest)
    for tree in (".agents/skills", ".claude/skills"):
        assert not (dest / tree / "beta").exists()
        assert (dest / tree / "alpha" / "SKILL.md").is_file()
    assert runtime_pack.check(dest) == []


def test_check_reports_drift(src, tmp_path):
    dest = tmp_path / "engine"
    runtime_pack.sync(dest)
    (dest / ".claude" / "skills" / "alpha" / "SKILL.md").write_text("x", encoding="utf-8")
    (dest / ".agents" / "skills" / "ghost").mkdir()
    (dest / ".agents" / "skills" / "ghost" / "SKILL.md").write_text("x", encoding="utf-8")
    problems = runtime_pack.check(dest)
    assert any(p.startswith("differs") and ".claude/skills/alpha/SKILL.md" in p for p in problems)
    assert any(p.startswith("stale") and "ghost" in p for p in problems)


def test_sync_refuses_a_destination_inside_a_git_tree(src, tmp_path):
    tree = tmp_path / "somerepo"
    (tree / ".git").mkdir(parents=True)
    with pytest.raises(runtime_pack.RuntimePackError, match="git work tree"):
        runtime_pack.sync(tree / "engine")
    assert not (tree / "engine").exists()


def test_sync_refuses_a_destination_inside_the_repo(src):
    with pytest.raises(runtime_pack.RuntimePackError, match="inside the repo"):
        runtime_pack.sync(workspace.REPO / "scratch-engine")


def test_engine_home_defaults_to_the_os_app_data_dir(monkeypatch):
    monkeypatch.delenv("PCB_ADVISOR_ENGINE_HOME")
    workspace.load(reload=True)
    try:
        assert runtime_pack.engine_home() == (oscompat.app_data_dir() / "pcb-advisor" / "engine").resolve()
    finally:
        monkeypatch.undo()
        workspace.load(reload=True)


def test_engine_home_follows_the_config_key(tmp_path, monkeypatch, engine_home):
    assert runtime_pack.engine_home() == engine_home.resolve()
    monkeypatch.delenv("PCB_ADVISOR_ENGINE_HOME")
    monkeypatch.setenv("PCB_ADVISOR_CONFIG", str(tmp_path / "c.json"))
    (tmp_path / "c.json").write_text(json.dumps({"agent": {"engine_home": str(tmp_path / "mine")}}), encoding="utf-8")
    workspace.load(reload=True)
    try:
        assert runtime_pack.engine_home() == (tmp_path / "mine").resolve()
    finally:
        monkeypatch.undo()
        workspace.load(reload=True)


# ---------------------------------------------------------------- the agent

def _respond(lte, monkeypatch, backend="claude_code"):
    import model
    seen = {}

    class Res:
        ok, text, provider, model, error = True, "fine", backend, "", ""

    def route(req, name=None):
        seen["req"] = req
        return Res()
    monkeypatch.setattr(gateway, "route", route)
    m = model.build(project=lte)
    agent.respond(m, "hello", m["chat"], backend=backend)
    return seen["req"]


def test_the_engine_runs_in_the_engine_home_with_the_repo_and_project_added(lte, monkeypatch, engine_home):
    req = _respond(lte, monkeypatch)
    assert pathlib.Path(req.options["cwd"]) == engine_home.resolve()
    add = req.options["add_dirs"]
    assert str(workspace.REPO) in add
    assert str(workspace.project_dir(lte)) in add
    assert len(add) == len(set(add))
    assert all(pathlib.Path(d).is_absolute() for d in add)
    # the pack was synced there before the turn
    assert (engine_home / "AGENTS.md").is_file() and (engine_home / "CLAUDE.md").is_file()


def test_the_workspace_section_gives_absolute_paths(lte, monkeypatch):
    prompt = _respond(lte, monkeypatch).prompt
    section = prompt.split("\n--- WORKSPACE ---\n")[1].split("\n--- CURRENT STATE ---")[0]
    assert workspace.REPO.as_posix() + "/scripts/trace_width.py" in section
    assert workspace.project_dir(lte).as_posix() + "/bom.json" in section
    assert "{repo}" not in section


def test_a_refused_engine_home_is_an_error_reply_not_a_crash(lte, monkeypatch, tmp_path):
    (tmp_path / "tree" / ".git").mkdir(parents=True)
    monkeypatch.setenv("PCB_ADVISOR_ENGINE_HOME", str(tmp_path / "tree" / "engine"))
    workspace.load(reload=True)
    import model
    out = agent.respond(model.build(project=lte), "hi", [], backend="claude_code")
    assert out["error"] and "git work tree" in out["reply"]


def test_rules_come_from_runtime_agents_md():
    src = (REPO / "runtime" / "AGENTS.md").read_bytes()
    assert agent.rules() == runtime_pack.render("AGENTS.md", src).decode("utf-8").strip()
    assert agent.rules().startswith("You are the PCB design advisor")
    assert len(agent.rules().splitlines()) <= 150


def test_the_allowlist_works_from_a_cwd_outside_the_repo():
    allowed = [oscompat.py(v) for v in workspace.get("agent.providers.claude_code.tools.allowed")]
    assert not [a for a in allowed if "{" in a], allowed
    assert f"Bash({oscompat.python_cmd()} {workspace.REPO.as_posix()}/scripts/sources.py *)" in allowed
    edit = [a for a in allowed if a.startswith("Edit(")]
    assert edit and all(a.startswith("Edit(//") for a in edit)
    assert "./" not in "".join(allowed)


def test_rule_path_is_the_double_slash_form():
    assert oscompat.rule_path(pathlib.PureWindowsPath("C:/Users/x/projects")) == "//c/Users/x/projects"
    assert oscompat.rule_path(pathlib.PurePosixPath("/Users/x/projects")) == "//Users/x/projects"


# ---------------------------------------------------------------- the repo

def test_the_repo_root_has_no_developer_instructions_the_engine_could_load():
    for name in ("AGENTS.md", "CLAUDE.md", ".agents"):
        assert not (REPO / name).exists(), name
    assert not (REPO / ".claude" / "skills").exists()


def test_every_runtime_skill_has_frontmatter_matching_its_folder():
    skills = sorted((REPO / "runtime" / "skills").iterdir())
    assert any(s.name == "altium-help" for s in skills)
    for folder in skills:
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        assert m, f"{folder.name}: no frontmatter"
        fields = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
        assert fields.get("name") == folder.name
        assert len(fields.get("description", "")) > 40, folder.name


def test_the_real_pack_syncs_clean(engine_home):
    runtime_pack.sync()
    assert runtime_pack.check() == []
    assert (engine_home / ".agents" / "skills" / "altium-help" / "SKILL.md").is_file()
    assert runtime_pack.SKILL_CODE in (engine_home / ".claude" / "skills" / "altium-help" / "SKILL.md").read_text(encoding="utf-8")
    assert runtime_pack.AGENTS_CODE in (engine_home / "AGENTS.md").read_text(encoding="utf-8")


def test_every_script_agents_md_names_is_allowed_for_claude_code():
    """A script AGENTS.md tells the engine to run but Claude Code may not run = a blocked answer."""
    import fnmatch
    repo = pathlib.Path(__file__).resolve().parents[1]
    cfg = json.loads((repo / "config" / "defaults.json").read_text(encoding="utf-8"))
    allowed = cfg["agent"]["providers"]["claude_code"]["tools"]["allowed"]
    patterns = [m.group(1) for a in allowed if (m := re.match(r"Bash\(\{python\} \{repo\}/(\S+) \*\)$", a))]
    text = (repo / "runtime" / "AGENTS.md").read_text(encoding="utf-8")
    named = sorted(set(re.findall(r"python <repo>/(scripts/\S+\.py)", text)))
    assert named, "no scripts found in AGENTS.md"
    missing = [s for s in named if not any(fnmatch.fnmatch(s, p) for p in patterns)]
    assert not missing, f"not in claude_code tools.allowed: {missing}"


def test_the_pack_carries_this_machines_python_command(monkeypatch):
    """The allow-list says `python3` on a Mac; an engine that read `python <repo>/...` typed it and was denied."""
    monkeypatch.setattr(runtime_pack.oscompat, "python_cmd", lambda: "python3")
    out = runtime_pack.render("AGENTS.md", b"run `python <repo>/scripts/calc.py` (not ipython <repo>)").decode()
    assert "`python3 <repo>/scripts/calc.py`" in out and "ipython <repo>" in out
    assert runtime_pack.render("x.py", b"python <repo>") == b"python <repo>"
    monkeypatch.setattr(runtime_pack.oscompat, "python_cmd", lambda: "python")
    assert runtime_pack.render("AGENTS.md", b"python <repo>/x") == b"python <repo>/x"
