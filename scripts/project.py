"""
Project lifecycle: create from the template, list, read and write project.json.

A project is a folder and nothing else - no database, no index, no registry.
Drop a folder into projects/ and it is a project; zip one up and mail it and it
still works.  `ensure()` repairs a folder that is missing pieces, which is what
makes a hand-made folder as valid as a generated one.
"""
import datetime as dt
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import session  # noqa: E402
import store  # noqa: E402
import workspace  # noqa: E402

SCHEMA_VERSION = 1
# the design log. The conversation lives in chats/<id>.jsonl, one per session.
LOGS = ("bom-log.jsonl", "supply-log.jsonl", "proposals.jsonl", "library-log.jsonl", "sheet-log.jsonl")
DERIVED = ("design-model.json", "bom.json", "artifacts")


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def template_dir():
    return workspace.templates_dir() / "project"


def dir_of(name):
    return workspace.project_dir(name)


def meta_path(name):
    return dir_of(name) / "project.json"


def exists(name):
    return dir_of(name).is_dir()


# ---------------------------------------------------------------- create

def create(name, title=None, brief=""):
    """Instantiate the template under a free name. Returns the name used."""
    safe = _free_name(workspace.safe_name(name))
    dest = dir_of(safe)
    src = template_dir()
    if not src.is_dir():
        raise SystemExit(f"project template missing: {src}")

    shutil.copytree(src, dest)
    (dest / "sources").mkdir(exist_ok=True)
    (dest / "chats").mkdir(exist_ok=True)

    fills = {
        "__NAME__": safe,
        "__TITLE__": title or name or safe,
        "__BRIEF__": brief,
        "__NOW__": now(),
        "__OWNER__": workspace.get("user.name", "") or "",
    }
    for path in (dest / "project.json", dest / "README.md"):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for token, value in fills.items():
                text = text.replace(token, _escape(value, path.suffix))
            path.write_text(text, encoding="utf-8")

    session.create(safe, title="First conversation")

    meta = load_meta(safe)
    meta["schema_version"] = SCHEMA_VERSION
    # the board starts as a copy of your engineering defaults, then diverges
    meta["board"] = {**workspace.get("engineering_defaults", {}), **(meta.get("board") or {})}
    save_meta(safe, meta)
    return safe


def _escape(value, suffix):
    return json.dumps(value, ensure_ascii=False)[1:-1] if suffix == ".json" else value


def _free_name(safe):
    if not dir_of(safe).exists():
        return safe
    n = 2
    while dir_of(f"{safe}-{n}").exists():
        n += 1
    return f"{safe}-{n}"


def ensure(name):
    """Make an existing folder a complete project. Never destroys anything."""
    d = dir_of(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources").mkdir(exist_ok=True)
    (d / "chats").mkdir(exist_ok=True)
    for f in LOGS:
        (d / f).touch()
    (d / "netlist").mkdir(exist_ok=True)
    if not session.list_all(name):
        session.create(name, title="First conversation")
    if not (d / "idea.json").exists():
        store.save_idea(workspace.safe_name(name), store.load_idea(workspace.safe_name(name)))
    if not meta_path(name).exists():
        save_meta(name, {
            "schema_version": SCHEMA_VERSION,
            "name": workspace.safe_name(name),
            "title": name,
            "brief": "",
            "created": now(),
            "updated": now(),
            "owner": workspace.get("user.name", "") or "",
            "status": "draft",
            "tags": [],
            "board": dict(workspace.get("engineering_defaults", {})),
            "altium": {"project_file": "", "pcb_file": "", "outputs_dir": ""},
            "notes": "",
        })
    return workspace.safe_name(name)


# ---------------------------------------------------------------- metadata

def load_meta(name):
    path = meta_path(name)
    if not path.exists():
        return {"name": workspace.safe_name(name), "title": name, "board": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": workspace.safe_name(name), "title": name, "board": {},
                "error": "project.json is not valid JSON"}


def altium_link(name) -> dict:
    meta = load_meta(name)
    alt = meta.get("altium")
    if isinstance(alt, dict):
        return {
            "project_file": str(alt.get("project_file", "") or ""),
            "pcb_file": str(alt.get("pcb_file", "") or ""),
            "outputs_dir": str(alt.get("outputs_dir", "") or ""),
        }
    return {"project_file": "", "pcb_file": "", "outputs_dir": ""}


def set_altium_link(name, project_file="", pcb_file=None, outputs_dir=None) -> dict:
    meta = load_meta(name)
    link = meta.get("altium")
    if not isinstance(link, dict):
        link = {}

    if not project_file:
        link = {
            "project_file": "",
            "pcb_file": str(pcb_file or "") if pcb_file is not None else "",
            "outputs_dir": str(outputs_dir or "") if outputs_dir is not None else "",
        }
        meta["altium"] = link
        save_meta(name, meta)
        return link

    p_path = pathlib.Path(project_file).resolve()
    if pcb_file is None:
        computed_pcb = ""
        try:
            from altium.prjpcb import read_prjpcb
            summary = read_prjpcb(p_path)
            pcbs = summary.get("pcbs", [])
            if len(pcbs) == 1:
                computed_pcb = str((p_path.parent / pathlib.Path(pcbs[0].replace("\\", "/"))).resolve())
        except Exception:
            computed_pcb = ""
        link["pcb_file"] = computed_pcb
    else:
        link["pcb_file"] = str(pathlib.Path(pcb_file).resolve()) if pcb_file else ""

    if outputs_dir is None:
        link["outputs_dir"] = str((p_path.parent / "Outputs").resolve())
    else:
        link["outputs_dir"] = str(pathlib.Path(outputs_dir).resolve()) if outputs_dir else ""

    link["project_file"] = str(p_path)
    meta["altium"] = link
    save_meta(name, meta)
    return link


def save_meta(name, meta):
    path = meta_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def touch(name, **fields):
    """Stamp `updated`, and set any fields passed along with it."""
    meta = load_meta(name)
    meta.update(fields)
    meta["updated"] = now()
    save_meta(name, meta)
    return meta


def board(name):
    """This board's engineering settings, with the global defaults underneath."""
    return {**workspace.get("engineering_defaults", {}), **(load_meta(name).get("board") or {})}


# ---------------------------------------------------------------- listing

def _lines(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def list_all():
    """Every project in the workspace, newest activity first."""
    root = workspace.projects_dir()
    root.mkdir(parents=True, exist_ok=True)
    out = []
    for d in root.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta = load_meta(d.name)
        idea = store.load_idea(d.name)
        sessions = session.list_all(d.name)
        stamps = [r.get("updated", "") for r in sessions] + [meta.get("updated", "")]
        out.append({
            "name": d.name,
            "title": meta.get("title") or d.name,
            "brief": idea.get("goal") or meta.get("brief") or "",
            "status": meta.get("status", "draft"),
            "lines": len(store.bom_lines(d.name)),
            "sheets": len(store.sheet_ids(d.name)),
            "sessions": len(sessions),
            "messages": sum(x.get("messages", 0) for x in sessions),
            "confirmed": bool(idea.get("confirmed")),
            "updated": max(stamps) if any(stamps) else "",
        })
    out.sort(key=lambda p: p["updated"], reverse=True)
    return out


# ---------------------------------------------------------------- reset

def reset(name):
    """Back to empty. Your notes and uploaded sources are untouched."""
    d = dir_of(name)
    if not d.exists():
        raise SystemExit(f"no such project: {name}")
    for f in LOGS + ("design-model.json", "bom.json", "idea.json"):
        (d / f).unlink(missing_ok=True)
    for sub in ("artifacts", "chats", "netlist", "exports", "library"):
        shutil.rmtree(d / sub, ignore_errors=True)
    ensure(name)
    touch(name)
    return workspace.safe_name(name)


if __name__ == "__main__":
    import oscompat
    oscompat.utf8_stdio()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "new":
        print(create(sys.argv[2] if len(sys.argv) > 2 else "untitled"))
    elif cmd == "reset":
        print(f"reset {reset(sys.argv[2] if len(sys.argv) > 2 else workspace.default_project())}")
    elif cmd == "show":
        print(json.dumps(load_meta(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        for p in list_all():
            print(f"{p['name']:24} {p['lines']:>3} BOM lines  {p['updated']}  {p['brief'][:40]}")
