"""The installers cannot run in the test suite (CI runs the real ones, see .github/workflows/install.yml). These pin
what a regression would break silently: syntax, the knobs CI and the README rely on, and the rules that keep a second
run harmless."""
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SH = (REPO / "install.sh").read_text(encoding="utf-8")
PS1 = (REPO / "install.ps1").read_text(encoding="utf-8")


# On Windows `bash` is usually the WSL launcher, which fails without a distro; the Mac/Linux jobs parse them.
@pytest.mark.skipif(not shutil.which("bash") or sys.platform == "win32", reason="no real bash")
@pytest.mark.parametrize("name", ["install.sh", "start.sh"])
def test_shell_scripts_parse(name):
    assert subprocess.run(["bash", "-n", str(REPO / name)], capture_output=True).returncode == 0


@pytest.mark.skipif(not shutil.which("pwsh"), reason="no pwsh")
def test_powershell_script_parses():
    code = "$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e);if($e){$e;exit 1}" % (REPO / "install.ps1")
    assert subprocess.run(["pwsh", "-NoProfile", "-Command", code], capture_output=True).returncode == 0


def test_powershell_script_is_plain_ascii_and_never_exits():
    PS1.encode("ascii")                                      # PowerShell 5.1 reads a BOM-less file as ANSI
    assert not re.search(r"^\s*exit\b", PS1, re.M)           # under `irm | iex` exit closes the student's terminal
    assert "-ExecutionPolicy Bypass" in PS1 and "Install-PcbAdvisor -Argv $args" in PS1


@pytest.mark.parametrize("knob", ["PCB_DIR", "PCB_REPO", "PCB_REF", "PCB_YES", "PCB_NO_CLAUDE", "PCB_NO_START", "PCB_NO_GIT", "PCB_ZIP_URL"])
def test_both_installers_honour_every_knob(knob):
    assert knob in SH and knob in PS1


def test_questions_default_to_yes_and_read_the_terminal_not_the_pipe():
    assert "[Y/n]" in SH and "[Y/n]" in PS1
    assert "/dev/tty" in SH                                  # stdin is the script under `curl | bash`
    assert "IsInputRedirected" in PS1


def test_winget_installs_are_user_scope_with_agreements_and_exact_id():
    m = re.search(r"& winget install[^\n]*", PS1)
    assert m and all(x in m.group(0) for x in ("-e --id", "--scope user", "--accept-package-agreements", "--accept-source-agreements"))
    assert "Python.Python.3.12" in PS1 and "Git.Git" in PS1


def test_a_second_run_never_deletes_user_data():
    for text in (SH, PS1):
        for m in re.finditer(r"(rm -rf|Remove-Item)[^\n]*", text):
            line = m.group(0)
            ok = ".venv" in line or "tmp" in line.lower() or "'.git'" in line or '/.git"' in line   # .git: the rollback
            assert ok, line
        assert "projects" not in " ".join(re.findall(r"(?:rm -rf|Remove-Item)[^\n]*", text))
    assert "pull --ff-only" in SH and "pull --ff-only" in PS1  # repair never rewrites local work
    assert "status --porcelain" in SH and "status --porcelain" in PS1


def test_a_zip_copy_becomes_a_clone_in_place_and_keeps_projects():
    """Update needs a branch with an upstream; a fresh folder would strand projects/, which live in the repo."""
    for text in (SH, PS1):
        assert "Turn it into a git clone" in text                  # asked, never done silently
        assert "FETCH_HEAD" in text and "-u" in text and "origin/" in text
        assert "reset" in text and "--hard" in text                # tracked files only; untracked work is untouched
    assert 'rm -rf "$DIR/.git"' in SH and "Join-Path $dir '.git'" in PS1   # a failed conversion leaves the ZIP copy


def test_the_signin_is_offered_not_forced_and_the_start_only_waits_on_doctor():
    for text in (SH, PS1):
        assert "auth login" in text and "auth status" in text
        assert "--exit-start" in text
    assert "install.ps1" in (REPO / "install.bat").read_text(encoding="utf-8")


def test_readme_and_agent_prompt_point_at_the_same_one_liners():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    agent = (REPO / "INSTALL-AGENT.md").read_text(encoding="utf-8")
    for needle in ("raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.ps1 | iex",
                   "raw.githubusercontent.com/ilaish5/pcb-advisor/main/install.sh | bash"):
        assert needle in readme and needle in agent
    assert "INSTALL-AGENT.md" in readme.split("## Install")[0]      # an agent sees it in the first lines
    assert "INSTALL-AGENT.md" in (REPO / "SETUP-PROMPT.md").read_text(encoding="utf-8")
