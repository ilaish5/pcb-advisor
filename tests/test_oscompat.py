"""The macOS / Windows seam. Each test pins one difference that used to break."""
import oscompat


def test_the_python_placeholder_becomes_a_command_this_machine_has():
    out = oscompat.py("Bash({python} scripts/sources.py *)")
    assert out == f"Bash({oscompat.python_cmd()} scripts/sources.py *)"
    assert "{python}" not in out


def test_an_old_python3_command_is_rewritten_too(monkeypatch):
    monkeypatch.setattr(oscompat, "python_cmd", lambda: "py")
    assert oscompat.py("Bash(python3 scripts/model.py *)") == "Bash(py scripts/model.py *)"
    assert oscompat.py("python3 pcb.py serve") == "py pcb.py serve"
    # only the interpreter, never a path or a name that merely contains it
    assert oscompat.py("/usr/bin/python3 x") == "/usr/bin/python3 x"


def test_a_command_on_path_is_run_by_its_full_path(monkeypatch, tmp_path):
    monkeypatch.setattr(oscompat.pathlib.Path, "home", classmethod(lambda cls: tmp_path))   # no real ~/.local/bin/claude
    monkeypatch.setattr(oscompat.shutil, "which", lambda c: r"C:\npm\claude.CMD")
    assert oscompat.resolve("claude") == r"C:\npm\claude.CMD"
    monkeypatch.setattr(oscompat.shutil, "which", lambda c: None)
    assert oscompat.resolve("claude") == "claude"


def test_child_processes_speak_utf8():
    assert oscompat.TEXT["encoding"] == "utf-8"
    env = oscompat.child_env()
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"


def test_a_hebrew_prompt_reaches_the_child_intact(tmp_path):
    import subprocess
    import sys
    echo = tmp_path / "echo.py"
    echo.write_text("import sys; sys.stdout.write(sys.stdin.read())", encoding="utf-8")
    text = "מעגל מודפס ✓ — A7670G"
    out = subprocess.run([sys.executable, str(echo)], input=text, capture_output=True,
                         env=oscompat.child_env(), **oscompat.TEXT).stdout
    assert out == text


def test_windows_device_names_never_become_a_project_folder():
    import workspace
    assert workspace.safe_name("CON") == "_CON"
    assert workspace.safe_name("nul.txt") == "_nul.txt"
    assert workspace.safe_name("console") == "console"


def test_a_path_with_a_space_becomes_its_short_space_free_form(monkeypatch):
    monkeypatch.setattr(oscompat, "_short_path", lambda p: r"C:\Users\JOHNSM~1\pcb-advisor")
    assert oscompat.command_path(r"C:\Users\John Smith\pcb-advisor") == "C:/Users/JOHNSM~1/pcb-advisor"
    # no space, no change; no short name available, the path stays as it is
    assert oscompat.command_path("C:/x/pcb") == "C:/x/pcb"
    monkeypatch.setattr(oscompat, "_short_path", lambda p: None)
    assert oscompat.command_path("C:/x y/pcb") == "C:/x y/pcb"


def test_expand_paths_types_the_short_form_but_keeps_rule_paths_long(monkeypatch):
    import workspace
    monkeypatch.setattr(workspace, "REPO", oscompat.pathlib.Path("C:/John Smith/pcb"))
    monkeypatch.setattr(oscompat, "_short_path", lambda p: "C:/JOHNSM~1/pcb" if "pcb" in str(p) and "projects" not in str(p) else None)
    out = oscompat.expand_paths("Bash(x {repo}/scripts/a.py *) Edit({repo_rule}/y)")
    assert "Bash(x C:/JOHNSM~1/pcb/scripts/a.py *)" in out
    assert "John Smith" in out.split("Edit(")[1]
