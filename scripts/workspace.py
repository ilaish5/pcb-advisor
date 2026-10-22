"""
The workspace: where things live, and what the user configured.

Every other script asks this module for a path.  Nothing else hardcodes one,
which is what makes the workspace movable (PCB_ADVISOR_HOME) and the whole
tool a folder you can copy to another machine.

Layers, lowest first:
  1. config/defaults.json   shipped with the repo, always complete, tracked in git
  2. config.json            yours, local, gitignored, holds only what you changed
  3. environment            PCB_ADVISOR_HOME, PCB_ADVISOR_CONFIG, PCB_ADVISOR_PORT,
                         PCB_ADVISOR_PROVIDER, and PCB_ADVISOR_ENGINE_HOME (read by runtime_pack)

A relative path in the config resolves against the workspace home; an absolute
one is taken as-is, so projects can live outside the repo.
"""
import copy
import json
import os
import pathlib
import re
import shutil

import oscompat

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULTS_PATH = REPO / "config" / "defaults.json"

_cache = None


# ---------------------------------------------------------------- locations

def home():
    """The workspace root: the repo, unless PCB_ADVISOR_HOME says otherwise."""
    env = os.environ.get("PCB_ADVISOR_HOME")
    return pathlib.Path(env).expanduser().resolve() if env else REPO


def config_path():
    env = os.environ.get("PCB_ADVISOR_CONFIG")
    return pathlib.Path(env).expanduser().resolve() if env else home() / "config.json"


def defaults():
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- config

def _merge(base, over):
    """Deep merge. A dict merges key by key; anything else replaces."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(reload=False):
    """The effective config: defaults <- config.json <- environment."""
    global _cache
    if _cache is not None and not reload:
        return _cache

    cfg = defaults()
    path = config_path()
    if path.exists():
        try:
            cfg = _merge(cfg, json.loads(path.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is not valid JSON: {exc}")

    port = os.environ.get("PCB_ADVISOR_PORT")
    if port and port.isdigit():
        cfg["server"]["port"] = int(port)
    provider = os.environ.get("PCB_ADVISOR_PROVIDER")
    if provider:
        cfg["agent"]["provider"] = provider

    _cache = cfg
    return cfg


def get(dotted, default=None):
    """get('server.port') -> 8931"""
    cur = load()
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def save(cfg):
    """Write only what differs from the shipped defaults. A small config file
    stays readable, and you inherit future defaults instead of freezing them."""
    diff = _diff(defaults(), cfg)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load(reload=True)
    return path


def set_value(dotted, value):
    """Set one key and persist it. Returns the value actually stored."""
    if dotted == "agent.autonomy" and value not in ("ask", "important", "auto"):
        raise SystemExit("agent.autonomy must be one of: ask, important, auto")
    cfg = copy.deepcopy(load())
    cur = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
        if not isinstance(cur, dict):
            raise SystemExit(f"{dotted}: '{part}' is not a section")
    cur[parts[-1]] = value
    save(cfg)
    return value


def _diff(base, cur):
    out = {}
    for k, v in (cur or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            sub = _diff(base[k], v)
            if sub:
                out[k] = sub
        elif base.get(k) != v:
            out[k] = v
    return out


def unknown_keys(cfg=None):
    """Keys in config.json that no default declares - almost always a typo."""
    return _unknown(defaults(), _diff(defaults(), cfg or load()), "")


def _unknown(base, over, prefix):
    bad = []
    for k, v in (over or {}).items():
        path = f"{prefix}{k}"
        if k not in base:
            # provider blocks are open: you may register your own
            if not re.match(r"^agent\.providers\.[^.]+$", path):
                bad.append(path)
        elif isinstance(v, dict) and isinstance(base[k], dict):
            bad.extend(_unknown(base[k], v, path + "."))
    return bad


# ---------------------------------------------------------------- paths

# The templates and the UI ship with the repo; your work lives in the workspace home. They
# are usually the same folder, and PCB_ADVISOR_HOME is what pulls them apart:
# your projects move to the new home, the knowledge stays where it was installed.
_REPO_DIRS = {"templates_dir", "ui_dir"}


def _dir(key):
    raw = get(f"workspace.{key}") or key.replace("_dir", "")
    p = pathlib.Path(raw).expanduser()
    if p.is_absolute():
        return p
    return (REPO if key in _REPO_DIRS else home()) / p


def projects_dir():
    return _dir("projects_dir")


def shared_dir():
    return _dir("shared_dir")


def templates_dir():
    return _dir("templates_dir")


def ui_dir():
    return _dir("ui_dir")


def datasheets_dir():
    return shared_dir() / "datasheets"


def project_dir(name=None):
    return projects_dir() / safe_name(name or default_project())


def default_project():
    return get("server.default_project", "demo")


# Everything a path must not contain: separators, the Windows-reserved set, and
# control characters. A denylist, not an allowlist - an allowlist of ASCII turns
# every Hebrew project name into "untitled".
_UNSAFE = re.compile(r'[/\\<>:"|?*\x00-\x1f]')


def safe_name(name):
    """A project name is a folder name. Non-Latin names are kept as they are;
    what must never survive is anything that could escape the projects dir."""
    safe = _UNSAFE.sub("-", str(name or ""))
    safe = re.sub(r"[-\s]+", "-", safe).strip("-. ")[:60].strip("-. ")
    # names Windows reserves for devices, with or without an extension
    if re.fullmatch(r"(?i)(con|prn|aux|nul|com\d|lpt\d)(\..*)?", safe):
        safe = "_" + safe
    return safe or "untitled"


# ---------------------------------------------------------------- the map
#
# What an engine with hands needs to know to find its way around. Generated,
# never written by hand: paths come from the config and PCB_ADVISOR_HOME can
# move them, so a hardcoded map would become a lie the first time someone
# changes projects_dir.
#
# `write` is the honest answer to "may the engine edit this directly", and the
# reasons matter more than the rule:
#   - the .jsonl logs are append-only and carry `by` (user or agent). Editing
#     one destroys the record of a student changing their mind, and forging
#     `by` destroys the only enforcement of "the student decides".
#   - derived files are rewritten on the next run; writing them is pointless.

def describe(project=None, engine_home=None):
    """The workspace as an engine needs to see it: real paths, what is in them,
    and what it may write. Absolute, because the engine's cwd is not the repo."""
    pdir = project_dir(project)

    def rel(p):
        # The engine runs in its own folder (the engine home), not in the repo, so every
        # path is absolute. Forward slashes on Windows too: the engine reads these into a shell.
        return p.as_posix()

    repo = REPO.as_posix()
    crepo = oscompat.command_path(REPO)      # what the engine types in a command
    places = [
            {"path": f"{repo}/shared/reference", "write": False,
             "what": "the course reference (git-tracked): AGENTS.md is the topic index; course/ad20-essentials/ is the "
                     "step-by-step Altium manual. Read it for any 'how do I ... in Altium' question"},
            {"path": rel(datasheets_dir()), "write": "via scripts/sources.py only",
             "what": "the shared library: GENERAL documents every project sees (application notes, design guides, "
                     "standards). A part's datasheet is not kept here but in the project's sources/. Each file has a "
                     ".json beside it with its url and sha256, and a .txt with its extracted text"},
            {"path": rel(pdir / "sources"), "write": "via scripts/sources.py only",
             "what": "documents THIS project uses: the datasheets of its parts, its uploads and what it cites, "
                     "same format"},
            {"path": rel(pdir / "project.json"), "write": False,
             "what": "this board's settings: layers, copper weight, temperature rise"},
            {"path": rel(pdir / "idea.json"), "write": False,
             "what": "the last SAVED idea, block diagram and checklist. Your idea.* actions go to the live draft "
                     "(idea-draft.json, also read-only) that CURRENT STATE shows; the student saves it"},
            {"path": rel(pdir / "bom-log.jsonl"), "write": False,
             "what": "append-only: every applied BOM change. You change the BOM only by emitting bom.propose; "
                     "the student approves, and the server appends"},
            {"path": rel(pdir / "bom.json"), "write": False,
             "what": "DERIVED from the logs: the BOM lines with stock, price and library state. Read it, never edit it"},
            {"path": rel(pdir / "supply-log.jsonl"), "write": False,
             "what": "append-only stock and price checks, with supplier and time. Only the availability skill writes it"},
            {"path": rel(pdir / "proposals.jsonl"), "write": False,
             "what": "append-only: your BOM proposals and the student's decisions on them"},
            {"path": rel(pdir / "library-log.jsonl"), "write": False,
             "what": "append-only: library parts, their model source and verification"},
            {"path": rel(pdir / "netlist") + "/<sheet>.json", "write": False,
             "what": "one schematic sheet. Emit netlist.write; the server validates it against the BOM"},
            {"path": rel(pdir / "chats") + "/<id>.jsonl", "write": False,
             "what": "append-only conversations, one file per session. index.json lists them; a session with an "
                     "anchor is about one BOM line"},
            {"path": rel(pdir / "chats") + "/<id>.memory.md", "write": False,
             "what": "what a conversation would otherwise forget. Bounded, and rewritten by a separate call"},
            {"path": rel(pdir / "notes.md"), "write": True,
             "what": "the project's notes. Nothing derives from it"},
            {"path": rel(pdir / "checks"), "write": False,
             "what": "DFM check reports and image slices. Each report has index.json, triage.json and slice_*.jpg files"},
            {"path": rel(pdir / "exports"), "write": "generated outputs",
             "what": "ready OutJob, BOMs, and CPL files exported for manufacturing"},
        ]
    try:
        import project as project_mod
        link = project_mod.altium_link(pdir.name)
        p_file = link.get("project_file")
        if p_file:
            folder_posix = pathlib.Path(p_file).parent.as_posix()
            places.append({
                "path": folder_posix,
                "write": False,
                "what": f"the student's Altium project (linked in Settings): {pathlib.Path(p_file).name}; "
                        f"board {pathlib.Path(link.get('pcb_file') or '?').name}; outputs {link.get('outputs_dir') or '?'}. "
                        "READ ONLY for file tools - never write here (changes go through scripts/altium/bridge.py); read a SchDoc/PcbDoc/PrjPcb/.RUL with "
                        + oscompat.py("python3 {repo}/scripts/altium/dump.py <file> [--full]"),
            })
    except Exception:
        pass
    return {
        "home": str(home()),
        "repo": oscompat.command_path(REPO),
        "cwd": str(engine_home) if engine_home else str(REPO),
        "project": pdir.name,
        "places": places,
        "scripts": [
            {"run": oscompat.py("python3 {repo}/scripts/outjob.py <project>"),
             "what": "generate ready Altium OutJob file (Gerber RS-274X, NC drill, JLC BOM, CPL, schematic PDF)"},
            {"run": oscompat.py("python3 {repo}/scripts/dfm.py ingest <project> <pdf>"),
             "what": "ingest JLCDFM report PDF into slices and triage table"},
            {"run": oscompat.py("python3 {repo}/scripts/checks/board.py <pcb_file>"),
             "what": "run physical board checks (connectors, decap distance, CPL rotation). Add --design <project> to also compare "
                     "the board with the design: a net, pin or part the PcbDoc lacks is an error (a clean DRC does NOT show this: no net, no unrouted net)"},
            {"run": oscompat.py("python3 {repo}/scripts/checks/schematic.py <source>"),
             "what": "build netlist and check single-pin nets, unconnected IC power pins, pin-net mismatches"},
            {"run": oscompat.py("python3 {repo}/scripts/skills/check_availability.py <project> [LINE ...]"),
             "what": "stock and price per supplier, stored with the time. NEVER state stock or price without running this"},
            {"run": oscompat.py("python3 {repo}/scripts/skills/compare_prices.py <project>"),
             "what": "cost per board by supplier, from the stored checks"},
            {"run": oscompat.py("python3 {repo}/scripts/skills/verify_part.py <project> <line>"),
             "what": "compare a part's pins with its datasheet text; the result is stored"},
            {"run": oscompat.py("python3 {repo}/scripts/skills/export_bom.py <project> [jlc|pcbway|generic]"),
             "what": "write the BOM for a manufacturer"},
            {"run": oscompat.py("python3 {repo}/scripts/skills/render_sheet.py <project> <sheet>"),
             "what": "draw a sheet from its netlist"},
            {"run": oscompat.py(f"python3 {crepo}/scripts/sources.py list {pdir.name}"),
             "what": "what is already in the shared library and in this project's sources"},
            {"run": oscompat.py(f"python3 {crepo}/scripts/sources.py get {pdir.name} <url> [name]"),
             "what": "add a datasheet to this project (it is stored in the project's sources/ only). Use this "
                     "rather than curl - it records the url and sha256, which is what makes it citable"},
            {"run": oscompat.py(f'python3 {crepo}/scripts/sources.py verify <name> "<quote>" {pdir.name}'),
             "what": "is this quote really in that document? Run it BEFORE you quote"},
            {"run": oscompat.py("python3 {repo}/scripts/trace_width.py <amps> --oz <copper> --rise <degrees>"),
             "what": "IPC-2221 trace width. Run it; never estimate a width yourself"},
            {"run": oscompat.py(f"python3 {crepo}/scripts/lineage.py {pdir.name}"),
             "what": "is each exported file still made from the current design? Run it before anything goes to JLC"},
            {"run": oscompat.py(f"python3 {crepo}/scripts/introspect.py {pdir.name} [summary|turns|errors|version]"),
             "what": "about yourself: what you ran, time and cost per turn, failures, the tool version and updates"},
            {"run": oscompat.py("python3 {repo}/scripts/model.py <project>"),
             "what": "the full project state, more than the summary above carries"},
        ],
    }


# ---------------------------------------------------------------- setup

def init(force=False):
    """Create the workspace folders and a config.json. Safe to re-run."""
    made = []
    for d in (projects_dir(), datasheets_dir()):
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            made.append(str(d.relative_to(home())) if d.is_relative_to(home()) else str(d))

    path = config_path()
    if force or not path.exists():
        path.write_text(json.dumps({
            "user": {"name": "", "language": "auto"},
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made.append(path.name)
        load(reload=True)
    made += _copy_examples()
    return {"home": str(home()), "config": str(path), "created": made}


def _copy_examples():
    """Give a new workspace the shipped example projects (examples/<name>/ -> projects/<name>/).
    A project that already exists is never touched, so deleting an example and re-running init
    brings it back, and editing one is safe."""
    src = REPO / "examples"
    made = []
    if not src.is_dir():
        return made
    for ex in sorted(src.iterdir()):
        dest = projects_dir() / safe_name(ex.name)
        if ex.is_dir() and not ex.name.startswith(".") and not dest.exists():
            shutil.copytree(ex, dest, ignore=shutil.ignore_patterns("__pycache__"))
            made.append(f"projects/{dest.name}")
    return made


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    import sys

    args = sys.argv[1:]
    if args and args[0] == "init":
        print(json.dumps(init(force="--force" in args), ensure_ascii=False, indent=2))
    elif len(args) >= 2 and args[0] == "set":
        raw = args[2] if len(args) > 2 else ""
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        print(f"{args[1]} = {json.dumps(set_value(args[1], val), ensure_ascii=False)}")
    elif len(args) == 1 and args[0] != "show":
        print(json.dumps(get(args[0]), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(load(), ensure_ascii=False, indent=2))
        for k in unknown_keys():
            print(f"  warning: unknown config key {k}")
