"""The few places where macOS and Windows disagree, in one file.

Altium only runs on Windows, so most students run this there; the people who
wrote it run macOS. Everything that would quietly differ between the two goes
through here instead of being special-cased where it bites.
"""
import functools
import os
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


def resolve(cmd):
    """Full path of a command on PATH, or the name unchanged if it is not there.

    On Windows an npm-installed CLI is `claude.cmd`. shutil.which finds it
    through PATHEXT, but subprocess given the bare name only looks for an .exe
    and raises FileNotFoundError - so run the path which() found."""
    return shutil.which(cmd) or cmd


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
    return re.sub(r"(?<![\w./-])python3 ", python_cmd() + " ", command)
