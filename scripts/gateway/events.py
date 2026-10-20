"""Human labels for engine steps and a kind for every way a turn can fail."""
import datetime
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


def label(tool_name, tool_input=None):
    """Short English label (<= 80 chars) for one tool call."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    name = str(tool_name or "")
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        m = re.search(r"""(?:^|[\s"'])((?:[^\s"']*[/\\])?scripts[/\\](?:[\w.-]+[/\\])*([\w.-]+\.py))(?:\s+(.*))?""",
                      cmd, re.S)
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
