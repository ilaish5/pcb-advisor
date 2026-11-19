"""Human labels for engine steps and a kind for every way a turn can fail."""
import datetime
import json
import os
import re
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ERROR_KINDS = ("not_installed", "not_logged_in", "usage_limit", "stopped",
               "idle_timeout", "total_timeout", "engine_error")


def _clip(s, n=80):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _base(path):
    return os.path.basename(str(path).replace("\\", "/").rstrip("/")) or str(path)


# an interpreter (python, python3, py, .../python.exe, quoted or not, `&` in PowerShell) running scripts/....py
SCRIPT_RUN = re.compile(
    r"""(?:^|[\s;&|("'])&?\s*["']?(?:[^\s"']*[/\\])?(?:python[\d.]*|py)(?:\.exe)?["']?(?:\s+-[\w-]+)*\s+"""
    r"""["']?((?:[^\s"']*[/\\])?scripts[/\\](?:[\w.-]+[/\\])*([\w.-]+\.py))["']?(?:\s+(.*))?""", re.S)


def is_script_run(tool_name, tool_input=None):
    """True for a Bash/PowerShell command that RUNS one of the tool's own scripts (python .../scripts/x.py).
    `ls`, `cat notes.txt`, and reading a script (`cat scripts/x.py`) are not runs."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    return str(tool_name or "") in ("Bash", "PowerShell") and bool(SCRIPT_RUN.search(str(inp.get("command") or "")))


def label(tool_name, tool_input=None):
    """Short English label (<= 80 chars) for one tool call."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    name = str(tool_name or "")
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        m = SCRIPT_RUN.search(cmd)
        if m:
            script = m.group(2)
            rest = (m.group(3) or "").strip().strip("\"'")
            return _clip(f"Running {script} {rest}".strip())
        return _clip("Running " + cmd) if cmd else name
    if name == "Read":
        return _clip("Reading " + _base(inp.get("file_path") or inp.get("path") or "")) if (inp.get("file_path") or inp.get("path")) else "Read"
    if name in ("Grep", "Glob"):
        pat = inp.get("pattern")
        return _clip(f"Searching for {pat}") if pat else name
    if name == "WebSearch":
        return _clip(f"Searching the web: {inp.get('query')}") if inp.get("query") else name
    if name == "WebFetch":
        host = urllib.parse.urlparse(str(inp.get("url") or "")).hostname
        return _clip(f"Opening {host}") if host else name
    if name == "Skill":
        sk = inp.get("skill") or inp.get("name")
        return _clip(f"Opening skill {sk}") if sk else name
    if name in ("Edit", "Write", "MultiEdit"):
        p = inp.get("file_path") or inp.get("path")
        return _clip("Editing " + _base(p)) if p else name
    return _clip(name) or "Working"


def classify(text="", stderr="", returncode=None):
    """(error_kind, retry_at_iso_or_None) from the engine's words. Order matters: a
    login problem and a limit are told apart before the generic fallback."""
    blob = f"{text or ''}\n{stderr or ''}"
    low = blob.lower()
    if ("not logged in" in low or "/login" in low or "oauth session expired" in low
            or "could not be refreshed" in low or "failed to authenticate" in low):
        return "not_logged_in", None
    if "usage limit" in low or "limit reached" in low:
        m = re.search(r"\|\s*(\d{10})(?!\d)", blob) or re.search(r"\breset[s]?\D{0,20}(\d{10})(?!\d)", blob)
        retry = None
        if m:
            try:
                retry = datetime.datetime.fromtimestamp(int(m.group(1)), datetime.timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                retry = None
        return "usage_limit", retry
    return "engine_error", None


CALL_CUT = 1500          # one string in a recorded tool call
CALL_BYTES = 8000        # one recorded call input, as json
MAX_CALLS = 80


def clip_value(v, cut=CALL_CUT, depth=0):
    """A copy of any json-like value with strings cut, lists at 20 items, nesting at 5 levels (for the debug record)."""
    if isinstance(v, str):
        return v if len(v) <= cut else v[:cut] + f"...[+{len(v) - cut} chars]"
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if depth >= 5:
        return str(v)[:200]
    if isinstance(v, dict):
        return {str(k): clip_value(x, cut, depth + 1) for k, x in list(v.items())[:20]}
    if isinstance(v, (list, tuple)):
        return [clip_value(x, cut, depth + 1) for x in list(v)[:20]]
    return str(v)[:cut]


def clip_input(inp):
    """A tool call's input, clipped recursively and held to about CALL_BYTES in all."""
    out = clip_value(inp) if isinstance(inp, dict) else {}
    try:
        text = json.dumps(out, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {}
    return out if len(text) <= CALL_BYTES else {"_cut": text[:CALL_BYTES]}


def now_iso():
    return datetime.datetime.now().isoformat(timespec="milliseconds")
