"""
The engine gateway.

A provider is transport and nothing else: text in, text out. The rules, the
state and the action parsing belong to agent.py, which is what makes swapping
an engine a config change rather than a rewrite.
"""
import shutil

import pytest

import gateway


@pytest.fixture(autouse=True)
def claude_on_path(monkeypatch):
    """The CLI tests fake stream.run (the Popen runner); the CI runners have no `claude` installed, so it is found here too."""
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: real(cmd, *a, **k) or (f"/fake/{cmd}" if cmd == "claude" else None))


def fake_stream(monkeypatch, stdout="", returncode=0, stderr="", ended="done"):
    """Replace the Popen runner. Returns a dict that records what the provider asked for."""
    seen = {}

    def fake_run(argv, stdin_text="", cwd=None, env=None, total_timeout=None, idle_timeout=None,
                 cancel=None, on_line=None):
        seen.update(argv=list(argv), stdin=stdin_text, cwd=cwd, total=total_timeout,
                    idle=idle_timeout, cancel=cancel)
        for ln in stdout.splitlines():
            if on_line:
                on_line(ln)
        return returncode, stderr, ended

    monkeypatch.setattr(gateway.stream, "run", fake_run)
    return seen


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
    seen = fake_stream(monkeypatch, stdout="hello")
    res = gateway.route(gateway.Request(prompt="THE PROMPT", timeout=5),
                        name="claude_code")
    assert res.ok
    assert seen["stdin"] == "THE PROMPT"
    assert "THE PROMPT" not in " ".join(seen["argv"])


def test_the_tool_policy_is_passed_to_the_cli(home, monkeypatch):
    """With no allow-list the CLI stops to ask for approval, and print mode has
    no way to answer - so it hangs until the timeout."""
    seen = fake_stream(monkeypatch, stdout="ok")
    gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code")
    argv = seen["argv"]
    assert "--allowedTools" in argv
    assert "--disallowedTools" in argv
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    # writing is allowed file by file - never the files the server owns
    # absolute rule paths: the engine runs in its own home, not in the repo
    assert any(a.startswith("Edit(//") and a.endswith("/projects/*/BOM.md)") for a in allowed)
    assert not {"Write", "Edit"} & set(allowed)
    assert not [a for a in allowed if "sketch.json" in a or "decisions" in a]
    # every script rule also covers the PowerShell tool (Windows engines use it as often as Bash)
    bash = [a for a in allowed if a.startswith("Bash(")]
    assert bash and all("PowerShell(" + a[5:] in allowed for a in bash)
    assert not [a for a in allowed if a.startswith("PowerShell(") and "Bash(" + a[11:] not in allowed]


def test_claude_add_dirs_are_flags_that_no_variadic_flag_can_swallow(home, monkeypatch):
    seen = fake_stream(monkeypatch, stdout="ok")
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
    fake_stream(monkeypatch, returncode=1, stderr="engine exploded")
    res = gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code")
    assert res.ok is False and "exploded" in (res.error or "")
    assert res.meta["error_kind"] == "engine_error"


def test_the_default_engine_args_stream_and_allowed_extra_joins_the_allow_list(home, monkeypatch):
    import workspace
    workspace.set_value("agent.providers.claude_code.tools.allowed_extra", ["Bash(ls /tmp)"])
    seen = fake_stream(monkeypatch, stdout="ok")
    assert gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code").ok
    argv = seen["argv"]
    assert argv[1:7] == ["-p", "-", "--output-format", "stream-json", "--verbose", "--strict-mcp-config"]
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert "Bash(ls /tmp)" in allowed and "PowerShell(ls /tmp)" in allowed
    assert gateway.provider("claude_code").available()[0]      # allowed_extra is a known tools key


def test_a_planned_engine_says_so_instead_of_pretending(home):
    row = next((r for r in gateway.describe_all() if r["status"] == "planned"), None)
    if row is None:
        pytest.skip("every registered engine is implemented")
    ok, why = gateway.provider(row["id"]).available()
    assert ok is False and why


def test_every_engine_gets_the_rules_files_in_its_prompt():
    import agent
    import runtime_pack
    text = agent.rules()
    assert text.startswith("You are the PCB design advisor")
    for f in agent.RULES_DIR.glob("*.md"):
        assert runtime_pack.render(f.name, f.read_bytes()).decode("utf-8").strip() in text


def test_a_repo_path_with_a_space_and_no_short_name_also_gets_a_quoted_rule(home, monkeypatch):
    import oscompat
    import workspace
    monkeypatch.setattr(workspace, "REPO", oscompat.pathlib.Path("C:/x y/pcb"))
    monkeypatch.setattr(oscompat, "_short_path", lambda p: None)
    seen = fake_stream(monkeypatch, stdout="ok")
    assert gateway.route(gateway.Request(prompt="x", timeout=5), name="claude_code").ok
    allowed = seen["argv"][seen["argv"].index("--allowedTools") + 1].split(",")
    assert any(f'"C:/x y/pcb/scripts/' in a and a.startswith("Bash(") for a in allowed)
    assert any(f' C:/x y/pcb/scripts/' in a for a in allowed)     # the plain form stays
