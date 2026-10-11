"""
The engine gateway.

A provider is transport and nothing else: text in, text out. The rules, the
state and the action parsing belong to agent.py, which is what makes swapping
an engine a config change rather than a rewrite.
"""
import pytest

import gateway


def test_every_registered_engine_describes_itself(home):
    rows = gateway.describe_all()
    assert rows
    for row in rows:
        assert row["id"] and row["title"] and row["status"] in ("implemented", "planned")


def test_the_configured_engine_is_the_default(home):
    import workspace
    workspace.set_value("agent.provider", "external")
    assert gateway.resolve(None) == "external"
    assert gateway.resolve("claude_code") == "claude_code"   # an explicit ask wins


def test_an_unknown_engine_name_does_not_crash_the_server(home):
    """Naming a provider that does not exist is a typo in a config file, and a
    typo must not take the whole tool down on startup."""
    name = gateway.resolve("no_such_engine")
    p = gateway.provider(name)
    ok, why = p.available()
    assert ok is False and why


def test_only_an_engine_with_hands_gets_the_filesystem_map(home):
    """Telling a text-only engine to go and open a datasheet does not fail
    loudly - it invents one."""
    assert gateway.provider("claude_code").has_workspace() is True
    assert gateway.provider("external").has_workspace() is False


# ---------------------------------------------------------------- the CLI call

def test_the_prompt_goes_on_stdin_never_as_an_argument(home, monkeypatch):
    """--allowedTools is variadic: given as arguments, it swallowed the trailing
    prompt and the engine answered a question it had never been asked. Nothing
    about the argv looked wrong, which is why this is a test and not a comment."""
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["stdin"] = kw.get("input")

        class R:
            returncode, stdout, stderr = 0, "hello", ""
        return R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = gateway.route(gateway.Request(prompt="THE PROMPT", timeout=5),
                        name="claude_code")
    assert res.ok
    assert seen["stdin"] == "THE PROMPT"
    assert "THE PROMPT" not in " ".join(seen["argv"])


def test_the_tool_policy_is_passed_to_the_cli(home, monkeypatch):
    """With no allow-list the CLI stops to ask for approval, and print mode has
    no way to answer - so it hangs until the timeout."""
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = " ".join(argv)
        seen["list"] = list(argv)

        class R:
            returncode, stdout, stderr = 0, "ok", ""
        return R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code")
    assert "--allowedTools" in seen["argv"]
    assert "--disallowedTools" in seen["argv"]
    argv = seen["list"]
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    # writing is allowed file by file - never the files the server owns
    # absolute rule paths: the engine runs in its own home, not in the repo
    assert any(a.startswith("Edit(//") and a.endswith("/projects/*/BOM.md)") for a in allowed)
    assert not {"Write", "Edit"} & set(allowed)
    assert not [a for a in allowed if "sketch.json" in a or "decisions" in a]


def test_claude_add_dirs_are_flags_that_no_variadic_flag_can_swallow(home, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["stdin"] = list(argv), kw.get("input")

        class R:
            returncode, stdout, stderr = 0, "ok", ""
        return R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    req = gateway.Request(prompt="P", timeout=5,
                          options={"add_dirs": ["C:/one", "C:/two words"]})
    assert gateway.route(req, name="claude_code").ok
    argv = seen["argv"]
    assert argv.count("--add-dir") == 2
    assert argv[argv.index("--add-dir") + 1] == "C:/one"
    assert "C:/two words" in argv
    # before the variadic tool flags, and each followed by a flag or the end
    assert max(i for i, a in enumerate(argv) if a == "--add-dir")         < argv.index("--allowedTools")
    assert seen["stdin"] == "P" and "P" not in argv
    # no option, no flags
    gateway.route(gateway.Request(prompt="P", timeout=5), name="claude_code")
    assert "--add-dir" not in seen["argv"]


def test_a_failing_engine_reports_rather_than_raises(home, monkeypatch):
    def fake_run(argv, **kw):
        class R:
            returncode, stdout, stderr = 1, "", "engine exploded"
        return R()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    res = gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code")
    assert res.ok is False and "exploded" in (res.error or "")


def test_a_planned_engine_says_so_instead_of_pretending(home):
    row = next((r for r in gateway.describe_all() if r["status"] == "planned"), None)
    if row is None:
        pytest.skip("every registered engine is implemented")
    ok, why = gateway.provider(row["id"]).available()
    assert ok is False and why


def test_every_engine_gets_the_rules_files_in_its_prompt():
    import agent
    text = agent.rules()
    assert text.startswith("You are the PCB design advisor")
    for f in agent.RULES_DIR.glob("*.md"):
        assert f.read_text(encoding="utf-8").strip() in text
