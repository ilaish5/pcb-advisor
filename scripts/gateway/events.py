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


# ---------------------------------------------------------------- what the student sees
# One verb phrase per script the agent runs, in the student's words. A script that is not here is "Running a check":
# the raw command line is for the debug record and the "details" of a step, never the headline.
SCRIPT_WORDS = {
    "check_availability.py": "Checking stock and price at JLC", "compare_prices.py": "Comparing prices",
    "verify_part.py": "Checking the part's pins against its datasheet", "render_sheet.py": "Drawing the sheet preview",
    "export_bom.py": "Exporting the BOM", "export_cpl.py": "Exporting the placement file", "lint.py": "Checking the project",
    "jlc.py": "Searching JLC", "library.py": "Checking the library", "partlib.py": "Checking the part library",
    "sources.py": "Working with the documents", "trace_width.py": "Calculating the trace width", "calc.py": "Calculating",
    "rules.py": "Checking the rules", "model.py": "Reading the project", "validate_netlist.py": "Checking the netlist",
    "preview_sch.py": "Drawing the schematic preview", "preview_pcb.py": "Drawing the board preview", "outjob.py": "Preparing the outputs",
    "dfm.py": "Checking manufacturability", "bridge.py": "Talking to Altium", "dump.py": "Reading the Altium files",
    "keeping.py": "Noting the decision", "project.py": "Reading the project", "introspect.py": "Looking at earlier runs",
    "lineage.py": "Tracing where a value came from", "order_check.py": "Checking the order", "verify_sources.py": "Checking the sources",
    "schematic.py": "Checking the schematic", "board.py": "Checking the board", "idea.py": "Checking the idea",
    "requirements.py": "Checking the requirements", "drc_origin.py": "Tracing the DRC findings", "drc_jlc_map.py": "Matching the DRC to JLC",
}
# R2/W22: the scripts whose run IS a check of the design (a sheet, the board, a part's pins, the order): a chip for one carries `check: true`,
# so the chat decides "a check ran" from the recorded script and not from the words of the label
CHECK_SCRIPTS = frozenset({"verify_part.py", "schematic.py", "schematic_review.py", "board.py", "lint.py", "validate_netlist.py", "rules.py",
                           "order_check.py", "requirements.py", "dfm.py", "drc_origin.py", "drc_jlc_map.py", "verify_sources.py"})
_FIRST = re.compile(r"^(Denied: Running|Running|Reading|Searching for|Searching the web:|Opening skill|Opening|Editing)\s*(.*)$", re.S)
# a bare tool name (the label of a call that has no input to name): said in words, never as the tool's own name
_BARE = {"Read": "Reading a file", "Grep": "Searching the project", "Glob": "Searching the project", "Bash": "Running a command",
         "PowerShell": "Running a command", "Edit": "Updating a file", "Write": "Updating a file", "MultiEdit": "Updating a file",
         "WebSearch": "Searching the web", "WebFetch": "Opening a web page", "Skill": "Opening instructions"}
_TOKEN = re.compile(r"^[\w:.-]+$")
_PLAIN_WORDS = {"Thinking", "Working", "Stopping", "Done"}


def human(label):
    """The student's version of a `label()` line: what is being done, not which command. Tool names, script names, search patterns, file
    names, paths and web addresses never show (`Running jlc.py search x` is "Searching JLC", `Reading W25Q128JV.pdf` is "Reading the
    datasheet", `Searching for ^pin.*` is "Searching the project"); the full label stays in the debug record (calls). Already plain
    words come back unchanged, so it is safe to apply twice."""
    lab = str(label or "").strip()
    if lab in _BARE:
        return _BARE[lab]
    m = _FIRST.match(lab)
    if not m:
        return lab if lab in _PLAIN_WORDS else "Working" if (not lab or _TOKEN.match(lab)) else lab       # one unknown token is a tool's name
    verb, rest = m.group(1), m.group(2).strip()
    if verb in ("Running", "Denied: Running"):
        script = re.match(r"([\w.-]+\.py)\b", rest)
        out = SCRIPT_WORDS.get(script.group(1), "Running a check") if script else "Running a command"
        return ("Not allowed: " + out[0].lower() + out[1:]) if verb != "Running" else out
    if verb == "Opening skill":
        return "Opening instructions"
    if verb == "Reading":
        if re.match(r"the\b", rest):
            return lab                                         # already plain
        return "Reading the datasheet" if re.search(r"\.pdf\b", rest, re.I) else "Reading the project files"
    if verb == "Searching for":
        return "Searching the project"
    if verb == "Searching the web:":
        return "Searching the web"
    if verb == "Editing":
        return "Updating a file"
    if verb == "Opening":
        return "Opening a web page" if re.match(r"[\w-]+(\.[\w-]+)+$", rest) else lab
    return lab


# an interpreter running code typed on the command line: never something to approve, never something to show
ONE_LINER = re.compile(
    r"""(?:^|[\s;&|("'])(?:[^\s"']*[/\\])?(?:python[\d.]*|py|node|perl|ruby|pwsh|powershell|cmd|bash|sh)(?:\.exe)?["']?\s+"""
    r"""(?:-\w*[ce]\b|-command\b|-encodedcommand\b|/c\b|-\s*(?:<<|$)|<<)""", re.I)


def is_internal_run(tool_name, tool_input=None):
    """True for a refused call the student has no business deciding on: a shell command that is not one of the tool's own
    scripts (`python -c ...`, a heredoc, `ls`, a combined command). The server's allow list is the only authority on shell
    commands, so these are never offered as "Allow" and never drawn; the agent is told to run its script as one plain command."""
    name = str(tool_name or "")
    if name not in ("Bash", "PowerShell"):
        return False
    return not is_script_run(name, tool_input) or bool(ONE_LINER.search(str((tool_input or {}).get("command") or "")))
