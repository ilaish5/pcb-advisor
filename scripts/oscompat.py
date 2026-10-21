"""The few places where macOS and Windows disagree, in one file.

Altium only runs on Windows, so most students run this there; the people who
wrote it run macOS. Everything that would quietly differ between the two goes
through here instead of being special-cased where it bites.
"""
import functools
import os
import pathlib
import re
import shutil
import subprocess
import sys

WINDOWS = os.name == "nt"

# Text to and from a child process. Without this, Windows decodes with the
# console code page (cp1255 / cp1252) and a Hebrew prompt arrives as '?' or
# raises UnicodeEncodeError before the CLI even starts.
TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


def child_env():
    """Environment for the engine CLI. Every Python the engine starts - our own
    scripts, run through its shell - then reads and prints UTF-8 too."""
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def utf8_stdio():
    """Print ✓, — and Hebrew to a Windows console or a redirected file
    without UnicodeEncodeError. A no-op where stdout is already UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _installer_dirs(cmd):
    """Where the official installer puts a CLI, for a terminal opened before it ran
    (its PATH change reaches only new terminals). `claude` and `agy` have one."""
    if cmd == "agy":
        if WINDOWS:
            local = os.environ.get("LOCALAPPDATA")
            return [pathlib.Path(local) / "agy" / "bin" / "agy.exe"] if local else []
        return [pathlib.Path.home() / ".local" / "bin" / "agy"]
    if cmd != "claude":
        return []
    exe = "claude.exe" if WINDOWS else "claude"
    return [pathlib.Path.home() / ".local" / "bin" / exe]


def which(cmd):
    """Full path of a command, or None. PATH first; then the official installer's folder
    (~/.local/bin/claude, Windows %USERPROFILE%\\.local\\bin\\claude.exe) so a terminal opened before
    the install still finds the CLI. A path given as `cmd` is checked as it is."""
    found = shutil.which(cmd)
    if found:
        return found
    for cand in _installer_dirs(cmd):
        if cand.is_file():
            return str(cand)
    return None


def resolve(cmd):
    """Full path of a command, or the name unchanged if it is not there.

    On Windows an npm-installed CLI is `claude.cmd`. shutil.which finds it
    through PATHEXT, but subprocess given the bare name only looks for an .exe
    and raises FileNotFoundError - so run the path which() found."""
    return which(cmd) or cmd


def _is_store_stub(path):
    # Windows ships python.exe / python3.exe aliases that open the Microsoft
    # Store instead of running anything.
    return "WindowsApps" in (path or "")


@functools.lru_cache(maxsize=1)
def python_cmd():
    """How to start Python from a shell on this machine: `python3` on macOS and
    Linux, `python` or `py` on Windows. Used in the commands the engine is
    allowed to run, so the allow-list matches what it actually types."""
    names = ("python", "py", "python3") if WINDOWS else ("python3", "python")
    for name in names:
        path = shutil.which(name)
        if not path or _is_store_stub(path):
            continue
        try:
            subprocess.run([path, "-c", "pass"], capture_output=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError):
            continue
        return name
    return "python" if WINDOWS else "python3"


def py(command):
    """`python3 scripts/x.py ...` -> the same command for this machine.
    Accepts the {python} placeholder used in config/defaults.json, and the
    literal `python3 ` that older configs and prompts carry."""
    command = command.replace("{python}", python_cmd())
    command = expand_paths(command)
    return re.sub(r"(?<![\w./-])python3 ", python_cmd() + " ", command)


def rule_path(path):
    """A path in the form Claude Code permission rules want for an absolute path:
    `//` + the POSIX form of the path, where `C:/Users/x` becomes `/c/Users/x`."""
    posix = (path if isinstance(path, pathlib.PurePath) else pathlib.PurePath(path)).as_posix()   # a PureWindowsPath stays one on any OS
    m = re.match(r"^([A-Za-z]):(/.*)?$", posix)
    if m:
        posix = f"/{m.group(1).lower()}{m.group(2) or ''}"
    return "/" + posix


def expand_paths(command):
    """The {repo} and {projects} placeholders of config/defaults.json. The engine
    runs in its own folder, not in the repo, so the allow-list needs absolute paths.
      {repo} {projects}              absolute, forward slashes (a command line)
      {repo_rule} {projects_rule}    the same, as a permission-rule path (Edit(...))"""
    if "{repo" not in command and "{projects" not in command:
        return command
    import workspace                # late: workspace imports this module
    repo, projects = workspace.REPO, workspace.projects_dir()
    for key, path in (("repo", repo), ("projects", projects)):
        command = command.replace("{%s_rule}" % key, rule_path(path))
        command = command.replace("{%s}" % key, pathlib.PurePath(path).as_posix())
    return command


def app_data_dir():
    """Where a per-user program keeps its own files on this OS."""
    if WINDOWS:
        return pathlib.Path(os.environ.get("LOCALAPPDATA") or pathlib.Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support"
    return pathlib.Path.home() / ".local" / "share"
