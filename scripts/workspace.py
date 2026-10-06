"""
The workspace: where things live, and what the user configured.

Every other script asks this module for a path.  Nothing else hardcodes one,
which is what makes the workspace movable (PCB_ADVISOR_HOME) and the whole
tool a folder you can copy to another machine.

Layers, lowest first:
  1. config/defaults.json   shipped with the repo, always complete, tracked in git
  2. config.json            yours, local, gitignored, holds only what you changed
  3. environment            PCB_ADVISOR_HOME, PCB_ADVISOR_CONFIG, PCB_ADVISOR_PORT

A relative path in the config resolves against the workspace home; an absolute
one is taken as-is, so projects can live outside the repo.
"""
import copy
import json
import os
import pathlib
import re

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
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


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
            cfg = _merge(cfg, json.loads(path.read_text(encoding="utf-8")))
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

# The corpus ships with the repo; your work lives in the workspace home. They
# are usually the same folder, and PCB_ADVISOR_HOME is what pulls them apart:
# your projects move to the new home, the knowledge stays where it was installed.
_REPO_DIRS = {"cascade_dir", "reference_dir", "templates_dir", "ui_dir"}


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


def cascade_dir():
    return _dir("cascade_dir")


def reference_dir():
    return _dir("reference_dir")


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
#   - the cascade is the corpus. A constraint invented there is served to every
#     future project, and `convention` provenance requires no source at all, so
#     validation will not catch it.
#   - derived files are rewritten on the next run; writing them is pointless.

def describe(project=None):
    """The workspace as an engine needs to see it: real paths, what is in them,
    and what it may write. Relative to home, so the prompt stays short."""
    pdir = project_dir(project)

    def rel(p):
        return str(p.relative_to(home())) if p.is_relative_to(home()) else str(p)

    return {
        "home": str(home()),
        "project": pdir.name,
        "places": [
            {"path": rel(cascade_dir()) + "/*.yaml", "write": False,
             "what": "the corpus: every question, option and constraint, with its provenance"},
            {"path": rel(reference_dir()) + "/*.md", "write": False,
             "what": "the same knowledge written out for a human"},
            {"path": rel(datasheets_dir()), "write": "via scripts/sources.py only",
             "what": "the shared document library. Each file has a .json beside it "
                     "with its url and sha256, and a .txt with its extracted text"},
            {"path": rel(pdir / "sources"), "write": "via scripts/sources.py only",
             "what": "copies of the documents THIS project cited"},
            {"path": rel(pdir / "project.json"), "write": False,
             "what": "this board's settings: layers, copper weight, temperature rise"},
            {"path": rel(pdir / "decisions.jsonl"), "write": False,
             "what": "append-only log of decisions. Never edit; the server appends "
                     "when you emit an answer action"},
            {"path": rel(pdir / "threads.jsonl"), "write": False,
             "what": "append-only, anchored discussions. The server appends on an ask action"},
            {"path": rel(pdir / "chats") + "/<id>.jsonl", "write": False,
             "what": "append-only conversations, one file per session. index.json "
                     "lists them; decisions and threads are shared across all of them"},
            {"path": rel(pdir / "chats") + "/<id>.memory.md", "write": False,
             "what": "what a conversation would otherwise forget: the student's "
                     "situation, what was ruled out and why, open promises. Bounded, "
                     "and rewritten by a separate call - do not edit it mid-turn"},
            {"path": rel(pdir / "notes.md"), "write": True,
             "what": "the project's notes: decisions, constraints, context. Nothing derives from it"},
            {"path": rel(pdir / "BOM.md"), "write": True,
             "what": "the bill of materials. The student also edits it in the UI"},
            {"path": rel(pdir / "design-model.json"), "write": False,
             "what": "DERIVED, rewritten every run. Read it if you want the full state"},
        ],
        "scripts": [
            {"run": "python3 scripts/sources.py list",
             "what": "what is already in the document library"},
            {"run": f"python3 scripts/sources.py get {pdir.name} <url> [name]",
             "what": "add a datasheet to this project. Use this rather than curl - "
                     "it records the url and sha256, which is what makes it citable"},
            {"run": "python3 scripts/sources.py fetch <url> [name]",
             "what": "add a document to the shared library only"},
            {"run": 'python3 scripts/sources.py verify <name> "<quote>"',
             "what": "is this quote really in that document? Run it BEFORE you quote"},
            {"run": "python3 scripts/trace_width.py <amps> --oz <copper> --rise <degrees>",
             "what": "IPC-2221 trace width. Run it; never estimate a width yourself"},
            {"run": "python3 scripts/model.py <project>",
             "what": "the full design state, more than the summary above carries"},
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
    return {"home": str(home()), "config": str(path), "created": made}


if __name__ == "__main__":
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
